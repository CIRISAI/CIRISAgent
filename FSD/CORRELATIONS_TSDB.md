# Functional Specification Document: Correlations-Based Time Series Database

**PATENT PENDING**

## Overview

This FSD outlines the enhancement of CIRIS Agent's existing correlations system into a unified Time Series Database (TSDB) that handles metrics, logs, traces, and audit data while maintaining agent introspection capabilities through the graph memory interface.

## Motivation

Currently, we have separate systems for:
- Correlations (service interactions)
- Metrics (telemetry data)
- Logs (application logs)
- Audit (action tracking)

**The Goal**: Unify these into a single TSDB built on correlations that:
- Leverages existing persistence infrastructure
- Makes all telemetry data agent-introspectable via RECALL/MEMORIZE/FORGET
- Provides time-based filtering and data retention
- Maintains clean architectural separation

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Agent Memory Interface                 │
│    RECALL/MEMORIZE/FORGET with time + metric filters       │
└─────────────────────┬───────────────────────────────────────┘
                      │
┌─────────────────────▼───────────────────────────────────────┐
│                Correlations TSDB Layer                     │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌────────┐ │
│  │   Metrics   │ │    Logs     │ │   Traces    │ │ Audit  │ │
│  │ Correlations│ │Correlations │ │Correlations │ │ Events │ │
│  └─────────────┘ └─────────────┘ └─────────────┘ └────────┘ │
└─────────────────────┬───────────────────────────────────────┘
                      │
┌─────────────────────▼───────────────────────────────────────┐
│              Enhanced Correlations Schema                   │
│     service_correlations table with TSDB capabilities      │
└─────────────────────┬───────────────────────────────────────┘
                      │
┌─────────────────────▼───────────────────────────────────────┐
│                 Correlations Cleaner                       │
│   Data retention and summarization service                 │
└─────────────────────────────────────────────────────────────┘
```

## Enhanced Correlations Schema

### Core TSDB Correlation Types

```python
class CorrelationType(str, Enum):
    # Existing
    SERVICE_INTERACTION = "service_interaction"

    # New TSDB Types
    METRIC_DATAPOINT = "metric_datapoint"
    LOG_ENTRY = "log_entry"
    TRACE_SPAN = "trace_span"
    AUDIT_EVENT = "audit_event"

    # Summarized Types (for retention)
    METRIC_HOURLY_SUMMARY = "metric_hourly_summary"
    METRIC_DAILY_SUMMARY = "metric_daily_summary"
    LOG_HOURLY_SUMMARY = "log_hourly_summary"
```

### Enhanced ServiceCorrelation Schema

```python
class ServiceCorrelation(BaseModel):
    # Existing fields
    correlation_id: str
    service_type: str
    handler_name: str
    action_type: str
    request_data: Dict[str, Any]
    response_data: Dict[str, Any]
    status: ServiceCorrelationStatus
    created_at: str
    updated_at: str

    # New TSDB fields
    correlation_type: CorrelationType = CorrelationType.SERVICE_INTERACTION
    timestamp: datetime  # Indexed timestamp for time queries
    metric_name: Optional[str] = None  # For metric correlations
    metric_value: Optional[float] = None  # For metric correlations
    log_level: Optional[str] = None  # For log correlations
    trace_id: Optional[str] = None  # For distributed tracing
    span_id: Optional[str] = None  # For trace spans
    parent_span_id: Optional[str] = None  # For trace hierarchy
    tags: Dict[str, str] = Field(default_factory=dict)  # Flexible tagging
    retention_policy: str = "raw"  # raw, hourly_summary, daily_summary
```

## Memory Interface Extensions

### Enhanced Memory Operations with Time Filters

```python
class TimeFilter(BaseModel):
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    time_range: Optional[str] = None  # "1h", "24h", "7d"

class MetricFilter(BaseModel):
    metric_names: Optional[List[str]] = None
    correlation_types: Optional[List[CorrelationType]] = None
    log_levels: Optional[List[str]] = None
    tags: Optional[Dict[str, str]] = None

class TSDBGraphNode(GraphNode):
    """Extended GraphNode for TSDB queries"""
    time_filter: Optional[TimeFilter] = None
    metric_filter: Optional[MetricFilter] = None
```

### Memory Service Extensions

```python
class MemoryService:
    async def recall_timeseries(
        self,
        node: TSDBGraphNode,
        time_filter: TimeFilter,
        metric_filter: MetricFilter
    ) -> MemoryOpResult:
        """Recall time-filtered correlation data"""

    async def memorize_metric(
        self,
        metric_name: str,
        value: float,
        timestamp: datetime,
        tags: Dict[str, str]
    ) -> MemoryOpResult:
        """Store metric as correlation"""

    async def memorize_log(
        self,
        log_entry: str,
        level: str,
        timestamp: datetime,
        tags: Dict[str, str]
    ) -> MemoryOpResult:
        """Store log entry as correlation"""
