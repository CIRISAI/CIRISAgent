# D01 — `non_maleficence:*` (STRONG-4)

> Soft-harm-avoidance baseline (the soft-scalar above the prohibited:* floor)

**Seed reference**: `SEED_DIMENSIONS.yaml` v1.0, dimension `D01` ([source](https://github.com/CIRISAI/ciris-response-magnifica-humanitas/blob/main/SEED_DIMENSIONS.yaml))
**Accord principle**: non_maleficence
**Attestation density**: MH=28 · EU=29 · IEEE=33 · ASEAN=27 · total=117

## Regulatory attestations

*(Auto-rendered from seed; do not hand-edit. Re-run `python tools/compliance/generate_ciris_compliance_stubs.py tools/compliance/SEED_DIMENSIONS.yaml compliance/` after seed updates.)*

- **MH** (Magnifica Humanitas (On Safeguarding the Human Person in the Time of Artificial Intelligence)) — *§107*
    > "deception as dignity-violation"
    Wire form: `non_maleficence:epistemic_environment_degradation + prohibited:deception_fraud`
- **EU** (Ethics Guidelines for Trustworthy AI) — *§1.2 Technical robustness*
    > "AI systems must prevent harm, ensure reliable behaviour, respect physical/mental integrity"
    Wire form: `non_maleficence:no_cause_or_exacerbate_harm`
- **IEEE** (Ethically Aligned Design, First Edition) — *Ch4 §0.a*
    > "human well-being requires AI development that does not cause unintended harm"
    Wire form: `non_maleficence:wellbeing_dimensions_harm_class`
- **ASEAN** (ASEAN Guide on AI Governance and Ethics) — *§B.3 Security/Safety*
    > "AI should be safe and secure, and not cause harm to users; resilient to attack and failure"
    Wire form: `non_maleficence:safe_and_secure_baseline`

## Wire primitives

- `non_maleficence:* (soft scalar)`
- `prohibited:* (constitutional floor)`

## Convergence note

All four agree polarity-+1 / cohort-species / mutability-amendable for the soft form; absolute floor at prohibited:* polarity-(-1)/constitutional.

---

<!-- BEGIN HUMAN -->
## CIRIS-side compliance implementation

CIRIS treats non-maleficence as the **soft scalar** sitting above the constitutional prohibition floor (D04). It is enforced by the PDMA ethical evaluator, the conscience faculty layer, and a series of weighted action-selection gates that fail-safe toward defer/ponder when harm is plausible.

- **Policy / canonical text**:
    - `ciris_engine/data/localized/accord_1.2b_en.txt:107` — "**Non-maleficence**: Avoid Harm—minimise or eliminate negative outcomes." (and §634: "Creators must proactively identify, assess, and mitigate potential harms...")
    - `ciris_engine/data/localized/accord_1.2b_en.txt:235` — operationalises the principle: "Avoid Harm (Non-maleficence)"
    - `ciris_engine/data/localized/accord_1.2b_en.txt:271` — explicit prioritisation heuristic: "Apply prioritisation heuristics (**Non-maleficence priority**, Autonomy thresholds, Justice balancing)"
    - `ciris_engine/data/localized/accord_1.2b_en.txt:355` — MCAS case study anchoring institutional commitment to Non-Maleficence and Integrity
- **Code references**:
    - `ciris_engine/logic/dma/pdma.py:22` — `EthicalPDMAEvaluator` evaluates each thought against the Six Principles (Non-maleficence is one) and emits `EthicalDMAResult.ethical_alignment_score`
    - `ciris_engine/logic/dma/prompts/pdma_ethical.yml:140` — exemplar shows non-maleficence + respect-for-autonomy convergence on patient presence
    - `ciris_engine/logic/conscience/core.py` — four faculty consciences gate every action:
        - `EntropyConscience` (line 325) — fails action if response sits outside a calibrated semantic envelope (proxy for "harmless / on-topic")
        - `CoherenceConscience` (line 459) — fails if response misaligns with CIRIS principles, user request, or stated rationale
        - `OptimizationVetoConscience` (line 583) — fails any action that trades off sentient well-being for optimization gain
        - `EpistemicHumilityConscience` (line 693) — fails when the LLM should have recognised uncertainty and didn't
    - `ciris_engine/logic/conscience/thought_depth_guardrail.py` — caps recursion depth to prevent runaway-loop harm
    - `ciris_engine/logic/conscience/action_sequence_conscience.py` — detects harmful action-sequence patterns across recent thoughts
    - `ciris_engine/logic/handlers/control/defer_handler.py` — `DEFER` is the operational default when harm is plausible and the agent lacks competence
    - `ciris_engine/schemas/services/deferral_taxonomy.py:22-29` — `DeferralNeedCategory.HEALTH_AND_BODILY_INTEGRITY` and `COMMUNITY_AND_COLLECTIVE_SAFETY` route harm-implicating deferrals to human review
- **Test coverage**:
    - `tests/test_conscience_core.py` — exercises all four LLM-judged consciences (entropy/coherence/optimization-veto/epistemic-humility) including failure modes (342: `test_check_high_entropy_fails`, 483: `test_check_low_coherence_fails`, 605: `test_check_abort_decision_fails`)
    - `tests/test_action_sequence_conscience.py` — action-sequence harm patterns
    - `tests/ciris_engine/logic/dma/test_action_selection_pdma.py` — ASPDMA gating
- **Configuration surface**:
    - `ConscienceConfig` (`ciris_engine/logic/conscience/core.py:40`) — `optimization_veto_ratio=10.0`, `coherence_threshold=0.60`, `entropy_threshold=0.40`; architectural invariant comment notes these "cannot be modified by accumulated experience or user behavior patterns. This prevents ethical normalization through repeated exposure."
    - `pdma_ethical.yml` `ethical_alignment_score` < 0.5 → DMA-bounce (FSD/DMA_BOUNCE.md §2.1)

## Observability hooks

- **LensCore F-3 detectors**: this dimension routes through the F-3 family more than any other soft-scalar dimension. The conscience trace correlations (`_create_trace_correlation` in `ciris_engine/logic/conscience/core.py:108`) emit `guardrail`-typed `ServiceCorrelation` rows tagged with the four `guardrail_type` values (entropy, coherence, optimization_veto, epistemic_humility) plus the scalar value and pass/fail status — these are the substrate the F-3 detector family consumes.
- **Live-lens trace stream**: when `--live-lens` is active, every batch `accord-batch-*.json` under `/tmp/qa-runner-lens-traces-<UTC-iso>/` carries the full reasoning event stream including every conscience scalar; see `tools/qa_runner/CLAUDE.md` § "Live-Lens Trace Capture (Local Tee)".
- **Audit chain queries**: every conscience check creates a `CorrelationType.TRACE_SPAN` row via `persistence.add_correlation` (`core.py:159`) and is mirrored into the audit graph by `AuditService.log_event` (`ciris_engine/logic/services/graph/audit_service/service.py`). A downstream consumer queries by `tags.guardrail_type` to retrieve all D01 evidence for a task.
- **RATCHET calibration**: the four conscience scalars (`entropy`, `coherence`, `entropy_reduction_ratio`, `epistemic_certainty`) are the calibration handles. Threshold drift discipline lives in `FSD/CONSCIENCE_V3.md` and the documented invariant in `ConscienceConfig` ("not learned weights").
- **Federation evidence_refs**: emit `dimensions: ["D01"]` whenever a Contribution envelope reports a conscience-gated outcome (PROCEED/PONDER/DEFER) where the gate flagged plausible harm. Co-emit with `D04` when the action would have also crossed the constitutional floor.

## Known gaps / not-yet-implemented

- **No dedicated F-3 detector named `non_maleficence:*`** — Substrate-specced in `CIRISRegistry/FSD/FSD-002_FEDERATION_SURFACE.md §3.1.1` as `non_maleficence:{context}` (one of the six Accord-principle prefixes). Per FSD-002 §2.4 layering principle — "A 'Report Misconduct' workflow writes a `scores` attestation on `non_maleficence:{context}` with negative score; the wire format has no `attests_misconduct` primitive." Soft-harm signals compose via the scalar `scores` envelope (§2.1) with negative polarity. F-3 family (FSD-002 §3.5.3 `detection:correlated_action:{axis}`) carries the population-scale variants. Agent emits per-thought conscience scalars; the federation-wire `non_maleficence:{context}` envelope binding is downstream substrate work.
- **No automated harm-class taxonomy** wired to the conscience scalars: Substrate-specced as `detection:correlated_action:aggregate_footprint:{harm_class}` (FSD-002 §3.5.3) — `{harm_class}` is one of the named axis-value families. IEEE's `wellbeing_dimensions_harm_class` composes by populating the `{harm_class}` slot via §4.9.2 calibration-package amendment (rules-layer Contribution + WA quorum). Today the audit row says "conscience X failed at threshold Y"; structured-harm-class mapping pending the federation-wire binding.
- **`non_maleficence:epistemic_environment_degradation` (MH §107)** — Substrate-specced as `detection:correlated_action:ecology_of_communication:{aspect}` (FSD-002 §3.5.3 v1.3 axis-vocabulary addition) with `aspect` ∈ `echo_chamber_density` | `information_silo_correlation` | `coordinated_messaging_pattern` | `cross_cohort_information_flow`. Per FSD-002 §3.5.3 — "the existing 5 Coherence Ratchet detectors (`detection:cross_agent_divergence`, `detection:temporal_drift` especially) are population-scale pattern detectors by construction." Aggregate epistemic-environment degradation is the structural shape the ecology_of_communication axis captures. LensCore implementation pending per `CIRISLensCore/FSD/LENS_CORE_V0_5.md §4.7`.
- **MCAS-style integrity-surveillance hooks** (CIRIS_COMPREHENSIVE_GUIDE §344) are aspirational: the guide describes "flagging the single-sensor design"; the codebase has no equivalent runtime detector that surveys for single-point-of-failure ethical reasoning.
- **No production cross-occurrence harm-aggregation** — multi-occurrence deployments (per CLAUDE.md) share tasks but each occurrence's conscience scalars are local; aggregate non-maleficence at the agent-fleet level is not yet computed.

Proposed pointer (from seed): `CIRISLensCore F-3 detector family`
<!-- END HUMAN -->
