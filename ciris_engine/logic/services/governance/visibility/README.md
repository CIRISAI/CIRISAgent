# CIRIS Visibility Service

**CRITICAL GOVERNANCE SERVICE: Reasoning Transparency & Agent Introspection**

## Overview

The CIRIS Visibility Service is one of the four core **Governance Services** in the CIRIS Trinity Architecture, providing complete reasoning transparency through systematic tracing of agent decision-making processes. It serves as the "TRACES" pillar in CIRIS's three-tier observability framework.

### The Three Observability Pillars

1. **TRACES** (Visibility Service) - **Why decisions were made, reasoning chains**
2. **LOGS** (Audit Service) - What happened, who did it, when
3. **METRICS** (Telemetry/TSDB/ResourceMonitor) - Performance and operational data

## Mission: Trust Through Transparency

### How Visibility Serves Meta-Goal M-1 (Covenant Integrity)

The Visibility Service directly supports **Meta-Goal M-1: Covenant Integrity** by providing:

- **Transparent Reasoning**: Complete visibility into agent decision-making processes
- **Accountable AI**: Every action can be traced back to its reasoning chain
- **Trust Building**: Stakeholders can understand and validate agent behavior
- **Compliance Verification**: Ensures adherence to ethical constraints and policies
- **Debugging & Improvement**: Enables systematic analysis of agent behavior patterns

**Without transparency, there can be no trust. Without trust, there can be no ethical AI.**

## Architecture & Location

- **Current Location**: `ciris_engine/logic/services/governance/visibility.py`
- **Service Type**: `ServiceType.VISIBILITY` (Governance Services category)
- **Protocol**: `ciris_engine/protocols/services/governance/visibility.py`
- **Schemas**: `ciris_engine/schemas/services/visibility.py`

**⚠️ NEEDS CONVERSION**: Service currently exists as single `.py` file but should be converted to module structure for consistency with other governance services.

## Core Capabilities

### 1. Current State Snapshots (`get_current_state`)
**Returns**: `VisibilitySnapshot`

Provides real-time view of agent's reasoning state:
- Current active task being processed
- Active thoughts in the reasoning chain
- Recent decisions with their outcomes
- Current reasoning depth (chain length)

```python
snapshot = await visibility_service.get_current_state()
print(f"Current task: {snapshot.current_task.description}")
print(f"Active thoughts: {len(snapshot.active_thoughts)}")
print(f"Reasoning depth: {snapshot.reasoning_depth}")
```

### 2. Complete Reasoning Traces (`get_reasoning_trace`)
**Returns**: `ReasoningTrace`

Provides complete thought-by-thought analysis for any task:
- Full sequence of thoughts with their reasoning
- Action decisions and their rationale
- Followup thought relationships
- Processing time metrics
- Conscience evaluation results

```python
trace = await visibility_service.get_reasoning_trace("task-123")
for step in trace.thought_steps:
    print(f"Thought: {step.thought.content}")
    if step.thought.final_action:
        print(f"Action: {step.thought.final_action.action_type}")
        print(f"Reasoning: {step.thought.final_action.reasoning}")
```

### 3. Decision History Analysis (`get_decision_history`)
**Returns**: `TaskDecisionHistory`

Analyzes all decisions made during task processing:
- Chronological decision records
- Alternatives considered for each decision
- Success/failure tracking
- Final task outcome correlation

```python
history = await visibility_service.get_decision_history("task-123")
print(f"Total decisions: {history.total_decisions}")
print(f"Successful: {history.successful_decisions}")
print(f"Success rate: {history.successful_decisions/history.total_decisions:.2%}")
```

### 4. Action Explanations (`explain_action`)
**Returns**: `str` (human-readable explanation)

Provides natural language explanations for specific actions:
- Why the action was chosen
- The reasoning process that led to it
- Conscience evaluation context

```python
explanation = await visibility_service.explain_action("thought-456")
print(explanation)
# Output: "Action: SPEAK\nReasoning: User asked for clarification..."
```

### 5. Task History (`get_task_history`)
**Returns**: `List[Task]`

Retrieves recent task history for pattern analysis:
- Completed, failed, and active tasks
- Sorted by recency
- Configurable limit (default 10, max 100)

## Data Models & Schemas

### Core Schemas

