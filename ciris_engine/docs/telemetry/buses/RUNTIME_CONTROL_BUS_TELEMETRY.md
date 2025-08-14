# Runtime Control Bus Telemetry

## Overview
The Runtime Control Bus manages all runtime control operations in CIRIS, providing critical system lifecycle management with comprehensive telemetry collection. It coordinates processor control, adapter management, configuration changes, and health monitoring while tracking operational metrics and maintaining system safety through its operation lock mechanism.

## Telemetry Data Collected

### Bus-Level Metrics (RuntimeControlBus)

| Metric Name | Type | Storage | Update Frequency | Access Method |
|------------|------|---------|------------------|---------------|
| active_operations | list | in-memory dict | real-time | `get_runtime_status()` |
| shutting_down | boolean | in-memory | on shutdown | `get_runtime_status()` |
| queue_size | gauge | in-memory | on-demand | `get_stats()` (inherited) |
| processed | counter | in-memory | per-operation | `get_stats()` (inherited) |
| failed | counter | in-memory | on-error | `get_stats()` (inherited) |
| running | boolean | in-memory | state change | `get_stats()` (inherited) |

### Service-Level Metrics (RuntimeControlService)

| Metric Name | Type | Storage | Update Frequency | Access Method |
|------------|------|---------|------------------|---------------|
| events_count | counter | in-memory | per-event | `_collect_custom_metrics()` |
| processor_status | gauge | in-memory | on status change | `_collect_custom_metrics()` |
| adapters_loaded | counter | in-memory | on adapter change | `_collect_custom_metrics()` |
| uptime_seconds | gauge | in-memory | on-demand | base service metrics |
| request_count | counter | in-memory | per-request | base service metrics |
| error_count | counter | in-memory | on-error | base service metrics |
| error_rate | calculated | in-memory | on-demand | base service metrics |
| healthy | boolean | in-memory | on-demand | `is_healthy()` |

### Processor Control Metrics

| Metric Name | Type | Storage | Update Frequency | Access Method |
|------------|------|---------|------------------|---------------|
| processor_queue_size | gauge | real-time | per-query | `get_processor_queue_status()` |
| processing_rate | gauge | real-time | per-query | `get_processor_queue_status()` |
| average_latency_ms | gauge | calculated | per-query | `get_processor_queue_status()` |
| oldest_message_age | gauge | real-time | per-query | `get_processor_queue_status()` |
| pause_resume_operations | counter | events | per-operation | event history |
| single_step_operations | counter | events | per-operation | event history |

### Adapter Management Metrics

| Metric Name | Type | Storage | Update Frequency | Access Method |
|------------|------|---------|------------------|---------------|
| total_adapters | counter | real-time | per-change | `list_adapters()` |
| running_adapters | counter | real-time | per-change | `list_adapters()` |
| failed_adapters | counter | real-time | per-change | `list_adapters()` |
| adapter_load_operations | counter | events | per-operation | event history |
| adapter_unload_operations | counter | events | per-operation | event history |

### Configuration Management Metrics

| Metric Name | Type | Storage | Update Frequency | Access Method |
|------------|------|---------|------------------|---------------|
| config_updates | counter | events | per-update | event history |
| config_backups | counter | events | per-backup | event history |
| config_restores | counter | events | per-restore | event history |
| last_config_change | timestamp | in-memory | on-change | internal |

## Data Structures

### Bus Statistics (from RuntimeControlBus)
```python
{
    "service_type": "RUNTIME_CONTROL",
    "queue_size": 0,                    # Messages waiting for processing
    "processed": 1247,                  # Total operations processed
    "failed": 3,                        # Failed operations count
    "running": true,                    # Bus processing state
    "bus_status": {
        "active_operations": ["pause_processing", "load_adapter"],
        "shutting_down": false
    }
}
```

### Runtime Status (from get_runtime_status)
```python
{
    "is_running": true,
    "uptime_seconds": 3600.5,
    "processor_count": 1,
    "adapter_count": 3,
    "total_messages_processed": 15234,
    "current_load": 0.25,
    "bus_status": {
        "active_operations": [],
        "shutting_down": false
    }
}
```

### Processor Queue Status
```python
{
    "processor_name": "agent",
    "queue_size": 5,                    # Pending thoughts + tasks
    "max_size": 1000,                   # Maximum queue capacity
    "processing_rate": 2.5,             # Operations per second
    "average_latency_ms": 125.3,        # Average processing time
    "oldest_message_age_seconds": 45.2  # Age of oldest queued message
}
```

