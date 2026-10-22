"""Claude over the native HTTPS API, for builds that cannot ship the ``anthropic`` SDK.

The iOS bundle cannot carry the SDK: every ``anthropic`` release requires
``jiter``, a native Rust extension with no iOS wheels (CIRISAgent#1298). Without
it the agent fell back to an OpenAI client pointed at ``openrouter.ai`` and sent
it the user's *Anthropic* API key - a credential handed to a third party, for a
chat that could not work there anyway.

This module calls the Claude API directly with ``httpx`` (already bundled
everywhere): ``POST /v1/messages`` for chat, ``GET /v1/models`` for the live
model list, ``GET /v1/models/{id}`` to validate a key and model. These are the
API the SDK itself wraps; the version is pinned by the ``anthropic-version``
header, and within a version Anthropic keeps existing inputs and outputs.

It is used ONLY when ``import anthropic`` fails. Desktop, server and Android keep
the SDK path unchanged.

Structured output works the way the OpenAI-compatible path's instructor JSON
mode does: the response model's JSON schema goes in the system prompt, the reply
is validated with pydantic, and a mismatch is re-asked with the validation error.
Forced tool use is avoided on purpose: ``tool_choice`` ``any``/``tool`` returns a
400 on current Claude models.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple, Type, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

logger = logging.getLogger(__name__)

ANTHROPIC_API_URL = "https://api.anthropic.com"
#: Pinned: the agent sends only fields this version defines. (2026-10-21 also
#: drops temperature/top_p/top_k; this path never sends them either way.)
ANTHROPIC_API_VERSION = "2023-06-01"
#: Schema-mismatch re-asks after the first reply, as instructor's reask does.
DEFAULT_REASK_ATTEMPTS = 2

ModelT = TypeVar("ModelT", bound=BaseModel)


class AnthropicStructuredOutputError(ValueError):
    """Claude's reply never matched the response model, re-asks included."""


class AnthropicRefusalError(RuntimeError):
    """Claude declined the request (``stop_reason: "refusal"``)."""


@dataclass
class _Usage:
    """Token counts under both naming schemes the service reads."""

    input_tokens: int = 0
    output_tokens: int = 0

    @property
    def prompt_tokens(self) -> int:
        return self.input_tokens

    @property
    def completion_tokens(self) -> int:
        return self.output_tokens


@dataclass
class AnthropicCompletion:
    """The parts of a Messages response the LLM service reads after a call."""

    id: str
    model: str
    stop_reason: Optional[str]
    usage: _Usage = field(default_factory=_Usage)


def _raise_for_status(response: httpx.Response) -> None:
    """Raise the OpenAI SDK's exception for an HTTP error, so the service's handlers apply unchanged.

    The LLM service catches openai's AuthenticationError / BadRequestError /
    RateLimitError / InternalServerError (and httpx.TransportError); raising the
    same classes keeps auth handling, circuit breaking and 400 remediation
    working on this path without a second set of handlers.
    """
    if response.status_code < 400:
        return
    import openai

    try:
        body: Any = response.json()
    except ValueError:
        body = response.text
    detail = body.get("error", {}).get("message") if isinstance(body, dict) else None
    message = f"Anthropic API {response.status_code}: {detail or response.text[:300]}"
    status = response.status_code
    if status == 400:
        raise openai.BadRequestError(message, response=response, body=body)
    if status == 401:
        raise openai.AuthenticationError(message, response=response, body=body)
    if status == 403:
        raise openai.PermissionDeniedError(message, response=response, body=body)
    if status == 404:
        raise openai.NotFoundError(message, response=response, body=body)
    if status == 429:
        raise openai.RateLimitError(message, response=response, body=body)
    if status >= 500:
        raise openai.InternalServerError(message, response=response, body=body)
    raise openai.APIStatusError(message, response=response, body=body)


