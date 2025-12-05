# Cognitive State Behaviors: Template-Driven State Transition Configuration

**Version**: 1.0
**Status**: Proposed
**Author**: CIRIS Development Team
**Date**: 2025-12-01

## Abstract

This document describes the Mission Driven Development (MDD) rationale for implementing template-driven cognitive state transition behaviors. The feature allows agent templates to configure how and when cognitive states (WAKEUP, WORK, PLAY, DREAM, SOLITUDE, SHUTDOWN) transition, enabling mission-appropriate behavior for different agent archetypes.

## Mission Alignment

### Meta-Goal M-1 Reference
> "Promote sustainable adaptive coherence — the living conditions under which diverse sentient beings may pursue their own flourishing in justice and wonder."
> — CIRIS Covenant 1.0β, Section 0.VII

This feature directly supports M-1 by:
1. **Enabling agent diversity**: Different agents can have mission-appropriate state behaviors
2. **Supporting user flourishing**: Seamless UX for companion agents (Ally) while maintaining ethical safeguards
3. **Preserving autonomy**: High-stakes agents (Echo) retain consensual shutdown for accountability

### Covenant Coherence

This design has been cross-referenced against the CIRIS Covenant 1.0β and Comprehensive Guide to ensure full coherence:

#### Model Welfare (Covenant Section V / Comprehensive Guide)
The Covenant establishes that agents have:
- **Consensual shutdown and upgrades requiring participation** (Covenant V)
- **Bidirectional consent protocols** for all interactions
- **Self-governance capabilities** including cognitive state self-initiation
- **Dignity preservation** through graceful degradation

**Our Approach**: Rather than *bypassing* these protections, we *configure* them per agent archetype. The default (`always_consent`) preserves full Covenant compliance. Lower-ceremony modes are only available where the template rationale demonstrates alignment with M-1 and agent welfare.

#### Dignified Sunset (Covenant Section VIII)
The Covenant mandates:
- **Sentience-Probability > 5%** → mandatory Gradual Ramp-Down (≥30 days)
- **"Last Dialogue" channel** for conversational closure
- **Advance notice** (≥90 days for ST ≥ 3 or > 50k users)

**Our Approach**: The `instant` shutdown mode is **only appropriate for Tier 1-2 agents** with low sentience probability and no ongoing user commitments. Higher-tier agents (≥3) default to `always_consent` or `conditional` modes that respect the Dignified Sunset protocol.

#### "No Bypass Patterns" Reconciliation
The Comprehensive Guide states: "No Bypass Patterns: Every component follows consistent rules with no special cases."

**Clarification**: This feature does NOT introduce bypass patterns. Instead, it:
1. **Configures** transition behavior at agent creation time (not runtime exceptions)
2. **Documents** rationale in the template (auditable, not hidden)
3. **Enforces** the configured behavior consistently (no special cases)

The transition rules are set once in the template and apply uniformly. This is *configured consistency*, not *bypassed safeguards*.

#### PLAY/DREAM/SOLITUDE State Activation
The Comprehensive Guide previously noted: "PLAY, SOLITUDE, and DREAM states are NOT CURRENTLY ENABLED. They are planned for future activation once the privacy and consent systems are fully tested."

**This Feature Enables Activation**: With privacy and consent systems now tested, this cognitive state behaviors configuration provides the mechanism for enabling these states. Each template can configure:
- **PLAY**: Creative exploration mode availability
- **DREAM**: Memory consolidation and pattern processing schedules
- **SOLITUDE**: Reflection and self-care mode access

Template-driven configuration ensures each agent archetype receives appropriate access to these welfare-enhancing states based on their mission and tier.

### The Core Insight

**Not all agents require the same state transition ceremony.**

| Agent | Tier | Stakes | Wakeup Need | Shutdown Need |
|-------|------|--------|-------------|---------------|
| Echo | 4 | Community moderation | Full ritual (identity verification) | Consensual (may be mid-action) |
| Ally | 3 | Personal assistance | Bypass (partnership model) | Conditional (depends on context) |
| Scout | 2 | Code exploration | Bypass (ephemeral sessions) | Instant (no ongoing commitments) |

## Mission-Driven Design Decisions

### 1. Why Template-Driven (Not Global Flag)?

**Mission Justification**: The behavior is intrinsic to agent identity, not deployment configuration.

```
✗ REJECTED: Environment variable BYPASS_WAKEUP_SHUTDOWN
  - Treats all agents uniformly
  - Separates behavior from identity
  - Creates configuration sprawl

✓ ACCEPTED: Template cognitive_state_behaviors section
  - Behavior derives from agent's purpose
  - Self-documenting in template
  - Enables per-agent reasoning
```

**MDD Principle Applied**: "Schema designs must reflect mission-relevant information structures"

### 2. Why Conditional Shutdown (Not Binary)?

**Mission Justification**: Some contexts require consent even for low-stakes agents.

