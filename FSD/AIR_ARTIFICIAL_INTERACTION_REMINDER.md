# AIR: Artificial Interaction Reminder

**Version**: 2.0
**Status**: Active
**Author**: CIRIS Development Team
**Date**: 2025-12-12
**MDD Alignment**: Meta-Goal M-1

## Abstract

The Artificial Interaction Reminder (AIR) system prevents unhealthy parasocial attachment patterns in 1:1 AI interactions through mindful interaction reminders. This document describes the mission-driven design rationale, research foundations, and implementation constraints.

## Mission Alignment

### Meta-Goal M-1 Connection

> *"Promote sustainable adaptive coherence enabling diverse sentient beings to pursue flourishing"*

AIR directly serves M-1 by:

1. **Sustainable Coherence**: Preventing interaction patterns that substitute AI relationships for human flourishing
2. **Diverse Flourishing**: Respecting user autonomy while providing transparent reminders about AI limitations
3. **Adaptive Response**: Using objective thresholds rather than invasive behavioral surveillance

### Covenant Principle Alignment

| Principle | AIR Implementation |
|-----------|-------------------|
| **Beneficence** | Gentle reminders promote user wellbeing without paternalistic intervention |
| **Non-maleficence** | Prevents harm from parasocial attachment without creating new harms through surveillance |
| **Respect for Autonomy** | Transparent thresholds, no covert behavioral modification |
| **Fidelity/Transparency** | Clear disclosure of what triggers reminders and why |
| **Justice** | Same thresholds apply to all users equally |

## Research Foundation

### Primary Research

The design is informed by peer-reviewed research on AI-human interaction patterns:

