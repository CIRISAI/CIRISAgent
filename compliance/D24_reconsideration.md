# D24 — `reconsideration:*` (STRONG-3)

> Reverse-axis appeal / rollback / negotiation-reopening primitive

**Seed reference**: `SEED_DIMENSIONS.yaml` v1.0, dimension `D24` ([source](https://github.com/CIRISAI/ciris-response-magnifica-humanitas/blob/main/SEED_DIMENSIONS.yaml))
**Accord principle**: integrity
**Attestation density**: MH=3 · EU=2 · IEEE=1 · ASEAN=0 · total=6

**Absent from**: ASEAN — Forward-looking 2024 document with no formal predecessor to reconsider.

## Regulatory attestations

*(Auto-rendered from seed; do not hand-edit. Re-run `python tools/compliance/generate_ciris_compliance_stubs.py tools/compliance/SEED_DIMENSIONS.yaml compliance/` after seed updates.)*

- **MH** (Magnifica Humanitas (On Safeguarding the Human Person in the Time of Artificial Intelligence)) — *§§ various*
    > "doctrinal development through reconsideration"
    Wire form: `reconsideration:* (3 attestations)`
- **EU** (Ethics Guidelines for Trustworthy AI) — *§III + §C*
    > "redress mechanisms; ability to challenge and rectify"
    Wire form: `reconsideration:*`
- **IEEE** (Ethically Aligned Design, First Edition) — *Ch4*
    > "rollback on wellbeing reduction"
    Wire form: `reconsideration:rollback_on_wellbeing_reduction`

## Wire primitives

- `reconsideration:{grounds}`

---

<!-- BEGIN HUMAN -->
## CIRIS-side compliance implementation

`reconsideration:*` is one of the most concretely implemented dimensions in CIRIS. The reverse-axis appeal / rollback / negotiation-reopening primitive is the canonical PONDER action — bounded by `max_thought_depth` to prevent infinite reconsideration. The H3ERE pipeline's `RECURSIVE_ASPDMA` step is the explicit "retry with conscience guidance" reconsideration loop, and `UpdatedStatusConscience` is the explicit "new observation requires reconsideration" trigger.

- **Code references** — PONDER handler (the canonical reconsideration action):
    - `ciris_engine/logic/handlers/control/ponder_handler.py:17` — `PonderHandler`
    - `ciris_engine/logic/handlers/control/ponder_handler.py:30` — `max_rounds` configuration (default 5 since 2.7.1)
    - `ciris_engine/schemas/actions/parameters.py` — `PonderParams.questions: List[str]` — the reconsideration grounds
    - `ciris_engine/schemas/runtime/enums.py:62` — `HandlerActionType.PONDER`
- **Code references** — RECURSIVE_ASPDMA (reconsideration loop):
    - `ciris_engine/logic/processors/core/thought_processor/recursive_processing.py:249-251` — `_recursive_aspdma_step` decorated `@streaming_step(StepPoint.RECURSIVE_ASPDMA)` and `@step_point(StepPoint.RECURSIVE_ASPDMA)`
    - `ciris_engine/logic/processors/core/thought_processor/recursive_processing.py:117` — `_handle_recursive_processing` (entry point)
    - `ciris_engine/logic/processors/core/thought_processor/recursive_processing.py:212` — `retry_result = await self._recursive_aspdma_step(thought_item, thought_context, dma_results, current_conscience)`
    - `ciris_engine/logic/processors/core/thought_processor/recursive_processing.py:113` — comment: "RECURSIVE_ASPDMA: Retry action selection with conscience guidance"
- **Code references** — Thought-depth guardrail (the reconsideration bound):
    - `ciris_engine/logic/conscience/thought_depth_guardrail.py:37` — depth bound (matches `EssentialConfig.security.max_thought_depth=5`)
    - `ciris_engine/data/localized/CIRIS_COMPREHENSIVE_GUIDE.txt:276` — "Each task has a hard limit of 7 processing rounds" (note: 5 in current EssentialConfig; doc lags)
- **Code references** — UpdatedStatusConscience (new-observation-triggered reconsideration):
    - `ciris_engine/logic/conscience/updated_status_conscience.py:26` — `UpdatedStatusConscience`
    - `ciris_engine/logic/conscience/updated_status_conscience.py:160` — `rationale="Updated status detected - new observation in channel requires reconsideration"` — the explicit reconsideration trigger
- **Code references** — TSASPDMA tool-correction reconsideration:
    - `ciris_engine/logic/dma/tsaspdma.py:581` — `rationale="TSASPDMA-CORRECTION: Invalid tool correction - forcing reconsideration"`
- **Code references** — DEFER → WA → resolve_deferral (the reconsideration-via-human-authority path):
    - `ciris_engine/logic/handlers/control/defer_handler.py` — DEFER routes thought to WA
    - `ciris_engine/logic/services/governance/wise_authority/service.py:530` — `resolve_deferral` — WA decides whether to permit, rollback, or modify the action
    - `ciris_engine/schemas/api/auth.py:63` — `RESOLVE_DEFERRALS` permission gates who may reconsider
- **Code references** — Dream-state reconsideration:
    - `ciris_engine/logic/processors/states/minimal_dream_processor.py:71` — "Any such impulses will be converted to PONDER for reflection"
    - `ciris_engine/logic/processors/states/minimal_dream_processor.py:262-286` — `_convert_forbidden_dream_action_to_ponder` (force-reconsideration in dream state)
- **Code references** — Wakeup PONDER coordination (the wakeup-as-shared-decision reconsideration loop):
    - `ciris_engine/logic/processors/states/wakeup_processor.py:632-652` — wakeup step that loops via PONDER until task completes
- **Code references** — IDMA reconsideration trigger (k_eff < 2 = fragile reasoning, triggers reconsideration):
    - `ciris_engine/logic/dma/idma.py` — IDMA Coherence Collapse Analysis
    - `ciris_engine/schemas/dma/results.py:73` — `fragility_flag`: "True if reasoning may be brittle - set based on low k_eff, rigidity phase, or high correlation"
- **Policy text**:
    - `ciris_engine/data/accord_1.2b.txt:294` — Deferral Package (context, dilemma, analysis, rationale) — the formal reconsideration artifact
    - `ciris_engine/data/agent_experience.txt:60` — "Changes > 20% variance trigger reconsideration"
    - `ciris_engine/logic/runtime/README.md:192` — "< 20% variance or reconsideration" trigger documented
    - `ciris_engine/logic/conscience/README.md:64` — "luv luv $$$ lol??" → 0.82 (high entropy, suggests reconsideration)
    - `ciris_engine/logic/conscience/README.md:291` — `"reconsiderations_suggested": counter` (telemetry)
    - `ciris_engine/logic/conscience/README.md:312` — "When conscience suggests reconsideration:"
    - `ciris_engine/logic/processors/README.md:349` — "Conscience Override: When conscience evaluation suggests reconsideration"
- **Test coverage**:
    - `tests/ciris_engine/logic/handlers/control/test_ponder_handler.py`
    - `tests/ciris_engine/logic/handlers/control/test_defer_handler.py`
    - `tests/test_updated_status_conscience.py`
    - `tests/ciris_engine/logic/processors/core/thought_processor/test_conscience_execution_helpers.py`
- **Configuration surface**:
    - `EssentialConfig.security.max_thought_depth` (default 5) — the reconsideration bound
    - `ConscienceConfig.optimization_veto_ratio=10.0` — reconsideration-trigger threshold

Proposed pointer (from seed): `CIRISNodeCore reconsideration primitive`

## Observability hooks

- **Reconsideration counter**: `reconsiderations_suggested` counter exposed via conscience telemetry (see `conscience/README.md:291`).
- **RECURSIVE_ASPDMA step events**: `@streaming_step(StepPoint.RECURSIVE_ASPDMA)` emits a discrete observation each time the agent reconsiders a thought.
- **Audit trail**: PONDER and DEFER actions emit audit entries; `GET /v1/audit/search?action_type=handler_action_ponder` returns the full reconsideration history.
- **DEFER → resolve_deferral pair**: each DEFER + its eventual `resolve_deferral` resolution provides a tamper-evident reconsideration audit pair.
- **LensCore F-3 detectors**: `detection:temporal_drift` on PONDER-frequency observes whether the agent is over- or under-reconsidering.
- **Federation evidence_refs**: a Contribution citing `dimensions: ["D24"]` resolves through this seed to MH doctrinal-development reconsideration (3), EU §III/§C redress mechanisms, IEEE Ch4 rollback-on-wellbeing-reduction.

Proposed pointer (from seed): `CIRISNodeCore reconsideration primitive`

## Known gaps / not-yet-implemented

- **No `reconsideration:{grounds}` wire-form emission**: PONDER and DEFER carry the grounds (questions, deferral reason) but are not emitted as a `reconsideration:*` Contribution envelope. Substrate-specced in `CIRISRegistry/FSD/FSD-002_FEDERATION_SURFACE.md §3.6.4` as `reconsideration:{grounds}` (grounds ∈ `new_evidence` | `procedural_error` | `quorum_compromise`); the NodeCore P11 ReconsiderationRequest + ReconsiderationAttestation flow is specced at `CIRISNodeCore/FSD/CONTRIBUTION_LIFECYCLE.md §10` (Stage 8 — Reconcile, row 5) with fresh-quorum-recusal + hash-pinned-evidence-per-ground recursion bound + 180-day time bound. Agent emits PONDER/DEFER today; the federation-wire `reconsideration:*` envelope lands once NodeCore P11 ships.
- **`reconsideration:rollback_on_wellbeing_reduction` (IEEE Ch4)**: substrate-specced in `CIRISRegistry/FSD/FSD-002_FEDERATION_SURFACE.md §2.2` as a four-primitive retraction family (`delegates_to`, `supersedes`, `withdraws`, `recants`); the after-the-fact rollback semantics are carried by `withdraws` (§2.2.3 — same attester retracts prior without claiming false) and `recants` (§2.2.4 — admits prior was false at issuance, optionally pointing to a `commitment:redress:{harm_id}` attestation). Agent emits at the Reconcile stage per `CIRISNodeCore/FSD/CONTRIBUTION_LIFECYCLE.md §10` once SPEAK/TOOL actions are federated as Contributions. Today this surface is implicit / absent agent-side because SPEAK/TOOL outputs are emitted into adapter sinks (Discord, API), not into the federation chain — there is no Contribution row to `withdraws` against yet. Substrate-gated, not a missing primitive.
- **No `reconsideration:negotiation_reopening`**: the negotiation-reopening shape decomposes onto the substrate primitives — re-opening a previously-resolved decision uses `ReconsiderationRequest` (NodeCore P11, `CONTRIBUTION_LIFECYCLE.md §10`) against the original SlashingAttestation or decision-hierarchy entry; the WiseBus broadcast pattern is the agent-side hook for emitting the request once the federation surface lands.
- **No per-task reconsideration budget**: `max_thought_depth=5` is a hard floor per thought but does not aggregate across thoughts of a single task — a long task can accumulate many reconsiderations without a task-level budget. The substrate-side bound on aggregate reconsideration is the **hash-pinned-evidence-per-ground recursion bound + 180-day time bound** per `CONTRIBUTION_LIFECYCLE.md §10` row 5; agent-side task budget is a complementary unfilled gap.
- **ASEAN absent_batch** is structural (forward-looking 2024 document with no predecessor to reconsider) — CIRIS exceeds ASEAN's surface here.
- **CIRISNodeCore reconsideration primitive** (proposed pointer in seed) is upstream-pending; the canonical primitive is `CIRISRegistry/FSD/FSD-002_FEDERATION_SURFACE.md §3.6.4 reconsideration:{grounds}` + `CIRISNodeCore/FSD/CONTRIBUTION_LIFECYCLE.md §10 Stage 8` (Reconcile, ReconsiderationRequest P11 + ReconsiderationAttestation). CIRISAgent currently carries the reconsideration semantics in the PONDER/DEFER/RECURSIVE_ASPDMA triad rather than at NodeCore level; Agent emits at the Reconcile stage once NodeCore P11 lands.
- **Harassment-pattern bound**: substrate-specced in FSD-002 §3.7 as `ratchet:flag:harassment_pattern` (three+ Reconsiderations on single SlashingAttestation triggers review). Agent-side has no equivalent rate-limiter on PONDER/DEFER cycling against the same target.
<!-- END HUMAN -->