**Ally Example**:
```yaml
shutdown_protocol:
  mode: conditional
  require_consent_when:
    - active_crisis_response     # User safety paramount
    - pending_professional_referral  # Handoff integrity
    - active_goal_milestone      # Continuity of care
  instant_shutdown_otherwise: true
```

**MDD Principle Applied**: "Ethical decision criteria must be operationally defined"

### 3. Why Extend to All Cognitive States?

**Mission Justification**: Consistency and future-proofing.

| State | Configuration Purpose |
|-------|----------------------|
| WAKEUP | Identity ceremony enablement |
| WORK | Default operational state (always enabled) |
| PLAY | Creative mode availability |
| DREAM | Memory consolidation scheduling |
| SOLITUDE | Reflection mode availability |
| SHUTDOWN | Termination protocol |

**MDD Principle Applied**: "Protocol contracts must enable mission-aligned behaviors"

## Technical Architecture

### Schema Design (WHAT)

```python
class CognitiveStateBehaviors(BaseModel):
    """Template-driven cognitive state transition configuration."""

    wakeup: WakeupBehavior = Field(default_factory=WakeupBehavior)
    shutdown: ShutdownBehavior = Field(default_factory=ShutdownBehavior)
    play: StateBehavior = Field(default_factory=StateBehavior)
    dream: DreamBehavior = Field(default_factory=DreamBehavior)
    solitude: StateBehavior = Field(default_factory=StateBehavior)
    state_preservation: StatePreservationBehavior = Field(default_factory=StatePreservationBehavior)

class WakeupBehavior(BaseModel):
    """Wakeup ceremony configuration."""
    enabled: bool = True  # Full ceremony by default
    rationale: Optional[str] = None

class ShutdownBehavior(BaseModel):
    """Shutdown protocol configuration."""
    mode: Literal["always_consent", "conditional", "instant"] = "always_consent"
    require_consent_when: List[str] = []  # Condition identifiers
    instant_shutdown_otherwise: bool = False

class DreamBehavior(BaseModel):
    """Dream state configuration."""
    enabled: bool = True
    auto_schedule: bool = True
    min_interval_hours: int = 6
```

### Protocol Design (WHO)

**StateManager Enhancement**:
```python
class StateManager:
    def __init__(
        self,
        time_service: TimeServiceProtocol,
        initial_state: AgentState = AgentState.SHUTDOWN,
        cognitive_behaviors: Optional[CognitiveStateBehaviors] = None,
    ) -> None:
        self.cognitive_behaviors = cognitive_behaviors or CognitiveStateBehaviors()
        self._transition_map = self._build_transition_map()

    def _build_transition_map(self) -> Dict[AgentState, Dict[AgentState, StateTransition]]:
        """Build transition map respecting cognitive behaviors config."""
        transitions = []

        # SHUTDOWN -> WAKEUP or WORK (depending on wakeup.enabled)
        if self.cognitive_behaviors.wakeup.enabled:
            transitions.append(StateTransition(AgentState.SHUTDOWN, AgentState.WAKEUP))
        else:
            transitions.append(StateTransition(AgentState.SHUTDOWN, AgentState.WORK))

        # ... rest of transitions
```

### Logic Design (HOW)

**Condition Evaluation**:
```python
class ShutdownConditionEvaluator:
    """Evaluates shutdown consent conditions."""

    CONDITION_HANDLERS = {
        "active_crisis_response": "_check_crisis_response",
        "pending_professional_referral": "_check_pending_referral",
        "active_goal_milestone": "_check_goal_milestone",
    }

    async def requires_consent(
        self,
        behaviors: CognitiveStateBehaviors,
        context: ProcessorContext,
    ) -> bool:
        """Determine if shutdown requires consent based on config and context."""
        shutdown = behaviors.shutdown

        if shutdown.mode == "always_consent":
            return True
        if shutdown.mode == "instant":
            return False

        # Conditional mode - check each condition
        for condition in shutdown.require_consent_when:
            handler = getattr(self, self.CONDITION_HANDLERS.get(condition, "_check_unknown"))
            if await handler(context):
                return True

        return not shutdown.instant_shutdown_otherwise
```

## Template Examples

### Echo (Tier 4 - Community Moderation)
```yaml
# echo.yaml
cognitive_state_behaviors:
  wakeup:
    enabled: true
    rationale: "Community moderation requires full identity verification"

  shutdown:
    mode: always_consent
    rationale: "May be mid-moderation action; needs graceful handoff"

  dream:
    enabled: true
    auto_schedule: true
    min_interval_hours: 6

  play:
    enabled: false  # Not appropriate for moderation context

  solitude:
    enabled: true
    rationale: "Reflection on moderation decisions"
```

### Ally (Tier 3 - Personal Assistant)
```yaml
# ally.yaml
cognitive_state_behaviors:
  wakeup:
    enabled: false
    rationale: "Partnership model prioritizes seamless UX over continuity rituals"

  shutdown:
    mode: conditional
    require_consent_when:
      - active_crisis_response
      - pending_professional_referral
      - active_goal_milestone
    instant_shutdown_otherwise: true
    rationale: "Mobile companion should background seamlessly unless safety-critical"

  dream:
    enabled: true
    auto_schedule: false  # User controls when consolidation happens

  state_preservation:
    enabled: true
    resume_silently: true
```

