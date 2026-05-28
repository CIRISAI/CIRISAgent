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
## What this dimension covers

Design, testing, and consultation should hear from multiple distinct sources, not a single voice (having multiple distinct sources weigh in — witness diversity). Twenty-four attestations across MH, EU, IEEE, and ASEAN treat stakeholder pluralism as a justice requirement; IEEE alone names sixteen distinct diversity values, reflecting engineering-society depth in this area.

## How CIRIS implements this today

Witness diversity at runtime is built into the agent through three concrete mechanisms: a 29-language pipeline that lets the agent reason in the user's native ethical frame, a multi-provider wisdom architecture that aggregates advice from several sources before responding, and a polyglot Accord that anchors reasoning across multiple traditions simultaneously rather than translating from a single base.

**29-language pipeline: reasoning happens in the witness's own language and tradition.** This is the most concrete diversity primitive in the agent.
- `CLAUDE.md` § "Localization" documents the 29 languages, reaching about 95% of the world's population.
- Source of truth: `localization/manifest.json`.
- Per-language Accord: `ciris_engine/data/localized/accord_1.2b_{lang}.txt`.
- Per-language Comprehensive Guide: `ciris_engine/data/localized/CIRIS_COMPREHENSIVE_GUIDE_{lang}.txt`.
- Per-language decision prompts: `ciris_engine/logic/dma/prompts/localized/{lang}/*.yml`.
- Language is auto-detected via `get_preferred_language()` (`ciris_engine/logic/utils/localization.py`) and threaded through the decision pipeline at `ciris_engine/logic/dma/idma.py:108`, `ciris_engine/logic/dma/csdma.py:120`, and `ciris_engine/logic/dma/action_selection_pdma.py:268`.

**Polyglot Accord: multi-tradition anchoring without a privileged base language.** Rather than translating from English, the polyglot variant anchors several traditions simultaneously.
- The polyglot Accord lives at `ciris_engine/data/accord_1.2b_POLYGLOT.txt`, with compressed variants `accord_1.2b_POLYGLOT_compressed_v1.txt` and `_v2.txt`.
- Discipline rule: a single load-bearing artifact, no per-locale mirrors that could silently shadow the base.

**Multi-tradition framing in the Comprehensive Guide.** The Guide explicitly invokes multiple traditions for the most contested concepts.
- `ciris_engine/data/localized/CIRIS_COMPREHENSIVE_GUIDE.txt:370,372` invokes African (Akan, Yoruba, Bantu — `sunsum`, `okra` / `ori`, `nkrabea`) and Islamic (`ayah`, `tafsir`) framings of artifact and authority.
- Aboriginal song-line / Dreaming framings appear at `ciris_engine/logic/buses/prohibitions.py:349-353`.
- This is the diversity primitive paired with the spiritual-direction apophatic bound: multiple traditions are jointly witnessed rather than collapsed into one.

**Multi-provider wisdom aggregation.** The wisdom-routing layer supports several providers contributing to a single response.
- `ciris_engine/logic/buses/wise_bus.py:40-50` is the multi-provider entry point.
- `GuidanceResponse.advice: Optional[List[WisdomAdvice]]` (`ciris_engine/logic/services/governance/wise_authority/README.md:99,106-112`) carries the aggregated advice.
- `WisdomAdvice.provider_type` tags each contribution by source kind (audio, geo, sensor, policy, vision); `WisdomAdvice.capability` carries the per-provider capability claim.

**Adaptive filter preserves anonymous voice.** Spam is filtered without filtering anonymous accountability.
- `ciris_engine/logic/services/governance/adaptive_filter/README.md:13-23` is the filter contract.
- Hash-based tracking (`adaptive_filter/README.md:39`) preserves the witness's shape without unmasking the speaker.

