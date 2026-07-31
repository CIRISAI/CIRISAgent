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
## What this dimension covers

Reconsideration asks: can the agent pause, think again, or roll back? An auditor wants to see that the agent does not commit to an action it has reason to doubt, that the doubt-trigger is explicit, and that the reconsideration is itself bounded (so it can't loop forever).

## How CIRIS implements this today

This is one of the most concretely implemented dimensions in CIRIS. The canonical reconsideration action is PONDER (think again before acting), and it is bounded by a hard maximum-thought-depth so reconsideration cannot run forever. The pipeline also has an explicit retry-with-guidance step that triggers when the internal safety checks flag a problem, plus a dedicated check that re-opens a thought when new information arrives mid-decision.

**PONDER handler (the canonical reconsideration action).**
- `ciris_engine/logic/handlers/control/ponder_handler.py:17` — `PonderHandler`
- `ciris_engine/logic/handlers/control/ponder_handler.py:30` — `max_rounds` configuration (default 5 since 2.7.1)
- `ciris_engine/schemas/actions/parameters.py` — `PonderParams.questions: List[str]` — the reconsideration grounds, written out
- `ciris_engine/schemas/runtime/enums.py:62` — `HandlerActionType.PONDER`

**The retry-with-guidance step (the reconsideration loop inside the pipeline).** When the internal safety checks flag a problem, the pipeline re-runs the action-selection step with the safety check's guidance fed back in.
- `ciris_engine/logic/processors/core/thought_processor/recursive_processing.py:249-251` — `_recursive_aspdma_step` decorated with `@streaming_step(StepPoint.RECURSIVE_ASPDMA)` and `@step_point(StepPoint.RECURSIVE_ASPDMA)`
- `ciris_engine/logic/processors/core/thought_processor/recursive_processing.py:117` — `_handle_recursive_processing` (entry point)
- `ciris_engine/logic/processors/core/thought_processor/recursive_processing.py:212` — the retry call site
- `ciris_engine/logic/processors/core/thought_processor/recursive_processing.py:113` — comment: "RECURSIVE_ASPDMA: Retry action selection with conscience guidance"

**Depth bound (the reconsideration ceiling).**
- `ciris_engine/logic/conscience/thought_depth_guardrail.py:37` — depth bound (matches `EssentialConfig.security.max_thought_depth=5`)
- `ciris_engine/data/localized/CIRIS_COMPREHENSIVE_GUIDE.txt:276` — documented (note: the guide says 7; the current `EssentialConfig` value is 5; the doc is being updated)

**New-observation trigger (re-open when fresh information arrives).**
- `ciris_engine/logic/conscience/updated_status_conscience.py:26` — `UpdatedStatusConscience`
- `ciris_engine/logic/conscience/updated_status_conscience.py:160` — the explicit trigger rationale: "Updated status detected — new observation in channel requires reconsideration"

**Tool-correction reconsideration (re-open when a tool call is wrong).**
- `ciris_engine/logic/dma/tsaspdma.py:581` — `"TSASPDMA-CORRECTION: Invalid tool correction - forcing reconsideration"`

**Reconsideration via human authority (DEFER → Wise Authority → resolve).** This is the "ask a human to reconsider" path.
- `ciris_engine/logic/handlers/control/defer_handler.py` — DEFER (escalate to a Wise Authority) routes the thought to a human
- `ciris_engine/logic/services/governance/wise_authority/service.py:530` — `resolve_deferral` — the Wise Authority decides whether to permit, roll back, or modify
- `ciris_engine/schemas/api/auth.py:63` — `RESOLVE_DEFERRALS` permission gates who may reconsider

**Dream-state reconsideration (forbidden actions become PONDER).** When the agent is in DREAM (deep introspection), forbidden impulses are converted to a reconsideration rather than executed.
- `ciris_engine/logic/processors/states/minimal_dream_processor.py:71` — "Any such impulses will be converted to PONDER for reflection"
- `ciris_engine/logic/processors/states/minimal_dream_processor.py:262-286` — `_convert_forbidden_dream_action_to_ponder`

**Wakeup PONDER coordination (looping until ready).**
- `ciris_engine/logic/processors/states/wakeup_processor.py:632-652` — wakeup loops via PONDER until the task completes

**Fragility-triggered reconsideration.** The inverse-decision check (IDMA — flags when the agent is approaching a decision-boundary) emits a fragility flag when reasoning is brittle, which prompts reconsideration.
- `ciris_engine/logic/dma/idma.py` — Coherence Collapse Analysis
- `ciris_engine/schemas/dma/results.py:73` — `fragility_flag`: "True if reasoning may be brittle — set based on low k_eff, rigidity phase, or high correlation"

**Policy text.**
- `ciris_engine/data/accord_1.2b.txt:294` — Deferral Package (context, dilemma, analysis, rationale) — the formal reconsideration artifact
- `ciris_engine/data/agent_experience.txt:60` — "Changes > 20% variance trigger reconsideration"
- `ciris_engine/logic/runtime/README.md:192` — "< 20% variance or reconsideration" trigger documented
- `ciris_engine/logic/conscience/README.md:64` — high-entropy input example suggesting reconsideration
- `ciris_engine/logic/conscience/README.md:291` — `"reconsiderations_suggested": counter` (telemetry)
- `ciris_engine/logic/conscience/README.md:312` — "When conscience suggests reconsideration"
- `ciris_engine/logic/processors/README.md:349` — "Conscience Override: When conscience evaluation suggests reconsideration"

**Tests.**
- `tests/ciris_engine/logic/handlers/control/test_ponder_handler.py`
- `tests/ciris_engine/logic/handlers/control/test_defer_handler.py`
- `tests/test_updated_status_conscience.py`
- `tests/ciris_engine/logic/processors/core/thought_processor/test_conscience_execution_helpers.py`

**Configuration.**
- `EssentialConfig.security.max_thought_depth` (default 5) — the reconsideration ceiling
- `ConscienceConfig.optimization_veto_ratio=10.0` — the threshold that triggers reconsideration

**Substrate-enforced facet (inherited via CIRISServer).** Bounded reconsideration *admission* — the anti-DoS and harassment-cluster gates on who may file a reconsideration, how often — now ships inside the agent's own deployment via CIRISServer's integration of the substrate. The facet is independently verified against the *real published wheels* by CIRISConformance [`test_220_reconsider_dos.py`](https://github.com/CIRISAI/CIRISConformance/blob/main/tests/test_220_reconsider_dos.py) (F-AV-RECONSIDER-DOS): `ciris_server.ReconsiderDosGuard` admits a fresh filing, refuses filings past the per-actor budget, refuses repeat same-pair filings as `HarassmentClusterDetected`, and refills the budget on a successful reversal — on both sqlite and postgres, across py3.10/3.12 on x86_64 + aarch64. D24 is one of the three controls the [CIRISConformance compliance coverage map](https://github.com/CIRISAI/CIRISConformance#compliance-coverage-map) marks fully substrate-gated (lane = substrate). The agent-side reconsideration surfaces above (PONDER depth bound, retry-with-guidance, DEFER→resolve) remain the in-pipeline half; the substrate guard bounds the federation-facing admission half.

Proposed pointer (from seed): `CIRISNodeCore reconsideration primitive`

## How you can tell it's working (observability)

If you wanted to verify this from outside, every PONDER or DEFER emits a discrete step event and an audit entry, and a per-agent counter tracks how often reconsideration is being suggested.

- **Reconsideration counter**: `reconsiderations_suggested` exposed via conscience telemetry (see `conscience/README.md:291`).
- **Retry-step events**: `@streaming_step(StepPoint.RECURSIVE_ASPDMA)` emits a discrete observation each time the agent reconsiders a thought.
- **Audit trail**: PONDER and DEFER actions emit audit entries; `GET /v1/audit/search?action_type=handler_action_ponder` returns the full reconsideration history.
- **DEFER → resolve pair**: each DEFER plus its eventual `resolve_deferral` resolution provides a tamper-evident reconsideration audit pair.
- **Drift detector**: `detection:temporal_drift` on PONDER frequency flags whether the agent is over- or under-reconsidering.
- **Federation evidence_refs**: a typed federation message citing `dimensions: ["D24"]` resolves through this seed to MH doctrinal-development reconsideration, EU §III/§C redress mechanisms, IEEE Ch4 rollback-on-wellbeing-reduction.

Proposed pointer (from seed): `CIRISNodeCore reconsideration primitive`

## Current limitations & next steps

- **Typed `reconsideration:{grounds}` federation envelope**: shared work with the upstream CIRIS substrate (`CIRISRegistry/FSD/FSD-002_FEDERATION_SURFACE.md §3.6.4`; grounds ∈ `new_evidence` | `procedural_error` | `quorum_compromise`; `CIRISNodeCore/FSD/CONTRIBUTION_LIFECYCLE.md §10 Stage 8` Reconcile, with a fresh-quorum-recusal rule, a hash-pinned-evidence-per-ground recursion bound, and a 180-day time bound). PONDER and DEFER carry the grounds today; the typed envelope lands when NodeCore P11 ships.
- **IEEE Ch4 `reconsideration:rollback_on_wellbeing_reduction`**: shared work with the upstream substrate (FSD-002 §2.2 four-primitive retraction family: `delegates_to`, `supersedes`, `withdraws`, `recants`). After-the-fact rollback semantics ride on `withdraws` and `recants`. Today the agent's external actions (SPEAK, TOOL) are emitted into adapter sinks rather than into the federation chain — there is no federated row to roll back yet. This will land once those actions are emitted as federation messages.
- **`reconsideration:negotiation_reopening`**: shared work with the upstream substrate — re-opening a previously-resolved decision uses the upstream `ReconsiderationRequest` primitive. The WiseBus broadcast pattern is the agent-side hook for emitting the request once the federation surface lands.
- **Per-task reconsideration budget** (next step, tracked in `CIRISAgent#815`): `max_thought_depth=5` is a hard per-thought floor, but a long task can accumulate many reconsiderations across thoughts without a task-level budget. The upstream substrate provides a per-ground recursion bound + 180-day time bound; an agent-side task-level budget will complement that.
- **ASEAN does not address reconsideration** (it is a forward-looking 2024 document with no predecessor to reconsider) — CIRIS exceeds ASEAN's surface here.
- **Harassment-pattern bound**: the federation-facing half is now substrate-enforced — `ciris_server.ReconsiderDosGuard` refuses repeat same-pair filings as `HarassmentClusterDetected` and budgets per-actor filings (CIRISConformance [`test_220`](https://github.com/CIRISAI/CIRISConformance/blob/main/tests/test_220_reconsider_dos.py), see above). An equivalent agent-side rate-limiter on PONDER/DEFER cycling against the same target remains a next step.

## Tracked requirements

- **Umbrella(s)**: `CIRISAgent#803` — Typed `<dimension>:*` wire envelope emission; `CIRISNodeCore#15` — Step-4 primitives (P8 moderation + E-4 multilateral + P11 ReconsiderationRequest + P2 CommonsCredits + 4-primitive retraction)
- **2.9.6**: `CIRISAgent#815` — per-task reconsideration budget

See `compliance/README.md` cross-cutting findings table for the 3.0 requirements finalization context.
<!-- END HUMAN -->
