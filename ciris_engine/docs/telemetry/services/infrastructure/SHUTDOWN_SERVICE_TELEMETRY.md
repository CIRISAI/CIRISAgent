# Shutdown Service Telemetry

## Overview
The Shutdown Service provides graceful shutdown coordination across the CIRIS system. It manages shutdown requests, handler registration, emergency shutdown capabilities, and ensures proper system termination. As a critical infrastructure service, it maintains minimal telemetry focused on shutdown readiness and handler management.

## Telemetry Data Collected

| Metric Name | Type | Storage | Update Frequency | Access Method |
|------------|------|---------|------------------|---------------|
| shutdown_requested | boolean | in-memory flag | on state change | `_collect_custom_metrics()` |
| registered_handlers | counter | calculated | real-time | `_collect_custom_metrics()` |
| emergency_mode | boolean | in-memory flag | on emergency | `_collect_custom_metrics()` |
| uptime_seconds | gauge | calculated | on request | inherited from BaseService |
| request_count | counter | in-memory counter | per method call | inherited from BaseService |
| error_count | counter | in-memory counter | on error | inherited from BaseService |
| error_rate | ratio | calculated | on request | inherited from BaseService |
| healthy | boolean | service state | on health check | inherited from BaseService |
| availability | ratio | uptime-based | on request | inherited from BaseInfrastructureService |

## Data Structures

### Shutdown State
```python
{
    "shutdown_requested": false,        # Whether shutdown has been requested
    "shutdown_reason": null,            # Reason for shutdown (if requested)
    "registered_handlers": 5,           # Total sync + async handlers registered
    "emergency_mode": false,            # Whether in emergency shutdown mode
    "handler_types": {
        "sync_handlers": 3,             # Number of sync handlers
        "async_handlers": 2             # Number of async handlers
    }
}
```

### Shutdown Handler Registry
```python
{
    "total_handlers": 5,
    "sync_handlers": [
        {"name": "cleanup_temp_files", "registered_at": "2025-08-14T13:00:00Z"},
        {"name": "save_state", "registered_at": "2025-08-14T13:01:00Z"}
    ],
    "async_handlers": [
        {"name": "graceful_connection_close", "registered_at": "2025-08-14T13:02:00Z"},
        {"name": "persist_final_data", "registered_at": "2025-08-14T13:03:00Z"}
    ]
}
```

### Emergency Shutdown Status
```python
{
    "command_received": "2025-08-14T13:30:00Z",
    "command_verified": true,
    "verification_error": null,
    "shutdown_initiated": "2025-08-14T13:30:01Z",
    "services_stopped": ["memory", "llm", "communication"],
    "data_persisted": true,
    "final_message_sent": true,
    "shutdown_completed": null,
    "exit_code": null
}
```

### Shutdown Metrics Snapshot
```python
{
    "shutdown_requested": 0.0,          # 1.0 if requested, 0.0 if not
    "registered_handlers": 5.0,         # Total handler count
    "emergency_mode": 0.0,              # 1.0 if emergency, 0.0 if normal
    "uptime_seconds": 3600.0,           # Service uptime
    "request_count": 1.0,               # Method calls
    "error_count": 0.0,                 # Error count
    "error_rate": 0.0,                  # Errors per request
    "healthy": 1.0,                     # Health status
    "availability": 1.0                 # Availability ratio
}
```

## API Access Patterns

### Current Access
- **No Direct API**: Shutdown metrics not exposed via REST
- **Internal Access**: Other services can access via dependency injection
- **Emergency API**: `/emergency/shutdown` for WA-authorized emergency shutdown

### Recommended Endpoints

#### Get Shutdown Status
```
GET /v1/telemetry/services/shutdown/status
```
Returns current shutdown service state:
```json
{
    "service_name": "ShutdownService",
    "service_type": "shutdown",
    "is_healthy": true,
    "uptime_seconds": 3600,
    "shutdown_state": {
        "requested": false,
        "reason": null,
        "emergency_mode": false,
        "handlers_registered": 5
    },
    "metrics": {
        "shutdown_requested": 0.0,
        "registered_handlers": 5.0,
        "emergency_mode": 0.0,
        "availability": 1.0
    }
}
```

