# Self Observation Service Telemetry

## Overview
The Self Observation Service is a governance service that enables autonomous self-monitoring, pattern detection, and adaptive learning within the CIRIS ecosystem. It coordinates between identity variance monitoring, pattern analysis, and telemetry collection to provide continuous introspection capabilities while maintaining identity stability within a 20% variance threshold. The service manages two critical sub-services: IdentityVarianceMonitor and PatternAnalysisLoop, which work together to ensure safe autonomous adaptation.

## Telemetry Data Collected

| Metric Name | Type | Storage | Update Frequency | Access Method |
|------------|------|---------|------------------|---------------|
| adaptation_count | counter | in-memory | per cycle | `get_status().custom_metrics` |
| consecutive_failures | counter | in-memory | per failure | `get_status().custom_metrics` |
| emergency_stop | boolean | in-memory | on status request | `get_status().custom_metrics` |
| changes_since_last_adaptation | counter | calculated | on status request | `get_status().custom_metrics` |
| current_variance | gauge | in-memory | per variance check | `get_status().custom_metrics` |
| uptime_seconds | gauge | calculated | on status request | `_calculate_uptime()` |
| request_count | counter | in-memory | per request | `_track_request()` |
| error_count | counter | in-memory | per error | `_track_error()` |
| error_rate | gauge | calculated | on status request | `error_count / request_count` |
| healthy | boolean | calculated | on status request | `is_healthy()` |
| task_run_count | counter | in-memory | per scheduled run | BaseScheduledService |
| task_error_count | counter | in-memory | per task error | BaseScheduledService |
| last_task_run | timestamp | in-memory | per scheduled run | BaseScheduledService |
| patterns_detected | counter | sub-service | via pattern loop | `get_detected_patterns()` |
| insights_generated | counter | sub-service | via pattern loop | `get_pattern_insights()` |
| variance_reports | counter | sub-service | via variance monitor | `check_variance()` |
| wa_review_triggers | counter | memory graph | per review | stored as graph nodes |

## Data Structures

### ServiceStatus (from BaseScheduledService)
```python
{
    "service_name": "SelfObservationService",
    "service_type": "visibility",
    "is_healthy": true,
    "uptime_seconds": 7200.0,
    "custom_metrics": {
        "adaptation_count": 5.0,
        "consecutive_failures": 0.0,
        "emergency_stop": 0.0,
        "changes_since_last_adaptation": 2.0,
        "current_variance": 0.15,
        "task_run_count": 12.0,
        "task_error_count": 0.0,
        "last_task_run": 1723641000.0
    },
    "last_error": null,
    "last_health_check": "2025-08-14T13:30:00Z"
}
```

### ServiceCapabilities
```python
{
    "service_name": "SelfObservationService",
    "actions": [
        "adapt_configuration",
        "monitor_identity",
        "process_feedback",
        "emergency_stop"
    ],
    "version": "1.0.0",
    "dependencies": [
        "variance_monitor",
        "feedback_loop",
        "telemetry_service"
    ],
    "metadata": {
        "description": "Autonomous self-configuration and adaptation service",
        "features": [
            "autonomous_adaptation",
            "identity_variance_monitoring",
            "pattern_detection",
            "configuration_feedback",
            "safe_adaptation",
            "wa_review_integration",
            "emergency_stop",
            "adaptation_history",
            "experience_processing"
        ],
        "safety_features": [
            "emergency_stop",
            "wa_review",
            "change_limits"
        ]
    }
}
```

### ObservationStatus
```python
{
    "is_active": true,
    "current_state": "learning",
    "cycles_completed": 5,
    "last_cycle_at": "2025-08-14T13:30:00Z",
    "current_variance": 0.15,
    "patterns_in_buffer": 0,
    "pending_proposals": 0,
    "average_cycle_duration_seconds": 120.0,
    "total_changes_applied": 8,
    "rollback_rate": 0.0,
    "identity_stable": true,
    "time_since_last_change": 3600.0,
    "under_review": false,
    "review_reason": null
}
```

### ObservationCycleResult
```python
{
    "cycle_id": "variance_check_1723641000",
    "state": "learning",
    "started_at": "2025-08-14T13:30:00Z",
    "completed_at": "2025-08-14T13:32:00Z",
    "patterns_detected": 3,
    "proposals_generated": 0,
    "proposals_approved": 0,
    "proposals_rejected": 0,
    "changes_applied": 0,
    "rollbacks_performed": 0,
    "variance_before": 0.12,
    "variance_after": 0.15,
    "success": true,
    "requires_review": false,
    "error": null
}
```

