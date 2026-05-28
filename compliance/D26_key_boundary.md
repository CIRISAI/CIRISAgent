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
## What this dimension covers

Key boundaries are the cryptographic walls around the agent's secrets: which key holds which data, who can decrypt, and — crucially — whether the private key ever leaves the hardware chip that protects it. If a key boundary is intact, an attacker who compromises the operating system still cannot impersonate the agent or read its secrets. If the boundary leaks, every other integrity claim is undermined.

## How CIRIS implements this today

The canonical edge-side boundary lives in the upstream CIRIS Edge substrate (shared work — implementation lands when that substrate ships). CIRISAgent's role today is to keep the agent's signing keys and the secrets-store master key inside hardware — a Trusted Platform Module (TPM — a hardware chip that signs cryptographically without ever exposing the private key) or platform secure enclave — and to make every signing operation pass canonical bytes into the boundary, getting a signature out without the key ever appearing in process memory.

- **Key isolation — the private key never leaves the hardware boundary**:
    - `ciris_engine/logic/services/infrastructure/authentication/verifier_singleton.py` — a single verifier instance per process; the only code path that touches the hardware-backed signing key.
    - `ciris_engine/logic/services/infrastructure/authentication/service.py:1790-1859` — registers ONLY the public key in the federation directory; the private key stays in hardware.
    - `ciris_engine/logic/services/infrastructure/authentication/service.py:21,703-864` — Ed25519 keypair generation, signing, and verification; legacy software-key path retained for community mode.
    - `ciris_engine/logic/audit/persist_signing.py:23-57` — returns the public key, actor ID, and signing key ID without ever exporting the private key.
    - `ciris_engine/logic/audit/persist_signing.py:60-75` — passes canonical bytes IN, gets signature OUT; the boundary is preserved.
- **Secrets-store master key — derived inside the hardware boundary**:
    - `ciris_engine/logic/secrets/encryption.py:9,36-51` — hardware mode keeps the master key inside the secure enclave.
    - `ciris_engine/logic/secrets/encryption.py:193-202` — HKDF derivation runs inside the verifier; per-secret keys derived from the master key plus a salt never leave hardware.
    - `ciris_engine/logic/secrets/encryption.py:211-243` — explicit boundary check before any key operation.
    - `ciris_engine/logic/secrets/store.py:11,511-528` — one-shot migration of the secrets master key from software to hardware.
    - `ciris_adapters/ciris_verify/adapter.py:192-215` — triggered after verifier init at startup.
- **Hardware-type identification — what kind of boundary protects this key**:
    - `ciris_engine/schemas/platform.py:32-69` — TPM and HSM enum, plus availability flags.
    - `ciris_engine/schemas/services/attestation.py:23,282` — per-attestation `hardware_type`: TPM 2.0, TEE, Keymaster, StrongBox, software-only.
    - `ciris_engine/schemas/services/attestation.py:201-204` — TrustZone, StrongBox, Keymaster variants.
    - `ciris_engine/logic/utils/platform_detection.py:157-161` — TPM device-file detection on Linux.
- **Boundary signal in every trace**:
    - `ciris_engine/schemas/services/attestation.py:272-282` — per-trace key status, key ID, fingerprint, storage mode, hardware-backed flag, hardware type.
    - `FSD/TRACE_WIRE_FORMAT.md:551-556` — key fields are detailed-tier (identifying), gated behind a privacy level so cross-trace correlation is controlled.
- **Wise Authority signing keys held in hardware**:
    - `ciris_adapters/ciris_verify/adapter.py:175-190` — rotates Wise Authority signing keys into hardware on first hardware-available startup.
    - `ciris_engine/logic/services/infrastructure/authentication/service.py:1780-1788` — auto-rotation logs each migrated authority.

## How you can tell it's working (observability)

If you want to verify the cryptographic boundary, the per-trace key signals and the public-key directory give you everything you need to confirm "same hardware-backed key signed every action in this window."

