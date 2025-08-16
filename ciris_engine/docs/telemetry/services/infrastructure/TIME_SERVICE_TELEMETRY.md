# Time Service Telemetry

## Overview
The Time Service provides centralized time operations across the CIRIS system. It ensures all services use consistent UTC time operations, supports test mocking, and prevents direct `datetime.now()` usage. As a critical infrastructure service, it provides basic telemetry through the inherited BaseService metrics framework and maintains uptime tracking.

## Telemetry Data Collected

| Metric Name | Type | Storage | Update Frequency | Access Method |
|------------|------|---------|------------------|---------------|
| uptime_seconds | gauge | in-memory calculation | on request | `get_status().metrics["uptime_seconds"]` |
| request_count | counter | in-memory | per service call | `get_status().metrics["request_count"]` |
| error_count | counter | in-memory | per error | `get_status().metrics["error_count"]` |
| error_rate | gauge | in-memory calculation | on request | `get_status().metrics["error_rate"]` |
| healthy | gauge | in-memory | on request | `get_status().metrics["healthy"]` |
| availability | gauge | in-memory calculation | on request | `get_status().metrics["availability"]` |
| service_uptime | gauge | in-memory calculation | on request | `get_uptime()` |
| start_time | timestamp | in-memory | at service start | `_start_time` (internal) |
| calls_served | counter | schema-defined | per operation | TimeServiceStatus.calls_served |

## Data Structures

### ServiceStatus (Inherited)
```python
{
    "service_name": "TimeService",           # Service identifier
    "service_type": "time",                  # Service type enum
    "is_healthy": true,                      # Health status
    "uptime_seconds": 3661.45,              # Time since start
    "metrics": {                             # Performance metrics
        "uptime_seconds": 3661.45,
        "request_count": 15420.0,
        "error_count": 0.0,
        "error_rate": 0.0,
        "healthy": 1.0,
        "availability": 1.0
    },
    "last_error": null,                      # Last error message
    "last_health_check": "2025-08-14T13:30:00Z"  # Last health check timestamp
}
```

### TimeSnapshot (Schema-Defined)
```python
{
    "current_time": "2025-08-14T13:30:00+00:00",    # Current UTC datetime
    "current_iso": "2025-08-14T13:30:00+00:00",     # ISO format string
    "current_timestamp": 1723643400.0,               # Unix timestamp
    "is_mocked": false,                              # Whether time is mocked
    "mock_time": null                                # Mock time if set
}
```

### TimeServiceStatus (Extended Schema)
```python
{
    "service_name": "TimeService",           # Service name
    "is_healthy": true,                      # Health status
    "uptime_seconds": 3661.45,              # Service uptime
    "is_mocked": false,                      # Mock status
    "calls_served": 15420                    # Total operations served
}
```

### ServiceCapabilities
```python
{
    "service_name": "TimeService",
    "actions": ["now", "now_iso", "timestamp"],     # Available operations
    "version": "1.0.0",                             # Service version
    "dependencies": [],                              # No dependencies
    "metadata": {
        "service_name": "TimeService",
        "method_name": "_get_metadata",
        "correlation_id": "550e8400-e29b-41d4-a716-446655440000",
        "category": "infrastructure",
        "critical": true,
        "description": "Provides consistent UTC time operations"
    }
}
```

## API Access Patterns

### Current Access
- **No Direct API**: Time service metrics not exposed via REST endpoints
- **Internal Access**: Other services access via dependency injection
- **Protocol Methods**: Direct access to `now()`, `now_iso()`, `timestamp()`, `get_uptime()`
- **Status Access**: Via `get_status()` method for monitoring

### Recommended Endpoints

#### Get Time Service Status
```
GET /v1/telemetry/time/status
```
Returns current service status with metrics:
```json
{
    "service_name": "TimeService",
    "service_type": "time",
    "is_healthy": true,
    "uptime_seconds": 3661.45,
    "metrics": {
        "uptime_seconds": 3661.45,
        "request_count": 15420.0,
        "error_count": 0.0,
        "error_rate": 0.0,
        "healthy": 1.0,
        "availability": 1.0
    },
    "last_error": null,
    "last_health_check": "2025-08-14T13:30:00Z"
}
```

#### Get Time Snapshot
```
GET /v1/telemetry/time/snapshot
```
Returns current time information:
```json
{
    "current_time": "2025-08-14T13:30:00+00:00",
    "current_iso": "2025-08-14T13:30:00+00:00",
    "current_timestamp": 1723643400.0,
    "is_mocked": false,
    "mock_time": null
}
```

#### Get Service Capabilities
```
GET /v1/telemetry/time/capabilities
```
Returns service capabilities and metadata:
```json
{
    "service_name": "TimeService",
    "actions": ["now", "now_iso", "timestamp"],
    "version": "1.0.0",
    "dependencies": [],
    "metadata": {
        "category": "infrastructure",
        "critical": true,
        "description": "Provides consistent UTC time operations"
    }
}
```

## Graph Storage

The Time Service does **NOT** use graph storage for telemetry. All metrics are:
- **In-memory only**: Calculated on demand from internal state
- **Stateless**: No persistent telemetry storage
- **Ephemeral**: Lost on service restart

Unlike other services that use `memorize_metric()`, the Time Service relies entirely on inherited BaseService metrics collection.

## Example Usage

