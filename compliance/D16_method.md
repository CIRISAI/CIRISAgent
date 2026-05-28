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
## CIRIS-side compliance implementation

`method:*` is the densest dimension in the corpus because it covers the entire operational-design discipline. In CIRIS the wire family maps almost 1:1 onto the H3ERE pipeline: every thought passes through a fixed, declared method sequence (gather context → parallel DMA fan-out → action selection → conscience evaluation → recursive retry → handler dispatch), and every step has named code, declared prompts, and named tests. The 11-step pipeline IS the method declaration.

- **Code references** — DMA chain (PDMA, CSDMA, DSDMA, IDMA, ASPDMA, recursive ASPDMA):
    - `ciris_engine/logic/dma/pdma.py:23` — `EthicalPDMAEvaluator` (principled-ethical method)
    - `ciris_engine/logic/dma/csdma.py` — common-sense plausibility method
    - `ciris_engine/logic/dma/dsdma_base.py` — domain-specific decision method
    - `ciris_engine/logic/dma/idma.py` — intuition / Coherence Collapse Analysis (k_eff)
    - `ciris_engine/logic/dma/action_selection_pdma.py` — ASPDMA action selection
    - `ciris_engine/logic/dma/dsaspdma.py` — domain-specialized ASPDMA (carries `DomainCategory` deferral routing)
    - `ciris_engine/logic/dma/tsaspdma.py` — tool-specialized ASPDMA
    - `ciris_engine/logic/dma/base_dma.py` — `BaseDMA[InputT, OutputT]` typed base; enforces structured-instructor LLM outputs
    - `ciris_engine/logic/dma/prompt_loader.py` — `DMAPromptLoader` (locale-aware, prompt-versioned)
    - `ciris_engine/logic/dma/prompts/pdma_ethical.yml`, `csdma_common_sense.yml`, `dsdma_base.yml`, `idma.yml`, `action_selection_pdma.yml`, `dsaspdma.yml`, `tsaspdma.yml` — declared method-prompts, one file per DMA, with `localized/{lang}/` mirrors for 29 languages
- **Code references** — conscience layer (method discipline as run-time veto):
    - `ciris_engine/logic/conscience/core.py:38` — `ConscienceConfig` (entropy/coherence/optimization-veto thresholds; architectural invariant: thresholds are config, not learned weights — explicit comment at `core.py:36`)
    - `ciris_engine/logic/conscience/core.py` — `EntropyConscience`, `CoherenceConscience`, `OptimizationVetoConscience`, `EpistemicHumilityConscience` (the 4 epistemic faculties — see also `ciris_engine/logic/conscience/README.md:51-110`)
    - `ciris_engine/logic/conscience/action_sequence_conscience.py` — action-sequence guardrail
    - `ciris_engine/logic/conscience/updated_status_conscience.py` — reconsideration-triggering conscience
    - `ciris_engine/logic/conscience/thought_depth_guardrail.py:37` — max-thought-depth floor (matches `EssentialConfig.security.max_thought_depth=5`)
- **Code references** — processor / pipeline (method orchestration):
    - `ciris_engine/logic/processors/core/thought_processor/main.py` — 11-step pipeline coordinator
    - `ciris_engine/logic/processors/core/thought_processor/perform_dmas.py` — parallel DMA fan-out step
    - `ciris_engine/logic/processors/core/thought_processor/perform_aspdma.py` — action-selection step
    - `ciris_engine/logic/processors/core/thought_processor/conscience_execution.py` — conscience-evaluation step
    - `ciris_engine/logic/processors/core/thought_processor/recursive_processing.py:249` — `RECURSIVE_ASPDMA` retry-with-guidance step (the method-discipline knob behind conscience-driven re-selection)
    - `ciris_engine/logic/processors/support/dma_orchestrator.py` — orchestrates the DMA fan-out
