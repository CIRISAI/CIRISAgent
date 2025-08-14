# TSDB Consolidation Service Telemetry

## Overview

The TSDB Consolidation Service is responsible for consolidating telemetry and memory data into permanent summary records for long-term storage (1000+ years). It runs automated consolidation cycles at three levels:

- **Basic (6-hour)**: Consolidates raw TSDB data, audit entries, traces, conversations, and tasks
- **Extensive (weekly)**: Consolidates basic summaries into daily summaries
- **Profound (monthly)**: Compresses daily summaries to meet storage targets

This service implements the "everything is a memory" architecture by creating permanent graph nodes with proper edge relationships for navigation and discovery.

## Telemetry Data Collected

| Metric Name | Type | Storage | Update Frequency | Access Method |
|------------|------|---------|------------------|---------------|
| last_consolidation_timestamp | timestamp | service status | after basic consolidation | `get_status()` |
| task_running | gauge | service status | real-time | `get_status()` |
| last_basic_consolidation | timestamp | service status | after basic consolidation | `get_status()` |
| last_extensive_consolidation | timestamp | service status | after extensive consolidation | `get_status()` |
| last_profound_consolidation | timestamp | service status | after profound consolidation | `get_status()` |
| basic_task_running | gauge | service status | real-time | `get_status()` |
| extensive_task_running | gauge | service status | real-time | `get_status()` |
| profound_task_running | gauge | service status | real-time | `get_status()` |
| basic_interval_hours | constant | service status | startup | `get_status()` |
| extensive_interval_days | constant | service status | startup | `get_status()` |
| profound_interval_days | constant | service status | startup | `get_status()` |
| profound_target_mb_per_day | constant | service status | startup | `get_status()` |
| memory_bus_available | gauge | base service | real-time | `get_status()` |
| time_service_available | gauge | base service | real-time | `get_status()` |
| consolidation_periods_processed | counter | operation logs | per consolidation | log analysis |
| total_records_processed | counter | operation logs | per consolidation | log analysis |
| total_summaries_created | counter | operation logs | per consolidation | log analysis |
| compression_ratio | histogram | operation logs | per consolidation | log analysis |
| nodes_deleted | counter | operation logs | per cleanup | log analysis |
| edges_deleted | counter | operation logs | per cleanup | log analysis |
| consolidation_duration_seconds | histogram | operation logs | per consolidation | log analysis |

## Data Structures

### ServiceStatus (Runtime Metrics)
```python
{
    "service_name": "TSDBConsolidationService",
    "service_type": "graph_service",
    "is_healthy": true,
    "uptime_seconds": 3600.0,
    "metrics": {
        "last_consolidation_timestamp": 1723636800.0,
        "task_running": 1.0,
        "last_basic_consolidation": 1723636800.0,
        "last_extensive_consolidation": 1723550400.0,
        "last_profound_consolidation": 1721001600.0,
        "basic_task_running": 1.0,
        "extensive_task_running": 0.0,
        "profound_task_running": 0.0
    },
    "last_error": null,
    "last_health_check": "2025-08-14T13:30:00Z",
    "custom_metrics": {
        "basic_interval_hours": 6.0,
        "extensive_interval_days": 7.0,
        "profound_interval_days": 30.0,
        "profound_target_mb_per_day": 20.0
    }
}
```

### ServiceCapabilities (Service Metadata)
```python
{
    "service_name": "TSDBConsolidationService",
    "actions": [
        "consolidate_tsdb_nodes",
        "consolidate_all_data",
        "create_proper_edges",
        "track_memory_events",
        "summarize_tasks",
        "create_6hour_summaries"
    ],
    "version": "2.0.0",
    "dependencies": ["MemoryService", "TimeService"],
    "metadata": {
        "consolidation_interval_hours": 6.0,
        "raw_retention_hours": 24.0
    }
}
```

