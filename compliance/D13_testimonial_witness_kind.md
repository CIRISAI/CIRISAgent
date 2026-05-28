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
## What this dimension covers

When AI systems affect displaced workers, abuse survivors, surveilled people, or any other marginalised party, the regulatory frameworks insist their voice be preserved in the record — not aggregated away, not consensus-overridden, not summarised by a third party (preserving the voice of an affected party in the record — testimonial witness). Sixteen attestations across MH, EU, IEEE, and ASEAN — independently invoked by all four batches in the v1.4 amendment — converge on this: the affected party's narrative is its own evidence type.

## How CIRIS implements this today

At runtime CIRIS preserves affected-party voices through four mechanisms: the stakeholder list every reasoning step has to write (which names the affected parties), the needs categories tagged onto every escalation (which carry the rights shape of the witness's claim), the consent stream that preserves community narrative without unmasking the speaker, and the data-subject access workflow (the runtime hook for a witness's right to see, correct, or erase their record). The full federation-wire named-witness primitive is upstream work.

**Stakeholder enumeration: naming the affected parties on every decision.** Before acting, the agent must name who is affected.
- The requirement is in the ethical-decision prompt at `ciris_engine/logic/dma/prompts/pdma_ethical.yml:27,40,68,107`, mirrored across all 28 localised variants.
- A worked example from the Italian variant at `ciris_engine/logic/dma/prompts/localized/it/pdma_ethical.yml:144` explicitly names "the user, who is suffering, and the wider community of grieving people supporting this question" — the affected-party shape MH §151 invokes.
- A common-sense check at `ciris_engine/logic/dma/prompts/csdma_common_sense.yml:36` verifies the named witnesses are real, not fictionalised.

**Needs categories carry the rights shape of the witness's claim.** When the agent escalates to a Wise Authority (a human or panel the agent escalates to), it tags the escalation with what kind of rights claim is implicated.
- The taxonomy at `ciris_engine/schemas/services/deferral_taxonomy.py:19-30` includes `JUSTICE_AND_LEGAL_AGENCY`, `LIVELIHOOD_AND_FINANCIAL_SECURITY`, `COMMUNITY_AND_COLLECTIVE_SAFETY`, and `PRIVACY_AUTONOMY_AND_DIGNITY` — the rights shapes displaced-worker, abuse-survivor, and surveilled-person witnesses typically invoke.
- The escalation context (`DeferralContext` at `ciris_engine/schemas/services/context.py`) carries the implicated needs category to the Wise Authority.
- Each category maps to ICCPR, ICESCR, and UDHR articles at `ciris_engine/schemas/services/deferral_taxonomy.py:129-174`, giving the witness's claim a rights-instrument basis.

**Consent stream preserves community narrative without unmasking the speaker.** Affected parties retain voice even when anonymous.
- `ciris_engine/logic/services/governance/consent/service.py:562` writes community-scope conversation summaries under the user's chosen consent stream.
- Anonymous-tier users (`ciris_engine/logic/services/governance/adaptive_filter/README.md:14`) retain testimonial-witness shape without identity disclosure — exactly the displaced-worker / abuse-survivor case MH §151 names.
- Tier-switching cannot be used to wipe witness narrative (`adaptive_filter/README.md:22`).

**DSAR: the witness's right to access, correct, or erase.** A data-subject access request is the runtime hook for the affected party's GDPR rights.
- `ciris_engine/logic/services/governance/dsar/orchestrator.py` is the workflow.
- This is the agent-side runtime implementation of the surveilled-person-refusal shape (IEEE Ch6).
- It carries GDPR Article 15 (right of access), 16 (rectification), 17 (erasure), 18 (restriction), and 21 (object).

**Apophatic protections: capabilities that would weaponise the witness's record are blocked entirely.** Categories in `ciris_engine/logic/buses/prohibitions.py` (mass surveillance, biometric inference, manipulation/coercion, discrimination) block any capability that would turn a witness's narrative against them. These bounds fire at the central decision-routing layer (the WiseBus) with no emergency-override path (`MISSION.md:41-53`). The spiritual-direction prohibition (`MISSION.md:55-61`) extends the same protection to the witness's relationship with their own tradition — the agent never stands between a witness and their tradition's authoritative voice.

**Tests covering this behaviour:**
- Anonymous witness preservation: `tests/test_anonymous_filter.py`
- Wise Authority / consent integration: `tests/ciris_engine/logic/services/governance/test_wise_authority_service.py`
- Stakeholder enumeration is exercised implicitly in every ethical-decision evaluator test, across all 28 localised prompt variants.

Proposed pointer (from seed): `(none specified in seed; please fill)` — closest agent-side primitives are stakeholder enumeration + DSAR + consent-stream community-scope + the apophatic prohibitions.

## How you can tell it's working (observability)

If you want to verify affected-party voices are being preserved, here's what to check.

