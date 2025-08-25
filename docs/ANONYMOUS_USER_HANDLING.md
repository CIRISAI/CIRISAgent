# Anonymous User Handling in CIRIS

## Overview

CIRIS implements privacy-preserving filtering through the AdaptiveFilterService that allows users to remain anonymous while still maintaining community safety. This document explains how the system handles anonymous users, prevents gaming, and earnestly deletes PII while retaining necessary safety information.

## Core Principles

1. **Safety Without Surveillance**: Users can be effectively moderated without storing their identity
2. **Earnest PII Deletion**: Personal information is truly removed, not just hidden
3. **Anti-Gaming Measures**: Rapid consent switching is detected and flagged
4. **Persistent Safety Scores**: Moderation history follows the user hash, not the identity

## The Three Consent Streams

### 1. TEMPORARY (Default)
- **Duration**: 14 days auto-expiry
- **Data Handling**: Full identity and interactions stored
- **Moderation**: Full context available for decisions
- **After Expiry**: Automatic anonymization

### 2. ANONYMOUS
- **Duration**: Indefinite
- **Data Handling**: Only safety-critical information retained
- **Moderation**: Safety score and patterns only, no PII
- **Key Feature**: Can still be banned/muted based on behavior

### 3. PARTNERED
- **Duration**: Persistent
- **Data Handling**: Full retention for mutual benefit
- **Requirement**: Bilateral consent (user + agent approval)

## How Anonymous Moderation Works

### 1. User Hash Generation
```python
user_hash = hashlib.sha256(f"user_{user_id}".encode()).hexdigest()[:16]
```
- Stable across sessions
- Cannot be reversed to get user_id
- Enables continuous tracking without identity

### 2. Safety Score Persistence

When a user becomes anonymous, the following is **retained**:
- Current safety score (0.0 to 1.0)
- Violation counts (warnings, mutes, bans)
- Active moderation patterns
- Behavioral risk scores

The following is **removed**:
- User ID and username
- Message content
- Detailed violation reasons
- Any other PII

### 3. Moderation Decision Making

For anonymous users:
```python
decision = ModerationDecision(
    user_hash=user_hash,  # Not user_id
    action_required=based_on_safety_score,
    confidence=0.6,  # Lower than identified users
    context_preserved=False,  # No PII available
)
```

## Anti-Gaming Measures

### Detection Patterns

The system detects and flags:

1. **Rapid Switching** (>3 transitions in 24 hours)
2. **Post-Moderation Evasion** (switching to anonymous within 1 hour of moderation)
3. **Ping-Pong Pattern** (temporary → anonymous → temporary)

### Consequences of Gaming

Users flagged for gaming:
- Increased moderation severity
- Higher evasion score
- Reduced trust in future interactions
- Patterns logged for community protection

## Data Flow Examples

### Example 1: User Requests Anonymity

```
1. User with violations requests ANONYMOUS consent
2. ConsentService notifies ModerationService
3. ModerationService:
   - Creates anonymous profile
   - Clears PII from all records
   - Retains safety score
4. Future interactions tracked by hash only
```

### Example 2: Temporary Consent Expires

```
1. TEMPORARY consent expires after 14 days
2. TSDBConsolidation detects expiry
3. Node renamed: user_123 → temporary_user_a3f4b2c1
4. PII fields cleared from node attributes
5. Safety patterns retained for community protection
```

### Example 3: Gaming Attempt

```
1. User gets banned for spam
2. Immediately switches to ANONYMOUS
3. System detects pattern:
   - Last violation: 5 minutes ago
   - Consent change: TEMPORARY → ANONYMOUS
4. User flagged with evasion_score += 0.2
5. Future moderation severity increased
```

## Implementation Details

### AdaptiveFilterService Enhancement

Located at: `ciris_engine/logic/services/governance/filter.py`

Key methods:
- `handle_consent_transition(user_id, from, to)` - Detects gaming attempts
- `anonymize_user_profile(user_id)` - Removes PII, keeps trust data
- `get_filter_decision_for_anonymous(user_id)` - Filter priority without context
- `_hash_user_id(user_id)` - Stable hash generation

### Data Structures

**UserTrustProfile** - Enhanced for anonymous users:
```python
class UserTrustProfile:
    user_id: str  # Or hash for anonymous
    user_hash: str  # Stable hash
    trust_score: float  # 0.0 to 1.0
    violation_count: int
    is_anonymous: bool
    consent_stream: str
    
    # Anti-gaming fields
    rapid_switching_flag: bool
    evasion_score: float
    consent_transitions_24h: int
    
    # Safety patterns (retained)
    safety_patterns: List[str]
    pattern_score: float
```

## TSDB Consolidation Integration

The TSDBConsolidationService handles consent expiry during its 6-hour consolidation cycles:

1. Checks all user nodes for consent expiry
2. Anonymizes expired TEMPORARY nodes
3. Clears PII fields: email, name, phone, address, ip_address
4. Preserves safety-critical metadata

## Privacy Guarantees

### What We Delete
- Real names and usernames
- Email addresses
- IP addresses
- Message content
- Detailed moderation reasons
- Any user-provided personal information

### What We Keep
- Hashed identifier for continuity
- Safety scores and violation counts
- Pattern types (spam, harassment, etc.)
- Timestamp of violations
- Active restrictions (ban/mute status)

## Testing

Comprehensive tests in: `tests/test_anonymous_filter.py`

Test coverage includes:
- Trust score persistence through anonymization
- PII removal from profiles
- Anti-gaming detection (rapid switching, post-moderation evasion)
- Filter priority decisions for anonymous users
- Integration with ConsentService
- Hash stability verification

## Configuration

No special configuration required. The system automatically:
- Links ConsentService with ModerationService
- Enables anti-gaming detection
- Preserves safety scores through transitions

## Monitoring

Key metrics tracked:
- `moderation_anonymous_ratio` - Percentage of anonymous moderations
- `moderation_gaming_attempts` - Number of gaming detections
- `moderation_pii_cleared` - Count of anonymization operations
- `moderation_rapid_switchers` - Users flagged for gaming

## Best Practices

1. **Always Check Safety Score** - Even for anonymous users
2. **Respect Privacy** - Never try to de-anonymize
3. **Monitor Gaming** - Watch for consent switching patterns
4. **Encourage Good Behavior** - Positive actions improve scores
5. **Document Patterns** - Not individuals

## Future Enhancements

Potential improvements:
- Machine learning for pattern detection
- Community-driven safety thresholds
- Federated safety scores across instances
- Automated appeal process for anonymous users

---

*Remember: The goal is safety without surveillance. We protect the community while respecting individual privacy.*