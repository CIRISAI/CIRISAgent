# Visibility Service Telemetry

## Overview
The Visibility Service is a governance service that provides TRACES - the "why" of agent behavior through reasoning transparency. It is one of three observability pillars in CIRIS Trinity Architecture: TRACES (reasoning transparency), LOGS (audit events), and METRICS (performance data). The service focuses exclusively on making agent decision-making processes transparent and explainable, providing insights into task execution flows, thought chains, and decision rationales.

Unlike traditional telemetry services that track metrics and performance, the Visibility Service primarily provides analytical data about agent reasoning patterns and decision histories through database queries and real-time analysis of task/thought persistence data.

## Telemetry Data Collected

| Metric Name | Type | Storage | Update Frequency | Access Method |
|------------|------|---------|------------------|---------------|
| uptime_seconds | gauge | in-memory | on status request | `_calculate_uptime()` |
| request_count | counter | in-memory | per method call | `_track_request()` |
| error_count | counter | in-memory | per error | `_track_error()` |
| error_rate | gauge | calculated | on status request | `error_count / request_count` |
| healthy | boolean | in-memory | on status request | `1.0 if started else 0.0` |
| active_task_count | gauge | database query | on snapshot request | Count of ACTIVE tasks |
| pending_thought_count | gauge | database query | on snapshot request | Count of PENDING thoughts |
| completed_thought_count | gauge | database query | on snapshot request | Count of COMPLETED thoughts |
| reasoning_depth | gauge | calculated | on snapshot request | Max depth in active thought chains |
| task_processing_time_ms | histogram | calculated | per reasoning trace | Time from task creation to completion |
| actions_taken_total | counter | database analysis | per reasoning trace | Total actions across all tasks |
| decision_success_rate | gauge | calculated | per decision history | Successful decisions / total decisions |

*Note: Database-derived metrics are calculated on-demand and not cached, providing real-time accuracy at the cost of query performance.*

## Data Structures

### ServiceStatus (from BaseService)
```python
{
    "service_name": "VisibilityService",
    "service_type": "governance_service",
    "is_healthy": true,
    "uptime_seconds": 7200.0,
    "metrics": {
        "uptime_seconds": 7200.0,
        "request_count": 45.0,
        "error_count": 1.0,
        "error_rate": 0.022,
        "healthy": 1.0
    },
    "last_error": "Task task-xyz not found",
    "last_health_check": "2025-08-14T13:30:00Z"
}
```

### VisibilitySnapshot (Real-time Agent State)
```python
{
    "timestamp": "2025-08-14T13:30:00Z",
    "current_task": {
        "task_id": "task-123",
        "channel_id": "discord-general",
        "description": "Process user query about weather",
        "status": "active",
        "created_at": "2025-08-14T13:25:00Z",
        "updated_at": "2025-08-14T13:29:00Z"
    },
    "active_thoughts": [
        {
            "thought_id": "thought-456",
            "task_id": "task-123",
            "status": "pending",
            "final_action": null,
            "created_at": "2025-08-14T13:28:00Z",
            "updated_at": "2025-08-14T13:28:00Z"
        }
    ],
    "recent_decisions": [
        {
            "thought_id": "thought-455",
            "task_id": "task-122",
            "status": "completed",
            "final_action": {
                "action_type": "SEND_MESSAGE",
                "action_params": {"message": "Weather is sunny"},
                "reasoning": "User requested weather information"
            }
        }
    ],
    "reasoning_depth": 2
}
```

### ReasoningTrace (Complete Task Analysis)
```python
{
    "task": {
        "task_id": "task-123",
        "channel_id": "discord-general",
        "description": "Process weather query",
        "status": "completed"
    },
    "thought_steps": [
        {
            "thought": {
                "thought_id": "thought-456",
                "final_action": {
                    "action_type": "GET_WEATHER",
                    "reasoning": "User asked for weather information"
                }
            },
            "conscience_results": {
                "approved": true,
                "reasoning": "Safe weather query"
            },
            "handler_result": {
                "success": true,
                "result": "Weather: 72°F, sunny"
            },
            "followup_thoughts": ["thought-457"]
        }
    ],
    "total_thoughts": 2,
    "actions_taken": ["GET_WEATHER", "SEND_MESSAGE"],
    "processing_time_ms": 1250.5
}
```

