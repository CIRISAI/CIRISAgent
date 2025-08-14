# Circuit Breaker Component Telemetry

## Overview
The Circuit Breaker Component is a critical fault tolerance mechanism in CIRIS that monitors service failures and temporarily disables failing services to prevent cascading failures. Circuit breakers are deployed across ALL services in the system - every service registered through the ServiceRegistry gets its own circuit breaker instance. This provides system-wide resilience and extensive telemetry collection for service health monitoring.

The circuit breaker pattern implements three states (CLOSED, OPEN, HALF_OPEN) with configurable thresholds and recovery timeouts. All state transitions, failure counts, and timing metrics are captured for comprehensive monitoring and debugging.

## Telemetry Data Collected

| Metric Name | Type | Storage | Update Frequency | Access Method |
|------------|------|---------|------------------|---------------|
| circuit_breaker_state | enum | in-memory | on state change | `get_stats()`, API endpoints |
| failure_count | counter | in-memory | on each failure | `get_stats()`, API endpoints |
| success_count | counter | in-memory | on each success | `get_stats()`, API endpoints |
| last_failure_time | timestamp | in-memory | on failure | `get_stats()`, API endpoints |
| state_transition_events | log | log files | on transition | log analysis |
| recovery_attempts | counter | calculated | on half-open | derived from state changes |
| availability_percentage | percentage | calculated | on-demand | derived from success/failure ratio |
| mean_time_to_recovery | duration | calculated | on-demand | time between failure and recovery |
| failure_rate | rate | calculated | on-demand | failures per time window |
| circuit_breaker_configuration | metadata | in-memory | on creation | config inspection |

## Data Structures

### Circuit Breaker Statistics (Core Telemetry)
```python
{
    "name": "LLM_OpenAICompatibleClient_12345",
    "state": "closed|open|half_open",
    "failure_count": 5,
    "success_count": 1523,
    "last_failure_time": 1723640100.5  # Unix timestamp or null
}
```

### Circuit Breaker Configuration
```python
{
    "name": "ServiceType_ProviderName",
    "failure_threshold": 5,     # Failures before opening
    "recovery_timeout": 60.0,   # Seconds before half-open
    "success_threshold": 3,     # Successes to close from half-open
    "timeout_duration": 30.0    # Request timeout (if implemented)
}
```

### Extended Circuit Breaker Telemetry (Calculated)
```python
{
    "name": "LLM_OpenAICompatibleClient_12345",
    "state": "open",
    "failure_count": 5,
    "success_count": 1523,
    "last_failure_time": 1723640100.5,
    "total_operations": 1528,
    "failure_rate": 0.0033,          # failure_count / total_operations
    "availability": 0.9967,          # 1 - failure_rate
    "time_since_last_failure": 120.5, # seconds
    "is_in_recovery": true,          # state == "half_open"
    "recovery_attempts": 2,          # estimated from logs
    "configuration": {
        "failure_threshold": 5,
        "recovery_timeout": 60.0,
        "success_threshold": 3
    }
}
```

### Service Registry Integration
```python
{
    "circuit_breaker_stats": {
        "OpenAICompatibleClient_12345": {
            "name": "LLM_OpenAICompatibleClient_12345",
            "state": "closed",
            "failure_count": 0,
            "success_count": 1523,
            "last_failure_time": null
        },
        "LocalGraphMemoryService_67890": {
            "name": "MEMORY_LocalGraphMemoryService_67890",
            "state": "open",
            "failure_count": 8,
            "success_count": 45,
            "last_failure_time": 1723640200.3
        }
    }
}
```

## API Access Patterns

### Current API Endpoints (Available)

#### Service Health Status (includes circuit breaker data)
```
GET /api/datum/v1/system/services/health
```
Returns comprehensive health including circuit breaker states:
```json
{
    "status": "success",
    "data": {
        "overall_health": "degraded",
        "service_types": {
            "LLM": {
                "healthy_count": 1,
                "unhealthy_count": 1,
                "services": [
                    {
                        "name": "OpenAICompatibleClient_12345",
                        "healthy": false,
                        "circuit_breaker_state": "open",
                        "failure_count": 5,
                        "last_failure": "2025-08-14T13:30:00Z"
                    }
                ]
            }
        }
    }
}
```

