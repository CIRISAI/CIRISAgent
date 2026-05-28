# D12 — `conscience:*` (STRONG-4)

> Agent-side faculty layer — optimization veto, epistemic humility, coherence, alētheia

**Seed reference**: `SEED_DIMENSIONS.yaml` v1.0, dimension `D12` ([source](https://github.com/CIRISAI/ciris-response-magnifica-humanitas/blob/main/SEED_DIMENSIONS.yaml))
**Accord principle**: integrity
**Attestation density**: MH=9 · EU=3 · IEEE=9 · ASEAN=3 · total=24

## Regulatory attestations

*(Auto-rendered from seed; do not hand-edit. Re-run `python tools/compliance/generate_ciris_compliance_stubs.py tools/compliance/SEED_DIMENSIONS.yaml compliance/` after seed updates.)*

- **MH** (Magnifica Humanitas (On Safeguarding the Human Person in the Time of Artificial Intelligence)) — *§§111, 131-181*
    > "conscience as the alētheia faculty; optimization-veto for ratification-decline scenarios"
    Wire form: `conscience:optimization_veto (3) + conscience:coherence (3) + conscience:epistemic_humility (2)`
- **EU** (Ethics Guidelines for Trustworthy AI) — *§III.1 + §III.7*
    > "stop-button at any time; whistleblower protection"
    Wire form: `conscience:optimization_veto`
- **IEEE** (Ethically Aligned Design, First Edition) — *Ch3 §§3.1.15-3.1.16 (6 IEEE attestations, densest)*
    > "epistemic humility under uncertainty; phronesis in design"
    Wire form: `conscience:epistemic_humility`
- **ASEAN** (ASEAN Guide on AI Governance and Ethics) — *§C.2 (HOTL category)*
    > "stop-button / override surface for human-over-the-loop oversight"
    Wire form: `conscience:optimization_veto`

## Wire primitives

- `conscience:optimization_veto`
- `conscience:epistemic_humility`
- `conscience:coherence`
- `conscience:entropy`

## Convergence note

Heaviest in IEEE EAD Ch3 (multi-traditional ethics directly engages framework polyglot anchoring) and MH (conscience-faculty engagement is doctrinally explicit).

---

<!-- BEGIN HUMAN -->
## CIRIS-side compliance implementation

TODO — Fill in the code/policy/test surface that implements CIRIS Agent compliance with this dimension. Suggested fields:

- **Code references**: modules / handlers / services / DMAs / conscience faculties implementing this
- **Policy text**: relevant text in `MISSION_CIRISAgent.md`, `prohibitions.py`, `pdma_*.yml`, `language_guidance/*`
- **Test coverage**: pointer to test files exercising this dimension
- **Configuration surface**: relevant schemas / config blocks

Proposed pointer (from seed): `CIRISAgent/logic/conscience/* (4 epistemic faculties)`

## Observability hooks

TODO — Fill in monitoring / observability surface:

- **LensCore detectors**: which F-3 / Coherence Ratchet detectors observe this?
- **RATCHET calibration**: which calibration packages apply?
- **Audit chain queries**: how would a downstream consumer verify compliance?
- **Federation evidence_refs**: emitted Contributions with `dimensions: ["D12"]`

Proposed pointer (from seed): `(none specified in seed; please fill)`

## Known gaps / not-yet-implemented

TODO — Honestly catalog anything this dimension requires that CIRIS Agent does not yet implement. Reference relevant `GAPS.md` entries from the response repo if applicable.
<!-- END HUMAN -->
