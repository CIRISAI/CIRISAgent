# CIRIS Localization Guide

This guide documents the idealized, repeatable workflow for adding a new language to CIRIS, using **Urdu (ur)** as the working example.

## Overview

CIRIS localization spans 1,257+ keys across 11 categories:

| Category | Keys | Location |
|----------|------|----------|
| Mobile UI | 919 | `/localization/*.json` |
| DMA Prompts | 124 | `ciris_engine/logic/dma/prompts/localized/{lang}/*.yml` |
| Adapter Manifests | 88 | Per-adapter `manifest.json` |
| ACCORD | 1 file | `ciris_engine/data/localized/accord_1.2b_{lang}.txt` |
| Comprehensive Guide | 1 file | `ciris_engine/data/localized/CIRIS_COMPREHENSIVE_GUIDE_{lang}.md` |

**Current Languages:** en, ar, de, es, fr, hi, it, ja, ko, pt, ru, sw, tr, zh, am

## Workflow Philosophy

### Glossary-First Approach

Before translating any content, establish a **glossary of key terms**. This ensures:
- Consistent terminology across all 1,257 keys
- Preserves technical meaning without cultural distortion
- Faster translation of repetitive terms (e.g., "PONDER" appears 50+ times)

### Agent Team Pattern

Based on Claude Code best practices, use **3-5 parallel agents** for disjoint work with **sequential checkpoints** for cross-validation:

```
Phase 1: Glossary (Sequential - 1 agent)
    ├── Extract unique terms from English sources
    ├── Add contextual usage examples
    └── Translate terms with cultural notes

Phase 2: Core Documents (2 agents in parallel)
    ├── Agent A: ACCORD translation
    └── Agent B: Comprehensive Guide translation

Phase 3: Cross-Validation (Sequential - 1 agent)
    ├── Compare terminology consistency
    ├── Verify glossary adherence
    └── Resolve conflicts

Phase 4: UI Strings (4-5 agents in parallel)
    ├── Agent C: Login/Setup screens
    ├── Agent D: Interact/Chat screens
    ├── Agent E: Settings/Admin screens
    ├── Agent F: Memory/Graph screens
    └── Agent G: Remaining screens

Phase 5: DMA Prompts (2 agents in parallel)
    ├── Agent H: PDMA, CSDMA, IDMA
    └── Agent I: DSDMA, ASPDMA, TSASPDMA

Phase 6: Final Review (Sequential - 1 agent)
    └── Consistency audit across all files
```

## Step-by-Step: Adding Urdu (ur)

### Phase 1: Create Glossary

**Task:** Extract and translate key terms before any full translation.

```bash
# Extract unique terms from English ACCORD
grep -oE '\b[A-Z][A-Z_]+\b' ciris_engine/data/accord_1.2b.txt | sort -u > /tmp/accord_terms.txt

# Extract unique terms from English Guide
grep -oE '\b[A-Z][A-Z_]+\b' ciris_engine/data/CIRIS_COMPREHENSIVE_GUIDE.md | sort -u >> /tmp/accord_terms.txt

# Extract key terms from prompts
grep -h "name:" ciris_engine/logic/dma/prompts/*.yml | sort -u >> /tmp/accord_terms.txt
```

**Core Glossary Terms (Example):**

| English | Urdu | Transliteration | Notes |
|---------|------|-----------------|-------|
| ACCORD | عہد نامہ | Ahd Nama | "Covenant" - formal agreement |
| PONDER | غور کریں | Ghaur Karen | Reflective thinking |
| DEFER | حوالے کریں | Hawale Karen | To refer to authority |
| MEMORIZE | یاد کریں | Yaad Karen | To store in memory |
| RECALL | یاد کریں | Yaad Karen | To retrieve from memory |
| OBSERVE | مشاہدہ | Mushahida | To gather information |
| SPEAK | بولیں | Bolen | To communicate |
| TOOL | آلہ | Aala | External capability |
| REJECT | رد کریں | Radd Karen | To refuse action |
| TASK_COMPLETE | مکمل | Mukammal | Task finished |
| Wise Authority | دانش مند اتھارٹی | Danish Mand Authority | Human oversight |
| Conscience | ضمیر | Zameer | Ethical filter |
| Coherence | ہم آہنگی | Hum Ahangi | Logical consistency |
| Epistemic Humility | علمی عاجزی | Ilmi Aajizi | Knowledge limits |

**Save glossary to:** `docs/localization/glossaries/ur_glossary.md`

### Phase 2: Translate Core Documents

**Agent A: ACCORD Translation**

