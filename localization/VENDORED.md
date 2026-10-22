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

**Patched** files: the `de`, `hi`, `sw`, `ko`, `tr` and `zh` glossaries, by
`localization/patches/wise_authority_term.diff`. They rendered Wise Authority as
"human advisor" (de, hi, sw, and zh in its example and usage note), "person in charge" (ko) or a slash pair (tr); the
Constitution 1.3 texts and Eric's ruling (2026-10-15) use "Wise Authority"
(Bilge Otorite in tr), and the pipeline injects glossary terms as binding, so
every new string inherited the wrong term. The same fix is upstream as
CIRISClient#237; drop the patch on the next re-vendor once it lands there. A patched
entry keeps the upstream digest and records the sha256 of the patched result; an
edit that isn't declared that way fails the check.

**Derived** files are ours and adapted for this repo. The record keeps their
upstream digest for provenance only, so `--upstream` can report when the source
moves. They are not drift-checked.

| Here | Derived from | What changed |
|---|---|---|
| `.github/workflows/i18n-lane.yml` | same path | No CIRISServer `.emitters` checkout and no client bundle mirrors (the agent has neither). Adds a `target` input (`accord` / `ui`) and Accord inputs. The client's strict gate is replaced by this check plus `accord_localize.py --verify` (Accord) or `tools/dev/check_localization_sync.py` (UI). The vendoring digest is checked, never re-recorded. Inputs reach the shell through env, via `localization/run_lane.sh`. **Sharded** (agent-only): a `plan` job (whole-run dry-run, so `--max-keys` still bounds the run, plus the locale assignment), a `shard` matrix (`shards` input, default 7 = 4 locales each, `fail-fast: false`, read-only token, never commits), and one `collect` job that refuses foreign locale files, gates the combined tree, merges the reports and commits once. The commit additionally waits for the gate to pass. An `extra_tm` input (default on, Accord only) adds read-only checkouts of CIRISAI/ciris-website and CIRISAI/CIRISClient as `--extra-tm` anchor corpora: `plan` resolves each default branch's commit ONCE and every shard checks out exactly those SHAs (plan outputs); the SHAs go into the step summary and, via `collect`, the commit message. |
| `.github/workflows/i18n-{translate,evaluate,repair}.yml` | same paths | Same `workflow_dispatch` callers, same `i18n-write-<ref>` one-writer concurrency group. They add the agent inputs, and `accord_units` defaults to one unit (`section0`). `mode` offers `fast` only (see "Local divergences"). They also take `shards`. |
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
- `localization/lane_shards.py` is the shard bookkeeping the lane's `plan`,
  `shard` and `collect` jobs share: the deterministic round-robin assignment
  over the manifest's 28 locales, the closed list of files each locale owns,
  `pack` (a shard uploads only its own locale files, its report, log and exit
  status) and `collect` (recompute the assignment; refuse a shard WHOLE if its
  artifact holds a file outside its locales, a symlink, or a report entry for
  another locale; copy the rest; merge the MQM reports; sum the spend parsed
  from each shard's `Spend.report` lines into `_lane.spend`).
- `localization/lane_backoff.py` wraps the vendored `localize.call_model`
  (module attribute, looked up at call time) with retry-in-place on
  402/408/429/5xx/529, exponential backoff with jitter, honouring
  `Retry-After`. Concurrent shards share one OpenRouter key, and OpenRouter
  pre-authorizes `max_tokens x price` per call, so 402 and 429 appear under
  parallel load. Unwrapped, the vendored code reads any exception as a dead
  rung: it escalates, marks the key unreviewed, or fails it closed. A 402 gets
  3 attempts, others 6 (`LOCALIZE_BACKOFF_*`). Anything else is re-raised
  unchanged, so escalation and fail-closed behave exactly as upstream.
  `accord_localize.install` installs it. For `TARGET=ui`, `run_lane.sh` runs
  `lane_backoff.py`, which is `localize.py`'s own CLI with the wrapper
  installed.

## Local divergences

Behaviour this repo changes without editing a vendored file. Each one should go
upstream to CIRISClient, then be removed here on the next re-vendor.

- **`--mode batch` is refused** (2026-10-14). The vendored `call_model` sends
  rung 0 as `<model>:batch` to OpenRouter's `/chat/completions`. OpenRouter
  serves `:batch` slugs only through its async batch adapters and answers the
  chat endpoint with HTTP 404 ("cannot be used with the chat/completions
  endpoint (adapter AnthropicBatchAdapter)"). This is true for every `:batch`
  slug, not one model: `anthropic/claude-sonnet-5:batch`,
  `google/gemini-3.7-flash:batch` and `openai/gpt-5.1:batch` all 404, while the
  plain ids answer. In run 38598155352 rung 0 died for all 28 locales, every
  key fell to a higher rung at full price, and `Spend.report(batch=True)`
  still halved every line: it reported ~$1.82 for ~$3.64 of calls. The
  refusal lives in `accord_localize.py` (`refuse_batch_mode`) and
  `run_lane.sh` (both targets), and the workflows offer `mode: fast` only.
  Upstream fix: drop the suffix on the chat path, or submit real batch jobs,
  and halve only the calls that were batched.
- **The drafting rung is `meta/muse-spark-1.3`** for accord runs on
  OpenRouter (2026-10-14, Eric's ruling: "move to muse for that leg, better to
  get off the claude family since you cover it inherently when you review").
  The vendored rung 0 is `anthropic/claude-sonnet-5`. `install()` in
  `accord_localize.py` replaces rung 0 only (`ACCORD_DRAFTER`). The repair rungs
  (`google/gemini-3.7-flash`, then `anthropic/claude-opus-5`) and the judge
  (`openai/gpt-5.1`) are the vendored ones. It also merges muse's price,
  $1.25 / $4.25 per MTok from OpenRouter's model list, into `PRICE`
  (`ACCORD_PRICE`). An explicit `LOCALIZE_LADDER` still wins. UI-target runs
  (`localize.py` directly) keep the vendored ladder. In the 2026-10-14 trial
  (18 hard keys across am/ha/yo/my/sw/es), muse-spark-1.3 passed 16, the best
  of nine models, at $0.13 against Sonnet 5's $0.32. The vendored
  `_openrouter_call` sends no `reasoning` setting, so muse reasons at its
  default effort, and its output token count includes that reasoning.
  Upstream fix: make rung 0 configurable per target, or adopt the rung.
- **Glossary rows for accord runs** (2026-10-14), set through hooks on the
  vendored `glossary` module (`terms`, `relevant`). The glossary files stay
  verbatim.
  - *constitution_ethics only:* the live `Ethics` row is dropped
    (`CONSTITUTION_ETHICS_GLOSSARY_DROP`). In every glossary that has it, it is
    the pipeline-stage label for the conscience step ("Conscience check"), not
    the word. Sent with this text, it made am render "ethics text" as
    "conscience text" (ህሊና ጽሑፍ) in every trial model, and the judge passed
    it. It also failed every yo draft for not writing the label. One row,
    `ethics text`, pins the document's own name per locale
    (`ETHICS_TEXT_RENDERINGS`). Each rendering is taken from that locale's
    accepted 1.3 output, or from the trial for the locales batch 1 withheld.
    The derivation of each rendering is in the code comment.
  - *constitution_ethics only:* the shipped 1.2b corpus is the authority for
    principle names (Eric's ruling, 2026-10-14). Group 1 of the 1.3 run
    (38627954361) rejected 123 line-locale pairs. Most of the de and th
    rejections were glossary-against-corpus conflicts: de pinned
    `Resilience` as "Widerstandsfähigkeit" and `Non-maleficence` as
    "Nicht-Schaden", which the 1.2b corpus never writes (it writes
    "Resilienz" 14/14 and "Schadensvermeidung" 12/12). th pinned `Integrity`
    and `Resilience` to words its corpus does not use for them. Every draft
    broke either the glossary or its own anchor, and the judge could always
    cite the other. Four tables in `accord_localize.py` fix this:
    - `CONSTITUTION_ETHICS_GLOSSARY_FIX` corrects 30 rows in 17 locales to the
      corpus's majority rendering. Each row has its count and source line in
      the code comment.
    - `CONSTITUTION_ETHICS_GLOSSARY_REMOVE` holds the rows with no 1.2b
      majority (te `Flourishing`, de `Reasoning`). They are not sent.
    - `english_renderings`, with the allow-lists `ENGLISH_RENDERING_KEPT*`,
      drops every row whose rendering is its own English. The exceptions are
      acronyms, proper names and identifiers, plus words the 1.2b corpus
      writes the same way (de `Agent`, fr `Service`, it `Wise Authority`, …).
      This is the ciris-website lesson: such a row canonizes leftover English.
      fr pinned `Wise Authority` as itself, while its corpus writes
      "Autorité Sage" (13 to 2), so that row is corrected instead.
    - `Wise Authority` follows Eric's second ruling ("Wise Authority not
      human advisor", 2026-10-14). Each locale gets its 1.2b majority
      rendering once the "human advisor" forms (de, hi, sw) and ko's 담당자
      are left out. That gives English for de, hi, id, ko and ur, which
      their corpus keeps, and "Bilge Otorite" for tr. sw has no other
      rendering, so its row is not sent. The prose bullets that tell hi, sw,
      ko and zh to say "human advisor" are not sent either
      (`HUMAN_ADVISOR_PROSE`, `accord_guidance`).
    - The `Ethics Check` stage label (`CONSTITUTION_ETHICS_GLOSSARY_DROP`)
      and the Version History rows ("1.0 -> 2026-03-27", `VERSION_ROW`) are
      dropped.

    UI runs, and Accord runs of the `accord` stem, send the vendored rows
    unchanged.
  - *every accord run:* the yo `Ethics` rendering is re-cased from the table's
    `ÌWÀ RERE` to the corpus's `ìwà rere` (`GLOSSARY_RECASE`), so it can sit
    inside a phrase.
  - *every accord run:* a term that occurs only inside a longer matched term
    is not sent (`drop_contained`, ported from the ciris-website copy of
    `glossary.py`, where it is a local patch).

  Upstream fix: fix `Ethics`' Context use (a UI label is not a prose term)
  and the yo casing in the glossaries, and take `drop_contained` into
  `glossary.relevant`. Align the principle-name rows with the shipped corpus,
  stop parsing Version History rows as terms, and drop or justify every row
  whose rendering is its own English.

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
