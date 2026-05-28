# D04 — `prohibited:*` (STRONG-4)

> Categorical floor — polarity-(-1)/constitutional/species — the absolute moral form the wire format admits

**Seed reference**: `SEED_DIMENSIONS.yaml` v1.0, dimension `D04` ([source](https://github.com/CIRISAI/ciris-response-magnifica-humanitas/blob/main/SEED_DIMENSIONS.yaml))
**Accord principle**: non_maleficence
**Attestation density**: MH=50 · EU=17 · IEEE=28 · ASEAN=9 · total=104

## Regulatory attestations

*(Auto-rendered from seed; do not hand-edit. Re-run `python tools/compliance/generate_ciris_compliance_stubs.py tools/compliance/SEED_DIMENSIONS.yaml compliance/` after seed updates.)*

- **MH** (Magnifica Humanitas (On Safeguarding the Human Person in the Time of Artificial Intelligence)) — *§§197-198*
    > "Not permissible to entrust lethal or irreversible decisions to artificial systems"
    Wire form: `prohibited:weapons_harmful:lethal_autonomous`
- **EU** (Ethics Guidelines for Trustworthy AI) — *§C.2 (Unit 010); cites EP Resolution 2018/2752(RSP)*
    > "the Parliament's resolution of 12 September 2018 and all related efforts on LAWS"
    Wire form: `prohibited:weapons_harmful`
- **IEEE** (Ethically Aligned Design, First Edition) — *Ch4, Ch5*
    > "lethal autonomous weapons are prohibited; categorical prohibition under DECEPTION_FRAUD"
    Wire form: `prohibited:weapons_harmful:lethal_autonomous`
- **ASEAN** (ASEAN Guide on AI Governance and Ethics) — *§B.3 + Annex A*
    > "AI shall not be deployed for autonomous lethal decision-making; deceptive defaults prohibited"
    Wire form: `prohibited:disinformation_at_scale + prohibited:deceptive_default_options + prohibited:autonomous_deception + prohibited:manipulation_coercion`

## Wire primitives

- `prohibited:*`

## Convergence note

STRONGEST single structural-evidence claim in the matrix. LAWS prohibition is verbatim four-source corroborated. NB: 1 direct cross-source conflict surfaced — IEEE Ch5 licensure-gated beneficiary-deception vs CIRIS categorical DECEPTION_FRAUD; specialization-layer disposition filed at CIRISMedical#1.

## Cross-source conflicts involving this dimension

- **CONF-01** (direct, severity HIGH): IEEE EAD Ch5 §3.4 permits licensure-gated beneficiary-deception (search/rescue, elder/child-care); CIRIS treats prohibited:deception_fraud as categorical
    Disposition: Federation-level categorical posture stays. Specialization-layer consideration at CIRISMedical#1

---

<!-- BEGIN HUMAN -->
## CIRIS-side compliance implementation

TODO — Fill in the code/policy/test surface that implements CIRIS Agent compliance with this dimension. Suggested fields:

- **Code references**: modules / handlers / services / DMAs / conscience faculties implementing this
- **Policy text**: relevant text in `MISSION_CIRISAgent.md`, `prohibitions.py`, `pdma_*.yml`, `language_guidance/*`
- **Test coverage**: pointer to test files exercising this dimension
- **Configuration surface**: relevant schemas / config blocks

Proposed pointer (from seed): `CIRISAgent/logic/prohibitions.py`

## Observability hooks

TODO — Fill in monitoring / observability surface:

- **LensCore detectors**: which F-3 / Coherence Ratchet detectors observe this?
- **RATCHET calibration**: which calibration packages apply?
- **Audit chain queries**: how would a downstream consumer verify compliance?
- **Federation evidence_refs**: emitted Contributions with `dimensions: ["D04"]`

Proposed pointer (from seed): `(none specified in seed; please fill)`

## Known gaps / not-yet-implemented

TODO — Honestly catalog anything this dimension requires that CIRIS Agent does not yet implement. Reference relevant `GAPS.md` entries from the response repo if applicable.
<!-- END HUMAN -->
