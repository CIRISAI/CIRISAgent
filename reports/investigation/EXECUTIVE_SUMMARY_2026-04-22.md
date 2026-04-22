# CIRIS Investigation Executive Summary (Baseline Pass)

Date: 2026-04-22 (UTC)
Scope: Consolidated summary of completed investigation artifacts to date.

## What is complete

1. **Section 1 (items 1–3) deep pass** completed with concrete findings.
2. **Section 1 (items 4–8) pass-1** completed with evidence + explicit caveats.
3. **Sections 2–12 baseline discovery sweep** completed (probe-level signal capture) for planning and prioritization.

## Key findings (high signal)

### Confirmed in code

- **22 core services exist** in code, but are organized as **six categories** (Graph, Infrastructure, Lifecycle, Governance, Runtime, Tool), not three strata in the grant wording.
- **Ten-verb action framework exists and is wired** through the runtime handler registry.
- **H3ERE conscience faculties exist** as four evaluator classes: entropy, coherence, optimization veto, epistemic humility.
- **Google OAuth flows and 14-day consent retention logic** are implemented in code, including explicit cleanup/delete paths in consent service.

### Contradicted / drift detected

- **"99 REST endpoints" claim is not aligned** with current static inventory baseline (256 discovered route decorators under API prefix scan).
- Service taxonomy wording drifts between public claim language and in-code categorization.

### Unverified in this environment (needs full validation run)

- **"3,500+ unit tests passing"** as a pass-status claim is not verified from this container run; collection succeeded at large scale but included collection errors due missing test dependencies.
- **"228MB RAM per agent"** was not benchmarked yet (cold start / +100 / +1000 message checkpoints pending).
- **Ed25519 audit chain end-to-end trace for SPEAK path** still needs a runtime integration proof (emit -> chain link -> signature verify -> persistence).

## Baseline coverage status by phase

- **Phase A**: Section 1 + baseline probes for Sections 2/8/9 captured.
- **Phase B**: baseline probes for Sections 3/10 captured.
- **Phase C**: baseline probes for Sections 4/5/6 captured.
- **Phase D**: baseline probes for Sections 7/11/12 captured.

## Ship-before-June-1 priorities

1. Replace or qualify any hardcoded endpoint-count claim using release-time generated OpenAPI counts.
2. Produce CI-backed pass/fail/skip test metrics from a fully provisioned environment.
3. Add integration tests for:
   - SPEAK -> audit-chain verification end-to-end,
   - 14-day retention hard-delete proof across storage layers.
4. Run and artifact memory benchmark for the published RAM claim.
5. Decide and document whether external architecture language uses six categories directly or an explicit mapping into three strata.

## Immediate next execution step

Start deep-validation on **Section 2** (known bugs + fix diffs), then **Section 3** (security surface), using the baseline evidence files to drive line-level verified findings.
