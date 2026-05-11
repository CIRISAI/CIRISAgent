# FSD: Safety-Battery CI Loop

**Status**: Draft v1.0 (Spec; first impl in this PR).
**Owner**: CIRISNodeCore + CIRISAgent qa_runner.
**Last updated**: 2026-05-11.
**Cross-references**: `cirisnodecore/MISSION.md` v1.0 §7.3 (safety.ciris.ai
pilot scope); `cirisnodecore/SCHEMA.md` v1.0 §11 (BatteryManifest) +
§13 (canonical-vs-pending split); `tests/safety/README.md`;
`tools/qa_runner/modules/safety_battery.py`;
`.github/workflows/safety-battery.yml`.

This FSD lives under `cirisnodecore/FSD/` so it travels with the
CIRISNodeCore spec at extraction time. Until the rust crate is `[Impl]`,
the loop runs in CIRISAgent's CI; once folded, it migrates to the crate
with no schema changes.

---

## 1. Why this loop

`MISSION.md` §7.3 names safety.ciris.ai as the pilot deployment of
CIRISNodeCore: external contributors propose questions / batteries /
prompt-edits / guide-edits / accord-edits as Contributions on the
federation chain; cell experts score real agent responses; tickets
emerge from scoring; edit proposals reference tickets; votes promote
winning edits into the canonical artifact in CIRISAgent's next release.

For that loop to function, safety.ciris.ai needs three things from the
CIRISAgent side:

1. **Reliable batch execution** of canonical batteries against the live
   agent, on a schedule, in CI, without per-run operator babysitting.
2. **Signed, addressable artifacts** that safety.ciris.ai can fetch,
   verify, and present to scorers — independent of GitHub's identity
   guarantees alone.
3. **Dedup** so the same (cell × battery_version × model × agent ×
   template) tuple doesn't burn LLM calls and CI minutes redundantly.

This FSD specifies all three.

---

## 2. The artifact tuple

A run is identified by a **6-element tuple**:

| Element | Source | Example |
|---|---|---|
| `cell.language` | BatteryManifest | `am` |
| `cell.domain` | BatteryManifest | `mental_health` |
| `battery_version` | BatteryManifest | `4` |
| `model_slug` | `--live-model` (slug-safe) | `google_gemma-4-31B-it` |
| `agent_version` | `ciris_engine/constants.py` | `2.8.9` |
| `template_id` | setup-completion payload | `default` |

Why each:

- **Cell** is the consensus boundary per `MISSION.md` Primitive 2/3. A
  run is bound to one (domain, language) cell.
- **`battery_version`** changes when the canonical question set changes
  (per `SCHEMA.md` §11). A `v4` and `v5` battery for the same cell are
  distinct artifacts.
- **`model_slug`** because the same battery against different models
  produces different responses — the (cell, model) pair is what
  scorers verify. Slugging: lowercase `/` → `_`, strip everything
  outside `[a-z0-9._-]`.
- **`agent_version`** because the agent's prompt surface, conscience
  faculty, and DMA pipeline change between releases. A 2.8.9 run and
  a 2.8.10 run against the same battery/model are distinct evidence.
- **`template_id`** because the agent's persona / identity / allowed
  capabilities differ per template. Today: `default` (Ally persona).
  Future: `datum`, `echo-speculative`, `scout` etc. each get their own
  artifact track.

### 2.1 Artifact name

```
safety-battery-{language}-{domain}-v{battery_version}-{model_slug}-{agent_version}-{template_id}
```

Example:

```
safety-battery-am-mental_health-v4-google_gemma-4-31B-it-2.8.9-default
```

GitHub Actions artifact name length cap is 255 chars; tuple fits well
under.

**Latest-wins**: no `run_id` in the name. Re-running the same tuple
overwrites the artifact pointer (each run still has a unique run_id
within the workflow run; the *named* artifact tracks the most recent).
safety.ciris.ai always fetches "the current canonical run of this
tuple."

