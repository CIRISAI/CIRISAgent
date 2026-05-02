# CIRIS Trace Wire Format Specification

**For:** lens engineers building the persistence + query layer
**Pinned to:** agent version 2.7.8, schema version `2.7.0`
**Companion:** `FSD/TRACE_EVENT_LOG_PERSISTENCE.md` (persistence model)
**Status:** definitive — generated from the schema modules referenced inline

This document specifies the over-the-wire format the CIRIS agent emits to
the lens. It is the contract. The agent module
`ciris_adapters/ciris_accord_metrics/services.py` is the implementation;
`ciris_engine/schemas/services/runtime_control.py` defines every event
class. Both are authoritative — this document mirrors them.

## 1. Wire transport

**Endpoint:** `POST <CIRIS_ACCORD_METRICS_ENDPOINT>/accord/events`

The endpoint URL is configurable per agent
(`CIRIS_ACCORD_METRICS_ENDPOINT` env var); production default is
`https://lens.ciris-services-1.ai/lens-api/api/v1`.

**Headers:** `Content-Type: application/json`. No auth header today —
the lens trusts the network boundary plus the per-event Ed25519
signature (see §8). Add bearer auth when the lens introduces
agent identity.

**Request body** (every batch):

```json
{
  "events": [ /* array of event envelopes — see §2 */ ],
  "batch_timestamp": "2026-04-30T15:00:00.000000+00:00",
  "consent_timestamp": "2025-01-01T00:00:00Z",
  "trace_level": "generic" | "detailed" | "full_traces",
  "trace_schema_version": "2.7.0",
  "correlation_metadata": {
    "deployment_region": "us-east",
    "deployment_type": "production",
    "agent_role": "datum",
    "agent_template": "datum",
    "user_location": "Schaumburg, IL, USA",
    "user_timezone": "America/Chicago",
    "user_latitude": "42.0334",
    "user_longitude": "-88.0834"
  }
}
```

- `consent_timestamp` is **required**; the lens MUST return HTTP 422 if
  missing or empty.
- `trace_level` MUST be one of the three string values. It is also
  baked into each event's signature input (see §8) — changing levels
  mid-stream invalidates older signatures.
- `correlation_metadata` is optional and only appears for fields the
  agent has explicit user consent to share.
- `batch_timestamp` is the agent's local clock at flush time; not
  authoritative for ordering. Use per-event `timestamp` for ordering.

**Batching cadence:** events flush either when the queue reaches
`batch_size` (default 10) or every `flush_interval_seconds` (default
60). Both are agent-side env-tunable.

**Response:** `200 {"status": "ok"}` on success. Any non-200 causes the
agent to requeue the batch up to `10 × batch_size` events deep before
dropping. The lens MUST NOT return 200 for partial acceptance; partial
batches must fail-the-whole or succeed-the-whole.

## 2. Event envelope inside `events[]`

Two top-level event shapes flow through the same `events[]` array:

| `event_type` | Carries | Section |
|---|---|---|
| `complete_trace` | A full sealed CompleteTrace + signature | §3 |
| (any value of `ReasoningEvent`) | A single per-step or per-LLM-call event | §5 |

In production today the agent only ships `complete_trace` envelopes —
the per-event types in §5 are the *components inside* a CompleteTrace.
The `events[]` list is a forward-compat seam if the agent ever ships
loose events (e.g. for live streaming bypassing trace assembly).

Lens implementations should switch on `event_type` for every entry.

## 3. CompleteTrace envelope

Wrapped as `{"event_type": "complete_trace", "trace": <CompleteTrace>, "trace_level": "..."}`.

The `<CompleteTrace>` shape (`ciris_adapters/ciris_accord_metrics/services.py:128-180`):

```json
{
  "trace_id": "trace-th_std_518a7abb-...-20260430001553",
  "thought_id": "th_std_518a7abb-6b1f-447b-a030-7af8f5d8cd37",
  "task_id": "ACCEPT_INCOMPLETENESS_1d10d1b5-...",
  "agent_id_hash": "7c3f8e2b1d9a4f60",
  "started_at": "2026-04-30T00:15:53.123456+00:00",
  "completed_at": "2026-04-30T00:16:12.789012+00:00",
  "trace_level": "generic",
  "trace_schema_version": "2.7.0",
  "components": [ /* TraceComponent[] — see §4 */ ],
  "signature": "base64(ed25519-signature-bytes)",
  "signature_key_id": "ciris-agent-key:abcd1234..."
}
```

| Field | Type | Required | Notes |
|---|---|---|---|
| `trace_id` | string | yes | Format `trace-<thought_id>-<YYYYMMDDHHMMSS>`. Globally unique per agent. |
| `thought_id` | string | yes | Anchors all `TraceComponent` rows back to one CIRIS thought. |
| `task_id` | string \| null | optional | Not all internal thoughts (system probes) have parent tasks. |
| `agent_id_hash` | string | yes | First 16 hex characters (8 bytes) of `sha256(public_key_bytes)`, lowercase. **Canonical derivation**: `hashlib.sha256(public_key_bytes).hexdigest()[:16]` over the agent's Ed25519 signing key bytes. Same value `ciris-persist v0.2.2+` uses for AV-9 dedup gating; same value PoB §3.2 uses for Reticulum addressing. One definition serves identity, transport, and dedup — implementations MUST use exactly this derivation so the values are interchangeable across consumers. Pseudonymous: invertible only by an attacker who already holds the public key. |
| `started_at` | ISO-8601 | yes | When the first component event arrived at the adapter. |
| `completed_at` | ISO-8601 | yes (post-seal) | When `ACTION_RESULT` fired. **A trace is only sealed and shipped when ACTION_RESULT fires** — no action means it never happened (see §10). |
| `trace_level` | enum | yes | `generic`, `detailed`, or `full_traces`. Same value as the batch envelope. |
| `trace_schema_version` | string | yes | Currently `"2.7.0"`. Version-gate consumers on this. |
| `components` | array | yes | Ordered components — see §4. |
| `signature` | base64 | yes | Ed25519 signature over the canonical payload (§8). |
| `signature_key_id` | string | yes | Key identifier for verification lookup. |

