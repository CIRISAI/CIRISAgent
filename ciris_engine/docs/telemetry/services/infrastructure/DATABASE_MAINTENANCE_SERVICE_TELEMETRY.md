# Database Maintenance Service Telemetry

## Overview
The Database Maintenance Service handles periodic database cleanup and archival operations. It runs scheduled maintenance tasks every hour to clean up orphaned data, archive old thoughts, and maintain database health. The service performs critical startup cleanup including removal of stale tasks, invalid thoughts, and runtime configuration from previous runs.

## Telemetry Data Collected

| Metric Name | Type | Storage | Update Frequency | Access Method |
|------------|------|---------|------------------|---------------|
| uptime_seconds | gauge | in-memory | real-time | `get_status().metrics["uptime_seconds"]` |
| request_count | counter | in-memory | per operation | `get_status().metrics["request_count"]` |
| error_count | counter | in-memory | on error | `get_status().metrics["error_count"]` |
| error_rate | gauge | in-memory | real-time | `get_status().metrics["error_rate"]` |
| healthy | boolean | in-memory | real-time | `get_status().metrics["healthy"]` |
| task_run_count | counter | in-memory | per scheduled run | `get_status().metrics["task_run_count"]` |
| task_error_count | counter | in-memory | on task error | `get_status().metrics["task_error_count"]` |
| task_error_rate | gauge | in-memory | real-time | `get_status().metrics["task_error_rate"]` |
| task_interval_seconds | gauge | in-memory | constant | `get_status().metrics["task_interval_seconds"]` |
| time_since_last_task_run | gauge | in-memory | real-time | `get_status().metrics["time_since_last_task_run"]` |
| task_running | boolean | in-memory | real-time | `get_status().metrics["task_running"]` |
| startup_cleanup_completed | boolean | log-based | per startup | Via service logs |
| orphaned_tasks_cleaned | counter | log-based | per cleanup run | Via service logs |
| orphaned_thoughts_cleaned | counter | log-based | per cleanup run | Via service logs |
| archived_thoughts_count | counter | log-based | per archive run | Via service logs |
| invalid_thoughts_cleaned | counter | log-based | per cleanup run | Via service logs |
| runtime_configs_cleaned | counter | log-based | per cleanup run | Via service logs |
| stale_wakeup_tasks_cleaned | counter | log-based | per cleanup run | Via service logs |

## Data Structures

### ServiceStatus
```python
{
    "service_name": "DatabaseMaintenanceService",
    "service_type": "MAINTENANCE",
    "is_healthy": true,
    "uptime_seconds": 3600.5,
    "metrics": {
        "uptime_seconds": 3600.5,
        "request_count": 12.0,
        "error_count": 0.0,
        "error_rate": 0.0,
        "healthy": 1.0,
        "task_run_count": 1.0,
        "task_error_count": 0.0,
        "task_error_rate": 0.0,
        "task_interval_seconds": 3600.0,
        "time_since_last_task_run": 1800.0,
        "task_running": 1.0
    },
    "last_error": null,
    "last_health_check": "2025-08-14T13:30:00Z"
}
```

### ServiceCapabilities
```python
{
    "service_name": "DatabaseMaintenanceService",
    "actions": ["cleanup", "archive", "maintenance"],
    "version": "1.0.0",
    "dependencies": ["TimeService"],
    "metadata": {
        "archive_older_than_hours": 24,
        "maintenance_interval": "hourly"
    }
}
```

### Cleanup Operation Log Event
```python
{
    "timestamp": "2025-08-14T13:30:00Z",
    "operation": "startup_cleanup",
    "orphaned_tasks_deleted": 5,
    "orphaned_thoughts_deleted": 12,
    "archived_thoughts_count": 150,
    "invalid_thoughts_deleted": 3,
    "runtime_configs_cleaned": 8,
    "stale_wakeup_tasks_deleted": 2,
    "archive_file": "data_archive/archive_thoughts_20250814_133000.jsonl"
}
```