### Get Current Time Operations
```python
time_service = get_service(ServiceType.TIME)

# Get current time
now = time_service.now()
print(f"Current time: {now}")

# Get ISO format
iso_time = time_service.now_iso()
print(f"ISO format: {iso_time}")

# Get Unix timestamp
timestamp = time_service.timestamp()
print(f"Timestamp: {timestamp}")

# Get service uptime
uptime = time_service.get_uptime()
print(f"Service uptime: {uptime} seconds")
```

### Check Service Health
```python
# Check if service is healthy
is_healthy = await time_service.is_healthy()
print(f"Time service healthy: {is_healthy}")

# Get full status
status = time_service.get_status()
print(f"Uptime: {status.uptime_seconds} seconds")
print(f"Error rate: {status.metrics['error_rate']}")
```

### Access Service Capabilities
```python
# Get service capabilities
capabilities = time_service.get_capabilities()
print(f"Available actions: {capabilities.actions}")
print(f"Dependencies: {capabilities.dependencies}")  # Empty list
print(f"Version: {capabilities.version}")
```

### Monitor Service Metrics
```python
# Access metrics from status
status = time_service.get_status()
metrics = status.metrics

print(f"Requests served: {metrics['request_count']}")
print(f"Errors encountered: {metrics['error_count']}")
print(f"Availability: {metrics['availability']}")
print(f"Health status: {metrics['healthy']}")
```

## Testing

### Test Files
- `tests/ciris_engine/logic/services/lifecycle/test_time_service.py`
- Test coverage includes lifecycle, consistency, mocking, and metrics

### Validation Steps
1. Start Time Service
2. Verify time operations return consistent UTC times
3. Check service status and metrics
4. Validate uptime calculation
5. Test time mocking for deterministic tests
6. Verify capability reporting

```python
async def test_time_service_telemetry():
    service = TimeService()

    # Start service
    await service.start()

    # Check initial status
    status = service.get_status()
    assert status.service_name == "TimeService"
    assert status.service_type == "time"
    assert status.is_healthy is True
    assert status.uptime_seconds > 0

    # Verify metrics structure
    metrics = status.metrics
    assert "uptime_seconds" in metrics
    assert "request_count" in metrics
    assert "error_count" in metrics
    assert "error_rate" in metrics
    assert "healthy" in metrics
    assert "availability" in metrics

    # Check capabilities
    capabilities = service.get_capabilities()
    assert "now" in capabilities.actions
    assert "now_iso" in capabilities.actions
    assert "timestamp" in capabilities.actions
    assert len(capabilities.dependencies) == 0
```

## Configuration

### Time Service Config (Schema-Defined)
```python
TimeServiceConfig:
    enable_mocking: bool = True      # Allow time mocking for tests
    default_timezone: str = "UTC"    # Always UTC for CIRIS
```

### Service Initialization
- **No dependencies**: Standalone service
- **No external configuration**: Uses hardcoded UTC operations
- **Version**: Fixed at "1.0.0"
- **Service type**: ServiceType.TIME

## Known Limitations

1. **No Historical Data**: No time-series storage of metrics
2. **No Request Tracking**: Base class request counting not utilized
3. **No Operation Metrics**: Individual operation (now/iso/timestamp) metrics not tracked
4. **Memory Only**: All telemetry lost on restart
5. **No Clock Skew Detection**: No monitoring for system clock drift
6. **No Time Zone Support**: Hardcoded to UTC only
7. **No Performance Timing**: No latency metrics for time operations

## Future Enhancements

1. **Operation Metrics**: Track individual method call counts and latencies
2. **Clock Monitoring**: Detect system clock drift and NTP synchronization
3. **Performance Tracking**: Monitor time operation performance
4. **Request Classification**: Track time requests by calling service
5. **Historical Storage**: Store uptime and availability metrics
6. **Alert Integration**: Notify on time service unavailability
7. **Precision Tracking**: Monitor microsecond precision capabilities

## Integration Points

- **All Services**: Every service depends on TimeService for consistent timestamps
- **BaseService**: Inherits standard telemetry framework
- **Testing Framework**: Provides mockable time for deterministic tests
- **Service Registry**: Registered as critical infrastructure service
- **Health Checks**: Part of system health monitoring

## Monitoring Recommendations

1. **Availability Alerts**: Alert immediately if Time Service becomes unhealthy
2. **Uptime Tracking**: Monitor continuous availability (target: 99.9%+)
3. **Startup Monitoring**: Track service restart frequency
4. **System Clock**: Monitor host system time synchronization
5. **Dependency Impact**: Monitor effects when Time Service is unavailable

## Performance Considerations

1. **Minimal Overhead**: Direct `datetime.now()` calls with UTC timezone
2. **No Caching**: Fresh time on every call (intentional for accuracy)
3. **Thread Safety**: All operations are thread-safe
4. **Memory Footprint**: Minimal state (only start time and metrics)
5. **CPU Impact**: Negligible - direct system calls only

## System Integration

The Time Service serves as the temporal foundation for CIRIS:
- **Consistency**: Ensures all timestamps across the system are UTC
- **Testability**: Enables deterministic testing via time mocking
- **Auditability**: Provides reliable timestamps for audit trails
- **Dependency-Free**: No external dependencies ensure high availability

It acts as the "heartbeat" of CIRIS, providing the temporal substrate upon which all other services depend for consistent, auditable operations.

## Critical Design Notes

1. **Self-Bootstrapping**: TimeService overrides `_now()` to avoid circular dependency
2. **UTC Only**: Hardcoded timezone prevents configuration errors
3. **Mock Support**: Built-in support for deterministic testing
4. **Zero Dependencies**: Ensures this critical service can always start
5. **Minimal State**: Only tracks service start time and inherited metrics
