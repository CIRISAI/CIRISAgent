# D26 — `key_boundary:*` (STRONG-3)

> CIRISEdge encryption key boundary attestation (cryptographic trust scoping)

**Seed reference**: `SEED_DIMENSIONS.yaml` v1.0, dimension `D26` ([source](https://github.com/CIRISAI/ciris-response-magnifica-humanitas/blob/main/SEED_DIMENSIONS.yaml))
**Accord principle**: integrity
**Attestation density**: MH=0 · EU=2 · IEEE=7 · ASEAN=2 · total=11

**Absent from**: MH — Encryption/key-management is not encyclical content.
  *Functional analogue*: Composition via stewardship-of-trust language

## Regulatory attestations

*(Auto-rendered from seed; do not hand-edit. Re-run `python tools/compliance/generate_ciris_compliance_stubs.py tools/compliance/SEED_DIMENSIONS.yaml compliance/` after seed updates.)*

- **EU** (Ethics Guidelines for Trustworthy AI) — *§1.3 Privacy and data governance*
    > "data security via cryptographic boundary"
    Wire form: `key_boundary:*`
- **IEEE** (Ethically Aligned Design, First Edition) — *Ch6 (7 attestations)*
    > "personal-data trust boundary; cryptographic isolation"
    Wire form: `key_boundary:*`
- **ASEAN** (ASEAN Guide on AI Governance and Ethics) — *§B.3 + §C.3*
    > "security via key-managed trust boundary"
    Wire form: `key_boundary:*`

## Wire primitives

- `key_boundary:{scope}`

---

<!-- BEGIN HUMAN -->
## CIRIS-side compliance implementation

`key_boundary:*` is the cryptographic trust scoping primitive — declaring WHICH key holds WHICH data and WHO can decrypt. The canonical key_boundary implementation lives in CIRISEdge (which does not exist in this repo at the audited HEAD). CIRISAgent implements the agent-side equivalent today via CIRISVerify-managed Ed25519 keys + the SecretsStore master-key migration to hardware.

- **Key isolation via CIRISVerify**:
    - `ciris_engine/logic/services/infrastructure/authentication/verifier_singleton.py` — single CIRISVerify instance per process; the only path that touches the TPM-backed signing key
    - `ciris_engine/logic/services/infrastructure/authentication/service.py:1790-1859` — `_register_agent_pubkey_with_persist()` registers ONLY the public key in `accord_public_keys`; the private key never leaves CIRISVerify's hardware boundary
    - `ciris_engine/logic/services/infrastructure/authentication/service.py:21,703-864` — Ed25519 keypair generation / signing / verification; legacy software-key path retained for community mode
    - `ciris_engine/logic/audit/persist_signing.py:23-57` — `get_signer_material()` returns pubkey + actor_id + signing_key_id without ever exporting the private key; signing happens inside CIRISVerify
    - `ciris_engine/logic/audit/persist_signing.py:60-75` — `sign_with_verifier()` passes canonical bytes INTO CIRISVerify, gets signature OUT; private key boundary preserved
- **Secrets-store key boundary**:
    - `ciris_engine/logic/secrets/encryption.py:9,36-51` — `Hardware mode: Master key in CIRISVerify TPM/Keystore`; multiple derivation strategies
    - `ciris_engine/logic/secrets/encryption.py:193-202` — `derive_key(self._hardware_key_id, context=b"ciris-secrets-v1:" + salt)`; HKDF derivation inside CIRISVerify; salt-derived per-secret keys never leave hardware
    - `ciris_engine/logic/secrets/encryption.py:211-243` — `has_hardware_key()`, `store_named_key()`; explicit boundary check before any key operation
    - `ciris_engine/logic/secrets/store.py:11,511-528` — `migrate_to_hardware_key()`: one-shot migration of secrets master key from software to TPM
    - `ciris_adapters/ciris_verify/adapter.py:192-215` — `_migrate_secrets_master_key()`: triggered after CIRISVerify init; called once at startup
- **Hardware-type identification (`key_boundary:{scope}` discriminator)**:
    - `ciris_engine/schemas/platform.py:32-69` — `HardwareSecurityType` enum: TPM (Trusted Platform Module), HSM (Hardware Security Module); `hardware_keystore_available`, `tpm_available` flags
    - `ciris_engine/schemas/services/attestation.py:23,282` — `hardware_type` carried per-attestation: `TPM_2_0`, `TEE`, `SOFTWARE_ONLY`, `Keymaster`, `StrongBox`, etc.
    - `ciris_engine/schemas/services/attestation.py:201-204` — `tee_implementation`: `TrustZone`, `StrongBox`, `Keymaster`
    - `ciris_engine/logic/utils/platform_detection.py:157-161` — TPM device-file detection on Linux
- **Cryptographic boundary in trace projection**:
    - `ciris_engine/schemas/services/attestation.py:272-282` — `VerifyAttestationContext` exposes `key_status`, `key_id`, `ed25519_fingerprint`, `key_storage_mode`, `hardware_backed`, `hardware_type` per-trace
    - `FSD/TRACE_WIRE_FORMAT.md:551-556` — key fields are DETAILED-tier (identifying), gated behind privacy level for cross-trace correlation control
- **WA key boundary**:
    - `ciris_adapters/ciris_verify/adapter.py:175-190` — `_migrate_wa_keys()` rotates Wise Authority signing keys into CIRISVerify on first hardware-available startup
    - `ciris_engine/logic/services/infrastructure/authentication/service.py:1780-1788` — auto-rotation logs each migrated WA

## Observability hooks

- **LensCore F-3 family**: not implemented for key_boundary specifically. The lens consumes per-trace `hardware_backed`, `key_storage_mode`, and `hardware_type` to correlate reasoning quality with key-isolation strength.
- **Trace projection**: per-trace key fingerprint + storage mode + hardware type lets downstream consumers verify that the same key signed every trace in a window — a key rotation surfaces as a fingerprint discontinuity.
- **Audit chain queries**: every entry in `cirislens_audit_log` carries `signing_key_id` resolving to `accord_public_keys` (`engine.audit_list_entries`); cross-substrate verification: chain entry → signing_key_id → pubkey directory → CIRISVerify hardware attestation. A signature valid under a pubkey registered as `hardware_backed=true` is a stronger evidence than one under a software key.
- **Federation evidence_refs**: emitted Contributions cite `dimensions: ["D26"]` when the contribution's trust depends on which hardware boundary protected the signing key. EU §1.3 (Privacy and data governance) "data security via cryptographic boundary" and IEEE Ch6 (7 attestations) "personal-data trust boundary; cryptographic isolation" are the primary attestations.
- **Hardware trust degradation**: CIRISVerify 1.2.x SoC vulnerability detection (e.g. CVE-2026-20435) flips `hardware_trust_degraded=true` → key boundary is functionally weakened even if cryptographically intact; downstream consumers must respect this as a boundary-degradation signal (`ciris_engine/schemas/services/attestation.py:180-218`).
- **Telemetry**: `/v1/telemetry/unified` exposes `hardware_backed`, `key_storage_mode` per service rollup.

## Known gaps / not-yet-implemented

- **CIRISEdge integration absent**: `ciris_engine/logic/adapters/edge_communication/` and `ciris_engine/logic/runtime/edge_runtime.py` (referenced in the task brief) DO NOT EXIST at the audited HEAD. CIRISEdge is the planned canonical `key_boundary:{scope}` host (per the substrate substitution trajectory step 2), but the agent's edge-adapter integration point is unwritten.
- **`key_boundary:{scope}` enum not closed**: the seed lists `key_boundary:*` as a wire primitive but the agent has no explicit enum of scope values. Today scope is implicit in `hardware_type` (TPM_2_0, TEE, SOFTWARE_ONLY) + `key_storage_mode` — no first-class `key_boundary` field exists in any schema.
- **Per-data-class key boundaries**: the agent uses ONE TPM key for audit signing, ONE for WA signing per WA, ONE master key for secrets store. No per-data-class boundary (per-tenant, per-channel, per-cohort) — IEEE Ch6 "personal-data trust boundary" maps to "secrets master key" today, not to a per-personal-data scoped key.
- **MH absence**: zero MH attestations; encryption/key-management is not encyclical content. Functional analogue is composition via stewardship-of-trust language, which has no agent-side wiring.
- **Cross-substrate provenance chain incomplete**:
    - CIRISVerify (hardware key) → CIRISAgent (signing) → persist (`accord_public_keys` directory) → audit chain verification: WIRED
    - CIRISVerify (hardware key) → CIRISEdge (data-at-rest boundary): NOT WIRED (CIRISEdge integration absent)
    - CIRISAgent (secrets master key) → CIRISVerify HKDF derivation: WIRED
    - CIRISAgent (per-channel encryption keys): NOT WIRED — adapters using their own encryption keys (e.g. Discord, Slack adapter tokens) are not under the CIRISVerify boundary; they live in `~/.ciris/.env` or shared secrets store with master-key protection but not per-adapter hardware isolation
- **Key rotation semantics**: `accord_public_keys` registration raises on "collision with differing content" but there's no automated rotation workflow; rotation requires operator intervention and re-signing of historical chain anchors is not implemented.
- **Software-mode fallback transparency**: when CIRISVerify falls back to software-only signing (community mode, no hardware available), the trace shows `hardware_backed=false` but downstream consumers must infer this is a boundary downgrade rather than a deliberate scope choice — no explicit `boundary_degraded` signal distinct from `hardware_trust_degraded`.

Proposed pointer (from seed): `CIRISEdge key_boundary` (canonical primitive lives in CIRISEdge — NOT in this repo). Agent-side equivalent: CIRISVerify-managed Ed25519 keys + SecretsStore hardware-key migration. Primary code: `ciris_adapters/ciris_verify/adapter.py:175-215`, `ciris_engine/logic/secrets/encryption.py:36-243`, `ciris_engine/logic/audit/persist_signing.py:23-75`.
<!-- END HUMAN -->
