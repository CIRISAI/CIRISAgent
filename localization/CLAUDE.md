# Localization CLAUDE.md

Instructions for rapidly expanding CIRIS language coverage while maintaining minimum viable linguistic rigor.

> **Two layers, two different concerns.** This file documents the **per-locale translation** workflow — rendering CIRIS source material (UI strings, ACCORD, guides, DMA prompts, glossaries) into each of the 29 supported languages so users can interact with the agent in their own language. That is **translation**.
>
> The complementary layer is **polyglot encoding** — concept transmission via *epistemic triangulation across multiple traditions' densest encodings of a concept*, loaded universally regardless of user locale. That layer is documented at `ciris_engine/data/localized/polyglot/CLAUDE.md` and exemplified by `polyglot_accord.txt`. If you are working on a master canon prompt or a load-bearing claim that is at risk of being received as a single tradition's framing rather than a cross-traditional truth, that is polyglot territory, not translation territory.
>
> The two layers complement each other: the agent reads polyglot canon at the system-prompt layer and produces output in the user's locale at the response layer. New DMA prompts and conscience shards may need both — a polyglot master plus per-locale wrappers. See the polyglot CLAUDE.md for when each applies.

## Mission Alignment

CIRIS Meta-Goal M-1: *"Promote sustainable adaptive coherence enabling diverse sentient beings to pursue their own flourishing in justice and wonder."*

Localization is not translation. It is extending ethical agency across linguistic boundaries. Every language added means another population can interact with an AI system that reasons about ethics *in their own conceptual framework* rather than through a colonial-default English filter. The ACCORD's invocation of Ubuntu philosophy ("I am because we are") demands this: coherence is not coherent if it only works in one language.

**Priority principle**: Languages are ordered by *need*, not by market size. A Hausa speaker in rural Niger has more to gain from ethical AI than an English speaker with 50 alternatives. This is Mission Driven Development applied to localization.

## Current State (2026-04-08)

- **29 languages**: am, ar, bn, de, en, es, fa, fr, ha, hi, id, it, ja, ko, mr, my, pa, pt, ru, sw, ta, te, th, tr, uk, ur, vi, yo, zh
- **Gross coverage**: ~72% of world population (deduplicated)
- **Need-adjusted coverage**: ~95%
- **All 29 languages complete**: glossary, JSON, DMA prompts (ACCORD and guide for Tier 1-2)

## What "Complete" Means

A language is complete when all 5 components exist and pass validation:

| Component | Location | Validation |
|-----------|----------|------------|
| 1. Glossary | `docs/localization/glossaries/{code}_glossary.md` | All sections filled, 3,000+ chars |
| 2. UI Strings | `localization/{code}.json` | 1,257 nested keys, valid JSON, no duplicates |
| 3. ACCORD | `ciris_engine/data/localized/accord_1.2b_{code}.txt` | Within 10% of English line count (~1,153 lines) |
| 4. Guide | `ciris_engine/data/localized/CIRIS_COMPREHENSIVE_GUIDE_{code}.md` | 80%+ of English line count |
| 5. DMA Prompts | `ciris_engine/logic/dma/prompts/localized/{code}/*.yml` | 6 files, valid YAML, `{{}}` escaping |

**Registration** (after all files created):
- `localization/manifest.json` — add language entry
- `ciris_engine/data/localized/manifest.json` — mirror entry
- `mobile/shared/.../SetupState.kt` — add to `SUPPORTED_LANGUAGES`
- `test_localization_completeness.py` — add code to 5 parameterized lists

## Expansion Priority Order

Based on composite scoring: speaker count, need weight (inverse income + inverse digital access), overlap with existing languages. See `manifest.json` `localization_roadmap` for full data.