### Adapter Information
```python
{
    "adapter_id": "discord_main",
    "adapter_type": "discord",
    "status": "RUNNING",               # RUNNING/STOPPED/ERROR
    "started_at": "2025-08-14T13:30:00Z",
    "messages_processed": 1523,
    "error_count": 2,
    "last_error": "Rate limit exceeded",
    "tools": [
        {
            "name": "discord_message",
            "description": "Send Discord message",
            "schema": {...}
        }
    ]
}
```

### Service Metrics (from BaseService)
```python
{
    "uptime_seconds": 3600.5,
    "request_count": 2347.0,
    "error_count": 8.0,
    "error_rate": 0.0034,
    "healthy": 1.0,
    "events_count": 156.0,
    "processor_status": 1.0,            # 1.0 = RUNNING, 0.0 = other
    "adapters_loaded": 3.0
}
```

### Runtime Events History
```python
{
    "event_type": "processor_control:pause",
    "timestamp": "2025-08-14T13:30:00Z",
    "source": "RuntimeControlService",
    "details": {
        "success": true,
        "result": {...}
    },
    "severity": "info"
}
```

## API Access Patterns

### Current Access
- **Internal Only**: Most bus metrics not exposed via API endpoints
- **Service Level**: RuntimeControlService metrics available through service status
- **Partial Exposure**: Some operations tracked in events history

### Recommended Endpoints

#### Runtime Control Overview
```
GET /v1/telemetry/runtime-control/overview
```
Returns comprehensive runtime control metrics:
```json
{
    "bus_status": {
        "queue_size": 0,
        "processed_operations": 1247,
        "failed_operations": 3,
        "active_operations": [],
        "shutting_down": false
    },
    "processor_status": {
        "status": "RUNNING",
        "queue_size": 5,
        "processing_rate": 2.5,
        "average_latency_ms": 125.3
    },
    "adapter_summary": {
        "total_adapters": 3,
        "running_adapters": 2,
        "failed_adapters": 1
    },
    "operation_counts": {
        "pause_resume_ops": 12,
        "single_step_ops": 456,
        "adapter_load_ops": 8,
        "config_update_ops": 23
    }
}
```

#### Processor Telemetry
```
GET /v1/telemetry/runtime-control/processor
```
Returns detailed processor metrics:
```json
{
    "current_status": "RUNNING",
    "queue_status": {
        "queue_size": 5,
        "max_size": 1000,
        "processing_rate": 2.5,
        "average_latency_ms": 125.3,
        "oldest_message_age_seconds": 45.2
    },
    "control_operations": {
        "total_pauses": 8,
        "total_resumes": 8,
        "single_steps": 456,
        "shutdowns": 1
    },
    "cognitive_state_transitions": {
        "WORK": 2340,
        "PLAY": 156,
        "SOLITUDE": 89,
        "DREAM": 23
    }
}
```

#### Adapter Management Telemetry
```
GET /v1/telemetry/runtime-control/adapters
```
Returns adapter management metrics:
```json
{
    "summary": {
        "total_adapters": 3,
        "running_adapters": 2,
        "stopped_adapters": 0,
        "error_adapters": 1
    },
    "adapters": [
        {
            "adapter_id": "discord_main",
            "adapter_type": "discord",
            "status": "RUNNING",
            "uptime_seconds": 3600,
            "messages_processed": 1523,
            "error_count": 2,
            "tools_count": 5
        }
    ],
    "operations": {
        "load_operations": 8,
        "unload_operations": 2,
        "load_failures": 1,
        "unload_failures": 0
    }
}
```

## Graph Storage (via TelemetryService)

### Metric Nodes Created
When TelemetryService is available, the following metric nodes may be created:
- Type: `RUNTIME_EVENT`
- Properties: `event_type`, `timestamp`, `source`, `severity`, `details`

### Event Categories
- `processor_control` - Pause, resume, single-step, shutdown operations
- `adapter_management` - Load, unload, status changes
- `config_management` - Updates, backups, restores
- `service_management` - Priority updates, circuit breaker resets
- `emergency_shutdown` - WA-authorized emergency shutdowns

### Edge Relationships
- `TRIGGERED_BY` - Links events to their trigger source
- `FOLLOWS` - Temporal sequence of operations
- `AFFECTS` - Operation impact relationships

## Example Usage

### Get Bus Statistics
```python
# Within CIRIS codebase
runtime_bus = service_registry.get_service(ServiceType.RUNTIME_CONTROL)
stats = runtime_bus.get_stats()
# Returns dict with queue size, processed count, etc.
```

### Check Processor Queue Status
```python
# Get current processor queue metrics
queue_status = await runtime_bus.get_processor_queue_status()
queue_size = queue_status.queue_size
processing_rate = queue_status.processing_rate
```

