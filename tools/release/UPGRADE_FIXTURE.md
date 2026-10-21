# Upgrade-compat fixture contract

## What this is

A bundle of agent databases produced by an in-CI vN-1 run and consumed by
vN's upgrade-compat test matrix. The test answers: *does a fresh checkout
of vN cleanly boot any of the database shapes vN-1 actually produces?*

In industry terms this is a **golden-snapshot upgrade test** (or "vN-1 → vN
compatibility test"). Each fixture is one golden artifact.

## Why three sources

The first iteration of this tooling built fixtures from a custom builder
that drove the setup wizard directly. That approach reinvented CI plumbing
(libtss2 install, server lifecycle, setup-payload shape, Wakeup-state
timing) and was brittle to setup-API drift — three sequential CI failures
chasing endpoint paths and reserved usernames.

The current approach piggybacks on three workflows that **already** bring
the agent up through the proper bootstrap path with mock LLM:

| Host workflow | What it exercises | Fixture identifier |
|---|---|---|
| `safety-battery.yml` (capture job) | Setup + full safety-scenario interaction with reasoning traces | `safety` |
| `memory-benchmark.yml` | Setup + 1000-message synthetic burst | `memory-burst` |
| `build.yml` (Staged QA job) | Setup + full qa_runner module sweep | `qa-full` |

Each host gets a `Capture upgrade-compat fixture` step at the end that
invokes the composite action at `.github/actions/capture-upgrade-fixture/`.
The composite action locates the agent's data dir, copies every `*.db`
file, computes sha256s, writes a `MANIFEST.json`, and uploads the bundle as
a separate workflow artifact.

This means **every CI run that touches the agent automatically produces a
fresh fixture** — no manual "go grab a DB from datum" loop, no custom
scenario plumbing to maintain.

## Fixture contents

Each artifact bundle contains all three of the agent's database files plus
a manifest:

```
upgrade-fixture-<version>-<source>[-<scenario-tag>]/
  ciris_engine.db        # graph nodes, tasks, thoughts, config, telemetry
  ciris_audit.db         # Ed25519-signed audit chain (legacy pre-2.9.0 format)
  secrets.db             # encrypted secrets store + master-key bootstrap state
  MANIFEST.json          # version, sha256s, source identifier, scenario tag,
                         # git_sha, workflow_run, captured_from path
```

The three DBs map to the three current absorption targets:

| DB file | Consumer test exercises |
|---|---|
| `ciris_engine.db` | A0a graph migration — every node/edge re-routed through persist Engine |
| `ciris_audit.db` | A0b audit-chain bridge — legacy chain root sha256 → `prev_hash` of seq=1 entry in `cirislens_audit_log` |
| `secrets.db` | Lane D3 (future) — secrets CRUD absorption via persist's `cirislens_secrets_*` substrate |

## Artifact naming

`upgrade-fixture-<agent_version>-<source>[-<scenario_tag>]`

- `safety` carries a scenario tag of the form `<lang>-<domain>-<template>`
  (e.g. `upgrade-fixture-2.8.13-stable-safety-am-mental_health-default`)
- `memory-burst` and `qa-full` are unparameterized

## Consumer side (vN's upgrade-compat matrix)

The consumer workflow (filed under release/2.9.0; not part of 2.8.13) will:

1. Use a `strategy.matrix.fixture` of `[safety, memory-burst, qa-full]` —
   one cell per host workflow
2. Download the latest matching artifact via `gh run download` against the
   previous release branch
3. Place the three DBs into a fresh `CIRIS_HOME/data/`
4. Boot vN through `_bootstrap_persist_engine` — A0a + A0b fire against the
   legacy DBs
5. Assert:
   - `.persist_migrated` sentinel written (A0a)
   - `.audit_bridged` sentinel written (A0b)
   - `cirislens_audit_log` row exists with `legacy_seq` matching the
     snapshot's terminal sequence_number
   - graph node counts equal pre-migration counts (no data loss)
   - no exceptions during boot
6. Optionally run a smoke interaction to confirm the migrated agent is
   operational on the new substrate

## Operational notes

- **Retention:** 90 days per `actions/upload-artifact@v4` setting. Short
  enough to not bloat the repo; long enough that vN consumers always have
  fresh artifacts from the previous release branch.
- **Determinism:** The fixtures are *not* byte-identical across CI runs
  (timestamps, generated UUIDs, telemetry timings vary). The consumer
  matrix asserts on *structural* invariants (counts, sentinel presence,
  bridge-row well-formedness), not on exact sha256s. The MANIFEST captures
  per-run sha256s for forensic comparison only.
- **Failure visibility:** A fixture capture failure does NOT block the
  host workflow — it's an `if: success()` step that runs only when the
  primary work succeeded. The composite action exits with `::error::`
  annotations so failures are visible in the workflow summary.

## Why not check fixtures into git?

Two reasons:
1. Pre-commit blocks files >250 KB (`check-added-large-files`); an audit DB
   for a real-scenario fixture easily exceeds that.
2. Fixtures become stale relative to the producer's setup-wizard / scenario
   surface as both evolve. Re-generating on every CI run keeps them
   permanently current.

Workflow artifacts (90-day retention) are the right home for this kind of
short-lived, large, regenerable evidence.
