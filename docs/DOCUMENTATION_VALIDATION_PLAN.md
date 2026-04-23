# Documentation Validation Plan - Bottom-Up Approach

## Overview

This plan defines a reproducible process for keeping grant-facing and architecture-facing claims synchronized with code reality.

The immediate Round 1 objective is to remove stale hard-coded counts (tests/endpoints) and replace them with script-generated baselines that can be re-run before each release and before external reporting deadlines.

## Validation Hierarchy

### Level 1: Implementation Files (Ground Truth)

1. **Service Implementations** (`ciris_engine/logic/services/`)
   - Validate service taxonomy and category mapping.
2. **Protocol Definitions** (`ciris_engine/protocols/`)
   - Validate protocol ↔ implementation alignment.
3. **Schema Definitions** (`ciris_engine/schemas/`)
   - Validate schema drift and typed contract coverage.
4. **Action Handlers** (`ciris_engine/logic/handlers/`)
   - Validate ten-verb implementation and handler routing.
5. **API Router Registration** (`ciris_engine/logic/adapters/api/app.py`)
   - Validate endpoint inventory from runtime registration.

### Level 2: Local Documentation

- Service READMEs, protocol READMEs, schema READMEs, and route docs must inherit counts from Level 1 outputs.

### Level 3: Public/External Claims

- `README.md`, `CLAUDE.md`, grant text, architecture docs, and site pages must only reference script-derived numbers.

### Level 4: Operational Evidence

- CI test collection logs, endpoint inventory output, and baseline snapshots must be retained in `docs/grant/`.

---

## Round 1 Measurement Methodology (Implemented)

### Canonical script

Use:

```bash
python tools/analysis/round1_grant_baseline.py \
  --markdown-out docs/grant/ROUND1_BASELINE_$(date +%F).md
```

This script captures:
- Service taxonomy counts from `ApiServiceConfiguration`
- Endpoint counts from the live FastAPI route graph (`create_app()`)
- Test collection totals/errors via `pytest --collect-only -q tests -o addopts=`

### Why this replaces stale static counts

- **Tests** and **endpoint** counts change frequently; hard-coding values in docs creates drift.
- The baseline script provides a single, repeatable mechanism for “latest known truth.”

---

## Round 1 Baseline Snapshot (2026-04-22 UTC)

Source artifact: `docs/grant/ROUND1_BASELINE_2026-04-22.md`.

- **Core services:** 22
  - graph 7, infrastructure 4, lifecycle 4, governance 4, runtime 2, tool 1
- **API method+path routes:** 257
  - GET 139, POST 83, PUT 17, PATCH 2, DELETE 16
- **Tests collected:** 10,662
- **Collection errors:** 37
- **Missing plugins detected in this environment:** `pytest_asyncio`, `hypothesis`

---

## Low-Hanging Hygiene Fixes (Round 1)

### Ship before June 1, 2026

1. Replace stale “78/99 endpoint” claims in grant-facing docs with “script-generated; see latest baseline artifact.”
2. Replace stale “3,500+ tests” claims with baseline-derived count plus date stamp.
3. Add a CI job that runs `round1_grant_baseline.py --skip-tests` on every PR.
4. Add a nightly CI job with full collection (`--skip-tests` off) and publish artifact.

### Ship this quarter

1. Install and pin missing pytest plugins in dev/test image (`pytest-asyncio`, `hypothesis`) so collection errors reflect code issues rather than environment gaps.
2. Normalize service strata naming across docs (Graph/Infrastructure/Runtime/Governance/Core Tool vs Lifecycle naming).
3. Add a generated endpoint CSV (path, method, auth dependency presence) to support the authZ audit pass.

### Nice to have

1. Add doc lint to block stale numeric claims unless accompanied by baseline date + artifact reference.
2. Auto-open a docs PR if baseline count deltas exceed thresholds.

---

## Ongoing Maintenance Schedule

### Per PR
- Run baseline script with `--skip-tests` and check service/endpoint drift.

### Nightly
- Run full baseline including pytest collection and persist markdown artifact.

### Pre-release / Pre-grant submission
- Regenerate baseline same day as submission and update all externally visible claim docs.

---

## Success Criteria

1. Every numeric claim in docs is either:
   - generated from tooling, or
   - stamped with measurement date and source artifact.
2. No conflicting endpoint/test/service counts across top-level docs.
3. Grant-facing counts can be reproduced from commands in this file.
