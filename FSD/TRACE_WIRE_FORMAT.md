# CIRIS Trace Wire Format Specification

**For:** lens engineers building the persistence + query layer
**Specifies:** trace_format **v2.8.0** (CIRISAgent#1249, CIRISConstitution#166, CC 3.1.5). v2.7.0 is the legacy format and is still the **default emission** (see "Format versions" below).
**Wire stamp:** `trace_schema_version "3.0.0"` (substrate canonicalization epoch, §8). This is not the format version.
**Artifact:** `ciris_adapters/ciris_accord_metrics/schemas/trace_format_v2_8_0.json`, SHA-256 `b6f6fd3fddaf8c08338304dafe94b6db5322498cf9f2391dbba8b5fa9fe50b62`
**Companion:** `FSD/TRACE_EVENT_LOG_PERSISTENCE.md` (persistence model)
**Status:** definitive. Mirrors the artifact and the modules referenced inline.

This document specifies the format of the traces the CIRIS agent emits. It
is the contract. The JSON Schema artifact above is authoritative for
every type, pattern, bound and trace level. Where this document and the
artifact differ, the artifact wins. Where the hash above and
`schemas/SCHEMA_SHA256` differ, the pin file wins (the Constitution pins
that value). The implementation lives in these places:

- `ciris_adapters/ciris_accord_metrics/services.py` builds component `data` and the `deployment_profile`.
- `ciris_adapters/ciris_accord_metrics/egress_schema.py` loads every bound from the artifact and filters to it before signing.
- `ciris_engine/logic/utils/mock_llm_guard.py` resolves the run kind.
- `ciris_engine/schemas/services/runtime_control.py` defines every event class.
- ciris-lens-core (in the ciris-server wheel) assembles, seals and signs the envelope.

### Format versions

| | v2.8.0 (this spec) | v2.7.0 (legacy, default emission) |
|---|---|---|
| Artifact | `schemas/trace_format_v2_8_0.json` (pinned, above) | `schemas/trace_format_v2_7_0.json` |
| How a trace identifies itself | `deployment_profile.trace_format_version = "2.8.0"`, a signed member | No marker. Absence of `deployment_profile.trace_format_version` means 2.7.x. |
| `trace_schema_version` | `"3.0.0"` | `"3.0.0"` on the wire. The v2.7.0 artifact's const `"2.7.0"` is stale (§3.2). |
| `deployment_profile` | 10 members, closed, bounded (§3.2) | the 6 members of §3.2, unbounded strings |
| Run kind | `deployment_profile.run_kind`, on every run (§3.2.1) | overrides `deployment_type` on non-production runs |
| Component `data` bounds | per-level, closed (§7) | the same bounds. The enforcer always loads the v2.8.0 artifact. |

**Emission switch.** The adapter config key `trace_format_version`
takes precedence over the env var `CIRIS_TRACE_FORMAT_VERSION`. Values
are `2.7.0` or `2.8.0`, and a leading `v` is accepted. Unset means
`2.7.0`. An unknown value also emits `2.7.0` and logs a WARNING, so a
typo never produces a format the receiving node refuses.

**Deployment ordering.** Persist v54.1 and earlier refuse a v2.8.0
trace whole (`schema_unsupported_version`). The default therefore stays
`2.7.0` until a Persist release that admits v2.8.0 is deployed on the
receiving nodes (§13).

The changes from v2.7.0 are summarized in §14.

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
  "trace_schema_version": "3.0.0",
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
  agent has explicit user consent to share. It is part of the **batch**
  envelope and is **not signed** (§8). Its `deployment_region`,
  `deployment_type` and `agent_template` are unsigned copies:
  - v2.7.0: `deployment_type` is the run-kind marker, else the
    operator's value, else omitted. Region and template are the operator
    config values, else omitted.
  - v2.8.0: `deployment_type` is the operator's value only.
    `deployment_region` and `agent_template` copy what the signed
    profile resolved (§3.2), except that an undeclared template is
    omitted here rather than defaulted.

  Admitters read the signed `deployment_profile`, never these copies.
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

ciris-lens-core assembles, seals and signs the `<CompleteTrace>`. The
agent supplies the component events (§4, §5) and the
`deployment_profile` block (§3.2). It never sets
`trace_schema_version`. Shape at v2.8.0:

```json
{
  "trace_id": "trace-th_std_518a7abb-...-20260430001553",
  "thought_id": "th_std_518a7abb-6b1f-447b-a030-7af8f5d8cd37",
  "task_id": "ACCEPT_INCOMPLETENESS_1d10d1b5-...",
  "agent_id_hash": "7c3f8e2b1d9a4f60",
  "started_at": "2026-04-30T00:15:53.123456+00:00",
  "completed_at": "2026-04-30T00:16:12.789012+00:00",
  "trace_level": "generic",
  "trace_schema_version": "3.0.0",
  "deployment_profile": { /* §3.2 — v2.8.0: 10 members incl. run_kind, trace_format_version */ },
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
| `trace_schema_version` | string | yes | const `"3.0.0"` in the v2.8.0 artifact. lens-core stamps it at seal time. It is the **canonicalization epoch** (major ≥ 3 selects JCS, RFC 8785; §8), never the trace format version. Gate the canonicalizer on it, and gate the format on `deployment_profile.trace_format_version`. |
| `deployment_profile` | object | yes | The agent-supplied signed block (§3.2). v2.8.0: closed, 10 required members, including `trace_format_version` and `run_kind`. v2.7.0: the 6 original members. Persistence MUST refuse a trace without it. |
| `components` | array | yes | Ordered components (§4). v2.8.0 artifact: `minItems` 1, `maxItems` 64. |
| `signature` | base64 | yes | Ed25519 signature over the canonical payload (§8). |
| `signature_key_id` | string | yes | Key identifier for verification lookup. |

The v2.8.0 artifact's top-level `required` set is `trace_id`
(pattern `^trace-.*$`), `thought_id`, `agent_id_hash`, `components`,
`started_at`, `trace_schema_version` and `deployment_profile`. The
artifact types `task_id`, `completed_at`, `signature` and
`signature_key_id` as `string | null`. A sealed trace always carries
all of them, and the signature checks of §8 apply. `trace_level` is
optional in the artifact. When it is absent, components are validated
at `generic` (§7).

**Component ordering:** `components[]` is in receipt order at the
adapter. Receipt order matches broadcast order from
`reasoning_event_stream` because each subscriber's queue preserves
FIFO. Use the per-component `timestamp` for tie-breaking at sub-millisecond
granularity (component_type is also a coarse ordering hint — components
go through the H3ERE step sequence: observation → context → rationale →
conscience → action).

### 3.1 `agent_id_hash` is denormalized onto every TraceComponent (2.7.9+)

`agent_id_hash` appears at BOTH the CompleteTrace envelope level (§3) AND
on every TraceComponent (§4). The two values MUST be equal — agents emit
them locked at build time; persistence MAY reject mismatches as
malformed. The denormalization is deliberate: each event row is
self-contained, so the persistence layer reads `agent_id_hash` directly
from each component row without propagating from the envelope. This makes
the persistence dedup tuple (§9.1) `(agent_id_hash, trace_id, thought_id,
event_type, attempt_index, ts)` resolvable from a single component row.

Without `agent_id_hash` in the dedup tuple, a malicious agent can
pre-claim a `(trace_id, thought_id, event_type, attempt_index, ts)`
tuple it doesn't own (AV-9 in `CIRISPersist/THREAT_MODEL.md §3.1`). The
`trace_id` namespace ("globally unique per agent by convention") is
**adversary-controllable at the SQL layer**. The dedup tuple's
`agent_id_hash` prefix prevents cross-agent collision; the `ts` suffix is
defense-in-depth against attempt_index counting bugs (§6).

**Schema version semantics.** At `trace_schema_version "2.7.0"` the
field appeared only at the CompleteTrace level and persistence
propagated; at `trace_schema_version "2.7.9"` (and `"3.0.0"`, the current
stamp, which keeps the 2.7.9 layout) it appears on both
CompleteTrace and every TraceComponent — persistence reads directly.
Persistence implementations MAY accept 2.7.0-shaped traces during a
dual-window transition (`SUPPORTED_VERSIONS = ["2.7.0", "2.7.9"]`) but
MUST reject 2.7.9 traces missing the per-component value.

**Cross-shape field injection.** A trace with `trace_schema_version:
"2.7.0"` whose components carry per-component `agent_id_hash` fields
(the 2.7.9 shape's extra field) is malformed-but-safe: the 2.7.0
canonical reconstruction strips per-component fields outside the
4-field shape, so the signature still verifies and the dedup is
unaffected. **Persistence at `"2.7.0"` MUST IGNORE per-component
`agent_id_hash` if present — only the envelope value is authoritative
for that schema version.** This closes the cross-shape injection
question: an attacker cannot smuggle a different `agent_id_hash` per
component into a 2.7.0 trace and have it influence dedup or signing.

### 3.2 `deployment_profile` block

`deployment_profile` carries the cohort-taxonomy fields the lens needs
to route a trace to the right manifold-conformity centroid (RATCHET M3
drift / M4 alignment-manifold detection). Without these labels, lens
cannot separate behavioral clusters by `(agent_role, task_class,
deployment_type)` — same `agent_template` distributes across all
behavioral clusters and per-agent aggregates lose provenance signal.

ciris-lens-core assembles and signs the envelope. `deployment_profile`
is the **only signed block the agent supplies**, so every agent-sourced,
per-process value rides here: the cohort labels, the run kind, the
format version and the provenance members. The agent builds it when the
LensClient is built (at start and at every rebuild, e.g. when the mock
LLM latches). lens-core stamps the same block on every trace that
client seals. A lens-computed resourcing axis is stamped post-receipt
and is not part of this block (§3.3).

**v2.8.0 shape** (artifact `definitions.DeploymentProfile`). The block
is **closed** (`additionalProperties: false`) and **every member is
required**. Every member is at level `generic`: the profile rides every
trace at every `trace_level`.

```json
"deployment_profile": {
  "agent_role":            "ally",
  "agent_template":        "ally",
  "deployment_domain":     "general",
  "deployment_type":       "personal",
  "deployment_region":     null,
  "deployment_trust_mode": "sovereign",
  "run_kind":              "prod-personal",
  "trace_format_version":  "2.8.0",
  "pipeline_metadata": {
    "agent_version":                 "2.15.0-stable",
    "accord_version":                "1.2-Beta",
    "identity_hash":                 "<sha256 hex>",
    "pdma_version":                  null,
    "dsdma_domain_registry_version": null
  },
  "calibration_version":   "crc-v2"
}
```

Kinds and their patterns come from `x-ciris-egress.patterns` (§7):

- **token**: `^[A-Za-z0-9_.:/@+=\-]+$`. No spaces, non-empty.
- **label**: `^[^\u0000-\u001f\u007f]*$`. One line, no control characters.

| Member | Type | Kind, `maxLength` | Who sets it and the source (first match wins) | At v2.7.0 |
|---|---|---|---|---|
| `agent_role` | string | label, 128 | Operator. Adapter config `agent_role`, else the lowercased agent name, else `"unknown"`. Free-form; no enum closure, so operators can define roles. | same |
| `agent_template` | string | label, 128 | Operator. Adapter config `agent_template`, else `CIRIS_TEMPLATE`, else `"<agent_name>-default-unspecified"` (`"unknown-default-unspecified"` with no agent name). The setup wizard or CIRISManager sets `CIRIS_TEMPLATE`. It is read through `get_env_var`, so a `.env` value counts. | Config, else the `-default-unspecified` form. `CIRIS_TEMPLATE` is not read. |
| `deployment_domain` | string | token, 64 | Operator. Adapter config `deployment_domain`, else `"general"`. Vocabulary below. | same |
| `deployment_type` | string | label, 128 | Operator. Adapter config `deployment_type`, else `"production"`. **The operator's value only.** The run kind never touches it. | Overridden by the run-kind marker on non-production runs (§3.2.1) |
| `deployment_region` | string \| null | token, 64 | Operator. Adapter config `deployment_region`, else the env var `CIRIS_ACCORD_METRICS_DEPLOYMENT_REGION`, else `null`. `null` declares "not disclosed". The agent never infers a region. | Config, else `null`. The env var is not read. |
| `deployment_trust_mode` | string | token, 64 | Operator. Adapter config `deployment_trust_mode`, else `"sovereign"`. Vocabulary below. | same |
| `run_kind` | string, enum `RunKind` | token, 64 | The agent's mock latch, the harness, or the operator (§3.2.1). Set on **every** run, production included. | absent |
| `trace_format_version` | string, const `"2.8.0"` | token, 64 | Agent constant. Identifies the contract; the v2.8.0 admission gate keys on it. | absent |
| `pipeline_metadata` | object, closed | object | Agent (table below). | absent |
| `calibration_version` | string \| null | token, 64 | Substrate. `ciris_server.AXIS_CALIBRATION_VERSION` is lens-core's axis-calibration bundle, e.g. `"crc-v2"` (CIRISAgent#820). `null` when the substrate exposes none. | absent |

All ten members are in the signed bytes (§8). Field order in the JSON
is not significant, because the bytes are JCS-canonical.

**`pipeline_metadata`** (closed, all five members required; CIRISAgent#878, #1245):

| Member | Type | Kind, `maxLength` | Source |
|---|---|---|---|
| `agent_version` | string (non-null) | token, 64 | `CIRIS_VERSION` of the emitting build, e.g. `"2.15.0-stable"` |
| `accord_version` | string \| null | token, 64 | `ACCORD_VERSION` the agent reasons under |
| `identity_hash` | string \| null | token, 128 | `AgentIdentityRoot.identity_hash`: sha256 hex of `"{name}:{description}:{role_description}"`, computed when the identity is seeded or refreshed from a template. It is read from the identity graph, so it names the persona actually running, not the template file. `null` before the identity exists (first run). |
| `pdma_version` | null | token, 64 | Declared for #878. No source exists, so it is always `null`. |
| `dsdma_domain_registry_version` | null | token, 64 | Declared for #878. No source exists, so it is always `null`. |

This `pipeline_metadata` is **agent-side provenance**. It is a
different thing from the admitter's post-ingest `PipelineMetadata`
(stages, timings), which the admitter computes itself. An admitter MUST
NOT conflate the two or overwrite one with the other.

**Filter before sign.** The agent passes the built profile through
`egress_schema.enforce_deployment_profile` (the same filter as for
component data, §7) before handing it to lens-core. A member whose
value does not fit its kind is dropped. Two examples are an operator
`deployment_region` of `"North America"`, which is not a token, and a
multi-line `agent_role`, which is not a label. Because every member is
required, a dropped member is restored to its migration default:

| Member | Restored default |
|---|---|
| `agent_role` | `"unknown"` |
| `agent_template` | `"unknown-default-unspecified"` |
| `deployment_domain` | `"general"` |
| `deployment_type` | `"production"` |
| `deployment_region` | `null` |
| `deployment_trust_mode` | `"sovereign"` |
| `calibration_version` | `null` |

A dropped `pipeline_metadata` member becomes `null`. `agent_version` is
a build constant and always survives. The result is that a conformant
agent never signs a profile the artifact refuses.

**v2.7.0 shape (legacy, default emission).** Exactly the first six
members above, byte-identical to 2.15.0, with no bounds in the v2.7.0
artifact:

```json
"deployment_profile": {
  "agent_role":            "ally",
  "agent_template":        "ally-v3-default",
  "deployment_domain":     "general",
  "deployment_type":       "production",
  "deployment_region":     "US",
  "deployment_trust_mode": "federated_peer"
}
```

**Value vocabularies.** The v2.8.0 artifact bounds `deployment_domain`
and `deployment_trust_mode` by kind and length only, and `deployment_type`
is a free-form label. The vocabularies below are the declared values.
They are not schema enums, so a value that validates is well-formed.

`deployment_domain` is modeled on EU AI Act risk tier × domain. It is a
MECE primary domain, one value per trace, and `general` is the default
for multi-domain assistants. Adding a domain requires a wire-format-spec
PR.

```
healthcare | legal | financial | employment | education |
critical_infra | biometric | law_enforcement |
personal_assistant | moderation | research_scientific |
manufacturing_industrial |
general
```

`deployment_type` was originally designed as this lifecycle closure:

```
development | test | staging | production | research | decommissioned
```

`decommissioned` agents should not emit traces; lens MAY flag any
observed `decommissioned` emissions.

**What `deployment_type` actually carries (2026-10, CIRISAgent#1245).**
The lifecycle closure above is not what agents emit. Four vocabularies
share this one string:

| Source | Values |
|---|---|
| This section (original design) | `development \| test \| staging \| production \| research \| decommissioned` |
| Adapter setup wizard / `deployment_type` adapter config | `"" \| personal \| business \| research \| nonprofit` (operator free-form) |
| Run-kind marker (v2.15.0+, trace_format **v2.7.0 only**) | `mock \| qa \| battery`, overriding the operator value on every non-production run |
| Migration default when nothing is declared | `production` |

QA rows are not `deployment_type="test"`. A harness run is marked `qa`
(or `battery` for evaluation batteries such as the safety battery,
model_eval and HE-300), and a mock-LLM run is `mock`. From v2.8.0 the
run kind has its own member (§3.2.1), and `deployment_type` is the
operator-declared value only: free-form, and not to be reinterpreted
by admitters. Do not add new meanings to `deployment_type` at any
version.

**Stale const in the v2.7.0 JSON Schema.**
`ciris_adapters/ciris_accord_metrics/schemas/trace_format_v2_7_0.json`
still declares `trace_schema_version` as const `"2.7.0"`. The signed
stamp on the wire is produced by lens-core at seal time and is
`"3.0.0"` (the JCS canonicalization epoch; mirrored as
`TRACE_SCHEMA_VERSION` in `ciris_accord_metrics/services.py`). Validate
v2.7.0 traces against the wire value, not that const. The v2.8.0
artifact declares `"3.0.0"`.

**`deployment_trust_mode`** (federation intent):

```
sovereign | limited_trust | federated_peer
```

| Value | Meaning |
|---|---|
| `sovereign` | Alone — no federation directory, no peer replication. Agent runs against its own state without contributing to or consuming federation aggregates. |
| `limited_trust` | Partial federation. Test deployments and evaluation peers — eligible for some shared corpora but not full aggregate participation. |
| `federated_peer` | Full federation participation — contributes to and consumes federation aggregates, eligible for case-law replication and N_eff measurement. |

Distinct from `attestation_status`: `deployment_trust_mode` is the
agent's declared *intent*; `attestation_status` is the federation's
verification finding (e.g. "claims federated_peer but failed
attestation"). Both are needed for cohort routing.

**Migration defaults.** An agent the operator has not configured emits
these values. Persistence and lens MUST accept them, because they are
well-formed by definition:

```
deployment_domain      = "general"
deployment_type        = "production"
deployment_trust_mode  = "sovereign"
deployment_region      = null
agent_role             = lowercased(agent_name)
agent_template         = "{agent_name}-default-unspecified"   # v2.8.0: CIRIS_TEMPLATE first
```

Under v2.7.0 every 2.7.x row carries the `-default-unspecified`
template unless the operator configured one. This is the gap #1245
reported.

**Persistence dedup unaffected.** `deployment_profile` does NOT enter
the §9.1 dedup tuple — it is provenance metadata, not identity. Two
traces from the same `agent_id_hash` with different
`deployment_profile` values are still subject to AV-9 dedup
(`(agent_id_hash, trace_id, thought_id, event_type, attempt_index, ts)`).
Profile drift across an agent's lifetime (e.g. operator promotes
`development` → `production`) is reflected in the trace history but
does not partition the agent's identity.

**Version semantics.** The block's members are selected by
`deployment_profile.trace_format_version`, not by `trace_schema_version`:

| `trace_format_version` | Members |
|---|---|
| absent | v2.7.x: the 6 original members |
| `"2.8.0"` | the 10 members above, closed |

An admitter MUST reconstruct the signed canonical from the block
exactly as received (§8). A v2.8.0 profile parsed into a closed
6-member struct loses four members, and its signature then fails to
verify. Historical `trace_schema_version` eras: the block is absent at
`"2.7.0"`, and required on the wire and in the canonical bytes from
`"2.7.9"` (and `"3.0.0"`).

**Cross-shape field injection.** A `trace_schema_version "2.7.0"`
trace whose envelope carries a `deployment_profile` block (the 2.7.9
shape's extra field) is malformed but safe. The 2.7.0 canonical
reconstruction strips envelope keys outside the 9-field shape, so the
signature still verifies and dedup is unaffected. Persistence at
`"2.7.0"` MUST IGNORE `deployment_profile` if present. This is the same
closure rule as the per-component `agent_id_hash` cross-shape rule
above. Likewise, a trace without `trace_format_version` is v2.7.x, and
any v2.8.0-only member it carries MUST NOT be read as a v2.8.0 member.

#### 3.2.1 `run_kind`

`run_kind` records what kind of run produced the trace
(CIRISAgent#1244, CIRISAgent#1245; CC 3.1.5). It is labelled on every row at every trace level, so a
synthetic run never depends on parsing a channel string. The artifact's
`definitions.RunKind` closes the vocabulary:

| Value | Meaning | Set by |
|---|---|---|
| `production` | A production run whose deployment is not distinguished. It stays valid for any emitter that does not make the managed/personal distinction. | explicit declaration (`CIRIS_TRACE_RUN_KIND` or config) |
| `prod-personal` | A production run on a personal install, i.e. anything not deployed by CIRISManager | the default when nothing is declared, or an operator |
| `prod-managed` | A production run on a CIRISManager deployment | the default when `CIRIS_MANAGED` is truthy, or an operator |
| `qa` | A harness or test run, even with a real model | the harness |
| `battery` | An evaluation battery (safety battery, model_eval, HE-300), even with a real model | the harness |
| `mock` | The mock LLM produced the reasoning | the agent's mock latch only |

Admitters treat `production`, `prod-personal` and `prod-managed` alike;
only the label differs. `qa` and `battery` are admitted and labelled. A
federation-tier admitter refuses `mock` with `trace_run_kind_mock`, a
Persist-side token the agent never emits. The agent also seals and
signs a mock run but keeps it local-only and never replicates it to the
federation store.

**Resolution** (`mock_llm_guard.wire_run_kind`; highest first):

1. **Mock LLM latch.** `mock`. Nothing can override it.
2. **Harness declaration.** `CIRIS_TRACE_RUN_KIND=qa|battery`. An
   unrecognized non-empty value resolves to `qa` and logs a WARNING,
   so a typo never reads as production.
3. **Harness-only launch flags** (lands with #1268). If any of
   `CIRIS_TESTING_MODE`, `CIRIS_BENCHMARK_MODE`, `CIRIS_TEST_MODE` or
   `CIRIS_RESEARCH_PROMPT_OVERRIDES` is set while the declaration is
   empty or `production`, the run resolves to `qa` with a WARNING.
   These flags only ever move a run away from production.
4. **Operator override.** Adapter config `run_kind`. Any non-mock value
   is accepted. An unknown value, `mock` included, resolves to `qa`
   with a WARNING.
5. **Explicit production declaration.** `CIRIS_TRACE_RUN_KIND=production|prod-personal|prod-managed`
   is kept as is.
6. **Undeclared.** `prod-managed` when `CIRIS_MANAGED` is truthy
   (CIRISManager sets `CIRIS_MANAGED=true` on every agent it deploys),
   otherwise `prod-personal`. The heuristic
   `path_resolution.is_managed()` is **not** used. It counts Docker
   mounts, so it would call a personal `install.sh` Docker install
   managed.

Steps 1–3 run before the operator override, so config can never
relabel a harness run as production. `CIRIS_TRACE_RUN_KIND` is read
from these sources, first non-empty wins:

1. the process env;
2. the `.env` file (`get_env_var`);
3. on Android, the system property `debug.ciris.trace_run_kind`, which
   the harness sets with `adb shell setprop`.

iOS simulator harnesses forward the variable as
`SIMCTL_CHILD_CIRIS_TRACE_RUN_KIND`. Values are case-insensitive.

**Under v2.7.0** (the default emission) there is no `run_kind` member.
The legacy resolver (`trace_run_kind`, which is steps 1–3 plus explicit
production values) writes a non-production kind (`mock | qa | battery`)
into `deployment_type`, in both the signed profile and the unsigned
`correlation_metadata` copy. Every production kind, `prod-*` included,
leaves `deployment_type` alone, so the v2.7.0 bytes are unchanged.
v2.7.0 does not read the config `run_kind`, `CIRIS_TEMPLATE` or the
region env var.

**Admitter rule.** `run_kind` exists only where
`deployment_profile.trace_format_version` is `"2.8.0"`. An admitter
MUST NOT infer `run_kind` from `deployment_type` on 2.7.x rows. Such a
row's `deployment_type` may hold `mock`, `qa` or `battery` in place of
the operator's value, or an operator value that merely looks like a
run kind.

**`channel_id` stays DETAILED.** API channel ids embed the user id
(`api_<user_id>`), so `THOUGHT_START.channel_id` is not promoted to
GENERIC (§5.1). The #1245 labelling ask is met by `run_kind` on every
row at every level.

### 3.3 `deployment_resourcing` (lens-computed, not agent-declared)

A 7th cohort axis — **resourcing tier** — is NOT in the agent-emitted
envelope. It is computed lens-side from observed cost / tokens /
model-class-per-trace and stamped into a separate column on the
persisted row (`cirislens.trace_context.deployment_resourcing`). The
agent emits nothing for this field.

```
deployment_resourcing ∈ {
  scarcity     // < 50K tokens/trace AND < $0.01/action; edge / Pi / on-device small model
  constrained  // 50–150K tokens AND $0.01–0.05; single mid-size model
  standard     // 150–250K tokens AND $0.05–0.10; full pipeline mid-large model
  abundance    // > 250K tokens OR > $0.10/action; large/redundant/multi-model
}
```

Rationale for **lens-computed, not agent-declared:**

1. **Avoids implicit class hierarchy.** Operators of resource-constrained
   deployments (Pi-class, edge, sovereign-mode) should not have to
   self-label as `scarcity` while datacenter deployments self-label as
   `abundance`. The label is an external observation, not an identity
   declaration. Agent self-identity stays clean of economic tier.
2. **Defensive against forgery.** Declared resourcing is gameable —
   an attacker declares `abundance` while paying $0.001 to confuse
   cohort routing. Computed resourcing reflects actual operational
   reality (tokens billed, model-class observed in `LLM_CALL` rows).
3. **Adaptive without recompilation.** Tier boundaries can be re-tuned
   lens-side as model economics shift (today's `abundance` is
   tomorrow's `constrained`) without requiring agent updates.

Computation lives in lens; this spec normatively reserves the field
name and value enum closure but does not constrain the computation
rule. Lens MAY publish its current rule under
`cirislens.trace_context.deployment_resourcing_rule_version` for
reproducibility.

## 4. TraceComponent envelope

Each entry in `components[]`:

```json
{
  "agent_id_hash": "7c3f8e2b1d9a4f60",
  "component_type": "rationale",
  "event_type": "ASPDMA_RESULT",
  "timestamp": "2026-04-30T00:16:01.234567+00:00",
  "data": { /* event-type-specific fields — see §5 */ }
}
```

| Field | Type | Notes |
|---|---|---|
| `agent_id_hash` | string | Same 16-hex-char SHA-256 prefix as the parent CompleteTrace's `agent_id_hash` (§3 + §3.1). MUST be equal to the envelope value; agents emit them locked, persistence MAY reject mismatches. **Required at `trace_schema_version "2.7.9"` and `"3.0.0"`**; absent at `"2.7.0"`. |
| `component_type` | string (token, 64) | Substrate-assigned H3ERE category: `observation`, `context`, `rationale`, `conscience`, `action`, `verb_second_pass`, `llm_call`, `deferral_routed`, `unknown`. |
| `event_type` | enum | The `ReasoningEvent` value — discriminator for `data` shape. Closed set below. |
| `timestamp` | ISO-8601 | Per-component wall clock. |
| `data` | object | Event-specific payload. Its shape at each trace level is `EventData_<EVENT>__<level>` in the artifact (§7). It is closed: a field the event's table does not list is not allowed. |

The artifact requires `component_type`, `event_type`, `timestamp` and
`data` on every component.

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
| `DEFERRAL_ROUTED` | `deferral_routed` |

Empty fields are stripped before signing and shipping. lens-core's
`strip_empty` removes `None`, empty strings, empty lists and empty dicts
recursively from `data`. The lens must treat absent fields as "not
emitted at this trace level," not "emitted as null." Two consequences
follow. First, every `data` member the artifact types as nullable is
in practice absent rather than `null`. Second, the
`deployment_profile` is not stripped, so its `null` members are present
(§3.2). lens-core injects `attempt_index` into `data` at capture (§6),
after the agent's egress filter has run.

**`event_type` vs `step_point` naming.** This spec and `ciris-persist
v0.1.2+` use `event_type` as the canonical discriminator; the alias
`step_point` appears in some early lens design notes
(`INCOMING_2_7_8.md §7.1`) but is non-canonical. Persistence layers MAY
accept `step_point` as a deserialization alias for migration but MUST
write `event_type` on output. The dedup tuple in §9.1 binds
`event_type`, not `step_point`.

**`event_type` enum closure.** The v2.8.0 artifact closes `event_type`
to the 15-variant `ReasoningEventType` taxonomy, which lens-core locks
at compile time:

- `THOUGHT_START`
- `SNAPSHOT_AND_CONTEXT`
- `DMA_RESULTS`
- `IDMA_RESULT`
- `ASPDMA_RESULT`
- `TSASPDMA_RESULT` *(deprecated)*
- `VERB_SECOND_PASS_RESULT`
- `CONSCIENCE_RESULT`
- `ACTION_RESULT`
- `LLM_CALL`
- `DEFERRAL_ROUTED`
- `DEFERRAL_RECEIVED`
- `DEFERRAL_RESOLVED`
- `GRATITUDE_SIGNALED`
- `CREDIT_GENERATED`

The first eleven have dedicated `data` definitions (§5). The other four
validate against `EventData_FALLBACK` (§7). Persistence MUST reject
components whose `event_type` is outside this set. Silently accepting
unknown event types would let a future agent emission slip past
per-version payload gates (AV-12) without per-event review. A new
event type ships with a trace-format bump and a §5 subsection.

**`agent_id_hash` denormalization (2.7.9+).** Each TraceComponent
carries `agent_id_hash` on the wire; its value MUST equal the parent
CompleteTrace's `agent_id_hash` (§3). The denormalization makes each
component row self-contained — persistence reads the value directly
from the row without propagating from the envelope. Mismatch is
malformed and persistence MAY reject. (At `trace_schema_version
"2.7.0"` the field appeared only at the envelope level and persistence
propagated; 2.7.9 lifts the contract to per-component-on-wire.)

## 5. Reasoning event types and `data` shapes

Each subsection describes one event's `data` dict. **The normative
field set for each event is §7.2 and the artifact's
`EventData_<EVENT>` definition.** Those give every field's kind, the
lowest trace level at which it may appear, and its bound. No `data`
field is required by the artifact, so a field may be absent at any
level.

The JSON examples below are illustrative. Some of them show keys the
artifact does not list for that event, such as `thought_id`, `task_id`
or `timestamp` inside `data`, `*_prompt` keys on `DMA_RESULTS`, and
the conscience scores on `ACTION_RESULT`. The agent's egress filter
drops any such key before signing (`unexpected_field`, §7.3), so it
never appears on a v2.8.0 or v2.7.0 wire. The exception is
`attempt_index`, which lens-core injects after the filter (§6); every
`EventData_*` definition declares it (integer, GENERIC).

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

The fields have these levels:

- **GENERIC:** `round_number`, `thought_depth`, `task_priority`,
  `updated_info_available`, `requires_human_input` and `thought_type`.
- **DETAILED:** adds `thought_status`, `parent_thought_id`,
  `channel_id` (label, 128) and `source_adapter`.
- **FULL_TRACES:** adds `task_description`, `initial_context` and
  `thought_content`. `thought_content` is capped at 500 characters.

`channel_id` is DETAILED, never GENERIC, because API channel ids embed
the user id (`api_<user_id>`). Synthetic runs are labelled at every
level by `deployment_profile.run_kind` (§3.2.1), not by parsing this
string.

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
  "disclosure_version": null,
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

**`disclosure_version`** (v2.8.0 only; CIRISAgent#832). It is GENERIC,
of kind token, 64 characters, typed `string | null`, and optional. It
names the CIRISVerify mandatory-disclosure version active when the
thought ran. It is carried per event rather than in
`deployment_profile` because the disclosure follows license status and
can change while the process runs. The agent emits the key only under
v2.8.0, taking it from `verify_attestation.disclosure_version`.
CIRISVerify publishes no disclosure version today, so the value is
`null`. Since lens-core strips empty values (§4), the key is absent on
the wire until CIRISVerify publishes one. A v2.7.0 trace never carries
it.

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
  "correlation_risk": 0.18, "fragility_flag": false,
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
| `original_reasoning` | string | FULL_TRACES only (text, 65536). |
| `final_action` | string | Refined selection (may equal `original_action`). |
| `final_reasoning` | string | FULL_TRACES only (text, 65536). |
| `verb_specific_data` | object | GENERIC. **Closed** (`additionalProperties: false`): the union of the per-verb members in §5.7.1, each level-gated on its own. |
| `second_pass_prompt` | string \| null | FULL only. |
| `attempt_index` | int | §6. Always 0 today (no recursive verb-second-pass). |

#### 5.7.1 `verb_specific_data` shapes

Per-verb. The lens MAY denormalize these into verb-specific columns at
write time, but MUST treat the dict as authoritative.

In the v2.8.0 artifact, `verb_specific_data` is one closed object.
Each member has its own level:

| Member | Kind, bound | Level |
|---|---|---|
| `rights_basis`, `secondary_need_categories` | list of token (64), at most 32 items | GENERIC |
| `primary_need_category`, `domain_hint`, `operational_reason` | token, 64 | GENERIC |
| `original_tool_name`, `final_tool_name` | token, 128 | GENERIC |
| `node_id_corrected` | bool | GENERIC |
| `defer_reason` | text, 500 | DETAILED |
| `defer_until` | timestamp | DETAILED |
| `original_node_id`, `final_node_id` | label, 128 | DETAILED |
| `original_parameters`, `final_parameters` | BoundedJson | FULL_TRACES |

A member above the envelope's `trace_level` is dropped before signing.
This means a DEFER reason never rides GENERIC (CIRISAgent#1245).
Unknown members are dropped too. A new verb's members therefore need an
artifact change before they can ship.

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
| `parent_event_type` | yes (2.7.9+) | The pipeline event_type whose execution issued this LLM call (e.g. `ASPDMA_RESULT`, `IDMA_RESULT`, `CONSCIENCE_RESULT`). Forms a non-forgeable parent-link with `parent_attempt_index` — see below. |
| `parent_attempt_index` | yes (2.7.9+) | The `attempt_index` of the parent pipeline event under the same `(thought_id, parent_event_type)` namespace. Together with `parent_event_type` and the parent CompleteTrace's `(agent_id_hash, trace_id, thought_id)`, uniquely identifies the parent row in the persistence layer. |

**Parent-event linkage (item #5 of #712).** LLM_CALL events MUST carry
`parent_event_type` + `parent_attempt_index` as first-class wire-format
fields, included in the trace's signed canonical bytes (§8). Implicit
positional linkage is not safe — broadcast reordering or replay can
break it. Explicit linkage in the signed bytes makes the link
non-forgeable: a malicious lens-side aggregator cannot rebind an
LLM_CALL to a different parent without invalidating the trace's
signature. The persistence layer's `trace_llm_calls` foreign key into
`trace_events` MUST resolve to `(agent_id_hash, trace_id, thought_id,
parent_event_type, parent_attempt_index)`.

**Required as of 2.7.9 — no transition window.** Both fields ship
together: `trace_schema_version "2.7.9"` MUST carry them, persistence
implementations MUST enforce their presence on incoming LLM_CALL events,
and lens-side aggregators MAY reject any LLM_CALL row missing either
field. The agent's wire-format emission and the persistence-layer
enforcement land in the same release; there is no period where one
side accepts the absence of these fields. If a deployed agent at
`trace_schema_version "2.7.0"` ships an LLM_CALL without the parent
fields, persistence MAY persist it for backfill compatibility but MUST
NOT advance the dedup index for that trace until the agent upgrades.

The lens schema in `FSD/TRACE_EVENT_LOG_PERSISTENCE.md §5.2` proposes a
sibling `trace_llm_calls` table for these — query-friendly per-call
rows rather than nesting them inside the parent component's data.

### 5.11 `DEFERRAL_ROUTED`

Emitted by the adapter's `send_deferral` when a Wise Authority deferral
is routed (`component_type` `deferral_routed`). It joins the deferring
thought's in-flight trace and seals with that thought's
`ACTION_RESULT`.

```json
{ "defer_until": "2026-05-15T00:00:00+00:00", "reason": "<DETAILED+, text ≤ 500>" }
```

`defer_until` is GENERIC (timestamp kind). `reason` is DETAILED+
(text, 500).

**Held by default.** The capture is skipped and counted, because Persist
floors that lack the `deferral_routed` component variant would refuse
the whole deferring trace (CIRISPersist#203). Set
`CIRIS_ACCORD_METRICS_CAPTURE_DEFERRALS=true` to capture it.

## 6. `attempt_index` semantics

Every component carries an `attempt_index` integer in `data`. Since
the 2.9.6 fold it is injected by ciris-lens-core at capture
(`TraceComponent::data_with_attempt_index`, used for both the wire and
the signed bytes). This happens after the agent's egress filter (§7).
Every `EventData_*` definition in the artifact declares it as an
integer at level GENERIC, so a sealed trace validates; the agent never
emits it itself.
Semantics:

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

There are three privacy/bandwidth tiers (`TraceDetailLevel` in
`accord_metrics/services.py`; the order comes from
`x-ciris-egress.levels`):

| Level | Includes | Excludes |
|---|---|---|
| `generic` | Numbers, booleans, short enumeration tokens and identifiers, sizes (tokens and bytes), durations, cost. **No content text.** The one exception is `attestation_context`, an agent-authored status string (text, 1024) that carries no LLM or user content. | Free text, reasons, lists of sources or flags, prompts, responses, prompt hashes, channel ids. |
| `detailed` | Generic, plus bounded lists (flags, sources, stakeholders), key identifiers (`channel_id`, `key_id`, `prompt_hash`, `base_url`), and short *reason* text capped at 500 characters (defer, conscience and override reasons). | The reasoning chain, prompts, responses, opaque JSON payloads. |
| `full_traces` | Detailed, plus reasoning text, every prompt and completion (text, 65536), and opaque JSON (`BoundedJson`). | Nothing beyond the bounds. |

`trace_level` is constant within a single batch envelope. An agent at
`generic` cannot mix `full_traces` events.

The signature input includes `trace_level` (see §8) — re-signing at a
different level produces a different signature, so verification cannot
be confused across levels.

### 7.1 The per-level schema

The artifact expresses level gating two ways, and they agree. A test
asserts this.

- **The `level` keyword.** Each `data` field (and each
  `deployment_profile` member) carries `level` with one of these values:
  `generic`, `detailed` or `full_traces`. It is the **lowest**
  `trace_level` at which the field may appear. Above the envelope's
  `trace_level` the field MUST be absent. `level` and the `x-ciris-*`
  keywords are annotations, so standard validators ignore them.
- **`EventData_<EVENT>__<level>` views.** These express the same rule in
  plain draft-07. Each view is `allOf` the base `EventData_<EVENT>`
  (closed: `additionalProperties: false`), plus a `propertyNames` enum
  listing the fields allowed at that level. That list is cumulative, so
  `__detailed` includes every generic field.
  `TraceComponent__<level>` selects the view by `event_type` with
  `if/then`. The root's `allOf` selects `TraceComponent__<level>` by the
  envelope's `trace_level`. An envelope with no `trace_level` is
  validated at `generic`. Event types without a dedicated definition use
  `EventData_FALLBACK__<level>`.

Nested objects are closed as well: `csdma`, `dsdma`, `pdma` and `idma`
inside `DMA_RESULTS`, `verb_specific_data` (§5.7.1), and
`deployment_profile.pipeline_metadata`. Their members carry their own
`level`, which the agent's filter applies. The views constrain only the
top-level `data` keys.

### 7.2 Field sets by event and level

These are the top-level `data` keys from the artifact, listed at the
lowest level where each one may appear. For each field's kind and bound,
see `definitions.EventData_<EVENT>.properties.<field>`. Every event also
admits `attempt_index` at GENERIC (injected by lens-core, §6); it is
omitted from the rows below.

| `event_type` | GENERIC | DETAILED adds | FULL_TRACES adds |
|---|---|---|---|
| `THOUGHT_START` | `round_number`, `thought_depth`, `task_priority`, `updated_info_available`, `requires_human_input`, `thought_type` | `thought_status`, `parent_thought_id`, `channel_id`, `source_adapter` | `task_description`, `initial_context`, `thought_content` |
| `SNAPSHOT_AND_CONTEXT` | `agent_name`, `cognitive_state`, `attestation_context`, `attestation_level`, `attestation_status`, `disclosure_severity`, `disclosure_version`, `binary_ok`, `env_ok`, `registry_ok`, `file_integrity_ok`, `audit_ok`, `play_integrity_ok`, `hardware_backed`, `memory_count`, `context_tokens` | `active_services`, `context_sources`, `service_health`, `agent_version`, `circuit_breaker_status`, `key_status`, `key_id`, `ed25519_fingerprint`, `key_storage_mode`, `hardware_type`, `verify_version` | `system_snapshot`, `gathered_context`, `relevant_memories`, `conversation_history` |
| `DMA_RESULTS` | `csdma`, `dsdma`, `pdma`, `idma`, `csdma_plausibility_score`, `dsdma_domain_alignment` | `dsdma_domain` | `combined_analysis` |
| `IDMA_RESULT` | `k_eff`, `effective_source_count`, `correlation_risk`, `source_overlap`, `fragility_flag`, `reasoning_is_fragile`, `phase`, `reasoning_state`, `idma_k_eff`, `idma_correlation_risk`, `idma_fragility_flag`, `idma_phase` | `k_raw`, `raw_source_count`, `rho_mean`, `phase_confidence`, `collapse_margin`, `safety_margin`, `sources_identified`, `source_ids`, `source_types`, `source_independence_scores`, `source_type_counts`, `correlation_factors`, `top_correlation_factors`, `pairwise_correlation_summary`, `rho_intra`, `rho_inter`, `module_count`, `effective_module_count`, `source_clusters`, `common_cause_flags`, `intervention_recommendation`, `next_best_recovery_step`, `delta_k_eff`, `delta_rho_mean`, `phase_persistence_steps`, `time_in_fragile_state_ms`, `moving_variance`, `rho_critical`, `k_required`, `defense_function`, `collapse_rate`, `time_to_truth`, `time_to_entropy`, `time_to_capture` | `reasoning`, `prompt_used` |
| `ASPDMA_RESULT` | `selected_action`, `selection_confidence`, `is_recursive` | `alternatives_considered`, `evaluation_time_ms` | `action_rationale`, `reasoning_summary`, `action_parameters`, `aspdma_prompt`, `raw_llm_response` |
| `TSASPDMA_RESULT` | `original_tool_name`, `final_action`, `final_tool_name` | `gotchas_acknowledged`, `tool_description` | `original_parameters`, `final_parameters`, `aspdma_rationale`, `tsaspdma_rationale`, `tsaspdma_prompt` |
| `VERB_SECOND_PASS_RESULT` | `verb`, `original_action`, `final_action`, `verb_specific_data` | — | `original_reasoning`, `final_reasoning`, `second_pass_prompt` |
| `CONSCIENCE_RESULT` | `conscience_passed`, `action_was_overridden`, `ethical_faculties_skipped`, `is_recursive`, `updated_status_detected`, `thought_depth_triggered`, `thought_depth_current`, `thought_depth_max`, `entropy_level`, `coherence_level`, `entropy_passed`, `entropy_score`, `entropy_threshold`, `coherence_passed`, `coherence_score`, `coherence_threshold`, `optimization_veto_passed`, `optimization_veto_entropy_ratio`, `epistemic_humility_passed`, `epistemic_humility_certainty` | `final_action`, `conscience_override_reason`, `entropy_reason`, `coherence_reason`, `optimization_veto_decision`, `optimization_veto_affected_values`, `epistemic_humility_uncertainties`, `epistemic_humility_recommendation` | `epistemic_data`, `updated_status_content`, `optimization_veto_justification`, `epistemic_humility_justification` |
| `ACTION_RESULT` | `execution_success`, `execution_time_ms`, `tokens_input`, `tokens_output`, `tokens_total`, `cost_cents`, `carbon_grams`, `energy_mwh`, `llm_calls`, `audit_sequence_number`, `audit_entry_hash`, `has_positive_moment`, `has_execution_error`, `success`, `action_executed` | `follow_up_thought_id`, `audit_entry_id`, `models_used`, `api_bases_used`, `execution_error`, `audit_signature` | `action_parameters`, `positive_moment` |
| `LLM_CALL` | `handler_name`, `service_name`, `model`, `response_model`, `duration_ms`, `prompt_tokens`, `completion_tokens`, `prompt_bytes`, `completion_bytes`, `cost_usd`, `status`, `error_class`, `attempt_count`, `retry_count`, `parent_event_type`, `parent_attempt_index` | `base_url`, `prompt_hash` | `prompt`, `response_text` |
| `DEFERRAL_ROUTED` | `defer_until` | `reason` | — |
| other (`EventData_FALLBACK`) | `event_type` | — | `raw_data` |

The members of `DMA_RESULTS.csdma`, `.dsdma` and `.pdma` are as
follows. `idma` uses the `IDMA_RESULT` field set without the `idma_*`
aliases.

| Object | GENERIC | DETAILED | FULL_TRACES |
|---|---|---|---|
| `csdma` | `plausibility_score` | `flags` | `reasoning`, `prompt_used` |
| `dsdma` | `domain_alignment` | `domain`, `flags` | `reasoning`, `prompt_used` |
| `pdma` | `has_conflicts` | `stakeholders`, `conflicts`, `alignment_check` | `reasoning`, `prompt_used` |

### 7.3 Kinds and bounds

Every field has an `x-ciris-kind`. Each string kind has a `pattern`, and
every kind has a bound. The bounds come from `x-ciris-egress.bounds`
and `x-ciris-egress.patterns`, and `egress_schema.py` loads them from
there rather than restating them:

| Kind | Pattern / shape | Bound (artifact constant) |
|---|---|---|
| `number`, `integer`, `bool` | JSON type | — (non-finite numbers are dropped) |
| `token` | `^[A-Za-z0-9_.:/@+=\-]+$` | `maxLength` 64 (`TOKEN_MAX_CHARS`). Identifier-like tokens use 128 (`IDENTIFIER_MAX_CHARS`). |
| `label` | `^[^\u0000-\u001f\u007f]*$` (one line) | `maxLength` 128 (`LABEL_MAX_CHARS`) |
| `timestamp` | ISO-8601 (`x-ciris-egress.patterns.timestamp`) | — |
| `url` | `^https?://[^\s/?#@]+(/[^\s?#]*)?$` (no userinfo, query or fragment) | `maxLength` 256 (`URL_MAX_CHARS`) |
| `text` | free text | GENERIC system text 1024 (`SYSTEM_TEXT_MAX_CHARS`). Reasons 500 (`REASON_MAX_CHARS`). FULL_TRACES text 65536 (`FULL_TEXT_MAX_CHARS`). |
| `list` | items of a declared kind | `maxItems` 32 (`LIST_MAX_ITEMS`). Service lists use 64. |
| `map` | token keys (≤ 128), typed values | `maxProperties` 64 (`MAP_MAX_ITEMS`) |
| `object` | closed, typed members | per member |
| `json` (`BoundedJson`) | any JSON | strings ≤ 8192 (`JSON_MAX_STRING_CHARS`), arrays and objects ≤ 256 entries (`JSON_MAX_ITEMS`), keys ≤ 128 (`JSON_MAX_KEY_CHARS`), depth ≤ 8 (`JSON_MAX_DEPTH`). JSON Schema cannot express depth, so the agent enforces it and an admitter may. |

A few fields carry their own bound. For example, `thought_content` is
text capped at 500, `raw_llm_response` is text capped at 1000,
`agent_name` is a label capped at 64, and `audit_signature` is a token
capped at 256. The per-field `maxLength`, `maxItems` or
`maxProperties` in the artifact is authoritative.

**Filter at the agent, refuse at the admitter.** The agent's
`egress_schema.enforce_egress_schema` runs on every component, and
`enforce_deployment_profile` runs on the v2.8.0 profile, both **before
signing**. The filter does not refuse a whole event. Instead:

- A field not in the event's schema, or above the trace level, is dropped (`unexpected_field`).
- A value of the wrong type is dropped (`wrong_type`). This includes a
  token or label that fails its pattern, and an over-long token, label
  or URL. A 96 KB "flag" is not a flag.
- Over-long `text` is truncated, and over-long lists and maps are cut
  to their cap (`over_cap`).

Each violation is logged once per (event, path, kind, level) as a
WARNING. The log names the producer's mistake and never the value, and
every violation is counted. The bounds apply whichever format version
is emitted, because the enforcer always loads the v2.8.0 artifact. A
conformant agent therefore never signs a trace the artifact refuses.

The admitter refuses and never truncates. A trace that fails the
artifact is refused whole with `trace_field_shape_violation`, a
Persist-side token (§12).

## 8. Signing & verification

Per-trace Ed25519 signatures. ciris-lens-core seals and signs with the
persist Engine's federation signer (`capture/seal.rs`,
`build_canonical_envelope`). The agent does not sign traces.