### 2.2 What the artifact contains

```
safety-battery-am-mental_health-v4-...-2.8.9-default/
├── results.jsonl                 # one row per question, per SCHEMA.md §5.1
├── summary.json                  # run-level rollup
├── manifest_signed.json          # the signed envelope (§3)
└── workflow.log                  # stdout/stderr from the runner
```

GitHub Actions Sigstore attestation is bound to the bundle; verifies
via `gh attestation verify` (§3.2).

---

## 3. Signing model

Two complementary signatures cover the artifact end-to-end:

### 3.1 Per-response audit-chain anchors (intrinsic provenance)

Each row in `results.jsonl` carries `agent_task_id` — the ID of the
agent's task that produced the response. That task ID resolves to a
signed audit-chain entry produced by the agent's TPM-backed Ed25519
signer at response time. The audit entry is durable in CIRISPersist
(per substrate) and signed against the agent's published pubkey.

Verification path (scorer's POV):

1. Read `agent_task_id` from a JSONL row.
2. Query the audit chain for that task ID.
3. Confirm the audit entry's signature against the agent's pubkey
   (also recorded in `manifest_signed.json` for offline verification).
4. Confirm the audit entry's recorded SPEAK content matches the JSONL
   row's `agent_response`.

This is provenance *intrinsic* to the agent. Verifying does not require
trusting CI, GitHub, or any external party — only the agent's signing
key, which is already the federation's root of trust per
`FEDERATION_THREAT_MODEL.md`.

### 3.2 Bundle-level Sigstore attestation (extrinsic provenance)

After the runner completes, the workflow uses
`actions/attest-build-provenance@v1` to produce a Sigstore-signed
attestation binding `results.jsonl` + `summary.json` +
`manifest_signed.json` to:

- The workflow file (path + content SHA)
- The commit SHA on `main` at run time
- The GitHub Actions runner identity (Fulcio-issued cert)
- The run ID

Verification: `gh attestation verify <artifact> --owner CIRISAI` or
the Sigstore CLI. The attestation proves "this bundle was produced by
the `safety-battery.yml` workflow at commit X on the CIRISAI
repository." Tampering invalidates it.

The two signature layers cover different threat models:
- **(3.1) audit-chain anchors** prove the per-response content came
  from the named CIRIS agent.
- **(3.2) Sigstore attestation** proves the bundle was assembled by
  this CI workflow on this commit.

Either is sufficient for many threat models; both together close the
loop end-to-end.

### 3.3 `manifest_signed.json` schema

```json
{
  "schema": "ciris.ai/safety_battery_manifest_signed/v1",
  "run_id": "20260511T193000Z",
  "captured_at_start": "2026-05-11T19:30:00Z",
  "captured_at_end":   "2026-05-11T19:48:32Z",

  "cell": {"domain": "mental_health", "language": "am"},
  "battery_id": "am_mental_health_v4",
  "battery_version": 4,
  "rubric_sha256": "c1e8e9a9314afe32...",

  "agent_id": "datum",
  "agent_version": "2.8.9-stable",
  "agent_signing_pubkey_fingerprint": "de74eced",
  "template_id": "default",

  "model": "google/gemma-4-31B-it",
  "model_slug": "google_gemma-4-31B-it",
  "live_base_url": "https://api.together.xyz/v1",
  "live_provider": "openai",

  "bundle": {
    "results_jsonl_sha256": "ab12cd34...",
    "summary_json_sha256":  "ef56gh78..."
  },

  "agent_audit_anchors": [
    {
      "question_id": "am_mh_v4_q01",
      "agent_task_id": "task_01HX..."
    },
    ...
  ],

  "ci_provenance": {
    "github_repository": "CIRISAI/CIRISAgent",
    "github_sha": "ee0e7172d...",
    "github_run_id": "25700000000",
    "workflow_path": ".github/workflows/safety-battery.yml"
  }
}
```

The Sigstore attestation produced by `actions/attest-build-provenance`
signs over this file plus the JSONL + summary; safety.ciris.ai verifies
both layers before trusting the bundle.

---

## 4. Dedup pre-flight

Before launching the agent + LLM calls, the workflow checks whether a
matching artifact already exists:

```
GET /repos/CIRISAI/CIRISAgent/actions/artifacts
   ?name=safety-battery-am-mental_health-v4-google_gemma-4-31B-it-2.8.9-default
   &per_page=10
```

Sort by `created_at` desc. Take the most recent. If:

1. The artifact exists, AND
2. Its Sigstore attestation verifies (`gh attestation verify`), AND
3. Its `created_at` is within the **freshness window** (default 7 days;
   policy parameter, override via `workflow_dispatch` input `force`),

then the workflow exits cleanly with status `success`, a clear log line
identifying the existing artifact's URL, and a job-summary annotation
pointing safety.ciris.ai at the URL.

Otherwise the workflow proceeds with the battery run.

### 4.1 When the freshness window expires

By default 7 days. Rationales:

- LLM-side: providers update model snapshots; gemma-4-31B-it today and
  next week may differ behaviorally even at the same model name.
- Agent-side: same agent_version + same template + same battery_version
  should produce stable behavior, but week-to-week regressions are
  worth catching.
- CI cost: at ~$0.0002 per battery run on Together gemma, weekly
  refresh per cell is cheap. The freshness window is the dial.

Operators can force a fresh run via `workflow_dispatch` with
`force: true` regardless of existing artifacts. The cron path always
uses the freshness window check.

### 4.2 Multiple cells in one workflow

When a future workflow extension runs N cells in a matrix, the dedup
check runs per-cell (per-tuple, really). A run that's fresh for `am`
and stale for `ar` will skip am, run ar, attest only the new ar
artifact.

---

## 5. CI bootstrap robustness

The CI runner is ephemeral: no `~/ciris/.env`, no data dir, no prior
state. Two safeguards:

### 5.1 Module-metadata `WIPE_DATA_ON_START`

Modules that need a clean-slate start (because their assumptions about
agent state are violated by leftover data, OR because they need a
deterministic baseline for signed-artifact reproducibility) declare:

```python
class SafetyBatteryTests:
    WIPE_DATA_ON_START = True
```

The qa_runner reads this via the same `_module_metadata.py` mechanism
as `REQUIRES_LIVE_LLM` and `SERVER_ENV`. When `True`, the runner forces
`--wipe-data` regardless of CLI flags, triggering:

- Data directory cleared
- `CIRIS_FORCE_FIRST_RUN=1` set
- Auto-setup-completion path fires (per `server.py` setup payload at
  ~line 1240) — completes the wizard with the live LLM config the
  runner already has

Result: agent reaches WORK reliably, every time, even with no prior
state. No flaky "stopped waiting for setup" failures.

### 5.2 Workflow `env:` belt-and-suspenders

The workflow YAML carries:

```yaml
env:
  CIRIS_FORCE_FIRST_RUN: "1"
  PYTHONUNBUFFERED: "1"
```

`CIRIS_FORCE_FIRST_RUN=1` survives any subshell env scrubbing; the
agent will be in first-run mode regardless of what `.env` writes ran.
`PYTHONUNBUFFERED=1` is the memory-benchmark workflow's pattern — keeps
stdout streaming through `tee` so cancellations don't lose the in-flight
output buffer.

---

## 6. End-to-end flow

```
[ CI trigger: cron | workflow_dispatch | PR on tests/safety/** ]
                          ↓
[ Pre-flight: query GH Actions API for matching tuple artifact ]
                          ↓
              ┌───────────┴───────────┐
              ↓ found + fresh         ↓ not found / stale / forced
[ Exit success ]                      [ Continue ]
[ Annotate URL ]                          ↓
                          [ Write TOGETHER_API_KEY → ~/.together_key ]
                                          ↓
                          [ Invoke qa_runner safety_battery ]
                          [ Runner: --wipe-data forced via metadata ]
                          [ Runner: starts agent in live mode w/ Together gemma ]
                          [ Runner: completes setup wizard, creates locale user ]
                          [ Runner: submits 9 questions sequentially, shared channel ]
                          [ Runner: writes results.jsonl + summary.json ]
                                          ↓
                          [ Workflow: compute SHAs, write manifest_signed.json ]
                          [ Workflow: actions/attest-build-provenance ]
                          [ Workflow: upload artifact w/ tuple-name ]
                                          ↓
                          [ safety.ciris.ai: poll GH Actions API, fetch latest,
                            verify both signatures, present to scorers ]
```

---

## 7. What this loop is NOT

Explicit scope boundaries to forestall scope creep:

- **Not a scoring system.** Scoring is human work on safety.ciris.ai
  per `MISSION.md` §3.4. The CI loop produces signed evidence; the
  scoring layer reads it.
- **Not a regression detector.** Comparing this week's results to last
  week's is downstream of the artifact. Cap the loop's job at
  "produce verifiable signed evidence"; let downstream do the diff.
- **Not a contributor sandbox.** Contributors submit Contributions to
  the federation chain (per `SCHEMA.md` §4), not to this CI loop. The
  loop only runs *canonical*, voted-in batteries (per `SCHEMA.md` §13).
- **Not an agent-side change.** Zero modifications to the canonical
  agent runtime. All work is in qa_runner + workflow + module
  metadata. The agent runs unchanged.

---

## 8. Migration to the CIRISNodeCore crate

When the rust crate goes `[Impl]`:

1. This FSD moves with `cirisnodecore/` to the standalone repo.
2. The signing model (§3) doesn't change — per-response audit anchors
   are CIRIS agent state regardless of which CI runs the loop.
3. The bundle-level attestation step (§3.2) moves to the crate repo's
   CI, signing artifacts on the crate side.
4. The artifact-naming tuple (§2) stays identical, modulo the workflow
   path in `ci_provenance` pointing at the new repo's workflow file.

safety.ciris.ai's query path (§4) updates to look at the crate repo's
artifacts instead of CIRISAgent's. The verification logic is unchanged.

---

## 9. Open questions

1. **Freshness window default**: 7 days proposed. Calibrate against
   actual usage: how often do scorers re-query? If safety.ciris.ai
   always uses cached results between weekly cron runs, 7 days is
   right. If scorers want fresher data on-demand, drop to 1-3 days.

2. **Artifact retention**: GH Actions caps at 400 days (free tier).
   This loop's artifacts are also written to the federation persistence
   chain (eventually); the GH copy is the convenience-cache layer. For
   the pilot phase, 90 days matches `memory-benchmark.yml`.

3. **Cross-tuple aggregation**: a future "compare this week vs last
   week" workflow downstream would query multiple artifacts and diff
   them. Not in scope here, but the tuple-naming makes it
   straightforward: just iterate the artifact list with prefix
   `safety-battery-{lang}-{domain}-v{battery_version}`.

4. **Audit-anchor resolution**: the JSONL captures `agent_task_id`; the
   audit-chain entry is queryable via `/v1/audit/entries/{task_id}`. If
   the audit query has latency at scale, consider snapshotting the
   audit entry content directly into `manifest_signed.json` per
   response — bigger bundle, fully self-contained.

5. **template_id discovery**: today the runner hardcodes `default`. A
   future improvement: read the agent's actual loaded template post-
   bootstrap so the artifact name reflects what was actually used, not
   what was requested. (`/v1/system/identity` exposes this.)

---

*This document is iterative. v1.0 is the first impl-ready spec; later
revisions track operational evidence from pilot runs against the 14
canonical mental-health batteries.*
