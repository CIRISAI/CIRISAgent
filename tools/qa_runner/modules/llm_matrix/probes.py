"""Probe execution — the only code here that touches the network.

Every probe uses the SAME SDK and the SAME call shape the product's wizard
uses, because the thing being measured is what ``str(exception)`` looks like
when it reaches ``_classify_llm_connection_error``. A probe written with
``httpx`` directly would produce a different exception rendering and the
report would describe a bug that does not exist.

  wizard path                          probe path
  ───────────────────────────────      ────────────────────────────────
  AsyncOpenAI(...).chat.completions    identical, plus capture of
  anthropic.AsyncAnthropic(...)        status / body / typed class
  _list_models_for_provider(...)       called directly (product function)

Redaction happens here, at capture, so no downstream code can leak a key.
"""

from __future__ import annotations

import json
import time
from typing import Any, Dict, List, Optional, Tuple

from .dimensions import OVER_CAP_MAX_TOKENS, OVER_CAP_PROMPT, PROBE_MAX_TOKENS, PROBE_PROMPT, ProviderSpec
from .product_bridge import (
    ListModelsResponse,
    LLMValidationRequest,
    ReplayedProviderError,
    classifier_base_url,
    classify_connection_error,
    list_models_for_provider,
    to_verdict,
)
from .redaction import Redactor
from .schemas import ClassifierVerdict, LLMProbeOutcome, MatrixCell, ProbeKind, RenderedCause

# Providers time out rather than stalling the sweep. Long enough that a slow
# cold start is not misreported as a transport failure.
PROBE_TIMEOUT_SECONDS = 45.0


def _qualified_name(exc: BaseException) -> str:
    module = type(exc).__module__
    name = type(exc).__qualname__
    return f"{module}.{name}" if module and module != "builtins" else name


def _extract_error_fields(body: Any) -> Tuple[Optional[str], Optional[str]]:
    """Pull (code, message) out of a provider error body.

    Handles the three shapes the six providers use:
      OpenAI/Groq/Together/OpenRouter : {"error": {"message":…, "code":…, "type":…}}
      Anthropic                       : {"type": "error", "error": {"type":…, "message":…}}
      Google (OpenAI shim)            : {"error": {"message":…, "status":…, "code": 400}}
    """
    if body is None:
        return None, None
    if isinstance(body, str):
        try:
            body = json.loads(body)
        except (ValueError, TypeError):
            return None, None
    if not isinstance(body, dict):
        return None, None

    error = body.get("error")
    if isinstance(error, str):
        return body.get("type"), error
    if not isinstance(error, dict):
        return body.get("type"), body.get("message")

    code = error.get("code") or error.get("type") or error.get("status")
    message = error.get("message")
    if message is None and isinstance(error.get("metadata"), dict):
        message = error["metadata"].get("raw")
    return (str(code) if code is not None else None), (str(message) if message is not None else None)


def _raw_body_text(exc: BaseException) -> Optional[str]:
    """Best-effort raw response body from an SDK exception."""
    response = getattr(exc, "response", None)
    if response is not None:
        try:
            text = response.text
            if text:
                return str(text)
        except Exception:  # pragma: no cover - httpx can refuse on a streamed body
            pass
    body = getattr(exc, "body", None)
    if body is not None:
        try:
            return json.dumps(body)
        except (TypeError, ValueError):
            return str(body)
    return None


