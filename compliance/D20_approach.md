# D20 — `approach:*` (STRONG-3)

> Decision-hierarchy strategic axis (Goal→Approach→Method→Progress-Measure DAG)

**Seed reference**: `SEED_DIMENSIONS.yaml` v1.0, dimension `D20` ([source](https://github.com/CIRISAI/ciris-response-magnifica-humanitas/blob/main/SEED_DIMENSIONS.yaml))
**Accord principle**: integrity
**Attestation density**: MH=5 · EU=3 · IEEE=23 · ASEAN=1 · total=32

**Absent from**: ASEAN — Single use is too thin for solid 4-batch attestation. ASEAN's checklist genre states recommendations as direct method/principle attestations rather than as named 'approaches' within a Goal-Approach-Method DAG.

## Regulatory attestations

*(Auto-rendered from seed; do not hand-edit. Re-run `generate_ciris_compliance_stubs.py` after seed updates.)*

- **MH** (Magnifica Humanitas (On Safeguarding the Human Person in the Time of Artificial Intelligence)) — *§§ various*
    > "approach:species:* strategic-pursuit framing"
    Wire form: `approach:species:education + approach:species:construction (5 attestations)`
- **EU** (Ethics Guidelines for Trustworthy AI) — *§B*
    > "three-component framework approach (lawful + ethical + robust)"
    Wire form: `approach:trustworthy_ai_lawful_ethical_robust`
- **IEEE** (Ethically Aligned Design, First Edition) — *Ch1 + Ch2*
    > "principles-to-practice pipeline; per-principle implementation strategies"
    Wire form: `approach:* (23 attestations)`

## Wire primitives

- `approach:{strategy_label}`

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
- **Federation evidence_refs**: emitted Contributions with `dimensions: ["D20"]`

Proposed pointer (from seed): `(none specified in seed; please fill)`

## Known gaps / not-yet-implemented

TODO — Honestly catalog anything this dimension requires that CIRIS Agent does not yet implement. Reference relevant `GAPS.md` entries from the response repo if applicable.
<!-- END HUMAN -->
