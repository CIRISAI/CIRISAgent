# Runtime Control Service Telemetry

## Overview
The Runtime Control Service manages processor control, adapter lifecycle, configuration operations, and service health monitoring. It provides comprehensive telemetry for runtime operations, emergency shutdown handling, service registry interactions, and system-wide health status. The service acts as the primary control plane for the CIRIS runtime system, tracking operational events, processor state changes, and adapter management operations.

## Telemetry Data Collected

| Metric Name | Type | Storage | Update Frequency | Access Method |
|------------|------|---------|------------------|---------------|
| events_count | gauge | in-memory list | per operation | `_collect_custom_metrics()` |
| processor_status | gauge | service state | state changes | `_collect_custom_metrics()` |
| adapters_loaded | gauge | adapter manager | adapter operations | `_collect_custom_metrics()` |
| uptime_seconds | gauge | inherited from BaseService | continuous | `_calculate_uptime()` |
| request_count | counter | inherited from BaseService | per request | `_track_request()` |
| error_count | counter | inherited from BaseService | per error | `_track_error()` |
| error_rate | gauge | inherited from BaseService | calculated | `error_count / request_count` |
| healthy | boolean | inherited from BaseService | per status check | `is_healthy()` |
| processor_queue_size | gauge | agent processor | per query | `get_processor_queue_status()` |
| processor_queue_rate | gauge | agent processor calculations | per query | `get_processor_queue_status()` |
| processor_latency_ms | gauge | agent processor calculations | per query | `get_processor_queue_status()` |
| config_changes_count | counter | configuration operations | per config update | `update_config()` |
| emergency_shutdown_events | counter | WA command handling | per emergency event | `handle_emergency_shutdown()` |
| circuit_breaker_resets | counter | service management | per reset operation | `reset_circuit_breakers()` |
| service_priority_updates | counter | service management | per priority change | `update_service_priority()` |
| runtime_events_history | array | in-memory events list | per event | `_record_event()` |
| kill_switch_configured | boolean | kill switch configuration | configuration time | `_configure_kill_switch()` |
| wa_keys_count | gauge | WA public key management | key configuration | `_configure_kill_switch()` |
| healthy_services_count | gauge | service health monitoring | per health check | `get_service_health_status()` |
| unhealthy_services_count | gauge | service health monitoring | per health check | `get_service_health_status()` |
| adapter_bootstrap_count | gauge | adapter lifecycle | adapter enumeration | `list_adapters()` |
| config_backup_operations | counter | configuration management | per backup operation | `backup_config()` |
| config_restore_operations | counter | configuration management | per restore operation | `restore_config()` |
| signature_verification_attempts | counter | WA security | per verification | `_verify_wa_signature()` |
| signature_verification_failures | counter | WA security | per failed verification | `_verify_wa_signature()` |

## Data Structures

### RuntimeEvent
```python
{
    "event_type": "processor_control:single_step",  # Operation category:action
    "timestamp": "2025-08-14T13:30:00Z",           # Event timestamp
    "source": "RuntimeControlService",              # Event source
    "details": {                                    # Event-specific details
        "success": true,
        "result": {...},                            # Operation result data
        "error": null                               # Error message if failed
    },
    "severity": "info"                             # Event severity level
}
```

### ProcessorQueueStatus
```python
{
    "processor_name": "agent",                      # Processor identifier
    "queue_size": 15,                              # Current queue depth
    "max_size": 1000,                             # Maximum queue capacity
    "processing_rate": 2.5,                       # Items per second
    "average_latency_ms": 450.0,                  # Average processing time
    "oldest_message_age_seconds": 12.3            # Age of oldest queued item
}
```

### AdapterInfo
```python
{
    "adapter_id": "discord_bootstrap",              # Adapter identifier
    "adapter_type": "discord",                     # Adapter type
    "status": "running",                           # Current status
    "started_at": "2025-08-14T10:00:00Z",         # Start timestamp
    "messages_processed": 1250,                   # Total messages handled
    "error_count": 3,                             # Error count
    "last_error": null,                           # Last error message
    "tools": [                                    # Available tools
        {
            "name": "discord_send",
            "description": "Send Discord message",
            "schema": {...}                        # Tool schema
        }
    ]
}
```