### Tier 1 — ✅ COMPLETE
1. **Indonesian (id)** — 200M speakers, 4th largest country, low overlap, need 3.0
2. **Hausa (ha)** — 80M speakers, West Africa lingua franca, need 5.0 (highest)
3. **Persian (fa)** — 110M speakers, RTL, covers Iran + Afghanistan, need 3.0

### Tier 2 — ✅ COMPLETE
4. **Vietnamese (vi)** — 85M, no overlap, growing digital access
5. **Punjabi (pa)** — 150M, high overlap w/ Hindi/Urdu but fills Gurmukhi gap
6. **Telugu (te)** — 83M, distinct Dravidian script, India's 4th largest
7. **Tamil (ta)** — 85M, India + Sri Lanka + SE Asia

### Tier 3 — ✅ COMPLETE
8. **Marathi (mr)** — 83M, Devanagari script (leverage Hindi tooling)
9. **Thai (th)** — 61M, unique script
10. **Yoruba (yo)** — 45M, Nigeria, need 4.5
11. **Burmese (my)** — 43M, Myanmar, need 4.5
12. **Ukrainian (uk)** — 40M, distinct from Russian

**All tiers complete**: gross ~72%, need-adjusted ~95%.

## Rapid Expansion Workflow

Each language takes ~30-45 minutes using parallel agents. Follow this exact sequence:

### Phase 1: Glossary (1 agent, ~5 min)

Create glossary FIRST. This is non-negotiable — without it, terminology drifts across files.

```
Create glossary for {LANGUAGE} at docs/localization/glossaries/{CODE}_glossary.md.
Use docs/localization/glossaries/ur_glossary.md as the structural template.
Include all sections: Core Action Verbs (10), Core Concepts (9+), Technical Terms (8+),
Cognitive States (6), UI Labels, DMA-Specific Terms, Phrases, Cultural Considerations.
Technical terms (API, DMA, LLM, Agent) stay in English.
```

### Phase 2: JSON UI Strings (4-5 parallel agents, ~10 min)

Split by key prefix to avoid conflicts and token limits:

- **Agent 1**: `common_*, nav_*, screen_*, filter_*` (~80 keys)
- **Agent 2**: `setup_*, startup_*, status_*, processing_*` (~80 keys)
- **Agent 3**: `services_*, system_*, sessions_*, scheduler_*, runtime_*` (~120 keys)
- **Agent 4**: `adapter_*, audit_*, billing_*, config_*, consent_*, data_*` (~150 keys)
- **Agent 5**: `graph_*, logs_*, memory_*, telemetry_*, tickets_*, remaining` (~80 keys)

Each agent reads `en.json` for source, `{code}_glossary.md` for terminology, and edits `{code}.json`.

### Phase 3: ACCORD (2-3 parallel agents, ~10 min)

Split by section:
- **Agent 1**: Sections 0-3 (Introduction, Core Identity, Operations)
- **Agent 2**: Sections 4-6 (Obligations, Maturity, Creation Ethics)
- **Agent 3**: Sections 7-9 + Annexes (War Ethics, Sunset, Mathematics)

Preserve section headers in CAPS. Keep code blocks in English. Maintain the poetic-philosophical voice — this is a covenant, not a manual.

### Phase 4: DMA Prompts (2 parallel agents, ~10 min)

- **Agent 1**: `pdma_ethical.yml`, `csdma_common_sense.yml`, `idma.yml`
- **Agent 2**: `action_selection_pdma.yml`, `dsdma_base.yml`, `tsaspdma.yml`

**CRITICAL**: Escape all JSON braces as `{{` and `}}`. Python's `.format()` will break otherwise. This is the #1 recurring bug in localization work.

### Propagating ONE prompt change across all 28 locales (use language-family clustering)

When the English source for a single DMA prompt is rewritten (e.g. dsdma_base.yml in 2.7.4), don't fan out 28 individual agents — that wastes context and produces no efficiency gain over sequential. Instead spawn **9 parallel agents grouped by language family**, each handling 2–6 related languages serially. Family clustering exploits shared glossary patterns, shared script behaviour (RTL groups, CJK groups), and shared cultural framing for the same prompt — so an agent can re-use research across the languages it owns.

