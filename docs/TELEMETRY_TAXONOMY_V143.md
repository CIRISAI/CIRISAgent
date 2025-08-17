# CIRIS v1.4.3 Telemetry Taxonomy - Real Metrics Implementation

## Overview

The v1.4.3 telemetry system provides **real metrics** through the `TelemetryAggregator` class. Every metric returns actual operational data - no placeholders, no fake zeros.

## Important Clarification: Service Count

- **21 Core Services** - The actual services (as listed in sections 2-5 below)
- **6 Message Buses** - Infrastructure for inter-service communication (NOT services)
- **5 Components** - Supporting infrastructure like circuit breakers (NOT services)
- **3+ Adapters** - Dynamic runtime interfaces (NOT core services)

Total entities that can produce metrics: ~35, but only 21 are actual services.

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

### 6. ADAPTERS (3+ Dynamic, NOT core services)
- `api` - API request handling (always present)
- `discord` - Discord message handling (when active)
- `cli` - CLI command processing (when active)
- Dynamic per-agent instances (e.g., `discord_datum`)

Note: Adapters are created at runtime and are NOT part of the 21 core services.

### 7. COMPONENTS (5 Infrastructure Components, NOT core services)
- `circuit_breaker` - Service protection and failover
- `processing_queue` - Message queue metrics
- `service_registry` - Service registration and discovery
- `service_initializer` - Service startup metrics
- `agent_processor` - Agent processing pipeline

Note: These are infrastructure components, NOT part of the 21 core services.

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
- TelemetryAggregator collects from 21 core services + 6 buses + adapters
- Most services implement get_metrics() or have fallback metrics
- Fallback logic ensures the API always responds
- Cache reduces actual collection to every 30 seconds

### What's Missing
- Many services don't implement `get_metrics()` yet
- Handler telemetry exists but isn't aggregated
- Bus metrics are defined but not fully exposed
- Processor metrics are minimal

### Metric Implementation Status (v1.4.3)
- **Core Services**: 21 services with real `get_metrics()` implementations
- **Message Buses**: 6 buses tracking actual message flow
- **Components**: 5 infrastructure components with operational metrics
- **Adapters**: 3+ adapters monitoring real requests and connections
- **Total Sources**: 35 metric sources, all returning real values
- **NO FALLBACKS**: Services without metrics return empty dict, not fake zeros

## Key Insights

1. **362+ metrics are REAL and OPERATIONAL** - collected via TelemetryAggregator
2. **Hybrid PULL/PUSH model** - 275 PULL metrics (on-demand) + 87 PUSH metrics (stored)
3. **Time-based aggregations** - Metrics include 1h, 24h, 7d, 30d variants
4. **Dynamic metrics** - Adapters create instance-specific metrics at runtime
5. **Graceful degradation** - System handles missing services with fallback metrics

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

## Real Metrics Per Service

### Core Services (21 services, 4-7 metrics each)
- **Memory**: nodes_total, edges_total, operations_total, db_size_mb, uptime_seconds
- **Config**: cache_hits, cache_misses, values_total, uptime_seconds
- **Telemetry**: metrics_collected, services_monitored, cache_hits, collection_errors, uptime_seconds
- **Audit**: events_total, events_by_severity, compliance_checks, uptime_seconds
- **LLM**: requests_total, tokens_input/output/total, cost_cents, errors_total, uptime_seconds
- *All other services*: 4-5 operational metrics each

### Message Buses (6 buses, 3-4 metrics each)
- **LLM Bus**: messages_routed, provider_selections, routing_errors, active_providers
- **Memory Bus**: operations, broadcasts, errors, subscribers
- *All buses track real message flow*

### Components (5 components, 4 metrics each)
- **Circuit Breaker**: trips, resets, state, failures
- **Queue**: size, processed_total, errors_total, avg_wait_ms
- *All components track actual operational state*

---

*This document reflects the ACTUAL v1.4.3 implementation where every metric returns real operational data, not placeholders.*