### ServiceHealthStatus
```python
{
    "overall_health": "healthy",                   # healthy|degraded|unhealthy
    "timestamp": "2025-08-14T13:30:00Z",          # Health check timestamp
    "healthy_services": 18,                       # Number of healthy services
    "unhealthy_services": 2,                      # Number of unhealthy services
    "service_details": {                          # Per-service health details
        "direct.runtime.LLMService": {
            "healthy": true,
            "circuit_breaker_state": "closed",
            "priority": "DIRECT",
            "priority_group": -1,
            "strategy": "DIRECT"
        },
        "registry.memory.Neo4jMemoryService": {
            "healthy": false,
            "circuit_breaker_state": "open",
            "priority": "HIGH",
            "priority_group": 0,
            "strategy": "FALLBACK",
            "error": "Connection timeout"
        }
    },
    "recommendations": [                          # Health improvement suggestions
        "Consider resetting circuit breakers",
        "Check service logs for details"
    ]
}
```

### RuntimeStatusResponse
```python
{
    "is_running": true,                           # Runtime operational status
    "uptime_seconds": 86400.0,                   # System uptime
    "processor_count": 1,                        # Number of processors
    "adapter_count": 3,                          # Number of adapters
    "total_messages_processed": 15000,           # Total processed messages
    "current_load": 0.65                         # System load factor
}
```

### EmergencyShutdownStatus
```python
{
    "command_received": "2025-08-14T13:30:00Z",   # Command receipt time
    "command_verified": true,                     # Signature verification result
    "verification_error": null,                  # Verification error if any
    "shutdown_initiated": "2025-08-14T13:30:01Z", # Shutdown start time
    "data_persisted": true,                      # Data persistence status
    "final_message_sent": true,                  # Final message sent status
    "shutdown_completed": "2025-08-14T13:30:05Z", # Shutdown completion time
    "exit_code": 0                               # Process exit code
}
```

### CircuitBreakerStatus
```python
{
    "state": "closed",                           # closed|open|half_open
    "failure_count": 0,                          # Current failure count
    "service_name": "registry.llm.OpenAIClient", # Service identifier
    "trip_threshold": 5,                         # Failure threshold
    "reset_timeout_seconds": 60.0               # Reset timeout
}
```

## API Access Patterns

### Current Access
- **Internal Service Access**: Via dependency injection and service registry
- **Telemetry Integration**: Records runtime events to TelemetryService when available
- **Event History**: Maintains in-memory history of runtime events (limited to 1000 entries)
- **Health Monitoring**: Continuous service health assessment and circuit breaker monitoring

### Recommended Endpoints

#### Get Runtime Control Service Status
```
GET /v1/telemetry/runtime-control/status
```
Returns comprehensive service status:
```json
{
    "service_name": "RuntimeControlService",
    "service_type": "CORE",
    "is_healthy": true,
    "uptime_seconds": 86400.0,
    "events_count": 245,
    "processor_status": "running",
    "adapters_loaded": 3,
    "last_config_change": "2025-08-14T12:00:00Z",
    "configuration": {
        "kill_switch_enabled": true,
        "wa_keys_configured": 2,
        "event_history_limit": 1000
    }
}
```

#### Get Processor Control Metrics
```
GET /v1/telemetry/runtime-control/processor
```
Returns processor control telemetry:
```json
{
    "processor_name": "agent",
    "status": "running",
    "queue_status": {
        "queue_size": 15,
        "max_size": 1000,
        "processing_rate": 2.5,
        "average_latency_ms": 450.0,
        "oldest_message_age_seconds": 12.3
    },
    "control_operations": {
        "single_steps_executed": 150,
        "pause_resume_cycles": 5,
        "emergency_stops": 0,
        "state_transitions": 45
    },
    "performance": {
        "uptime_seconds": 86400.0,
        "success_rate": 0.996,
        "average_response_time_ms": 125.0
    }
}
```

#### Get Adapter Management Metrics
```
GET /v1/telemetry/runtime-control/adapters
```
Query parameters:
- `adapter_type`: Filter by adapter type
- `status`: Filter by adapter status

Returns adapter management telemetry:
```json
{
    "total_adapters": 3,
    "adapters_by_type": {
        "discord": 1,
        "api": 1,
        "cli": 1
    },
    "adapters_by_status": {
        "running": 3,
        "stopped": 0,
        "error": 0
    },
    "operations": {
        "load_operations": 3,
        "unload_operations": 0,
        "failed_operations": 0,
        "bootstrap_adapters": 1
    },
    "adapters": [
        {
            "adapter_id": "discord_bootstrap",
            "adapter_type": "discord",
            "status": "running",
            "uptime_seconds": 86400.0,
            "messages_processed": 1250,
            "error_count": 3,
            "tools_count": 5
        }
    ]
}
```