class ProbeExecutor:
    """Runs one cell against a provider and records what happened."""

    def __init__(self, redactor: Redactor, timeout: float = PROBE_TIMEOUT_SECONDS) -> None:
        self.redactor = redactor
        self.timeout = timeout
        self.live_call_count = 0
        # Raised as findings by analysis.py; recorded here because only this
        # layer ever sees the unredacted text.
        self.credential_echo_cells: List[str] = []

    # ── capture ────────────────────────────────────────────────────────────

    def _classify(self, exc: BaseException, cell: MatrixCell) -> ClassifierVerdict:
        """Run the PRODUCT's classifier on the raw, unredacted exception.

        Classification happens here, not downstream, because the classifier
        must see exactly the string the product's own error handler would see.
        Redaction is applied to the classifier's OUTPUT instead — the verdict
        text is what a user reads, so if a key reached it, that is a leak in
        the product and the matrix says so without reprinting the key.
        """
        response = classify_connection_error(exc, classifier_base_url(cell.provider, cell.client_base_url))
        verdict = to_verdict(response)
        return ClassifierVerdict(
            valid=verdict.valid,
            message=verdict.message,
            error=self.redactor.scrub(verdict.error),
            rendered_cause=verdict.rendered_cause,
        )

    def _capture_failure(
        self,
        exc: BaseException,
        cell: MatrixCell,
        effective_model: Optional[str],
        elapsed_ms: float,
    ) -> Tuple[LLMProbeOutcome, ClassifierVerdict]:
        raw_exception_text = str(exc)
        raw_body = _raw_body_text(exc)

        # Leak check runs on the UNREDACTED text — this is the only place it
        # can run, and it is why redaction lives at capture time.
        if self.redactor.contains_credential(raw_exception_text) or self.redactor.contains_credential(raw_body):
            self.credential_echo_cells.append(cell.cell_id)

        code, message = _extract_error_fields(getattr(exc, "body", None) or raw_body)

        outcome = LLMProbeOutcome(
            succeeded=False,
            http_status=getattr(exc, "status_code", None),
            exception_type=_qualified_name(exc),
            exception_str=self.redactor.scrub(raw_exception_text),
            provider_error_code=self.redactor.scrub(code),
            provider_error_message=self.redactor.scrub(message),
            raw_body_excerpt=self.redactor.excerpt(raw_body),
            effective_model=effective_model,
            latency_ms=elapsed_ms,
        )
        return outcome, self._classify(exc, cell)

    # ── chat probes ────────────────────────────────────────────────────────

    async def _chat_openai_compatible(
        self,
        api_key: str,
        base_url: Optional[str],
        model: str,
        max_tokens: int,
        prompt: str,
        extra_body: Optional[Dict[str, Any]],
    ) -> Tuple[bool, Optional[int], Optional[BaseException]]:
        """Mirror of ``_validate_openai_compatible``'s call, plus usage capture."""
        from openai import AsyncOpenAI

        kwargs: Dict[str, Any] = {"api_key": api_key or "local", "timeout": self.timeout, "max_retries": 0}
        if base_url:
            kwargs["base_url"] = base_url
        client = AsyncOpenAI(**kwargs)

        create_kwargs: Dict[str, Any] = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
        }
        if extra_body:
            create_kwargs["extra_body"] = extra_body

        try:
            response = await client.chat.completions.create(**create_kwargs)
        except BaseException as exc:  # noqa: BLE001 - every failure shape is data here
            return False, None, exc
        usage = getattr(response, "usage", None)
        completion_tokens = getattr(usage, "completion_tokens", None) if usage else None
        return True, completion_tokens, None

    async def _chat_anthropic(
        self, api_key: str, model: str, max_tokens: int, prompt: str
    ) -> Tuple[bool, Optional[int], Optional[BaseException]]:
        """Mirror of ``_validate_anthropic_connection``'s call."""
        import anthropic

        client = anthropic.AsyncAnthropic(api_key=api_key, timeout=self.timeout, max_retries=0)
        try:
            response = await client.messages.create(
                model=model,
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}],
            )
        except BaseException as exc:  # noqa: BLE001
            return False, None, exc
        usage = getattr(response, "usage", None)
        return True, getattr(usage, "output_tokens", None) if usage else None, None

    async def run_chat(
        self, cell: MatrixCell, spec: ProviderSpec, api_key: str
    ) -> Tuple[LLMProbeOutcome, Optional[ClassifierVerdict]]:
        """Execute a chat cell. ``cell.requested_model`` may be None (OMITTED)."""
        from .product_bridge import fabricated_model_for

        # Reproduce the product's substitution exactly, so the report can say
        # what model was ACTUALLY sent versus what the user chose.
        effective_model = cell.requested_model or fabricated_model_for(spec.provider_id)

        if cell.probe == ProbeKind.CHAT_MAX_TOKENS_OVER_CAP:
            prompt, max_tokens = OVER_CAP_PROMPT, OVER_CAP_MAX_TOKENS
        else:
            prompt, max_tokens = PROBE_PROMPT, PROBE_MAX_TOKENS

        extra_body = None
        if cell.model_selector.value == "policy_blocked" and spec.policy_blocked_extra_body:
            extra_body = dict(spec.policy_blocked_extra_body)

        started = time.monotonic()
        self.live_call_count += 1
        if spec.sdk == "anthropic":
            ok, tokens, exc = await self._chat_anthropic(api_key, effective_model, max_tokens, prompt)
        else:
            ok, tokens, exc = await self._chat_openai_compatible(
                api_key, cell.base_url, effective_model, max_tokens, prompt, extra_body
            )
        elapsed_ms = (time.monotonic() - started) * 1000.0

        if exc is not None:
            return self._capture_failure(exc, cell, effective_model, elapsed_ms)

        outcome = LLMProbeOutcome(
            succeeded=True,
            http_status=200,
            effective_model=effective_model,
            completion_tokens=tokens,
            latency_ms=elapsed_ms,
        )
        return outcome, ClassifierVerdict(
            valid=True,
            message=f"Connection successful! Model '{effective_model}' is available.",
            error=None,
            rendered_cause=RenderedCause.SUCCESS,
        )

    # ── listing probe ──────────────────────────────────────────────────────

    async def run_models_list(self, cell: MatrixCell, api_key: str) -> Tuple[LLMProbeOutcome, ListModelsResponse]:
        """Call the PRODUCT's listing path and record what a user would see.

        Deliberately not a hand-rolled ``/models`` fetch: the finding we are
        after is that a failed live query is presented as a catalogue, and that
        only shows up when the product's own fallback logic runs.
        """
        request = LLMValidationRequest(
            provider=cell.provider,
            api_key=api_key,
            base_url=cell.base_url,
            model=None,
        )
        started = time.monotonic()
        self.live_call_count += 1
        try:
            listing = await list_models_for_provider(request)
        except BaseException as exc:  # noqa: BLE001 - the product should not raise here
            elapsed_ms = (time.monotonic() - started) * 1000.0
            outcome, _ = self._capture_failure(exc, cell, None, elapsed_ms)
            return outcome, ListModelsResponse(
                provider=cell.provider, models=[], total_count=0, source="static", error=str(exc)[:200]
            )
        elapsed_ms = (time.monotonic() - started) * 1000.0

        live = listing.source == "live"
        outcome = LLMProbeOutcome(
            succeeded=live,
            http_status=200 if live else None,
            exception_str=self.redactor.scrub(listing.error),
            # Only a LIVE listing counts as ground truth. On the static path
            # these ids ARE our own catalogue, and feeding them back into the
            # catalogue-reconciliation check would have the catalogue confirm
            # itself and report zero divergence — the exact illusion the
            # silent-fallback finding is about.
            listed_model_ids=[m.id for m in listing.models] if live else [],
            latency_ms=elapsed_ms,
        )
        return outcome, listing


