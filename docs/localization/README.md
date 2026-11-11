# docs/localization

Historical material from the first localization effort (April 2026), plus one
directory that is still load-bearing.

| Here | Status |
|---|---|
| `glossaries/` | **Read by a test.** `test_localization_completeness.py` requires one glossary per language here. These are the agent's original glossaries. The translation pipeline does NOT read them: it reads `localization/glossaries/`, vendored from CIRISClient. The two sets differ in all 29 files, so a term fixed in one is not fixed in the other |
| `LESSONS_LEARNED.md` | Historical. Still worth reading for the failure modes |
| `PERSIAN_LOCALIZATION_SUMMARY.md`, `TAMIL_LOCALIZATION_SUMMARY.md` | Historical snapshots of two bootstrap runs |

Current state and process: [`localization/CLAUDE.md`](../../localization/CLAUDE.md).
