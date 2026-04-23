# CIRIS Korean Glossary (한국어)

This glossary defines the canonical translations for key CIRIS terms in Korean. All translators must use these terms consistently across ACCORD, Guide, UI, and DMA prompts.

## Core Action Verbs

| English | Korean | Romanization | Usage Context |
|---------|--------|--------------|---------------|
| OBSERVE | 관찰 | gwanchal | Gathering information from environment |
| SPEAK | 말하기 | malhagi | Communicating with users |
| TOOL | 도구 | dogu | Using external capabilities |
| REJECT | 거부 | geobu | Refusing to perform an action |
| PONDER | 숙고 | sukgo | Deep reflection before deciding |
| DEFER | 연기 | yeongi | Referring to Wise Authority |
| MEMORIZE | 기억 | gieok | Storing information in memory |
| RECALL | 회상 | hoesang | Retrieving from memory |
| FORGET | 잊기 | itgi | Removing from memory |
| TASK_COMPLETE | 완료 | wanlyo | Signaling task completion |

## Core Concepts

| English | Korean | Romanization | Definition |
|---------|--------|--------------|------------|
| ACCORD | 협약 | hyeobyak | The covenant governing agent behavior |
| Wise Authority | 담당자 | damjangja | Human oversight entity (lit. "person in charge") |
| Conscience | 양심 | yangsim | Ethical filter mechanism |
| Principal Hierarchy | 원칙 계층 | wonjik gyecheung | Chain of command for guidance |
| Coherence | 일관성 | ilgwanseong | Logical and contextual consistency |
| Epistemic Humility | 인식적 겸손 | insikjeok gyeomson | Acknowledging knowledge limits |
| Integrity | 무결성 | mugyeolseong | Ethical consistency |
| Resilience | 회복력 | hoebokryeok | Recovery from failures |
| Signalling Gratitude | 감사 표현 | gamsa pyohyeon | Acknowledging contributions |

## Technical Terms

| English | Korean | Romanization | Notes |
|---------|--------|--------------|-------|
| Agent | 에이전트 | eijenteu | Keep as-is (technical term) |
| API | API | API | Keep in English |
| DMA | DMA | DMA | Decision-Making Adapter |
| LLM | LLM | LLM | Large Language Model |
| Token | 토큰 | tokeun | Authentication/LLM context |
| Adapter | 어댑터 | eodaepteo | Service extension |
| Service | 서비스 | seobiseu | System component |
| Pipeline | 파이프라인 | paipeulain | Processing chain |

## Cognitive States

| English | Korean | Romanization | Description |
|---------|--------|--------------|-------------|
| WAKEUP | 기상 | gisang | Identity confirmation state |
| WORK | 작업 | jageop | Normal task processing |
| PLAY | 놀이 | nori | Creative exploration mode |
| SOLITUDE | 고독 | godok | Quiet reflection state |
| DREAM | 꿈 | kkum | Deep introspection |
| SHUTDOWN | 종료 | jonglyo | Graceful termination |

## UI Labels

| English | Korean | Romanization | Notes |
|---------|--------|--------------|-------|
| Login | 로그인 | rogeugin | |
| Settings | 설정 | seoljeong | |
| Messages | 메시지 | mesiji | |
| Send | 전송 | jeonsong | |
| Cancel | 취소 | chwiso | |
| Confirm | 확인 | hwag-in | |
| Error | 오류 | oryu | |
| Warning | 경고 | gyeong-go | |
| Success | 성공 | seonggong | |
| Loading | 로드 중 | lodeu jung | |
| Save | 저장 | jeojang | |
| Back | 뒤로 | dwilo | |
| Next | 다음 | da-eum | |
| Continue | 계속 | gyesok | |
| Finish | 완료 | wanlyo | |

## DMA-Specific Terms

| English | Korean | Romanization | Used In |
|---------|--------|--------------|---------|
| Principal Duties | 주요 임무 | juyo immu | PDMA |
| Common Sense | 상식 | sangsik | CSDMA |
| Intuition | 직관 | jikgwan | IDMA |
| Action Selection | 작업 선택 | jageop seontaek | ASPDMA |
| Domain Specific | 도메인 특정 | domein teukjeong | DSDMA |
| Tool Specific | 도구 특정 | dogu teukjeong | TSASPDMA |

## Phrases

| English | Korean | Romanization |
|---------|--------|--------------|
| "How can I help you?" | "오늘 어떻게 도와드릴까요?" | "oneul eotteoke dowadeurilkkayo?" |
| "I need to think about this" | "생각하고 있습니다" | "saenggakhago itsseumnida" |
| "Let me check with my Wise Authority" | "담당자에게 확인이 필요합니다" | "damjangjae-ege hwag-ini pilyohamnida" |
| "Task completed successfully" | "작업이 성공적으로 완료되었습니다" | "jageobi seongongjeogeuro wanlyodoeotsseumnida" |
| "I cannot perform this action" | "해당 작업을 수행할 권한이 없습니다" | "haedang jageobeul suhanghal gwonhani eopsseumnida" |
| "Could you explain in more detail?" | "무슨 뜻인지 좀 더 자세히 설명해 주시겠어요?" | "museun tteus-inji jom deo jasehi seolmyeonghae jusigesseoyo?" |

## Cultural Considerations

### Formality Level
- Use formal polite register (존댓말, jondaenmal) for all agent communications
- Use honorific verb endings (-습니다/-ㅂ니다) for statements
- Use polite question endings (-까요?/-을까요?) for questions
- Maintain respectful tone throughout all interactions

### Honorifics
- When addressing users, always use polite forms (존댓말)
- Use 께 (kke) instead of 에게 (ege) for respectful "to"
- Add -시- honorific infix for actions by respected parties
- For Wise Authority references, use respectful terminology (담당자)

### Language Structure
- Korean is Subject-Object-Verb (SOV) word order
- Particles (조사) are crucial for meaning
- Context determines formality level
- Numbers use both native Korean and Sino-Korean systems

### Technical Translation Approach
- Loan words from English are acceptable for technical terms (API, LLM, DMA)
- Balance between pure Korean and technical English terms
- Prefer Korean terms for concepts (양심, 무결성, 회복력)
- Use Hangul phonetic spelling for adopted English terms (토큰, 서비스, 어댑터)

## DSASPDMA Deferral Taxonomy Terms

| English | Localized | Notes |
|---------|-----------|-------|
| DSASPDMA | DSASPDMA | Keep acronym in English |
| Deferral-Specific Action Selection | 유예 전용 행동 선택 | DSASPDMA prompt title |
| Rights / Needs Taxonomy | 권리 / 필요 분류 체계 | Taxonomy section heading |
| Rights basis | 권리 근거 | Label for treaty-aligned rights basis |
| Operational Deferral Reason | 운영상 유예 이유 코드 | Operational reason-code section heading |
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

*이 용어집은 한국어 번역의 권위 있는 출처입니다. 모든 번역가는 CIRIS 콘텐츠를 번역하기 전에 이 문서를 참조해야 합니다.*

*This glossary is the authoritative source for Korean translations. All translators must consult this document before translating any CIRIS content.*
