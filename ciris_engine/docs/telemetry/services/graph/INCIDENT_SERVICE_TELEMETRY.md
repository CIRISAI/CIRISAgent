# Incident Service Telemetry

## Overview
The Incident Management Service is ITIL-aligned incident processing service that provides self-improvement through systematic analysis of operational incidents. It captures WARNING/ERROR logs, detects patterns, identifies problems, and generates actionable insights during dream cycles. The service stores all data as graph nodes and provides both in-memory statistics and persistent graph storage.

## Telemetry Data Collected

| Metric Name | Type | Storage | Update Frequency | Access Method |
|------------|------|---------|------------------|---------------|
| incidents_processed | counter | computed | per analysis cycle | method: `get_incident_count()` |
| patterns_detected | counter | graph memory | per analysis cycle | computed from insights |
| problems_identified | counter | graph memory | per analysis cycle | computed from problems |
| insights_generated | counter | graph memory | per analysis cycle | graph query |
| analysis_cycles_completed | counter | computed | per dream cycle | implicit tracking |
| incident_severity_distribution | histogram | graph memory | per incident | computed from incidents |
| incident_component_distribution | histogram | graph memory | per incident | computed from incidents |
| incident_time_distribution | histogram | graph memory | per incident | computed from incidents |
| recommendations_generated | counter | graph memory | per insight | computed from insights |
| service_availability | gauge | in-memory | real-time | `get_status().metrics` |
| memory_bus_connectivity | gauge | in-memory | real-time | `get_status().metrics` |
| recent_incidents_cache | gauge | computed | on query | `_get_recent_incidents()` |
| pattern_detection_effectiveness | computed | graph memory | per analysis | derived metric |
| problem_resolution_tracking | counter | graph memory | on resolution | graph query |

## Data Structures

### IncidentNode (Primary Data Structure)
```python
{
    "id": "incident_20250814_133045_1234",
    "type": "AUDIT_ENTRY",
    "scope": "LOCAL",
    "attributes": {
        "incident_type": "ERROR",
        "severity": "HIGH",
        "status": "OPEN",
        "description": "Failed to connect to external API",
        "source_component": "api_client",
        "detection_method": "AUTOMATED_LOG_MONITORING",
        "detected_at": "2025-08-14T13:30:45Z",
        "resolved_at": null,
        "impact": "TBD",
        "urgency": "MEDIUM",
        "correlation_id": "trace-12345",
        "task_id": "task-67890",
        "thought_id": "thought-abc123",
        "handler_name": "api_request_handler",
        "exception_type": "ConnectionTimeoutError",
        "stack_trace": "Traceback...",
        "filename": "api_client.py",
        "line_number": 142,
        "function_name": "make_request",
        "problem_id": null,
        "related_incidents": []
    },
    "created_at": "2025-08-14T13:30:45Z",
    "updated_by": "IncidentManagementService",
    "updated_at": "2025-08-14T13:30:45Z"
}
```

### ProblemNode (Root Cause Analysis)
```python
{
    "id": "problem_recurring_error_connection_timeout_0",
    "type": "CONCEPT",
    "scope": "IDENTITY",
    "attributes": {
        "problem_statement": "Recurring error: Connection timeout (occurred 5 times)",
        "affected_incidents": ["incident_1", "incident_2", "incident_3", "incident_4", "incident_5"],
        "status": "UNDER_INVESTIGATION",
        "potential_root_causes": [
            "Timeout configuration may be too aggressive",
            "Network connectivity or service availability issues"
        ],
        "recommended_actions": [
            "Increase timeout values in configuration",
            "Implement retry logic with exponential backoff",
            "Add connection pooling and retry logic"
        ],
        "incident_count": 5,
        "first_occurrence": "2025-08-14T10:30:00Z",
        "last_occurrence": "2025-08-14T13:30:00Z",
        "resolution": null,
        "resolved_at": null
    }
}
```

