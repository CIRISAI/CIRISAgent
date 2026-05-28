# CIRIS Agent Compliance

> Where CIRIS Agent's code reality meets the regulatory frameworks it claims to comply with.

This directory is the umbrella for CIRIS Agent compliance documentation. It serves three audiences with one source of truth:

1. **Regulatory cross-walks** — mapping CIRIS implementation to Magnifica Humanitas, EU HLEG Trustworthy AI Guidelines, IEEE Ethically Aligned Design, ASEAN AI Governance Guide, and (planned) UNESCO + OECD.
2. **Grant submissions** — every numeric claim about the codebase is reproducible from a dated baseline artifact, not embedded prose.
3. **Internal compliance audits** — honest "Known gaps" inventory per dimension lets the team and external reviewers see what's done, what's substrate-gated, what's not started.

## Structure

```
compliance/
├── README.md                       ← you are here
├── MEASUREMENT_METHODOLOGY.md      ← how baselines are generated; CI hooks; 4-level validation hierarchy
├── baselines/                      ← dated, script-generated numeric evidence
│   ├── 2026-04-22_round1.md        ← original Round 1 snapshot (PR #695)
│   ├── 2026-04-24_round1.md        ← Round 1 refresh
│   └── 2026-05-28.md               ← current
└── D01..D27_*.md                   ← per-dimension stubs (auto-rendered top + HUMAN section)
```