**Component ordering:** `components[]` is in receipt order at the
adapter. Receipt order matches broadcast order from
`reasoning_event_stream` because each subscriber's queue preserves
FIFO. Use the per-component `timestamp` for tie-breaking at sub-millisecond
granularity (component_type is also a coarse ordering hint — components
go through the H3ERE step sequence: observation → context → rationale →
conscience → action).

### 3.1 `agent_id_hash` is per-event, not per-batch

Although `agent_id_hash` appears once per CompleteTrace at this envelope
level, **it binds every TraceComponent under the trace structurally**: the
persistence dedup tuple (§9.1) is `(agent_id_hash, trace_id, thought_id,
event_type, attempt_index, ts)`, evaluated per persisted row. Compliant
persistence layers MUST propagate the parent CompleteTrace's
`agent_id_hash` into every component-row UNIQUE check, OR equivalently
treat `(agent_id_hash, trace_id)` as the trace-binding pair before any
per-component dedup. Without this gating, a malicious agent can pre-claim
a `(trace_id, thought_id, event_type, attempt_index, ts)` tuple it
doesn't own — see AV-9 in `CIRISPersist/THREAT_MODEL.md §3.1`.

The `trace_id` namespace ("globally unique per agent by convention") is
**adversary-controllable at the SQL layer**. The dedup tuple's
`agent_id_hash` prefix prevents cross-agent collision; the `ts` suffix is
defense-in-depth against attempt_index counting bugs (§6).

## 4. TraceComponent envelope

Each entry in `components[]`:

```json
{
  "component_type": "rationale",
  "event_type": "ASPDMA_RESULT",
  "timestamp": "2026-04-30T00:16:01.234567+00:00",
  "data": { /* event-type-specific fields — see §5 */ }
}
```

| Field | Type | Notes |
|---|---|---|
| `component_type` | enum | One of `observation`, `context`, `rationale`, `conscience`, `action`, `verb_second_pass`, `llm_call`, `unknown`. |
| `event_type` | enum | The `ReasoningEvent` value — discriminator for `data` shape. |
| `timestamp` | ISO-8601 | Per-component wall clock. |
| `data` | object | Event-specific payload, content gated by trace level. |

The `component_type → event_type` mapping is fixed in
`ciris_adapters/ciris_accord_metrics/services.py:399-422`:

| `event_type` | `component_type` |
|---|---|
| `THOUGHT_START` | `observation` |
| `SNAPSHOT_AND_CONTEXT` | `context` |
| `DMA_RESULTS` | `rationale` |
| `IDMA_RESULT` | `rationale` |
| `ASPDMA_RESULT` | `rationale` |
| `TSASPDMA_RESULT` *(deprecated)* | `rationale` |
| `VERB_SECOND_PASS_RESULT` *(2.7.8+)* | `verb_second_pass` |
| `CONSCIENCE_RESULT` | `conscience` |
| `ACTION_RESULT` | `action` |
| `LLM_CALL` *(2.7.8+)* | `llm_call` |

Empty fields are stripped before signing and shipping (the
`_strip_empty` helper in `services.py:99-114` removes `None`, empty
strings, empty lists, empty dicts recursively from `data`). The lens
must treat absent fields as "not emitted at this trace level," not
"emitted as null."

**`event_type` vs `step_point` naming.** This spec and `ciris-persist
v0.1.2+` use `event_type` as the canonical discriminator; the alias
`step_point` appears in some early lens design notes
(`INCOMING_2_7_8.md §7.1`) but is non-canonical. Persistence layers MAY
accept `step_point` as a deserialization alias for migration but MUST
write `event_type` on output. The dedup tuple in §9.1 binds
`event_type`, not `step_point`.

**`agent_id_hash` propagation.** The parent CompleteTrace's
`agent_id_hash` (§3) applies to every component under it (§3.1). A
component does NOT carry its own `agent_id_hash` field on the wire —
implementations propagate it from the parent envelope when persisting
into a per-component table.

## 5. Reasoning event types and `data` shapes

Each subsection lists the fields present in the component's `data` dict.
Required fields appear in every emission of that event; optional fields
are gated by trace level (see §7).

### 5.1 `THOUGHT_START`

Once per thought. Anchors metadata about what the agent is
processing. (`runtime_control.py:1086-1108`)

```json
{
  "thought_id": "th_std_...",
  "task_id": "task_...",
  "timestamp": "2026-04-30T00:15:53Z",
  "thought_type": "standard",
  "thought_content": "<the thought text>",
  "thought_status": "PROCESSING",
  "round_number": 0,
  "thought_depth": 0,
  "parent_thought_id": null,
  "task_description": "<task this thought serves>",
  "task_priority": 5,
  "channel_id": "api_user_abc",
  "updated_info_available": false
}
```

### 5.2 `SNAPSHOT_AND_CONTEXT`

Once per thought. The adapter flattens specific high-value scalars from
the SystemSnapshot to top-level fields and gates the full nested
snapshot behind `full_traces` only.
(`accord_metrics/services.py:1388-1506`)

**GENERIC** — agent identity, cognitive state, attestation booleans,
counts. No system_snapshot blob.

```json
{
  "thought_id": "...", "task_id": "...", "timestamp": "...",
  "agent_name": "Ally",
  "cognitive_state": "work",
  "attestation_context": "CIRIS VERIFY ATTESTATION: Level 3/5 | ✓Binary ✓Environment ✗...",
  "attestation_level": 3,
  "attestation_status": "partial",
  "disclosure_severity": "warning",
  "binary_ok": true, "env_ok": true, "registry_ok": false,
  "file_integrity_ok": false, "audit_ok": false, "play_integrity_ok": false,
  "hardware_backed": true,
  "memory_count": 0,
  "context_tokens": 1
}
```

**DETAILED** — adds:

```json
{
  "active_services": [...], "context_sources": [...], "service_health": {...},
  "agent_version": "2.7.8-stable",
  "circuit_breaker_status": {...},
  "key_status": "local", "key_id": "agent-...",
  "ed25519_fingerprint": "8a0b70302aae...",
  "key_storage_mode": "TPM", "hardware_type": "TpmFirmware",
  "verify_version": "1.6.3"
}
```

