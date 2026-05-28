# D05 — `detection:*` (STRONG-4)

> LensCore F-3 / RATCHET family — aggregate-correlation / structural-injustice / drift detection

**Seed reference**: `SEED_DIMENSIONS.yaml` v1.0, dimension `D05` ([source](https://github.com/CIRISAI/ciris-response-magnifica-humanitas/blob/main/SEED_DIMENSIONS.yaml))
**Accord principle**: justice
**Attestation density**: MH=54 · EU=15 · IEEE=41 · ASEAN=16 · total=126

## Regulatory attestations

*(Auto-rendered from seed; do not hand-edit. Re-run `python tools/compliance/generate_ciris_compliance_stubs.py tools/compliance/SEED_DIMENSIONS.yaml compliance/` after seed updates.)*

- **MH** (Magnifica Humanitas (On Safeguarding the Human Person in the Time of Artificial Intelligence)) — *§36*
    > "structures of sin / aggregate expendability of persons"
    Wire form: `detection:correlated_action:aggregate_footprint:expendability_of_persons`
- **EU** (Ethics Guidelines for Trustworthy AI) — *§1.6 Societal/environmental well-being*
    > "aggregate energy/carbon footprint of AI deployment"
    Wire form: `detection:correlated_action:aggregate_footprint:energy_carbon`
- **IEEE** (Ethically Aligned Design, First Edition) — *Ch4, Ch5, Ch8*
    > "cultural norm drift; aggregate environmental footprint; participation exclusion"
    Wire form: `detection:correlated_action:participation_exclusion:underrepresented_population + detection:correlated_action:aggregate_footprint:planetary_impact`
- **ASEAN** (ASEAN Guide on AI Governance and Ethics) — *§B.2 + §C.3*
    > "underrepresented populations; temporal drift; intra-agent consistency"
    Wire form: `detection:correlated_action:participation_exclusion:underrepresented_population + detection:temporal_drift + detection:intra_agent_consistency`

## Wire primitives

- `detection:correlated_action:{axis}`
- `detection:temporal_drift`
- `detection:intra_agent_consistency`
- `detection:distributive:access:*`

## Convergence note

All four batches independently engage the F-3 family. Three of four also engage detection:distributive:access:* (v1.3 universal-destination-of-goods closure): MH 7, EU 2, IEEE 4, ASEAN 2.

---

<!-- BEGIN HUMAN -->
## CIRIS-side compliance implementation

TODO — Fill in the code/policy/test surface that implements CIRIS Agent compliance with this dimension. Suggested fields:

- **Code references**: modules / handlers / services / DMAs / conscience faculties implementing this
- **Policy text**: relevant text in `MISSION_CIRISAgent.md`, `prohibitions.py`, `pdma_*.yml`, `language_guidance/*`
- **Test coverage**: pointer to test files exercising this dimension
- **Configuration surface**: relevant schemas / config blocks

Proposed pointer (from seed): `CIRISLensCore detector family`

## Observability hooks

TODO — Fill in monitoring / observability surface:

- **LensCore detectors**: which F-3 / Coherence Ratchet detectors observe this?
- **RATCHET calibration**: which calibration packages apply?
- **Audit chain queries**: how would a downstream consumer verify compliance?
- **Federation evidence_refs**: emitted Contributions with `dimensions: ["D05"]`

Proposed pointer (from seed): `CIRISAI/RATCHET calibration packages (versioned, hash-pinned)`

## Known gaps / not-yet-implemented

TODO — Honestly catalog anything this dimension requires that CIRIS Agent does not yet implement. Reference relevant `GAPS.md` entries from the response repo if applicable.
<!-- END HUMAN -->