### TSDBPeriodSummary (Consolidation Result)
```python
{
    "metrics": {
        "llm.tokens.total": {
            "count": 234.0,
            "sum": 45678.0,
            "min": 10.0,
            "max": 500.0,
            "avg": 195.2
        }
    },
    "total_tokens": 45678,
    "total_cost_cents": 1234,
    "total_carbon_grams": 12.3,
    "total_energy_kwh": 0.015,
    "action_counts": {
        "send_message": 25,
        "analyze_thought": 15,
        "execute_handler": 10
    },
    "source_node_count": 156,
    "period_start": "2025-08-14T12:00:00+00:00",
    "period_end": "2025-08-14T18:00:00+00:00",
    "period_label": "2025-08-14 12:00-18:00 UTC",
    "conversations": [],
    "traces": [],
    "audits": [],
    "tasks": [],
    "memories": []
}
```

### ConsolidationCycleStats (Operational Telemetry)
```python
{
    "consolidation_start": "2025-08-14T13:30:00Z",
    "total_records_processed": 1523,
    "total_summaries_created": 8,
    "periods_consolidated": 4,
    "compression_ratio": 190.4,  # 1523:8 ratio
    "cleanup_stats": {
        "nodes_deleted": 1200,
        "edges_deleted": 45
    },
    "consolidation_duration_seconds": 12.5
}
```

## API Access Patterns

### Current Access
- **Internal Only**: No direct REST endpoints expose TSDB consolidation telemetry
- **Service Status**: Available via runtime control service status endpoints
- **Graph Queries**: Summary data accessible via memory bus queries
- **Log Analysis**: Operational metrics in structured logs

### Recommended Endpoints

#### Get Consolidation Status
```
GET /v1/telemetry/consolidation/status
```
Returns current consolidation service status:
```json
{
    "service_name": "TSDBConsolidationService",
    "is_healthy": true,
    "uptime_seconds": 3600.0,
    "last_consolidation": "2025-08-14T12:00:00Z",
    "next_consolidation": "2025-08-14T18:00:00Z",
    "consolidation_levels": {
        "basic": {
            "interval_hours": 6,
            "last_run": "2025-08-14T12:00:00Z",
            "task_running": false
        },
        "extensive": {
            "interval_days": 7,
            "last_run": "2025-08-07T00:00:00Z",
            "task_running": false
        },
        "profound": {
            "interval_days": 30,
            "last_run": "2025-07-01T00:00:00Z",
            "task_running": false,
            "target_mb_per_day": 20.0
        }
    }
}
```

#### Get Period Summary
```
GET /v1/telemetry/consolidation/summary
```
Query parameters:
- `period_start`: ISO timestamp (required)
- `period_end`: ISO timestamp (required)

Returns:
```json
{
    "summary_found": true,
    "consolidation_level": "basic",
    "summary": {
        "total_tokens": 45678,
        "total_cost_cents": 1234,
        "action_counts": {"send_message": 25},
        "source_node_count": 156,
        "period_label": "2025-08-14 12:00-18:00 UTC"
    }
}
```

#### Get Consolidation History
```
GET /v1/telemetry/consolidation/history
```
Query parameters:
- `hours`: Number of hours to look back (default 168 = 1 week)
- `level`: Consolidation level filter (basic|extensive|profound)

Returns:
```json
{
    "consolidations": [
        {
            "timestamp": "2025-08-14T12:00:00Z",
            "level": "basic",
            "periods_processed": 4,
            "records_processed": 1523,
            "summaries_created": 8,
            "duration_seconds": 12.5
        }
    ],
    "total_consolidations": 28,
    "average_duration_seconds": 11.2
}
```

## Graph Storage

### Node Types Created
- `TSDB_SUMMARY` - 6-hour consolidation summaries (basic level)
- `AUDIT_SUMMARY` - Audit event summaries per period
- `TRACE_SUMMARY` - Distributed tracing summaries per period
- `CONVERSATION_SUMMARY` - Service interaction summaries per period
- `TASK_SUMMARY` - Task execution summaries per period

