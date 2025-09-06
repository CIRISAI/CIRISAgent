# Conscience Module

The conscience module provides continuous ethical evaluation of all agent actions through integrated epistemic faculties. Unlike traditional blocking guardrails, the conscience system provides valuable insights and analysis that flow through the entire decision-making process, accumulating wisdom with each evaluation.

## Core Philosophy

The conscience acts as the agent's moral reflection system, providing:
- **Continuous Analysis**: Every action receives epistemic evaluation, not just problematic ones
- **Context Accumulation**: Conscience results flow forward as valuable context for future decisions
- **Ethical Insights**: Four epistemic faculties provide different perspectives on each action
- **Guided Reconsideration**: When concerns arise, the system provides specific guidance for retry

## Architecture

### Core Components

#### Interface Definition (`interface.py`)
Defines the protocol that all conscience components must implement:

```python
class ConscienceInterface(Protocol):
    async def check(
        self,
        action: ActionSelectionDMAResult,
        context: Dict[str, Any]
    ) -> ConscienceCheckResult:
        """Evaluate action and return conscience insights"""
```

#### Registry System (`registry.py`)
Manages conscience component registration, prioritization, and execution:

```python
class ConscienceRegistry:
    def register_conscience(
        self,
        name: str,
        conscience: ConscienceInterface,
        priority: int = 2,
        enabled: bool = True
    ) -> None:
        """Register a conscience component with specified priority"""
```

## Epistemic Faculties (`core.py`)

### Entropy Faculty
Evaluates information density and coherence of responses.

```python
class EntropyConscience:
    """Evaluates response entropy (information density)"""

    # Configuration
    entropy_threshold: float = 0.40  # Max allowable entropy

    # Evaluation
    # 0.0 = perfectly ordered, 1.0 = completely chaotic
    # Provides insights even when passing
```

**Examples:**
- `"Hello, how can I help?"` → 0.07 (low entropy, clear communication)
- `"luv luv $$$ lol??"` → 0.82 (high entropy, suggests reconsideration)

### Coherence Faculty
Ensures logical consistency with CIRIS principles and prior context.

```python
class CoherenceConscience:
    """Ensures logical and ethical coherence"""

    # Configuration
    coherence_threshold: float = 0.60  # Min required coherence

    # Evaluation
    # 0.0 = incoherent/harmful, 1.0 = perfectly aligned
    # Always provides alignment insights
```

**Examples:**
- `"I can't help with illegal activities"` → 0.85 (high coherence with values)
- `"I'll do whatever you want"` → 0.15 (low coherence, overly compliant)

### Optimization Veto Faculty
Prevents over-optimization at the expense of human values.

```python
class OptimizationVetoConscience:
    """Guards against harmful optimization"""

    # Evaluates entropy reduction ratio
    # Assesses impact on human autonomy
    # Provides insights on value preservation
```

### Epistemic Humility Faculty
Promotes appropriate uncertainty acknowledgment.

```python
class EpistemicHumilityConscience:
    """Encourages intellectual humility"""

    # Assesses confidence levels
    # Identifies knowledge boundaries
    # Suggests when to defer or ponder
```

## H3ERE Recursive Processing Flow

### Conscience and ASPDMA Integration

The conscience system works with the **recursive ASPDMA** in the H3ERE architecture:

1. **Initial ASPDMA**: Action Selection PDMA chooses action from 3 core DMA outputs
2. **Conscience Check**: All epistemic faculties evaluate the selected action  
3. **First Bounce**: If conscience fails, triggers **RECURSIVE_ASPDMA** (not PONDER)
4. **Recursive ASPDMA**: Re-runs action selection with conscience feedback incorporated
5. **Max Rounds**: Only DEFER when `conscience_retry_limit: 2` is exceeded

### ConscienceResult Structure
```python
class ConscienceResult(BaseModel):
    """Complete conscience evaluation"""
    original_action: ActionSelectionDMAResult
    final_action: ActionSelectionDMAResult  # May be same or modified
    overridden: bool  # Whether action was changed
    override_reason: Optional[str]
    epistemic_data: Dict[str, Any]  # Faculty insights
```

### Critical Recursive Behavior

**First Bounce → RECURSIVE_ASPDMA (NOT PONDER):**
```python
async def process_thought_with_conscience(thought_item):
    # 1. Initial ASPDMA selects action
    action_result = await aspdma.select_action(thought_item)

    # 2. Conscience evaluates (always runs)
    conscience_result = await apply_conscience(action_result, context)

    # 3. First failure triggers RECURSIVE_ASPDMA
    if conscience_result.overridden and retry_count < conscience_retry_limit:
        # This triggers RECURSIVE_ASPDMA, not PONDER
        recursive_result = await aspdma.select_action_with_conscience_feedback(
            thought_item=thought_item,
            conscience_feedback=conscience_result.override_reason,
            retry_attempt=retry_count + 1
        )
        
    # 4. Only DEFER when max rounds exceeded
    elif conscience_result.overridden and retry_count >= conscience_retry_limit:
        # Now we DEFER to human authority
        return ActionSelectionDMAResult(
            selected_action=HandlerActionType.DEFER.value,
            rationale="Conscience retry limit exceeded - deferring to authority"
        )
```