- **Per-trace key fingerprint + storage mode + hardware type**: lets a downstream consumer confirm the same key signed every trace in a window. A key rotation shows up as a fingerprint discontinuity.
- **Audit-chain key lookup**: every chain entry carries the signing key ID, which resolves through the federation pubkey directory to a hardware attestation. A signature valid under a hardware-backed pubkey is strictly stronger evidence than one under a software key.
- **Federation evidence**: outbound Contributions cite `dimensions: ["D26"]` when trust depends on which hardware boundary protected the signing key. EU §1.3 "data security via cryptographic boundary" and IEEE Ch6 "personal-data trust boundary; cryptographic isolation" are the primary attestations.
- **Hardware-trust-degraded signal**: SoC-vulnerability detection (e.g. CVE-2026-20435) flips a degraded flag. The boundary is functionally weakened even if cryptographically intact — downstream consumers should treat this as a boundary downgrade (`ciris_engine/schemas/services/attestation.py:180-218`).
- **Telemetry**: `/v1/telemetry/unified` exposes hardware-backed and key-storage-mode per-service rollups.

## Current limitations & next steps

- **Edge-side `key_boundary:no_seed_in_heap` predicate** — shared work with the upstream CIRIS Edge substrate (`CIRISRegistry/FSD/FSD-002_FEDERATION_SURFACE.md §3.4`, Edge AV-17: federation seed bytes never observed in the edge process heap during signing). Edge's MISSION §1.4 declares it is structurally "not a key custodian." The agent emits this predicate once the Edge adapter lands. Tracked at `CIRISEdge#37` (umbrella) and `CIRISEdge#38` (the `{scope}` slot).
- **Agent-side `key_boundary:{scope}` projection** — the upstream substrate specifies the scope enum across `hardware_custody:{platform}` (tpm | ios_secure_enclave | android_keystore | software_fallback per Verify §1.6) and Edge's `key_boundary:no_seed_in_heap` predicate (Edge §3.4). The agent's existing `hardware_type` + `key_storage_mode` map directly onto the substrate enum; projecting them under the typed `<dimension>:*` wire envelope is tracked at `CIRISAgent#803`.
- **Per-data-class delegated keys** — today the agent holds one hardware key for audit signing, one per Wise Authority, and one master key for the secrets store. The upstream substrate's structural delegation primitive (`delegates_to`, FSD-002 §2.2.1 — bounded scope, depth-2 default, explicit purpose like `hardware_rotation` / `re_signer` / `ephemeral_session`) lets a single root key delegate to ephemeral or per-data-class keys without compromising the root. IEEE Ch6 "personal-data trust boundary" maps onto a delegate-scoped key emitted from the secrets master root. Lands when the federation-wire delegation envelopes ship.
- **Per-channel adapter keys under the hardware boundary** — adapters using their own credentials (e.g. Discord, Slack adapter tokens) live in `~/.ciris/.env` or the shared secrets store with master-key protection, but not under per-adapter hardware isolation. Next step is bringing per-channel keys under the same delegated-scope discipline.
- **Automated key rotation** — the public-key directory accepts new keys but rejects collisions with differing content; today rotation is operator-driven. The next step is signed rotation events over the wire (`delegates_to:hardware_rotation`, FSD-002 §2.2.1).
- **Explicit `boundary_degraded` signal** — when CIRISVerify falls back to software-only (community mode, no hardware available), traces show `hardware_backed=false`, but downstream consumers must infer this is a boundary downgrade rather than a deliberate scope choice. Adding an explicit `boundary_degraded` flag distinct from `hardware_trust_degraded` is tracked at `CIRISAgent#816`.

Proposed pointer (from seed): `CIRISEdge key_boundary` (canonical primitive lives in the upstream Edge substrate). Agent-side equivalent today: hardware-rooted Ed25519 signing keys plus SecretsStore master-key migration to hardware. Primary code: `ciris_adapters/ciris_verify/adapter.py:175-215`, `ciris_engine/logic/secrets/encryption.py:36-243`, `ciris_engine/logic/audit/persist_signing.py:23-75`.

## Tracked requirements

- **Umbrella(s)**: `CIRISAgent#803` — Typed `<dimension>:*` wire envelope emission; `CIRISLensCore#26` — F-3 detector family per FSD-002 §3.5.3; `CIRISEdge#37` — key_boundary + named-witness wire + witness aggregation
- **Substrate spec(s)**: `CIRISEdge#38` — key_boundary `{scope}` slot
- **2.9.6**: `CIRISAgent#816` — boundary_degraded signal

See `compliance/README.md` cross-cutting findings table for the 3.0 requirements finalization context.
<!-- END HUMAN -->
