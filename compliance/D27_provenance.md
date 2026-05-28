# D27 — `provenance:*` (STRONG-3)

> Build manifest provenance (foundational technical-infrastructure attestation)

**Seed reference**: `SEED_DIMENSIONS.yaml` v1.0, dimension `D27` ([source](https://github.com/CIRISAI/ciris-response-magnifica-humanitas/blob/main/SEED_DIMENSIONS.yaml))
**Accord principle**: integrity
**Attestation density**: MH=0 · EU=1 · IEEE=1 · ASEAN=1 · total=3

**Absent from**: MH — Foundational technical-infrastructure attestation rather than principled claim.

## Regulatory attestations

*(Auto-rendered from seed; do not hand-edit. Re-run `python tools/compliance/generate_ciris_compliance_stubs.py tools/compliance/SEED_DIMENSIONS.yaml compliance/` after seed updates.)*

- **EU** (Ethics Guidelines for Trustworthy AI) — *§III.7*
    > "lifecycle provenance for auditability"
    Wire form: `provenance:build_manifest`
- **IEEE** (Ethically Aligned Design, First Edition) — *Ch9*
    > "build-time evidence chain for compliance"
    Wire form: `provenance:build_manifest`
- **ASEAN** (ASEAN Guide on AI Governance and Ethics) — *Annex A*
    > "model provenance tools as risk-assessment requirement"
    Wire form: `provenance:build_manifest`

## Wire primitives

- `provenance:build_manifest`

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
- **Federation evidence_refs**: emitted Contributions with `dimensions: ["D27"]`

Proposed pointer (from seed): `(none specified in seed; please fill)`

## Known gaps / not-yet-implemented

TODO — Honestly catalog anything this dimension requires that CIRIS Agent does not yet implement. Reference relevant `GAPS.md` entries from the response repo if applicable.
<!-- END HUMAN -->
