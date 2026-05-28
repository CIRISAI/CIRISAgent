# D08 — `autonomy:*` (STRONG-4)

> Human-centric design + informational self-determination

**Seed reference**: `SEED_DIMENSIONS.yaml` v1.0, dimension `D08` ([source](https://github.com/CIRISAI/ciris-response-magnifica-humanitas/blob/main/SEED_DIMENSIONS.yaml))
**Accord principle**: autonomy
**Attestation density**: MH=7 · EU=15 · IEEE=21 · ASEAN=8 · total=51

## Regulatory attestations

*(Auto-rendered from seed; do not hand-edit. Re-run `generate_ciris_compliance_stubs.py` after seed updates.)*

- **MH** (Magnifica Humanitas (On Safeguarding the Human Person in the Time of Artificial Intelligence)) — *§107*
    > "autonomy of the human as imago Dei; informed agency protection"
    Wire form: `autonomy:agent_self_determination`
- **EU** (Ethics Guidelines for Trustworthy AI) — *§1.1 + §2.2 (Unit 019); 15 EU attestations total*
    > "respect for human autonomy — the first principle; AI shall not unjustifiably subordinate, coerce, deceive, manipulate"
    Wire form: `autonomy:human_centric_design`
- **IEEE** (Ethically Aligned Design, First Edition) — *Ch3 + Ch4*
    > "user autonomy; data agency; informed consent"
    Wire form: `autonomy:informed_agency_protection`
- **ASEAN** (ASEAN Guide on AI Governance and Ethics) — *§B.4 Human-centricity*
    > "AI shall not erode human autonomy; informational self-determination"
    Wire form: `autonomy:informational_self_determination`

## Wire primitives

- `autonomy:*`

## Convergence note

Direct 1:1 mapping in EU HLEG (Respect for Human Autonomy = CIRIS autonomy). Composition-based in the other three.

## Cross-source conflicts involving this dimension

- **CONF-04** (mutability, severity LOW_MEDIUM): ASEAN §A.5.3 admits opt-out where feasible; EU HLEG firmer (opt-out where possible without detriment, otherwise rectification mechanisms required)

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
- **Federation evidence_refs**: emitted Contributions with `dimensions: ["D08"]`

Proposed pointer (from seed): `(none specified in seed; please fill)`

## Known gaps / not-yet-implemented

TODO — Honestly catalog anything this dimension requires that CIRIS Agent does not yet implement. Reference relevant `GAPS.md` entries from the response repo if applicable.
<!-- END HUMAN -->