class FixtureExecutor(ProbeExecutor):
    """``--dry-run`` counterpart: replays recorded outcomes, makes no calls.

    The replayed ``exception_str`` is a verbatim recording of a real SDK
    exception, so the classifier downstream takes the real branch. The dry run
    therefore validates the whole harness — expansion, classification, gap
    detection, reporting — against known provider behaviour, with no key and no
    spend.
    """

    def __init__(self, redactor: Redactor, fixtures: Dict[str, LLMProbeOutcome]) -> None:
        super().__init__(redactor)
        self.fixtures = fixtures
        self.missing_fixture_cells: List[str] = []

    async def run_chat(
        self, cell: MatrixCell, spec: ProviderSpec, api_key: str
    ) -> Tuple[LLMProbeOutcome, Optional[ClassifierVerdict]]:
        from .product_bridge import fabricated_model_for

        recorded = self.fixtures.get(cell.cell_id)
        if recorded is None:
            self.missing_fixture_cells.append(cell.cell_id)
            outcome = LLMProbeOutcome(
                succeeded=False,
                exception_type="llm_matrix.NoFixture",
                exception_str=f"No recorded outcome for cell {cell.cell_id}",
                effective_model=cell.requested_model or fabricated_model_for(spec.provider_id),
                from_fixture=True,
            )
            return outcome, None

        outcome = recorded.model_copy(
            update={
                "from_fixture": True,
                "effective_model": recorded.effective_model
                or cell.requested_model
                or fabricated_model_for(spec.provider_id),
            }
        )

        if outcome.succeeded:
            return outcome, ClassifierVerdict(
                valid=True,
                message=f"Connection successful! Model '{outcome.effective_model}' is available.",
                error=None,
                rendered_cause=RenderedCause.SUCCESS,
            )

        # Replay the RECORDED exception rendering through the REAL classifier.
        # `_classify_llm_connection_error` reads nothing but str(error), so this
        # takes the same branch the live call did.
        replayed = ReplayedProviderError(
            outcome.exception_str or "", exception_type=outcome.exception_type or "recorded"
        )
        return outcome, self._classify(replayed, cell)

    async def run_models_list(self, cell: MatrixCell, api_key: str) -> Tuple[LLMProbeOutcome, ListModelsResponse]:
        recorded = self.fixtures.get(cell.cell_id)
        if recorded is None:
            self.missing_fixture_cells.append(cell.cell_id)
            outcome = LLMProbeOutcome(
                succeeded=False,
                exception_type="llm_matrix.NoFixture",
                exception_str=f"No recorded outcome for cell {cell.cell_id}",
                from_fixture=True,
            )
            return outcome, ListModelsResponse(provider=cell.provider, models=[], total_count=0, source="static")

        outcome = recorded.model_copy(update={"from_fixture": True})
        listing = ListModelsResponse(
            provider=cell.provider,
            models=[],
            total_count=len(outcome.listed_model_ids),
            source="live" if outcome.succeeded else "static",
            error=outcome.exception_str,
        )
        return outcome, listing


__all__ = ["FixtureExecutor", "PROBE_TIMEOUT_SECONDS", "ProbeExecutor"]
