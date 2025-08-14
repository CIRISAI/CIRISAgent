# Agent Processor Telemetry

## Overview
The Agent Processor (AgentProcessor) is the core orchestration engine in CIRIS that manages the complete cognitive lifecycle through 6 distinct cognitive states (WAKEUP, WORK, PLAY, SOLITUDE, DREAM, SHUTDOWN). It coordinates thought processing, state transitions, task execution, and integrates with all major system components. The processor provides comprehensive telemetry covering cognitive state transitions, processing performance, thought lifecycle management, and system health metrics.

## Telemetry Data Collected

| Metric Name | Type | Storage | Update Frequency | Access Method |
|------------|------|---------|------------------|---------------|
| current_state | enum | in-memory | on state change | `get_current_state()` |
| state_duration | timedelta | calculated | on-demand | `get_status()` |
| round_number | counter | in-memory | per round | `current_round_number` |
| is_processing | boolean | in-memory | per round | `get_status()` |
| state_history | list | in-memory | on transition | `get_state_history()` |
| processor_metrics | dict | in-memory | continuous | `get_status()["processor_metrics"]` |
| queue_status | dict | calculated | on-demand | `get_queue_status()` |
| thought_processing_traces | correlation | persistent | per thought | ServiceCorrelation storage |
| cognitive_state_transitions | correlation | persistent | per transition | StateTransitionRecord |
| batch_processing_performance | metric | time-series | per batch | enhanced telemetry |
| dream_scheduling | memory graph | persistent | scheduled events | GraphNode storage |
| shutdown_negotiation_status | dict | in-memory | during shutdown | shutdown processor |

## Data Structures

### Main Processor Status
```python
{
    "state": "WORK",                    # Current cognitive state
    "state_duration": "0:15:30",        # Time in current state
    "round_number": 1247,               # Processing round counter
    "is_processing": true,              # Active processing status
    "processor_metrics": {
        "WAKEUP": {
            "start_time": "2025-08-14T10:00:00Z",
            "items_processed": 15,
            "errors": 0,
            "rounds_completed": 12,
            "additional_metrics": {
                "thoughts_generated": 8,
                "actions_dispatched": 7,
                "memories_created": 3,
                "llm_tokens_used": 1200,
                "cache_hits": 5,
                "cache_misses": 2,
                "custom_counters": {"identity_confirmations": 1},
                "custom_gauges": {"confidence_score": 0.95}
            }
        },
        "WORK": {
            "start_time": "2025-08-14T10:15:00Z",
            "items_processed": 234,
            "errors": 3,
            "rounds_completed": 78,
            "additional_metrics": {
                "thoughts_generated": 156,
                "actions_dispatched": 145,
                "memories_created": 89,
                "llm_tokens_used": 45600,
                "cache_hits": 123,
                "cache_misses": 33
            }
        }
        // ... other states
    },
    "queue_status": {
        "thought_counts": {
            "pending": 12,
            "processing": 3,
            "completed": 1543,
            "failed": 7,
            "total": 1565
        },
        "recent_activity": [
            {
                "thought_id": "thought_12345",
                "thought_type": "task_analysis",
                "status": "completed",
                "created_at": "2025-08-14T10:30:00Z",
                "content_preview": "Analyzing user request for weather information..."
            }
        ],
        "task_summary": {
            "active_tasks": 5,
            "pending_tasks": 12
        },
        "queue_health": {
            "has_pending_work": true,
            "has_processing_work": true,
            "has_recent_failures": false,
            "queue_utilization": "medium"
        }
    }
}
```

### State Transition Record
```python
{
    "timestamp": "2025-08-14T10:15:00.123456+00:00",
    "from_state": "WAKEUP",
    "to_state": "WORK",
    "metadata": {
        "reason": "wakeup_complete",
        "trigger": "automatic",
        "round_number": 12,
        "preload_tasks_loaded": 3
    }
}
```

### Thought Processing Correlation
```python
{
    "correlation_id": "trace_agent_processor_thought_67890_1692015300.123",
    "correlation_type": "TRACE_SPAN",
    "service_type": "agent_processor",
    "handler_name": "AgentProcessor",
    "action_type": "process_thought",
    "created_at": "2025-08-14T10:30:00.123456Z",
    "trace_context": {
        "trace_id": "task_task_123_thought_67890",
        "span_id": "agent_processor_thought_67890",
        "span_name": "process_single_thought",
        "baggage": {
            "thought_id": "thought_67890",
            "task_id": "task_123",
            "processor_state": "WORK"
        }
    },
    "tags": {
        "thought_id": "thought_67890",
        "task_id": "task_123",
        "component_type": "agent_processor",
        "thought_type": "task_analysis",
        "processor_state": "WORK"
    },
    "response_data": {
        "success": true,
        "execution_time_ms": 1250.5,
        "result_type": "action_dispatched",
        "tokens_used": 850,
        "result_summary": "Successfully processed thought and dispatched action"
    }
}
```

