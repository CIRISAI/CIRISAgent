# Telemetry Best Practices

Quick reference guide for implementing telemetry in CIRIS services and buses.

## Quick Decision Tree

```
Are you implementing a message bus?
├─ YES → Return BusMetrics (Pydantic model)
└─ NO  → Return Dict[str, float]
```

---

## For Message Buses

### ✅ DO

```python
from ciris_engine.schemas.infrastructure.base import BusMetrics

def get_metrics(self) -> BusMetrics:
    """Get bus metrics as typed BusMetrics schema."""
    return BusMetrics(
        messages_sent=self._sent_count,
        messages_received=self._received_count,
        messages_dropped=0,
        average_latency_ms=0.0,
        active_subscriptions=len(self._subscribers),
        queue_depth=self.get_queue_size(),
        errors_last_hour=self._error_count,
        busiest_service=None,
        additional_metrics={
            "bus_specific_metric": self._custom_value,
            "bus_uptime_seconds": self._calculate_uptime(),
        },
    )
```

### ❌ DON'T

```python
# ❌ Don't return dict from buses
async def get_metrics(self) -> Dict[str, float]:
    return {"messages_sent": self._count}

# ❌ Don't return Dict[str, Any]
def get_metrics(self) -> Dict[str, Any]:
    return {"data": self._complex_object}

# ❌ Don't skip standard fields
def get_metrics(self) -> BusMetrics:
    return BusMetrics(
        messages_sent=self._count,
        # Missing required fields!
    )
```

---

## For Services

### ✅ DO

```python
async def get_metrics(self) -> Dict[str, float]:
    """Return service metrics as dict."""
    uptime = (self._time_service.now() - self._start_time).total_seconds()

    return {
        # Standard metrics
        "uptime_seconds": uptime,
        "requests_handled": float(self._requests),
        "error_count": float(self._errors),
        "error_rate": self._calculate_error_rate(),

        # Service-specific metrics (prefixed with category)
        "incidents_active": float(len(self._active_incidents)),
        "incidents_resolved": float(self._resolved_count),
    }
```

### ❌ DON'T

```python
# ❌ Don't return complex types
async def get_metrics(self) -> Dict[str, Any]:
    return {
        "incidents": self._incident_list,  # No objects!
        "data": [1, 2, 3],                 # No lists!
    }

# ❌ Don't use inconsistent naming
async def get_metrics(self) -> Dict[str, float]:
    return {
        "UptimeSeconds": self._uptime,     # Use snake_case
        "RequestCount": self._requests,    # Not PascalCase
    }

# ❌ Don't forget to cast to float
async def get_metrics(self) -> Dict[str, float]:
    return {
        "count": self._count,  # Should be float(self._count)
    }
```

---

## Standard Metric Names

### Required for All Services

```python
{
    "uptime_seconds": 123.45,      # Time since service started
    "requests_handled": 1000.0,    # Total requests processed
    "error_count": 5.0,            # Total errors encountered
    "error_rate": 0.005,           # Error rate (0.0 - 1.0)
}
```

### Optional but Recommended

```python
{
    "memory_mb": 256.0,            # Memory usage in megabytes
    "queue_depth": 10.0,           # Current queue size
    "active_connections": 5.0,     # Active connections/subscriptions
}
```

### Category-Specific Naming

Use `{category}_{metric}` format:

```python
# Graph Services
{
    "memory_operations_total": 1000.0,
    "memory_broadcasts": 50.0,
}

# Communication Services
{
    "communication_messages_sent": 500.0,
    "communication_broadcasts": 25.0,
}

# LLM Services
{
    "llm_requests_total": 100.0,
    "llm_tokens_used": 50000.0,
}
```

---

## Backward Compatibility

Always include v1.4.3 metric names in `additional_metrics`:

```python
additional_metrics={
    # New metrics (v1.3.1+)
    "memory_operations_total": self._operations,
    "memory_broadcasts": self._broadcasts,
    "memory_uptime_seconds": uptime,

    # Legacy metrics (v1.4.3 compatibility)
    "memory_bus_operations": self._operations,
    "memory_bus_broadcasts": self._broadcasts,
    "memory_bus_errors": self._errors,
}
```

---

## Testing Checklist

### For Buses