### LearningSummary
```python
{
    "total_patterns": 23,
    "patterns_by_type": {
        "temporal": 8,
        "frequency": 7,
        "performance": 5,
        "error": 3
    },
    "action_frequencies": {
        "process_thought": 156,
        "memory_query": 89,
        "pattern_analysis": 23
    },
    "most_used_actions": [
        "process_thought",
        "memory_query",
        "pattern_analysis"
    ],
    "least_used_actions": [
        "emergency_stop",
        "rollback_change"
    ],
    "insights_count": 12,
    "recent_insights": [
        "High memory query frequency during evening hours",
        "Pattern analysis triggered by error clustering"
    ],
    "learning_rate": 2.3,
    "recommendation": "continue"
}
```

## API Access Patterns

### Current Access (via REST API)
- **GET /v1/system/services/status** - Service status with metrics
- **GET /v1/system/services/capabilities** - Service capabilities
- **GET /v1/self-observation/status** - Detailed observation status
- **POST /v1/self-observation/trigger-cycle** - Manually trigger analysis cycle
- **GET /v1/self-observation/patterns** - Get detected patterns
- **GET /v1/self-observation/insights** - Get pattern insights
- **GET /v1/self-observation/learning-summary** - Get learning progress

### Internal Service Access
```python
# Get service metrics
self_observation = get_service(ServiceType.VISIBILITY)  # Maps to self-observation
status = self_observation.get_status()
observation_status = await self_observation.get_adaptation_status()

# Trigger analysis cycle
cycle_result = await self_observation.trigger_adaptation_cycle()

# Get learning data
patterns = await self_observation.get_detected_patterns(hours=24)
insights = await self_observation.get_pattern_insights(limit=10)
summary = await self_observation.get_learning_summary()

# Pattern analysis
analysis_result = await self_observation.analyze_patterns(force=True)
action_freq = await self_observation.get_action_frequency(hours=168)
```

## Graph Storage

**Extensive Use**: The Self Observation Service makes heavy use of memory graph storage for persistent telemetry and pattern data:

### Node Types Stored
- **Cycle Events** (NodeType.CONCEPT, GraphScope.LOCAL)
  - Observation cycle start/completion events
  - Pattern detection events
  - Variance threshold breaches
  - Emergency stop activations

- **Cycle Summaries** (NodeType.CONCEPT, GraphScope.IDENTITY)
  - Complete cycle results with metrics
  - Duration, variance, success status
  - Pattern counts and change applications

- **Pattern Insights** (NodeType.CONCEPT, GraphScope.LOCAL)
  - Detected patterns with confidence scores
  - Pattern effectiveness metrics
  - Learning insights and recommendations

- **Identity Snapshots** (NodeType.CONCEPT, GraphScope.IDENTITY)
  - Periodic identity state captures
  - Variance calculations from baseline
  - Configuration change tracking

- **WA Review Events** (NodeType.CONCEPT, GraphScope.IDENTITY)
  - Review triggers and outcomes
  - Approved/rejected adaptations
  - Constraint modifications

### Storage Patterns
```python
# Cycle event storage
cycle_event = GraphNode(
    id=f"cycle_event_{cycle_id}_{event_type}_{timestamp}",
    type=NodeType.CONCEPT,
    scope=GraphScope.LOCAL,
    attributes={
        "cycle_id": cycle_id,
        "event_type": event_type,
        "data": event_data.model_dump(),
        "timestamp": timestamp
    },
    updated_by="self_observation",
    updated_at=current_time
)

# Pattern insight storage
insight_node = GraphNode(
    id=f"pattern_insight_{pattern_id}",
    type=NodeType.CONCEPT,
    scope=GraphScope.LOCAL,
    attributes={
        "pattern_type": pattern_type,
        "confidence": confidence_score,
        "description": pattern_description,
        "actionable": is_actionable,
        "metadata": pattern_metadata
    }
)
```

## Example Usage

### Monitor Service Health
```python
async def monitor_self_observation():
    self_obs = get_service(ServiceType.VISIBILITY)
    status = self_obs.get_status()

    # Check critical metrics
    if status.custom_metrics.get("emergency_stop", 0.0) > 0:
        logger.critical("Self-observation in emergency stop state")

    variance = status.custom_metrics.get("current_variance", 0.0)
    if variance > 0.18:  # Approaching 20% threshold
        logger.warning(f"Identity variance approaching threshold: {variance:.3f}")

    failures = status.custom_metrics.get("consecutive_failures", 0.0)
    if failures > 2:
        logger.error(f"High consecutive failures: {failures}")
```

