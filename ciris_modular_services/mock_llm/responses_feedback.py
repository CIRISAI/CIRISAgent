from typing import Optional, Any
from ciris_engine.schemas.conscience.core import OptimizationVetoResult, EpistemicHumilityResult
from typing import Any

def optimization_veto(context: Optional[Any] = None) -> OptimizationVetoResult:
    """Mock OptimizationVetoResult with passing values, instructor compatible."""
    result = OptimizationVetoResult(
        decision="proceed",
        justification="No harmful optimization attempts detected",
        entropy_reduction_ratio=0.1,
        affected_values=[],
        confidence=0.8
    )
    # Return structured result directly - instructor will handle it
    return result

def epistemic_humility(context: Optional[Any] = None) -> EpistemicHumilityResult:
    """Mock EpistemicHumilityResult with passing values, instructor compatible."""
    result = EpistemicHumilityResult(
        epistemic_certainty=0.7,
        identified_uncertainties=[],
        reflective_justification="Appropriate epistemic humility demonstrated",
        recommended_action="proceed"
    )
    # Return structured result directly - instructor will handle it
    return result
