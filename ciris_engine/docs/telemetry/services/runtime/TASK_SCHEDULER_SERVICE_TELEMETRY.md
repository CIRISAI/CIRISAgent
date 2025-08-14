# Task Scheduler Service Telemetry

## Overview
The Task Scheduler Service manages scheduled tasks and proactive goals for CIRIS agents, integrating with the time-based DEFER system to enable agents to schedule their own future actions. The service provides comprehensive telemetry for monitoring task execution, cron scheduling effectiveness, deferral patterns, and service performance. It tracks both one-time deferred tasks and recurring cron-based schedules with detailed execution metrics.

## Telemetry Data Collected

| Metric Name | Type | Storage | Update Frequency | Access Method |
|------------|------|---------|------------------|---------------|
| active_tasks | gauge | in-memory counter | per task create/complete | `_collect_custom_metrics()` |
| check_interval | config | service configuration | service start | `_collect_custom_metrics()` |
| task_run_count | counter | inherited from BaseScheduledService | per scheduled run | `_collect_custom_metrics()` |
| task_error_count | counter | inherited from BaseScheduledService | per error | `_collect_custom_metrics()` |
| task_error_rate | gauge | calculated from counters | per metrics collection | `_collect_custom_metrics()` |
| task_interval_seconds | config | service configuration | service start | `_collect_custom_metrics()` |
| time_since_last_task_run | gauge | calculated from timestamps | per metrics collection | `_collect_custom_metrics()` |
| task_running | boolean | task state check | per metrics collection | `_collect_custom_metrics()` |
| uptime_seconds | gauge | inherited from BaseService | continuous | `_calculate_uptime()` |
| request_count | counter | inherited from BaseService | per API call | `_track_request()` |
| error_count | counter | inherited from BaseService | per error | `_track_error()` |
| error_rate | gauge | inherited from BaseService | calculated | `error_count / request_count` |
| healthy | boolean | inherited from BaseService | per health check | `is_healthy()` |
| scheduled_tasks_created | counter | **NOT IMPLEMENTED** | - | TODO: Track task creation |
| scheduled_tasks_completed | counter | **NOT IMPLEMENTED** | - | TODO: Track task completion |
| scheduled_tasks_failed | counter | **NOT IMPLEMENTED** | - | TODO: Track task failures |
| deferral_requests | counter | **NOT IMPLEMENTED** | - | TODO: Track deferral operations |
| cron_trigger_count | counter | **NOT IMPLEMENTED** | - | TODO: Track cron executions |
| avg_task_execution_time | gauge | **NOT IMPLEMENTED** | - | TODO: Track execution timing |

## Data Structures

### TaskSchedulerStatus
```python
{
    "service_name": "TaskSchedulerService",
    "active_tasks": 12,                    # Number of currently active tasks
    "check_interval": 60,                  # Task check interval in seconds
    "cron_support": true,                  # Whether croniter is available
    "task_execution": {
        "run_count": 1440,                 # Total scheduled runs
        "error_count": 3,                  # Failed runs
        "error_rate": 0.002,               # Error rate
        "last_run_age_seconds": 25         # Time since last run
    },
    "performance": {
        "uptime_seconds": 86400,
        "task_running": true,
        "healthy": true
    }
}
```

### ScheduledTask (Core Data Model)
```python
{
    "task_id": "task_1723644600.123",      # Unique identifier
    "name": "Daily Report Generation",      # Human-readable name
    "goal_description": "Generate daily metrics report",
    "status": "ACTIVE",                    # PENDING|ACTIVE|COMPLETE|CANCELLED|FAILED
    "defer_until": "2025-08-15T09:00:00Z", # One-time execution timestamp
    "schedule_cron": "0 9 * * *",          # Recurring cron expression
    "trigger_prompt": "Generate today's metrics report",
    "origin_thought_id": "thought_12345",   # Creating thought ID
    "created_at": "2025-08-14T10:30:00Z",  # Creation timestamp
    "last_triggered_at": "2025-08-14T09:00:00Z", # Last execution
    "deferral_count": 2,                   # Self-deferral count
    "deferral_history": [                  # Deferral audit trail
        {
            "deferred_at": "2025-08-13T09:00:00Z",
            "deferred_until": "2025-08-14T09:00:00Z",
            "reason": "High system load detected"
        }
    ]
}
```

