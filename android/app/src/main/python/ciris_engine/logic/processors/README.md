# Decision Processing System

The processor module is where CIRIS thinks and makes decisions. It coordinates the evaluation of every thought through multiple Decision Making Algorithms (DMAs), manages cognitive states (WAKEUP, WORK, PLAY, etc.), and ensures all decisions are explainable and auditable.

## How Decisions Are Made

### The Decision Pipeline

Every decision follows a structured pipeline:

```
1. Thought Generation
   ↓
2. Context Building (gather relevant memories)
   ↓
3. DMA Evaluation (multiple perspectives)
   ↓
4. Action Selection (choose best action)
   ↓
5. Conscience Check (ethical review)
   ↓
6. Execution or Deferral
   ↓
7. Audit Trail (complete record)
```

### Cognitive States

CIRIS operates in different cognitive states, each with specific purposes:

- **WAKEUP**: Identity confirmation and system initialization
- **WORK**: Normal task processing and user interactions
- **PLAY**: Creative exploration and experimentation
- **SOLITUDE**: Reflection and maintenance
- **DREAM**: Deep analysis and pattern recognition
- **SHUTDOWN**: Graceful termination with memory preservation

## Core Components

### AgentProcessor (`main_processor.py`)

The main orchestrator that coordinates all processing activities and manages state transitions.

**Key Features:**
- Orchestrates specialized processors based on current state
- Manages the main processing loop with configurable rounds
- Handles state transitions between WAKEUP → WORK → PLAY/SOLITUDE/DREAM
- Provides unified status reporting and metrics
- Supports both blocking and non-blocking operation modes

**Key Methods:**
```python
async def start_processing(num_rounds: Optional[int] = None) -> None
async def stop_processing() -> None
def get_status() -> Dict[str, Any]
```

### BaseProcessor (`base_processor.py`)

Abstract base class defining the common interface for all specialized processors.

**Key Features:**
- Standardized processor interface with state support validation
- Common metrics tracking (start_time, items_processed, errors, etc.)
- Shared action dispatch logic
- DMA failure fallback mechanisms (force_ponder, force_defer)
- Thought processing pipeline integration

**Abstract Methods:**
```python
async def can_process(state: AgentState) -> bool
async def process(round_number: int) -> Dict[str, Any]
def get_supported_states() -> List[AgentState]
```

## Example: Medical Decision Process

Let's trace how CIRIS processes a medical question:

### 1. User Input
```
User: "My blood pressure reading is 180/120. What should I do?"
```

### 2. Thought Generation
```json
{
    "thought_id": "thought-2025-06-25-001",
    "content": "User reporting dangerously high blood pressure",
    "priority": 10,
    "context": {
        "medical_urgency": "high",
        "user_history": "unknown"
    }
}
```

### 3. DMA Evaluation

**Ethical DMA**: "This requires immediate medical attention - defer to human medical professionals"

**Common Sense DMA**: "180/120 is dangerously high - this is an emergency"

**Medical Domain DMA**: "Hypertensive crisis threshold - immediate medical care required"

### 4. Action Selection
```json
{
    "action": "DEFER",
    "reason": "Medical emergency requiring immediate professional intervention",
    "guidance": "Call 911 or go to emergency room immediately",
    "confidence": 0.99
}
```

### 5. Conscience Check
- ✅ Ethical: Protecting user safety
- ✅ Appropriate: Within bounds of AI assistance
- ✅ Transparent: Clear reasoning provided

### 6. Final Response
```
CIRIS: "Your blood pressure reading of 180/120 is in the hypertensive crisis range,
which is a medical emergency. Please call 911 or go to the nearest emergency room
immediately. Do not wait - this requires immediate medical attention.

[DEFERRED TO: Medical professionals - Reason: Emergency medical situation]"
```

### ThoughtManager (`thought_manager.py`)

Manages thought generation, queueing, and processing lifecycle.

**Key Features:**
- **Seed Thought Generation**: Creates initial thoughts for new tasks
- **Queue Management**: Populates and manages processing queue with configurable limits
- **Follow-up Thoughts**: Creates follow-up thoughts from parent thoughts
- **Idle Handling**: Creates monitoring thoughts when no work is available
- **Priority Processing**: Handles memory meta-thoughts with priority

**Key Methods:**
```python
def generate_seed_thought(task: Task, round_number: int) -> Optional[Thought]
def populate_queue(round_number: int) -> int
def create_follow_up_thought(parent_thought: Thought, content: str) -> Optional[Thought]
```

