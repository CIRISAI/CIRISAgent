# D23 — `accountability:*` (STRONG-3)

> Named accountability as primary axis (not just structural composition)

**Seed reference**: `SEED_DIMENSIONS.yaml` v1.0, dimension `D23` ([source](https://github.com/CIRISAI/ciris-response-magnifica-humanitas/blob/main/SEED_DIMENSIONS.yaml))
**Accord principle**: fidelity
**Attestation density**: MH=0 · EU=6 · IEEE=3 · ASEAN=19 · total=28

**Absent from**: MH — MH covers accountability FUNCTIONALLY via integrity:* + originator-obligations Accord §IV Ch 2 — architecturally structural rather than named-axis-attested.
  *Functional analogue*: integrity:* + the Accord §IV Ch 2 bidirectional creator-creation obligations

## Regulatory attestations

*(Auto-rendered from seed; do not hand-edit. Re-run `python tools/compliance/generate_ciris_compliance_stubs.py tools/compliance/SEED_DIMENSIONS.yaml compliance/` after seed updates.)*

- **EU** (Ethics Guidelines for Trustworthy AI) — *§1.7 Accountability*
    > "lifecycle accountability with redress mechanisms"
    Wire form: `accountability:lifecycle_responsibility`
- **IEEE** (Ethically Aligned Design, First Edition) — *Ch2 P6 + Ch11*
    > "accountability principle; rights-based legal accountability"
    Wire form: `accountability:*`
- **ASEAN** (ASEAN Guide on AI Governance and Ethics) — *§B.6 + §C.2 (19 attestations)*
    > "accountability and integrity; human-in-control over AI-augmented decisions"
    Wire form: `accountability:human_in_control + accountability:lifecycle`

## Wire primitives

- `accountability:{axis}`
- `accountability:human_in_control (ASEAN-distinctive — HITL/HOTL/HOOTL)`

## Convergence note

ASEAN's accountability:human_in_control with HITL/HOTL/HOOTL gradient is currently single-source; likely to become STRONG when other oversight-ladder regulatory batches map.

---

<!-- BEGIN HUMAN -->
## What this dimension covers

Accountability asks: who is responsible for the agent's actions, and can that responsibility be verified after the fact? An auditor wants a tamper-evident answer to "who decided this, on what basis, and can you prove the record hasn't been altered?"

## How CIRIS implements this today

CIRIS takes a different approach to accountability than naming it as a single axis: instead of declaring an `accountability:*` label on each action, the accountability properties are built into the substrate — the agent's identity is keyed with Ed25519 cryptography, every action emits an audit entry on a tamper-evident chain, every decision carries a written rationale, and every escalation to a Wise Authority (a human or panel the agent defers to) is recorded with the human's signed response. The same goal — verifiable responsibility — is achieved structurally.

**Authentication Service (the cryptographic root of identity).**
- `ciris_engine/logic/services/infrastructure/authentication/` — Ed25519-keyed agent identity
- `ciris_engine/schemas/api/auth.py:63` — `RESOLVE_DEFERRALS` permission (the Wise Authority axis)

**Audit Service (the lifecycle record).** Event types are locked at the database level — adding a new type requires a schema migration, not a configuration change.
- `ciris_engine/logic/services/graph/audit_service/service.py:59` — `AuditEventData`, `AuditQuery`, `VerificationReport`
- `ciris_engine/logic/services/graph/audit_service/service.py:74-100` — `AuditEventType` enforcement (CHECK constraint, V018/V020 migrations) — 21 locked event types
- `ciris_engine/schemas/audit/core.py` — `AuditEventType` enum (the immutable accountability vocabulary)

**Wise Authority (the human-in-control surface that ASEAN names as HITL/HOTL/HOOTL).**
- `ciris_engine/logic/services/governance/wise_authority/service.py:42` — `WiseAuthorityService`
- `ciris_engine/logic/handlers/control/defer_handler.py` — DEFER (escalate to a Wise Authority) routes the thought to a human
- `ciris_engine/logic/handlers/control/reject_handler.py:18` — REJECT records refusal with a written reason

**Conscience layer (the stop-button surface).** Internal safety checks running on each thought can veto an action mid-pipeline; the optimization-veto check is the "stop-button at any time" surface called for in EU §III.1.
- `ciris_engine/logic/conscience/core.py` — `OptimizationVetoConscience`
- `ciris_engine/logic/conscience/action_sequence_conscience.py` — sequence-level checks

**Audit chain API (the verification surface).**
- `ciris_engine/logic/adapters/api/routes/audit.py:781` — `GET /v1/audit/entries`
- `:919` — `GET /v1/audit/entries/{entry_id}`
- `:970` — `POST /v1/audit/search`
- `:1006` — `POST /v1/audit/verify/{entry_id}` — Ed25519 chain verification (the cryptographic verification surface)
- `:1030` — `POST /v1/audit/export`

**Originator obligations (the developer-side commitment).**
- `MISSION.md` — the Mission Driven Development charter; every claim is anchored to a file path
- `ciris_engine/logic/buses/prohibitions.py` — the originator's declaration of what the agent will not be

**Auditable reasoning (the per-decision rationale).** Every action-selection result carries a written rationale, required by schema.
- `ciris_engine/schemas/dma/results.py:242` — `rationale: str` (required field)
- `ciris_engine/schemas/dma/results.py:248` — `reasoning: Optional[str]` (detailed reasoning)

**Policy text.**
- `ciris_engine/data/accord_1.2b.txt:108` — "Integrity: Act Ethically — apply a transparent, auditable reasoning process"
- `ciris_engine/data/accord_1.2b.txt:125` — "Accountability: Maintain tamper-evident logs, rationale chains, and documentation"
- `ciris_engine/data/accord_1.2b.txt:294` — Deferral Package (context, dilemma, analysis, rationale) — the formal escalation artifact
- `ciris_engine/data/accord_1.2b.txt:488` — Transparent Accountability: logs, rationales, and WBD tickets to authorized auditors

**Tests.**
- `tests/ciris_engine/logic/handlers/control/test_defer_handler.py`, `test_reject_handler.py`
- Audit service tests under `tests/`

**Configuration.**
- `AuditEventType` enum (21 values) — locks the accountability vocabulary at the persistence layer
- Wise Authority registration in `service_initializer.py:704, 2050` — declares which endpoints carry the `RESOLVE_DEFERRALS` permission

Proposed pointer (from seed): `(none specified in seed; please fill)`

## How you can tell it's working (observability)

If you wanted to verify this from outside, the audit chain itself is cryptographically signed and externally verifiable, every action's rationale is stored alongside the action, and every Wise Authority resolution names the human (by Ed25519 public-key hash) who made the call.

- **Tamper-evident audit chain**: every action emits an audit entry; `POST /v1/audit/verify/{entry_id}` performs Ed25519 chain verification end-to-end.
- **Per-action accountability slice**: `GET /v1/audit/search` with an action-type filter returns the full chronological trail.
- **Signed rationale chains** (Accord 1.2b §1006): every action-selection emission carries `rationale` and `reasoning` as audit-anchored fields.
- **Wise Authority resolution telemetry**: deferral resolutions are logged with the Wise Authority's identity (Ed25519 public-key hash).
- **Drift detectors**: `detection:correlated_action:*` flags audit-chain anomalies.
- **Federation evidence_refs**: a typed federation message citing `dimensions: ["D23"]` resolves through this seed to EU §1.7 lifecycle accountability, IEEE Ch2 P6 + Ch11 rights-based accountability, ASEAN §B.6 + §C.2 (the 19-attestation human-in-control density).

Proposed pointer (from seed): `(none specified in seed; please fill)`

## Current limitations & next steps

- **Typed `accountability:*` envelope as a named axis**: shared work with the upstream CIRIS substrate. Accountability is decomposed into substrate-attested primitives (`audit_chain:hash_continuity`, `audit_chain:merkle_inclusion`, `audit_chain:tree_head_signed` in FSD-002 §3.3; `transparency_log:inclusion`, `transparency_log:consistency` in FSD-002 §3.2 per RFC 6962). A per-action accountability claim writes a `scores` attestation pointing back to the audit-chain prefix. Substrate primitives cover the structural surface; the named-axis emission is a presentation layer above the wire.
- **ASEAN human-in-control gradient (HITL / HOTL / HOOTL)**: shared work with the upstream substrate (`vote:{contribution_id}` in FSD-002 §3.6.3 NodeCore P4; `deferral_request` / `deferral_response` in `MESSAGE_TAXONOMY.md §4.7-§4.8`). The mode is structurally inferred from the vote timing (synchronous = HITL, asynchronous = HOTL, no vote = HOOTL) rather than declared as a separate enum. The agent emits the request envelope; the gradient falls out compositionally.
- **EU §1.7 lifecycle accountability**: shared work with the upstream substrate (`commitment_fulfillment:{prior_contribution_id}` in FSD-002 §3.6.4; Stage 9 Archive in `CIRISNodeCore/FSD/CONTRIBUTION_LIFECYCLE.md §11`). The lifecycle is captured by the chain-row sequence rooted into Merkle batches.
- **IEEE Ch11 rights-based accountability**: shared work with the upstream substrate (`testimonial_witness:{kind}` in FSD-002 §3.6.3 v1.4; lexical-vulnerability-priority reference policy in FSD-002 §6.1.4 v1.3). UDHR-grounded rights basis composes via scalar attestations once the envelope ships.
- **MH bidirectional originator obligations (Accord §IV Ch 2)**: shared work with the upstream substrate (`trust_grant`, `registry_vouch` in `MESSAGE_TAXONOMY.md §4.14, §4.13`; `commitment` in §4.26). Originator-side obligations register via a Commissive commitment; receiver-side via `trust_grant`. Bidirectional composition runs at the consumer side.
- **Promotion to a named axis** is likely as more oversight-ladder regulatory batches map — this is contingent on the seed graduating accountability to a primary axis.

## Tracked requirements

- **Umbrella(s)**: `CIRISAgent#803` — Typed `<dimension>:*` wire envelope emission
- **Substrate spec(s)**: `CIRISRegistry#27` — oversight_mode HITL/HOTL/HOOTL envelope field

See `compliance/README.md` cross-cutting findings table for the 3.0 requirements finalization context.
<!-- END HUMAN -->