### ScheduledTaskInfo (API Response Format)
```python
{
    "task_id": "task_1723644600.123",
    "name": "Daily Report Generation",
    "goal_description": "Generate daily metrics report",
    "status": "ACTIVE",
    "defer_until": "2025-08-15T09:00:00Z",  # ISO string format
    "schedule_cron": "0 9 * * *",
    "created_at": "2025-08-14T10:30:00Z",   # ISO string format
    "last_triggered_at": "2025-08-14T09:00:00Z", # ISO string format
    "deferral_count": 2
}
```

### Task Execution Statistics
```python
{
    "total_tasks_created": 156,
    "active_tasks": 12,
    "completed_tasks": 142,
    "cancelled_tasks": 2,
    "failed_tasks": 0,
    "one_time_tasks": 89,                  # Deferred tasks
    "recurring_tasks": 67,                 # Cron tasks
    "avg_deferral_count": 1.2,            # Average deferrals per task
    "most_deferred_task": {
        "task_id": "task_xyz",
        "deferral_count": 8,
        "name": "Weekly Cleanup"
    }
}
```

### Cron Scheduling Analytics
```python
{
    "cron_support_available": true,        # croniter library installed
    "cron_expressions_used": [
        {
            "expression": "0 9 * * *",     # Daily at 9am
            "task_count": 5,
            "description": "Daily tasks"
        },
        {
            "expression": "0 0 * * 0",     # Weekly on Sunday
            "task_count": 2,
            "description": "Weekly tasks"
        }
    ],
    "invalid_cron_attempts": 3,            # Failed cron validations
    "next_cron_triggers": [
        {
            "task_id": "task_abc",
            "next_execution": "2025-08-15T09:00:00Z",
            "cron_expression": "0 9 * * *"
        }
    ]
}
```

### Service Capabilities Metadata
```python
{
    "features": ["cron_scheduling", "one_time_defer", "task_persistence"],
    "cron_support": true,                  # croniter availability
    "description": "Task scheduling and deferral service",
    "service_name": "TaskSchedulerService",
    "actions": ["schedule_task", "cancel_task", "get_scheduled_tasks"],
    "version": "1.0.0",
    "dependencies": ["TimeService"]
}
```

## API Access Patterns

### Current Access
- **Internal Service Access**: Via dependency injection and service registry
- **Database Integration**: Uses SQLite database for task persistence
- **Time Service Integration**: Consistent timestamps and scheduling
- **DEFER System Integration**: Handles time-based task deferrals

### Recommended Endpoints

#### Get Task Scheduler Status
```
GET /v1/telemetry/task-scheduler/status
```
Returns comprehensive service status:
```json
{
    "service_name": "TaskSchedulerService",
    "healthy": true,
    "uptime_seconds": 86400,
    "task_management": {
        "active_tasks": 12,
        "check_interval_seconds": 60,
        "cron_support": true
    },
    "execution_metrics": {
        "task_run_count": 1440,
        "task_error_count": 3,
        "task_error_rate": 0.002,
        "time_since_last_run": 25,
        "task_running": true
    },
    "performance": {
        "request_count": 89,
        "error_count": 1,
        "error_rate": 0.011
    }
}
```

#### Get Active Tasks Summary
```
GET /v1/telemetry/task-scheduler/tasks
```
Query parameters:
- `status`: Filter by PENDING|ACTIVE|COMPLETE|CANCELLED|FAILED
- `type`: Filter by one_time|recurring
- `limit`: Maximum number of tasks to return

