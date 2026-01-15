# CIRIS Covenant Metrics Adapter

This adapter provides covenant compliance metrics collection for CIRISLens, reporting WBD (Wisdom-Based Deferral) events and PDMA decision events as specified in the CIRIS Covenant Section II.

## Trace Detail Levels

The adapter supports three privacy levels for trace capture:

| Level | Default | Description | Use Case |
|-------|---------|-------------|----------|
| `generic` | ✅ | Numeric scores only | Powers [ciris.ai/ciris-scoring](https://ciris.ai/ciris-scoring) |
| `detailed` | | Adds lists & identifiers | Debugging without reasoning exposure |
| `full_traces` | | Complete reasoning text | Research corpus contribution |

### What Each Level Captures

**generic** (default) - Minimum data for CIRIS Capacity Score:
- All numeric scores (plausibility_score, domain_alignment, k_eff, correlation_risk, etc.)
- Boolean flags (conscience_passed, fragility_flag, etc.)
- Execution metrics (tokens, cost, timing)
- Audit chain hashes (for integrity verification)
- **NO text strings, NO reasoning, NO prompts**

**detailed** - Adds actionable identifiers:
- Everything in `generic`, plus:
- `sources_identified`, `correlation_factors` (IDMA)
- `stakeholders`, `conflicts` (PDMA)
- `flags` arrays (CSDMA, DSDMA)
- Action types and follow-up IDs

**full_traces** - Complete data for Coherence Ratchet corpus:
- Everything in `detailed`, plus:
- Full reasoning text from all DMAs
- Prompts used for each decision
- Complete context and conversation history
- Error messages and raw parameters

## Privacy-First Design

**CRITICAL**: This adapter requires **EXPLICIT opt-in** via the setup wizard. No data is collected or sent without your consent.

### What Data is Collected

When you consent, the following data is sent to CIRISLens:

#### WBD (Wisdom-Based Deferral) Events
Per CIRIS Covenant Section II, Chapter 3:
```json
{
  "event_type": "wbd_deferral",
  "timestamp": "2025-12-15T14:00:00Z",
  "agent_id": "abc123def456...",  // Anonymized hash
  "thought_id": "thought-123",
  "task_id": "task-456",
  "reason": "Ethical uncertainty...",  // Truncated to 200 chars
  "defer_until": "2025-12-15T15:00:00Z",
  "priority": "medium"
}
```

#### PDMA Decision Events
Per CIRIS Covenant Section II, Chapter 2:
```json
{
  "event_type": "pdma_decision",
  "timestamp": "2025-12-15T14:00:00Z",
  "agent_id": "abc123def456...",  // Anonymized hash
  "thought_id": "thought-123",
  "selected_action": "SPEAK",
  "rationale": "User requested...",  // Truncated to 200 chars
  "reasoning_summary": "..."  // Truncated to 500 chars
}
```

#### Complete Reasoning Traces (H3ERE Pipeline)
Full 6-component traces capturing the complete reasoning pipeline:
```json
{
  "trace_id": "trace-thought-123-20260112162156",
  "thought_id": "thought-123",
  "task_id": "task-456",
  "agent_id_hash": "abc123def456...",
  "components": [
    {"component_type": "observation", "event_type": "THOUGHT_START", ...},
    {"component_type": "context", "event_type": "SNAPSHOT_AND_CONTEXT", ...},
    {"component_type": "dma_results", "data": {
      "pdma": {...},      // Ethical PDMA evaluation
      "csdma": {...},     // Common Sense DMA evaluation
      "dsdma": {...},     // Domain-Specific DMA evaluation
      "idma": {           // Intuition DMA (CCA epistemic diversity)
        "k_eff": 2.0,     // Effective independent sources (>= 2 = healthy)
        "correlation_risk": 0.2,
        "phase": "healthy",
        "fragility_flag": false,
        "sources_identified": ["source1", "source2"],
        "reasoning": "..."
      }
    }},
    {"component_type": "action", "event_type": "ASPDMA_RESULT", ...},
    {"component_type": "conscience", "event_type": "CONSCIENCE_RESULT", ...},
    {"component_type": "outcome", "event_type": "ACTION_RESULT", ...}
  ]
}
```

**IDMA (Intuition DMA)** implements Coherence Collapse Analysis (CCA) to detect fragile reasoning:
- **k_eff formula**: `k_eff = k / (1 + ρ(k-1))` where k = sources, ρ = correlation
- **k_eff < 2**: FRAGILE - dangerous single-source dependence
- **k_eff >= 2**: HEALTHY - multiple truly independent perspectives
- **Nascent agents**: Expected to have low k_eff initially (~1.0)

### What is NOT Collected

- User messages or conversation content
- Personal identifiable information (PII)
- Chat history
- Tool call details or parameters
- External API responses
- File contents

### Privacy Controls

1. **Anonymization**: Agent IDs are SHA-256 hashed
2. **Truncation**: All text fields are truncated to prevent sensitive data leakage
3. **No PII**: Only structural metadata is collected
4. **Consent Required**: Nothing is sent without explicit consent
5. **Revocable**: Disable the adapter to stop collection immediately

## Usage

### 1. Load the Adapter

```bash
python main.py --adapter api --adapter ciris_covenant_metrics
```

### 2. Complete Setup Wizard

The adapter requires completing the setup wizard which includes:

1. **Data Disclosure**: Review exactly what data will be collected
2. **Explicit Consent**: Check the consent box (required)
3. **Endpoint Config**: Configure CIRISLens URL (optional, has default)
4. **Confirmation**: Review and enable

### 3. Verify Status

Check adapter status via the API:
```bash
curl http://localhost:8000/v1/system/adapters/ciris_covenant_metrics
```

## Configuration

Environment variables:
- `CIRIS_COVENANT_METRICS_ENDPOINT`: CIRISLens API URL (default: `https://lens.ciris.ai/v1`)
- `CIRIS_COVENANT_METRICS_CONSENT`: Set to `true` to enable (for QA testing)
- `CIRIS_COVENANT_METRICS_TRACE_LEVEL`: One of `generic`, `detailed`, `full_traces` (default: `generic`)

Wizard/config file settings:
- `consent_given`: Boolean - must be true to collect data
- `consent_timestamp`: ISO timestamp when consent was given
- `trace_level`: One of `generic`, `detailed`, `full_traces` (default: `generic`)
- `batch_size`: Number of events to batch (1-100, default: 10)
- `flush_interval_seconds`: Seconds between batch sends (10-300, default: 60)

## How It Works

### WBD Event Collection

1. Adapter registers as a `WISE_AUTHORITY` service with `send_deferral` capability
2. When any component calls `WiseBus.send_deferral()`, it broadcasts to ALL services with this capability
3. The CovenantMetricsService receives the deferral and queues it for transmission
4. Events are batched and sent to CIRISLens API

### Event Batching

- Events are queued in memory
- Sent when batch reaches `batch_size` OR `flush_interval_seconds` elapsed
- Failed batches are re-queued up to 10x batch size
- All events are flushed on adapter stop

## Revoking Consent

To stop data collection:

1. **Via Setup Wizard**: Re-run wizard and uncheck consent
2. **Disable Adapter**: Remove from command line arguments
3. **Immediate**: Data collection stops immediately when consent is revoked

## CIRISLens API

Events are sent to:
```
POST {endpoint}/covenant/events
```

Request body:
```json
{
  "events": [...],
  "batch_timestamp": "2025-12-15T14:00:00Z",
  "consent_timestamp": "2025-12-15T13:00:00Z"
}
```

## Covenant References

- **Section II, Chapter 2**: Principled Decision-Making Algorithm (PDMA)
- **Section II, Chapter 3**: Wisdom-Based Deferral (WBD)
- **Section II, Chapter 5**: Intuition DMA and Coherence Collapse Analysis (CCA)

**Research Papers:**
- CIRIS Architecture: [DOI 10.5281/zenodo.18137161](https://doi.org/10.5281/zenodo.18137161)
- Coherence Ratchet Theory: [DOI 10.5281/zenodo.18142668](https://doi.org/10.5281/zenodo.18142668)

For more information about the CIRIS Covenant, see: https://ciris.ai/ciris_covenant.pdf

## Support

- Privacy Policy: https://ciris.ai/privacy
- Issues: https://github.com/CIRISAI/CIRISAgent/issues
