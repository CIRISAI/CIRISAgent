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
## CIRIS-side compliance implementation

D05 detection lives primarily in CIRISLensCore (the post-trace federation analytics layer). CIRISAgent's role is to emit the trace dimensions LensCore needs and to host the agent-side faculties that produce them. The bulk of F-3 detector implementation is NOT in this repo.

- **Agent-side dimension emission** (what the agent measures and ships):
    - `ciris_engine/logic/infrastructure/sub_services/identity_variance_monitor.py:43-50` — `IdentityVarianceMonitor`: per-window drift sampling; the only fully-implemented `detection:temporal_drift` analogue in the agent today
    - `ciris_engine/logic/services/governance/self_observation/service.py` — SelfObservation service: tracks behavioral patterns over time; surfaces `detection:intra_agent_consistency` candidates
    - `ciris_engine/logic/services/governance/adaptive_filter/service.py:39+` — `AdaptiveFilterService`: filters input streams against drift baselines; emits signals downstream
    - `ciris_engine/schemas/infrastructure/behavioral_patterns.py` — `BehavioralPattern`, `reliability_level` (consistency metric, `behavioral_patterns.py:123`)
    - `ciris_engine/schemas/infrastructure/identity_variance.py:78` — `VarianceCheckMetadata` (handler_name="identity_variance_monitor")
- **Per-trace integrity dimensions for federation analysis**:
    - `ciris_engine/schemas/runtime/system_context.py:163` — `verify_attestation` projected into every traced thought; the six `*_ok` booleans are documented as near-zero-correlation dimensions for k_eff analysis (`FSD/TRACE_WIRE_FORMAT.md:519-522`)
    - `FSD/PROOF_OF_BENEFIT_FEDERATION.md:52` — `N_eff` metric: empirical participation-ratio + entropy-perplexity over the 17-dim constraint vector; measured peak 9.51, lifetime mean 7.20
- **Conscience-layer detection** (per-thought, in-agent):
    - `ciris_engine/logic/dma/idma.py:10` — IDMA `k_eff < 2` / rigidity-phase detector (per-thought fragility detection)
    - `ciris_engine/schemas/conscience/core.py:199` — `reasoning_transparency` scalar (0.0-1.0) feeds downstream correlation analysis
    - Conscience faculties (`conscience:optimization_veto`, `conscience:epistemic_humility`, `conscience:coherence`, `conscience:entropy`) produce signals that detection layers correlate post-hoc
- **Aggregate-correlation substrate** (what the agent provides for LensCore):
    - `ciris_engine/logic/services/graph/tsdb_consolidation/service.py:97` — `AuditConsolidator` produces per-window summary nodes carrying the audit evidence list; downstream lens computes aggregate-footprint metrics from these
    - `ciris_engine/logic/services/graph/incident_service/service.py:38-54` — `IncidentManagementService`: ingests `/app/logs/incidents_latest.log` warnings/errors as graph nodes; aggregates per-class incident counts for `detection:correlated_action:*` rollups
    - `tools/qa_runner/modules/safety_battery.py:241-246` — `_capture_ci_provenance`: captures GitHub Actions run metadata into safety battery output for cross-run drift analysis

## Observability hooks

- **LensCore F-3 detector family**: NOT implemented in this repo. The seed-named detectors that the federation analytics layer is expected to host:
    - `detection:correlated_action:aggregate_footprint:energy_carbon` — agent emits per-call token counts via `ciris_adapters/model_usage/`, lens aggregates
    - `detection:correlated_action:aggregate_footprint:expendability_of_persons` — MH §36 "structures of sin" detector; no agent-side wiring
    - `detection:correlated_action:participation_exclusion:underrepresented_population` — depends on demographic metadata the agent does not collect
    - `detection:temporal_drift` — partial: agent has `IdentityVarianceMonitor`, no cross-agent federation drift detector
    - `detection:intra_agent_consistency` — partial: agent has SelfObservation snapshots; no cross-window consistency detector emitting structured signals
    - `detection:distributive:access:*` — not implemented; v1.3 universal-destination-of-goods closure has no detector
- **RATCHET calibration packages**: versioned, hash-pinned externally to this repo. Agent must surface the calibration version it was last evaluated against — currently no such field exists in `AttestationResult`.
- **Audit chain queries** (the integrity substrate that detection findings reference):
    - `engine.audit_list_entries(filter_json, cursor, limit)` — paginated DESC by sequence_number; used by both `verify_complete_chain` and downstream rollups
    - `engine.audit_verify_chain` — end-to-end walk against `cirislens_audit_log`
- **Per-trace constraint vector**: 17-dim space per `FSD/PROOF_OF_BENEFIT_FEDERATION.md:52`; the lens computes N_eff to validate Sybil-resistance — every action contributes to this constraint vector through its trace metadata.
- **Federation evidence_refs**: emitted Contributions cite `dimensions: ["D05"]` when the contribution itself produces detector-relevant evidence (rare from the agent; common from the lens looking back at agent traces).
- **Telemetry rollup**: `/v1/telemetry/unified` (`ciris_engine/logic/adapters/api/routes/telemetry.py:1879+`) provides operational-view aggregates; not detector-grade but consumed by drift dashboards.

## Known gaps / not-yet-implemented

This is the dimension with the deepest gap between the seed claim and the implementation. Honest catalog:

- **F-3 detectors NOT implemented in LensCore** (referenced in seed but not in any CIRISAI repo yet):
    - `detection:correlated_action:aggregate_footprint:expendability_of_persons` (MH §36)
    - `detection:correlated_action:participation_exclusion:underrepresented_population` (IEEE Ch4, ASEAN §B.2)
    - `detection:correlated_action:cultural_norm_drift:{population}` (IEEE; T3-04 v1.5+ candidate)
    - `detection:correlated_action:aggregate_footprint:planetary_impact` (IEEE Ch8)
    - `detection:distributive:access:*` family (all 4 batches engage, no detector exists)
    - `detection:affective_state_shift:{axis}` (IEEE; T3-01 v1.5+ HIGH priority candidate, CIRISRegistry#20)
- **Agent-side gaps**:
    - `IdentityVarianceMonitor` is single-agent; no federation-wide drift correlation
    - No emission of `goal:planet` scale (T3-06 REINFORCED candidate from MH + IEEE Ch4 + IEEE Ch8)
    - SelfObservation produces behavioral patterns but not signed structured `detection:intra_agent_consistency` envelopes
    - Adaptive filter trigger rates are not exported as detection signals (only as filter-internal config)
- **Calibration version drift**: RATCHET calibration packages are versioned externally but the agent does not pin which calibration version a given trace was emitted under. A downstream consumer cannot reproduce calibration-dependent detection without timestamp-guessing.
- **CIRISVerify → LensCore link**: integrity dimensions (`*_ok` booleans) are projected into traces today but the lens-side F-3 family that correlates them is the missing component. Substrate substitution trajectory routes this into the LensCore Rust crate at step 3.

Proposed pointer (from seed): `CIRISLensCore detector family` (NOT in this repo); monitor pointer: `CIRISAI/RATCHET calibration packages (versioned, hash-pinned)`. Agent-side primary code references: `ciris_engine/logic/infrastructure/sub_services/identity_variance_monitor.py`, `ciris_engine/logic/services/governance/self_observation/service.py`, `ciris_engine/logic/services/governance/adaptive_filter/service.py`, `ciris_engine/schemas/runtime/system_context.py:163` (per-trace dimension projection).
<!-- END HUMAN -->
