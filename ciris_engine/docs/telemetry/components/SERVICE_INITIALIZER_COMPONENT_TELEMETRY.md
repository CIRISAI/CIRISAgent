# Service Initializer Component Telemetry

## Overview
The Service Initializer Component is responsible for bootstrapping all 21 core services in the CIRIS system. It manages the complete initialization lifecycle from infrastructure services to application services, following strict dependency ordering and verification patterns. The initializer provides critical telemetry on service startup performance, health verification, and registration success rates.

## Telemetry Data Collected

| Metric Name | Type | Storage | Update Frequency | Access Method |
|------------|------|---------|------------------|---------------|
| service_initialization_order | list | in-memory | on startup | initialization sequence |
| service_start_times | histogram | memory graph | per service start | GraphTelemetryService |
| service_verification_results | gauge | in-memory | per verification | health check methods |
| service_registration_count | counter | ServiceRegistry | on registration | `get_provider_info()` |
| failed_services_list | list | logging/memory | on failure | exception handlers |
| bootstrap_phase_duration | timer | memory graph | per phase | telemetry service |
| dependency_resolution_time | timer | memory graph | per resolution | dependency checks |
| config_migration_metrics | counter | memory graph | on migration | config service |
| mock_service_detection | boolean | in-memory | module loading | module loader |
| total_initialization_time | timer | memory graph | completion | time service |
| service_health_status | gauge | in-memory dict | verification | health protocols |
| registry_service_count | counter | ServiceRegistry | registration | provider info |
| circuit_breaker_initial_state | enum | ServiceRegistry | registration | circuit breakers |

## Data Structures

### Service Initialization Tracking
```python
{
    "initialization_sequence": [
        {
            "phase": "infrastructure",
            "services": ["TimeService", "ShutdownService", "InitializationService", "ResourceMonitorService"],
            "start_time": "2025-08-14T10:00:00Z",
            "duration_ms": 150,
            "status": "completed"
        },
        {
            "phase": "memory_and_secrets",
            "services": ["SecretsService", "LocalGraphMemoryService", "GraphConfigService"],
            "start_time": "2025-08-14T10:00:00.150Z",
            "duration_ms": 300,
            "status": "completed"
        },
        {
            "phase": "security",
            "services": ["AuthenticationService", "WiseAuthorityService"],
            "start_time": "2025-08-14T10:00:00.450Z",
            "duration_ms": 200,
            "status": "completed"
        },
        {
            "phase": "core_services",
            "services": ["GraphTelemetryService", "OpenAICompatibleClient", "GraphAuditService"],
            "start_time": "2025-08-14T10:00:00.650Z",
            "duration_ms": 500,
            "status": "completed"
        }
    ],
    "total_services_initialized": 21,
    "total_duration_ms": 1150,
    "failed_services": [],
    "mock_services_detected": ["MockLLMService"],
    "skip_flags": {
        "llm_init_skipped": true
    }
}
```

### Service Health Verification
```python
{
    "memory_service": {
        "verified": true,
        "test_node_id": "_verification_test",
        "operations_tested": ["memorize", "recall", "forget"],
        "verification_time_ms": 50,
        "error": null
    },
    "security_services": {
        "secrets_service": {"healthy": true, "error": null},
        "wa_auth_system": {"healthy": true, "error": null},
        "auth_service": {"healthy": true, "error": null}
    },
    "core_services": {
        "telemetry_service": {"initialized": true, "error": null},
        "llm_service": {"initialized": true, "type": "OpenAICompatibleClient", "model": "gpt-4"},
        "audit_services": {"count": 1, "primary": "GraphAuditService", "healthy": true}
    }
}
```

### Service Registry Telemetry
```python
{
    "services_registered": {
        "TIME": {
            "count": 1,
            "providers": ["TimeService"],
            "capabilities": ["now", "format_timestamp", "parse_timestamp"],
            "priority": "CRITICAL"
        },
        "MEMORY": {
            "count": 1,
            "providers": ["LocalGraphMemoryService"],
            "capabilities": ["memorize", "recall", "forget", "memorize_metric", "memorize_log"],
            "priority": "HIGH"
        },
        "LLM": {
            "count": 2,
            "providers": ["OpenAICompatibleClient_primary", "OpenAICompatibleClient_secondary"],
            "capabilities": ["call_llm_structured"],
            "priority": "HIGH, NORMAL"
        },
        "WISE_AUTHORITY": {
            "count": 1,
            "providers": ["WiseAuthorityService"],
            "capabilities": ["authenticate", "guidance", "send_deferral"],
            "priority": "HIGH"
        }
    },
    "circuit_breakers_initialized": 8,
    "total_registered_services": 21
}
```