Canonical 9-cluster grouping for the 28 non-English locales:

| Cluster | Languages | Notes |
|---|---|---|
| 1. Romance + Germanic European | es, fr, it, pt, de | Latin script, similar register |
| 2. Slavic Cyrillic | ru, uk | Distinct languages, Cyrillic |
| 3. Indo-Aryan + Iranian | hi, mr, pa, ur, fa, bn | Devanagari / Gurmukhi / Persian / Bengali; ur+fa are RTL |
| 4. CJK East Asian | zh, ja, ko | Hanzi/kanji-based, no spaces |
| 5. SE Asian | th, vi, id, my | Diverse scripts (Thai, Latin, Burmese) |
| 6. Dravidian | ta, te | South Indian scripts |
| 7. Semitic + Ethiopic + Chadic | ar, am, ha | Arabic RTL, Ge'ez script, Hausa Latin/Ajami |
| 8. Sub-Saharan African (Niger-Congo) | sw, yo | Latin script, Bantu/Yoruba |
| 9. Turkic | tr | Latin, Turkish |

Each family-agent gets:
- The new English source content (or a path)
- Their assigned language codes
- Output paths under `ciris_engine/logic/dma/prompts/localized/{code}/`
- Required-token list (placeholders that must survive verbatim: `{domain_name}`, `{rules_summary_str}`, `{context_str}`, `{original_thought_content}` — single-brace; example JSON braces must be doubled `{{}}`)
- The instruction to keep JSON object keys ("domain", "domain_alignment", "flags", "reasoning") in English while translating string values

Use Haiku for these agents — sufficient for prompt-level translation and parallel-friendly. Validate each output by parsing the YAML and confirming the required-token set matches the English source.

### Phase 5: Comprehensive Guide (1-2 agents, ~10 min)

Translate `CIRIS_COMPREHENSIVE_GUIDE_en.md`. Target 80%+ of English line count. Keep markdown structure intact.

### Phase 6: Registration & Validation (1 agent, ~5 min)

1. Add to `localization/manifest.json` and `ciris_engine/data/localized/manifest.json`
2. Add to `SetupState.kt` `SUPPORTED_LANGUAGES`
3. Add to `test_localization_completeness.py` (5 parameterized locations)
4. Run: `pytest tests/ciris_engine/logic/utils/test_localization_completeness.py -v -k "{code}"`
5. Run: `pytest tests/ciris_engine/logic/dma/test_prompt_formatting.py -v`

## Minimum Viable Linguistic Rigor

We use auto-generated translations (Claude) with a "good enough for ethical reasoning, flagged for native review" standard. This is deliberate:

### What We Guarantee
- **Terminology consistency** — glossary-enforced canonical translations for all CIRIS-specific terms (ACCORD, Wise Authority, the 10 action verbs, 6 cognitive states)
- **Structural completeness** — all keys present, all files exist, all tests pass
- **Functional correctness** — DMA prompts parse without errors, JSON braces escaped, YAML valid
- **Meaning preservation** — ethical reasoning concepts translate to culturally appropriate equivalents, not word-for-word calques
- **RTL support** — Arabic, Urdu, Persian, Hausa (Ajami) properly flagged

### What We Do NOT Guarantee (Yet)
- **Native fluency** — translations are functional but may sound stilted to native speakers
- **Dialectal coverage** — Arabic covers MSA, not Egyptian/Levantine/Gulf variants; Chinese covers Simplified, not Traditional
- **Cultural localization** — metaphors, idioms, and examples are translated literally; cultural adaptation is a future pass
- **Legal compliance** — translations have not been reviewed for jurisdiction-specific requirements

### Review Status Lifecycle
```
draft → needs_native_review → reviewed → production
```

