# Localization Lessons Learned

This document captures lessons learned from the CIRIS localization effort to help future agents work more efficiently.

## Summary Statistics

- **Languages**: 16 (en + 15 translations)
- **Total keys per language**: 1,257 nested keys
- **ACCORD document**: ~1,153 lines per language
- **DMA prompts**: 6 YAML files per language
- **Glossaries**: 1 per language (15 total)

## What Worked Well

### 1. Glossary-First Approach
Creating glossaries BEFORE translation ensured consistent terminology across all files. Key benefits:
- Technical terms like "ACCORD", "Wise Authority", "Conscience" have canonical translations
- Reduced rework from inconsistent translations
- Agents could reference glossaries for correct terminology

### 2. Parallel Sub-Agent Strategy
Splitting large files into sub-sections worked much better than single agents:
- **Good**: "Fix am.json mobile common/nav keys" (specific scope)
- **Bad**: "Translate entire en.json to Urdu" (too broad, hits token limits)

Recommended split for JSON files (~1,257 keys):
1. common_*, nav_*, screen_*, filter_* (~80 keys)
2. setup_*, startup_*, status_*, processing_* (~80 keys)
3. services_*, system_*, sessions_*, scheduler_*, runtime_* (~120 keys)
4. adapter_*, audit_*, billing_*, config_*, consent_*, data_*, graph_*, logs_*, memory_*, telemetry_*, tickets_*, remaining (~230 keys)

### 3. Haiku Model for Translation Tasks
Using `model: haiku` for translation sub-agents was effective:
- Fast execution
- Sufficient quality for UI string translation
- Lower token limits forced focused scope

### 4. Unit Tests for Validation
The localization completeness test (`test_localization_completeness.py`) correctly identified:
- Missing keys
- Duplicate keys
- Incomplete ACCORD translations
- Missing DMA prompts

## What Didn't Work

### 1. Full-File Translation Agents
Agents attempting to translate entire files hit token limits:
```
API Error: Claude's response exceeded the 32000 output token maximum.
```

**Solution**: Split into sub-sections of ~100-200 keys each.

### 2. Nested JSON Structure Complexity
The JSON files have deeply nested structures:
```json
{
  "mobile": {
    "interact_action_defer": "...",
    "interact_action_forget": "..."
  }
}
```

**Solution**: Agents should use Python/Edit tools to surgically add missing keys rather than rewriting entire files.

### 3. Race Conditions Between Agents
Multiple agents editing the same file can cause conflicts.

**Solution**: Assign non-overlapping key prefixes to each agent (e.g., one agent does `common_*`, another does `nav_*`).

## Recommended Workflow for Future Languages

### Phase 1: Glossary (1 agent, ~5 min)
```
Create glossary for {language} at docs/localization/glossaries/{code}_glossary.md
Use TEMPLATE_glossary.md as base
Include all CIRIS action verbs, core concepts, technical terms
```

### Phase 2: JSON Translation (4-5 parallel agents)
Split by key prefix groups:
- Agent 1: `common_*, nav_*, screen_*, filter_*`
- Agent 2: `setup_*, startup_*, status_*, processing_*`
- Agent 3: `services_*, system_*, sessions_*, scheduler_*, runtime_*`
- Agent 4: `adapter_*, audit_*, billing_*, config_*, consent_*, data_*`
- Agent 5: `graph_*, logs_*, memory_*, telemetry_*, tickets_*, remaining`

### Phase 3: ACCORD Translation (2-3 parallel agents)
Split by sections:
- Agent 1: Sections 0-3 (Introduction, Core Identity, Operations)
- Agent 2: Sections 4-6 (Obligations, Maturity, Creation Ethics)
- Agent 3: Sections 7-9 + Annexes (War Ethics, Sunset, Mathematics)