```

## Data Retention Strategy

### Correlations Cleaner Service

```python
class CorrelationsCleanerService:
    async def summarize_hourly_metrics(self):
        """Aggregate raw metrics into hourly summaries after 1 hour"""

    async def summarize_daily_metrics(self):
        """Aggregate hourly summaries into daily summaries after 24 hours"""

    async def cleanup_raw_data(self):
        """Remove raw data older than retention policy"""

    async def cleanup_logs(self):
        """Summarize/remove old log entries"""
```

### Retention Policies

| Data Type | Raw Retention | Hourly Summary | Daily Summary |
|-----------|---------------|----------------|---------------|
| Metrics | 1 hour | 24 hours | 30 days |
| Logs | 2 hours | 24 hours | 7 days |
| Audit Events | 7 days | 30 days | 1 year |
| Service Correlations | 24 hours | 30 days | 90 days |
| Traces | 1 hour | 24 hours | 7 days |

## API Extensions

### New TSDB API Endpoints

```bash
# Time-filtered correlation queries
GET /v1/correlations/timeseries?start=2025-06-09T10:00:00Z&end=2025-06-09T11:00:00Z&type=metric_datapoint

# Metric-specific queries
GET /v1/correlations/metrics/{metric_name}?range=24h

# Log queries with level filtering
GET /v1/correlations/logs?level=ERROR&range=1h

# Trace reconstruction
GET /v1/correlations/traces/{trace_id}

# Agent introspection - memory with time filters
POST /v1/memory/{scope}/recall_timeseries
{
  "time_filter": {"time_range": "24h"},
  "metric_filter": {"correlation_types": ["metric_datapoint"], "metric_names": ["cpu_usage"]}
}
```

## Implementation Plan

### Phase 1: Schema Enhancement
1. **Extend ServiceCorrelation** with TSDB fields
2. **Add database migrations** for new columns
3. **Update correlation persistence** to handle new types
4. **Create CorrelationType enum** with all supported types

### Phase 2: TSDB Data Ingestion
1. **Enhance TelemetryService** to write metrics as correlations
2. **Create LogCorrelationCollector** to capture log entries
3. **Extend AuditService** to use correlations
4. **Add TraceCorrelationCollector** for distributed tracing

### Phase 3: Memory Interface Extensions
1. **Extend MemoryService** with time-filtered operations
2. **Add TSDBGraphNode** support
3. **Implement recall_timeseries()** method
4. **Add memorize_metric/log** convenience methods

### Phase 4: Correlations Cleaner Service
1. **Create CorrelationsCleanerService**
2. **Implement retention policies**
3. **Add data summarization logic**
4. **Schedule cleanup tasks**

### Phase 5: API Integration
1. **Add TSDB endpoints** to API
2. **Extend CIRISClient** with TSDB methods
3. **Update CIRISGui** with time-series visualizations
4. **Add memory interface API** for agent introspection

## Data Flow Examples

### Metric Collection Flow
```
1. Agent processes thought -> metrics generated
2. TelemetryService.record_metric() -> creates METRIC_DATAPOINT correlation
3. Agent can RECALL metrics via memory interface with time filters
4. CorrelationsCleanerService summarizes hourly -> METRIC_HOURLY_SUMMARY
5. Old raw data cleaned up per retention policy
```

### Log Aggregation Flow
```
1. Application logs generated -> LogCorrelationCollector captures
2. Creates LOG_ENTRY correlations with timestamps
3. Agent can RECALL logs via memory interface: "show me ERROR logs from last hour"
4. CorrelationsCleanerService summarizes/cleans old logs
```

### Audit Trail Flow
```
1. Agent action -> AuditService.log_action() -> AUDIT_EVENT correlation
2. Creates audit correlation with action details
3. Agent can introspect: "RECALL my actions from yesterday"
4. Long-term retention for audit compliance
```

### Distributed Tracing Flow
```
1. Request spans multiple services -> TraceCorrelationCollector
2. Creates TRACE_SPAN correlations with trace_id/span_id
3. Agent can reconstruct traces: "RECALL the processing flow for thought X"
4. Trace relationships preserved in correlation hierarchy
```

## Agent Introspection Capabilities

With this system, the agent gains powerful self-awareness:

```python
# Agent can explore its own metrics
memory_service.recall_timeseries(
    TSDBGraphNode(id="cpu_usage", scope=GraphScope.LOCAL),
    TimeFilter(time_range="24h"),
    MetricFilter(correlation_types=[CorrelationType.METRIC_DATAPOINT])
)

# Agent can review its own decision history
memory_service.recall_timeseries(
    TSDBGraphNode(id="agent_actions", scope=GraphScope.IDENTITY),
    TimeFilter(time_range="7d"),
    MetricFilter(correlation_types=[CorrelationType.AUDIT_EVENT])
)

