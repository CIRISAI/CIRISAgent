# Adaptive Filter Service Telemetry

## Overview
The Adaptive Filter Service is a governance service that provides intelligent message filtering across all CIRIS adapters. It determines message priority, prevents spam, detects mentions and direct messages, and maintains user trust profiles. The service uses graph-based configuration storage and includes comprehensive learning capabilities to adapt to changing patterns over time.

## Telemetry Data Collected

| Metric Name | Type | Storage | Update Frequency | Access Method |
|------------|------|---------|------------------|---------------|
| total_filtered | counter | in-memory | per filtered message | `_collect_custom_metrics()` |
| total_messages_processed | counter | in-memory | per message processed | `_collect_custom_metrics()` |
| false_positive_reports | counter | in-memory | per report | `_collect_custom_metrics()` |
| filter_count | gauge | calculated | on status request | `len(all_triggers)` |
| attention_triggers | gauge | calculated | on status request | `len(attention_triggers)` |
| review_triggers | gauge | calculated | on status request | `len(review_triggers)` |
| llm_filters | gauge | calculated | on status request | `len(llm_filters)` |
| uptime_seconds | gauge | in-memory | on status request | `_calculate_uptime()` |
| request_count | counter | in-memory | per request | `_track_request()` |
| error_count | counter | in-memory | per error | `_track_error()` |
| error_rate | gauge | calculated | on status request | `error_count / request_count` |
| healthy | boolean | in-memory | on status request | `1.0 if started else 0.0` |
| config_version | gauge | config-based | on status request | `config.version` |
| user_profiles_count | gauge | not tracked* | per config update | N/A |
| priority_distribution | histogram | not tracked* | per filtering | N/A |

*Could be added by extending `_collect_custom_metrics()` to include profile and priority statistics.

## Data Structures

### ServiceStatus (from BaseService)
```python
{
    "service_name": "AdaptiveFilterService",
    "service_type": "INFRASTRUCTURE",
    "is_healthy": true,
    "uptime_seconds": 3600.0,
    "metrics": {
        "total_filtered": 1250.0,
        "total_messages_processed": 3420.0,
        "false_positive_reports": 12.0,
        "filter_count": 12.0,
        "attention_triggers": 3.0,
        "review_triggers": 4.0,
        "llm_filters": 3.0,
        "uptime_seconds": 3600.0,
        "request_count": 3420.0,
        "error_count": 5.0,
        "error_rate": 0.0015,
        "healthy": 1.0
    },
    "last_error": "Failed to save config: Connection timeout",
    "last_health_check": "2025-08-14T13:30:00Z"
}
```

### ServiceCapabilities
```python
{
    "service_name": "AdaptiveFilterService",
    "actions": [
        "filter",
        "update_trust",
        "add_filter",
        "remove_filter",
        "get_health"
    ],
    "version": "1.0.0",
    "dependencies": [
        "MemoryService",
        "GraphConfigService",
        "TimeService"
    ],
    "metadata": {
        "description": "Adaptive message filtering with graph memory persistence",
        "features": [
            "spam_detection",
            "trust_tracking",
            "self_configuration",
            "llm_filtering"
        ],
        "filter_types": [
            "regex",
            "keyword",
            "llm_based"
        ],
        "max_buffer_size": 1000,
        "service_name": "AdaptiveFilterService",
        "method_name": "_get_metadata",
        "correlation_id": "550e8400-e29b-41d4-a716-446655440000"
    }
}
```

### FilterStats (Internal Statistics)
```python
{
    "total_messages_processed": 3420,
    "total_filtered": 1250,
    "by_priority": {
        "critical": 45,
        "high": 234,
        "medium": 856,
        "low": 2285,
        "ignore": 0
    },
    "by_trigger_type": {
        "regex": 178,
        "custom": 45,
        "length": 89,
        "frequency": 23,
        "count": 12
    },
    "false_positive_reports": 12,
    "true_positive_confirmations": 89,
    "last_reset": "2025-08-14T00:00:00Z"
}
```