### Maintenance Configuration
```python
{
    "archive_dir_path": "data_archive",
    "archive_older_than_hours": 24,
    "run_interval_seconds": 3600,  # 1 hour
    "cleanup_patterns": [
        "adapter.",    # Adapter configurations
        "runtime.",    # Runtime-specific settings
        "session.",    # Session-specific data
        "temp."        # Temporary configurations
    ]
}
```

## API Access Patterns

### Current Access
- **No Direct API**: Service status accessible via general service endpoints
- **Internal Access**: Other services can access via dependency injection
- **Log-Based Metrics**: Cleanup statistics available through service logs

### Recommended Endpoints

#### Get Service Status
```
GET /v1/telemetry/services/database-maintenance/status
```
Returns current service status and metrics:
```json
{
    "service": "DatabaseMaintenanceService",
    "health": {
        "healthy": true,
        "uptime_seconds": 3600.5,
        "last_error": null
    },
    "task_metrics": {
        "run_count": 1,
        "error_count": 0,
        "error_rate": 0.0,
        "interval_seconds": 3600,
        "time_since_last_run": 1800,
        "currently_running": true
    },
    "maintenance_config": {
        "archive_older_than_hours": 24,
        "archive_directory": "data_archive"
    }
}
```

#### Get Cleanup History
```
GET /v1/telemetry/services/database-maintenance/history
```
Query parameters:
- `period`: 1h|1d|7d|30d
- `operation`: startup|scheduled|all

Returns cleanup operation history:
```json
{
    "period": "1d",
    "operations": [
        {
            "timestamp": "2025-08-14T13:30:00Z",
            "type": "startup_cleanup",
            "orphaned_tasks_deleted": 5,
            "orphaned_thoughts_deleted": 12,
            "archived_thoughts_count": 150,
            "invalid_thoughts_deleted": 3
        }
    ],
    "summary": {
        "total_operations": 1,
        "total_orphaned_tasks_cleaned": 5,
        "total_thoughts_archived": 150
    }
}
```

#### Trigger Manual Cleanup
```
POST /v1/telemetry/services/database-maintenance/cleanup
```
Request body:
```json
{
    "operation": "startup|archive|invalid_thoughts|runtime_config|stale_wakeup"
}
```
Returns:
```json
{
    "operation": "startup",
    "started": true,
    "estimated_completion": "2025-08-14T13:35:00Z"
}
```

## Graph Storage
The Database Maintenance Service does not directly store telemetry in the graph, but its operations affect:

- **ConfigurationNode**: Cleanup operations remove runtime configs from the graph
- **TaskNode**: Orphaned tasks are removed via database operations
- **ThoughtNode**: Invalid thoughts are removed via database operations

All cleanup operations are logged to the audit trail and can be retrieved via:
```python
audit_service = get_service(ServiceType.AUDIT)
events = await audit_service.get_events_by_service("DatabaseMaintenanceService")
```

## Example Usage

### Check Service Status
```python
maintenance_service = get_service(ServiceType.MAINTENANCE)
status = maintenance_service.get_status()

print(f"Uptime: {status.metrics['uptime_seconds']}s")
print(f"Task runs: {status.metrics['task_run_count']}")
print(f"Errors: {status.metrics['task_error_count']}")
```

### Trigger Startup Cleanup
```python
# Performed automatically at service initialization
maintenance_service = DatabaseMaintenanceService(
    time_service=time_service,
    archive_older_than_hours=24
)
await maintenance_service.start()  # Triggers startup cleanup
```

### Monitor Cleanup Operations
```python
import logging

# Set up log monitoring for cleanup operations
logger = logging.getLogger("ciris_engine.services.DatabaseMaintenanceService")
logger.setLevel(logging.INFO)

# Cleanup operations will be logged automatically:
# INFO: Orphan cleanup: 5 tasks, 12 thoughts removed.
# INFO: Archived and deleted 150 thoughts older than 24 hours
# INFO: Cleaned up 8 runtime-specific configuration entries
```

## Testing

### Test Files
- `tests/logic/services/infrastructure/test_database_maintenance.py` (to be created)
- `tests/logic/persistence/test_maintenance.py` (existing)

### Validation Steps
1. Initialize service with test database
2. Create orphaned tasks and thoughts
3. Run startup cleanup operation
4. Verify cleanup statistics in logs
5. Check archived files created
6. Validate metrics updated correctly

