# Trace capture for research

Signed CEG traces from a live model run, at three detail levels.

## Isolated (recommended when sharing a box)

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
| `OUT_DIR` | `/out` | |

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