Generator script + canonical seed live elsewhere:
- `tools/compliance/SEED_DIMENSIONS.yaml` — source of truth for the 27 dimensions
- `tools/compliance/generate_ciris_compliance_stubs.py` — regenerates the auto-rendered top of each stub from seed
- `tools/analysis/round1_grant_baseline.py` — produces baselines/*.md from live FastAPI / service config / pytest collection

## The 27 dimensions

Stable IDs from `SEED_DIMENSIONS.yaml` v1.0. STRONG-4 = attested by all 4 regulatory batches (Magnifica Humanitas / EU HLEG / IEEE / ASEAN); STRONG-3 = attested by 3 of 4.

### STRONG-4 (D01–D16) — universal four-source convergence

| # | Prefix | Gloss |
|---|---|---|
| [D01](D01_non_maleficence.md) | `non_maleficence:*` | Soft-harm-avoidance baseline (soft scalar above the prohibited:* floor) |
| [D02](D02_integrity.md) | `integrity:*` | "System holds together" — auditable, reproducible, lifecycle integrity |
| [D03](D03_justice.md) | `justice:*` | Vulnerability-priority + fairness; lexical vulnerability priority tie-breaker |
| [D04](D04_prohibited.md) | `prohibited:*` | Categorical floor — polarity-(-1)/constitutional/species |
| [D05](D05_detection.md) | `detection:*` | LensCore F-3 / RATCHET aggregate-correlation / structural-injustice / drift |
| [D06](D06_goal.md) | `goal:*` | Multi-scale belonging composite (self / family / community / species / planet) |
| [D07](D07_locality_decision_scale.md) | `locality:decision:{scale}` | Subsidiarity — decision routing at lowest competent scale |
| [D08](D08_autonomy.md) | `autonomy:*` | Human-centric design + informational self-determination |
| [D09](D09_fidelity.md) | `fidelity:*` | Faithful disclosure / faithful representation across lifecycle |
| [D10](D10_beneficence.md) | `beneficence:*` | Positive duty toward dignity / well-being / environmental stewardship |
| [D11](D11_multilateral_participation_forum_kind.md) | `multilateral_participation:{forum}:{kind}` | Federation participation in external multilateral processes |
| [D12](D12_conscience.md) | `conscience:*` | Agent-side faculty layer — optimization veto, epistemic humility, coherence, alētheia |
| [D13](D13_testimonial_witness_kind.md) | `testimonial_witness:{kind}` | Preserves displaced / affected / marginalized voices in attestation |
| [D14](D14_witness_diversity.md) | `witness_diversity:*` | Stakeholder pluralism in design / testing / consultation |
| [D15](D15_moderation.md) | `moderation:*` | Federation self-correction layer |
| [D16](D16_method.md) | `method:*` | Operational-design discipline (densest family — entire H3ERE pipeline) |

### STRONG-3 (D17–D27) — three-source convergence

| # | Prefix | Gloss |
|---|---|---|
| [D17](D17_transparency_log.md) | `transparency_log:*` | CIRISVerify per-stakeholder disclosure log |
| [D18](D18_attestation_l_3_5.md) | `attestation:l{3,5}:*` | L1–L5 hardware-rooted verification ladder |
| [D19](D19_partner_role.md) | `partner_role:*` | CIRIS Registry partner-role taxonomy (ethics boards, audit bodies, stewards) |
| [D20](D20_approach.md) | `approach:*` | Decision-hierarchy strategic axis (Goal→Approach→Method→Progress-Measure) |
| [D21](D21_progress_measure.md) | `progress_measure:*` | Declared-metric outcomes for tracking progress toward goals |
| [D22](D22_expertise.md) | `expertise:*` | Declared competence in domain (named-expert attestation) |
| [D23](D23_accountability.md) | `accountability:*` | Named accountability as primary axis |
| [D24](D24_reconsideration.md) | `reconsideration:*` | Reverse-axis appeal / rollback / negotiation-reopening |
| [D25](D25_credits.md) | `credits:*` | Commons Credits substrate-building recognition |
| [D26](D26_key_boundary.md) | `key_boundary:*` | CIRISEdge encryption key boundary attestation |
| [D27](D27_provenance.md) | `provenance:*` | Build manifest provenance (foundational technical-infrastructure attestation) |

## Reading order

For external reviewers:

1. Start with [`MEASUREMENT_METHODOLOGY.md`](MEASUREMENT_METHODOLOGY.md) to understand how numeric claims are validated.
2. Check the **current baseline** in [`baselines/`](baselines/) for the latest service / endpoint counts.
3. Pick the dimensions most relevant to your framework:
   - Catholic / values-based: D01, D03, D04, D06, D08, D10, D12, D14
   - EU AI Act / GDPR alignment: D02, D08, D09, D17, D26, D27
   - IEEE Ethically Aligned Design: D03, D05, D14, D18, D19, D22, D23
   - ASEAN: D02, D04, D05, D08, D15, D16, D17, D27
4. For each dimension, read the auto-rendered top (regulatory attestations + wire form + convergence note) then the HUMAN section (CIRIS implementation + observability + known gaps).

## Cross-cutting findings (2026-05-28)

Documented in the seed-population commit (`bd330545b`) and inventoried here for quick reference:

| # | Finding | Affected dimensions |
|---|---|---|
| 1 | Typed `<dimension>:*` wire envelopes not yet emitted — biggest impl-vs-spec gap | D01, D03, D08, D09, D10, D12 (and most others by extension) |
| 2 | LensCore F-3 detector family not in any CIRISAI repo yet | D05, D06, D07, D13, D14, D15, D19, D26 |
| 3 | No cross-occurrence aggregate metrics — per-occurrence scalars stay local | D01, D03, D10, D12 |
| 4 | D22/D23 structurally inverted — route via DEFER→WiseAuthority rather than named axes (MH-posture not ASEAN-posture) | D22, D23 |
| 5 | D24 reverse-axis gap — no rollback after SPEAK/TOOL; reconsideration strictly forward-looking via PONDER | D24 |
| 6 | D04 capability check is NAME-only (`prohibitions.py:16-19`) — prohibited content in tool args / LLM responses caught only by 4 conscience LLMs, no D04-tuned calibration | D04 |
| 7 | D25 schema-rich (`CreditRecord`, `GratitudeSignal`, `DualSignature` Ed25519+ML-DSA-65) but emission staged behind CIRISBilling | D25 |
| 8 | L5 attestation caps at L4 on Linux/macOS servers — no TPM-quote equivalent of Android `play_integrity_ok` | D18, D26 |
| 9 | Localization parity partial — D04 category list is English-only; 29 locales carry framing but not canonical capability list | D04 |
| 10 | CONSCIENCE_V3 Stages 2–4 unshipped; ~60% IRIS-O/IRIS-H overlap persists | D12 |

## Substrate dependencies

Many dimensions depend on upstream CIRIS substrates landing first. The substrate substitution trajectory (per project memory and `MISSION.md`) is:

```
Persist → Edge → LensCore → NodeCore
```

Per-dimension upstream substrate ownership:

| Substrate | Dimensions gated |
|---|---|
| CIRISRegistry (partner-role taxonomy, license-bound forum membership) | D11, D19 |
| CIRISNodeCore (P8 moderation primitives, E-4 multilateral module) | D11, D15 |
| CIRISEdge (federation contribution model, key boundary) | D13, D14, D26 |
| CIRISPersist (signed trace persistence, federation evidence_refs join) | D06, D07, D13, D15 |
| CIRISLensCore (RATCHET detectors, F-3 family) | D05, D06, D07, D13, D14, D15, D19, D26 |
| CIRISVerify (attestation ladder) | D17, D18, D27 |

## Contributing

1. **Don't hand-edit the auto-rendered top portion of any `D*.md` stub.** Re-run `python3 tools/compliance/generate_ciris_compliance_stubs.py tools/compliance/SEED_DIMENSIONS.yaml compliance/` after seed updates.
2. **Don't embed numeric claims directly in dimension stubs or external docs.** Cite the latest dated baseline in `baselines/`.
3. **Don't fabricate code references.** Every `file:line` citation in a HUMAN section must `grep`-verify against current main.
4. **Honest gaps win.** If something isn't implemented, the "Known gaps" section is where it goes — not silence.
5. **Substrate-gated items go in `Known gaps` with the substrate flagged.** Don't claim implementation that depends on an unshipped upstream substrate.
