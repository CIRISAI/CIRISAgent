# Wise Bus Telemetry

## Overview
The Wise Bus manages all Wise Authority (WA) operations including deferral broadcasting, guidance requests, and capability validation. It features medical domain prohibition, multi-provider fan-out, response arbitration, and wisdom extension capabilities for non-medical domains (geo, weather, sensor).

## Telemetry Data Collected

### Bus-Level Metrics (Inherited from BaseBus)

| Metric Name | Type | Storage | Update Frequency | Access Method |
|------------|------|---------|------------------|---------------|
| processed_count | counter | in-memory | per-message | `get_stats()` |
| failed_count | counter | in-memory | on-error | `get_stats()` |
| queue_size | gauge | in-memory | real-time | `get_queue_size()` |
| running | boolean | in-memory | on-demand | `get_stats()` |
| service_type | enum | in-memory | static | `get_stats()` |

### WiseBus-Specific Metrics (Currently Not Exposed)

| Metric Name | Type | Storage | Update Frequency | Access Method |
|------------|------|---------|------------------|---------------|
| deferral_broadcast_count | counter | none | per-broadcast | not exposed |
| successful_deferrals | counter | none | per-success | not exposed |
| guidance_request_count | counter | none | per-request | not exposed |
| guidance_response_count | counter | none | per-response | not exposed |
| blocked_medical_requests | counter | none | per-block | not exposed |
| provider_count | gauge | none | per-operation | not exposed |
| arbitration_conflicts | counter | none | per-arbitration | not exposed |
| capability_validation_failures | counter | none | per-validation | not exposed |
| multi_provider_responses | counter | none | per-guidance | not exposed |
| timeout_count | counter | none | per-timeout | not exposed |
| average_response_time_ms | gauge | none | per-guidance | not exposed |

### Medical Blocking Metrics (Implicit)

| Metric Name | Type | Storage | Update Frequency | Access Method |
|------------|------|---------|------------------|---------------|
| blocked_capabilities | counter | none | per-block | not exposed |
| prohibited_terms_detected | counter | none | per-detection | not exposed |
| medical_domain_rejections | counter | none | per-rejection | not exposed |

## Data Structures

### Bus Statistics (from BaseBus)
```python
{
    "service_type": "WISE_AUTHORITY",        # Fixed service type
    "queue_size": 0,                         # Current message queue size
    "processed": 1523,                       # Total messages processed
    "failed": 12,                            # Failed message processing
    "running": True                          # Bus processing status
}
```

### Deferral Broadcast Statistics (Potential)
```python
{
    "total_deferrals_sent": 1234,            # All deferral broadcasts
    "successful_broadcasts": 1198,           # At least one service received
    "failed_broadcasts": 36,                 # No services received
    "average_services_per_broadcast": 2.3,   # Services reached per deferral
    "broadcast_success_rate": "97.08%"       # Success rate percentage
}
```

### Guidance Request Statistics (Potential)
```python
{
    "total_guidance_requests": 5678,         # All guidance requests
    "successful_responses": 5234,            # Successful responses
    "timeout_failures": 234,                # Timed out requests
    "capability_matches": 4567,              # Capability-matched requests
    "fallback_requests": 1111,               # Fallback to basic guidance
    "average_response_time_ms": 1247.5,      # Mean response latency
    "multi_provider_requests": 2345          # Requests with multiple providers
}
```

### Medical Blocking Statistics (Potential)
```python
{
    "blocked_requests": 23,                  # Medical capability blocks
    "prohibited_capabilities": [             # Most common blocked terms
        "domain:medical",
        "domain:health",
        "domain:diagnosis"
    ],
    "block_rate": "0.40%",                  # Percentage of requests blocked
    "last_block_timestamp": "2025-08-14T13:30:00Z"
}
```

### Response Arbitration Metrics (Potential)
```python
{
    "arbitration_events": 1234,             # Multi-response arbitrations
    "confidence_based_selections": 987,     # Confidence-based choices
    "single_response_cases": 3456,          # No arbitration needed
    "average_response_count": 2.1,          # Responses per arbitration
    "highest_confidence_selected": 0.95     # Best confidence seen
}
```

## API Access Patterns

### Current Access
- **Limited Bus Metrics**: Only inherited BaseBus metrics via `get_stats()`
- **No WA-Specific Metrics**: Deferral, guidance, blocking metrics not exposed
- **No Medical Blocking Stats**: Prohibited capability metrics not tracked
- **No Performance Metrics**: Response times, arbitration data not available

### Recommended Endpoints

