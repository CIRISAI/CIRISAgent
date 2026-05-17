# Upgrade-compat fixture contract

## What this is

A frozen agent-DB snapshot produced by each release branch, consumed by the
**next** major release's upgrade-compat test matrix. The test answers: *does a
fresh checkout of vN cleanly boot an agent DB produced by vN-1?*

In industry terms this is a **golden-snapshot upgrade test** (sometimes
"vN-1 → vN compatibility test"). The fixture is the golden artifact.

## Per-release responsibilities

| Role | Where | What |
|---|---|---|
| **Producer** (vN-1) | this branch | Build the fixture: `python -m tools.release.build_upgrade_fixture --out fixtures/v<version>` |
| **Consumer** (vN) | next branch | Boot fixture through bootstrap path (A0a + A0b on 2.9.0), assert sentinels written + chain bridged + no exceptions |

Producer ships fixture as a GitHub release asset (or workflow artifact, for
unreleased branches). Consumer checks it in at
`tests/fixtures/upgrade_snapshots/v<version>/` and exercises it from a CI
matrix entry.

## Fixture contents

```
fixtures/v2.8.13/
  ciris_engine.db          # graph + tasks + thoughts + config
  ciris_audit.db           # legacy audit chain (Ed25519-signed)
  MANIFEST.json            # version, sha256s, scenario digest, build time
```

## Scenario

The fixture is built by `build_upgrade_fixture.py`. It runs a fixed,
deterministic scenario against the agent with `--mock-llm`:

1. Setup wizard with known admin password
2. Fixed list of agent interactions (see `SCENARIO_MESSAGES`)
3. Graceful shutdown to flush the chain

If the scenario changes, **bump `SCENARIO_VERSION`** in the script. Manifest
records the digest so consumers can detect drift.

## Why deterministic?

Two reasons:

1. **Reproducibility.** CI re-runs must produce byte-identical fixtures
   (modulo timestamps), so failure diffs point at real upgrade-path bugs
   rather than noise.
2. **Diff-able expectations.** The consumer test asserts specific row counts
   (e.g. graph nodes from the scenario), and those counts must be stable.

## Open question for 2.9.0

We may want fixtures from **multiple** prior releases (2.7.4, 2.8.10, 2.8.12,
2.8.13) so the matrix proves we can upgrade from any reasonably-recent agent
DB. The producer script is version-agnostic; just check out the old tag,
install, and run.