#### Get Handler Registry
```
GET /v1/telemetry/services/shutdown/handlers
```
Returns registered shutdown handlers:
```json
{
    "total_handlers": 5,
    "sync_handlers": 3,
    "async_handlers": 2,
    "handler_details": [
        {
            "name": "cleanup_temp_files",
            "type": "sync",
            "registered_at": "2025-08-14T13:00:00Z"
        },
        {
            "name": "graceful_connection_close",
            "type": "async",
            "registered_at": "2025-08-14T13:02:00Z"
        }
    ]
}
```

#### Check Shutdown Readiness
```
GET /v1/telemetry/services/shutdown/readiness
```
Returns system shutdown readiness:
```json
{
    "ready_for_shutdown": true,
    "registered_handlers": 5,
    "dependencies_check": true,
    "active_processes": 0,
    "estimated_shutdown_time_ms": 2000,
    "blockers": []
}
```

## Example Usage

### Get Current Status
```python
shutdown_service = get_service(ServiceType.SHUTDOWN)
status = shutdown_service.get_status()

print(f"Shutdown requested: {shutdown_service.is_shutdown_requested()}")
print(f"Shutdown reason: {shutdown_service.get_shutdown_reason()}")
print(f"Handlers registered: {status.metrics.get('registered_handlers', 0)}")
```

### Monitor Shutdown State
```python
# Get metrics
metrics = shutdown_service._collect_custom_metrics()
if metrics.get('shutdown_requested', 0.0) > 0:
    logger.warning("Shutdown has been requested")

if metrics.get('emergency_mode', 0.0) > 0:
    logger.critical("System is in emergency shutdown mode")
```

### Register Shutdown Handler
```python
def cleanup_handler():
    logger.info("Performing cleanup during shutdown")
    # Cleanup logic here

shutdown_service.register_shutdown_handler(cleanup_handler)

# Check handler count
metrics = shutdown_service._collect_custom_metrics()
handler_count = int(metrics.get('registered_handlers', 0))
logger.info(f"Total handlers registered: {handler_count}")
```

### Wait for Shutdown
```python
# Async wait
await shutdown_service.wait_for_shutdown_async()
logger.info("Shutdown signal received")

# Sync wait (blocking)
shutdown_service.wait_for_shutdown()
logger.info("Shutdown signal received")
```

## Emergency Shutdown Integration

### Ed25519 Signature Verification
The emergency shutdown endpoint (`/emergency/shutdown`) accepts WA-signed commands with Ed25519 signatures:

```python
# Command validation flow (handled by RuntimeControl service)
command = WASignedCommand(
    command_id="emergency_001",
    command_type="SHUTDOWN_NOW",
    wa_id="root_authority",
    wa_public_key="base64_ed25519_key",
    issued_at=datetime.utcnow(),
    reason="Critical security issue detected",
    signature="base64_signature"
)

# Signature verification and emergency shutdown telemetry
status = await runtime_service.handle_emergency_command(command)
```

### Emergency Shutdown Metrics
During emergency shutdown, additional telemetry is collected:
- Command verification status
- Handler execution timing
- Service stop progression
- Data persistence confirmation
- Force termination triggers

## Testing

### Test Files
- `tests/ciris_engine/logic/services/lifecycle/test_shutdown_service.py`
- `tests/integration/test_emergency_shutdown.py`

### Validation Steps
1. Start shutdown service
2. Register test handlers
3. Verify handler count in metrics
4. Request shutdown with reason
5. Check shutdown state flags
6. Verify handler execution
7. Test emergency shutdown path

