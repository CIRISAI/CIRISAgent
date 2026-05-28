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
## CIRIS-side compliance implementation

The L1-L5 ladder is owned by CIRISVerify (Rust); CIRISAgent consumes it via the `ciris_verify` adapter, projects the achieved level into every trace, and gates runtime behaviors on `max_level`. Canonical level definitions live in `FSD/TRACE_WIRE_FORMAT.md:510-517`:

| Level | Requires | Meaning |
|------:|----------|---------|
| 0 | (nothing) | CIRISVerify not loaded or disabled |
| 1 | `binary_ok` | Agent binary hash matches a published artifact |
| 2 | + `env_ok` | Runtime environment matches expected config |
| 3 | + `registry_ok` OR `hardware_backed` | Signing key registered with Portal OR signing key hardware-backed (TPM/TEE) |
| 4 | + `file_integrity_ok` | All loadable files (prompts, configs, accord) verified against their hashes |
| 5 | + `audit_ok` AND `play_integrity_ok` (mobile) | Audit chain verified end-to-end; on mobile, Google Play Integrity passed |

- **Verifier integration**:
    - `ciris_adapters/ciris_verify/adapter.py:48-127` — `CIRISVerifyAdapter` registers as a TOOL service with HIGH priority; exposes `license:verify`, `license:check_capability`, `license:get_disclosure`, `license:get_tier`
    - `ciris_adapters/ciris_verify/service.py:49-201` — `CIRISVerifyService` wraps the FFI client; nonce-challenge license check (`os.urandom(32)`); cache TTL configurable (default 600s)
    - `ciris_adapters/ciris_verify/ffi_bindings/` — Python bindings to CIRISVerify Rust binary; `libciris_verify_ffi.dylib` shipped per-platform
    - `tools/update_ciris_verify.py` — staging tool that updates CIRISVerify binaries + Python bindings for Android/iOS
    - `ciris_engine/logic/services/infrastructure/authentication/verifier_singleton.py` — singleton accessor; only ONE CIRISVerify FFI instance per process (multiple instances cause tokio runtime conflicts — `ciris_adapters/ciris_verify/service.py:115-132`)
- **Attestation pipeline (agent-side)**:
    - `ciris_engine/logic/services/infrastructure/authentication/attestation/verifier_runner.py` — drives full attestation against CIRISVerify
    - `ciris_engine/logic/services/infrastructure/authentication/attestation/result_builder.py:210-300` — builds `AttestationResult` from raw verify response; maps `attestation.get("level", 0)` → `max_level`; cross-validates disk/agent/registry hashes (v0.9.7+)
    - `ciris_engine/logic/services/infrastructure/authentication/attestation/play_integrity.py` — Play Integrity verification for L5 on Android
    - `ciris_engine/logic/services/infrastructure/authentication/attestation/tree_verify.py` — file-tree integrity walk (L4)
- **Schema surface**:
    - `ciris_engine/schemas/services/attestation.py:13-218` — `AttestationResult`: full attestation state with `max_level`, `level_pending`, `attestation_status`, per-check booleans, hardware-trust degradation (v1.2.x SoC vulnerability detection), disk/agent/registry cross-validation, device attestation
    - `ciris_engine/schemas/services/attestation.py:244-298` — `VerifyAttestationContext`: unified projection into traces/responses
    - `ciris_engine/schemas/services/attestation.py:221-232` — `AttestationCacheStatus` with stale-while-revalidate support
- **Cross-platform attestation**:
    - `ciris_engine/schemas/platform.py:32-69` — `HardwareSecurityType` (TPM, HSM); `hardware_keystore_available`, `tpm_available` flags
    - `ciris_engine/logic/utils/platform_detection.py:157-161` — TPM detection via `/dev/tpm0`, `/dev/tpmrm0`
    - Mobile two-phase attestation: `level_pending=True` when waiting for device attestation token (`ciris_engine/schemas/services/attestation.py:47`)
- **Hardware trust degradation (CVE detection)**:
    - `ciris_engine/schemas/services/attestation.py:175-219` — vulnerable SoC detection (e.g. CVE-2026-20435 MediaTek); `hardware_trust_degraded`, `trust_degradation_reason`, `security_advisories` list with patch levels
    - When hardware trust is degraded, wallet operations are auto-downgraded to receive-only (policy enforced by wallet adapter)
- **Startup attestation budget**:
    - Commit `1bc2becc0`: gate processor on 15s startup attestation budget — agent will not transition out of WAKEUP until attestation completes or budget expires

## Observability hooks

