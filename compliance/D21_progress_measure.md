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
## What this dimension covers

Progress measure is the bottom layer of the four-level decision hierarchy: Goal (what we're trying to achieve) → Approach (the strategy) → Method (the specific algorithm) → Progress Measure (how we know we're getting there). For an auditor, the question is: "Can you show me the numbers, declared in advance, that tell you whether you're succeeding?"

## How CIRIS implements this today

A dedicated Telemetry Service (one of the seven graph services) collects structured metrics, and the Round 1 baseline (`docs/grant/ROUND1_BASELINE_2026-04-22.md`) declares the headline counts: 22 core services, 257 API routes, 10662 collected tests. Each metric is anchored to an audit entry so that claims about progress are tamper-evident.

**Telemetry Service (the measurement substrate).**
- `ciris_engine/logic/services/graph/telemetry_service/` — service implementation
- `ciris_engine/schemas/services/graph/telemetry.py:150` — the `metric_name` field on telemetry records
- `ciris_engine/schemas/telemetry/core.py:101` — `MetricData` schema
- `ciris_engine/schemas/telemetry/unified.py:18` — `MetricDataPoint`, `:32` — `ResourceMetricWithStats`
- `ciris_engine/schemas/telemetry/collector.py:35` — `MetricEntry`

**The fragility scalar `k_eff` (the core epistemic-health measurement).** Computed by the inverse-decision check (IDMA — flags when the agent is approaching a decision-boundary), one number per thought.
- `ciris_engine/logic/dma/idma.py` — emits `k_eff = k / (1 + ρ(k-1))` per thought
- `ciris_engine/schemas/dma/results.py:45-75` — IDMA result schema; the `reasoning` field carries the epistemic-health measure
- `ciris_engine/data/localized/CIRIS_COMPREHENSIVE_GUIDE.txt:233-239` — `k_eff` documented as the canonical fragility measure

**Conscience scalars (per-thought safety measurements).** Each internal safety check on a thought emits a normalized scalar.
- `ciris_engine/logic/conscience/core.py:38-45` — entropy / coherence / optimization-veto thresholds
- `ciris_engine/logic/conscience/core.py` — `EntropyConscience`, `CoherenceConscience` emit normalized scalars per thought

**Commons Credits reputation summary (governance-weight measure).** Credit records (CommonsCredits — non-monetary recognition of substrate-building work) aggregate into a per-agent reputation summary.
- `ciris_engine/schemas/services/agent_credits.py:180-226` — `AgentCreditSummary` (total interactions, resolved interactions, average coherence, `k_eff` diversity)

**API telemetry surface (the reporting endpoints).**
- `ciris_engine/logic/adapters/api/routes/telemetry.py:681` — `GET /v1/telemetry/overview`
- `:748` — `GET /v1/telemetry/resources`
- `:966` — `GET /v1/telemetry/metrics`
- `:1260` — `GET /v1/telemetry/traces`
- `:1431` — `GET /v1/telemetry/logs`
- `:1717` — `POST /v1/telemetry/query` (custom query)
- `:1756` — `GET /v1/telemetry/metrics/{metric_name}`
- `:1854` — `GET /v1/telemetry/unified` (the headline "X / Y services healthy" view)
- `:1917` — `GET /v1/telemetry/resources/history`
- `:639` — `GET /v1/telemetry/otlp/{signal}` (OTLP export for external observability stacks)

**Incident-management service (negative progress).**
- `ciris_engine/logic/services/graph/incident_service/` — tracks incidents as anti-progress observations

**Policy text.**
- `MISSION.md` — the four-level hierarchy; progress is measured against Meta-Goal M-1
- `docs/grant/ROUND1_BASELINE_2026-04-22.md` — declared baseline metrics (service taxonomy, endpoint inventory, test collection)
- `CLAUDE.md` (root) — declared quality standards: 80% test-coverage target, <1s response time, ≤4GB memory

**Tests.**
- `tests/` — 10662 collected tests (per baseline) — the meta-progress measure
- `tests/ciris_engine/logic/services/graph/telemetry_service/` (where present)

**Configuration.**
- `EssentialConfig` — declared performance bounds (memory, depth, timeouts)
- `ConscienceConfig` thresholds — declared scalar bounds

