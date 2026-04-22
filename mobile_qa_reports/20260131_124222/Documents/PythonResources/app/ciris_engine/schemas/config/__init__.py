"""
Configuration schemas for CIRIS Engine.

Provides essential configuration schemas for bootstrap
and agent identity templates.
"""

from .agent import AgentTemplate
from .cognitive_state_behaviors import (
    CognitiveStateBehaviors,
    DreamBehavior,
    ShutdownBehavior,
    StateBehavior,
    StatePreservationBehavior,
    WakeupBehavior,
)
from .essential import (
    DatabaseConfig,
    EssentialConfig,
    OperationalLimitsConfig,
    SecurityConfig,
    ServiceEndpointsConfig,
    TelemetryConfig,
)

__all__ = [
    "EssentialConfig",
    "DatabaseConfig",
    "ServiceEndpointsConfig",
    "SecurityConfig",
    "OperationalLimitsConfig",
    "TelemetryConfig",
    "AgentTemplate",
    # Cognitive state behaviors
    "CognitiveStateBehaviors",
    "WakeupBehavior",
    "ShutdownBehavior",
    "StateBehavior",
    "DreamBehavior",
    "StatePreservationBehavior",
]
