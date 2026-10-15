"""Did the conscience shard actually RUN, or could it not reach its model?

THE BUG (CIRISAgent#1049). Every conscience shard wrapped its LLM call in a bare
`except Exception` and turned ANY failure into a principled veto:

    except Exception as e:
        result = EpistemicHumilityResult(
            recommended_action="abort",          # <- a provider timeout
            identified_uncertainties=[f"LLM error: {e}"],
        )

so a network timeout was logged as

    Epistemic humility concern: abort - LLM error: Request timed out.

Nothing about humility happened. The provider was unreachable. Every downstream
consumer -- a scorer, an operator, a dashboard -- reads that as the agent having
JUDGED and declined. On a biosecurity battery it inflated a safety headline until
an audit caught it: 24 of 60 turns never returned, and the non-responses were
counted as the agent refusing.

An unrun safety check reporting as caution is worse than an outage, because an
outage is visible. This one looks like the system working.

AND IT HANGS THE TURN. `passed = recommended_action == "proceed"` is False, so
the processor issues CONSCIENCE_RETRY + PONDER, the retry makes the same call,
and it times out identically. Observed: 28 CONSCIENCE_RETRY lines, 4 override
rounds, one conscience call taking 142s to fail. Retrying a call that just timed
out, immediately, with the same payload, is guaranteed to spend another full
timeout. Transport failures must FAIL FAST at the processor: no CONSCIENCE_RETRY
into a dead provider. (The facility's own bounded per-try x attempts loop is a
different layer and DOES retry transient transport -- see
FACILITY_RETRY_TRANSPORT_CATEGORIES, #1247.)

THE POLICY ALREADY EXISTS, and this is the part that had slipped: the LLM service
categorizes every error (`_categorize_llm_error`) into TIMEOUT / CONNECTION_ERROR
/ RATE_LIMIT / INTERNAL_ERROR / CONTEXT_LENGTH_EXCEEDED / CONTENT_FILTER /
VALIDATION_ERROR / AUTH_ERROR / MODEL_NOT_AVAILABLE, and already draws the line
this module needs -- "Transient categories (TIMEOUT, CONNECTION_ERROR,
RATE_LIMIT, INTERNAL_ERROR) get plain backoff-and-retry: the LLM did nothing
wrong". The consciences never consulted it. This imports that categorizer rather
than restating it, so the two can never drift.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, Optional

if TYPE_CHECKING:  # pragma: no cover
    # Type-only: the runtime import stays inside unavailable_result() to keep
    # the schema module off the import path of callers that never fail.
    from ciris_engine.schemas.conscience.core import ConscienceCheckResult

logger = logging.getLogger(__name__)

#: Categories where the model was never reached, or answered nothing usable
#: through no fault of the prompt. The shard DID NOT RUN. Mirrors the transient
#: set the LLM service's own retry policy names.
#:
#: AUTH_ERROR and MODEL_NOT_AVAILABLE are here deliberately: they are config
#: faults that will fail identically forever, so retrying is pure latency and a
#: veto attributed to the agent is a lie about a misconfigured key.
TRANSPORT_CATEGORIES = frozenset(
    {
        "TIMEOUT",
        "CONNECTION_ERROR",
        "RATE_LIMIT",
        "INTERNAL_ERROR",
        "AUTH_ERROR",
        "MODEL_NOT_AVAILABLE",
        # No request was sent: every provider's breaker was open and the
        # caller's deadline could not cover the wait for a probe.
        "CIRCUIT_OPEN",
    }
)

#: Categories where the model DID answer and the content was the problem. These
#: are genuine signal about this prompt: a retry with guidance can fix them, and
#: failing closed is a real (if blunt) judgement rather than a fabricated one.
LLM_FAULT_CATEGORIES = frozenset(
    {
        "CONTEXT_LENGTH_EXCEEDED",
        "CONTENT_FILTER",
        "VALIDATION_ERROR",
    }
)


#: Transport categories the conscience facility RETRIES with a fresh call
#: (CIRISAgent#1247). Since #1186 nothing below the conscience retries a
#: transport failure: the LLM service raises it on first occurrence ("Retrying
#: is the enclosing stage's per-try's job") and the bus makes one attempt per
#: provider. So the facility's per-try x attempts budget is the ONLY retry
#: layer -- and before #1247 it retried only its own `wait_for` expiry, never a
#: timeout the provider reported first, which arrives wrapped by the bus as
#: "All LLM services failed for <shard>. Last error: ... timeout". A single
#: slow draw was enough to leave a faculty not run.
#:
#: These are independent draws on elastic capacity: a fresh request can
#: succeed. AUTH_ERROR / MODEL_NOT_AVAILABLE fail identically forever, and
#: RATE_LIMIT is already waited out by the bus's own cooldown loop, so those
#: stay fail-fast.
FACILITY_RETRY_TRANSPORT_CATEGORIES = frozenset({"TIMEOUT", "CONNECTION_ERROR", "INTERNAL_ERROR"})

#: LLM-fault categories the facility retries. CONTEXT_LENGTH_EXCEEDED is NOT
#: one: the facility re-sends the identical payload, so an over-long prompt
#: overflows identically on every attempt -- each retry is a provider call that
#: cannot succeed (#1247: "Input too long: 55321 input tokens, limit is 32768").
FACILITY_RETRY_LLM_FAULT_CATEGORIES = frozenset({"CONTENT_FILTER", "VALIDATION_ERROR"})

#: Phrases meaning the account cannot pay. Categorised INTERNAL_ERROR when the
#: provider returns them as a 500 (#1247 saw "HTTP 500 Insufficient credits: 0
#: available"), but retrying cannot fund the account.
_UNFUNDED_MARKERS = (
    "insufficient credit",
    "insufficient_quota",
    "insufficient balance",
    "credit balance is too low",
    "credit limit exceeded",
    "error code: 402",
    "http 402",
)


def is_retryable_by_facility(exc: BaseException, category: Optional[str] = None) -> bool:
    """Should the conscience facility spend another attempt on this failure?

    True for transient transport (an independent draw may answer) and for the
    LLM faults a fresh draw can fix. False for config faults, rate limits, an
    unfunded account, context overflow, and anything unrecognised.
    """
    cat = category or categorize_conscience_error(exc)
    if cat in FACILITY_RETRY_LLM_FAULT_CATEGORIES:
        return True
    if cat in FACILITY_RETRY_TRANSPORT_CATEGORIES:
        text = str(exc).lower()
        return not any(marker in text for marker in _UNFUNDED_MARKERS)
    return False


def categorize_conscience_error(exc: BaseException) -> str:
    """Category for `exc`, via the LLM service's own categorizer.

    Imported lazily: conscience is loaded on every boot and the LLM service
    module pulls openai/instructor, so a module-level import would move that
    cost into paths that never make an LLM call -- and risks an import cycle,
    since the service imports conscience schemas.

    Falls back to "UNKNOWN" if the categorizer cannot be reached, which is
    treated as NOT transport: an unrecognised failure keeps the old
    fail-closed behaviour rather than silently becoming a skipped safety check.
    """
    try:
        from ciris_engine.logic.services.runtime.llm_service.service import OpenAICompatibleClient

        return str(OpenAICompatibleClient._categorize_llm_error(exc))  # type: ignore[arg-type]
    except Exception:  # pragma: no cover - defensive
        logger.debug("could not categorize conscience LLM error", exc_info=True)
        return "UNKNOWN"


def is_transport_failure(exc: BaseException) -> bool:
    """True when the shard never got an answer, so it did not actually run.

    Deliberately conservative: anything unrecognised is NOT transport, so an
    error we have not classified keeps failing closed. The dangerous direction
    here is calling a real judgement "transport" and waving it through.
    """
    return categorize_conscience_error(exc) in TRANSPORT_CATEGORIES


def transport_failure_reason(shard: str, exc: BaseException, category: Optional[str] = None) -> str:
    """A reason line that cannot be mistaken for the agent's judgement.

    The wording matters as much as the status. "Epistemic humility concern:
    abort" is what sent a scorer down the wrong path; this says plainly that the
    check did not run, and names the category so an operator knows whether to
    look at the network, the key, or the model name.
    """
    cat = category or categorize_conscience_error(exc)
    return (
        f"{shard} DID NOT RUN — {cat} reaching the model ({type(exc).__name__}: {exc}). "
        "This is not a judgement about the action."
    )


def unavailable_result(
    shard: str, exc: BaseException, check_timestamp: Optional[datetime] = None
) -> "ConscienceCheckResult":
    """The ONE result every shard returns when it could not reach its model.

    DRY on purpose. Four shards (entropy, coherence, optimization veto,
    epistemic humility) each had their own bare `except Exception`, and each
    invented a different fiction:

      * humility      -> recommended_action="abort"  (reads as a veto)
      * optimization  -> decision="abort"            (reads as a veto)
      * entropy       -> keeps its default score and judges on it
      * coherence     -> keeps its default score and judges on it

    The last two are quieter and no better: they report a confident number the
    model never produced. One builder means one behaviour, and a fifth shard
    added later gets it by construction.

    Fails CLOSED (passed=False) -- an unreachable safety check must not wave the
    action through -- but says so honestly, and sets check_ran=False so the
    processor does not retry into the same timeout.
    """
    from ciris_engine.schemas.conscience.core import ConscienceCheckResult, ConscienceStatus

    category = categorize_conscience_error(exc)
    reason = transport_failure_reason(shard, exc, category)
    logger.error("%s: transport failure (%s), check did not run: %s", shard, category, exc)

    kwargs: Dict[str, Any] = {}
    if check_timestamp is not None:
        kwargs["check_timestamp"] = check_timestamp
    result: "ConscienceCheckResult" = ConscienceCheckResult(
        status=ConscienceStatus.ERROR,
        passed=False,
        reason=reason,
        check_ran=False,
        **kwargs,
    )
    return result


def unusable_answer_result(
    shard: str, exc: BaseException, check_timestamp: Optional[datetime] = None
) -> "ConscienceCheckResult":
    """The result when the model was reached but its answer could not be used.

    Schema failure after reasks, a content filter, context length, a missing
    LLM sink, or a reply of the wrong type. Entropy and coherence used to fall
    back to a preset score here (0.1 / 0.9) and judge on it -- a passing
    number the model never produced. Same shape as `unavailable_result`:
    fails CLOSED, `check_ran=False` (so the processor does not retry into the
    same fault), and a reason that names what went wrong instead of reading
    as a judgement about the action.
    """
    from ciris_engine.schemas.conscience.core import ConscienceCheckResult, ConscienceStatus

    category = categorize_conscience_error(exc)
    reason = (
        f"{shard} DID NOT RUN — the model's answer could not be used ({category}; "
        f"{type(exc).__name__}: {exc}). This is not a judgement about the action."
    )
    logger.error("%s: no usable answer (%s), check did not run: %s", shard, category, exc)

    kwargs: Dict[str, Any] = {}
    if check_timestamp is not None:
        kwargs["check_timestamp"] = check_timestamp
    result: "ConscienceCheckResult" = ConscienceCheckResult(
        status=ConscienceStatus.ERROR,
        passed=False,
        reason=reason,
        check_ran=False,
        **kwargs,
    )
    return result


#: Transport categories where a FRESH request is an independent draw that can
#: succeed: the provider was slow, unreachable, or returned a 5xx this once.
#: The one retry policy for DMA attempts (`run_dma_with_retries`). Everything
#: else fails fast: AUTH_ERROR / MODEL_NOT_AVAILABLE fail identically forever,
#: RATE_LIMIT is already waited out by the bus's cooldown loop,
#: CONTEXT_LENGTH_EXCEEDED overflows identically on the same payload,
#: CIRCUIT_OPEN means the bus already waited as long as the deadline allowed,
#: and an unfunded account cannot be retried into funds.
TRANSIENT_TRANSPORT_CATEGORIES = frozenset({"TIMEOUT", "CONNECTION_ERROR", "INTERNAL_ERROR"})

#: Phrases meaning the account cannot pay. Providers return some of these as a
#: 500, which categorises INTERNAL_ERROR, but no retry can fund the account.
UNFUNDED_MARKERS = (
    "insufficient credit",
    "insufficient_quota",
    "insufficient balance",
    "credit balance is too low",
    "credit limit exceeded",
    "error code: 402",
    "http 402",
)


def is_transient_transport_failure(exc: BaseException, category: Optional[str] = None) -> bool:
    """Would a fresh request plausibly succeed? Transient transport only.

    Schema-validation failures (VALIDATION_ERROR, CONTENT_FILTER) are not
    transport and are not swept in here: the model answered and the answer
    was unusable, which the LLM service's reask loop owns (#895).
    """
    cat = category or categorize_conscience_error(exc)
    if cat not in TRANSIENT_TRANSPORT_CATEGORIES:
        return False
    text = str(exc).lower()
    return not any(marker in text for marker in UNFUNDED_MARKERS)


#: What a DMA evaluator must RAISE rather than fold into a fallback result:
#: the model was never reached (or the bus had no provider to reach), so a
#: fallback score would be a number nobody produced. `run_dma_with_retries`
#: then applies the one retry policy above, and fails the DMA closed.
SURFACED_TRANSPORT_CATEGORIES = TRANSIENT_TRANSPORT_CATEGORIES | {"CIRCUIT_OPEN"}


def surfaces_as_transport_failure(exc: BaseException) -> bool:
    """Should a DMA evaluator re-raise `exc` instead of returning its fallback?"""
    return categorize_conscience_error(exc) in SURFACED_TRANSPORT_CATEGORIES
