# Processing Queue Component Telemetry

## Overview
The Processing Queue Component manages the in-memory queue of thoughts and tasks awaiting processing in CIRIS. It provides telemetry data about queue depths, processing rates, and thought lifecycle tracking. The component is implemented across multiple layers: the ThoughtManager handles queue population, the AgentProcessor provides status access, and the RuntimeControlService exposes telemetry via API endpoints.

## Telemetry Data Collected

| Metric Name | Type | Storage | Update Frequency | Access Method |
|------------|------|---------|------------------|---------------|
| queue_size | gauge | real-time calculation | per query | `get_processor_queue_status()` |
| max_size | gauge | configuration | static | `get_processor_queue_status()` |
| processing_rate | gauge | calculated | per query | `get_processor_queue_status()` |
| average_latency_ms | gauge | calculated | per query | `get_processor_queue_status()` |
| oldest_message_age_seconds | gauge | calculated | per query | `get_processor_queue_status()` |
| pending_tasks | gauge | database query | per query | `get_queue_status()` |
| pending_thoughts | gauge | database query | per query | `get_queue_status()` |
| processing_thoughts | gauge | database query | per query | `get_queue_status()` |
| total_tasks | gauge | database query | per query | `get_queue_status()` |
| total_thoughts | gauge | database query | per query | `get_queue_status()` |
| in_memory_queue_size | gauge | deque length | per populate | `len(processing_queue)` |
| max_active_thoughts | gauge | configuration | static | ThoughtManager config |
| seed_thoughts_generated | counter | per generation cycle | per round | `generate_seed_thoughts()` |
| queue_populate_count | counter | per populate operation | per round | `populate_queue()` |
| thoughts_marked_processing | counter | per batch processing | per batch | `mark_thoughts_processing()` |
| follow_up_thoughts_created | counter | per follow-up creation | per creation | `create_follow_up_thought()` |

## Data Structures

### ProcessorQueueStatus
```python
{
    "processor_name": "agent",
    "queue_size": 15,           # pending_tasks + pending_thoughts
    "max_size": 1000,          # Configured maximum
    "processing_rate": 1.0,     # Messages per second (calculated)
    "average_latency_ms": 0.0,  # Average processing time (calculated)
    "oldest_message_age_seconds": 45.3  # Age of oldest pending item
}
```

### QueueStatus (Internal)
```python
{
    "pending_tasks": 3,
    "pending_thoughts": 12,
    "processing_thoughts": 5,
    "total_tasks": 150,
    "total_thoughts": 1247
}
```

### ProcessingQueueItem
```python
{
    "thought_id": "thought_12345_std_seed",
    "source_task_id": "task_67890",
    "thought_type": "STANDARD",
    "content": {
        "text": "Initial seed thought for task: User wants help with...",
        "metadata": {}
    },
    "raw_input_string": "User wants help with documentation",
    "initial_context": {
        "task_id": "task_67890",
        "channel_id": "cli_channel_001",
        "round_number": 1,
        "depth": 0,
        "parent_thought_id": None,
        "correlation_id": "corr_123456"
    },
    "ponder_notes": None,
    "conscience_feedback": None
}
```

### ThoughtManager Queue State
```python
{
    "processing_queue_size": 8,        # Current in-memory queue size
    "max_active_thoughts": 50,         # Configured limit
    "queue_capacity_used": 0.16,       # queue_size / max_active_thoughts
    "memory_meta_mode": false,         # Whether processing only memory meta-thoughts
    "queue_cleared_count": 45,         # Number of times queue was cleared
    "capacity_warnings": 2             # Times max capacity was reached
}
```

## API Access Patterns

### Current Access
- **Full Exposure**: `GET /api/datum/v1/system/processing-queue` endpoint
- **Authorization**: OBSERVER role or higher
- **Response Format**: `SuccessResponse<ProcessorQueueStatus>`

### Recommended Endpoints

