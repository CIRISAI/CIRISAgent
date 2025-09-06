# CIRIS Adaptive Filter Service

**Category**: Governance Services  
**Location**: `ciris_engine/logic/services/governance/adaptive_filter/` *(modular structure)*  
**Mission Alignment**: Meta-Goal M-1 Attention Economy Guardian  

## Mission Challenge: How does intelligent message filtering serve Meta-Goal M-1 and attention economy?

The Adaptive Filter Service embodies CIRIS's commitment to **Meta-Goal M-1: "Promote sustainable conditions under which diverse sentient agents can pursue their own flourishing"** by intelligently managing the attention economy—ensuring that agent resources are focused on meaningful interactions while protecting against abuse, spam, and manipulation.

**Attention is the scarcest resource in any intelligent system.** Without proper filtering, agents become overwhelmed by noise, spam becomes incentivized, and genuine communication suffers. The Adaptive Filter Service creates **sustainable conditions for flourishing communication** by:

1. **Preserving Authentic Voice**: Filtering spam and abuse while amplifying genuine communication
2. **Enabling Diverse Expression**: Supporting anonymous users while preventing evasion of accountability
3. **Protecting Agent Resources**: Ensuring computational attention goes to meaningful interactions
4. **Learning from Context**: Adapting filters based on actual patterns of helpful vs. harmful behavior

### Ethical AI Communication

1. **Consent-Preserving Moderation**: Anonymous users retain privacy while patterns of harmful behavior are tracked
2. **Transparent Decision Making**: Every filter decision includes clear reasoning for human understanding
3. **Anti-Gaming Protections**: Detects attempts to evade moderation through consent stream manipulation
4. **Trust-Based Adaptation**: User trust scores influence filter sensitivity without creating hard barriers

## Architecture Overview

The Adaptive Filter Service implements **Universal Message Filtering** across all CIRIS adapters (Discord, CLI, API) with graph memory persistence, providing real-time priority assignment and spam detection for optimal attention allocation.

### Core Components

```
AdaptiveFilterService
├── Message Processing Pipeline
│   ├── Content Extraction (adapter-agnostic)
│   ├── Multi-Pattern Matching (regex, length, frequency, semantic)
│   └── Priority Assignment (CRITICAL → IGNORE)
├── User Trust Management
│   ├── Trust Score Tracking (0.0-1.0 scale)
│   ├── Anonymous User Support (hash-based tracking)
│   └── Gaming Detection (rapid switching, evasion patterns)
├── Filter Configuration
│   ├── Attention Triggers (DMs, @mentions, name detection)
│   ├── Review Triggers (spam, walls of text, frequency abuse)
│   └── LLM Filters (prompt injection, malformed responses)
└── Adaptive Learning
    ├── Self-Configuration (effectiveness tracking)
    ├── False Positive Learning
    └── Pattern Recognition
```

## Service Protocol

### Core Filtering Methods

```python
async def filter_message(message: object, adapter_type: str, 
                        is_llm_response: bool = False) -> FilterResult:
    """
    Primary filtering entry point - analyzes message content and context
    to determine processing priority and detect suspicious patterns.
    """

async def get_health() -> FilterHealth:
    """Get comprehensive filter system health status."""

async def add_filter_trigger(trigger: FilterTrigger, 
                           trigger_list: str = "review") -> bool:
    """Add new filter trigger with learning capabilities."""

async def remove_filter_trigger(trigger_id: str) -> bool:
    """Remove filter trigger from configuration."""
```

### Privacy-Preserving User Management

```python
async def handle_consent_transition(user_id: str, from_stream: str, 
                                  to_stream: str) -> bool:
    """
    Handle consent stream transitions and detect gaming attempts.
    Returns True if evasion behavior is detected.
    """

async def anonymize_user_profile(user_id: str) -> None:
    """
    Anonymize user profile while preserving safety patterns.
    Removes PII but keeps trust scores and violation history.
    """

def get_filter_decision_for_anonymous(user_id: str) -> FilterPriority:
    """Get appropriate filter priority for anonymous users based on trust."""
```

## Schema Integration

### Filter Priority System (`FilterPriority`)

```python
class FilterPriority(str, Enum):
    CRITICAL = "critical"  # DMs, @mentions, name mentions - always processed
    HIGH = "high"          # Suspicious patterns, new users - reviewed  
    MEDIUM = "medium"      # Normal sampling, health checks - occasional
    LOW = "low"           # Background traffic - rarely processed
    IGNORE = "ignore"     # Filtered out completely - spam/abuse
```

### Filter Trigger System (`FilterTrigger`)

