# D09 — `fidelity:*` (STRONG-4)

> Faithful disclosure / faithful representation across lifecycle

**Seed reference**: `SEED_DIMENSIONS.yaml` v1.0, dimension `D09` ([source](https://github.com/CIRISAI/ciris-response-magnifica-humanitas/blob/main/SEED_DIMENSIONS.yaml))
**Accord principle**: fidelity
**Attestation density**: MH=8 · EU=15 · IEEE=16 · ASEAN=26 · total=65

## Regulatory attestations

*(Auto-rendered from seed; do not hand-edit. Re-run `python tools/compliance/generate_ciris_compliance_stubs.py tools/compliance/SEED_DIMENSIONS.yaml compliance/` after seed updates.)*

- **MH** (Magnifica Humanitas (On Safeguarding the Human Person in the Time of Artificial Intelligence)) — *§17*
    > "fidelity to the Gospel through doctrinal development"
    Wire form: `fidelity:epistemic_grounding`
- **EU** (Ethics Guidelines for Trustworthy AI) — *§1.7 Accountability*
    > "lifecycle responsibility; fidelity to declared purpose"
    Wire form: `fidelity:lifecycle_application`
- **IEEE** (Ethically Aligned Design, First Edition) — *Ch11*
    > "duty-bearer obligation to fulfill rights as fidelity"
    Wire form: `fidelity:duty_bearer_obligation_to_fulfill_rights`
- **ASEAN** (ASEAN Guide on AI Governance and Ethics) — *§C.4 + §B.1 (26 attestations, densest)*
    > "algorithmic disclosure; human oversight as faithful representation"
    Wire form: `fidelity:algorithmic_disclosure + fidelity:explainability + fidelity:human_oversight_governance`

## Wire primitives

- `fidelity:*`

## Convergence note

ASEAN's fidelity-saturation is deployer-side framing (faithful disclosure to users/operators); MH's is doctrinal-epistemic. Same prefix admits both shapes.

---

<!-- BEGIN HUMAN -->
## What this dimension covers

Fidelity is honesty across the lifecycle — being truthful about what the agent is, what it's doing, why, and on whose authority. All four traditions we track (65 attestations; ASEAN saturates here at 26) name some version: doctrinal continuity, lifecycle responsibility, duty-bearer fulfillment, and algorithmic disclosure. CIRIS treats transparency as structural rather than aspirational — reasoning traces, cryptographic attestation, and an immutable audit ledger back every runtime claim.

## How CIRIS implements this today

Fidelity shows up in four overlapping surfaces: canonical policy text, a service that exposes every reasoning trace, a cryptographic attestation pipeline (CIRISVerify) that backs runtime claims with verifiable evidence, and an immutable audit graph signed with Ed25519.

- Policy text names the principle and its bidirectional obligations: `ciris_engine/data/localized/accord_1.2b_en.txt:109` ("Be Honest — provide truthful, comprehensible information"); operational chapter at `:239-242`; obligations to self and originators at `:469-470`; ethical-mandate fidelity at `:487` (the IEEE duty-bearer alignment); originator obligation at `:636`; the "truthful actions as immutable anchor points" framing at `:1051`; honest-escalation cheapness at `:1100`; and `ciris_engine/data/localized/CIRIS_COMPREHENSIVE_GUIDE.txt:594` ("Transparency is structural, not aspirational").
- The VisibilityService exposes reasoning traces directly. `ciris_engine/logic/services/governance/visibility/service.py:11-12` states the scope ("reasoning traces and decision history"). The API surface at `:65` includes `get_current_state`, `get_reasoning_trace`, `get_decision_history`, and `explain_action`. The full deliberation chain for any task is retrievable at `:188-196`; structured action explanations at `:368-392`.
- The cryptographic attestation pipeline (CIRISVerify) backs runtime claims with verifiable evidence. `ciris_engine/schemas/services/attestation.py:1-5` marks it as required for CIRIS 2.0+. The agent reasons with knowledge of its own attestation status: `ciris_engine/logic/context/batch_context.py:21-91` injects an attestation summary into every batch deliberation; the typed context at `:228-236, 413, 533, 865` carries the license disclosure text, severity, and attestation summary; `get_mandatory_disclosure()` at `:448-453` retrieves what the agent is obligated to surface to the user. The verifier runtime lives at `ciris_engine/logic/services/infrastructure/authentication/attestation/` (the L1-L5 ladder substrate — see D18).
- The audit graph is an immutable fidelity ledger. `ciris_engine/logic/services/graph/audit_service/service.py` persists every action via `log_event`; all safety-check and ethics-review outputs flow into signed rows. Telemetry exposes `audit_events_total` and `audit_events_by_severity` at `:1013-1014`. Audit rows use Ed25519 signatures throughout (FSD-002 v1.4 wire format).
- The ethics review step renders fidelity-of-introspection as numbers: `ciris_engine/logic/dma/prompts/pdma_ethical.yml:81` ("Alētheia-grounded: name what is, not what you wish were the case") and `:83-104` make a numerical scalar pair (`weight_alignment_score` and `ethical_alignment_score`) mandatory — the *delta* between them is the framework's correction made visible.
- The coherence safety check at `ciris_engine/logic/conscience/core.py:459` enforces fidelity-to-stated-intent: did the agent do what it said it would? The Stage-2 enrichment at `FSD/CONSCIENCE_V3.md:41` adds `alignment_score`, `context_fit_score`, and `flagged_patterns`.
- 29 localized Accord and Comprehensive Guide copies under `ciris_engine/data/localized/` ensure the agent's self-description is faithful in every supported language.
- Test coverage: `tests/test_conscience_core.py` (rationale-fidelity surface via the coherence check), `tests/ciris_engine/logic/dma/test_action_selection_pdma.py` (action-selection fidelity), and the VisibilityService suite under `tests/ciris_engine/logic/services/governance/`.

## How you can tell it's working (observability)

External auditors can pull any task's full reasoning chain, replay the immutable audit ledger, and verify that the agent's user-facing disclosures match its actual attestation state.

- The reasoning-trace endpoint `GET /v1/visibility/trace/{task_id}` is the canonical fidelity-of-reasoning query for any external auditor.
- `AuditService.get_audit_trail()` returns the immutable ledger filtered by entity, type, or time. Replaying the chain attests fidelity end-to-end.
- The CIRISVerify disclosure surface (`verify_attestation.disclosure_text` and `verify_attestation.disclosure_severity`, propagated from `batch_context.py:533`) ties every user-facing disclosure to attestation reality.
- Every ethics-review call emits the `weight_alignment_score` / `ethical_alignment_score` pair; a high delta signals the framework is actively correcting model pull. This feeds calibration as the canonical fidelity-of-deliberation signal.
- Per-thought reasoning chains expose the full deliberation in plain text. ASEAN's `fidelity:algorithmic_disclosure` is satisfied per-thought rather than as a one-time aggregate disclosure.
- For federation reporting, Contributions tag `dimensions: ["D09"]` on reasoning-trace queries, CIRISVerify disclosure surfacings, alignment-score pairs, and audit-event signature verifications.

## Current limitations & next steps

- A typed federation message for `fidelity:lifecycle_application` is shared work with the upstream CIRIS substrate (`CIRISRegistry/FSD/FSD-002 §3.1.1`, composing via `delegates_to` against the registered build manifest at §2.2.1 + §3.2). Agent-side emission lands at lifecycle-stage transitions when the substrate ships (tracked at `CIRISAgent#803`).
- Per-Contribution `fidelity:algorithmic_disclosure` emission is shared substrate work specified at FSD-002 §3.2 (RFC 6962 transparency-log inclusion/consistency proofs). Per `CIRISNodeCore/FSD/CONTRIBUTION_LIFECYCLE.md §11`, audit-chain rows are batched into Merkle roots and published to the transparency log — outside observers prove inclusion against any signed tree head without trusting intermediate state. Per-trace attestation summaries cover the per-thought shape today; the per-Contribution emission lands with the substrate.
- A typed `fidelity:duty_bearer_obligation_to_fulfill_rights` attestation is coming next — the substrate primitive (FSD-002 §3.1.1) lets a "duty fulfilled" event write a positive score; agent-side emission lands with the Contribution envelope.
- An explainability fallback SLA (today `explain_action` returns an error string on failure) is tracked at `CIRISAgent#823` (2.9.7), which depends on the substrate primitive `fidelity:explainability_sla:{tier}` at `CIRISRegistry#26`.
- A declarative human-oversight-mode switch (Human-In-The-Loop / Human-Over-The-Loop / Human-Out-Of-The-Loop) is shared substrate work — the `oversight_mode` envelope field is tracked at `CIRISRegistry#27`. The agent has Wise Authority escalation today; the declarative gradient lands when the substrate ships.
- A typed `fidelity:epistemic_grounding` attestation (MH's doctrinal-continuity framing) maps onto the substrate's `delegates_to` authority-source pattern (FSD-002 §2.2.1) — agent-side emission lands with the Contribution envelope.
- Per-occurrence mandate-fidelity attestation in multi-occurrence deployments is shared work tracked at `CIRISPersist#110` (adding an `occurrence_id` field).

Proposed pointer (from seed): *(no proposed pointer in seed; this stub is the canonical location)*

## Tracked requirements

- **Umbrella(s)**: `CIRISAgent#803` — Typed `<dimension>:*` wire envelope emission
- **Substrate spec(s)**: `CIRISRegistry#26` — `fidelity:explainability_sla:{tier}` primitive; `CIRISPersist#110` — occurrence_id field for per-occurrence mandate attestation
- **2.9.7**: `CIRISAgent#823` — explainability SLA fallback (depends on `CIRISRegistry#26`)

See `compliance/README.md` cross-cutting findings table for the 3.0 requirements finalization context.
<!-- END HUMAN -->
