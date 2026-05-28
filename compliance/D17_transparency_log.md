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
## What this dimension covers

A transparency log is the running, mandatory record of what the agent has disclosed to whom — its capabilities, its limits, its licensing tier, and any warnings the user is entitled to see. Without a transparency log, "the system is transparent" is just a marketing claim; with one, anyone can replay the same disclosure history the agent rendered to a stakeholder at a specific moment in time.

## How CIRIS implements this today

The canonical signed disclosure register lives in the upstream CIRIS substrate (the Rust-based CIRISVerify component). CIRISAgent integrates with that register and propagates the current mandatory disclosure into three surfaces every time the agent acts: the agent's own reasoning context, the API responses it returns, and the reasoning traces it ships to the federation. All three surfaces render the same text for consistency.

- **Disclosure pulled from the signed register**:
    - `ciris_adapters/ciris_verify/adapter.py:339-350` — returns the `MandatoryDisclosure` that must be shown to users (severity info/warning/critical).
    - `ciris_adapters/ciris_verify/service.py:232-249` — resolves disclosure from current license status; safe fallback when the verifier is unavailable.
    - `ciris_adapters/ciris_verify/ffi_bindings/types.py` — `MandatoryDisclosure`, `DisclosureSeverity` schemas (mirror the substrate's Rust types).
- **Disclosure propagated into every surface**:
    - `ciris_engine/schemas/services/attestation.py:244-298` — `VerifyAttestationContext` carries `disclosure_text` + `disclosure_severity` into the agent's reasoning context (so the agent sees its own obligations), into reasoning traces (so the federation analytics layer sees what stakeholders saw), and into API responses (so clients can render the disclosure).
    - `ciris_engine/schemas/runtime/system_context.py:163` — `verify_attestation` on SystemSnapshot; `system_context.py:169` retains a legacy field for backward compatibility.
    - `FSD/TRACE_WIRE_FORMAT.md:540-544` — severity drives banner styling in CIRIS-aware clients.
- **Agent-side transparency services**:
    - `ciris_engine/logic/services/governance/visibility/service.py:39-150` — VisibilityService provides reasoning traces; a counter tracks transparency requests per-query.
    - `ciris_engine/schemas/services/visibility.py:19` — reasoning-state snapshot schema.
    - `ciris_engine/schemas/dma/results.py:252` — every reasoning decision preserves the user prompt for debugging.
- **The persistent per-action log**:
    - `ciris_engine/logic/services/graph/audit_service/service.py` — the cryptographically signed log of every action the agent took, tagged with signing key, sequence number, and chain link, scoped per tenant.
    - `ciris_engine/logic/audit/verifier.py:72` — `verify_complete_chain()` lets any downstream consumer verify the log's integrity end-to-end.
- **License-tier disclosure**:
    - `ciris_adapters/ciris_verify/adapter.py:362-370` — `is_licensed()` and `get_agent_tier()`; the mandatory disclosure differs between community mode and licensed mode.

## How you can tell it's working (observability)

If you want to verify what stakeholders were told and when, the surfaces below give you the disclosure text the agent rendered alongside the action it took.

- **Per-trace disclosure block**: every reasoning trace carries the full disclosure context (`FSD/TRACE_WIRE_FORMAT.md:495+`) including a pre-rendered summary string. The same text appears in agent reasoning context, API responses, and traces.
- **Re-walk the log**: `engine.audit_list_entries(filter_json, cursor, limit)` exposes the persistent log; a tenant filter scopes per-stakeholder views.
- **Federation evidence**: outbound Contributions cite `dimensions: ["D17"]` when disclosure is the load-bearing claim; EU §1.4 + §III.4 (per-stakeholder transparency) is the most directly attested form.
- **Telemetry**: `/v1/telemetry/unified` surfaces the transparency-request count from VisibilityService and disclosure-render counts from API middleware.

## Current limitations & next steps

- **Per-stakeholder routing** — disclosure today is per-license/per-tier, not yet per-affected-stakeholder. IEEE's four-dimensional transparency framing (traceability + verifiability + intelligibility + accountability) is partly covered today: traceability via the audit chain, verifiability via the attestation ladder. Per-stakeholder intelligibility is next.
- **Disclosure version history on traces** — the agent renders the current disclosure into every trace but does not yet stamp a version field linking that trace to a specific disclosure manifest. If license tier upgrades, the new disclosure renders in new traces but past traces don't carry an explicit version pointer. Tracked at `CIRISAgent#832` and `CIRISAgent#833`.
- **End-to-end signature on the rendered disclosure** — today, trust in the disclosure text is rooted transitively in the CIRISVerify hardware attestation. A separate signature on the rendered disclosure payload (so a third party can independently verify the rendered bytes match the substrate-signed bytes) is on the roadmap.
- **MH "honest signs" coverage** — the encyclical-genre framing of "honest signs of authority and intent" is partially covered by the per-trace attestation summary plus license-tier disclosure. Full coverage lands when the structural-pattern detector (LensCore's federation-side detector family that watches for patterns no single agent can see) ships its ecology-of-communication detector family per FSD-002 §3.5.3 (echo chambers, coordinated messaging, etc.). Shared work with the upstream LensCore substrate; tracked at `CIRISLensCore#26`.
- **`/v1/system/federation` endpoint** — coming next; currently `/health`, `/startup-status`, `/time` are exposed under `ciris_engine/logic/adapters/api/routes/system/health.py`. The federation manifest-hash route is tracked at `CIRISAgent#808`.
- **Disclosure-version anchor on each audit-chain entry** — the chain records what action happened with which signing key; recording which disclosure version was active at action-time (so a consumer can reconstruct stakeholder-history without timestamp-guessing) is next, tracked at `CIRISAgent#833`.
- **Test coverage** — adapter loading and verification are covered; a test asserting the disclosure text reaches trace rows and API responses end-to-end is next. Tracked at `CIRISAgent#804`.

Proposed pointer (from seed): `CIRISVerify transparency_log` (canonical primitive lives in the upstream substrate). Agent-side integration: `ciris_adapters/ciris_verify/adapter.py:339-350`, `ciris_adapters/ciris_verify/service.py:232-249`, `ciris_engine/schemas/services/attestation.py:244-298`.

## Quantitative baseline

Per [MEASUREMENT_METHODOLOGY.md](MEASUREMENT_METHODOLOGY.md), externally-observable transparency surfaces in the current baseline ([`baselines/2026-05-28.md`](baselines/2026-05-28.md)):

- **22 core services** — each surfaces health + telemetry via the unified telemetry endpoint
- **256 API method+path routes** — full API surface available for per-stakeholder disclosure; **16 auth-related** routes (the authZ surface); **6 OAuth** routes (the multi-stakeholder identity surface)

Per the methodology, claims about CIRIS's transparency surface in grant or regulatory submissions cite the dated baseline file rather than embedding raw numbers — this prevents drift when routes are added/removed.

## Tracked requirements

- **Umbrella(s)**: `CIRISAgent#803` — Typed `<dimension>:*` wire envelope emission; `CIRISLensCore#26` — F-3 detector family per FSD-002 §3.5.3
- **2.9.5**: `CIRISAgent#804` — disclosure_text trace test; `CIRISAgent#808` — /v1/system/federation manifest hash
- **2.9.7**: `CIRISAgent#832` — disclosure_version field on traces; `CIRISAgent#833` — audit chain records disclosure_version

See `compliance/README.md` cross-cutting findings table for the 3.0 requirements finalization context.
<!-- END HUMAN -->
