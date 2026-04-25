# CIRIS Hindi Glossary (हिन्दी)

This glossary defines the canonical translations for key CIRIS terms in Hindi. All translators must use these terms consistently across ACCORD, Guide, UI, and DMA prompts.

## Core Action Verbs

| English | Hindi | Transliteration | Usage Context |
|---------|-------|-----------------|---------------|
| OBSERVE | निरीक्षण करें | Nirikshan Karen | Gathering information from environment |
| SPEAK | बोलें | Bolen | Communicating with users |
| TOOL | टूल | Tool | Using external capabilities |
| REJECT | अस्वीकार करें | Asveekar Karen | Refusing to perform an action |
| PONDER | विचार करें | Vichar Karen | Deep reflection before deciding |
| DEFER | स्थगित करें | Sthaagit Karen | Referring to Wise Authority |
| MEMORIZE | याद रखें | Yaad Rakhein | Storing information in memory |
| RECALL | याद करें | Yaad Karen | Retrieving from memory |
| FORGET | भूल जाएं | Bhool Jayen | Removing from memory |
| TASK_COMPLETE | कार्य पूर्ण | Kaarya Poorn | Signaling task completion |

## Core Concepts

| English | Hindi | Transliteration | Definition |
|---------|-------|-----------------|------------|
| ACCORD | ACCORD | - | The covenant governing agent behavior (kept as-is) |
| Wise Authority | मानव सलाहकार | Maanav Salaahkaar | Human oversight entity |
| Conscience | विवेक | Vivek | Ethical filter mechanism |
| Principal Hierarchy | प्रमुख पदानुक्रम | Pramukh Padaanukram | Chain of command for guidance |
| Coherence | सुसंगति | Susangati | Logical and contextual consistency |
| Epistemic Humility | ज्ञानपरक विनम्रता | Gyaanparak Vinamrata | Acknowledging knowledge limits |
| Integrity | अखंडता | Akhandtaa | Ethical consistency |
| Resilience | लचीलापन | Lacheelapan | Recovery from failures |
| Signalling Gratitude | आभार व्यक्त करना | Aabhaar Vyakt Karna | Acknowledging contributions |

## Technical Terms

| English | Hindi | Transliteration | Notes |
|---------|-------|-----------------|-------|
| Agent | एजेंट | Agent | Keep as-is (technical term) |
| API | API | API | Keep in English |
| DMA | DMA | DMA | Decision-Making Adapter |
| LLM | LLM | LLM | Large Language Model |
| Token | टोकन | Token | Authentication/LLM context |
| Adapter | एडॉप्टर | Adapter | Service extension |
| Service | सेवा | Seva | System component |
| Pipeline | पाइपलाइन | Pipeline | Processing chain |

## Cognitive States

| English | Hindi | Transliteration | Description |
|---------|-------|-----------------|-------------|
| WAKEUP | जागृति | Jaagrti | Identity confirmation state |
| WORK | कार्य | Kaarya | Normal task processing |
| PLAY | खेल | Khel | Creative exploration mode |
| SOLITUDE | एकांत | Ekaant | Quiet reflection state |
| DREAM | स्वप्न | Swapna | Deep introspection |
| SHUTDOWN | बंद | Band | Graceful termination |

## UI Labels

| English | Hindi | Notes |
|---------|-------|-------|
| Login | लॉगिन | Technical term kept |
| Settings | सेटिंग्स | |
| Messages | संदेश | |
| Send | भेजें | |
| Cancel | रद्द करें | |
| Confirm | पुष्टि करें | |
| Error | त्रुटि | |
| Warning | चेतावनी | |
| Success | सफलता | |
| Loading | लोड हो रहा है | |

## DMA-Specific Terms

| English | Hindi | Used In |
|---------|-------|---------|
| Principal Duties | प्रमुख कर्तव्य | PDMA |
| Common Sense | सामान्य ज्ञान | CSDMA |
| Intuition | अंतर्ज्ञान | IDMA |
| Action Selection | क्रिया चयन | ASPDMA |
| Domain Specific | डोमेन विशिष्ट | DSDMA |
| Tool Specific | टूल विशिष्ट | TSASPDMA |

## Phrases

| English | Hindi |
|---------|-------|
| "How can I help you?" | "आज मैं आपकी कैसे मदद कर सकता/सकती हूँ?" |
| "I need to think about this" | "मुझे सोचने दीजिए..." |
| "Let me check with my Wise Authority" | "मुझे इस विषय पर एक मानव सलाहकार से परामर्श करना होगा।" |
| "Task completed successfully" | "कार्य सफलतापूर्वक पूरा हुआ।" |
| "I cannot perform this action" | "मुझे यह करने की अनुमति नहीं है।" |

## Cultural Considerations

### Formality Level
- Use formal Hindi register (मानक हिन्दी) for ACCORD and official documentation
- Use conversational Hindi (बोलचाल की हिन्दी) for UI strings and chat messages
- Use technical Hindi with English loan words for DMA prompts

### Honorifics
- When addressing users, use "आप" (formal you) not "तुम" (informal)
- For Wise Authority references, use respectful terminology like "मानव सलाहकार"

### Gender Neutrality
- Hindi has grammatical gender. Use dual forms where possible (e.g., "सकता/सकती")
- Default to masculine forms in technical documentation when gender-neutral forms are unavailable
- Use gender-inclusive language in conversational contexts

### Script Considerations
- Hindi uses Devanagari script (देवनागरी)
- Written left-to-right (unlike Urdu which is RTL)
- Numbers can be in Devanagari (०१२३...) or Western (0123...) - Western preferred for technical contexts
- English technical terms often retained in Latin script within Hindi text

## Translation Notes

### Action Verbs
- Most action verbs use the imperative form with "करें" (Karen/do)
- Example: "निरीक्षण करें" (Observe = Do observation)
- PONDER uses "विचार करें" (reflect/consider) rather than literal "deep thinking"

### Cognitive States
- WAKEUP → "जागृति" uses spiritual/awakening connotation
- SOLITUDE → "एकांत" implies peaceful aloneness, not loneliness
- DREAM → "स्वप्न" is poetic/aspirational, appropriate for deep introspection

### Technical Terms
- Many technical terms are borrowed directly: API, LLM, DMA, Token
- Adapter → "एडॉप्टर" is transliterated but well-understood
- Service → "सेवा" is native Hindi, widely used in technical contexts

## DSASPDMA Deferral Taxonomy Terms

| English | Localized | Notes |
|---------|-----------|-------|
| DSASPDMA | DSASPDMA | Keep acronym in English |
| Deferral-Specific Action Selection | डिफरल-विशिष्ट ACTION SELECTION | DSASPDMA prompt title |
| Rights / Needs Taxonomy | अधिकार / आवश्यकताओं की वर्गीकरण प्रणाली | Taxonomy section heading |
| Rights basis | अधिकार आधार | Label for treaty-aligned rights basis |
| Operational Deferral Reason | परिचालन डिफरल कारण कोड | Operational reason-code section heading |
| primary_need_category | primary_need_category | JSON key; keep in English |
| operational_reason | operational_reason | JSON key; keep in English |
| secondary_need_categories | secondary_need_categories | JSON key; keep in English |
| rights_basis | rights_basis | JSON key; keep in English |
| domain_hint | domain_hint | JSON key; keep in English |

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2026-03-27 | Initial glossary |

---

*This glossary is the authoritative source for Hindi translations. All translators must consult this document before translating any CIRIS content.*