### Edge Relationships
- `SUMMARIZES` - Links summary to all source nodes in period
- `TEMPORAL_NEXT` - Links to next period summary of same type
- `TEMPORAL_PREV` - Links to previous period summary of same type
- `CORRELATES_WITH` - Links summaries within same period
- `CONSOLIDATES_FROM` - Links extensive summaries to basic summaries
- `PARTICIPATES_IN` - Links users to conversation summaries

### Consolidation Levels
```python
class ConsolidationLevel(Enum):
    BASIC = "basic"        # 6-hour summaries
    EXTENSIVE = "extensive" # Daily summaries (from 4 basic)
    PROFOUND = "profound"   # Compressed daily summaries
```

## Example Usage

### Get Service Status
```python
tsdb_service = get_service(ServiceType.TSDB_CONSOLIDATION)
status = tsdb_service.get_status()

print(f"Last consolidation: {status.metrics['last_basic_consolidation']}")
print(f"Service healthy: {status.is_healthy}")
print(f"Tasks running: {status.metrics['basic_task_running']}")
```

### Get Period Summary
```python
from datetime import datetime, timedelta, timezone

now = datetime.now(timezone.utc)
period_start = now.replace(hour=12, minute=0, second=0, microsecond=0)
period_end = period_start + timedelta(hours=6)

summary = await tsdb_service.get_summary_for_period(period_start, period_end)
if summary:
    print(f"Tokens used: {summary.total_tokens}")
    print(f"Cost: ${summary.total_cost_cents / 100:.2f}")
    print(f"Actions: {summary.action_counts}")
```

### Check Consolidation Health
```python
def check_consolidation_health(tsdb_service):
    status = tsdb_service.get_status()

    # Check if consolidation is overdue
    now = datetime.now(timezone.utc)
    last_basic = datetime.fromtimestamp(
        status.metrics['last_basic_consolidation'],
        tz=timezone.utc
    )

    hours_since_last = (now - last_basic).total_seconds() / 3600

    if hours_since_last > 8:  # Overdue by 2 hours
        return {"healthy": False, "reason": "Consolidation overdue"}

    return {"healthy": True, "hours_since_last": hours_since_last}
```

## Testing

### Test Files
- `tests/ciris_engine/logic/services/graph/test_tsdb_consolidation_service.py` - Unit tests
- `tests/ciris_engine/logic/services/graph/test_tsdb_extensive_consolidation.py` - Weekly tests
- `tests/ciris_engine/logic/services/graph/test_tsdb_profound_consolidation.py` - Monthly tests
- `tests/ciris_engine/logic/services/graph/test_tsdb_edge_creation.py` - Edge relationship tests

### Validation Steps
1. Start service and verify task creation
2. Wait for consolidation cycle or trigger manually
3. Check that summaries are created with proper attributes
4. Verify edges link summaries to source nodes
5. Check cleanup removes raw data after retention period
6. Validate temporal edges between consecutive periods

```python
async def test_consolidation_telemetry():
    service = TSDBConsolidationService(mock_memory_bus, mock_time_service)
    await service.start()

    # Check service is healthy
    assert service.is_healthy()

    # Verify status contains telemetry
    status = service.get_status()
    assert "last_consolidation_timestamp" in status.metrics
    assert "basic_task_running" in status.metrics

    # Check capabilities include actions
    caps = service.get_capabilities()
    assert "consolidate_tsdb_nodes" in caps.actions
    assert caps.version == "2.0.0"
```

## Configuration

### Consolidation Intervals
```python
{
    "basic_interval_hours": 6,     # 00:00, 06:00, 12:00, 18:00 UTC
    "extensive_interval_days": 7,  # Weekly on Mondays
    "profound_interval_days": 30,  # Monthly on 1st
}
```

