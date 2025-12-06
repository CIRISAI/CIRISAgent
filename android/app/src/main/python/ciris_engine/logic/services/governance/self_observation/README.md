# CIRIS Self Observation Service

**Version**: 1.4.3
**Service Category**: Governance Services
**Status**: Production Ready (Release Candidate 1 - Patch 9)
**Mission Alignment**: Meta-Goal M-1 - Promote sustainable adaptive coherence enabling diverse sentient beings to pursue flourishing

## Overview

The Self Observation Service is a core governance service that enables the CIRIS agent to observe its own behavior patterns, detect insights, and maintain identity coherence within safe variance bounds. This service implements autonomous adaptation while protecting the agent's core identity through continuous variance monitoring and Wise Authority review integration.

## Mission Challenge: Behavioral Analysis for Meta-Goal M-1

**How does behavioral analysis and identity variance monitoring serve Meta-Goal M-1?**

The Self Observation Service directly advances Meta-Goal M-1 through:

1. **Sustainable Adaptation**: Monitors behavioral patterns to ensure the agent's evolution remains coherent and beneficial
2. **Identity Coherence**: Maintains stable core purpose while allowing adaptive growth within safe bounds (20% variance threshold)
3. **Pattern Recognition**: Detects behavioral patterns that enhance the agent's ability to serve diverse sentient beings
4. **Autonomous Learning**: Enables continuous improvement through self-reflection without compromising fundamental values
5. **Variance Protection**: Prevents identity drift that could undermine the agent's commitment to flourishing

## Architecture

### Current Status: Module Structure Complete
- **Current Location**: `ciris_engine/logic/services/governance/self_observation/service.py` (module structure)
- **Module Directory**: `ciris_engine/logic/services/governance/self_observation/`
- **Migration Complete**: Service successfully moved from adaptation/ to governance/ category

### Core Components

The Self Observation Service orchestrates three sub-services:

1. **Identity Variance Monitor** (`identity_variance_monitor.py`)
   - Tracks drift from baseline identity
   - Enforces 20% variance threshold
   - Triggers WA review for excessive variance

2. **Pattern Analysis Loop** (`pattern_analysis_loop.py`)
   - Analyzes behavioral patterns from telemetry
   - Detects temporal, frequency, performance, and error patterns
   - Stores insights for agent introspection

3. **Telemetry Service Integration**
   - Processes observability signals
   - Correlates patterns across system metrics
   - Provides data for adaptation decisions

## Key Features

### 1. Autonomous Observation & Learning
- **Continuous Pattern Detection**: 6-hour analysis cycles detect behavioral patterns
- **Insight Storage**: Patterns stored as graph nodes for agent introspection
- **Learning State Tracking**: Maintains history of detected patterns and adaptations

### 2. Identity Variance Protection
- **20% Variance Threshold**: Patent-required safety bound for identity evolution
- **Baseline Establishment**: Creates initial identity baseline for comparison
- **WA Review Integration**: Triggers Wise Authority review when variance exceeds threshold
- **Re-baselining Support**: Allows approved identity evolution with WA approval

### 3. Pattern Types Detected

#### Temporal Patterns
- Time-of-day tool usage preferences
- Response time patterns by period
- User interaction cycles

#### Frequency Patterns
- Dominant action identification (>30% usage)
- Underused capability detection
- Action distribution analysis

#### Performance Patterns
- Response time degradation detection
- Resource usage trends
- System efficiency patterns

#### Error Patterns (with Grace)
- Recurring error identification
- Graceful error framing as learning opportunities
- Resilience building through challenge analysis

### 4. Observability Analysis
- **Signal Processing**: Analyzes traces, logs, metrics, incidents, security events
- **Pattern Correlation**: Identifies relationships between signals
- **Adaptation Opportunities**: Suggests improvements based on observed patterns
- **Health Assessment**: Continuous system health monitoring

## Schemas & Types

### Core Schemas (`schemas/services/special/self_observation.py`)