#### `VisibilitySnapshot`
```python
class VisibilitySnapshot(BaseModel):
    timestamp: datetime
    current_task: Optional[Task]
    active_thoughts: List[Thought]
    recent_decisions: List[Thought]
    reasoning_depth: int
```

#### `ReasoningTrace`
```python
class ReasoningTrace(BaseModel):
    task: Task
    thought_steps: List[ThoughtStep]
    total_thoughts: int
    actions_taken: List[str]
    processing_time_ms: float
```

#### `ThoughtStep`
```python
class ThoughtStep(BaseModel):
    thought: Thought
    conscience_results: Optional[dict]
    handler_result: Optional[HandlerResult]
    followup_thoughts: List[str]
```

#### `TaskDecisionHistory`
```python
class TaskDecisionHistory(BaseModel):
    task_id: str
    task_description: str
    created_at: datetime
    decisions: List[DecisionRecord]
    total_decisions: int
    successful_decisions: int
    final_status: str
    completion_time: Optional[datetime]
```

## API Integration

The Visibility Service is exposed through the **Telemetry API endpoints**:

### `/v1/telemetry/traces` (GET)
**Authentication**: OBSERVER role or higher
**Parameters**:
- `limit`: Maximum traces to return (1-100, default 10)
- `start_time`: Optional filter by start time
- `end_time`: Optional filter by end time

Returns comprehensive reasoning traces from recent task history, automatically calling `get_task_history()` and `get_reasoning_trace()` for each task.

```bash
# Get recent reasoning traces
curl -H "Authorization: Bearer $TOKEN" \
  "https://agents.ciris.ai/api/agent-id/v1/telemetry/traces?limit=5"
```

### Service Dependencies

The traces endpoint requires both:
- **Visibility Service** (this service) - for reasoning traces
- **Audit Service** - for operational context

If either service is unavailable, returns HTTP 503 with appropriate error message.

## Metrics & Monitoring

### Custom Metrics (v1.4.3 API)

The service tracks four key transparency metrics:

```python
{
    "visibility_requests_total": float,      # Total transparency requests
    "visibility_explanations_total": float,  # Explanations provided
    "visibility_redactions_total": float,    # Content redactions applied
    "visibility_uptime_seconds": float       # Service uptime
}
```

### Performance Tracking

Internal counters track service utilization:
- `_transparency_requests`: API calls for transparency data
- `_redaction_operations`: Privacy-preserving content redactions
- `_dsar_requests`: Data Subject Access Requests (GDPR compliance)
- `_audit_requests`: Audit-related visibility requests

## Data Sources & Persistence

### Primary Data Sources

1. **Task Persistence** (`get_task_by_id`, `get_tasks_by_status`)
   - Task metadata and status tracking
   - Creation and completion timestamps
   - Task outcome information

2. **Thought Persistence** (`get_thought_by_id`, `get_thoughts_by_*`)
   - Complete thought chains and reasoning
   - Action decisions with rationale
   - Parent-child thought relationships

3. **Telemetry Correlations** (`get_recent_correlations`)
   - Service interaction traces
   - Performance correlation data

### Database Integration

- **Primary DB**: SQLite database at `self._db_path`
- **Fallback**: Memory graph queries for correlation data
- **Backup**: Telemetry service direct access when available

## Security & Privacy

### Role-Based Access Control

- **OBSERVER**: Can view traces and reasoning data
- **ADMIN**: Full visibility access + management
- **AUTHORITY**: All visibility data + system control
- **SYSTEM_ADMIN**: Complete system transparency

### Privacy Protection

- **Redaction Support**: `apply_redaction()` method for sensitive content
- **Consent Tracking**: Respects user privacy preferences
- **GDPR Compliance**: DSAR request handling and audit trails

## Testing & Quality Assurance

### Comprehensive Test Suite

Location: `tests/ciris_engine/logic/services/governance/test_visibility_service.py`

**Test Coverage**:
- ✅ Service lifecycle (start/stop/health)
- ✅ Empty state handling (no data scenarios)
- ✅ Active task and thought tracking
- ✅ Reasoning depth calculations
- ✅ Complete reasoning trace generation
- ✅ Decision history analysis
- ✅ Action explanation functionality
- ✅ Task history retrieval with filtering
- ✅ Error handling and edge cases

### Metrics Testing

