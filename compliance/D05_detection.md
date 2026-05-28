# D05 — `detection:*` (STRONG-4)

> LensCore F-3 / RATCHET family — aggregate-correlation / structural-injustice / drift detection

**Seed reference**: `SEED_DIMENSIONS.yaml` v1.0, dimension `D05` ([source](https://github.com/CIRISAI/ciris-response-magnifica-humanitas/blob/main/SEED_DIMENSIONS.yaml))
**Accord principle**: justice
**Attestation density**: MH=54 · EU=15 · IEEE=41 · ASEAN=16 · total=126

## Regulatory attestations

*(Auto-rendered from seed; do not hand-edit. Re-run `python tools/compliance/generate_ciris_compliance_stubs.py tools/compliance/SEED_DIMENSIONS.yaml compliance/` after seed updates.)*

- **MH** (Magnifica Humanitas (On Safeguarding the Human Person in the Time of Artificial Intelligence)) — *§36*
    > "structures of sin / aggregate expendability of persons"
    Wire form: `detection:correlated_action:aggregate_footprint:expendability_of_persons`
- **EU** (Ethics Guidelines for Trustworthy AI) — *§1.6 Societal/environmental well-being*
    > "aggregate energy/carbon footprint of AI deployment"
    Wire form: `detection:correlated_action:aggregate_footprint:energy_carbon`
- **IEEE** (Ethically Aligned Design, First Edition) — *Ch4, Ch5, Ch8*
    > "cultural norm drift; aggregate environmental footprint; participation exclusion"
    Wire form: `detection:correlated_action:participation_exclusion:underrepresented_population + detection:correlated_action:aggregate_footprint:planetary_impact`
- **ASEAN** (ASEAN Guide on AI Governance and Ethics) — *§B.2 + §C.3*
    > "underrepresented populations; temporal drift; intra-agent consistency"
    Wire form: `detection:correlated_action:participation_exclusion:underrepresented_population + detection:temporal_drift + detection:intra_agent_consistency`

## Wire primitives

- `detection:correlated_action:{axis}`
- `detection:temporal_drift`
- `detection:intra_agent_consistency`
- `detection:distributive:access:*`

## Convergence note

All four batches independently engage the F-3 family. Three of four also engage detection:distributive:access:* (v1.3 universal-destination-of-goods closure): MH 7, EU 2, IEEE 4, ASEAN 2.

---

<!-- BEGIN HUMAN -->
## What this dimension covers

Detection covers the harms that no single agent action can reveal on its own: aggregate environmental footprint, cohort exclusion, slow norm-drift, and patterns of coordinated behavior across many agents. These are the harms that only show up when you look across many traces together — so the detection layer lives in the federation analytics layer, not inside any one agent.

## How CIRIS implements this today

The detection layer is split by design: the agent (this repo) measures and ships the per-trace signals; the structural-pattern detector (LensCore's federation-side detector family that watches for patterns no single agent can see) correlates them across the population. Today the agent ships rich per-trace evidence and runs an in-agent identity-variance monitor; the cross-trace detector family lives upstream in LensCore.

- **What the agent measures and ships**:
    - `ciris_engine/logic/infrastructure/sub_services/identity_variance_monitor.py:43-50` — the identity-variance monitor (watches for drift between the agent's intended identity and its actual behavior); the fully-implemented temporal-drift signal today.
    - `ciris_engine/logic/services/governance/self_observation/service.py` — SelfObservation: tracks behavioral patterns over time; surfaces intra-agent-consistency candidates.
    - `ciris_engine/logic/services/governance/adaptive_filter/service.py:39+` — adaptive filter: filters input streams against drift baselines.
    - `ciris_engine/schemas/infrastructure/behavioral_patterns.py` — `BehavioralPattern`, `reliability_level` (consistency metric, `behavioral_patterns.py:123`).
    - `ciris_engine/schemas/infrastructure/identity_variance.py:78` — `VarianceCheckMetadata`.
- **Per-trace integrity signals carried to the federation**:
    - `ciris_engine/schemas/runtime/system_context.py:163` — every traced thought carries six near-independent integrity signals so the federation analytics layer can correlate without being fooled by one signal masking another (`FSD/TRACE_WIRE_FORMAT.md:519-522`).
    - `FSD/PROOF_OF_BENEFIT_FEDERATION.md:52` — the 17-dimensional constraint vector that the federation uses to validate Sybil resistance.
- **In-agent conscience-layer detection (per-thought)**:
    - `ciris_engine/logic/dma/idma.py:10` — per-thought fragility detector.
    - `ciris_engine/schemas/conscience/core.py:199` — reasoning-transparency scalar (0.0–1.0) feeds downstream correlation analysis.
    - The conscience faculties (optimization-veto, epistemic-humility, coherence, entropy) produce signals the detection layer correlates after the fact.
- **Aggregate substrate the agent provides upstream**:
    - `ciris_engine/logic/services/graph/tsdb_consolidation/service.py:97` — per-window audit summary nodes carry the evidence list; the federation analytics layer computes aggregate footprints from these.
    - `ciris_engine/logic/services/graph/incident_service/service.py:38-54` — IncidentManagementService ingests warning/error logs as graph nodes for per-class rollups.
    - `tools/qa_runner/modules/safety_battery.py:241-246` — captures CI run metadata for cross-run drift analysis.

## How you can tell it's working (observability)

If you want to verify what the detection layer sees today, look at the per-trace signals the agent ships; for the cross-trace verdicts themselves, you query LensCore (the federation analytics layer).

- **Per-trace constraint vector**: every action contributes to the 17-dimensional constraint vector (`FSD/PROOF_OF_BENEFIT_FEDERATION.md:52`); the federation analytics layer computes an effective-dimensionality score to validate Sybil resistance (peak 9.51, lifetime mean 7.20).
- **Re-walk the audit chain**: `engine.audit_list_entries(filter_json, cursor, limit)` and `engine.audit_verify_chain` give downstream verifiers the same evidence the detector reads.
- **Operational drift dashboards**: `/v1/telemetry/unified` (`ciris_engine/logic/adapters/api/routes/telemetry.py:1879+`) provides operational aggregates; not detector-grade but used by drift dashboards.
- **Federation evidence**: outbound Contributions cite `dimensions: ["D05"]` when the action itself produces detector-relevant evidence (rarer from the agent, common from the lens looking back at agent traces).

## Current limitations & next steps

This is the dimension with the largest agent-side / federation-side split. The agent ships the signals today; the cross-trace detector family lands when the upstream LensCore substrate ships its v0.6.

- **Cross-trace detector family** — shared work with the upstream CIRISLensCore substrate. LensCore v0.5 ships three detectors today (cohort-mismatch, manifold-outlier, unconsented-external-probe per `CIRISLensCore/FSD/LENS_CORE_V0_5.md §4.7`); the population-scale correlated-action family arrives in v0.6 per `CIRISRegistry/FSD/FSD-002_FEDERATION_SURFACE.md §3.5.3`. Each detector calibrated via a versioned, hash-pinned package (`CIRISAI/RATCHET/calibration/correlated_action_v{N}.yaml`); per FSD-002 §4.6 these flags are never sole evidence for any enforcement action. The federation calibration system that tunes detectors over time (RATCHET) is governed by FSD-002 §4.9.2 amendment discipline. Specific detectors landing on this track:
    - aggregate environmental footprint (energy/carbon and planetary scale, FSD-002 §3.5.3),
    - participation exclusion of underrepresented cohorts (IEEE Ch4, ASEAN §B.2),
    - cultural-norm drift (IEEE, T3-04 candidate),
    - distributive access (FSD-002 §3.5.5),
    - affective-state shift (`CIRISRegistry#20`),
    - ecology-of-communication patterns (echo chambers, coordinated messaging, FSD-002 §3.5.3 v1.3 addition).
    Tracked at `CIRISLensCore#26`.
- **Federation-wide identity-drift correlation** — the in-agent identity-variance monitor is single-agent today; cross-agent drift correlation is a federation-side detector that lands with LensCore v0.6.
- **`goal:planet` scale emission** — T3-06 candidate (planetary-scale evidence emission) is next.
- **Signed `intra_agent_consistency` envelopes** — SelfObservation produces behavioral patterns; emitting them as signed structured envelopes is next.
- **Adaptive-filter trigger rates as detection signals** — trigger rates today are filter-internal config; exporting them as detection signals is tracked at `CIRISAgent#819`.
- **Per-trace calibration-version pin** — the agent does not yet record which RATCHET calibration version a trace was emitted under. Next step tracked at `CIRISAgent#820`.

Proposed pointer (from seed): `CIRISLensCore detector family` (substrate work — lands with LensCore v0.6); monitor pointer: `CIRISAI/RATCHET calibration packages (versioned, hash-pinned)`. Agent-side primary code references: `ciris_engine/logic/infrastructure/sub_services/identity_variance_monitor.py`, `ciris_engine/logic/services/governance/self_observation/service.py`, `ciris_engine/logic/services/governance/adaptive_filter/service.py`, `ciris_engine/schemas/runtime/system_context.py:163`.

## Tracked requirements

- **Umbrella(s)**: `CIRISLensCore#26` — F-3 detector family per FSD-002 §3.5.3
- **2.9.7**: `CIRISAgent#819` — adaptive-filter trigger rates as detection signal; `CIRISAgent#820` — calibration_version per trace

See `compliance/README.md` cross-cutting findings table for the 3.0 requirements finalization context.
<!-- END HUMAN -->