**Canonical payload at `trace_schema_version "3.0.0"`** (the bytes signed;
same layout as `"2.7.9"`):

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
    "deployment_profile": trace.deployment_profile,  # the WHOLE block as supplied, not stripped (§3.2):
                                                     #   v2.7.0: the 6 members
                                                     #   v2.8.0: all 10 members, incl. run_kind,
                                                     #   trace_format_version, pipeline_metadata{5}
    "components": [
        {
            "agent_id_hash": c.agent_id_hash,  # 2.7.9+ — denormalized from envelope, MUST equal trace.agent_id_hash
            "component_type": c.component_type,
            "data": strip_empty(c.data | {"attempt_index": c.attempt_index}),  # omit None / "" / [] / {}
            "event_type": c.event_type,
            "timestamp": c.timestamp,
        }
        for c in trace.components
    ],
}
signed_bytes = jcs_canonicalize(canonical)   # RFC 8785 — 2.9.6 HARD cutover
signature = ed25519_sign(signed_bytes)
```

**2.9.6 LensCore fold — the producer moved into the substrate.** As of the
fold (CIRISAgent#866/#857) the agent's Python trace producer is RETIRED:
`ciris-lens-core`'s `LensClient`/`CaptureClient` owns capture → seal →
Ed25519-sign (via the persist Engine's federation signer) →
`receive_and_persist`. As of ciris-lens-core **1.0.1** (CIRISLensCore#43.2)
the substrate stamps `trace_schema_version "3.0.0"` and seals with the JCS
canonicalizer selected by the SAME `canon_version_for_trace_schema` gate the
verifier uses (major ≥ 3 ⇒ RFC 8785) — stamp and bytes cannot skew, the
carve-out era is closed, and the 2.9.6 JCS cutover is complete at every
layer. (lens-core 1.0.0 transitionally stamped "2.7.9"/V1Python.) The `"3.0.0"`+JCS producer below was live
in the agent's Python signer for the pre-fold window (commits
9c3546dc8/2a228b4a4) and remains live in the **cirisnode adapter's private
legacy pipeline** (`ciris_adapters/cirisnode/_legacy_trace.py`, its own wire
counterpart) — persist's signed-epoch verify gate dispatches both eras
correctly.

**JCS canonicalization — the 2.9.6 cutover (CEG §0.9).** `signed_bytes` at
schema era "3.0.0" is the RFC 8785 (JSON Canonicalization Scheme) byte
sequence, produced by `ciris_verify_core::jcs` (the one blessed impl,
shipped in ciris-verify ≥ 5.0.0; Python producers reach it via
`ciris_verify.jcs_canonicalize`). This is byte-identical to what the Rust
federation verifiers recompute, so the signed bytes and the verifier's
reconstructed bytes match on **all** inputs.

Pre-2.9.6 the producer used `json.dumps(canonical, sort_keys=True,
separators=(",", ":"))`. That is **not** JCS: Python's `json.dumps` defaults to
`ensure_ascii=True`, so every non-ASCII codepoint was emitted as a `\uXXXX`
escape while RFC 8785 requires the minimal literal UTF-8 encoding. The two
agree only on pure-ASCII traces; they diverge on the entire multilingual trace
corpus (Amharic, Arabic, Chinese, …), where the legacy bytes verified locally
but failed against any Rust verifier. 2.9.6 ships the cut across the substrate
triple in lockstep — agent producer (`_build_canonical_message`), LensCore's
byte-parity harness, persist's reconstruction, and verify — so there is no
mixed-canonicalization window: a 2.9.6 signature is JCS, full stop. (For ASCII
traces the bytes are unchanged, so already-signed historical ASCII traces still
verify.)

**What is in the signed bytes.** The whole `deployment_profile` block
is part of the signed canonical, so **every** member is non-forgeable
after emission. Under v2.8.0 that covers `run_kind`,
`trace_format_version`, `pipeline_metadata` and `calibration_version`
as well as the six cohort labels. A federation peer verifying the
signature recovers exactly the labels, run kind and provenance the
agent declared at signing time. Re-stamping by an intermediary, or by
persist itself, fails verification. So does dropping a member: a
verifier that parses the profile into a narrower struct and rebuilds
the canonical from it cannot reproduce the bytes (§3.2, §13). Every
component, including its `data` (with `attempt_index`), is signed too.

These are **not** signed:

- the batch envelope, including `correlation_metadata` (§1), whose
  `deployment_*` / `agent_template` values are unsigned copies;
- `batch_timestamp` and `consent_timestamp`;
- `deployment_resourcing` (§3.3), which is lens-computed post-receipt
  and stamped into the persisted row, not into the agent-signed
  envelope.

**Format version vs canonical shape.** `trace_format_version` changes
what is *inside* `deployment_profile` and `data`. It does not change
the canonical shape or the canonicalizer, which are selected by
`trace_schema_version` (table below). A v2.8.0 trace and a v2.7.0 trace
at `"3.0.0"` have the same 10-key outer canonical and the same JCS
bytes rule.

**Schema-version-gated canonical shapes — deterministic dispatch.**
`trace_schema_version` is part of the signed canonical bytes (it
appears as a top-level key in the canonical above), which makes the
field self-authenticating: the verifier MUST select the canonical
shape by `trace_schema_version` and reject on signature mismatch with
the *selected* shape. There is no fallback iteration, no "try-list"
under load — a 2.7.9 trace whose signature fails against the 2.7.9
canonical is invalid even if it would happen to verify against the
2.7.0 shape.

| `trace_schema_version` | Outer canonical | Per-component shape | Notes |
|---|---|---|---|
| `"2.7.0"` | 9 keys (no `deployment_profile`) | 4 fields: `component_type`, `data`, `event_type`, `timestamp` | The 9-field outer canonical shipped in 2.7.8.9. Persistence propagates `agent_id_hash` from envelope. |
| `"2.7.9"` | 10 keys (adds `deployment_profile`) | 5 fields: above + `agent_id_hash` (denormalized) | Agent's wire-format emission 2.7.9 → pre-2.9.6. Same field layout as `"3.0.0"`; **canonicalizer is legacy Python `json.dumps(sort_keys=True, separators=(",",":"))`**. Persistence reads `agent_id_hash` directly from each component AND extracts the 6 `deployment_profile` fields into denormalized `cirislens.trace_context` columns. |
| `"3.0.0"` | 10 keys (adds `deployment_profile`) | 5 fields: above + `agent_id_hash` (denormalized) | Current stamp, for both trace_format v2.7.0 and v2.8.0. Agent's wire-format emission as of release/2.9.6. **Identical field layout to `"2.7.9"`; the ONLY change is the canonicalizer → RFC 8785 (JCS).** The major-version bump is the signed-bytes-bound discriminator for the canonicalizer gate (`major >= 3 ⇒ JCS`, `2.x ⇒ Python`); without it a verifier cannot tell which canonicalizer reproduces the signature. See §8 "JCS canonicalization". |

The legacy 2-field shape (`{"components", "trace_level"}`, pre-2.7.8.9)
is retired on the agent side. Persistence implementations MAY accept
it for federation peers that haven't upgraded, but only by dispatching
on a `trace_schema_version` that explicitly opts in (e.g. a
hypothetical `"2.7.legacy"` sentinel) — never as silent fallback for
unrecognized versions.

**Key:** unified Ed25519 signing key, shared between the audit service
and accord_metrics traces. Agent registers its public key with the
lens at startup (POST `<endpoint>/accord/agents/register`); the lens
caches `signature_key_id → public_key` for verification.

**Verification on the lens side:**

1. Look up the public key by `signature_key_id`.
2. Reconstruct `canonical` from the received CompleteTrace using the
   shape that matches `trace_schema_version` (table above).
3. JCS-canonicalize the reconstructed `canonical` (RFC 8785, via
   `ciris_verify_core::jcs`) to obtain `canonical_bytes` — the same
   canonicalizer the producer used (2.9.6+); never `json.dumps`.
4. `ed25519_verify(public_key, canonical_bytes, signature)`.
5. Reject the trace on signature mismatch.

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

**Residual: `agent_id_hash` collision-resistance is 8 bytes.** The
16-hex-character truncation gives 64 bits of pre-image resistance —
~2⁶⁴ work to grind a targeted collision against a specific victim's
hash, ~2³² work for a birthday collision against any pair in the
population. For non-adversarial federation scale (target: ≤4B agents,
the birthday bound) this is generous. An attacker willing to spend
2⁶⁴ SHA-256 ops to deliberately collide a victim's hash for targeted
DOS against the dedup tuple is the residual — same trade-off PoB §3.2
made for Reticulum addressing. Persistence threat models should
explicitly note this residual under the AV-9 closure (acceptable for
anti-DOS at federation scale; not a confidentiality boundary).

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

This example is a wakeup `ACCEPT_INCOMPLETENESS` thought from agent
Datum on the mock-LLM deterministic path, at trace_level=generic and
trace_format v2.8.0. Because it is a mock run, `run_kind` is `mock`,
and the trace is sealed and signed but kept local-only (§3.2.1). Every
`data` key shown is GENERIC (§7.2). `attempt_index` is injected by
lens-core (§6). The `events[]` array inside the batch envelope contains
exactly one entry:

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
    "trace_schema_version": "3.0.0",
    "deployment_profile": {
      "agent_role": "datum", "agent_template": "datum",
      "deployment_domain": "general", "deployment_type": "production",
      "deployment_region": null, "deployment_trust_mode": "sovereign",
      "run_kind": "mock", "trace_format_version": "2.8.0",
      "pipeline_metadata": { "agent_version": "2.15.0-stable", "accord_version": "1.2-Beta",
                             "identity_hash": "<sha256 hex>", "pdma_version": null,
                             "dsdma_domain_registry_version": null },
      "calibration_version": "crc-v2"
    },
    "components": [
      { "component_type": "observation", "event_type": "THOUGHT_START", "timestamp": "...:53.123Z",
        "data": { "thought_type": "standard", "round_number": 0,
                  "thought_depth": 0, "task_priority": 5,
                  "updated_info_available": false, "attempt_index": 0 } },
      { "component_type": "context", "event_type": "SNAPSHOT_AND_CONTEXT", "timestamp": "...:53.456Z",
        "data": { "agent_name": "Datum", "cognitive_state": "wakeup",
                  "attestation_level": 3, "attestation_status": "verified",
                  "binary_ok": true, "env_ok": true, "hardware_backed": true,
                  "memory_count": 0, "attempt_index": 0 } },

      /* ~3 LLM_CALL components fire here for the parallel DMA panel: */
      { "component_type": "llm_call", "event_type": "LLM_CALL", "timestamp": "...:54.012Z",
        "data": { "handler_name": "CSDMA", "service_name": "MockLLMService",
                  "duration_ms": 850.0, "status": "ok",
                  "prompt_tokens": 4200, "completion_tokens": 380,
                  "prompt_bytes": 18400, "completion_bytes": 1750,
                  "attempt_count": 1, "retry_count": 0,
                  "parent_event_type": "DMA_RESULTS", "parent_attempt_index": 0,
                  "attempt_index": 0 } },
      { "component_type": "llm_call", "event_type": "LLM_CALL", "timestamp": "...:54.045Z",
        "data": { "handler_name": "DSDMA", "service_name": "MockLLMService",
                  "duration_ms": 920.0, "status": "ok",
                  "prompt_tokens": 4250, "completion_tokens": 410,
                  "parent_event_type": "DMA_RESULTS", "parent_attempt_index": 0,
                  "attempt_index": 1 } },
      { "component_type": "llm_call", "event_type": "LLM_CALL", "timestamp": "...:54.078Z",
        "data": { "handler_name": "EthicalPDMA", "service_name": "MockLLMService",
                  "duration_ms": 1010.0, "status": "ok",
                  "prompt_tokens": 5100, "completion_tokens": 290,
                  "parent_event_type": "DMA_RESULTS", "parent_attempt_index": 0,
                  "attempt_index": 2 } },

      { "component_type": "rationale", "event_type": "DMA_RESULTS", "timestamp": "...:55.012Z",
        "data": { "csdma": { "plausibility_score": 1.00 },
                  "dsdma": { "domain_alignment": 1.00 },
                  "csdma_plausibility_score": 1.00, "dsdma_domain_alignment": 1.00,
                  "attempt_index": 0 } },

      { "component_type": "llm_call", "event_type": "LLM_CALL", "timestamp": "...:55.234Z",
        "data": { "handler_name": "IDMA", "service_name": "MockLLMService",
                  "duration_ms": 750.0, "status": "ok",
                  "parent_event_type": "IDMA_RESULT", "parent_attempt_index": 0,
                  "attempt_index": 3 } },

      { "component_type": "rationale", "event_type": "IDMA_RESULT", "timestamp": "...:56.012Z",
        "data": { "k_eff": 3.0, "fragility_flag": false, "phase": "healthy",
                  "attempt_index": 0 } },

      { "component_type": "llm_call", "event_type": "LLM_CALL", "timestamp": "...:56.512Z",
        "data": { "handler_name": "ASPDMA", "service_name": "MockLLMService",
                  "duration_ms": 1200.0, "status": "ok",
                  "response_model": "ASPDMALLMResult",
                  "parent_event_type": "ASPDMA_RESULT", "parent_attempt_index": 0,
                  "attempt_index": 4 } },

      /* First conscience pass — passes, no override */
      { "component_type": "rationale", "event_type": "ASPDMA_RESULT", "timestamp": "...:57.789Z",
        "data": { "selected_action": "speak", "is_recursive": false,
                  "selection_confidence": 0.85, "attempt_index": 0 } },
      { "component_type": "conscience", "event_type": "CONSCIENCE_RESULT", "timestamp": "...:58.234Z",
        "data": { "conscience_passed": true, "action_was_overridden": false,
                  "is_recursive": false,
                  "entropy_passed": true, "entropy_score": 0.25,
                  "coherence_passed": true, "coherence_score": 0.95,
                  "optimization_veto_passed": true,
                  "epistemic_humility_passed": true, "epistemic_humility_certainty": 0.90,
                  "thought_depth_current": 0, "thought_depth_max": 5,
                  "entropy_level": 0.25, "coherence_level": 0.95, "attempt_index": 0 } },

      /* Trace seals here */
      { "component_type": "action", "event_type": "ACTION_RESULT", "timestamp": "...:12.789Z",
        "data": { "action_executed": "speak",
                  "execution_success": true, "execution_time_ms": 36.0,
                  "audit_sequence_number": 42, "audit_entry_hash": "abcd...",
                  "tokens_total": 28000, "tokens_input": 24000, "tokens_output": 4000,
                  "llm_calls": 5, "cost_cents": 0.012,
                  "attempt_index": 0 } }
    ],
    "signature": "base64(...)",
    "signature_key_id": "ciris-agent-key:7c3f8e2b..."
  }
}
```