class AnthropicHTTPClient:
    """A minimal async client for the Claude API over HTTPS."""

    def __init__(
        self,
        api_key: str,
        timeout: float = 60.0,
        base_url: str = ANTHROPIC_API_URL,
        transport: Optional[httpx.AsyncBaseTransport] = None,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url
        self.timeout = timeout
        self._transport = transport  # tests inject an httpx.MockTransport
        self._http: Optional[httpx.AsyncClient] = None

    def _headers(self) -> Dict[str, str]:
        return {
            "x-api-key": self.api_key,
            "anthropic-version": ANTHROPIC_API_VERSION,
            "content-type": "application/json",
        }

    def _client(self) -> httpx.AsyncClient:
        if self._http is None or self._http.is_closed:
            self._http = httpx.AsyncClient(timeout=self.timeout, transport=self._transport)
        return self._http

    def _url(self, path: str) -> str:
        return f"{str(self.base_url).rstrip('/')}{path}"

    async def create_message(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        response = await self._client().post(self._url("/v1/messages"), headers=self._headers(), json=payload)
        _raise_for_status(response)
        data: Dict[str, Any] = response.json()
        return data

    async def list_model_ids(self) -> List[str]:
        """Every model id this key can see, following pagination."""
        ids: List[str] = []
        params: Dict[str, Any] = {"limit": 100}
        while True:
            response = await self._client().get(self._url("/v1/models"), headers=self._headers(), params=params)
            _raise_for_status(response)
            page = response.json()
            ids.extend(str(m["id"]) for m in page.get("data", []) if isinstance(m, dict) and m.get("id"))
            if not page.get("has_more") or not page.get("last_id"):
                return ids
            params = {"limit": 100, "after_id": page["last_id"]}

    async def retrieve_model(self, model: str) -> Dict[str, Any]:
        """The model record; raises NotFoundError for an unknown model, AuthenticationError for a bad key."""
        response = await self._client().get(self._url(f"/v1/models/{model}"), headers=self._headers())
        _raise_for_status(response)
        data: Dict[str, Any] = response.json()
        return data

    async def aclose(self) -> None:
        if self._http is not None:
            await self._http.aclose()


_DATA_URL = re.compile(r"^data:(?P<media>[\w/+.-]+);base64,(?P<data>.+)$", re.S)


def _convert_block(block: Any) -> Dict[str, Any]:
    """One OpenAI-style content block as a Messages API block."""
    if isinstance(block, dict) and block.get("type") == "image_url":
        url = (block.get("image_url") or {}).get("url", "")
        match = _DATA_URL.match(url)
        if match:
            return {
                "type": "image",
                "source": {"type": "base64", "media_type": match.group("media"), "data": match.group("data")},
            }
        return {"type": "image", "source": {"type": "url", "url": url}}
    if isinstance(block, dict) and block.get("type") == "text":
        return {"type": "text", "text": str(block.get("text", ""))}
    return {"type": "text", "text": str(block)}


def convert_messages(messages: Sequence[Dict[str, Any]]) -> Tuple[str, List[Dict[str, Any]]]:
    """OpenAI-style messages -> (system text, Messages API messages)."""
    system_parts: List[str] = []
    out: List[Dict[str, Any]] = []
    for message in messages:
        role = message.get("role")
        content = message.get("content", "")
        if role == "system":
            if isinstance(content, list):
                system_parts.extend(str(b.get("text", "")) for b in content if isinstance(b, dict))
            else:
                system_parts.append(str(content))
            continue
        api_role = "assistant" if role == "assistant" else "user"
        if isinstance(content, list):
            out.append({"role": api_role, "content": [_convert_block(b) for b in content]})
        else:
            out.append({"role": api_role, "content": str(content)})
    return "\n\n".join(p for p in system_parts if p), out


def _schema_instruction(response_model: Type[BaseModel]) -> str:
    schema = json.dumps(response_model.model_json_schema(), separators=(",", ":"))
    return (
        "Respond with ONLY a JSON object that validates against this JSON schema. "
        "No prose, no code fences, nothing before or after the object.\n"
        f"JSON schema: {schema}"
    )


def _text_of(data: Dict[str, Any]) -> str:
    return "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")


def _extract_json(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```[a-zA-Z]*\s*|\s*```$", "", stripped)
    start, end = stripped.find("{"), stripped.rfind("}")
    return stripped[start : end + 1] if start != -1 and end > start else stripped


def _reask_attempts(max_retries: Any) -> int:
    return max_retries if isinstance(max_retries, int) and max_retries >= 0 else DEFAULT_REASK_ATTEMPTS


class _Completions:
    def __init__(self, client: AnthropicHTTPClient) -> None:
        self._client = client

    async def create_with_completion(
        self,
        *,
        model: str,
        messages: Sequence[Dict[str, Any]],
        response_model: Type[ModelT],
        max_tokens: int = 4096,
        max_retries: Any = None,
        **_ignored: Any,
    ) -> Tuple[ModelT, AnthropicCompletion]:
        """instructor's ``create_with_completion`` over the native Messages API.

        ``temperature``, ``extra_body`` (OpenRouter routing, metadata) and seeds
        are accepted and not sent: current Claude models reject non-default
        sampling parameters, and the rest belongs to other providers.
        """
        system, api_messages = convert_messages(messages)
        system = f"{system}\n\n{_schema_instruction(response_model)}" if system else _schema_instruction(response_model)
        total = _Usage()
        last_error: Optional[Exception] = None

        for attempt in range(_reask_attempts(max_retries) + 1):
            data = await self._client.create_message(
                {"model": model, "max_tokens": max_tokens, "system": system, "messages": api_messages}
            )
            usage = data.get("usage") or {}
            total.input_tokens += int(usage.get("input_tokens", 0) or 0)
            total.output_tokens += int(usage.get("output_tokens", 0) or 0)
            completion = AnthropicCompletion(
                id=str(data.get("id", "")),
                model=str(data.get("model", model)),
                stop_reason=data.get("stop_reason"),
                usage=total,
            )
            if data.get("stop_reason") == "refusal":
                category = (data.get("stop_details") or {}).get("category")
                raise AnthropicRefusalError(f"Claude declined the request (refusal, category={category})")

            text = _text_of(data)
            try:
                return response_model.model_validate_json(_extract_json(text)), completion
            except ValidationError as e:
                last_error = e
                logger.info(
                    "[ANTHROPIC_HTTP] %s reply did not match the schema (attempt %d): %s",
                    response_model.__name__,
                    attempt + 1,
                    str(e)[:300],
                )
                api_messages = api_messages + [
                    {"role": "assistant", "content": text or "(empty)"},
                    {
                        "role": "user",
                        "content": f"That reply did not validate against the schema:\n{e}\n"
                        "Reply again with ONLY the corrected JSON object.",
                    },
                ]
        raise AnthropicStructuredOutputError(
            f"{response_model.__name__}: no schema-valid reply after re-asks: {last_error}"
        ) from last_error


class _Chat:
    def __init__(self, client: AnthropicHTTPClient) -> None:
        self.completions = _Completions(client)


class AnthropicHTTPInstructor:
    """Stands in for ``instructor.from_anthropic(...)``: ``.client`` and ``.chat.completions``."""

    def __init__(self, client: AnthropicHTTPClient) -> None:
        self.client = client
        self.chat = _Chat(client)
