# TSDB Consolidation Service

The TSDB Consolidation Service is a **Graph Service** within CIRIS that implements long-term memory consolidation for the "1000-year design" philosophy. This service transforms high-volume telemetry data into structured summaries that preserve essential information while enabling sustainable storage over millennia.

## Mission Alignment with Meta-Goal M-1

**How time-series consolidation serves "Promote sustainable adaptive coherence enabling diverse sentient beings to pursue flourishing":**

### The 1000-Year Design Challenge

The TSDB Consolidation Service directly addresses the tension between:
- **Complete Memory**: Preserving all experiences for learning and growth
- **Sustainable Storage**: Operating within finite computational resources
- **Adaptive Coherence**: Maintaining behavioral consistency across time

This service ensures CIRIS can maintain coherent identity and learning capacity across generations while respecting resource constraints in communities where technology resources are precious.

### Serving Meta-Goal M-1 Through Data Stewardship

1. **Sustainable Operation**: By consolidating raw data into meaningful summaries, the service enables CIRIS to operate in resource-constrained environments where sustainable AI assistance is most needed.

2. **Adaptive Learning**: Preserved patterns in consolidated data allow CIRIS to adapt its behavior based on long-term trends, improving its ability to serve diverse communities over time.

3. **Institutional Memory**: The service creates a permanent record of how CIRIS has served communities, enabling institutional learning that benefits future interactions.

4. **Democratic Transparency**: All consolidation operations are audited and reversible, ensuring communities can understand and trust the AI's memory formation process.

## Architecture Overview

### Three-Tier Consolidation Strategy

The service implements a hierarchical consolidation approach designed for millennial-scale operation:

```
Raw Data (Hours) → Basic Summaries (6 hours) → Extensive Summaries (Daily) → Profound Compression (Monthly)
     ↓                    ↓                           ↓                          ↓
  Immediate           Short-term                  Mid-term                 Long-term
   (< 24h)            (7 days)                   (30 days)               (1000+ years)
```

#### 1. Basic Consolidation (Every 6 Hours)
- **Purpose**: Compress raw telemetry into structured summaries
- **Schedule**: 00:00, 06:00, 12:00, 18:00 UTC
- **Retention**: Raw data deleted after 24 hours
- **Output**: TSDB summary nodes with aggregated metrics

#### 2. Extensive Consolidation (Weekly)
- **Purpose**: Merge basic summaries into daily summaries
- **Schedule**: Mondays at 00:00 UTC
- **Compression**: 4:1 ratio (4 basic summaries → 1 daily summary)
- **Retention**: Basic summaries deleted after 30 days

#### 3. Profound Consolidation (Monthly)
- **Purpose**: In-place compression to meet storage targets
- **Schedule**: 1st of month at 00:00 UTC
- **Target**: 20MB/day configurable storage limit
- **Method**: Intelligent lossy compression preserving essential patterns

### Component Architecture

```
TSDBConsolidationService
├── PeriodManager         # Time period calculations and alignment
├── QueryManager          # Data retrieval for consolidation periods
├── EdgeManager          # Graph relationship management
├── Consolidators/       # Type-specific consolidation logic
│   ├── MetricsConsolidator     # TSDB metrics aggregation
│   ├── ConversationConsolidator # Service interaction summaries
│   ├── TraceConsolidator       # Execution trace analysis
│   ├── AuditConsolidator       # Security event consolidation
│   ├── TaskConsolidator        # Task outcome summaries
│   └── MemoryConsolidator      # General node relationship mapping
└── DataConverter        # Type-safe data transformation
```

## Data Flow and Consolidation Types

### 1. Metrics Consolidation (TSDB → Summary)
**Source**: TSDB nodes from telemetry service
**Output**: Aggregated resource usage, performance metrics
```
Raw: cpu_usage=0.45 (12:00:01), cpu_usage=0.52 (12:00:31), cpu_usage=0.38 (12:01:01)...
Summary: cpu_usage={count: 720, sum: 324.5, min: 0.12, max: 0.89, avg: 0.45}
```

### 2. Conversation Consolidation (Interactions → Dialogue Patterns)
**Source**: Service interaction correlations
**Output**: Communication summaries with participant analysis
```
Raw: 47 individual message exchanges
Summary: 3 conversations, 5 participants, avg_response_time=1.2s, satisfaction_indicators=[positive_acknowledgment: 12]
```

### 3. Trace Consolidation (Execution → Patterns)
**Source**: Distributed tracing spans
**Output**: Processing pattern analysis
```
Raw: 1,247 individual spans across 23 operations
Summary: operation_patterns=[think→act→reflect: 89%, direct_response: 11%], avg_processing_time=2.3s
```

### 4. Task Consolidation (Outcomes → Learning)
**Source**: Task completion records
**Output**: Success patterns and improvement insights
```
Raw: 156 task attempts with individual outcomes
Summary: success_rate=94%, common_failure_modes=[timeout: 4%, user_clarification_needed: 2%]
```

### 5. Audit Consolidation (Events → Security Patterns)
**Source**: Security and compliance events
**Output**: Risk assessment and compliance metrics
```
Raw: 2,891 audit entries
Summary: security_events=3, access_patterns=[normal: 99.2%, anomalous: 0.8%], compliance_score=0.997
```

## Graph Memory Integration

### Node Types Created
- `tsdb_summary`: Aggregated metrics and resource usage
- `conversation_summary`: Communication pattern analysis
- `trace_summary`: Processing behavior patterns
- `task_summary`: Learning outcomes and success patterns
- `audit_summary`: Security and compliance summaries