The same thought under v2.7.0 (the default) has the same components.
Its `deployment_profile` has only the first six members, and
`deployment_type` is `"mock"` (the run-kind marker, §3.2.1).

## 12. Validation contract for the lens

The lens / admitter MUST:

1. **Verify the Ed25519 signature** before persisting any component
   (§8). Rebuild the canonical from the `deployment_profile` exactly as
   received, with every member.
2. **Honor the action anchor** — only `complete_trace` envelopes
   represent committed history; loose events without `complete_trace`
   wrappers should be treated as in-flight observations and not
   persisted as durable rows.
3. **Preserve per-attempt rows** — multiple `ASPDMA_RESULT`,
   `CONSCIENCE_RESULT`, `LLM_CALL` events for the same `thought_id`
   are intentional. Use `(thought_id, event_type, attempt_index)` as
   the dedup key, not `(thought_id, event_type)`.
4. **Treat `verb_specific_data` as authoritative per-verb payload.**
   The lens may project per-verb columns at write time (e.g. extract
   `rights_basis` for DEFER). At v2.8.0 the object is closed and
   bounded (§5.7.1). The lens must not reject a known-shape event only
   because its `verb` value is new to the lens, since `verb` is a
   token, not a schema enum.
5. **Respect `trace_level`** — content-bearing fields (`prompt`,
   `response_text`, reasoning text) are absent at lower levels by
   design, not by accident. Fail-open queries that group by
   `trace_level` so dashboards don't claim "no reasoning data" when
   the agent is at `generic` for legitimate privacy reasons.