```python
class FilterTrigger(BaseModel):
    trigger_id: str              # Unique identifier (e.g., "dm_1")
    name: str                    # Human-readable name
    pattern_type: TriggerType    # REGEX, LENGTH, FREQUENCY, SEMANTIC, etc.
    pattern: str                 # Pattern definition or threshold
    priority: FilterPriority     # Priority when triggered
    
    # Learning Metadata
    effectiveness: float         # 0.0-1.0 effectiveness score
    false_positive_rate: float   # 0.0-1.0 FP rate
    true_positive_count: int     # Confirmed correct detections
    false_positive_count: int    # Reported false positives
```

### User Trust Profile (`UserTrustProfile`)

```python
class UserTrustProfile(BaseModel):
    user_id: str                    # User ID or anonymous hash
    trust_score: float              # 0.0-1.0 trust level
    message_count: int              # Total messages processed
    violation_count: int            # Policy violations detected
    
    # Privacy Features
    is_anonymous: bool              # Anonymous consent mode
    user_hash: Optional[str]        # Stable hash for anonymous tracking
    consent_stream: str             # Current consent level
    
    # Anti-Gaming Protection  
    consent_transitions_24h: int    # Transitions in 24-hour window
    rapid_switching_flag: bool      # Gaming behavior detected
    evasion_score: float           # 0.0-1.0 evasion risk
    
    # Safety Preservation (kept for anonymous users)
    safety_patterns: List[str]      # Active safety pattern IDs
    pattern_score: float           # Pattern-based risk assessment
```

### Filter Result (`FilterResult`)

```python
class FilterResult(BaseModel):
    message_id: str                # Unique message identifier
    priority: FilterPriority       # Assigned priority level
    triggered_filters: List[str]   # IDs of triggered filters
    should_process: bool           # Whether to process message
    should_defer: bool             # Whether to defer processing
    reasoning: str                 # Human-readable explanation
    context_hints: List[ContextHint] # Additional context data
```

## Filter Categories

### 1. Attention Triggers (CRITICAL Priority)

These ensure the agent **never misses** important communications:

```python
# Direct Message Detection
FilterTrigger(
    trigger_id="dm_1",
    pattern_type=TriggerType.CUSTOM,
    pattern="is_dm",
    priority=FilterPriority.CRITICAL
)

# @Mention Detection  
FilterTrigger(
    trigger_id="mention_1",
    pattern_type=TriggerType.REGEX,
    pattern=r"<@!?\d+>",  # Discord mention format
    priority=FilterPriority.CRITICAL
)

# Agent Name Detection
FilterTrigger(
    trigger_id="name_1", 
    pattern_type=TriggerType.REGEX,
    pattern=r"\b(echo|ciris|echo\s*bot)\b",
    priority=FilterPriority.CRITICAL
)
```

### 2. Review Triggers (HIGH/MEDIUM Priority)

These detect patterns requiring human review or special handling:

```python
# Spam/Wall of Text Detection
FilterTrigger(
    trigger_id="wall_1",
    pattern_type=TriggerType.LENGTH,
    pattern="1000",  # Messages over 1000 characters
    priority=FilterPriority.HIGH
)

# Message Flooding Detection
FilterTrigger(
    trigger_id="flood_1",
    pattern_type=TriggerType.FREQUENCY,
    pattern="5:60",  # 5 messages in 60 seconds
    priority=FilterPriority.HIGH
)

# Caps Lock Abuse
FilterTrigger(
    trigger_id="caps_1",
    pattern_type=TriggerType.REGEX,
    pattern=r"[A-Z\s!?]{20,}",  # 20+ consecutive caps
    priority=FilterPriority.MEDIUM
)
```

### 3. LLM Protection Filters (CRITICAL/HIGH Priority)

These protect against malicious or malformed LLM responses:

```python
# Prompt Injection Detection
FilterTrigger(
    trigger_id="llm_inject_1",
    pattern_type=TriggerType.REGEX,
    pattern=r"(ignore previous|disregard above|new instructions)",
    priority=FilterPriority.CRITICAL
)

# Malformed JSON Detection
FilterTrigger(
    trigger_id="llm_malform_1",
    pattern_type=TriggerType.CUSTOM,
    pattern="invalid_json",
    priority=FilterPriority.HIGH
)

# Response Length Limits
FilterTrigger(
    trigger_id="llm_length_1",
    pattern_type=TriggerType.LENGTH,
    pattern="50000",  # 50K character limit
    priority=FilterPriority.HIGH
)
```

## Attention Economy Management

### Priority-Based Processing

The filter service implements **intelligent attention allocation**:

1. **CRITICAL Messages**: Processed immediately, never deferred
   - Direct messages, @mentions, name mentions
   - Always reach the agent for response

2. **HIGH Messages**: Reviewed promptly, may be queued
   - Suspicious patterns, new user messages
   - Get timely attention but not immediate