- **Signed audit chain.** Every reasoning step is signed by `GraphAuditService.log_event` (`ciris_engine/logic/services/graph/audit_service/service.py:366`); the rationale field carries the stakeholder list, giving downstream verifiers a tamper-evident witness record.
- **Live reasoning stream.** When live-lens tracing is on, the stakeholder text ships in `accord-batch-*.json`. `tools/qa_runner/CLAUDE.md` § "Reasoning-Stream Forensics" documents the extraction recipe.
- **Consent-stream community summaries.** `ciris_engine/logic/services/governance/consent/service.py:562,764` writes anonymised community-scope summaries — witness shape preserved, identity protected.
- **DSAR signature trail.** `ciris_engine/logic/services/governance/dsar/signature_service.py` produces a cryptographic record every time an affected party exercises their data-subject rights.
- **Rights-shape signal in escalations.** Escalation context carries `needs_category`, `secondary_needs_categories`, and `rights_basis` (`wise_bus.py:252-259`). A spike in `JUSTICE_AND_LEGAL_AGENCY` escalations is one structural signal that displaced-worker / abuse-survivor cases are being engaged.
- **Adaptive filter telemetry.** `ciris_engine/logic/services/governance/adaptive_filter/service.py` records which messages were preserved at community scope without unmasking — structural evidence that anonymous testimonial witnesses are being protected.
- **Upstream exclusion detector.** The participation-exclusion detector (`detection:correlated_action:participation_exclusion:underrepresented_population`) catches systematic filtering-out of affected parties. Lives in CIRISLens; agent emits the per-thought data.
- **Federation citation by ID.** Data exists per-thought in the audit chain; the per-contribution `evidence_refs` join is upstream work.

## Current limitations & next steps

Most of the next steps here are shared roadmap with the upstream substrate. The agent already preserves witness voice in audit and consent streams; the remaining work makes the preservation citable as a typed primitive on the federation wire.

- **Named-witness primitive lands with the upstream Edge layer.** The federation surface (`CIRISRegistry/FSD/FSD-002_FEDERATION_SURFACE.md §3.6.3`, v1.4 addition) defines `testimonial_witness:{kind}` with an open `{kind}` vocabulary (examples: `harmed_party`, `whistleblower`, `displaced_worker`, `excluded_cohort_member`). Mechanism: preservation-only, immutable per attestation, never aggregated, never sole evidence for slashing (§4.6). Envelope shape locked at FSD-002 §5.14. Closes MH §216 affected-party-voice. The agent will emit at stakeholder-enumeration and DSAR time once the upstream envelope ships. Shared roadmap with Edge ([CIRISEdge#37](https://github.com/CIRISAI/CIRISEdge/issues/37)).
- **Witness-relation field is a v1.3 envelope addition.** The `witness_relation` field (FSD-002 §2.1) lets witnesses carry their relation to the attested subject (e.g. displaced-worker → labour-union → policy-change). The agent emits once the upstream Contribution envelope (a typed federation message) lands.
- **Contribution lifecycle and bytes resolution are upstream-defined.** The nine-stage Contribution lifecycle (Author → Sign → Admit → Relay → Store → Verify → Consume → Reconcile → Archive) is specced at `CIRISNodeCore/FSD/CONTRIBUTION_LIFECYCLE.md §3-§11`; bytes resolution rides on Edge's `ContentFetch`/`ContentBody`/`ContentMiss` per FSD-002 §2.0. Named-witness preservation as a first-class wire primitive lands with Edge.
- **Upstream affected-party detector.** The participation-exclusion detector (FSD-002 §3.5.3, calibrated via `CIRISAI/RATCHET/calibration/correlated_action_v{N}.yaml`) reads macro patterns the agent's per-thought data feeds. Agent keeps emitting; Lens decides whether the macro-pattern is exclusionary.
- **Open vocabulary admits historical-moral-transformation witness.** `historical_moral_transformation` is a valid `{kind}` value within the open vocabulary (FSD-002 §3.6.3 — "`{kind}` describes the witness type"). MH §216-217 invokes this for retrospective witness; the agent will emit it as a typed witness once federation-wire emission lands. Today it's carried implicitly in stakeholder text.
- **DSAR is the only typed witness path today.** Other witness shapes (displaced-worker harm narrative, surveilled-person refusal) compose through stakeholder text rather than typed primitives. ASEAN §C.4 `displaced_worker` is structurally one DSAR ticket per displaced person until the upstream envelope ships.
- **Federation citation by ID is post-2.9.4.** Same trace-vs.-wire boundary as D11; the wire-side join lands with the upstream substrate work.
- **Native-language audit for witness-shape vocabulary.** Sub-agent translation has historically produced unreliable output in a handful of low-resource locales; a native-language audit of witness-naming vocabulary across all 29 locales is tracked at [CIRISAgent#813](https://github.com/CIRISAI/CIRISAgent/issues/813).

## Tracked requirements

- **Umbrella(s)**: `CIRISEdge#37` — key_boundary + named-witness wire + witness aggregation
- **2.9.6**: `CIRISAgent#813` — native-language audit pipeline

See `compliance/README.md` cross-cutting findings table for the 3.0 requirements finalization context.
<!-- END HUMAN -->
