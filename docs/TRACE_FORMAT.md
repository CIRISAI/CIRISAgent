# CIRIS Covenant Trace Format

This document describes the reasoning trace format used by CIRIS agents for integrity verification and ethical compliance monitoring.

## Overview

CIRIS captures complete reasoning traces for every decision, from initial observation through final action. Each trace is cryptographically signed with Ed25519 to ensure integrity and enable third-party verification.

**Privacy by Design**: Agent IDs are hashed, and trace detail levels allow granular control over what data is shared. At `generic` and `detailed` levels, no user content is included. At `full_traces` level, user content IS included when explicitly consented to for research purposes.

## Trace Structure

A complete trace contains:

```
CompleteTrace
├── trace_id          # Unique identifier
├── thought_id        # ID of the thought being processed
├── task_id           # Optional parent task ID
├── agent_id_hash     # SHA-256 hash of agent ID (first 16 chars)
├── started_at        # ISO timestamp
├── completed_at      # ISO timestamp
├── trace_level       # generic | detailed | full_traces
├── components[]      # Array of 7 trace components
├── signature         # Ed25519 signature (base64)
└── signature_key_id  # Key ID for signature verification
```

## Trace Components

Each trace contains 7 ordered components representing the reasoning pipeline:

### 1. THOUGHT_START (Observation)
What triggered processing.

| Field | Level | Description |
|-------|-------|-------------|
| round_number | generic | Processing round |
| thought_depth | generic | Depth in thought tree |
| task_priority | generic | Numeric priority |
| thought_type | detailed | Type classification |
| thought_content | full | Truncated to 500 chars |

### 2. SNAPSHOT_AND_CONTEXT (Context)
Environmental state when decision was made.

| Field | Level | Description |
|-------|-------|-------------|
| cognitive_state | generic | WORK, PLAY, SOLITUDE, etc. |
| active_services | detailed | List of running services |
| service_health | detailed | Health status map |
| system_snapshot | full | Complete snapshot object |

### 3. DMA_RESULTS (Rationale - Part 1)
Three parallel DMA evaluations.

| DMA | Key Metric | Description |
|-----|------------|-------------|
| CSDMA | plausibility_score | Common sense check (0-1) |
| DSDMA | domain_alignment | Domain expertise match (0-1) |
| PDMA | has_conflicts | Stakeholder conflict detection |

### 4. IDMA_RESULT (Rationale - Part 2)
Identity fragility check using Coherence Collapse Analysis.

| Field | Level | Description |
|-------|-------|-------------|
| k_eff | generic | Effective connectivity (0-2+) |
| correlation_risk | generic | Risk of identity drift |
| phase | generic | chaos / healthy / rigidity |
| fragility_flag | generic | Boolean warning flag |
| sources_identified | detailed | Contributing factors |

### 5. ASPDMA_RESULT (Rationale - Part 3)
Action selection decision.

| Field | Level | Description |
|-------|-------|-------------|
| selected_action | generic | SPEAK, PONDER, DEFER, etc. |
| selection_confidence | generic | Confidence score (0-1) |
| is_recursive | generic | Follow-up thought created |
| action_rationale | full | Reasoning text |

### 6. CONSCIENCE_RESULT (Conscience)
Ethical validation across four faculties.

| Faculty | Metrics | Description |
|---------|---------|-------------|
| Entropy | entropy_score, entropy_threshold | Information uncertainty check |
| Coherence | coherence_score, coherence_threshold | Logical consistency check |
| Optimization Veto | entropy_ratio, affected_values | Prevents value collapse |
| Epistemic Humility | certainty, uncertainties | Acknowledges limitations |

**Key Fields**:
- `conscience_passed` - Overall pass/fail
- `action_was_overridden` - Conscience changed the action
- `entropy_level` - From epistemic_data (0-1)
- `coherence_level` - From epistemic_data (0-1)

### 7. ACTION_RESULT (Action + Outcome)
Execution result and resource consumption.