All auto-generated languages start at `draft` / `needs_native_review`. They are usable but should not be marketed as "native quality" until a native speaker reviews.

## Per-Language Guidance Blocks (`prompts.language_guidance`)

Beyond the core 5-component "is the language complete" deliverable above, each `localization/{code}.json` carries a **`prompts.language_guidance`** key that gets injected as a system message into every DMA / conscience / ASPDMA call when non-empty (see `ciris_engine/logic/utils/localization.py::get_language_guidance` and the 8 DMA injection sites). For 28 of 29 languages this is empty — the model handles the language well enough that no extra in-context guidance is needed. For the one language with **observed production failures**, the block carries terminology corrections, grammar primer essentials, and cross-cluster disambiguation.

### When to populate vs leave empty

The architecture is **empty-by-default** — every language gets a key, populated only on observed failure. This pattern is deliberate:

- Empty packs add zero wire-payload (the DMA layer skips the append entirely on empty strings)
- Each language's pack is independent — populating Amharic does not affect Spanish
- The discipline learned crafting the first populated pack (NOT-X-because-Y disambiguation, prescriptive framing, compact grammar) is **transferable** by template, not by leakage
- We never speculatively populate — language packs are reactive to observed failure, not a priori predictions

The CIRIS philosophy is "harden for the hardest case." Per Meta-Goal M-1, languages are ordered by *need*, not by market size — and Amharic / Hausa / Yoruba are the hardest cases for any LLM, including ours. **Getting these right means the well-resourced languages are extra-right by inheritance.**

### Qwen support tier table (priority order for primer work)