#### Get Service Health Metrics
```
GET /v1/telemetry/runtime-control/health
```
Returns service health monitoring data:
```json
{
    "overall_health": "healthy",
    "timestamp": "2025-08-14T13:30:00Z",
    "service_counts": {
        "total_services": 24,
        "healthy_services": 22,
        "unhealthy_services": 2,
        "direct_services": 21,
        "registry_services": 3
    },
    "circuit_breaker_summary": {
        "closed": 20,
        "open": 2,
        "half_open": 0
    },
    "health_trends": {
        "health_checks_performed": 500,
        "health_degradations": 5,
        "recovery_events": 3
    },
    "recommendations": [
        "Consider resetting circuit breakers for failed services",
        "Check service logs for error details"
    ]
}
```

#### Get Configuration Management Metrics
```
GET /v1/telemetry/runtime-control/config
```
Returns configuration operation telemetry:
```json
{
    "config_version": "1.0.0",
    "last_config_change": "2025-08-14T12:00:00Z",
    "operations": {
        "config_updates": 15,
        "config_backups": 3,
        "config_restores": 1,
        "validation_operations": 20,
        "failed_operations": 1
    },
    "backup_summary": {
        "total_backups": 3,
        "total_size_bytes": 1024000,
        "oldest_backup": "2025-08-10T09:00:00Z",
        "newest_backup": "2025-08-14T08:00:00Z"
    },
    "validation_summary": {
        "syntax_validations": 15,
        "schema_validations": 5,
        "validation_errors": 2,
        "validation_warnings": 8
    }
}
```

#### Get Emergency Operations Metrics
```
GET /v1/telemetry/runtime-control/emergency
```
Returns emergency shutdown and security metrics:
```json
{
    "kill_switch": {
        "enabled": true,
        "configured_keys": 2,
        "trust_tree_depth": 3,
        "allow_relay": true,
        "max_shutdown_time_ms": 30000
    },
    "emergency_events": {
        "shutdown_commands_received": 0,
        "shutdown_commands_verified": 0,
        "shutdown_commands_rejected": 0,
        "emergency_stops": 0,
        "signature_verifications": 0,
        "signature_failures": 0
    },
    "security_metrics": {
        "wa_keys_configured": 2,
        "signature_algorithm": "Ed25519",
        "command_expiry_seconds": 300,
        "audit_logging_enabled": true
    }
}
```

#### Get Runtime Events History
```
GET /v1/telemetry/runtime-control/events
```
Query parameters:
- `limit`: Number of recent events (default: 100, max: 1000)
- `category`: Filter by event category
- `severity`: Filter by severity level

Returns runtime events history:
```json
{
    "events": [
        {
            "event_type": "processor_control:single_step",
            "timestamp": "2025-08-14T13:30:00Z",
            "source": "RuntimeControlService",
            "details": {
                "success": true,
                "processor_name": "agent",
                "operation": "single_step"
            },
            "severity": "info"
        }
    ],
    "total_events": 245,
    "events_by_category": {
        "processor_control": 150,
        "adapter_management": 50,
        "config_management": 30,
        "service_management": 10,
        "emergency_shutdown": 0
    },
    "events_by_severity": {
        "info": 200,
        "warning": 30,
        "error": 15,
        "critical": 0
    }
}
```

## Graph Storage

### Telemetry Service Integration
When `telemetry_service` is available, the Runtime Control service records:
- `runtime_control_operation`: General service operations
- `processor_control_event`: Processor state changes and control operations
- `adapter_lifecycle_event`: Adapter load/unload operations
- `config_operation_event`: Configuration management operations
- `emergency_shutdown_event`: WA-authorized emergency shutdown events
- `service_health_check`: Service health status changes

### Memory Graph Nodes
Runtime telemetry data can be stored as graph nodes via the telemetry service:
```python
# Via TelemetryService.memorize_metric()
{
    "node_type": "metric",
    "metric_name": "runtime_control_event",
    "timestamp": "2025-08-14T13:30:00Z",
    "data": {
        "event_type": "processor_control:single_step",
        "source": "RuntimeControlService",
        "success": true,
        "processor_name": "agent",
        "operation_id": "uuid-1234"
    }
}
```

## Example Usage

