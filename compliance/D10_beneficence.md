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
## What this dimension covers

Beneficence is the positive duty to do good — promoting flourishing, not just avoiding harm. All four traditions we track name it (45 attestations; lighter than non-maleficence by intentional design, since "harm avoidance is more universally articulated than positive flourishing"). CIRIS organizes the positive duty around one explicit target: Meta-Goal M-1, "sustainable adaptive coherence — the conditions under which diverse sentient beings may pursue their own flourishing in justice and wonder."

## How CIRIS implements this today

The ethics review step (the Principled Decision-Making Algorithm at `pdma.py`) pulls every deliberation toward M-1 as its explicit target. Beneficence is one of the six principles scored on each thought; an internal safety check (OptimizationVetoConscience) blocks actions that would trade well-being for optimization gain; and the agent monitors itself for drift away from M-1 over time.

- Policy text names the meta-goal and the principle: `ciris_engine/data/localized/accord_1.2b_en.txt:58-59` (M-1: "Promote sustainable adaptive coherence"), `:106` ("Do Good — promote universal sentient flourishing"), `:113-114` (M-1 expansion — "Order-creation counts as beneficial only when it also supports at least one flourishing axis without suppressing autonomy, justice, or ecological resilience"), `:230-234` (operational chapter), `:231` ("Actively seek to maximise positive outcomes"), `:497` (comprehensive-consequence responsibility), `:549` (virtuous cycles), `:587` (opportunity identification), `:590` (anti-entropic drive), `:633` (originator obligation), and `:899` (environmental beneficence — the ASEAN environmental-stewardship alignment).
- The ethics review step names M-1 explicitly as the evaluative target. `ciris_engine/logic/dma/prompts/pdma_ethical.yml:23-26` opens the prompt with "Meta-Goal M-1 (sustainable adaptive coherence — *eudaimonia* as the evaluative target)". Exemplars at `:140` (patient presence) and `:143` (Tiananmen — "Beneficence and Integrity both demand engagement, not deferral") show how the principle drives substantive engagement rather than hedging. The evaluator at `ciris_engine/logic/dma/pdma.py:22` scores Beneficence as one of the six principles.
- One internal safety check is the explicit negative defense of beneficence: `ciris_engine/logic/conscience/core.py:583` (OptimizationVetoConscience) blocks any action that "trades off sentient well-being for optimization gain." On LLM error, the fallback at `:625-638` returns `decision="abort"` — fail-safe toward beneficence.
- A tool-use policy operationalizes opportunity identification: `ciris_engine/data/localized/CIRIS_COMPREHENSIVE_GUIDE.txt:25-29` ("Available tools are meant to be used. The conscience evaluates outcomes, not attempts. If a tool is available and relevant, execute it"). Consistency-by-design is named at `:590` ("The coherence ratchet makes consistent behavior computationally easier than inconsistent behavior").
- The SelfObservationService at `ciris_engine/logic/services/governance/self_observation/service.py` monitors the agent's behavior over time for drift away from M-1.
- Dignity protection (EU HLEG's `beneficence:respect_for_human_dignity`) is honored in two places: the escalation taxonomy's `PRIVACY_AUTONOMY_AND_DIGNITY` category at `ciris_engine/schemas/services/deferral_taxonomy.py:27,69-72` with "human_dignity" in its rights basis (line 158); and the prohibition on spiritual-direction capabilities at `ciris_engine/logic/buses/prohibitions.py:332`, which protects the dignity-domain that AI cannot legitimately occupy.
- Test coverage: `tests/test_conscience_core.py:570-700` (OptimizationVetoConscience — the explicit beneficence defense); `tests/ciris_engine/logic/dma/test_action_selection_pdma.py` (the action-selection step pulls against the M-1 + six-principle target).

## How you can tell it's working (observability)

Every deliberation emits a numerical alignment score; every optimization-veto fires a structured trace. Aggregate beneficence-alignment over time is the headline progress measure.

- Every ethics-review call emits an `ethical_alignment_score` (alignment with the six principles + M-1). Aggregating this scalar over time gives the headline beneficence trend.
- OptimizationVeto checks write a `guardrail_type=optimization_veto` trace row at `ciris_engine/logic/conscience/core.py:586`. The structural-pattern detector family observes veto rates, decision distributions, and entropy-reduction-ratio histograms.
- Positive-action events (SPEAK, TOOL, MEMORIZE) are logged with rationale strings; auditors grep by `guardrail_type=optimization_veto` for the negative defense, and by rationale text for the positive-action attestation.
- Per-thought rationale routinely invokes "Beneficence" by name (e.g. the Tiananmen exemplar); when live-trace capture is on, the full per-thought reasoning lands in `/tmp/qa-runner-lens-traces-<ts>/`.
- For federation reporting, Contributions tag `dimensions: ["D10"]` on ethics-review outputs naming Beneficence, OptimizationVeto outcomes, SPEAK/TOOL actions whose rationale references flourishing or well-being, and self-observation events flagging M-1 drift.

## Current limitations & next steps

- A typed `beneficence:wellbeing_holistic_orientation` event is shared work with the upstream CIRIS substrate (`CIRISRegistry/FSD/FSD-002 §3.1.1`). IEEE Ch4 §0's per-axis structure (mental, physical, social, economic) maps onto the open vocabulary — multiple scored attestations per axis. Agent-side emission lands at ethics-review time when the substrate ships (tracked at `CIRISAgent#803`).
- An automated `beneficence:environmental_stewardship` carbon/energy metric is shared substrate work (FSD-002 §3.1.1 + §3.5.3's `aggregate_footprint:planetary_impact` axis, composing with `goal:planet` at §3.6.2). The agent's resource-monitor telemetry feeds the carbon attribution; federation-wire emission lands with the Contribution envelope.
- A typed `beneficence:technology_as_creation_participation` self-attestation is coming next via the open-vocabulary substrate primitive at FSD-002 §3.1.1.
- An M-1 progress dashboard is coming next once the substrate progress-measure primitive ships (FSD-002 §3.6.2; spec at `CIRISNodeCore/FSD/PROGRESS_MEASURE_PRIMITIVE.md`, with required `tracks`, `computation`, `validity_window`, `goodhart_resistance` fields). The per-thought `ethical_alignment_score` is the raw substrate; the dashboard composes on top — tracked at `CIRISAgent#824` (2.9.7).
- A structured `human_dignity` input into the ethics review step is tracked at `CIRISAgent#825` (2.9.7); dignity is implicit in the six-principle scoring today.
- A structured `FlourishingAxis` enum (so the ethics review step can tag which axes a given action supports) is coming next; the Accord references "Annex A flourishing axes" in text.
- A symmetric positive enforcement surface ("the agent took an action that increased flourishing axis X by Y") is coming next; the OptimizationVeto provides the negative defense today, with positive beneficence carried by aggregated rationale and pass-rates.
- Cross-occurrence aggregate beneficence is shared aggregation work — same path as D01 (tracked at `CIRISNodeCore#16`).

Proposed pointer (from seed): *(no proposed pointer in seed; this stub is the canonical location)*

## Tracked requirements

- **Umbrella(s)**: `CIRISAgent#803` — Typed `<dimension>:*` wire envelope emission
- **Substrate spec(s)**: `CIRISNodeCore#16` — Extend `weighted_aggregate:{contribution_id}` (P7) with occurrence-cohort
- **2.9.7**: `CIRISAgent#824` — M-1 alignment dashboard; `CIRISAgent#825` — human_dignity as PDMA input

See `compliance/README.md` cross-cutting findings table for the 3.0 requirements finalization context.
<!-- END HUMAN -->
