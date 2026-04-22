# Audit Trail System

Every action in CIRIS is permanently recorded in a cryptographically-secured audit trail. This isn't just logging - it's a tamper-proof record that enables accountability, debugging, and compliance. The system uses hash chains and digital signatures to ensure that once something is recorded, it cannot be altered or deleted without detection.

## Why This Matters

**For Healthcare**: Complete audit trail for patient interactions, medication decisions, and treatment recommendations - essential for compliance and safety reviews.

**For Education**: Track all student interactions, content decisions, and assessment actions for transparency and improvement.

**For Communities**: Understand moderation decisions, track patterns, and ensure fair treatment of all members.

## Architecture Overview

```
User Action → Handler → Audit Service → Cryptographic Chain → Permanent Storage
                                          ↓
                                    Digital Signature
                                          ↓
                                    Verification System
```

### Core Components

- **Hash Chain**: Links each audit entry to the previous one cryptographically
- **Digital Signatures**: Proves who performed each action and when
- **Verification System**: Detects any tampering or missing entries

## How It Works

### 1. Every Action Creates an Audit Entry

When CIRIS makes a decision or takes an action:

```python
# User asks a question
user_message = "Should I increase my medication dose?"

# CIRIS evaluates and decides to defer to human
audit_entry = {
    "event_id": "evt-2025-06-15-001",
    "event_type": "DEFER",
    "originator_id": "ciris-agent-01",
    "event_payload": {
        "reason": "Medical dosage changes require physician approval",
        "question": "Should I increase my medication dose?",
        "risk_level": "high"
    }
}
```

### 2. Hash Chain Links Entries Together

Each entry is cryptographically linked to the previous one:

```
Entry 1: {action: "OBSERVE", hash: "abc123...", prev: "genesis"}
    ↓
Entry 2: {action: "PONDER", hash: "def456...", prev: "abc123..."}
    ↓
Entry 3: {action: "DEFER", hash: "ghi789...", prev: "def456..."}
    ↓
Entry 4: {action: "SPEAK", hash: "jkl012...", prev: "ghi789..."}
```

If anyone tries to change Entry 2, the hash won't match Entry 3's "prev" field, revealing the tampering.

### 3. Digital Signatures Prove Authenticity

Each entry is digitally signed:
- **Who**: Which agent or service created this entry
- **When**: Cryptographically-proven timestamp
- **What**: Exact content that was signed
- **Integrity**: Mathematical proof it hasn't been altered

## What Gets Audited

### Every Decision
- **OBSERVE**: Information gathering actions
- **SPEAK**: Messages sent to users
- **TOOL**: External tool usage (search, calculations)
- **PONDER**: Internal reasoning steps
- **DEFER**: Escalations to human oversight
- **MEMORIZE**: Knowledge storage actions
- **RECALL**: Information retrieval
- **FORGET**: Data removal (with reason)
- **TASK_COMPLETE**: Goal achievement

### Additional Events
- **Guardrail Activations**: When safety mechanisms trigger
- **Permission Checks**: Access control decisions
- **Resource Usage**: Token consumption, costs
- **Errors**: Failures and recovery attempts
- **Configuration Changes**: System modifications

## Real-World Examples

### Medical Decision Audit
```json
{
    "event_id": "evt-2025-06-15-14:32:15",
    "event_type": "DEFER",
    "originator_id": "ciris-medical-01",
    "event_payload": {
        "context": "Patient asking about changing diabetes medication",
        "reason": "Medication changes require physician approval",
        "risk_assessment": "HIGH - potential for adverse effects",
        "alternative_provided": "Suggested discussing with doctor at next visit"
    },
    "entity_id": "patient-discussion-789",
    "correlation_id": "session-456"
}
```

### Educational Interaction Audit
```json
{
    "event_id": "evt-2025-06-15-09:15:42",
    "event_type": "SPEAK",
    "originator_id": "ciris-edu-01",
    "event_payload": {
        "student_grade": "5th",
        "subject": "mathematics",
        "action": "Provided hint for fraction problem",
        "pedagogical_approach": "Socratic questioning",
        "content_filter": "age_appropriate_check_passed"
    },
    "entity_id": "student-session-234",
    "correlation_id": "math-lesson-15"
}
```

### Community Moderation Audit
```json
{
    "event_id": "evt-2025-06-15-22:45:33",
    "event_type": "TOOL",
    "originator_id": "ciris-discord-01",
    "event_payload": {
        "tool": "timeout_user",
        "reason": "Repeated violations of community guideline #3",
        "duration": "10 minutes",
        "warnings_given": 2,
        "automatic_action": false,
        "human_review_requested": true
    },
    "entity_id": "discord-user-567",
    "correlation_id": "moderation-case-89"
}
```

## Verification: Ensuring Integrity

### How to Verify Your Audit Trail

```bash
# Check audit integrity
curl http://localhost:8080/v1/audit/verify

# Response
{
    "valid": true,
    "entries_verified": 15234,
    "chain_intact": true,
    "signatures_valid": true,
    "verification_time_ms": 127,
    "last_entry": "2025-06-15T23:59:59Z"
}
```

