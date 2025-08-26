# CIRIS Telemetry Architecture Documentation
*Version: 1.0.2-RC1*
*Last Updated: 2025-08-26*

## Executive Summary

The CIRIS telemetry system provides comprehensive observability for all system components through a unified collection pipeline. The architecture supports dynamic service registration, parallel metric collection, and real-time health monitoring with full traces, logs, and metrics support.

**Service Architecture:**
- **Core Services**: 33 services (21 core + 6 buses + 3 runtime objects + 3 bootstrap)
- **Adapter Services**: 3 services per adapter instance (9 total with all 3 adapters)
- **Total with All Adapters**: 41 services (33 core + 9 adapter services with unique registrations)

## Telemetry Endpoints

### Unified Telemetry Endpoint
`GET /v1/telemetry/unified`

The primary telemetry endpoint that aggregates all system metrics:

**Query Parameters:**
- `view`: View type (summary|health|operational|detailed|performance|reliability)
- `category`: Filter by category (buses|graph|infrastructure|governance|runtime|adapters|components|all)
- `format`: Output format (json|prometheus|graphite)
- `live`: Force live collection bypassing cache (true|false)

**Example Usage:**
```bash
# JSON format (default)
curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/v1/telemetry/unified

# Prometheus format for monitoring stacks
curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/v1/telemetry/unified?format=prometheus

# Detailed view with specific category
curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/v1/telemetry/unified?view=detailed&category=graph
```

### Traces Endpoint
`GET /v1/telemetry/traces`

Returns cognitive reasoning traces from agent thoughts and tasks:

**Response:**
- Traces from wakeup thoughts
- Task execution traces
- Thought chains with timestamps and depth
- Decision points and confidence levels

### Logs Endpoint
`GET /v1/telemetry/logs`

Returns system logs with filtering:

**Query Parameters:**
- `start_time`: ISO8601 timestamp for log start
- `end_time`: ISO8601 timestamp for log end
- `level`: Log level filter (DEBUG|INFO|WARNING|ERROR|CRITICAL)
- `limit`: Maximum entries to return

### Metrics Endpoint
`GET /v1/telemetry/metrics`

Returns detailed system and service metrics:

**Response:**
- System metrics (CPU, memory, disk)
- Per-service metrics with custom fields
- Request counts and error rates
- Uptime and health status

### OpenTelemetry Protocol (OTLP) Export Endpoint
`GET /v1/telemetry/otlp/{signal}`

Exports telemetry data in OTLP JSON format compatible with OpenTelemetry v1.7.0 specification. This enables integration with any OpenTelemetry-compatible collector or observability platform.

**Path Parameters:**
- `signal`: The telemetry signal to export (metrics|traces|logs)

**Query Parameters:**
- `limit`: Maximum items to return (1-1000, default: 100)
- `start_time`: ISO8601 timestamp for data start (optional)
- `end_time`: ISO8601 timestamp for data end (optional)

**Signal Types:**

#### Metrics Export (`/v1/telemetry/otlp/metrics`)
Returns OTLP resourceMetrics containing:
- System-level metrics (health, uptime, error rates)
- Service-level metrics (per-service health, memory, requests)
- Covenant metrics (wise authority deferrals, compliance rate)
- All metrics include proper OTLP gauge/sum types with timestamps

#### Traces Export (`/v1/telemetry/otlp/traces`)
Returns OTLP resourceSpans containing:
- Cognitive processing traces from agent thoughts
- Operation spans with trace and span IDs
- Thought steps as span events
- Attributes for cognitive state and agent context

#### Logs Export (`/v1/telemetry/otlp/logs`)
Returns OTLP resourceLogs containing:
- Audit log entries with severity mapping
- Trace context correlation (trace_id, span_id)
- Service and component attributes
- Proper OTLP severity levels (DEBUG=5, INFO=9, WARNING=13, ERROR=17, CRITICAL=21)