### Queue Status Details
```python
{
    "thought_counts": {
        "pending": 12,
        "processing": 3,
        "completed": 1543,
        "failed": 7,
        "total": 1565
    },
    "recent_activity": [
        {
            "thought_id": "thought_12345",
            "thought_type": "task_analysis",
            "status": "completed",
            "created_at": "2025-08-14T10:30:00Z",
            "content_preview": "Analyzing user request for weather information..."
        }
    ],
    "task_summary": {
        "active_tasks": 5,
        "pending_tasks": 12
    },
    "queue_health": {
        "has_pending_work": true,
        "has_processing_work": true,
        "has_recent_failures": false,
        "queue_utilization": "medium"  # low/medium/high
    }
}
```

## API Access Patterns

### Current Access
- **Full Status**: `get_status()` returns comprehensive processor state
- **State Only**: `get_current_state()` returns current cognitive state
- **Queue Status**: `get_queue_status()` returns processing queue details
- **State History**: `get_state_history(limit=10)` returns recent state transitions
- **Internal Metrics**: `processor.get_metrics()` for each state processor

### Recommended Endpoints

#### Cognitive State Overview
```
GET /v1/telemetry/agent-processor/state
```
Returns current cognitive state and transitions:
```json
{
    "current_state": "WORK",
    "state_duration_seconds": 930,
    "round_number": 1247,
    "is_processing": true,
    "consecutive_errors": 0,
    "last_transition": {
        "timestamp": "2025-08-14T10:15:00Z",
        "from_state": "WAKEUP",
        "to_state": "WORK",
        "reason": "wakeup_complete"
    },
    "state_health": "healthy",
    "auto_transition_due": false
}
```

#### Processing Performance Metrics
```
GET /v1/telemetry/agent-processor/performance
```
Returns processing performance across all states:
```json
{
    "overall_metrics": {
        "uptime_seconds": 18650,
        "total_rounds": 1247,
        "total_thoughts_processed": 1565,
        "average_thoughts_per_minute": 5.2,
        "error_rate_percent": 0.45
    },
    "by_state": {
        "WORK": {
            "time_spent_seconds": 14200,
            "thoughts_processed": 1234,
            "average_processing_time_ms": 850.3,
            "cache_hit_rate": 78.5
        },
        "DREAM": {
            "sessions_completed": 3,
            "total_dream_time_minutes": 90,
            "insights_generated": 12
        }
    }
}
```

#### Thought Processing Pipeline
```
GET /v1/telemetry/agent-processor/pipeline
```
Returns thought processing pipeline status:
```json
{
    "pipeline_health": "healthy",
    "current_batch_size": 5,
    "pending_thoughts": 12,
    "processing_thoughts": 3,
    "batch_processing_stats": {
        "average_batch_time_ms": 2340.5,
        "batches_per_hour": 156,
        "batch_success_rate": 96.8
    },
    "thought_lifecycle": {
        "average_time_to_process_ms": 1250.5,
        "p95_processing_time_ms": 3200.0,
        "thought_types": {
            "task_analysis": 45,
            "memory_retrieval": 23,
            "action_planning": 34
        }
    }
}
```

#### State Transition Analysis
```
GET /v1/telemetry/agent-processor/transitions
```
Returns state transition patterns and health:
```json
{
    "transition_history": [
        {
            "timestamp": "2025-08-14T10:15:00Z",
            "from_state": "WAKEUP",
            "to_state": "WORK",
            "duration_in_previous_state_seconds": 900,
            "trigger": "automatic"
        }
    ],
    "transition_patterns": {
        "most_common_transitions": [
            {"from": "WORK", "to": "DREAM", "count": 12, "avg_duration": 1800},
            {"from": "DREAM", "to": "WORK", "count": 12, "avg_duration": 1800}
        ],
        "unusual_transitions": [],
        "failed_transitions": 0
    },
    "state_distribution": {
        "WORK": 76.2,
        "DREAM": 12.8,
        "WAKEUP": 5.5,
        "SOLITUDE": 3.2,
        "PLAY": 2.1,
        "SHUTDOWN": 0.2
    }
}
```

