# LLM Service Telemetry

## Overview
The LLM Service (OpenAI-compatible) manages interactions with Large Language Model APIs, providing structured LLM calls with circuit breaker protection, comprehensive resource tracking, and environmental impact monitoring. The service tracks token usage, costs, carbon emissions, response performance, and circuit breaker statistics for operational visibility and responsible AI management.

## Telemetry Data Collected

| Metric Name | Type | Storage | Update Frequency | Access Method |
|------------|------|---------|------------------|---------------|
| circuit_breaker_state | gauge | in-memory service | per call | `_collect_custom_metrics()` |
| consecutive_failures | counter | circuit breaker state | per failure | `circuit_breaker.get_stats()` |
| recovery_attempts | counter | circuit breaker state | per recovery | `circuit_breaker.get_stats()` |
| last_failure_age_seconds | gauge | circuit breaker state | per call | `circuit_breaker.get_stats()` |
| success_rate | gauge | circuit breaker calculations | per call | `circuit_breaker.get_stats()` |
| call_count | counter | circuit breaker state | per call | `circuit_breaker.get_stats()` |
| failure_count | counter | circuit breaker state | per failure | `circuit_breaker.get_stats()` |
| cache_size_mb | gauge | in-memory calculation | per status check | `sys.getsizeof(_response_cache)` |
| cache_entries | gauge | in-memory dict | per response | `len(_response_cache)` |
| response_cache_hit_rate | gauge | **NOT IMPLEMENTED** | - | TODO: Track cache hits |
| avg_response_time_ms | gauge | **NOT IMPLEMENTED** | - | TODO: Track response times |
| model_cost_per_1k_tokens | config | model configuration | service start | Static per model |
| retry_delay_base | config | service configuration | service start | `base_delay` |
| retry_delay_max | config | service configuration | service start | `max_delay` |
| model_timeout_seconds | config | service configuration | service start | `openai_config.timeout_seconds` |
| model_max_retries | config | service configuration | service start | `max_retries` |
| tokens_used | counter | per-call telemetry | per API call | `ResourceUsage.tokens_used` |
| tokens_input | counter | per-call telemetry | per API call | `ResourceUsage.tokens_input` |
| tokens_output | counter | per-call telemetry | per API call | `ResourceUsage.tokens_output` |
| cost_cents | counter | per-call calculation | per API call | `ResourceUsage.cost_cents` |
| carbon_grams | counter | per-call calculation | per API call | `ResourceUsage.carbon_grams` |
| energy_kwh | counter | per-call calculation | per API call | `ResourceUsage.energy_kwh` |
| uptime_seconds | gauge | inherited from BaseService | continuous | `_calculate_uptime()` |
| request_count | counter | inherited from BaseService | per request | `_track_request()` |
| error_count | counter | inherited from BaseService | per error | `_track_error()` |
| error_rate | gauge | inherited from BaseService | calculated | `error_count / request_count` |
| healthy | boolean | inherited from BaseService | per status check | `is_healthy()` |

## Data Structures

### LLMStatus
```python
{
    "available": true,                   # Circuit breaker availability
    "model": "gpt-4o-mini",             # Current model name
    "usage": {
        "total_calls": 1250,             # Total API calls made
        "failed_calls": 15,              # Failed API calls
        "success_rate": 0.988            # Success rate (0-1)
    },
    "rate_limit_remaining": null,        # API rate limits (not tracked)
    "response_time_avg": null            # Average response time (not tracked)
}
```

### ResourceUsage (Per API Call)
```python
{
    "tokens_used": 1523,                 # Total tokens consumed
    "tokens_input": 890,                 # Input prompt tokens
    "tokens_output": 633,                # Generated response tokens
    "cost_cents": 0.23,                  # Cost in USD cents
    "carbon_grams": 0.045,               # CO2 emissions in grams
    "energy_kwh": 0.00009,               # Energy consumption in kWh
    "model_used": "gpt-4o-mini"          # Model that incurred costs
}
```

### Circuit Breaker Stats
```python
{
    "name": "llm_service",               # Circuit breaker name
    "state": "closed",                   # closed|open|half_open
    "failure_count": 2,                  # Consecutive failures
    "success_count": 0,                  # Successes in half_open state
    "last_failure_time": 1723644600.0,   # Unix timestamp of last failure
    "consecutive_failures": 2,           # Current failure streak
    "recovery_attempts": 0,              # Recovery attempts made
    "last_failure_age": 0,               # Seconds since last failure
    "success_rate": 0.988,               # Historical success rate
    "call_count": 1250,                  # Total calls made
    "failure_count": 15                  # Total failures
}
```