### Configuration Migration Metrics
```python
{
    "migration_stats": {
        "total_keys_migrated": 25,
        "sections_processed": ["database", "security", "services", "graph"],
        "migration_duration_ms": 100,
        "errors": [],
        "bootstrap_config_size": 2048
    }
}
```

## API Access Patterns

### Current Access
- **Internal Tracking**: Service start times and durations stored in memory graph via GraphTelemetryService
- **Registry Access**: Service registration data available via ServiceRegistry.get_provider_info()
- **Health Verification**: Available through individual service health check methods
- **Log Analysis**: Initialization events captured in system logs

### Recommended Endpoints

#### Service Initialization Summary
```
GET /v1/telemetry/service-initializer
```
Returns complete initialization telemetry:
```json
{
    "initialization_completed": true,
    "total_duration_ms": 1150,
    "services_initialized": 21,
    "phases_completed": 4,
    "failed_services": [],
    "mock_services": ["MockLLMService"],
    "health_verification": {
        "memory_service": true,
        "security_services": true,
        "core_services": true
    },
    "registry_stats": {
        "total_registered": 21,
        "by_type": {
            "LLM": 2,
            "MEMORY": 1,
            "TIME": 1,
            "WISE_AUTHORITY": 1
        }
    }
}
```

#### Bootstrap Performance Metrics
```
GET /v1/telemetry/bootstrap-performance
```
Returns timing breakdown:
```json
{
    "phase_timings": [
        {
            "phase": "infrastructure",
            "duration_ms": 150,
            "services_count": 4,
            "avg_service_init_ms": 37.5
        },
        {
            "phase": "memory_and_secrets",
            "duration_ms": 300,
            "services_count": 3,
            "avg_service_init_ms": 100
        }
    ],
    "slowest_services": [
        {"name": "GraphAuditService", "duration_ms": 200},
        {"name": "OpenAICompatibleClient", "duration_ms": 150}
    ],
    "fastest_services": [
        {"name": "TimeService", "duration_ms": 20},
        {"name": "ShutdownService", "duration_ms": 15}
    ]
}
```

#### Service Health Matrix
```
GET /v1/telemetry/service-health-bootstrap
```
Returns health verification results:
```json
{
    "verification_summary": {
        "total_checks": 3,
        "passed": 3,
        "failed": 0,
        "skipped": 0
    },
    "health_details": {
        "memory_service": {
            "status": "healthy",
            "test_operations": ["memorize", "recall", "forget"],
            "verification_time_ms": 50
        },
        "security_services": {
            "status": "healthy",
            "components": ["secrets", "wa_auth", "authentication"]
        },
        "core_services": {
            "status": "healthy",
            "critical_services": 5,
            "audit_services": 1
        }
    }
}
```

## Example Usage

### Monitor Initialization Progress
```python
# Access initialization telemetry
initializer = ServiceInitializer()
await initializer.initialize_infrastructure_services()

# Check timing metrics stored in graph
telemetry_service = initializer.telemetry_service
bootstrap_metrics = await telemetry_service.get_bootstrap_metrics()
print(f"Infrastructure init took {bootstrap_metrics['duration_ms']}ms")
```

### Verify Service Health
```python
# Run health verifications
memory_healthy = await initializer.verify_memory_service()
security_healthy = await initializer.verify_security_services()
core_healthy = initializer.verify_core_services()

health_status = {
    "memory": memory_healthy,
    "security": security_healthy,
    "core": core_healthy
}
```

### Access Registry Telemetry
```python
# Get service registration stats
registry = initializer.service_registry
provider_info = registry.get_provider_info()

# Count services by type
service_counts = {}
for service_type, providers in provider_info["services"].items():
    service_counts[service_type] = len(providers)

print(f"Registered {sum(service_counts.values())} total services")
```

### Track Module Loading
```python
# Monitor module loading with MOCK detection
modules_to_load = ["mockllm", "custom_adapter"]
await initializer.load_modules(modules_to_load)

# Check for MOCK services
mock_warnings = initializer.module_loader.get_mock_warnings()
print(f"MOCK services detected: {len(mock_warnings)}")
```

## Graph Storage

### TSDB Nodes for Metrics
Service initialization metrics are stored as TSDBGraphNodes in the memory graph:

```python
{
    "node_type": "TSDB",
    "metric_type": "service_initialization",
    "service_name": "GraphTelemetryService",
    "duration_ms": 200,
    "timestamp": "2025-08-14T10:00:00.650Z",
    "tags": ["bootstrap", "telemetry", "core_service"],
    "metadata": {
        "phase": "core_services",
        "dependencies": ["memory_bus", "time_service"],
        "capabilities": ["memorize_metric", "get_stats"]
    }
}
```

### Configuration Nodes
Config migration creates CONFIG nodes:
```python
{
    "node_type": "CONFIG",
    "key": "database.audit_db",
    "value": "data/ciris_audit.db",
    "updated_by": "system_bootstrap",
    "migrated_from": "essential_config",
    "timestamp": "2025-08-14T10:00:00.200Z"
}
```

