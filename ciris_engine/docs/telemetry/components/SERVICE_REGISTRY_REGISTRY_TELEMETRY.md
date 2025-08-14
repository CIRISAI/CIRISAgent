# Service Registry Telemetry

## Overview
The Service Registry is the central hub for service discovery, health monitoring, and provider management in CIRIS. It tracks all registered services, manages circuit breakers for resilience, and provides priority-based service selection with multiple distribution strategies.

## Telemetry Data Collected

| Metric Name | Type | Storage | Update Frequency | Access Method |
|------------|------|---------|------------------|---------------|
| registered_services | gauge | in-memory dict | on registration | `get_provider_info()` |
| services_by_type | histogram | in-memory dict | on registration | `get_provider_info()` |
| circuit_breaker_state | enum | in-memory | on state change | `get_provider_info()` |
| circuit_breaker_failure_count | counter | in-memory | on failure | circuit breaker stats |
| circuit_breaker_success_count | counter | in-memory | on success | circuit breaker stats |
| service_priority | enum | in-memory | on registration | `get_provider_info()` |
| service_capabilities | list | in-memory | on registration | `get_provider_info()` |
| priority_group | integer | in-memory | on registration | `get_provider_info()` |
| selection_strategy | enum | in-memory | on registration | `get_provider_info()` |
| round_robin_index | counter | in-memory dict | per selection | internal state |
| healthy_services_count | gauge | calculated | on-demand | iterate providers |
| unhealthy_services_count | gauge | calculated | on-demand | iterate providers |

## Data Structures

### Provider Information
```python
{
    "services": {
        "LLM": [
            {
                "name": "OpenAICompatibleClient_12345",
                "priority": "NORMAL",
                "priority_group": 0,
                "strategy": "fallback",
                "capabilities": ["call_llm_structured", "get_available_models"],
                "metadata": {
                    "provider": "openai",
                    "model": "gpt-4",
                    "domain": "general"
                },
                "circuit_breaker_state": "closed"
            }
        ],
        "MEMORY": [
            {
                "name": "LocalGraphMemoryService_67890",
                "priority": "CRITICAL",
                "priority_group": 0,
                "strategy": "fallback",
                "capabilities": ["memorize", "recall", "forget"],
                "metadata": {
                    "storage_backend": "sqlite",
                    "db_path": "/app/data/ciris.db"
                },
                "circuit_breaker_state": "closed"
            }
        ]
    },
    "circuit_breaker_stats": {
        "OpenAICompatibleClient_12345": {
            "name": "LLM_OpenAICompatibleClient_12345",
            "state": "closed",
            "failure_count": 0,
            "success_count": 1523,
            "last_failure_time": null
        }
    }
}
```

### Service Provider Details
```python
{
    "name": "ServiceClassName_InstanceID",
    "priority": "CRITICAL|HIGH|NORMAL|LOW|FALLBACK",
    "priority_group": 0,  # For sub-grouping within priority
    "strategy": "fallback|round_robin",
    "instance": <service_object>,
    "capabilities": ["capability1", "capability2"],
    "circuit_breaker": <CircuitBreaker>,
    "metadata": {
        "provider": "provider_name",
        "version": "1.0.0",
        "domain": "medical|legal|general",
        # ... custom metadata
    }
}
```

### Circuit Breaker Statistics
```python
{
    "name": "ServiceType_ProviderName",
    "state": "closed|open|half_open",
    "failure_count": 5,
    "success_count": 100,
    "last_failure_time": 1723640100.5,
    "failure_threshold": 5,
    "recovery_timeout": 60.0,
    "success_threshold": 3
}
```

## API Access Patterns

### Current Access
- **Partial Exposure**: `get_provider_info()` available but not exposed via API endpoint
- **Internal Use**: Called by buses and services for provider discovery

### Recommended Endpoints

#### Service Registry Overview
```
GET /v1/telemetry/service-registry
```
Returns complete registry state:
```json
{
    "total_services": 24,
    "services_by_type": {
        "LLM": 2,
        "MEMORY": 1,
        "COMMUNICATION": 3,
        "AUDIT": 1,
        "TELEMETRY": 1
    },
    "healthy_services": 23,
    "unhealthy_services": 1,
    "circuit_breakers_open": 1,
    "providers": {
        // Full provider info
    }
}
```

#### Circuit Breaker Status
```
GET /v1/telemetry/circuit-breakers
```
Returns all circuit breaker states:
```json
{
    "total_breakers": 24,
    "states": {
        "closed": 22,
        "open": 1,
        "half_open": 1
    },
    "breakers": [
        {
            "service": "LLM_OpenAIClient_12345",
            "state": "open",
            "failure_count": 5,
            "last_failure": "2025-08-14T13:30:00Z",
            "recovery_at": "2025-08-14T13:31:00Z"
        }
    ]
}
```

