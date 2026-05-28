# D19 — `partner_role:*` (STRONG-3)

> CIRIS Registry partner-role taxonomy (ethics boards, audit bodies, stewards)

**Seed reference**: `SEED_DIMENSIONS.yaml` v1.0, dimension `D19` ([source](https://github.com/CIRISAI/ciris-response-magnifica-humanitas/blob/main/SEED_DIMENSIONS.yaml))
**Accord principle**: integrity
**Attestation density**: MH=0 · EU=1 · IEEE=19 · ASEAN=1 · total=21

**Absent from**: MH — MH names ecclesial relations rather than secular institutional partner-role taxonomies.
  *Functional analogue*: Ecclesial-magisterial relations carry analogous structural role but in different vocabulary

## Regulatory attestations

*(Auto-rendered from seed; do not hand-edit. Re-run `python tools/compliance/generate_ciris_compliance_stubs.py tools/compliance/SEED_DIMENSIONS.yaml compliance/` after seed updates.)*

- **EU** (Ethics Guidelines for Trustworthy AI) — *§III.7*
    > "audit/compliance partners"
    Wire form: `partner_role:audit_body`
- **IEEE** (Ethically Aligned Design, First Edition) — *Ch7 + Ch9 + Ch10 + Ch11 (19 attestations)*
    > "Chief Values Officer, ethics committees, certification bodies, ISO-like body, accreditation bodies, HRIA/AIA stewards, trusted disclosure stewards"
    Wire form: `partner_role:{19 distinct roles}`
- **ASEAN** (ASEAN Guide on AI Governance and Ethics) — *§E.001*
    > "ASEAN Working Group on AI Governance (regional intergovernmental dual-remit)"
    Wire form: `partner_role:regional_intergovernmental_working_group`

## Wire primitives

- `partner_role:{role}`

## Convergence note

REINFORCED v1.5+ T-3 candidate here: specialization-pattern proposal covers dual-remit (ASEAN) + trusted-disclosure-steward (IEEE).

## v1.5+ T-3 candidates affecting this dimension

- **T3-07** `partner_role:trusted_disclosure_steward:{authority}` (priority MEDIUM, source(s): ieee_ead_v1)
- **T3-08** `partner_role:regional_intergovernmental_working_group_dual_remit` (priority MEDIUM, source(s): asean_guide_v1)

---

<!-- BEGIN HUMAN -->
## CIRIS-side compliance implementation

TODO — Fill in the code/policy/test surface that implements CIRIS Agent compliance with this dimension. Suggested fields:

- **Code references**: modules / handlers / services / DMAs / conscience faculties implementing this
- **Policy text**: relevant text in `MISSION_CIRISAgent.md`, `prohibitions.py`, `pdma_*.yml`, `language_guidance/*`
- **Test coverage**: pointer to test files exercising this dimension
- **Configuration surface**: relevant schemas / config blocks

Proposed pointer (from seed): `CIRISRegistry partner role registry`

## Observability hooks

TODO — Fill in monitoring / observability surface:

- **LensCore detectors**: which F-3 / Coherence Ratchet detectors observe this?
- **RATCHET calibration**: which calibration packages apply?
- **Audit chain queries**: how would a downstream consumer verify compliance?
- **Federation evidence_refs**: emitted Contributions with `dimensions: ["D19"]`

Proposed pointer (from seed): `(none specified in seed; please fill)`

## Known gaps / not-yet-implemented

TODO — Honestly catalog anything this dimension requires that CIRIS Agent does not yet implement. Reference relevant `GAPS.md` entries from the response repo if applicable.
<!-- END HUMAN -->