### Service Capabilities Metadata
```python
{
    "model": "gpt-4o-mini",              # Current model
    "instructor_mode": "JSON",           # Instructor parsing mode
    "timeout_seconds": 30,               # API timeout
    "max_retries": 3,                    # Retry attempts
    "circuit_breaker_state": "closed"    # Current CB state
}
```

### Model Pricing Configuration
```python
# GPT-4o-mini (default)
{
    "input_cost_per_1m": 15.0,          # $0.15 per 1M tokens
    "output_cost_per_1m": 60.0          # $0.60 per 1M tokens
}

# GPT-4o
{
    "input_cost_per_1m": 250.0,         # $2.50 per 1M tokens
    "output_cost_per_1m": 1000.0        # $10.00 per 1M tokens
}

# GPT-4-turbo
{
    "input_cost_per_1m": 1000.0,        # $10.00 per 1M tokens
    "output_cost_per_1m": 3000.0        # $30.00 per 1M tokens
}

# Claude models
{
    "input_cost_per_1m": 300.0,         # $3.00 per 1M tokens
    "output_cost_per_1m": 1500.0        # $15.00 per 1M tokens
}

# Llama models
{
    "input_cost_per_1m": 10.0,          # $0.10 per 1M tokens
    "output_cost_per_1m": 10.0          # $0.10 per 1M tokens
}
```

## API Access Patterns

### Current Access
- **Internal Service Access**: Via dependency injection and service registry
- **Telemetry Integration**: Records metrics to TelemetryService when available
- **Circuit Breaker Monitoring**: Direct access to circuit breaker statistics
- **Resource Tracking**: Every API call generates ResourceUsage data

### Recommended Endpoints

#### Get LLM Service Status
```
GET /v1/telemetry/llm/status
```
Returns comprehensive service status:
```json
{
    "service_name": "llm_service",
    "model": "gpt-4o-mini",
    "available": true,
    "circuit_breaker": {
        "state": "closed",
        "failure_count": 0,
        "success_rate": 1.0,
        "last_failure_age_seconds": 0
    },
    "usage": {
        "total_calls": 1250,
        "failed_calls": 15,
        "success_rate": 0.988
    },
    "performance": {
        "cache_size_mb": 2.4,
        "cache_entries": 45,
        "uptime_seconds": 86400
    },
    "configuration": {
        "timeout_seconds": 30,
        "max_retries": 3,
        "instructor_mode": "JSON"
    }
}
```

#### Get Resource Usage Summary
```
GET /v1/telemetry/llm/resources
```
Query parameters:
- `period`: 1h|1d|7d|30d
- `model`: Filter by specific model

Returns aggregated resource usage:
```json
{
    "period": "1d",
    "model": "gpt-4o-mini",
    "total_calls": 150,
    "total_tokens": 125000,
    "total_cost_cents": 18.75,
    "total_carbon_grams": 3.75,
    "total_energy_kwh": 0.0075,
    "average_tokens_per_call": 833,
    "cost_breakdown": {
        "input_cost_cents": 5.25,
        "output_cost_cents": 13.50
    },
    "environmental_impact": {
        "carbon_equivalent_miles_driven": 0.009,
        "trees_needed_to_offset": 0.00015
    }
}
```

#### Get Circuit Breaker Metrics
```
GET /v1/telemetry/llm/circuit-breaker
```
Returns circuit breaker health:
```json
{
    "state": "closed",
    "is_healthy": true,
    "configuration": {
        "failure_threshold": 5,
        "recovery_timeout": 10.0,
        "success_threshold": 2,
        "timeout_duration": 30.0
    },
    "current_stats": {
        "consecutive_failures": 0,
        "recovery_attempts": 0,
        "call_count": 1250,
        "failure_count": 15,
        "success_rate": 0.988
    },
    "last_failure": {
        "timestamp": "2025-08-14T10:30:00Z",
        "age_seconds": 7200,
        "error_type": "RateLimitError"
    }
}
```

#### Get Model Cost Analysis
```
GET /v1/telemetry/llm/costs
```
Query parameters:
- `timeframe`: hour|day|week|month
- `breakdown`: tokens|calls|models

