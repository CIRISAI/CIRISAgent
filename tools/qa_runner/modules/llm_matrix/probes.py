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
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

if TYPE_CHECKING:  # annotation-only; `from __future__ import annotations` defers it
    from ciris_engine.logic.adapters.api.routes.setup.models import LLMValidationResponse

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
    # Google wraps its error in a LIST — [{"error": {...}}] — observed live.
    # Without this unwrap every Google failure recorded code=None/message=None,
    # so fixtures replayed with no body and could only exercise the legacy
    # substring fallback: the capture side of the same defect the product's
    # typed walker had, and it froze the gap measurement for one provider.
    if isinstance(body, list) and body and isinstance(body[0], dict):
        body = body[0]
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

    def _verdict_from_response(self, response: "LLMValidationResponse") -> ClassifierVerdict:
        """A verdict for a product response that never involved an exception —
        the pre-network refusals (no model selected, whitespace key)."""
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

        # OMITTED-model cells run the REAL product path, which now refuses
        # before any network I/O — the fabricated-substitution behaviour this
        # branch used to reproduce was deleted (Lane A / #1078-class). Calling
        # the product rather than mimicking it means this measurement follows
        # the product: if the substitution ever comes back, effective_model
        # will name it again and the FABRICATED_MODEL findings re-fire.
        if cell.requested_model is None and cell.probe is not ProbeKind.CHAT_MAX_TOKENS_OVER_CAP:
            from ciris_engine.logic.adapters.api.routes.setup.llm_validation import (
                _validate_llm_connection,
            )
            from ciris_engine.logic.adapters.api.routes.setup.models import LLMValidationRequest

            started = time.monotonic()
            product_verdict = await _validate_llm_connection(
                LLMValidationRequest(
                    provider=cell.provider, api_key=api_key, base_url=cell.client_base_url, model=None
                )
            )
            elapsed_ms = (time.monotonic() - started) * 1000.0
            outcome = LLMProbeOutcome(
                succeeded=bool(product_verdict.valid),
                http_status=None,
                effective_model=None,  # nothing was sent anywhere, which is the fix
                latency_ms=elapsed_ms,
            )
            return outcome, self._verdict_from_response(product_verdict)

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

    async def _list_models_direct(
        self, sdk: str, api_key: str, base_url: Optional[str]
    ) -> Tuple[bool, Optional[BaseException]]:
        """Ask the provider's models endpoint directly — NO model named.

        Shares the product's lister, so a provider envelope quirk is learned
        once. Together's bare-array /models previously fooled the product into
        showing a cached catalogue AND fooled this probe into reporting a dead
        key — the same quirk, two wrong conclusions, because each had its own
        copy of the call.
        """
        from ciris_engine.logic.services.runtime.llm_service.model_listing import list_model_ids

        try:
            await list_model_ids(sdk, api_key, base_url, timeout=self.timeout)
        except BaseException as exc:  # noqa: BLE001 - the classifier reads the exception
            return False, exc
        return True, None

    async def run_credential_probe(
        self, cell: MatrixCell, spec: ProviderSpec, api_key: str
    ) -> LLMProbeOutcome:
        """Is this CREDENTIAL valid? Answered without naming a model.

        Liveness used to be established with a minimal completion, which cannot
        be asked without naming a model — so a decommissioned model reported as
        a bad key. That happened: Groq's cheap_model was retired, the preflight
        got 404, and a perfectly live credential was classified OTHER and its
        whole column skipped.

        That is the same defect this harness exists to find, one level up. The
        wizard fabricates a model when the user chose none; the probe fabricated
        one when the question did not need one at all. Authentication and model
        availability are different questions, and a probe that conflates them
        cannot answer either cleanly.

        /models answers it with no model: 200 means the key works, 401 means it
        does not, and a retired model cannot make a live key look dead.
        """
        started = time.monotonic()
        self.live_call_count += 1
        ok, exc = await self._list_models_direct(spec.sdk, api_key, cell.base_url)
        elapsed_ms = (time.monotonic() - started) * 1000.0

        if ok:
            return LLMProbeOutcome(succeeded=True, http_status=200, latency_ms=elapsed_ms)
        outcome, _ = self._capture_failure(exc, cell, None, elapsed_ms)  # type: ignore[arg-type]
        return outcome

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
        # An omitted model runs the REAL product path in dry-run too: the
        # refusal happens before any network I/O, so replaying a recording of
        # it is strictly worse than executing it — the recording carries no
        # exception (nothing raised), which replayed as an empty
        # "Connection failed". Same branch as the live executor.
        if cell.requested_model is None and cell.probe is not ProbeKind.CHAT_MAX_TOKENS_OVER_CAP:
            from ciris_engine.logic.adapters.api.routes.setup.llm_validation import (
                _validate_llm_connection,
            )
            from ciris_engine.logic.adapters.api.routes.setup.models import LLMValidationRequest

            product_verdict = await _validate_llm_connection(
                LLMValidationRequest(
                    provider=cell.provider, api_key=api_key or "sk-dry-run", base_url=cell.client_base_url, model=None
                )
            )
            outcome = LLMProbeOutcome(
                succeeded=bool(product_verdict.valid),
                http_status=None,
                effective_model=None,
                latency_ms=0.0,
                from_fixture=True,
            )
            return outcome, self._verdict_from_response(product_verdict)

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

        # Replay the RECORDED failure through the REAL classifier, structure and
        # all: the classifier is typed-first now, so the replay must carry the
        # recorded status and body or it can only ever exercise the legacy
        # substring fallback — and the gap measurement goes blind to fixes.
        # Transport failures carry no provider body — their entire identity is
        # the exception TYPE, which the classifier now tests with isinstance.
        # Rebuild the real type for the two the product distinguishes; every
        # body-carrying failure replays through ReplayedProviderError, which
        # carries the recorded status and body for the typed walker.
        exc_type = outcome.exception_type or "recorded"
        replayed: BaseException
        if exc_type.endswith("APITimeoutError"):
            import httpx
            from openai import APITimeoutError

            replayed = APITimeoutError(request=httpx.Request("POST", "https://replay.invalid/v1"))
        elif exc_type.endswith("APIConnectionError"):
            import httpx
            from openai import APIConnectionError

            replayed = APIConnectionError(request=httpx.Request("POST", "https://replay.invalid/v1"))
        else:
            replayed = ReplayedProviderError(
                outcome.exception_str or "",
                exception_type=exc_type,
                status_code=outcome.http_status,
                error_code=outcome.provider_error_code,
                error_message=outcome.provider_error_message,
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
