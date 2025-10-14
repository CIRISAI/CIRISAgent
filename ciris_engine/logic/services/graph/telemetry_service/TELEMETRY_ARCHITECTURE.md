# CIRIS Telemetry Architecture

## Overview

CIRIS uses a **two-tier telemetry architecture** that balances type safety with simplicity:

- **Tier 1: Message Buses** → Return typed `BusMetrics` (Pydantic models)
- **Tier 2: Services** → Return `Dict[str, float]` → Converted to `ServiceTelemetryData`

This architecture ensures:
✅ Type safety where it matters most (buses handle multi-provider routing)
✅ Simplicity for service implementations (lightweight dict returns)
✅ Centralized conversion and validation (telemetry service)
✅ Backward compatibility (existing patterns preserved)

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                    Telemetry Service                         │
│                  (Central Collector)                         │
└─────────────────────────────────────────────────────────────┘
                          ▲
                          │
         ┌────────────────┴────────────────┐
         │                                  │
    ┌────▼─────┐                     ┌─────▼────┐
    │  Buses   │                     │ Services │
    │  (Tier 1)│                     │ (Tier 2) │
    └────┬─────┘                     └─────┬────┘
         │                                  │
         │ BusMetrics                       │ Dict[str,float]
         │ (Pydantic)                       │
         │                                  │
         └────────────────┬─────────────────┘
                          │
                          ▼
                 ┌────────────────────┐
                 │ ServiceTelemetryData│
                 │    (Pydantic)       │
                 └────────────────────┘
```

---

## Tier 1: Message Buses → BusMetrics

### Why Typed Models?

Message buses require strict typing because they:
- Route between multiple service providers
- Track complex operational metrics
- Expose public APIs for monitoring
- Need validation for distributed systems

### BusMetrics Schema

Location: `ciris_engine/schemas/infrastructure/base.py`

```python
class BusMetrics(BaseModel):
    """Message bus performance metrics."""

    # Standard fields (required for all buses)
    messages_sent: int = Field(0, description="Total messages sent")
    messages_received: int = Field(0, description="Total messages received")
    messages_dropped: int = Field(0, description="Messages dropped")
    average_latency_ms: float = Field(0.0, description="Average message latency")
    active_subscriptions: int = Field(0, description="Number of active subscriptions")
    queue_depth: int = Field(0, description="Current queue depth")
    errors_last_hour: int = Field(0, description="Bus errors in last hour")
    busiest_service: Optional[str] = Field(None, description="Service with most traffic")

    # Bus-specific metrics
    additional_metrics: Dict[str, Union[str, int, float, bool]] = Field(
        default_factory=dict, description="Additional bus metrics"
    )
```

### Buses Returning BusMetrics

All 6 message buses return `BusMetrics`:

1. **MemoryBus** - `ciris_engine/logic/buses/memory_bus.py`
2. **LLMBus** - `ciris_engine/logic/buses/llm_bus.py`
3. **ToolBus** - `ciris_engine/logic/buses/tool_bus.py`
4. **CommunicationBus** - `ciris_engine/logic/buses/communication_bus.py`
5. **WiseBus** - `ciris_engine/logic/buses/wise_bus.py`
6. **RuntimeControlBus** - `ciris_engine/logic/buses/runtime_control_bus.py`

### Implementation Pattern

```python
def get_metrics(self) -> BusMetrics:
    """Get bus metrics as typed BusMetrics schema."""

    # Calculate standard metrics from internal counters
    uptime_seconds = (self._time_service.now() - self._start_time).total_seconds()

    # Return BusMetrics with standard fields
    return BusMetrics(
        messages_sent=self._sent_count,
        messages_received=self._received_count,
        messages_dropped=0,  # Not tracked yet
        average_latency_ms=self._calculate_avg_latency(),
        active_subscriptions=self._count_active_services(),
        queue_depth=self.get_queue_size(),
        errors_last_hour=self._error_count,
        busiest_service=self._find_busiest_service(),

        # Bus-specific metrics in additional_metrics
        additional_metrics={
            "memory_operations_total": self._operation_count,
            "memory_broadcasts": self._broadcast_count,
            "memory_uptime_seconds": uptime_seconds,

            # v1.4.3 compatibility metrics
            "memory_bus_operations": self._operation_count,
            "memory_bus_broadcasts": self._broadcast_count,
            "memory_bus_errors": self._error_count,
        },
    )