### AdaptiveFilterConfig (Graph-Stored Configuration)
```python
{
    "config_id": "filter_config",
    "version": 3,
    "attention_triggers": [
        {
            "trigger_id": "dm_1",
            "name": "direct_message",
            "pattern_type": "custom",
            "pattern": "is_dm",
            "priority": "critical",
            "description": "Direct messages to agent",
            "enabled": true,
            "effectiveness": 0.95,
            "false_positive_rate": 0.02,
            "true_positive_count": 234,
            "false_positive_count": 5,
            "last_triggered": "2025-08-14T13:25:00Z",
            "created_at": "2025-01-15T10:00:00Z",
            "created_by": "system"
        }
    ],
    "review_triggers": [...],
    "llm_filters": [...],
    "user_profiles": {
        "user_12345": {
            "user_id": "user_12345",
            "message_count": 342,
            "violation_count": 2,
            "helpful_count": 23,
            "first_seen": "2025-01-10T15:30:00Z",
            "last_seen": "2025-08-14T13:20:00Z",
            "trust_score": 0.78,
            "flags": ["frequent_poster"],
            "roles": ["member"],
            "avg_message_length": 127.5,
            "avg_message_interval": 180.2,
            "common_triggers": ["wall_1"]
        }
    },
    "total_messages_processed": 3420,
    "total_issues_caught": 156,
    "last_adjustment": "2025-08-14T12:00:00Z"
}
```

### FilterResult (Processing Output)
```python
{
    "message_id": "msg_1723641234567",
    "priority": "critical",
    "triggered_filters": ["dm_1", "mention_1"],
    "should_process": true,
    "should_defer": false,
    "reasoning": "Message triggered filters: direct_message, at_mention -> critical priority",
    "suggested_action": null,
    "context_hints": [
        {"key": "user_id", "value": "user_12345"},
        {"key": "channel_id", "value": "channel_67890"},
        {"key": "is_dm", "value": "true"},
        {"key": "adapter_type", "value": "discord"},
        {"key": "is_llm_response", "value": "false"}
    ]
}
```

### FilterHealth (Health Assessment)
```python
{
    "is_healthy": true,
    "warnings": [
        "High false positive rate for caps_abuse"
    ],
    "errors": [],
    "stats": {
        "total_messages_processed": 3420,
        "total_filtered": 1250,
        "by_priority": {...},
        "false_positive_reports": 12,
        "last_reset": "2025-08-14T00:00:00Z"
    },
    "config_version": 3,
    "last_updated": "2025-08-14T13:30:00Z"
}
```

## API Access Patterns

### Current Access (via REST API)
- **GET /v1/system/services/status** - Service status with metrics
- **GET /v1/system/services/capabilities** - Service capabilities
- **POST /v1/filters/message** - Filter a message (if exposed)
- **GET /v1/filters/health** - Filter system health (if exposed)
- **POST /v1/filters/triggers** - Add filter trigger (if exposed)
- **DELETE /v1/filters/triggers/{id}** - Remove filter trigger (if exposed)

### Internal Service Access
```python
# Get service metrics
filter_service = get_service(ServiceType.FILTER)
status = filter_service.get_status()
metrics = status.metrics

# Filter a message
result = await filter_service.filter_message(
    message={"content": "Hello @echo", "user_id": "123"},
    adapter_type="discord",
    is_llm_response=False
)

# Check filter health
health = await filter_service.get_health()
if not health.is_healthy:
    logger.warning(f"Filter issues: {health.errors}")

# Add custom filter
trigger = FilterTrigger(
    trigger_id="custom_1",
    name="custom_pattern",
    pattern_type=TriggerType.REGEX,
    pattern=r"\bspam\b",
    priority=FilterPriority.HIGH,
    description="Custom spam detection"
)
success = await filter_service.add_filter_trigger(trigger, "review")
```

## Graph Storage

### Configuration Storage (GraphConfigService)
The service stores its complete configuration in the memory graph using GraphConfigService:

**Storage Key**: `"adaptive_filter.config"`
**Storage Format**: JSON serialization of AdaptiveFilterConfig
**Persistence**: Graph-based with version tracking
**Updates**: Automatic on configuration changes