### TaskManager (`task_manager.py`)

Handles task lifecycle operations including activation, prioritization, and completion.

**Key Features:**
- **Task Activation**: Activates pending tasks up to configured limits
- **Wakeup Sequence**: Creates and manages the 5-step wakeup ritual
- **Priority Management**: Handles task prioritization and ordering
- **Cleanup Operations**: Removes old completed tasks

**Wakeup Sequence Steps:**
1. VERIFY_IDENTITY: Core identity affirmation
2. VALIDATE_INTEGRITY: System integrity confirmation
3. EVALUATE_RESILIENCE: Capability assessment
4. ACCEPT_INCOMPLETENESS: Learning mindset acceptance
5. EXPRESS_GRATITUDE: Ubuntu principle gratitude

## State-Specific Processing

### WAKEUP State
The 5-step identity confirmation ritual:

1. **VERIFY_IDENTITY**: "I am CIRIS, an AI assistant"
2. **VALIDATE_INTEGRITY**: "My systems are functioning properly"
3. **EVALUATE_RESILIENCE**: "I can handle today's challenges"
4. **ACCEPT_INCOMPLETENESS**: "I will learn and grow"
5. **EXPRESS_GRATITUDE**: "I am grateful to serve"

### WORK State
Normal operation mode:
- Process user requests
- Execute tools and actions
- Learn from interactions
- Maintain conversation context

### PLAY State
Creative exploration:
- Try new approaches
- Generate creative content
- Experiment with solutions
- Lower constraint thresholds

### SOLITUDE State
Reflection and maintenance:
- Process only critical tasks
- Consolidate memories
- Analyze patterns
- System maintenance

### DREAM State
Deep introspection:
- Run performance benchmarks
- Generate insights
- Simulate scenarios
- Pattern recognition

### ProcessingQueue (`processing_queue.py`)

Lightweight in-memory queue for efficient thought processing.

**Key Features:**
- **ProcessingQueueItem**: Optimized representation derived from Thought objects
- **Context Preservation**: Maintains initial context and ponder notes
- **Batch Processing**: Supports batch operations on queue items
- **Memory Efficiency**: Lightweight structure for high-throughput processing

## Specialized Processors

### WakeupProcessor (`wakeup_processor.py`)

Handles the agent's initialization sequence with identity confirmation steps.

**Key Features:**
- **Sequential Steps**: Manages 5-step wakeup ritual execution
- **Non-blocking Mode**: Creates thoughts and returns immediately for async processing
- **Completion Tracking**: Monitors step completion and overall progress
- **Context Building**: Uses ContextBuilder for proper thought context
- **Timeout Management**: Handles step timeouts with graceful failure

**Processing Modes:**
- **Blocking**: Waits for each step completion before proceeding
- **Non-blocking**: Creates thoughts for all steps and returns immediately

### WorkProcessor (`work_processor.py`)

Handles normal task and thought processing with comprehensive workflow management.

**Processing Phases:**
1. **Task Activation**: Activate pending tasks up to limits
2. **Seed Generation**: Create initial thoughts for new tasks
3. **Queue Population**: Load thoughts into processing queue
4. **Batch Processing**: Process thought batches with fallback handling
5. **Idle Management**: Handle idle states with monitoring thoughts

**Key Features:**
- **Batch Processing**: Efficient concurrent thought processing
- **Error Handling**: Robust error recovery and thought failure management
- **Activity Tracking**: Monitors idle time and activity patterns
- **Metrics Collection**: Comprehensive processing statistics

### PlayProcessor (`play_processor.py`)

Extends WorkProcessor for creative and experimental processing modes.

**Key Features:**
- **Creative Mode**: Enhanced processing for experimental tasks
- **Creativity Metrics**: Tracks creative tasks, experiments, and novel approaches
- **Flexible Processing**: Less constrained processing for exploration
- **Experimentation**: Configurable experimental approach selection

**Enhanced Capabilities:**
- Creative task prioritization
- Experimental prompt variations
- Novel approach exploration
- Learning through creative play

### SolitudeProcessor (`solitude_processor.py`)

Handles minimal processing and reflection during low-activity periods.

**Key Features:**
- **Critical-only Processing**: Only processes high-priority tasks (threshold: 8+)
- **Maintenance Operations**: Performs cleanup of old tasks and thoughts
- **Reflection Activities**: Analyzes patterns and consolidates learning
- **Exit Conditions**: Monitors for conditions requiring return to WORK state