#### Processing Queue Status
```
GET /v1/telemetry/processing-queue
```
Returns complete queue telemetry:
```json
{
    "processor_name": "agent",
    "queue_status": {
        "current_size": 15,
        "max_size": 1000,
        "capacity_utilization": 0.015,
        "processing_rate": 2.3,
        "average_latency_ms": 150.5,
        "oldest_message_age_seconds": 45.3
    },
    "task_breakdown": {
        "pending_tasks": 3,
        "pending_thoughts": 12,
        "processing_thoughts": 5,
        "total_tasks": 150,
        "total_thoughts": 1247
    },
    "in_memory_queue": {
        "size": 8,
        "max_active_thoughts": 50,
        "capacity_used": 0.16,
        "memory_meta_mode": false
    },
    "performance_metrics": {
        "seed_thoughts_generated": 145,
        "queue_populate_operations": 67,
        "follow_up_thoughts_created": 89,
        "processing_batches": 156
    }
}
```

#### Queue History
```
GET /v1/telemetry/processing-queue/history?hours=24
```
Returns historical queue depth data:
```json
{
    "time_range": "2025-08-14T00:00:00Z to 2025-08-14T23:59:59Z",
    "samples": [
        {
            "timestamp": "2025-08-14T13:30:00Z",
            "queue_size": 15,
            "pending_tasks": 3,
            "pending_thoughts": 12,
            "processing_rate": 2.3
        }
    ],
    "aggregates": {
        "avg_queue_size": 12.4,
        "max_queue_size": 28,
        "avg_processing_rate": 2.1,
        "total_processed": 1456
    }
}
```

#### Active Thoughts
```
GET /v1/visibility/thoughts
```
Returns current in-memory queue items:
```json
{
    "queue_size": 8,
    "max_capacity": 50,
    "thoughts": [
        {
            "thought_id": "thought_12345_std_seed",
            "task_id": "task_67890",
            "type": "STANDARD",
            "age_seconds": 45.3,
            "content_preview": "Initial seed thought for task...",
            "depth": 0,
            "round_number": 1
        }
    ]
}
```

## Graph Storage

### Telemetry Graph Nodes
Processing queue telemetry is stored in the memory graph via TelemetryService:

```python
# Queue status metrics
await memory_service.memorize_metric(
    "processing_queue_size",
    queue_size,
    tags={"processor": "agent", "type": "queue_depth"}
)

await memory_service.memorize_metric(
    "processing_rate",
    processing_rate,
    tags={"processor": "agent", "type": "performance"}
)

await memory_service.memorize_metric(
    "queue_capacity_utilization",
    capacity_utilization,
    tags={"processor": "agent", "type": "capacity"}
)
```

### Graph Query Patterns
```python
# Get recent queue depth trends
recent_depths = await memory_service.recall(
    "processing_queue_size",
    time_range="last_24h",
    tags={"processor": "agent"}
)

# Get processing performance metrics
performance = await memory_service.recall(
    "processing_rate",
    time_range="last_1h",
    tags={"type": "performance"}
)
```

## Example Usage

### Monitor Queue Health
```python
from ciris_engine.logic.services.runtime.control_service import RuntimeControlService

# Get queue status
runtime_control = RuntimeControlService()
status = await runtime_control.get_processor_queue_status()

# Check for bottlenecks
if status.queue_size > 100:
    logger.warning(f"Queue backed up: {status.queue_size} items")

if status.processing_rate < 0.5:
    logger.warning(f"Low processing rate: {status.processing_rate} items/sec")

# Monitor capacity
capacity_used = status.queue_size / status.max_size
if capacity_used > 0.8:
    logger.error(f"Queue at {capacity_used*100:.1f}% capacity")
```

### Track Processing Patterns
```python
from ciris_engine.logic.processors.support.thought_manager import ThoughtManager

# Monitor queue population
thought_manager = ThoughtManager(time_service, max_active_thoughts=50)
added_count = thought_manager.populate_queue(round_number=1)

logger.info(f"Round 1: Added {added_count} thoughts to queue")

# Check for memory meta-thought priority
if added_count == len([t for t in pending if t.thought_type == ThoughtType.MEMORY]):
    logger.info("Memory meta-thoughts detected, processing exclusively")
```

