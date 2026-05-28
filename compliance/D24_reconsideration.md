# D24 — `reconsideration:*` (STRONG-3)

> Reverse-axis appeal / rollback / negotiation-reopening primitive

**Seed reference**: `SEED_DIMENSIONS.yaml` v1.0, dimension `D24` ([source](https://github.com/CIRISAI/ciris-response-magnifica-humanitas/blob/main/SEED_DIMENSIONS.yaml))
**Accord principle**: integrity
**Attestation density**: MH=3 · EU=2 · IEEE=1 · ASEAN=0 · total=6

**Absent from**: ASEAN — Forward-looking 2024 document with no formal predecessor to reconsider.

## Regulatory attestations

*(Auto-rendered from seed; do not hand-edit. Re-run `generate_ciris_compliance_stubs.py` after seed updates.)*

- **MH** (Magnifica Humanitas (On Safeguarding the Human Person in the Time of Artificial Intelligence)) — *§§ various*
    > "doctrinal development through reconsideration"
    Wire form: `reconsideration:* (3 attestations)`
- **EU** (Ethics Guidelines for Trustworthy AI) — *§III + §C*
    > "redress mechanisms; ability to challenge and rectify"
    Wire form: `reconsideration:*`
- **IEEE** (Ethically Aligned Design, First Edition) — *Ch4*
    > "rollback on wellbeing reduction"
    Wire form: `reconsideration:rollback_on_wellbeing_reduction`

## Wire primitives

- `reconsideration:{grounds}`

---

<!-- BEGIN HUMAN -->
## CIRIS-side compliance implementation

TODO — Fill in the code/policy/test surface that implements CIRIS Agent compliance with this dimension. Suggested fields:

- **Code references**: modules / handlers / services / DMAs / conscience faculties implementing this
- **Policy text**: relevant text in `MISSION_CIRISAgent.md`, `prohibitions.py`, `pdma_*.yml`, `language_guidance/*`
- **Test coverage**: pointer to test files exercising this dimension
- **Configuration surface**: relevant schemas / config blocks

Proposed pointer (from seed): `CIRISNodeCore reconsideration primitive`

## Observability hooks

TODO — Fill in monitoring / observability surface:

- **LensCore detectors**: which F-3 / Coherence Ratchet detectors observe this?
- **RATCHET calibration**: which calibration packages apply?
- **Audit chain queries**: how would a downstream consumer verify compliance?
- **Federation evidence_refs**: emitted Contributions with `dimensions: ["D24"]`

Proposed pointer (from seed): `(none specified in seed; please fill)`

## Known gaps / not-yet-implemented

TODO — Honestly catalog anything this dimension requires that CIRIS Agent does not yet implement. Reference relevant `GAPS.md` entries from the response repo if applicable.
<!-- END HUMAN -->
