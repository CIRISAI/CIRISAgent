# Wise Authority Service Telemetry

## Overview
The Wise Authority Service is a governance service that handles authorization, decision deferrals, and wisdom-based guidance within the CIRIS ecosystem. It manages human oversight through the Wisdom-Based Deferral (WBD) system and provides authorization checks for system actions. The service integrates with the WiseBus for guidance requests and maintains deferral state in the SQLite database.

## Telemetry Data Collected

| Metric Name | Type | Storage | Update Frequency | Access Method |
|------------|------|---------|------------------|---------------|
| pending_deferrals | gauge | database query | on status request | `_collect_custom_metrics()` |
| resolved_deferrals | gauge | database query | on status request | `_collect_custom_metrics()` |
| total_deferrals | gauge | calculated | on status request | `sum(pending + resolved)` |
| uptime_seconds | gauge | in-memory | on status request | `_calculate_uptime()` |
| request_count | counter | in-memory | per request | `_track_request()` |
| error_count | counter | in-memory | per error | `_track_error()` |
| error_rate | gauge | calculated | on status request | `error_count / request_count` |
| healthy | boolean | in-memory | on status request | `1.0 if started else 0.0` |
| authorization_checks | counter | not tracked* | per check | N/A |
| guidance_requests | counter | not tracked* | per request | N/A |
| deferral_resolutions | counter | not tracked* | per resolution | N/A |

*Not currently tracked but could be added via `_track_request()` in respective methods.

## Data Structures

### ServiceStatus (from BaseService)
```python
{
    "service_name": "WiseAuthorityService",
    "service_type": "governance_service",
    "is_healthy": true,
    "uptime_seconds": 3600.0,
    "metrics": {
        "pending_deferrals": 5.0,
        "resolved_deferrals": 23.0,
        "total_deferrals": 28.0,
        "uptime_seconds": 3600.0,
        "request_count": 142.0,
        "error_count": 2.0,
        "error_rate": 0.014,
        "healthy": 1.0
    },
    "last_error": "Deferral task-123 not found",
    "last_health_check": "2025-08-14T13:30:00Z"
}
```

### ServiceCapabilities
```python
{
    "service_name": "WiseAuthorityService",
    "actions": [
        "check_authorization",
        "request_approval",
        "get_guidance",
        "send_deferral",
        "get_pending_deferrals",
        "resolve_deferral",
        "grant_permission",
        "revoke_permission",
        "list_permissions"
    ],
    "version": "1.0.0",
    "dependencies": [
        "TimeService",
        "AuthenticationService",
        "GraphAuditService",
        "SecretsService"
    ],
    "metadata": {
        "service_name": "WiseAuthorityService",
        "method_name": "_get_metadata",
        "correlation_id": "550e8400-e29b-41d4-a716-446655440000"
    }
}
```

### PendingDeferral Records
```python
{
    "deferral_id": "defer_task-123_1723641000.123",
    "created_at": "2025-08-14T13:30:00Z",
    "deferred_by": "ciris_agent",
    "task_id": "task-123",
    "thought_id": "thought-456",
    "reason": "Action 'delete_user_data' requires human approval",
    "channel_id": "discord-channel-789",
    "user_id": "user-456",
    "priority": "high",
    "assigned_wa_id": null,
    "requires_role": null,
    "status": "pending"
}
```

### Database Schema Impact
```sql
-- Tasks table stores deferral state
CREATE TABLE tasks (
    task_id TEXT PRIMARY KEY,
    channel_id TEXT NOT NULL,
    description TEXT NOT NULL,
    status TEXT NOT NULL,              -- 'deferred' for pending deferrals
    priority INTEGER DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    context_json TEXT,                 -- Contains deferral metadata
    -- ... other fields
);

-- Context JSON structure for deferrals:
{
    "deferral": {
        "deferral_id": "defer_task-123_1723641000.123",
        "thought_id": "thought-456",
        "reason": "Requires human approval",
        "defer_until": "2025-08-15T13:30:00Z",
        "requires_wa_approval": true,
        "context": {"action": "sensitive_operation"},
        "created_at": "2025-08-14T13:30:00Z",
        "resolution": {                 -- Added when resolved
            "approved": true,
            "reason": "Approved after review",
            "resolved_by": "wa-2025-06-24-AUTH01",
            "resolved_at": "2025-08-14T14:00:00Z"
        }
    },
    "wa_guidance": "Proceed with caution"  -- Added if approved
}
```

