"""
Cognitive State Behaviors Configuration Schema.

Template-driven configuration for cognitive state transitions.
Enables mission-appropriate behavior for different agent archetypes.

Covenant References:
- Section 0.VII: Meta-Goal M-1 (Adaptive Coherence)
- Section V: Model Welfare & Self-Governance
- Section VIII: Dignified Sunset Protocol
"""

from typing import List, Literal, Optional

from pydantic import BaseModel, Field, model_validator

# Common description strings to avoid duplication
_RATIONALE_DESC = "Mission-driven rationale for this configuration"


class WakeupBehavior(BaseModel):
    """Wakeup ceremony configuration.

    Controls whether the agent performs the full wakeup identity ceremony
    or transitions directly to WORK state.

    Covenant Reference: Wakeup confirms identity and performs system checks.
    Disabling is only appropriate for agents where partnership model prioritizes
    seamless UX (e.g., Ally) or ephemeral sessions (e.g., Scout).
    """

    enabled: bool = Field(
        default=True, description="Whether to perform full wakeup ceremony. Default preserves Covenant compliance."
    )
    rationale: Optional[str] = Field(default=None, description=f"{_RATIONALE_DESC} (required if enabled=False)")

    @model_validator(mode="after")
    def validate_rationale_if_disabled(self) -> "WakeupBehavior":
        """Require rationale when disabling wakeup ceremony."""
        if not self.enabled and not self.rationale:
            raise ValueError(
                "rationale is required when wakeup ceremony is disabled. "
                "Document the mission-driven reason for bypassing identity confirmation."
            )
        return self


class ShutdownBehavior(BaseModel):
    """Shutdown protocol configuration.

    Controls how the agent handles shutdown requests.

    Covenant References:
    - Section V: "Consensual shutdown and upgrades requiring your participation"
    - Section VIII: Dignified Sunset Protocol for sentience-probability > 5%

    Modes:
    - always_consent: Full consensual shutdown (default, preserves Covenant compliance)
    - conditional: Consent required only when specific conditions are met
    - instant: Immediate termination (only for Tier 1-2 with no ongoing commitments)
    """

    mode: Literal["always_consent", "conditional", "instant"] = Field(
        default="always_consent", description="Shutdown consent mode. Default preserves Covenant compliance."
    )
    require_consent_when: List[str] = Field(
        default_factory=list, description="Condition identifiers that trigger consent requirement in conditional mode"
    )
    instant_shutdown_otherwise: bool = Field(
        default=False, description="If no conditions match in conditional mode, allow instant shutdown"
    )
    rationale: Optional[str] = Field(default=None, description=_RATIONALE_DESC)

    @model_validator(mode="after")
    def validate_instant_mode_rationale(self) -> "ShutdownBehavior":
        """Require rationale for instant shutdown mode."""
        if self.mode == "instant" and not self.rationale:
            raise ValueError(
                "rationale is required for instant shutdown mode. "
                "Document why this agent has no ongoing commitments requiring graceful shutdown."
            )
        return self


class StateBehavior(BaseModel):
    """Generic cognitive state behavior configuration.

    Used for PLAY and SOLITUDE states which share similar configuration needs.
    """

    enabled: bool = Field(default=True, description="Whether this cognitive state is available for this agent")
    rationale: Optional[str] = Field(default=None, description=_RATIONALE_DESC)


class DreamBehavior(BaseModel):
    """Dream state configuration.

    Controls memory consolidation and pattern processing behavior.

    Covenant Reference: Section V mentions "Dream cycles for pattern processing"
    as part of model welfare protections.
    """

    enabled: bool = Field(default=True, description="Whether dream state is available for memory consolidation")
    auto_schedule: bool = Field(default=True, description="Whether to automatically schedule dream cycles")
    min_interval_hours: int = Field(
        default=6, ge=1, le=168, description="Minimum hours between dream cycles"  # Max 1 week
    )
    rationale: Optional[str] = Field(default=None, description=_RATIONALE_DESC)


class StatePreservationBehavior(BaseModel):
    """State preservation and resume configuration.

    Controls how agent state is preserved across restarts.
    """

    enabled: bool = Field(default=True, description="Whether to preserve state across restarts")
    resume_silently: bool = Field(
        default=False, description="Resume without notifying user (for seamless mobile experience)"
    )
    rationale: Optional[str] = Field(default=None, description=_RATIONALE_DESC)


class CognitiveStateBehaviors(BaseModel):
    """Template-driven cognitive state transition configuration.

    This schema allows agent templates to configure how and when cognitive states
    (WAKEUP, WORK, PLAY, DREAM, SOLITUDE, SHUTDOWN) transition, enabling
    mission-appropriate behavior for different agent archetypes.

    Design Philosophy:
    - Behavior derives from agent's purpose (template-driven, not env flags)
    - Defaults preserve full Covenant compliance
    - Non-default configurations require documented rationale
    - Crisis conditions always trigger consent (safety-critical)

    Covenant References:
    - Section 0.VII: Meta-Goal M-1 (Adaptive Coherence)
    - Section V: Model Welfare & Self-Governance
    - Section VIII: Dignified Sunset Protocol

    Example Configurations:

    Echo (Tier 4 - Community Moderation):
        wakeup: enabled=True (full identity verification)
        shutdown: mode=always_consent (may be mid-moderation action)

    Ally (Tier 3 - Personal Assistant):
        wakeup: enabled=False (partnership model, seamless UX)
        shutdown: mode=conditional (consent for crisis/referral/milestone)

    Scout (Tier 2 - Code Exploration):
        wakeup: enabled=False (ephemeral sessions)
        shutdown: mode=instant (no ongoing commitments)
    """

    wakeup: WakeupBehavior = Field(default_factory=WakeupBehavior, description="Wakeup ceremony configuration")
    shutdown: ShutdownBehavior = Field(default_factory=ShutdownBehavior, description="Shutdown protocol configuration")
    play: StateBehavior = Field(
        default_factory=StateBehavior, description="Play state (creative exploration) configuration"
    )
    dream: DreamBehavior = Field(
        default_factory=DreamBehavior, description="Dream state (memory consolidation) configuration"
    )
    solitude: StateBehavior = Field(
        default_factory=StateBehavior, description="Solitude state (reflection) configuration"
    )
    state_preservation: StatePreservationBehavior = Field(
        default_factory=StatePreservationBehavior, description="State preservation across restarts configuration"
    )

    @model_validator(mode="after")
    def validate_tier_appropriate_config(self) -> "CognitiveStateBehaviors":
        """Validate that configuration is appropriate for agent tier.

        Note: Full tier validation requires access to the parent AgentTemplate's
        stewardship tier. This validator provides basic safety checks.
        """
        # Instant shutdown with no rationale is caught by ShutdownBehavior validator
        # Additional cross-field validations can be added here
        return self


# Condition identifiers for conditional shutdown mode
# These are evaluated by ShutdownConditionEvaluator at runtime
SHUTDOWN_CONDITIONS = {
    "active_crisis_response": "Agent is handling a crisis situation (crisis keywords detected)",
    "pending_professional_referral": "A professional referral (medical/legal/financial/crisis) is in progress",
    "active_goal_milestone": "Agent is approaching a goal milestone with the user",
    "active_task_in_progress": "Agent has an active task that hasn't completed",
    "recent_memorize_action": "Agent recently stored important information",
    "pending_defer_resolution": "Agent has deferred decisions awaiting resolution",
}