### IncidentInsightNode (Analysis Results)
```python
{
    "id": "incident_insight_20250814_140000",
    "type": "CONCEPT",
    "scope": "LOCAL",
    "attributes": {
        "insight_type": "PERIODIC_ANALYSIS",
        "summary": "Analyzed 25 incidents, found 3 patterns and identified 2 problems requiring attention",
        "details": {
            "incident_count": 25,
            "pattern_count": 3,
            "problem_count": 2,
            "severity_breakdown": {
                "CRITICAL": 2,
                "HIGH": 8,
                "MEDIUM": 12,
                "LOW": 3
            },
            "component_breakdown": {
                "api_client": 10,
                "database": 7,
                "message_handler": 5,
                "unknown": 3
            },
            "time_distribution": {
                "2025-08-14 10:00": 5,
                "2025-08-14 11:00": 8,
                "2025-08-14 12:00": 7,
                "2025-08-14 13:00": 5
            }
        },
        "behavioral_adjustments": [
            "Add additional error handling and logging to api_client",
            "Implement periodic memory cleanup in long-running operations"
        ],
        "configuration_changes": [
            "Consider increasing timeout values for affected operations",
            "Increase memory limits or implement memory usage monitoring"
        ],
        "source_incidents": ["incident_1", "incident_2", ...],
        "source_problems": ["problem_1", "problem_2"],
        "analysis_timestamp": "2025-08-14T14:00:00Z",
        "applied": false,
        "effectiveness_score": null
    }
}
```

### Pattern Detection Results
```python
{
    "recurring_error_connection_timeout": [
        # List of IncidentNode objects with similar errors
    ],
    "component_issues_api_client": [
        # List of incidents from same component
    ],
    "error_spike_0": [
        # List of incidents clustered in time
    ]
}
```

## API Access Patterns

### Current Access
- **Internal Storage**: All incidents, problems, and insights stored as graph nodes via memory bus
- **No Direct API**: No REST endpoints expose incident data directly
- **Graph Queries Required**: Must query graph database for incident analytics
- **Service Status**: Basic health metrics available via `get_status()`

### Recommended Endpoints

#### Get Incident Count
```
GET /v1/incidents/count?hours=24
```
Returns count of incidents in time window:
```json
{
    "count": 15,
    "window_hours": 24,
    "severity_breakdown": {
        "CRITICAL": 1,
        "HIGH": 4,
        "MEDIUM": 7,
        "LOW": 3
    }
}
```

#### Get Recent Incidents
```
GET /v1/incidents/recent?hours=24&limit=100
```
Returns recent incidents with filtering:
```json
{
    "incidents": [
        {
            "id": "incident_20250814_133045_1234",
            "severity": "HIGH",
            "status": "OPEN",
            "description": "Failed to connect to external API",
            "source_component": "api_client",
            "detected_at": "2025-08-14T13:30:45Z"
        }
    ],
    "total_count": 15,
    "filtered_count": 15
}
```

#### Get Incident Patterns
```
GET /v1/incidents/patterns?hours=168
```
Returns detected patterns:
```json
{
    "patterns": [
        {
            "pattern_key": "recurring_error_connection_timeout",
            "incident_count": 5,
            "description": "Connection timeout errors",
            "first_occurrence": "2025-08-14T10:30:00Z",
            "last_occurrence": "2025-08-14T13:30:00Z"
        }
    ],
    "analysis_window_hours": 168
}
```

#### Get Problems
```
GET /v1/incidents/problems?status=UNDER_INVESTIGATION
```
Returns identified problems:
```json
{
    "problems": [
        {
            "id": "problem_recurring_error_connection_timeout_0",
            "problem_statement": "Recurring error: Connection timeout (occurred 5 times)",
            "status": "UNDER_INVESTIGATION",
            "incident_count": 5,
            "potential_root_causes": [
                "Timeout configuration may be too aggressive"
            ],
            "recommended_actions": [
                "Increase timeout values in configuration"
            ]
        }
    ]
}
```

