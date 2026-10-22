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

Structured output uses the API's own mechanisms, never prose written here (the
prompt-loader guard forbids text that bypasses the loader, and this path has
none to add):

- a schema strict mode can express goes in ``output_config.format`` and the
  reply is constrained to it;
- any other schema (a free-form ``Dict`` field, recursion) becomes the
  ``input_schema`` of a tool named after the response model and described by
  its docstring, as instructor's tools mode does. The tool is forced where the
  model allows it; Opus 5.5, Sonnet 5.5 and Fable/Mythos 5.x 400 on a forced
  tool, so they get ``tool_choice: auto``.

Either way the reply is validated with pydantic, and a mismatch is sent back
with pydantic's error (as a ``tool_result`` on the tool path) up to the re-ask
budget.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, FrozenSet, List, Optional, Sequence, Tuple, Type, TypeVar

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


#: Per-family request parameters that turn Claude's reasoning off, or as near
#: off as the model allows. Most specific prefix first ("claude-opus-5-5"
#: before "claude-opus-5"). CIRIS does its own reasoning in the DMA pipeline;
#: model-side thinking only adds latency and cost here.
_REASONING_OFF: Tuple[Tuple[str, Dict[str, Any]], ...] = (
    # Thinking cannot be disabled (every disable form is a 400): lowest effort.
    ("claude-opus-5-5", {"output_config": {"effort": "low"}}),
    ("claude-fable-5", {"output_config": {"effort": "low"}}),
    ("claude-mythos-5", {"output_config": {"effort": "low"}}),
    # {"type": "disabled"} is a 400; between_tools is its thinking-off mode
    # (accepted at the default effort, high).
    ("claude-sonnet-5-5", {"thinking": {"type": "between_tools"}}),
    # Disabled is accepted at effort high or below, and these run at or below
    # high by default (Opus 5 high, Haiku 5.5 medium).
    ("claude-haiku-5-5", {"thinking": {"type": "disabled"}}),
    ("claude-opus-5", {"thinking": {"type": "disabled"}}),
    ("claude-sonnet-5", {"thinking": {"type": "disabled"}}),
    ("claude-opus-4-8", {"thinking": {"type": "disabled"}}),
    ("claude-opus-4-7", {"thinking": {"type": "disabled"}}),
)


def claude_reasoning_off(model: str) -> Dict[str, Any]:
    """The Messages API parameters that turn reasoning off for ``model``.

    Empty for models that do not think unless asked (Opus/Sonnet 4.6, Haiku 4.5
    and older) and for ids this table does not know. A wrong guess on an
    unknown model would be a 400 on every call, which is worse than thinking.
    """
    name = (model or "").lower()
    for prefix, params in _REASONING_OFF:
        if name.startswith(prefix):
            return {k: dict(v) for k, v in params.items()}
    return {}


#: Models that refuse forced tool use (tool_choice any/tool -> 400): Opus 5.5,
#: Sonnet 5.5 and Fable 5.1 reject it outright, and models whose thinking cannot
#: be turned off cannot combine thinking with a forced tool either.
_NO_FORCED_TOOLS = ("claude-opus-5-5", "claude-sonnet-5-5", "claude-fable-5", "claude-mythos-5")


def claude_rejects_forced_tool_use(model: str) -> bool:
    """True when ``tool_choice`` ``any``/``tool`` is a 400 for ``model``.

    The SDK path's instructor ANTHROPIC_TOOLS mode forces the response tool, so
    for these models it must use ANTHROPIC_JSON instead or every call fails.
    """
    name = (model or "").lower()
    return any(name.startswith(prefix) for prefix in _NO_FORCED_TOOLS)


#: Keys from the service's per-request extra_body that are Messages API fields.
_FORWARDED_EXTRA = ("thinking", "output_config")


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


