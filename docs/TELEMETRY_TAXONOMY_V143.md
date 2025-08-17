# CIRIS v1.4.3 Telemetry Taxonomy - The Reality

## Overview

The v1.4.3 telemetry system uses the `TelemetryAggregator` class to collect metrics from services across 7 major categories. Most metrics are collected on-demand (PULL model) with a 30-second cache to reduce load.

## Service Categories & Metrics

### 1. BUSES (6 Message Buses)
- `llm_bus` - LLM request routing and load balancing
- `memory_bus` - Graph memory operations
- `communication_bus` - Inter-service communication
- `wise_bus` - Wise Authority deferral and decisions
- `tool_bus` - Tool execution coordination
- `runtime_control_bus` - Runtime control commands

### 2. GRAPH Services (6 Services)
- `memory` - Graph database operations, node/edge counts
- `config` - Configuration management and caching
- `telemetry` - Meta-telemetry about telemetry collection
- `audit` - Audit event tracking and compliance
- `incident_management` - Incident patterns and severity
- `tsdb_consolidation` - Time-series data consolidation

### 3. INFRASTRUCTURE Services (7 Services)
- `time` - Time synchronization and clock services
- `shutdown` - Graceful shutdown coordination
- `initialization` - Service startup and initialization
- `authentication` - Auth tokens and session management
- `resource_monitor` - CPU, memory, disk monitoring
- `database_maintenance` - DB optimization and cleanup
- `secrets` - Secrets management and rotation

### 4. GOVERNANCE Services (4 Services)
- `wise_authority` - WA deferrals and guidance
- `adaptive_filter` - Content filtering and adaptation
- `visibility` - Transparency and observability
- `self_observation` - Agent self-monitoring

### 5. RUNTIME Services (4 Services)
- `llm` - LLM usage, tokens, costs
- `runtime_control` - Processing control and state
- `task_scheduler` - Task queue and scheduling
- `secrets_tool` - Secrets tool executions

### 6. ADAPTERS (3+ Dynamic)
- `api` - API request handling (always present)
- `discord` - Discord message handling (when active)
- `cli` - CLI command processing (when active)
- Dynamic per-agent instances (e.g., `discord_datum`)

### 7. COMPONENTS (5 Core Components)
- `circuit_breaker` - Service protection and failover
- `processing_queue` - Message queue metrics
- `service_registry` - Service registration and discovery
- `service_initializer` - Service startup metrics
- `agent_processor` - Agent processing pipeline

## API Endpoints

### Primary Endpoints
- `GET /telemetry/unified` - Aggregated metrics from all services (30s cache)
- `GET /telemetry/overview` - High-level system overview
- `GET /telemetry/resources` - Current resource usage
- `GET /telemetry/resources/history` - Historical resource data
- `GET /telemetry/metrics` - Available metrics list
- `GET /telemetry/metrics/{metric_name}` - Specific metric history
- `GET /telemetry/traces` - Execution traces
- `GET /telemetry/logs` - System logs
- `POST /telemetry/query` - Query metrics with filters

## Collection Mechanism

### TelemetryAggregator Flow
1. **Parallel Collection**: Collects from all services simultaneously
2. **Service Discovery**: Uses ServiceRegistry to find available services
3. **Fallback Logic**: Gracefully handles missing services
4. **Caching**: 30-second TTL to reduce load
5. **Aggregation**: Calculates system-wide metrics

### Metric Types

#### PULL Metrics (Majority)
- Collected on-demand via `get_metrics()` or `get_telemetry()`
- Not stored unless explicitly pushed
- Real-time values when requested
- Examples: uptime, request counts, error rates

#### PUSH Metrics (Minority)
- Actively stored via `memorize_metric()`
- Persisted in TSDB for historical queries
- Critical metrics only (LLM usage, costs, incidents)
- Examples: llm_tokens, estimated_cost, CO2 emissions

## Actual Implementation Notes

### What's Real
- TelemetryAggregator attempts to collect from ~40+ services
- Most services return empty metrics or aren't implemented
- Fallback logic ensures the API always responds
- Cache reduces actual collection to every 30 seconds

### What's Missing
- Many services don't implement `get_metrics()` yet
- Handler telemetry exists but isn't aggregated
- Bus metrics are defined but not fully exposed
- Processor metrics are minimal

### Current Metric Count (Reality)
- **Defined in categories**: ~40 services/components
- **Actually returning metrics**: ~10-15 services
- **Unique metric names**: ~50-100 (varies by runtime)
- **Persisted to TSDB**: <20 metrics

## Key Insights

1. **The 362+ metric claim is aspirational** - it counts potential metrics if all services were fully instrumented
2. **Most telemetry is PULL-based** - collected on demand, not stored
3. **Very few PUSH metrics** - only critical ones go to TSDB
4. **Dynamic metrics** - Adapters create instance-specific metrics
5. **Graceful degradation** - System handles missing services well

## Usage Examples

```python
# Get all metrics (uses 30s cache)
GET /telemetry/unified

# Get specific service metrics
GET /telemetry/unified?category=graph

# Get resource metrics only
GET /telemetry/resources

# Query historical data (if pushed to TSDB)
GET /telemetry/metrics/llm_tokens_total
```

## Future State

To reach the promised 362+ metrics, we need:
1. Implement `get_metrics()` in all services
2. Wire up handler telemetry to aggregator
3. Expose bus metrics properly
4. Add processor thought metrics
5. Implement adapter-specific metrics

---

*This document reflects the ACTUAL v1.4.3 implementation, not the theory.*
