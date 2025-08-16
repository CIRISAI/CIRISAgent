# Resource Monitor Service Telemetry

## Overview
The Resource Monitor Service tracks system resource usage (CPU, memory, disk, tokens) and enforces resource limits. It runs continuously every second, updating a snapshot of current resource state and emitting signals when thresholds are exceeded.

## Telemetry Data Collected

| Metric Name | Type | Storage | Update Frequency | Access Method |
|------------|------|---------|------------------|---------------|
| memory_mb | gauge | in-memory snapshot | 1 second | `snapshot.memory_mb` |
| memory_percent | gauge | in-memory snapshot | 1 second | `snapshot.memory_percent` |
| cpu_percent | gauge | in-memory snapshot | 1 second | `snapshot.cpu_percent` |
| cpu_average_1m | gauge | in-memory snapshot | 1 second | `snapshot.cpu_average_1m` |
| disk_free_mb | gauge | in-memory snapshot | 1 second | `snapshot.disk_free_mb` |
| disk_used_mb | gauge | in-memory snapshot | 1 second | `snapshot.disk_used_mb` |
| tokens_used_hour | counter | in-memory deque | on token use | `snapshot.tokens_used_hour` |
| tokens_used_day | counter | in-memory deque | on token use | `snapshot.tokens_used_day` |
| thoughts_active | gauge | database query | 1 second | `snapshot.thoughts_active` |
| warnings | list | in-memory snapshot | 1 second | `snapshot.warnings` |
| critical | list | in-memory snapshot | 1 second | `snapshot.critical` |
| healthy | boolean | in-memory snapshot | 1 second | `snapshot.healthy` |
| cpu_history | time-series | in-memory deque | 1 second | `_cpu_history` (60 samples) |
| token_history | time-series | in-memory deque | on token use | `_token_history` (86400 samples) |

## Data Structures

### ResourceSnapshot
```python
{
    "memory_mb": 1234,              # Current memory usage in MB
    "memory_percent": 30,           # Memory as % of limit
    "cpu_percent": 45,              # Current CPU usage %
    "cpu_average_1m": 42,           # 1-minute CPU average
    "disk_free_mb": 50000,          # Free disk space
    "disk_used_mb": 10000,          # Used disk space
    "tokens_used_hour": 15000,      # Tokens in last hour
    "tokens_used_day": 250000,      # Tokens in last day
    "thoughts_active": 5,           # Active thoughts in queue
    "warnings": [                   # Resource warnings
        "memory_mb: 3000/4096",
        "tokens_hour: 45000/50000"
    ],
    "critical": [                   # Critical resource issues
        "cpu_percent: 95/80"
    ],
    "healthy": true                 # Overall health status
}
```

### ResourceBudget Configuration
```python
{
    "memory_mb": {
        "limit": 4096,
        "warning": 3072,     # 75% threshold
        "critical": 3686,     # 90% threshold
        "action": "throttle",
        "cooldown_seconds": 60
    },
    "cpu_percent": {
        "limit": 80,
        "warning": 60,
        "critical": 75,
        "action": "defer",
        "cooldown_seconds": 30
    },
    "tokens_hour": {
        "limit": 50000,
        "warning": 40000,
        "critical": 45000,
        "action": "reject",
        "cooldown_seconds": 300
    },
    "tokens_day": {
        "limit": 500000,
        "warning": 400000,
        "critical": 450000,
        "action": "shutdown",
        "cooldown_seconds": 3600
    },
    "thoughts_active": {
        "limit": 100,
        "warning": 80,
        "critical": 90,
        "action": "defer",
        "cooldown_seconds": 10
    }
}
```

### Resource Actions
```python
class ResourceAction(Enum):
    NONE = "none"          # No action
    LOG = "log"           # Log warning only
    THROTTLE = "throttle" # Slow down processing
    DEFER = "defer"       # Defer new requests
    REJECT = "reject"     # Reject new requests
    SHUTDOWN = "shutdown" # Graceful shutdown
```

### Signal Events
```python
{
    "signal": "throttle|defer|reject|shutdown",
    "resource": "memory_mb|cpu_percent|tokens_hour|...",
    "timestamp": "2025-08-14T13:30:00Z",
    "current_value": 3686,
    "limit": 4096
}
```

## API Access Patterns

### Current Access
- **No Direct API**: Resource snapshot not exposed via REST
- **Internal Access**: Other services can access via dependency injection
- **Signal Bus**: Services can subscribe to resource signals

### Recommended Endpoints

#### Get Resource Snapshot
```
GET /v1/telemetry/resources/snapshot
```
Returns current resource state:
```json
{
    "memory": {
        "used_mb": 1234,
        "limit_mb": 4096,
        "percent": 30
    },
    "cpu": {
        "current": 45,
        "average_1m": 42,
        "limit": 80
    },
    "disk": {
        "free_mb": 50000,
        "used_mb": 10000
    },
    "tokens": {
        "hour": 15000,
        "hour_limit": 50000,
        "day": 250000,
        "day_limit": 500000
    },
    "thoughts": {
        "active": 5,
        "limit": 100
    },
    "health": {
        "healthy": true,
        "warnings": ["memory approaching limit"],
        "critical": []
    }
}
```

#### Get Resource History
```
GET /v1/telemetry/resources/history
```
Query parameters:
- `resource`: cpu|memory|tokens
- `period`: 1h|1d|7d

