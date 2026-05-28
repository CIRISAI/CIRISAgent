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
## CIRIS-side compliance implementation

`provenance:build_manifest` is the foundational claim that a running agent is the artifact it claims to be — same bytes, same dependencies, same identity lineage that CI built. The canonical signed manifest lives in CIRISVerify + CIRISRegistry; CIRISAgent's role is to (a) STAGE the canonical runtime tree deterministically, (b) VERIFY against the registered manifest at runtime, and (c) carry provenance metadata into every trace.

- **Canonical staging (build-time)**:
    - `tools/dev/stage_runtime.py:1-52` — `stage_runtime`: produces a clean directory tree containing ONLY runtime-loaded files; canonical input for CIRISVerify manifest signing (`ciris-build-sign sign --tree <staged> --target python-source-tree`), wheel packaging, mobile bundling, and runtime file-tree verification
    - `tools/dev/stage_runtime.py:76-115` — `ExemptRules`: mirrors `ciris_verify_core::security::build_manifest::ExemptRules`; serialized into signed `FileTreeExtras`; defaults match CI `ciris-build-sign` invocation plus `md` exempt (2.8.5)
    - `tools/dev/stage_runtime.py:25-36` — Include roots: `ciris_engine`, `ciris_adapters`, `ciris_sdk`. Exempt dirs/extensions explicitly enumerated and matched against CI workflow flags
    - `tools/dev/stage_runtime.py:49-51` — `--print-manifest` output is CI-stable and diffable against the canonical manifest registered with CIRISRegistry under `project=ciris-agent`
- **Template manifest (subordinate provenance)**:
    - `tools/templates/generate_manifest.py:3` — Generate a signed manifest of pre-approved CIRIS templates
    - `tools/templates/generate-template-manifest.py:3` — alternate entry point
    - `tools/generate_template_manifest.py:3` — top-level alias
    - `tools/templates/validate_templates.py` — validates templates against the signed manifest before agent runtime loads them
- **Runtime verification**:
    - `ciris_engine/logic/services/infrastructure/authentication/attestation/tree_verify.py` — file-tree integrity walker; reproduces the same hashes the signing-time walker produced
    - `ciris_engine/logic/services/infrastructure/authentication/attestation/result_builder.py:284-285` — `file_fields` populated from registry manifest verification: `total_files`, `files_checked`, `files_passed`, `files_failed`, `per_file_results`
    - `ciris_engine/schemas/services/attestation.py:69-167` — provenance fields: `total_files`, `module_integrity_summary`, `cross_validated_files` (disk == agent == registry, strongest verification), `filesystem_verified_files` (disk == registry, no agent hash), `agent_verified_files` (agent == registry, e.g. Chaquopy), `disk_agent_mismatch` (RED FLAG: tampering indicator), `registry_mismatch_files`
    - `ciris_engine/schemas/services/attestation.py:160-163` — `sources_agreeing`: number of registry sources that agree (0-3); `attestation_proof`: full attestation proof from CIRISVerify
- **Identity provenance (lineage)**:
    - `ciris_engine/schemas/runtime/extended.py:48-55` — `IdentityLineage`: creation provenance; "relationship back to this root, establishing clear provenance for all knowledge"
    - `ciris_engine/schemas/services/agent_credits.py` — agent credit tracking ties contributions back to provenance metadata
- **CI build provenance capture (run-time origin)**:
    - `tools/qa_runner/modules/safety_battery.py:241-246` — `_capture_ci_provenance()`: captures GitHub Actions workflow metadata (commit SHA, run ID, workflow name); aligns with `actions/attest-build-provenance@v1` records
    - `tools/qa_runner/modules/safety_battery.py:817-864` — bundle hashes that `attest-build-provenance` binds against; `ci_provenance` field on safety battery output
    - `tools/qa_runner/modules/safety_interpret.py:65,1059` — reuses `_capture_ci_provenance` for interpret-stage rollups
- **Mobile/desktop build provenance**:
    - `tools/build_test_wheel.py` — builds platform-specific wheel with bundled GUI JAR, mimics CI
    - `tools/update_ciris_verify.py` — updates CIRISVerify binaries + Python bindings for Android/iOS (cross-platform provenance staging)
    - `tools/analysis/round1_grant_baseline.py:1-60` — reproducible Round 1 grant-readiness baseline; captures core service taxonomy, REST endpoint inventory, test inventory; baseline at `docs/grant/ROUND1_BASELINE_2026-04-22.md`

## Observability hooks