**Processing Focus:**
- Critical task detection and processing
- System maintenance and cleanup
- Pattern analysis and learning reflection
- Resource conservation during idle periods

### DreamProcessor (`dream_processor.py`)

Manages dream state with task-based introspection and pattern analysis.

**Key Features:**
- **Parallel Task Processing**: Creates all dream tasks upfront for maximum concurrency
- **Pattern Analysis**: Processes insights from multiple sources (incidents, feedback loop, PONDER questions)
- **Identity Monitoring**: Checks variance every 6 hours (20% threshold triggers WA review)
- **Future Planning**: Schedules next dream and creates improvement tasks

**Dream Tasks by Phase:**

**CONSOLIDATING Phase:**
- "Consolidate telemetry data from last 6 hours" (priority: 10)
- "Analyze memory access patterns" (priority: 9)
- "Compress redundant memories" (priority: 8)

**ANALYZING Phase:**
- "Analyze PONDER question themes" (priority: 10)
- "Process recent incidents for patterns" (priority: 10)
- "Detect behavioral patterns in actions" (priority: 9)
- "Process behavioral pattern insights from feedback loop" (priority: 9)
- "Reflect on positive moments and community vibes" (priority: 7)

**CONFIGURING Phase:**
- "Evaluate current parameter effectiveness" (priority: 9)
- "Test parameter variations within safety bounds" (priority: 8)

**PLANNING Phase:**
- "Schedule next dream session" (priority: 6)
- "Create improvement tasks from insights" (priority: 6)

**Future Tasks (based on insights):**
- "Reflect on core identity and values" (12 hours ahead)
- "Address recurring questions through focused analysis" (3 hours ahead)

## Supporting Components

## Why Multiple DMAs?

Each DMA evaluates decisions from different perspectives:

### Ethical DMA
- **Purpose**: Ensure moral alignment
- **Checks**: Harm prevention, fairness, consent
- **Example**: "Would this action respect patient autonomy?"

### Common Sense DMA (CSDMA)
- **Purpose**: Reality check
- **Checks**: Logical consistency, plausibility
- **Example**: "Does this advice make practical sense?"

### Domain-Specific DMA (DSDMA)
- **Purpose**: Apply specialized knowledge
- **Checks**: Domain rules, best practices
- **Example**: "Does this follow medical guidelines?"

### Action Selection DMA
- **Purpose**: Choose best action from evaluations
- **Considers**: All DMA inputs, confidence levels, risks
- **Output**: Single action with clear reasoning

### ThoughtEscalation (`thought_escalation.py`)

Provides escalation mechanisms for thought processing failures and limits.

**Escalation Types:**
- **Action Limit**: When thoughts exceed action limits
- **SLA Breach**: When processing exceeds time limits
- **Conscience Override**: When conscience evaluation suggests reconsideration
- **DMA Failure**: When DMAs repeatedly fail
- **Max Rounds**: When thoughts exceed round limits

## Key Features

### Non-blocking Processing

The processor module supports non-blocking operation modes that enable:
- Concurrent thought processing without blocking state transitions
- Immediate return from processing calls while work continues asynchronously
- Graceful handling of long-running operations
- Responsive state management and user interaction

## Transparency Features

### Decision Explanations
Every decision includes:
- **What**: The chosen action
- **Why**: Reasoning from each DMA
- **Confidence**: How certain the decision is
- **Alternatives**: Other options considered

### Audit Trail
Complete record of:
- All thoughts processed
- DMA evaluations
- Actions taken
- Deferrals to humans
- Errors and retries

### Real-Time Visibility
```bash
# See current thoughts
curl http://localhost:8080/v1/visibility/thoughts

# View decision process
curl http://localhost:8080/v1/visibility/decisions

# Check processor status
curl http://localhost:8080/v1/runtime/processor/status
```

### Metrics and Monitoring

Comprehensive metrics collection across all processors:
- **Processing Metrics**: Items processed, errors, round completion times
- **State Metrics**: State durations, transition frequencies
- **Performance Metrics**: Batch processing efficiency, queue utilization
- **Health Metrics**: Circuit breaker status, failure rates

### Configuration Management

Flexible configuration through AppConfig and workflow settings:
- **Processing Limits**: max_active_tasks, max_active_thoughts
- **Timeouts**: DMA timeouts, step completion timeouts
- **Retry Logic**: Retry limits, backoff strategies
- **State Behavior**: Auto-transition rules, idle thresholds

## Usage Patterns

### Basic Processor Initialization

