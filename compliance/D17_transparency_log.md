# D17 — `transparency_log:*` (STRONG-3)

> CIRISVerify per-stakeholder disclosure log

**Seed reference**: `SEED_DIMENSIONS.yaml` v1.0, dimension `D17` ([source](https://github.com/CIRISAI/ciris-response-magnifica-humanitas/blob/main/SEED_DIMENSIONS.yaml))
**Accord principle**: fidelity
**Attestation density**: MH=2 · EU=5 · IEEE=23 · ASEAN=10 · total=40

**Absent from**: MH — Non-zero but structurally low (2). Classified STRONG-3 by analyst because encyclical genre is not a technical-disclosure framework.
  *Functional analogue*: detection:correlated_action:ecology_of_communication:* + the F-3 detector family

## Regulatory attestations

*(Auto-rendered from seed; do not hand-edit. Re-run `python tools/compliance/generate_ciris_compliance_stubs.py tools/compliance/SEED_DIMENSIONS.yaml compliance/` after seed updates.)*

- **MH** (Magnifica Humanitas (On Safeguarding the Human Person in the Time of Artificial Intelligence)) — *§§ various*
    > "honest signs of authority and intent"
    Wire form: `transparency_log:* (sparse)`
- **EU** (Ethics Guidelines for Trustworthy AI) — *§1.4 + §III.4*
    > "transparency about purpose, capability, and limitations"
    Wire form: `transparency_log:per_stakeholder_disclosure`
- **IEEE** (Ethically Aligned Design, First Edition) — *Ch2 P5 + Ch6 + Ch11*
    > "traceability + verifiability + intelligibility four-dimensional transparency"
    Wire form: `transparency_log:* (23 attestations)`
- **ASEAN** (ASEAN Guide on AI Governance and Ethics) — *§B.1 + §C.4*
    > "transparency and explainability through documentation and disclosure"
    Wire form: `transparency_log:* (10 attestations)`

## Wire primitives

- `transparency_log:*`

---

<!-- BEGIN HUMAN -->
## CIRIS-side compliance implementation

The transparency log primitive is owned by CIRISVerify (per-stakeholder mandatory disclosure log). CIRISAgent integrates it via the `ciris_verify` adapter and surfaces disclosure context to every reasoning trace, API response, and LLM-context block. The agent does NOT host the canonical log — it consumes and propagates.

- **Adapter integration**:
    - `ciris_adapters/ciris_verify/adapter.py:339-350` — `get_mandatory_disclosure()` returns the `MandatoryDisclosure` that MUST be shown to users (severity ∈ info/warning/critical)
    - `ciris_adapters/ciris_verify/service.py:232-249` — `CIRISVerifyService.get_mandatory_disclosure()` resolves disclosure from current license status; fallback message when verifier unavailable
    - `ciris_adapters/ciris_verify/ffi_bindings/types.py` — `MandatoryDisclosure`, `DisclosureSeverity` schemas (mirror of CIRISVerify's Rust-side types)
- **Per-stakeholder disclosure propagation**:
    - `ciris_engine/schemas/services/attestation.py:244-298` — `VerifyAttestationContext`: unified disclosure-and-attestation context; `disclosure_text` + `disclosure_severity` flow into:
        - Agent LLM context (SystemSnapshot) — agent sees its own disclosure obligations
        - Accord traces (CIRISLens) — every traced thought carries the disclosure block
        - API responses — clients receive the disclosure they must render
    - `ciris_engine/schemas/runtime/system_context.py:163` — `verify_attestation` field on SystemSnapshot; `system_context.py:169` retains legacy `disclosure_text` field for backwards compat
    - `FSD/TRACE_WIRE_FORMAT.md:540-544` — `disclosure_severity` ∈ {info, warning, critical} drives UI banner severity in CIRIS-aware clients
- **Visibility/transparency services** (agent-side analogue of stakeholder disclosure):
    - `ciris_engine/logic/services/governance/visibility/service.py:39-150` — `VisibilityService` provides TRACES (reasoning transparency); `_transparency_requests` counter tracked per-query
    - `ciris_engine/schemas/services/visibility.py:19` — reasoning-state snapshot schema
    - `ciris_engine/schemas/dma/results.py:252` — every DMA result preserves the user prompt for debugging/transparency
- **Audit-chain transparency** (the persistent per-stakeholder log on the agent side):
    - `ciris_engine/logic/services/graph/audit_service/service.py` — `cirislens_audit_log` records every action with signing key, sequence number, hash chain link; tenant-scoped per `_audit_tenant_id`
    - `ciris_engine/logic/audit/verifier.py:72` — `verify_complete_chain()` lets any downstream consumer verify the disclosure log's integrity end-to-end
- **License/tier disclosure (MH "honest signs of authority and intent")**:
    - `ciris_adapters/ciris_verify/adapter.py:362-370` — `is_licensed()` and `get_agent_tier()`; mandatory disclosure differs between community mode and licensed mode

## Observability hooks

- **LensCore F-3 family**: `detection:correlated_action:ecology_of_communication:*` is the functional analogue named in the seed for MH's transparency framing. Not implemented in this repo.
- **Trace projection**: every reasoning trace ships the full `VerifyAttestationContext` block (`FSD/TRACE_WIRE_FORMAT.md:495+`), giving the lens a per-trace per-stakeholder disclosure history at GENERIC privacy level. The block includes pre-rendered `attestation_context` summary string used in agent LLM context, API responses, and traces — all three surfaces render the same disclosure text for consistency.
- **Audit chain queries**: `engine.audit_list_entries(filter_json, cursor, limit)` exposes the persistent log; tenant_id filter scopes per-stakeholder views.
- **Federation evidence_refs**: emitted Contributions cite `dimensions: ["D17"]` when the action's disclosure obligation is the load-bearing claim. EU `transparency_log:per_stakeholder_disclosure` (§1.4 + §III.4) is the most directly attested form.
- **Telemetry endpoint**: `/v1/telemetry/unified` surfaces `_transparency_requests` count from VisibilityService and disclosure-render counts from API middleware.

## Known gaps / not-yet-implemented

- **Per-stakeholder routing**: CIRISVerify's transparency log is per-license/per-tier, not per-affected-stakeholder. IEEE's 4-dim transparency (traceability + verifiability + intelligibility + a fourth via Ch2 P5 + Ch6 + Ch11) is partially covered — traceability via audit chain, verifiability via attestation ladder, but intelligibility-per-stakeholder is unwired.
- **Disclosure history**: the agent renders the CURRENT mandatory disclosure into every trace, but does not retain a per-stakeholder disclosure VERSION HISTORY. If the disclosure text changes (e.g. license tier upgrade), past traces show the old text but there's no explicit version field linking traces to disclosure manifests.
- **Cross-substrate provenance**: the disclosure text shown in API responses originates in CIRISVerify (Rust), is cached in `ciris_adapters/ciris_verify/service.py:65` (`CachedLicenseStatus`), and re-renders in clients. No SHA-256 chain proving the rendered text equals the CIRISVerify-signed text; trust is transitively rooted in the CIRISVerify hardware attestation, not in a separate signature on the disclosure payload.
- **MH §honesty-signs** (MH=2 attestations) is not directly addressed by the technical log primitive — encyclical "honest signs of authority and intent" is functionally covered by the per-trace `attestation_context` summary plus license-tier disclosure. Substrate-specced as `detection:correlated_action:ecology_of_communication:*` (FSD-002 §3.5.3 v1.3 axis-vocabulary addition) with `aspect` ∈ `echo_chamber_density` | `information_silo_correlation` | `coordinated_messaging_pattern` | `cross_cohort_information_flow`. LensCore detector lands at substrate-substitution step 3; calibrated via `CIRISAI/RATCHET/calibration/correlated_action_v{N}.yaml` per §4.9.1 axis-vocabulary discipline. **Substrate-specced, LensCore implementation pending.**
- **Test coverage**: `ciris_adapters/ciris_verify/tests/test_adapter.py` exercises adapter loading and verification flow but no test asserts that disclosure_text actually appears in trace rows or API responses — the projection is implicit.
- **No `/v1/system/federation` endpoint exists yet** despite seed reference; `ciris_engine/logic/adapters/api/routes/system/health.py` exposes `/health`, `/startup-status`, `/time` but no federation status route. This was claimed for 2.9.4 but is not present at the audited HEAD.
- **Audit-chain disclosure traceability**: the chain records WHAT action happened with WHICH signing key but not WHICH disclosure version was active at action-time. A consumer reconstructing per-stakeholder disclosure history must cross-reference action timestamps with CIRISVerify license-status cache lifetimes.
- **MH §honest-signs** (MH=2 attestations) is structurally low because encyclical genre is not a technical-disclosure framework; the seed's functional analogue (`detection:correlated_action:ecology_of_communication:*` + F-3 detector family) is a lens-side primitive that doesn't yet exist anywhere in CIRISAI.

Proposed pointer (from seed): `CIRISVerify transparency_log` (canonical primitive lives outside this repo). Agent-side integration: `ciris_adapters/ciris_verify/adapter.py:339-350`, `ciris_adapters/ciris_verify/service.py:232-249`, `ciris_engine/schemas/services/attestation.py:244-298` (`VerifyAttestationContext`).

## Quantitative baseline

Per [MEASUREMENT_METHODOLOGY.md](MEASUREMENT_METHODOLOGY.md), externally-observable transparency surfaces in the current baseline ([`baselines/2026-05-28.md`](baselines/2026-05-28.md)):

- **22 core services** — each surfaces health + telemetry via the unified telemetry endpoint
- **256 API method+path routes** — full API surface available for per-stakeholder disclosure; **16 auth-related** routes (the authZ surface); **6 OAuth** routes (the multi-stakeholder identity surface)

Per the methodology, claims about CIRIS's transparency surface in grant or regulatory submissions cite the dated baseline file rather than embedding raw numbers — this prevents drift when routes are added/removed.
<!-- END HUMAN -->
