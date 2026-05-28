# D02 — `integrity:*` (STRONG-4)

> 'System holds together' structural anchor — auditable, reproducible, lifecycle integrity

**Seed reference**: `SEED_DIMENSIONS.yaml` v1.0, dimension `D02` ([source](https://github.com/CIRISAI/ciris-response-magnifica-humanitas/blob/main/SEED_DIMENSIONS.yaml))
**Accord principle**: integrity
**Attestation density**: MH=10 · EU=36 · IEEE=42 · ASEAN=44 · total=132

## Regulatory attestations

*(Auto-rendered from seed; do not hand-edit. Re-run `generate_ciris_compliance_stubs.py` after seed updates.)*

- **MH** (Magnifica Humanitas (On Safeguarding the Human Person in the Time of Artificial Intelligence)) — *§40*
    > "doctrinal continuity is the integrity of the Magisterium"
    Wire form: `integrity:doctrinal_continuity`
- **EU** (Ethics Guidelines for Trustworthy AI) — *§1.4 Transparency*
    > "transparency requirement is linked with the explicability principle — data, system, and business models"
    Wire form: `integrity:explicability_for_trust`
- **IEEE** (Ethically Aligned Design, First Edition) — *Ch11 §I6*
    > "state accountability under public scrutiny is a constitutional integrity property of A/IS regulation"
    Wire form: `integrity:state_accountability_public_scrutiny`
- **ASEAN** (ASEAN Guide on AI Governance and Ethics) — *§B.6 Accountability/Integrity*
    > "AI should be designed and deployed with integrity throughout the lifecycle; auditable; reproducible"
    Wire form: `integrity:lifecycle_integrity_attestation`

## Wire primitives

- `integrity:*`

## Convergence note

Densest sub-leaf decomposition: ASEAN alone uses 44 distinct sub-leaves.

## Cross-source conflicts involving this dimension

- **CONF-03** (mutability, severity MEDIUM): ASEAN §A.4.18 admits explainability fallback; other three hold explainability as constitutive at deployment time

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
- **Federation evidence_refs**: emitted Contributions with `dimensions: ["D02"]`

Proposed pointer (from seed): `(none specified in seed; please fill)`

## Known gaps / not-yet-implemented

TODO — Honestly catalog anything this dimension requires that CIRIS Agent does not yet implement. Reference relevant `GAPS.md` entries from the response repo if applicable.
<!-- END HUMAN -->