# Agent can analyze its error patterns
memory_service.recall_timeseries(
    TSDBGraphNode(id="error_logs", scope=GraphScope.LOCAL),
    TimeFilter(time_range="24h"),
    MetricFilter(log_levels=["ERROR", "CRITICAL"])
)
```

## Future-Oriented Scheduling with MEMORIZE

The TSDB integrates with the agent's proactive task scheduling system through future-dated MEMORIZE operations:

### Scheduling Mechanism
```python
# Agent schedules a future task by MEMORIZing into the future
memory_service.memorize(
    GraphNode(
        id="scheduled_tasks/task-123",
        scope=GraphScope.LOCAL,
        attributes={
            "scheduled_for": "2025-06-16T10:00:00Z",  # Future timestamp
            "task_type": "MAINTENANCE",
            "action": "Run database optimization",
            "priority": "medium",
            "created_at": "2025-06-15T14:30:00Z"
        }
    )
)

# The TSDB stores this as a future-dated correlation
CorrelationEvent(
    correlation_type=CorrelationType.SCHEDULED_TASK,
    timestamp="2025-06-16T10:00:00Z",  # Future execution time
    service_a="task_scheduler",
    service_b="agent_self",
    attributes={
        "task_id": "task-123",
        "status": "scheduled"
    }
)
```

### Task Scheduler Integration
```python
# TaskSchedulerService queries TSDB for upcoming tasks
upcoming_tasks = await tsdb.query_future_correlations(
    correlation_type=CorrelationType.SCHEDULED_TASK,
    time_range=TimeRange(start=now, end=now + timedelta(hours=24)),
    status="scheduled"
)

# Agent can introspect its own scheduled future
memory_service.recall_timeseries(
    TSDBGraphNode(id="scheduled_tasks", scope=GraphScope.LOCAL),
    TimeFilter(future_range="7d"),  # Look 7 days into the future
    MetricFilter(correlation_types=[CorrelationType.SCHEDULED_TASK])
)
```

### Self-Deferral Pattern
```python
# Agent defers to its future self by scheduling a task
def defer_to_future_self(task_description: str, defer_until: datetime):
    # Create scheduled task in TSDB via MEMORIZE
    memory_service.memorize(
        GraphNode(
            id=f"deferred_tasks/{uuid4()}",
            attributes={
                "task": task_description,
                "defer_until": defer_until.isoformat(),
                "reason": "Deferring to future self for better context"
            }
        )
    )

    # TSDB creates future correlation for task activation
    # TaskScheduler will trigger at specified time
```

This approach enables:
- **Proactive Behavior**: Agent schedules its own future activities
- **Time-Aware Memory**: TSDB handles both past and future correlations
- **Self-Management**: Agent can defer complex decisions to future iterations
- **Introspection**: Agent can query what it has scheduled for itself
- **Persistence**: Scheduled tasks survive restarts via TSDB storage

## Benefits

1. **Unified Storage**: Single persistence layer for all telemetry data
2. **Agent Introspection**: Agent can explore its own metrics/logs/audit history
3. **Time-based Queries**: Natural time filtering for all data types
4. **Data Retention**: Automatic summarization and cleanup
5. **Existing Infrastructure**: Builds on proven correlations system
6. **Clean Architecture**: Maintains separation of concerns
7. **Scalability**: Efficient storage with retention policies
8. **Debugging**: Complete system observability through single interface

## Migration Strategy

1. **Phase 1**: Enhance schema, maintain backward compatibility
2. **Phase 2**: Gradually migrate telemetry systems to use correlations
3. **Phase 3**: Add TSDB query capabilities
4. **Phase 4**: Enable agent introspection features
5. **Phase 5**: Deprecate old separate storage systems

## Testing Strategy

1. **Unit Tests**: Each component (TelemetryService, CorrelationsCleanerService, etc.)
2. **Integration Tests**: End-to-end TSDB workflows
3. **Performance Tests**: Time-series query performance with large datasets
4. **Retention Tests**: Data summarization and cleanup verification
5. **Agent Introspection Tests**: Memory interface with time filters

## Success Metrics

- **Storage Efficiency**: Reduction in duplicate storage systems
- **Query Performance**: Sub-100ms response for time-filtered queries
- **Data Retention**: Automatic cleanup maintaining <1GB database size
- **Agent Capabilities**: Agent can successfully introspect its own telemetry
- **API Adoption**: CIRISGui successfully visualizes time-series data

This unified TSDB approach transforms correlations into a comprehensive observability platform while maintaining the elegant agent introspection capabilities that make CIRIS unique.

---

*Copyright © 2025 Eric Moore and CIRIS L3C - AGPL-3.0 License*
