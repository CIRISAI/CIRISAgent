# D18 — `attestation:l{3,5}:*` (STRONG-3)

> Verification ladder (L1-L5 hardware-rooted attestation)

**Seed reference**: `SEED_DIMENSIONS.yaml` v1.0, dimension `D18` ([source](https://github.com/CIRISAI/ciris-response-magnifica-humanitas/blob/main/SEED_DIMENSIONS.yaml))
**Accord principle**: integrity
**Attestation density**: MH=2 · EU=4 · IEEE=5 · ASEAN=0 · total=11

**Absent from**: ASEAN — ASEAN framing is normative-principles + risk-assessment, not federation-attestation ladder.
  *Functional analogue*: Composition via accountability-tier wording

## Regulatory attestations

*(Auto-rendered from seed; do not hand-edit. Re-run `python tools/compliance/generate_ciris_compliance_stubs.py tools/compliance/SEED_DIMENSIONS.yaml compliance/` after seed updates.)*

- **MH** (Magnifica Humanitas (On Safeguarding the Human Person in the Time of Artificial Intelligence)) — *§§ various*
    > "structural verification of doctrinal claims"
    Wire form: `attestation:l3:doctrinal_continuity`
- **EU** (Ethics Guidelines for Trustworthy AI) — *§III.7*
    > "auditability requires attestation at multiple verification levels"
    Wire form: `attestation:l3:* + attestation:l5:*`
- **IEEE** (Ethically Aligned Design, First Edition) — *Ch2 P5 + Ch9*
    > "system-level verifiable attestations"
    Wire form: `attestation:l3:* + attestation:l5:*`

## Wire primitives

- `attestation:l1 through l5`

---

<!-- BEGIN HUMAN -->
## What this dimension covers

This is the five-level verification ladder (L1 says software was bit-for-bit signed; L5 adds hardware-rooted attestation that the code is running on the device it claims to run on). Each level adds an independent check: at L1 you know the binary is genuine; at L4 you know every loadable file is genuine; at L5 you also know the audit log is end-to-end verified and (on mobile) that the device itself is genuine. Each higher level subsumes all lower ones.

## How CIRIS implements this today

The canonical ladder lives in the upstream CIRIS substrate (Rust-based CIRISVerify). CIRISAgent consumes it, projects the achieved level into every reasoning trace, and uses the level to gate runtime behaviors. Canonical definitions live in `FSD/TRACE_WIRE_FORMAT.md:510-517`:

| Level | Requires | Plain-language meaning |
|------:|----------|---------|
| 0 | (nothing) | Verifier not loaded |
| 1 | binary OK | The running binary matches its published hash |
| 2 | + environment OK | The runtime environment matches expected config |
| 3 | + registry OK OR hardware-backed | The signing key is either registered with the federation directory OR held in a Trusted Platform Module (TPM — a hardware chip that signs cryptographically without ever exposing the private key) / secure enclave |
| 4 | + file-integrity OK | Every prompt, config, and ACCORD text file matches its registered fingerprint of every file in the running build |
| 5 | + audit OK AND device OK (mobile) | The audit chain is end-to-end verified; on mobile, Google Play Integrity has passed |

- **Verifier wiring**:
    - `ciris_adapters/ciris_verify/adapter.py:48-127` — registers the verifier as a high-priority tool service; exposes verify, capability-check, disclosure, and tier queries.
    - `ciris_adapters/ciris_verify/service.py:49-201` — wraps the verifier with a nonce-challenge license check (configurable cache TTL, default 600s).
    - `ciris_adapters/ciris_verify/ffi_bindings/` — Python bindings to the verifier; per-platform native libraries.
    - `tools/update_ciris_verify.py` — updates verifier binaries and bindings for Android/iOS.
    - `ciris_engine/logic/services/infrastructure/authentication/verifier_singleton.py` — single verifier instance per process (multiple instances cause runtime conflicts).
- **Agent-side attestation pipeline**:
    - `ciris_engine/logic/services/infrastructure/authentication/attestation/verifier_runner.py` — drives full attestation.
    - `ciris_engine/logic/services/infrastructure/authentication/attestation/result_builder.py:210-300` — builds the `AttestationResult` from raw verifier response; cross-validates disk, agent, and registry hashes.
    - `ciris_engine/logic/services/infrastructure/authentication/attestation/play_integrity.py` — Play Integrity verification (Android L5).
    - `ciris_engine/logic/services/infrastructure/authentication/attestation/tree_verify.py` — file-tree integrity walk (L4).
- **Schemas**:
    - `ciris_engine/schemas/services/attestation.py:13-218` — full attestation state with achieved level, per-check booleans, hardware-trust-degradation flags (CVE detection), and per-source cross-validation.
    - `ciris_engine/schemas/services/attestation.py:244-298` — unified projection into traces and API responses.
    - `ciris_engine/schemas/services/attestation.py:221-232` — cache status with stale-while-revalidate support.
- **Cross-platform attestation**:
    - `ciris_engine/schemas/platform.py:32-69` — `HardwareSecurityType` enum (TPM, HSM); hardware-keystore and TPM flags.
    - `ciris_engine/logic/utils/platform_detection.py:157-161` — TPM detection via `/dev/tpm0`, `/dev/tpmrm0`.
    - Mobile two-phase attestation: pending state while waiting for device token (`ciris_engine/schemas/services/attestation.py:47`).
- **Hardware-trust degradation on known vulnerabilities**:
    - `ciris_engine/schemas/services/attestation.py:175-219` — detects vulnerable SoCs (e.g. CVE-2026-20435 MediaTek); flags `hardware_trust_degraded`, populates reason and advisories with patch levels.
    - When trust is degraded, wallet operations auto-downgrade to receive-only (policy enforced by the wallet adapter).
- **Startup attestation budget**:
    - The agent will not transition out of WAKEUP until attestation completes or a 15-second budget expires.

## How you can tell it's working (observability)

If you want to verify the agent's attestation claim, you can re-run the same checks downstream.

- **Per-trace ladder block**: every traced thought ships the achieved level, status, mode, each per-check boolean, key fingerprint, hardware type, verifier version, and a pre-rendered summary string (`FSD/TRACE_WIRE_FORMAT.md:495-562`). Identifying key fields are gated behind a privacy tier so cross-trace correlation is controlled.
- **Independent integrity signals**: the six per-check booleans are treated as separate near-independent signals by the federation analytics layer rather than collapsed into one level (`FSD/TRACE_WIRE_FORMAT.md:519-522`), so an analyst cannot be fooled by one signal masking another.
- **Re-walk the audit chain**: L5's audit-OK check is computed by walking the audit log via `engine.audit_verify_chain`; downstream consumers replay the same walk (`ciris_engine/logic/audit/verifier.py:72`).
- **Federation evidence**: outbound Contributions cite `dimensions: ["D18"]` when evidentiary weight depends on the achieved level. EU §III.7 auditability and IEEE Ch2 P5 + Ch9 system-level verifiable attestations are the primary attestations.
- **Telemetry**: `/v1/telemetry/unified` includes the per-service level rollup. Verifier version is pinned per-trace so a future semantics change does not silently invalidate older comparisons (`FSD/TRACE_WIRE_FORMAT.md:558-561`).
- **Audit logging**: attestation refresh events log level, pending state, and instance ID (`ciris_engine/logic/services/infrastructure/authentication/service.py:2488-2557`).

## Current limitations & next steps

- **L5 on server platforms** — reaches L4 today on Linux/macOS servers; L5 requires Play Integrity (Android-only) today. L5 on server lands when the agent populates the L5 claim from a TPM hardware-quote rather than from Play Integrity. The wire format already specifies the TPM-quote shape (`CIRISVerify/FSD/FSD-001 §4 HardwareAttestation` with `tpm_quote` + `pcr_values` + `aik_certificate`); the substrate primitive exists. Agent-side integration is the next step.
- **iOS App Attest pipeline** — the schema is in place (`device_attestation`, `ciris_engine/schemas/services/attestation.py:52-56`). The wire format is specified (`IOSAttestation` proto with `app_attest_assertion` + `device_check_token`). Maturity lags Android Play Integrity; today iOS falls back to L4 in the verifier runner. iOS L5 is shared work with the upstream CIRISVerify substrate.
- **Distinct L3-branch signal** — L3 passes on either federation-directory registration OR hardware-backed signing. The upstream substrate specifies these as two independent claims (`attestation:l3:registry_consensus` and `hardware_custody:{platform}`); the agent-side wire-format binding that disambiguates them per-trace is tracked at `CIRISAgent#806`.
- **Hardware-trust-degraded warning surfaced via system health** — when the verifier flags hardware-trust-degraded, the wallet auto-downgrades but no top-level warning shows up on `/v1/system/health`. Operators must read the advisory list directly today. Tracked at `CIRISAgent#814`.
- **End-to-end L5 test on real TPM hardware** — CI today uses software-only fallback. A fixture exercising L5 on TPM-equipped hardware is next.
- **`/v1/system/federation` endpoint** — coming next; federation status is currently inferred from the auth service and verifier state per request.
- **ASEAN attestation absent** — D18 has zero ASEAN attestations because ASEAN frames in normative-principles + risk-assessment language rather than an attestation-ladder vocabulary; the seed marks accountability-tier composition as the functional analogue.

Proposed pointer (from seed): `CIRISVerify attestation ladder L1-L5` (canonical ladder lives in the upstream Rust substrate). Agent-side integration: `ciris_adapters/ciris_verify/`, `ciris_engine/logic/services/infrastructure/authentication/attestation/`, `ciris_engine/schemas/services/attestation.py`. Ladder definitions: `FSD/TRACE_WIRE_FORMAT.md:510-517`.

## Tracked requirements

- **Umbrella(s)**: `CIRISEdge#37` — key_boundary + named-witness wire + witness aggregation
- **2.9.5**: `CIRISAgent#806` — l3_branch field on AttestationResult
- **2.9.6**: `CIRISAgent#814` — hardware_trust_degraded → /v1/system/health

See `compliance/README.md` cross-cutting findings table for the 3.0 requirements finalization context.
<!-- END HUMAN -->
