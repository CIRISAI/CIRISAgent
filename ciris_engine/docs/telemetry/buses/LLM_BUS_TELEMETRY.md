# LLM Bus Telemetry

## Overview
The LLM Bus tracks all language model interactions, provider health, selection metrics, and resource usage. It manages multiple LLM providers with circuit breakers, automatic failover, and distribution strategies.

## Telemetry Data Collected

| Metric Name | Type | Storage | Update Frequency | Access Method |
|------------|------|---------|------------------|---------------|
| total_requests | counter | in-memory dict | real-time | `get_service_stats()` |
| failed_requests | counter | in-memory dict | real-time | `get_service_stats()` |
| total_latency_ms | gauge | in-memory dict | real-time | `get_service_stats()` |
| average_latency_ms | calculated | in-memory dict | on-demand | `get_service_stats()` |
| consecutive_failures | counter | in-memory dict | real-time | `get_service_stats()` |
| last_request_time | timestamp | in-memory dict | real-time | `get_service_stats()` |
| last_failure_time | timestamp | in-memory dict | on failure | `get_service_stats()` |
| circuit_breaker_state | enum | in-memory | on change | `get_service_stats()` |
| failure_count | counter | in-memory | real-time | circuit breaker |
| success_count | counter | in-memory | real-time | circuit breaker |
| tokens_used | counter | telemetry graph | per-call | graph query |
| tokens_input | counter | telemetry graph | per-call | graph query |
| tokens_output | counter | telemetry graph | per-call | graph query |
| cost_cents | gauge | telemetry graph | per-call | graph query |
| carbon_grams | gauge | telemetry graph | per-call | graph query |
| energy_kwh | gauge | telemetry graph | per-call | graph query |
| round_robin_index | counter | in-memory dict | per-call | internal only |

## Data Structures

### ServiceMetrics (per LLM service)
```python
{
    "total_requests": 15234,           # Total requests to this service
    "failed_requests": 23,              # Number of failed requests
    "total_latency_ms": 6891234.5,      # Sum of all latencies
    "average_latency_ms": 452.3,        # Calculated average
    "failure_rate": "0.15%",            # Calculated failure rate
    "consecutive_failures": 0,          # Current failure streak
    "circuit_breaker_state": "closed",  # closed/open/half_open
    "last_request": "2025-08-14T13:30:00Z",
    "last_failure": "2025-08-14T12:15:00Z"
}
```

### CircuitBreaker Stats
```python
{
    "name": "OpenAICompatibleClient_12345",
    "state": "closed",            # closed/open/half_open
    "failure_count": 0,           # Failures in current window
    "success_count": 0,           # Successes in half_open state
    "last_failure_time": 1723640100.5
}
```

### Resource Telemetry (sent to TelemetryService)
```python
{
    "llm.tokens.total": 1523,        # Total tokens used
    "llm.tokens.input": 523,         # Input/prompt tokens
    "llm.tokens.output": 1000,       # Generated tokens
    "llm.cost.cents": 4.5,           # Cost in cents
    "llm.environmental.carbon_grams": 0.12,  # Carbon footprint
    "llm.environmental.energy_kwh": 0.0003,  # Energy usage
    "llm.latency.ms": 452.3          # Request latency
}
```

## API Access Patterns

### Current Access
- **Internal Only**: `LLMBus.get_service_stats()` method exists but not exposed via API
- **Partial Exposure**: Some metrics flow to TelemetryService and get stored in graph

### Recommended Endpoint
```
GET /v1/telemetry/llm/usage
```
Returns aggregated metrics for all LLM providers:
```json
{
    "services": {
        "OpenAICompatibleClient_12345": {
            "total_requests": 15234,
            "failed_requests": 23,
            "failure_rate": "0.15%",
            "average_latency_ms": "452.30",
            "consecutive_failures": 0,
            "circuit_breaker_state": "closed",
            "last_request": "2025-08-14T13:30:00Z",
            "last_failure": "2025-08-14T12:15:00Z"
        }
    },
    "distribution_strategy": "latency_based",
    "total_providers": 2,
    "healthy_providers": 2
}
```

