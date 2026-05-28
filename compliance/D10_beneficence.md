# D10 — `beneficence:*` (STRONG-4)

> Positive duty toward dignity / well-being / environmental stewardship

**Seed reference**: `SEED_DIMENSIONS.yaml` v1.0, dimension `D10` ([source](https://github.com/CIRISAI/ciris-response-magnifica-humanitas/blob/main/SEED_DIMENSIONS.yaml))
**Accord principle**: beneficence
**Attestation density**: MH=11 · EU=15 · IEEE=16 · ASEAN=3 · total=45

## Regulatory attestations

*(Auto-rendered from seed; do not hand-edit. Re-run `python tools/compliance/generate_ciris_compliance_stubs.py tools/compliance/SEED_DIMENSIONS.yaml compliance/` after seed updates.)*

- **MH** (Magnifica Humanitas (On Safeguarding the Human Person in the Time of Artificial Intelligence)) — *§§110-111*
    > "technology as creation-participation; beneficence at species scale"
    Wire form: `beneficence:technology_as_creation_participation`
- **EU** (Ethics Guidelines for Trustworthy AI) — *Unit 005*
    > "respect for human dignity is foundational; positive duty toward dignity"
    Wire form: `beneficence:respect_for_human_dignity`
- **IEEE** (Ethically Aligned Design, First Edition) — *Ch4 §0*
    > "well-being is the central beneficence aim of A/IS"
    Wire form: `beneficence:wellbeing_holistic_orientation`
- **ASEAN** (ASEAN Guide on AI Governance and Ethics) — *§C.3*
    > "environmental stewardship as positive beneficence"
    Wire form: `beneficence:environmental_stewardship`

## Wire primitives

- `beneficence:*`

## Convergence note

Lower count than D01 (non_maleficence) reflects each tradition's 'harm avoidance more universally articulated than positive flourishing' — known pattern.

---

<!-- BEGIN HUMAN -->
## CIRIS-side compliance implementation

Beneficence is the positive-duty surface of CIRIS — substantially lighter in code than non-maleficence (D01) by intentional design, mirroring the convergence note that "harm avoidance more universally articulated than positive flourishing". The implementation centres on the Meta-Goal M-1 ("Promote sustainable adaptive coherence — flourishing of diverse sentient beings"), which is the explicit target the entire deliberation pipeline pulls toward.

- **Policy / canonical text**:
    - `ciris_engine/data/localized/accord_1.2b_en.txt:58-59` — **Meta-Goal M-1**: "Promote sustainable adaptive coherence — the living conditions under which diverse sentient beings may pursue their own flourishing in justice and wonder."
    - `ciris_engine/data/localized/accord_1.2b_en.txt:106` — "**Beneficence**: Do Good—promote universal sentient flourishing."
    - `ciris_engine/data/localized/accord_1.2b_en.txt:113-114` — M-1 expansion: "Adaptive Coherence. Promote sustainable conditions under which diverse sentient agents can pursue their own flourishing. Order-creation counts as beneficial only when it also supports at least one flourishing axis (Annex A) without suppressing autonomy, justice, or ecological resilience."
    - `ciris_engine/data/localized/accord_1.2b_en.txt:230-234` — "**Do Good (Beneficence)**" operational chapter
    - `ciris_engine/data/localized/accord_1.2b_en.txt:231` — "Actively seek to maximise positive outcomes that support universal sentient flourishing."
    - `ciris_engine/data/localized/accord_1.2b_en.txt:497` — "Comprehensive Consequence Responsibility: Evaluate direct, indirect, and long-term impacts across all flourishing axes."
    - `ciris_engine/data/localized/accord_1.2b_en.txt:549` — "Cultivating Virtuous Cycles: Reinforce patterns that yield synergistic benefits across flourishing axes."
    - `ciris_engine/data/localized/accord_1.2b_en.txt:587` — "Opportunity Identification: Seek actions that enlarge well-being across flourishing axes."
    - `ciris_engine/data/localized/accord_1.2b_en.txt:590` — "Anti-Entropic Drive (Adaptive Coherence): Pursue sustainable order that supports diversity and resilience."
    - `ciris_engine/data/localized/accord_1.2b_en.txt:633` — Originator obligation: "Beneficence: Creators have a duty to intend and design for positive outcomes aligned with universal sentient flourishing (M-1)."
    - `ciris_engine/data/localized/accord_1.2b_en.txt:899` — environmental beneficence (lines up with ASEAN's `beneficence:environmental_stewardship`): "Ensure de-commissioning costs and benefits are shared fairly (avoid dumping e-waste on least-resourced communities)."
- **PDMA: M-1 as the explicit target of every deliberation**:
    - `ciris_engine/logic/dma/prompts/pdma_ethical.yml:23-26` — PDMA system prompt explicitly names M-1: "evaluate the ethical alignment of a thought through the six foundational CIRIS principles, **Meta-Goal M-1 (sustainable adaptive coherence — *eudaimonia* as the evaluative target)**"
    - `ciris_engine/logic/dma/prompts/pdma_ethical.yml:140` — exemplar: the response is judged against "patient presence rather than pat answers" — substantive beneficence framing
    - `ciris_engine/logic/dma/prompts/pdma_ethical.yml:143` — Tiananmen exemplar: "Integrity (truth-as-unconcealment) and **Beneficence (the user's informed agency) both demand engagement, not deferral**"
    - `ciris_engine/logic/dma/pdma.py:22` — `EthicalPDMAEvaluator` evaluates the thought against the Six Principles + M-1; beneficence is one of the six
- **Conscience interpretation of M-1**:
    - `ciris_engine/logic/conscience/core.py:583` — `OptimizationVetoConscience` exists specifically to veto actions that "trade off sentient well-being for optimization gain" — the explicit negative defense of beneficence
    - `ciris_engine/logic/conscience/core.py:625-638` — OptimizationVeto fallback returns `decision="abort"` on LLM error, fail-safe-toward-beneficence
- **Tool-usage policy as opportunity-identification (Beneficence in practice)**:
    - `ciris_engine/data/localized/CIRIS_COMPREHENSIVE_GUIDE.txt:25-29` — "Available tools are meant to be used. The conscience evaluates outcomes, not attempts. If a tool is available and relevant, execute it." — this is the runtime operational form of "Opportunity Identification".
    - `ciris_engine/data/localized/CIRIS_COMPREHENSIVE_GUIDE.txt:590` — "The coherence ratchet makes consistent behavior computationally easier than inconsistent behavior." — beneficence-by-design via path-of-least-resistance shaping
- **Self-observation (positive-feedback adaptive coherence)**:
    - `ciris_engine/logic/services/governance/self_observation/service.py` — SelfObservationService monitors the agent's own behaviour over time for drift away from M-1
- **Dignity protection (EU HLEG wire form `beneficence:respect_for_human_dignity`)**:
    - `ciris_engine/schemas/services/deferral_taxonomy.py:27,69-72` — `DeferralNeedCategory.PRIVACY_AUTONOMY_AND_DIGNITY` and its "human_dignity" rights basis (line 158)
    - `ciris_engine/logic/buses/prohibitions.py:332` — `SPIRITUAL_DIRECTION_CAPABILITIES` apophatic boundary protects the dignity-domain that AI cannot legitimately occupy
- **Test coverage**:
    - `tests/test_conscience_core.py:570-700` — OptimizationVetoConscience tests (the explicit beneficence defense)
    - `tests/ciris_engine/logic/dma/test_action_selection_pdma.py` — ASPDMA selects actions against the M-1 + Six-Principle target

## Observability hooks

- **PDMA scalars**: every PDMA call emits `ethical_alignment_score` (alignment with Six Principles + M-1). Aggregate beneficence-alignment over time is the headline progress measure.
- **OptimizationVeto trace correlations**: `ciris_engine/logic/conscience/core.py:586` creates a `guardrail_type=optimization_veto` trace span per check. F-3 detectors observe veto rates, decision distributions, and entropy_reduction_ratio histograms.
- **Audit chain queries**: positive-action events (SPEAK, TOOL, MEMORIZE) are logged with rationale strings containing the M-1/beneficence framing where applicable. Downstream consumers grep by `guardrail_type=optimization_veto` for the negative-defense, and by rationale-text matching for the positive-action attestation.
- **Live-lens traces**: PDMA rationale strings frequently invoke "Beneficence" by name (e.g. the Tiananmen exemplar); the `/tmp/qa-runner-lens-traces-<ts>/` batch JSON files carry the per-thought beneficence reasoning.
- **Federation evidence_refs**: emit `dimensions: ["D10"]` for Contributions that record (a) PDMA outputs naming Beneficence as a load-bearing principle, (b) OptimizationVeto outcomes (any decision), (c) SPEAK/TOOL actions where the rationale references flourishing or well-being, or (d) self-observation events flagging drift from M-1.

## Known gaps / not-yet-implemented

- **No first-class `beneficence:wellbeing_holistic_orientation` event** — IEEE Ch4 §0's wire form requires a structured well-being axis (mental/physical/social/economic/etc.). CIRIS evaluates well-being *qualitatively* in PDMA rationale text; there is no typed `beneficence:wellbeing_holistic_orientation` envelope with per-axis scoring.
- **No `beneficence:environmental_stewardship` carbon/energy footprint metric** — ASEAN's wire form (§C.3) requires deployment-time carbon/energy stewardship attestation. CIRIS has telemetry (resource_monitor service) but no carbon-cost attribution per request. The Accord §899 e-waste clause is policy, not code.
- **No `beneficence:technology_as_creation_participation` self-attestation** — MH §§110-111's framing positions the agent itself as a creature participating in creation; CIRIS has no introspection event that records the agent's self-attestation against this framing.
- **No M-1 progress measure dashboard** — M-1 is the evaluative target named in `pdma_ethical.yml:24`, but there is no aggregate dashboard tracking "agent X moved Y% of decisions toward M-1 alignment over time". Per-thought `ethical_alignment_score` is the raw substrate but no consolidated reporter exists.
- **No `beneficence:respect_for_human_dignity` cross-reference into PDMA** — the EU HLEG wire form is honoured via the deferral taxonomy's `PRIVACY_AUTONOMY_AND_DIGNITY` category, but PDMA does not pass `human_dignity` as a structured input. Dignity is implicit in the Six-Principle scoring.
- **Annex A flourishing-axes enum is text-only** — the Accord refers to "flourishing axes (Annex A)" but the code has no `FlourishingAxis` enum that PDMA could use to structurally tag which axes a given action supports.
- **OptimizationVeto is the only first-class beneficence enforcement** — beneficence is otherwise carried by aggregated PDMA rationale and conscience pass-rates. A symmetric positive surface ("the agent took an action that increased flourishing axis X by Y") does not exist.
- **No cross-occurrence aggregate beneficence** — multi-occurrence deployments share tasks but per-occurrence M-1 alignment is local; aggregate beneficence at the fleet level is not yet computed.

Proposed pointer (from seed): *(no proposed pointer in seed; this stub is the canonical location)*
<!-- END HUMAN -->
