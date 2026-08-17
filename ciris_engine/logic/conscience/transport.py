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
timeout. Transport failures must FAIL FAST.

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
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:  # pragma: no cover
    pass

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
    return f"{shard} DID NOT RUN — {cat} reaching the model ({type(exc).__name__}: {exc}). " "This is not a judgement about the action."


def unavailable_result(shard: str, exc: BaseException, check_timestamp: object = None) -> "ConscienceCheckResult":
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

    kwargs = {}
    if check_timestamp is not None:
        kwargs["check_timestamp"] = check_timestamp
    return ConscienceCheckResult(
        status=ConscienceStatus.ERROR,
        passed=False,
        reason=reason,
        check_ran=False,
        **kwargs,
    )
