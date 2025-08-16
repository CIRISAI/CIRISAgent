# Audit Service Telemetry

## Overview
The Audit Service is a comprehensive audit and compliance system that provides cryptographic integrity, tamper-evident logging, and dual storage (graph + optional file export). It implements the "everything is a memory" architecture by storing all audit entries as graph nodes while maintaining optional hash chain verification and file exports for compliance.

## Telemetry Data Collected

| Metric Name | Type | Storage | Update Frequency | Access Method |
|------------|------|---------|------------------|---------------|
| cached_entries | gauge | in-memory counter | per audit entry | `_collect_custom_metrics()` |
| pending_exports | gauge | in-memory buffer | per export batch | `_collect_custom_metrics()` |
| hash_chain_enabled | boolean | configuration | on initialization | `_collect_custom_metrics()` |
| cache_size_mb | gauge | calculated | on metrics collection | `_collect_custom_metrics()` |
| uptime_seconds | gauge | inherited | real-time | BaseService |
| request_count | counter | inherited | per operation | BaseService |
| error_count | counter | inherited | per error | BaseService |
| error_rate | ratio | inherited | calculated | BaseService |
| healthy | boolean | inherited | real-time | BaseService |
| memory_bus_available | boolean | inherited | real-time | BaseGraphService |
| audit_entries_stored | counter | graph memory | per log_event/log_action | graph query |
| hash_chain_entries | counter | sqlite database | per entry (if enabled) | database query |
| export_batches | counter | file system | per export flush | file metrics |
| verification_reports | counter | graph memory | per verification | graph query |
| integrity_checks | counter | graph memory | per verification | graph query |

## Data Structures

### AuditRequest (Runtime)
```python
{
    "entry_id": "uuid-12345",
    "timestamp": "2025-08-14T13:30:00Z",
    "entity_id": "thought_123",
    "event_type": "conscience_check",
    "actor": "conscience_system",
    "details": {
        "action_type": "DEFER",
        "thought_id": "thought_123",
        "task_id": "task_456",
        "handler_name": "conscience_handler",
        "metadata": "{}"
    },
    "outcome": "allowed"
}
```

### AuditEntryNode (Graph Storage)
```python
{
    "id": "audit_conscience_check_uuid-12345",
    "type": "AUDIT_ENTRY",
    "scope": "local",
    "action": "conscience_check",
    "actor": "conscience_system",
    "timestamp": "2025-08-14T13:30:00Z",
    "context": {
        "service_name": "GraphAuditService",
        "correlation_id": "uuid-12345",
        "additional_data": {
            "thought_id": "thought_123",
            "task_id": "task_456",
            "outcome": "allowed",
            "severity": "info"
        }
    },
    "signature": null,
    "hash_chain": null,
    "attributes": {
        "action_type": "conscience_check",
        "event_id": "uuid-12345"
    }
}
```

### Hash Chain Entry (SQLite)
```python
{
    "entry_id": 123,
    "event_id": "uuid-12345",
    "event_timestamp": "2025-08-14T13:30:00Z",
    "event_type": "conscience_check",
    "originator_id": "thought_123",
    "event_summary": "conscience_check by conscience_system",
    "event_payload": "{\"action_type\": \"DEFER\", ...}",
    "sequence_number": 123,
    "previous_hash": "abc123...",
    "entry_hash": "def456...",
    "signature": "ghi789...",
    "signing_key_id": "key_001"
}
```

### VerificationReport
```python
{
    "verified": true,
    "total_entries": 1234,
    "valid_entries": 1234,
    "invalid_entries": 0,
    "chain_intact": true,
    "last_valid_entry": "uuid-12345",
    "first_invalid_entry": null,
    "verification_started": "2025-08-14T13:30:00Z",
    "verification_completed": "2025-08-14T13:30:15Z",
    "duration_ms": 15000,
    "errors": [],
    "warnings": []
}
```

### Export Buffer
```python
[
    {
        "entry_id": "uuid-12345",
        "timestamp": "2025-08-14T13:30:00Z",
        "entity_id": "thought_123",
        "event_type": "conscience_check",
        "actor": "conscience_system",
        "details": {...},
        "outcome": "allowed"
    }
]
```

## API Access Patterns

### Current Access
- **Graph Storage**: All audit entries stored as AUDIT_ENTRY nodes via memory bus
- **Hash Chain**: Optional cryptographic integrity via SQLite database
- **File Export**: Optional export to JSONL, CSV, or SQLite files
- **Cache Access**: Recent entries cached in-memory for quick access

### Recommended Endpoints

#### Get Audit Trail
```
GET /v1/audit/trail?entity_id={id}&hours=24&action_types=conscience_check,DEFER
```
Returns:
```json
{
    "entries": [
        {
            "id": "audit_conscience_check_uuid-12345",
            "action": "conscience_check",
            "actor": "conscience_system",
            "timestamp": "2025-08-14T13:30:00Z",
            "context": {
                "correlation_id": "uuid-12345",
                "service_name": "GraphAuditService"
            }
        }
    ],
    "total": 1,
    "cached": 0,
    "from_graph": 1
}
```