### Monitor Active Operations
```python
# Check for ongoing operations (uses operation lock)
status = await runtime_bus.get_runtime_status()
active_ops = status["bus_status"]["active_operations"]
is_shutting_down = status["bus_status"]["shutting_down"]
```

### Get Events History
```python
# Access service directly for events
runtime_service = await runtime_bus.get_service()
events = runtime_service.get_events_history(limit=50)
recent_errors = [e for e in events if e.severity == "error"]
```

## Testing

### Test File
`tests/ciris_engine/logic/buses/test_runtime_control_bus.py` - Comprehensive tests exist

### Validation Steps
1. Perform processor control operation (pause/resume)
2. Verify bus statistics update correctly
3. Check event recording in history
4. Confirm operation lock prevents conflicts
5. Validate shutdown state handling

```python
# Example validation
async def test_runtime_control_metrics():
    runtime_bus = get_service(ServiceType.RUNTIME_CONTROL)

    # Get initial stats
    initial_stats = runtime_bus.get_stats()
    initial_processed = initial_stats["processed"]

    # Perform operation
    result = await runtime_bus.pause_processing()

    # Check metrics updated
    new_stats = runtime_bus.get_stats()
    assert new_stats["processed"] > initial_processed

    # Verify operation was recorded
    status = await runtime_bus.get_runtime_status()
    # Check processor status changed
```

## Configuration

### Operation Priority Levels
```python
{
    "CRITICAL": 0,    # Shutdown, emergency stop
    "HIGH": 1,        # Configuration changes
    "NORMAL": 2,      # Status queries (default)
    "LOW": 3          # Metrics, non-essential ops
}
```

### Bus Settings
```python
{
    "max_queue_size": 1000,        # Maximum queued operations
    "operation_timeout": 30.0,     # Timeout for operations
    "shutdown_timeout": 10.0,      # Grace period for shutdown
    "event_history_limit": 1000    # Maximum stored events
}
```

### Cognitive State Mapping
- **WAKEUP** - Identity confirmation phase
- **WORK** - Normal task processing
- **PLAY** - Creative exploration mode
- **SOLITUDE** - Reflection and analysis
- **DREAM** - Deep introspection
- **SHUTDOWN** - Graceful termination

## Known Limitations

1. **In-Memory Events**: Event history is lost on restart (max 1000 events)
2. **No Operation Metrics**: Individual operation timing not tracked
3. **Limited Queue Analytics**: No queue depth over time analysis
4. **No Cognitive State Timing**: State transition duration not measured
5. **Adapter Metrics Gaps**: Limited adapter performance tracking beyond basic counters
6. **Configuration Change Tracking**: No detailed audit trail for config changes

## Future Enhancements

1. **Persistent Event Store**: Store events in graph for durability and analysis
2. **Operation Timing**: Track latency percentiles for all operations
3. **Queue Analytics**: Monitor queue depth trends and processing patterns
4. **Cognitive State Metrics**: Track time spent in each cognitive state
5. **Advanced Adapter Telemetry**: Detailed performance metrics per adapter
6. **Configuration Audit Trail**: Complete tracking of all configuration changes
7. **Predictive Monitoring**: Detect patterns that predict system issues
8. **Cross-Instance Aggregation**: Aggregate metrics across multiple CIRIS instances

## Integration Points

- **TimeService**: Provides consistent timestamps for all operations
- **ServiceRegistry**: Manages service discovery and health checking
- **AgentProcessor**: Interfaces with cognitive processing queue
- **AdapterManager**: Coordinates adapter lifecycle and metrics
- **ConfigService**: Manages configuration state and changes
- **TelemetryService**: May store detailed metrics in graph when available

## Monitoring Recommendations

1. **Queue Depth Alerts**: Monitor processor queue size for potential bottlenecks
2. **Operation Failure Rates**: Track failed operations ratio
3. **Adapter Health**: Monitor adapter status and error counts
4. **Configuration Changes**: Alert on unexpected configuration modifications
5. **Cognitive State Distribution**: Monitor time spent in each processing state
6. **Emergency Shutdowns**: Immediate alerts for WA-authorized shutdowns
7. **Resource Utilization**: Track adapter and processor resource usage
8. **Bus Throughput**: Monitor operations processed per time period

## Safety and Security Considerations

1. **Operation Lock**: Prevents concurrent critical operations
2. **Shutdown Protection**: Graceful handling of shutdown requests
3. **WA Emergency Commands**: Cryptographically verified emergency shutdowns
4. **Configuration Validation**: Input validation for configuration changes
5. **Adapter Isolation**: Errors in one adapter don't affect others
6. **Event Integrity**: Tamper-evident logging of critical operations