### Monitor Processor Control
```python
runtime_control = get_service(ServiceType.RUNTIME_CONTROL)

# Get processor queue status
queue_status = await runtime_control.get_processor_queue_status()
print(f"Queue size: {queue_status.queue_size}")
print(f"Processing rate: {queue_status.processing_rate} items/sec")

# Check if queue is backed up
if queue_status.queue_size > 100:
    logger.warning(f"Processor queue backed up: {queue_status.queue_size} items")
```

### Monitor Adapter Health
```python
# List all adapters and check their status
adapters = await runtime_control.list_adapters()

for adapter in adapters:
    print(f"Adapter {adapter.adapter_id}: {adapter.status}")
    if adapter.error_count > 0:
        logger.warning(f"Adapter {adapter.adapter_id} has {adapter.error_count} errors")
```

### Track Service Health
```python
# Get comprehensive service health status
health_status = await runtime_control.get_service_health_status()

print(f"Overall health: {health_status.overall_health}")
print(f"Healthy services: {health_status.healthy_services}")
print(f"Unhealthy services: {health_status.unhealthy_services}")

# Check for specific service issues
for service_name, details in health_status.service_details.items():
    if not details["healthy"]:
        logger.error(f"Service {service_name} is unhealthy: {details.get('error', 'Unknown error')}")
```

### Monitor Runtime Events
```python
# Get recent runtime events
events = runtime_control.get_events_history(limit=50)

# Count events by type
event_counts = {}
for event in events:
    event_type = event.event_type
    event_counts[event_type] = event_counts.get(event_type, 0) + 1

print("Recent event types:")
for event_type, count in event_counts.items():
    print(f"  {event_type}: {count}")
```

### Check Emergency Shutdown Capability
```python
# Verify kill switch configuration
status = runtime_control.get_status()
metrics = status.metrics

print(f"Emergency shutdown configured: {metrics.get('kill_switch_configured', False)}")
print(f"WA keys configured: {metrics.get('wa_keys_count', 0)}")
```

### Monitor Configuration Changes
```python
# Track configuration operations
if hasattr(runtime_control, '_last_config_change') and runtime_control._last_config_change:
    last_change = runtime_control._last_config_change
    time_since = (runtime_control._now() - last_change).total_seconds()
    print(f"Last config change: {time_since:.1f} seconds ago")
```

## Testing

### Test Files
- `tests/logic/services/runtime/test_runtime_control_service.py`
- `tests/integration/test_runtime_control_operations.py`
- `tests/telemetry/test_runtime_control_telemetry.py`

### Validation Steps
1. Initialize RuntimeControlService with telemetry integration
2. Verify processor control operations and telemetry recording
3. Test adapter lifecycle management and event tracking
4. Validate configuration operations and backup/restore telemetry
5. Test service health monitoring and circuit breaker telemetry
6. Verify emergency shutdown handling and WA signature verification
7. Test runtime event recording and history management

```python
async def test_runtime_control_telemetry():
    # Setup service with telemetry
    telemetry_service = Mock()
    time_service = TimeService()

    runtime_control = RuntimeControlService(
        time_service=time_service
    )

    await runtime_control.start()

    # Test processor control operation
    response = await runtime_control.single_step()

    # Verify event recording
    assert len(runtime_control._events_history) > 0
    last_event = runtime_control._events_history[-1]
    assert last_event.event_type == "processor_control:single_step"
    assert last_event.source == "RuntimeControlService"

    # Test metrics collection
    metrics = runtime_control._collect_custom_metrics()
    assert "events_count" in metrics
    assert "processor_status" in metrics
    assert metrics["events_count"] > 0

    # Test service health monitoring
    health_status = await runtime_control.get_service_health_status()
    assert health_status.overall_health in ["healthy", "degraded", "unhealthy"]
    assert isinstance(health_status.healthy_services, int)
    assert isinstance(health_status.service_details, dict)
```

## Configuration

### Kill Switch Configuration
```python
{
    "enabled": true,                               # Kill switch enabled
    "trust_tree_depth": 3,                       # WA signature trust depth
    "allow_relay": true,                         # Allow relayed commands
    "max_shutdown_time_ms": 30000,               # Maximum shutdown time
    "command_expiry_seconds": 300,               # Command expiry time
    "require_reason": true,                      # Require shutdown reason
    "log_to_audit": true,                        # Audit logging enabled
    "allow_override": false,                     # Allow override commands
    "root_wa_public_keys": [                     # WA public keys
        "-----BEGIN PUBLIC KEY-----...",
        "-----BEGIN PUBLIC KEY-----..."
    ]
}
```