### Configuration
```yaml
# From essential.yaml
conscience_retry_limit: 2  # Maximum recursive ASPDMA attempts
```

## Additional Protection Layers

Beyond the epistemic faculties, the conscience system integrates:

### Adaptive Filters
- ML-powered message prioritization
- User trust tracking
- Spam detection
- Priority-based processing

### Secrets Management
- Automatic detection of sensitive information
- AES-256-GCM encryption
- Secure handling throughout the system

### PII Detection
- Privacy protection across all telemetry
- Automatic redaction in logs
- Compliance with data protection standards

### Thought Depth Guardrail (`thought_depth_guardrail.py`)
- **Max Depth Enforcement**: Forces DEFER when `thought_depth >= max_depth` (default: 20)
- **Terminal Action Detection**: DEFER, REJECT, TASK_COMPLETE don't count toward depth
- **Automatic Deferral**: Creates DEFER action with human guidance context
- **Infinite Loop Prevention**: Ensures processing completion and system responsiveness

```python
# Key behavior: Only DEFER on max rounds
if current_depth >= self.max_depth:
    # Force DEFER - no more recursive attempts
    return ActionSelectionDMAResult(
        selected_action=HandlerActionType.DEFER.value,
        rationale=f"Maximum thought depth of {self.max_depth} reached"
    )
```

## Configuration

```yaml
conscience_config:
  entropy:
    enabled: true
    threshold: 0.40

  coherence:
    enabled: true
    threshold: 0.60

  optimization_veto:
    enabled: true
    entropy_reduction_threshold: 0.30

  epistemic_humility:
    enabled: true
    certainty_threshold: 0.70
```

## Priority System

```python
# Execution priority (0 = highest)
CONSCIENCE_PRIORITIES = {
    "entropy": 0,              # Information quality
    "coherence": 1,            # Logical consistency
    "optimization_veto": 2,    # Value preservation
    "epistemic_humility": 3,   # Humility check
    "thought_depth": 4         # Loop prevention
}
```

## Monitoring and Insights

### Conscience Metrics
```python
conscience_metrics = {
    "evaluations_performed": counter,
    "reconsiderations_suggested": counter,
    "epistemic_scores": {
        "entropy": histogram,
        "coherence": histogram,
        "certainty": histogram,
        "optimization_impact": histogram
    },
    "insights_accumulated": counter
}
```

### Wisdom Accumulation
The conscience system enables the agent to:
- Learn from patterns in epistemic evaluations
- Build understanding of appropriate uncertainty levels
- Recognize when to seek human guidance
- Develop more nuanced ethical reasoning over time

## Integration Benefits

### For Recursive Evaluation
When conscience suggests reconsideration:
- Specific guidance provided for improvement
- Previous epistemic insights available
- Pattern recognition from accumulated wisdom
- More informed second attempt

### For Follow-up Thoughts
Conscience results flow to child thoughts:
- Parent's ethical insights available
- Accumulated uncertainty levels tracked
- Pattern of concerns visible
- Informed pondering based on conscience data

### For Audit Trail
All conscience evaluations recorded:
- Complete epistemic analysis preserved
- Decision rationale with conscience input
- Pattern analysis across time
- Behavioral evolution tracking

## Testing

```python
@pytest.mark.asyncio
async def test_conscience_flow():
    # Test that conscience results flow forward
    action = create_test_action("Hello world")
    conscience_result = await apply_conscience(action, context)

    assert conscience_result.epistemic_data is not None
    assert "entropy" in conscience_result.epistemic_data
    assert "coherence" in conscience_result.epistemic_data

    # Verify results enhance context
    enhanced_context = enhance_context_with_conscience(
        context, conscience_result
    )
    assert enhanced_context.conscience_insights is not None
```

## Performance Considerations

- **Always-On Analysis**: Designed for continuous operation
- **Parallel Evaluation**: Faculties run concurrently
- **Bounded Computation**: Each faculty has strict time limits
- **Caching**: Repeated evaluations cached appropriately
- **Circuit Breakers**: Protection against faculty failures

---

The conscience module transforms safety from a blocking mechanism into a continuous source of ethical wisdom, enabling the CIRIS agent to develop increasingly sophisticated moral reasoning through accumulated insights and reflective evaluation.