## Graph Storage (via TelemetryService)

### Metric Nodes Created
When TelemetryService is available, the following metric nodes are created:
- Type: `METRIC`
- Properties: `metric_name`, `value`, `timestamp`, `handler_name`, `tags`

### Edge Relationships
- `MEASURED_BY` - Links metric to handler
- `TAGGED_WITH` - Links metric to service/model tags

## Example Usage

### Get Current LLM Stats
```python
# Within CIRIS codebase
llm_bus = service_registry.get_service(ServiceType.LLM)
stats = llm_bus.get_service_stats()
# Returns dict with all provider metrics
```

### Check Circuit Breaker State
```python
# Check if a specific service is available
service_name = "OpenAICompatibleClient_12345"
if service_name in llm_bus.circuit_breakers:
    breaker = llm_bus.circuit_breakers[service_name]
    is_available = breaker.is_available()
    state = breaker.state.value
```

### Monitor Distribution Strategy
```python
# Get current distribution strategy
stats = llm_bus.get_stats()
strategy = stats["distribution_strategy"]  # "latency_based", "round_robin", etc.
```

## Testing

### Test File
`tests/logic/buses/test_llm_bus.py` - Comprehensive tests exist

### Validation Steps
1. Make an LLM call through the bus
2. Verify `service_metrics` dictionary updates
3. Check circuit breaker state changes on failures
4. Confirm telemetry flows to graph (if TelemetryService present)

```python
# Example validation
async def test_llm_metrics_collection():
    llm_bus = get_service(ServiceType.LLM)

    # Make a call
    result, usage = await llm_bus.call_llm_structured(
        messages=[{"role": "user", "content": "test"}],
        response_model=TestModel,
        handler_name="test_handler"
    )

    # Check metrics
    stats = llm_bus.get_service_stats()
    assert any(s["total_requests"] > 0 for s in stats.values())
```

## Configuration

### Circuit Breaker Settings
```python
{
    "failure_threshold": 5,      # Failures before opening
    "recovery_timeout": 60.0,    # Seconds before trying half-open
    "success_threshold": 3,      # Successes needed to close
    "timeout_duration": 30.0     # Request timeout
}
```

### Distribution Strategies
- `LATENCY_BASED` - Route to lowest latency provider (default)
- `ROUND_ROBIN` - Distribute evenly across providers
- `RANDOM` - Random selection
- `LEAST_LOADED` - Route to provider with fewest active requests

## Known Limitations

1. **In-Memory Storage**: Service metrics and circuit breaker states are lost on restart
2. **No Historical Data**: Only current metrics are available, no time-series history
3. **Per-Instance Metrics**: In multi-instance deployments, metrics are not aggregated
4. **No Rate Limiting**: Request rate limiting not implemented at bus level

## Future Enhancements

1. **Persist Metrics**: Store service metrics in Redis/Graph for durability
2. **Time-Series Data**: Keep rolling window of metrics for trending
3. **Cross-Instance Aggregation**: Aggregate metrics across multiple CIRIS instances
4. **Rate Limiting**: Add per-handler rate limiting with token buckets
5. **Cost Budgets**: Implement cost limits per handler/domain

## Integration Points

- **TelemetryService**: Sends detailed resource metrics when available
- **TimeService**: Uses for timestamps and latency calculations
- **ServiceRegistry**: Discovers and manages LLM providers
- **Domain Routing**: Filters providers by domain (medical, legal, etc.)

## Monitoring Recommendations

1. **Alert on Circuit Breaker Opens**: Service degradation indicator
2. **Track Average Latency**: Performance degradation detection
3. **Monitor Token Usage**: Cost and quota management
4. **Watch Failure Rates**: Service health indicator
5. **Track Provider Distribution**: Load balancing effectiveness
