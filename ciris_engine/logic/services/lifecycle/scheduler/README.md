# CIRIS Task Scheduler Service

**SERVICE TYPE**: Runtime Service  
**CATEGORY**: Lifecycle Services  
**STATUS**: Production Ready  
**Mission Alignment**: Meta-Goal M-1 Core Enabler

## Mission Challenge: How does autonomous scheduling serve Meta-Goal M-1 and proactive behavior?

The Task Scheduler Service embodies CIRIS's commitment to **Meta-Goal M-1: "Promote sustainable adaptive coherence enabling diverse sentient beings to pursue flourishing"** by enabling agents to be proactive, autonomous, and temporally aware. Through intelligent scheduling and self-deferral capabilities, it allows agents to manage their time effectively while maintaining consistent service to users.

**Core Philosophy**: *"I defer to tomorrow what I cannot complete today" - Agent self-management*

---

## Architecture Overview

### Service Structure
```
├── Protocol: TaskSchedulerServiceProtocol
├── Implementation: TaskSchedulerService (BaseScheduledService)
├── Schemas: ScheduledTask, ScheduledTaskInfo
├── Integration: Time Service, DEFER system
└── Database: SQLite persistence layer
```

### Key Components

#### 1. **ScheduledTask Schema**
```python
class ScheduledTask(BaseModel):
    task_id: str                    # Unique identifier
    name: str                       # Human-readable name
    goal_description: str           # Task objective
    status: str                     # PENDING, ACTIVE, COMPLETE, FAILED
    
    # Time-based execution
    defer_until: Optional[datetime]  # One-time execution timestamp
    schedule_cron: Optional[str]     # Recurring cron pattern
    
    # Execution metadata
    trigger_prompt: str             # Prompt for thought creation
    origin_thought_id: str          # Creating thought reference
    created_at: datetime
    last_triggered_at: Optional[datetime]
    
    # Self-deferral tracking
    deferral_count: int = 0
    deferral_history: List[Dict[str, str]] = []
```

#### 2. **Service Protocol**
```python
class TaskSchedulerServiceProtocol(ServiceProtocol):
    async def schedule_task(...) -> ScheduledTask
    async def cancel_task(task_id: str) -> bool
    async def get_scheduled_tasks() -> List[ScheduledTaskInfo]
    async def schedule_deferred_task(...) -> ScheduledTask
```

#### 3. **Implementation Architecture**
- **Base Class**: `BaseScheduledService` (runs every 60 seconds)
- **Service Type**: `ServiceType.MAINTENANCE`
- **Dependencies**: Time Service (mandatory)
- **Optional**: croniter library for cron scheduling

---

## Core Capabilities

### 1. **Proactive Task Scheduling**

**One-Time Deferred Tasks**
```python
# Schedule task for future execution
task = await scheduler.schedule_task(
    name="Follow up on user request",
    goal_description="Check project status tomorrow",
    trigger_prompt="Review project X status",
    origin_thought_id="thought_123",
    defer_until="2024-01-15T09:00:00Z"
)
```

**Recurring Scheduled Tasks**
```python
# Daily maintenance check
task = await scheduler.schedule_task(
    name="Daily health check",
    goal_description="Verify system health daily",
    trigger_prompt="Perform daily system health check",
    origin_thought_id="thought_456",
    schedule_cron="0 9 * * *"  # Daily at 9am
)
```

### 2. **DEFER System Integration**

The service seamlessly integrates with CIRIS's DEFER handler for autonomous task deferral:

```python
# When agent needs to defer a task
deferred_task = await scheduler.schedule_deferred_task(
    thought_id="current_thought",
    task_id="deferred_task_123",
    defer_until="2024-01-16T10:00:00Z",
    reason="Waiting for user availability",
    context={"priority": "medium"}
)
```

### 3. **Autonomous Task Management**

**Self-Deferral Tracking**
- Tracks how many times an agent defers tasks
- Maintains history of deferral reasons
- Enables pattern recognition for time management