### User Profile Storage
User trust profiles are embedded within the main configuration and persisted to the graph:
- **Location**: `config.user_profiles[user_id]`
- **Update Pattern**: Modified in-memory, batch saved to graph
- **Retention**: Indefinite until manual cleanup

### Message Buffer (In-Memory Only)
Frequency detection uses in-memory message buffers:
- **Storage**: `_message_buffer[user_id]` dictionary
- **Retention**: Sliding window based on trigger time_window
- **Persistence**: Not persisted - lost on service restart

## Example Usage

### Monitor Filter Performance
```python
async def monitor_filter_performance():
    filter_service = get_service(ServiceType.FILTER)
    status = filter_service.get_status()

    total_processed = status.metrics["total_messages_processed"]
    total_filtered = status.metrics["total_filtered"]
    filter_rate = total_filtered / max(1, total_processed)

    logger.info(f"Filter Stats: {total_filtered}/{total_processed} = {filter_rate:.2%}")

    if filter_rate > 0.5:
        logger.warning("High filtering rate - possible spam attack")
    elif filter_rate < 0.1:
        logger.info("Low filtering rate - system operating normally")
```

### Track Filter Effectiveness
```python
async def analyze_filter_effectiveness():
    filter_service = get_service(ServiceType.FILTER)
    health = await filter_service.get_health()

    # Extract trigger statistics from config (requires direct access)
    if hasattr(filter_service, '_config') and filter_service._config:
        config = filter_service._config

        for trigger in config.attention_triggers + config.review_triggers:
            total_triggers = trigger.true_positive_count + trigger.false_positive_count
            if total_triggers > 10:  # Sufficient sample size
                effectiveness = trigger.true_positive_count / total_triggers

                if effectiveness < 0.3:
                    logger.warning(f"Low effectiveness trigger: {trigger.name} = {effectiveness:.2%}")
                elif trigger.false_positive_rate > 0.2:
                    logger.warning(f"High false positive trigger: {trigger.name} = {trigger.false_positive_rate:.2%}")
```

### User Trust Analysis
```python
async def analyze_user_trust_patterns():
    filter_service = get_service(ServiceType.FILTER)

    # Access user profiles (requires config access)
    if hasattr(filter_service, '_config') and filter_service._config:
        config = filter_service._config

        low_trust_users = []
        for user_id, profile in config.user_profiles.items():
            if profile.trust_score < 0.3 and profile.message_count > 10:
                low_trust_users.append({
                    "user_id": user_id,
                    "trust_score": profile.trust_score,
                    "violations": profile.violation_count,
                    "messages": profile.message_count
                })

        if low_trust_users:
            logger.warning(f"Low trust users detected: {len(low_trust_users)}")
            for user in low_trust_users[:5]:  # Top 5
                logger.info(f"User {user['user_id']}: trust={user['trust_score']:.2f}")
```

### Message Filtering Pipeline Test
```python
async def test_filtering_pipeline():
    filter_service = get_service(ServiceType.FILTER)

    test_cases = [
        {"content": "<@123> hello", "expected_priority": FilterPriority.CRITICAL},
        {"content": "hey echo", "expected_priority": FilterPriority.CRITICAL},
        {"content": "SPAM " * 100, "expected_priority": FilterPriority.HIGH},
        {"content": "normal message", "expected_priority": FilterPriority.LOW},
    ]

    for test in test_cases:
        result = await filter_service.filter_message(
            message={"content": test["content"]},
            adapter_type="discord"
        )

        success = result.priority == test["expected_priority"]
        logger.info(f"Test '{test['content'][:20]}...': {success} (got {result.priority})")

        if not success:
            logger.warning(f"Filter mismatch: expected {test['expected_priority']}, got {result.priority}")
            logger.info(f"Triggered filters: {result.triggered_filters}")
```

## Testing

### Test Files
- `tests/ciris_engine/logic/services/governance/test_filter_simple.py`
- `tests/test_privacy_safeguards.py` (integration tests)
- `tests/ciris_engine/logic/runtime/test_service_initializer.py` (initialization tests)

