"""conscience components."""

from .core import CoherenceConscience, EntropyConscience, EpistemicHumilityConscience, OptimizationVetoConscience
from .interface import ConscienceInterface
from .registry import conscienceRegistry
from .thought_depth_guardrail import ThoughtDepthGuardrail

__all__ = [
    "ConscienceInterface",
    "conscienceRegistry",
    "EntropyConscience",
    "CoherenceConscience",
    "OptimizationVetoConscience",
    "EpistemicHumilityConscience",
    "ThoughtDepthGuardrail",
]
