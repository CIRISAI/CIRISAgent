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
## CIRIS-side compliance implementation

`accountability:*` (as primary axis) is currently embedded structurally in CIRIS rather than declared as a named axis. The MH absent_batch noted this pattern: MH covers accountability functionally via integrity:* + originator-obligations rather than naming it. CIRIS sits in the same posture — accountability runs through the audit chain, the WA escalation path, and the Authentication Service rather than as a labeled `accountability:*` Contribution.

- **Code references** — Authentication Service (accountability:agent_identity):
    - `ciris_engine/logic/services/infrastructure/authentication/` — Ed25519-keyed agent identity, the cryptographic root of accountability
    - `ciris_engine/schemas/api/auth.py:63` — `RESOLVE_DEFERRALS` permission (the WA-authority axis)
- **Code references** — Audit Service (accountability:lifecycle):
    - `ciris_engine/logic/services/graph/audit_service/service.py:59` — `AuditEventData`, `AuditQuery`, `VerificationReport`
    - `ciris_engine/logic/services/graph/audit_service/service.py:74-100` — `AuditEventType` enforcement (CHECK constraint, V018/V020 migrations) — 21 locked event types
    - `ciris_engine/schemas/audit/core.py` — `AuditEventType` enum (the immutable lifecycle-accountability vocabulary)
- **Code references** — Wise Authority (accountability:human_in_control, the ASEAN HITL/HOTL/HOOTL surface):
    - `ciris_engine/logic/services/governance/wise_authority/service.py:42` — WiseAuthorityService
    - `ciris_engine/logic/handlers/control/defer_handler.py` — DEFER routes thoughts requiring human accountability to WA
    - `ciris_engine/logic/handlers/control/reject_handler.py:18` — REJECT records refusal with reason for accountability
- **Code references** — Conscience layer (accountability:optimization_veto):
    - `ciris_engine/logic/conscience/core.py` — `OptimizationVetoConscience`; the "stop-button at any time" surface (EU §III.1) that breaks the accountability chain back to human review
    - `ciris_engine/logic/conscience/action_sequence_conscience.py` — sequence-level accountability checks
- **Code references** — Audit chain (accountability:tamper_evident_log):
    - `ciris_engine/logic/adapters/api/routes/audit.py:781` — `GET /v1/audit/entries`
    - `:919` — `GET /v1/audit/entries/{entry_id}`
    - `:970` — `POST /v1/audit/search`
    - `:1006` — `POST /v1/audit/verify/{entry_id}` — Ed25519 chain verification (the cryptographic accountability surface)
    - `:1030` — `POST /v1/audit/export`
- **Code references** — Originator obligations (Accord §IV Ch 2, the MH functional analogue):
    - `MISSION.md` — declared mission-driven-development charter; every claim anchored to a file path
    - `ciris_engine/logic/buses/prohibitions.py` — the originator's accountability declaration of what the agent will not be
- **Code references** — DMA rationale chain (accountability:auditable_reasoning):
    - `ciris_engine/schemas/dma/results.py:242` — `rationale: str` REQUIRED field on every ActionSelectionDMAResult
    - `ciris_engine/schemas/dma/results.py:248` — `reasoning: Optional[str]` detailed reasoning process
- **Policy text**:
    - `ciris_engine/data/accord_1.2b.txt:108` — "Integrity: Act Ethically—apply a transparent, auditable reasoning process"
    - `ciris_engine/data/accord_1.2b.txt:125` — "Accountability: Maintain tamper-evident logs, rationale chains, and documentation"
    - `ciris_engine/data/accord_1.2b.txt:294` — Deferral Package (context, dilemma, analysis, rationale) — the formal escalation accountability artifact
    - `ciris_engine/data/accord_1.2b.txt:488` — Transparent Accountability: logs, PDMA rationales, WBD tickets to authorised auditors
- **Test coverage**:
    - `tests/ciris_engine/logic/handlers/control/test_defer_handler.py`, `test_reject_handler.py`
    - Audit service tests under `tests/`
- **Configuration surface**:
    - `AuditEventType` enum (21 values) — locks the accountability vocabulary at the persistence layer
    - WA registration in `service_initializer.py:704, 2050` — declares which WA endpoints carry resolve_deferral permission

Proposed pointer (from seed): `(none specified in seed; please fill)`

## Observability hooks

- **Tamper-evident audit chain**: every action emits an audit entry; `POST /v1/audit/verify/{entry_id}` performs Ed25519 chain verification.
- **Per-action accountability slice**: `GET /v1/audit/search` with action_type filter returns the full chronological accountability trail.
- **Cryptographically-signed rationale chains** (Accord 1.2b §1006): every PDMA emission carries `rationale` + `reasoning` as audit-anchored fields.
- **WA-resolution telemetry**: deferral resolutions are logged with the WA identity (Ed25519 pubkey hash) for human-in-control accountability.
- **LensCore F-3 detectors**: `detection:correlated_action:*` flags accountability-chain anomalies.
- **Federation evidence_refs**: a Contribution citing `dimensions: ["D23"]` resolves through this seed to EU §1.7 lifecycle accountability, IEEE Ch2 P6 + Ch11 rights-based accountability, ASEAN §B.6 + §C.2 (the 19-attestation human_in_control density).

Proposed pointer (from seed): `(none specified in seed; please fill)`

## Known gaps / not-yet-implemented

- **No `accountability:*` named-axis wire-form emission**: CIRIS treats accountability as a structural property of the audit chain, conscience, and WA escalation rather than as a named Contribution axis. MH posture; not ASEAN posture.
- **`accountability:human_in_control` HITL/HOTL/HOOTL gradient (ASEAN-distinctive)**: CIRIS implements HITL (PONDER + DEFER hold actions for human review) and HOTL (asynchronous WA review post-action) but does not explicitly tag which mode is active per thought.
- **`accountability:lifecycle_responsibility` (EU §1.7)**: the lifecycle is implemented (initialization → wakeup → work → shutdown) but no single envelope binds lifecycle-stage to accountability-attestation.
- **`accountability:rights_based_legal` (IEEE Ch11)**: the structural shape exists (UDHR-grounded rights basis in `deferral_taxonomy.py:317`) but no explicit rights-based-legal accountability envelope.
- **Originator-creation bidirectional obligations (Accord §IV Ch 2, MH functional analogue)**: enforced via MISSION.md + prohibitions.py but not surfaced as a wire-form Contribution.
- **Likely to become STRONG-4 when oversight-ladder regulatory batches map** — promoting `accountability:*` to a named axis in CIRIS Agent is contingent on the seed graduating it.
<!-- END HUMAN -->
