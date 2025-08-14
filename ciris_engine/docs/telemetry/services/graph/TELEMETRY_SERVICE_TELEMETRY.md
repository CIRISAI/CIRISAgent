# Telemetry Service Telemetry

## Overview
The Telemetry Service is the central hub for all metrics collection in CIRIS. It implements the "everything is a memory" architecture by storing all telemetry data as graph nodes. This service handles operational metrics, resource usage, behavioral data, and system snapshots.

## Telemetry Data Collected

| Metric Name | Type | Storage | Update Frequency | Access Method |
|------------|------|---------|------------------|---------------|
| metric_nodes_created | counter | graph memory | per metric | graph query |
| metric_types | histogram | graph memory | per metric | graph query |
| cached_metrics | gauge | in-memory dict | real-time | `_recent_metrics` |
| summary_cache_hits | counter | in-memory | on access | internal |
| summary_cache_size | gauge | in-memory dict | on update | `len(_summary_cache)` |
| memory_type_distribution | histogram | graph memory | per consolidation | graph query |
| grace_policies_applied | counter | graph memory | on consolidation | graph query |
| telemetry_snapshots | counter | graph memory | per snapshot | graph query |
| resource_usage_tracked | counter | graph memory | per record | graph query |
| behavioral_data_stored | counter | graph memory | per store | graph query |

## Data Structures

### MetricDataPoint (Cached)
```python
{
    "metric_name": "llm.tokens.total",
    "value": 1523.0,
    "timestamp": "2025-08-14T13:30:00Z",
    "tags": {
        "source": "telemetry",
        "metric_type": "operational",
        "service": "OpenAIClient",
        "handler": "analyze_thought"
    },
    "service_name": "telemetry_service"
}
```

### TSDBGraphNode (Stored in Graph)
```python
{
    "id": "metric-uuid-12345",
    "type": "METRIC",
    "scope": "local",
    "attributes": {
        "metric_name": "llm.tokens.total",
        "value": 1523.0,
        "tags": {
            "source": "telemetry",
            "metric_type": "operational",
            "timestamp": "2025-08-14T13:30:00Z"
        }
    },
    "created_at": "2025-08-14T13:30:00Z"
}
```

### TelemetrySnapshot
```python
{
    "timestamp": "2025-08-14T13:30:00Z",
    "telemetry_data": {
        "metrics_count": 45678,
        "active_services": 24,
        "memory_usage_mb": 1234.5,
        "cpu_percent": 45.6
    },
    "resource_data": {
        "tokens_used": 123456,
        "cost_cents": 4567,
        "carbon_grams": 12.3
    },
    "behavioral_data": {
        "thoughts_processed": 5678,
        "messages_sent": 234,
        "decisions_made": 89
    }
}
```

### ConsolidationCandidate
```python
{
    "memory_ids": ["metric-1", "metric-2", "metric-3"],
    "memory_type": "operational",
    "time_span": "0:06:00:00",  # 6 hours
    "total_size": 45678,
    "grace_applicable": true,
    "grace_reasons": ["forgive_errors", "extend_patience"]
}
```

## API Access Patterns

### Current Access
- **Internal Storage**: Metrics stored as graph nodes via memory bus
- **No Direct API**: No REST endpoints expose telemetry data directly
- **Graph Queries Required**: Must query graph database for metrics

### Recommended Endpoints

#### Get Metric Summary
```
GET /v1/telemetry/metrics/{metric_name}/summary
```
Query parameters:
- `window_minutes`: Time window (default 60)

Returns:
```json
{
    "metric_name": "llm.tokens.total",
    "window_minutes": 60,
    "summary": {
        "count": 234,
        "sum": 45678.0,
        "average": 195.2,
        "min": 10.0,
        "max": 500.0,
        "latest": 234.0
    }
}
```

#### Get Telemetry Snapshot
```
GET /v1/telemetry/snapshot
```
Returns current system telemetry:
```json
{
    "timestamp": "2025-08-14T13:30:00Z",
    "metrics_count": 45678,
    "cached_metrics": 100,
    "summary_cache_size": 25,
    "active_services": 24,
    "memory_usage_mb": 1234.5,
    "cpu_percent": 45.6
}
```

#### Get Metric Count
```
GET /v1/telemetry/metrics/count
```
Returns total metrics in graph:
```json
{
    "total_metrics": 45678,
    "by_type": {
        "operational": 23456,
        "behavioral": 12345,
        "social": 5678,
        "identity": 3456,
        "wisdom": 1023
    }
}
```

## Graph Storage

### Node Types Created
- `METRIC` - All telemetry metrics
- `TELEMETRY_SNAPSHOT` - Periodic system snapshots
- `CONSOLIDATION` - Consolidated metric summaries

### Edge Relationships
- `MEASURED_BY` - Links metric to service
- `CONSOLIDATED_FROM` - Links summary to source metrics
- `GRACE_APPLIED` - Links grace policy to consolidation