Location: `tests/test_metrics_governance_services.py`

**Verified Metrics**:
- All four visibility metrics present and non-negative
- Proper metric collection and reporting
- Integration with base service metrics

## Common Use Cases

### 1. User Trust & Transparency
```python
# Show user why agent made a decision
explanation = await visibility_service.explain_action(thought_id)
print(f"I chose this action because: {explanation}")
```

### 2. Debugging Agent Behavior
```python
# Analyze problematic task execution
trace = await visibility_service.get_reasoning_trace(failed_task_id)
print(f"Failed after {trace.total_thoughts} thoughts")
for step in trace.thought_steps:
    if step.thought.status == ThoughtStatus.FAILED:
        print(f"Failure point: {step.thought.content}")
```

### 3. Performance Analysis
```python
# Compare reasoning efficiency across tasks
history = await visibility_service.get_task_history(limit=50)
for task in history:
    trace = await visibility_service.get_reasoning_trace(task.task_id)
    efficiency = trace.processing_time_ms / max(trace.total_thoughts, 1)
    print(f"Task {task.task_id}: {efficiency:.1f}ms per thought")
```

### 4. Compliance Monitoring
```python
# Verify ethical decision-making patterns
current_state = await visibility_service.get_current_state()
for decision in current_state.recent_decisions:
    if decision.final_action:
        print(f"Recent action: {decision.final_action.action_type}")
        print(f"Ethical reasoning: {decision.final_action.reasoning}")
```

## Future Enhancements

### Planned Improvements

1. **Module Structure Conversion**
   - Convert from single `.py` file to proper module
   - Align with other governance service patterns
   - Enable more sophisticated internal organization

2. **Enhanced Correlation Analysis**
   - Better integration with telemetry service traces
   - Cross-service reasoning correlation
   - Performance bottleneck identification

3. **Advanced Analytics**
   - Reasoning pattern recognition
   - Decision quality scoring
   - Predictive behavior analysis

4. **Real-time Streaming**
   - WebSocket support for live reasoning traces
   - Real-time decision monitoring
   - Interactive debugging capabilities

## Integration Examples

### With API Client
```typescript
// TypeScript SDK usage
const traces = await client.telemetry.getTraces({ 
  limit: 10, 
  includeReasoning: true 
});

traces.forEach(trace => {
  console.log(`Task: ${trace.taskDescription}`);
  console.log(`Thoughts: ${trace.thoughtCount}`);
  console.log(`Success: ${trace.outcome}`);
});
```

### With CLI
```bash
# View current agent reasoning state
python main.py --adapter cli --command "show current reasoning"

# Analyze specific task reasoning
python main.py --adapter cli --command "explain task task-123"
```

## Critical Dependencies

- **BusManager**: Service communication and coordination
- **TimeService**: Timestamp generation and time operations  
- **Persistence Layer**: Task and thought data storage
- **Memory Graph**: Optional correlation data source

## Error Handling

### Graceful Degradation
- Returns empty traces when no data available
- Handles malformed thought data gracefully
- Provides meaningful error messages for missing dependencies

### Common Error Patterns
```python
# Task not found
trace = await visibility_service.get_reasoning_trace("nonexistent")
assert trace.task.description == "Task not found"
assert len(trace.thought_steps) == 0

# Empty database
state = await visibility_service.get_current_state()
assert state.current_task is None
assert len(state.active_thoughts) == 0
```

---

## Summary

The CIRIS Visibility Service is **essential for ethical AI operation** - it provides the transparency foundation that enables trust, accountability, and continuous improvement. By making agent reasoning processes completely visible and traceable, it directly supports CIRIS's core mission of responsible AI deployment.

**Key Value Propositions**:
- 🔍 **Complete Transparency**: Every decision can be traced and explained
- 🛡️ **Trust Building**: Stakeholders can verify agent behavior
- 🎯 **Compliance**: Supports regulatory and ethical requirements
- 🐛 **Debugging**: Enables systematic behavior analysis
- 📈 **Improvement**: Provides data for reasoning enhancement

**Production Status**: ✅ Fully operational at [agents.ciris.ai](https://agents.ciris.ai) with 100% test coverage and comprehensive API integration.

The service represents a critical advancement in AI transparency - moving beyond "black box" decision-making to fully explainable, auditable reasoning processes that users can trust and understand.