# TSDB Consolidation with Absolute Reputability

**Version**: 1.0
**Date**: January 14, 2025
**Status**: APPROVED
**Classification**: ARCHITECTURAL DECISION RECORD

## Executive Summary

This FSD defines how CIRIS maintains absolute reputability in perpetuity through a sophisticated 3-level consolidation system that preserves complete audit trails while achieving efficient storage (<20MB/day) for resource-constrained deployments.

## Core Principle: Never Delete Audit Data

**Fundamental Rule**: The cryptographically-signed audit log in SQLite is NEVER deleted or modified. Consolidation only affects graph representations used for querying.

## Architecture Overview

### Dual-Layer Audit System

```
┌─────────────────────────────────────────────────────────────┐
│                     Layer 1: Immutable Audit Log            │
│  SQLite Database with Cryptographic Hash Chain & Signatures │
│                    NEVER DELETED OR MODIFIED                 │
└─────────────────────────────────────────────────────────────┘
                               │
                               │ Replicated to
                               ▼
┌─────────────────────────────────────────────────────────────┐
│                    Layer 2: Graph Memory                     │
│         Queryable Nodes Subject to Consolidation            │
│                  (For Performance & Analysis)                │
└─────────────────────────────────────────────────────────────┘
```

### Three-Level Consolidation Strategy

1. **Basic Consolidation** (6-hour periods)
   - Frequency: Every 6 hours aligned to clock (00:00, 06:00, 12:00, 18:00 UTC)
   - Retention: Raw graph nodes kept for 24 hours
   - Purpose: First-level aggregation for recent data

2. **Extensive Consolidation** (weekly)
   - Frequency: Every Monday at 00:00 UTC
   - Consolidates: Previous week's basic summaries (Mon-Sun) into daily summaries
   - Creates: 7 daily summaries (one per day) for each node type
   - Retention: Basic summaries kept for 7 days
   - Purpose: Daily trends while reducing storage (4 summaries → 1 per day)

3. **Profound Consolidation** (monthly)
   - Frequency: 1st of each month at 00:00 UTC
   - Process: Compress existing daily summaries in-place
   - Retention: Indefinite (configurable target MB/day)
   - Purpose: Long-term storage efficiency for future multimedia

## Cryptographic Integrity

### Hash Chain Structure

```sql
Entry N-1: {
    sequence_number: 1000,
    entry_hash: SHA256(entry_content),
    previous_hash: "abc123...",
    signature: RSA_SIGN(entry_hash + timestamp)
}
    ↓
Entry N: {
    sequence_number: 1001,
    entry_hash: SHA256(entry_content),
    previous_hash: SHA256(Entry N-1),
    signature: RSA_SIGN(entry_hash + timestamp)
}
```

### Signature Details

- **Algorithm**: RSA-PSS with SHA-256
- **Key Size**: 2048 bits
- **Key Rotation**: Every 90 days
- **Storage**: Separate `audit_signing_keys` table

## Data Flow

### 1. Audit Entry Creation

```python
Handler Action
    ↓
AuditRequest Created
    ↓
GraphAuditService.audit()
    ├── Generate entry_hash
    ├── Get previous_hash from chain
    ├── Create RSA signature
    ├── Store in SQLite (permanent)
    └── Store in Graph (queryable)
```

### 2. Basic Consolidation (6-hour)

```python
Every 6 hours:
    ├── Query graph nodes in period
    ├── Create summaries by type:
    │   ├── MetricsSummary (TSDB data)
    │   ├── AuditSummary (audit entries)
    │   ├── ConversationSummary (interactions)
    │   ├── TraceSummary (execution traces)
    │   └── TaskSummary (completed tasks)
    ├── Store summaries in graph
    ├── Create edges to source nodes
    └── Mark period as consolidated

Note: SQLite audit_log untouched
```

### 3. Extensive Consolidation (weekly)

```python
Every Monday at 00:00 UTC:
    ├── Query basic summaries from past week
    ├── Group summaries by day (4 per day)
    ├── For each day in the week:
    │   ├── Aggregate 4 basic summaries (00:00, 06:00, 12:00, 18:00)
    │   ├── Sum all metrics, tokens, costs, carbon
    │   ├── Combine action counts and errors
    │   ├── Create daily summary node (e.g., "tsdb_daily_20250707")
    │   └── Create edges to the 4 source summaries
    ├── Total: 7 daily summaries created
    └── Store with consolidation_level="extensive"

Note: Original audit entries still in SQLite
```

### 4. Profound Consolidation (monthly)

```python
1st of month at 00:00 UTC:
    ├── Query extensive (daily) summaries from past month
    ├── Compress existing summaries in-place:
    │   ├── Text: Remove redundancy, compress descriptions
    │   ├── Metrics: Keep only significant patterns
    │   ├── Future multimedia: Lossy compression for images/video
    │   ├── Future telemetry: Statistical aggregation only
    │   └── Target: <20MB/day for graph storage
    ├── Update existing summary nodes with compressed data
    ├── No new nodes created - only compression
    ├── Preserve all edges and relationships
    └── Delete basic summaries >30 days old

Note: Compression only affects graph nodes, never audit_log
Future: When multimedia support added, profound consolidation
      will handle video thumbnails, image compression, etc.
```

## Verification Capabilities

### Complete Chain Verification

```python
async def verify_complete_chain() -> VerificationReport:
    """Verify entire audit chain integrity."""
    # 1. Check sequence numbers are monotonic
    # 2. Verify each hash links to previous
    # 3. Validate all signatures
    # 4. Report any tampering with exact location
```

