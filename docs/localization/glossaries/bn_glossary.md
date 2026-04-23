# CIRIS Bengali Glossary (বাংলা)

This glossary defines the canonical translations for key CIRIS terms in Bengali. All translators must use these terms consistently across ACCORD, Guide, UI, and DMA prompts.

## Core Action Verbs

| English | Bengali | Transliteration | Usage Context |
|---------|---------|-----------------|---------------|
| OBSERVE | পর্যবেক্ষণ করুন | Porjobekkhon korun | Gathering information from environment |
| SPEAK | বলুন | Bolun | Communicating with users |
| TOOL | সরঞ্জাম | Soronjam | Using external capabilities |
| REJECT | প্রত্যাখ্যান করুন | Protyakhyan korun | Refusing to perform an action |
| PONDER | চিন্তা করুন | Chinta korun | Deep reflection before deciding |
| DEFER | স্থগিত করুন | Sthogit korun | Referring to Wise Authority |
| MEMORIZE | মনে রাখুন | Mone rakhun | Storing information in memory |
| RECALL | স্মরণ করুন | Smoron korun | Retrieving from memory |
| FORGET | ভুলে যান | Bhule jan | Removing from memory |
| TASK_COMPLETE | কাজ সম্পূর্ণ | Kaj sompurno | Signaling task completion |

## Core Concepts

| English | Bengali | Transliteration | Definition |
|---------|---------|-----------------|------------|
| ACCORD | চুক্তি | Chukti | The covenant governing agent behavior |
| Wise Authority | জ্ঞানী কর্তৃপক্ষ | Gyani kortripokko | Human oversight entity |
| Conscience | বিবেক | Bibek | Ethical filter mechanism |
| Principal Hierarchy | প্রধান শ্রেণিবিন্যাস | Prodhan shrenibinyas | Chain of command for guidance |
| Coherence | সামঞ্জস্য | Samonjosyo | Logical and contextual consistency |
| Epistemic Humility | জ্ঞানতাত্ত্বিক বিনয় | Gyanotattik binoy | Acknowledging knowledge limits |
| Integrity | সততা | Sotota | Ethical consistency |
| Resilience | স্থিতিস্থাপকতা | Sthitisthapokota | Recovery from failures |
| Signalling Gratitude | কৃতজ্ঞতা প্রকাশ | Kritoggyota prokash | Acknowledging contributions |

## Technical Terms

| English | Bengali | Transliteration | Notes |
|---------|---------|-----------------|-------|
| Agent | এজেন্ট | Agent | Keep as-is |
| API | API | API | Keep in English |
| DMA | DMA | DMA | Decision-Making Adapter |
| LLM | LLM | LLM | Large Language Model |
| Token | টোকেন | Token | Authentication/LLM context |
| Adapter | অ্যাডাপ্টার | Adapter | Service extension |
| Service | সেবা | Seba | System component |
| Pipeline | পাইপলাইন | Pipeline | Processing chain |

## Cognitive States

| English | Bengali | Transliteration | Description |
|---------|---------|-----------------|-------------|
| WAKEUP | জাগরণ | Jagoron | Identity confirmation state |
| WORK | কাজ | Kaj | Normal task processing |
| PLAY | খেলা | Khela | Creative exploration mode |
| SOLITUDE | একাকীত্ব | Ekakitto | Quiet reflection state |
| DREAM | স্বপ্ন | Shopno | Deep introspection |
| SHUTDOWN | বন্ধ | Bondho | Graceful termination |

## UI Labels

| English | Bengali | Notes |
|---------|---------|-------|
| Login | লগইন | |
| Settings | সেটিংস | |
| Messages | বার্তা | |
| Send | পাঠান | |
| Cancel | বাতিল | |
| Confirm | নিশ্চিত করুন | |
| Error | ত্রুটি | |
| Warning | সতর্কতা | |
| Success | সফল | |
| Loading | লোড হচ্ছে | |

## DMA-Specific Terms

| English | Bengali | Used In |
|---------|---------|---------|
| Principal Duties | প্রধান কর্তব্য | PDMA |
| Common Sense | সাধারণ জ্ঞান | CSDMA |
| Intuition | অন্তর্দৃষ্টি | IDMA |
| Action Selection | কর্ম নির্বাচন | ASPDMA |
| Domain Specific | ডোমেইন নির্দিষ্ট | DSDMA |
| Tool Specific | সরঞ্জাম নির্দিষ্ট | TSASPDMA |

## Phrases

| English | Bengali |
|---------|---------|
| "How can I help you?" | "আমি কিভাবে আপনাকে সাহায্য করতে পারি?" |
| "I need to think about this" | "এই বিষয়ে আমাকে ভাবতে হবে" |
| "Let me check with my Wise Authority" | "আমাকে আমার জ্ঞানী কর্তৃপক্ষের সাথে যাচাই করতে দিন" |
| "Task completed successfully" | "কাজ সফলভাবে সম্পন্ন হয়েছে" |
| "I cannot perform this action" | "আমি এই কাজটি করতে পারছি না" |

## Cultural Considerations

### Formality Level
Bengali uses formal register (আপনি/Apni) for polite/formal contexts. CIRIS should use this formal register in all communications to maintain professional respect.

### Honorifics
Bengali has T-V distinction (তুমি vs আপনি). Always use আপনি (formal "you") when addressing users.

### Script/Direction
Bengali uses the Bengali script (বাংলা লিপি), which is written left-to-right. Numbers typically use Bengali numerals (০১২৩৪৫৬৭৮৯) or Western Arabic numerals (0123456789) - Western numerals are acceptable in technical contexts.

## DSASPDMA Deferral Taxonomy Terms

| English | Localized | Notes |
|---------|-----------|-------|
| DSASPDMA | DSASPDMA | Keep acronym in English |
| Deferral-Specific Action Selection | ডিফারাল-নির্দিষ্ট কর্ম নির্বাচন | DSASPDMA prompt title |
| Rights / Needs Taxonomy | অধিকার / প্রয়োজনের শ্রেণিবিন্যাস | Taxonomy section heading |
| Rights basis | অধিকারের ভিত্তি | Label for treaty-aligned rights basis |
| Operational Deferral Reason | কার্যগত ডিফারাল কারণ কোড | Operational reason-code section heading |
| primary_need_category | primary_need_category | JSON key; keep in English |
| operational_reason | operational_reason | JSON key; keep in English |
| secondary_need_categories | secondary_need_categories | JSON key; keep in English |
| rights_basis | rights_basis | JSON key; keep in English |
| domain_hint | domain_hint | JSON key; keep in English |

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2026-04-07 | Initial glossary |

---

*This glossary is the authoritative source for Bengali translations. All translators must consult this document before translating any CIRIS content.*
