# D15 — `moderation:*` (STRONG-4)

> Federation self-correction layer (with IEEE shifting some load to partner_role:* ethics-board constructions)

**Seed reference**: `SEED_DIMENSIONS.yaml` v1.0, dimension `D15` ([source](https://github.com/CIRISAI/ciris-response-magnifica-humanitas/blob/main/SEED_DIMENSIONS.yaml))
**Accord principle**: integrity
**Attestation density**: MH=2 · EU=2 · IEEE=1 · ASEAN=1 · total=5+ with adjacent coverage

## Regulatory attestations

*(Auto-rendered from seed; do not hand-edit. Re-run `generate_ciris_compliance_stubs.py` after seed updates.)*

- **MH** (Magnifica Humanitas (On Safeguarding the Human Person in the Time of Artificial Intelligence)) — *§§220-223*
    > "dialogue-as-negotiation primitive engages moderation:* adjacency"
    Wire form: `moderation:* + adjacent reconsideration:*`
- **EU** (Ethics Guidelines for Trustworthy AI) — *§III.7*
    > "whistleblower protection + out-of-distribution attestation"
    Wire form: `moderation:whistleblower_protection + moderation:ood_attestation`
- **IEEE** (Ethically Aligned Design, First Edition) — *Ch4 + Ch11*
    > "rollback on wellbeing reduction (reconsideration:* adjacent); ethics-board / certification-body partner_role constructions"
    Wire form: `reconsideration:rollback_on_wellbeing_reduction + partner_role:ethics_board`
- **ASEAN** (ASEAN Guide on AI Governance and Ethics) — *Annex A*
    > "out-of-distribution attestation"
    Wire form: `moderation:ood_attestation`

## Wire primitives

- `moderation:*`
- `reconsideration:* (adjacent)`
- `partner_role:* (IEEE-style ethics boards)`

## Convergence note

Tier with caveat: IEEE shifts some structural load to partner_role:* (ethics boards/audit bodies) instead of moderation:* directly. Composition is interoperable.

---

<!-- BEGIN HUMAN -->
## CIRIS-side compliance implementation

TODO — Fill in the code/policy/test surface that implements CIRIS Agent compliance with this dimension. Suggested fields:

- **Code references**: modules / handlers / services / DMAs / conscience faculties implementing this
- **Policy text**: relevant text in `MISSION_CIRISAgent.md`, `prohibitions.py`, `pdma_*.yml`, `language_guidance/*`
- **Test coverage**: pointer to test files exercising this dimension
- **Configuration surface**: relevant schemas / config blocks

Proposed pointer (from seed): `CIRISNodeCore P8 Moderation primitives`

## Observability hooks

TODO — Fill in monitoring / observability surface:

- **LensCore detectors**: which F-3 / Coherence Ratchet detectors observe this?
- **RATCHET calibration**: which calibration packages apply?
- **Audit chain queries**: how would a downstream consumer verify compliance?
- **Federation evidence_refs**: emitted Contributions with `dimensions: ["D15"]`

Proposed pointer (from seed): `(none specified in seed; please fill)`

## Known gaps / not-yet-implemented

TODO — Honestly catalog anything this dimension requires that CIRIS Agent does not yet implement. Reference relevant `GAPS.md` entries from the response repo if applicable.
<!-- END HUMAN -->