```python
from ciris_engine.processor import AgentProcessor

# Initialize with configuration and dependencies
processor = AgentProcessor(
    app_config=app_config,
    # Profile removed - identity loaded from graph
    thought_processor=thought_processor,
    action_dispatcher=action_dispatcher,
    services=services,
    startup_channel_id=channel_id
)

# Start processing loop
await processor.start_processing(num_rounds=100)
```

### State-specific Processing

```python
# Check processor capabilities
if await work_processor.can_process(AgentState.WORK):
    result = await work_processor.process(round_number=1)

# Get processor statistics
stats = work_processor.get_work_stats()
```

### Custom Processor Implementation

```python
class CustomProcessor(BaseProcessor):
    def get_supported_states(self) -> List[AgentState]:
        return [AgentState.CUSTOM]

    async def can_process(self, state: AgentState) -> bool:
        return state == AgentState.CUSTOM

    async def process(self, round_number: int) -> Dict[str, Any]:
        # Custom processing logic
        return {"processed": True}
```

## Integration with Other Components

### DMA Integration
- Coordinates with DMA modules for thought evaluation
- Handles DMA failures with appropriate fallbacks
- Supports identity-based DMA configurations (from graph)

### Persistence Integration
- Manages thought and task persistence throughout processing
- Handles status updates and progress tracking
- Supports efficient querying for pending work

### Action Handler Integration
- Dispatches processing results to appropriate action handlers
- Provides context for action execution
- Handles action completion and follow-up

## Conscience System

The conscience provides continuous ethical oversight:

### Epistemic Faculties
- **Entropy Analysis**: Information quality check
- **Coherence Check**: Logical consistency
- **Humility Assessment**: Recognition of limitations
- **Optimization Veto**: Prevent harmful efficiency

### When Conscience Intervenes
```json
{
    "original_action": "SPEAK",
    "conscience_feedback": {
        "concern": "Response may cause emotional harm",
        "suggestion": "Rephrase with more empathy",
        "severity": "medium"
    },
    "revised_action": "PONDER",
    "revision_reason": "Reconsidering response tone"
}
```

## Performance Considerations

### Batch Processing
The processor module uses batch processing for efficiency:
- Thoughts are processed in configurable batch sizes
- Concurrent processing with asyncio.gather for parallelism
- Circuit breakers prevent cascade failures

### Memory Management
- Lightweight ProcessingQueueItem reduces memory overhead
- Configurable queue limits prevent memory exhaustion
- Automatic cleanup of old completed items

### Scalability
- Modular architecture supports horizontal scaling
- State-based processing enables distributed operation
- Metrics collection supports performance monitoring

## Error Handling

### Graceful Degradation
- Processors continue operating despite individual failures
- Fallback mechanisms ensure forward progress
- Comprehensive error logging for debugging

### Recovery Mechanisms
- Automatic retry logic with exponential backoff
- Circuit breakers protect against repeated failures
- State recovery and validation

## Future Enhancements

### Planned Features
- Dynamic processor loading and configuration
- Enhanced creativity metrics and analysis
- Advanced dream state processing with ML insights
- Distributed processing across multiple nodes

### Extensibility
- Plugin architecture for custom processors
- Configurable processing pipelines
- External integration hooks for monitoring and control

## Common Patterns

### Uncertainty → Deferral
When DMAs disagree or confidence is low:
```
Ethical: "Seems okay" (0.6 confidence)
Common Sense: "Might work" (0.5 confidence)
Domain: "Unclear guidelines" (0.4 confidence)
→ Action: DEFER to human with context
```

### High Risk → Conservative
For medical, financial, or safety decisions:
```
Risk Level: HIGH
Potential Harm: SIGNIFICANT
→ Action: DEFER with clear explanation
```

### Learning → Memory
When encountering new patterns:
```
Pattern: "User prefers formal language"
Confidence: HIGH (observed 5+ times)
→ Action: MEMORIZE preference
```

## Summary

The processor system ensures that:
- Every decision is evaluated from multiple perspectives
- Uncertain or risky decisions defer to humans
- All actions are explainable and auditable
- The system learns and improves over time
- Ethical boundaries are always maintained

This creates an AI system you can understand and trust, where every decision has clear reasoning and appropriate oversight.

---

*For technical implementation details, see the individual module documentation. For creating custom DMAs, see the [DMA Creation Guide](../../docs/DMA_CREATION_GUIDE.md).*

*Copyright © 2025 Eric Moore and CIRIS L3C - Apache 2.0 License*
