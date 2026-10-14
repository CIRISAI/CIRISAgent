# Vendored: the CIRISClient localization pipeline

CIRISAgent translates with **CIRISClient's** localization pipeline, not with
sub-agent fan-outs. The fan-outs produced word-salad in 5 of 28 locales that
structural validation could not see (JSON parsed, keys present, placeholders
matched). The pipeline answers that with an evaluate lane: MQM error spans from a
judge of a *different model family*, then repair, then re-review.

The machine-readable record is [`upstream/vendored.json`](upstream/vendored.json). The gate is
`python3 tools/dev/check_localize_vendoring.py` (pre-commit hook
`localize-vendoring`, plus the first and last steps of every i18n lane run).

**Keep JSON out of `localization/` itself.** The agent's string loader
(`_get_localization_dir`) uses `<CIRIS_HOME>/localization/` as THE bundle
directory as soon as that folder holds any `*.json`. In a dev checkout,
CIRIS_HOME is the repo root. That is why the record lives in `upstream/`. The
first cut of #1253 put it at the top level, and every `get_string` /
`language_guidance` read then came back empty. The vendoring check and
`tests/localization` now fail on any top-level JSON here.

Every adapter mode is read-only except a real lane run. `--check`,
`--dry-run`, `--glossary-report`, `--segments` and `--verify` stage into a
throwaway directory and never write `ciris_engine/data/localized` or the
committed stage. A test asserts this byte for byte.

## Upstream

| | |
|---|---|
| Repository | `CIRISAI/CIRISClient` |
| Commit | `e040ae76550d90039b6050706d65865ded6f77f4` (`origin/main`, 2026-10-08) |
| Vendored | 2026-10-13 |

## What is vendored, and how

**Verbatim** files are byte-identical to upstream at that commit. The record
holds each one's upstream path, git blob id and sha256. The check fails if any of
them differs, if one goes missing, or if an undeclared file shows up in a
vendored directory (`glossaries/`, `upstream/`).

| Here | Upstream |
|---|---|
| `localization/localize.py` | `localization/localize.py` |
| `localization/glossary.py` | `localization/glossary.py` |
| `localization/review_only.py` | `localization/review_only.py` |
| `localization/drive.sh` | `localization/drive.sh` |
| `localization/TRANSLATION_GUIDE.md` | `localization/TRANSLATION_GUIDE.md` |
| `localization/glossaries/*_glossary.md` (28 + `TEMPLATE`) | `localization/glossaries/` |
| `localization/upstream/check_localization_sync.py` | `client/tools/check_localization_sync.py` |

**Patched** files: none. No vendored file needed an edit. If one ever does, the
change goes in as a `kind: "patched"` entry: the patch file in the tree, the
upstream digest kept, and the sha256 of the patched result recorded. An edit
that isn't declared that way fails the check.

**Derived** files are ours and adapted for this repo. The record keeps their
upstream digest for provenance only, so `--upstream` can report when the source
moves. They are not drift-checked.

| Here | Derived from | What changed |
|---|---|---|
| `.github/workflows/i18n-lane.yml` | same path | No CIRISServer `.emitters` checkout and no client bundle mirrors (the agent has neither). Adds a `target` input (`accord` / `ui`) and Accord inputs. The client's strict gate is replaced by this check plus `accord_localize.py --verify` (Accord) or `tools/dev/check_localization_sync.py` (UI). The vendoring digest is checked, never re-recorded. Inputs reach the shell through env, via `localization/run_lane.sh`. An `extra_tm` input (default on, Accord only) adds read-only checkouts of CIRISAI/ciris-website and CIRISAI/CIRISClient, each pinned to its default branch's commit, as `--extra-tm` anchor corpora; the SHAs go into the step summary and the commit message. |
| `.github/workflows/i18n-{translate,evaluate,repair}.yml` | same paths | Same `workflow_dispatch` callers, same `i18n-write-<ref>` one-writer concurrency group. They add the agent inputs, and `accord_units` defaults to one unit (`section0`). |
| `tools/dev/check_localize_vendoring.py` | `packaging/check_vendoring.py` | Same per-file-digest pattern, applied to this record instead of a `client/` tree digest. |

Not vendored: `packaging/check_vendoring.py` itself (it hashes a `client/`
tree this repo doesn't have).

## Agent-owned adapters (not vendored)

These files let the vendored code run here unmodified. Each hook is a module
attribute that the vendored functions look up at call time.

- `localization/check_localization_sync.py` is a **shim**. `localize.py` does
  `import check_localization_sync as guard` with its own directory first on
  the path, so it resolves here. The shim loads the vendored gate from
  `upstream/` and re-exports its primitives unchanged: `flat_values`, the
  placeholder grammar, `manifest_languages`. It replaces only the bundle
  location:
  - `LOCALIZE_TARGET=ui` (the default) targets
    `ciris_engine/data/localized/{lang}.json`, a single copy, with
    `prompts.language_guidance` excluded. That subtree is a per-language
    primer, not a translation.
  - `LOCALIZE_TARGET=accord` targets the staged Accord bundle.
- `localization/accord_segments.py` segments the Accord into one key per
  non-blank line and reassembles it from skeleton + values. The round trip is
  lossless for the English source and for all 29 shipped locales.
- `localization/accord_localize.py` stages the Accord as a key bundle, seeds
  it from the translation memory, overrides the prompts, anchors, glossary
  row, structural rules and per-unit selection, runs the lanes, and writes
  complete locales back to `ciris_engine/data/localized/accord_<v>_<lang>.txt`.
  With `--extra-tm DIR` it also reads the website's, the client's and the
  agent UI's translated strings as extra terminology anchors (ranked after
  the accord TM, bounded per key and per request, never written as values).
  That is a replacement `anchors_for` hook, not an edit to `localize.py`.
- `localization/run_lane.sh` is the workflow entry point.

## Re-vendoring

```bash
python3 tools/dev/check_localize_vendoring.py --upstream ~/CIRISClient --ref origin/main   # what moved
python3 tools/dev/check_localize_vendoring.py --revendor ~/CIRISClient --ref origin/main   # pull + re-record
python3 tools/dev/check_localize_vendoring.py                                             # gate
```

`--revendor` rewrites the verbatim files and the record. It refuses while a
patched entry exists, because patches are re-applied by hand. For derived files
it only reports that upstream moved: merging those is a reviewed change. Then
run `pytest tests/localization`, because the adapters depend on vendored names
(`anchors_for`, `structural_problems`, `missing_by_language`, `translate_lane`,
`_repair_once`, `gloss.deprecated`, `SYSTEM_*`, `GUIDE_RULES`,
`_PLACEHOLDER_RULE`).

The vendored files are excluded from black, isort, trailing-whitespace,
end-of-file and line-ending fixers (`.pre-commit-config.yaml`, and
`[tool.black]` in `pyproject.toml` for Grace's `black .`). Reformatting them
would be a silent fork.

## What the output is, and is not

Every value the pipeline writes is `status: draft` /
`review_status: machine_reviewed`. Each reassembled Accord file says so in a
provenance line. The pipeline guarantees terminology consistency, structural
completeness, placeholder integrity and meaning preservation, as judged by an
independent MQM reviewer. It does not guarantee native fluency, and nothing it
writes may be described as native quality.
