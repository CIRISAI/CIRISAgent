# CIRIS Database Maintenance Service

**Service Category**: Infrastructure Services  
**Location**: `ciris_engine/logic/persistence/maintenance.py`  
**Protocol**: `ciris_engine/protocols/services/infrastructure/database_maintenance.py`  
**Service Type**: `ServiceType.MAINTENANCE`  

## Mission Alignment

**Meta-Goal M-1**: Promote sustainable adaptive coherence enabling diverse sentient beings to pursue flourishing

The Database Maintenance Service serves Meta-Goal M-1 by:

1. **Sustainable Data Management**: Prevents database bloat and corruption through automated cleanup and archival
2. **Adaptive System Health**: Maintains optimal performance by removing orphaned data and optimizing storage
3. **Long-term Coherence**: Preserves system reliability over extended operation periods (1000-year design)
4. **Resource Efficiency**: Enables continued flourishing by managing limited storage and memory resources

## Service Overview

The Database Maintenance Service is a critical infrastructure component responsible for automated database hygiene and long-term data lifecycle management. It extends `BaseScheduledService` to provide continuous background maintenance operations that ensure system reliability and performance.

### Core Capabilities

- **Startup Cleanup**: Removes orphaned tasks and thoughts from interrupted sessions
- **Automated Archival**: Archives historical data older than configured thresholds
- **Runtime Configuration Cleanup**: Removes transient configuration from previous runs
- **Orphan Detection**: Identifies and removes data without valid parent relationships
- **Storage Optimization**: Monitors database size and archive directory usage
- **Scheduled Operations**: Runs maintenance tasks on configurable intervals (default: hourly)

## Architecture

### Class Hierarchy
```
DatabaseMaintenanceService
├── BaseScheduledService
│   └── BaseService
└── DatabaseMaintenanceServiceProtocol
```

### Dependencies
- **TimeService**: Required for timestamp operations and scheduling
- **ConfigService**: Optional, used for runtime configuration cleanup
- **Persistence Layer**: Direct access to task/thought database operations

### Service Registration
```python
ServiceType.MAINTENANCE  # Registered as infrastructure service
```

## Key Operations

### 1. Startup Cleanup (`perform_startup_cleanup`)

**Purpose**: Restore database to clean state after system restarts or crashes

**Operations**:
- **Invalid Thoughts Cleanup**: Removes thoughts with malformed context JSON
- **Runtime Config Cleanup**: Removes adapter/session-specific configurations from previous runs
- **Stale Wakeup Tasks**: Cleans up interrupted startup sequences (WAKEUP_, VERIFY_IDENTITY_, etc.)
- **Orphan Detection**: Removes active tasks whose parent tasks are missing or inactive
- **Thought Orphan Cleanup**: Removes pending/processing thoughts for inactive tasks

**Logging**: Comprehensive logging of all cleanup actions with counts

### 2. Periodic Maintenance (`_perform_periodic_maintenance`)

**Purpose**: Continuous system health maintenance

**Schedule**: Hourly by default (3600 seconds)
**Operations**: Currently placeholder for future enhancements
**Metrics Tracking**: Increments vacuum operations counter

### 3. Data Archival

**Purpose**: Long-term data lifecycle management for 1000-year operation

**Scope**:
- **Thoughts**: Archives thoughts older than configured threshold (default: 24 hours)
- **Tasks**: Deferred to TSDB consolidation service (no longer handled here)

**Archive Format**:
- **Location**: Configurable archive directory (default: `data_archive/`)
- **Format**: JSONL files with timestamp-based naming
- **Naming**: `archive_thoughts_{YYYYMMDD_HHMMSS}.jsonl`

**Process**:
1. Query thoughts older than threshold
2. Export to JSONL archive file
3. Delete from operational database
4. Update metrics counters

## Configuration

### Initialization Parameters

```python
DatabaseMaintenanceService(
    time_service: TimeServiceProtocol,           # Required
    archive_dir_path: str = "data_archive",     # Archive location
    archive_older_than_hours: int = 24,         # Archive threshold
    config_service: Optional[Any] = None,       # For config cleanup
)
```

### Runtime Configuration Patterns

The service identifies and removes these runtime-specific configurations:
- `adapter.*` - Adapter configurations
- `runtime.*` - Runtime-specific settings  
- `session.*` - Session-specific data
- `temp.*` - Temporary configurations

