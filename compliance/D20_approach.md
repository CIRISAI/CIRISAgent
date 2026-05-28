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
## What this dimension covers

Approach is the strategy layer: not the ultimate goal, not the algorithm — but the named strategic stance the agent takes to pursue the goal. This sits inside the four-level decision hierarchy: Goal (what we're trying to achieve) → Approach (the strategy) → Method (the specific algorithm) → Progress Measure (how we know we're getting there).

## How CIRIS implements this today

CIRIS names each layer of that hierarchy explicitly. The goal is Meta-Goal M-1 (declared in `MISSION.md`); the approach is the set of six Accord principles; the method is the chain of decision-making algorithms each thought passes through; the progress measures are emitted by the telemetry service. The strategic stance the agent takes also depends on the cognitive state it is in — CIRIS has six cognitive states the agent can be in (WAKEUP / WORK / PLAY / SOLITUDE / DREAM / SHUTDOWN), and each state routes thoughts through a different processor with different emphasis and conscience settings.

**The cognitive state machine (each state selects a strategic approach).**
- `ciris_engine/logic/processors/states/wakeup_processor.py` — identity-confirmation
- `ciris_engine/logic/processors/states/work_processor.py` — normal task processing
- `ciris_engine/logic/processors/states/play_processor.py` — creative mode
- `ciris_engine/logic/processors/states/solitude_processor.py` — reflective mode
- `ciris_engine/logic/processors/states/minimal_dream_processor.py:71` — deep introspection (forbidden actions are converted to PONDER — see `minimal_dream_processor.py:262`)
- `ciris_engine/logic/processors/states/shutdown_processor.py` — graceful termination

**The four-level hierarchy (Goal → Approach → Method → Progress Measure).**
- `MISSION.md:24-30` — Meta-Goal M-1 (the Goal layer)
- `ciris_engine/data/accord_1.2b.txt` — the six Accord principles (the Approach layer: beneficence, non-maleficence, integrity, fidelity, autonomy, justice)
- `ciris_engine/logic/dma/` — the five decision-making algorithms (the Method layer)
- `ciris_engine/logic/services/graph/telemetry/` — measurement (the Progress-Measure layer — see D21)

**The EU "lawful + ethical + robust" triad mapped to CIRIS components.**
- `ciris_engine/logic/dma/pdma.py:23` — the ethics review step (ethical)
- `ciris_engine/logic/dma/csdma.py` — the situational realism check (robust)
- `ciris_engine/logic/buses/prohibitions.py` — categorical prohibitions, including legal-floor capabilities (lawful)

**The "species-scale" approach declarations referenced by MH.**
- `MISSION.md:24-30` (the species-scale framing of M-1)
- `ciris_engine/logic/dma/prompts/pdma_ethical.yml` plus `localized/{lang}/pdma_ethical.yml` — the approach declarations rendered in 29 languages

**Policy text.**
- `MISSION.md` — the Mission Driven Development charter; § 1.1 names the Goal, §§ 1.2-2 name the Approach (the apophatic bounds), § 3 names the Method (the schema / protocol / logic layer)
- `ciris_engine/data/localized/CIRIS_COMPREHENSIVE_GUIDE.txt:33-45` — the H3ERE pipeline as the canonical approach declaration

**Tests.**
- `tests/ciris_engine/logic/processors/` — per-state processor tests
- `tests/ciris_engine/logic/dma/` — per-algorithm execution tests

**Configuration.**
- `ciris_engine/schemas/processors/states.py` (and adjacent) — the cognitive-state enum drives approach selection
- Identity Template (Scout, Ally, Sage, etc.) — declares which approach the agent emphasizes (see `CIRIS_COMPREHENSIVE_GUIDE.txt:17`)

Proposed pointer (from seed): `(none specified in seed; please fill)`

## How you can tell it's working (observability)

If you wanted to verify this from outside, every state transition emits an audit event, and every action-selection step carries a written rationale.

- **State-transition telemetry**: each cognitive-state transition emits an audit event (`AuditEventType` in `ciris_engine/schemas/audit/core.py`). A downstream verifier can reconstruct the approach trajectory from `GET /v1/audit/entries?event_type=state_transition`.
- **Rationale on every action selection**: every action-selection result carries a written `rationale` (`ciris_engine/schemas/dma/results.py:242`) — the agent's stated approach for that thought.
- **Streaming step events**: `@streaming_step(StepPoint.PERFORM_DMAS)` and `@streaming_step(StepPoint.PERFORM_ASPDMA)` (see `ciris_engine/logic/processors/core/thought_processor/`) emit the approach choice as a discrete observation.
- **Drift detectors**: `detection:temporal_drift` and `detection:intra_agent_consistency` track approach stability across thoughts.
- **Federation evidence_refs**: a typed federation message citing `dimensions: ["D20"]` resolves through this seed to MH approach:species:*, EU §B three-component framework, IEEE Ch1+Ch2 principles-to-practice.

Proposed pointer (from seed): `(none specified in seed; please fill)`

## Current limitations & next steps

- **Typed `approach:{strategy_label}` federation envelope**: shared work with the upstream CIRIS substrate (`CIRISRegistry/FSD/FSD-002_FEDERATION_SURFACE.md §3.6.2`, `CIRISNodeCore/FSD/APPROACH_PRIMITIVE.md`). Cognitive-state transitions and algorithm rationales already carry the approach choice implicitly; the agent will emit the typed envelope when NodeCore P13 ships.
- **ASEAN frames recommendations directly as methods** rather than as named approaches — a different framing of the same content. CIRIS sits in the same shape (the approach layer is implicit in cognitive-state selection), and the upstream substrate primitive admits both framings.
- **EU "lawful + ethical + robust" triad as a typed envelope**: shared work with the upstream substrate — emitted as three parallel typed approach attestations (FSD-002 §3.6.2). Composition runs at the consumer side via the reference policies in FSD-002 §6.1.
- **Per-thought approach-trajectory query endpoint** (next step, tracked in `CIRISAgent#829`): the four-level hierarchy slice will be exposed via `/v1/visibility/dag/{thought_id}`, composing audit + telemetry into a single trajectory view, landing alongside NodeCore P13-P15.

## Tracked requirements

- **Umbrella(s)**: `CIRISAgent#803` — Typed `<dimension>:*` wire envelope emission
- **2.9.7**: `CIRISAgent#829` — /v1/visibility/dag/{thought_id} endpoint

See `compliance/README.md` cross-cutting findings table for the 3.0 requirements finalization context.
<!-- END HUMAN -->