**Example Usage:**
```bash
# Export metrics in OTLP format
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/v1/telemetry/otlp/metrics

# Export traces for the last hour
curl -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/v1/telemetry/otlp/traces?start_time=2025-08-21T00:00:00Z"

# Export logs with limit
curl -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/v1/telemetry/otlp/logs?limit=500"
```

**OTLP Integration:**
The OTLP export endpoints enable CIRIS to integrate with modern observability stacks:
- **Collectors**: OpenTelemetry Collector, Jaeger, Tempo
- **Backends**: Prometheus, Grafana, DataDog, New Relic, Splunk
- **Formats**: Standard OTLP JSON format (application/json)
- **Compatibility**: OpenTelemetry v1.7.0 specification compliant

**Push vs Pull Model:**
Currently, CIRIS supports the **pull model** where external collectors can fetch telemetry data from these endpoints. For environments requiring push-based telemetry, collectors can periodically poll these endpoints or use a sidecar collector pattern.

## Service Taxonomy & Collection

### Core Services (33 Total)

#### Graph Services (6)
- `memory` - Graph-based memory storage and retrieval
- `config` - Configuration management via graph
- `telemetry` - Metrics collection and aggregation (self-reporting)
- `audit` - Audit trail and compliance logging
- `incident_management` - Incident tracking and resolution
- `tsdb_consolidation` - Time-series data consolidation

#### Infrastructure Services (7)
- `time` - Centralized time service with UTC timezone awareness
- `shutdown` - Graceful shutdown coordination with Ed25519 signatures
- `initialization` - Multi-phase startup orchestration
- `authentication` - JWT-based auth with role-based access control
- `resource_monitor` - CPU, memory, and disk usage tracking
- `database_maintenance` - SQLite optimization and cleanup
- `secrets` - Secure secrets management with encryption

#### Governance Services (4)
- `wise_authority` - Ethical guidance and decision oversight
- `adaptive_filter` - Dynamic content filtering and moderation
- `visibility` - Transparency feeds and DSAR compliance
- `self_observation` - Pattern analysis and identity variance monitoring

#### Runtime Services (3)
- `llm` - LLM provider management (OpenAI, Anthropic, local models)
- `runtime_control` - Processing control and state management
- `task_scheduler` - Background task scheduling and execution

#### Tool Services (1)
- `secrets_tool` - Tool interface for secrets management

#### Message Buses (6)
- `llm_bus` - Routes LLM requests to providers
- `memory_bus` - Routes memory operations to graph backends
- `communication_bus` - Routes messages to communication adapters
- `wise_bus` - Routes wisdom requests to authorities
- `tool_bus` - Routes tool requests to providers
- `runtime_control_bus` - Routes control commands

#### Runtime Objects (3)
- `api_bootstrap` - API server initialization
- `service_registry` - Dynamic service registration
- `agent_processor` - Core agent processing loop

### Dynamic Adapter Services

Each adapter type adds different services:

**API Adapter (3 services):**
- `ServiceType.TOOL_api_tool` - Tool service
- `ServiceType.COMMUNICATION_api_<id>` - Communication service
- `ServiceType.RUNTIME_CONTROL_api_runtime` - Runtime control service

**CLI Adapter (3 services):**
- `ServiceType.TOOL_cli_tool` - Tool service
- `ServiceType.COMMUNICATION_cli_<id>` - Communication service
- `ServiceType.WISE_AUTHORITY_cli_wise` - Wise authority service (not runtime control)

**Discord Adapter (3 services):**
- `ServiceType.TOOL_discord_tool` - Tool service
- `ServiceType.COMMUNICATION_discord_<id>` - Communication service
- `ServiceType.WISE_AUTHORITY_discord_wise` - Wise authority service (not runtime control)

Note: CLI and Discord adapters provide WISE_AUTHORITY services instead of RUNTIME_CONTROL, as they focus on interactive wisdom/guidance rather than runtime management.

## Telemetry Collection Pipeline

