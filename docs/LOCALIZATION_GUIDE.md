# CIRIS Localization Guide

This file used to hold a 400-line walkthrough for adding a language by hand
with parallel agents, written when CIRIS shipped 15 languages. Its paths, key
counts and workflow no longer match the repository, and following it would
break things (it had strings under `/localization/*.json`, where a JSON file
now disables the agent's string loader). It was replaced by this pointer on
2026-11-11; the old text is in git history.

Where things are now:

| You want to | Read |
|---|---|
| Know the current state of all 29 languages, and how to translate | [`localization/CLAUDE.md`](../localization/CLAUDE.md) |
| Understand the translation pipeline and where it comes from | [`localization/VENDORED.md`](../localization/VENDORED.md) |
| See what the quality ratchet rests on | [`localization/PRIOR_ART.md`](../localization/PRIOR_ART.md) |
| Propose a correction as a native speaker | <https://ciris.ai/crowdsourcing-alignment> |
| Work on safety batteries and rubrics | [`tests/safety/README.md`](../tests/safety/README.md) |
| Work on the polyglot layer (not translation) | [`ciris_engine/data/localized/polyglot/CLAUDE.md`](../ciris_engine/data/localized/polyglot/CLAUDE.md) |
| Read what the early fan-out effort got wrong | [`docs/localization/LESSONS_LEARNED.md`](localization/LESSONS_LEARNED.md) |
