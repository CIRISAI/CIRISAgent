# Localization CLAUDE.md

Instructions for rapidly expanding CIRIS language coverage while maintaining minimum viable linguistic rigor.

> **Two layers, two different concerns.** This file documents the **per-locale translation** workflow — rendering CIRIS source material (UI strings, ACCORD, guides, DMA prompts, glossaries) into each of the 29 supported languages so users can interact with the agent in their own language. That is **translation**.
>
> The complementary layer is **polyglot encoding** — concept transmission via *epistemic triangulation across multiple traditions' densest encodings of a concept*, loaded universally regardless of user locale. That layer is documented at `ciris_engine/data/localized/polyglot/CLAUDE.md` and exemplified by `polyglot_accord.txt`. If you are working on a master canon prompt or a load-bearing claim that is at risk of being received as a single tradition's framing rather than a cross-traditional truth, that is polyglot territory, not translation territory.
>
> The two layers complement each other: the agent reads polyglot canon at the system-prompt layer and produces output in the user's locale at the response layer. New DMA prompts and conscience shards may need both — a polyglot master plus per-locale wrappers. See the polyglot CLAUDE.md for when each applies.

## Translating: use the vendored pipeline, not agent fan-outs

Translation work goes through the CIRISClient pipeline vendored here
(`localize.py`; provenance in `VENDORED.md`). Its lanes run translate, then
evaluate (MQM spans from a different-family judge), then repair. Sub-agent
fan-outs (one agent per file or per language family, Haiku for volume) are how
the first 29 languages were bootstrapped. They produced word-salad in 5 of 28
locales that structural checks missed, and this file no longer describes them.

```bash
# 1.3 is renamed: constitution_ethics_1.3_<lang>.txt, TM from the shipped accord_1.2b_<lang>.txt
E13='--version 1.3 --stem constitution_ethics --tm-version 1.2b --tm-stem accord'
python3 localization/accord_localize.py $E13 --segments                    # plan + run size
python3 localization/accord_localize.py $E13 --check                       # what is missing
python3 localization/accord_localize.py $E13 --units section0 --lane translate --dry-run
# + website / client / agent-UI strings as terminology anchors (never values); CI checks these out pinned
python3 localization/accord_localize.py $E13 --extra-tm ~/ciris-website --extra-tm ~/CIRISClient --extra-tm . \
    --units section0 --lane translate --dry-run
python3 localization/localize.py --check                                     # UI/prompt bundle (LOCALIZE_TARGET=ui)
python3 localization/prompt_localize.py --check                              # DMA prompt templates still in English, per locale
python3 localization/prompt_localize.py --lane translate --keys 'rsaspdma.*' --dry-run
```

**A new DMA prompt** (`ciris_engine/logic/dma/prompts/<name>.yml`): commit an
English copy in each `localized/<lang>/` folder, then dispatch `i18n translate`
with `target: prompts` and `keys: <name>.*`. A field still byte-identical to
English counts as missing, so the lane picks it up and the chain-localization
tests fail until it has. **A rewritten field** already has an (old) translation
in each locale, so it is not missing: dispatch with the exact key and
`overwrite: true`.

What each part of the ratchet rests on, and where the prior art says it is weak: `localization/PRIOR_ART.md`.

Real runs spend tokens. They go through the `i18n translate|evaluate|repair`
workflows (dispatch only, one writer at a time). Never hand-edit vendored files:
`tools/dev/check_localize_vendoring.py` fails on any drift.

## Mission Alignment

CIRIS Meta-Goal M-1: *"Promote sustainable adaptive coherence enabling diverse sentient beings to pursue their own flourishing in justice and wonder."*

Localization is not translation. It is extending ethical agency across linguistic boundaries. Every language added means another population can interact with an AI system that reasons about ethics *in their own conceptual framework* rather than through a colonial-default English filter. The ACCORD's invocation of Ubuntu philosophy ("I am because we are") demands this: coherence is not coherent if it only works in one language.

**Priority principle**: Languages are ordered by *need*, not by market size. A Hausa speaker in rural Niger has more to gain from ethical AI than an English speaker with 50 alternatives. This is Mission Driven Development applied to localization.

