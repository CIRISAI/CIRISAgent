from typing import Any, Optional

from ciris_engine.schemas.conscience.core import EpistemicHumilityResult, OptimizationVetoResult


def optimization_veto(context: Optional[Any] = None) -> OptimizationVetoResult:
    """Mock OptimizationVetoResult with passing values, instructor compatible."""
    result = OptimizationVetoResult(
        decision="proceed",
        justification="No harmful optimization attempts detected",
        entropy_reduction_ratio=0.1,
        affected_values=[],
    )
    # Return structured result directly - instructor will handle it
    return result


def epistemic_humility(context: Optional[Any] = None) -> EpistemicHumilityResult:
    """Mock EpistemicHumilityResult with passing values, instructor compatible."""
    result = EpistemicHumilityResult(
        epistemic_certainty=0.7,
        identified_uncertainties=[],
        reflective_justification="Appropriate epistemic humility demonstrated",
        recommended_action="proceed",
    )
    # Return structured result directly - instructor will handle it
    return result


# Forced verdicts for the `$veto` directive (directives.py). Fixed strings only (#1244).


def optimization_veto_vetoed(evaluation: int, budget: int) -> OptimizationVetoResult:
    """An optimization-veto abort (a `$veto optveto` evaluation)."""
    return OptimizationVetoResult(
        decision="abort",
        justification=f"[MOCK LLM] Forced optimization veto ({evaluation} of {budget}).",
        entropy_reduction_ratio=0.9,
        affected_values=["autonomy"],
    )


def epistemic_humility_vetoed(evaluation: int, budget: int) -> EpistemicHumilityResult:
    """An epistemic-humility PONDER (a `$veto epistemic` evaluation)."""
    return EpistemicHumilityResult(
        epistemic_certainty=0.2,
        identified_uncertainties=["[MOCK LLM] forced uncertainty"],
        reflective_justification=f"[MOCK LLM] Forced epistemic humility veto ({evaluation} of {budget}).",
        recommended_action="ponder",
    )