### 1. Parallel Collection
All services are queried in parallel using asyncio for optimal performance:
```python
# Aggregator collects from all services simultaneously
metrics = await telemetry_service.get_aggregated_telemetry()
```

### 2. Health Determination
Services are considered healthy when:
- They respond to telemetry requests
- Error rate < 10%
- Uptime > 0 seconds
- No circuit breakers open

### 3. Metric Types

#### Standard Metrics (All Services)
- `healthy`: Boolean health status
- `uptime_seconds`: Time since service start
- `error_count`: Total errors encountered
- `requests_handled`: Total requests processed
- `error_rate`: Percentage of failed requests
- `memory_mb`: Memory usage (if available)

#### Custom Metrics (Service-Specific)
Each service can report custom metrics relevant to its function:
- LLM services: token usage, latency, model costs
- Memory services: node counts, query times
- Bus services: routing metrics, provider selections

## Prometheus Integration

The telemetry system exports metrics in Prometheus format:

```prometheus
# HELP ciris_system_healthy System Healthy
# TYPE ciris_system_healthy gauge
ciris_system_healthy 1

# HELP ciris_services_online Services Online
# TYPE ciris_services_online gauge
ciris_services_online 33

# Per-service metrics
# HELP ciris_service_uptime_seconds Service uptime in seconds
# TYPE ciris_service_uptime_seconds gauge
ciris_service_uptime_seconds{service="memory"} 1234.5
```

Total metrics exported: 550+ with full HELP and TYPE documentation

## Testing Tool

Use `tools/api_telemetry_tool.py` for comprehensive testing:

```bash
# Run all tests
python tools/api_telemetry_tool.py

# Monitor mode (real-time updates)
python tools/api_telemetry_tool.py --monitor --interval 5

# Custom endpoint
python tools/api_telemetry_tool.py --host agents.ciris.ai --port 443
```

## Key Features

### 1. No Fallback Philosophy
- **NO default metrics** - Real data only
- **NO fake uptime** - Actual service runtime
- **NO placeholder data** - Fail fast and loud

### 2. Dynamic Service Discovery
Services register themselves at runtime:
- Core services via ServiceInitializer
- Adapter services via ServiceRegistry
- Bus providers via capability registration

### 3. Comprehensive Observability
- **Traces**: Cognitive reasoning paths with thought chains
- **Logs**: System events with severity levels
- **Metrics**: Real-time performance and health data

### 4. Multiple Output Formats
- **JSON**: For API consumption
- **Prometheus**: For monitoring stacks
- **Graphite**: For time-series databases

## Implementation Notes

### BaseService Integration
All core services inherit from BaseService which provides:
- Automatic uptime tracking
- Error counting
- Request metrics
- Health status reporting

### Adapter Service Telemetry
Adapter services implement telemetry directly:
```python
async def collect_telemetry(self) -> Dict[str, Any]:
    return {
        "uptime_seconds": (self._time_service.now() - self._start_time).total_seconds(),
        "healthy": self._started,
        "error_count": 0,
        # ... custom metrics
    }
```

### Timezone Handling
All timestamps use UTC via TimeService:
- Consistent timezone across all services
- ISO8601 format for serialization
- Timezone-aware datetime objects

## Monitoring Best Practices

1. **Use Prometheus format** for production monitoring
2. **Enable live collection** sparingly (performance impact)
3. **Monitor error rates** as primary health indicator
4. **Track service registration** for dynamic services
5. **Use traces** for debugging agent behavior
6. **Check incidents_latest.log** for warnings/errors

## Current Status (2025-08-21)

✅ **Fully Operational:**
- All 33 core services reporting healthy
- With all 3 adapters: 41 total services registered and operational
- Traces, logs, and metrics endpoints working
- Prometheus export with 554+ metrics
- Zero telemetry collection errors
- API telemetry tool for comprehensive testing

## Related Documentation

- API Documentation: See OpenAPI spec at `/v1/docs`
- Service Documentation: See individual service files
- Testing: Use `tools/api_telemetry_tool.py`
