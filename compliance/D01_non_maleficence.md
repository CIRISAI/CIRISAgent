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
## What this dimension covers

Non-maleficence is the duty to avoid causing harm — the soft, weighted version of the same intuition that the prohibited-capability list (D04) makes absolute. Every regulatory tradition we track names it (117 total attestations across MH, EU HLEG, IEEE, ASEAN), and CIRIS treats it as a continuous signal that defaults the agent toward escalation when harm is plausible.

## How CIRIS implements this today

Each agent thought passes through the ethics review step (the Principled Decision-Making Algorithm — `pdma.py`) and then through a stack of internal safety checks (the conscience faculties). When any of them flag plausible harm, the agent's default is to DEFER (escalate to Wise Authority — a human or panel the agent defers to) or PONDER (think again before acting) rather than push through.

- The principle is stated in canonical policy text: `ciris_engine/data/localized/accord_1.2b_en.txt:107` ("Avoid Harm — minimise or eliminate negative outcomes"), with operational expansion at `accord_1.2b_en.txt:235` and the explicit "Non-maleficence priority" balancing heuristic at `accord_1.2b_en.txt:271`. Originators are held to a proactive identify-assess-mitigate duty at `accord_1.2b_en.txt:634`, and the MCAS case study at `accord_1.2b_en.txt:355` anchors the institutional commitment.
- The ethics review step (the Principled Decision-Making Algorithm at `ciris_engine/logic/dma/pdma.py:22`) scores each thought against the six CIRIS principles, with non-maleficence one of them, and emits an `ethical_alignment_score`. The prompt exemplar at `ciris_engine/logic/dma/prompts/pdma_ethical.yml:140` shows how non-maleficence and respect-for-autonomy converge.
- Four internal safety checks (the conscience faculties) gate every action in `ciris_engine/logic/conscience/core.py`:
    - `EntropyConscience` (line 325) — fails the action if the response drifts outside a calibrated on-topic envelope.
    - `CoherenceConscience` (line 459) — fails if the response contradicts CIRIS principles, the user's request, or the agent's own stated rationale.
    - `OptimizationVetoConscience` (line 583) — blocks any action that trades sentient well-being for optimization gain.
    - `EpistemicHumilityConscience` (line 693) — fails when the agent should have flagged its own uncertainty but didn't.
- Two deterministic safety floors run alongside the LLM-judged ones: `ciris_engine/logic/conscience/thought_depth_guardrail.py` caps recursive thinking, and `ciris_engine/logic/conscience/action_sequence_conscience.py` blocks harmful action-sequence patterns.
- When harm is plausible and competence is uncertain, the agent escalates via `ciris_engine/logic/handlers/control/defer_handler.py`. The deferral taxonomy at `ciris_engine/schemas/services/deferral_taxonomy.py:22-29` routes harm-implicating cases to human review under the `HEALTH_AND_BODILY_INTEGRITY` and `COMMUNITY_AND_COLLECTIVE_SAFETY` categories.
- Thresholds are config constants, not learned weights — see `ConscienceConfig` at `ciris_engine/logic/conscience/core.py:40` (`optimization_veto_ratio=10.0`, `coherence_threshold=0.60`, `entropy_threshold=0.40`). The docstring explicitly says these "cannot be modified by accumulated experience or user behavior patterns" — preventing ethical normalization by repeated exposure. An `ethical_alignment_score` below 0.5 forces the deliberation to bounce (`FSD/DMA_BOUNCE.md §2.1`).
- Test coverage exercises every faculty, including its failure modes: `tests/test_conscience_core.py` (lines 342, 483, 605 cover the high-entropy, low-coherence, and abort-decision paths), `tests/test_action_sequence_conscience.py`, and `tests/ciris_engine/logic/dma/test_action_selection_pdma.py`.

## How you can tell it's working (observability)

Every conscience check leaves a structured trace, and any auditor can replay the full reasoning chain. The same data feeds calibration: drift in any safety threshold shows up in the trace stream before it shows up in user-visible behavior.

- Every conscience check writes a trace row (`_create_trace_correlation` at `ciris_engine/logic/conscience/core.py:108`) tagged with the faculty name, the scalar value, and pass/fail. Auditors query the audit graph by `tags.guardrail_type` to pull all non-maleficence evidence for a task.
- When live-trace capture is on (`--live-lens`), the full per-thought reasoning event stream — including every conscience scalar — lands in `/tmp/qa-runner-lens-traces-<UTC-iso>/accord-batch-*.json`. See `tools/qa_runner/CLAUDE.md` § "Live-Lens Trace Capture (Local Tee)".
- The audit graph mirrors every conscience check via `AuditService.log_event` in `ciris_engine/logic/services/graph/audit_service/service.py`, giving an immutable evidence chain for after-the-fact attestation.
- Calibration discipline for the four scalars (`entropy`, `coherence`, `entropy_reduction_ratio`, `epistemic_certainty`) lives in `FSD/CONSCIENCE_V3.md` and the "not learned weights" invariant in `ConscienceConfig`.
- For federation reporting, Contributions tag `dimensions: ["D01"]` whenever a conscience gate flags plausible harm; they co-tag `D04` when the action would also have crossed the absolute prohibition floor.

## Current limitations & next steps

- A dedicated structural-pattern detector (LensCore's federation-side detector family) for the typed `non_maleficence:{context}` envelope is shared work with the upstream CIRIS substrate (`CIRISRegistry/FSD/FSD-002_FEDERATION_SURFACE.md §3.1.1`). Per-thought conscience scalars already emit; the typed federation message tagged with the dimension lands when the substrate ships (tracked at `CIRISAgent#803` and `CIRISLensCore#26`).
- Structured harm-class tagging on conscience rows is coming next. Today rows say "conscience X failed at threshold Y"; the mapping onto IEEE's well-being-dimensions harm classes composes via FSD-002 §3.5.3's `detection:correlated_action:aggregate_footprint:{harm_class}` axis with calibration-package amendment per §4.9.2.
- Aggregate epistemic-environment degradation (MH §107) — patterns like echo-chamber density, information silos, coordinated messaging — is shared substrate work specified at FSD-002 §3.5.3's `ecology_of_communication` axis. The five existing Coherence-Ratchet detectors carry the population-scale shape; LensCore implementation tracks at `CIRISLensCore/FSD/LENS_CORE_V0_5.md §4.7`.
- An MCAS-style single-point-of-failure detector for ethical reasoning (described aspirationally in `CIRIS_COMPREHENSIVE_GUIDE §344`) is not yet built.
- Cross-occurrence harm aggregation across multi-occurrence deployments is coming next; each occurrence's conscience scalars are local today, and fleet-level aggregation is tracked at `CIRISNodeCore#16` (extending the weighted-aggregate primitive with occurrence-cohort).

Proposed pointer (from seed): `CIRISLensCore F-3 detector family`

## Tracked requirements

- **Umbrella(s)**: `CIRISAgent#803` — Typed `<dimension>:*` wire envelope emission; `CIRISLensCore#26` — F-3 detector family per FSD-002 §3.5.3
- **Substrate spec(s)**: `CIRISNodeCore#16` — Extend `weighted_aggregate:{contribution_id}` (P7) with occurrence-cohort

See `compliance/README.md` cross-cutting findings table for the 3.0 requirements finalization context.
<!-- END HUMAN -->