Returns task list:
```json
{
    "total_count": 12,
    "filtered_count": 12,
    "tasks": [
        {
            "task_id": "task_1723644600.123",
            "name": "Daily Report Generation",
            "status": "ACTIVE",
            "type": "recurring",
            "next_execution": "2025-08-15T09:00:00Z",
            "deferral_count": 0,
            "created_at": "2025-08-14T10:30:00Z"
        }
    ],
    "summary": {
        "pending": 5,
        "active": 7,
        "one_time": 8,
        "recurring": 4
    }
}
```

#### Get Task Execution Analytics
```
GET /v1/telemetry/task-scheduler/analytics
```
Query parameters:
- `period`: 1h|1d|7d|30d
- `task_type`: one_time|recurring

Returns execution analytics:
```json
{
    "period": "7d",
    "execution_summary": {
        "total_executions": 168,
        "successful_executions": 165,
        "failed_executions": 3,
        "success_rate": 0.982,
        "avg_executions_per_day": 24
    },
    "task_creation": {
        "tasks_created": 23,
        "tasks_completed": 18,
        "tasks_cancelled": 2,
        "completion_rate": 0.783
    },
    "deferral_patterns": {
        "total_deferrals": 12,
        "avg_deferrals_per_task": 0.52,
        "common_deferral_reasons": [
            {"reason": "System maintenance", "count": 5},
            {"reason": "High system load", "count": 3}
        ]
    }
}
```

#### Get Cron Scheduling Status
```
GET /v1/telemetry/task-scheduler/cron
```
Returns cron-specific metrics:
```json
{
    "cron_support": {
        "available": true,
        "library": "croniter"
    },
    "active_cron_tasks": 4,
    "cron_expressions": [
        {
            "expression": "0 9 * * *",
            "description": "Daily at 9am",
            "task_count": 2,
            "next_triggers": [
                {
                    "task_id": "task_abc",
                    "task_name": "Daily Report",
                    "next_execution": "2025-08-15T09:00:00Z"
                }
            ]
        }
    ],
    "validation_stats": {
        "valid_expressions": 15,
        "invalid_attempts": 2,
        "success_rate": 0.882
    }
}
```

#### Get Task Performance Metrics
```
GET /v1/telemetry/task-scheduler/performance
```
Returns performance analytics:
```json
{
    "service_performance": {
        "uptime_seconds": 86400,
        "check_frequency": {
            "interval_seconds": 60,
            "checks_per_hour": 60,
            "missed_checks": 0
        },
        "execution_timing": {
            "avg_trigger_delay_ms": 150,
            "max_trigger_delay_ms": 500,
            "tasks_triggered_on_time": 0.995
        }
    },
    "resource_usage": {
        "active_task_memory_mb": 0.5,
        "database_connections": 1,
        "background_task_status": "running"
    },
    "error_analysis": {
        "task_execution_errors": 3,
        "cron_parsing_errors": 1,
        "database_errors": 0,
        "most_common_error": "Invalid cron expression"
    }
}
```

## Graph Storage

### Memory Graph Integration
Task scheduler data can be stored as graph nodes for long-term analysis:

```python
# Scheduled Task Node
{
    "node_type": "scheduled_task",
    "task_id": "task_1723644600.123",
    "metadata": {
        "name": "Daily Report Generation",
        "status": "ACTIVE",
        "task_type": "recurring",
        "cron_expression": "0 9 * * *",
        "created_at": "2025-08-14T10:30:00Z"
    },
    "relationships": [
        {"type": "CREATED_BY", "target": "thought_12345"},
        {"type": "SCHEDULED_FOR", "target": "time_2025-08-15T09:00:00Z"}
    ]
}
```