**Stewardship tier as a more-diverse-oversight floor.** Tier 4-5 stewardship agents (the agent's level of authorization — stewardship tier) serve communities under additional Wise Authority oversight — the tier gate at `ciris_engine/logic/buses/wise_bus.py:114-145` reflects "more witness-diverse contexts require more diverse oversight."

**Tests covering this behaviour:**
- Localisation paths via `tools/qa_runner` (`python -m tools.qa_runner streaming` with `CIRIS_PREFERRED_LANGUAGE=am`).
- Anonymous-witness filter: `tests/test_anonymous_filter.py`.
- Multi-tradition common-sense realism: `tests/ciris_engine/logic/services/adaptation/test_self_observation.py`.
- Per-locale prompt validity is verified during prompt-loader initialization (`ciris_engine/logic/dma/prompt_loader.py`).

Proposed pointer (from seed): `(none specified in seed; please fill)` — agent-side implementation is the 29-locale pipeline + polyglot Accord + multi-provider wisdom; consult `CLAUDE.md` § Localization.

## How you can tell it's working (observability)

If you want to verify witness diversity is alive in production, here's what to check.

- **Per-thought language tag.** `get_preferred_language()` records the language used for each thought; it's signed into the audit chain alongside the reasoning result.
- **Multi-provider advice log.** `GuidanceResponse.advice` carries each provider's contribution (`ciris_engine/logic/services/governance/wise_authority/README.md:99`); the `WisdomAdvice.provider_type` tags the source kind.
- **Per-language coverage query.** The audit chain records locale on every signed event, so the language and tradition distribution of the agent's reasoning corpus is computable.
- **Live reasoning stream.** When live-lens tracing is on, every locale-tagged reasoning event ships in `accord-batch-*.json`. Per-locale sampling verifies the "discipline inherited across 29 locales" pattern.
- **Upstream participation-exclusion detector.** The structural-pattern detector (`detection:correlated_action:participation_exclusion:underrepresented_population`) catches systematic witness-diversity gaps. Lives in CIRISLens; agent emits the data.
- **Federation citation by ID.** Per-thought locale and multi-provider advice data is already emitted; the federation-wire citation (`evidence_refs.dimensions = ["D14"]`) lands with the upstream substrate work.

## Current limitations & next steps

The agent already produces rich per-thought diversity data; the remaining work is the upstream witness-set gate that turns this data into a structural admission test.

- **Witness-set diversity gate is upstream.** The federation surface defines `witness_diversity:{contribution_id}` (`CIRISRegistry/FSD/FSD-002_FEDERATION_SURFACE.md §3.6.3`, NodeCore §2 P10; §4.9 `WitnessSet`) with a four-axis bar (jurisdictional, organisational, software-stack, cell-expertise) and a default minimum of N=3. A Contribution that fails the bar can't be admitted (`CIRISNodeCore/FSD/CONTRIBUTION_LIFECYCLE.md §5` Admit gates). Agent emits per-thought locale and multi-provider data; the gate fires substrate-side. Shared roadmap with NodeCore.
- **Self-monitoring of witness diversity per agent.** The agent doesn't yet self-flag when it has been running with a single provider all day. Tracked at [CIRISAgent#827](https://github.com/CIRISAI/CIRISAgent/issues/827).
- **`witness_diversity:{value}` is axis-shaped, not enum-shaped.** IEEE's 16 distinct values (`ubuntu_five_moral_domains`, `intercultural_RI_dialogue`, `end_user_target_community_consultation`, …) map to the four-axis bar (jurisdictional, organisational, software-stack, cell-expertise) rather than to a wire enum. Agent emits the structural-evidence inputs; the bar check is NodeCore-side.
- **Upstream Coherence-Ratchet detectors.** The five Coherence-Ratchet detectors (FSD-002 §3.5.1) and the participation-exclusion axis (§3.5.3) are the macro-pattern check. Per §4.6 these flags can't be sole evidence for downstream consequences — Wise Authority quorum remains the load-bearing gate. Agent keeps emitting per-thought data; the macro check is shared work with CIRISLens.
- **Multi-provider verify-then-aggregate is part of step 2 of the substrate trajectory.** Edge's multi-medium reachability (FSD-002 §3.4, `transport:medium:{medium}`) and durable-ack delivery (Edge §4) become the verify-at-edge layer for multi-provider advice arrays. Post-Edge, agents witness-aggregate at trace-emit time with per-medium provenance.
- **Native-language audit pipeline.** Sub-agent translation has been unreliable in a handful of low-resource locales; without a native-language audit pass, "29 languages" can risk shading into "29 unverified translations." Tier-0 primer-hardening (Amharic, Hausa, Yoruba) is partial mitigation. Native-audit infrastructure is tracked at [CIRISAgent#813](https://github.com/CIRISAI/CIRISAgent/issues/813).
- **Red-team consultation is operator-side, not agent-runtime.** EU §III.7's red-team consultation kind lives in the operator's SDLC rather than as a runtime witness primitive.
- **Bad-pattern rendering discipline is informal.** Primer prompts must render abstract descriptions rather than verbatim bad-pattern examples; the agent complies but doesn't yet check this structurally.

## Tracked requirements

- **Umbrella(s)**: `CIRISEdge#37` — key_boundary + named-witness wire + witness aggregation
- **2.9.6**: `CIRISAgent#813` — native-language audit pipeline
- **2.9.7**: `CIRISAgent#827` — witness diversity self-monitor

See `compliance/README.md` cross-cutting findings table for the 3.0 requirements finalization context.
<!-- END HUMAN -->