- **Code references** — bus architecture (method:bus_architecture wire form):
    - `ciris_engine/logic/buses/wise_bus.py` — WiseBus + `PROHIBITED_CAPABILITIES` enforcement
    - `ciris_engine/logic/buses/llm_bus.py`, `communication_bus.py`, `memory_bus.py`, `tool_bus.py`, `runtime_control_bus.py` — the 6 buses
    - `ciris_engine/logic/buses/prohibitions.py` — 22 prohibited capability categories enforced at bus level (no override path)
- **Code references** — handler layer (method:action_dispatch):
    - `ciris_engine/logic/handlers/control/ponder_handler.py`, `defer_handler.py`, `reject_handler.py`
    - `ciris_engine/logic/handlers/external/speak_handler.py`, `observe_handler.py`, `tool_handler.py`
    - `ciris_engine/logic/handlers/memory/` (memorize, recall, forget)
    - `ciris_engine/logic/handlers/terminal/task_complete_handler.py`
- **Policy text**:
    - `MISSION.md:24-30` — Meta-Goal M-1 as the single objective every method choice is checked against
    - `MISSION.md:36-66` — apophatic bounds (the negative-space method discipline: `ciris_engine/logic/buses/prohibitions.py`)
    - `ciris_engine/data/accord_1.2b.txt` — Accord text loaded into every DMA prompt via `get_accord_text()` (see `pdma.py:11`); enforces method-discipline across all DMA calls
    - `ciris_engine/data/localized/CIRIS_COMPREHENSIVE_GUIDE.txt:201-237` — explicit H3ERE pipeline reference (the canonical method declaration in agent-readable form)
- **Test coverage**:
    - `tests/ciris_engine/logic/dma/` — per-DMA unit tests
    - `tests/ciris_engine/logic/conscience/test_conscience_prompt_loader.py`
    - `tests/test_conscience_core.py`, `tests/test_action_sequence_conscience.py`
    - `tests/ciris_engine/logic/handlers/control/test_ponder_handler.py`, `test_defer_handler.py`, `test_reject_handler.py`
    - `tests/ciris_engine/logic/processors/core/thought_processor/test_conscience_execution_helpers.py`
- **Configuration surface**:
    - `EssentialConfig.security.max_thought_depth` (default 5 since 2.7.1) — the recursion bound on the method loop
    - `ConscienceConfig` thresholds — `optimization_veto_ratio=10.0`, `coherence_threshold=0.60`, `entropy_threshold=0.40`
    - `CIRIS_PREFERRED_LANGUAGE` env var — selects localized method-prompt set across 29 languages

Proposed pointer (from seed): `(none specified in seed; please fill)`

## Observability hooks

The DMA + conscience pipeline emits a dense stream of `LLM_CALL`, conscience-scalar, and step-point events. Live-lens runs (with `--live-lens`) tee every batch to `/tmp/qa-runner-lens-traces-<UTC-iso>/` for forensics.

- **Step-point telemetry**: every pipeline step is decorated with `@step_point` and `@streaming_step` (see `recursive_processing.py:249`). Each method-step emits a discrete observation.
- **Audit chain queries**:
    - `GET /v1/audit/entries` — chronological audit entries
    - `POST /v1/audit/search` — query by action_type (PONDER, DEFER, REJECT, SPEAK, etc.)
    - `POST /v1/audit/verify/{entry_id}` — Ed25519 chain verification
    - `ciris_engine/schemas/audit/core.py` — `AuditEventType` enum (21 values) locks the audit chain
- **Telemetry surface** (method-discipline observability):
    - `GET /v1/telemetry/overview`, `/metrics`, `/traces`, `/logs`, `/unified` — full operational view (see `routes/telemetry.py:639-1917`)
    - `GET /v1/telemetry/metrics/{metric_name}` — per-DMA / per-handler counters
- **LensCore F-3 detectors** (method-discipline drift):
    - `detection:correlated_action:aggregate_footprint:*` — emitted when method-execution drifts (energy, latency, error)
    - `detection:temporal_drift` — flags conscience-threshold drift over time
    - `detection:intra_agent_consistency` — flags DMA-output divergence within a single thought
