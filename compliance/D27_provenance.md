# D27 — `provenance:*` (STRONG-3)

> Build manifest provenance (foundational technical-infrastructure attestation)

**Seed reference**: `SEED_DIMENSIONS.yaml` v1.0, dimension `D27` ([source](https://github.com/CIRISAI/ciris-response-magnifica-humanitas/blob/main/SEED_DIMENSIONS.yaml))
**Accord principle**: integrity
**Attestation density**: MH=0 · EU=1 · IEEE=1 · ASEAN=1 · total=3

**Absent from**: MH — Foundational technical-infrastructure attestation rather than principled claim.

## Regulatory attestations

*(Auto-rendered from seed; do not hand-edit. Re-run `python tools/compliance/generate_ciris_compliance_stubs.py tools/compliance/SEED_DIMENSIONS.yaml compliance/` after seed updates.)*

- **EU** (Ethics Guidelines for Trustworthy AI) — *§III.7*
    > "lifecycle provenance for auditability"
    Wire form: `provenance:build_manifest`
- **IEEE** (Ethically Aligned Design, First Edition) — *Ch9*
    > "build-time evidence chain for compliance"
    Wire form: `provenance:build_manifest`
- **ASEAN** (ASEAN Guide on AI Governance and Ethics) — *Annex A*
    > "model provenance tools as risk-assessment requirement"
    Wire form: `provenance:build_manifest`

## Wire primitives

- `provenance:build_manifest`

---

<!-- BEGIN HUMAN -->
## What this dimension covers

Provenance is the claim that the running agent is the exact artifact CI built — same bytes, same dependencies, same identity lineage — and that any third party can verify this without trusting the operator. It's the foundation underneath every other integrity claim: if you can't prove what's running, the audit chain and disclosure log are just promises.

## How CIRIS implements this today

The canonical signed manifest lives in the upstream CIRIS substrate (the verifier + registry components). CIRISAgent's three jobs: (a) at build time, stage a deterministic runtime tree so the sign-time and verify-time fingerprints match; (b) at runtime, walk every loadable file and compare against the registered fingerprint of every file in the running build; (c) carry the resulting provenance state into every trace.

- **Build-time canonical staging — deterministic tree for sign-time fingerprint**:
    - `tools/dev/stage_runtime.py:1-52` — produces a clean directory tree containing only runtime-loaded files; the canonical input for manifest signing, wheel packaging, mobile bundling, and runtime verification.
    - `tools/dev/stage_runtime.py:76-115` — exemption rules are themselves signed into the manifest, mirroring the verifier's rules.
    - `tools/dev/stage_runtime.py:25-36` — include roots are `ciris_engine`, `ciris_adapters`, `ciris_sdk`; exempt directories and extensions are enumerated.
    - `tools/dev/stage_runtime.py:49-51` — `--print-manifest` output is CI-stable and diffable against the registered manifest.
- **Template manifest — subordinate signed chain for templates**:
    - `tools/templates/generate_manifest.py:3` — generates a signed manifest of pre-approved agent templates.
    - `tools/templates/generate-template-manifest.py:3` and `tools/generate_template_manifest.py:3` — alternate entry points.
    - `tools/templates/validate_templates.py` — validates templates against the signed manifest before runtime loads them.
- **Runtime verification — every loadable file fingerprint-checked**:
    - `ciris_engine/logic/services/infrastructure/authentication/attestation/tree_verify.py` — walks the file tree and reproduces the same hashes the signing-time walker produced.
    - `ciris_engine/logic/services/infrastructure/authentication/attestation/result_builder.py:284-285` — populates per-file totals: files checked, files passed, files failed.
    - `ciris_engine/schemas/services/attestation.py:69-167` — provenance fields including `cross_validated_files` (the strongest signal: disk and agent and registry all agree), per-source-only verifications, and a tampering-indicator field (`disk_agent_mismatch`).
    - `ciris_engine/schemas/services/attestation.py:160-163` — number of registry sources agreeing (0-3) plus the full attestation proof.
- **Identity lineage — provenance of who created the agent**:
    - `ciris_engine/schemas/runtime/extended.py:48-55` — `IdentityLineage`: creation provenance ("relationship back to this root, establishing clear provenance for all knowledge").
    - `ciris_engine/schemas/services/agent_credits.py` — ties contributions back to provenance metadata.
- **CI build provenance — origin of the bytes CI shipped**:
    - `tools/qa_runner/modules/safety_battery.py:241-246` — captures GitHub Actions workflow metadata (commit SHA, run ID, workflow name) aligned with `actions/attest-build-provenance@v1`.
    - `tools/qa_runner/modules/safety_battery.py:817-864` — bundle hashes that the build-provenance attestation binds against.
    - `tools/qa_runner/modules/safety_interpret.py:65,1059` — reuses the same CI provenance capture for interpret-stage rollups.
- **Mobile/desktop build provenance**:
    - `tools/build_test_wheel.py` — builds platform-specific wheel with bundled GUI JAR, mimicking CI.
    - `tools/update_ciris_verify.py` — updates verifier binaries and bindings for Android/iOS (cross-platform staging).
    - `tools/analysis/round1_grant_baseline.py:1-60` — reproducible grant-readiness baseline; captures core service taxonomy, REST endpoint inventory, test inventory.

## How you can tell it's working (observability)

If you want to verify the running agent against its registered manifest, the per-trace provenance signals and the API expose the same evidence the runtime checked.

- **Per-trace provenance signals**: traces ship the verifier version, agent version, and the full module-integrity summary. `cross_validated_files` (all three sources — disk, agent, registry — agreeing) is the load-bearing signal.
- **Per-trace version pinning**: `verify_version` is pinned per-trace (`FSD/TRACE_WIRE_FORMAT.md:558-561`) so a future change in verifier semantics doesn't silently invalidate older comparisons. Provenance is implicitly version-anchored.
- **The audit chain is a provenance chain**: every chain entry's signature traces back through the public-key directory to a hardware-rooted key, which is itself bound to a registered binary manifest. Walking the chain end-to-end is walking provenance.
- **Federation evidence**: outbound Contributions cite `dimensions: ["D27"]` when evidentiary weight depends on the build manifest matching the registered one. EU §III.7 "lifecycle provenance for auditability", IEEE Ch9 "build-time evidence chain for compliance", and ASEAN Annex A "model provenance tools as risk-assessment requirement" all converge here.
- **Telemetry**: `/v1/telemetry/unified` includes module-integrity status and cross-validated-files counts per-service.

## Current limitations & next steps

- **Per-trace calibration-version pin** — the federation calibration system that tunes detectors over time (RATCHET) is versioned upstream; the agent does not yet pin which calibration version a trace was emitted under. The substrate provides the structural primitive (`delegates_to` chains, FSD-002 §3.5.3 — the rename from old to new calibration name happens through the wire format itself rather than as a breaking flag day). Agent-side emission lands when federation-wire delegation envelopes ship. Tracked at `CIRISAgent#820`.
- **SLSA attestation cross-referenced from AttestationResult** — CI captures SLSA-style build attestations via `actions/attest-build-provenance@v1` and the safety battery captures matching bundle hashes; the two trails are not yet cross-referenced inside the runtime `AttestationResult`. Connecting them is a near-term step.
- **Per-locale signed sub-manifests** — localized prompts (`ciris_engine/data/localized/*.txt`) are covered today at coarse granularity (whole-file hash). Per-locale per-revision granularity is shared work with the upstream registry substrate. Tracked at `CIRISRegistry#29`.
- **Trace-to-manifest binding** — traces carry verifier version but not an explicit "this trace was produced by an agent whose manifest matched registry hash X." Adding the explicit binding is a near-term step.
- **Markdown CI gate** — runtime-loaded `.md` files would silently fall outside the manifest today (the staging rule exempts `.md` for devnote isolation). A CI gate that fails if any `.md` is referenced from runtime code paths is tracked at `CIRISAgent#807`.
- **Template-provenance forward projection** — the signed template manifest exists; surfacing "this agent is running template T whose manifest hash is X" inside `AttestationResult` is next.
- **`/v1/system/federation` endpoint** — the runtime knows its own provenance state via `AttestationResult.attestation_proof`; the API exposes high-level booleans but not the full proof chain. Endpoint coming next.
- **Identity-lineage cross-link to build manifest** — `IdentityLineage` tracks identity creation provenance but is not yet cross-linked to the build manifest ("I was created by an agent running build hash X"). Next step.
- **Skill-import signed manifests** — community skill imports validate source URL but do not yet require a signed manifest. The substrate spec for this primitive is `provenance:skill_import:{source}`; tracked at `CIRISRegistry#28`.

Proposed pointer (from seed): `(none specified in seed)` — Agent-side primary code: `tools/dev/stage_runtime.py` (canonical staging), `tools/templates/generate_manifest.py` (template manifest), `ciris_engine/logic/services/infrastructure/authentication/attestation/tree_verify.py` (runtime verification), `ciris_engine/schemas/services/attestation.py:69-167` (per-file results, cross-validation flags).

## Quantitative baseline

Per [MEASUREMENT_METHODOLOGY.md](MEASUREMENT_METHODOLOGY.md), the build-provenance evidence pipeline uses `tools/analysis/round1_grant_baseline.py` to capture reproducible numeric claims. Current baseline ([`baselines/2026-05-28.md`](baselines/2026-05-28.md)):

- **22 core services**, **256 API routes** — the surface CIRISVerify's tree-verify covers per `tree_verify.py`
- **6 service categories** (graph/infrastructure/lifecycle/governance/runtime/tool) — each manifests separately in `ApiServiceConfiguration`

Historical baselines in [`baselines/`](baselines/) provide the provenance trail for the documentation itself — D27 is partly self-referential: this dimension's evidence claims about CIRIS provenance ARE provenance-tracked via the same dated-snapshot pattern.

## Tracked requirements

- **Umbrella(s)**: `CIRISLensCore#26` — F-3 detector family per FSD-002 §3.5.3
- **Substrate spec(s)**: `CIRISRegistry#28` — `provenance:skill_import:{source}` primitive; `CIRISRegistry#29` — Per-locale `provenance:build_manifest:{target}` granularity
- **2.9.5**: `CIRISAgent#807` — CI gate: no .md from runtime
- **2.9.7**: `CIRISAgent#820` — calibration_version per trace

See `compliance/README.md` cross-cutting findings table for the 3.0 requirements finalization context.
<!-- END HUMAN -->
