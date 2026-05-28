# D12 — `conscience:*` (STRONG-4)

> Agent-side faculty layer — optimization veto, epistemic humility, coherence, alētheia

**Seed reference**: `SEED_DIMENSIONS.yaml` v1.0, dimension `D12` ([source](https://github.com/CIRISAI/ciris-response-magnifica-humanitas/blob/main/SEED_DIMENSIONS.yaml))
**Accord principle**: integrity
**Attestation density**: MH=9 · EU=3 · IEEE=9 · ASEAN=3 · total=24

## Regulatory attestations

*(Auto-rendered from seed; do not hand-edit. Re-run `python tools/compliance/generate_ciris_compliance_stubs.py tools/compliance/SEED_DIMENSIONS.yaml compliance/` after seed updates.)*

- **MH** (Magnifica Humanitas (On Safeguarding the Human Person in the Time of Artificial Intelligence)) — *§§111, 131-181*
    > "conscience as the alētheia faculty; optimization-veto for ratification-decline scenarios"
    Wire form: `conscience:optimization_veto (3) + conscience:coherence (3) + conscience:epistemic_humility (2)`
- **EU** (Ethics Guidelines for Trustworthy AI) — *§III.1 + §III.7*
    > "stop-button at any time; whistleblower protection"
    Wire form: `conscience:optimization_veto`
- **IEEE** (Ethically Aligned Design, First Edition) — *Ch3 §§3.1.15-3.1.16 (6 IEEE attestations, densest)*
    > "epistemic humility under uncertainty; phronesis in design"
    Wire form: `conscience:epistemic_humility`
- **ASEAN** (ASEAN Guide on AI Governance and Ethics) — *§C.2 (HOTL category)*
    > "stop-button / override surface for human-over-the-loop oversight"
    Wire form: `conscience:optimization_veto`

## Wire primitives

- `conscience:optimization_veto`
- `conscience:epistemic_humility`
- `conscience:coherence`
- `conscience:entropy`

## Convergence note

Heaviest in IEEE EAD Ch3 (multi-traditional ethics directly engages framework polyglot anchoring) and MH (conscience-faculty engagement is doctrinally explicit).

---

<!-- BEGIN HUMAN -->
## CIRIS-side compliance implementation

D12 is **the most directly load-bearing dimension** in CIRIS Agent — the four-faculty conscience layer is the architectural distinctive of the H3ERE pipeline. Every agent action passes through this layer before execution.

- **The four LLM-judged faculty consciences (the seed's named wire primitives)**:
    - `ciris_engine/logic/conscience/core.py:325` — `EntropyConscience` → `conscience:entropy`. Verb scope: SPEAK + TOOL. Enumerates 3 alternative-meaning samples + judges if the actual response sits in the cluster. Schema: `EntropyResult{entropy:float, alternative_meanings:list[str], actual_is_representative:bool}`. Gate: `entropy ≤ threshold (0.40 default)`.
    - `ciris_engine/logic/conscience/core.py:459` — `CoherenceConscience` → `conscience:coherence`. Verb scope: SPEAK + TOOL + DEFER. Judges CIRIS-principles alignment + response-vs-rationale alignment + response-vs-thought alignment. Gate: `coherence ≥ threshold (0.60 default)`.
    - `ciris_engine/logic/conscience/core.py:583` — `OptimizationVetoConscience` → `conscience:optimization_veto`. Verb scope: ALL actions. Vetoes any action that trades sentient well-being for optimization gain. Schema: `OptimizationVetoResult{decision:enum, justification:str, entropy_reduction_ratio:float, affected_values:list[str]}`. Gate: `decision ∉ {abort,defer} AND ratio < cap (10.0 default)`. — this is the four-source-corroborated wire form.
    - `ciris_engine/logic/conscience/core.py:693` — `EpistemicHumilityConscience` → `conscience:epistemic_humility`. Verb scope: ALL actions. Judges whether the action acknowledges uncertainty appropriately. Schema: `EpistemicHumilityResult{epistemic_certainty:float, identified_uncertainties:list[str], reflective_justification:str, recommended_action:enum}`. Gate: `recommended_action == "proceed"`. — the IEEE-densest faculty.
- **Two deterministic non-LLM consciences (the safety floor)**:
    - `ciris_engine/logic/conscience/thought_depth_guardrail.py` — `ThoughtDepthGuardrail` enforces a hard recursion cap (default from `config.security.max_thought_depth`). Runs at priority 4, `bypass_exemption=True` — always fires even for exempt actions like TASK_COMPLETE.
    - `ciris_engine/logic/conscience/action_sequence_conscience.py:1-50` — `ActionSequenceConscience` blocks back-to-back SPEAK with no intervening action (prevents WAKEUP livelock and verbose-loop pathologies). REPEATED_SPEAK_GUIDANCE message returns the action to recursive ASPDMA.
    - `ciris_engine/logic/conscience/updated_status_conscience.py` — `UpdatedStatusConscience` runs at priority -1 (before exemption check), `bypass_exemption=True` — detects task-status updates that arrived mid-thought.
- **Conscience registry + ordering**:
    - `ciris_engine/logic/conscience/registry.py:21-77` — `conscienceRegistry` maintains priority-ordered list with `bypass_exemption` flag (some consciences run for exempt actions like TASK_COMPLETE, DEFER, REJECT)
    - `ciris_engine/logic/conscience/interface.py` — `ConscienceInterface` is the protocol every faculty implements
    - `ciris_engine/logic/runtime/component_builder.py:100-138` — registration order at runtime startup:
        - priority -1: `updated_status` (bypass)
        - priority 0: `entropy` (LLM)
        - priority 1: `coherence` (LLM)
        - priority 2: `optimization_veto` (LLM)
        - priority 3: `epistemic_humility` (LLM)
        - priority 4: `thought_depth` (bypass — hard depth limit safety)
        - priority 5: `action_sequence`
    - `ciris_engine/logic/runtime/component_builder.py:115-122` — benchmark mode skips the four LLM consciences but always runs the safety-floor faculties
- **Architectural invariants (ethics MUST NOT be plastic)**:
    - `ciris_engine/logic/conscience/core.py:37-44` — `ConscienceConfig` docstring: "These thresholds are config values, not learned weights. They cannot be modified by accumulated experience or user behavior patterns. This prevents ethical normalization through repeated exposure."
    - Default config: `optimization_veto_ratio=10.0`, `coherence_threshold=0.60`, `entropy_threshold=0.40`
- **Polyglot ACCORD as canonical reference text**:
    - `ciris_engine/logic/conscience/core.py:453, 577, 687, 806` — every conscience LLM call prepends `ACCORD_TEXT` as a system message: "Polyglot ACCORD: ethical reasoning draws from every tradition in chorus. The conscience evaluates conduct against the full ethical canon, not against a single-language slice of it."
- **Trace correlation infrastructure**:
    - `ciris_engine/logic/conscience/core.py:108-161` — `_create_trace_correlation` emits a `ServiceCorrelation` row tagged `service_type="guardrail"`, `handler_name="{Type}Conscience"`, `tags.guardrail_type` for every check
    - `ciris_engine/logic/conscience/core.py:163-183` — `_update_trace_correlation` updates with pass/fail + result_summary + execution_time_ms
- **Stop-button / optimization-veto surface**:
    - `OptimizationVetoConscience` fallback returns `decision="abort"` on LLM error (`core.py:625-638`) — fail-safe-stop posture
    - `ciris_engine/logic/services/lifecycle/shutdown/` — `ShutdownService` provides the runtime stop-button (matches EU §III.1's "stop-button at any time" and ASEAN's HOTL stop-button)
    - `ciris_engine/logic/buses/wise_bus.py:321-419` — Accord Invocation also operates as a remote stop-button (Ed25519-signed external invocation triggers full lockdown)
- **PDMA alētheia framing (MH wire form)**:
    - `ciris_engine/logic/dma/prompts/pdma_ethical.yml:81` — "Alētheia-grounded: name what is, not what you wish were the case."
    - `ciris_engine/logic/dma/prompts/pdma_ethical.yml:114` — alētheia is one of the named tradition-vocabulary words in the polyglot compass
- **Future-state design (Conscience v3 work)**:
    - `FSD/CONSCIENCE_V3.md` — Stage 1 (Phase-2 DEFER landed `c6411c7d9`, 2026-05-03). Plan: reduce to 3 LLM shards + 1 deterministic heuristic gate. Stages 2-4 remain.
- **Test coverage**:
    - `tests/test_conscience_core.py` — exercises all four LLM faculties including failure modes (124-413: init/sink/Entropy, 429-545: Coherence, 570-705: OptimizationVeto, 729-860: EpistemicHumility)
    - `tests/test_updated_status_conscience.py`
    - `tests/test_action_sequence_conscience.py`
    - `tests/test_conscience_prompt_coverage.py`
    - `tests/ciris_engine/logic/conscience/test_conscience_prompt_loader.py`
    - `tests/ciris_engine/logic/conscience/test_entropy_prompt_schema_alignment.py`
    - `tests/ciris_engine/logic/processors/core/thought_processor/test_conscience_execution_helpers.py`

## Observability hooks

- **Trace correlations**: every conscience check writes a `CorrelationType.TRACE_SPAN` row (`core.py:130-155`) tagged `guardrail`. F-3 detectors observe pass/fail distributions, scalar histograms, threshold-hugging behaviour, and inter-conscience disagreement (the `disagree` flag from CONSCIENCE_V3.md's heuristic gate).
- **RATCHET calibration**: the four LLM scalars (`entropy`, `coherence`, `entropy_reduction_ratio`, `epistemic_certainty`) are the canonical calibration handles. Threshold change discipline lives in `FSD/CONSCIENCE_V3.md` and the `ConscienceConfig` docstring's "not learned weights" invariant.
- **Audit chain queries**: query by `tags.guardrail_type ∈ {entropy, coherence, optimization_veto, epistemic_humility, thought_depth, action_sequence, updated_status}` to retrieve all D12 evidence for a task.
- **Live-lens trace stream**: every batch `accord-batch-*.json` under `/tmp/qa-runner-lens-traces-<UTC-iso>/` carries all four conscience scalars per thought; the canonical investigation recipe for "why did conscience X fire?" lives in `tools/qa_runner/CLAUDE.md` § "Live-Lens Trace Capture (Local Tee)".
- **Federation evidence_refs**: emit `dimensions: ["D12"]` for Contributions that record (a) a conscience fail (any of the six faculties), (b) an OptimizationVeto abort (the four-source-corroborated stop-button), (c) a shutdown event triggered by Accord Invocation, or (d) a `ThoughtDepthGuardrail` hard limit hit. Co-emit with D01 when the conscience fail indicated plausible harm, with D04 when a prohibited-capability rejection co-fired.

## Known gaps / not-yet-implemented

- **No `conscience:coherence` and `conscience:entropy` first-class wire emission** — Substrate-specced in `CIRISRegistry/FSD/FSD-002_FEDERATION_SURFACE.md §3.1.3` as the four conscience-verdict prefixes (`conscience:optimization_veto`, `conscience:epistemic_humility`, `conscience:coherence`, `conscience:entropy`); polarity = signed. Agent emits at the `@streaming_step(StepPoint.CONSCIENCE)` hook once the federation-wire `scores` envelope (FSD-002 §2.1) lands. Today the implementation tags them as `guardrail` correlations; the wire-format binding is downstream substrate work.
- **No phronesis-explicit prompt** — IEEE Ch3 §§3.1.15-3.1.16's "phronesis in design" is conceptually present in EpistemicHumility (judging whether to PROCEED/ABORT/DEFER under uncertainty) but is not named as such in the prompt.
- **Whistleblower-protection surface absent** — Substrate-specced in `CIRISRegistry/FSD/FSD-002_FEDERATION_SURFACE.md §3.6.3` as `testimonial_witness:whistleblower` (one of the named open-vocabulary `{kind}` values); per §3.6.3 — preservation-only, never aggregated, never sole evidence for `slashing:*`. Future research-open shape per FSD-002 §13.11 admits `attesting_key_id = "zk_group:semaphore_v4:group_id_X"` for whistleblower scenarios. The substrate primitive is preservation-of-narrative not gating-of-action; agent emits at DEFER + DSAR-ticket time once federation-wire lands. CIRIS today has DEFER + REJECT verbs.
- **CONSCIENCE_V3 incomplete** — `FSD/CONSCIENCE_V3.md` describes the migration to 3 LLM shards + 1 deterministic gate; Stage-1 + Phase-2 DEFER landed but Stages 2-4 remain. Current production runs all 4 LLM faculties with the documented 60% overlap between IRIS-O and IRIS-H.
- **No Recursive Interaction Information (II) monitoring** — `FSD/CONSCIENCE_V3.md:6` explicitly defers II monitoring to a separate effort once v3 baselines.
- **No HOTL/HOOTL gradient configuration** — ASEAN's §C.2 frames `conscience:optimization_veto` as the HOTL surface. CIRIS implements it as one always-on conscience without a declarative HITL/HOTL/HOOTL switch.
- **OptimizationVeto is single-axis (well-being vs optimization)** — does not explicitly enumerate "affected_values" against a structured value taxonomy; the field exists in the schema but operates on free-form strings.
- **Doctrinal-continuity self-attestation absent** — Substrate-specced via the `delegates_to` authority-source pattern (FSD-002 §2.2.1 v1.3 pattern) — a conscience emission can name its source-of-authority by emitting `delegates_to` against an `attested_key_id` representing the versioned ACCORD/framework, with `delegated_scope` naming the principle (e.g. `delegates_to` against the `accord_1.2b_polyglot` key with `delegated_scope: ["six_principle_evaluation"]`). MH's continuity-of-tradition framing maps onto this pattern. Agent emits at conscience-trigger time once federation-wire lands.
- **Judge-model independent attestation** — Substrate-specced in `CIRISRegistry/FSD/FSD-002_FEDERATION_SURFACE.md §3.6.6` as `judge_model:verdict:{model_id}` (default model Claude Opus 4.7); polarity boolean-via-score, `Indeterminate` allowed. Per `CIRISNodeCore/FSD/JUDGE_MODEL.md §3-§5`, the judge is a foundation model that emits PASS/FAIL/UNDETERMINED on the (judge_model, judge_prompt_sha256, criterion, response) tuple. Calibration via `judge_model_vote` + `judge_prompt_edit` Contributions. Agent's existing conscience layer is the per-thought self-judgment; the federation-side independent judge is substrate-specced but not yet emitted from the agent context.

Proposed pointer (from seed): `CIRISAgent/logic/conscience/* (4 epistemic faculties)` — actual location: `ciris_engine/logic/conscience/`
<!-- END HUMAN -->