#### Circuit Breaker Reset (Administrative)
```
POST /api/datum/v1/system/services/circuit-breakers/reset
{
    "service_type": "LLM"  // Optional, resets all if omitted
}
```
Returns reset confirmation:
```json
{
    "status": "success",
    "data": {
        "service_type": "LLM",
        "reset_count": 2,
        "services_affected": [
            "OpenAICompatibleClient_12345",
            "AnthropicClient_67890"
        ],
        "message": "Circuit breakers reset successfully"
    }
}
```

### Recommended Additional Endpoints

#### Circuit Breaker Overview Dashboard
```
GET /api/datum/v1/telemetry/circuit-breakers
```
Proposed response:
```json
{
    "status": "success",
    "data": {
        "total_breakers": 24,
        "states": {
            "closed": 22,
            "open": 1,
            "half_open": 1
        },
        "system_health": "degraded",
        "breakers": [
            {
                "service": "LLM_OpenAIClient_12345",
                "state": "open",
                "failure_count": 5,
                "failure_rate": 0.15,
                "last_failure": "2025-08-14T13:30:00Z",
                "recovery_at": "2025-08-14T13:31:00Z",
                "service_type": "LLM"
            }
        ]
    }
}
```

#### Individual Circuit Breaker Details
```
GET /api/datum/v1/telemetry/circuit-breakers/{service_name}
```
Detailed metrics for specific circuit breaker:
```json
{
    "status": "success",
    "data": {
        "name": "LLM_OpenAICompatibleClient_12345",
        "state": "half_open",
        "current_stats": {
            "failure_count": 5,
            "success_count": 1523,
            "total_operations": 1528,
            "failure_rate": 0.0033,
            "availability": 99.67
        },
        "configuration": {
            "failure_threshold": 5,
            "recovery_timeout": 60.0,
            "success_threshold": 3
        },
        "timeline": {
            "last_failure_time": "2025-08-14T13:30:00Z",
            "last_success_time": "2025-08-14T13:28:45Z",
            "time_in_current_state": 65.5,
            "estimated_recovery_time": "2025-08-14T13:31:00Z"
        }
    }
}
```

## Example Usage

### Direct Circuit Breaker Access
```python
from ciris_engine.logic.registries.circuit_breaker import CircuitBreaker, CircuitBreakerConfig

# Create circuit breaker with custom config
config = CircuitBreakerConfig(
    failure_threshold=3,
    recovery_timeout=30.0,
    success_threshold=2
)
cb = CircuitBreaker("MyService", config)

# Check availability before operation
if cb.is_available():
    try:
        # Perform operation
        result = await my_service.do_something()
        cb.record_success()  # Record success
    except Exception as e:
        cb.record_failure()  # Record failure
        raise
else:
    raise CircuitBreakerError("Service unavailable")

# Get telemetry
stats = cb.get_stats()
print(f"State: {stats['state']}, Failures: {stats['failure_count']}")
```

### Service Registry Circuit Breaker Access
```python
from ciris_engine.logic.registries.base import get_global_registry

# Get all circuit breaker stats via registry
registry = get_global_registry()
provider_info = registry.get_provider_info()
circuit_stats = provider_info["circuit_breaker_stats"]

# Analyze circuit breaker health
for service_name, stats in circuit_stats.items():
    if stats["state"] == "open":
        print(f"SERVICE DOWN: {service_name} - {stats['failure_count']} failures")
    elif stats["failure_count"] > 2:
        print(f"SERVICE DEGRADED: {service_name} - {stats['failure_count']} failures")

# Reset all circuit breakers (admin operation)
registry.reset_circuit_breakers()
```

