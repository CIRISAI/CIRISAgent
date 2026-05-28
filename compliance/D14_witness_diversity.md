# D14 — `witness_diversity:*` (STRONG-4)

> Stakeholder pluralism in design/testing/consultation

**Seed reference**: `SEED_DIMENSIONS.yaml` v1.0, dimension `D14` ([source](https://github.com/CIRISAI/ciris-response-magnifica-humanitas/blob/main/SEED_DIMENSIONS.yaml))
**Accord principle**: justice
**Attestation density**: MH=3 · EU=3 · IEEE=16 · ASEAN=2 · total=24

## Regulatory attestations

*(Auto-rendered from seed; do not hand-edit. Re-run `python tools/compliance/generate_ciris_compliance_stubs.py tools/compliance/SEED_DIMENSIONS.yaml compliance/` after seed updates.)*

- **MH** (Magnifica Humanitas (On Safeguarding the Human Person in the Time of Artificial Intelligence)) — *§§ various*
    > "signs-of-times-contribution + catholicity"
    Wire form: `witness_diversity:signs_of_times + witness_diversity:catholicity`
- **EU** (Ethics Guidelines for Trustworthy AI) — *§III.7*
    > "stakeholder consultation + testing red teams + stakeholder panels"
    Wire form: `witness_diversity:stakeholder_consultation + witness_diversity:red_team + witness_diversity:stakeholder_panel`
- **IEEE** (Ethically Aligned Design, First Edition) — *Ch7, Ch9 (16 distinct values)*
    > "ubuntu_five_moral_domains, intercultural_RI_dialogue, end_user_target_community_consultation, affected_population_metric_selection, ..."
    Wire form: `witness_diversity:{16 distinct values}`
- **ASEAN** (ASEAN Guide on AI Governance and Ethics) — *§C.4*
    > "user testing varied backgrounds; stakeholder impact assessment"
    Wire form: `witness_diversity:user_testing_varied_backgrounds + witness_diversity:stakeholder_impact_assessment`

## Wire primitives

- `witness_diversity:*`

## Convergence note

IEEE saturation reflects engineering-society methodology density.

---

<!-- BEGIN HUMAN -->
## CIRIS-side compliance implementation

`witness_diversity:*` is the stakeholder-pluralism dimension: design / testing / consultation must include diverse witness perspectives, not a single voice. On CIRISAgent this composes through three primitives:

1. 29-locale localization that mechanically forces the agent to operate in the user's native ethical-reasoning frame.
2. WiseBus multi-provider wisdom architecture that aggregates advice from multiple wisdom sources.
3. The polyglot accord that anchors ACCORD reasoning across multiple traditions simultaneously.

**29-language pipeline localization (the diversity mechanism)**
- `CLAUDE.md` § "Localization" documents 29 languages reaching ~95% of the world's population.
- `localization/manifest.json` is the source of truth.
- Per-language ACCORD at `ciris_engine/data/localized/accord_1.2b_{lang}.txt`.
- Per-language Comprehensive Guide at `ciris_engine/data/localized/CIRIS_COMPREHENSIVE_GUIDE_{lang}.txt`.
- Per-language DMA prompts at `ciris_engine/logic/dma/prompts/localized/{lang}/*.yml`.
- Auto-detection via `get_preferred_language()` (`ciris_engine/logic/utils/localization.py`) at `CIRIS_PREFERRED_LANGUAGE` env var; referenced from `ciris_engine/logic/dma/idma.py:108`, `ciris_engine/logic/dma/csdma.py:120`, `ciris_engine/logic/dma/action_selection_pdma.py:268`.
- This is the agent's per-thought witness-diversity primitive: ethical reasoning happens in the witness's own language, against their tradition's framing.

**Polyglot accord (multi-tradition anchoring)**
- `ciris_engine/data/accord_1.2b_POLYGLOT.txt` and the compressed variants (`accord_1.2b_POLYGLOT_compressed_v1.txt`, `accord_1.2b_POLYGLOT_compressed_v2.txt`) anchor cross-tradition framing simultaneously rather than translating from a single base.
- Per user-memory `feedback_polyglot_artifacts_universal`: polyglot artifacts must load universally, never duplicate per-locale (per-locale mirrors silently shadow the base).
- The base polyglot accord is the single load-bearing artifact; uplift discipline checks `localized/{lang}/` before promotion.

**Multi-tradition framing in CIRIS_COMPREHENSIVE_GUIDE**
- `ciris_engine/data/localized/CIRIS_COMPREHENSIVE_GUIDE.txt:370,372` explicitly invokes African (Akan / Yoruba / Bantu — `sunsum`, `okra` / `ori`, `nkrabea`) and Islamic (`ayah`, `tafsir`) framings of artifact and authority.
- This is the witness_diversity primitive for the spiritual-direction apophatic bound — multiple traditions are jointly witnessed, not collapsed into a single authoritative framing.
- Aboriginal song-line / Dreaming framings appear at `ciris_engine/logic/buses/prohibitions.py:349-353` as part of the same multi-tradition witness invocation.

**WiseBus multi-provider wisdom (multi-provider witness aggregation)**
- `ciris_engine/logic/buses/wise_bus.py:40-50` `WiseBus` supports multiple WA service providers; `GuidanceResponse.advice: Optional[List[WisdomAdvice]]` (`ciris_engine/logic/services/governance/wise_authority/README.md:99,106-112`) carries multi-provider advice aggregation.
- Per WA service README §"Wisdom Extension System": diverse wisdom providers can contribute to a single guidance response.
- `WisdomAdvice.provider_type` (audio | geo | sensor | policy | vision) tags the witness type; `WisdomAdvice.capability` carries the per-provider capability claim.

**Adaptive filter preserves anonymous voice**
- `ciris_engine/logic/services/governance/adaptive_filter/README.md:13-23` filters spam without filtering anonymous accountability.
- Witness diversity in the consent-stream sense: anonymous users retain voice. Hash-based tracking (`adaptive_filter/README.md:39`) preserves witness shape without unmasking.

**Stewardship tier as multi-perspective scope**
- `ciris_engine/logic/buses/wise_bus.py:114-145` Tier 4-5 stewardship agents serve communities under additional WA oversight; the tier-gate is the structural reflection of "more witness-diverse contexts require more diverse oversight."

**Test coverage**
- Localization paths tested via `tools/qa_runner` (`python -m tools.qa_runner streaming` with `CIRIS_PREFERRED_LANGUAGE=am`).
- Anonymous-witness filter tested in `tests/test_anonymous_filter.py`.
- Multi-tradition CSDMA realism in `tests/ciris_engine/logic/services/adaptation/test_self_observation.py`.
- Per-locale prompt validity verified during prompt-loader initialization (`ciris_engine/logic/dma/prompt_loader.py`).

Proposed pointer (from seed): `(none specified in seed; please fill)` — agent-side implementation is the 29-locale pipeline + polyglot accord + WiseBus multi-provider; consult `CLAUDE.md` § Localization.

## Observability hooks

- **Localization audit** — `get_preferred_language()` (`ciris_engine/logic/utils/localization.py` referenced from `ciris_engine/logic/dma/idma.py:108`, `ciris_engine/logic/dma/csdma.py:120`) records which language the agent reasoned in for each thought; this is signed into the audit chain alongside the PDMA result.
- **WiseBus advice aggregation log** — `GuidanceResponse.advice` carries each provider's contribution (`ciris_engine/logic/services/governance/wise_authority/README.md:99`); the `WisdomAdvice.provider_type` (audio | geo | sensor | policy | vision) tags the witness type.
- **Audit chain per-language coverage query** — `GraphAuditService.log_event` records the locale on every signed event; downstream verifier can compute the language / tradition distribution of the agent's reasoning corpus.
- **Live-lens trace stream** — per `tools/qa_runner/CLAUDE.md`, when `--live-lens` is on, every locale-tagged DMA reasoning event ships in `accord-batch-*.json`. The "rest of 29 inherit the discipline" pattern (user-memory `feedback_tier0_primer_strategy`) is verified by sampling per-locale traces.
- **F-3 detector adjacency** — D05 family `detection:correlated_action:participation_exclusion:underrepresented_population` is the upstream CIRISLens detector that catches systematic witness-diversity gaps. RATCHET temporal-drift detector catches witness composition shifts over time.
- **Federation evidence_refs** — `evidence_refs.dimensions = ["D14"]` not yet emitted on the wire; agent emits per-thought locale + multi-provider advice data; federation-side citation is downstream substrate work.

## Known gaps / not-yet-implemented

- **No structural enforcement that diverse witnesses are actually consulted.** Substrate-specced as `witness_diversity:{contribution_id}` in `CIRISRegistry/FSD/FSD-002_FEDERATION_SURFACE.md §3.6.3` (NodeCore §2 P10; §4.9 `WitnessSet`); witness set must meet **jurisdictional + organizational + software-stack + cell-expertise bars** with N=3 default. Polarity = boolean-via-score. This is the federation-side gate that catches "agent ran all day with one provider" — a Contribution that fails the N=3 witness-diversity gate cannot be admitted at FSD-002 Admit stage (`CIRISNodeCore/FSD/CONTRIBUTION_LIFECYCLE.md §5` Admit gates). Agent emits per-thought locale + multi-provider advice data; the gate fires substrate-side. Agent-side per-call witness diversity self-monitoring is a complementary unfilled gap.
- **`witness_diversity:{value}` enum is not modeled.** Substrate-specced as a per-axis bar (jurisdictional + organizational + software-stack + cell-expertise) rather than as a value-enum at FSD-002 §3.6.3 / NodeCore P10. IEEE's 16 distinct values (`ubuntu_five_moral_domains`, `intercultural_RI_dialogue`, `end_user_target_community_consultation`, …) map to the cell-expertise + organizational + jurisdictional bars rather than to a value-enum on the wire. Agent emits the structural-evidence data (locale, provider, jurisdiction); the bar check is NodeCore-side P10 logic.
- **Substrate gate: CIRISLens (D05 detector family).** Substrate-specced in FSD-002 §3.5.1 as five Coherence-Ratchet detectors + §3.5.3 `detection:correlated_action:{axis}` (F-3 structural-injustice handle), with `participation_exclusion:{cohort}` axis directly addressing witness-diversity gaps. Per §4.6, RATCHET flags cannot be sole evidence for slashing — WA quorum is the load-bearing gate. Agent will keep emitting per-thought locale + provider data; lens decides whether the macro-distribution is plural via `detection:correlated_action:participation_exclusion:underrepresented_population`.
- **Substrate gate: CIRISEdge (multi-provider verify-then-aggregate).** Per user-memory `project_substrate_substitution_trajectory`, Edge is step 2 of the Rust-crate swap. Verify-at-edge for multi-provider WisdomAdvice arrays uses Edge §1.5 multi-medium reachability (FSD-002 §3.4 `transport:medium:{medium}`) + Edge §4 `send_durable` ACK match (`delivery:durable_ack`). Post-Edge agents witness-aggregate at trace-emission time with provenance per Edge medium.
- **Translation quality is unreliable below a quality bar.** Per user-memory `feedback_subagent_translation_unreliable` (Burmese-class word-salad in 5/28 locales): structural prefix-checks miss semantic-quality failures. Without a native-language audit pipeline, 29-locale "diversity" can shade into "29 broken translations." Tier-0 primer-hardening (am / ha / yo) is partial mitigation; closure requires native-audit infrastructure not yet in CIRISAgent.
- **No `red_team` consultation primitive (EU §III.7).** Stakeholder red-teaming as a consultation kind has no agent-side runtime hook — it lives in the SDLC (operator-side QA process), not in runtime witness aggregation.
- **Sub-agent translation cannot be trusted to render bad-pattern examples.** Per user-memory `feedback_priming_aware_primer` — primer prompts must render abstract descriptions only, never verbatim bad-pattern examples. The CIRISAgent localization pipeline complies but is not formally checked.
<!-- END HUMAN -->