### Key Test Scenarios
```python
async def test_telemetry_collection():
    # Create service with mock dependencies
    time_service = TimeService()
    await time_service.start()

    service = AdaptiveFilterService(
        memory_service=MockMemory(),
        time_service=time_service,
        config_service=MockConfig()
    )
    await service.start()
    await asyncio.sleep(0.1)  # Allow initialization

    # Test message processing
    messages = [
        {"content": "<@123> help", "is_dm": True},    # Critical
        {"content": "SPAM " * 50},                    # High
        {"content": "normal message"}                 # Low
    ]

    for msg in messages:
        result = await service.filter_message(msg, "discord")
        assert result is not None

    # Check metrics collection
    status = service.get_status()
    assert status.metrics["total_messages_processed"] == 3.0
    assert status.metrics["filter_count"] > 0
    assert status.is_healthy == True

    # Check custom metrics
    custom_metrics = service._collect_custom_metrics()
    assert "attention_triggers" in custom_metrics
    assert "review_triggers" in custom_metrics
    assert "llm_filters" in custom_metrics

    await service.stop()
    await time_service.stop()

async def test_filter_trigger_management():
    # Test adding and removing filters
    service = create_filter_service()

    initial_count = service.get_status().metrics["filter_count"]

    # Add custom trigger
    new_trigger = FilterTrigger(
        trigger_id="test_trigger",
        name="test_pattern",
        pattern_type=TriggerType.REGEX,
        pattern=r"\btest\b",
        priority=FilterPriority.MEDIUM,
        description="Test trigger"
    )

    success = await service.add_filter_trigger(new_trigger, "review")
    assert success == True

    new_count = service.get_status().metrics["filter_count"]
    assert new_count == initial_count + 1

    # Remove trigger
    success = await service.remove_filter_trigger("test_trigger")
    assert success == True

    final_count = service.get_status().metrics["filter_count"]
    assert final_count == initial_count

async def test_health_monitoring():
    service = create_filter_service()

    # Test healthy state
    health = await service.get_health()
    assert health.is_healthy == True
    assert len(health.errors) == 0

    # Test warning conditions (mock high false positive rate)
    if hasattr(service, '_config') and service._config:
        # Modify trigger to simulate high FP rate
        trigger = service._config.attention_triggers[0]
        trigger.false_positive_rate = 0.4  # Above 0.3 threshold

        health = await service.get_health()
        assert len(health.warnings) > 0
        assert any("false positive" in warning.lower() for warning in health.warnings)
```

### Property-Based Testing
```python
from hypothesis import given, strategies as st

@given(content=st.text())
async def test_filter_robustness(content):
    """Ensure filter never crashes on arbitrary input"""
    service = create_filter_service()

    try:
        result = await service.filter_message(
            {"content": content}, "discord"
        )
        # Should always return valid result
        assert result is not None
        assert hasattr(result, 'priority')
        assert hasattr(result, 'triggered_filters')
        assert isinstance(result.should_process, bool)
    except Exception as e:
        pytest.fail(f"Filter crashed on input: {repr(content[:100])} - {e}")
```

## Configuration

### Dependencies
- **MemoryService**: For graph-based data storage (required)
- **GraphConfigService**: For configuration persistence (required)
- **TimeService**: For consistent timestamps (optional but recommended)
- **LLMService**: For semantic analysis (optional)

### Configuration Storage
- **Key**: `"adaptive_filter.config"` in GraphConfigService
- **Format**: AdaptiveFilterConfig JSON serialization
- **Initialization**: Creates default config if none exists
- **Updates**: Automatic save on configuration changes

### Default Configuration
The service creates a comprehensive default configuration including:
- **Attention Triggers**: DM detection, @mentions, name mentions
- **Review Triggers**: Text walls, message flooding, emoji spam, caps abuse
- **LLM Filters**: Prompt injection, malformed JSON, excessive length

### Health Check Thresholds
- **Critical Filters**: Must have at least 1 attention trigger enabled
- **False Positive Rate**: Warnings at >30% for any trigger
- **Effectiveness**: Warnings for triggers <30% effectiveness (after sufficient samples)

## Known Limitations

