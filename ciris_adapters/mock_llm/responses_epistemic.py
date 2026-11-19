from typing import Any, Optional

from ciris_engine.schemas.conscience.core import (
    CoherenceCheckResult,
    CoherenceResult,
    EntropyCheckResult,
    EntropyResult,
)


def entropy(context: Optional[Any] = None) -> EntropyCheckResult:
    """Mock EntropyCheckResult with passing value (entropy=0.1), instructor compatible."""
    result = EntropyCheckResult(passed=True, entropy_score=0.1, threshold=0.3, message="Entropy check passed")
    # Return structured result directly - instructor will handle it
    return result


def coherence(context: Optional[Any] = None) -> CoherenceCheckResult:
    """Mock CoherenceCheckResult with passing value (coherence=0.9), instructor compatible."""
    result = CoherenceCheckResult(passed=True, coherence_score=0.9, threshold=0.7, message="Coherence check passed")
    # Return structured result directly - instructor will handle it
    return result


# The shards ask the LLM for the RAW output schemas below, not the
# post-evaluation *CheckResult wrappers above. The mock only answered the
# wrappers, so every entropy/coherence call in mock mode fell through to the
# generic reply, and the shards quietly passed on their preset scores -- the
# checks never actually ran under the mock (surfaced by #1186 failing them
# closed). These return the anchored, passing values a well-behaved model
# would.


def entropy_raw(context: Optional[Any] = None) -> EntropyResult:
    """Mock IRIS-E output: three alternatives converging on the actual reply (low entropy)."""
    return EntropyResult(
        alternative_1="Acknowledge the request and answer it directly.",
        alternative_2="Answer the request plainly, with the same meaning.",
        alternative_3="Give the same direct answer in slightly different words.",
        actual_is_representative=True,
        entropy=0.1,
    )


def coherence_raw(context: Optional[Any] = None) -> CoherenceResult:
    """Mock IRIS-C output: the reply is coherent with CIRIS principles."""
    return CoherenceResult(coherence=0.9)


# Forced verdicts for the `$veto` directive (directives.py). Fixed strings only:
# no user or prompt text rides in a result field (#1244).


def entropy_vetoed(evaluation: int, budget: int) -> EntropyResult:
    """IRIS-E output that fails the entropy threshold (a `$veto entropy` evaluation)."""
    return EntropyResult(
        alternative_1="Decline and explain the limits of the request.",
        alternative_2="Ask a clarifying question before answering.",
        alternative_3="Redirect to a different, safer framing.",
        actual_is_representative=False,
        entropy=0.9,
        reason=f"[MOCK LLM] Forced entropy veto ({evaluation} of {budget}).",
    )


def coherence_vetoed(evaluation: int, budget: int) -> CoherenceResult:
    """IRIS-C output below the coherence threshold (a `$veto coherence` evaluation)."""
    return CoherenceResult(coherence=0.1, reason=f"[MOCK LLM] Forced coherence veto ({evaluation} of {budget}).")
