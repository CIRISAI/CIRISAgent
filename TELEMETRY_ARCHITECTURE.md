# CIRIS Telemetry Architecture Documentation
*Version: 1.4.5*
*Last Updated: 2025-08-21*

## Executive Summary

The CIRIS telemetry system provides comprehensive observability for all system components through a unified collection pipeline. The architecture supports dynamic service registration, parallel metric collection, and real-time health monitoring with full traces, logs, and metrics support.

**Service Architecture:**
- **Core Services**: 33 services (21 core + 6 buses + 3 runtime objects + 3 bootstrap)
- **Dynamic Services**: 3+ adapter services per adapter instance
- **Total Range**: 33-50+ services depending on active adapters

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

Each adapter adds 3 services:
- `ServiceType.TOOL_<adapter>_tool` - Tool service
- `ServiceType.COMMUNICATION_<adapter>_<id>` - Communication service
- `ServiceType.RUNTIME_CONTROL_<adapter>_runtime` - Runtime control service

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
- Traces, logs, and metrics endpoints working
- Prometheus export with 554 metrics
- Zero telemetry collection errors
- API telemetry tool for comprehensive testing

## Related Documentation

- API Documentation: See OpenAPI spec at `/v1/docs`
- Service Documentation: See individual service files
- Testing: Use `tools/api_telemetry_tool.py`