1. **No Request-Level Tracking**: Individual filter operations not counted via `_track_request()`
2. **Limited Performance Metrics**: No response time measurements for filtering operations
3. **In-Memory Message Buffers**: Lost on service restart, affecting frequency detection
4. **No User Profile Analytics**: Profile statistics not exposed in telemetry
5. **Missing Priority Distribution**: No histogram of message priorities over time
6. **Limited Graph Integration**: Uses graph for config only, not for analytics data
7. **No Real-Time Alerting**: Health issues only detected on status requests
8. **Config Size Growth**: User profiles grow indefinitely without cleanup

## Future Enhancements

1. **Enhanced Metrics Collection**
   - Request-level tracking with `_track_request()` calls in `filter_message()`
   - Response time measurements for filter operations
   - Priority distribution histograms over time
   - User profile statistics (count, trust score distributions)

2. **Advanced Analytics**
   - Filter effectiveness trending and regression detection
   - User behavior pattern analysis and anomaly detection
   - Channel-specific filtering statistics and health scores
   - Trigger performance optimization recommendations

3. **Real-Time Monitoring**
   - Stream key metrics to memory graph for dashboards
   - Automated alerting for filter health issues
   - Performance regression detection and notifications
   - Capacity planning for filter processing load

4. **Operational Intelligence**
   - User trust score trend analysis and risk prediction
   - Filter accuracy improvement via machine learning feedback
   - Adaptive threshold adjustment based on community patterns
   - Cross-channel spam pattern detection and prevention

5. **Data Lifecycle Management**
   - User profile retention policies and automated cleanup
   - Message buffer persistence options for frequency analysis
   - Historical data archival and compression strategies
   - GDPR compliance for user data removal

## Integration Points

- **CommunicationBus**: Receives messages from Discord, API, CLI adapters for filtering
- **GraphConfigService**: Stores and retrieves filter configuration with version control
- **MemoryService**: Could be extended to store analytics data and filter results
- **LLMService**: Optional integration for semantic content analysis and learning
- **TimeService**: Provides consistent timestamps for all filter operations
- **API Layer**: Exposes telemetry via REST endpoints for external monitoring
- **Other Services**: Used by communication adapters for message priority determination

## Monitoring Recommendations

1. **Critical Alerts**
   - `error_rate > 0.05`: High error rate indicating filter malfunction
   - `healthy == 0.0`: Service down or dependencies unavailable
   - `total_filtered / total_messages_processed > 0.8`: Potential spam attack
   - `filter_count == 0`: No active filters (system vulnerable)

2. **Operational Dashboards**
   - Real-time filtering rate and priority distribution
   - Filter trigger effectiveness and false positive rates
   - User trust score distributions and violation trends
   - Service uptime and error patterns over time

3. **Capacity Planning**
   - Message processing throughput vs. system load
   - Filter complexity impact on response times
   - User profile growth rate and memory consumption
   - Configuration size growth and storage requirements

4. **Security Monitoring**
   - Unusual filtering patterns that might indicate attacks
   - High-volume low-trust user activity spikes
   - Filter evasion attempts and pattern evolution
   - Suspicious direct message or mention patterns

## Performance Considerations

1. **Configuration Loading**: Initial startup requires graph query - may block service start
2. **In-Memory Processing**: All filtering logic runs in memory for speed
3. **Regex Performance**: Complex patterns may impact filtering speed at scale
4. **User Profile Growth**: Profiles stored in memory, growing with user base
5. **Graph I/O**: Configuration saves are asynchronous but may impact performance
6. **Message Buffer Management**: Frequency detection requires periodic cleanup

## System Integration

The Adaptive Filter Service acts as the **intelligence gatekeeper** for CIRIS:
- **Message Triage**: Determines which messages require immediate attention vs. deferred processing
- **Spam Protection**: Prevents malicious content from consuming system resources
- **User Reputation**: Builds trust profiles to optimize future interactions
- **Quality Control**: Ensures LLM outputs meet safety and format standards
- **Load Management**: Helps balance system load through intelligent message deferral

Its telemetry is essential for maintaining system responsiveness, preventing abuse, and ensuring high-quality user interactions across all communication channels.
