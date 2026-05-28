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

- **No `accountability:*` named-axis wire-form emission**: Substrate-specced via the audit-chain primitives `audit_chain:hash_continuity`, `audit_chain:merkle_inclusion`, `audit_chain:tree_head_signed` (FSD-002 §3.3 — `system:*` reserved substrate-self-reports) + `transparency_log:inclusion`, `transparency_log:consistency` (FSD-002 §3.2 — Verify §4 RFC 6962). Accountability decomposes onto these substrate-attested primitives rather than a single `accountability:*` prefix; per FSD-002 §2.4 layering principle, a per-action accountability claim writes a `scores` attestation pointing back to the audit-chain prefix. **Substrate primitives cover the structural surface; named-axis emission is a UX layer above the wire.**
- **`accountability:human_in_control` HITL/HOTL/HOOTL gradient (ASEAN-distinctive)**: Substrate-specced via the `vote:{contribution_id}` primitive (FSD-002 §3.6.3 NodeCore §2 P4 — signed score on a Contribution; Weight = Credits × expertise multiplier) + the `deferral_request` / `deferral_response` Contribution pair (`CIRISNodeCore/FSD/MESSAGE_TAXONOMY.md §4.7-§4.8`). HITL = synchronous vote; HOTL = asynchronous vote; HOOTL = no vote. Mode is structurally inferred from the vote-timing of the Contribution, not from a separate mode-enum. Agent emits the vote-request envelope; the gradient is composition-derived.
- **`accountability:lifecycle_responsibility` (EU §1.7)**: Substrate-specced via `commitment_fulfillment:{prior_contribution_id}` (FSD-002 §3.6.4 — APPROACH_PRIMITIVE `commits` field, track-record of follow-through on prior approach/method commit) PLUS Stage 9 Archive (`CIRISNodeCore/FSD/CONTRIBUTION_LIFECYCLE.md §11`) — the lifecycle is structurally captured by the chain-row sequence rooted into Merkle batches. The full lifecycle binds to accountability via walking the chain.
- **`accountability:rights_based_legal` (IEEE Ch11)**: Substrate-specced via `testimonial_witness:{kind}` preservation primitives (FSD-002 §3.6.3 v1.4 addition — `harmed_party`, `displaced_worker`, etc.) PLUS the lexical-vulnerability-priority reference policy (FSD-002 §6.1.4 v1.3 addition). UDHR-grounded rights basis composes via scalar attestations on the rights-instrument prefix once Contribution envelope ships.
- **Originator-creation bidirectional obligations (Accord §IV Ch 2, MH functional analogue)**: Substrate-specced via the trust-graph primitives (`trust_grant`, `registry_vouch` in MESSAGE_TAXONOMY §4.14, §4.13) + the `commitment` Contribution kind (MESSAGE_TAXONOMY.md §4.26 Commissive / Bilateral or Broadcast / Open; high-stakes witness-gated). Originator-side obligations register via Commissive commitment; receiver-side obligations register via `trust_grant`. Bidirectional composition runs consumer-side.
- **Likely to become STRONG-4 when oversight-ladder regulatory batches map** — promoting `accountability:*` to a named axis in CIRIS Agent is contingent on the seed graduating it.
<!-- END HUMAN -->