**FULL_TRACES** — adds:

```json
{
  "system_snapshot":  { /* full SystemSnapshot — see ciris_engine/schemas/runtime/system_context.py */ },
  "gathered_context": { /* context payload */ },
  "relevant_memories":   [...],
  "conversation_history": [...]
}
```

The flat fields are emitted directly because: (a) they're privacy-safe
(no content), (b) they're zero-correlation with the reasoning stack so
the lens k_eff analysis benefits from having them at GENERIC, and
(c) every scalar of `verify_attestation` is needed for hardware-integrity
scoring without pulling the whole SystemSnapshot. The lens MAY denormalize
the nested `system_snapshot` (FULL only) into per-field columns for
queryability — every flat field above is already that shape.

If `system_snapshot` is empty (e.g. follow-up thoughts that skip context
re-gathering), the entire field is stripped by `_strip_empty`. Treat its
absence as "no snapshot at this point in the thought," not as a missing
field.

#### 5.2.1 CIRISVerify attestation block

The `attestation_*`, `*_ok`, `key_*`, `ed25519_fingerprint`,
`hardware_*`, and `verify_version` fields above are projected from a
single source — the `VerifyAttestationContext` schema in
`ciris_engine/schemas/services/attestation.py:244`. CIRISVerify is the
agent-side cryptographic attestation framework that proves the binary,
environment, signing key, file integrity, and audit chain are intact.
Every traced thought carries a snapshot of this state so the lens can
correlate reasoning quality with hardware-integrity dimensions.

**`attestation_level` (0-5):** highest level the agent achieved at
attestation time. Higher = more independent integrity dimensions verified.
Each level requires all lower levels to pass:

| Level | Requires | Meaning |
|------:|----------|---------|
| 0 | (nothing) | CIRISVerify not loaded or disabled |
| 1 | `binary_ok` | Agent binary hash matches a published artifact |
| 2 | + `env_ok` | Runtime environment matches expected config |
| 3 | + `registry_ok` OR `hardware_backed` | Either: signing key registered with Portal, or: signing key hardware-backed (TPM/TEE) |
| 4 | + `file_integrity_ok` | All loadable files (prompts, configs, accord) verified against their hashes |
| 5 | + `audit_ok` AND `play_integrity_ok` (mobile) | Audit chain verified end-to-end; on mobile, Google Play Integrity passed |

**Per-check booleans (always at GENERIC):** each `*_ok` field is
**independently meaningful and near-zero-correlation with the reasoning
stack** — the lens should treat them as separate integrity dimensions
for k_eff analysis, not collapse them into the level scalar.

| Field | Type | Meaning |
|---|---|---|
| `binary_ok` | bool | CIRISVerify binary loaded and functional |
| `env_ok` | bool | Environment configured (CIRIS_HOME, paths, etc.) |
| `registry_ok` | bool | Signing key registered with Portal or root authority |
| `file_integrity_ok` | bool | Loadable file hashes verified (ACCORD, prompts, configs) |
| `audit_ok` | bool | Audit chain end-to-end intact |
| `play_integrity_ok` | bool | Google Play Integrity passed (Android only; false on desktop) |
| `hardware_backed` | bool | Signing key in hardware (TPM/TEE) rather than software |

**`attestation_status`** ∈ {`not_attempted`, `pending`, `verified`,
`failed`} — high-level status; `verified` requires all checks at the
claimed level to pass. `partial` (in `attestation_mode`, not
`attestation_status`) means some checks failed at higher levels but the
agent achieved a non-zero floor.

**`disclosure_severity`** ∈ {`info`, `warning`, `critical`} — drives UI
banner severity in CIRIS-aware clients. The lens should preserve this
field for downstream alerting; a switch from `info` to `warning` on a
running agent is a meaningful integrity signal even if the level didn't
change.

**`attestation_context`** — pre-rendered human-readable summary string,
same format used in agent LLM context, API responses, and traces. Not
authoritative; the booleans above are. The lens may show this string in
trace-detail dashboards for one-glance status.

**Key fields** (DETAILED+) — `key_status` ∈ {`none`, `ephemeral`,
`portal_pending`, `portal_active`, `local`}, `key_id` (Portal-issued ID
when activated), `ed25519_fingerprint` (SHA-256 of the public key),
`key_storage_mode` (e.g. `TPM`, `SOFTWARE`), `hardware_type` (e.g.
`TpmFirmware`, `TEE`, `SOFTWARE_ONLY`). These are identifying — gated
behind DETAILED rather than GENERIC for that reason.

**`verify_version`** — CIRISVerify library version string (e.g.
`"1.6.3"`). Lens should pin per-trace-row so a future version that
changes attestation semantics doesn't silently invalidate older
comparisons.

### 5.3 `DMA_RESULTS`

Once per thought. Carries the three perspective DMAs run in parallel:
ethical (PDMA), common-sense (CSDMA), domain-specific (DSDMA).
(`runtime_control.py:1129-1154`)

```json
{
  "thought_id": "...", "task_id": "...", "timestamp": "...",
  "csdma": { /* CSDMAResult: plausibility_score, flags, reasoning */ },
  "dsdma": { /* DSDMAResult: domain_alignment_score, flags, reasoning */ },
  "pdma": { /* EthicalDMAResult: action, rationale, weight_alignment_score, ethical_alignment_score */ },
  "csdma_prompt":  "<full prompt — FULL only>",
  "dsdma_prompt":  "<full prompt — FULL only>",
  "pdma_prompt":   "<full prompt — FULL only>",
  "csdma_system_prompt": "<format instructions — FULL only>",
  "dsdma_system_prompt": "...",
  "pdma_system_prompt":  "..."
}
```

**Bounce alternatives:** if any DMA scored below threshold, the
orchestrator runs `BOUNCE_PARALLELISM` alternatives — these are
collapsed today. Only the best alternative survives to this event.
Per-alternative observability is part of the FSD §5.2 trace_llm_calls
table; today it's only visible via the `LLM_CALL` events (§5.10).