### Memory Types
```python
class MemoryType(Enum):
    OPERATIONAL = "operational"  # Metrics, logs, performance
    BEHAVIORAL = "behavioral"    # Actions, decisions, patterns
    SOCIAL = "social"           # Interactions, relationships
    IDENTITY = "identity"       # Self-knowledge, capabilities
    WISDOM = "wisdom"          # Learned principles, insights
```

### Grace Policies
```python
class GracePolicy(Enum):
    FORGIVE_ERRORS = "forgive_errors"          # Consolidate errors into learning
    EXTEND_PATIENCE = "extend_patience"        # Allow more time before judging
    ASSUME_GOOD_INTENT = "assume_good_intent"  # Interpret ambiguity positively
    RECIPROCAL_GRACE = "reciprocal_grace"      # Mirror the grace we receive
```

## Example Usage

### Record a Metric
```python
telemetry_service = get_service(ServiceType.TELEMETRY)

await telemetry_service.record_metric(
    metric_name="custom.metric",
    value=123.45,
    tags={"component": "my_service", "action": "process"},
    handler_name="my_handler"
)
```

### Get Metric Summary
```python
summary = await telemetry_service.get_metric_summary(
    metric_name="llm.tokens.total",
    window_minutes=60
)
print(f"Average tokens: {summary['average']}")
```

### Process System Snapshot
```python
snapshot = SystemSnapshot(
    timestamp=datetime.now(timezone.utc),
    telemetry_data=TelemetryData(...),
    resource_data=ResourceData(...),
    behavioral_data=BehavioralData(...)
)

await telemetry_service.process_snapshot(snapshot)
```

### Store Behavioral Data
```python
behavioral_data = BehavioralData(
    thoughts_processed=100,
    messages_sent=50,
    decisions_made=25
)

await telemetry_service.store_behavioral_context(
    context_id="session-123",
    behavioral_data=behavioral_data
)
```

## Testing

### Test Files
- `tests/logic/services/graph/test_telemetry_service.py` - Service tests
- `tests/integration/test_telemetry_flow.py` - End-to-end tests

### Validation Steps
1. Record metric via `record_metric()`
2. Verify metric appears in graph as METRIC node
3. Check metric in `_recent_metrics` cache
4. Query metric summary
5. Verify consolidation after time window

```python
async def test_telemetry_flow():
    telemetry = get_service(ServiceType.TELEMETRY)

    # Record metric
    await telemetry.record_metric(
        "test.metric",
        value=100.0,
        tags={"test": "true"}
    )

    # Get summary
    summary = await telemetry.get_metric_summary(
        "test.metric",
        window_minutes=5
    )

    assert summary["count"] >= 1
    assert summary["latest"] == 100.0
```

## Configuration

### Cache Settings
```python
{
    "max_cached_metrics": 100,        # Per metric name
    "summary_cache_ttl_seconds": 60,  # Summary cache TTL
}
```

### Consolidation Settings
```python
{
    "consolidation_window_hours": 6,   # When to consolidate
    "min_metrics_for_consolidation": 100,  # Minimum to trigger
    "grace_policy": "forgive_errors",  # Default grace policy
}
```

## Known Limitations

1. **Graph Dependency**: All metrics stored in graph, no time-series DB
2. **Cache Size Limited**: Only 100 recent metrics cached per name
3. **No Aggregation Pipeline**: Must query and aggregate manually
4. **No Metric Expiration**: Metrics never auto-deleted
5. **Single-Node View**: No cross-instance metric aggregation

## Future Enhancements

1. **Time-Series Database**: Add InfluxDB/Prometheus backend
2. **Stream Processing**: Real-time metric aggregation
3. **Metric Retention Policies**: Auto-expire old metrics
4. **Distributed Telemetry**: Aggregate across instances
5. **Custom Dashboards**: Grafana integration
6. **Alerting Rules**: Threshold-based alerts

## Integration Points

- **MemoryBus**: Stores all metrics as graph memories
- **TimeService**: Provides consistent timestamps
- **All Services**: Send metrics here for storage
- **TSDBConsolidationService**: Consolidates old metrics

## Monitoring Recommendations

1. **Metric Growth Rate**: Monitor graph node creation rate
2. **Cache Hit Rate**: Track summary cache effectiveness
3. **Consolidation Success**: Ensure consolidation runs
4. **Memory Usage**: Watch cache memory growth
5. **Query Performance**: Monitor graph query times

## Performance Considerations

1. **Graph Write Load**: Every metric creates a graph node
2. **Cache Memory**: 100 metrics × N names can grow large
3. **No Batching**: Each metric written individually
4. **Graph Query Cost**: Aggregations require full scans
5. **Consolidation Overhead**: Periodic heavy processing

## Architecture Notes

This service implements the patent's vision where "everything is a memory":
- Operational metrics become operational memories
- Resource usage becomes resource memories
- Behavioral patterns become behavioral memories
- All stored in the unified graph with grace-based consolidation

The grace policies ensure that even errors and failures contribute to learning rather than being discarded, embodying the principle that "there is no failure, only feedback."