```

### Key Patterns

✅ **Standard fields first** - Use BusMetrics fields for common metrics
✅ **additional_metrics for specifics** - Bus-unique metrics go here
✅ **Backward compatibility** - Include legacy metric names
✅ **Uptime tracking** - All buses track uptime_seconds
✅ **Error counting** - Track errors in errors_last_hour

---

## Tier 2: Services → Dict[str, float]

### Why Dicts?

Services use simple dicts because they:
- Have straightforward metrics (counters, gauges)
- Don't need complex routing logic
- Benefit from lightweight implementations
- Are converted centrally by telemetry service

### ServiceTelemetryData Schema

Location: `ciris_engine/schemas/services/telemetry.py`

```python
class ServiceTelemetryData(BaseModel):
    """Standard telemetry data for all services."""

    healthy: bool = True
    uptime_seconds: float = 0.0
    error_count: int = 0
    requests_handled: int = 0
    error_rate: float = 0.0
    memory_mb: Optional[float] = None
    custom_metrics: Optional[Dict[str, Union[str, int, float, bool]]] = None
```

### Services Returning Dict[str, float]

**Graph Services (6):**
- ✅ incident_service
- ✅ tsdb_consolidation
- ✅ config_service
- ✅ audit_service
- ✅ telemetry_service
- ⚠️ memory_service (uses base implementation)

**Lifecycle Services (4):**
- ✅ scheduler
- ✅ time
- ✅ initialization
- ✅ shutdown

**Governance Services (5):**
- ✅ self_observation
- ✅ adaptive_filter
- ⚠️ wise_authority (uses get_status())
- ⚠️ consent (uses base implementation)
- ⚠️ visibility (uses base implementation)

**Runtime Services (2):**
- ✅ control_service
- ✅ llm_service

**Infrastructure Services (4):**
- ✅ database_maintenance
- ✅ authentication
- ⚠️ resource_monitor (uses get_status())
- ⚠️ secrets (uses base implementation)

**Tool Services (1):**
- ✅ secrets_tool_service

### Implementation Pattern

```python
async def get_metrics(self) -> Dict[str, float]:
    """Return service metrics as dict."""

    # Calculate uptime
    uptime = (self._time_service.now() - self._start_time).total_seconds()

    # Return flat dict of metrics
    return {
        "uptime_seconds": uptime,
        "requests_handled": self._request_count,
        "error_count": self._error_count,
        "error_rate": self._calculate_error_rate(),

        # Service-specific metrics
        "incidents_active": len(self._active_incidents),
        "incidents_resolved": self._resolved_count,
        "average_resolution_time": self._avg_resolution_time,
    }
```

### Key Patterns

✅ **Flat dictionary** - Simple key-value pairs
✅ **Snake_case naming** - Consistent naming convention
✅ **Float values** - All metrics as floats (even counters)
✅ **Uptime tracking** - Include uptime_seconds
✅ **Category prefixes** - Use category name in keys (e.g., "incidents_active")

---

## Telemetry Service Conversion

Location: `ciris_engine/logic/services/graph/telemetry_service/service.py`

### How Conversion Works

```python
async def _try_collect_metrics(self, service: Any) -> Optional[ServiceTelemetryData]:
    """Try different methods to collect metrics from service."""

    # 1. Try get_metrics() first (most common)
    result = await self._try_get_metrics_method(service)
    if result:
        return result

    # 2. Try _collect_metrics() (fallback)
    result = self._try_collect_metrics_method(service)
    if result:
        return result

    # 3. Try get_status() (last resort)
    return await self._try_get_status_method(service)