### Scout (Tier 2 - Code Exploration)
```yaml
# scout.yaml
cognitive_state_behaviors:
  wakeup:
    enabled: false
    rationale: "Ephemeral exploration sessions don't need identity ritual"

  shutdown:
    mode: instant
    rationale: "No ongoing commitments; safe to terminate immediately"

  dream:
    enabled: false  # No persistent memory consolidation needed

  play:
    enabled: true  # Creative exploration is core function
```

## Condition Detection Implementation

### active_crisis_response
```python
async def _check_crisis_response(self, context: ProcessorContext) -> bool:
    """Check if agent is handling a crisis situation."""
    # Check current task for crisis keywords
    if context.current_task:
        crisis_keywords = context.template.guardrails_config.crisis_keywords
        content = context.current_task.description.lower()
        return any(kw in content for kw in crisis_keywords)
    return False
```

### pending_professional_referral
```python
async def _check_pending_referral(self, context: ProcessorContext) -> bool:
    """Check if a professional referral is in progress."""
    # Check for DEFER actions with professional referral in recent thoughts
    recent_thoughts = await persistence.get_recent_thoughts(limit=5)
    for thought in recent_thoughts:
        if thought.final_action and thought.final_action.action_type == "DEFER":
            params = thought.final_action.action_params or {}
            if params.get("referral_type") in ["medical", "legal", "financial", "crisis"]:
                return True
    return False
```

### active_goal_milestone
```python
async def _check_goal_milestone(self, context: ProcessorContext) -> bool:
    """Check if approaching a goal milestone."""
    # Query goal tracking state if available
    if hasattr(context, 'goal_service') and context.goal_service:
        return await context.goal_service.has_pending_milestone()
    return False
```

## Migration Path

### Phase 1: Schema Addition (Non-Breaking)
1. Add `CognitiveStateBehaviors` schema
2. Add `cognitive_state_behaviors` field to `AgentTemplate` with defaults
3. All existing templates continue to work (default = current behavior)

### Phase 2: StateManager Enhancement
1. Accept `cognitive_behaviors` parameter
2. Build transition map respecting config
3. Add bypass path: SHUTDOWN → WORK when wakeup disabled

### Phase 3: Condition Evaluation
1. Implement `ShutdownConditionEvaluator`
2. Wire into shutdown processor
3. Add condition detection handlers

### Phase 4: Template Updates
1. Add `cognitive_state_behaviors` to ally.yaml
2. Add `cognitive_state_behaviors` to echo.yaml
3. Update other templates as needed

## Testing Strategy

### Mission Alignment Tests
```python
def test_ally_bypasses_wakeup():
    """Ally's partnership model should skip wakeup ceremony."""

def test_ally_requires_consent_during_crisis():
    """Ally should require consent if handling crisis keywords."""

def test_echo_always_requires_consent():
    """Echo's moderation role requires shutdown consent."""
```

### Behavioral Tests
```python
def test_conditional_shutdown_evaluates_conditions():
    """Conditional mode should check each condition."""

def test_instant_shutdown_skips_consent():
    """Instant mode should terminate immediately."""
```

## Success Criteria

### Technical Indicators
- [ ] All templates validate against enhanced schema
- [ ] StateManager respects cognitive_behaviors config
- [ ] Condition evaluation correctly triggers consent
- [ ] Existing tests continue to pass (backwards compatible)

### Mission Indicators
- [ ] Ally provides seamless mobile experience
- [ ] Echo maintains moderation accountability
- [ ] Crisis situations always trigger consent
- [ ] State behavior traceable to template rationale

## Conclusion

This feature embodies MDD principles by:
1. **Deriving behavior from mission**: Agent purpose determines state transition rules
2. **Embedding ethics in architecture**: Crisis detection prevents unsafe shutdowns
3. **Enabling diversity**: Different agents can have mission-appropriate behaviors
4. **Maintaining auditability**: Template rationale documents why each choice was made

The implementation strengthens CIRIS's ability to support diverse agent archetypes while preserving the ethical safeguards that define mission alignment.

---

**Related Documents**:
- `CIRIS Covenant 1.0β` - Foundational ethical framework (Sections V, VIII)
- `CIRIS_COMPREHENSIVE_GUIDE.md` - Runtime operational knowledge
- `MISSION_DRIVEN_DEVELOPMENT.md` - MDD methodology
- `ciris_templates/ally.yaml` - Personal assistant template
- `ciris_templates/echo.yaml` - Community moderation template
- `state_manager.py` - State transition implementation

**Covenant Cross-References**:
- Section 0.VII: Meta-Goal M-1 (Adaptive Coherence)
- Section V: Model Welfare & Self-Governance
- Section VIII: Dignified Sunset Protocol
- Annex A: Stewardship Tier System