#### Wise Authority Operations Summary
```
GET /v1/telemetry/wise/summary
```
Returns aggregated WA operation statistics:
```json
{
    "bus_status": {
        "service_type": "WISE_AUTHORITY",
        "queue_size": 0,
        "processed": 1523,
        "failed": 12,
        "running": true
    },
    "deferrals": {
        "total_sent": 234,
        "successful_broadcasts": 228,
        "average_services_reached": 2.3,
        "success_rate": "97.44%"
    },
    "guidance": {
        "total_requests": 1567,
        "successful_responses": 1489,
        "timeout_count": 45,
        "average_response_time_ms": 1247.5,
        "multi_provider_count": 789
    },
    "medical_blocking": {
        "blocked_requests": 23,
        "block_rate": "1.47%",
        "most_blocked_terms": [
            "domain:medical",
            "domain:health"
        ]
    }
}
```

#### Medical Domain Blocking Stats
```
GET /v1/telemetry/wise/blocking
```
Returns medical domain blocking statistics:
```json
{
    "total_blocked": 23,
    "block_rate": "1.47%",
    "prohibited_capabilities": [
        {
            "term": "domain:medical",
            "count": 8,
            "last_seen": "2025-08-14T13:30:00Z"
        },
        {
            "term": "domain:health",
            "count": 6,
            "last_seen": "2025-08-14T12:45:00Z"
        }
    ],
    "blocked_requests_by_hour": {
        "2025-08-14T13:00:00Z": 3,
        "2025-08-14T12:00:00Z": 5
    }
}
```

#### Provider and Capability Stats
```
GET /v1/telemetry/wise/providers
```
Returns provider distribution and capability statistics:
```json
{
    "registered_providers": {
        "total": 3,
        "healthy": 3,
        "capabilities": [
            "domain:navigation",
            "domain:weather",
            "domain:translation"
        ]
    },
    "capability_usage": {
        "domain:navigation": {
            "requests": 567,
            "success_rate": "98.94%"
        },
        "domain:weather": {
            "requests": 234,
            "success_rate": "97.44%"
        }
    },
    "arbitration_stats": {
        "multi_response_cases": 123,
        "confidence_selections": 98,
        "average_confidence": 0.87
    }
}
```

## Graph Storage

The WiseBus currently does not store telemetry data in the memory graph, but could potentially create:

### Proposed Metric Nodes
- Type: `METRIC`
- Properties: `metric_name`, `value`, `timestamp`, `handler_name`, `tags`
- Tags: `wise_authority`, `deferral`, `guidance`, `medical_blocking`

### Proposed Edge Relationships
- `MEASURED_BY` - Links metrics to WiseBus operations
- `BLOCKED_BY` - Links blocked requests to prohibition reasons
- `ARBITRATED_BY` - Links guidance responses to arbitration decisions
- `DEFERRED_TO` - Links deferrals to WA services

### Proposed CIRIS Memory Integration
```python
# Telemetry data that could be memorized
await self.memorize_metric("wise.deferrals.total", total_count, {
    "services_reached": len(services),
    "success": any_success,
    "handler": handler_name
})

await self.memorize_metric("wise.guidance.response_time", latency_ms, {
    "provider_count": len(responses),
    "arbitrated": len(responses) > 1,
    "capability": request.capability
})

await self.memorize_metric("wise.blocking.medical", 1, {
    "blocked_capability": capability,
    "prohibited_term": matched_term,
    "handler": handler_name
})
```

## Example Usage

### Get Basic Bus Stats
```python
# Current functionality
wise_bus = service_registry.get_service(ServiceType.WISE_AUTHORITY)
stats = wise_bus.get_stats()
# Returns: {"service_type": "WISE_AUTHORITY", "queue_size": 0, "processed": 1523, ...}
```

### Check Medical Blocking (Manual)
```python
# Test capability validation
try:
    wise_bus._validate_capability("domain:medical")
except ValueError as e:
    # Blocked - would increment blocking counter if tracked
    logger.info(f"Medical capability blocked: {e}")
```

### Monitor Deferral Success
```python
# Send deferral and check result
context = DeferralContext(
    thought_id="test_123",
    task_id="task_456",
    reason="Needs WA review"
)
success = await wise_bus.send_deferral(context, "handler_name")
# Success indicates at least one WA service received the deferral
```

### Guidance Request with Capability
```python
# Request guidance with capability filtering
request = GuidanceRequest(
    context="Navigate to destination",
    options=["Route A", "Route B"],
    capability="domain:navigation"
)
response = await wise_bus.request_guidance(request, timeout=10.0)
# Response includes arbitration from multiple providers if available
```

## Testing

### Test Files
- `tests/logic/buses/test_wise_bus_medical_blocking.py` - Comprehensive medical blocking tests
- `tests/logic/buses/test_wise_bus_safe_domains.py` - Safe domain capability tests

### Validation Steps for Telemetry
1. Send deferral to multiple WA services
2. Verify broadcast success metrics update
3. Request guidance with valid capability
4. Check response time tracking
5. Test medical capability blocking
6. Confirm prohibition metrics increment
7. Test multi-provider arbitration
8. Validate confidence-based selection metrics