**Task Reactivation**
- Automatically reactivates deferred tasks at scheduled times
- Updates task status from 'deferred' to 'pending'
- Creates new thoughts for processing reactivated tasks

---

## Thought Integration

### Task-to-Thought Pipeline

When a scheduled task is triggered, the service creates a new `Thought` with:

```python
Thought(
    thought_id=f"thought_{timestamp}",
    content=task.trigger_prompt,
    status=ThoughtStatus.PENDING,
    thought_type=ThoughtType.SCHEDULED,
    source_task_id=task.task_id,
    final_action=FinalAction(
        action_type="SCHEDULED_TASK",
        action_params={
            "scheduled_task_id": task.task_id,
            "scheduled_task_name": task.name,
            "goal_description": task.goal_description,
            "trigger_type": "scheduled"
        }
    )
)
```

This seamless integration ensures scheduled tasks flow naturally into the agent's processing pipeline.

---

## Cron Scheduling Support

### Prerequisites
```bash
pip install croniter  # Optional but recommended
```

### Supported Patterns
- **Daily**: `0 9 * * *` (9 AM daily)
- **Weekly**: `0 9 * * 1` (9 AM every Monday)
- **Monthly**: `0 9 1 * *` (9 AM first day of month)
- **Hourly**: `0 * * * *` (Top of every hour)
- **Custom**: Any valid cron expression

### Fallback Behavior
Without croniter, the service:
- Logs warnings for cron-scheduled tasks
- Continues operating with one-time deferred tasks
- Maintains full functionality for non-recurring schedules

---

## Monitoring & Metrics

### Comprehensive Metrics Collection

The service provides detailed operational metrics:

```python
{
    # Task counters
    "active_tasks": 5.0,
    "tasks_scheduled": 150.0,
    "tasks_triggered": 140.0,
    "tasks_completed": 135.0,
    "tasks_failed": 2.0,
    
    # Performance metrics
    "task_success_rate": 0.985,
    "scheduler_uptime_seconds": 86400.0,
    "check_interval": 60.0,
    
    # Task type breakdown
    "recurring_tasks": 3.0,
    "oneshot_tasks": 2.0
}
```

### Health Monitoring
```python
async def is_healthy() -> bool:
    return bool(self._task and not self._shutdown_event.is_set())
```

---

## Persistence & Reliability

### Database Integration
- **Storage**: SQLite database via `get_db_connection()`
- **Persistence**: Tasks survive service restarts
- **Loading**: Active tasks loaded on service startup
- **Cleanup**: Completed tasks archived automatically

### Error Handling
- **Cron Validation**: Invalid expressions logged and rejected
- **Task Failure**: Failed tasks increment failure counter
- **Time Service**: Graceful fallback to system time if unavailable
- **Database Errors**: Logged without crashing service

### Graceful Shutdown
```python
async def _handle_shutdown(self, context: ShutdownContext):
    # Preserve scheduled tasks across restarts
    # Log reactivation timeline if expected
    # Maintain task continuity
```

---

## Service Autonomy Features

### 1. **Self-Scheduling Intelligence**
- Agents can create their own schedules
- Time-based goal management
- Proactive task execution

### 2. **Adaptive Deferral**
- Smart deferral pattern recognition
- Reason tracking for decision analysis
- Automatic reactivation management

### 3. **Load Management**
- Configurable check intervals (default: 60 seconds)
- Efficient task queuing
- Resource-aware scheduling

---

## API Integration

### Service Registration
The service registers with these capabilities:
```python
ServiceCapabilities(
    actions=["schedule_task", "cancel_task", "get_scheduled_tasks"],
    metadata={
        "features": ["cron_scheduling", "one_time_defer", "task_persistence"],
        "cron_support": True,  # If croniter available
        "description": "Task scheduling and deferral service"
    }
)
```