## API Access Patterns

### Current Access (via REST API)
- **GET /v1/wa/deferrals** - List pending deferrals
- **POST /v1/wa/deferrals/{id}/resolve** - Resolve a deferral
- **GET /v1/system/services/status** - Service status with metrics
- **GET /v1/system/services/capabilities** - Service capabilities

### Internal Service Access
```python
# Get service metrics
wise_authority = get_service(ServiceType.WISE_AUTHORITY)
status = wise_authority.get_status()
metrics = status.metrics

# Check authorization
authorized = await wise_authority.check_authorization(
    wa_id="wa-2025-06-24-AUTH01",
    action="approve_deferrals"
)

# Get pending deferrals
deferrals = await wise_authority.get_pending_deferrals()
```

## Graph Storage

**Not Used**: Unlike other services, WiseAuthority does not store telemetry in the memory graph. All persistent data (deferrals) is stored in the SQLite database tasks table, and metrics are calculated on-demand from database queries.

**Rationale**: Deferrals require ACID properties and complex queries that SQL handles better than graph storage. The service focuses on governance rather than analytics.

## Example Usage

### Monitor Deferral Metrics
```python
async def monitor_deferrals():
    wise_authority = get_service(ServiceType.WISE_AUTHORITY)
    status = wise_authority.get_status()

    pending = status.metrics["pending_deferrals"]
    resolved = status.metrics["resolved_deferrals"]
    total = status.metrics["total_deferrals"]

    logger.info(f"Deferrals: {pending} pending, {resolved} resolved, {total} total")

    if pending > 10:
        logger.warning("High number of pending deferrals - WA attention needed")
```

### Track Authorization Patterns
```python
async def track_authorization_request(wa_id: str, action: str, resource: str):
    wise_authority = get_service(ServiceType.WISE_AUTHORITY)

    # Check authorization (currently no built-in tracking)
    authorized = await wise_authority.check_authorization(wa_id, action, resource)

    # Manual tracking could be added here
    logger.info(f"Authorization check: {wa_id} -> {action}:{resource} = {authorized}")

    return authorized
```

### Get Deferral Resolution Time
```python
async def analyze_deferral_performance():
    import sqlite3
    import json

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Query resolved deferrals with timing
    cursor.execute("""
        SELECT context_json, updated_at
        FROM tasks
        WHERE status = 'pending'
        AND context_json LIKE '%"resolution":%'
    """)

    resolution_times = []
    for row in cursor.fetchall():
        context = json.loads(row[0])
        if "deferral" in context and "resolution" in context["deferral"]:
            created = context["deferral"]["created_at"]
            resolved = context["deferral"]["resolution"]["resolved_at"]
            # Calculate time difference...

    conn.close()
    return resolution_times
```

## Testing

### Test Files
- `tests/ciris_engine/logic/services/governance/test_wise_authority_service.py`
- `tests/test_wise_bus_deferrals.py`
- `tests/test_wise_bus_broadcast_integration.py`

### Key Test Scenarios
```python
async def test_telemetry_collection():
    # Start service
    wise_authority = WiseAuthorityService(
        time_service=time_service,
        auth_service=auth_service,
        db_path=temp_db
    )
    await wise_authority.start()

    # Create some deferrals
    for i in range(3):
        deferral = DeferralRequest(
            task_id=f"task-{i}",
            thought_id=f"thought-{i}",
            reason=f"Test deferral {i}",
            defer_until=time_service.now() + timedelta(hours=1)
        )
        await wise_authority.send_deferral(deferral)

    # Check metrics
    status = wise_authority.get_status()
    assert status.metrics["pending_deferrals"] == 3.0
    assert status.metrics["total_deferrals"] == 3.0

    # Resolve one deferral
    pending = await wise_authority.get_pending_deferrals()
    response = DeferralResponse(
        approved=True,
        reason="Test approval",
        wa_id="wa-test",
        signature="test-sig"
    )
    await wise_authority.resolve_deferral(pending[0].deferral_id, response)

    # Check updated metrics
    status = wise_authority.get_status()
    assert status.metrics["pending_deferrals"] == 2.0
    assert status.metrics["resolved_deferrals"] == 1.0
```

