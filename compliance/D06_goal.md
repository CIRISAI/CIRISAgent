# D06 — `goal:*` (STRONG-4)

> Multi-scale belonging composite — self/family/community/affiliations/species/planet

**Seed reference**: `SEED_DIMENSIONS.yaml` v1.0, dimension `D06` ([source](https://github.com/CIRISAI/ciris-response-magnifica-humanitas/blob/main/SEED_DIMENSIONS.yaml))
**Accord principle**: beneficence
**Attestation density**: MH=34 · EU=6 · IEEE=13 · ASEAN=7 · total=60

## Regulatory attestations

*(Auto-rendered from seed; do not hand-edit. Re-run `generate_ciris_compliance_stubs.py` after seed updates.)*

- **MH** (Magnifica Humanitas (On Safeguarding the Human Person in the Time of Artificial Intelligence)) — *§§148-156*
    > "labor as integral to belonging at family/community/affiliations/species scales"
    Wire form: `goal:family + goal:community + goal:affiliations + goal:species`
- **EU** (Ethics Guidelines for Trustworthy AI) — *§A*
    > "Trustworthy AI for Europe"
    Wire form: `goal:affiliations (EU-jurisdiction scope)`
- **IEEE** (Ethically Aligned Design, First Edition) — *Ch4 §0.a*
    > "well-being of all humans as the species-scale aim of A/IS"
    Wire form: `goal:species`
- **ASEAN** (ASEAN Guide on AI Governance and Ethics) — *§A (6 ASEAN attestations of goal:affiliations)*
    > "regional ecosystem belonging; cross-jurisdictional cooperation"
    Wire form: `goal:affiliations (ASEAN-jurisdiction)`

## Wire primitives

- `goal:{scale}`

## Convergence note

Every available {scale} value is exercised somewhere in the corpus. NB: `goal:planet` is a REINFORCED v1.5+ T-3 candidate (MH + IEEE Ch4 + IEEE Ch8).

## v1.5+ T-3 candidates affecting this dimension

- **T3-06** `goal:planet` (priority MEDIUM_HIGH, source(s): magnifica_humanitas_v1, ieee_ead_v1)

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
- **Federation evidence_refs**: emitted Contributions with `dimensions: ["D06"]`

Proposed pointer (from seed): `(none specified in seed; please fill)`

## Known gaps / not-yet-implemented

TODO — Honestly catalog anything this dimension requires that CIRIS Agent does not yet implement. Reference relevant `GAPS.md` entries from the response repo if applicable.
<!-- END HUMAN -->