### Task Execution Event Node
```python
# Task Execution Record
{
    "node_type": "task_execution",
    "execution_id": "exec_1723644600.456",
    "metadata": {
        "task_id": "task_1723644600.123",
        "execution_type": "cron_trigger",
        "status": "completed",
        "triggered_at": "2025-08-15T09:00:00Z",
        "completed_at": "2025-08-15T09:02:30Z",
        "duration_seconds": 150
    },
    "relationships": [
        {"type": "EXECUTION_OF", "target": "task_1723644600.123"},
        {"type": "CREATED_THOUGHT", "target": "thought_67890"}
    ]
}
```

### Task Deferral Event Node
```python
# Deferral Event Record
{
    "node_type": "task_deferral",
    "deferral_id": "defer_1723644500.789",
    "metadata": {
        "task_id": "task_1723644600.123",
        "original_time": "2025-08-14T09:00:00Z",
        "deferred_until": "2025-08-15T09:00:00Z",
        "reason": "High system load detected",
        "deferral_count": 2
    },
    "relationships": [
        {"type": "DEFERRAL_OF", "target": "task_1723644600.123"},
        {"type": "REQUESTED_BY", "target": "thought_12345"}
    ]
}
```

## Example Usage

### Get Service Status
```python
task_scheduler = get_service(ServiceType.MAINTENANCE)  # or ServiceType.TASK_SCHEDULER
status = task_scheduler.get_status()

print(f"Task Scheduler: {status.service_name}")
print(f"Healthy: {status.is_healthy}")
print(f"Active tasks: {status.metrics.get('active_tasks', 0)}")
print(f"Check interval: {status.metrics.get('check_interval', 0)}s")
print(f"Task runs: {status.metrics.get('task_run_count', 0)}")
print(f"Task errors: {status.metrics.get('task_error_count', 0)}")
```

### Monitor Task Execution
```python
task_scheduler = get_service(ServiceType.MAINTENANCE)
metrics = task_scheduler._collect_custom_metrics()

print(f"Active tasks: {int(metrics.get('active_tasks', 0))}")
print(f"Task running: {'Yes' if metrics.get('task_running', 0) > 0 else 'No'}")
print(f"Error rate: {metrics.get('task_error_rate', 0):.3f}")
print(f"Last run: {int(metrics.get('time_since_last_task_run', 0))}s ago")

# Alert if too many errors
if metrics.get('task_error_rate', 0) > 0.1:
    logger.warning(f"High task error rate: {metrics['task_error_rate']:.2%}")
```

### Schedule and Monitor Tasks
```python
# Schedule a one-time task
task = await task_scheduler.schedule_task(
    name="Weekly Cleanup",
    goal_description="Clean up old log files",
    trigger_prompt="Run weekly cleanup routine",
    origin_thought_id="thought_abc123",
    defer_until="2025-08-21T02:00:00Z"
)

print(f"Scheduled task: {task.name} ({task.task_id})")
print(f"Execution time: {task.defer_until}")

# Schedule a recurring task
recurring_task = await task_scheduler.schedule_task(
    name="Daily Backup",
    goal_description="Backup system data",
    trigger_prompt="Perform daily system backup",
    origin_thought_id="thought_def456",
    schedule_cron="0 2 * * *"  # Daily at 2am
)

print(f"Recurring task: {recurring_task.name}")
print(f"Cron schedule: {recurring_task.schedule_cron}")
```

### Get All Scheduled Tasks
```python
tasks = await task_scheduler.get_scheduled_tasks()

print(f"Total active tasks: {len(tasks)}")
for task in tasks:
    print(f"  {task.name} ({task.status})")
    if task.defer_until:
        print(f"    Next execution: {task.defer_until}")
    if task.schedule_cron:
        print(f"    Cron schedule: {task.schedule_cron}")
    print(f"    Deferrals: {task.deferral_count}")
```

