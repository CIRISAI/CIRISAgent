# D21 — `progress_measure:*` (STRONG-3)

> Declared-metric outcomes for tracking progress toward goals

**Seed reference**: `SEED_DIMENSIONS.yaml` v1.0, dimension `D21` ([source](https://github.com/CIRISAI/ciris-response-magnifica-humanitas/blob/main/SEED_DIMENSIONS.yaml))
**Accord principle**: integrity
**Attestation density**: MH=1 · EU=1 · IEEE=8 · ASEAN=0 · total=10

**Absent from**: ASEAN — ASEAN stops at recommendation-level rather than measurement-protocol level.

## Regulatory attestations

*(Auto-rendered from seed; do not hand-edit. Re-run `generate_ciris_compliance_stubs.py` after seed updates.)*

- **MH** (Magnifica Humanitas (On Safeguarding the Human Person in the Time of Artificial Intelligence)) — *§§ various*
    > "structural-coherence progress markers"
    Wire form: `progress_measure:*`
- **EU** (Ethics Guidelines for Trustworthy AI) — *§III.7*
    > "measurable progress toward trustworthiness"
    Wire form: `progress_measure:*`
- **IEEE** (Ethically Aligned Design, First Edition) — *Ch7 (8 attestations)*
    > "documentation criteria as progress_measure; well-being indicators"
    Wire form: `progress_measure:* (8 distinct)`

## Wire primitives

- `progress_measure:{metric}`

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
- **Federation evidence_refs**: emitted Contributions with `dimensions: ["D21"]`

Proposed pointer (from seed): `(none specified in seed; please fill)`

## Known gaps / not-yet-implemented

TODO — Honestly catalog anything this dimension requires that CIRIS Agent does not yet implement. Reference relevant `GAPS.md` entries from the response repo if applicable.
<!-- END HUMAN -->