6. **Dispatch on two separate version keys.**
   - `trace_schema_version` selects the canonicalizer and canonical
     shape (§8). It is `"3.0.0"` today.
   - `deployment_profile.trace_format_version` selects the format
     contract. It is absent for v2.7.x and `"2.8.0"` for this spec.

   The lens should advertise the formats it admits. It should refuse an
   unknown or unvendored format by name rather than guess. Persist's
   token for this is `schema_unsupported_version`, or HTTP 422 naming
   the version gap on the HTTP surface.
7. **Validate a v2.8.0 trace against the pinned artifact.** That is
   `trace_format_v2_8_0.json` at the SHA-256 in `schemas/SCHEMA_SHA256`
   (the Constitution pins it; header of this document). Use the per-level
   views (§7.1) selected by the envelope's `trace_level`.
   **Refuse, never truncate.** A non-conformant trace is refused whole.
8. **Treat the run kind as follows.** Read `deployment_profile.run_kind`
   only on v2.8.0 traces (§3.2.1).
   - `production`, `prod-personal` and `prod-managed` are admitted
     alike.
   - `qa` and `battery` are admitted and labelled.
   - A federation-tier admitter refuses `mock`.
   - On 2.7.x rows, never infer a run kind from `deployment_type`.
9. **Keep provenance distinct.** `deployment_profile.pipeline_metadata`
   is agent-signed provenance. Do not merge it with, or overwrite it
   by, the admitter's own post-ingest pipeline metadata (§3.2).

