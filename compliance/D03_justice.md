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
## What this dimension covers

Justice in CIRIS means fairness across populations and a structural priority for vulnerable groups when interests conflict. All four traditions we track (80 attestations total) name "lexical vulnerability priority" — the same tie-breaking rule MH, EU HLEG, IEEE, and ASEAN independently invoke. CIRIS combines policy text, a rights-grounded escalation taxonomy, and an absolute floor against discrimination capabilities.

## How CIRIS implements this today

Justice shows up in three places: as explicit fairness policy in the canonical text, as a rights-anchored taxonomy that routes vulnerable-population concerns to human review, and as a hard "never" list that blocks discrimination capabilities at the central decision-routing layer.

- Policy text in the canonical Accord names the principle, the originator's duty, the kill-switch trigger, and even end-of-lifecycle distributive justice: `ciris_engine/data/localized/accord_1.2b_en.txt:111` ("distribute benefits and burdens equitably"), `:638` (originator obligation against embedding bias), `:380` ("Evidence of weaponization against vulnerable populations" as a kill-switch criterion), `:899` (e-waste / decommissioning equity), `:247` (operational chapter), `:271` ("Justice balancing" as a balancing heuristic), and `:371,384` (the bias-audit + retraining workflow).
- The escalation taxonomy is grounded in international human rights law and carries the vulnerability-priority logic. `ciris_engine/schemas/services/deferral_taxonomy.py:1-9` states the framing (ICCPR and ICESCR rights families); `:19-30` enumerates the rights-impact categories; `:129-173` maps each category to specific rights (including `equal_protection` and `non_discrimination` under collective safety); `:317` renders the rights chain into the escalation prompt; and `ciris_engine/schemas/services/context.py:52` makes `rights_basis: List[str]` a first-class field on every escalation.
- An absolute prohibition on discrimination capabilities lives at the central decision-routing layer (the WiseBus, where actions flow through governance review). `ciris_engine/logic/buses/prohibitions.py:978-993` enumerates fourteen discrimination categories (protected-class, redlining, employment, housing, lending, education, healthcare, algorithmic bias, eugenics, social Darwinism, racial profiling, gender, disability, age). `:1082` marks `DISCRIMINATION` as `NEVER_ALLOWED`.
- The ethics review step (the Principled Decision-Making Algorithm at `ciris_engine/logic/dma/pdma.py:22`) scores Justice as one of the six principles. When concerns surface, `ciris_engine/logic/handlers/control/defer_handler.py` routes them to Wise Authority (a human or panel the agent defers to) with the rights basis attached. `ciris_engine/logic/services/governance/wise_authority/service.py:531-689` carries the vulnerable-population framing forward into any follow-up task.
- Test coverage: `tests/test_prohibition_system.py` covers discrimination-category detection; `tests/ciris_engine/logic/dma/test_action_selection_pdma.py` exercises the action-selection step (Action-Selection PDMA) with Justice considerations.

## How you can tell it's working (observability)

Auditors can pull every escalation that named a vulnerable-population concern and trace it from the original thought through the conscience signals to the human handoff.

- Every deferral routed through `WiseBus.send_deferral` (`ciris_engine/logic/buses/wise_bus.py:147`) persists the rights basis alongside the need category, so the audit graph can be queried by either field to attest justice-related routing.
- Per-thought reasoning carries the `ethical_alignment_score`; vulnerable-population framing surfaces in the rationale strings and in the `flagged_patterns` enrichment (the CONSCIENCE_V3 work).
- Population-scale fairness signals route through the structural-pattern detector family (LensCore's federation-side detector family) for aggregate participation-exclusion patterns (cross-referenced with D05).
- For federation reporting, Contributions tag `dimensions: ["D03"]` when an escalation's rights basis maps to `equal_protection` or `non_discrimination`, or when an action was refused on vulnerable-population grounds.

## Current limitations & next steps

- A typed federation message tagged with `justice:lexical_vulnerability_priority` is shared work with the upstream CIRIS substrate (`CIRISRegistry/FSD/FSD-002 §6.1.4`). The lexical priority is a federation-side composition policy applied to scalar `justice:*` attestations alongside the testimonial-witness preservation primitives (FSD-002 §3.6.3). Agent-side emission lands when the substrate ships the Contribution envelope (tracked at `CIRISAgent#803`).
- Automated fairness-outcome testing (who is being excluded, on what resource axis, at what severity) is shared substrate work specified at FSD-002 §3.5.3 + §3.5.5 as the structural-pattern detector family's participation-exclusion and distributive-access axes. LensCore implementation tracks at `CIRISLensCore/FSD/LENS_CORE_V0_5.md §4.7` with calibration via §4.9.2.
- A typed runtime mechanism for vulnerable-population identification is coming next. The substrate primitive (`testimonial_witness:{kind}` at FSD-002 §3.6.3, with values like `harmed_party`, `displaced_worker`, `excluded_cohort_member`) is the wire-format identifier. Today the agent's stakeholder enumeration is free-text; the typed witness slot lands with federation-wire emission.
- The discrimination prohibition matches capability *names*, not content inside tool arguments — documented at `ciris_engine/logic/buses/prohibitions.py:16-19` as a first-line defense. A malicious adapter naming itself "general_advice" could proxy discriminatory content, caught (if at all) by the internal safety checks; a content-pattern detector tuned for discrimination is a next step.
- The rights basis is currently used at escalation time but not yet passed as a structured input to the ethics review step. Adding it as a PDMA input is tracked at `CIRISAgent#817` (2.9.7).
- Cross-occurrence aggregate fairness across multi-occurrence deployments is coming next; same shared aggregation path as D01.

Proposed pointer (from seed): *(no proposed pointer in seed; this stub is the canonical location)*

## Tracked requirements

- **Umbrella(s)**: `CIRISAgent#803` — Typed `<dimension>:*` wire envelope emission
- **2.9.7**: `CIRISAgent#817` — rights basis as PDMA input

See `compliance/README.md` cross-cutting findings table for the 3.0 requirements finalization context.
<!-- END HUMAN -->