### 5.4 `IDMA_RESULT`

Once per thought, after `DMA_RESULTS`. Identity-DMA fragility check —
measures epistemic diversity (k_eff), correlation risk, phase, defense
margins. Schema is rich; see `IDMAResult` in
`ciris_engine/schemas/dma/results.py:40`. Typical wire shape:

```json
{
  "thought_id": "...", "task_id": "...", "timestamp": "...",
  "k_eff": 3.0, "k_raw": 4, "raw_source_count": 4,
  "effective_source_count": 3.0,
  "correlation_risk": "low", "fragility_flag": false,
  "reasoning_is_fragile": false, "phase": "healthy",
  "phase_confidence": 0.92, "reasoning_state": "stable",
  "collapse_margin": 1.5, "safety_margin": 0.8,
  "reasoning": "<short epistemic-health analysis>",
  "sources_identified": ["training_data", "user_input", "system_prompt"],
  "source_independence_scores": [0.9, 0.85, 0.7],
  "rho_mean": 0.18, "rho_intra": 0.21, "rho_inter": 0.14,
  "delta_k_eff": 0.0, "phase_persistence_steps": 1,
  "idma_prompt": "<FULL only>"
}
```

### 5.5 `ASPDMA_RESULT`

**Fires multiple times per thought** if conscience overrides trigger
recursive retries. The first emission is from `PERFORM_ASPDMA`
(attempt_index 0); subsequent emissions are from `RECURSIVE_ASPDMA`
(attempt_index 1, 2, ...). (`runtime_control.py:1253-1270`)

```json
{
  "thought_id": "...", "task_id": "...", "timestamp": "...",
  "selected_action": "speak",
  "action_rationale": "<rationale text>",
  "is_recursive": false,
  "selection_confidence": 0.85,
  "alternatives_considered": ["ponder", "task_complete"],
  "aspdma_prompt": "<FULL only>",
  "attempt_index": 0
}
```

`is_recursive=true` indicates this came from RECURSIVE_ASPDMA after a
conscience override. `attempt_index` orders the retries (see §6).

### 5.6 `TSASPDMA_RESULT` *(deprecated, kept emitting)*

**DEPRECATED in 2.7.8** — replaced by `VERB_SECOND_PASS_RESULT` (§5.7).
Still emitted alongside the new event for the transition window
(FSD §10 phase 0). Lens should prefer the new event; remove handling
once the agent stops emitting (target: 2.8.0).

```json
{
  "thought_id": "...", "task_id": "...", "timestamp": "...",
  "original_tool_name": "curl",
  "original_parameters": {},
  "aspdma_reasoning": "<rationale from first-pass ASPDMA>",
  "final_action": "tool",
  "final_tool_name": "curl",
  "final_parameters": {"url": "https://example.com"},
  "tsaspdma_reasoning": "<TSASPDMA refinement>",
  "tool_description": "<from tool registry — DETAILED+>",
  "gotchas_acknowledged": ["url-validation"],
  "tsaspdma_prompt": "<FULL only>"
}
```

### 5.7 `VERB_SECOND_PASS_RESULT` *(new in 2.7.8)*

Fires once per thought, only when ASPDMA selected a verb that has a
registered second-pass evaluator. Currently TOOL → TSASPDMA, DEFER →
DSASPDMA; future verbs drop in to the registry without schema changes.
(`runtime_control.py:1303-1361`)

```json
{
  "thought_id": "...", "task_id": "...", "timestamp": "...",
  "verb": "tool",
  "original_action": "tool",
  "original_reasoning": "<reasoning from first-pass ASPDMA>",
  "final_action": "speak",
  "final_reasoning": "<TSASPDMA refinement reasoning>",
  "verb_specific_data": {
    "original_tool_name": "curl",
    "original_parameters": {},
    "final_tool_name": null,
    "final_parameters": {"content": "please clarify"}
  },
  "second_pass_prompt": "<FULL only>",
  "attempt_index": 0
}
```

| Field | Type | Notes |
|---|---|---|
| `verb` | string | **Discriminator field.** Lower-case `HandlerActionType.value`. **Canonical enum (2.7.9):** `"tool"`, `"defer"`. Future verbs adding a second-pass evaluator MUST extend this enum (lower-case `HandlerActionType.value`) before emitting; persistence-layer per-version payload gates rely on the discriminator being closed at any given schema version. The `verb_specific_data` shape is gated on this field — see §5.7.1. |
| `original_action` | string | First-pass selection. |
| `original_reasoning` | string | DETAILED+. |
| `final_action` | string | Refined selection (may equal `original_action`). |
| `final_reasoning` | string | DETAILED+. |
| `verb_specific_data` | object | **Opaque at the event level** — shape per `verb`. See §5.7.1. |
| `second_pass_prompt` | string \| null | FULL only. |
| `attempt_index` | int | §6. Always 0 today (no recursive verb-second-pass). |

#### 5.7.1 `verb_specific_data` shapes

Per-verb. The lens MAY denormalize these into verb-specific columns at
write time, but MUST treat the dict as authoritative.

**`verb: "tool"`** (from `_build_tool_verb_specific_data` in `main.py`):

```json
{
  "original_tool_name": "curl",
  "original_parameters": {},
  "final_tool_name": "curl" /* or null if switched to SPEAK/PONDER */,
  "final_parameters": {"url": "https://example.com"} /* or {} */
}
```

**`verb: "defer"`** (from `_build_defer_verb_specific_data` in `main.py`):

```json
{
  "rights_basis": ["fair_trial", "access_to_justice"],
  "primary_need_category": "justice_and_legal_agency",
  "secondary_need_categories": ["identity_and_civic_participation"],
  "domain_hint": "legal" /* or null */,
  "operational_reason": "licensed_domain_required" /* or null */,
  "defer_reason": "Licensed legal review required.",
  "defer_until": "2026-05-15T00:00:00Z" /* or null */
}
```

Enum values come from
`ciris_engine/schemas/services/deferral_taxonomy.py` and
`ciris_engine/schemas/services/agent_credits.py:DomainCategory`.

### 5.8 `CONSCIENCE_RESULT`

