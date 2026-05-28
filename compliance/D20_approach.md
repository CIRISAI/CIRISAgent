# D20 — `approach:*` (STRONG-3)

> Decision-hierarchy strategic axis (Goal→Approach→Method→Progress-Measure DAG)

**Seed reference**: `SEED_DIMENSIONS.yaml` v1.0, dimension `D20` ([source](https://github.com/CIRISAI/ciris-response-magnifica-humanitas/blob/main/SEED_DIMENSIONS.yaml))
**Accord principle**: integrity
**Attestation density**: MH=5 · EU=3 · IEEE=23 · ASEAN=1 · total=32

**Absent from**: ASEAN — Single use is too thin for solid 4-batch attestation. ASEAN's checklist genre states recommendations as direct method/principle attestations rather than as named 'approaches' within a Goal-Approach-Method DAG.

## Regulatory attestations

*(Auto-rendered from seed; do not hand-edit. Re-run `python tools/compliance/generate_ciris_compliance_stubs.py tools/compliance/SEED_DIMENSIONS.yaml compliance/` after seed updates.)*

- **MH** (Magnifica Humanitas (On Safeguarding the Human Person in the Time of Artificial Intelligence)) — *§§ various*
    > "approach:species:* strategic-pursuit framing"
    Wire form: `approach:species:education + approach:species:construction (5 attestations)`
- **EU** (Ethics Guidelines for Trustworthy AI) — *§B*
    > "three-component framework approach (lawful + ethical + robust)"
    Wire form: `approach:trustworthy_ai_lawful_ethical_robust`
- **IEEE** (Ethically Aligned Design, First Edition) — *Ch1 + Ch2*
    > "principles-to-practice pipeline; per-principle implementation strategies"
    Wire form: `approach:* (23 attestations)`

## Wire primitives

- `approach:{strategy_label}`

---

<!-- BEGIN HUMAN -->
## CIRIS-side compliance implementation

`approach:*` is the middle layer of the Goal→Approach→Method→Progress-Measure DAG. In CIRIS, the strategic-pursuit axis is named: Meta-Goal M-1 is the goal, the Accord principles are the approach, and the H3ERE pipeline is the method. The named approach lives in the 6-state cognitive state machine (WAKEUP / WORK / PLAY / SOLITUDE / DREAM / SHUTDOWN) — each state selects an approach by routing thoughts through a different processor with different DMA emphasis and conscience configuration.

- **Code references** — cognitive state machine (named approach selection):
    - `ciris_engine/logic/processors/states/wakeup_processor.py` — identity-confirmation approach
    - `ciris_engine/logic/processors/states/work_processor.py` — normal-task approach
    - `ciris_engine/logic/processors/states/play_processor.py` — creative approach
    - `ciris_engine/logic/processors/states/solitude_processor.py` — reflective approach
    - `ciris_engine/logic/processors/states/minimal_dream_processor.py:71` — deep-introspection approach (forbidden actions converted to PONDER — `minimal_dream_processor.py:262`)
    - `ciris_engine/logic/processors/states/shutdown_processor.py` — graceful-termination approach
- **Code references** — Goal→Approach→Method DAG:
    - `MISSION.md:24-30` — Meta-Goal M-1 (the Goal layer)
    - `ciris_engine/data/accord_1.2b.txt` — the 6 Accord principles (the Approach layer: beneficence / non-maleficence / integrity / fidelity / autonomy / justice)
    - `ciris_engine/logic/dma/` — the 5 DMA evaluators (the Method layer)
    - `ciris_engine/logic/services/graph/telemetry/` — measurement (the Progress-Measure layer — see D21)
- **Code references** — `approach:trustworthy_ai_lawful_ethical_robust` (EU mapping):
    - `ciris_engine/logic/dma/pdma.py:23` — `EthicalPDMAEvaluator` (ethical)
    - `ciris_engine/logic/dma/csdma.py` — common-sense robustness check (robust)
    - `ciris_engine/logic/buses/prohibitions.py` — categorical prohibitions, including legal-floor capabilities (lawful)
- **Code references** — `approach:species:*` (MH-education / MH-construction adjacent):
    - `MISSION.md:24-30` (M-1 species-scale framing)
    - `ciris_engine/logic/dma/prompts/pdma_ethical.yml` + `localized/{lang}/pdma_ethical.yml` — the approach declarations rendered in 29 languages
- **Policy text**:
    - `MISSION.md` — full Mission Driven Development charter; § 1.1 names the Goal, §§ 1.2-2 name the Approach (apophatic bounds), § 3 names the Method (the schema/protocol/logic layer)
    - `ciris_engine/data/localized/CIRIS_COMPREHENSIVE_GUIDE.txt:33-45` — H3ERE pipeline as the canonical approach declaration
- **Test coverage**:
    - `tests/ciris_engine/logic/processors/` — per-state processor tests
    - `tests/ciris_engine/logic/dma/` — per-DMA approach-execution tests
- **Configuration surface**:
    - `ciris_engine/schemas/processors/states.py` (and adjacent) — cognitive-state enum drives approach selection
    - Identity Template (Scout, Ally, Sage, etc.) — declares which approach the agent emphasizes (see `CIRIS_COMPREHENSIVE_GUIDE.txt:17`)

Proposed pointer (from seed): `(none specified in seed; please fill)`

## Observability hooks

- **State-transition telemetry**: every cognitive-state transition emits an audit event (`AuditEventType` in `ciris_engine/schemas/audit/core.py`). A downstream verifier can reconstruct the approach trajectory from `GET /v1/audit/entries?event_type=state_transition`.
- **DMA-result telemetry**: each ASPDMA emission carries a `rationale` field (`ciris_engine/schemas/dma/results.py:242`) — the verbal approach-declaration for that thought.
- **Streaming step events**: `@streaming_step(StepPoint.PERFORM_DMAS)` and `@streaming_step(StepPoint.PERFORM_ASPDMA)` (see `ciris_engine/logic/processors/core/thought_processor/`) emit the approach choice as a discrete observation.
- **LensCore F-3 detectors**: `detection:temporal_drift` and `detection:intra_agent_consistency` track approach-stability across thoughts.
- **Federation evidence_refs**: a Contribution citing `dimensions: ["D20"]` resolves through this seed to MH approach:species:*, EU §B three-component framework, IEEE Ch1+Ch2 principles-to-practice.

Proposed pointer (from seed): `(none specified in seed; please fill)`

## Known gaps / not-yet-implemented

- **No explicit `approach:{strategy_label}` wire-form emission**: cognitive state transitions and DMA rationales carry the approach choice implicitly, but a structured `approach:*` Contribution is not yet emitted.
- **ASEAN absent_batch** (single use): ASEAN frames recommendations directly as methods rather than as named approaches. CIRIS exhibits the same shape — the approach layer is implicit in cognitive-state selection rather than named in a wire envelope.
- **`approach:trustworthy_ai_lawful_ethical_robust` triad**: the three components are implemented (PDMA = ethical, CSDMA = robust, prohibitions + audit chain = lawful) but not bundled as a single EU-compatible attestation.
- **Per-thought approach-trajectory query**: there is no single endpoint that, given a thought ID, returns the full Goal→Approach→Method→Progress-Measure DAG slice for that thought. The data is reconstructible from the audit + telemetry endpoints; consolidating the view is pending.
<!-- END HUMAN -->
