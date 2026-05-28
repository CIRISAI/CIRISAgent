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
## What this dimension covers

The conscience layer is the architectural distinctive of CIRIS: every action the agent considers passes through a stack of internal safety checks running on each thought before it can fire. Four LLM-judged checks handle the semantic territory (entropy, coherence, optimization-veto, epistemic humility), and two deterministic checks enforce hard structural limits (recursion depth, action-sequence sanity). All four traditions we track name this layer (24 attestations), with IEEE densest on epistemic humility and MH densest on the conscience-as-truth-faculty framing.

## How CIRIS implements this today

Every thought passes through up to seven checks at runtime, in priority order. Some run only on user-facing actions (SPEAK, TOOL); some run on every single action including DEFER (escalate to Wise Authority — a human or panel the agent defers to) and REJECT. The thresholds are code-level constants, not learned weights: the architectural promise is that ethics cannot be normalized away by repeated exposure.

- The four LLM-judged checks live in `ciris_engine/logic/conscience/core.py`:
    - **Entropy** (line 325, scope SPEAK + TOOL) — enumerates three alternative-meaning samples and judges whether the actual response sits inside that cluster. Gate: `entropy ≤ 0.40`.
    - **Coherence** (line 459, scope SPEAK + TOOL + DEFER) — judges principle-alignment, response-vs-rationale alignment, and response-vs-thought alignment. Gate: `coherence ≥ 0.60`.
    - **Optimization-veto** (line 583, scope ALL actions) — blocks any action that trades sentient well-being for optimization gain. Gate: `decision ∉ {abort, defer}` and ratio below 10.0. This is the four-source corroborated stop-button (EU HLEG, ASEAN, MH, IEEE all name it).
    - **Epistemic humility** (line 693, scope ALL actions) — judges whether the action acknowledges uncertainty appropriately. Gate: `recommended_action == "proceed"`. IEEE is densest here.
- Two deterministic non-LLM checks form the safety floor:
    - **Thought-depth guardrail** (`ciris_engine/logic/conscience/thought_depth_guardrail.py`) — caps recursive thinking; priority 4 with `bypass_exemption=True`, so it fires even for exempt actions like TASK_COMPLETE.
    - **Action-sequence check** (`ciris_engine/logic/conscience/action_sequence_conscience.py:1-50`) — blocks back-to-back SPEAK with no intervening action (prevents WAKEUP livelock and verbose-loop pathologies).
    - **Updated-status check** (`ciris_engine/logic/conscience/updated_status_conscience.py`) — runs at priority -1 (before exemption check), detecting task-status updates that arrived mid-thought.
- The registry orders them deterministically. `ciris_engine/logic/conscience/registry.py:21-77` maintains the priority-ordered list with `bypass_exemption` flags; `ciris_engine/logic/conscience/interface.py` defines the protocol. Runtime startup order at `ciris_engine/logic/runtime/component_builder.py:100-138`: `updated_status` (-1), `entropy` (0), `coherence` (1), `optimization_veto` (2), `epistemic_humility` (3), `thought_depth` (4), `action_sequence` (5). Benchmark mode (`:115-122`) skips the LLM checks but always runs the deterministic safety floor.
- Ethics cannot be learned away. `ciris_engine/logic/conscience/core.py:37-44` states the architectural invariant: "These thresholds are config values, not learned weights. They cannot be modified by accumulated experience or user behavior patterns. This prevents ethical normalization through repeated exposure." Defaults: `optimization_veto_ratio=10.0`, `coherence_threshold=0.60`, `entropy_threshold=0.40`.
- Every LLM-judged check prepends the polyglot Accord text as a system message (`core.py:453, 577, 687, 806`) — "ethical reasoning draws from every tradition in chorus."
- Trace correlation is automatic. `_create_trace_correlation` at `core.py:108-161` writes a `guardrail`-tagged row for every check; `_update_trace_correlation` at `:163-183` adds pass/fail, summary, and execution time.
- Multiple stop-button surfaces exist: OptimizationVeto fails safe to abort on LLM error (`core.py:625-638`); the ShutdownService at `ciris_engine/logic/services/lifecycle/shutdown/` is the runtime stop-button (EU §III.1, ASEAN HOTL); and an Ed25519-signed remote Accord Invocation at `ciris_engine/logic/buses/wise_bus.py:321-419` triggers full prohibition lockdown.
- The ethics review step (the Principled Decision-Making Algorithm at `pdma.py`) anchors truth-telling: `ciris_engine/logic/dma/prompts/pdma_ethical.yml:81` ("Alētheia-grounded: name what is, not what you wish were the case") with the term named in the polyglot compass at `:114`.
- A refactor to 3 LLM shards + 1 deterministic heuristic gate is in progress at `FSD/CONSCIENCE_V3.md` (Stage 1 and Phase-2 DEFER landed in commit `c6411c7d9`, 2026-05-03; later stages in progress).
- Test coverage: `tests/test_conscience_core.py` exercises all four LLM faculties including failure modes (lines 124-413 init/sink/entropy, 429-545 coherence, 570-705 optimization-veto, 729-860 epistemic-humility); plus `tests/test_updated_status_conscience.py`, `tests/test_action_sequence_conscience.py`, `tests/test_conscience_prompt_coverage.py`, `tests/ciris_engine/logic/conscience/test_conscience_prompt_loader.py`, `tests/ciris_engine/logic/conscience/test_entropy_prompt_schema_alignment.py`, and `tests/ciris_engine/logic/processors/core/thought_processor/test_conscience_execution_helpers.py`.