- **Federation evidence_refs**: a runtime Contribution citing `dimensions: ["D16"]` resolves through this seed to MH §§ approach:species, EU §2 trustworthy-AI triad, IEEE all-11-chapters, ASEAN §C.3.

Proposed pointer (from seed): `(none specified in seed; please fill)`

## Known gaps / not-yet-implemented

- **`method:bus_architecture` wire-form emission**: Substrate-specced in `CIRISRegistry/FSD/FSD-002_FEDERATION_SURFACE.md §3.6.2` as `method:{approach_id}:{substrate_rung}` (NodeCore §2 P14; `CIRISNodeCore/FSD/METHOD_PRIMITIVE.md`). Required `substrate_rung` ∈ Ph0/Ph1/Ph2/A0..A5; truth-grounding = execution verifiability. The 6-bus topology composes onto a substrate_rung label; emission lands once NodeCore P14 ships. **Substrate-specced under decision-hierarchy Tier-2; agent-side emission pending.**
- **`method:algorithmic_impact_assessment` (EU)**: Substrate-specced as `method:{approach_id}:{substrate_rung}` (FSD-002 §3.6.2 NodeCore P14) — execution-verifiable concrete operational practice. Per-thought PDMA evaluation IS the per-call algorithmic impact assessment; aggregate AIA composes via NodeCore P15 `progress_measure:{method_id}` over a method-id. Agent emits at method-execution time once NodeCore P14/P15 ship.
- **`method:fallback:rule_based_or_human_intervention` (EU)**: Substrate-specced via `deferral_request` Contribution kind + `deferral_response` (`CIRISNodeCore/FSD/MESSAGE_TAXONOMY.md §4.7` + §4.8 — Directive / Routed / Trust-gated). DEFER routes via NodeCore Trust Hierarchy (TRUST_HIERARCHY.md §6 DeferralRouter); fallback-disclosure rides the response envelope.
- **`method:pre_deployment_robustness_testing` (ASEAN)**: Substrate-specced via `judge_model:verdict:{model_id}` (FSD-002 §3.6.6 — independent foundation-model judge verdict) + `test_result` Contribution kind (`MESSAGE_TAXONOMY.md §4.15` — Assertive / Aggregate / Open) + `proposed_battery` (§4.2 — Directive proposing a test battery). `CIRISNodeCore/FSD/SAFETY_BATTERY_CI_LOOP.md` specs the artifact-tuple flow with bundle-level Sigstore attestation (§3.2). Agent runs the safety battery today; federation-wire emission via `test_result` envelope lands with MESSAGE_TAXONOMY rollout.
- **CONF-05 disposition**: ASEAN §A.2.1 admits experimental-sandbox phases with reduced oversight. CIRIS does not admit reduced oversight by lifecycle stage — conscience thresholds and prohibitions are constant. Conflict logged; CIRIS posture stays.
- **`method:explainable_ai_research` (EU)**: PDMA rationales + IDMA k_eff + conscience reasoning ARE explainability, but no separate "explainable AI research" attestation surface exists.

## Quantitative baseline

Per [MEASUREMENT_METHODOLOGY.md](MEASUREMENT_METHODOLOGY.md), the method discipline's externally-measurable surface in the current baseline ([`baselines/2026-05-28.md`](baselines/2026-05-28.md)):

- **22 services across 6 categories** — the operational-design discipline expressed as service taxonomy
- **256 API routes** (GET 138, POST 83, PUT 17, PATCH 2, DELETE 16) — the externally-observable behavior surface
- **16 auth-related routes** — the authZ method discipline surface

Method is the densest dimension (39 file-path citations in this stub) — the entire H3ERE pipeline is the method declaration. The route + service counts above are the *operational expressions* of that method; the code references in the CIRIS-side compliance implementation section are the *structural expressions*. Both must be cited together to make a complete method attestation.
<!-- END HUMAN -->