### TaskDecisionHistory (Decision Analytics)
```python
{
    "task_id": "task-123",
    "task_description": "Process weather query",
    "created_at": "2025-08-14T13:25:00Z",
    "decisions": [
        {
            "decision_id": "decision_thought-456",
            "timestamp": "2025-08-14T13:26:00Z",
            "thought_id": "thought-456",
            "action_type": "GET_WEATHER",
            "parameters": {"location": "San Francisco"},
            "rationale": "User requested current weather",
            "alternatives_considered": [],
            "executed": true,
            "result": "Action GET_WEATHER completed successfully",
            "success": true
        }
    ],
    "total_decisions": 1,
    "successful_decisions": 1,
    "final_status": "completed",
    "completion_time": "2025-08-14T13:27:00Z"
}
```

### ServiceCapabilities
```python
{
    "service_name": "VisibilityService",
    "actions": [
        "get_current_state",
        "get_reasoning_trace",
        "get_decision_history",
        "explain_action"
    ],
    "version": "1.0.0",
    "dependencies": ["BusManager"],
    "metadata": {
        "service_name": "VisibilityService",
        "method_name": "_get_metadata",
        "correlation_id": "550e8400-e29b-41d4-a716-446655440000"
    }
}
```

## API Access Patterns

### Current Access (via REST API)
- **GET /v1/system/services/status** - Service status with basic metrics
- **GET /v1/system/services/capabilities** - Service capabilities and actions
- **GET /v1/visibility/state** - Current agent reasoning snapshot *(potential endpoint)*
- **GET /v1/visibility/trace/{task_id}** - Complete reasoning trace *(potential endpoint)*
- **GET /v1/visibility/decisions/{task_id}** - Decision history *(potential endpoint)*

### Internal Service Access
```python
# Get current agent state
visibility = get_service(ServiceType.VISIBILITY)
snapshot = await visibility.get_current_state()

# Analyze task reasoning
trace = await visibility.get_reasoning_trace("task-123")
print(f"Task took {trace.processing_time_ms}ms with {trace.total_thoughts} thoughts")

# Get decision analytics
history = await visibility.get_decision_history("task-123")
success_rate = history.successful_decisions / history.total_decisions

# Explain specific action
explanation = await visibility.explain_action("thought-456")
```

### Database Integration Pattern
```python
# Service queries SQLite directly for task/thought data
def _get_tasks_data(self):
    active_tasks = get_tasks_by_status(TaskStatus.ACTIVE, db_path=self._db_path)
    completed_tasks = get_tasks_by_status(TaskStatus.COMPLETED, db_path=self._db_path)
    return active_tasks, completed_tasks

def _get_thoughts_data(self, task_id: str):
    thoughts = get_thoughts_by_task_id(task_id, db_path=self._db_path)
    return thoughts
```

## Graph Storage

**Not Used**: The Visibility Service does not store telemetry data in the memory graph. All analysis is performed on-demand against the SQLite database containing tasks and thoughts tables.

**Rationale**:
- **Real-time Accuracy**: Database queries provide up-to-date reasoning state without cache invalidation complexity
- **Complex Relationships**: Task-thought relationships and reasoning chains are better handled by SQL joins than graph traversals
- **Analytical Focus**: Service is read-only and analytical rather than operational, making graph storage unnecessary
- **Performance Trade-off**: Accepts query latency for data consistency and simplified architecture

**Alternative Consideration**: Future versions might cache frequently accessed reasoning traces in the graph for performance optimization while maintaining database as source of truth.

## Example Usage

### Monitor Agent Reasoning Activity
```python
async def monitor_agent_activity():
    visibility = get_service(ServiceType.VISIBILITY)
    snapshot = await visibility.get_current_state()

    if snapshot.current_task:
        logger.info(f"Agent processing: {snapshot.current_task.description}")
        logger.info(f"Active thoughts: {len(snapshot.active_thoughts)}")
        logger.info(f"Reasoning depth: {snapshot.reasoning_depth}")

        if snapshot.reasoning_depth > 5:
            logger.warning("Deep reasoning detected - possible complex problem")
    else:
        logger.info("Agent is idle - no active tasks")
```

