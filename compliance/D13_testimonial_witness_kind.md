# D13 — `testimonial_witness:{kind}` (STRONG-4)

> v1.4 affected-party-voice closure — preserves displaced/affected/marginalized voices in attestation

**Seed reference**: `SEED_DIMENSIONS.yaml` v1.0, dimension `D13` ([source](https://github.com/CIRISAI/ciris-response-magnifica-humanitas/blob/main/SEED_DIMENSIONS.yaml))
**Accord principle**: justice
**Attestation density**: MH=11 · EU=2 · IEEE=2 · ASEAN=1 · total=16

## Regulatory attestations

*(Auto-rendered from seed; do not hand-edit. Re-run `generate_ciris_compliance_stubs.py` after seed updates.)*

- **MH** (Magnifica Humanitas (On Safeguarding the Human Person in the Time of Artificial Intelligence)) — *§§81, 89, 138, 151, 166, 167, 173, 216, 217 (11 attestations)*
    > "displaced_worker, abuse_survivor, war_victim, displaced_person, displaced_migrant, historical_moral_transformation"
    Wire form: `testimonial_witness:displaced_worker + :abuse_survivor + :war_victim + :displaced_person + :displaced_migrant + :historical_moral_transformation`
- **EU** (Ethics Guidelines for Trustworthy AI) — *§1.5.c + §III.5.d*
    > "give voice to affected and impacted workers in design-team diversity assessment"
    Wire form: `testimonial_witness:affected_worker + testimonial_witness:impacted_worker`
- **IEEE** (Ethically Aligned Design, First Edition) — *Ch6 + Ch7*
    > "surveilled-person refusal; on-the-ground practitioner narrative"
    Wire form: `testimonial_witness:surveilled_person_refusal + testimonial_witness:on_the_ground_practitioner`
- **ASEAN** (ASEAN Guide on AI Governance and Ethics) — *§C.4*
    > "workforce displacement narrative preservation"
    Wire form: `testimonial_witness:displaced_worker`

## Wire primitives

- `testimonial_witness:{kind}`
- `witness_relation`

## Convergence note

The v1.4 amendment is independently invoked by all four batches — positive evidence the addition was correct. {kind} slot populated with diverse but interoperable values.

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
- **Federation evidence_refs**: emitted Contributions with `dimensions: ["D13"]`

Proposed pointer (from seed): `(none specified in seed; please fill)`

## Known gaps / not-yet-implemented

TODO — Honestly catalog anything this dimension requires that CIRIS Agent does not yet implement. Reference relevant `GAPS.md` entries from the response repo if applicable.
<!-- END HUMAN -->