#### Service Health Matrix
```
GET /v1/telemetry/service-health
```
Returns health status by service type:
```json
{
    "LLM": {
        "total": 2,
        "healthy": 1,
        "unhealthy": 1,
        "providers": [
            {"name": "OpenAI", "healthy": false, "reason": "circuit_breaker_open"},
            {"name": "Anthropic", "healthy": true}
        ]
    }
}
```

## Example Usage

### Get Registry Information
```python
# Get complete registry info
registry = get_global_registry()
info = registry.get_provider_info()

# Get info for specific service type
llm_info = registry.get_provider_info(service_type="LLM")
```

### Check Service Availability
```python
# Get available LLM services
llm_services = await registry.get_services(
    service_type=ServiceType.LLM,
    required_capabilities=["call_llm_structured"]
)

# Check if any are healthy
healthy_count = len(llm_services)
```

### Monitor Circuit Breakers
```python
# Get all circuit breaker states
info = registry.get_provider_info()
breaker_stats = info["circuit_breaker_stats"]

# Count open breakers
open_breakers = sum(
    1 for stats in breaker_stats.values()
    if stats["state"] == "open"
)
```

### Register Service with Telemetry
```python
# Register with metadata for telemetry
registry.register_service(
    service_type=ServiceType.LLM,
    provider=llm_service,
    priority=Priority.NORMAL,
    capabilities=["call_llm_structured"],
    metadata={
        "provider": "openai",
        "model": "gpt-4",
        "domain": "medical",
        "max_tokens": 4096
    },
    priority_group=0,
    strategy=SelectionStrategy.FALLBACK
)
```

## Testing

### Test Files
- `tests/logic/registries/test_service_registry.py` - Registry tests
- `tests/logic/registries/test_circuit_breaker.py` - Circuit breaker tests

### Validation Steps
1. Register multiple services
2. Verify `get_provider_info()` returns all services
3. Trigger circuit breaker by failing requests
4. Confirm service marked unhealthy
5. Wait for recovery timeout
6. Verify half-open state transition

```python
async def test_registry_telemetry():
    registry = ServiceRegistry()

    # Register services
    registry.register_service(
        ServiceType.LLM,
        MockLLMService(),
        priority=Priority.NORMAL
    )

    # Get telemetry
    info = registry.get_provider_info()
    assert "LLM" in info["services"]
    assert len(info["services"]["LLM"]) == 1
    assert info["services"]["LLM"][0]["circuit_breaker_state"] == "closed"
```

## Configuration

### Priority Levels
```python
class Priority(Enum):
    CRITICAL = 0  # Always try first
    HIGH = 1      # Preferred providers
    NORMAL = 2    # Standard providers
    LOW = 3       # Use if others unavailable
    FALLBACK = 9  # Last resort
```

### Selection Strategies
```python
class SelectionStrategy(Enum):
    FALLBACK = "fallback"        # First available in priority order
    ROUND_ROBIN = "round_robin"  # Rotate through providers
```

### Circuit Breaker Defaults
```python
{
    "failure_threshold": 5,      # Failures before opening
    "recovery_timeout": 60.0,    # Seconds before half-open
    "success_threshold": 3,      # Successes to close
    "timeout_duration": 30.0     # Request timeout
}
```

## Known Limitations

1. **In-Memory State**: All registry state lost on restart
2. **No Persistence**: Circuit breaker states not saved
3. **No Cross-Instance Sync**: Multiple CIRIS instances don't share registry
4. **Limited Health Checks**: Only circuit breaker based, no active probing
5. **No Service Discovery**: Manual registration only, no auto-discovery

## Future Enhancements

1. **Persistent State**: Store registry in Redis/etcd for durability
2. **Active Health Checks**: Periodic health probes to services
3. **Service Discovery**: Auto-discover services via DNS/Kubernetes
4. **Distributed Registry**: Sync state across CIRIS instances
5. **Service Mesh Integration**: Integrate with Istio/Linkerd
6. **Weighted Load Balancing**: Route based on service capacity

## Integration Points

- **All Buses**: Use registry for service discovery
- **Circuit Breakers**: Manage resilience for all services
- **ServiceInitializer**: Registers services at startup
- **RuntimeControl**: Queries registry for system status

## Monitoring Recommendations

1. **Alert on Service Loss**: When service count drops
2. **Monitor Circuit Breakers**: Alert on multiple opens
3. **Track Registration Changes**: Log all register/unregister
4. **Watch Priority Distribution**: Ensure balanced priorities
5. **Monitor Selection Patterns**: Track round-robin fairness

## Security Considerations

1. **Mock/Real Separation**: Prevents mixing mock and real LLM services
2. **Capability Validation**: Services must declare capabilities
3. **Metadata Validation**: Domain tagging for specialized routing
4. **No Dynamic Code Loading**: Services must be pre-instantiated
5. **Audit Trail**: All registrations logged

## Performance Considerations

1. **O(n) Service Lookup**: Linear search through providers
2. **No Caching**: Provider list searched each time
3. **Synchronous Health Checks**: Can block if service slow
4. **Memory Growth**: Unbounded circuit breaker history
5. **No Rate Limiting**: Unlimited registration/queries allowed