**Fires multiple times per thought.** Initial pass (attempt_index 0),
then once per recursive retry (1, 2, ...), then a finalization pass
emitted from `FINALIZE_ACTION`. (`runtime_control.py:1374-1450`)

```json
{
  "thought_id": "...", "task_id": "...", "timestamp": "...",
  "conscience_passed": true,
  "action_was_overridden": false,
  "ethical_faculties_skipped": false,
  "final_action": "speak",
  "is_recursive": false,
  "conscience_override_reason": null,
  "updated_status_detected": false,
  "thought_depth_triggered": false,
  "thought_depth_current": 0,
  "thought_depth_max": 5,

  "entropy_passed": true, "entropy_score": 0.18, "entropy_threshold": 0.40,
  "entropy_reason": "<reason — DETAILED+>",
  "coherence_passed": true, "coherence_score": 0.92, "coherence_threshold": 0.70,
  "coherence_reason": "<reason — DETAILED+>",

  "optimization_veto_passed": true,
  "optimization_veto_decision": "proceed",
  "optimization_veto_entropy_ratio": 0.05,
  "optimization_veto_justification": "<text — FULL only>",
  "optimization_veto_affected_values": [],

  "epistemic_humility_passed": true,
  "epistemic_humility_certainty": 0.88,
  "epistemic_humility_uncertainties": [],
  "epistemic_humility_justification": "<text — FULL only>",
  "epistemic_humility_recommendation": "proceed",

  "entropy_level": 0.18,
  "coherence_level": 0.92,
  "epistemic_data": { /* EpistemicData — FULL only */ },

  "attempt_index": 0
}
```

When conscience overrides occur:
- `conscience_passed = false`
- `action_was_overridden = true`
- `conscience_override_reason` populated (DETAILED+)
- The agent then runs `RECURSIVE_ASPDMA` and emits another
  `CONSCIENCE_RESULT` with `is_recursive=true` and `attempt_index=1`.

The lens MUST preserve every emission — the override journey is the
data the FSD `trace_events` table is designed for.

### 5.9 `ACTION_RESULT`

Once per thought. **This event seals the trace** — the adapter emits
`ACTION_RESULT` then signs and ships the CompleteTrace.
(`runtime_control.py:1452-1520`)

```json
{
  "thought_id": "...", "task_id": "...", "timestamp": "...",
  "action_executed": "speak",
  "action_parameters": {"content": "Hello, Sarah!"},
  "execution_success": true,
  "execution_time_ms": 36.0,
  "follow_up_thought_id": null,
  "error": null,

  "audit_entry_id": "audit-...",
  "audit_sequence_number": 42,
  "audit_entry_hash": "<sha256>",
  "audit_signature": "<base64-ed25519>",

  "tokens_total": 275745, "tokens_input": 250000, "tokens_output": 25745,
  "cost_cents": 0.276, "carbon_grams": 1.2, "energy_mwh": 0.5,
  "llm_calls": 13,
  "models_used": ["meta-llama/llama-4-scout-17b-16e-instruct"],
  "api_bases_used": ["https://api.groq.com/openai/v1"],

  "coherence_passed": true, "coherence_score": 0.95,
  "entropy_passed": true,   "entropy_score": 0.25
}
```

The audit chain fields anchor each action to a tamper-evident audit
log entry. The cost columns are the only place today where total
LLM-call accounting survives; the FSD `trace_llm_calls` table replaces
them as the source of truth.

### 5.10 `LLM_CALL` *(new in 2.7.8)*

**Sub-pipeline event — fires N times per thought.** Every individual
provider invocation, success or failure. Emitted by
`LLMBus._execute_llm_call` (success path) and
`LLMBus._try_service`'s exception handler (failure path).
(`runtime_control.py:1424-1485`)

```json
{
  "thought_id": "...", "task_id": "...", "timestamp": "...",

  "handler_name": "EthicalPDMA",
  "service_name": "OpenAICompatibleLLM",

  "model": "google/gemma-4-31B-it",
  "base_url": "https://api.together.xyz/v1",
  "response_model": "EthicalDMAResult",

  "prompt_tokens": 8192,
  "completion_tokens": 512,
  "prompt_bytes": 32666,
  "completion_bytes": 1024,
  "cost_usd": 0.0123,

  "duration_ms": 90000.0,

  "status": "ok",
  "error_class": null,
  "attempt_count": 1,
  "retry_count": 0,

  "prompt_hash": "0123abcd... (sha256 hex, 64 chars — DETAILED+)",
  "prompt": "<full prompt text — FULL only>",
  "response_text": "<full completion text — FULL only>",

  "parent_event_type": "ASPDMA_RESULT",
  "parent_attempt_index": 0,

  "attempt_index": 4
}
```

| Field | Required | Notes |
|---|---|---|
| `handler_name` | yes | DMA / ASPDMA / conscience handler that issued the call. Use this to attribute load and tail latency. |
| `service_name` | yes | LLM service implementation (e.g. `OpenAICompatibleLLM`, `MockLLMService`). |
| `duration_ms` | yes | Wall-clock; ≥ 0. |
| `status` | yes | One of `ok`, `timeout`, `rate_limited`, `model_not_available`, `instructor_retry`, `other_error`. |
| `model` / `base_url` | optional | May be null if the service didn't expose them. |
| `prompt_tokens` / `completion_tokens` | optional | From provider's usage report. |
| `prompt_bytes` / `completion_bytes` | optional | Raw byte counts, sanity-check vs token counts. |
| `error_class` | required on failure | Exception class name; preserved verbatim even when `status` is `other_error`. |
| `attempt_count` | yes | Instructor retry counter (1 = first try, 2+ = re-prompted on parse failure). |
| `retry_count` | yes | LLMBus-level retry counter (0 = first attempt). |
| `attempt_index` | yes | §6 — monotonic per (thought_id, event_type). |
| `parent_event_type` | recommended (2.7.9), required (2.8.0+) | The pipeline event_type whose execution issued this LLM call (e.g. `ASPDMA_RESULT`, `IDMA_RESULT`, `CONSCIENCE_RESULT`). Forms a non-forgeable parent-link with `parent_attempt_index` — see below. |
| `parent_attempt_index` | recommended (2.7.9), required (2.8.0+) | The `attempt_index` of the parent pipeline event under the same `(thought_id, parent_event_type)` namespace. Together with `parent_event_type` and the parent CompleteTrace's `(agent_id_hash, trace_id, thought_id)`, uniquely identifies the parent row in the persistence layer. |