### Phase 4: DMA Prompts (2 parallel agents)
- Agent 1: pdma_ethical.yml, csdma_common_sense.yml, idma.yml
- Agent 2: action_selection_pdma.yml, dsdma_base.yml, tsaspdma.yml

### Phase 5: Validation (1 agent)
```bash
pytest tests/ciris_engine/logic/utils/test_localization_completeness.py -v -k "{language_code}"
```

## Key File Locations

| Content | Path Pattern |
|---------|--------------|
| Mobile JSON | `localization/{code}.json` |
| ACCORD | `ciris_engine/data/localized/accord_1.2b_{code}.txt` |
| Guide | `ciris_engine/data/localized/CIRIS_COMPREHENSIVE_GUIDE_{code}.md` |
| DMA Prompts | `ciris_engine/logic/dma/prompts/localized/{code}/*.yml` |
| Glossaries | `docs/localization/glossaries/{code}_glossary.md` |

## Registering New Languages

**CRITICAL**: After creating translation files, you MUST register the language in these 3 locations:

| File | Purpose |
|------|---------|
| `localization/manifest.json` | Backend language registry |
| `ciris_engine/data/localized/manifest.json` | Package data registry (copy of above) |
| `mobile/shared/.../viewmodels/SetupState.kt` | Mobile UI dropdown (`SUPPORTED_LANGUAGES` list) |

### manifest.json Entry Format
```json
"ur": {
  "name": "Urdu",
  "native_name": "اردو",
  "iso_639_1": "ur",
  "direction": "rtl",  // Only for RTL languages (ar, ur)
  "origin": "auto-generated",
  "added": "2026-03-27",
  "status": "draft",
  "review_status": "needs_native_review",
  "coverage": "complete"
}
```

### SetupState.kt Entry Format
```kotlin
SupportedLanguage("ur", "اردو", "Urdu")
```

### Test Parameterization
Also add the language code to test parametrization in:
- `tests/ciris_engine/logic/utils/test_localization_completeness.py` (5 locations)

## Agent Prompt Templates

### For JSON Key Groups
```
Add missing mobile keys to /home/emoore/CIRISAgent/localization/{code}.json.

Focus ONLY on these key prefixes: {prefix_list}

Read existing {code}.json, read en.json for missing keys, use {code}_glossary.md for terminology.
Edit {code}.json to add ONLY these specific key groups with {language} translations.
```

### For ACCORD Sections
```
Translate sections {X}-{Y} of the ACCORD to {language}.
Source: ciris_engine/data/accord_1.2b.txt
Target: ciris_engine/data/localized/accord_1.2b_{code}.txt
Use glossary at docs/localization/glossaries/{code}_glossary.md
Preserve section headers in CAPS, keep code blocks in English.
```

## Common Issues and Fixes

| Issue | Symptom | Fix |
|-------|---------|-----|
| Token limit exceeded | "Claude's response exceeded 32000 token maximum" | Split into smaller sub-sections |
| Missing keys | Test shows "missing X keys" | Run targeted agent for specific prefix group |
| Duplicate keys | JSON parse error or test failure | Use `check_duplicate_keys()` function |
| Inconsistent terminology | Different translations for same term | Enforce glossary usage in prompts |
| RTL issues (ar, ur) | Text direction wrong | Ensure `_meta.direction: "rtl"` is set |

## Validation Checklist

- [ ] JSON file has 1,257 nested keys
- [ ] JSON is valid (parseable)
- [ ] No duplicate keys
- [ ] ACCORD has ~1,150-1,160 lines
- [ ] All 6 DMA prompt files exist
- [ ] Glossary exists with all sections filled
- [ ] RTL languages have `direction: "rtl"` in metadata
- [ ] Placeholders preserved ({0}, {name}, %s, etc.)
- [ ] Technical terms match glossary

---

*Last updated: 2026-03-27*
*Languages completed: am, ar, de, es, fr, hi, it, ja, ko, pt, ru, sw, tr, ur, zh (16 total including en)*