### Perpetual Verification Guarantee

Even 50 years later, you can:
1. Export the complete audit_log table
2. Verify the unbroken hash chain
3. Validate signatures with archived public keys
4. Prove no tampering occurred

## Storage Efficiency

### Before Consolidation
- Raw audit entries: ~2KB each
- 10,000 actions/day = 20MB/day
- Annual storage: 7.3GB

### After Profound Consolidation
- Monthly summary: ~600KB
- Daily equivalent: <20KB
- Annual storage: 7.3MB (graph) + 7.3GB (audit_log)

### Key Insight
The audit_log (Layer 1) grows linearly but is write-only and highly compressible. The graph (Layer 2) stays small through consolidation.

## Calendar Alignment

### Why Calendar-Bound?

1. **Human Comprehension**: "Week of 2025-01-06" vs "168-hour period starting..."
2. **Regulatory Alignment**: Most compliance requires calendar-based reporting
3. **Cross-Instance Coordination**: Multiple CIRIS instances consolidate simultaneously
4. **Predictable Maintenance**: Admins know exactly when consolidation occurs

### Implementation

```python
class CalendarBoundScheduler:
    def get_next_weekly_monday(self, now: datetime) -> datetime:
        """Next Monday at 00:00 UTC"""
        days_until_monday = (7 - now.weekday()) % 7
        if days_until_monday == 0 and now.hour > 0:
            days_until_monday = 7
        next_monday = now.date() + timedelta(days=days_until_monday)
        return datetime.combine(next_monday, time(0, 0), tzinfo=timezone.utc)

    def get_next_month_start(self, now: datetime) -> datetime:
        """First day of next month at 00:00 UTC"""
        if now.day == 1 and now.hour == 0:
            return now.replace(minute=0, second=0, microsecond=0)
        next_month = now.replace(day=1) + timedelta(days=32)
        return next_month.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
```

## Trust Building Features

### 1. Tamper Evidence
- Any modification breaks hash chain
- Binary search locates exact tamper point
- Signatures prove authenticity

### 2. Export Capabilities
```python
POST /v1/audit/export
{
    "format": "sqlite",  # or "jsonl", "csv"
    "start_date": "2025-01-01",
    "end_date": "2025-01-31",
    "include_signatures": true
}
```

### 3. Public Transparency
Per CIRIS Accord Section II:
> "Deployments with >100,000 monthly active users must publish redacted PDMA logs and audit trails within 180 days"

### 4. Verification API
```bash
# Verify specific entry
POST /v1/audit/verify/{entry_id}

# Verify date range
POST /v1/audit/verify/range
{
    "start_date": "2025-01-01",
    "end_date": "2025-01-31"
}
```

## Implementation Configuration

### Essential Config (GraphConfig)

```python
class GraphConfig(BaseModel):
    """Graph service configuration."""
    # Fixed intervals (non-configurable for consistency)
    # Basic: 6 hours (clock-aligned)
    # Extensive: Weekly (Monday 00:00 UTC)
    # Profound: Monthly (1st at 00:00 UTC)

    # Configurable parameters
    tsdb_raw_retention_hours: int = Field(
        24,
        description="How long to keep raw TSDB data before consolidation"
    )
    tsdb_profound_target_mb_per_day: float = Field(
        20.0,
        description="Target size in MB per day after profound consolidation"
    )
    consolidation_timezone: str = Field(
        "UTC",
        description="Timezone for consolidation scheduling"
    )
```

## Security Considerations

### 1. Key Management
- Private keys for signing stored securely
- Public keys archived with audit entries
- Key rotation every 90 days
- Revocation tracking

### 2. Access Control
- Read access: Based on user role
- Write access: System-only (no external modification)
- Export access: Requires ADMIN role
- Verification: Public (transparency)

### 3. Future Enhancements
- External timestamp anchoring (RFC 3161)
- Blockchain merkle root anchoring
- Hardware Security Module (HSM) integration
- Distributed backup to IPFS

## Compliance Mappings

### HIPAA
- ✅ Audit trail integrity
- ✅ Non-repudiation
- ✅ Time synchronization
- ✅ Export capabilities

### SOC 2
- ✅ Change tracking
- ✅ Access logging
- ✅ Data integrity
- ✅ Monitoring

### GDPR
- ✅ Processing records
- ✅ Consent tracking
- ✅ Data lineage
- ⚠️ Right to erasure (requires legal review)

## Operational Procedures

### Daily Operations
1. Monitor consolidation job success
2. Verify hash chain integrity (automated)
3. Check storage growth rates

### Monthly Procedures
1. Export audit log for backup
2. Verify profound consolidation size
3. Archive signing keys if rotated

### Annual Procedures
1. Full chain verification
2. Storage capacity planning
3. Key ceremony for new signing keys

## Conclusion

The CIRIS TSDB Consolidation system achieves the seemingly impossible: maintaining complete, cryptographically-verifiable audit trails in perpetuity while operating efficiently in resource-constrained environments. Through careful separation of immutable audit logs from queryable graph representations, calendar-aligned consolidation windows, and profound compression techniques, we ensure that trust can be verified decades into the future while serving communities with limited resources today.

This architecture embodies the CIRIS principle: sophisticated technology serving human needs with transparency, accountability, and respect for resource constraints.

---

*"In perpetuity" means forever. This design ensures that promise is kept.*