```python
# Example validation test
async def test_wise_bus_telemetry():
    wise_bus = get_service(ServiceType.WISE_AUTHORITY)

    # Get initial stats
    initial_stats = wise_bus.get_stats()
    initial_processed = initial_stats["processed"]

    # Send a deferral
    context = DeferralContext(
        thought_id="test_thought",
        task_id="test_task",
        reason="Test deferral"
    )

    success = await wise_bus.send_deferral(context, "test_handler")

    # Check if processing occurred (current functionality)
    # In future: check deferral-specific metrics
    updated_stats = wise_bus.get_stats()
    # Note: Deferrals don't go through message queue, so processed count won't change

    # Test medical blocking
    medical_blocked = False
    try:
        wise_bus._validate_capability("domain:medical")
    except ValueError:
        medical_blocked = True
        # In future: check blocking counter incremented

    assert medical_blocked, "Medical capability should be blocked"
```

## Configuration

### Timeout Settings
```python
{
    "guidance_timeout_seconds": 5.0,        # Default guidance request timeout
    "deferral_default_hours": 1,            # Default defer duration
    "max_providers": 5                       # Prevent unbounded fan-out
}
```

### Medical Blocking Configuration
The `PROHIBITED_CAPABILITIES` set is hardcoded and includes:
- Domain prefixes: `domain:medical`, `domain:health`, etc.
- Modality prefixes: `modality:medical`
- Provider prefixes: `provider:medical`
- Direct terms: `medical`, `health`, `clinical`, etc.

## Known Limitations

1. **No Telemetry Collection**: WiseBus doesn't currently collect operation-specific metrics
2. **No Performance Tracking**: Response times, arbitration latencies not measured
3. **No Medical Blocking Stats**: Prohibited capability attempts not tracked
4. **No Provider Health Metrics**: WA service availability not monitored
5. **No Historical Data**: Only current bus state available, no trending
6. **Queue Not Used**: WA operations are synchronous, so queue metrics not meaningful
7. **No Capability Analytics**: Usage patterns by capability not tracked

## Future Enhancements

1. **Operation Metrics Collection**: Track deferrals, guidance requests, blocking events
2. **Performance Monitoring**: Measure response times, arbitration latencies
3. **Provider Health Dashboard**: Monitor WA service availability and performance
4. **Medical Blocking Analytics**: Track prohibited attempts and patterns
5. **Capability Usage Statistics**: Analyze capability request patterns
6. **Multi-Provider Insights**: Arbitration success rates, confidence distributions
7. **Real-time Alerting**: Alert on high failure rates or blocking attempts
8. **Historical Trending**: Time-series data for performance analysis
9. **Graph Integration**: Store telemetry in memory graph for correlation
10. **Compliance Reporting**: Medical blocking compliance reports for audits

## Integration Points

- **ServiceRegistry**: Discovers and validates WA service capabilities
- **TimeService**: Provides timestamps for deferrals and metrics
- **TelemetryService**: Potential integration for storing WA metrics in graph
- **AuditService**: May audit deferral decisions and guidance requests
- **WiseAuthority Services**: Multiple providers for guidance and deferrals

## Monitoring Recommendations

1. **Medical Blocking Alerts**: Monitor prohibited capability attempts
2. **Deferral Success Rates**: Track broadcast success to WA services
3. **Guidance Response Times**: Alert on elevated latencies
4. **Provider Health**: Monitor WA service availability
5. **Arbitration Effectiveness**: Track multi-provider response quality
6. **Capability Coverage**: Ensure adequate provider coverage for domains
7. **Compliance Monitoring**: Verify medical domain blocking effectiveness

## Wisdom Extension System (FSD-019)

The WiseBus is central to the wisdom extension capability system:

### Supported Safe Domains
- **Geographic**: `domain:navigation`, `domain:geo`
- **Environmental**: `domain:weather`, `domain:sensor`
- **Communication**: `domain:translation`, `domain:transcription`
- **Security**: `domain:security`, `domain:compliance`

### Medical Domain Firewall
- **Hard Block**: All medical/health capabilities prohibited at bus level
- **Case Insensitive**: Blocking works regardless of case
- **Substring Matching**: Partial matches of medical terms blocked
- **Clear Error Messages**: Provides actionable guidance on prohibition

### Multi-Provider Architecture
- **Fan-out**: Requests sent to multiple matching providers
- **Timeout Management**: Configurable response timeout (default 5s)
- **Arbitration**: Confidence-based selection of best response
- **Graceful Degradation**: Fallback to single provider if multi-provider fails

This telemetry documentation provides a comprehensive view of the WiseBus capabilities and identifies areas for enhanced monitoring to support the wisdom extension system while maintaining medical domain prohibition.
