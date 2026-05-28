# D17 — `transparency_log:*` (STRONG-3)

> CIRISVerify per-stakeholder disclosure log

**Seed reference**: `SEED_DIMENSIONS.yaml` v1.0, dimension `D17` ([source](https://github.com/CIRISAI/ciris-response-magnifica-humanitas/blob/main/SEED_DIMENSIONS.yaml))
**Accord principle**: fidelity
**Attestation density**: MH=2 · EU=5 · IEEE=23 · ASEAN=10 · total=40

**Absent from**: MH — Non-zero but structurally low (2). Classified STRONG-3 by analyst because encyclical genre is not a technical-disclosure framework.
  *Functional analogue*: detection:correlated_action:ecology_of_communication:* + the F-3 detector family

## Regulatory attestations

*(Auto-rendered from seed; do not hand-edit. Re-run `python tools/compliance/generate_ciris_compliance_stubs.py tools/compliance/SEED_DIMENSIONS.yaml compliance/` after seed updates.)*

- **MH** (Magnifica Humanitas (On Safeguarding the Human Person in the Time of Artificial Intelligence)) — *§§ various*
    > "honest signs of authority and intent"
    Wire form: `transparency_log:* (sparse)`
- **EU** (Ethics Guidelines for Trustworthy AI) — *§1.4 + §III.4*
    > "transparency about purpose, capability, and limitations"
    Wire form: `transparency_log:per_stakeholder_disclosure`
- **IEEE** (Ethically Aligned Design, First Edition) — *Ch2 P5 + Ch6 + Ch11*
    > "traceability + verifiability + intelligibility four-dimensional transparency"
    Wire form: `transparency_log:* (23 attestations)`
- **ASEAN** (ASEAN Guide on AI Governance and Ethics) — *§B.1 + §C.4*
    > "transparency and explainability through documentation and disclosure"
    Wire form: `transparency_log:* (10 attestations)`

## Wire primitives

- `transparency_log:*`

---

<!-- BEGIN HUMAN -->
## CIRIS-side compliance implementation

TODO — Fill in the code/policy/test surface that implements CIRIS Agent compliance with this dimension. Suggested fields:

- **Code references**: modules / handlers / services / DMAs / conscience faculties implementing this
- **Policy text**: relevant text in `MISSION_CIRISAgent.md`, `prohibitions.py`, `pdma_*.yml`, `language_guidance/*`
- **Test coverage**: pointer to test files exercising this dimension
- **Configuration surface**: relevant schemas / config blocks

Proposed pointer (from seed): `CIRISVerify transparency_log`

## Observability hooks

TODO — Fill in monitoring / observability surface:

- **LensCore detectors**: which F-3 / Coherence Ratchet detectors observe this?
- **RATCHET calibration**: which calibration packages apply?
- **Audit chain queries**: how would a downstream consumer verify compliance?
- **Federation evidence_refs**: emitted Contributions with `dimensions: ["D17"]`

Proposed pointer (from seed): `(none specified in seed; please fill)`

## Known gaps / not-yet-implemented

TODO — Honestly catalog anything this dimension requires that CIRIS Agent does not yet implement. Reference relevant `GAPS.md` entries from the response repo if applicable.
<!-- END HUMAN -->