- **LensCore F-3 family**: not implemented for build-provenance specifically. The lens consumes per-trace `verify_version` (`FSD/TRACE_WIRE_FORMAT.md:558-561`) so that a future CIRISVerify version which changes attestation semantics doesn't silently invalidate older comparisons — provenance is implicitly version-anchored per trace.
- **RATCHET calibration**: provenance verification is bedrock for any calibration claim; the agent should pin which calibration version a given trace was emitted under (not yet implemented — see Known gaps).
- **Trace projection**: `verify_version`, `agent_version`, and the full `module_integrity_summary` are projected into traces. `cross_validated_files` (strongest provenance — all three sources agree) is the load-bearing signal.
- **Audit chain queries**: every chain entry's signature traces back through `accord_public_keys` to a CIRISVerify-rooted hardware key, which is itself bound to a registered binary manifest — the audit chain IS a provenance chain when walked end-to-end.
- **Federation evidence_refs**: emitted Contributions cite `dimensions: ["D27"]` when the contribution's evidentiary weight depends on the agent's build manifest matching the registered one. EU §III.7 "lifecycle provenance for auditability", IEEE Ch9 "build-time evidence chain for compliance", and ASEAN Annex A "model provenance tools as risk-assessment requirement" all converge on `provenance:build_manifest`.
- **Telemetry**: `/v1/telemetry/unified` includes `module_integrity_ok`, `cross_validated_files` counts per service rollup.

## Known gaps / not-yet-implemented

- **Per-trace calibration version anchor**: the agent does NOT pin which RATCHET/calibration package version a given trace was emitted under. Substrate-specced via the `delegates_to` chain pattern in FSD-002 §3.5.3 — "Consumers pinning `RATCHET/calibration/correlated_action_v{N}.yaml` SHOULD see a `delegates_to` structural attestation from the RATCHET release authority mapping the old name to the new (`delegates_to:correlated_action_v{N+1}:from:emergent_deception_v{N}`). One of FSD-002 §2.2's four structural primitives doing real federation work — the rename happens *through* the wire format's own mechanisms rather than as a breaking flag day." Calibration-package amendment discipline per FSD-002 §4.9.2 (rules-layer Contribution + WA quorum). Agent emits the calibration-version pin once federation-wire `delegates_to` envelopes land.
- **Cross-substrate provenance chains** (the seed's "foundational technical-infrastructure attestation"):
    - CIRISAgent (staged tree) → ciris-build-sign (signing) → CIRISRegistry (manifest registration) → CIRISVerify (runtime verification): WIRED for `ciris_engine`, `ciris_adapters`, `ciris_sdk` source trees
    - CI workflow run → `actions/attest-build-provenance@v1` → SLSA-style attestation: WIRED in `safety_battery.py`, but the resulting SLSA attestation is NOT cross-referenced from the runtime `AttestationResult` — they are two parallel provenance trails
    - CIRISAgent → ACCORD localized prompts (`ciris_engine/data/localized/*.txt`) → registered manifest: WIRED at coarse granularity (whole file hash) but NOT at per-locale per-revision granularity
    - CIRISAgent → CIRISLensCore (downstream traces): version-anchored per-trace, but no provenance binding that "this trace was produced by an agent whose manifest matched registry hash X"
    - CIRISAgent → CIRISEdge (data-at-rest): NOT WIRED (CIRISEdge integration absent — see D26)
- **Markdown-as-devnotes rule**: `tools/dev/stage_runtime.py:31-36` exempts `.md` from the manifest (2.8.5 devnote-isolation). Any future `.md` file that becomes runtime-loaded would silently fall outside the provenance chain — there is no CI gate verifying that no `.md` is referenced from runtime code paths.
- **Template manifest (subordinate chain)**: signed template manifest exists but the linkage from "this agent is running template T" → "T's manifest hash is X" → "X is registered with CIRISRegistry" is not surfaced in `AttestationResult`. Template provenance is verified at template-load time but not projected forward into traces.
- **MH absence**: zero MH attestations; foundational technical-infrastructure attestation rather than principled claim. No agent-side wiring connects MH-style provenance language to the technical primitive.
- **No `/v1/system/federation` endpoint** exposing the agent's currently-registered manifest hash to operators — the runtime knows its own provenance state via `AttestationResult.attestation_proof` but the API only exposes high-level booleans, not the full proof chain.
- **Identity lineage gaps**: `IdentityLineage` (`ciris_engine/schemas/runtime/extended.py:48-55`) tracks identity creation provenance but is not cross-linked to the build manifest; an agent's identity record does not carry "I was created by an agent running build hash X".
- **Skill-import provenance**: `ciris_engine/logic/services/skill_import/parser.py:172` and `builder.py:181` track `source_url` for imported skills but do not require a signed manifest — community skills enter the runtime with parser-validated but unsigned provenance.

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
