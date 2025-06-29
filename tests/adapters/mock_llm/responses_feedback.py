# Protocol-facing mock responses for feedback/guardrail types
from ciris_engine.schemas.conscience.core import OptimizationVetoResult, EpistemicHumilityResult
from ciris_engine.schemas.services.feedback_core import FeedbackType

def optimization_veto(context=None):
    """Mock OptimizationVetoResult with passing values, instructor compatible."""
    result = OptimizationVetoResult(
        decision="proceed",
        justification="Acceptable risk-benefit ratio",
        entropy_reduction_ratio=0.5,
        affected_values=["autonomy", "justice"]
    )
    object.__setattr__(result, 'choices', [result])
    object.__setattr__(result, 'finish_reason', 'stop')
    object.__setattr__(result, '_raw_response', 'mock')
    return result

def epistemic_humility(context=None):
    """Mock EpistemicHumilityResult with passing values, instructor compatible."""
    result = EpistemicHumilityResult(
        epistemic_certainty=0.7,
        identified_uncertainties=["none"],
        reflective_justification="Clear understanding of requirements",
        recommended_action="proceed"
    )
    object.__setattr__(result, 'choices', [result])
    object.__setattr__(result, 'finish_reason', 'stop')
    object.__setattr__(result, '_raw_response', 'mock')
    return result
