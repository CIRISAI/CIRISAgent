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

| Component | Fields |
|-----------|--------|
| THOUGHT_START | round_number, thought_depth, task_priority, updated_info_available, requires_human_input |
| SNAPSHOT_AND_CONTEXT | cognitive_state |
| DMA_RESULTS (CSDMA) | plausibility_score |
| DMA_RESULTS (DSDMA) | domain_alignment |
| DMA_RESULTS (PDMA) | has_conflicts |
| DMA_RESULTS (IDMA) | k_eff, correlation_risk, fragility_flag, phase |
| ASPDMA_RESULT | selected_action, selection_confidence, is_recursive |
| CONSCIENCE_RESULT | conscience_passed, action_was_overridden, ethical_faculties_skipped, updated_status_detected, thought_depth_triggered/current/max, entropy_level, coherence_level, entropy_passed/score/threshold, coherence_passed/score/threshold, optimization_veto_passed/entropy_ratio, epistemic_humility_passed/certainty |
| ACTION_RESULT | execution_success, execution_time_ms, tokens_input/output/total, cost_cents, carbon_grams, energy_mwh, llm_calls, audit_sequence_number, audit_entry_hash, has_positive_moment, has_execution_error |

**NO text strings, NO reasoning, NO prompts** at this level.

**detailed** - Adds actionable identifiers (everything in generic, plus):

| Component | Additional Fields |
|-----------|-------------------|
| THOUGHT_START | thought_type, thought_status, parent_thought_id, channel_id, source_adapter |
| SNAPSHOT_AND_CONTEXT | active_services, context_sources, service_health, agent_version, circuit_breaker_status |
| DMA_RESULTS (CSDMA) | flags |
| DMA_RESULTS (DSDMA) | domain, flags |
| DMA_RESULTS (PDMA) | stakeholders, conflicts, alignment_check |
| DMA_RESULTS (IDMA) | sources_identified, correlation_factors |
| ASPDMA_RESULT | alternatives_considered, evaluation_time_ms |
| CONSCIENCE_RESULT | final_action, conscience_override_reason, entropy_reason, coherence_reason, optimization_veto_decision/affected_values, epistemic_humility_uncertainties/recommendation |
| ACTION_RESULT | action_executed, follow_up_thought_id, audit_entry_id, models_used, api_bases_used, execution_error, audit_signature |

**full_traces** - Complete data for Coherence Ratchet corpus (everything in detailed, plus):

| Component | Additional Fields |
|-----------|-------------------|
| THOUGHT_START | task_description, initial_context, thought_content (truncated to 500 chars) |
| SNAPSHOT_AND_CONTEXT | system_snapshot, gathered_context, relevant_memories, conversation_history |
| DMA_RESULTS (all) | reasoning, prompt_used, combined_analysis |
| ASPDMA_RESULT | action_rationale, reasoning_summary, action_parameters, aspdma_prompt, raw_llm_response |
| CONSCIENCE_RESULT | epistemic_data, updated_status_content, optimization_veto_justification, epistemic_humility_justification |
| ACTION_RESULT | action_parameters, positive_moment |

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

Each trace captures the 6-component reasoning pipeline. Fields vary by trace level:

**Generic Level** (default) - numeric scores only:
```json
{
  "trace_id": "trace-th_seed_abc123-20260115220652",
  "thought_id": "th_seed_abc123",
  "task_id": "task-456",
  "agent_id_hash": "sha256_hash...",
  "started_at": "2026-01-15T22:06:52.658Z",
  "completed_at": "2026-01-15T22:06:53.917Z",
  "components": [
    {
      "component_type": "observation",
      "event_type": "THOUGHT_START",
      "data": {"round_number": 0, "thought_depth": 0, "task_priority": 0}
    },
    {
      "component_type": "context",
      "event_type": "SNAPSHOT_AND_CONTEXT",
      "data": {"cognitive_state": null}
    },
    {
      "component_type": "rationale",
      "event_type": "DMA_RESULTS",
      "data": {
        "csdma": {"plausibility_score": 0.9},
        "dsdma": {"domain_alignment": 0.9},
        "pdma": null,
        "idma": {"k_eff": 1.0, "correlation_risk": 0.0, "fragility_flag": true}
      }
    },
    {
      "component_type": "rationale",
      "event_type": "ASPDMA_RESULT",
      "data": {"selected_action": "SPEAK", "selection_confidence": null, "is_recursive": false}
    },
    {
      "component_type": "conscience",
      "event_type": "CONSCIENCE_RESULT",
      "data": {
        "conscience_passed": true,
        "entropy_passed": true, "entropy_score": 0.1, "entropy_threshold": 0.4,
        "coherence_passed": true, "coherence_score": 0.9, "coherence_threshold": 0.6,
        "optimization_veto_passed": true, "epistemic_humility_passed": true
      }
    },
    {
      "component_type": "action",
      "event_type": "ACTION_RESULT",
      "data": {
        "execution_success": true,
        "tokens_total": 205771, "cost_cents": 4.21,
        "audit_sequence_number": 33, "audit_entry_hash": "480f7afb..."
      }
    }
  ],
  "signature": "base64_ed25519_signature...",
  "signature_key_id": "wa-2025-06-14-ROOT00"
}
```

**Detailed Level** - adds identifiers and lists (IDMA example):
```json
"idma": {
  "k_eff": 2.0,
  "correlation_risk": 0.2,
  "fragility_flag": false,
  "phase": "healthy",
  "sources_identified": ["source1", "source2"],
  "correlation_factors": ["shared_training_data"]
}
```

