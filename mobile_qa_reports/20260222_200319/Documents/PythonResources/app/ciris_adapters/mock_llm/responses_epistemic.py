from typing import Any, Optional

from ciris_engine.schemas.conscience.core import CoherenceCheckResult, EntropyCheckResult


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