#### Get Insights
```
GET /v1/incidents/insights?limit=10
```
Returns recent insights:
```json
{
    "insights": [
        {
            "id": "incident_insight_20250814_140000",
            "insight_type": "PERIODIC_ANALYSIS",
            "summary": "Analyzed 25 incidents, found 3 patterns and identified 2 problems",
            "analysis_timestamp": "2025-08-14T14:00:00Z",
            "recommendations_count": 4
        }
    ]
}
```

## Graph Storage

### Node Types Created
- `INCIDENT` (mapped to AUDIT_ENTRY) - Individual incidents from logs
- `PROBLEM` (mapped to CONCEPT) - Root cause problems identified from patterns
- `INCIDENT_INSIGHT` (mapped to CONCEPT) - Analysis results and recommendations

### Edge Relationships
- `CAUSED_BY` - Links incident to problem
- `ANALYZED_IN` - Links incident to insight
- `DERIVED_FROM` - Links insight to source incidents and problems
- `RESOLVED_BY` - Links problem to resolution action

### Memory Scopes
- **LOCAL**: Incidents and insights (operational data)
- **IDENTITY**: Problems (self-knowledge about recurring issues)

### Storage Patterns
- Incidents stored immediately upon detection
- Problems stored when patterns are identified (≥3 related incidents)
- Insights stored during dream cycle analysis
- No automatic expiration - relies on graph consolidation policies

## Example Usage

### Process Recent Incidents (Dream Cycle)
```python
incident_service = get_service(ServiceType.INCIDENT_MANAGEMENT)

# Called during dream cycle for self-improvement
insight = await incident_service.process_recent_incidents(hours=24)

print(f"Analysis summary: {insight.summary}")
print(f"Behavioral adjustments: {insight.behavioral_adjustments}")
print(f"Configuration changes: {insight.configuration_changes}")
```

### Get Incident Count
```python
incident_count = await incident_service.get_incident_count(hours=6)
print(f"Incidents in last 6 hours: {incident_count}")
```

### Query Recent Incidents Directly
```python
from datetime import datetime, timedelta

cutoff_time = datetime.now() - timedelta(hours=12)
incidents = await incident_service._get_recent_incidents(cutoff_time)

for incident in incidents:
    print(f"Incident: {incident.description} (Severity: {incident.severity})")
```

### Check Service Health
```python
status = incident_service.get_status()
print(f"Service healthy: {status.is_healthy}")
print(f"Memory bus available: {status.metrics['service_available']}")
```

## Testing

### Test Files
- `tests/ciris_engine/logic/services/graph/test_incident_service.py` - Service unit tests
- `tests/test_incident_capture_handler.py` - Integration tests

### Validation Steps
1. Create test incidents via log parsing or direct creation
2. Verify incidents stored as AUDIT_ENTRY nodes in graph
3. Run pattern detection and verify patterns identified
4. Check problem creation from recurring patterns
5. Validate insight generation during analysis cycles
6. Verify service health and status reporting

```python
async def test_incident_telemetry_flow():
    incident_service = IncidentManagementService(memory_bus, time_service)

    # Test incident count
    count = await incident_service.get_incident_count(hours=1)
    assert count >= 0

    # Test incident processing
    insight = await incident_service.process_recent_incidents(hours=24)
    assert insight.insight_type in ["PERIODIC_ANALYSIS", "NO_INCIDENTS"]

    # Test service health
    status = incident_service.get_status()
    assert status.service_name == "IncidentManagementService"
    assert "service_available" in status.metrics
```

## Configuration

### Analysis Settings
```python
{
    "analysis_window_hours": 24,          # Default incident lookback
    "pattern_threshold": 3,               # Min incidents for pattern
    "cluster_threshold_minutes": 5,       # Time clustering window
    "component_threshold": 5,             # Min incidents per component
}
```

### Log File Integration
```python
{
    "log_file_path": "/app/logs/incidents_latest.log",
    "log_format": "%Y-%m-%d %H:%M:%S.%f - %s - %s - %s - %s",
    "fallback_to_file": True,             # Use file if memory bus fails
}
```

## Known Limitations

