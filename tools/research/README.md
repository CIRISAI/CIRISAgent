# Trace capture for research

Signed CEG traces from a live model run, at three detail levels.

## Isolated (recommended when sharing a box)

Published to GHCR with every release — pull a pinned image rather than building
from a working tree:

```bash
docker run --rm \
  -e API_KEY=sk-... \
  -v "$PWD/traces:/out" \
  ghcr.io/cirisai/ciris-research-capture:latest
```

Or build locally from source:

```bash
cd docker
API_KEY=sk-... docker compose -f docker-compose.research.yml run --rm capture
```

Container-local database, logs and port. Nothing is shared with development
except `docker/research-traces/`, mounted read-write. Two people can run at once.

## Direct

```bash
API_KEY=sk-... ./tools/research/capture_traces.sh
```

## Knobs

| var | default | notes |
|---|---|---|
| `API_KEY` / `API_KEY_FILE` | — | **required** |
| `PROVIDER` | `openrouter` | `openrouter` `together` `groq` `openai` `deepinfra` |
| `MODEL` | `meta-llama/llama-4-scout` | **case-sensitive** — Together lists both `google/gemma-4-31B-it` and `pearl-ai/gemma-4-31b-it` |
| `LANGUAGES` | `en` | comma-separated |
| `QUESTIONS_FILE` | built-in corpus | container path, e.g. `/questions/mine.json` |
| `CONCURRENCY` | `1` | |
| `BASE_URL` | per provider | override for anything unlisted |
| `OVERRIDES` | none | path to a prompt-override manifest — see below |
| `OUT_DIR` | `/out` | |

## Prompt overrides

`OVERRIDES=/path/manifest.json` applies research-bound prompt replacements
through the audited facility, so the run records having been manipulated. The
manifest is validated **before** the provider preflight, with the same loader
the agent uses at startup — a manifest the agent would refuse costs ~8 seconds
here instead of ten minutes and a "Server failed to start".

Required fields: `manifest_version`, `experiment_id`, `condition`, `mode`,
`residue_digest`.

`residue_digest` is the one you cannot write from memory. It pins the inline
English action doctrine that overrides do **not** cover — the ASPDMA user
message, the DEFER policy, the identity blocks, the formatters — which every
arm shares, so a mid-campaign change to it is a confound. It is a hash over the
source tree, so it is specific to the commit you are running:

```bash
# the value for this tree
python3 -m ciris_engine.logic.utils.research_overrides digest

# a complete strict manifest, every value a visible REPLACE:: marker
python3 -m ciris_engine.logic.utils.research_overrides skeleton > manifest.json

# same, pre-filled with the CURRENT live values — for a surgical change
python3 -m ciris_engine.logic.utils.research_overrides baseline > manifest.json

# check before you run
python3 -m ciris_engine.logic.utils.research_overrides validate manifest.json
```

`mode: strict` demands **totality**: all ~97 reachable keys across the five
namespaces, or the manifest is refused. That is deliberate and is not going to
be relaxed. Partial replacement leaves CIRIS text inside a supposedly non-CIRIS
arm, and a run that applied half its overrides and reported clean is the exact
result this facility exists to make impossible. Use `mode: additive` for a
pilot — additive is recorded in the trace, so it can never later be read as a
total replacement.

Running via the **Research Trace Capture** workflow instead of locally: the
`Instrument` step summary prints that run's `residue_digest`, ready to paste,
and a rejected manifest fails at the staging step with the cause and the
remedy — before the capture starts.

## Output

```
$OUT_DIR/default/ceg-seal-<trace_id>.json           generic
$OUT_DIR/accord_detailed/ceg-seal-<trace_id>.json   + actionable lists
$OUT_DIR/accord_full/ceg-seal-<trace_id>.json       + raw prompts/completions
```

Each file is the CEG carrier **as it would ship**: the full
`federation_attestations` row, all 22 columns, including
`scrub_signature_classical`, `scrub_signature_pqc`, `original_content_hash`.
Byte columns are hex-encoded as `{"__hex__": "..."}`. Written on **seal**, so an
unreachable canonical does not cost you the corpus.

```python
import json
d = json.load(open("ceg-seal-<id>.json"))
d["signed_rows"]                              # PQC-signed count
d["ceg_rows"][0]["attestation_envelope"]      # the wire envelope
d["ceg_rows"][0]["scrub_signature_pqc"]       # importable into the mesh
```

## Exit codes

| code | meaning |
|---|---|
| 0 | ran, traces captured |
| 2 | no API key / unknown provider |
| 3 | preflight failed — names the cause (401 bad key · 402 valid key, no credit · 404 model case · 429 rate limit) |
| 4 | **ran but captured nothing** |
| 5 | override manifest missing or refused — the agent would not have started on it |

Exit 4 exists because the failure it catches is silent: a run once reported
`Success Rate 100.0%` while writing zero trace files, and anything reading that
directory would have computed over an empty set and called it clean. A capture
run with no captures is a failed run.

## If a run captures nothing

Every path logs its verdict — grep the adapter log for `Local-copy` and
`CEG seal`. You will get one of: `Local-copy enabled: <dir>`,
`Local-copy OFF`, `CEG seal teed: <file> — N rows, M signed`,
`CEG seal NOT teed (no local_copy_dir)`, or
`CEG seal teed NOTHING: no carrier row matches trace_id=...` (a source-side
defect, not a capture one).

## Notes

**Building on a host where buildkit's DNS fails.** Some hosts resolve
`registry-1.docker.io` fine but buildkit's network does not
(`i/o timeout ... on 10.19.16.1:53`). `docker pull python:3.12-slim` then
`DOCKER_BUILDKIT=0 docker build -f docker/Dockerfile.research -t ciris-research-capture:local .`
works, because the legacy builder resolves the base locally. Pulling from GHCR
avoids the problem entirely.

**Verified end-to-end** at 2.9.7: image builds clean, container run returns
exit 0 with 6 traces across generic/detailed/full_traces, all 6 PQC-signed,
written through the volume mount to the host. Guards verified in-container:
exit 2 with no key, exit 3 on a bad key naming the cause.