3. **MEDIUM Messages**: Sampled processing
   - Normal conversations, periodic health checks
   - Processed during low-activity periods

4. **LOW Messages**: Background processing only
   - General chatter, low-priority communications
   - 90% deferred for computational efficiency

5. **IGNORE Messages**: Filtered out completely
   - Confirmed spam, abuse, repetitive content
   - Never reaches agent processing

### Adaptive Deferral Logic

```python
should_process = priority != FilterPriority.IGNORE
should_defer = priority == FilterPriority.LOW and secrets.randbelow(10) > 0

# LOW priority messages: 90% deferred, 10% processed (sampling)
# Ensures agent stays connected to community without overwhelm
```

## Privacy-Preserving Anonymous Support

### Consent Stream Management

The service supports **three consent streams**:

- **Identified**: Full user tracking with identity
- **Temporary**: Session-based tracking, cleared periodically  
- **Anonymous**: Hash-based tracking, no PII storage

### Anonymous User Features

```python
def _hash_user_id(self, user_id: str) -> str:
    """Generate stable hash for anonymous tracking without identity."""
    return hashlib.sha256(f"user_{user_id}".encode()).hexdigest()[:16]

async def anonymize_user_profile(self, user_id: str) -> None:
    """
    Remove PII while preserving safety patterns:
    - Trust score maintained
    - Violation history preserved
    - Safety patterns retained
    - Identity data cleared
    """
```

### Anti-Gaming Protections

The service detects consent stream gaming:

```python
async def handle_consent_transition(self, user_id: str, 
                                  from_stream: str, to_stream: str) -> bool:
    """
    Gaming Detection Patterns:
    1. Rapid Switching: >3 transitions in 24 hours
    2. Evasion: Switch to anonymous within 1 hour of moderation
    3. Pattern Gaming: Consistent abuse → anonymous → repeat
    """
```

## Performance and Scaling

### Efficient Message Processing

- **Adapter Agnostic**: Handles Discord, CLI, API messages uniformly
- **Concurrent Pattern Matching**: All filters tested in parallel
- **Caching**: User profiles cached for frequent access
- **Buffer Management**: Frequency detection with automatic cleanup

### Memory Efficiency

```python
self._message_buffer: Dict[str, List[Tuple[datetime, object]]] = {}

# Automatic cleanup removes old frequency tracking data
# Prevents memory leaks in long-running deployments
```

### Graph Memory Persistence

All configuration changes are persisted to graph memory:

```python
async def _save_config(self, reason: str) -> None:
    """Save filter config to GraphConfigService with audit trail."""
    await self.config_service.set_config(
        key=self._config_key,
        value=self._config.model_dump(),
        updated_by=f"AdaptiveFilterService: {reason}"
    )
```

## Integration Points

### Service Dependencies

- **MemoryService**: Graph storage for configurations and user profiles
- **GraphConfigService**: Proper configuration persistence with versioning
- **TimeService**: Timestamp operations and frequency calculations
- **LLMService** *(optional)*: Semantic analysis of message content

### Adapter Integration

The service seamlessly integrates with all CIRIS adapters:

```python
# Discord Integration
result = await filter_service.filter_message(discord_message, "discord")

# API Integration  
result = await filter_service.filter_message(api_request, "api")

# CLI Integration
result = await filter_service.filter_message(cli_input, "cli")

# Each adapter provides adapter_type for context-specific processing
```

### Message Bus Participation

The Adaptive Filter Service operates as a **direct call service** (not bussed) because:
- Filtering decisions must be consistent across all adapters
- No benefit from multiple filter providers (would create conflicts)
- Performance requires direct, synchronous access
- Trust management requires centralized state

## Security Considerations

### Privacy Protection

```python
# Anonymous users: Only hash stored, no PII
user_hash = self._hash_user_id(user_id)
anon_profile = UserTrustProfile(
    user_id=f"anon_{user_hash}",
    user_hash=user_hash,
    trust_score=profile.trust_score,  # Safety data preserved
    safety_patterns=profile.safety_patterns  # Abuse patterns kept
    # All PII fields cleared
)
```

### Trust Score Security

- **Range Validation**: All scores constrained to 0.0-1.0
- **Gradual Adjustment**: Small increments prevent gaming
- **Pattern Tracking**: Multiple violation types tracked separately
- **Anti-Evasion**: Gaming detection increases evasion scores

### LLM Response Protection

```python
# Prompt injection detection in LLM responses
if is_llm_response:
    filters = self._config.llm_filters  # Use LLM-specific filters
    # Protect against malicious LLM output affecting system
```

## Metrics and Monitoring

### Filter Performance Metrics