```

### BusMetrics → ServiceTelemetryData

```python
# Buses return BusMetrics (Pydantic model)
metrics_result = bus.get_metrics()

# Convert to dict
if hasattr(metrics_result, "model_dump"):
    metrics = metrics_result.model_dump()

    # Merge additional_metrics into top-level for backward compatibility
    if "additional_metrics" in metrics:
        additional = metrics.pop("additional_metrics")
        metrics.update(additional)
else:
    # Fallback for any remaining dict returns
    metrics = metrics_result

# Convert to ServiceTelemetryData
return ServiceTelemetryData(
    healthy=is_healthy,
    uptime_seconds=metrics.get("uptime_seconds", 0.0),
    error_count=metrics.get("error_count", 0),
    requests_handled=metrics.get("messages_sent", 0),
    error_rate=metrics.get("error_rate", 0.0),
    memory_mb=metrics.get("memory_mb"),
    custom_metrics=metrics,  # Full dict for custom fields
)
```

### Dict[str, float] → ServiceTelemetryData

```python
def _try_collect_metrics_method(self, service: Any) -> Optional[ServiceTelemetryData]:
    """Try to collect metrics via _collect_metrics() method."""

    try:
        metrics = service._collect_metrics()

        # Convert dict to ServiceTelemetryData
        if isinstance(metrics, dict):
            return ServiceTelemetryData(
                healthy=True,
                uptime_seconds=metrics.get("uptime_seconds", 0.0),
                error_count=metrics.get("error_count", 0),
                requests_handled=metrics.get("requests_handled", 0),
                error_rate=metrics.get("error_rate", 0.0),
                memory_mb=metrics.get("memory_mb"),
                custom_metrics=metrics.get("custom_metrics"),
            )
    except Exception as e:
        logger.error(f"Error calling _collect_metrics: {e}")

    return None
```

---

## Best Practices

### For Bus Implementations

✅ **Always return BusMetrics**
❌ Never return `Dict[str, Any]` or untyped dicts

✅ **Use standard fields**
```python
messages_sent=self._sent_count,  # ✅ Standard field
additional_metrics={"custom_field": 123}  # ✅ Bus-specific
```

✅ **Include backward compatibility**
```python
additional_metrics={
    "memory_operations_total": self._count,  # New metric
    "memory_bus_operations": self._count,    # v1.4.3 compat
}
```

✅ **Track uptime**
```python
uptime_seconds = (self._time_service.now() - self._start_time).total_seconds()
```

### For Service Implementations

✅ **Return Dict[str, float]**
```python
async def get_metrics(self) -> Dict[str, float]:
    return {
        "uptime_seconds": self._uptime,
        "requests_handled": self._requests,
    }
```

✅ **Use consistent naming**
- `{category}_{metric_name}` for service-specific metrics
- `uptime_seconds`, `error_count`, `error_rate` for standard metrics

✅ **All values as floats**
```python
"request_count": float(self._requests),  # ✅ Cast to float
"error_count": float(self._errors),      # ✅ Even counters
```

❌ **Avoid complex types**
```python
return {
    "data": self._complex_object,  # ❌ No objects
    "list": [1, 2, 3],            # ❌ No lists
}
```

### For Adding New Metrics

1. **Identify the category**
   - Is this a bus or service?
   - What category does it belong to?

2. **Choose the right pattern**
   - Buses → Add to `additional_metrics` in `BusMetrics`
   - Services → Add to `Dict[str, float]` return

3. **Follow naming conventions**
   - Use snake_case
   - Prefix with category name
   - Be descriptive but concise

4. **Document the metric**
   - Add docstring explaining what it measures
   - Include units (seconds, bytes, count, etc.)
   - Note if it's cumulative or instantaneous

---

## Migration Guide

### Converting a Service to Return BusMetrics

**Before:**
```python
async def get_metrics(self) -> Dict[str, float]:
    return {
        "operations_total": float(self._ops),
        "errors_total": float(self._errors),
    }
