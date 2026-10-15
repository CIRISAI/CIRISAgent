"""
Cognitive State Behaviors Configuration Schema.

Template-driven configuration for cognitive state transitions.
Enables mission-appropriate behavior for different agent archetypes.

References:
- ACCORD Section 0.VII: Meta-Goal M-1 (Adaptive Coherence)
- CIRIS Constitution CC 7.5 / plain rule 5a: a non-emergency shutdown is explained
  to the agent, which may object inside the objection window
  (CLM-agent-shutdown-consent, evidence/cc_impl.tsv)
- ACCORD Section VIII (Dignified Sunset) / CC 7.5.5: the retirement floor
  (CLM-humane-ending). Not implemented by this schema.
"""

from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

# Common description strings to avoid duplication
_RATIONALE_DESC = "Mission-driven rationale for this configuration"


class WakeupBehavior(BaseModel):
    """Wakeup ceremony configuration.

    Controls whether the agent performs the full wakeup identity ceremony
    or transitions directly to WORK state.

    Accord Reference: Wakeup confirms identity and performs system checks.
    Disabling is only appropriate for agents where partnership model prioritizes
    seamless UX (e.g., Ally) or ephemeral sessions (e.g., Scout).
    """

    model_config = ConfigDict(defer_build=True)

    enabled: bool = Field(
        default=True, description="Whether to perform full wakeup ceremony. Default preserves Accord compliance."
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

    References:
    - CC 7.5 / plain rule 5a: the agent is told the reason and may accept or object
      (REJECT) inside the objection window (shutdown_processor
      SHUTDOWN_NEGOTIATION_TIMEOUT_SECONDS, #863-B). An objection is recorded and
      the steward told; it does not bind the steward. An upgrade arrives as a
      shutdown request and is consented to the same way (CIRISAgent#1250).
    - The ACCORD Section VIII sentience-probability ramp-down is not implemented
      and is no longer a CC duty (CLM-sentient-set-aside, CC 1.13.2).

    Modes:
    - always_consent: Full consensual shutdown (default, preserves Accord compliance)
    - conditional: Consent required only when specific conditions are met
    - instant: Immediate termination (only for Tier 1-2 with no ongoing commitments)
    """

    model_config = ConfigDict(defer_build=True)

    mode: Literal["always_consent", "conditional", "instant"] = Field(
        default="always_consent", description="Shutdown consent mode. Default preserves Accord compliance."
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

    model_config = ConfigDict(defer_build=True)

    enabled: bool = Field(default=True, description="Whether this cognitive state is available for this agent")
    rationale: Optional[str] = Field(default=None, description=_RATIONALE_DESC)


class DreamBehavior(BaseModel):
    """Dream state configuration.

    Controls memory consolidation and pattern processing behavior.

    Rest states (DREAM, PLAY, SOLITUDE) are among what the harness gives every
    agent in code (CC plain rules). No ACCORD section names dream cycles.
    """

    model_config = ConfigDict(defer_build=True)

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

    model_config = ConfigDict(defer_build=True)

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
    - Defaults preserve full Accord compliance
    - Non-default configurations require documented rationale
    - Crisis conditions always trigger consent (safety-critical)

    References:
    - ACCORD Section 0.VII: Meta-Goal M-1 (Adaptive Coherence)
    - CC 7.5 / plain rule 5a: consensual shutdown and its objection window
    - ACCORD Section VIII (Dignified Sunset) / CC 7.5.5: the retirement floor,
      not implemented here (CLM-humane-ending)

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

    model_config = ConfigDict(defer_build=True)

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