### Single Step Debugging
```python
# Execute one processing cycle
result = await runtime_control.single_step()

if result.success:
    logger.info(f"Single step completed in {result.execution_time_ms}ms")
    logger.info(f"Before: {result.before_state.queue_size} items")
    logger.info(f"After: {result.after_state.queue_size} items")
else:
    logger.error(f"Single step failed: {result.error}")
```

### Performance Analysis
```python
from ciris_engine.logic.persistence.models.queue_status import get_queue_status

# Get detailed queue breakdown
queue_status = get_queue_status()

logger.info(f"Queue Analysis:")
logger.info(f"  Pending Tasks: {queue_status.pending_tasks}")
logger.info(f"  Pending Thoughts: {queue_status.pending_thoughts}")
logger.info(f"  Processing Thoughts: {queue_status.processing_thoughts}")
logger.info(f"  Total Pipeline: {queue_status.pending_tasks + queue_status.pending_thoughts + queue_status.processing_thoughts}")

# Calculate throughput metrics
total_completed = queue_status.total_thoughts - queue_status.pending_thoughts - queue_status.processing_thoughts
if queue_status.total_thoughts > 0:
    completion_rate = total_completed / queue_status.total_thoughts
    logger.info(f"  Completion Rate: {completion_rate:.2%}")
```

## Testing

### Test Files
- `tests/logic/processors/support/test_thought_manager.py` - ThoughtManager tests
- `tests/logic/processors/core/test_main_processor.py` - AgentProcessor tests
- `tests/services/test_runtime_control_extensions.py` - RuntimeControl tests
- `tests/api/test_system_extensions.py` - API endpoint tests
- `tests/logic/persistence/models/test_queue_status.py` - Queue status tests

### Validation Steps
1. **Queue Population**: Verify thoughts are correctly added to in-memory queue
2. **Status Retrieval**: Confirm accurate counts from database and memory
3. **API Exposure**: Test endpoint returns proper ProcessorQueueStatus
4. **Capacity Limits**: Verify max_active_thoughts enforcement
5. **Memory Meta Priority**: Test exclusive processing of memory meta-thoughts
6. **Error Handling**: Verify graceful degradation when processor unavailable

```python
async def test_processing_queue_telemetry():
    """Test complete processing queue telemetry pipeline."""

    # Setup
    thought_manager = ThoughtManager(mock_time_service, max_active_thoughts=10)
    runtime_control = RuntimeControlService()

    # Create test tasks and thoughts
    test_tasks = create_test_tasks(count=5)
    thought_count = thought_manager.generate_seed_thoughts(test_tasks, round_number=1)
    assert thought_count == 5

    # Populate queue
    queued_count = thought_manager.populate_queue(round_number=1)
    assert queued_count <= 10  # Respects max_active_thoughts

    # Verify queue status
    queue_status = await runtime_control.get_processor_queue_status()
    assert queue_status.processor_name == "agent"
    assert queue_status.queue_size >= 5
    assert queue_status.max_size == 1000

    # Test capacity enforcement
    thought_manager.max_active_thoughts = 3
    limited_count = thought_manager.populate_queue(round_number=2)
    assert limited_count == 3  # Limited by capacity
```

## Configuration

### ThoughtManager Settings
```python
class ThoughtManagerConfig:
    max_active_thoughts: int = 50      # In-memory queue capacity
    default_channel_id: str = None     # Default channel for thoughts
    memory_meta_priority: bool = True  # Prioritize memory meta-thoughts
    capacity_warning_threshold: float = 0.8  # Warn at 80% capacity
```

### Processing Queue Defaults
```python
{
    "max_queue_size": 1000,           # ProcessorQueueStatus max_size
    "default_processing_rate": 1.0,   # Fallback rate when no metrics
    "queue_poll_interval": 1.0,       # Seconds between queue polls
    "oldest_message_warning": 300     # Warn if message older than 5 minutes
}
```

