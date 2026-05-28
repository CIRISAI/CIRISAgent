# D21 — `progress_measure:*` (STRONG-3)

> Declared-metric outcomes for tracking progress toward goals

**Seed reference**: `SEED_DIMENSIONS.yaml` v1.0, dimension `D21` ([source](https://github.com/CIRISAI/ciris-response-magnifica-humanitas/blob/main/SEED_DIMENSIONS.yaml))
**Accord principle**: integrity
**Attestation density**: MH=1 · EU=1 · IEEE=8 · ASEAN=0 · total=10

**Absent from**: ASEAN — ASEAN stops at recommendation-level rather than measurement-protocol level.

## Regulatory attestations

*(Auto-rendered from seed; do not hand-edit. Re-run `python tools/compliance/generate_ciris_compliance_stubs.py tools/compliance/SEED_DIMENSIONS.yaml compliance/` after seed updates.)*

- **MH** (Magnifica Humanitas (On Safeguarding the Human Person in the Time of Artificial Intelligence)) — *§§ various*
    > "structural-coherence progress markers"
    Wire form: `progress_measure:*`
- **EU** (Ethics Guidelines for Trustworthy AI) — *§III.7*
    > "measurable progress toward trustworthiness"
    Wire form: `progress_measure:*`
- **IEEE** (Ethically Aligned Design, First Edition) — *Ch7 (8 attestations)*
    > "documentation criteria as progress_measure; well-being indicators"
    Wire form: `progress_measure:* (8 distinct)`

## Wire primitives

- `progress_measure:{metric}`

---

<!-- BEGIN HUMAN -->
## CIRIS-side compliance implementation

`progress_measure:*` is the bottom layer of the Goal→Approach→Method→Progress-Measure DAG. CIRIS implements progress measurement through a dedicated Telemetry Service (one of the 7 graph services) plus a structured metric schema. The Round 1 baseline (`docs/grant/ROUND1_BASELINE_2026-04-22.md`) declares the surface: 22 core services, 257 method+path API routes, 10662 collected tests — these counts are the headline progress measures.

- **Code references** — Telemetry Service (the measurement substrate):
    - `ciris_engine/logic/services/graph/telemetry_service/` — service implementation
    - `ciris_engine/schemas/services/graph/telemetry.py:150` — `metric_name` field on telemetry records
    - `ciris_engine/schemas/telemetry/core.py:101` — `MetricData` schema
    - `ciris_engine/schemas/telemetry/unified.py:18` — `MetricDataPoint`, `:32` — `ResourceMetricWithStats`
    - `ciris_engine/schemas/telemetry/collector.py:35` — `MetricEntry`
- **Code references** — IDMA k_eff (the core quality measurement):
    - `ciris_engine/logic/dma/idma.py` — Intuition DMA; emits `k_eff = k / (1 + ρ(k-1))` per thought
    - `ciris_engine/schemas/dma/results.py:45-75` — IDMA result schema; `reasoning` field carries the epistemic-health progress measure
    - `ciris_engine/data/localized/CIRIS_COMPREHENSIVE_GUIDE.txt:233-239` — k_eff documented as the canonical fragility progress measure
- **Code references** — conscience scalars (per-thought progress measures):
    - `ciris_engine/logic/conscience/core.py:38-45` — entropy / coherence / optimization-veto scalar thresholds
    - `ciris_engine/logic/conscience/core.py` — `EntropyConscience`, `CoherenceConscience` emit normalized scalars per thought
- **Code references** — Commons Credits reputation summary (governance-weight progress measure):
    - `ciris_engine/schemas/services/agent_credits.py:180-226` — `AgentCreditSummary` (total_interactions, resolved_interactions, average_coherence, k_eff diversity)
- **Code references** — API telemetry surface:
    - `ciris_engine/logic/adapters/api/routes/telemetry.py:681` — `GET /v1/telemetry/overview`
    - `:748` — `GET /v1/telemetry/resources`
    - `:966` — `GET /v1/telemetry/metrics`
    - `:1260` — `GET /v1/telemetry/traces`
    - `:1431` — `GET /v1/telemetry/logs`
    - `:1717` — `POST /v1/telemetry/query` (custom telemetry query)
    - `:1756` — `GET /v1/telemetry/metrics/{metric_name}`
    - `:1854` — `GET /v1/telemetry/unified` (the "35/35 services healthy" headline)
    - `:1917` — `GET /v1/telemetry/resources/history`
    - `:639` — `GET /v1/telemetry/otlp/{signal}` (OTLP export for external observability stacks)
- **Code references** — incident-management service (negative-progress measures):
    - `ciris_engine/logic/services/graph/incident_service/` — tracks incidents as anti-progress observations
- **Policy text**:
    - `MISSION.md` — Goal-Approach-Method-Progress DAG; progress is measured against Meta-Goal M-1
    - `docs/grant/ROUND1_BASELINE_2026-04-22.md` — declared baseline metrics (service taxonomy, endpoint inventory, test collection)
    - `CLAUDE.md` (root) — declared quality standards: test coverage target 80%, response time <1s, memory ≤4GB
- **Test coverage**:
    - `tests/` — 10662 collected tests (per baseline) — the meta-progress-measure
    - `tests/ciris_engine/logic/services/graph/telemetry_service/` (if present)
- **Configuration surface**:
    - `EssentialConfig` — declared performance bounds (memory, depth, timeouts)
    - `ConscienceConfig` thresholds — declared scalar bounds

Proposed pointer (from seed): `(none specified in seed; please fill)`

## Observability hooks

- **OTLP export**: `GET /v1/telemetry/otlp/{metrics,traces,logs}` emits CNCF-compatible OTLP JSON. External observability platforms (Grafana, Honeycomb, Datadog) can consume the progress-measure stream directly.
- **Prometheus / Graphite converters**: `routes/telemetry_converters.py:36` (`convert_to_graphite`, `convert_to_prometheus`)
- **Unified service health**: `GET /v1/telemetry/unified` returns `services_online`/`services_total` — the headline progress measure of system integrity.
- **Audit chain**: every progress measurement is anchored to an audit entry (`GET /v1/audit/entries`) for tamper-evident progress claims.
- **LensCore F-3 detectors**: `detection:temporal_drift` on conscience scalars; `detection:correlated_action:aggregate_footprint:*` on resource consumption.
- **Federation evidence_refs**: a Contribution citing `dimensions: ["D21"]` resolves through this seed to MH structural-coherence markers, EU §III.7 measurable progress, IEEE Ch7 documentation-as-progress-measure.

Proposed pointer (from seed): `(none specified in seed; please fill)`

## Known gaps / not-yet-implemented

- **No declared `progress_measure:{metric}` wire-form emission**: telemetry metrics are exposed via API but not yet wrapped in a Contribution envelope tagged with `dimensions: ["D21"]`.
- **No per-Goal progress-measure binding**: telemetry counts everything but does not declaratively bind each metric to a specific Meta-Goal M-1 sub-goal. The connection between "this metric" and "this goal" lives in human-readable docs, not in machine-emitted wire envelopes.
- **ASEAN absent_batch**: ASEAN stops at recommendation level rather than measurement-protocol level. CIRIS exceeds ASEAN's surface here — measurement protocols are richly implemented.
- **`progress_measure:wellbeing_indicators` (IEEE Ch7)**: agent-wellbeing scalars (conscience entropy/coherence, IDMA k_eff) exist but are not bundled as a single "wellbeing indicator" attestation.
- **Long-horizon progress claims**: the telemetry surface measures runtime state; long-horizon progress (e.g., "this agent improved its k_eff from k=1.4 to k=2.1 over 90 days") requires the TSDB consolidation service (`tsdb_consolidation_service`) — implemented but not surfaced through a `progress_measure:longitudinal` wire form.
<!-- END HUMAN -->
