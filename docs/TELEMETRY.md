# CIRIS Telemetry System

## Overview

The CIRIS telemetry system provides comprehensive monitoring and metrics collection across all services, adapters, and components. It uses a unified, hierarchical approach to gather real-time operational data.

## Architecture

### Service Categories

The telemetry system organizes services into 8 categories:

1. **Graph Services** (6) - Data persistence and analytics
   - memory, config, telemetry, audit, incident_management, tsdb_consolidation

2. **Infrastructure Services** (6) - Core platform services
   - time, shutdown, initialization, authentication, resource_monitor, database_maintenance

3. **Governance Services** (4) - Ethics and covenant compliance
   - wise_authority, adaptive_filter, visibility, self_observation

4. **Runtime Services** (3) - Execution management
   - llm, runtime_control, task_scheduler

5. **Tool Services** (1) - External integrations
   - secrets_tool

6. **Adapter Services** (Variable) - Communication channels
   - Multiple instances supported per type
   - Each instance identified by unique adapter_id
   - Examples: api_bootstrap, discord_guild_123, cli_session_01

7. **Components** (2) - Internal runtime components
   - service_registry (includes circuit breaker details)
   - agent_processor

8. **Covenant Metrics** (Computed) - Ethical compliance metrics
   - Derived from governance services

## API Endpoints

### Unified Telemetry Endpoint

**GET** `/v1/telemetry/unified`

Returns complete telemetry data from all services.

#### Response Structure

```json
{
  "graph": {
    "memory": {
      "healthy": true,
      "uptime_seconds": 3600.0,
      "error_count": 0,
      "requests_handled": 1523,
      "error_rate": 0.0,
      "memory_mb": 128.5,
      "custom_metrics": {...}
    },
    // ... other graph services
  },
  "infrastructure": {
    // ... infrastructure services
  },
  "governance": {
    // ... governance services
  },
  "runtime": {
    // ... runtime services
  },
  "tools": {
    // ... tool services
  },
  "adapters": {
    "api_bootstrap": {
      "healthy": true,
      "uptime_seconds": 3600.0,
      "error_count": 0,
      "requests_handled": 450,
      "error_rate": 0.0,
      "custom_metrics": {
        "adapter_id": "api_bootstrap",
        "adapter_type": "api",
        "api_requests_total": 450.0,
        "api_active_connections": 5.0
      }
    },
    // ... other active adapter instances
  },
  "components": {
    "service_registry": {
      "healthy": true,
      "uptime_seconds": 300.0,
      "custom_metrics": {
        "registry_total_services": 30.0,
        "registry_circuit_breakers": 12.0,
        "registry_open_breakers": 0.0
      }
    },
    "agent_processor": {
      "healthy": true,
      "uptime_seconds": 300.0,
      "custom_metrics": {
        "processor_queue_size": 0,
        "processor_current_state": "work"
      }
    }
  },
  "covenant": {
    "wise_authority_deferrals": 15,
    "filter_interventions": 3,
    "ethical_decisions": 42,
    "covenant_compliance_rate": 0.98
  },
  "metadata": {
    "collection_method": "parallel",
    "timestamp": "2025-01-20T12:00:00Z",
    "cache_hit": false
  }
}
```

### Service Health Endpoint

**GET** `/v1/system/services/health`

Returns health status and circuit breaker states for all services.

#### Response Structure

```json
{
  "data": {
    "overall_health": "healthy",
    "timestamp": "2025-01-20T12:00:00Z",
    "healthy_services": 30,
    "unhealthy_services": 0,
    "service_details": {
      "direct.graph.MemoryService": {
        "healthy": true,
        "circuit_breaker_state": "closed",
        "priority": "DIRECT",
        "priority_group": -1,
        "strategy": "DIRECT"
      },
      // ... other services
      "registry.llm.MockLLMService": {
        "healthy": true,
        "circuit_breaker_state": "closed",
        "priority": "NORMAL",
        "priority_group": 0,
        "strategy": "FALLBACK"
      }
    }
  }
}
```

## Key Metrics

### Common Service Metrics

All services provide these base metrics:

- `healthy` - Boolean indicating service health
- `uptime_seconds` - Time since service start
- `error_count` - Total errors encountered
- `requests_handled` - Total requests processed
- `error_rate` - Error rate (errors/requests)
- `memory_mb` - Memory usage (optional)