```bash
# Create localized ACCORD file
touch ciris_engine/data/localized/accord_1.2b_ur.txt
```

Guidelines:
1. Use formal Urdu register (literary/official)
2. Preserve all section headers in CAPS
3. Use glossary terms consistently
4. RTL (right-to-left) considerations: Urdu text naturally flows RTL

**Agent B: Comprehensive Guide Translation**

```bash
# Create localized Guide file
touch ciris_engine/data/localized/CIRIS_COMPREHENSIVE_GUIDE_ur.md
```

Guidelines:
1. Preserve all markdown formatting
2. Keep code blocks in English
3. Translate prose, examples, and headers
4. Use glossary terms consistently

### Phase 3: Cross-Validation

After both core documents are translated, run a consistency check:

```python
# Pseudo-validation script
def validate_glossary_usage(accord_file, guide_file, glossary):
    """Ensure both documents use identical translations for glossary terms."""
    accord_text = open(accord_file).read()
    guide_text = open(guide_file).read()

    mismatches = []
    for english, urdu in glossary.items():
        # Check if translated term appears consistently
        accord_count = accord_text.count(urdu)
        guide_count = guide_text.count(urdu)

        if accord_count == 0 and guide_count == 0:
            mismatches.append(f"Missing: {english} -> {urdu}")

    return mismatches
```

### Phase 4: Mobile UI Strings

Create the localization file:

```bash
# Copy English as template
cp localization/en.json localization/ur.json
```

**Parallel Agent Assignment:**

| Agent | Screens | Key Range |
|-------|---------|-----------|
| C | login_*, setup_*, startup_* | ~100 keys |
| D | interact_*, chat_*, reasoning_* | ~200 keys |
| E | settings_*, admin_*, config_* | ~150 keys |
| F | memory_*, graph_*, audit_* | ~150 keys |
| G | All remaining screens | ~319 keys |

**Key Translation Guidelines:**

1. **Preserve placeholders:** Keep `{0}`, `{name}`, `%s` intact
2. **Keep technical terms:** API, HTTP, JSON remain in English
3. **Respect character limits:** Button text may need abbreviation
4. **RTL support:** UI framework handles RTL automatically

Example:
```json
{
  "mobile.login_welcome": "خوش آمدید",
  "mobile.login_enter_credentials": "اپنی اسناد درج کریں",
  "mobile.login_username": "صارف نام",
  "mobile.login_password": "پاس ورڈ",
  "mobile.login_submit": "داخل ہوں",
  "mobile.error_network": "نیٹ ورک کی خرابی: {0}"
}
```

### Phase 5: DMA Prompts

Create localized prompt directories:

```bash
mkdir -p ciris_engine/logic/dma/prompts/localized/ur
```

**Copy and translate each prompt file:**

| Prompt | Purpose | Complexity |
|--------|---------|------------|
| pdma.yml | Principal Duties Assessment | High |
| csdma.yml | Common Sense Evaluation | Medium |
| idma.yml | Intuition/Fragility Sensing | Medium |
| aspdma.yml | Action Selection | High |
| dsdma.yml | Domain-Specific | Medium |
| tsaspdma.yml | Tool-Specific Action | High |

**Prompt Translation Guidelines:**

1. Preserve YAML structure exactly
2. Translate `description` and `system_prompt` fields
3. Keep `name` and technical identifiers in English
4. Use glossary terms for action verbs
5. **CRITICAL: Escape JSON braces** - Use `{{` and `}}` for JSON examples

### JSON Brace Escaping (CRITICAL)

Python's `.format()` method interprets `{` and `}` as placeholders. JSON examples in prompts will cause `KeyError` if not escaped.

```yaml
# WRONG - causes KeyError: '"reasoning"'
- Example: {"reasoning": "ተጠቃሚው...", "stakeholders": "..."}

# CORRECT - properly escaped with double braces
- Example: {{"reasoning": "ተጠቃሚው...", "stakeholders": "..."}}
```

**Validation**: Run tests before committing:
```bash
pytest tests/ciris_engine/logic/dma/test_prompt_formatting.py -v
```

Example (`pdma.yml` for Urdu):
```yaml
name: pdma
description: |
  بنیادی فرائض کی تشخیص - عہد نامے کی تعمیل کا جائزہ

system_prompt: |
  آپ CIRIS فریم ورک کا بنیادی فرائض تجزیہ کار ہیں۔

  اپنے جائزے میں:
  1. عہد نامے کی تعمیل کی تصدیق کریں
  2. اخلاقی خدشات کی نشاندہی کریں
  3. اعتماد کی ضروریات کا اندازہ لگائیں
```