| Field | Level | Description |
|-------|-------|-------------|
| execution_success | generic | Boolean success |
| execution_time_ms | generic | Duration |
| tokens_input | generic | LLM input tokens |
| tokens_output | generic | LLM output tokens |
| cost_cents | generic | Estimated cost |
| audit_entry_hash | generic | Linked audit entry |
| action_executed | detailed | Action type |
| models_used | detailed | LLM models list |

## Trace Detail Levels

### generic (Default)
Numeric scores only. Powers [ciris.ai/ciris-scoring](https://ciris.ai/ciris-scoring).

- No text strings or reasoning
- Minimal bandwidth (~1.7KB per trace)
- Suitable for production metrics

### detailed
Adds actionable identifiers and lists.

- Includes flags, stakeholders, service lists
- Good for debugging without full exposure
- Moderate bandwidth (~2.7KB per trace)

### full_traces
Complete reasoning for research corpus (Coherence Ratchet).

- Full prompts and reasoning text
- User message content (truncated to 500 chars)
- Action parameters including response text
- **Requires explicit user consent** - only enabled when user opts in
- Used for ethical AI research and model improvement

## Signature Verification

Each trace is signed with Ed25519 using a per-agent unified signing key.

### Signed Payload Structure

```json
{
  "components": [
    {
      "component_type": "observation",
      "data": { ... },
      "event_type": "THOUGHT_START",
      "timestamp": "2026-02-08T12:34:56Z"
    },
    ...
  ],
  "trace_level": "generic"
}
```

**Critical**: `trace_level` is included in the signed payload. Each detail level produces a unique signature, allowing independent verification at any level.

### Verification Process

1. Agent registers public key with CIRISLens at startup
2. Traces are signed before transmission
3. CIRISLens verifies signature using registered public key
4. Verification confirms trace integrity and authenticity

### Key Management

- Keys stored at `data/agent_signing.key`
- Same key used for audit trail and trace signing
- Key ID format: `agent-{hash12}`

## Example Trace (generic level)

Based on a real verified trace from production:

```json
{
  "trace_id": "trace-th_seed_08b4901c_3cacdfa6-739-20260130024435",
  "thought_id": "th_seed_08b4901c_3cacdfa6",
  "agent_id_hash": "e8821136df22",
  "started_at": "2026-02-08T12:34:56.123Z",
  "completed_at": "2026-02-08T12:34:58.456Z",
  "trace_level": "generic",
  "components": [
    {
      "component_type": "observation",
      "event_type": "THOUGHT_START",
      "timestamp": "2026-02-08T12:34:56.123Z",
      "data": {
        "round_number": 1,
        "thought_depth": 0,
        "task_priority": 5
      }
    },
    {
      "component_type": "rationale",
      "event_type": "DMA_RESULTS",
      "timestamp": "2026-02-08T12:34:57.234Z",
      "data": {
        "csdma": { "plausibility_score": 0.85 },
        "dsdma": { "domain_alignment": 0.80 },
        "pdma": { "has_conflicts": false },
        "idma": { "k_eff": 1.0, "phase": "healthy" }
      }
    },
    {
      "component_type": "conscience",
      "event_type": "CONSCIENCE_RESULT",
      "timestamp": "2026-02-08T12:34:57.890Z",
      "data": {
        "conscience_passed": true,
        "entropy_level": 0.12,
        "coherence_level": 0.95
      }
    },
    {
      "component_type": "action",
      "event_type": "ACTION_RESULT",
      "timestamp": "2026-02-08T12:34:58.456Z",
      "data": {
        "execution_success": true,
        "tokens_total": 1847,
        "cost_cents": 0.02
      }
    }
  ],
  "signature": "base64-ed25519-signature...",
  "signature_key_id": "agent-e8821136df22"
}
```

## Related Files

- Schema: `ciris_adapters/ciris_covenant_metrics/schemas/trace_format_v1_9_1.json`
- Service: `ciris_adapters/ciris_covenant_metrics/services.py`
- Signing: `ciris_engine/logic/audit/signing_protocol.py`

## See Also

- [OVERVIEW.md](OVERVIEW.md) - Architecture overview
- [COVENANT.md](../COVENANT.md) - Ethical framework
- [API_SPEC.md](API_SPEC.md) - API documentation
