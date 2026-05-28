# D26 — `key_boundary:*` (STRONG-3)

> CIRISEdge encryption key boundary attestation (cryptographic trust scoping)

**Seed reference**: `SEED_DIMENSIONS.yaml` v1.0, dimension `D26` ([source](https://github.com/CIRISAI/ciris-response-magnifica-humanitas/blob/main/SEED_DIMENSIONS.yaml))
**Accord principle**: integrity
**Attestation density**: MH=0 · EU=2 · IEEE=7 · ASEAN=2 · total=11

**Absent from**: MH — Encryption/key-management is not encyclical content.
  *Functional analogue*: Composition via stewardship-of-trust language

## Regulatory attestations

*(Auto-rendered from seed; do not hand-edit. Re-run `generate_ciris_compliance_stubs.py` after seed updates.)*

- **EU** (Ethics Guidelines for Trustworthy AI) — *§1.3 Privacy and data governance*
    > "data security via cryptographic boundary"
    Wire form: `key_boundary:*`
- **IEEE** (Ethically Aligned Design, First Edition) — *Ch6 (7 attestations)*
    > "personal-data trust boundary; cryptographic isolation"
    Wire form: `key_boundary:*`
- **ASEAN** (ASEAN Guide on AI Governance and Ethics) — *§B.3 + §C.3*
    > "security via key-managed trust boundary"
    Wire form: `key_boundary:*`

## Wire primitives

- `key_boundary:{scope}`

---

<!-- BEGIN HUMAN -->
## CIRIS-side compliance implementation

TODO — Fill in the code/policy/test surface that implements CIRIS Agent compliance with this dimension. Suggested fields:

- **Code references**: modules / handlers / services / DMAs / conscience faculties implementing this
- **Policy text**: relevant text in `MISSION_CIRISAgent.md`, `prohibitions.py`, `pdma_*.yml`, `language_guidance/*`
- **Test coverage**: pointer to test files exercising this dimension
- **Configuration surface**: relevant schemas / config blocks

Proposed pointer (from seed): `CIRISEdge key_boundary`

## Observability hooks

TODO — Fill in monitoring / observability surface:

- **LensCore detectors**: which F-3 / Coherence Ratchet detectors observe this?
- **RATCHET calibration**: which calibration packages apply?
- **Audit chain queries**: how would a downstream consumer verify compliance?
- **Federation evidence_refs**: emitted Contributions with `dimensions: ["D26"]`

Proposed pointer (from seed): `(none specified in seed; please fill)`

## Known gaps / not-yet-implemented

TODO — Honestly catalog anything this dimension requires that CIRIS Agent does not yet implement. Reference relevant `GAPS.md` entries from the response repo if applicable.
<!-- END HUMAN -->
