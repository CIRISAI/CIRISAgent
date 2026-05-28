# D18 — `attestation:l{3,5}:*` (STRONG-3)

> Verification ladder (L1-L5 hardware-rooted attestation)

**Seed reference**: `SEED_DIMENSIONS.yaml` v1.0, dimension `D18` ([source](https://github.com/CIRISAI/ciris-response-magnifica-humanitas/blob/main/SEED_DIMENSIONS.yaml))
**Accord principle**: integrity
**Attestation density**: MH=2 · EU=4 · IEEE=5 · ASEAN=0 · total=11

**Absent from**: ASEAN — ASEAN framing is normative-principles + risk-assessment, not federation-attestation ladder.
  *Functional analogue*: Composition via accountability-tier wording

## Regulatory attestations

*(Auto-rendered from seed; do not hand-edit. Re-run `generate_ciris_compliance_stubs.py` after seed updates.)*

- **MH** (Magnifica Humanitas (On Safeguarding the Human Person in the Time of Artificial Intelligence)) — *§§ various*
    > "structural verification of doctrinal claims"
    Wire form: `attestation:l3:doctrinal_continuity`
- **EU** (Ethics Guidelines for Trustworthy AI) — *§III.7*
    > "auditability requires attestation at multiple verification levels"
    Wire form: `attestation:l3:* + attestation:l5:*`
- **IEEE** (Ethically Aligned Design, First Edition) — *Ch2 P5 + Ch9*
    > "system-level verifiable attestations"
    Wire form: `attestation:l3:* + attestation:l5:*`

## Wire primitives

- `attestation:l1 through l5`

---

<!-- BEGIN HUMAN -->
## CIRIS-side compliance implementation

TODO — Fill in the code/policy/test surface that implements CIRIS Agent compliance with this dimension. Suggested fields:

- **Code references**: modules / handlers / services / DMAs / conscience faculties implementing this
- **Policy text**: relevant text in `MISSION_CIRISAgent.md`, `prohibitions.py`, `pdma_*.yml`, `language_guidance/*`
- **Test coverage**: pointer to test files exercising this dimension
- **Configuration surface**: relevant schemas / config blocks

Proposed pointer (from seed): `CIRISVerify attestation ladder L1-L5`

## Observability hooks

TODO — Fill in monitoring / observability surface:

- **LensCore detectors**: which F-3 / Coherence Ratchet detectors observe this?
- **RATCHET calibration**: which calibration packages apply?
- **Audit chain queries**: how would a downstream consumer verify compliance?
- **Federation evidence_refs**: emitted Contributions with `dimensions: ["D18"]`

Proposed pointer (from seed): `(none specified in seed; please fill)`

## Known gaps / not-yet-implemented

TODO — Honestly catalog anything this dimension requires that CIRIS Agent does not yet implement. Reference relevant `GAPS.md` entries from the response repo if applicable.
<!-- END HUMAN -->