```python
async def test_database_maintenance_telemetry():
    time_service = TimeService()
    maintenance_service = DatabaseMaintenanceService(
        time_service=time_service,
        archive_dir_path="test_archive",
        archive_older_than_hours=1
    )

    await maintenance_service.start()

    # Check initial metrics
    status = maintenance_service.get_status()
    assert status.is_healthy
    assert status.metrics["task_run_count"] >= 0

    # Wait for scheduled task execution
    await asyncio.sleep(3700)  # Slightly over 1 hour

    # Check updated metrics
    status = maintenance_service.get_status()
    assert status.metrics["task_run_count"] >= 1
    assert status.metrics["time_since_last_task_run"] < 3600
```

## Configuration

### Archive Settings
- **Archive Directory**: Configurable via `archive_dir_path` (default: "data_archive")
- **Archive Threshold**: Configurable via `archive_older_than_hours` (default: 24 hours)
- **Task Interval**: Fixed at 3600 seconds (1 hour) for scheduled maintenance

### Cleanup Patterns
Runtime configuration cleanup targets patterns:
- `adapter.*` - Adapter configurations
- `runtime.*` - Runtime-specific settings
- `session.*` - Session-specific data
- `temp.*` - Temporary configurations

### Archive File Format
Archived thoughts are stored as JSONL files:
```
data_archive/archive_thoughts_YYYYMMDD_HHMMSS.jsonl
```

## Known Limitations

1. **No Persistent Metrics**: Cleanup statistics not stored persistently between restarts
2. **Log-Based Tracking**: Most operational metrics only available via log parsing
3. **No Real-Time Progress**: Long cleanup operations don't report incremental progress
4. **Fixed Schedule**: Maintenance interval not configurable at runtime
5. **Archive Only**: No restore functionality for archived data
6. **Sequential Operations**: All cleanup tasks run serially, not optimized for large datasets

## Future Enhancements

1. **Persistent Metrics**: Store cleanup statistics in time-series database
2. **Progress Reporting**: Real-time progress updates for long-running operations
3. **Configurable Schedule**: Runtime-adjustable maintenance intervals
4. **Archive Management**: Tools for archive lifecycle management and cleanup
5. **Performance Optimization**: Parallel processing for large cleanup operations
6. **Restore Capability**: Tools to restore archived data when needed
7. **Predictive Cleanup**: ML-based prediction of optimal cleanup timing
8. **Resource Usage Metrics**: Track memory and CPU usage during cleanup operations

## Integration Points

- **TimeService**: Provides consistent timestamps and age calculations
- **ConfigService**: Manages configuration cleanup operations
- **Database Layer**: Performs SQL operations for orphan detection and cleanup
- **Audit Service**: Logs all cleanup operations for compliance
- **File System**: Creates and manages archive files
- **BaseScheduledService**: Inherits scheduled task management and metrics

## Monitoring Recommendations

1. **Alert on Cleanup Failures**: Monitor `task_error_count` for cleanup failures
2. **Track Archive Growth**: Monitor archive directory size and file count
3. **Orphan Detection Trends**: Alert on increasing orphaned data over time
4. **Cleanup Performance**: Monitor cleanup duration for performance degradation
5. **Archive Success Rate**: Track percentage of successful archive operations
6. **Disk Space Usage**: Monitor archive directory disk consumption

## Performance Considerations

1. **Database Locks**: Cleanup operations may briefly lock database tables
2. **I/O Intensive**: Archive operations are disk-intensive for large datasets
3. **Memory Usage**: Large cleanup operations may temporarily increase memory usage
4. **Startup Delay**: Startup cleanup can delay service initialization
5. **Log Volume**: Verbose logging during cleanup can generate significant log data

## System Integration

The Database Maintenance Service is critical for system health:
- Prevents database bloat by removing orphaned data
- Ensures clean startup state by removing stale configurations
- Maintains performance by archiving old data
- Provides audit trail of all cleanup operations
- Supports system reliability through automated maintenance

It acts as the "janitor" of CIRIS, maintaining database hygiene and preventing data accumulation issues that could impact system performance over time.