- [ ] Returns `BusMetrics` type (not dict)
- [ ] All standard fields populated
- [ ] Bus-specific metrics in `additional_metrics`
- [ ] Backward compatibility metrics included
- [ ] Can be serialized with `.model_dump()`
- [ ] Test passes: `isinstance(metrics, BusMetrics)`

### For Services

- [ ] Returns `Dict[str, float]`
- [ ] All values are floats (not ints or other types)
- [ ] Uses snake_case naming
- [ ] Includes `uptime_seconds`
- [ ] Category-prefixed metric names
- [ ] No complex objects or lists in values

### Unit Test Template

```python
def test_service_get_metrics(mock_registry, mock_time_service):
    """Test service metrics collection."""
    service = MyService(mock_registry, mock_time_service)

    # Collect metrics
    metrics = await service.get_metrics()

    # Verify type
    assert isinstance(metrics, dict)

    # Verify required fields
    assert "uptime_seconds" in metrics
    assert "requests_handled" in metrics
    assert "error_count" in metrics

    # Verify types
    assert isinstance(metrics["uptime_seconds"], float)
    assert isinstance(metrics["error_count"], float)

    # Verify category-specific metrics
    assert "myservice_custom_metric" in metrics
```

---

## Common Pitfalls

### 1. Wrong Return Type

```python
# ❌ Bus returning dict
class MyBus(BaseBus):
    async def get_metrics(self) -> Dict[str, float]:  # Wrong!
        return {"count": 1.0}

# ✅ Bus returning BusMetrics
class MyBus(BaseBus):
    def get_metrics(self) -> BusMetrics:  # Correct!
        return BusMetrics(...)
```

### 2. Missing Standard Fields

```python
# ❌ Missing required BusMetrics fields
return BusMetrics(
    messages_sent=100,
    # Where are the other fields?
)

# ✅ All standard fields provided
return BusMetrics(
    messages_sent=100,
    messages_received=100,
    messages_dropped=0,
    average_latency_ms=0.0,
    active_subscriptions=5,
    queue_depth=0,
    errors_last_hour=2,
    busiest_service=None,
    additional_metrics={},
)
```

### 3. Non-Float Values

```python
# ❌ Integer values
return {
    "count": 100,  # Should be 100.0
}

# ✅ Float values
return {
    "count": float(100),  # or 100.0
}
```

### 4. Inconsistent Naming

```python
# ❌ Mixed naming conventions
return {
    "UptimeSeconds": 123.0,
    "request_count": 100.0,
    "ErrorRate": 0.01,
}

# ✅ Consistent snake_case
return {
    "uptime_seconds": 123.0,
    "request_count": 100.0,
    "error_rate": 0.01,
}
```

---

## Metric Collection Priority

The telemetry service tries these methods in order:

1. **`async def get_metrics(self) -> Dict[str, float]`** ← Preferred
2. **`def _collect_metrics(self) -> Dict[str, float]`** ← Fallback
3. **`def get_status(self) -> ServiceStatus`** ← Last resort

Always implement `get_metrics()` for new services.

---

## Quick Reference

### Bus Implementation

```python
from ciris_engine.schemas.infrastructure.base import BusMetrics

class MyBus(BaseBus):
    def get_metrics(self) -> BusMetrics:
        return BusMetrics(
            messages_sent=self._sent,
            messages_received=self._received,
            messages_dropped=0,
            average_latency_ms=0.0,
            active_subscriptions=len(self._subs),
            queue_depth=self.get_queue_size(),
            errors_last_hour=self._errors,
            busiest_service=None,
            additional_metrics={
                "mybus_custom": self._custom,
            },
        )
```

### Service Implementation

```python
class MyService(BaseService):
    async def get_metrics(self) -> Dict[str, float]:
        uptime = (self._time.now() - self._start).total_seconds()

        return {
            "uptime_seconds": uptime,
            "requests_handled": float(self._requests),
            "error_count": float(self._errors),
            "error_rate": self._calc_error_rate(),
            "myservice_custom": float(self._custom),
        }
```

---

## Need Help?

- See `TELEMETRY_ARCHITECTURE.md` for detailed explanations
- Check `ciris_engine/schemas/infrastructure/base.py` for BusMetrics definition
- Check `ciris_engine/schemas/services/telemetry.py` for ServiceTelemetryData
- Look at existing bus implementations in `ciris_engine/logic/buses/`
- Review tests in `tests/test_buses_coverage_simple.py`
