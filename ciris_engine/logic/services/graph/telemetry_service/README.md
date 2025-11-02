# CIRIS Telemetry Service

**Service Type**: Graph Service
**Location**: `ciris_engine/logic/services/graph/telemetry_service.py`
**Status**: Production (needs conversion to module directory)
**Protocol**: `TelemetryServiceProtocol`

## Overview

The CIRIS Telemetry Service is a graph-based system monitoring service that implements the "Graph Memory as Identity Architecture" by storing all metrics and telemetry data as memories in the system's graph database. This service consolidates functionality from multiple telemetry approaches into a unified system that treats telemetry data as persistent memories rather than ephemeral metrics.

## Mission Alignment

**Serves Meta-Goal M-1** through:
- **Sustainable Monitoring**: Provides comprehensive system health visibility without resource waste
- **Adaptive Coherence**: Enables system self-understanding and adaptive responses to performance issues
- **Transparency**: Complete observability into all system operations and resource usage
- **Wisdom Generation**: Converts operational data into actionable insights for system optimization
- **Trust Building**: Reliable system monitoring supports confident operation by diverse stakeholders

## Architecture

### Core Components

1. **GraphTelemetryService** - Main service implementation
2. **TelemetryAggregator** - Enterprise-grade parallel telemetry collection
3. **Memory Integration** - All metrics stored as graph nodes via MemoryBus
4. **Consolidation System** - Grace-based memory consolidation for long-term storage
5. **Real-time Caching** - Recent metrics cached for quick status queries

### Service Categories Monitored

The service monitors 37+ real services across 7 categories:

- **Buses** (6): `llm_bus`, `memory_bus`, `communication_bus`, `wise_bus`, `tool_bus`, `runtime_control_bus`
- **Graph Services** (6): `memory`, `config`, `telemetry`, `audit`, `incident_management`, `tsdb_consolidation`
- **Infrastructure** (7): `time`, `shutdown`, `initialization`, `authentication`, `resource_monitor`, `database_maintenance`, `secrets`
- **Governance** (5): `wise_authority`, `adaptive_filter`, `visibility`, `self_observation`, `consent`
- **Runtime** (3): `llm`, `runtime_control`, `task_scheduler`
- **Tools** (1): `secrets_tool`
- **Adapters** (3): `api`, `discord`, `cli` (each can spawn multiple instances)
- **Components** (2): `service_registry`, `agent_processor`
- **Registry Services**: Dynamic services registered at runtime
- **Covenant Metrics**: Computed ethical/governance metrics

## Key Features

### Graph-Based Storage
- All telemetry data stored as `TSDBGraphNode` memories
- Leverages the unified memory system for persistence
- Enables introspection and analysis of system behavior over time
- Supports time-series queries through the memory graph

### Parallel Collection
- Collects from all services simultaneously with 5-second timeout
- Handles dynamic adapter instances (API, Discord, CLI)
- Semantic naming for dynamic services
- Graceful degradation when services are unavailable

### Enterprise Aggregation
```python
# System-wide health in single call
aggregated = await telemetry_service.get_aggregated_telemetry()
print(f"{aggregated.services_online}/{aggregated.services_total} services healthy")
```

### Resource Tracking
- Comprehensive LLM token usage and costs
- Memory, CPU, and disk utilization
- Carbon footprint and energy consumption
- Model-specific resource attribution

### Covenant Metrics
Computes ethical governance metrics:
- Wise Authority deferrals and ethical decisions
- Adaptive Filter interventions
- Transparency scores
- Self-observation insights
- Covenant compliance rates

## Schemas

### Core Data Types