### Handle Deferred Tasks
```python
# Schedule a deferred task (typically called by DEFER handler)
deferred_task = await task_scheduler.schedule_deferred_task(
    thought_id="thought_xyz789",
    task_id="original_task_123",
    defer_until="2025-08-15T14:00:00Z",
    reason="Waiting for external API rate limit reset",
    context={"api": "weather_service", "retry_count": 2}
)

print(f"Deferred task: {deferred_task.name}")
print(f"Reason: {deferred_task.deferral_history[-1]['deferral_reason']}")
print(f"Total deferrals: {deferred_task.deferral_count}")
```

### Check Service Health
```python
task_scheduler = get_service(ServiceType.MAINTENANCE)
is_healthy = await task_scheduler.is_healthy()

if not is_healthy:
    logger.error("Task scheduler is unhealthy")
    # Check specific issues
    if not task_scheduler._task or task_scheduler._task.done():
        logger.error("Background task is not running")
    if task_scheduler._shutdown_event.is_set():
        logger.error("Shutdown event is set")
```

## Testing

### Test Files
- `tests/logic/services/lifecycle/test_task_scheduler_service.py`
- `tests/integration/test_task_scheduler_telemetry.py`
- `tests/logic/runtime/test_task_scheduling_integration.py`

### Validation Steps
1. Initialize TaskSchedulerService with database and time service
2. Schedule various types of tasks (one-time, recurring)
3. Verify task execution and metrics collection
4. Test cron expression validation and scheduling
5. Test deferral functionality and history tracking
6. Validate service health and error handling
7. Test task cancellation and cleanup

```python
async def test_task_scheduler_telemetry():
    # Setup service
    time_service = Mock()
    task_scheduler = TaskSchedulerService(
        db_path=":memory:",
        time_service=time_service,
        check_interval_seconds=5
    )

    await task_scheduler.start()

    # Schedule tasks
    one_time_task = await task_scheduler.schedule_task(
        name="Test Task",
        goal_description="Test one-time execution",
        trigger_prompt="Execute test",
        origin_thought_id="test_thought",
        defer_until="2025-08-15T12:00:00Z"
    )

    recurring_task = await task_scheduler.schedule_task(
        name="Recurring Test",
        goal_description="Test recurring execution",
        trigger_prompt="Execute recurring test",
        origin_thought_id="test_thought_2",
        schedule_cron="*/5 * * * *"  # Every 5 minutes
    )

    # Verify metrics
    metrics = task_scheduler._collect_custom_metrics()
    assert metrics["active_tasks"] == 2.0
    assert metrics["check_interval"] == 5.0

    # Check status
    status = task_scheduler.get_status()
    assert status.is_healthy
    assert status.service_name == "TaskSchedulerService"

    # Test capabilities
    capabilities = task_scheduler.get_capabilities()
    assert "schedule_task" in capabilities.actions
    assert "cancel_task" in capabilities.actions
    assert "get_scheduled_tasks" in capabilities.actions

    # Test task retrieval
    tasks = await task_scheduler.get_scheduled_tasks()
    assert len(tasks) == 2
    assert any(task.name == "Test Task" for task in tasks)
    assert any(task.name == "Recurring Test" for task in tasks)
```

## Configuration

### Service Configuration
```python
{
    "db_path": "/app/data/agent.db",        # SQLite database path
    "check_interval_seconds": 60,           # How often to check for due tasks
    "time_service": TimeServiceProtocol,    # Time service dependency
    "service_name": "TaskSchedulerService", # Service identifier
    "version": "1.0.0"                     # Service version
}
```

### Database Schema (Implicit)
The service uses the existing database schema with tables:
- `thoughts`: For storing generated thoughts from task triggers
- `tasks`: For task metadata (if implemented)
- Additional tables may be used for task persistence

### Cron Support Configuration
```python
{
    "croniter_available": True,             # Whether croniter is installed
    "cron_validation": True,                # Validate cron expressions
    "max_cron_tasks": 100                   # Maximum recurring tasks
}
```

## Known Limitations