### Track Pattern Learning Progress
```python
async def analyze_learning_progress():
    self_obs = get_service(ServiceType.VISIBILITY)

    # Get learning summary
    summary = await self_obs.get_learning_summary()

    logger.info(f"Learning Progress:")
    logger.info(f"  Total patterns: {summary.total_patterns}")
    logger.info(f"  Learning rate: {summary.learning_rate:.2f} patterns/day")
    logger.info(f"  Insights generated: {summary.insights_count}")

    # Check pattern distribution
    for pattern_type, count in summary.patterns_by_type.items():
        logger.info(f"  {pattern_type}: {count} patterns")

    # Review recent insights
    for insight in summary.recent_insights[:3]:
        logger.info(f"  Recent insight: {insight}")
```

### Monitor Identity Variance
```python
async def check_identity_drift():
    self_obs = get_service(ServiceType.VISIBILITY)
    obs_status = await self_obs.get_adaptation_status()

    # Check variance levels
    current_variance = obs_status.current_variance
    threshold = 0.20  # 20% threshold

    variance_percent = current_variance * 100
    threshold_percent = threshold * 100

    logger.info(f"Identity Variance: {variance_percent:.1f}% (threshold: {threshold_percent:.1f}%)")

    if current_variance > threshold * 0.8:  # 80% of threshold
        logger.warning("Identity variance approaching critical threshold")

    if obs_status.under_review:
        logger.info(f"Under WA review: {obs_status.review_reason}")

    # Check stability
    if not obs_status.identity_stable:
        logger.warning("Identity marked as unstable")
```

### Trigger Manual Analysis
```python
async def run_emergency_analysis():
    """Trigger immediate pattern analysis and variance check."""
    self_obs = get_service(ServiceType.VISIBILITY)

    # Run pattern analysis
    analysis_result = await self_obs.analyze_patterns(force=True)
    logger.info(f"Pattern analysis: {analysis_result.patterns_detected} patterns found")

    # Trigger observation cycle
    cycle_result = await self_obs.trigger_adaptation_cycle()

    if cycle_result.requires_review:
        logger.warning("Analysis triggered WA review requirement")

    if cycle_result.error:
        logger.error(f"Analysis cycle failed: {cycle_result.error}")
    else:
        logger.info(f"Analysis cycle completed successfully")
        logger.info(f"  Variance: {cycle_result.variance_before:.3f} -> {cycle_result.variance_after:.3f}")
```

## Testing

### Test Files
- `tests/ciris_engine/logic/services/adaptation/test_self_observation_service.py`
- `tests/infrastructure/sub_services/test_identity_variance_monitor.py`
- `tests/infrastructure/sub_services/test_pattern_analysis_loop.py`
- `tests/integration/test_self_observation_integration.py`

### Key Test Scenarios
```python
async def test_telemetry_collection():
    # Initialize service
    time_service = MockTimeService()
    memory_bus = MockMemoryBus()

    self_obs = SelfObservationService(
        time_service=time_service,
        memory_bus=memory_bus,
        variance_threshold=0.20,
        observation_interval_hours=1
    )
    await self_obs.start()

    # Simulate some patterns and variance
    await simulate_behavioral_patterns()
    await simulate_identity_drift(0.15)

    # Trigger analysis cycle
    cycle_result = await self_obs.trigger_adaptation_cycle()

    # Verify metrics collection
    status = self_obs.get_status()
    assert "adaptation_count" in status.custom_metrics
    assert "current_variance" in status.custom_metrics
    assert status.custom_metrics["current_variance"] == 0.15

    # Verify learning data
    summary = await self_obs.get_learning_summary()
    assert summary.total_patterns > 0
    assert summary.learning_rate > 0

    # Verify graph storage
    stored_events = await memory_bus.get_stored_events()
    assert any("cycle_event" in event.id for event in stored_events)
```

## Configuration

### Initialization Parameters
- **time_service**: TimeServiceProtocol for consistent timestamps
- **memory_bus**: MemoryBus for graph storage (auto-initialized if None)
- **variance_threshold**: Identity variance limit (default: 0.20)
- **observation_interval_hours**: How often to run cycles (default: 6)
- **stabilization_period_hours**: Cool-down after changes (default: 24)

### Sub-Service Dependencies
- **IdentityVarianceMonitor**: Tracks identity drift and enforces 20% limit
- **PatternAnalysisLoop**: Detects behavioral patterns and generates insights
- **GraphTelemetryService**: Collects and stores telemetry data