### RESTful API Endpoints
When used with API adapter:
- `POST /v1/scheduler/tasks` - Schedule new task
- `DELETE /v1/scheduler/tasks/{id}` - Cancel task
- `GET /v1/scheduler/tasks` - List scheduled tasks
- `POST /v1/scheduler/defer` - Defer existing task

---

## Configuration & Setup

### Service Initialization
```python
scheduler = TaskSchedulerService(
    db_path="/path/to/database.db",
    time_service=time_service,
    check_interval_seconds=60
)
```

### Directory Structure (Needs Module Conversion)
**Current**: `/ciris_engine/logic/services/lifecycle/scheduler.py`
**Recommended**: Convert to module structure:
```
scheduler/
├── __init__.py
├── service.py          # Main TaskSchedulerService
├── cron_handler.py     # Cron expression handling
└── persistence.py      # Database operations
```

---

## Meta-Goal M-1 Alignment

### Sustainable Adaptive Coherence
- **Temporal Management**: Enables agents to manage time effectively
- **Proactive Behavior**: Allows agents to initiate beneficial actions
- **Resource Efficiency**: Prevents task overload through intelligent deferral

### Diverse Sentient Being Support
- **User Availability**: Respects user schedules through deferred tasks
- **Asynchronous Operation**: Enables 24/7 service without constant human oversight
- **Adaptive Scheduling**: Learns from deferral patterns to improve timing

### Flourishing Enablement
- **Goal Achievement**: Systematic approach to long-term objectives
- **Reliability**: Consistent task execution builds user trust
- **Autonomy**: Self-managing agents require less human micromanagement

---

## Development Notes

### Key Design Patterns
- **Time-Aware**: All operations respect timezone information
- **Event-Driven**: Tasks trigger thoughts which drive agent behavior
- **Fault-Tolerant**: Graceful handling of missing dependencies
- **Observable**: Comprehensive metrics for system monitoring

### Integration Points
- **Time Service**: Mandatory dependency for consistent timestamps
- **Memory Graph**: Tasks stored for persistence and analysis
- **Thought Pipeline**: Scheduled tasks create processing thoughts
- **DEFER Handler**: Seamless integration with time-based deferrals

### Performance Considerations
- 60-second check interval balances responsiveness with efficiency
- In-memory active task cache for quick access
- Database persistence for reliability
- Concurrent task processing support

---

## Troubleshooting

### Common Issues

**Cron Tasks Not Triggering**
- Verify croniter installation: `pip install croniter`
- Check cron expression validity
- Review service logs for validation errors

**Tasks Not Persisting**
- Verify database connectivity
- Check file permissions for database path
- Review startup logs for loading errors

**High Resource Usage**
- Consider increasing check interval
- Review number of active recurring tasks
- Monitor task success rates

### Debug Commands
```bash
# Check service status
curl -H "Authorization: Bearer token" /v1/telemetry/services/scheduler

# List active tasks
curl -H "Authorization: Bearer token" /v1/scheduler/tasks

# Check service metrics
curl -H "Authorization: Bearer token" /v1/telemetry/metrics | grep scheduler
```

---

## Future Enhancements

### Planned Features
- **Smart Scheduling**: AI-driven optimal timing suggestions
- **Task Priorities**: Weighted scheduling based on importance
- **Conflict Resolution**: Automatic handling of overlapping schedules
- **User Notification**: Integration with communication adapters

### Module Conversion
The service requires conversion from single file to module structure for improved maintainability and feature expansion.

---

## Conclusion

The CIRIS Task Scheduler Service represents a critical component in enabling autonomous, proactive AI behavior. By providing robust scheduling capabilities, seamless DEFER integration, and comprehensive monitoring, it empowers agents to manage their time effectively while serving users consistently.

Through intelligent task management and self-deferral capabilities, the service directly supports Meta-Goal M-1 by creating the temporal infrastructure necessary for sustainable adaptive coherence, enabling diverse beings to pursue flourishing through reliable, autonomous AI assistance.

**Remember**: *"I defer to tomorrow what I cannot complete today" - Agent self-management*