```python
async def test_shutdown_telemetry():
    service = ShutdownService()
    await service.start()

    # Register handlers
    def sync_handler():
        pass

    async def async_handler():
        pass

    service.register_shutdown_handler(sync_handler)
    service._register_async_shutdown_handler(async_handler)

    # Check metrics
    metrics = service._collect_custom_metrics()
    assert metrics['registered_handlers'] == 2.0
    assert metrics['shutdown_requested'] == 0.0

    # Request shutdown
    await service.request_shutdown("Test shutdown")

    # Verify state change
    metrics = service._collect_custom_metrics()
    assert metrics['shutdown_requested'] == 1.0
    assert service.get_shutdown_reason() == "Test shutdown"
```

## Configuration

### Shutdown Behavior
- **Handler Limit**: No hardcoded limit (memory-bound)
- **Emergency Timeout**: 5 seconds default for emergency shutdown
- **Force Kill**: SIGKILL after timeout in emergency mode
- **Handler Execution**: Sync handlers first, then async with timeout

### Emergency Shutdown Settings
```python
emergency_config = {
    "timeout_seconds": 5,           # Grace period before force kill
    "max_handler_time_ms": 2500,    # Half timeout for handlers
    "allow_force_kill": True,       # Enable SIGKILL fallback
    "log_execution_times": True     # Log handler performance
}
```

## Known Limitations

1. **No Handler Metrics**: Individual handler execution times not tracked
2. **No Persistence**: Shutdown history lost on restart
3. **Limited Emergency Telemetry**: Emergency shutdown metrics not persisted
4. **No Handler Validation**: No checks for handler reliability or timeout
5. **Synchronous Logging**: Handler errors logged synchronously during shutdown

## Future Enhancements

1. **Handler Performance Tracking**: Measure individual handler execution times
2. **Shutdown History**: Persist shutdown events and reasons
3. **Handler Health Checks**: Validate handlers before shutdown
4. **Shutdown Simulation**: Dry-run capability for testing
5. **Progressive Shutdown**: Staged shutdown with configurable timeouts
6. **Shutdown Metrics Persistence**: Store emergency shutdown telemetry

## Integration Points

- **RuntimeControlBus**: Receives emergency shutdown commands
- **All Services**: Register shutdown handlers via dependency injection
- **Emergency API**: Provides WA-authorized emergency shutdown endpoint
- **AuditService**: Logs shutdown events and reasons
- **TimeService**: Provides consistent timestamps (when available)

## Monitoring Recommendations

1. **Alert on Shutdown Request**: Immediate notification when shutdown requested
2. **Monitor Handler Count**: Alert on unusual handler registration patterns
3. **Emergency Mode Detection**: Critical alert when emergency mode activated
4. **Handler Execution Time**: Track shutdown duration for performance
5. **Failed Handler Detection**: Alert on handler execution errors

## Performance Considerations

1. **Handler Execution Order**: Sync handlers execute before async
2. **Emergency Timeout**: Fast timeout to prevent hanging in emergency mode
3. **Thread Safety**: All state changes protected by threading.Lock
4. **Memory Usage**: Handler list grows with registrations (no cleanup until shutdown)
5. **Blocking Operations**: `wait_for_shutdown()` blocks calling thread

## System Integration

The Shutdown Service is the final coordination point for system termination:
- Ensures all services can clean up properly
- Provides emergency override for security situations
- Maintains system integrity during shutdown process
- Enables external monitoring of shutdown readiness

It acts as the "last responder" in the CIRIS lifecycle, ensuring graceful termination under both normal and emergency conditions while maintaining audit trails and operational visibility.

## Security Considerations

### Ed25519 Emergency Shutdown
- Only WA-authorized keys can trigger emergency shutdown
- Commands must be issued within 5-minute window
- Signature verification prevents unauthorized termination
- All emergency commands are audit logged

### Handler Security
- No validation of handler code quality or safety
- Handlers run with full service privileges
- Error in handlers don't prevent shutdown completion
- Handlers should implement their own timeout logic