## Example Usage

### Monitor Processor State
```python
# Get current processor status
status = agent_processor.get_status()
current_state = status["state"]
processing_active = status["is_processing"]

# Check if processor is healthy
if status["queue_status"]["queue_health"]["has_recent_failures"]:
    logger.warning("Processor has recent failures")

# Monitor specific state metrics
work_metrics = status["processor_metrics"].get("WORK", {})
if work_metrics.get("errors", 0) > 5:
    logger.error("Work processor has high error count")
```

### Track State Transitions
```python
# Get recent state history
transitions = agent_processor.get_state_history(limit=5)
for transition in transitions:
    print(f"{transition.timestamp}: {transition.from_state} -> {transition.to_state}")

# Check if processor stuck in one state
current_duration = agent_processor.state_manager.get_state_duration()
if current_duration > timedelta(hours=2) and current_state != "DREAM":
    logger.warning(f"Processor stuck in {current_state} for {current_duration}")
```

### Monitor Thought Processing Performance
```python
# Get detailed queue status
queue_status = agent_processor.get_queue_status()
pending_count = queue_status.pending_tasks
processing_count = queue_status.processing_tasks

# Check processing health
if pending_count > 50:
    logger.warning(f"High pending thought count: {pending_count}")

# Monitor recent thought activity
recent_thoughts = queue_status.recent_activity[:3]
for thought in recent_thoughts:
    if thought["status"] == "failed":
        logger.error(f"Recent thought failure: {thought['thought_id']}")
```

### Access Processing Correlations
```python
# Query thought processing traces
from ciris_engine.logic.persistence import get_correlations_by_service

correlations = get_correlations_by_service(
    service_type="agent_processor",
    start_time=datetime.now() - timedelta(hours=1)
)

# Analyze processing performance
processing_times = [
    c.response_data.execution_time_ms
    for c in correlations
    if c.response_data and c.response_data.execution_time_ms
]

avg_time = sum(processing_times) / len(processing_times)
print(f"Average thought processing time: {avg_time:.2f}ms")
```

## Testing

### Test Files
- `tests/logic/processors/core/test_main_processor.py` - Core processor tests
- `tests/logic/processors/support/test_state_manager.py` - State management tests
- `tests/logic/telemetry/test_processor_telemetry.py` - Telemetry integration tests

### Validation Steps
1. Start agent processor and verify telemetry collection
2. Trigger state transitions and validate history recording
3. Process thoughts and verify correlation creation
4. Test error scenarios and failure telemetry
5. Validate queue status accuracy
6. Check metric aggregation across states

```python
async def test_agent_processor_telemetry():
    processor = AgentProcessor(...)

    # Test state telemetry
    await processor.start_processing()
    status = processor.get_status()
    assert status["state"] == "WAKEUP"
    assert status["is_processing"] is True

    # Test transition recording
    initial_history_count = len(processor.get_state_history())
    # ... trigger state transition
    new_history_count = len(processor.get_state_history())
    assert new_history_count > initial_history_count

    # Test thought processing telemetry
    # ... create and process thoughts
    correlations = get_correlations_by_service("agent_processor")
    assert len(correlations) > 0
    assert all(c.service_type == "agent_processor" for c in correlations)
```

## Configuration

### Cognitive States
```python
class AgentState(Enum):
    WAKEUP = "wakeup"        # Identity confirmation and initialization
    WORK = "work"            # Normal task processing
    PLAY = "play"            # Creative and experimental mode
    SOLITUDE = "solitude"    # Reflection and introspection
    DREAM = "dream"          # Deep memory consolidation
    SHUTDOWN = "shutdown"    # Graceful termination
```

### State Transition Rules
```python
VALID_TRANSITIONS = [
    # Emergency shutdown from any state
    (ANY_STATE, SHUTDOWN),
    # Startup transition
    (SHUTDOWN, WAKEUP),
    # Normal workflow
    (WAKEUP, WORK),
    (WORK, DREAM),     # Scheduled introspection
    (WORK, PLAY),      # Creative sessions
    (WORK, SOLITUDE),  # Reflection periods
    (DREAM, WORK),     # Return from introspection
    (PLAY, WORK),      # Return from creativity
    (SOLITUDE, WORK),  # Return from reflection
]
```

