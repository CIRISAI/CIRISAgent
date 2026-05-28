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

This is the five-level verification ladder that an external party uses to decide how much to trust an attestation from a running CIRIS agent. Each higher level adds an independent check on top of every lower level; if any lower level fails, all higher levels are reported UNVERIFIED. That "watchman" principle is the heart of the ladder: the verifier proves itself first, then proves its environment, then proves its registry standing, then proves its file integrity, then proves its operator identity and tamper-evident history.

The ladder itself is owned by CIRISAgent — its canonical UI surface lives in `client/shared/src/commonMain/kotlin/ai/ciris/mobile/shared/ui/screens/TrustPage.kt`. CIRISVerify supplies the raw data points (`binarySelfCheck`, `hardwareBacked`, `hardwareType`, `sourcesOk`, `moduleIntegrityOk`, `fileIntegrityOk`, `auditOk`, `registryKeyStatus`, `playIntegrityOk`, etc.); CIRISAgent composes those points into the L1–L5 picture an auditor reads.

This consumer-side-composition rule is now formally specified by the federation: **CEG 0.2 §8.1.9 Policy I — Attestation-Ladder Composition** (`CIRISRegistry/FSD/CEG/08_composition.md`). The CEG 0.2 wire-break (§5.2 + §13.1, commit `4b27130` on CIRISRegistry main) renames the on-wire attestation prefixes from the old `attestation:l{N}:*` form to mechanism-only: `self_verify` / `hardware_rooted` / `registry_consensus` / `license_validity` / `agent_integrity`. The L1–L5 numbering survives only as a consumer-rendering convention; the wire never speaks levels. CIRIS 3.0 ships with CEG as the federation wire format.

## How CIRIS implements this today

| Level | Plain-language meaning | What has to be true |
|------:|------------------------|---------------------|
| **L1 — Binary Loaded** | The CIRISVerify library is genuinely the published library and its critical signing functions exist. The watchman has proven itself. | `binarySelfCheck` passes (CIRISVerify computes a SHA-256 of its own native library at runtime and compares against the registry-published hash) |
| **L2 — Environment (hardware-rooted)** | The agent's signing key is held in hardware that won't release it — TPM 2.0 on Linux/Windows desktop, Secure Enclave on iOS/macOS, StrongBox / Android Keystore on Android — and a device-attestation token has been obtained from the platform vendor where available. | `hardwareBacked` is true; `hardwareType` identifies the keystore; on mobile, Apple App Attest or Google Play Integrity has returned a token; on desktop, a TPM PCR quote has been produced. |
| **L3 — Registry Cross-Validation** | The Steward Key and file manifest agree across three independent network channels, so a single network compromise can't lie about identity. | 2 of 3 sources agree: HTTPS authoritative + DNS US advisory + DNS EU advisory. |
| **L4 — File Integrity** | Every file on disk (Python code, config, ACCORD text, dependencies) matches the SHA-256 hash the registry publishes for the current build. | `moduleIntegrityOk` and `fileIntegrityOk` are both true. |
| **L5 — Full Attestation (Registry & Audit)** | The operator's Steward Key (purchased through CIRISPortal) is registered and active, and the audit chain shows no tampering. This is the operator's identity claim plus the tamper-evident log of past attestation events. | `registryKeyStatus` reports `active` AND `auditOk` is true. |

- **Verifier wiring**:
    - `ciris_adapters/ciris_verify/adapter.py:48-127` — registers the verifier as a high-priority tool service; exposes verify, capability-check, disclosure, and tier queries.
    - `ciris_adapters/ciris_verify/service.py:49-201` — wraps the verifier with a nonce-challenge license check (configurable cache TTL, default 600s).
    - `ciris_adapters/ciris_verify/ffi_bindings/` — Python bindings to the verifier; per-platform native libraries.
    - `tools/update_ciris_verify.py` — updates verifier binaries and bindings for Android/iOS.
    - `ciris_engine/logic/services/infrastructure/authentication/verifier_singleton.py` — single verifier instance per process (multiple instances cause runtime conflicts).
- **Agent-side attestation pipeline**:
    - `ciris_engine/logic/services/infrastructure/authentication/attestation/verifier_runner.py` — drives full attestation.
    - `ciris_engine/logic/services/infrastructure/authentication/attestation/result_builder.py:210-300` — builds the `AttestationResult` from raw verifier response; cross-validates disk, agent, and registry hashes.
    - `ciris_engine/logic/services/infrastructure/authentication/attestation/play_integrity.py` — Play Integrity verification (Android L2 device attestation).
    - `ciris_engine/logic/services/infrastructure/authentication/attestation/tree_verify.py` — file-tree integrity walk (L4).
