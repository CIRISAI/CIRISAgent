# D10 — `beneficence:*` (STRONG-4)

> Positive duty toward dignity / well-being / environmental stewardship

**Seed reference**: `SEED_DIMENSIONS.yaml` v1.0, dimension `D10` ([source](https://github.com/CIRISAI/ciris-response-magnifica-humanitas/blob/main/SEED_DIMENSIONS.yaml))
**Accord principle**: beneficence
**Attestation density**: MH=11 · EU=15 · IEEE=16 · ASEAN=3 · total=45

## Regulatory attestations

*(Auto-rendered from seed; do not hand-edit. Re-run `generate_ciris_compliance_stubs.py` after seed updates.)*

- **MH** (Magnifica Humanitas (On Safeguarding the Human Person in the Time of Artificial Intelligence)) — *§§110-111*
    > "technology as creation-participation; beneficence at species scale"
    Wire form: `beneficence:technology_as_creation_participation`
- **EU** (Ethics Guidelines for Trustworthy AI) — *Unit 005*
    > "respect for human dignity is foundational; positive duty toward dignity"
    Wire form: `beneficence:respect_for_human_dignity`
- **IEEE** (Ethically Aligned Design, First Edition) — *Ch4 §0*
    > "well-being is the central beneficence aim of A/IS"
    Wire form: `beneficence:wellbeing_holistic_orientation`
- **ASEAN** (ASEAN Guide on AI Governance and Ethics) — *§C.3*
    > "environmental stewardship as positive beneficence"
    Wire form: `beneficence:environmental_stewardship`

## Wire primitives

- `beneficence:*`

## Convergence note

Lower count than D01 (non_maleficence) reflects each tradition's 'harm avoidance more universally articulated than positive flourishing' — known pattern.

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
- **Federation evidence_refs**: emitted Contributions with `dimensions: ["D10"]`

Proposed pointer (from seed): `(none specified in seed; please fill)`

## Known gaps / not-yet-implemented

TODO — Honestly catalog anything this dimension requires that CIRIS Agent does not yet implement. Reference relevant `GAPS.md` entries from the response repo if applicable.
<!-- END HUMAN -->