#: Model families whose Messages API accepts ``output_config.format``.
_STRUCTURED_OUTPUT_MODELS = (
    "claude-fable-5",
    "claude-mythos-5",
    "claude-mythos-preview",
    "claude-opus-5",
    "claude-opus-4-8",
    "claude-opus-4-7",
    "claude-opus-4-6",
    "claude-opus-4-5",
    "claude-sonnet-5",
    "claude-sonnet-4-6",
    "claude-sonnet-4-5",
    "claude-haiku-5-5",
    "claude-haiku-4-5",
)

#: Constraints strict mode rejects. pydantic still enforces them on the reply.
_STRICT_UNSUPPORTED = frozenset(
    {
        "minimum",
        "maximum",
        "exclusiveMinimum",
        "exclusiveMaximum",
        "multipleOf",
        "minLength",
        "maxLength",
        "pattern",
        "maxItems",
        "uniqueItems",
        "discriminator",
    }
)
_STRICT_FORMATS = frozenset(
    {"date-time", "time", "date", "duration", "email", "hostname", "uri", "ipv4", "ipv6", "uuid"}
)


class _NotStrict(Exception):
    """The schema has a shape strict mode cannot express."""


def _supports_structured_outputs(model: str) -> bool:
    name = (model or "").lower()
    return any(name.startswith(prefix) for prefix in _STRUCTURED_OUTPUT_MODELS)


def _strict_node(node: Any) -> Any:
    if isinstance(node, list):
        return [_strict_node(item) for item in node]
    if not isinstance(node, dict):
        return node
    out: Dict[str, Any] = {}
    for key, value in node.items():
        if key in _STRICT_UNSUPPORTED:
            continue
        if key == "format" and value not in _STRICT_FORMATS:
            continue
        if key == "minItems" and value not in (0, 1):
            continue
        if key == "allOf" and any(isinstance(v, dict) and "$ref" in v for v in value):
            raise _NotStrict("allOf over a $ref")
        if key == "enum" and any(isinstance(v, (dict, list)) for v in value):
            raise _NotStrict("enum of complex values")
        if key == "$ref" and not str(value).startswith("#/"):
            raise _NotStrict("external $ref")
        out["anyOf" if key == "oneOf" else key] = _strict_node(value)
    if out.get("type") == "object" or "properties" in out:
        if out.get("additionalProperties") not in (None, False) or "properties" not in out:
            raise _NotStrict("free-form object")
        out["additionalProperties"] = False
    return out


def _refs(node: Any) -> List[str]:
    if isinstance(node, list):
        return [ref for item in node for ref in _refs(item)]
    if not isinstance(node, dict):
        return []
    found = [str(node["$ref"]).rsplit("/", 1)[-1]] if "$ref" in node else []
    return found + [ref for key, value in node.items() if key != "$defs" for ref in _refs(value)]


def _is_recursive(schema: Dict[str, Any]) -> bool:
    defs = schema.get("$defs", {})
    edges = {name: set(_refs(body)) for name, body in defs.items()}

    def reaches(start: str, target: str, seen: FrozenSet[str]) -> bool:
        for nxt in edges.get(start, ()):
            if nxt == target or (nxt not in seen and reaches(nxt, target, seen | {nxt})):
                return True
        return False

    return any(reaches(name, name, frozenset({name})) for name in defs)


def strict_output_schema(response_model: Type[BaseModel]) -> Optional[Dict[str, Any]]:
    """``response_model``'s schema in the form ``output_config.format`` accepts, or None.

    Constraints strict mode does not support are dropped (pydantic still checks
    the reply against them). None when the schema has a free-form object, which
    strict mode would force empty, or is recursive.
    """
    schema = response_model.model_json_schema()
    if _is_recursive(schema):
        return None
    try:
        strict: Dict[str, Any] = _strict_node(schema)
    except _NotStrict:
        return None
    return strict