1. **No Real-Time Metrics**: Telemetry computed on-demand, not continuously collected
2. **Graph Query Dependency**: All analytics require graph database queries
3. **No Retention Policies**: Incidents stored indefinitely without cleanup
4. **Limited Pattern Detection**: Simple similarity-based grouping only
5. **No Alerting Integration**: No automatic notification of critical patterns
6. **Single-Instance View**: No cross-instance incident aggregation
7. **Memory Bus Dependency**: Service degraded if memory bus unavailable
8. **Log File Fallback**: Basic log parsing with limited metadata extraction

## Future Enhancements

1. **Real-Time Telemetry**: Continuous metric collection and updating
2. **Advanced Pattern Detection**: Machine learning-based pattern recognition
3. **Alerting Integration**: Automatic alerts for critical incident patterns
4. **Cross-Instance Analytics**: Aggregate incidents across multiple CIRIS instances
5. **Retention Policies**: Configurable incident cleanup and archival
6. **Performance Metrics**: Track analysis performance and optimization
7. **Integration APIs**: REST endpoints for external monitoring systems
8. **Predictive Analytics**: Forecast potential issues based on trends

## Integration Points

- **MemoryBus**: Primary storage for all incident data
- **TimeService**: Consistent timestamps for incident tracking
- **Dream Cycle**: Triggered analysis during DREAM cognitive state
- **Log Monitoring**: Automatic incident capture from application logs
- **Self-Observation Service**: Behavioral adjustment integration
- **Audit Service**: Cross-referencing with audit trail data

## Monitoring Recommendations

1. **Incident Rate**: Monitor incidents per hour/day for trend analysis
2. **Pattern Detection Rate**: Track how often patterns are identified
3. **Problem Resolution Rate**: Monitor how quickly problems are addressed
4. **Insight Application Rate**: Track whether recommendations are implemented
5. **Service Availability**: Monitor memory bus connectivity
6. **Analysis Performance**: Track time taken for incident analysis cycles
7. **Storage Growth**: Monitor graph node creation rate for incidents

## Performance Considerations

1. **Graph Storage Overhead**: Each incident creates multiple graph operations
2. **Analysis Complexity**: Pattern detection scales with incident count
3. **Memory Usage**: Large incident datasets can consume significant memory
4. **Query Performance**: Complex analytics require expensive graph queries
5. **File I/O Fallback**: Log file parsing can be slow for large files
6. **Batch Processing**: Analysis runs in batches during dream cycles only

## Architecture Notes

The Incident Management Service embodies the CIRIS principle of "learning from every failure":

- **Incidents as Learning Opportunities**: Every WARNING/ERROR becomes structured learning data
- **Pattern-Based Self-Improvement**: Recurring issues are systematically identified and addressed
- **Dream Cycle Integration**: Analysis happens during reflection periods, not disrupting operational flow
- **Graph-Based Memory**: All incidents become part of the system's permanent memory for future reference
- **ITIL Alignment**: Professional incident management practices adapted for autonomous systems
- **Proactive Problem Management**: Root cause analysis prevents incident recurrence

The service transforms operational problems into structured knowledge, supporting the meta-goal of adaptive coherence by continuously improving system reliability and resilience.

## Sample Queries

### Get Incident Statistics
```cypher
MATCH (n:AUDIT_ENTRY)
WHERE n.attributes.incident_type IS NOT NULL
RETURN
    count(n) as total_incidents,
    n.attributes.severity as severity,
    count(*) as count
ORDER BY severity
```

### Find Recurring Problems
```cypher
MATCH (p:CONCEPT)
WHERE p.attributes.problem_statement IS NOT NULL
AND p.attributes.incident_count >= 3
RETURN p.id, p.attributes.problem_statement, p.attributes.incident_count
ORDER BY p.attributes.incident_count DESC
```

### Get Recent Insights
```cypher
MATCH (i:CONCEPT)
WHERE i.attributes.insight_type IS NOT NULL
AND datetime(i.attributes.analysis_timestamp) > datetime() - duration('P1D')
RETURN i.id, i.attributes.summary, i.attributes.analysis_timestamp
ORDER BY i.attributes.analysis_timestamp DESC
```