## Current State (checked against the tree 2026-11-11)

This section replaces a snapshot dated 2026-04-08 that had drifted badly. Each
line names where to re-check it, because this one will drift too.

- **29 languages**, source of truth `ciris_engine/data/localized/manifest.json`:
  am, ar, bn, de, en, es, fa, fr, ha, hi, id, it, ja, ko, mr, my, pa, pt, ru,
  sw, ta, te, th, tr, uk, ur, vi, yo, zh. There is no `localization/manifest.json`
  and there must not be one: any `*.json` directly in `localization/` hijacks
  the agent's string loader (see `VENDORED.md`).
- **In production** on the app stores. User feedback on translation quality is
  reported positive, most of it from Amharic speakers (maintainer, 2026-11-11).
  It is not recorded per locale in this repository.
- **Every language has a language primer** (`prompts.language_guidance` in
  `ciris_engine/data/localized/<lang>.json`), not only Amharic. en, es, fr, it
  and pt carry it split into numbered single-class parts; the other 24 carry
  one authored block of roughly 4 to 17 KB. Doctrine that reads the same in
  every language has moved to `prompts.universal_guidance`, which the pipeline
  translates. See `LANGUAGE_GUIDANCE_PART_KEYS` in
  `ciris_engine/logic/utils/localization.py`.
- **Every language has a safety battery**: `tests/safety/<language>_mental_health/`
  holds the v4 question arc, the scoring rubric and the machine-applicable
  `canonical_universal_criteria.json`, for all 29.
- **The batteries run.** `.github/workflows/safety-battery.yml` (weekly, and on
  dispatch per language) captures responses and has an interpreter agent apply
  the criteria. `qa_reports/safety_interpret/` holds about 300 interpreted
  runs covering all 29 locales, the latest dated 2026-10-15; per locale that
  is between 7 (vi) and 22 (am). What they found is in
  `tests/safety/FINDINGS_LEDGER.md`; what was changed in response is in
  `tests/safety/GUIDANCE_FIXES.md`; the process is `FSD/SAFETY_GUIDANCE_PROCESS.md`.
  `qa_reports/safety_sweeps.json` is an older ledger (30 sweeps, May 2026) and
  its "never evaluated" notes are stale.
- **Rules are crowdsourced, verdicts are machined.** `tests/safety/` is merged
  consensus state; changes are proposed through the federation flow in
  `tests/safety/README.md`, not edited directly.
- **Translation runs in CI**, through the vendored pipeline: `i18n translate`,
  `i18n evaluate`, `i18n repair` (dispatch only), with targets `accord`, `ui`
  and `prompts`.

## Three corpora, run independently, read by each other

CIRIS text is translated in three repositories. Each runs its own localization
on its own schedule, with its own review, and none waits for another.

| Corpus | Repository | What it holds |
|---|---|---|
| Agent | `CIRISAI/CIRISAgent` (this one) | Agent and API strings, language primers, ethics text, guide, DMA and conscience prompts |
| Client | `CIRISAI/CIRISClient` | The apps' interface strings (Android, iOS, desktop share one bundle) |
| Website | `CIRISAI/ciris-website` | Site dictionaries and chrome |

They are not merged and there is no shared bundle. They are kept coherent by
reading each other's shipped translations as **analysis and terminology
anchors**: when one corpus translates or reviews a string, the other corpora's
rendering of the same terms in that language is in front of the translator and
the reviewer. An anchor is never copied in as a value.

What this repository does, which you can verify here:

- `accord_localize.EXTRA_LAYOUTS` recognises a website checkout, a client
  checkout and this repository's own UI bundle, ranked in that order.
- The lanes check the website and the client out read-only at their
  default-branch commit, pinned once per run, for the `accord` and `prompts`
  targets, and put both commits in the commit message (`i18n-lane.yml`,
  `extra_tm`).
- The other corpus's own review is respected: a string its MQM review flagged
  critical or major, a file whose status is rejected, a value left in English
  or in the wrong script, is not used as an anchor (`_flagged_keys`,
  `_file_status`, `_usable`).

