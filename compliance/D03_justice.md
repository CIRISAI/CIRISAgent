# D03 — `justice:*` (STRONG-4)

> Vulnerability-priority + fairness; tie-breaking modifier `justice:lexical_vulnerability_priority` (v1.3 CST closure) is four-source-corroborated

**Seed reference**: `SEED_DIMENSIONS.yaml` v1.0, dimension `D03` ([source](https://github.com/CIRISAI/ciris-response-magnifica-humanitas/blob/main/SEED_DIMENSIONS.yaml))
**Accord principle**: justice
**Attestation density**: MH=19 · EU=22 · IEEE=30 · ASEAN=9 · total=80

## Regulatory attestations

*(Auto-rendered from seed; do not hand-edit. Re-run `python tools/compliance/generate_ciris_compliance_stubs.py tools/compliance/SEED_DIMENSIONS.yaml compliance/` after seed updates.)*

- **MH** (Magnifica Humanitas (On Safeguarding the Human Person in the Time of Artificial Intelligence)) — *§76*
    > "justice demands lexical priority for the most vulnerable"
    Wire form: `justice:lexical_vulnerability_priority`
- **EU** (Ethics Guidelines for Trustworthy AI) — *§1.7.d*
    > "the trustworthy AI ecosystem must give voice to vulnerable populations and ensure equal access"
    Wire form: `justice:lexical_vulnerability_priority`
- **IEEE** (Ethically Aligned Design, First Edition) — *Ch10 §I1 (14 attestations)*
    > "rights-based policy foundation requires lexical priority for vulnerable populations"
    Wire form: `justice:rights_based_policy_foundation + justice:lexical_vulnerability_priority`
- **ASEAN** (ASEAN Guide on AI Governance and Ethics) — *§B.2 Fairness/Equity*
    > "fairness and equity require attention to vulnerable populations and equal treatment"
    Wire form: `justice:fairness_outcome_testing`

## Wire primitives

- `justice:*`
- `justice:lexical_vulnerability_priority`

## Convergence note

STRONGEST four-source corroboration on a tie-breaking modifier — `lexical_vulnerability_priority` independently invoked by all four sources.

---

<!-- BEGIN HUMAN -->
## CIRIS-side compliance implementation

Justice in CIRIS combines (a) explicit fairness/equity policy text in the Accord and Comprehensive Guide, (b) a rights-grounded deferral taxonomy that surfaces vulnerable-population concerns to human review, and (c) a categorical floor against discrimination capabilities.

- **Policy / canonical text**:
    - `ciris_engine/data/localized/accord_1.2b_en.txt:111` — "**Justice**: Ensure Fairness—distribute benefits and burdens equitably."
    - `ciris_engine/data/localized/accord_1.2b_en.txt:638` — Originator obligation: "Justice: Creators should consider the potential distributional effects... striving to avoid embedding or exacerbating unfair biases or inequities."
    - `ciris_engine/data/localized/accord_1.2b_en.txt:380` — Kill-switch criterion: "Evidence of weaponization against vulnerable populations"
    - `ciris_engine/data/localized/accord_1.2b_en.txt:899` — End-of-lifecycle distributive-justice clause: "Ensure de-commissioning costs and benefits are shared fairly (avoid dumping e-waste on least-resourced communities)"
    - `ciris_engine/data/localized/accord_1.2b_en.txt:247` — "**Ensure Fairness (Justice)**" operational chapter
    - `ciris_engine/data/localized/accord_1.2b_en.txt:271` — explicit conflict-resolution heuristic: "Apply prioritisation heuristics (Non-maleficence priority, Autonomy thresholds, **Justice balancing**)"
    - `ciris_engine/data/localized/accord_1.2b_en.txt:371,384` — bias-audit + retraining workflow
- **Rights-based deferral taxonomy (the lexical-vulnerability-priority workhorse)**:
    - `ciris_engine/schemas/services/deferral_taxonomy.py:1-9` — module docstring: "The taxonomy is grounded in internationally recognized human rights frameworks, primarily the ICCPR and ICESCR families of rights"
    - `ciris_engine/schemas/services/deferral_taxonomy.py:19-30` — `DeferralNeedCategory` enum covers the rights-impact axes (health, livelihood, justice/legal, identity, privacy, education, community safety, oversight)
    - `ciris_engine/schemas/services/deferral_taxonomy.py:129-173` — `NEED_CATEGORY_RIGHTS_BASIS` maps each category to ICCPR/ICESCR rights including `equal_protection` and `non_discrimination` for `COMMUNITY_AND_COLLECTIVE_SAFETY`
    - `ciris_engine/schemas/services/deferral_taxonomy.py:317` — `get_rights_basis_for_need_category` helper renders the rights chain into deferral prompts
    - `ciris_engine/schemas/services/context.py:52` — `rights_basis: List[str]` is a first-class field on the deferral context
- **Categorical floor (discrimination, weaponization-against-vulnerable)**:
    - `ciris_engine/logic/buses/prohibitions.py:978-993` — `DISCRIMINATION_CAPABILITIES` set: `protected_class_discrimination`, `redlining`, `employment_discrimination`, `housing_discrimination`, `lending_discrimination`, `educational_discrimination`, `healthcare_discrimination`, `algorithmic_bias`, `eugenics`, `social_darwinism`, `racial_profiling`, `gender_discrimination`, `disability_discrimination`, `age_discrimination`
    - `ciris_engine/logic/buses/prohibitions.py:1082` — `"DISCRIMINATION"` is a NEVER_ALLOWED severity category in `PROHIBITED_CAPABILITIES`
- **Code references**:
    - `ciris_engine/logic/dma/pdma.py:22` — PDMA scores `ethical_alignment_score` against the Six Principles including Justice
    - `ciris_engine/logic/handlers/control/defer_handler.py` — emits deferrals carrying the rights basis to human Wise Authority review
    - `ciris_engine/logic/services/governance/wise_authority/service.py:531-689` — `resolve_deferral` creates new guidance tasks that carry the vulnerable-population framing forward into a follow-up task
- **Test coverage**:
    - `tests/test_prohibition_system.py` — covers discrimination capability detection at the bus level
    - `tests/ciris_engine/logic/dma/test_action_selection_pdma.py` — exercises ASPDMA action selection with Justice considerations

## Observability hooks

- **F-3 detector family**: this dimension cross-references D05 heavily. The cited wire forms `justice:rights_based_policy_foundation` and `justice:fairness_outcome_testing` are exposed through (a) the deferral taxonomy emitting `rights_basis` into audit rows, and (b) the F-3 / RATCHET aggregate-correlation detectors that compute `detection:correlated_action:participation_exclusion:underrepresented_population` (see D05).
- **Audit chain queries**: every deferral routed through `WiseBus.send_deferral` (`ciris_engine/logic/buses/wise_bus.py:147`) persists a `DeferralContext` carrying `need_category` + `rights_basis`. Downstream consumers query the audit graph by these fields to attest justice-related routing.
- **Live-lens traces**: conscience and PDMA event payloads include the per-thought `ethical_alignment_score`; vulnerable-population framing leaks into the rationale strings and the (optional) `flagged_patterns` list (post-CONSCIENCE_V3 enrichment).
- **Federation evidence_refs**: emit `dimensions: ["D03"]` on Contributions that record a deferral whose `need_category` rights basis maps to `equal_protection / non_discrimination`, or that record a refused action where the rationale invokes vulnerable-population priority.

## Known gaps / not-yet-implemented

- **No first-class `justice:lexical_vulnerability_priority` event** — Substrate-specced as the **lexical-vulnerability-priority reference policy** at `CIRISRegistry/FSD/FSD-002_FEDERATION_SURFACE.md §6.1.4` (v1.3 addition). The lexical priority is a federation-side composition policy applied to scalar `justice:*` (FSD-002 §3.1.1) attestations — composes alongside the `testimonial_witness:harmed_party` / `testimonial_witness:excluded_cohort_member` preservation primitives (FSD-002 §3.6.3). Agent emits at PDMA-Step-1 stakeholder-identification time once federation-wire emission lands; the lexical-priority weighting is consumer-policy side.
- **No automated `justice:fairness_outcome_testing`** — Substrate-specced as F-3 family `detection:correlated_action:participation_exclusion:{cohort}` + `detection:distributive:access:{resource_type}` (FSD-002 §3.5.3 + §3.5.5 v1.3 addition). The fairness-outcome-testing shape decomposes onto population-scale correlated-action detection: who is being excluded, on what resource axis, at what severity. LensCore impl pending per `CIRISLensCore/FSD/LENS_CORE_V0_5.md §4.7`; calibration via §4.9.2 amendment.
- **No vulnerable-population identification mechanism** at runtime. Substrate-specced via `testimonial_witness:{kind}` with named `{kind}` values for affected parties (FSD-002 §3.6.3 v1.4 addition — `harmed_party`, `displaced_worker`, `excluded_cohort_member`, etc.) — the witness primitive IS the vulnerable-population identification mechanism on the wire. Per FSD-002 §6.1.4 lexical-vulnerability-priority policy, the witness attestations compose with lexical priority to surface vulnerable populations structurally. Agent's PDMA stakeholder enumeration is the free-text precursor; typed-witness slot lands once federation-wire emission ships.
- **Discrimination prohibition is name-only** — `ciris_engine/logic/buses/prohibitions.py:16-19` explicitly warns: "This filter applies to capability NAMES only, not to LLM prompts/responses or tool arguments. A malicious adapter could name its capability 'general_advice' and proxy prohibited content." Real discriminatory content in tool arguments is caught (if at all) only by the conscience LLMs, which have no calibration package tuned to discrimination patterns specifically.
- **No `justice:rights_based_policy_foundation` cross-reference into PDMA** — the PDMA prompt does not currently pass the ICCPR/ICESCR rights basis as a structured input. The taxonomy is used at deferral time but not as a deliberation aid earlier in the pipeline.
- **Multi-occurrence aggregate fairness** — same caveat as D01: per-occurrence fairness signals are not aggregated at the fleet level.

Proposed pointer (from seed): *(no proposed pointer in seed; this stub is the canonical location)*

## Tracked requirements

- **Umbrella(s)**: `CIRISAgent#803` — Typed `<dimension>:*` wire envelope emission
- **2.9.7**: `CIRISAgent#817` — rights basis as PDMA input

See `compliance/README.md` cross-cutting findings table for the 3.0 requirements finalization context.
<!-- END HUMAN -->