### Event History Configuration
```python
{
    "max_events": 1000,                          # Maximum events to keep
    "event_categories": [                        # Tracked event categories
        "processor_control",
        "adapter_management",
        "config_management",
        "service_management",
        "emergency_shutdown"
    ],
    "severity_levels": [                         # Event severity levels
        "info",
        "warning",
        "error",
        "critical"
    ]
}
```

## Known Limitations

1. **Event History Persistence**: Events are stored in-memory only and lost on restart
2. **Processor Queue Metrics**: Some queue metrics are placeholder values due to processor implementation
3. **Adapter Tool Discovery**: Tool enumeration may fail for some adapter types
4. **Circuit Breaker Details**: Limited circuit breaker state information from service registry
5. **Configuration Validation**: Limited validation capabilities compared to full schema validation
6. **WA Key Management**: No automatic key rotation or expiry handling
7. **Health Check Depth**: Service health checks are basic and may not detect all failure modes
8. **Metric Aggregation**: No built-in metric aggregation over time periods

## Future Enhancements

1. **Persistent Event Storage**: Store runtime events in graph database for historical analysis
2. **Enhanced Processor Metrics**: Real-time queue depth monitoring and processing latencies
3. **Advanced Health Monitoring**: Deep service health checks with dependency analysis
4. **Configuration Versioning**: Full configuration version control and rollback capabilities
5. **Emergency Response Analytics**: Analytics on emergency shutdown patterns and response times
6. **Adapter Performance Tracking**: Detailed adapter performance and resource utilization metrics
7. **Predictive Health Monitoring**: ML-based prediction of service failures and degradations
8. **Real-time Dashboards**: Live telemetry visualization and alerting systems
9. **Multi-tenant Support**: Tenant-specific runtime control and telemetry isolation
10. **Automated Recovery**: Self-healing capabilities based on telemetry patterns

## Integration Points

- **TelemetryService**: Records runtime control events and operations
- **TimeService**: Provides consistent timestamps for all telemetry data
- **AgentProcessor**: Sources for queue status and processor control metrics
- **RuntimeAdapterManager**: Provides adapter lifecycle and status information
- **GraphConfigService**: Sources for configuration operation telemetry
- **ServiceRegistry**: Provides service health and circuit breaker status
- **AuditService**: Records high-level runtime control operations for compliance
- **ShutdownService**: Integration for emergency shutdown coordination
- **WiseAuthority**: Sources for emergency command authorization and validation

## Monitoring Recommendations

1. **Processor Queue Alerts**: Alert when queue size exceeds threshold or processing rate drops
2. **Service Health Monitoring**: Continuous monitoring of service health status with degradation alerts
3. **Circuit Breaker Alerts**: Immediate alerts when circuit breakers open
4. **Emergency Preparedness**: Monitor WA key configuration and signature verification capabilities
5. **Configuration Change Tracking**: Audit all configuration changes with approval workflows
6. **Adapter Stability**: Monitor adapter error rates and automatic restart patterns
7. **Runtime Event Analysis**: Pattern analysis of runtime events for operational insights
8. **Performance Degradation**: Track service response times and processing latencies

## Performance Considerations

1. **Event History Management**: In-memory event storage limited to 1000 entries to prevent memory growth
2. **Service Health Checks**: Health check operations add latency to status requests
3. **Configuration Operations**: Large configuration operations may impact service responsiveness
4. **Circuit Breaker Queries**: Service registry queries for circuit breaker status add overhead
5. **Adapter Enumeration**: Listing adapters with tool discovery can be slow for many adapters
6. **WA Signature Verification**: Cryptographic operations add latency to emergency commands
7. **Telemetry Recording**: Event recording adds minimal overhead but accumulates over time

## System Integration

The Runtime Control Service is the central management hub for CIRIS operations:
- Provides unified control plane for all runtime operations and monitoring
- Implements emergency shutdown capabilities with cryptographic authorization
- Coordinates processor, adapter, and configuration lifecycle management
- Maintains comprehensive operational telemetry for system observability
- Supports both manual operations and automated system management

The service acts as a "mission control center" for CIRIS, ensuring that all runtime operations are properly coordinated, monitored, and secured while maintaining detailed telemetry for operational visibility and system health management.