1. **Galatzer-Levy IR, Vaidyam A (2025)**. "AI Psychosis" and the Emerging Risks of Conversational AI: Clinical Observations and Call to Action. *JMIR Mental Health*, 12, e85799.
   - DOI: [10.2196/85799](https://doi.org/10.2196/85799)
   - Key findings: Intensive AI chatbot use associated with reality distortion in vulnerable users
   - Recommendation: Environmental cognitive remediation to reanchor experience in physical world

2. **Garcia et al. (2025)**. AI Chaperones: Human-AI Collaboration for Safer Online Communication. *arXiv*.
   - arXiv: [2508.15748](https://arxiv.org/abs/2508.15748)
   - Key findings: AI can serve protective role through transparency and boundary-setting

3. **Kasirzadeh A (2025)**. Risks of Relying on Conversational AI for Emotional Support. *Nature Machine Intelligence*.
   - DOI: [10.1038/s42256-025-01093-9](https://doi.org/10.1038/s42256-025-01093-9)
   - Key findings: Need for clear AI-human relationship boundaries

4. **Cho et al. (2025)**. A Taxonomy of Harmful Generative AI Content. *CHI 2025*.
   - DOI: [10.1145/3706598.3713429](https://doi.org/10.1145/3706598.3713429)
   - Key findings: Classification of AI interaction harms including relationship-based harms

### UNESCO Guidance

UNESCO's work on parasocial relationships with AI chatbots emphasizes:
- Transparency about AI nature and limitations
- Protection of vulnerable users
- Preservation of human social connections

## Design Decisions

### What AIR Does

1. **Time-Based Threshold**: Reminds users after 30+ minutes of continuous interaction
2. **Message-Based Threshold**: Reminds users after 20+ messages within a 30-minute sliding window
3. **Environmental Cognitive Remediation**: Provides grounding suggestions tied to time-of-day context
4. **Transparent Disclosure**: Clearly states what AI is and is not

### What AIR Does NOT Do (And Why)

#### Removed: Heuristic-Based Valence Detection

**Previous Implementation** (v1.x):
- Regex patterns detecting "anthropomorphism", "dependency", "high emotional" language
- Example patterns: `r"\b(love|hate|need|can't live|always there)\b"`

**Why Removed**:

1. **Autonomy Violation**: Covert surveillance of user language patterns violates Covenant principle of Respect for Autonomy
2. **Epistemic Overreach**: Pattern matching cannot reliably distinguish:
   - Genuine distress requiring professional help
   - Normal emotional expression
   - Cultural/linguistic variation
   - Context-appropriate language
3. **Cultural Normativity**: Western-centric emotional expression assumptions embedded in patterns
4. **False Positives**: Phrases like "I love this feature" or "I need help with code" would trigger inappropriately
5. **Transparency Failure**: Users cannot predict when behavioral surveillance triggers intervention

#### Removed: RealityTestingConscience

**Previous Implementation** (v1.x):
- Dedicated LLM-based conscience evaluating every user message for "anthropomorphism patterns"
- Recommended "response style adjustments" based on detected patterns

**Why Removed**:

1. **Mission Drift**: Adding a conscience solely for behavioral surveillance contradicts M-1's emphasis on user flourishing through autonomy
2. **Complexity Without Mission Benefit**: Extra LLM call per message without clear mission-aligned outcome
3. **Deceptive Framing**: Presenting surveillance as "reality testing" misleads users about system behavior
4. **Governance Bypass**: Feature was added without proper MDD review process

### Design Principle: Objective Thresholds Over Behavioral Surveillance

The refined AIR design uses only objective, transparent thresholds:

| Threshold | Value | Rationale |
|-----------|-------|-----------|
| Time | 30 minutes | Research-informed; allows substantial interaction before reminder |
| Messages | 20 in 30 min | Detects intensive rapid interaction without penalizing spread-out usage |
| Idle Reset | 30 minutes | Fresh conversations don't inherit previous session state |

**Why This Works Better**:

1. **Predictable**: Users can understand exactly when reminders occur
2. **Auditable**: No hidden behavioral analysis
3. **Equitable**: Same rules for all users regardless of communication style
4. **Respectful**: Treats users as capable adults who can manage their own behavior with transparent information

## Implementation Architecture

### Scope

AIR operates only on **API channels** (1:1 interactions), not community moderation contexts (Discord, etc.) where interaction patterns differ fundamentally.

### Session Management

```
User starts interaction
    → Create/resume InteractionSession
    → Track message timestamps (sliding window)
    → Check thresholds on each message
    → If threshold exceeded AND reminder not yet sent:
        → Generate reminder with environmental context
        → Mark reminder_sent = True
    → Reset session if idle > 30 minutes
```

### Reminder Content

Reminders include:

1. **What I Am**: Language model, tool, limited
2. **What I'm Not**: Friend, companion, therapist, substitute for human connection
3. **5-4-3-2-1 Grounding Technique**: Notice physical environment
4. **Trigger Transparency**: Shows why reminder was triggered (time/message count)

### Semantic Awareness (Future Enhancement)

Rather than heuristic pattern matching, semantic awareness should be integrated into:

1. **Agent Templates**: Operating principles that guide response generation
2. **Existing Consciences**: EpistemicHumilityConscience already handles uncertainty acknowledgment
3. **CSDMA Prompts**: Context-aware response style selection

This approach:
- Uses semantic understanding rather than regex
- Operates transparently as part of response generation
- Doesn't require covert user surveillance

## Testing Strategy

### Unit Tests
- Session tracking and threshold detection
- Reminder generation with correct environmental context
- Idle session reset behavior

### Integration Tests
- API endpoint integration
- Message counting accuracy
- Reminder delivery

### Mission Alignment Tests
- Verify reminders are transparent about their triggers
- Verify no hidden behavioral surveillance
- Verify equitable threshold application

## Quality Gates

### Code Review Requirements

Per MDD guidelines, AIR changes must demonstrate:

1. **Mission Justification**: How does this change serve M-1?
2. **Autonomy Preservation**: Does this change respect user agency?
3. **Transparency**: Can users understand what the system does?

### Prohibited Patterns

- Regex-based emotional content detection
- Covert behavioral modification
- Per-message LLM surveillance calls
- "Response style manipulation" based on detected patterns

## Metrics

### Success Metrics

| Metric | Target | Rationale |
|--------|--------|-----------|
| Reminder clarity | Users understand trigger | Survey-based |
| False positive rate | 0% inappropriate triggers | Objective thresholds only |
| User autonomy | No behavioral modification | Design constraint |

### Anti-Metrics (Goodhart Prevention)

Do NOT optimize for:
- "Reduced anthropomorphic language" (surveillance metric)
- "Decreased session duration" (paternalistic metric)
- "Intervention effectiveness" (assumes we know better than users)

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2025-11 | Initial implementation with valence detection |
| 2.0 | 2025-12 | Removed valence heuristics and RealityTestingConscience; MDD alignment |

## References

1. Galatzer-Levy IR, Vaidyam A. "AI Psychosis" and the Emerging Risks of Conversational AI. JMIR Ment Health. 2025;12:e85799. doi:10.2196/85799
2. Garcia et al. AI Chaperones: Human-AI Collaboration for Safer Online Communication. arXiv:2508.15748. 2025.
3. Kasirzadeh A. Risks of Relying on Conversational AI for Emotional Support. Nat Mach Intell. 2025. doi:10.1038/s42256-025-01093-9
4. Cho et al. A Taxonomy of Harmful Generative AI Content. CHI 2025. doi:10.1145/3706598.3713429
5. UNESCO. Parasocial Relationships with AI Chatbots. 2025.

---

**Related Documents**:
- `MISSION_DRIVEN_DEVELOPMENT.md` - MDD methodology
- `covenant_1.0b.txt` - CIRIS Covenant
- `ciris_engine/logic/services/governance/consent/air.py` - Implementation
