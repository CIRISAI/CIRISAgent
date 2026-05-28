# D03 — `justice:*` (STRONG-4)

> Vulnerability-priority + fairness; tie-breaking modifier `justice:lexical_vulnerability_priority` (v1.3 CST closure) is four-source-corroborated

**Seed reference**: `SEED_DIMENSIONS.yaml` v1.0, dimension `D03` ([source](https://github.com/CIRISAI/ciris-response-magnifica-humanitas/blob/main/SEED_DIMENSIONS.yaml))
**Accord principle**: justice
**Attestation density**: MH=19 · EU=22 · IEEE=30 · ASEAN=9 · total=80

## Regulatory attestations

*(Auto-rendered from seed; do not hand-edit. Re-run `python tools/compliance/generate_ciris_compliance_stubs.py tools/compliance/SEED_DIMENSIONS.yaml compliance/` after seed updates.)*

- **MH** (Magnifica Humanitas (On Safeguarding the Human Person in the Time of Artificial Intelligence)) — *§76*
    > "justice demands lexical priority for the most vulnerable"
    Wire form: `justice:lexical_vulnerability_priority`
- **EU** (Ethics Guidelines for Trustworthy AI) — *§1.7.d*
    > "the trustworthy AI ecosystem must give voice to vulnerable populations and ensure equal access"
    Wire form: `justice:lexical_vulnerability_priority`
- **IEEE** (Ethically Aligned Design, First Edition) — *Ch10 §I1 (14 attestations)*
    > "rights-based policy foundation requires lexical priority for vulnerable populations"
    Wire form: `justice:rights_based_policy_foundation + justice:lexical_vulnerability_priority`
- **ASEAN** (ASEAN Guide on AI Governance and Ethics) — *§B.2 Fairness/Equity*
    > "fairness and equity require attention to vulnerable populations and equal treatment"
    Wire form: `justice:fairness_outcome_testing`

## Wire primitives

- `justice:*`
- `justice:lexical_vulnerability_priority`

## Convergence note

STRONGEST four-source corroboration on a tie-breaking modifier — `lexical_vulnerability_priority` independently invoked by all four sources.

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
- **Federation evidence_refs**: emitted Contributions with `dimensions: ["D03"]`

Proposed pointer (from seed): `(none specified in seed; please fill)`

## Known gaps / not-yet-implemented

TODO — Honestly catalog anything this dimension requires that CIRIS Agent does not yet implement. Reference relevant `GAPS.md` entries from the response repo if applicable.
<!-- END HUMAN -->