```python
# Service telemetry data
class ServiceTelemetryData(BaseModel):
    healthy: bool
    uptime_seconds: Optional[float]
    error_count: Optional[int]
    requests_handled: Optional[int]
    error_rate: Optional[float]
    memory_mb: Optional[float]
    custom_metrics: Optional[Dict[str, Union[int, float, str]]]

# Aggregated system response
class AggregatedTelemetryResponse(BaseModel):
    system_healthy: bool
    services_online: int
    services_total: int
    overall_error_rate: float
    overall_uptime_seconds: int
    total_errors: int
    total_requests: int
    services: Dict[str, ServiceTelemetryData]
    timestamp: str
    metadata: Optional[AggregatedTelemetryMetadata]

# Resource usage tracking
class LLMUsageData(BaseModel):
    tokens_used: Optional[int]
    tokens_input: Optional[int]
    tokens_output: Optional[int]
    cost_cents: Optional[float]
    carbon_grams: Optional[float]
    energy_kwh: Optional[float]
    model_used: Optional[str]
```

### Memory Types
```python
class MemoryType(str, Enum):
    OPERATIONAL = "operational"    # Metrics, logs, performance
    BEHAVIORAL = "behavioral"      # Actions, decisions, patterns
    SOCIAL = "social"             # Interactions, relationships
    IDENTITY = "identity"         # Self-knowledge, capabilities
    WISDOM = "wisdom"             # Learned principles, insights
```

## Protocol Implementation

### TelemetryServiceProtocol Methods

```python
async def record_metric(
    metric_name: str,
    value: float = 1.0,
    tags: Optional[Dict[str, str]] = None,
    handler_name: Optional[str] = None,
) -> None

async def query_metrics(
    metric_name: str,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    tags: Optional[Dict[str, str]] = None,
) -> List[Dict[str, Any]]

async def get_metric_summary(
    metric_name: str,
    window_minutes: int = 60
) -> Dict[str, float]

async def get_metric_count() -> int

async def get_telemetry_summary() -> TelemetrySummary
```

### Enterprise Methods

```python
async def get_aggregated_telemetry() -> AggregatedTelemetryResponse
async def process_system_snapshot(snapshot: SystemSnapshot) -> TelemetrySnapshotResult
async def get_service_status() -> TelemetryServiceStatus
```

## Grace-Based Consolidation

The service implements grace-based memory consolidation following covenant principles:

### Grace Policies
```python
class GracePolicy(str, Enum):
    FORGIVE_ERRORS = "forgive_errors"
    EXTEND_PATIENCE = "extend_patience"
    ASSUME_GOOD_INTENT = "assume_good_intent"
    RECIPROCAL_GRACE = "reciprocal_grace"
```

### Consolidation Logic
- Applies wisdom to memory consolidation decisions
- Converts errors into learning opportunities
- Maintains important context while reducing storage overhead
- Preserves system identity through selective memory retention

## Configuration

### Resource Limits
```python
ResourceLimits(
    max_memory_mb=4096,
    max_cpu_percent=80.0,
    max_disk_gb=100.0,
    max_api_calls_per_minute=1000,
    max_concurrent_operations=50,
)
```

### Caching
- Recent metrics: 100 entries per metric
- Summary cache: 60-second TTL
- Aggregation cache: 30-second TTL
- Parallel collection timeout: 5 seconds

## Usage Examples

### Basic Metric Recording
```python
# Record operational metric
await telemetry_service.record_metric(
    "user_request_processed",
    value=1.0,
    tags={"handler": "chat", "model": "gpt-4"},
    handler_name="chat_handler"
)

# Record resource usage
await telemetry_service._record_resource_usage(
    "llm_service",
    ResourceUsage(
        tokens_used=150,
        tokens_input=100,
        tokens_output=50,
        cost_cents=0.3,
        carbon_grams=0.05
    )
)
```

### System Health Monitoring
```python
# Get comprehensive system status
status = await telemetry_service.get_aggregated_telemetry()

if status.system_healthy:
    print(f"✅ System healthy: {status.services_online}/{status.services_total}")
else:
    unhealthy = [name for name, data in status.services.items() if not data.healthy]
    print(f"⚠️  Unhealthy services: {unhealthy}")
```

### Metric Queries
```python
# Query historical metrics
metrics = await telemetry_service.query_metrics(
    "user_request_processed",
    start_time=datetime.now() - timedelta(hours=1),
    tags={"handler": "chat"}
)

# Get metric statistics
summary = await telemetry_service.get_metric_summary(
    "response_time_ms",
    window_minutes=30
)
print(f"Avg response: {summary['mean']}ms, 95th: {summary['p95']}ms")
```