## Configuration

### Database Path
- Default: Uses `get_sqlite_db_full_path()` from config
- Override: Pass `db_path` parameter to constructor
- **Critical**: Database must have `tasks` table with proper schema

### Dependencies
- **TimeService**: For consistent timestamps (optional)
- **AuthenticationService**: For WA certificate management
- **GraphAuditService**: For audit trail (dependency only)
- **SecretsService**: For cryptographic operations (dependency only)

### Health Checks
- Service started: `_started == True`
- Dependencies available: `_check_dependencies() == True`
- Database accessible: Implicit in metrics collection

## Known Limitations

1. **No Request-Level Tracking**: Individual authorization checks, guidance requests not counted
2. **No Performance Metrics**: Response times, throughput not tracked
3. **Limited Historical Data**: Only current counts, no time-series metrics
4. **No Graph Integration**: Metrics not stored in memory graph unlike other services
5. **Database Dependency**: All metrics require database queries - no caching
6. **No Segmentation**: Metrics not broken down by WA role, action type, or channel

## Future Enhancements

1. **Enhanced Metrics Collection**
   - Request-level tracking with `_track_request()` calls
   - Response time measurements for each operation
   - Authorization success/failure rates by action type
   - Guidance request patterns and provider usage

2. **Historical Telemetry**
   - Time-series data for deferral creation/resolution rates
   - Trend analysis for WA activity levels
   - Performance regression detection

3. **Graph Integration**
   - Store key metrics in memory graph for analytics
   - Cross-service correlation with other governance metrics
   - Real-time dashboards and alerting

4. **Advanced Analytics**
   - Deferral resolution time distributions
   - WA workload balancing metrics
   - Pattern detection for recurring authorization failures
   - Capacity planning for human oversight needs

5. **Operational Intelligence**
   - Automated alerts for deferral queue buildup
   - WA availability and response time tracking
   - System bottleneck identification
   - Load-based guidance routing optimization

## Integration Points

- **WiseBus**: Provides guidance capabilities to other services
- **AuthenticationService**: Manages WA certificates and permissions
- **TimeService**: Ensures consistent timestamps across deferrals
- **Database**: Persistent storage for deferral state and resolution
- **API Layer**: Exposes telemetry via REST endpoints for monitoring
- **Other Services**: Authorization checks for sensitive operations

## Monitoring Recommendations

1. **Critical Alerts**
   - `pending_deferrals > 20`: High deferral queue requiring WA attention
   - `error_rate > 0.05`: High error rate indicating service issues
   - `healthy == 0.0`: Service down or unhealthy

2. **Operational Dashboards**
   - Real-time deferral queue size and age
   - WA response time and resolution patterns
   - Authorization success rates by action type
   - Service uptime and error trends

3. **Capacity Planning**
   - Track deferral creation vs resolution rates
   - Monitor WA workload distribution
   - Identify peak usage patterns for staffing
   - Forecast growth in governance overhead

4. **Security Monitoring**
   - Unusual authorization failure patterns
   - Unauthorized elevation attempts
   - Anomalous deferral patterns that might indicate system abuse
   - WA certificate usage and access patterns

## Performance Considerations

1. **Database Query Cost**: Every metrics collection requires 2 database queries
2. **No Caching**: Status queries hit database directly without caching layer
3. **Synchronous Operations**: Database operations block metrics collection
4. **JSON Parsing Overhead**: Context parsing for each deferral in `get_pending_deferrals()`
5. **Memory Usage**: Low - only in-memory counters, no telemetry buffering

## System Integration

The Wise Authority Service acts as the **ethical conscience** of CIRIS:
- **Governance Enforcement**: Blocks unauthorized actions until human review
- **Wisdom Aggregation**: Coordinates multiple wisdom providers through WiseBus
- **Audit Trail**: Maintains complete record of human oversight decisions
- **System Safety**: Provides final human oversight for high-risk operations

Its telemetry is critical for ensuring the human oversight system remains responsive and effective, preventing autonomous systems from operating without appropriate governance guardrails.