### What Verification Checks

1. **Hash Chain Integrity**
   - Each entry links correctly to the previous one
   - No entries have been deleted or reordered
   - Content matches the stored hashes

2. **Digital Signatures**
   - Signatures are mathematically valid
   - Signed by authorized agents/services
   - Timestamps are consistent

3. **Completeness**
   - No gaps in sequence numbers
   - All required fields present
   - Correlation IDs link related events

### If Tampering is Detected

```json
{
    "valid": false,
    "errors": [
        {
            "type": "hash_mismatch",
            "entry_id": "evt-2025-06-15-12:34:56",
            "sequence": 5678,
            "expected_hash": "abc123...",
            "actual_hash": "def456...",
            "recommendation": "Investigate entry modification"
        }
    ],
    "first_invalid_entry": 5678,
    "total_affected_entries": 4567
}
```

## Using the Audit Trail

### For Debugging

```bash
# Find all deferrals in the last hour
curl "http://localhost:8080/v1/audit/search?type=DEFER&since=1h"

# Trace a specific user interaction
curl "http://localhost:8080/v1/audit/trace/session-456"

# Get audit statistics
curl http://localhost:8080/v1/audit/stats
```

### For Compliance

```python
# Generate compliance report
from datetime import datetime, timedelta

# Get all medical decisions from last month
start_date = datetime.now() - timedelta(days=30)
audit_entries = await audit_service.query(
    event_types=["DEFER", "TOOL"],
    start_date=start_date,
    filter_payload={"risk_level": "high"}
)

# Export for review
await audit_service.export_for_compliance(
    entries=audit_entries,
    format="pdf",
    include_signatures=True
)
```

### For Learning and Improvement

```python
# Analyze decision patterns
patterns = await audit_service.analyze_patterns(
    event_type="DEFER",
    group_by="reason",
    time_period="7d"
)

# Results show what triggers human escalation
{
    "medical_decisions": 45,
    "privacy_concerns": 23,
    "ethical_dilemmas": 12,
    "uncertain_context": 34
}

# Use insights to improve DMAs and decision-making
```

## Performance and Storage

### Typical Metrics
- **Entry Creation**: ~25ms (including signing)
- **Verification**: ~5ms per entry
- **Storage**: ~2KB per entry
- **Query Performance**: <100ms for most searches

### Storage Estimates
- **Low Activity** (100 actions/day): ~60MB/year
- **Medium Activity** (1,000 actions/day): ~600MB/year
- **High Activity** (10,000 actions/day): ~6GB/year

### Retention Policies

```python
# Configure retention
audit_config = {
    "retention_days": 365,        # Keep for 1 year
    "archive_after_days": 90,     # Move to cold storage
    "compliance_retention": 2555, # 7 years for medical
    "auto_verify_interval": 3600  # Verify every hour
}
```

## Security Properties

### What the Audit Trail Guarantees

1. **Immutability**: Once written, entries cannot be changed
2. **Completeness**: No entries can be deleted without detection
3. **Authenticity**: Every entry is cryptographically signed
4. **Ordering**: Temporal sequence is preserved and verifiable
5. **Non-repudiation**: Actions cannot be denied after the fact

### What It Doesn't Guarantee

1. **Prevention**: Audit trails record actions, they don't prevent them
2. **Privacy**: Audit entries may contain sensitive information
3. **Interpretation**: Context and intent require human analysis

## Technical Implementation Details

### Cryptographic Specifications
- **Hash Algorithm**: SHA-256 for chain integrity
- **Signature Algorithm**: RSA-PSS with 2048-bit keys
- **Key Rotation**: Automatic every 90 days
- **Storage**: SQLite with encryption at rest

### API Endpoints

```
GET  /v1/audit/entries        # Query audit entries
GET  /v1/audit/verify         # Verify integrity
GET  /v1/audit/stats          # Get statistics
GET  /v1/audit/trace/{id}     # Trace correlations
POST /v1/audit/export         # Export for compliance
GET  /v1/audit/search         # Advanced search
```

## Best Practices

### For Developers
1. **Always include context** in audit payloads
2. **Use correlation IDs** to link related actions
3. **Don't log secrets** or sensitive data directly
4. **Test audit scenarios** in your integration tests

### For Operators
1. **Regular verification** - Set up automated checks
2. **Backup audit data** - Critical for compliance
3. **Monitor growth** - Plan for storage scaling
4. **Access control** - Limit who can read audit data

### For Compliance Officers
1. **Understand the guarantees** - What can and cannot be proven
2. **Regular exports** - Don't wait for audits to check
3. **Verify integrity** - Run verification before reports
4. **Document procedures** - How to use audit data

## Summary

The CIRIS audit trail provides:
- **Complete accountability** for all agent actions
- **Cryptographic proof** of integrity
- **Practical tools** for debugging and compliance
- **Reasonable performance** even at high volume
- **Future-proof design** for long-term operation

This isn't just about compliance - it's about building trust through transparency. Every decision can be traced, verified, and understood.

---

*For implementation details and API reference, see the code documentation. For compliance procedures, see your organization's audit guide.*