### Service-Specific Metrics

#### API Adapter
- `api_requests_total` - Total API requests
- `api_errors_total` - Total API errors
- `api_response_time_ms` - Average response time
- `api_active_connections` - Active WebSocket connections

#### Discord Adapter
- `discord_messages_processed` - Messages handled
- `discord_commands_handled` - Commands executed
- `discord_errors_total` - Total errors
- `discord_guilds_active` - Active Discord guilds

#### CLI Adapter
- `cli_commands_executed` - Commands run
- `cli_errors_total` - Total errors
- `cli_sessions_active` - Active CLI sessions

#### Service Registry
- `registry_total_services` - Services registered
- `registry_service_types` - Unique service types
- `registry_circuit_breakers` - Total circuit breakers
- `registry_open_breakers` - Circuit breakers in OPEN state
- `registry_hit_rate` - Service lookup hit rate

## Circuit Breaker States

Each service has an associated circuit breaker with three states:

1. **CLOSED** - Service operating normally
2. **OPEN** - Service failed, requests blocked
3. **HALF_OPEN** - Testing recovery

Circuit breaker details are available through:
- Service health endpoint (`circuit_breaker_state` field)
- Service registry metrics (`registry_open_breakers`)
- Service registry info (`get_circuit_breaker_details()`)

## Multi-Adapter Support

The telemetry system fully supports multiple adapter instances:

- Each adapter instance has a unique `adapter_id`
- Only active/running adapters appear in telemetry
- Adapter metrics include instance-specific data
- Dynamic discovery based on loaded adapters

Example with multiple API instances:
```json
{
  "adapters": {
    "api_bootstrap": { ... },
    "api_datum_01": { ... },
    "api_datum_02": { ... }
  }
}
```

## Implementation Details

### Collection Process

1. **Parallel Collection** - All services queried simultaneously
2. **Timeout Protection** - 5-second timeout per service
3. **Fallback Handling** - Failed services return unhealthy status
4. **Caching** - 30-second TTL for performance

### Health Detection

Services are considered healthy if:
- They have a `healthy: true` metric
- OR they have `uptime_seconds > 0`
- AND their circuit breaker is not OPEN

### Type Safety

All telemetry data uses Pydantic models:
- `ServiceTelemetryData` - Individual service metrics
- `TelemetrySnapshot` - Complete system telemetry
- No `Dict[str, Any]` - Full type validation

## Usage Examples

### Check System Health

```bash
curl -X GET http://localhost:8000/v1/system/services/health \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### Get Full Telemetry

```bash
curl -X GET http://localhost:8000/v1/telemetry/unified \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### Monitor Specific Service

```python
import requests

response = requests.get(
    "http://localhost:8000/v1/telemetry/unified",
    headers={"Authorization": "Bearer YOUR_TOKEN"}
)

telemetry = response.json()
memory_service = telemetry["graph"]["memory"]
print(f"Memory Service Health: {memory_service['healthy']}")
print(f"Uptime: {memory_service['uptime_seconds']}s")
```

## Troubleshooting

### Service Shows Unhealthy

1. Check `error_count` and `error_rate` metrics
2. Verify circuit breaker state isn't OPEN
3. Check logs in `/app/logs/incidents_latest.log`
4. Ensure service has implemented `get_metrics()`

### Missing Adapter Instances

1. Verify adapter is running (`is_running: true`)
2. Check adapter has `get_metrics()` method
3. Ensure adapter_id is properly set
4. Check runtime control service can list adapters

### Circuit Breaker Issues

1. Check `registry_open_breakers` count
2. Review service health endpoint for states
3. Reset breakers via service registry if needed
4. Monitor `registry_health_check_failures`

## Best Practices

1. **Always implement get_metrics()** in new services
2. **Include health and uptime** as base metrics
3. **Use DEBUG logging** for telemetry collection
4. **Handle Mocks gracefully** in test environments
5. **Update adapter_id** for each adapter instance
6. **Monitor circuit breaker states** proactively

## Version History

- **v1.4.5** - Multi-adapter support, circuit breaker visibility
- **v1.4.3** - Initial telemetry system with 35 sources
- **v1.4.0** - Basic metrics collection

---

For implementation details, see `/ciris_engine/logic/services/graph/telemetry_service.py`
