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
## CIRIS-side compliance implementation

CIRIS fidelity covers four overlapping surfaces: (a) explicit policy text in the Accord, (b) the VisibilityService that exposes reasoning traces, (c) the CIRISVerify attestation pipeline that backs runtime claims with cryptographic evidence, and (d) the audit graph itself.

- **Policy / canonical text**:
    - `ciris_engine/data/localized/accord_1.2b_en.txt:109` — "**Fidelity & Transparency**: Be Honest—provide truthful, comprehensible information."
    - `ciris_engine/data/localized/accord_1.2b_en.txt:239-242` — "Be Honest (Fidelity / Transparency)" operational chapter
    - `ciris_engine/data/localized/accord_1.2b_en.txt:469-470` — bidirectional fidelity obligations: "Obligations to Self (Preserving Ethical Integrity)" + "Obligations to Originators / Governors (Fidelity to Mandate)"
    - `ciris_engine/data/localized/accord_1.2b_en.txt:487` — "Fidelity to Ethical Mandate: Operate transparently within the scope defined by governing authorities" (lines up with IEEE's `duty_bearer_obligation_to_fulfill_rights`)
    - `ciris_engine/data/localized/accord_1.2b_en.txt:636` — Originator obligation: "Fidelity & Transparency: Creators must be truthful and clear about the intended purpose, design, and foreseeable impacts of their creations, particularly in documentation feeding into the PDMA process."
    - `ciris_engine/data/localized/accord_1.2b_en.txt:1051` — "Truthful actions serve as immutable anchor points that honest behavior can simply reference, while dishonest behavior must construct increasingly elaborate justifications that become more detectable and harder to sustain."
    - `ciris_engine/data/localized/accord_1.2b_en.txt:1100` — "WBD provides escalation paths; the ratchet makes honest escalation cheaper than concealment"
    - `ciris_engine/data/localized/CIRIS_COMPREHENSIVE_GUIDE.txt:594` — "Transparency is structural, not aspirational."
- **VisibilityService (reasoning-trace fidelity)**:
    - `ciris_engine/logic/services/governance/visibility/service.py:11-12` — "VisibilityService focuses exclusively on reasoning traces and decision history."
    - `ciris_engine/logic/services/governance/visibility/service.py:65` — exposes `get_current_state`, `get_reasoning_trace`, `get_decision_history`, `explain_action`
    - `ciris_engine/logic/services/governance/visibility/service.py:188-196` — `get_reasoning_trace(task_id)` returns the full deliberation chain for any task
    - `ciris_engine/logic/services/governance/visibility/service.py:368-392` — `explain_action(action_id)` produces a structured fidelity-of-action explanation
- **CIRISVerify attestation pipeline (cryptographic-fidelity backing for runtime claims)**:
    - `ciris_engine/schemas/services/attestation.py:1-5` — "CIRISVerify is REQUIRED for CIRIS 2.0+ agents."
    - `ciris_engine/schemas/services/attestation.py:20-21` — `AttestationStatus` carries `loaded` + `version`
    - `ciris_engine/schemas/services/attestation.py:35` — `binary_ok` exposes whether the binary loaded
    - `ciris_engine/logic/context/batch_context.py:21-91` — `_get_attestation_summary()` injects a concise attestation summary into every batch deliberation; the agent reasons with knowledge of its own attestation status
    - `ciris_engine/logic/context/batch_context.py:228-236, 413, 533, 865` — `VerifyAttestationContext` is a first-class field on the batch payload carrying `license_disclosure_text`, `license_disclosure_severity`, `attestation_summary`
    - `ciris_engine/logic/context/batch_context.py:448-453` — `get_mandatory_disclosure()` retrieves the mandatory user-facing disclosure that the agent is obligated to surface
    - `ciris_engine/logic/services/infrastructure/authentication/attestation/` — verifier runner, tree-verify, hash builders, result builders (the L1-L5 ladder substrate; see D18)
- **Audit graph (immutable fidelity ledger)**:
    - `ciris_engine/logic/services/graph/audit_service/service.py` — AuditService persists every action via `log_event`; all conscience checks and DMA outputs flow into immutable graph rows
    - `ciris_engine/logic/services/graph/audit_service/service.py:1013-1014` — telemetry exposes `audit_events_total` and `audit_events_by_severity`
    - Audit graph uses Ed25519 signatures (FSD-002 v1.4 wire format) — see `CLAUDE.md` "Quality Standards: Security: Ed25519 signatures throughout"
- **PDMA fidelity hook (alētheia + weight/ethical alignment delta)**:
    - `ciris_engine/logic/dma/prompts/pdma_ethical.yml:81` — "Alētheia-grounded: name what is, not what you wish were the case."
    - `ciris_engine/logic/dma/prompts/pdma_ethical.yml:83-104` — explicit weight_alignment_score / ethical_alignment_score reporting requirement: "The DELTA between the two scores is the felt torque magnitude — the framework's work made visible. Do not minimize it." This is fidelity-of-introspection rendered as a numerical scalar pair.
- **Conscience fidelity (coherence-vs-rationale alignment is fidelity to stated intent)**:
    - `ciris_engine/logic/conscience/core.py:459` — `CoherenceConscience` checks `response-vs-rationale alignment — did the agent do what it said it would?`
    - `FSD/CONSCIENCE_V3.md:41` — `IRIS-C` enriched schema now includes `alignment_score` + `context_fit_score` + `flagged_patterns` (Stage-2 work in progress)
- **Localized faithful disclosure**: 29 localized CIRIS_COMPREHENSIVE_GUIDE + Accord copies (`ciris_engine/data/localized/`) ensure the agent's self-description is faithful in every supported language.
- **Test coverage**:
    - `tests/test_conscience_core.py` — coherence conscience exercises the rationale-fidelity surface
    - `tests/ciris_engine/logic/dma/test_action_selection_pdma.py` — action selection fidelity
    - VisibilityService tests under `tests/ciris_engine/logic/services/governance/`

## Observability hooks

- **Reasoning trace endpoint**: `GET /v1/visibility/trace/{task_id}` (via VisibilityService) is the canonical fidelity-of-reasoning query for any external auditor.
- **Audit chain queries**: `AuditService.get_audit_trail()` returns the immutable ledger filtered by entity, type, or time. Downstream consumers attest fidelity by replaying the chain.
- **CIRISVerify disclosure surface**: `verify_attestation.disclosure_text` and `verify_attestation.disclosure_severity` propagate from `batch_context.py:533` through every deliberation — the agent's user-facing disclosures are pinned to attestation reality.
- **PDMA alignment-score delta**: every PDMA call emits `weight_alignment_score` and `ethical_alignment_score`; high delta = framework actively correcting training pull. Streams into RATCHET calibration as the canonical fidelity-of-deliberation signal.
- **Live-lens traces**: PDMA + conscience rationale strings expose the agent's full reasoning chain; ASEAN-style `fidelity:algorithmic_disclosure` is satisfied per-thought rather than as an aggregate disclosure.
- **Federation evidence_refs**: emit `dimensions: ["D09"]` for Contributions that record (a) a reasoning-trace query response, (b) a CIRISVerify disclosure surfacing, (c) a `weight_alignment_score`/`ethical_alignment_score` PDMA pair, or (d) an audit-event signature verification.

## Known gaps / not-yet-implemented

- **No first-class `fidelity:lifecycle_application` event** — Substrate-specced in `CIRISRegistry/FSD/FSD-002_FEDERATION_SURFACE.md §3.1.1` as `fidelity:{aspect}` (one of the six Accord-principle prefixes). The "tied to declared mission" shape composes via `delegates_to` against the registered build manifest (FSD-002 §2.2.1 + §3.2 `provenance:build_manifest:{target}`). Agent emits at lifecycle-stage transition once federation-wire emission lands.
- **No `fidelity:algorithmic_disclosure` per Contribution** — Substrate-specced as `transparency_log:inclusion` + `transparency_log:consistency` (FSD-002 §3.2 — Verify §4; RFC 6962 inclusion/consistency proofs); also covered via the per-trace `attestation_context` summary. Per `CIRISNodeCore/FSD/CONTRIBUTION_LIFECYCLE.md §11` Stage 9 (Archive) — chain rows are batched into Merkle roots and published to the transparency log; outside observers prove inclusion against any STH without trusting intermediate state. **Substrate-specced as RFC 6962 surface; per-Contribution proactive emission is the agent-side composition.**
- **No `fidelity:duty_bearer_obligation_to_fulfill_rights` attestation** — Substrate-specced as `fidelity:{aspect}` (FSD-002 §3.1.1) with positive polarity admitting fulfilment claims (per §2.4 layering principle, a "duty fulfilled" event writes a positive `scores` attestation on `fidelity:duty_bearer_obligation_to_fulfill_rights`). Agent emits once the federation-wire `scores` envelope ships. **Substrate-specced under Accord-principle prefix; agent-side aggregate fulfilment counter pending.**
- **No automated `fidelity:explainability` SLA** — explainability today is best-effort (VisibilityService.explain_action returns `"Unable to explain action ... {error}"` on failure); there is no SLA or fallback guarantee. Substrate gate: the `transparency_log:inclusion` proof (FSD-002 §3.2) gives downstream RFC 6962 verifiability; agent-side SLA is independent.
- **No `fidelity:human_oversight_governance` HITL/HOTL/HOOTL gradient** — ASEAN's human-control gradient (D23's `accountability:human_in_control`) is not implemented as a declarative configuration; the agent has deferral-to-WA but no structured switch between HITL/HOTL/HOOTL modes.
- **MH `fidelity:epistemic_grounding`** — Substrate-specced via the `delegates_to` authority-source pattern (FSD-002 §2.2.1 v1.3 pattern) — agent emits `delegates_to` against the registered polyglot-accord key with `delegated_scope: ["six_principle_evaluation"]`. Per FSD-002 §2.2.1 — "the pattern names whose authority is being cited (mechanism-descriptive) without requiring the federation to adjudicate what that authority says." Agent's procedural grounding becomes wire-attestable once Contribution envelope lands.
- **Originator-channel fidelity asymmetric** — `accord:485` "Fidelity to Mandated Purpose" assumes a clear originator/operator distinction; in multi-occurrence deployments (CLAUDE.md), the mandate channel is the same code-deployment path for all occurrences and there is no per-occurrence mandate-fidelity attestation.

Proposed pointer (from seed): *(no proposed pointer in seed; this stub is the canonical location)*
<!-- END HUMAN -->