Proposed pointer (from seed): `(none specified in seed; please fill)`

## How you can tell it's working (observability)

If you wanted to verify this from outside, the telemetry stream exports in standard formats (OTLP, Prometheus, Graphite), every progress claim is anchored to a tamper-evident audit entry, and the unified health endpoint returns a single roll-up number.

- **OTLP export**: `GET /v1/telemetry/otlp/{metrics,traces,logs}` emits CNCF-compatible OTLP JSON. External observability platforms (Grafana, Honeycomb, Datadog) can consume the stream directly.
- **Prometheus / Graphite converters**: `routes/telemetry_converters.py:36` (`convert_to_graphite`, `convert_to_prometheus`)
- **Unified service health**: `GET /v1/telemetry/unified` returns `services_online`/`services_total` — the headline measure of system integrity.
- **Audit chain anchor**: every progress measurement is anchored to an audit entry (`GET /v1/audit/entries`) for tamper-evident progress claims.
- **Drift detectors**: `detection:temporal_drift` on conscience scalars; `detection:correlated_action:aggregate_footprint:*` on resource consumption.
- **Federation evidence_refs**: a typed federation message citing `dimensions: ["D21"]` resolves through this seed to MH structural-coherence markers, EU §III.7 measurable progress, IEEE Ch7 documentation-as-progress-measure.

Proposed pointer (from seed): `(none specified in seed; please fill)`

## Current limitations & next steps

- **Typed `progress_measure:{metric}` federation envelope**: shared work with the upstream CIRIS substrate (`CIRISRegistry/FSD/FSD-002_FEDERATION_SURFACE.md §3.6.2`, `CIRISNodeCore/FSD/PROGRESS_MEASURE_PRIMITIVE.md`). Required fields are `tracks[]`, `computation`, `validity_window`, `goodhart_resistance`. The agent will emit at telemetry-write time when NodeCore P15 ships.
- **Per-Goal progress-measure binding**: shared work with the upstream substrate (FSD-002 §3.6.2 Tier-2 hierarchy). The hierarchy resolves goal-binding by walking up from method to approach to goal — the binding falls out structurally when NodeCore P12-P15 ship. The agent emits the per-metric data today.
- **ASEAN stops at recommendation level** rather than measurement-protocol level. CIRIS exceeds ASEAN's surface here — measurement protocols are richly implemented.
- **IEEE Ch7 `progress_measure:wellbeing_indicators`**: shared work with the upstream substrate (FSD-002 §3.6.2). Bundles the conscience entropy/coherence scalars plus the `k_eff` fragility scalar. The substrate-side `goodhart_resistance` field is the guard against optimization-toward-the-metric.
- **Long-horizon progress claims** (next step, tracked in `CIRISAgent#830`): the `validity_window` field on the typed envelope plus the Stage 9 Archive retention policy (`CIRISNodeCore/FSD/CONTRIBUTION_LIFECYCLE.md §11`) carry the longitudinal slice. TSDB consolidation feeds it; emission rides the existing primitive with a multi-period validity window.

## Quantitative baseline

Per [MEASUREMENT_METHODOLOGY.md](MEASUREMENT_METHODOLOGY.md), the canonical numeric evidence for this dimension flows from `tools/analysis/round1_grant_baseline.py`. Current baseline ([`baselines/2026-05-28.md`](baselines/2026-05-28.md)):

- **API method+path routes**: 256 (GET 138, POST 83, PUT 17, PATCH 2, DELETE 16) — the externally-measurable surface for `progress_measure:{metric}` claims
- **Core services**: 22 (each carrying its own progress metrics via the telemetry service rollup)
- **Auth-related routes**: 16 (the authZ audit surface relevant to declared-metric trust)

Historical drift: 257 → 255 → 256 across 2026-04-22 → 2026-04-24 → 2026-05-28 (see [`baselines/`](baselines/) for the full set of dated snapshots). Drift is normal; the methodology requires re-running the script before any external claim.

## Tracked requirements

- **Umbrella(s)**: `CIRISAgent#803` — Typed `<dimension>:*` wire envelope emission
- **2.9.7**: `CIRISAgent#830` — TSDB longitudinal progress emission

See `compliance/README.md` cross-cutting findings table for the 3.0 requirements finalization context.
<!-- END HUMAN -->