Returns cost analysis:
```json
{
    "timeframe": "day",
    "total_cost_cents": 45.30,
    "cost_by_model": {
        "gpt-4o-mini": 18.75,
        "gpt-4o": 26.55
    },
    "cost_by_operation": {
        "input_tokens": 15.20,
        "output_tokens": 30.10
    },
    "trends": {
        "cost_per_hour": 1.89,
        "tokens_per_hour": 5208,
        "calls_per_hour": 6.25
    },
    "projections": {
        "monthly_cost_cents": 1359.0,
        "monthly_tokens": 3750000,
        "monthly_carbon_grams": 112.5
    }
}
```

## Graph Storage

### Telemetry Service Integration
When `telemetry_service` is available, the LLM service records:
- `llm_tokens_used`: Token consumption per call
- `llm_api_call_structured`: Structured API call counter

### Memory Graph Nodes
Resource usage data can be stored as graph nodes via the telemetry service:
```python
# Via TelemetryService.memorize_metric()
{
    "node_type": "metric",
    "metric_name": "llm_resource_usage",
    "timestamp": "2025-08-14T13:30:00Z",
    "data": {
        "model": "gpt-4o-mini",
        "tokens_used": 1523,
        "cost_cents": 0.23,
        "carbon_grams": 0.045,
        "call_id": "uuid-1234"
    }
}
```

## Example Usage

### Get Service Status
```python
llm_service = get_service(ServiceType.LLM)
status = llm_service._get_status()

print(f"LLM Service: {status.model}")
print(f"Available: {status.available}")
print(f"Success Rate: {status.usage.success_rate:.3f}")
print(f"Total Calls: {status.usage.total_calls}")
```

### Monitor Circuit Breaker
```python
llm_service = get_service(ServiceType.LLM)
cb_stats = llm_service.circuit_breaker.get_stats()

if cb_stats["state"] != "closed":
    logger.warning(f"Circuit breaker {cb_stats['state']}: {cb_stats['failure_count']} failures")

if cb_stats["success_rate"] < 0.95:
    logger.alert(f"LLM success rate dropped to {cb_stats['success_rate']:.2%}")
```

### Track Resource Usage
```python
# Make structured call and track usage
response, usage = await llm_service.call_llm_structured(
    messages=[{"role": "user", "content": "Hello"}],
    response_model=MyResponse,
    max_tokens=1000,
    temperature=0.0
)

# Usage is automatically tracked in telemetry
print(f"Tokens used: {usage.tokens_used}")
print(f"Cost: ${usage.cost_cents/100:.4f}")
print(f"Carbon: {usage.carbon_grams}g CO2")
print(f"Energy: {usage.energy_kwh} kWh")
```

### Check Service Health
```python
llm_service = get_service(ServiceType.LLM)
is_healthy = await llm_service.is_healthy()

if not is_healthy:
    logger.error("LLM service is unhealthy")
    # Check specific issues
    if not llm_service.circuit_breaker.is_available():
        logger.error("Circuit breaker is open")
```

### Monitor Performance Metrics
```python
llm_service = get_service(ServiceType.LLM)
metrics = llm_service._collect_custom_metrics()

print(f"Cache size: {metrics['cache_size_mb']:.2f}MB")
print(f"Cache entries: {int(metrics['cache_entries'])}")
print(f"Circuit breaker failures: {int(metrics['consecutive_failures'])}")
```

## Testing

### Test Files
- `tests/logic/services/runtime/test_llm_service.py`
- `tests/integration/test_llm_circuit_breaker.py`
- `tests/telemetry/test_llm_resource_tracking.py`

### Validation Steps
1. Initialize LLM service with telemetry integration
2. Make structured API calls and verify resource tracking
3. Trigger circuit breaker by simulating failures
4. Verify metrics collection and telemetry recording
5. Test cost calculations for different models
6. Validate environmental impact calculations

```python
async def test_llm_telemetry():
    # Setup service with telemetry
    telemetry_service = Mock()
    llm_service = OpenAICompatibleClient(
        config=test_config,
        telemetry_service=telemetry_service
    )

    await llm_service.start()

    # Make API call
    response, usage = await llm_service.call_llm_structured(
        messages=[{"role": "user", "content": "test"}],
        response_model=TestModel,
        max_tokens=100
    )

    # Verify telemetry recorded
    telemetry_service.record_metric.assert_called_with(
        "llm_tokens_used", usage.tokens_used
    )

    # Check resource tracking
    assert usage.tokens_used > 0
    assert usage.cost_cents > 0
    assert usage.carbon_grams > 0
    assert usage.model_used == "gpt-4o-mini"

    # Check circuit breaker stats
    cb_stats = llm_service.circuit_breaker.get_stats()
    assert cb_stats["call_count"] == 1
    assert cb_stats["state"] == "closed"
```