Returns time-series data:
```json
{
    "resource": "cpu",
    "period": "1h",
    "data": [
        {"timestamp": "2025-08-14T13:00:00Z", "value": 45},
        {"timestamp": "2025-08-14T13:01:00Z", "value": 42}
    ]
}
```

#### Check Resource Availability
```
POST /v1/telemetry/resources/check
```
Request body:
```json
{
    "resource": "tokens_hour",
    "amount": 1000
}
```
Returns:
```json
{
    "available": true,
    "current": 15000,
    "requested": 1000,
    "limit": 50000,
    "would_exceed": false
}
```

## Example Usage

### Get Current Snapshot
```python
resource_monitor = get_service(ServiceType.VISIBILITY)
snapshot = resource_monitor.snapshot

print(f"Memory: {snapshot.memory_mb}MB / {budget.memory_mb.limit}MB")
print(f"CPU: {snapshot.cpu_percent}% (avg: {snapshot.cpu_average_1m}%)")
print(f"Tokens (hour): {snapshot.tokens_used_hour}")
```

### Record Token Usage
```python
# After LLM call
await resource_monitor.record_tokens(tokens_used=1523)
```

### Check Resource Availability
```python
# Before expensive operation
can_proceed = await resource_monitor.check_available(
    resource="memory_mb",
    amount=500  # Need 500MB more
)
if not can_proceed:
    logger.warning("Insufficient memory, deferring operation")
```

### Subscribe to Resource Signals
```python
async def handle_resource_signal(signal: str, resource: str):
    if signal == "throttle":
        logger.info(f"Throttling due to {resource}")
        # Reduce processing rate
    elif signal == "shutdown":
        logger.critical(f"Shutdown triggered by {resource}")
        # Initiate graceful shutdown

resource_monitor.signal_bus.register("throttle", handle_resource_signal)
resource_monitor.signal_bus.register("shutdown", handle_resource_signal)
```

## Testing

### Test Files
- `tests/logic/services/infrastructure/test_resource_monitor.py`
- `tests/integration/test_resource_limits.py`

### Validation Steps
1. Start resource monitor service
2. Verify snapshot updates every second
3. Allocate memory to trigger warning
4. Continue to trigger critical threshold
5. Verify signal emitted
6. Check cooldown prevents repeated signals

```python
async def test_resource_monitoring():
    monitor = ResourceMonitorService(
        budget=test_budget,
        db_path=test_db,
        time_service=time_service
    )

    await monitor.start()
    await asyncio.sleep(1.1)  # Wait for first update

    # Check snapshot populated
    assert monitor.snapshot.memory_mb > 0
    assert monitor.snapshot.cpu_percent >= 0

    # Record tokens
    await monitor.record_tokens(1000)
    await asyncio.sleep(1.1)  # Wait for update

    assert monitor.snapshot.tokens_used_hour == 1000
```

## Configuration

### Update Interval
- Fixed at 1 second (BaseScheduledService)
- Not configurable to ensure timely limit enforcement

### History Retention
- CPU: 60 samples (1 minute)
- Tokens: 86400 samples (24 hours)
- Both use `collections.deque` with maxlen

### Resource Limits Structure
```python
ResourceLimit:
    limit: int           # Hard limit
    warning: int         # Warning threshold (e.g., 75%)
    critical: int        # Critical threshold (e.g., 90%)
    action: ResourceAction  # What to do when exceeded
    cooldown_seconds: int   # Prevent action spam
```

## Known Limitations

1. **No Persistence**: History lost on restart
2. **Single Process**: Only monitors CIRIS process, not system-wide
3. **No Prediction**: Reactive only, no predictive warnings
4. **Fixed Interval**: 1-second granularity may miss spikes
5. **No Aggregation**: No roll-ups or summaries

## Future Enhancements

1. **Persistent History**: Store in time-series database
2. **System-Wide Monitoring**: Track total system resources
3. **Predictive Alerts**: ML-based resource prediction
4. **Custom Intervals**: Configurable monitoring frequency
5. **Resource Quotas**: Per-user or per-handler limits
6. **Cost Tracking**: Monitor cloud resource costs

## Integration Points

- **TimeService**: Provides consistent timestamps
- **Database**: Queries active thoughts count
- **Signal Bus**: Emits resource events to subscribers
- **All Services**: Can check resource availability
- **LLM Services**: Report token usage

## Monitoring Recommendations

1. **Alert on Critical**: Any critical threshold hit
2. **Track Warning Frequency**: Repeated warnings indicate issues
3. **Monitor Signal Emissions**: Track throttle/defer/reject rates
4. **Watch Token Burn Rate**: Alert on unusual token usage
5. **Memory Leak Detection**: Alert on continuous memory growth

## Performance Considerations

1. **Database Query**: Thoughts count queries DB every second
2. **CPU Sampling**: `cpu_percent(interval=0)` may be inaccurate
3. **Memory Overhead**: Token history can use ~10MB RAM
4. **Signal Handler Cost**: Synchronous handlers block monitoring
5. **No Caching**: Snapshot recalculated every second

## System Integration

The Resource Monitor is critical for system stability:
- Prevents OOM by monitoring memory
- Prevents API rate limit violations via token tracking
- Enables graceful degradation via signals
- Provides health status for load balancers

It acts as the "autonomic nervous system" of CIRIS, maintaining homeostasis without conscious intervention.
