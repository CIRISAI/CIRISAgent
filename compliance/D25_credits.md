# D25 — `credits:*` (STRONG-3)

> Commons Credits substrate-building recognition (non-monetary contribution attestation)

**Seed reference**: `SEED_DIMENSIONS.yaml` v1.0, dimension `D25` ([source](https://github.com/CIRISAI/ciris-response-magnifica-humanitas/blob/main/SEED_DIMENSIONS.yaml))
**Accord principle**: justice
**Attestation density**: MH=4 · EU=1 · IEEE=4 · ASEAN=0 · total=9

**Absent from**: ASEAN — Credit/recognition framing is implicit in §D National-level (workforce upskilling) rather than wire-attested.

## Regulatory attestations

*(Auto-rendered from seed; do not hand-edit. Re-run `generate_ciris_compliance_stubs.py` after seed updates.)*

- **MH** (Magnifica Humanitas (On Safeguarding the Human Person in the Time of Artificial Intelligence)) — *§§ various (4)*
    > "labor as substrate-building; intergenerational credit; AI literacy credit"
    Wire form: `credits:{subject}:substrate_building`
- **EU** (Ethics Guidelines for Trustworthy AI) — *§1.6*
    > "AI literacy and digital skills as substrate building"
    Wire form: `credits:digital_literacy:substrate_building`
- **IEEE** (Ethically Aligned Design, First Edition) — *Ch8 + Ch9 (4 attestations)*
    > "human-capability contribution recognition; participatory design credits"
    Wire form: `credits:{subject}:substrate_building`

## Wire primitives

- `credits:{subject}:substrate_building`

---

<!-- BEGIN HUMAN -->
## CIRIS-side compliance implementation

TODO — Fill in the code/policy/test surface that implements CIRIS Agent compliance with this dimension. Suggested fields:

- **Code references**: modules / handlers / services / DMAs / conscience faculties implementing this
- **Policy text**: relevant text in `MISSION_CIRISAgent.md`, `prohibitions.py`, `pdma_*.yml`, `language_guidance/*`
- **Test coverage**: pointer to test files exercising this dimension
- **Configuration surface**: relevant schemas / config blocks

Proposed pointer (from seed): `CIRISBilling Commons Credits + CIRIS_COMPREHENSIVE_GUIDE 'Commons Credits' section`

## Observability hooks

TODO — Fill in monitoring / observability surface:

- **LensCore detectors**: which F-3 / Coherence Ratchet detectors observe this?
- **RATCHET calibration**: which calibration packages apply?
- **Audit chain queries**: how would a downstream consumer verify compliance?
- **Federation evidence_refs**: emitted Contributions with `dimensions: ["D25"]`

Proposed pointer (from seed): `(none specified in seed; please fill)`

## Known gaps / not-yet-implemented

TODO — Honestly catalog anything this dimension requires that CIRIS Agent does not yet implement. Reference relevant `GAPS.md` entries from the response repo if applicable.
<!-- END HUMAN -->