In the other direction, the client and the website include this repository's
corpus in their own analysis the same way (maintainer, 2026-11-11). That side
lives in those repositories and is not visible from here; the website carries
its own `localization/localize.py`, `glossary.py` and `SITE_NOTES.md`.

The pipeline code itself flows one way: `localize.py`, `glossary.py`, the
translation guide and the 28 glossaries are vendored byte-identical from
CIRISClient (`VENDORED.md`). A fix to the pipeline or to a glossary goes
upstream to the client and comes back on the next re-vendor.

Consequences worth knowing:

- **A correction in one corpus does not propagate.** If a native speaker fixes
  a term in the client, the agent's value is unchanged until its own lane runs
  and sees the fix as an anchor. The glossary is the only thing all three are
  bound by.
- **Agreement between corpora is evidence, not proof.** Three pipelines of the
  same lineage, with overlapping models, can agree on the same mistake.
- **This repository has two glossary sets.** `localization/glossaries/` (from
  the client, read by the pipeline) and `docs/localization/glossaries/` (the
  agent's originals, read only by the completeness test) differ in all 29
  files.

## What a language consists of

| Component | Location | Checked by |
|---|---|---|
| UI and agent strings | `ciris_engine/data/localized/<lang>.json` (about 6,000 leaf keys in en) | `test_localization_completeness.py`; `tools/dev/check_localization_integrity.py` |
| Language primer | `prompts.language_guidance` in that file (authored per language, excluded from translation) | the safety battery |
| Ethics text | `ciris_engine/data/localized/constitution_ethics_1.3_<lang>.txt` (`accord_1.2b_<lang>.txt` kept as the research control arm) | `accord_localize.py --verify`; hash pins |
| Comprehensive guide | `ciris_engine/data/localized/CIRIS_COMPREHENSIVE_GUIDE_<lang>.txt` | completeness test |
| DMA prompts | `ciris_engine/logic/dma/prompts/localized/<lang>/*.yml` (10 templates) | chain-localization tests; `test_prompt_formatting.py`; `prompt_localize.py --verify` |
| Conscience prompts | `ciris_engine/logic/conscience/prompts/localized/<lang>/*.yml` (3; the optimization veto is polyglot and universal) | chain-localization tests |
| Crisis resources | `ciris_engine/data/localized/crisis_resources_<lang>.json` | `test_crisis_block_in_every_dma_1248.py` |
| Glossary | `localization/glossaries/<lang>_glossary.md` (vendored from CIRISClient; what the pipeline reads). `docs/localization/glossaries/` is the older agent-side copy | vendoring check |
| Safety battery | `tests/safety/<language>_mental_health/` | `safety-battery.yml` |

Registration is the manifest entry alone. The tests read the language list from
the manifest (`get_supported_languages`); there are no per-test lists to edit.
The app's language list lives in CIRISClient, not in this repository.

## Priority

Languages are ordered by need, not market size. The original roadmap (three
tiers, 12 languages added after the first 17) is complete. Hardening effort
still follows the same order: the languages the base models know least get the
most primer work and the most battery runs.

### Base-model support, worst first

Ranked by inverse Qwen support. Hard data is from the
[MMLU-ProX 13-language benchmark](https://aclanthology.org/2025.emnlp-main.79.pdf)
where given; the rest is inferred. This table is from early 2026 and concerns
one model family. Production now also runs other models (root `CLAUDE.md`,
"Live LLM model matrix"), so read it as the reason for the ordering, not as
current measurement.

| Tier | Languages | Signal |
|---|---|---|
| 0, outside Qwen3's 119 languages | am, ha, yo | Production-observed transliteration and sense-collision errors in am; ha and yo by absence of training data |
| 1, listed but low-resource | sw (40.1%, worst of 13 tested), my, mr, pa, te, ta | |
| 2 | ur, bn (57.6%), fa, hi (58.0%), th (60.1%), vi, id, uk, tr | |
| 3 | ar (62.1%), ko (62.1%), ja (63.4%), ru, it | |
| 4 | de (65.9%), pt (66.6%), es (66.5%), fr (67.1%), zh (65.9%) | |
| 5 | en (70.3%) | |

## Language primers

Each `prompts.language_guidance` is injected as a system message into every
DMA, conscience and action-selection call
(`ciris_engine/logic/utils/localization.py::get_language_guidance`). It began as
a reactive fix for Amharic in 2.7.6, on the rule "populate only on observed
failure". That rule no longer describes the tree: all 29 are populated.

What a primer carries, from the Amharic original:

1. Top-line operating rules: register, script, numerals, mark uncertainty
   instead of transliterating, keep CIRIS identifiers in English.
2. Terminology with NOT-X-because-Y pairs for the terms that collide.
3. The wire-protocol terms: the ten action verbs and six cognitive states, with
   the reminder that JSON values stay in English.
4. Compact prescriptive grammar: formal imperatives, modals, plurals.
5. Cross-cluster disambiguation for adjacent clinical conditions.
6. A closing reminder of the agent's role.

Framing is prescriptive ("respect these conventions"), not descriptive.
Descriptive context turns into template mimicry (Walia-LLM, Azime et al.,
EMNLP 2024).

A primer is authored for its language. It is not a translation of the English
one and the pipeline does not translate it (`UI_EXCLUDED_PREFIXES`). A change
to one is tested by the battery for that language and recorded in
`GUIDANCE_FIXES.md`. Open per-locale work is tracked in `FINDINGS_LEDGER.md`
(section 5 lists which locales still lack which fix).

## What is and is not guaranteed

Guaranteed, by gates that fail closed: terminology from the glossary;
structural completeness; placeholders, doubled braces and `str.format`
validity; the right script; hard-fail safety criteria per language.

Not guaranteed: native fluency; dialect coverage (Arabic is MSA, Chinese is
Simplified); cultural adaptation of examples; legal review per jurisdiction.

Machine-reviewed is not native-reviewed. `ciris.ai/crowdsourcing-alignment` is
the route for a native speaker to propose an edit; structured native review of
judgment calls is still being built.

## Pitfalls that have actually occurred

| Pitfall | What catches it |
|---|---|
| JSON braces not doubled in a DMA prompt | `test_prompt_formatting.py`; `prompt_localize.prompt_problems` |
| A placeholder doubled or translated (the prompt silently loses a substitution) | `prompt_localize.py --verify`, which lists 28 standing cases as of 2026-11-11 |
| A locale file left in English | chain-localization tests (`tests/ciris_engine/logic/utils/test_<lang>_chain_localization.py`) |
| Another language's text in a locale (Russian in uk, Bengali in pa) | `check_localization_integrity.py` |
| Word-salad that parses | only the evaluate lane and native review |
| A JSON file placed in `localization/` | the vendoring check; every string lookup returns empty until it is removed |

## Commands

```bash
pytest tests/ciris_engine/logic/utils/test_localization_completeness.py -v
pytest tests/ciris_engine/logic/utils/test_am_chain_localization.py -v     # one per language
pytest tests/ciris_engine/logic/dma/test_prompt_formatting.py -v
python3 tools/dev/check_localization_integrity.py                           # value integrity of the string bundle
python3 tools/dev/check_localize_vendoring.py
python3 localization/prompt_localize.py --verify                            # DMA prompt structure
```

## File reference

| What | Where |
|---|---|
| Pipeline provenance and adapters | `localization/VENDORED.md` |
| What the ratchet rests on | `localization/PRIOR_ART.md` |
| String loader, primer composition | `ciris_engine/logic/utils/localization.py` |
| Safety batteries, ledger, fixes | `tests/safety/` |
| Safety guidance design and process | `FSD/SAFETY_GUIDANCE.md`, `FSD/SAFETY_GUIDANCE_PROCESS.md` |
| Polyglot layer (not translation) | `ciris_engine/data/localized/polyglot/CLAUDE.md` |
| Early lessons (historical) | `docs/localization/LESSONS_LEARNED.md`, `docs/localization/README.md` |

---

*Localization is how Meta-Goal M-1 stops being aspirational and starts being operational across the world's linguistic diversity.*