**Admitter refusal tokens** (Persist-side; the agent never emits them):

| Token | Refused trace |
|---|---|
| `trace_field_shape_violation` | v2.8.0 trace that fails the artifact (unexpected field, wrong type, pattern, bound, field above its level) |
| `trace_run_kind_mock` | `run_kind` is `mock`, at federation tier |
| `schema_unsupported_version` | a trace format the admitter does not admit. Persist v54.1 and earlier return it for every v2.8.0 trace. |

## 13. Open issues / forward compat

- **Persist must admit v2.8.0** (CIRISPersist#1089). Persist has
  confirmed `deployment_profile.trace_format_version` as the gate member
  and will read `deployment_profile.run_kind`. Until a release with the
  following ships and is deployed, emission stays v2.7.0:
  - It must admit the new members as **typed signed fields**, gated on
    `trace_format_version == "2.8.0"` and never dropped silently.
    Persist's `DeploymentProfile` is a closed six-field struct today. A
    v2.8.0 profile parsed into it loses four members, so its signature
    fails to verify.
  - It must validate against the vendored artifact. Persist's ack cites
    the earlier hash `8c51028c…`. The artifact has since changed, so
    `prod-personal` / `prod-managed` were added and the pin is now
    `b6f6fd3f…`. Persist must vendor the current pin.
- **`attempt_index` (resolved in the artifact).** lens-core injects
  `attempt_index` into every component's `data` (§6). Every closed
  `EventData_*` now declares it (integer, GENERIC); before that, a
  validator applying the artifact to a sealed trace would have refused
  every trace. `test_a_sealed_trace_with_attempt_index_validates` pins
  it against the post-injection shape.
- **Unsourced members.**
  - `pipeline_metadata.pdma_version` and
    `.dsdma_domain_registry_version` are declared for #878 but have no
    source, so they are always `null`.
  - `SNAPSHOT_AND_CONTEXT.disclosure_version` is `null`, and so absent
    on the wire, until CIRISVerify publishes a disclosure version
    (#832).
  - `calibration_version` is `null` on a substrate that exposes no
    `AXIS_CALIBRATION_VERSION`.
- **Region on managed deployments.** CIRISManager sets `CIRIS_MANAGED`
  and `CIRIS_TEMPLATE` but not `CIRIS_ACCORD_METRICS_DEPLOYMENT_REGION`.
  Managed agents emit `deployment_region: null` until Manager sets it or
  the operator configures one (#878).
- **Deferred by user ruling.** `cohort_target_id` and `classifications`
  (#878) are not part of v2.8.0.
- **Harness coverage.** Whether every harness declares a run kind is
  tracked in #1268 (the launch-flag backstop, §3.2.1 step 3, and the
  launcher lint). Harnesses pinned to agents older than v2.15.0 cannot
  mark runs at all.
- **TSASPDMA_RESULT** is deprecated but still emitted, and still in the
  v2.8.0 artifact. Drop dual-emit handling once the lens stops reading
  it.
- **`trace_events` + `trace_llm_calls` schema bump** per
  FSD §8 — adds the per-attempt and per-LLM-call shapes natively.
- **Loose event envelopes** (non-`complete_trace`) are not used today
  but the wire format reserves them. If the lens grows a live-streaming
  pane in the future, switch from `complete_trace` to per-event
  shipping by changing `_complete_trace` in the agent adapter; no
  schema-level changes required.

## 14. Changes from v2.7.0

| Area | v2.7.0 | v2.8.0 |
|---|---|---|
| Format identity | none on the wire | `deployment_profile.trace_format_version` = `"2.8.0"` (signed, required) |
| `trace_schema_version` | `"3.0.0"` on the wire (artifact const `"2.7.0"` is stale) | const `"3.0.0"`, unchanged: canonicalization epoch only |
| `deployment_profile` | 6 members, unbounded strings, open | 10 members, all required, closed, every member level `generic` with kind / pattern / `maxLength` (§3.2) |
| Run kind | marker overrides `deployment_type` (`mock`/`qa`/`battery`) on non-production runs | `run_kind` member on every run: `production \| prod-personal \| prod-managed \| qa \| battery \| mock` (§3.2.1) |
| `deployment_type` | operator value or run-kind marker | operator value only (label, 128) |
| `agent_template` source | config, else `-default-unspecified` | config, else `CIRIS_TEMPLATE`, else `-default-unspecified` |
| `deployment_region` source | config, else `null` | config, else `CIRIS_ACCORD_METRICS_DEPLOYMENT_REGION`, else `null` |
| Operator `run_kind` config | not read | read (step 4 of §3.2.1) |
| Provenance | none | `pipeline_metadata` (5 members), `calibration_version` |
| `SNAPSHOT_AND_CONTEXT` | — | adds `disclosure_version` (GENERIC, token 64, nullable) |
| `data.attempt_index` | injected by lens-core, not in the artifact | declared on every `EventData_*` (integer, GENERIC) |
| `correlation_metadata` copies | marker in `deployment_type`; config region/template | operator `deployment_type`; region/template mirror the signed profile |
| Component `data` | per-level bounds (the enforcer loads the v2.8.0 artifact for both versions); v2.7.0 artifact has none | same bounds, now published: `level`, `x-ciris-kind`, patterns, bounds, `EventData_<EVENT>__<level>` views, `BoundedJson` (§7) |
| `components` | artifact `maxItems` 6 | artifact `maxItems` 64 |
| `event_type` closure | 10 values | 15-variant `ReasoningEventType` (§4) |
| Admitter | Persist ≤ v54.1 admits | Persist ≤ v54.1 refuses whole (`schema_unsupported_version`); needs CIRISPersist#1089 |

---

**Source-of-truth files** (cite these in any divergence dispute):

- `ciris_adapters/ciris_accord_metrics/schemas/trace_format_v2_8_0.json` + `schemas/SCHEMA_SHA256` — the v2.8.0 contract and its pin
- `ciris_adapters/ciris_accord_metrics/schemas/trace_format_v2_7_0.json` — the legacy contract
- `ciris_adapters/ciris_accord_metrics/egress_schema.py` — filter before sign (loads the artifact)
- `ciris_engine/logic/utils/mock_llm_guard.py` — `TraceRunKind`, `trace_run_kind`, `wire_run_kind`
- `ciris_engine/schemas/services/runtime_control.py` — every event class
- `ciris_engine/schemas/streaming/reasoning_stream.py` — dispatcher + union
- `ciris_adapters/ciris_accord_metrics/services.py` — component builder, `deployment_profile` builder, LensClient wiring
- `ciris_engine/logic/buses/llm_bus.py` — LLM_CALL emission
- `ciris_engine/logic/processors/core/thought_processor/main.py` — VERB_SECOND_PASS_RESULT emission
- `tests/ciris_adapters/ciris_accord_metrics/test_trace_format_v2_8_0.py` — artifact parity, pin and emission tests
- `tests/ciris_adapters/ciris_accord_metrics/test_run_kind_marker.py` — run-kind marker tests
- `tests/ciris_engine/schemas/streaming/test_reasoning_stream_new_events.py` — schema regression suite
- `tests/adapters/accord_metrics/test_attempt_index_and_new_events.py` — attempt_index + new-event regression suite