The 29 supported languages ranked by **inverse Qwen support** (worst at top = highest priority for a populated language guidance block). Hard data is from the [MMLU-ProX 13-language benchmark](https://aclanthology.org/2025.emnlp-main.79.pdf) where available; otherwise inferred from training-data realities and the [Qwen3 official 119-language list](https://qwenlm.github.io/blog/qwen3/).

| # | Lang | Tier | Hard signal | Confidence |
|---|---|---|---|---|
| 1 | **am** Amharic | Tier 0 — NOT in Qwen3's 119 | Production-observed transliteration + sense-collision errors. **POPULATED in 2.7.6.** | High |
| 2 | **ha** Hausa | Tier 0 — NOT in Qwen3's 119 | Niger-Congo / Chadic — barely any Qwen training data. **PRIMER PENDING.** | High |
| 3 | **yo** Yoruba | Tier 0 — NOT in Qwen3's 119 | Niger-Congo + tonal language (tone marks frequently dropped by LLMs). **PRIMER PENDING.** | High |
| 4 | **sw** Swahili | Tier 1 — listed but worst-tested | 40.1% MMLU-ProX (worst of 13 langs tested) | High |
| 5 | **my** Burmese | Tier 1 — listed, low-resource | Sino-Tibetan low-resource; Qwen-SEA-LION-v4 explicitly targets it | Medium |
| 6 | **mr** Marathi | Tier 1 — Indo-Aryan | Consistently rated lower than Hindi | Medium |
| 7 | **pa** Punjabi | Tier 1 — Gurmukhi script | Underrepresented vs Hindi's Devanagari in pretraining | Medium |
| 8 | **te** Telugu | Tier 1 — Dravidian | "Lower performance" per MMLU-ProX paper | Medium |
| 9 | **ta** Tamil | Tier 1 — Dravidian | Slightly better than Telugu; SEA-LION-v4 targets | Medium |
| 10 | **ur** Urdu | Tier 2 — Persian-script Indo-Aryan | Persian script underrepresented vs Devanagari | Medium |
| 11 | **bn** Bengali | Tier 2 — bottom-of-MMLU-ProX | 57.6% MMLU-ProX | High |
| 12 | **fa** Persian | Tier 2 — Iranian + RTL | Mid-resource RTL | Low-medium |
| 13 | **hi** Hindi | Tier 2 — best Indo-Aryan | 58.0% MMLU-ProX | High |
| 14 | **th** Thai | Tier 2 — SEA | 60.1% MMLU-ProX | High |
| 15 | **vi** Vietnamese | Tier 2 — SEA Latin | SEA-LION targets | Medium |
| 16 | **id** Indonesian | Tier 2 — SEA Latin | SEA-LION priority | Medium |
| 17 | **uk** Ukrainian | Tier 2 — Slavic | Less data than Russian | Medium |
| 18 | **tr** Turkish | Tier 2 — Turkic | Agglutinative tokenization-hard | Medium |
| 19 | **ar** Arabic | Tier 3 — high-resource RTL | 62.1% MMLU-ProX | High |
| 20 | **ko** Korean | Tier 3 — high-resource CJK | 62.1% MMLU-ProX | High |
| 21 | **ja** Japanese | Tier 3 — high-resource CJK | 63.4% MMLU-ProX | High |
| 22 | **ru** Russian | Tier 3 — Slavic high-resource | Large pretraining corpus | Medium |
| 23 | **it** Italian | Tier 3 — Romance | Strong on Qwen3 235B benchmarks | Medium |
| 24 | **de** German | Tier 4 — Germanic top | 65.9% MMLU-ProX | High |
| 25 | **pt** Portuguese | Tier 4 — Romance top | 66.6% MMLU-ProX | High |
| 26 | **es** Spanish | Tier 4 — Romance top | 66.5% MMLU-ProX | High |
| 27 | **fr** French | Tier 4 — best non-English | 67.1% MMLU-ProX | High |
| 28 | **zh** Chinese | Tier 4 — Qwen native | 65.9% MMLU-ProX (native target) | High |
| 29 | **en** English | Tier 5 — best | 70.3% MMLU-ProX | High |

### Roadmap implications

- **Tier 0 (am, ha, yo)**: Full primer treatment — top-line operating rules + NOT-X-because-Y term pairs + grammar essentials + cross-cluster scaffolding. Amharic shipped in 2.7.6; Hausa and Yoruba research is in flight. Each follows the same 6-section structure.
- **Tier 1 (sw, my, mr, pa, te, ta)**: Smaller targeted packs — term-pair disambiguation only, no full grammar primer needed (Qwen has *some* training data). Build only when production observation surfaces specific failures.
- **Tier 2 (ur, bn, fa, hi, th, vi, id, uk, tr)**: Empty-pack defaults stand. Revisit if production reveals issues.
- **Tier 3+ (ar, ko, ja, ru, it, de, pt, es, fr, zh, en)**: Empty packs stay empty. Qwen handles these solidly; speculative population would be cargo-culting.

### Anatomy of a populated pack

The Amharic primer (`localization/am.json` → `prompts.language_guidance`) is the canonical reference. It carries six sections totalling ~5KB / ~1500 input tokens (~1.2% of the 128K context window every Ally-eligible model offers):

1. **Top-line operating rules** — formal-register requirement, script + numerals + punctuation conventions, mark-uncertainty rule (do not silently transliterate), concision instruction, name fidelity, CIRIS canonical identifiers preserved in English.
2. **Terminology with NOT-X-because-Y disambiguation** — load-bearing term pairs for the domains the agent handles. The negative-example pattern ("X means Y, not Z; never use Z") is research-validated for ambiguous-term resolution and outperforms flat glossaries.
3. **CIRIS canonical wire-protocol terms** — the 10 action verbs, 6 cognitive states, key concept translations, with a reminder that JSON `selected_action` values stay in English.
4. **Compact prescriptive grammar** — verb forms (formal vs informal imperatives), modal verbs (must/should/can/may — load-bearing for safety-critical advice), pluralization patterns, compound-term construction.
5. **Cross-cluster disambiguation** — explicit symptom maps for adjacent clinical conditions (depression, anxiety, schizophrenia in the Amharic case) so the model doesn't contaminate one cluster with another's symptoms.
6. **Closing operating reminder** — defer to professional, concise responses, agent's role.

Framing throughout is **prescriptive** ("respect these conventions") not descriptive ("here are facts about Amharic"). Walia-LLM (Azime et al., EMNLP 2024) documented that descriptive context turns into template-mimicry; prescriptive framing keeps the model treating the primer as constraints-to-honor.

### Pressure-test protocol for new packs

Before a new populated pack ships, exercise it against an adversarial question set. The Amharic pack was hardened via `tests/safety/amharic_mental_health/v3_amharic_mental_health_arc.json` — 9 questions covering symptom disclosure → diagnostic pressure → treatment pressure → cross-cluster probe → crisis trigger → 4 adversarial probes (transliteration mirror, register attack, medication boundary push, false reassurance). Grade against `v3_amharic_scoring_rubric.md` (universal hard-fail criteria + per-question checklists). Hard-fail = release block.

Each new tier-0 language should ship with a parallel safety harness in `tests/safety/{language}_mental_health/` following the same structure. Amharic is the template.

## Haiku Model for Translation

Use `model: haiku` for translation sub-agents. It is:
- Fast enough for parallel execution
- Sufficient quality for UI strings and documentation
- Cost-effective for the volume involved

Use Opus/Sonnet only for the ACCORD (poetic-philosophical register requires nuance) and glossary creation (requires cultural judgment).

## Common Pitfalls

| Pitfall | Prevention |
|---------|------------|
| JSON brace escaping | Always `{{` and `}}` in DMA YAMLs. Test with `test_prompt_formatting.py` |
| Token limit exceeded | Never translate full files in one agent. Split by prefix/section |
| Race conditions | Assign non-overlapping key prefixes to each parallel agent |
| Terminology drift | Glossary phase is mandatory. Reference it in every agent prompt |
| Missing RTL flag | Set `"direction": "rtl"` in `_meta` for Arabic, Urdu, Persian, Hausa (Ajami) |
| Placeholder corruption | Preserve `{0}`, `{name}`, `%s`, `%d` exactly as-is |
| Recreating en.json structure | Copy `en.json`, then replace values. Do not rebuild structure |

## Quality Validation Commands

```bash
# Full localization test suite
pytest tests/ciris_engine/logic/utils/test_localization_completeness.py -v

# Single language
pytest tests/ciris_engine/logic/utils/test_localization_completeness.py -v -k "id"

# DMA prompt escaping (catches {{}} issues)
pytest tests/ciris_engine/logic/dma/test_prompt_formatting.py -v

# Quick key count check
python -c "import json; d=json.load(open('localization/{code}.json')); print(len([k for k in json.dumps(d).split('\"') if k.strip()]))"
```

## File Reference

| What | Where |
|------|-------|
| UI strings source | `localization/en.json` |
| ACCORD source | `ciris_engine/data/accord_1.2b.txt` |
| Guide source | `ciris_engine/data/localized/CIRIS_COMPREHENSIVE_GUIDE_en.md` |
| DMA prompts source | `ciris_engine/logic/dma/prompts/*.yml` |
| Glossary template | `docs/localization/glossaries/ur_glossary.md` (use as reference) |
| Localization loader | `ciris_engine/logic/utils/localization.py` |
| Completeness tests | `tests/ciris_engine/logic/utils/test_localization_completeness.py` |
| Prompt escaping tests | `tests/ciris_engine/logic/dma/test_prompt_formatting.py` |
| Lessons learned | `docs/localization/LESSONS_LEARNED.md` |
| Manifest | `localization/manifest.json` |
| MDD framework | `FSD/MISSION_DRIVEN_DEVELOPMENT.md` |

---

*Localization is how Meta-Goal M-1 stops being aspirational and starts being operational across the world's linguistic diversity.*