**Full Traces Level** - adds reasoning text (IDMA example):
```json
"idma": {
  "k_eff": 2.0,
  "correlation_risk": 0.2,
  "fragility_flag": false,
  "phase": "healthy",
  "sources_identified": ["source1", "source2"],
  "correlation_factors": ["shared_training_data"],
  "reasoning": "Analysis identified 2 independent sources with low correlation...",
  "prompt_used": "Evaluate epistemic diversity of the following reasoning..."
}
```

**IDMA (Intuition DMA)** implements Coherence Collapse Analysis (CCA) to detect fragile reasoning:
- **k_eff formula**: `k_eff = k / (1 + ρ(k-1))` where k = sources, ρ = correlation
- **k_eff < 2**: FRAGILE - dangerous single-source dependence
- **k_eff >= 2**: HEALTHY - multiple truly independent perspectives
- **Nascent agents**: Expected to have low k_eff initially (~1.0)

### Egress Schema (enforced before signing)

Every component is checked against its trace level's schema in
`egress_schema.py` before it reaches the signer. A field the level doesn't
allow is dropped. So is a value of the wrong type, such as free text where a
number, enum token, bool or hash belongs. Over-long text and lists are capped.
Every violation is logged once as a WARNING (`[TRACE-SCHEMA]`, naming the event,
field path, level and kind, never the value) and counted in
`schema_violations_*` metrics. A violation is a bug in the code that produced the
field: fix it there, and don't rely on the filter.

| Level | Allowed |
|---|---|
| `generic` | Numbers, booleans and short enum-like tokens (no whitespace, at most 64 chars). One named exception: `attestation_context`, agent-authored and required at every level by FSD-001, capped at 1024 chars. No LLM text, no user text, no URLs, no channel ids. Inside `verb_specific_data`, only enum, boolean and tool-name members. |
| `detailed` | Everything in `generic`, plus key identifiers (channel id, thought/audit ids, key ids, model ids, provider base URL without userinfo or query) and actionable lists (at most 32 items, each one line of at most 128 chars). Also allows short reason summaries (defer reason, conscience reasons, execution error), capped at 500 chars. The reasoning chain itself (pass rationales, DMA reasoning) and tool parameters are not allowed. |
| `full_traces` | Everything, still bounded: free text at most 65,536 chars, opaque JSON at most 8 levels deep, 256 items, 8,192 chars per string. |

What this does **not** do: it can't recognise a person's name inside an
allowed reason summary at `detailed`. That residue is handled by the
substrate's scrubber and by the run-kind marker below, not by this filter.

### Mock LLM and Synthetic Runs

- **Mock LLM** (`CIRIS_MOCK_LLM`, `--mock-llm`, or the mock_llm module or
  service loaded): traces never leave the node. There is no ship grant, no
  federation transport and no delivery controller. Only the local tee
  (`CIRIS_ACCORD_METRICS_LOCAL_COPY_DIR`) and loopback endpoints may receive
  them. Consent and config can't lift this (CIRISAgent#1244).
- **Run kind**: `deployment_type` carries `mock` (always, under the mock LLM),
  or `qa` / `battery` when the harness sets `CIRIS_TRACE_RUN_KIND`, even
  with a real model (CIRISAgent#1245). Production runs keep the operator's
  value, or the default `production`.

### Privacy Controls

1. **Anonymization**: Agent IDs are SHA-256 hashed
2. **Level-gated egress**: the schema above, enforced before signing; at `generic`, free text never ships
3. **Consent Required**: Nothing leaves the node without explicit consent (and never under the mock LLM)
4. **Revocable**: Disable the adapter to stop collection immediately

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
- `CIRIS_ACCORD_METRICS_ENDPOINT`: CIRISLens API URL (default: `https://lens.ciris-services-1.ai/lens-api/api/v1`)
- `CIRIS_ACCORD_METRICS_CONSENT`: Set to `true` to enable (for QA testing)
- `CIRIS_ACCORD_METRICS_TRACE_LEVEL`: One of `generic`, `detailed`, `full_traces` (default: `generic`)

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
  "batch_timestamp": "2026-01-15T14:00:00Z",
  "consent_timestamp": "2025-12-15T13:00:00Z",
  "trace_level": "generic",
  "correlation_metadata": {
    "deployment_region": "na",
    "deployment_type": "business",
    "agent_role": "customer_support",
    "agent_template": "discord-moderator"
  }
}
```

### Batch Payload Fields

| Field | Type | Description |
|-------|------|-------------|
| `events` | array | Array of trace/event objects |
| `batch_timestamp` | string | ISO timestamp when batch was sent |
| `consent_timestamp` | string | ISO timestamp when user gave consent |
| `trace_level` | string | Detail level: `generic`, `detailed`, or `full_traces` |
| `correlation_metadata` | object | Optional early warning correlation data (see below) |

### Early Warning Correlation Metadata

These optional fields help power the CIRIS Early Warning System by enabling correlation analysis across the network. All fields are anonymous and optional.

| Field | Values | Description |
|-------|--------|-------------|
| `deployment_region` | `na`, `eu`, `uk`, `apac`, `latam`, `mena`, `africa`, `oceania` | Geographic region for timezone/regulatory correlation |
| `deployment_type` | `personal`, `business`, `research`, `nonprofit` | Deployment context for risk pattern analysis |
| `agent_role` | `assistant`, `customer_support`, `content`, `coding`, `research`, `education`, `moderation`, `automation`, `other` | Primary agent function for role-specific risk detection |
| `agent_template` | string | CIRIS template name if using a standard template (e.g., `discord-moderator`) |

Only non-empty fields are included in the payload. If no correlation metadata is configured, the `correlation_metadata` object is omitted entirely.

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