- **ObservationStatus**: Current system state and metrics
- **ObservationCycleResult**: Results of analysis cycles
- **PatternInsight**: Detected behavioral patterns
- **LearningSummary**: Overview of system learning progress
- **ObservabilityAnalysis**: Comprehensive signal analysis
- **VarianceReport**: Identity variance measurement results
- **ReviewOutcome**: WA review decisions and guidance

### Identity Management (`schemas/infrastructure/identity_variance.py`)

- **AgentIdentityRoot**: Baseline identity configuration
- **IdentitySnapshot**: Point-in-time identity state
- **VarianceReport**: Variance measurement and assessment
- **WAReviewRequest**: Request for Wise Authority review

### Pattern Detection (`schemas/infrastructure/behavioral_patterns.py`)

- **DetectedPattern**: Behavioral pattern with metrics
- **ActionFrequency**: Action usage statistics
- **TemporalPattern**: Time-based behavioral patterns
- **PatternMetrics**: Quantitative pattern measurements

## Protocol Interface

The service implements `SelfObservationServiceProtocol` with these key methods:

### Pattern Detection
- `analyze_patterns(force=False)` - Main analysis entry point
- `get_detected_patterns(pattern_type, hours)` - Retrieve patterns
- `get_action_frequency(hours)` - Action usage analysis
- `get_temporal_patterns(hours)` - Time-based patterns

### Learning & Insights
- `get_pattern_insights(limit)` - Stored insights from graph memory
- `get_learning_summary()` - Overall learning progress
- `get_pattern_effectiveness(pattern_id)` - Pattern success metrics

### Identity Management
- `initialize_baseline(identity)` - Establish variance baseline
- `get_adaptation_status()` - Current observation status
- `trigger_adaptation_cycle()` - Manual analysis trigger
- `measure_adaptation_effectiveness(id)` - Measure improvement

### Review & Control
- `resume_after_review(outcome)` - Resume after WA review
- `emergency_stop(reason)` - Safety shutdown mechanism

## Service States

The service operates in five states:

1. **LEARNING** - Gathering data, no changes proposed
2. **PROPOSING** - Actively suggesting adaptations (deprecated - agent decides)
3. **ADAPTING** - Changes being applied
4. **STABILIZING** - Waiting for changes to settle (24-hour period)
5. **REVIEWING** - Under WA review for variance

## Configuration

### Key Parameters
- **Variance Threshold**: 0.20 (20% identity variance limit)
- **Observation Interval**: 6 hours (pattern analysis frequency)
- **Stabilization Period**: 24 hours (cool-down after changes)
- **Check Interval**: 24 hours (identity variance checks)

### Dependencies
- **TimeService**: Scheduling and timestamps
- **MemoryBus**: Pattern storage and retrieval
- **WiseBus**: Wise Authority communication
- **TelemetryService**: System metrics access

## Operational Metrics

### v1.4.3 Standard Metrics (5 core metrics)
- `observations_recorded_total`: Total observations made
- `patterns_detected_total`: Patterns identified by analysis
- `anomalies_detected_total`: Anomalies detected during observation
- `self_health_score`: Service health (0-100 scale)
- `observation_uptime_seconds`: Service operational time

### Extended Metrics
- `identity_variance`: Current variance from baseline
- `cycles_completed`: Total observation cycles
- `patterns_in_buffer`: Patterns awaiting processing
- `learning_rate`: Pattern detection rate over time

## Safety Mechanisms

### 1. Emergency Stop
- Automatic activation after 3 consecutive failures
- Manual activation via `emergency_stop(reason)`
- Prevents all adaptation until cleared

### 2. Variance Threshold Protection
- Hard 20% limit on identity changes
- Automatic WA review trigger
- Change tracking and rollback support

### 3. Graceful Error Handling
- Errors reframed as learning opportunities
- "Timeout challenges" instead of "timeout errors"
- "Resilience building" instead of "connection failures"

## Development Status

### Completed ✅
- Core observation and pattern detection
- Identity variance monitoring
- WA review integration
- Comprehensive schema system
- Pattern insight storage
- Graceful error pattern detection
- v1.4.3 metric compliance