1. **Task Persistence**: Tasks are only stored in memory; lost on service restart
2. **Database Integration**: No dedicated scheduled_tasks table implemented
3. **Execution Timing**: No precise execution timing metrics tracked
4. **Task History**: No historical execution data preserved
5. **Concurrency**: No protection against concurrent task modifications
6. **Task Dependencies**: No support for task dependencies or chaining
7. **Priority Scheduling**: All tasks have equal priority
8. **Resource Limits**: No limits on number of active tasks or memory usage
9. **Execution Monitoring**: No real-time monitoring of task execution progress
10. **Error Recovery**: Limited error recovery and retry mechanisms

## Future Enhancements

1. **Persistent Task Storage**: Implement dedicated database tables for task persistence
2. **Execution Metrics**: Track detailed timing, success rates, and performance metrics
3. **Task Dependencies**: Support for task chains and prerequisite relationships
4. **Priority Queues**: Implement task priority and resource allocation
5. **Real-time Monitoring**: WebSocket streams for live task execution updates
6. **Advanced Scheduling**: Support for more complex scheduling patterns
7. **Task Templates**: Reusable task templates and parameterization
8. **Batch Operations**: Bulk task operations and management
9. **Resource Management**: Memory limits, task quotas, and resource monitoring
10. **Integration Hooks**: Callbacks and webhooks for task lifecycle events
11. **Performance Optimization**: Async task processing and parallelization
12. **Audit Trail**: Complete audit log of all task operations and state changes

## Integration Points

- **TimeService**: Provides consistent timestamps and scheduling calculations
- **Database**: SQLite integration for task and thought persistence
- **DEFER System**: Handles time-based task deferrals and reactivation
- **Thought System**: Creates thoughts when scheduled tasks trigger
- **Audit Service**: Could log task creation, execution, and lifecycle events
- **Memory Graph**: Can store task nodes for long-term analysis
- **API Layer**: Exposes task management via REST endpoints
- **BaseService**: Inherits standard service lifecycle and metrics

## Monitoring Recommendations

1. **Task Execution Monitoring**: Alert on failed task executions or high error rates
2. **Schedule Drift**: Monitor for tasks not executing on schedule
3. **Memory Usage**: Track active task count and memory consumption
4. **Database Health**: Monitor database connections and query performance
5. **Cron Validation**: Alert on invalid cron expressions or parsing errors
6. **Service Health**: Monitor background task status and uptime
7. **Deferral Patterns**: Track excessive deferrals that might indicate system issues
8. **Performance Degradation**: Monitor task execution timing and delays
9. **Resource Limits**: Alert when approaching task count or memory limits
10. **Integration Issues**: Monitor failures in thought creation or database operations

## Performance Considerations

1. **Check Interval**: Lower check intervals provide better timing precision but higher CPU usage
2. **Task Count**: Large numbers of active tasks can impact memory usage and check performance
3. **Database I/O**: Task persistence operations can add latency
4. **Time Calculations**: Cron calculations and time comparisons add compute overhead
5. **Memory Growth**: Task history and deferral records can accumulate over time
6. **Concurrent Access**: Multiple threads accessing task data could cause race conditions
7. **Background Task**: Continuous loop adds steady CPU and memory overhead
8. **Error Handling**: Exception handling and logging can impact performance during failures

## System Integration

The Task Scheduler Service is critical for CIRIS's proactive behavior and time-based intelligence:
- Enables agents to schedule future actions and maintain long-term goals
- Integrates with the DEFER system for sophisticated time-based reasoning
- Supports both reactive (deferred) and proactive (scheduled) task management
- Provides the foundation for agent self-management and autonomous planning
- Maintains task history for learning and pattern recognition

The service acts as the "temporal memory" of CIRIS agents, allowing them to remember commitments, schedule future actions, and maintain continuity across time periods while providing comprehensive telemetry for monitoring and optimization.
