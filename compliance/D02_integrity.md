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
## CIRIS-side compliance implementation

Integrity is the system-holds-together property — CIRIS implements it through a tamper-evident audit chain, identity-variance bounds, a build-time signed manifest, and the L1-L5 attestation ladder. The chain is the load-bearing surface; everything else hangs off it.

- **Audit chain (lifecycle integrity)**:
    - `ciris_engine/logic/audit/persist_signing.py:23` — resolves the agent's CIRISVerify-backed Ed25519 signing material; same key bridges legacy chain and signs every regular entry
    - `ciris_engine/logic/audit/persist_signing.py:60` — signs canonical bytes (canonicalization owned by persist's `audit_canonicalize_for_signing`)
    - `ciris_engine/logic/audit/persist_signing.py:78` — tenant_id resolution (`agent-default` when `CIRIS_AGENT_TENANT` unset)
    - `ciris_engine/logic/audit/verifier.py:72` — `verify_complete_chain()` walks the full chain via persist's `audit_verify_chain` against `cirislens_audit_log`
    - `ciris_engine/logic/audit/chain_bridge.py:132` — A0b bridge entry brings the legacy `ciris_audit.db` chain into persist's canonical store; signed with the same TPM-backed key as regular entries
    - `ciris_engine/logic/services/graph/audit_service/service.py:192-196` — A3 cutover: all writes go through `_write_to_persist_chain`; reads delegate to persist's verifier; legacy `AuditHashChain` / `AuditSignatureManager` removed
- **Reproducibility / lifecycle (build-time integrity)**:
    - `tools/dev/stage_runtime.py:1-52` — canonical runtime tree staging; mirrors `ciris_verify_core::security::build_manifest::walk_file_tree` + `ExemptRules` so the `file_tree_hash` computed at sign time equals the one CIRISVerify computes at verify time
    - `tools/dev/stage_runtime.py:76-101` — `ExemptRules` serialized into signed `FileTreeExtras`; deterministic across CI and runtime
    - `tools/templates/generate_manifest.py` — generates a signed manifest of pre-approved agent templates
- **Identity-variance bounds (doctrinal continuity)**:
    - `ciris_engine/logic/infrastructure/sub_services/identity_variance_monitor.py:43-50` — `IdentityVarianceMonitor` tracks drift from baseline; triggers WA review when variance exceeds 20% threshold
    - `ciris_engine/schemas/infrastructure/identity_variance.py` — `IdentitySnapshot`, `IdentityDiff`, `VarianceReport`, `WAReviewRequest` schemas
- **Hardware-rooted signing material**:
    - `ciris_adapters/ciris_verify/adapter.py:175-215` — `_migrate_wa_keys()` and `_migrate_secrets_master_key()` move WA signing keys + secrets master key into CIRISVerify's TPM/Keystore when hardware is available
    - `ciris_engine/logic/services/infrastructure/authentication/service.py:1790-1859` — `_register_agent_pubkey_with_persist()` registers the agent's pubkey with `accord_public_keys` (C3 lane); audit-chain verifiers resolve `signing_key_id → pubkey` here
- **Policy/schema surface**:
    - `ciris_engine/schemas/services/attestation.py:13-219` — `AttestationResult` carries `audit_ok`, `file_integrity_ok`, `module_integrity_ok`, integrity-failure reasons, per-file results
    - `ciris_engine/schemas/audit/hash_chain.py` and `ciris_engine/schemas/audit/verification.py` — chain + verification result schemas
    - `FSD/TRACE_WIRE_FORMAT.md:495-562` — federation wire spec for the per-trace integrity block

## Observability hooks

- **LensCore F-3 family**: not yet implemented in this repo. Per-trace integrity dimensions (`audit_ok`, `file_integrity_ok`, `binary_ok`, `env_ok`, `registry_ok`, `hardware_backed`) are projected into every traced thought via `VerifyAttestationContext` (`ciris_engine/schemas/runtime/system_context.py:163`) so the lens can run k_eff analysis treating each as a separate near-zero-correlation dimension — see `FSD/TRACE_WIRE_FORMAT.md:519-522`.
- **Audit chain queries**: downstream verification uses `engine.audit_list_entries(filter_json, cursor, limit)` (tenant-scoped DESC by sequence_number) and `engine.audit_verify_chain` for end-to-end walk. Production fixture: 69-entry chain (clean + tampered) — see `ciris_engine/logic/audit/verifier.py:72-100`.
- **Identity drift telemetry**: `IdentityVarianceMonitor` periodically samples identity state into `IdentitySnapshot` nodes (`created_by="identity_variance_monitor"` per `ciris_engine/schemas/services/nodes.py:281`); drift > 20% raises `WAReviewRequest`.
- **Telemetry rollup**: `/v1/telemetry/unified` (`ciris_engine/logic/adapters/api/routes/telemetry.py:1879+`) aggregates audit/incident/tsdb services into a single integrity health view.
- **TSDB consolidation**: `ciris_engine/logic/services/graph/tsdb_consolidation/service.py:539` preserves the `cirislens_audit_log` chain across consolidation windows; `AuditConsolidator` (`service.py:97`) generates `tsdb_consolidate_audit` summary nodes per window.
- **Federation evidence_refs**: emitted Contributions cite `dimensions: ["D02"]` when instantiating integrity claims; per-row `verify_attestation` block in traces carries the full ladder state. CONF-03 (ASEAN explainability fallback vs other three batches holding it constitutive) should surface in evidence_refs as a mutability flag.

## Known gaps / not-yet-implemented

- LensCore F-3 detector family (cross-trace integrity correlation analysis) — Substrate-specced in `CIRISRegistry/FSD/FSD-002_FEDERATION_SURFACE.md §3.5.1` as the five Coherence-Ratchet detectors, including `detection:hash_chain_integrity` (boolean-via-score, -1 on break — "non-forgeable evidence of deletion") + `detection:intra_agent_consistency` (signed — same agent over time, sudden self-inconsistency). LensCore phasing per `CIRISLensCore/FSD/LENS_CORE_V0_5.md §4.7` (the five CCA §F detectors are v0.6+ work; v0.5 ships `cohort_mismatch`, `manifold_outlier`, `unconsented_external_probe`). Substrate substitution trajectory routes detection into LensCore at step 3.
- No automated `attestation:l5` ratification flow yet — L5 requires both `audit_ok` and `play_integrity_ok`. Substrate-specced as `attestation:l5:agent_integrity` (FSD-002 §3.2; Verify §4 + Agent §4.6 — "agent source-tree byte-equal against registered manifest"). TPM-quote equivalent for server-side is structurally supported via `TPMAttestation` proto in `CIRISVerify/FSD/FSD-001 §4 HardwareAttestation` (`tpm_quote` + `pcr_values` + `aik_certificate` fields). Server-side L5 lands when agent populates `attestation:l5:agent_integrity` from a TPM-quote rather than from Play Integrity.
- `accord_public_keys` registration (`service.py:1790`) is one-way — Substrate-specced via the `delegates_to` structural primitive (FSD-002 §2.2.1) with `delegation_purpose: "hardware_rotation"` and bounded `delegation_valid_from`/`delegation_valid_until` window. Rotation surfaces structurally through the `delegates_to` chain in the federation chain; agent emits the rotation `delegates_to` row once federation-wire `delegates_to` envelopes land. Anti-rollback specced as `rollback_detected:{revision_field}` (FSD-002 §3.2 — "-1 only" polarity — "Anti-rollback — decrease in revocation revision").
- `tsdb_consolidate_audit` summary nodes carry `audits=attrs.get("audits", [])` lists but no chain hash anchor — a consolidation window's integrity proof is implicit in the persist chain, not explicit in the summary node.
- CONF-03 (ASEAN §A.4.18 explainability fallback) is not yet wire-flagged; downstream consumers cannot distinguish "explainability constitutive" vs "explainability fallback admissible" in evidence_refs.
- Cross-substrate provenance from CIRISVerify → CIRISRegistry → CIRISAgent is fully implemented for binary + file-tree integrity but does NOT yet extend to localization artifacts (`localization/*.json`, `ciris_engine/data/localized/*.txt`) at L4 granularity — they share a single coarse hash rather than per-locale signed sub-manifests.
- TSDB consolidation occasionally produces `tsdb_consolidate_audit` summary nodes (`tsdb_consolidation/service.py:720,1088,1197`) but their integrity guarantee is implicit in the persist chain — no explicit Merkle anchor per consolidation window.
- Test coverage: `tests/ciris_engine/logic/services/graph/test_audit_service.py` exercises persist-routed chain writes and `verify_complete_chain` against a 69-entry fixture but no fixture asserts that identity-variance + audit-chain + file-integrity together compose into a single "integrity verified" attestation surface.

Proposed pointer (from seed): `(none specified in seed)` — primary code references: `ciris_engine/logic/audit/`, `ciris_engine/logic/services/graph/audit_service/`, `tools/dev/stage_runtime.py`, `ciris_engine/logic/infrastructure/sub_services/identity_variance_monitor.py`.
<!-- END HUMAN -->
