# D01 — `non_maleficence:*` (STRONG-4)

> Soft-harm-avoidance baseline (the soft-scalar above the prohibited:* floor)

**Seed reference**: `SEED_DIMENSIONS.yaml` v1.0, dimension `D01` ([source](https://github.com/CIRISAI/ciris-response-magnifica-humanitas/blob/main/SEED_DIMENSIONS.yaml))
**Accord principle**: non_maleficence
**Attestation density**: MH=28 · EU=29 · IEEE=33 · ASEAN=27 · total=117

## Regulatory attestations

*(Auto-rendered from seed; do not hand-edit. Re-run `python tools/compliance/generate_ciris_compliance_stubs.py tools/compliance/SEED_DIMENSIONS.yaml compliance/` after seed updates.)*

- **MH** (Magnifica Humanitas (On Safeguarding the Human Person in the Time of Artificial Intelligence)) — *§107*
    > "deception as dignity-violation"
    Wire form: `non_maleficence:epistemic_environment_degradation + prohibited:deception_fraud`
- **EU** (Ethics Guidelines for Trustworthy AI) — *§1.2 Technical robustness*
    > "AI systems must prevent harm, ensure reliable behaviour, respect physical/mental integrity"
    Wire form: `non_maleficence:no_cause_or_exacerbate_harm`
- **IEEE** (Ethically Aligned Design, First Edition) — *Ch4 §0.a*
    > "human well-being requires AI development that does not cause unintended harm"
    Wire form: `non_maleficence:wellbeing_dimensions_harm_class`
- **ASEAN** (ASEAN Guide on AI Governance and Ethics) — *§B.3 Security/Safety*
    > "AI should be safe and secure, and not cause harm to users; resilient to attack and failure"
    Wire form: `non_maleficence:safe_and_secure_baseline`

## Wire primitives

- `non_maleficence:* (soft scalar)`
- `prohibited:* (constitutional floor)`

## Convergence note

All four agree polarity-+1 / cohort-species / mutability-amendable for the soft form; absolute floor at prohibited:* polarity-(-1)/constitutional.

---

<!-- BEGIN HUMAN -->
## CIRIS-side compliance implementation

TODO — Fill in the code/policy/test surface that implements CIRIS Agent compliance with this dimension. Suggested fields:

- **Code references**: modules / handlers / services / DMAs / conscience faculties implementing this
- **Policy text**: relevant text in `MISSION_CIRISAgent.md`, `prohibitions.py`, `pdma_*.yml`, `language_guidance/*`
- **Test coverage**: pointer to test files exercising this dimension
- **Configuration surface**: relevant schemas / config blocks

Proposed pointer (from seed): `CIRISAgent/compliance/D01_non_maleficence.md`

## Observability hooks

TODO — Fill in monitoring / observability surface:

- **LensCore detectors**: which F-3 / Coherence Ratchet detectors observe this?
- **RATCHET calibration**: which calibration packages apply?
- **Audit chain queries**: how would a downstream consumer verify compliance?
- **Federation evidence_refs**: emitted Contributions with `dimensions: ["D01"]`

Proposed pointer (from seed): `CIRISLensCore F-3 detector family`

## Known gaps / not-yet-implemented

TODO — Honestly catalog anything this dimension requires that CIRIS Agent does not yet implement. Reference relevant `GAPS.md` entries from the response repo if applicable.
<!-- END HUMAN -->
