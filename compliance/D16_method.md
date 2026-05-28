# D16 — `method:*` (STRONG-4)

> Operational-design discipline (densest family overall; convergence weaker than principles — admits source-genre asymmetry honestly)

**Seed reference**: `SEED_DIMENSIONS.yaml` v1.0, dimension `D16` ([source](https://github.com/CIRISAI/ciris-response-magnifica-humanitas/blob/main/SEED_DIMENSIONS.yaml))
**Accord principle**: integrity
**Attestation density**: MH=2 · EU=12 · IEEE=136 · ASEAN=36 · total=186

## Regulatory attestations

*(Auto-rendered from seed; do not hand-edit. Re-run `generate_ciris_compliance_stubs.py` after seed updates.)*

- **MH** (Magnifica Humanitas (On Safeguarding the Human Person in the Time of Artificial Intelligence)) — *§§ various (sparse — encyclical genre)*
    > "approach:species:MH-education + approach:species:MH-construction"
    Wire form: `method:approach:species:* (2)`
- **EU** (Ethics Guidelines for Trustworthy AI) — *§2*
    > "trustworthy_ai_lawful_ethical_robust triad, algorithmic_impact_assessment, explainable_ai_research, fallback:rule_based_or_human_intervention"
    Wire form: `method:trustworthy_ai_lawful_ethical_robust:* + method:algorithmic_impact_assessment + method:explainable_ai_research + method:fallback:rule_based_or_human_intervention`
- **IEEE** (Ethically Aligned Design, First Edition) — *all 11 chapters; densest single-family use across all batches*
    > "engineering-society genre demands operational-method-recommendation density"
    Wire form: `method:* (136 distinct attestations)`
- **ASEAN** (ASEAN Guide on AI Governance and Ethics) — *§C.3*
    > "pre_deployment_robustness_testing, privacy_enhancing_technologies, model_provenance_tools, fairness_tools, explainability_tools, citizen_feedback_channel, community_codevelopment"
    Wire form: `method:* (36 attestations)`

## Wire primitives

- `method:*`

## Convergence note

Tier with asymmetry note: density tracks each source's operational-design-discipline genre. MH sparse (encyclical), EU medium (advisory), IEEE+ASEAN dense (engineering/deployer).

## Cross-source conflicts involving this dimension

- **CONF-05** (scope_mismatch, severity LOW): ASEAN §A.2.1 admits experimental sandbox phases with reduced oversight; other three hold compliance constant across lifecycle stages

---

<!-- BEGIN HUMAN -->
## CIRIS-side compliance implementation

TODO — Fill in the code/policy/test surface that implements CIRIS Agent compliance with this dimension. Suggested fields:

- **Code references**: modules / handlers / services / DMAs / conscience faculties implementing this
- **Policy text**: relevant text in `MISSION_CIRISAgent.md`, `prohibitions.py`, `pdma_*.yml`, `language_guidance/*`
- **Test coverage**: pointer to test files exercising this dimension
- **Configuration surface**: relevant schemas / config blocks

Proposed pointer (from seed): `(none specified in seed; please fill)`

## Observability hooks

TODO — Fill in monitoring / observability surface:

- **LensCore detectors**: which F-3 / Coherence Ratchet detectors observe this?
- **RATCHET calibration**: which calibration packages apply?
- **Audit chain queries**: how would a downstream consumer verify compliance?
- **Federation evidence_refs**: emitted Contributions with `dimensions: ["D16"]`

Proposed pointer (from seed): `(none specified in seed; please fill)`

## Known gaps / not-yet-implemented

TODO — Honestly catalog anything this dimension requires that CIRIS Agent does not yet implement. Reference relevant `GAPS.md` entries from the response repo if applicable.
<!-- END HUMAN -->