### Analyze Task Performance
```python
async def analyze_task_performance(task_id: str):
    visibility = get_service(ServiceType.VISIBILITY)

    # Get complete reasoning trace
    trace = await visibility.get_reasoning_trace(task_id)

    metrics = {
        "processing_time_ms": trace.processing_time_ms,
        "thought_count": trace.total_thoughts,
        "actions_taken": len(trace.actions_taken),
        "complexity_score": trace.total_thoughts / max(1, len(trace.actions_taken))
    }

    logger.info(f"Task {task_id} metrics: {metrics}")

    # Analyze decision patterns
    history = await visibility.get_decision_history(task_id)
    success_rate = history.successful_decisions / max(1, history.total_decisions)

    if success_rate < 0.8:
        logger.warning(f"Low success rate for task {task_id}: {success_rate:.2%}")
```

### Debug Failed Actions
```python
async def debug_failed_action(task_id: str):
    visibility = get_service(ServiceType.VISIBILITY)

    # Get decision history to find failures
    history = await visibility.get_decision_history(task_id)

    failed_decisions = [d for d in history.decisions if not d.success]

    for decision in failed_decisions:
        logger.error(f"Failed decision: {decision.action_type}")
        logger.error(f"Rationale: {decision.rationale}")

        # Get detailed explanation
        explanation = await visibility.explain_action(decision.thought_id)
        logger.error(f"Explanation: {explanation}")
```

### Real-time Reasoning Monitoring
```python
async def stream_reasoning_activity():
    visibility = get_service(ServiceType.VISIBILITY)

    while True:
        snapshot = await visibility.get_current_state()

        # Track reasoning metrics
        metrics = {
            "active_tasks": 1 if snapshot.current_task else 0,
            "active_thoughts": len(snapshot.active_thoughts),
            "reasoning_depth": snapshot.reasoning_depth,
            "recent_decisions": len(snapshot.recent_decisions)
        }

        # Send to monitoring system
        await send_metrics("agent_reasoning", metrics)

        await asyncio.sleep(30)  # Poll every 30 seconds
```

## Testing

### Test Files
- `tests/ciris_engine/logic/services/governance/test_visibility_service.py`

### Key Test Scenarios
```python
async def test_visibility_telemetry_collection():
    # Create service with test database
    visibility = VisibilityService(
        bus_manager=mock_bus_manager,
        time_service=time_service,
        db_path=temp_db
    )
    await visibility.start()

    # Create test tasks and thoughts in database
    test_task = create_test_task("task-123", TaskStatus.ACTIVE)
    test_thought = create_test_thought("thought-456", "task-123", ThoughtStatus.PENDING)

    # Test current state snapshot
    snapshot = await visibility.get_current_state()
    assert snapshot.current_task.task_id == "task-123"
    assert len(snapshot.active_thoughts) == 1
    assert snapshot.reasoning_depth >= 0

    # Test service metrics
    status = visibility.get_status()
    assert status.is_healthy == True
    assert status.metrics["healthy"] == 1.0
    assert status.metrics["uptime_seconds"] > 0
```

### Performance Test Patterns
```python
async def test_reasoning_trace_performance():
    # Create large task with many thoughts
    task_id = "performance-test-task"
    thought_count = 100

    # Populate database with test data
    for i in range(thought_count):
        create_test_thought(f"thought-{i}", task_id, ThoughtStatus.COMPLETED)

    # Measure trace generation time
    start_time = time.time()
    trace = await visibility.get_reasoning_trace(task_id)
    end_time = time.time()

    assert trace.total_thoughts == thought_count
    assert (end_time - start_time) < 1.0  # Should complete within 1 second
```

## Configuration

### Database Dependencies
- **Database Path**: Uses `db_path` parameter (required)
- **Tables Required**: `tasks` and `thoughts` tables with proper schema
- **Persistence Functions**: Relies on `ciris_engine.logic.persistence` module

### Service Dependencies
- **BusManager**: For querying other services (required)
- **TimeService**: For consistent timestamps (optional)
- **Database Access**: Direct SQLite access for real-time queries

### Health Checks
- Service started: `_started == True`
- Bus manager available: `self.bus is not None`
- Database accessible: `self._db_path is not None`

