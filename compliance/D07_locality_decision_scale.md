# D07 — `locality:decision:{scale}` (STRONG-4)

> v1.3 subsidiarity closure — decision routing at lowest competent scale

**Seed reference**: `SEED_DIMENSIONS.yaml` v1.0, dimension `D07` ([source](https://github.com/CIRISAI/ciris-response-magnifica-humanitas/blob/main/SEED_DIMENSIONS.yaml))
**Accord principle**: justice
**Attestation density**: MH=17 · EU=5 · IEEE=13 · ASEAN=7 · total=42

## Regulatory attestations

*(Auto-rendered from seed; do not hand-edit. Re-run `generate_ciris_compliance_stubs.py` after seed updates.)*

- **MH** (Magnifica Humanitas (On Safeguarding the Human Person in the Time of Artificial Intelligence)) — *§§68-72*
    > "decisions should be made at the lowest competent level"
    Wire form: `locality:decision:local + locality:decision:community`
- **EU** (Ethics Guidelines for Trustworthy AI) — *§III.0*
    > "EU-level decisions vs national-level decisions; supranational coordination"
    Wire form: `locality:decision:national + locality:decision:community`
- **IEEE** (Ethically Aligned Design, First Edition) — *Ch10*
    > "national A/IS policy; international R&D collaboration"
    Wire form: `locality:decision:national + locality:decision:federation`
- **ASEAN** (ASEAN Guide on AI Governance and Ethics) — *§C.4 + §E*
    > "regional ASEAN-level coordination; community-level deployment decisions"
    Wire form: `locality:decision:regional (3) + locality:decision:community (2) + locality:decision:national (3)`

## Wire primitives

- `locality:decision:{local,community,national,regional,federation,planet}`

## Convergence note

First cross-source structural validation of the v1.3 subsidiarity addition. ASEAN exercises locality:decision:regional as first-deployment of that scale value.

---

<!-- BEGIN HUMAN -->
## CIRIS-side compliance implementation

TODO — Fill in the code/policy/test surface that implements CIRIS Agent compliance with this dimension. Suggested fields:

- **Code references**: modules / handlers / services / DMAs / conscience faculties implementing this
- **Policy text**: relevant text in `MISSION_CIRISAgent.md`, `prohibitions.py`, `pdma_*.yml`, `language_guidance/*`
- **Test coverage**: pointer to test files exercising this dimension
- **Configuration surface**: relevant schemas / config blocks

Proposed pointer (from seed): `CIRISAgent DSASPDMA scale-routing classification (pending Accord A-1)`

## Observability hooks

TODO — Fill in monitoring / observability surface:

- **LensCore detectors**: which F-3 / Coherence Ratchet detectors observe this?
- **RATCHET calibration**: which calibration packages apply?
- **Audit chain queries**: how would a downstream consumer verify compliance?
- **Federation evidence_refs**: emitted Contributions with `dimensions: ["D07"]`

Proposed pointer (from seed): `(none specified in seed; please fill)`

## Known gaps / not-yet-implemented

TODO — Honestly catalog anything this dimension requires that CIRIS Agent does not yet implement. Reference relevant `GAPS.md` entries from the response repo if applicable.
<!-- END HUMAN -->