### Monitoring Circuit Breaker States
```python
import time

def monitor_circuit_breakers():
    """Monitor circuit breaker states across all services"""
    registry = get_global_registry()

    while True:
        info = registry.get_provider_info()
        stats = info["circuit_breaker_stats"]

        # Count states
        state_counts = {"closed": 0, "open": 0, "half_open": 0}
        for cb_stats in stats.values():
            state_counts[cb_stats["state"]] += 1

        # Alert on service degradation
        if state_counts["open"] > 0:
            print(f"ALERT: {state_counts['open']} services down")

        # Log detailed status
        for name, cb_stats in stats.items():
            if cb_stats["state"] != "closed":
                print(f"{name}: {cb_stats['state']} ({cb_stats['failure_count']} failures)")

        time.sleep(30)  # Check every 30 seconds
```

## Testing

### Test Coverage Locations
Circuit breaker functionality is tested indirectly through:
- Service registry tests: `tests/logic/registries/` (when they exist)
- LLM service tests: `tests/ciris_engine/logic/services/runtime/test_llm_service_comprehensive.py`
- Bus tests: `tests/test_llm_bus.py`
- API integration tests: `tests/api/test_system_extensions*.py`

### Validation Steps
1. **State Transitions**: Register service, cause failures, verify state changes
2. **Recovery Logic**: Wait for timeout, verify half-open transition
3. **Success Threshold**: Record successes in half-open, verify closed transition
4. **API Integration**: Test API endpoints return correct circuit breaker data
5. **Registry Integration**: Verify circuit breakers are created for all services

```python
async def test_circuit_breaker_telemetry():
    """Test circuit breaker telemetry collection"""
    from ciris_engine.logic.registries.circuit_breaker import CircuitBreaker

    cb = CircuitBreaker("TestService")

    # Initial state
    stats = cb.get_stats()
    assert stats["state"] == "closed"
    assert stats["failure_count"] == 0

    # Record failures to trigger opening
    for _ in range(5):
        cb.record_failure()

    # Verify telemetry after opening
    stats = cb.get_stats()
    assert stats["state"] == "open"
    assert stats["failure_count"] == 5
    assert stats["last_failure_time"] is not None

    # Verify availability check
    assert not cb.is_available()
```

## Configuration

### Default Circuit Breaker Settings
```python
# From CircuitBreakerConfig class
{
    "failure_threshold": 5,      # Failures before opening
    "recovery_timeout": 60.0,    # Seconds before half-open attempt
    "success_threshold": 3,      # Successes needed to close
    "timeout_duration": 30.0     # Request timeout (not implemented)
}
```

### Per-Service Customization
```python
# Custom config when registering services
config = CircuitBreakerConfig(
    failure_threshold=3,    # More sensitive
    recovery_timeout=30.0,  # Faster recovery
    success_threshold=2     # Fewer successes needed
)

registry.register_service(
    service_type=ServiceType.LLM,
    provider=llm_service,
    circuit_breaker_config=config
)
```

### Circuit Breaker States
```python
class CircuitState(Enum):
    CLOSED = "closed"      # Normal operation
    OPEN = "open"          # Service disabled, fail fast
    HALF_OPEN = "half_open"  # Testing recovery
```

## Graph Storage

Circuit breakers do not currently store data in the CIRIS memory graph. All telemetry is:
- **In-Memory**: Current state, counters, timestamps
- **Ephemeral**: Lost on system restart
- **Log-Based**: State transitions logged for analysis

### Potential Graph Integration
Future enhancements could store circuit breaker events in the memory graph:
```python
# Potential graph node structure
CircuitBreakerEventNode = {
    "node_type": "circuit_breaker_event",
    "service_name": "LLM_OpenAIClient_12345",
    "event_type": "state_transition",
    "from_state": "closed",
    "to_state": "open",
    "timestamp": 1723640100.5,
    "failure_count": 5,
    "metadata": {
        "trigger": "threshold_exceeded",
        "service_type": "LLM"
    }
}
```

## Known Limitations