## Configuration

### OpenAI Configuration
```python
{
    "api_key": "sk-...",                 # OpenAI API key
    "model_name": "gpt-4o-mini",         # Default model
    "base_url": null,                    # Custom API endpoint
    "instructor_mode": "JSON",           # Parsing mode
    "max_retries": 3,                    # Retry attempts
    "timeout_seconds": 30                # API timeout
}
```

### Circuit Breaker Configuration
```python
{
    "failure_threshold": 5,              # Failures before opening
    "recovery_timeout": 10.0,            # Seconds before testing recovery
    "success_threshold": 2,              # Successes to close circuit
    "timeout_duration": 30.0             # Request timeout
}
```

### Response Cache Configuration
```python
{
    "max_cache_size": 100,               # Maximum cached responses
    "cache_enabled": true                # Cache structured responses
}
```

## Known Limitations

1. **Response Time Tracking**: Average response times not implemented
2. **Cache Hit Rate**: Cache performance metrics not tracked
3. **Rate Limit Monitoring**: API rate limits not monitored from responses
4. **Detailed Error Classification**: Circuit breaker only tracks total failures
5. **Cost Prediction**: No predictive cost modeling for budget planning
6. **Model Comparison**: No A/B testing metrics between models
7. **Memory Usage**: Response cache size estimation may be inaccurate
8. **Historical Data**: No persistent storage of usage history across restarts

## Future Enhancements

1. **Response Time Metrics**: Track and analyze API response latencies
2. **Enhanced Cache Analytics**: Hit rates, memory efficiency, cache eviction metrics
3. **Rate Limit Integration**: Parse rate limit headers from API responses
4. **Detailed Error Taxonomy**: Classify failures by type (timeout, rate limit, auth, etc.)
5. **Cost Budgeting**: Budget tracking, alerts, and automatic throttling
6. **Model Performance Comparison**: A/B testing metrics and model effectiveness
7. **Predictive Analytics**: Usage patterns, cost forecasting, capacity planning
8. **Real-time Dashboards**: Live metrics visualization and alerting
9. **Carbon Offset Tracking**: Integration with carbon offset programs
10. **Multi-provider Support**: Metrics normalization across different LLM providers

## Integration Points

- **TelemetryService**: Records token usage and API call metrics
- **TimeService**: Provides consistent timestamps for all metrics
- **Circuit Breaker**: Fault tolerance and service resilience metrics
- **ResourceMonitor**: Integration with system-wide resource tracking
- **Memory Graph**: Persistent storage of telemetry data via graph nodes
- **API Layer**: Exposes telemetry data via REST endpoints
- **Audit Service**: Records high-level service usage for compliance

## Monitoring Recommendations

1. **Circuit Breaker Alerts**: Alert when state changes to OPEN or success rate < 95%
2. **Cost Monitoring**: Daily/monthly budget alerts and usage trending
3. **Environmental Impact**: Track carbon footprint and set reduction goals
4. **Performance Degradation**: Monitor response times and token efficiency
5. **Cache Efficiency**: Track cache hit rates and memory usage
6. **Model Effectiveness**: Compare token efficiency across different models
7. **Retry Pattern Analysis**: Monitor retry frequency and success patterns
8. **Usage Pattern Detection**: Identify unusual spikes or drops in API usage

## Performance Considerations

1. **Telemetry Overhead**: Metric collection adds ~1-2ms per API call
2. **Circuit Breaker Cost**: State checks are O(1) but add minimal latency
3. **Cache Memory**: Response cache can grow to significant size with large responses
4. **Cost Calculations**: Model-specific pricing calculations add compute overhead
5. **Concurrent Access**: Circuit breaker state is not thread-safe (single-process assumption)
6. **Retry Backoff**: Exponential backoff can extend total request time significantly
7. **Resource Calculation**: Environmental impact calculations are estimates, not precise

## System Integration

The LLM Service is critical for CIRIS's language understanding capabilities:
- Provides structured LLM interactions for all cognitive functions
- Implements responsible AI practices through resource and environmental tracking
- Maintains service resilience through circuit breaker patterns
- Integrates with telemetry system for comprehensive observability
- Supports cost management and budgeting for sustainable operations

The service acts as a "responsible gateway" to LLM capabilities, ensuring that AI interactions are tracked, measured, and managed within ethical and environmental constraints while maintaining high availability and performance.