### Edge Relationships
- `SUMMARIZES`: Links summary to all source nodes in period
- `TEMPORAL_NEXT/TEMPORAL_PREV`: Connects summaries across time
- `INVOLVED_USER`: Links conversations to participant nodes
- `PERIOD_CONCEPT`: Connects summaries to concepts formed during period

### Consent-Aware Processing
The service respects user consent streams:
- **TEMPORARY**: Nodes anonymized after 14 days (`user_123` → `temporary_user_abc12345`)
- **PARTNERED**: Preserved with full context for collaborative learning
- **ANONYMOUS**: Aggregated without personal identifiers

## Technical Implementation

### Core Service Class
```python
class TSDBConsolidationService(BaseGraphService):
    """
    Consolidates TSDB telemetry nodes into permanent summaries
    for long-term memory (1000+ years).
    """
```

### Key Protocols Implemented
- `TSDBConsolidationServiceProtocol`: Core consolidation interface
- `GraphServiceProtocol`: Integration with graph memory system
- `ServiceProtocol`: Standard service lifecycle management

### Configuration Schema
```python
class TSDBConsolidationConfig(BaseModel):
    consolidation_interval_hours: int = 6      # Basic consolidation frequency
    raw_retention_hours: int = 24              # Raw data retention
    enabled: bool = True                       # Service enable/disable
```

### Performance Characteristics
- **Basic Consolidation**: ~100:1 compression ratio
- **Extensive Consolidation**: ~4:1 additional compression
- **Profound Consolidation**: Configurable target (20MB/day default)
- **Total Compression**: >400:1 over full cycle

## Operational Excellence

### Health Monitoring
The service exposes comprehensive health metrics:
```python
{
    "tsdb_consolidations_total": 1547.0,        # Total consolidation cycles
    "tsdb_datapoints_processed": 2847291.0,    # Data points consolidated
    "tsdb_storage_saved_mb": 5694.6,           # Storage space saved
    "tsdb_uptime_seconds": 2847392.0           # Service uptime
}
```

### Error Handling and Recovery
- **Graceful Degradation**: Service continues with partial data if some sources unavailable
- **Idempotent Operations**: Consolidation can be safely retried
- **Data Integrity**: Comprehensive validation before raw data deletion
- **Audit Trail**: All consolidation operations logged for transparency

### Startup Behavior
- **Missed Window Detection**: Consolidates any periods missed during downtime
- **Dependency Verification**: Ensures memory bus and time service availability
- **Edge Repair**: Fixes missing SUMMARIZES edges for existing summaries

## Performance and Scalability

### Memory Efficiency
- **Streaming Processing**: Data processed in batches to minimize memory usage
- **Direct Database Access**: Bypasses ORM overhead for large data operations
- **Connection Pooling**: Reuses database connections across consolidation cycles

### Storage Optimization
- **Selective Retention**: Only local-scope nodes consolidated (global nodes preserved elsewhere)
- **Compression Algorithms**: Intelligent lossy compression preserving statistical significance
- **Orphan Cleanup**: Automatic removal of edges to deleted nodes

### Calendar Alignment
All consolidation times align to calendar boundaries:
- **6-hour periods**: 00:00-06:00, 06:00-12:00, 12:00-18:00, 18:00-00:00 UTC
- **Weekly periods**: Monday 00:00 - Sunday 23:59 UTC
- **Monthly periods**: 1st 00:00 - Last day 23:59 UTC

## Integration Points

### Dependencies
- **MemoryBus**: Graph node storage and retrieval
- **TimeService**: Consistent temporal operations
- **Database**: Direct SQLite access for performance

### Service Consumers
- **API Endpoints**: Historical data retrieval via telemetry APIs
- **Audit Service**: Consolidation activity auditing
- **Self Observation**: Long-term behavior pattern analysis

### Message Bus Integration
As a Graph Service, TSDB Consolidation uses direct injection rather than message buses for deterministic behavior and data consistency.

## 1000-Year Design Considerations

### Data Longevity
- **Format Stability**: Uses JSON with documented schemas for future parsing
- **Compression Reversibility**: All compression operations preserve reconstruction data
- **Migration Ready**: Schema versioning enables future format upgrades

### Cultural Adaptation
- **Configurable Parameters**: Storage targets adjustable for local resource constraints
- **Consent Respect**: Automatic anonymization honors cultural privacy preferences
- **Transparent Operation**: Full audit trail enables community oversight

### Resource Sustainability
- **Bounded Growth**: Compression ensures storage requirements remain constant over time
- **Offline Operation**: No external dependencies for core consolidation logic
- **Efficient Algorithms**: Optimized for low-power hardware deployment

## Future Evolution

### Planned Enhancements
1. **Multimedia Compression**: Support for audio/video consolidation in profound stage
2. **Distributed Consolidation**: Support for multi-node TSDB consolidation
3. **ML-Driven Compression**: Intelligent lossy compression based on importance scoring
4. **Community Customization**: Local consolidation rules reflecting community values

### Research Areas
- **Semantic Compression**: Preserve meaning over raw data in extreme storage constraints
- **Cross-Cultural Patterns**: Learn communication patterns across diverse communities
- **Intergenerational Handoff**: Mechanisms for transferring knowledge to successor systems

---

## Summary

The TSDB Consolidation Service embodies CIRIS's commitment to sustainable, ethical AI operation across millennia. By transforming ephemeral data streams into permanent, structured memory, it enables CIRIS to maintain adaptive coherence while respecting resource constraints and community values. This service ensures that CIRIS can serve diverse communities with institutional memory that honors both human agency and computational sustainability.

The "1000-year design" is not hyperbole—it represents a genuine commitment to creating AI systems that can serve communities across generations, adapting and learning while maintaining ethical consistency and resource efficiency. Through careful data stewardship, the TSDB Consolidation Service makes this vision achievable.