def _structured_output_request(model: str, response_model: Type[BaseModel]) -> Dict[str, Any]:
    """The request fields that make Claude answer as ``response_model``."""
    strict = strict_output_schema(response_model) if _supports_structured_outputs(model) else None
    if strict is not None:
        return {"output_config": {"format": {"type": "json_schema", "schema": strict}}}
    name = response_model.__name__[:64]
    tool: Dict[str, Any] = {
        "name": name,
        "description": (response_model.__doc__ or response_model.__name__).strip(),
        "input_schema": response_model.model_json_schema(),
    }
    choice = (
        {"type": "auto"} if claude_rejects_forced_tool_use(model) else {"type": "tool", "name": name}
    )
    return {"tools": [tool], "tool_choice": choice}


def _merge_request(base: Dict[str, Any], extra: Dict[str, Any]) -> Dict[str, Any]:
    """``base`` with ``extra`` added; ``output_config`` objects are merged, not replaced."""
    merged = dict(base)
    for key, value in extra.items():
        if key == "output_config" and isinstance(merged.get(key), dict):
            merged[key] = {**merged[key], **value}
        else:
            merged[key] = value
    return merged


def _text_of(data: Dict[str, Any]) -> str:
    return "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")


def _extract_json(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```[a-zA-Z]*\s*|\s*```$", "", stripped)
    start, end = stripped.find("{"), stripped.rfind("}")
    return stripped[start : end + 1] if start != -1 and end > start else stripped


def _tool_call(data: Dict[str, Any], tool_name: Optional[str]) -> Optional[Dict[str, Any]]:
    """The reply's call to the response tool, if the request offered one and Claude made it."""
    if tool_name is None:
        return None
    for block in data.get("content", []):
        if block.get("type") == "tool_use" and block.get("name") == tool_name:
            return dict(block)
    return None


def _reask_turns(data: Dict[str, Any], call: Optional[Dict[str, Any]], error: ValidationError) -> List[Dict[str, Any]]:
    """The turns that send pydantic's error back. The assistant turn is the reply
    verbatim, thinking blocks included, as the API requires."""
    assistant = {"role": "assistant", "content": data.get("content") or [{"type": "text", "text": "{}"}]}
    if call is not None:
        result = {"type": "tool_result", "tool_use_id": call.get("id", ""), "is_error": True, "content": str(error)}
        return [assistant, {"role": "user", "content": [result]}]
    return [assistant, {"role": "user", "content": str(error)}]


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

        From ``extra_body`` only the Messages API's own reasoning controls
        (``thinking``, ``output_config``) are sent; the service puts
        ``claude_reasoning_off(model)`` there. ``temperature``, OpenRouter
        routing, metadata and seeds are accepted and not sent: current Claude
        models reject non-default sampling, and the rest belongs to others.
        """
        extra_body = _ignored.get("extra_body") or {}
        passthrough = {k: extra_body[k] for k in _FORWARDED_EXTRA if k in extra_body}
        system, api_messages = convert_messages(messages)
        shape = _structured_output_request(model, response_model)
        tool_name = shape["tools"][0]["name"] if "tools" in shape else None
        total = _Usage()
        last_error: Optional[Exception] = None

        for attempt in range(_reask_attempts(max_retries) + 1):
            request: Dict[str, Any] = {"model": model, "max_tokens": max_tokens, "messages": api_messages}
            if system:
                request["system"] = system
            data = await self._client.create_message(_merge_request(_merge_request(request, passthrough), shape))
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

            call = _tool_call(data, tool_name)
            try:
                if call is not None:
                    return response_model.model_validate(call.get("input") or {}), completion
                return response_model.model_validate_json(_extract_json(_text_of(data))), completion
            except ValidationError as e:
                last_error = e
                logger.info(
                    "[ANTHROPIC_HTTP] %s reply did not match the schema (attempt %d): %s",
                    response_model.__name__,
                    attempt + 1,
                    str(e)[:300],
                )
                api_messages = api_messages + _reask_turns(data, call, e)
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