## Integration Points

### Memory Bus Integration
- All metrics flow through `MemoryBus.memorize_metric()`
- Stored as `TSDBGraphNode` instances in memory graph
- Enables graph-based queries and analysis
- Supports memory consolidation workflows

### Service Registry Integration
- Discovers services dynamically through `ServiceRegistry`
- Generates semantic names for adapter instances
- Handles service lifecycle changes gracefully
- Maps service implementations to telemetry categories

### Time Service Integration
- Uses `TimeService` for consistent timestamps
- Supports time synchronization validation
- Handles time drift detection
- Critical dependency (service fails without time service)

## File Structure (Current)

```
telemetry_service.py                    # Single file implementation
├── TelemetryAggregator                 # Enterprise collection class
├── GraphTelemetryService               # Main service class
├── MemoryType enum                     # Memory categorization
├── GracePolicy enum                    # Consolidation policies
└── ConsolidationCandidate dataclass    # Memory consolidation planning
```

## Required Directory Conversion

The service needs conversion from single file to module directory structure:

```
telemetry_service/
├── __init__.py                   # Service exports
├── service.py                    # Main GraphTelemetryService
├── aggregator.py                 # TelemetryAggregator
├── consolidation.py              # Memory consolidation logic
├── types.py                      # Enums and data classes
└── README.md                     # This documentation
```

## Dependencies

### Required Services
- **MemoryBus**: For metric storage as graph memories
- **TimeService**: For consistent timestamps (critical)
- **ServiceRegistry**: For dynamic service discovery

### Optional Services
- **RuntimeControlService**: For adapter instance listing
- **PSUtil**: For system resource monitoring (graceful degradation)

### Schema Dependencies
- `ciris_engine.schemas.services.graph.telemetry` - Core schemas
- `ciris_engine.schemas.telemetry.unified` - Unified response models
- `ciris_engine.schemas.runtime.protocols_core` - Base types
- `ciris_engine.schemas.runtime.system_context` - System snapshots

## Testing

The service includes comprehensive test coverage:
- Unit tests for metric recording and querying
- Integration tests with memory bus
- Performance tests for parallel collection
- Error handling and graceful degradation tests
- Schema validation tests

## Performance Characteristics

### Throughput
- Parallel collection across 37+ services in <5 seconds
- Handles 1000+ metrics per minute
- Concurrent operations limited to 50 for stability

### Memory Usage
- Efficient caching with configurable limits
- Memory consolidation reduces long-term storage overhead
- Graph storage leverages shared memory infrastructure

### Error Handling
- Graceful degradation when services unavailable
- No fake metrics - real data or explicit unavailability
- Timeout protection for collection operations
- Comprehensive error logging and recovery

## Security Considerations

- All telemetry data treated as sensitive operational information
- Metrics stored in secured memory graph with access controls
- Service discovery limited to registered services only
- Resource limits prevent telemetry from consuming excessive resources
- Grace-based consolidation preserves important security events

## Future Enhancements

### Planned Features
- Real-time alerting based on metric thresholds
- Advanced analytics and trend detection
- Machine learning-based anomaly detection
- Export capabilities for external monitoring systems
- Dashboard visualizations for operational insights

### Technical Debt
- Convert from single file to module directory structure
- Implement more sophisticated consolidation algorithms
- Add support for custom metric aggregation functions
- Enhance error recovery and retry mechanisms
- Optimize graph query performance for large datasets

## Conclusion

The CIRIS Telemetry Service represents a sophisticated approach to system monitoring that aligns operational visibility with the system's core mission of promoting sustainable adaptive coherence. By treating telemetry as memory rather than ephemeral data, the service enables the system to learn from its operational history and make increasingly intelligent decisions about resource allocation and performance optimization.

The service's graph-based architecture, comprehensive monitoring capabilities, and grace-based consolidation policies make it a critical component for maintaining system health while supporting the ethical and sustainable operation that defines CIRIS's approach to artificial intelligence systems.