### Retention Policies
```python
{
    "raw_retention_hours": 24,        # Keep raw data 24h after consolidation
    "basic_retention_days": 7,        # Keep basic summaries 7 days
    "extensive_retention_days": 30,   # Keep daily summaries 30 days
    "profound_target_mb_per_day": 20  # Target storage per day
}
```

### Task Management
```python
{
    "max_periods_per_run": 30,           # Limit consolidation batch size
    "missed_window_limit": 10,           # Max missed periods to catch up
    "consolidation_timeout_seconds": 300 # Max time per consolidation
}
```

## Known Limitations

1. **Sequential Processing**: Consolidation runs sequentially, may lag under heavy load
2. **Memory Requirements**: Large periods require substantial memory for processing
3. **Database Locks**: Long consolidations may lock database tables
4. **No Pause/Resume**: Running consolidations cannot be paused
5. **Fixed Intervals**: Consolidation times are calendar-aligned, not configurable
6. **Storage Growth**: No automatic cleanup of profound summaries
7. **Error Recovery**: Failed consolidations require manual restart

## Future Enhancements

1. **Parallel Processing**: Consolidate multiple periods concurrently
2. **Incremental Consolidation**: Process data as it arrives vs batch processing
3. **Configurable Intervals**: Allow custom consolidation schedules
4. **Pause/Resume**: Support interrupting and resuming consolidations
5. **Compression Algorithms**: Advanced compression for multimedia data
6. **Auto-scaling**: Adjust intervals based on data volume
7. **Real-time Dashboards**: Live consolidation progress tracking
8. **Alerting**: Notifications when consolidation fails or falls behind

## Integration Points

- **MemoryBus**: Stores all summaries and manages graph persistence
- **TimeService**: Provides consistent timestamps for period boundaries
- **TelemetryService**: Source of raw metrics to be consolidated
- **AuditService**: Source of audit entries to be consolidated
- **RuntimeControl**: Monitors service health and task status

## Monitoring Recommendations

1. **Consolidation Lag**: Alert if basic consolidation is >8 hours overdue
2. **Storage Growth**: Monitor daily storage increase vs targets
3. **Processing Time**: Alert if consolidation takes >5 minutes
4. **Task Health**: Monitor task status for crashes or hangs
5. **Compression Ratio**: Track efficiency of data consolidation
6. **Edge Integrity**: Verify all summaries have proper edges
7. **Database Health**: Monitor for lock contention during consolidation

## Performance Considerations

1. **I/O Bottleneck**: Database queries during consolidation are intensive
2. **Memory Usage**: Large periods can consume significant memory
3. **CPU Load**: Aggregation calculations can spike CPU usage
4. **Lock Duration**: Long transactions may impact concurrent operations
5. **Network Traffic**: Distributed graph backends see high query load

## Architecture Notes

The TSDB Consolidation Service embodies key CIRIS principles:

- **Everything is Memory**: All telemetry becomes permanent graph memories
- **Grace-Based Consolidation**: Errors and failures become learning experiences
- **Temporal Coherence**: Maintains temporal relationships across all time scales
- **Type Safety**: Uses strongly-typed schemas throughout consolidation pipeline
- **Audit Trail**: All consolidation actions are fully auditable

The three-tier consolidation strategy (basic→extensive→profound) mirrors the human memory hierarchy, ensuring that important patterns are preserved at longer time scales while managing storage efficiently.

## Error Recovery

### Common Failure Scenarios
- **Database connection lost**: Service auto-reconnects on next cycle
- **Memory bus unavailable**: Service marks as unhealthy, retries on recovery
- **Corrupted summary data**: Manual cleanup required, consolidation continues
- **Clock skew**: Period boundaries may be calculated incorrectly
- **Disk space exhaustion**: Consolidation fails, requires manual intervention

### Recovery Procedures
1. Check service status via `get_status()`
2. Review consolidation logs for specific errors
3. Restart service to clear transient failures
4. For data corruption, delete affected summaries and re-consolidate
5. For persistent failures, check database integrity and disk space