**Protection**: Preserves configurations created by `system_bootstrap`

## Telemetry & Metrics

### Core Metrics
```python
{
    "service_name": "database_maintenance",
    "healthy": bool,
    "uptime_seconds": float,
    "cleanup_runs": int,
    "records_deleted": int, 
    "vacuum_runs": int,
    "archive_runs": int,
    "last_cleanup_duration_ms": float,
    "archive_dir_size_mb": float,
    "next_run_seconds": int,
    "database_size_mb": float,
    "db_maintenance_uptime_seconds": float
}
```

### Scheduled Task Metrics (from BaseScheduledService)
- `task_run_count`: Number of scheduled executions
- `task_error_count`: Failed execution count
- `task_error_rate`: Failure percentage
- `task_interval_seconds`: Configured run interval
- `time_since_last_task_run`: Seconds since last execution
- `task_running`: Boolean indicator of active task

## Error Handling

### Graceful Degradation
- **Database Errors**: Logged with full stack traces, service continues
- **File System Errors**: Handled gracefully, metrics report 0.0 for inaccessible paths
- **Configuration Errors**: Service continues with warning if config service unavailable
- **Scheduled Task Errors**: Caught and logged, next run proceeds normally

### Recovery Patterns
- **Startup Cleanup**: Always runs on service initialization
- **Orphan Cleanup**: Self-healing approach removes inconsistent data
- **Archive Directory**: Created automatically if missing

## Testing

### Test Coverage
- **Metrics Collection**: Comprehensive validation of all telemetry data
- **Error Scenarios**: Testing with missing files, invalid configurations
- **Mock Dependencies**: Isolated testing with mocked time and config services
- **Archive Operations**: Temporary directory testing for file operations

### Test Location
`tests/ciris_engine/logic/persistence/test_maintenance_telemetry.py`

## Integration Points

### Service Initialization
Registered during system startup via `ServiceInitializer`

### Runtime Control Integration
Exposes maintenance operations through runtime control service

### Memory Graph Integration
Works with graph-based configuration system for runtime config cleanup

### TSDB Consolidation Coordination
Defers task archival to specialized TSDB consolidation service

## Future Enhancements

### Planned Improvements
1. **Enhanced Periodic Maintenance**: Currently placeholder, needs specific maintenance operations
2. **Configurable Cleanup Thresholds**: Per-data-type retention policies
3. **Compression Support**: Archive file compression for long-term storage
4. **Database Vacuum Operations**: Automated SQLite VACUUM for space reclamation
5. **Health Check Endpoints**: Dedicated maintenance status endpoints

### Architecture Evolution
The service is currently implemented as a single file but is planned for conversion to a proper service module structure:

**Current**: `ciris_engine/logic/persistence/maintenance.py`
**Future**: `ciris_engine/logic/services/infrastructure/database_maintenance/`

This conversion will align with the standardized service module pattern used throughout CIRIS.

## 1000-Year Design Principles

### Sustainability
- **Bounded Growth**: Prevents unlimited data accumulation
- **Resource Management**: Monitors and controls storage usage
- **Automated Operations**: Reduces human intervention requirements

### Reliability
- **Self-Healing**: Automatically corrects database inconsistencies
- **Error Resilience**: Continues operation despite individual failures
- **Comprehensive Logging**: Enables diagnosis and system health monitoring

### Adaptability
- **Configurable Thresholds**: Allows adjustment for different deployment scenarios
- **Modular Design**: Clean separation of concerns for future enhancements
- **Protocol-Based**: Interface-driven design enables implementation evolution

## Security Considerations

### Data Protection
- **Archive Security**: Archive files contain sensitive thought data
- **SQL Injection Prevention**: Uses parameterized queries with placeholders
- **Access Control**: No direct external access, operates through service protocols

### Audit Trail
- **Operation Logging**: All maintenance actions logged with timestamps
- **Metric Tracking**: Historical maintenance operations tracked for analysis
- **Change Documentation**: Clear indication of what data was modified or removed

## Conclusion

The Database Maintenance Service embodies CIRIS's commitment to sustainable, long-term operation while maintaining system performance and reliability. Through automated cleanup, intelligent archival, and comprehensive monitoring, it ensures the system can operate reliably for extended periods while serving Meta-Goal M-1 by enabling continued flourishing through efficient resource management.

Its design balances immediate operational needs with long-term sustainability requirements, making it an essential component of the 1000-year architecture vision.