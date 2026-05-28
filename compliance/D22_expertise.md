# D22 — `expertise:*` (STRONG-3)

> Declared competence in domain (named-expert attestation)

**Seed reference**: `SEED_DIMENSIONS.yaml` v1.0, dimension `D22` ([source](https://github.com/CIRISAI/ciris-response-magnifica-humanitas/blob/main/SEED_DIMENSIONS.yaml))
**Accord principle**: integrity
**Attestation density**: MH=1 · EU=1 · IEEE=10 · ASEAN=0 · total=12

**Absent from**: ASEAN — ASEAN frames competence at the organizational-governance level, not the named-expert level.

## Regulatory attestations

*(Auto-rendered from seed; do not hand-edit. Re-run `generate_ciris_compliance_stubs.py` after seed updates.)*

- **MH** (Magnifica Humanitas (On Safeguarding the Human Person in the Time of Artificial Intelligence)) — *§§ various*
    > "discernment expertise (sensus fidelium adjacent)"
    Wire form: `expertise:*`
- **EU** (Ethics Guidelines for Trustworthy AI) — *§III.7*
    > "domain expertise required for trustworthy deployment"
    Wire form: `expertise:domain`
- **IEEE** (Ethically Aligned Design, First Edition) — *Ch7-Ch11 (10 attestations)*
    > "engineering, ethics, law, policy expertise; interdisciplinary expertise composition"
    Wire form: `expertise:{domain}`

## Wire primitives

- `expertise:{domain}`

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
- **Federation evidence_refs**: emitted Contributions with `dimensions: ["D22"]`

Proposed pointer (from seed): `(none specified in seed; please fill)`

## Known gaps / not-yet-implemented

TODO — Honestly catalog anything this dimension requires that CIRIS Agent does not yet implement. Reference relevant `GAPS.md` entries from the response repo if applicable.
<!-- END HUMAN -->