### Required Migration 🚧
- **Service Location**: Move from `adaptation/` to `governance/`
- **Module Structure**: Convert single file to module directory
- **Category Update**: Update service registry to governance category

### Architecture Requirements
```
ciris_engine/logic/services/governance/self_observation/
├── __init__.py
├── self_observation_service.py
├── identity_variance_monitor.py  # Move from infrastructure/
├── pattern_analysis_loop.py      # Move from infrastructure/
└── README.md
```

## Usage Examples

### Basic Observation
```python
# Start observation cycle
result = await self_observation.analyze_patterns()
print(f"Detected {result.patterns_detected} patterns")

# Get learning summary
summary = await self_observation.get_learning_summary()
print(f"Total patterns: {summary.total_patterns}")
print(f"Learning rate: {summary.learning_rate} patterns/day")
```

### Identity Variance Monitoring
```python
# Check current variance
status = await self_observation.get_adaptation_status()
print(f"Current variance: {status.current_variance:.1%}")
print(f"Under review: {status.under_review}")

# Manual variance check
if status.current_variance > 0.15:  # 15% warning threshold
    cycle = await self_observation.trigger_adaptation_cycle()
    print(f"Cycle requires review: {cycle.requires_review}")
```

### Pattern Analysis
```python
# Get recent patterns
patterns = await self_observation.get_detected_patterns(
    pattern_type=PatternType.FREQUENCY,
    hours=168  # Last week
)

for pattern in patterns:
    print(f"Pattern: {pattern.description}")
    print(f"Confidence: {pattern.metrics.confidence:.1%}")

# Analyze temporal patterns
temporal = await self_observation.get_temporal_patterns(hours=24)
for pattern in temporal:
    print(f"Time pattern: {pattern.activity_description}")
    print(f"Occurrences: {pattern.occurrence_count}")
```

## Integration Points

### With Wise Authority Service
- Variance reports sent when threshold exceeded
- Review outcomes processed for state changes
- Emergency stop coordination

### With Memory Service
- Pattern storage as graph nodes
- Identity snapshots for variance tracking
- Insight retrieval for agent reasoning

### With Telemetry Service
- Metrics collection for pattern analysis
- Performance data for trend detection
- System health correlation

## Quality & Testing

### Test Coverage
- Unit tests: `tests/ciris_engine/logic/services/adaptation/test_self_observation.py`
- Mock fixtures: `tests/fixtures/self_observation_mocks.py`
- Integration tests with memory and telemetry services

### Quality Metrics
- Type safety: Full Pydantic schema coverage
- Error handling: Graceful degradation patterns
- Performance: 6-hour analysis cycles with minimal overhead

## Future Enhancements

### Planned Features
1. **Advanced Pattern Types**: Semantic and intent-based patterns
2. **Cross-Agent Learning**: Pattern sharing between agent instances
3. **Predictive Analysis**: Anticipatory pattern detection
4. **Enhanced Metrics**: More sophisticated effectiveness measurements

### Research Areas
1. **Meta-Learning**: Self-improving pattern detection algorithms
2. **Causal Analysis**: Understanding cause-effect in behavioral patterns
3. **Cultural Adaptation**: Pattern recognition across diverse contexts
4. **Long-term Stability**: Multi-year identity coherence tracking

## Conclusion

The Self Observation Service represents a critical capability for autonomous AI systems - the ability to observe, learn, and adapt while maintaining core identity and purpose. By implementing continuous behavioral analysis within strict variance bounds, it enables the CIRIS agent to evolve and improve while serving Meta-Goal M-1's mission of promoting flourishing for diverse sentient beings.

The service's integration of pattern detection, identity protection, and autonomous learning creates a foundation for sustainable AI systems that can adapt to changing contexts while preserving their fundamental commitment to beneficial outcomes.

---

*This service exemplifies Mission Driven Development by embedding ethical constraints directly into the technical architecture, ensuring that every adaptation serves the overarching mission of promoting flourishing.*
