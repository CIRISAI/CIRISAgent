# D23 — `accountability:*` (STRONG-3)

> Named accountability as primary axis (not just structural composition)

**Seed reference**: `SEED_DIMENSIONS.yaml` v1.0, dimension `D23` ([source](https://github.com/CIRISAI/ciris-response-magnifica-humanitas/blob/main/SEED_DIMENSIONS.yaml))
**Accord principle**: fidelity
**Attestation density**: MH=0 · EU=6 · IEEE=3 · ASEAN=19 · total=28

**Absent from**: MH — MH covers accountability FUNCTIONALLY via integrity:* + originator-obligations Accord §IV Ch 2 — architecturally structural rather than named-axis-attested.
  *Functional analogue*: integrity:* + the Accord §IV Ch 2 bidirectional creator-creation obligations

## Regulatory attestations

*(Auto-rendered from seed; do not hand-edit. Re-run `generate_ciris_compliance_stubs.py` after seed updates.)*

- **EU** (Ethics Guidelines for Trustworthy AI) — *§1.7 Accountability*
    > "lifecycle accountability with redress mechanisms"
    Wire form: `accountability:lifecycle_responsibility`
- **IEEE** (Ethically Aligned Design, First Edition) — *Ch2 P6 + Ch11*
    > "accountability principle; rights-based legal accountability"
    Wire form: `accountability:*`
- **ASEAN** (ASEAN Guide on AI Governance and Ethics) — *§B.6 + §C.2 (19 attestations)*
    > "accountability and integrity; human-in-control over AI-augmented decisions"
    Wire form: `accountability:human_in_control + accountability:lifecycle`

## Wire primitives

- `accountability:{axis}`
- `accountability:human_in_control (ASEAN-distinctive — HITL/HOTL/HOOTL)`

## Convergence note

ASEAN's accountability:human_in_control with HITL/HOTL/HOOTL gradient is currently single-source; likely to become STRONG when other oversight-ladder regulatory batches map.

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
- **Federation evidence_refs**: emitted Contributions with `dimensions: ["D23"]`

Proposed pointer (from seed): `(none specified in seed; please fill)`

## Known gaps / not-yet-implemented

TODO — Honestly catalog anything this dimension requires that CIRIS Agent does not yet implement. Reference relevant `GAPS.md` entries from the response repo if applicable.
<!-- END HUMAN -->