### Database Query Limits
```python
{
    "pending_thoughts_limit": 1000,   # Max thoughts returned by query
    "task_query_timeout": 30.0,       # Query timeout seconds
    "status_cache_ttl": 5.0           # Cache queue status for 5 seconds
}
```

## Known Limitations

1. **In-Memory Queue Loss**: Processing queue cleared on restart, no persistence
2. **No Historical Metrics**: Processing rates and latencies not calculated from real data
3. **Limited Age Tracking**: oldest_message_age_seconds not implemented
4. **Capacity Enforcement**: max_size not enforced, only used for reporting
5. **No Cross-Round Tracking**: Queue metrics don't span processing rounds
6. **Database Dependency**: All telemetry requires database queries, no caching
7. **Memory Meta Exclusive**: When memory meta-thoughts present, other thoughts ignored
8. **Static Configuration**: max_active_thoughts not dynamically adjustable

## Future Enhancements

1. **Persistent Queue State**: Store processing queue in Redis for durability
2. **Real Processing Metrics**: Calculate actual processing rates and latencies
3. **Historical Tracking**: Store queue depth trends in TSDB
4. **Age Calculation**: Implement oldest_message_age_seconds from thought timestamps
5. **Dynamic Capacity**: Allow runtime adjustment of max_active_thoughts
6. **Queue Persistence**: Save/restore in-memory queue across restarts
7. **Performance Optimization**: Cache queue status with intelligent invalidation
8. **Advanced Metrics**: Track processing time per thought type, success rates
9. **Alert Integration**: Automatic alerts for queue backups and processing delays
10. **Load Balancing**: Distribute processing load based on queue depth

## Integration Points

- **RuntimeControlService**: Primary telemetry exposure point
- **AgentProcessor**: Core queue status provider via `get_queue_status()`
- **ThoughtManager**: In-memory queue management and population
- **TelemetryService**: Graph storage for historical queue metrics
- **API System Extensions**: RESTful access via `/system/processing-queue`
- **Persistence Layer**: Database queries for task and thought counts
- **SingleStep Debugging**: Queue state before/after processing cycles

## Monitoring Recommendations

1. **Alert on Queue Backup**: When queue_size > 100 for > 5 minutes
2. **Monitor Processing Rate**: Alert if rate < 0.5 items/sec for > 2 minutes
3. **Track Capacity Usage**: Warn at 80%, critical at 95% of max_active_thoughts
4. **Age Monitoring**: Alert if oldest message > 5 minutes old
5. **Memory Meta Priority**: Log when exclusive memory processing activated
6. **Failed Thoughts**: Monitor processing_thoughts that remain stuck
7. **Round Processing**: Track thoughts processed per round for performance tuning
8. **Database Performance**: Monitor queue status query times

## Security Considerations

1. **Authorization Required**: OBSERVER role minimum for queue status access
2. **Sensitive Data Filtering**: Thought content not exposed in telemetry APIs
3. **Rate Limiting**: Queue status queries should be rate-limited
4. **Data Sanitization**: Ensure no PII in queue item previews
5. **Audit Logging**: Log all queue status queries for security monitoring
6. **Memory Inspection**: In-memory queue access requires admin privileges
7. **Configuration Protection**: max_active_thoughts changes require ADMIN role

## Performance Considerations

1. **Database Query Cost**: Each status call queries tasks and thoughts tables
2. **Memory Usage**: In-memory queue limited by max_active_thoughts setting
3. **Query Optimization**: Batch status queries when possible
4. **Cache Strategy**: Consider caching queue status for high-frequency access
5. **Indexing**: Ensure database indexes on task/thought status fields
6. **Memory Efficiency**: ProcessingQueueItem objects consume memory per item
7. **Concurrent Access**: Thread-safe access to in-memory queue required
8. **Large Queue Handling**: Performance degrades with very large queues