- **LensCore F-3 family**: integrity dimensions (`*_ok` booleans) are documented as separate near-zero-correlation dimensions for k_eff analysis (`FSD/TRACE_WIRE_FORMAT.md:519-522`). The lens treats each as an independent integrity axis rather than collapsing into `max_level`.
- **Trace projection**: every traced thought ships `attestation_level`, `attestation_status`, `attestation_mode`, all per-check booleans, key fingerprint, hardware type, verify version, plus pre-rendered `attestation_context` summary string (`FSD/TRACE_WIRE_FORMAT.md:495-562`). DETAILED-tier fields gate identifying key info (key_id, ed25519_fingerprint, hardware_type) behind privacy tier.
- **Audit chain queries**: L5 `audit_ok` is computed by walking `cirislens_audit_log` via `engine.audit_verify_chain`; downstream consumers verify the agent's L5 claim by replaying the same query (`ciris_engine/logic/audit/verifier.py:72`).
- **Federation evidence_refs**: emitted Contributions cite `dimensions: ["D18"]` when the contribution's evidentiary weight depends on the achieved attestation level. EU §III.7 auditability framing and IEEE Ch2 P5 + Ch9 system-level verifiable attestations are the primary cross-source attestations.
- **Telemetry**: `/v1/telemetry/unified` includes `attestation_level` per-service rollup. CIRISVerify version pinned per-trace-row so future semantics changes don't silently invalidate older comparisons (`FSD/TRACE_WIRE_FORMAT.md:558-561`).
- **Audit logging**: attestation refresh events log `level=X/5`, `level_pending=bool`, instance ID (`ciris_engine/logic/services/infrastructure/authentication/service.py:2488-2557`).

## Known gaps / not-yet-implemented

- **L5 server-side gap**: L5 requires `audit_ok` AND `play_integrity_ok`. Desktop and server deployments have `play_integrity_ok=false` by design — Play Integrity is Android-specific. Substrate-specced via `hardware_custody:tpm` in FSD-002 §3.2 (Verify §1.6, §4 `storage_descriptor()` per AV-7); TPM 2.0 is one of the four named `hardware_type` values per `CIRISVerify/FSD/FSD-001 §4 HardwareAttestation` proto. TPMAttestation proto carries `tpm_quote` + `pcr_values` + `aik_certificate` fields. L5-equivalent for Linux/macOS server lands when the agent populates `attestation:l5:agent_integrity` (FSD-002 §3.2) from a TPM-quote rather than from Play Integrity. Substrate primitives exist; agent-side TPM-quote integration is the gap, not the primitive.
- **ASEAN absence**: D18 has zero ASEAN attestations; the seed marks composition via accountability-tier wording as the functional analogue. No agent-side wiring bridges ASEAN's risk-assessment framing to the L-ladder.
- **iOS App Attest**: schema exists (`device_attestation` field, `ciris_engine/schemas/services/attestation.py:52-56`). Substrate-specced via `hardware_custody:ios_secure_enclave` (FSD-002 §3.2 — one of the four hardware-custody platforms) + `IOSAttestation` proto in CIRISVerify FSD-001 §4 (`app_attest_assertion` + `device_check_token` fields); iOS attestation pipeline is not as mature as Android Play Integrity; `verifier_runner` falls back to L4 on iOS.
- **L3 OR-gate ambiguity**: L3 passes on `registry_ok` OR `hardware_backed`. Substrate-specced as two distinct primitives — `attestation:l3:registry_consensus` (FSD-002 §3.2 — "2-of-3 multi-source registry consensus on key/build/license validity") and `hardware_custody:{platform}` (FSD-002 §3.2 — names which platform); a trace at L3 carries BOTH attestations independently per the scalar-attestation model (FSD-002 §2.1). Downstream consumers read each prefix per FSD-002 §6 composition policies. Substrate-side disambiguation is structural; agent-side disambiguation pending the wire-format binding.
- **Cross-substrate provenance**:
    - CIRISVerify (binary) → CIRISRegistry (file-tree manifest) → CIRISAgent (file_integrity check) is fully wired
    - CIRISVerify → Portal (signing key registration) → CIRISAgent (registry_ok) is wired
    - CIRISVerify → CIRISLensCore (attestation projection into traces) is wired
    - CIRISVerify → CIRISEdge (key_boundary attestation, see D26) is NOT wired — CIRISEdge integration does not exist in this repo
- **Hardware trust degradation surfacing**: when `hardware_trust_degraded=True`, the wallet adapter auto-downgrades but there's no top-level system warning surfaced via the `/v1/system/health` `warnings` field. Operators must read `AttestationResult.security_advisories` directly.
- **Test fixtures**: `tests/ciris_adapters/ciris_verify/test_adapter.py` covers loader + adapter lifecycle. No fixture exercises a complete L5 attestation on a real TPM-equipped runner — CI uses software-only fallback.
- **No `/v1/system/federation` endpoint** exists yet despite the user-supplied reference; federation status is currently inferred from auth service + verifier state at request time.

Proposed pointer (from seed): `CIRISVerify attestation ladder L1-L5` (canonical ladder lives in CIRISVerify Rust). Agent-side integration: `ciris_adapters/ciris_verify/`, `ciris_engine/logic/services/infrastructure/authentication/attestation/`, `ciris_engine/schemas/services/attestation.py`. Ladder definitions: `FSD/TRACE_WIRE_FORMAT.md:510-517`.
<!-- END HUMAN -->