#### Query Audit Events
```
POST /v1/audit/query
```
Body:
```json
{
    "start_time": "2025-08-14T00:00:00Z",
    "end_time": "2025-08-14T23:59:59Z",
    "actor": "conscience_system",
    "event_type": "conscience_check",
    "limit": 100,
    "offset": 0
}
```

#### Verify Audit Integrity
```
POST /v1/audit/verify
```
Returns:
```json
{
    "verified": true,
    "total_entries": 1234,
    "valid_entries": 1234,
    "chain_intact": true,
    "duration_ms": 15000,
    "errors": []
}
```

#### Export Audit Data
```
POST /v1/audit/export
```
Body:
```json
{
    "start_time": "2025-08-14T00:00:00Z",
    "end_time": "2025-08-14T23:59:59Z",
    "format": "jsonl"
}
```

#### Get Service Metrics
```
GET /v1/audit/metrics
```
Returns:
```json
{
    "cached_entries": 45,
    "pending_exports": 12,
    "hash_chain_enabled": true,
    "cache_size_mb": 2.3,
    "uptime_seconds": 86400,
    "request_count": 5678,
    "error_count": 2,
    "memory_bus_available": true
}
```

## Graph Storage

### Node Types Created
- `AUDIT_ENTRY` - All audit events and actions
- `VERIFICATION_REPORT` - Integrity verification results
- `AUDIT_EVENT` - General event logging

### Edge Relationships
- `AUDITED_BY` - Links entities to their audit entries
- `VERIFIED_BY` - Links audit entries to verification reports
- `TRIGGERED_BY` - Links audit events to their triggers
- `EXPORTED_TO` - Links audit entries to export batches

### Memory Types by Category
```python
class AuditMemoryType(Enum):
    OPERATIONAL = "operational"  # Service operations, startup/shutdown
    BEHAVIORAL = "behavioral"    # Handler actions, decisions
    SOCIAL = "social"           # Interactions, communications
    IDENTITY = "identity"       # Authentication, authorization
    WISDOM = "wisdom"          # Conscience checks, ethical decisions
```

### Graph Storage Strategy
- **Primary Storage**: All audit entries stored as graph nodes via MemoryBus
- **Hash Chain**: Optional cryptographic verification stored in SQLite
- **Export Files**: Compliance exports in JSONL/CSV/SQLite formats
- **Cache Layer**: In-memory recent entries for performance

## Example Usage

### Log an Action
```python
audit_service = get_service(ServiceType.AUDIT)
context = AuditActionContext(
    thought_id="thought_123",
    handler_name="conscience_handler"
)

await audit_service.log_action(
    HandlerActionType.DEFER,
    context,
    outcome="deferred_to_wisdom_authority"
)
```

### Log a General Event
```python
from ciris_engine.schemas.services.graph.audit import AuditEventData

event_data = AuditEventData(
    entity_id="user_session_456",
    actor="authentication_system",
    outcome="success",
    severity="info",
    action="user_login",
    resource="authentication",
    reason="valid_credentials",
    metadata={"ip_address": "192.168.1.1"}
)

await audit_service.log_event("user_login", event_data)
```

### Query Audit Trail
```python
from ciris_engine.schemas.services.graph.audit import AuditQuery

query = AuditQuery(
    start_time=datetime.now() - timedelta(hours=24),
    actor="conscience_system",
    event_type="conscience_check",
    limit=100
)

entries = await audit_service.query_audit_trail(query)
for entry in entries:
    print(f"Action: {entry.action} by {entry.actor} at {entry.timestamp}")
```

### Verify Audit Integrity
```python
verification_report = await audit_service.verify_audit_integrity()

print(f"Verified: {verification_report.verified}")
print(f"Total entries: {verification_report.total_entries}")
print(f"Chain intact: {verification_report.chain_intact}")

if verification_report.errors:
    print(f"Errors found: {verification_report.errors}")
```

### Export Audit Data
```python
export_path = await audit_service.export_audit_data(
    start_time=datetime.now() - timedelta(days=7),
    format="jsonl"
)
print(f"Audit data exported to: {export_path}")
```

## Testing

### Test Files
- `tests/logic/services/graph/test_audit_service.py` - Service unit tests
- `tests/integration/test_audit_flow.py` - End-to-end audit flows
- `tests/security/test_audit_integrity.py` - Hash chain and signature tests

### Validation Steps
1. Log audit entry via `log_event()` or `log_action()`
2. Verify entry appears in graph as AUDIT_ENTRY node
3. Check entry in `_recent_entries` cache
4. Verify hash chain entry if enabled
5. Query entry via `query_audit_trail()`
6. Verify integrity via `verify_audit_integrity()`
7. Export and verify file format