### Health Checks
- Service started: `_started == True`
- Dependencies healthy: All sub-services report healthy
- Emergency stop inactive: `_emergency_stop == False`
- Failure threshold: `_consecutive_failures < _max_failures`

## Known Limitations

1. **No Real-Time Pattern Alerts**: Patterns only detected during scheduled intervals
2. **Limited Historical Analytics**: No built-in trending or forecasting
3. **No Pattern Effectiveness Tracking**: Cannot measure if acting on patterns improved outcomes
4. **Memory Growth**: Stored insights and patterns accumulate without cleanup
5. **Single Variance Metric**: Only one overall variance score, no dimensional breakdown
6. **No Cross-Service Correlation**: Pattern detection isolated to self-observation data
7. **Manual Review Process**: WA review process not automated or streamlined
8. **No A/B Testing**: Cannot test different observation strategies in parallel

## Future Enhancements

1. **Real-Time Analytics**
   - Stream pattern detection for immediate insights
   - Real-time variance monitoring with instant alerts
   - Continuous learning from every interaction

2. **Advanced Pattern Analytics**
   - Pattern effectiveness measurement and feedback loops
   - Cross-correlation analysis between different pattern types
   - Predictive pattern modeling for proactive adaptations

3. **Enhanced Graph Integration**
   - Time-series pattern storage for trend analysis
   - Cross-service pattern correlation and sharing
   - Automated pattern lifecycle management (creation, validation, retirement)

4. **Intelligent Review System**
   - Automated low-risk adaptation approval
   - Smart WA notification prioritization
   - Historical review outcome learning

5. **Multi-Dimensional Variance**
   - Separate variance tracking for different identity aspects
   - Weighted variance calculations based on criticality
   - Dynamic threshold adjustment based on system state

6. **Performance Optimization**
   - Incremental pattern analysis to reduce computation
   - Smart memory management with pattern archiving
   - Caching layer for frequently accessed insights

## Integration Points

- **IdentityVarianceMonitor**: Provides identity drift detection and WA review triggers
- **PatternAnalysisLoop**: Supplies behavioral pattern detection and insight generation
- **MemoryBus**: Stores all telemetry data, patterns, and insights in graph format
- **WiseBus**: Triggers WA reviews when variance exceeds safe thresholds
- **TimeService**: Ensures consistent timestamps across all observation data
- **BaseScheduledService**: Provides scheduled execution and task metrics
- **API Layer**: Exposes all telemetry via REST endpoints for external monitoring
- **Other Services**: Observes and learns from interactions with all system services

## Monitoring Recommendations

1. **Critical Alerts**
   - `emergency_stop == 1.0`: Service in emergency stop state
   - `current_variance > 0.18`: Approaching critical variance threshold
   - `consecutive_failures >= 3`: Pattern of analysis failures
   - `under_review == true`: Service waiting for human oversight

2. **Operational Dashboards**
   - Real-time variance tracking with threshold visualization
   - Pattern detection rates and learning progress metrics
   - Sub-service health status (variance monitor, pattern loop)
   - Analysis cycle performance and error rates

3. **Learning Analytics**
   - Pattern type distribution and effectiveness trends
   - Action frequency analysis and behavioral insights
   - Insight generation rates and quality assessments
   - Cross-service learning correlation analysis

4. **Capacity Planning**
   - Memory growth from stored patterns and insights
   - Analysis cycle duration trends and resource usage
   - WA review frequency and resolution time tracking
   - Pattern library growth and maintenance needs

## Performance Considerations

1. **Memory Usage**: Grows over time as patterns and insights accumulate in graph storage
2. **Analysis Cycles**: Periodic heavy computation during scheduled pattern analysis
3. **Graph Queries**: Pattern and insight queries can be expensive on large datasets
4. **Sub-Service Coordination**: Multiple services running concurrent scheduled tasks
5. **WA Review Latency**: Blocking on human review can delay adaptation cycles

## System Integration

The Self Observation Service acts as the **learning conscience** of CIRIS:
- **Continuous Learning**: Automatically detects and learns from behavioral patterns
- **Safe Evolution**: Maintains identity stability while enabling adaptive growth
- **Human Oversight**: Ensures critical changes receive appropriate human review
- **System Optimization**: Provides insights for improving overall system performance

Its telemetry is essential for understanding how the system learns and adapts over time, ensuring that autonomous evolution remains beneficial and aligned with core values while preventing harmful drift from intended behavior.
