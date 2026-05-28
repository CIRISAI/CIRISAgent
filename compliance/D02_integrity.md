# D02 — `integrity:*` (STRONG-4)

> 'System holds together' structural anchor — auditable, reproducible, lifecycle integrity

**Seed reference**: `SEED_DIMENSIONS.yaml` v1.0, dimension `D02` ([source](https://github.com/CIRISAI/ciris-response-magnifica-humanitas/blob/main/SEED_DIMENSIONS.yaml))
**Accord principle**: integrity
**Attestation density**: MH=10 · EU=36 · IEEE=42 · ASEAN=44 · total=132

## Regulatory attestations

*(Auto-rendered from seed; do not hand-edit. Re-run `python tools/compliance/generate_ciris_compliance_stubs.py tools/compliance/SEED_DIMENSIONS.yaml compliance/` after seed updates.)*

- **MH** (Magnifica Humanitas (On Safeguarding the Human Person in the Time of Artificial Intelligence)) — *§40*
    > "doctrinal continuity is the integrity of the Magisterium"
    Wire form: `integrity:doctrinal_continuity`
- **EU** (Ethics Guidelines for Trustworthy AI) — *§1.4 Transparency*
    > "transparency requirement is linked with the explicability principle — data, system, and business models"
    Wire form: `integrity:explicability_for_trust`
- **IEEE** (Ethically Aligned Design, First Edition) — *Ch11 §I6*
    > "state accountability under public scrutiny is a constitutional integrity property of A/IS regulation"
    Wire form: `integrity:state_accountability_public_scrutiny`
- **ASEAN** (ASEAN Guide on AI Governance and Ethics) — *§B.6 Accountability/Integrity*
    > "AI should be designed and deployed with integrity throughout the lifecycle; auditable; reproducible"
    Wire form: `integrity:lifecycle_integrity_attestation`

## Wire primitives

- `integrity:*`

## Convergence note

Densest sub-leaf decomposition: ASEAN alone uses 44 distinct sub-leaves.

## Cross-source conflicts involving this dimension

- **CONF-03** (mutability, severity MEDIUM): ASEAN §A.4.18 admits explainability fallback; other three hold explainability as constitutive at deployment time

---

<!-- BEGIN HUMAN -->
## What this dimension covers

Integrity is the "system holds together" property — proof that the running agent is the same software that was signed, that its actions have not been silently rewritten, and that its identity has not drifted past safe bounds. Without integrity, every other ethical claim becomes unverifiable.

## How CIRIS implements this today

CIRIS rests integrity on four pillars: a cryptographically signed log of every action the agent took (the audit chain), a fingerprint of every file in the running build, a monitor that watches for drift between the agent's intended identity and its actual behavior, and modern signing algorithms (Ed25519 + ML-DSA-65 post-quantum) rooted in hardware where available. The audit chain is load-bearing; everything else hangs off it.

- **The audit chain — a tamper-evident running record of every action**:
    - `ciris_engine/logic/audit/persist_signing.py:23` — resolves the agent's signing key; the same key bridges the legacy log and signs every new entry.
    - `ciris_engine/logic/audit/persist_signing.py:60` — signs canonical bytes so two verifiers compute the same fingerprint.
    - `ciris_engine/logic/audit/persist_signing.py:78` — tenant scoping (`agent-default` when no tenant set).
    - `ciris_engine/logic/audit/verifier.py:72` — `verify_complete_chain()` walks the full log end-to-end and reports any break.
    - `ciris_engine/logic/audit/chain_bridge.py:132` — brings the older audit DB into the canonical store, signed by the same hardware-backed key.
    - `ciris_engine/logic/services/graph/audit_service/service.py:192-196` — every write goes through the persist chain; legacy direct-write paths are removed.
- **Build-time integrity — proof the running files match what CI signed**:
    - `tools/dev/stage_runtime.py:1-52` — produces a deterministic runtime tree so the fingerprint computed at sign time equals the one computed at verification time.
    - `tools/dev/stage_runtime.py:76-101` — exemption rules are themselves signed into the manifest, so what's excluded is auditable too.
    - `tools/templates/generate_manifest.py` — signs the manifest of pre-approved agent templates.
- **Identity-variance monitor — watches for drift from baseline**:
    - `ciris_engine/logic/infrastructure/sub_services/identity_variance_monitor.py:43-50` — tracks drift; triggers Wise Authority review when variance exceeds 20%.
    - `ciris_engine/schemas/infrastructure/identity_variance.py` — `IdentitySnapshot`, `IdentityDiff`, `VarianceReport`, `WAReviewRequest` schemas.
- **Hardware-rooted signing material — keys that never leave the chip**:
    - `ciris_adapters/ciris_verify/adapter.py:175-215` — migrates Wise Authority signing keys and the secrets master key into a Trusted Platform Module (TPM — a hardware chip that signs cryptographically without ever exposing the private key) or platform secure enclave when available.
    - `ciris_engine/logic/services/infrastructure/authentication/service.py:1790-1859` — publishes the agent's public key to the federation directory; verifiers resolve key ID → pubkey from there.
- **Schemas that carry the integrity state**:
    - `ciris_engine/schemas/services/attestation.py:13-219` — `AttestationResult` carries booleans for audit, file-integrity, module-integrity, per-file results, and failure reasons.
    - `ciris_engine/schemas/audit/hash_chain.py` and `ciris_engine/schemas/audit/verification.py` — chain and verification schemas.
    - `FSD/TRACE_WIRE_FORMAT.md:495-562` — federation wire spec for the per-trace integrity block.

## How you can tell it's working (observability)

If you want to verify integrity yourself, the surfaces below tell you what the agent claims and let you re-check the claim independently.

- **Per-trace integrity block**: every traced thought carries six near-independent integrity signals (audit-chain OK, file-integrity OK, binary OK, environment OK, registry OK, hardware-backed) via `VerifyAttestationContext` (`ciris_engine/schemas/runtime/system_context.py:163`). They are independent on purpose so a downstream analyst cannot be fooled by one signal masking another (`FSD/TRACE_WIRE_FORMAT.md:519-522`).
- **Re-walk the chain**: `engine.audit_list_entries(filter_json, cursor, limit)` paginates the log; `engine.audit_verify_chain` walks it end-to-end. A production fixture (clean + tampered, 69 entries) exercises both paths — see `ciris_engine/logic/audit/verifier.py:72-100`.
- **Identity-drift telemetry**: the variance monitor periodically writes `IdentitySnapshot` nodes (`created_by="identity_variance_monitor"`, `ciris_engine/schemas/services/nodes.py:281`); drift over 20% raises a Wise Authority review request.
- **Unified telemetry rollup**: `/v1/telemetry/unified` (`ciris_engine/logic/adapters/api/routes/telemetry.py:1879+`) aggregates audit, incident, and TSDB services into a single integrity health view.
- **Long-window preservation**: TSDB consolidation preserves the chain across consolidation windows (`ciris_engine/logic/services/graph/tsdb_consolidation/service.py:539`) and writes a per-window audit summary node (`service.py:97`).
- **Federation evidence**: outbound Contributions cite `dimensions: ["D02"]` when integrity is the load-bearing claim; the per-trace integrity block carries the full ladder state.

## Current limitations & next steps

- **Cross-trace correlation detector (LensCore F-3 family)** — coming next via the upstream LensCore substrate. The detector family is specified in `CIRISRegistry/FSD/FSD-002_FEDERATION_SURFACE.md §3.5.1` (chain-integrity break detector + intra-agent consistency detector). LensCore v0.5 ships three detectors today; the chain-integrity family lands in v0.6 (`CIRISLensCore/FSD/LENS_CORE_V0_5.md §4.7`). Tracked at `CIRISLensCore#26`.
- **iOS App Attest at L2** — the L2 hardware-rooted check passes on iOS today via Secure Enclave key storage. The App Attest token piece (which adds vendor-platform device-attestation alongside Secure Enclave key storage) is staged; the wire shape is specified (`IOSAttestation` proto with `app_attest_assertion` + `device_check_token`). iOS App Attest integration is the next iOS-specific step. See D18 for the full L1–L5 ladder semantics.
- **Key rotation as a signed event** — the public-key directory accepts registration; rotation is operator-driven today. Next step: emit rotation as a structural delegation event over the wire (FSD-002 §2.2.1 `delegates_to:hardware_rotation`), with anti-rollback enforced via the `rollback_detected:{revision_field}` primitive (FSD-002 §3.2).
- **Per-window tamper-evident anchor in TSDB summaries** — consolidation summary nodes today carry the audit list but no separate chain-hash anchor; the integrity guarantee is implicit in the chain rather than explicit in the summary.
- **CONF-03 explainability-fallback mutability flag** — the ASEAN explainability-fallback admissibility is not yet flagged in outbound evidence; downstream consumers cannot yet distinguish "explainability constitutive" from "explainability fallback admissible."
- **Per-locale signed sub-manifests** — localization artifacts (`localization/*.json`, `ciris_engine/data/localized/*.txt`) currently share a single coarse hash. Per-locale granularity is shared work with the upstream CIRISRegistry substrate; tracked at `CIRISRegistry#29`.
- **Composite integrity fixture** — existing tests cover chain-write and end-to-end verification against a 69-entry fixture, but no single fixture asserts that identity-variance + audit-chain + file-integrity compose into a unified "integrity verified" surface. Tracked at `CIRISAgent#805`.

Proposed pointer (from seed): `(none specified in seed)` — primary code references: `ciris_engine/logic/audit/`, `ciris_engine/logic/services/graph/audit_service/`, `tools/dev/stage_runtime.py`, `ciris_engine/logic/infrastructure/sub_services/identity_variance_monitor.py`.

## Tracked requirements

- **Umbrella(s)**: `CIRISLensCore#26` — F-3 detector family per FSD-002 §3.5.3
- **Substrate spec(s)**: `CIRISRegistry#29` — Per-locale `provenance:build_manifest:{target}` granularity
- **2.9.5**: `CIRISAgent#805` — integrity attestation fixture
- **2.9.6**: `CIRISAgent#809` — key-rotation alert

See `compliance/README.md` cross-cutting findings table for the 3.0 requirements finalization context.
<!-- END HUMAN -->