```python
async def test_comprehensive_audit_flow():
    audit_service = get_service(ServiceType.AUDIT)

    # Log an event
    event_data = AuditEventData(
        entity_id="test_entity",
        actor="test_actor",
        action="test_action",
        outcome="success"
    )

    await audit_service.log_event("test_event", event_data)

    # Query the event
    query = AuditQuery(
        start_time=datetime.now() - timedelta(minutes=1),
        limit=10
    )
    entries = await audit_service.query_audit_trail(query)

    assert len(entries) >= 1
    assert entries[0].action == "test_event"

    # Verify integrity
    report = await audit_service.verify_audit_integrity()
    assert report.verified or not audit_service.enable_hash_chain

    # Check metrics
    status = audit_service.get_status()
    assert status.metrics["cached_entries"] >= 1
```

## Configuration

### Service Configuration
```python
{
    "export_path": "/var/log/ciris/audit.jsonl",
    "export_format": "jsonl",  # jsonl, csv, sqlite
    "enable_hash_chain": true,
    "db_path": "ciris_audit.db",
    "key_path": "audit_keys",
    "retention_days": 90,
    "cache_size": 1000
}
```

### Hash Chain Configuration
```python
{
    "enable_hash_chain": true,
    "algorithm": "rsa-pss",
    "key_size": 2048,
    "auto_rotate_keys": false,
    "signature_required": true
}
```

### Export Configuration
```python
{
    "export_enabled": true,
    "export_interval_seconds": 60,
    "max_buffer_size": 1000,
    "compress_exports": false,
    "retention_policy": "90d"
}
```

## Known Limitations

1. **Cache Size Limited**: Only configurable number of recent entries cached (default 1000)
2. **Export Lag**: Exports happen every 60 seconds, not real-time
3. **Hash Chain Overhead**: Cryptographic operations add latency when enabled
4. **No Auto-Pruning**: Old audit entries never automatically deleted
5. **Single Database**: Hash chain uses single SQLite file, no distribution
6. **Memory Growth**: In-memory cache can grow large with high audit volume
7. **Export Atomicity**: Export failures can lose buffered entries

## Future Enhancements

1. **Distributed Hash Chain**: Multi-node cryptographic integrity
2. **Real-time Exports**: Stream audit events to external systems
3. **Auto-Retention**: Configurable audit data lifecycle management
4. **Advanced Analytics**: ML-based audit pattern analysis
5. **Compliance Templates**: Pre-built export formats (SOX, GDPR, etc.)
6. **Performance Optimization**: Batch operations and async processing
7. **Audit Dashboards**: Real-time audit monitoring and alerting
8. **Cross-Service Correlation**: Link audit events across service boundaries

## Integration Points

- **MemoryBus**: Primary storage for all audit entries as graph nodes
- **TimeService**: Consistent timestamps across all audit events
- **All Services**: Send audit events here via log_action/log_event
- **Hash Chain**: Optional cryptographic integrity verification
- **File System**: Optional compliance exports in multiple formats
- **ServiceRegistry**: Service discovery and health monitoring

## Monitoring Recommendations

1. **Audit Volume**: Monitor entries per second to detect unusual activity
2. **Cache Hit Rate**: Track cache effectiveness for performance tuning
3. **Hash Chain Health**: Monitor signature verification success rate
4. **Export Success**: Ensure compliance exports complete successfully
5. **Storage Growth**: Watch graph node count and disk usage
6. **Integrity Verification**: Regular automated integrity checks
7. **Error Patterns**: Monitor for recurring audit failures
8. **Performance Impact**: Track audit overhead on system performance

## Performance Considerations

1. **Graph Write Load**: Every audit event creates a graph node
2. **Hash Chain Latency**: Cryptographic operations add processing time
3. **Cache Memory**: Large audit volumes can consume significant RAM
4. **Export I/O**: File exports can impact disk performance
5. **Query Complexity**: Graph queries for audit trails can be expensive
6. **Verification Cost**: Full chain verification is computationally intensive
7. **Concurrent Access**: Multiple services logging simultaneously

## Architecture Notes

The Audit Service embodies several key CIRIS principles:

**Everything is a Memory**: All audit entries are stored as graph memories, enabling rich relationships and queries while maintaining the unified memory model.

**Type Safety**: Complete elimination of `Dict[str, Any]` through comprehensive Pydantic models for all audit data structures.

**Ethical Accountability**: Cryptographic hash chains and digital signatures ensure audit integrity, supporting the ethical obligation of transparent accountability.

**Grace-Based Resilience**: Even audit failures are logged and become learning opportunities rather than being discarded.

**Covenant Compliance**: The dual storage approach (graph + optional files) supports both operational needs and regulatory compliance requirements.

The service demonstrates how technical infrastructure can embody ethical principles, providing the transparency and accountability foundations that enable trustworthy autonomous systems.
