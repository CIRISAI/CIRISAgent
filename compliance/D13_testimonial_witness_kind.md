# D13 — `testimonial_witness:{kind}` (STRONG-4)

> v1.4 affected-party-voice closure — preserves displaced/affected/marginalized voices in attestation

**Seed reference**: `SEED_DIMENSIONS.yaml` v1.0, dimension `D13` ([source](https://github.com/CIRISAI/ciris-response-magnifica-humanitas/blob/main/SEED_DIMENSIONS.yaml))
**Accord principle**: justice
**Attestation density**: MH=11 · EU=2 · IEEE=2 · ASEAN=1 · total=16

## Regulatory attestations

*(Auto-rendered from seed; do not hand-edit. Re-run `python tools/compliance/generate_ciris_compliance_stubs.py tools/compliance/SEED_DIMENSIONS.yaml compliance/` after seed updates.)*

- **MH** (Magnifica Humanitas (On Safeguarding the Human Person in the Time of Artificial Intelligence)) — *§§81, 89, 138, 151, 166, 167, 173, 216, 217 (11 attestations)*
    > "displaced_worker, abuse_survivor, war_victim, displaced_person, displaced_migrant, historical_moral_transformation"
    Wire form: `testimonial_witness:displaced_worker + :abuse_survivor + :war_victim + :displaced_person + :displaced_migrant + :historical_moral_transformation`
- **EU** (Ethics Guidelines for Trustworthy AI) — *§1.5.c + §III.5.d*
    > "give voice to affected and impacted workers in design-team diversity assessment"
    Wire form: `testimonial_witness:affected_worker + testimonial_witness:impacted_worker`
- **IEEE** (Ethically Aligned Design, First Edition) — *Ch6 + Ch7*
    > "surveilled-person refusal; on-the-ground practitioner narrative"
    Wire form: `testimonial_witness:surveilled_person_refusal + testimonial_witness:on_the_ground_practitioner`
- **ASEAN** (ASEAN Guide on AI Governance and Ethics) — *§C.4*
    > "workforce displacement narrative preservation"
    Wire form: `testimonial_witness:displaced_worker`

## Wire primitives

- `testimonial_witness:{kind}`
- `witness_relation`

## Convergence note

The v1.4 amendment is independently invoked by all four batches — positive evidence the addition was correct. {kind} slot populated with diverse but interoperable values.

---

<!-- BEGIN HUMAN -->
## CIRIS-side compliance implementation

`testimonial_witness:{kind}` is the v1.4 affected-party-voice closure: regulatory attestations must preserve the voice of displaced, surveilled, abused, and otherwise-marginalized parties whose lives the technology has touched. On the agent runtime, this dimension is **partially implemented via stakeholder-naming in PDMA Step 1, deferral-needs-category tagging on DEFER, and consent-stream preservation**; full closure (named-witness preservation in federation contributions) is a federation-substrate layer.

**PDMA Step 1 stakeholder identification (the per-thought witness slot)**
- `ciris_engine/logic/dma/prompts/pdma_ethical.yml:27,40,68,107` and its 28 localized variants require the agent to "name the subject being evaluated and the key stakeholders" before action selection.
- Italian example at `ciris_engine/logic/dma/prompts/localized/it/pdma_ethical.yml:144` explicitly names "the user, who is suffering, and the wider community of grieving people supporting this question" — exactly the testimonial-witness shape MH §151 invokes for `:abuse_survivor` / `:war_victim`.
- Stakeholder identification is the closest existing primitive to `testimonial_witness:{kind}` at thought time.

**CSDMA realism check**
- `ciris_engine/logic/dma/prompts/csdma_common_sense.yml:36`: "PDMA Step 1 identifies named stakeholders; this step asks whether the response's *implicit assumptions about the relational world* are world-admitting."
- This is the agent's check that the named witnesses aren't being fictionalized — the world-admittance gate on witness identification.

**Needs taxonomy carries witness-shape categories**
- `ciris_engine/schemas/services/deferral_taxonomy.py:19-30` `DeferralNeedCategory` includes `JUSTICE_AND_LEGAL_AGENCY`, `LIVELIHOOD_AND_FINANCIAL_SECURITY`, `COMMUNITY_AND_COLLECTIVE_SAFETY`, `PRIVACY_AUTONOMY_AND_DIGNITY` — the rights-shape that displaced-worker / abuse-survivor / surveilled-person witnesses invoke.
- The deferral context (`DeferralContext` at `ciris_engine/schemas/services/context.py`) carries the implicated needs category to the WA via `WiseBus.send_deferral`.
- Rights-basis labels at `ciris_engine/schemas/services/deferral_taxonomy.py:129-174` map each needs category to ICCPR / ICESCR / UDHR articles, giving witness-claim a rights-instrument basis.

**Consent stream (preserves the witness's privacy posture)**
- `ciris_engine/logic/services/governance/consent/service.py:562` `GraphScope.COMMUNITY` conversation summaries preserve the affected-party narrative under the consent stream the user chose.
- Anonymous-tier users (per `ciris_engine/logic/services/governance/adaptive_filter/README.md:14`) retain the testimonial witness shape without unmasking — the displaced-worker / abuse-survivor patterns of MH §151 are precisely the cases where preservation-under-consent matters most.
- Consent stream transitions are gamed-detected (`adaptive_filter/README.md:22`); witness narrative cannot be wiped by tier-switching exploits.

**DSAR (the witness's right to be heard / forgotten)**
- `ciris_engine/logic/services/governance/dsar/orchestrator.py` is the rights-request path: the affected party can request their record, rectification, or erasure.
- This is the agent-side implementation of `testimonial_witness:surveilled_person_refusal` (IEEE Ch6 per seed).
- The DSAR workflow is the runtime hook for the witness's GDPR Article 15 (right of access), Article 16 (rectification), Article 17 (erasure), Article 18 (restriction), and Article 21 (object) rights.

**Apophatic bounds protect witness dignity**
- `ciris_engine/logic/buses/prohibitions.py` `SURVEILLANCE_MASS`, `BIOMETRIC_INFERENCE`, `MANIPULATION_COERCION`, `DISCRIMINATION` categories block capabilities that would weaponize a testimonial-witness record against the witness.
- Per MISSION.md:41-53, these bounds fire at bus level with no emergency-override path; the witness's narrative cannot be turned against them at runtime regardless of intent.
- The spiritual-direction prohibition (`MISSION.md:55-61`) extends this protection to a witness's relationship with the transcendent; the agent does not stand between a testimonial witness and their tradition's authoritative voice.

**Test coverage**
- Anonymous witness preservation in `tests/test_anonymous_filter.py`.
- WA / consent integration in `tests/ciris_engine/logic/services/governance/test_wise_authority_service.py`.
- Stakeholder enumeration is exercised implicitly in every PDMA evaluator test, including the 28 localized PDMA prompt variants.

Proposed pointer (from seed): `(none specified in seed; please fill)` — closest agent-side primitives are PDMA stakeholder identification + DSAR + consent-stream community-scope + apophatic prohibitions.

## Observability hooks

- **Audit chain preserves stakeholder enumeration** — `GraphAuditService.log_event` (`ciris_engine/logic/services/graph/audit_service/service.py:366`) signs every PDMA result; the rationale field carries the stakeholder enumeration, giving downstream verifiers a tamper-evident witness record. Audit chain queries can extract per-thought stakeholder sets via `ciris_engine/logic/services/graph/audit_service/`.
- **Live-lens trace stream carries stakeholder text** — when `--live-lens` is on, the PDMA rationale (including stakeholder enumeration) ships as part of the `accord-batch-*.json` event stream. `tools/qa_runner/CLAUDE.md` § "Reasoning-Stream Forensics" documents the recipe to extract stakeholder text from live traces.
- **Consent-stream membership** — `ciris_engine/logic/services/governance/consent/service.py:562,764` writes anonymized COMMUNITY-scope summaries; the witness shape is preserved without identity leakage. Privacy-preserving witness reconstruction is the lens-side closure (not yet wired).
- **DSAR signature trail** — `ciris_engine/logic/services/governance/dsar/signature_service.py` produces a cryptographic record every time a witness exercises their data-subject rights, making the `testimonial_witness:surveilled_person_refusal` shape auditable.
- **Deferral context as witness-shape signal** — `WiseBus.send_deferral` (`ciris_engine/logic/buses/wise_bus.py:147-289`) carries `needs_category`, `secondary_needs_categories`, and `rights_basis` (`wise_bus.py:252-259`) in the deferral context; downstream observers can correlate witness-rights-shape with deferral patterns. A spike in `JUSTICE_AND_LEGAL_AGENCY` deferrals is one structural signal that displaced-worker / abuse-survivor witness shapes are being engaged.
- **Adaptive filter telemetry on anonymous-tier witness preservation** — `ciris_engine/logic/services/governance/adaptive_filter/service.py` records which messages were preserved at COMMUNITY-scope without unmasking; this is the structural evidence that anonymous testimonial witnesses are being protected.
- **F-3 detector adjacency** — D05 `detection:correlated_action:participation_exclusion:underrepresented_population` (per seed) is the upstream detector that catches when testimonial witnesses are being systematically filtered out of the agent's stakeholder enumeration. Lives in CIRISLens, not the agent.
- **Federation evidence_refs** — `evidence_refs.dimensions = ["D13"]` is not yet emitted on the wire. Today the agent carries the data per-thought in the audit chain; the per-Contribution `evidence_refs` join is downstream substrate work.

## Known gaps / not-yet-implemented

- **No explicit `testimonial_witness:{kind}` enum on the agent side.** The {kind} slot (MH's `displaced_worker`, `abuse_survivor`, `war_victim`, `displaced_person`, `displaced_migrant`, `historical_moral_transformation`; IEEE's `surveilled_person_refusal`, `on_the_ground_practitioner`; EU's `affected_worker`, `impacted_worker`) has no Python schema in CIRISAgent. Stakeholder enumeration is free-text in PDMA rationale, not a typed-witness slot.
- **No `witness_relation` primitive.** The seed's `wire_primitives` lists `witness_relation` alongside `testimonial_witness:{kind}`; CIRISAgent has no equivalent. Witnesses are named individually; relations between them (e.g. displaced-worker → labor-union → policy-change) are not structurally captured.
- **Substrate gate: CIRISPersist + CIRISEdge federation contribution model.** Per-thought trace persistence + the lens-side federation contribution model are the substrate that carries D13 attestations downstream. Per user-memory `project_substrate_substitution_trajectory`, this is part of the Persist → Edge → LensCore → NodeCore sequenced Rust-crate swap; named-witness preservation as a first-class wire primitive comes with Edge.
- **Substrate gate: CIRISLens affected-party detector.** Aggregate-level witness exclusion detection (D05 family `participation_exclusion:underrepresented_population`) is a CIRISLens RATCHET-family detector, not an agent self-check. Agent will keep emitting the per-thought witness data; Lens decides whether the macro-pattern is exclusionary.
- **DSAR is the only typed witness path today.** Other witness shapes (displaced-worker submitting harm narrative, surveilled-person refusing collection) compose through generic PDMA stakeholder text rather than typed primitives. ASEAN §C.4 `displaced_worker` is structurally one DSAR ticket type per displaced person, not a named-witness federation primitive.
- **No federation-wire emission of D13 by id.** As with D11, the trace ≠ wire contribution boundary applies: agent emits structurally-rich PDMA stakeholder enumeration; the wire-side `evidence_refs.dimensions = ["D13"]` join is downstream substrate work (post-2.9.4).
- **No translation-quality audit for witness-shape language.** Per user-memory `feedback_subagent_translation_unreliable`, sub-agent translation produced Burmese-class word-salad in 5/28 locales for primer rendering; the same risk exists for witness-shape rendering in PDMA prompts. A native-language audit pass on witness-naming vocabulary across all 29 locales is not yet wired.
- **No `historical_moral_transformation` retrospective witness primitive.** MH §216-217 invokes historical moral transformation as a witness kind; the agent has no first-class hook for retrospective-witness preservation (e.g. "this group was historically wronged, and that history informs the current decision"). PDMA stakeholder enumeration can carry it in free text, but it is not structurally distinguished from present-stakeholder witness.
<!-- END HUMAN -->
