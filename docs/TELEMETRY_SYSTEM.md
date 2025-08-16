# CIRIS Telemetry System - v1.4.3

## Current State

### Architecture
- **PULL-based system**: 275 metrics collected on-demand via `get_metrics()` methods
- **PUSH-based storage**: 18 metrics actively stored in TSDB for historical queries
- **Unified endpoint**: `/telemetry/unified` aggregates all metrics with 30-second cache
- **Export formats**: JSON, Prometheus, Graphite

### Metrics Distribution
- **21 core services** each exposing ~10-15 metrics via `get_metrics()`
- **Real-time collection** without persistent storage overhead
- **Historical data** only for critical metrics (LLM usage, costs)

### API Access
```python
# Get all metrics
GET /telemetry/unified

# Get specific metric history (if pushed to TSDB)
GET /telemetry/metrics/{metric_name}

# Get current resource usage
GET /telemetry/resources
```

### Test Coverage
- `telemetry.py`: 75-80% coverage
- 70+ tests across 3 test suites
- All critical paths tested

## Implementation Details

Each service implements a `get_metrics()` method returning a dictionary:
```python
def get_metrics(self) -> Dict[str, Any]:
    return {
        "uptime_seconds": self.uptime(),
        "request_count": self.request_count,
        "error_count": self.error_count,
        "healthy": self.is_healthy()
    }
```

The telemetry service aggregates these on-demand when API endpoints are called.

## Note
This is a lightweight, efficient design for v1.4.3. Most metrics are available real-time without the storage overhead of persisting everything to TSDB.