## Testing

### Test Files
- `tests/logic/runtime/test_service_initializer.py` - Main initialization tests
- `tests/logic/registries/test_service_registry.py` - Registry telemetry tests
- `tests/logic/services/test_health_verification.py` - Health check tests

### Validation Steps
1. Initialize all services in correct order
2. Verify timing metrics are recorded
3. Confirm health verification passes
4. Check service registration counts
5. Validate configuration migration
6. Test MOCK service detection

```python
async def test_initialization_telemetry():
    initializer = ServiceInitializer()
    start_time = time.time()

    # Phase 1: Infrastructure
    await initializer.initialize_infrastructure_services()
    infrastructure_time = time.time() - start_time

    # Phase 2: Memory and Secrets
    await initializer.initialize_memory_service(config)
    memory_time = time.time() - start_time - infrastructure_time

    # Verify telemetry
    assert infrastructure_time > 0
    assert memory_time > 0

    # Check service registry
    info = initializer.service_registry.get_provider_info()
    assert len(info["services"]) >= 4  # At least 4 service types

    # Verify health checks
    assert await initializer.verify_memory_service()
    assert await initializer.verify_security_services()
    assert initializer.verify_core_services()
```

## Configuration

### Bootstrap Phases
The initializer follows a strict 4-phase initialization:
1. **Infrastructure**: TimeService, ShutdownService, InitializationService, ResourceMonitorService
2. **Memory & Secrets**: SecretsService, LocalGraphMemoryService, GraphConfigService
3. **Security**: AuthenticationService, WiseAuthorityService
4. **Core Services**: All remaining services (telemetry, LLM, audit, etc.)

### Service Dependencies
```python
DEPENDENCY_ORDER = {
    "TimeService": [],
    "SecretsService": ["TimeService"],
    "LocalGraphMemoryService": ["TimeService", "SecretsService"],
    "GraphTelemetryService": ["memory_bus", "TimeService"],
    "OpenAICompatibleClient": ["TelemetryService", "TimeService"],
    "GraphAuditService": ["memory_bus", "TimeService"]
}
```

### Health Check Timeouts
```python
{
    "memory_verification_timeout": 30.0,  # seconds
    "security_health_timeout": 10.0,      # seconds
    "service_start_timeout": 60.0,        # seconds per service
    "total_bootstrap_timeout": 300.0      # seconds total
}
```

## Known Limitations

1. **Sequential Initialization**: Services start one by one, not in parallel
2. **In-Memory Phase Tracking**: Phase timing data lost on restart
3. **Limited Rollback**: Failed initialization requires full restart
4. **No Partial Recovery**: Single service failure can block entire initialization
5. **MOCK Detection Timing**: Module pre-scanning adds initialization overhead

## Future Enhancements

1. **Parallel Initialization**: Start independent services concurrently
2. **Persistent Bootstrap Metrics**: Store initialization history in database
3. **Graceful Degradation**: Continue with partial service set on non-critical failures
4. **Service Dependency Graph**: Visual representation of initialization order
5. **Performance Benchmarking**: Track initialization performance over time
6. **Health Check Dashboard**: Real-time view of service verification status

## Integration Points

- **GraphTelemetryService**: Stores all timing and performance metrics
- **ServiceRegistry**: Tracks service registration and circuit breaker states
- **TimeService**: Provides timestamps for all initialization events
- **ConfigService**: Records configuration migration metrics
- **AuditService**: Logs all initialization events for compliance
- **ModuleLoader**: Reports MOCK service detection and module loading stats

## Monitoring Recommendations

1. **Track Bootstrap Time**: Alert if initialization exceeds expected duration
2. **Monitor Service Failures**: Alert on any failed service initialization
3. **Health Verification**: Ensure all health checks pass consistently
4. **Registry Growth**: Track service registration trends over time
5. **MOCK Detection**: Log and monitor test vs. production service usage
6. **Config Migration**: Verify configuration values are properly migrated

## Security Considerations

1. **Service Verification**: Each service must pass health checks before use
2. **MOCK Isolation**: MOCK services prevent real service initialization for safety
3. **Secrets Bootstrap**: Master key generation and storage during initialization
4. **Audit Integration**: All initialization events are audited for compliance
5. **Circuit Breakers**: Services get circuit breakers for resilience from start
6. **Dependency Validation**: Services verify their dependencies before starting

## Performance Considerations

1. **Sequential Start**: Services start in dependency order, not optimized for speed
2. **Health Check Overhead**: Verification adds ~100ms per service
3. **Memory Allocation**: Each service allocates resources during initialization
4. **Database Creation**: First-time database setup can add significant time
5. **Key Generation**: Cryptographic key generation during bootstrap adds latency