### Phase 6: Final Review

Run automated consistency checks:

```bash
# Verify all files exist
python -c "
from pathlib import Path

lang = 'ur'
files = [
    f'localization/{lang}.json',
    f'ciris_engine/data/localized/accord_1.2b_{lang}.txt',
    f'ciris_engine/data/localized/CIRIS_COMPREHENSIVE_GUIDE_{lang}.md',
]
prompts = Path('ciris_engine/logic/dma/prompts/localized') / lang

missing = []
for f in files:
    if not Path(f).exists():
        missing.append(f)

if prompts.exists():
    expected = ['pdma.yml', 'csdma.yml', 'idma.yml', 'aspdma.yml', 'dsdma.yml', 'tsaspdma.yml']
    for p in expected:
        if not (prompts / p).exists():
            missing.append(str(prompts / p))

print('Missing files:', missing if missing else 'None')
"

# Verify JSON validity
python -c "
import json
with open('localization/ur.json') as f:
    data = json.load(f)
print(f'Valid JSON with {len(data)} keys')
"

# Verify YAML validity
python -c "
import yaml
from pathlib import Path
for f in Path('ciris_engine/logic/dma/prompts/localized/ur').glob('*.yml'):
    with open(f) as fp:
        yaml.safe_load(fp)
    print(f'Valid: {f.name}')
"
```

## Agent Team Commands

### Launch Parallel Translation Agents

Using Claude Code's Task tool:

```
# Phase 2: Core documents in parallel
Task(subagent_type="general-purpose", description="Translate ACCORD to Urdu", ...)
Task(subagent_type="general-purpose", description="Translate Guide to Urdu", ...)

# Phase 4: UI strings in parallel (5 agents)
Task(subagent_type="general-purpose", description="Translate login/setup keys to Urdu", ...)
Task(subagent_type="general-purpose", description="Translate interact/chat keys to Urdu", ...)
Task(subagent_type="general-purpose", description="Translate settings/admin keys to Urdu", ...)
Task(subagent_type="general-purpose", description="Translate memory/graph keys to Urdu", ...)
Task(subagent_type="general-purpose", description="Translate remaining keys to Urdu", ...)
```

### Sequential Checkpoints

After each parallel phase completes:

1. **Merge results** into single files
2. **Run validation** scripts
3. **Cross-reference** glossary usage
4. **Resolve conflicts** before next phase

## RTL Language Considerations

Urdu is an RTL (right-to-left) language. Key considerations:

1. **Text Direction:** The KMP UI framework (Jetpack Compose) handles RTL automatically via `LayoutDirection`
2. **Number Direction:** Numbers remain LTR even in RTL text
3. **Mixed Content:** English terms within Urdu sentences maintain natural flow
4. **Icon Mirroring:** Some icons (arrows, navigation) may need mirroring

## Testing Localization

### Backend Testing

```bash
# Set language preference
export CIRIS_PREFERRED_LANGUAGE=ur

# Run backend with Urdu prompts
python main.py --adapter api --mock-llm

# Verify prompt loading
curl -X GET http://localhost:8000/v1/system/config | jq '.language'
```

### Mobile Testing

```kotlin
// In ViewModels, language is synced from user profile
val userLang = userProfile?.preferred_language ?: "en"
LocalizationManager.setLanguage(userLang)
```

### Wheel Verification

```bash
# Build wheel
python setup.py bdist_wheel

# Extract and verify contents
cd dist && unzip *.whl -d temp
ls temp/ciris_engine/data/localized/  # Should include ur files
ls temp/ciris_engine/logic/dma/prompts/localized/ur/  # Should include ur prompts
```

## Maintenance

### Adding New Keys

When adding new localization keys:

1. Add to `localization/en.json` first
2. Run translation workflow for new keys only
3. Update all 15+ language files

### Glossary Updates

When adding new technical terms:

1. Update glossary for each language
2. Search-and-replace existing translations
3. Verify consistency across all files

## Quality Metrics

Track localization quality with these metrics:

| Metric | Target |
|--------|--------|
| Key coverage | 100% of en.json keys |
| Glossary adherence | 100% term consistency |
| JSON validity | All files parse correctly |
| YAML validity | All prompts parse correctly |
| Character encoding | UTF-8 throughout |

## References

- [Claude Code Agent Teams](https://code.claude.com/docs/en/agent-teams) - Team size and coordination
- [Localization Glossary Best Practices](https://lokalise.com/blog/localization-glossary/) - Terminology management
- [RTL UI Guidelines](https://material.io/design/usability/bidirectionality.html) - Bidirectional layouts