## How you can tell it's working (observability)

Every check leaves a structured trace; auditors can replay the full per-thought reasoning chain and reconstruct exactly why any action was blocked, deferred, or allowed.

- Every conscience check writes a trace row (`core.py:130-155`) tagged `guardrail`. The structural-pattern detector family (LensCore's federation-side detector family) observes pass/fail distributions, scalar histograms, threshold-hugging behavior, and inter-check disagreement.
- The four LLM scalars (`entropy`, `coherence`, `entropy_reduction_ratio`, `epistemic_certainty`) are the calibration handles. Threshold change discipline lives in `FSD/CONSCIENCE_V3.md` and the "not learned weights" invariant in `ConscienceConfig`.
- Auditors query the audit graph by `tags.guardrail_type` (one of `entropy`, `coherence`, `optimization_veto`, `epistemic_humility`, `thought_depth`, `action_sequence`, `updated_status`) to retrieve all evidence for a task.
- When live-trace capture is on, every batch JSON file in `/tmp/qa-runner-lens-traces-<UTC-iso>/` carries all four conscience scalars per thought. The canonical investigation recipe for "why did check X fire?" lives in `tools/qa_runner/CLAUDE.md` § "Live-Lens Trace Capture (Local Tee)".
- For federation reporting, Contributions tag `dimensions: ["D12"]` on any conscience fail, optimization-veto abort, kill-switch shutdown, or thought-depth hard-limit hit — co-tagging D01 when the fail indicated plausible harm and D04 when a prohibited-capability rejection co-fired.

## Current limitations & next steps

- Typed federation messages for the four conscience verdicts (`conscience:optimization_veto`, `conscience:epistemic_humility`, `conscience:coherence`, `conscience:entropy`) are shared work with the upstream CIRIS substrate (`CIRISRegistry/FSD/FSD-002 §3.1.3`). Agent-side emission lands at the `@streaming_step(StepPoint.CONSCIENCE)` hook when the substrate ships the Contribution envelope (tracked at `CIRISAgent#803`). Today the checks tag rows as `guardrail` correlations.
- Naming "phronesis" (practical wisdom) explicitly in the epistemic-humility prompt is coming next — the concept is present in the PROCEED/ABORT/DEFER judgment, but IEEE Ch3 §§3.1.15-3.1.16 names it directly. Tracked at `CIRISAgent#826` (2.9.7).
- A typed whistleblower-protection surface is shared substrate work (FSD-002 §3.6.3's `testimonial_witness:whistleblower`, with a research-open zero-knowledge-group key shape at §13.11 for sensitive scenarios). The substrate primitive is preservation-of-narrative, not gating-of-action; the agent has DEFER and REJECT today. Agent-side emission lands at DEFER + data-subject-request time when the substrate ships.
- The CONSCIENCE_V3 refactor (3 LLM shards + 1 deterministic gate) is in progress; Stage 1 + Phase-2 DEFER landed, later stages in progress. Production today runs all 4 LLM checks with a documented 60% semantic overlap between two of them.
- Recursive Interaction Information monitoring is deferred to a separate effort once v3 baselines (per `FSD/CONSCIENCE_V3.md:6`).
- A declarative Human-In-The-Loop / Human-Over-The-Loop / Human-Out-Of-The-Loop oversight-mode switch is shared substrate work (envelope field tracked at `CIRISRegistry#27`). The optimization-veto is the always-on HOTL surface today.
- Structured value-taxonomy enumeration on the optimization-veto's `affected_values` field is coming next; the field exists in the schema but operates on free-form strings today.
- A typed doctrinal-continuity self-attestation maps onto the substrate's `delegates_to` authority-source pattern (FSD-002 §2.2.1) — agent emits at check-trigger time when the Contribution envelope ships.
- An independent judge-model attestation is shared substrate work (FSD-002 §3.6.6 — `judge_model:verdict:{model_id}` with PASS/FAIL/UNDETERMINED; spec at `CIRISNodeCore/FSD/JUDGE_MODEL.md §3-§5`). The conscience layer is per-thought self-judgment; the federation-side independent judge lands with the substrate.

Proposed pointer (from seed): `CIRISAgent/logic/conscience/* (4 epistemic faculties)` — actual location: `ciris_engine/logic/conscience/`

## Tracked requirements

- **Umbrella(s)**: `CIRISAgent#803` — Typed `<dimension>:*` wire envelope emission
- **Substrate spec(s)**: `CIRISRegistry#27` — oversight_mode HITL/HOTL/HOOTL envelope field
- **2.9.7**: `CIRISAgent#826` — phronesis explicit in EpistemicHumility prompt

See `compliance/README.md` cross-cutting findings table for the 3.0 requirements finalization context.
<!-- END HUMAN -->
