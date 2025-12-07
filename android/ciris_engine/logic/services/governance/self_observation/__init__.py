"""
Self-Observation Service Module

Enables the agent to observe its own behavior patterns and generate insights
for continuous learning. This service coordinates:
- IdentityVarianceMonitor (tracks drift from baseline identity)
- PatternAnalysisLoop (detects patterns and stores insights)
- Configurable pattern detection algorithms (via graph config)

The agent can modify its own observation algorithms through graph configuration,
enabling meta-learning and self-directed analytical evolution.
"""

from .service import ObservationCycle, ObservationState, SelfObservationService

__all__ = [
    "SelfObservationService",
    "ObservationState",
    "ObservationCycle",
]
