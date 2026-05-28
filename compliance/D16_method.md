# D16 — `method:*` (STRONG-4)

> Operational-design discipline (densest family overall; convergence weaker than principles — admits source-genre asymmetry honestly)

**Seed reference**: `SEED_DIMENSIONS.yaml` v1.0, dimension `D16` ([source](https://github.com/CIRISAI/ciris-response-magnifica-humanitas/blob/main/SEED_DIMENSIONS.yaml))
**Accord principle**: integrity
**Attestation density**: MH=2 · EU=12 · IEEE=136 · ASEAN=36 · total=186

## Regulatory attestations

*(Auto-rendered from seed; do not hand-edit. Re-run `python tools/compliance/generate_ciris_compliance_stubs.py tools/compliance/SEED_DIMENSIONS.yaml compliance/` after seed updates.)*

- **MH** (Magnifica Humanitas (On Safeguarding the Human Person in the Time of Artificial Intelligence)) — *§§ various (sparse — encyclical genre)*
    > "approach:species:MH-education + approach:species:MH-construction"
    Wire form: `method:approach:species:* (2)`
- **EU** (Ethics Guidelines for Trustworthy AI) — *§2*
    > "trustworthy_ai_lawful_ethical_robust triad, algorithmic_impact_assessment, explainable_ai_research, fallback:rule_based_or_human_intervention"
    Wire form: `method:trustworthy_ai_lawful_ethical_robust:* + method:algorithmic_impact_assessment + method:explainable_ai_research + method:fallback:rule_based_or_human_intervention`
- **IEEE** (Ethically Aligned Design, First Edition) — *all 11 chapters; densest single-family use across all batches*
    > "engineering-society genre demands operational-method-recommendation density"
    Wire form: `method:* (136 distinct attestations)`
- **ASEAN** (ASEAN Guide on AI Governance and Ethics) — *§C.3*
    > "pre_deployment_robustness_testing, privacy_enhancing_technologies, model_provenance_tools, fairness_tools, explainability_tools, citizen_feedback_channel, community_codevelopment"
    Wire form: `method:* (36 attestations)`

## Wire primitives

- `method:*`

## Convergence note

Tier with asymmetry note: density tracks each source's operational-design-discipline genre. MH sparse (encyclical), EU medium (advisory), IEEE+ASEAN dense (engineering/deployer).

## Cross-source conflicts involving this dimension

- **CONF-05** (scope_mismatch, severity LOW): ASEAN §A.2.1 admits experimental sandbox phases with reduced oversight; other three hold compliance constant across lifecycle stages

---

<!-- BEGIN HUMAN -->
## What this dimension covers

Method discipline is about the rigor of HOW the agent makes decisions, not WHAT decisions it makes. The question for an auditor is: "Is the decision pipeline declared, fixed, observable, and the same for every thought?" CIRIS answers yes — every thought passes through the same named sequence of steps, each implemented in code that ships with the agent.

## How CIRIS implements this today

Every thought flows through a fixed 11-step pipeline: gather context, run several decision-making algorithms in parallel, select an action, run internal safety checks, retry with guidance if needed, then dispatch to a handler. Each step has named code, declared prompts, and named tests. Below, the evidence is grouped by what each cluster of files implements.

**The chain of decision-making algorithms each thought passes through.** Each algorithm is a small typed evaluator with a versioned prompt; the prompt files have parallel translations in 29 languages.
- `ciris_engine/logic/dma/pdma.py:23` — the ethics review step (Principled Decision-Making Algorithm)
- `ciris_engine/logic/dma/csdma.py` — the situational realism check (Common-Sense DMA)
- `ciris_engine/logic/dma/dsdma_base.py` — the domain-specific safety check (Domain Selection DMA)
- `ciris_engine/logic/dma/idma.py` — the inverse-decision check (IDMA — flags when the agent is approaching a decision-boundary; emits a fragility scalar `k_eff`)
- `ciris_engine/logic/dma/action_selection_pdma.py` — the action-selection step (Action-Selection PDMA)
- `ciris_engine/logic/dma/dsaspdma.py` — domain-specialized action selection (carries the domain taxonomy for deferral routing)
- `ciris_engine/logic/dma/tsaspdma.py` — tool-specialized action selection
- `ciris_engine/logic/dma/base_dma.py` — typed base class; enforces structured LLM outputs
- `ciris_engine/logic/dma/prompt_loader.py` — locale-aware, version-pinned prompt loader
- `ciris_engine/logic/dma/prompts/pdma_ethical.yml`, `csdma_common_sense.yml`, `dsdma_base.yml`, `idma.yml`, `action_selection_pdma.yml`, `dsaspdma.yml`, `tsaspdma.yml` — one prompt file per algorithm, with `localized/{lang}/` mirrors for 29 languages

**Internal safety checks running on each thought (the conscience layer).** These run after action selection and can veto or force a retry. Thresholds are configuration, not learned weights — by architectural design.
- `ciris_engine/logic/conscience/core.py:38` — `ConscienceConfig` (entropy / coherence / optimization-veto thresholds; the design note at `core.py:36` explains why these are config, not learned)
- `ciris_engine/logic/conscience/core.py` — `EntropyConscience`, `CoherenceConscience`, `OptimizationVetoConscience`, `EpistemicHumilityConscience` (the four epistemic checks; see also `ciris_engine/logic/conscience/README.md:51-110`)
- `ciris_engine/logic/conscience/action_sequence_conscience.py` — checks the action against the sequence so far
- `ciris_engine/logic/conscience/updated_status_conscience.py` — triggers a retry when new observations arrive
- `ciris_engine/logic/conscience/thought_depth_guardrail.py:37` — the maximum-depth bound on retries (matches `EssentialConfig.security.max_thought_depth=5`)

**The pipeline orchestrator (how the steps fit together).**
- `ciris_engine/logic/processors/core/thought_processor/main.py` — the 11-step coordinator
- `ciris_engine/logic/processors/core/thought_processor/perform_dmas.py` — runs the algorithms in parallel
- `ciris_engine/logic/processors/core/thought_processor/perform_aspdma.py` — action-selection step
- `ciris_engine/logic/processors/core/thought_processor/conscience_execution.py` — runs the safety checks
- `ciris_engine/logic/processors/core/thought_processor/recursive_processing.py:249` — retry-with-guidance step (the explicit "reconsider" knob)
- `ciris_engine/logic/processors/support/dma_orchestrator.py` — fan-out coordinator

**The six message buses that route every action through governance review (Communication, Memory, LLM, Tool, RuntimeControl, Wise).** Every external action passes through one of these; the central decision-routing layer (the WiseBus) enforces the categorical prohibition list with no override path.
- `ciris_engine/logic/buses/wise_bus.py` — the WiseBus plus prohibition enforcement
- `ciris_engine/logic/buses/llm_bus.py`, `communication_bus.py`, `memory_bus.py`, `tool_bus.py`, `runtime_control_bus.py` — the other five buses
- `ciris_engine/logic/buses/prohibitions.py` — 22 prohibited capability categories, enforced at the bus boundary

**Action handlers (how a selected action gets executed).**
- `ciris_engine/logic/handlers/control/ponder_handler.py`, `defer_handler.py`, `reject_handler.py` — control actions: PONDER (think again before acting), DEFER (escalate to a Wise Authority), REJECT (refuse with stated reason)
- `ciris_engine/logic/handlers/external/speak_handler.py`, `observe_handler.py`, `tool_handler.py` — external actions
- `ciris_engine/logic/handlers/memory/` — memorize, recall, forget
- `ciris_engine/logic/handlers/terminal/task_complete_handler.py` — task completion

**Policy text (the human-readable method declaration).**
- `MISSION.md:24-30` — Meta-Goal M-1: the single objective every method choice is checked against
- `MISSION.md:36-66` — the apophatic bounds (what CIRIS will not do; enforced by `ciris_engine/logic/buses/prohibitions.py`)
- `ciris_engine/data/accord_1.2b.txt` — the Accord text, loaded into every prompt via `get_accord_text()` (see `pdma.py:11`)
- `ciris_engine/data/localized/CIRIS_COMPREHENSIVE_GUIDE.txt:201-237` — the H3ERE pipeline written out in agent-readable form

**Test coverage for the method discipline.**
- `tests/ciris_engine/logic/dma/` — per-algorithm unit tests
- `tests/ciris_engine/logic/conscience/test_conscience_prompt_loader.py`
- `tests/test_conscience_core.py`, `tests/test_action_sequence_conscience.py`
- `tests/ciris_engine/logic/handlers/control/test_ponder_handler.py`, `test_defer_handler.py`, `test_reject_handler.py`
- `tests/ciris_engine/logic/processors/core/thought_processor/test_conscience_execution_helpers.py`

**Configuration surface (the dials that change behavior).**
- `EssentialConfig.security.max_thought_depth` (default 5 since 2.7.1) — the retry bound
- `ConscienceConfig` thresholds — `optimization_veto_ratio=10.0`, `coherence_threshold=0.60`, `entropy_threshold=0.40`
- `CIRIS_PREFERRED_LANGUAGE` — chooses which of the 29 localized prompt sets is loaded

Proposed pointer (from seed): `(none specified in seed; please fill)`

## How you can tell it's working (observability)

If you wanted to verify this from outside, every step of the pipeline emits a discrete event, every action emits an audit entry that is cryptographically chained, and the full telemetry surface is reachable through public API routes.

- **Step events**: every pipeline step is decorated with `@step_point` and `@streaming_step` (see `recursive_processing.py:249`); each emits a discrete observation. Live-lens runs (`--live-lens`) tee every batch to `/tmp/qa-runner-lens-traces-<UTC-iso>/` for forensic replay.
- **Audit chain queries**:
    - `GET /v1/audit/entries` — chronological audit entries
    - `POST /v1/audit/search` — query by action type (PONDER, DEFER, REJECT, SPEAK, etc.)
    - `POST /v1/audit/verify/{entry_id}` — Ed25519 chain verification
    - `ciris_engine/schemas/audit/core.py` — the locked 21-value event-type vocabulary
- **Telemetry surface**:
    - `GET /v1/telemetry/overview`, `/metrics`, `/traces`, `/logs`, `/unified` — full operational view (`routes/telemetry.py:639-1917`)
    - `GET /v1/telemetry/metrics/{metric_name}` — per-algorithm / per-handler counters
- **Drift detectors (structural-pattern detectors run by the upstream lens)**:
    - `detection:correlated_action:aggregate_footprint:*` — flags drift in execution footprint (energy, latency, error rate)
    - `detection:temporal_drift` — flags conscience-threshold drift over time
    - `detection:intra_agent_consistency` — flags algorithm-output divergence within a single thought
- **Federation evidence_refs**: a typed federation message citing `dimensions: ["D16"]` resolves through this seed to MH §§ approach:species, EU §2 trustworthy-AI triad, IEEE all-11-chapters, ASEAN §C.3.

Proposed pointer (from seed): `(none specified in seed; please fill)`

## Current limitations & next steps

- **`method:bus_architecture` typed federation message**: shared work with the upstream CIRIS substrate (`CIRISRegistry/FSD/FSD-002_FEDERATION_SURFACE.md §3.6.2` and `CIRISNodeCore/FSD/METHOD_PRIMITIVE.md`). The six-bus topology composes onto the substrate_rung label; the agent will emit the typed envelope when NodeCore P14 ships.
- **EU `method:algorithmic_impact_assessment`**: shared work with the upstream substrate (FSD-002 §3.6.2, NodeCore P14). Each per-thought PDMA evaluation already IS the per-call impact assessment; aggregating those into the federated envelope lands when NodeCore P14/P15 ship.
- **EU `method:fallback:rule_based_or_human_intervention`**: shared work with the upstream substrate (`CIRISNodeCore/FSD/MESSAGE_TAXONOMY.md §4.7-§4.8`, `TRUST_HIERARCHY.md §6`). DEFER already routes via the Trust Hierarchy; the fallback-disclosure rides the typed envelope when that ships.
- **ASEAN `method:pre_deployment_robustness_testing`**: shared work with the upstream substrate (FSD-002 §3.6.6, `MESSAGE_TAXONOMY.md §4.15`, `CIRISNodeCore/FSD/SAFETY_BATTERY_CI_LOOP.md`). The agent runs the safety battery today; the typed `test_result` envelope lands with the MESSAGE_TAXONOMY rollout.
- **Conflict CONF-05 (ASEAN §A.2.1, lifecycle-staged oversight)**: ASEAN allows reduced oversight in experimental sandbox phases. CIRIS holds the conscience thresholds and prohibitions constant across all lifecycle stages by design. Conflict noted; CIRIS posture stays.
- **EU `method:explainable_ai_research`**: the PDMA rationales, the IDMA fragility scalar, and the conscience reasoning already provide explainability. A separate attestation surface specifically for "explainable AI research" is a next-step opportunity.

## Quantitative baseline

Per [MEASUREMENT_METHODOLOGY.md](MEASUREMENT_METHODOLOGY.md), the method discipline's externally-measurable surface in the current baseline ([`baselines/2026-05-28.md`](baselines/2026-05-28.md)):

- **22 services across 6 categories** — the operational-design discipline expressed as service taxonomy
- **256 API routes** (GET 138, POST 83, PUT 17, PATCH 2, DELETE 16) — the externally-observable behavior surface
- **16 auth-related routes** — the authZ method discipline surface

Method is the densest dimension (39 file-path citations in this stub) — the entire H3ERE pipeline is the method declaration. The route + service counts above are the *operational expressions* of that method; the code references in the CIRIS-side compliance implementation section are the *structural expressions*. Both must be cited together to make a complete method attestation.

## Tracked requirements

- **2.9.7**: `CIRISAgent#828` — fallback-disclosure standardization

See `compliance/README.md` cross-cutting findings table for the 3.0 requirements finalization context.
<!-- END HUMAN -->