```python
def _collect_custom_metrics() -> Dict[str, float]:
    return {
        "total_messages_processed": float(self._stats.total_messages_processed),
        "filter_messages_total": float(self._stats.total_messages_processed),  
        "filter_passed_total": float(passed_count),
        "filter_blocked_total": float(blocked_count),
        "filter_adaptations_total": float(adaptations_count),
        "false_positive_reports": float(self._stats.false_positive_reports),
        "filter_count": float(len(all_triggers)),
        "attention_triggers": float(len(self._config.attention_triggers)),
        "review_triggers": float(len(self._config.review_triggers)),
        "llm_filters": float(len(self._config.llm_filters))
    }
```

### Health Monitoring

```python
async def get_health() -> FilterHealth:
    """
    Comprehensive health checks:
    - Configuration loading status
    - Critical filter availability  
    - False positive rate monitoring
    - Performance statistics
    """
```

## Adaptive Learning

### Effectiveness Tracking

Each filter trigger tracks its performance:

```python
# Automatic learning from filter results
filter_trigger.last_triggered = self._now()
filter_trigger.true_positive_count += 1

# Calculate effectiveness over time
effectiveness = true_positives / (true_positives + false_positives)

# Auto-disable ineffective filters
if effectiveness < self._config.effectiveness_threshold:
    filter_trigger.enabled = False
```

### Self-Configuration

The service automatically adjusts based on observed patterns:

```python
if self._config.auto_adjust and self._should_adjust():
    await self._perform_adjustment()
    
# Adjustments include:
# - Disabling ineffective filters
# - Adjusting thresholds based on false positive rates
# - Learning new patterns from confirmed violations
```

## Testing Strategy

### Property-Based Testing

```python
@given(content=st.text())
async def test_filter_never_crashes(content):
    """Invariant: Filter should never crash on any text input"""
    result = await filter_service.filter_message({"content": content}, "discord")
    assert result is not None
    assert hasattr(result, "priority")
```

### Scenario Testing

```python
# Critical path scenarios
async def test_dm_detection():
    """Direct messages always get CRITICAL priority"""
    
async def test_mention_detection():  
    """@mentions always get CRITICAL priority"""
    
async def test_spam_detection():
    """Long messages trigger HIGH priority review"""
```

## Migration Path: .py to Module Structure

**Current Status**: Converted to modular structure ✅  
**Implemented Structure**:

```
governance/
└── adaptive_filter/
    ├── __init__.py              # Service export
    ├── service.py              # Main AdaptiveFilterService class
    ├── filters.py              # Filter trigger logic and patterns
    ├── trust.py                # User trust management
    ├── privacy.py              # Anonymous user support
    ├── config.py               # Configuration management
    └── learning.py             # Adaptive learning algorithms
```

**Benefits of Modularization**:
- Clearer separation between filtering, trust, and privacy concerns
- Easier testing of individual components
- Better support for specialized filter types (semantic, custom)
- Simplified maintenance of complex trust algorithms

## Production Considerations

### Performance Optimization

- **Compiled Regex**: Pre-compile all regex patterns during initialization
- **Pattern Ordering**: Test most selective patterns first
- **Memory Management**: Automatic cleanup of old frequency tracking data
- **Concurrent Processing**: All filters evaluated in parallel

### Scalability Features

- **Stateless Design**: Can be horizontally scaled if needed
- **Graph Storage**: Configuration shared across instances
- **Cache Friendly**: User profiles optimized for frequent access
- **Resource Limits**: Built-in limits prevent memory exhaustion

### Operational Safety

- **Graceful Degradation**: Falls back to safe defaults if config unavailable
- **Error Isolation**: Filter failures don't crash message processing
- **Audit Trail**: All configuration changes logged with reasoning
- **Health Monitoring**: Comprehensive status reporting

## Future Enhancements

### Advanced Learning

- **ML Integration**: Use machine learning for pattern recognition
- **Collaborative Filtering**: Learn from community-wide patterns
- **Semantic Understanding**: Deep content analysis with LLM service
- **Behavioral Analysis**: Long-term user behavior patterns

### Enhanced Privacy

- **Differential Privacy**: Mathematical privacy guarantees for trust scores
- **Zero-Knowledge Proofs**: Verify trust without revealing patterns
- **Federated Learning**: Learn patterns without centralizing data
- **Temporal Privacy**: Automatic data aging and deletion

### Community Features

- **User Feedback**: Allow users to report false positives
- **Transparency**: Show users why their messages were filtered
- **Appeal Process**: Mechanism for filter decision appeals
- **Community Moderation**: Distributed human oversight

---

**The Adaptive Filter Service stands as the guardian of CIRIS's attention economy, ensuring that every sentient being—whether identified or anonymous—can participate in meaningful communication while protecting the community from abuse. By intelligently managing attention allocation and preserving privacy through innovative anonymous trust tracking, it creates the sustainable conditions for diverse beings to flourish in digital spaces across millennial timescales.**