- **Agent-side ladder composition**:
    - `client/shared/src/commonMain/kotlin/ai/ciris/mobile/shared/ui/screens/TrustPage.kt` — canonical UI surface; lines 549–622 compose each level from raw verifier data points; lines 1419–1560 (L2 Environment), 1564–1640 (L3 Cross-Validation), 1640–1850 (L4 File Integrity), 2124–2200 (L5 Registry & Audit) carry the per-level explanations rendered to operators.
- **Schemas**:
    - `ciris_engine/schemas/services/attestation.py:13-218` — full attestation state with achieved level, per-check booleans, hardware-trust-degradation flags (CVE detection), and per-source cross-validation.
    - `ciris_engine/schemas/services/attestation.py:244-298` — unified projection into traces and API responses.
    - `ciris_engine/schemas/services/attestation.py:221-232` — cache status with stale-while-revalidate support.
- **Cross-platform attestation**:
    - `ciris_engine/schemas/platform.py:32-69` — `HardwareSecurityType` enum (TPM, HSM); hardware-keystore and TPM flags.
    - `ciris_engine/logic/utils/platform_detection.py:157-161` — TPM detection via `/dev/tpm0`, `/dev/tpmrm0`.
    - Mobile two-phase attestation: pending state while waiting for device token (`ciris_engine/schemas/services/attestation.py:47`).
- **Hardware-trust degradation on known vulnerabilities**:
    - `ciris_engine/schemas/services/attestation.py:175-219` — detects vulnerable SoCs (e.g. CVE-2026-20435 MediaTek); flags `hardware_trust_degraded`, populates reason and advisories with patch levels. This degrades L2 specifically (the hardware-rooted level), and because every higher level requires L2 to pass, L3–L5 also become UNVERIFIED.
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

- **L2 device-attestation reach** — Android (Google Play Integrity) and desktop (TPM PCR quote) cover most of the install base. iOS App Attest is staged (`device_attestation` schema at `ciris_engine/schemas/services/attestation.py:52-56`); the wire shape is specified (`IOSAttestation` proto with `app_attest_assertion` + `device_check_token`). On iOS today the L2 hardware-rooted check still passes via Secure Enclave key storage; the App Attest token piece is the next iOS-side step.
- **Hardware-trust-degraded warning on system health** — when the verifier flags `hardware_trust_degraded` (e.g. CVE-affected SoC), the wallet auto-downgrades but no top-level warning surfaces on `/v1/system/health`. Operators have to read the advisory list directly today. Tracked at `CIRISAgent#814`.
- **End-to-end L2 test on real TPM hardware** — CI today uses software-only fallback. A fixture exercising L2 on TPM-equipped hardware (real PCR quote, real EK certificate chain) is next.
- **`/v1/system/federation` endpoint** — coming next; federation status is currently inferred from the auth service and verifier state per request.
- **ASEAN attestation absent** — D18 has zero ASEAN attestations because ASEAN frames in normative-principles + risk-assessment language rather than an attestation-ladder vocabulary; the seed marks accountability-tier composition as the functional analogue.

Proposed pointer (from seed): `CIRISVerify attestation ladder L1-L5` (this seed line predates CEG 0.2 and reads as "the ladder lives in the substrate" — under CEG 0.2 the ladder is consumer-side composition per §8.1.9 Policy I; the substrate ships mechanism-only data points). Agent-side integration: `ciris_adapters/ciris_verify/`, `ciris_engine/logic/services/infrastructure/authentication/attestation/`, `ciris_engine/schemas/services/attestation.py`. Canonical consumer-side ladder composition: `client/shared/src/commonMain/kotlin/ai/ciris/mobile/shared/ui/screens/TrustPage.kt`. Authoritative wire-form spec: `CIRISRegistry/FSD/CEG/05_namespace.md §5.2` (mechanism-only prefixes) + `08_composition.md §8.1.9` (Policy I composition rule) + `13_anti_patterns.md §13.1` (deprecation of `attestation:l{N}:*`).

## Tracked requirements

- **Umbrella(s)**: `CIRISEdge#37` — key_boundary + named-witness wire + witness aggregation
- **2.9.6**: `CIRISAgent#814` — hardware_trust_degraded → /v1/system/health

See `compliance/README.md` cross-cutting findings table for the 3.0 requirements finalization context.
<!-- END HUMAN -->