### Processing Configuration
```python
{
    "max_active_thoughts": 50,      # Concurrent thought limit
    "batch_size": 5,                # Thoughts per batch
    "round_delay_seconds": 3.0,     # Delay between rounds in WORK
    "max_consecutive_errors": 5,    # Error threshold before shutdown
    "dream_schedule_hours": 6,      # Hours between dream sessions
    "dream_duration_minutes": 30,   # Default dream session length
}
```

## Graph Storage

### Dream Scheduling
Dream sessions are scheduled as GraphNode entities in memory:
```python
{
    "id": "dream_schedule_1692015300",
    "type": "CONCEPT",
    "scope": "LOCAL",
    "attributes": {
        "task_type": "scheduled_dream",
        "scheduled_for": "2025-08-14T16:00:00Z",
        "duration_minutes": 30,
        "priority": "health_maintenance",
        "can_defer": true,
        "defer_window_hours": 2
    }
}
```

### State Metadata Storage
State-specific metadata is stored with each processor:
```python
{
    "state_metadata": {
        "WORK": {
            "entered_at": "2025-08-14T10:15:00Z",
            "metrics": {
                "tasks_completed": 45,
                "thoughts_processed": 234,
                "last_activity": "2025-08-14T10:45:00Z"
            }
        }
    }
}
```

## Known Limitations

1. **In-Memory State**: Current state and round counters lost on restart
2. **No State Persistence**: State history not saved across restarts
3. **Limited Batch Analytics**: No historical batch performance analysis
4. **No Cross-Instance Sync**: Multiple CIRIS instances don't share processor state
5. **Fixed Dream Scheduling**: Dream schedules not dynamically adjusted based on workload
6. **No Predictive Transitions**: State transitions are reactive, not predictive
7. **Limited Error Classification**: Errors not categorized by type or severity

## Future Enhancements

1. **Persistent State Management**: Store state history and metrics in database
2. **Predictive State Transitions**: ML-based state transition recommendations
3. **Dynamic Load Balancing**: Adjust batch sizes based on system load
4. **Advanced Dream Scheduling**: Workload-aware dream session scheduling
5. **Cognitive Performance Analytics**: Deep analysis of cognitive state effectiveness
6. **Cross-Instance Coordination**: Synchronized processing across multiple instances
7. **Real-Time Performance Optimization**: Auto-tuning of processing parameters
8. **Cognitive Health Scoring**: Overall processor health metrics

## Integration Points

- **State Processors**: Each cognitive state has dedicated processor with telemetry
- **Thought Processor**: Integrates with thought generation and processing pipeline
- **Action Dispatcher**: Coordinates with action execution and telemetry
- **Memory Service**: Stores dream schedules and long-term state metadata
- **Telemetry Service**: Records all processing correlations and metrics
- **Runtime Control**: Exposes processor status via API endpoints
- **Service Registry**: Manages processor service discovery and health

## Monitoring Recommendations

1. **Alert on State Locks**: When processor stuck in non-DREAM state > 2 hours
2. **Monitor Error Rates**: Alert when error rate > 5% in any 10-minute window
3. **Track Processing Latency**: P95 thought processing time > 5 seconds
4. **Queue Depth Monitoring**: Alert when pending thoughts > 100
5. **State Transition Anomalies**: Alert on unexpected or failed transitions
6. **Dream Session Health**: Alert if no dream sessions in 12+ hours
7. **Batch Processing Efficiency**: Monitor batch success rate < 95%
8. **Cognitive Load Balance**: Monitor state distribution for balance issues

## Security Considerations

1. **Thought Content Filtering**: Sensitive data in thought traces is sanitized
2. **Correlation Access Control**: Processing traces require appropriate permissions
3. **State Audit Trail**: All state transitions are audited and logged
4. **Error Information Leakage**: Error details sanitized in public telemetry
5. **Memory Safety**: Dream scheduling prevents memory exhaustion attacks
6. **Processing Limits**: Max thought limits prevent DoS attacks
7. **Shutdown Security**: Emergency shutdown requires authenticated triggers

## Performance Considerations

1. **Batch Processing Overhead**: Larger batches reduce per-thought overhead but increase latency
2. **Correlation Storage**: Each thought creates persistent correlation record
3. **State History Growth**: Unbounded state history can consume memory
4. **Telemetry Collection Overhead**: Comprehensive telemetry impacts performance by ~2-5%
5. **Queue Status Queries**: Frequent queue status calls can impact database performance
6. **Dream Memory Usage**: Dream sessions can consume significant memory during consolidation
