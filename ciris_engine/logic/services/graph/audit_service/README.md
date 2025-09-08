# Audit Service

**Mission-Critical**: Immutable audit trail with cryptographic signatures ensuring complete transparency and accountability for all CIRIS operations.

## Mission Alignment

**Serves Meta-Goal M-1** through:
- **Transparency**: Every decision and action is permanently recorded and explainable
- **Accountability**: Complete traceability enables ethical oversight and learning
- **Trust Building**: Cryptographic integrity ensures audit data cannot be tampered with
- **Institutional Memory**: Failure analysis and pattern recognition for continuous improvement
- **Compliance**: Regulatory audit trails for healthcare, education, and governance applications

## Overview

The Audit Service provides comprehensive logging and verification of all system operations through an immutable, cryptographically-secured audit trail. It combines three critical capabilities:

1. **Graph-Based Storage** - All audit data stored as graph memories for relationship analysis
2. **Cryptographic Integrity** - Ed25519 signatures and hash chain for tamper evidence  
3. **Compliance Export** - File-based exports for regulatory requirements

## Core Capabilities

### Audit Logging
- **Action Logging** - Every handler action with context and outcome
- **Event Logging** - General system events with structured metadata
- **Conscience Logging** - Ethical decision processes and reasoning chains
- **Error Logging** - Failures, exceptions, and recovery actions

### Cryptographic Security
- **Hash Chain** - Tamper-evident chain linking all audit entries
- **Digital Signatures** - Ed25519 signatures on all entries
- **Integrity Verification** - Automated detection of tampering or corruption
- **Key Management** - Secure key storage and rotation

### Query and Analysis
- **Trail Retrieval** - Time-based and entity-filtered audit queries
- **Pattern Analysis** - Integration with graph memory for relationship discovery
- **Compliance Reporting** - Structured exports for regulatory requirements
- **Real-time Monitoring** - Live audit event streaming

## Architecture Integration

### Graph Memory Integration
```python
# Audit entries stored as typed graph nodes
audit_entry = AuditEntry(
    id=f"audit_{uuid4()}",
    timestamp=time_service.now(),
    action_type=HandlerActionType.SPEAK,
    context=audit_context,
    outcome="success",
    hash_pointer=previous_entry_hash
)

# Stored with relationships to entities and actions
await memory_bus.memorize(
    concept="audit_entry",
    content=audit_entry,
    associations=[
        Association(target_concept=entity_id, relationship="AUDITS"),
        Association(target_concept=action_id, relationship="RECORDS")
    ]
)
```

### Service Dependencies
- **TimeService** - Consistent timestamps across audit entries
- **MemoryBus** - Graph storage for audit data and relationships
- **Optional: FileSystem** - Compliance exports and hash chain database

### Message Bus Usage
**Direct Injection** - Single authoritative audit service for system integrity

## Key Operations

### Core Audit Methods

#### `log_action(action_type, context, outcome)`
Records handler actions with full context:
```python
await audit_service.log_action(
    action_type=HandlerActionType.MEMORIZE,
    context=AuditActionContext(
        entity_id="user_123",
        request_id="req_456", 
        metadata={"concept": "patient_data", "scope": "LOCAL"}
    ),
    outcome="success"
)
```

#### `log_event(event_type, event_data)`
General system event logging:
```python
await audit_service.log_event(
    event_type="wise_authority_deferral",
    event_data={
        "decision": "treatment_recommendation",
        "deferred_to": "dr_smith",
        "reasoning": "medical expertise required",
        "urgency": "high"
    }
)
```

#### `log_conscience_event(thought_id, decision, reasoning)`
Ethical decision process logging:
```python
await audit_service.log_conscience_event(
    thought_id="ethical_123",
    decision="decline_unsafe_request", 
    reasoning="Request violates patient safety protocols",
    metadata={"confidence": 0.95, "consulted_authorities": ["medical_ethics"]}
)
```

### Verification and Integrity

#### `verify_audit_integrity()`
Comprehensive integrity verification:
```python
report = await audit_service.verify_audit_integrity()
# Returns: VerificationReport with:
# - verified: bool
# - total_entries: int  
# - chain_intact: bool
# - invalid_entries: List[str]
```

#### `get_audit_trail(entity_id, hours, action_types)`
Filtered audit trail retrieval:
```python
trail = await audit_service.get_audit_trail(
    entity_id="patient_456",
    hours=24,
    action_types=["MEMORIZE", "RECALL", "WISE_AUTHORITY_DEFERRAL"]
)
```

## Data Schemas

### AuditEventData
```python
class AuditEventData(BaseModel):
    entity_id: str = "system"
    actor: str = "system" 
    outcome: str = "success"
    severity: str = "info"
    action: Optional[str] = None
    resource: Optional[str] = None
    reason: Optional[str] = None
    metadata: Dict[str, Union[str, int, float, bool]] = {}
```

### VerificationReport  
```python
class VerificationReport(BaseModel):
    verified: bool
    total_entries: int
    valid_entries: int
    invalid_entries: int
    chain_intact: bool
    verification_started: datetime
    verification_completed: datetime
```

## Security Features

### Cryptographic Guarantees
- **Ed25519 Signatures** - Each audit entry cryptographically signed
- **Hash Chain Integrity** - Tamper-evident chain linking all entries
- **Key Rotation** - Secure key management with rotation capability
- **Immutability** - Once written, audit entries cannot be modified

### Threat Mitigation
- **Data Tampering** - Cryptographic signatures detect any modifications
- **Chain Breaks** - Hash chain verification catches missing/altered entries  
- **Unauthorized Access** - Signature verification prevents forged entries
- **Compliance Violations** - Complete audit trail for regulatory review

## Production Characteristics

### Performance
- **Low Latency** - <5ms per audit entry in normal operation
- **High Throughput** - Handles 1000+ audit entries per second
- **Memory Efficient** - Configurable cache size for recent entries
- **Storage Optimized** - Graph compression for long-term retention

### Reliability  
- **99.99% Availability** - Critical path for all system operations
- **Automatic Recovery** - Handles temporary storage failures gracefully
- **Retention Management** - Configurable retention periods with auto-cleanup
- **Export Backup** - Multiple format exports for disaster recovery

### Monitoring
- **Integrity Alerts** - Automatic alerts on hash chain breaks
- **Performance Metrics** - Latency and throughput monitoring
- **Storage Monitoring** - Disk usage and retention policy compliance
- **Verification Reports** - Scheduled integrity verification

## Development Guidelines

### Audit Best Practices
1. **Log Everything** - Every significant system operation must be audited
2. **Structured Data** - Use typed schemas, never raw dictionaries
3. **Context Rich** - Include sufficient context for forensic analysis
4. **Timely Logging** - Audit entries created immediately after actions
5. **Error Handling** - Audit failures must not break primary operations

### Testing Requirements
- **Integrity Testing** - Verify hash chain and signature validation
- **Performance Testing** - Ensure audit logging doesn't impact system performance
- **Tampering Simulation** - Test detection of various tampering scenarios
- **Export Validation** - Verify compliance export formats and completeness

---

*The Audit Service is foundational to CIRIS's trustworthiness. Every interaction, decision, and system change is permanently recorded with cryptographic integrity, enabling the transparency and accountability essential for ethical AI deployment in critical domains.*

## Related Documentation
- [Graph Memory System](../../../README.md#graph-memory-as-identity) 
- [Service Architecture](../../README.md#graph-services)
- [Cryptographic Standards](../../../../protocols/services/graph/audit.py)