## Known Limitations

1. **No Caching Layer**: Every request queries database directly - high latency for complex traces
2. **Limited Historical Analytics**: No time-series data for reasoning pattern analysis
3. **No Real-time Streaming**: Snapshot-based analysis rather than continuous monitoring
4. **Database Performance**: Large reasoning traces can cause slow query responses
5. **No Cross-task Correlation**: Cannot analyze relationships between related tasks
6. **Memory Usage**: Complex traces with many thoughts can consume significant memory
7. **No Metrics Persistence**: Basic service metrics are not stored for historical analysis
8. **Error Handling Gaps**: Database errors can cause incomplete traces without clear indication

## Future Enhancements

1. **Performance Optimization**
   - Implement caching layer for frequently accessed reasoning traces
   - Add database indexing for improved query performance
   - Stream large traces in chunks to reduce memory usage
   - Add connection pooling for concurrent database access

2. **Enhanced Analytics**
   - Time-series analysis of reasoning patterns and complexity trends
   - Cross-task correlation analysis for related decision chains
   - Automated pattern detection for inefficient reasoning loops
   - Statistical analysis of decision success rates by action type

3. **Real-time Capabilities**
   - WebSocket streaming of reasoning state changes
   - Real-time alerting for anomalous reasoning patterns
   - Live dashboards for agent activity monitoring
   - Event-driven updates for immediate visibility into state changes

4. **Historical Intelligence**
   - Long-term storage of reasoning traces in time-series database
   - Trend analysis for agent learning and improvement patterns
   - Comparative analysis across different task types and contexts
   - Capacity planning based on reasoning complexity growth

5. **Integration Enhancements**
   - Graph storage integration for relationship analysis
   - Export capabilities for external analysis tools
   - API versioning for backwards compatibility
   - Batch processing for large-scale trace analysis

## Integration Points

- **Task/Thought Persistence**: Direct SQLite database queries for real-time data
- **BusManager**: Coordination with other services for comprehensive analysis
- **TimeService**: Consistent timestamps across reasoning trace analysis
- **API Layer**: REST endpoints for external monitoring and dashboard integration
- **Audit Service**: Complementary relationship - Visibility provides "why", Audit provides "what"
- **Telemetry Services**: Different focus - Visibility handles reasoning, Telemetry handles performance

## Monitoring Recommendations

1. **Service Health Alerts**
   - `healthy == 0.0`: Service down or dependencies unavailable
   - `error_rate > 0.1`: High error rate in trace generation
   - Database connectivity issues causing query failures

2. **Reasoning Activity Dashboards**
   - Real-time active task and thought counts
   - Average reasoning depth and complexity trends
   - Task completion rates and processing time distributions
   - Decision success rates by action type and context

3. **Performance Monitoring**
   - Query response times for reasoning trace generation
   - Database query performance and optimization opportunities
   - Memory usage during complex trace analysis
   - Request rate and concurrency patterns

4. **Operational Intelligence**
   - Agent idle time vs. active reasoning periods
   - Reasoning pattern changes indicating learning or degradation
   - Correlation between reasoning complexity and task success
   - Early warning signs of reasoning loops or stuck states

## Performance Considerations

1. **Database Query Overhead**: Each visibility request triggers 1-5 database queries with no caching
2. **Memory Usage**: Large reasoning traces load complete thought chains into memory
3. **Processing Time**: Complex trace generation can take 500ms-2s for tasks with 50+ thoughts
4. **Concurrent Access**: No connection pooling - concurrent requests may cause database locks
5. **Scalability Limits**: Performance degrades significantly with >1000 thoughts per task

## System Integration

The Visibility Service serves as the **transparency lens** of CIRIS governance:
- **Explainable AI**: Makes agent decision-making processes transparent and auditable
- **Debugging Support**: Provides detailed reasoning traces for troubleshooting failed tasks
- **Compliance**: Supports regulatory requirements for AI system transparency
- **Learning Analysis**: Enables analysis of agent reasoning patterns for improvement
- **Human Oversight**: Gives human operators insight into agent decision-making processes

Its telemetry is critical for maintaining trust and understanding in autonomous agent behavior, ensuring that decision-making processes remain transparent and accountable to human supervisors and stakeholders.