```

**After:**
```python
def get_metrics(self) -> BusMetrics:
    return BusMetrics(
        messages_sent=self._ops,
        messages_received=self._ops,
        messages_dropped=0,
        average_latency_ms=0.0,
        active_subscriptions=self._count_subscriptions(),
        queue_depth=self.get_queue_size(),
        errors_last_hour=self._errors,
        busiest_service=None,
        additional_metrics={
            "operations_total": self._ops,
            "errors_total": self._errors,
        },
    )
```

### Adding Backward Compatibility

Always include legacy metric names in `additional_metrics`:

```python
additional_metrics={
    # New metrics
    "memory_operations_total": self._operation_count,
    "memory_broadcasts": self._broadcast_count,

    # v1.4.3 compatibility
    "memory_bus_operations": self._operation_count,
    "memory_bus_broadcasts": self._broadcast_count,
}
```

---

## Testing Telemetry

### Unit Tests

```python
def test_get_metrics_returns_bus_metrics():
    """Test that bus returns typed BusMetrics."""
    bus = MemoryBus(mock_registry, mock_time_service)

    metrics = bus.get_metrics()

    # Check type
    assert isinstance(metrics, BusMetrics)

    # Check standard fields
    assert isinstance(metrics.messages_sent, int)
    assert isinstance(metrics.average_latency_ms, float)

    # Check additional metrics
    metrics_dict = metrics.model_dump()
    assert "memory_operations_total" in metrics_dict["additional_metrics"]
```

### Integration Tests

```python
async def test_telemetry_service_collects_from_bus():
    """Test that telemetry service can collect from bus."""
    telemetry_service = TelemetryService(runtime)

    # Collect from memory bus
    result = await telemetry_service.collect_from_bus("memory_bus")

    # Should return ServiceTelemetryData
    assert isinstance(result, ServiceTelemetryData)
    assert result.healthy is True
    assert "memory_operations_total" in result.custom_metrics
```

---

## Troubleshooting

### Issue: "AttributeError: 'dict' object has no attribute 'model_dump'"

**Cause:** Service is returning `Dict[str, float]` instead of `BusMetrics`

**Solution:** If this is a bus, convert to return `BusMetrics`. If this is a service, this is expected behavior.

### Issue: "Validation error for BusMetrics"

**Cause:** Missing required fields or wrong types

**Solution:** Ensure all standard BusMetrics fields are provided:
```python
BusMetrics(
    messages_sent=0,           # Required
    messages_received=0,        # Required
    messages_dropped=0,         # Required
    average_latency_ms=0.0,    # Required
    active_subscriptions=0,     # Required
    queue_depth=0,             # Required
    errors_last_hour=0,        # Required
    busiest_service=None,      # Optional
    additional_metrics={},     # Optional
)
```

### Issue: "Metrics not appearing in telemetry endpoint"

**Cause:** Telemetry service can't find the service or method

**Solution:** Ensure service implements one of:
1. `async def get_metrics(self) -> Dict[str, float]`
2. `def _collect_metrics(self) -> Dict[str, float]`
3. `def get_status(self) -> ServiceStatus`

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.3.1 | 2025-01-13 | All 6 buses converted to return BusMetrics |
| 1.4.3 | 2024-xx-xx | Previous version using Dict[str, float] for buses |

---

## See Also

- `ciris_engine/schemas/infrastructure/base.py` - BusMetrics definition
- `ciris_engine/schemas/services/telemetry.py` - ServiceTelemetryData definition
- `ciris_engine/logic/buses/` - All bus implementations
- `ciris_engine/logic/services/` - All service implementations
- `tests/test_buses_coverage_simple.py` - Bus metrics testing examples