1. **In-Memory State**: All circuit breaker state lost on restart
2. **No Persistence**: State and statistics not persisted between restarts
3. **No Historical Data**: No long-term trend analysis capability
4. **Limited Timeout**: `timeout_duration` config not implemented in current version
5. **No Gradual Recovery**: Half-open state allows unlimited requests (not throttled)
6. **No Cross-Instance Sync**: Circuit breakers not shared across CIRIS instances
7. **Manual Recovery**: No automatic circuit breaker healing based on external health checks

## Future Enhancements

1. **Persistent State**: Store circuit breaker state in Redis/database
2. **Historical Analytics**: Long-term failure pattern analysis
3. **Predictive Monitoring**: ML-based failure prediction
4. **Dynamic Thresholds**: Adaptive thresholds based on service characteristics
5. **Gradual Recovery**: Throttled requests during half-open state
6. **Health Probes**: Active health checking to accelerate recovery
7. **Circuit Breaker Mesh**: Distributed circuit breaker coordination
8. **Graph Integration**: Store circuit breaker events in memory graph
9. **Configurable Strategies**: Multiple circuit breaker algorithms (exponential backoff, etc.)
10. **External Triggers**: Integration with monitoring systems (Prometheus, etc.)

## Integration Points

### System-Wide Integration
- **ServiceRegistry**: Creates circuit breaker for every registered service
- **All Buses**: LLM, Memory, Communication, Tool, RuntimeControl, Wise buses use circuit breakers
- **API Endpoints**: Health monitoring and administrative reset capabilities
- **Logging System**: State transitions logged for debugging
- **RuntimeControl**: Circuit breaker status exposed in system health

### Service Dependencies
Circuit breakers protect these critical service types:
- **LLM Services**: OpenAI, Anthropic, local models
- **Memory Services**: Neo4j, ArangoDB, in-memory graphs
- **Communication Services**: Discord, API, CLI adapters
- **Tool Services**: Various tool providers
- **Infrastructure Services**: Authentication, audit, telemetry

## Monitoring Recommendations

### Critical Alerts
1. **Service Down**: Alert when circuit breaker enters OPEN state
2. **Multiple Failures**: Alert when >20% of services have open circuit breakers
3. **Recovery Stuck**: Alert when circuit breaker stuck in HALF_OPEN for >5 minutes
4. **Failure Spike**: Alert when failure rate increases >5x normal

### Operational Monitoring
1. **Dashboard Metrics**: Real-time circuit breaker state visualization
2. **Trend Analysis**: Historical failure patterns and recovery times
3. **Service Health Matrix**: Circuit breaker status by service type
4. **Recovery Success Rate**: Percentage of successful recoveries

### Key Performance Indicators (KPIs)
1. **System Availability**: Percentage of services with closed circuit breakers
2. **Mean Time to Recovery (MTTR)**: Average time from failure to recovery
3. **Failure Rate**: Failures per time period across all services
4. **Circuit Breaker Effectiveness**: Prevented cascading failures

## Security Considerations

1. **Admin-Only Reset**: Circuit breaker reset requires ADMIN role
2. **No Bypass Mechanism**: Circuit breakers cannot be disabled per-service
3. **Audit Trail**: All circuit breaker resets logged for security audit
4. **State Inspection**: Health endpoints available to OBSERVER role and above
5. **Failure Logging**: Failures logged but sensitive data excluded

## Performance Considerations

1. **Low Overhead**: Circuit breaker checks are O(1) operations
2. **Memory Usage**: Minimal per-service memory footprint
3. **Thread Safety**: Circuit breakers are not currently thread-safe
4. **Recovery Timing**: Recovery timeout based on wall-clock time
5. **State Transitions**: Atomic state changes prevent race conditions

## Dependencies

### Required Components
- `ciris_engine.logic.registries.circuit_breaker`: Core implementation
- `ciris_engine.logic.registries.base`: ServiceRegistry integration
- `ciris_engine.schemas.services.core.runtime`: API response schemas
- Python `time` module: Timestamp management
- Python `logging` module: State transition logging

### Optional Integrations
- FastAPI routes: API endpoint exposure
- Memory graph services: Future event storage
- External monitoring: Prometheus/Grafana integration