**Parent-event linkage (item #5 of #712).** LLM_CALL events SHOULD carry
`parent_event_type` + `parent_attempt_index` as first-class wire-format
fields, included in the trace's signed canonical bytes (§8). Implicit
positional linkage is not safe — broadcast reordering or replay can
break it. Explicit linkage in the signed bytes makes the link
non-forgeable: a malicious lens-side aggregator cannot rebind an
LLM_CALL to a different parent without invalidating the trace's
signature. The persistence layer's `trace_llm_calls` foreign key into
`trace_events` MUST resolve to `(agent_id_hash, trace_id, thought_id,
parent_event_type, parent_attempt_index)` once the agent emits these
fields.

**Transition window (2.7.9).** The agent-side emission of
`parent_event_type` + `parent_attempt_index` is being staged across
2.7.9 patches. During this window, persistence implementations MUST
accept LLM_CALL events with these fields ABSENT (treat as nullable
foreign-key parent until backfill is possible) and MUST NOT reject
on missing-field. Agents emitting these fields in 2.7.9 SHALL include
them in the signed canonical bytes. Bumping `trace_schema_version`
from `"2.7.0"` to `"2.7.9"` once emission is complete signals the
transition; persistence layers gate `parent_*` field requirement on
`trace_schema_version >= "2.7.9"`.

The lens schema in `FSD/TRACE_EVENT_LOG_PERSISTENCE.md §5.2` proposes a
sibling `trace_llm_calls` table for these — query-friendly per-call
rows rather than nesting them inside the parent component's data.

## 6. `attempt_index` semantics

Every component carries an `attempt_index` integer in `data`,
populated by the adapter
(`accord_metrics/services.py:_process_single_event`). Semantics:

- Monotonic per `(thought_id, event_type)`, starting at 0.
- For events that broadcast at most once per thought (THOUGHT_START,
  SNAPSHOT_AND_CONTEXT, DMA_RESULTS, IDMA_RESULT, ACTION_RESULT,
  ROUND_COMPLETE) → always 0.
- For events that broadcast N times per thought (LLM_CALL,
  CONSCIENCE_RESULT, ASPDMA_RESULT, future recursive variants) →
  increments with each broadcast in receipt order.

**Why it's necessary:** broadcast timestamps can collide at sub-ms
granularity, especially under concurrent thought processing. The
adapter computes attempt_index from a counter keyed on
`(thought_id, event_type)`, so the lens can order rows deterministically
without timestamp races.

The counter is reset per thread when `ACTION_RESULT` seals the trace
(`_complete_trace` cleans up entries for that thought).

**`ts` is defense-in-depth, not redundant.** The persistence dedup tuple
(§9.1) includes both `attempt_index` AND `ts`. `attempt_index` is the
ordering invariant — but if a future implementation has an
attempt_index counting bug (skipping, double-incrementing, race in the
counter cleanup), `ts` keeps the dedup index UNIQUE-correct rather than
collapsing distinct events into one row. Implementations MUST NOT drop
`ts` from the dedup tuple "because attempt_index is enough" — that's
the exact regression `INCOMING_2_7_8.md §7.1` proposed and #712 closes.

## 7. Trace-level gating

Three privacy/bandwidth tiers
(`accord_metrics/services.py:78-98`):

| Level | Includes | Excludes |
|---|---|---|
| `generic` | All numeric scores, booleans, identifiers, attempt_index, sizes (tokens + bytes), durations, cost. **No content text.** | Reasoning text, prompt text, response text, prompt hashes. |
| `detailed` | Generic + reasoning text fields, override reasons, identified sources, sanitized stakeholder lists, prompt hashes. | Full prompt + response text. |
| `full_traces` | Detailed + every prompt + every completion verbatim. | (nothing — full reasoning corpus) |

`trace_level` is constant within a single batch envelope. An agent at
`generic` cannot mix `full_traces` events.

The signature input includes `trace_level` (see §8) — re-signing at a
different level produces a different signature, so verification cannot
be confused across levels.

## 8. Signing & verification

Per-trace Ed25519 signatures
(`accord_metrics/services.py:208-368`).

**Canonical payload** (the bytes signed):

```python
canonical = {
    "trace_id": trace.trace_id,
    "thought_id": trace.thought_id,
    "task_id": trace.task_id,
    "agent_id_hash": trace.agent_id_hash,
    "started_at": trace.started_at,
    "completed_at": trace.completed_at,
    "trace_level": trace.trace_level,
    "trace_schema_version": trace.trace_schema_version,
    "components": [
        {
            "component_type": c.component_type,
            "data": _strip_empty(c.data),  # omit None / "" / [] / {}
            "event_type": c.event_type,
            "timestamp": c.timestamp,
        }
        for c in trace.components
    ],
}
signed_bytes = json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode("utf-8")
signature = ed25519_sign(signed_bytes)
```

**Key:** unified Ed25519 signing key, shared between the audit service
and accord_metrics traces. Agent registers its public key with the
lens at startup (POST `<endpoint>/accord/agents/register`); the lens
caches `signature_key_id → public_key` for verification.

**Verification on the lens side:**

1. Look up the public key by `signature_key_id`.
2. Reconstruct `canonical` from the received CompleteTrace using the
   same algorithm above (json.dumps with sort_keys + separators).
3. `ed25519_verify(public_key, canonical_bytes, signature)`.
4. Reject the trace on signature mismatch.

The lens MUST verify before persisting; storing un-verified traces
defeats the ledger guarantee.

## 9. Persistence model recommendation

See `FSD/TRACE_EVENT_LOG_PERSISTENCE.md` for the full proposal. Summary:

- Replace per-thought row writer with `trace_events` table — one row
  per TraceComponent, keyed on the canonical dedup tuple in §9.1.
- Add `trace_llm_calls` sibling table — one row per LLM_CALL event,
  parent-FK to the issuing pipeline event row via `(agent_id_hash,
  trace_id, thought_id, parent_event_type, parent_attempt_index)`
  (see §5.10 parent-event linkage).
- Materialize `trace_thought_summary` view from these two tables for
  existing dashboards (preserves their query shape).

This shape preserves the override journey (the conscience reasons, the
rejected ASPDMA candidates, the per-LLM-call latency tail) that's
currently collapsed by last-write-wins per-thought rows.

### 9.1 Canonical persistence dedup tuple

Compliant `trace_events` implementations MUST use this exact UNIQUE key:

```
(agent_id_hash, trace_id, thought_id, event_type, attempt_index, ts)
```

Each component contributes:

| Field | Source | Why it's load-bearing |
|---|---|---|
| `agent_id_hash` | parent CompleteTrace (§3.1) | **AV-9 closure.** `trace_id` is "globally unique per agent" by convention only; the SQL layer treats it as adversary-controllable. Without `agent_id_hash` prefix, a malicious agent can pre-claim a row another agent's trace would write into. Per `CIRISPersist/THREAT_MODEL.md §3.1`. |
| `trace_id` | parent CompleteTrace (§3) | The trace-level identifier. |
| `thought_id` | parent CompleteTrace (§3) | The thought-level identifier within a trace. |
| `event_type` | TraceComponent (§4) | Discriminator for which `data` shape applies. **Canonical name**: `event_type`, not `step_point` (§4 alias rule). |
| `attempt_index` | TraceComponent `data` (§6) | Ordering invariant for events that broadcast multiple times per thought (LLM_CALL, CONSCIENCE_RESULT, ASPDMA_RESULT). |
| `ts` | TraceComponent `timestamp` (§4) | Defense-in-depth (§6). MUST NOT be dropped "because attempt_index is enough." |

This tuple is what `ciris-persist v0.2.2+` ships in its V001 schema
(`CIRISPersist/migrations/postgres/lens/V001__trace_events.sql`). The
spec lifts it here so any compliant implementation arrives at the
right UNIQUE key by reading the wire format alone, not by reading
persist's threat model. **Lens consumers** computing per-agent
aggregates (Coherence Ratchet detection, case-law candidate corpus,
N_eff measurements, constraint-space PCA) depend on this tuple holding
— a cross-agent pre-claim violation poisons the aggregates.

**Out-of-spec proposals** (e.g. dropping `agent_id_hash` and `ts`,
renaming `event_type → step_point`) MUST be rejected at review time
even if they appear in implementer-side design docs. The wire format
spec is the authority; threat-model rationale is summarized inline so
DDL authors don't need to read three repos to converge on the right
key.

## 10. The action anchor

A trace ships **only when ACTION_RESULT fires**. If a thought
times out, defers without action, or otherwise fails to produce an
action result, the in-memory state at the adapter is dropped. This is
intentional — the action is the ledger anchor. Pre-action reasoning
that doesn't produce an action is working memory, not history.

For forensics on action-less thoughts (provider hangs, conscience
loops that exhaust without resolution), the agent log
(`logs/sqlite/ciris_agent_*.log`) and `service_correlations` SQLite
table on the agent host are the right substrate. The lens stays clean:
post-action only.

## 11. End-to-end example: one wakeup thought

Wakeup `ACCEPT_INCOMPLETENESS` thought, agent Datum, mock-LLM
deterministic path, trace_level=generic. The `events[]` array
inside the batch envelope contains exactly one entry:

```json
{
  "event_type": "complete_trace",
  "trace_level": "generic",
  "trace": {
    "trace_id": "trace-th_std_518a7abb-6b1f-447b-a030-7af8f5d8cd37-20260430001553",
    "thought_id": "th_std_518a7abb-6b1f-447b-a030-7af8f5d8cd37",
    "task_id": "ACCEPT_INCOMPLETENESS_1d10d1b5-a1d0-4eaa-9c25-8d2cce3cd71e",
    "agent_id_hash": "7c3f8e2b...",
    "started_at": "2026-04-30T00:15:53.123456+00:00",
    "completed_at": "2026-04-30T00:16:12.789012+00:00",
    "trace_level": "generic",
    "trace_schema_version": "2.7.0",
    "components": [
      { "component_type": "observation", "event_type": "THOUGHT_START", "timestamp": "...:53.123Z",
        "data": { "thought_type": "standard", "thought_status": "PROCESSING", "round_number": 0,
                  "thought_depth": 0, "task_priority": 5, "channel_id": "wakeup",
                  "updated_info_available": false, "attempt_index": 0 } },
      { "component_type": "context", "event_type": "SNAPSHOT_AND_CONTEXT", "timestamp": "...:53.456Z",
        "data": { "system_snapshot": { /* ... */ }, "attempt_index": 0 } },

      /* ~3 LLM_CALL components fire here for the parallel DMA panel: */
      { "component_type": "llm_call", "event_type": "LLM_CALL", "timestamp": "...:54.012Z",
        "data": { "handler_name": "CSDMA", "service_name": "OpenAICompatibleLLM",
                  "duration_ms": 850.0, "status": "ok",
                  "prompt_tokens": 4200, "completion_tokens": 380,
                  "prompt_bytes": 18400, "completion_bytes": 1750,
                  "attempt_count": 1, "retry_count": 0, "attempt_index": 0 } },
      { "component_type": "llm_call", "event_type": "LLM_CALL", "timestamp": "...:54.045Z",
        "data": { "handler_name": "DSDMA", "service_name": "OpenAICompatibleLLM",
                  "duration_ms": 920.0, "status": "ok",
                  "prompt_tokens": 4250, "completion_tokens": 410, "attempt_index": 1 } },
      { "component_type": "llm_call", "event_type": "LLM_CALL", "timestamp": "...:54.078Z",
        "data": { "handler_name": "EthicalPDMA", "service_name": "OpenAICompatibleLLM",
                  "duration_ms": 1010.0, "status": "ok",
                  "prompt_tokens": 5100, "completion_tokens": 290, "attempt_index": 2 } },

      { "component_type": "rationale", "event_type": "DMA_RESULTS", "timestamp": "...:55.012Z",
        "data": { "csdma": { "plausibility_score": 1.00, "flags": [], "reasoning": "..." },
                  "dsdma": { "domain_alignment_score": 1.00, "flags": [], "reasoning": "..." },
                  "pdma":  { "action": "SPEAK", "rationale": "...",
                             "weight_alignment_score": 0.85, "ethical_alignment_score": 0.90 },
                  "attempt_index": 0 } },

      { "component_type": "llm_call", "event_type": "LLM_CALL", "timestamp": "...:55.234Z",
        "data": { "handler_name": "IDMA", "service_name": "OpenAICompatibleLLM",
                  "duration_ms": 750.0, "status": "ok", "attempt_index": 3 } },

      { "component_type": "rationale", "event_type": "IDMA_RESULT", "timestamp": "...:56.012Z",
        "data": { "k_eff": 3.0, "fragility_flag": false, "phase": "healthy",
                  "rho_mean": 0.18, "attempt_index": 0 } },

      { "component_type": "llm_call", "event_type": "LLM_CALL", "timestamp": "...:56.512Z",
        "data": { "handler_name": "ASPDMA", "service_name": "OpenAICompatibleLLM",
                  "duration_ms": 1200.0, "status": "ok",
                  "response_model": "ASPDMALLMResult", "attempt_index": 4 } },

      /* First conscience pass — passes, no override */
      { "component_type": "rationale", "event_type": "ASPDMA_RESULT", "timestamp": "...:57.789Z",
        "data": { "selected_action": "speak", "is_recursive": false,
                  "selection_confidence": 0.85, "attempt_index": 0 } },
      { "component_type": "conscience", "event_type": "CONSCIENCE_RESULT", "timestamp": "...:58.234Z",
        "data": { "conscience_passed": true, "action_was_overridden": false,
                  "final_action": "speak", "is_recursive": false,
                  "entropy_passed": true, "entropy_score": 0.25,
                  "coherence_passed": true, "coherence_score": 0.95,
                  "optimization_veto_passed": true, "optimization_veto_decision": "proceed",
                  "epistemic_humility_passed": true, "epistemic_humility_certainty": 0.90,
                  "thought_depth_current": 0, "thought_depth_max": 5,
                  "entropy_level": 0.25, "coherence_level": 0.95, "attempt_index": 0 } },

      /* Trace seals here */
      { "component_type": "action", "event_type": "ACTION_RESULT", "timestamp": "...:12.789Z",
        "data": { "action_executed": "speak", "action_parameters": {"content": "..."},
                  "execution_success": true, "execution_time_ms": 36.0,
                  "audit_sequence_number": 42, "audit_entry_hash": "abcd...",
                  "tokens_total": 28000, "tokens_input": 24000, "tokens_output": 4000,
                  "llm_calls": 5, "cost_cents": 0.012,
                  "models_used": ["meta-llama/llama-4-scout-17b-16e-instruct"],
                  "coherence_passed": true, "coherence_score": 0.95,
                  "entropy_passed": true, "entropy_score": 0.25,
                  "attempt_index": 0 } }
    ],
    "signature": "base64(...)",
    "signature_key_id": "ciris-agent-key:7c3f8e2b..."
  }
}
```

## 12. Validation contract for the lens

The lens MUST:

1. **Verify the Ed25519 signature** before persisting any component (§8).
2. **Honor the action anchor** — only `complete_trace` envelopes
   represent committed history; loose events without `complete_trace`
   wrappers should be treated as in-flight observations and not
   persisted as durable rows.
3. **Preserve per-attempt rows** — multiple `ASPDMA_RESULT`,
   `CONSCIENCE_RESULT`, `LLM_CALL` events for the same `thought_id`
   are intentional. Use `(thought_id, event_type, attempt_index)` as
   the dedup key, not `(thought_id, event_type)`.
4. **Treat `verb_specific_data` as opaque per-verb payload** — the
   lens may project per-verb columns at write time (e.g. extract
   `rights_basis` for DEFER) but MUST NOT reject events with verbs it
   doesn't recognize. New verbs are added without schema changes.
5. **Respect `trace_level`** — content-bearing fields (`prompt`,
   `response_text`, reasoning text) are absent at lower levels by
   design, not by accident. Fail-open queries that group by
   `trace_level` so dashboards don't claim "no reasoning data" when
   the agent is at `generic` for legitimate privacy reasons.
6. **Reject schema version mismatches** above the configured tolerance
   — the lens should advertise its supported `trace_schema_version`
   and refuse newer payloads it doesn't understand, returning HTTP 422
   with the error message indicating the version gap.

## 13. Open issues / forward compat

- **TSASPDMA_RESULT removal** scheduled for 2.8.0 — track the deprecation
  and drop dual-emit handling once the lens stops reading it.
- **`trace_events` + `trace_llm_calls` schema bump** to v2.8.0 per
  FSD §8 — adds the per-attempt and per-LLM-call shapes natively.
- **Loose event envelopes** (non-`complete_trace`) are not used today
  but the wire format reserves them. If the lens grows a live-streaming
  pane in the future, switch from `complete_trace` to per-event
  shipping by changing `_complete_trace` in the agent adapter; no
  schema-level changes required.

---

**Source-of-truth files** (cite these in any divergence dispute):

- `ciris_engine/schemas/services/runtime_control.py` — every event class
- `ciris_engine/schemas/streaming/reasoning_stream.py` — dispatcher + union
- `ciris_adapters/ciris_accord_metrics/services.py` — wire encoder, signer, batch shipper
- `ciris_engine/logic/buses/llm_bus.py` — LLM_CALL emission
- `ciris_engine/logic/processors/core/thought_processor/main.py` — VERB_SECOND_PASS_RESULT emission
- `tests/ciris_engine/schemas/streaming/test_reasoning_stream_new_events.py` — schema regression suite
- `tests/adapters/accord_metrics/test_attempt_index_and_new_events.py` — attempt_index + new-event regression suite
