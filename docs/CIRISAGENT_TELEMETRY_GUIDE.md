# CIRIS Agent Telemetry Guide

## Complete Telemetry Access for CIRISManager

This guide provides exhaustive documentation of ALL telemetry available from CIRIS agents and EXACTLY how to retrieve it.

---

## Table of Contents

1. [Authentication](#authentication)
2. [Base URLs](#base-urls)
3. [System Telemetry](#system-telemetry)
4. [Service Health & Status](#service-health--status)
5. [Memory & Graph Telemetry](#memory--graph-telemetry)
6. [LLM & Resource Usage](#llm--resource-usage)
7. [Audit & Security Telemetry](#audit--security-telemetry)
8. [Agent State & Visibility](#agent-state--visibility)
9. [Processing Queue & Runtime](#processing-queue--runtime)
10. [Incident Management](#incident-management)
11. [WebSocket Streaming](#websocket-streaming)
12. [Docker Container Logs](#docker-container-logs)
13. [Manager-Specific Endpoints](#manager-specific-endpoints)
14. [Metrics Aggregation](#metrics-aggregation)

---

## Authentication

### Standard API Authentication
```bash
# Format: Bearer username:password
curl -H "Authorization: Bearer admin:ciris_admin_password" \
  https://agents.ciris.ai/api/{agent}/v1/...

# Service Token (for CIRISManager)
curl -H "Authorization: Bearer service:YOUR_SERVICE_TOKEN" \
  https://agents.ciris.ai/api/{agent}/v1/...
```

### Available Agents
- `datum` - Primary agent
- `sage` - Secondary agent
- `scout` - Scout agent (when deployed)
- `echo-core` - Echo Core agent (when deployed)
- `echo-speculative` - Echo Speculative agent (when deployed)

---

## Base URLs

### Production
```
https://agents.ciris.ai/api/{agent}/v1/
```

### Direct Container Access (Internal)
```bash
# SSH to production
ssh -i ~/.ssh/ciris_deploy root@108.61.119.117

# Access container
docker exec ciris-{agent} curl http://localhost:8080/v1/...
```

---

## System Telemetry

### 1. System Health Overview
```bash
GET /system/health

curl -H "Authorization: Bearer admin:ciris_admin_password" \
  https://agents.ciris.ai/api/datum/v1/system/health
```

**Response:**
```json
{
  "data": {
    "status": "healthy",  // healthy|degraded|critical
    "version": "1.4.1",
    "uptime_seconds": 129600.5,
    "services": {
      "healthy": 33,
      "degraded": 0,
      "failed": 0
    },
    "initialization_complete": true,
    "cognitive_state": "WORK",
    "timestamp": "2025-08-14T13:30:00Z"
  }
}
```

### 2. System Time & Sync Status
```bash
GET /system/time

curl -H "Authorization: Bearer admin:ciris_admin_password" \
  https://agents.ciris.ai/api/datum/v1/system/time
```

**Response:**
```json
{
  "data": {
    "system_time": "2025-08-14T13:30:00Z",
    "agent_time": "2025-08-14T13:30:00Z",
    "uptime_seconds": 129600.5,
    "time_sync": {
      "synced": true,
      "drift_ms": 0.3,
      "last_sync": "2025-08-14T13:00:00Z"
    }
  }
}
```

### 3. Resource Usage & Limits
```bash
GET /system/resources

curl -H "Authorization: Bearer admin:ciris_admin_password" \
  https://agents.ciris.ai/api/datum/v1/system/resources
```

**Response:**
```json
{
  "data": {
    "current_usage": {
      "cpu_percent": 12.5,
      "memory_mb": 512,
      "memory_percent": 12.5,
      "disk_gb": 2.3,
      "disk_percent": 5.8,
      "network_connections": 45,
      "open_files": 234,
      "threads": 67
    },
    "limits": {
      "max_memory_mb": 4096,
      "max_cpu_percent": 80,
      "max_disk_gb": 40,
      "max_connections": 1000
    },
    "health_status": "healthy",
    "warnings": [],
    "critical": []
  }
}
```

---

## Service Health & Status

### 4. All Services Status
```bash
GET /system/services

curl -H "Authorization: Bearer admin:ciris_admin_password" \
  https://agents.ciris.ai/api/datum/v1/system/services
```

**Response:**
```json
{
  "data": {
    "services": [
      {
        "name": "OpenAICompatibleClient",
        "type": "runtime",
        "healthy": true,
        "available": true,
        "uptime_seconds": 129600,
        "metrics": {
          "requests_handled": 15234,
          "error_count": 23,
          "avg_response_time_ms": 450.3,
          "memory_mb": 128
        }
      },
      // ... 32 more services
    ],
    "total_services": 33,
    "healthy_services": 33,
    "timestamp": "2025-08-14T13:30:00Z"
  }
}
```

### 5. Service Registry Details
```bash
GET /telemetry/service-registry

curl -H "Authorization: Bearer admin:ciris_admin_password" \
  https://agents.ciris.ai/api/datum/v1/telemetry/service-registry
```

**Response includes:**
- Service providers by type
- Circuit breaker states
- Priority groups
- Capability mappings

---

## Memory & Graph Telemetry

### 6. Memory Statistics
```bash
GET /memory/stats

curl -H "Authorization: Bearer admin:ciris_admin_password" \
  https://agents.ciris.ai/api/datum/v1/memory/stats
```

**Response:**
```json
{
  "data": {
    "total_nodes": 45678,
    "total_edges": 123456,
    "memory_scopes": {
      "identity": 234,
      "episodic": 15234,
      "semantic": 8976,
      "procedural": 3456,
      "working": 567
    },
    "graph_size_mb": 234.5,
    "last_consolidation": "2025-08-14T06:00:00Z"
  }
}
```

### 7. Memory Timeline
```bash
GET /memory/timeline?hours=24

curl -H "Authorization: Bearer admin:ciris_admin_password" \
  https://agents.ciris.ai/api/datum/v1/memory/timeline?hours=24
```

**Response:**
```json
{
  "data": {
    "timeline": [
      {
        "timestamp": "2025-08-14T13:00:00Z",
        "event_type": "thought",
        "node_id": "thought_abc123",
        "content": "Processing user request",
        "metadata": {
          "handler": "MessageHandler",
          "duration_ms": 234
        }
      }
      // ... more events
    ],
    "total_events": 2456,
    "period_hours": 24
  }
}
```

### 8. Graph Nodes by Scope
```bash
GET /memory/scopes/{scope}/nodes?limit=100

curl -H "Authorization: Bearer admin:ciris_admin_password" \
  https://agents.ciris.ai/api/datum/v1/memory/scopes/working/nodes?limit=100
```

---

## LLM & Resource Usage

### 9. LLM Usage Metrics
```bash
GET /telemetry/llm/usage

curl -H "Authorization: Bearer admin:ciris_admin_password" \
  https://agents.ciris.ai/api/datum/v1/telemetry/llm/usage
```

**Response:**
```json
{
  "data": {
    "total_requests": 15234,
    "total_tokens": 4567890,
    "total_cost_cents": 23456,
    "by_model": {
      "meta-llama/Llama-4-Scout-17B-16E-Instruct": {
        "requests": 10234,
        "tokens": 3456789,
        "cost_cents": 15678,
        "avg_latency_ms": 456.7
      }
    },
    "by_provider": {
      "together.xyz": {
        "requests": 8234,
        "failures": 23,
        "circuit_breaker_state": "closed"
      },
      "lambda.ai": {
        "requests": 7000,
        "failures": 12,
        "circuit_breaker_state": "closed"
      }
    },
    "hourly_usage": [
      {
        "hour": "2025-08-14T13:00:00Z",
        "requests": 234,
        "tokens": 56789,
        "cost_cents": 345
      }
    ]
  }
}
```

### 10. Circuit Breaker Status
```bash
GET /telemetry/circuit-breakers

curl -H "Authorization: Bearer admin:ciris_admin_password" \
  https://agents.ciris.ai/api/datum/v1/telemetry/circuit-breakers
```

**Response:**
```json
{
  "data": {
    "circuit_breakers": [
      {
        "name": "llm_OpenAICompatibleClient_1234",
        "state": "closed",  // closed|open|half_open
        "failure_count": 0,
        "success_count": 1234,
        "last_failure": "2025-08-14T00:54:00Z",
        "last_success": "2025-08-14T13:29:00Z",
        "consecutive_failures": 0
      }
    ]
  }
}
```

---

## Audit & Security Telemetry

### 11. Recent Audit Events
```bash
GET /audit/recent?limit=100

curl -H "Authorization: Bearer admin:ciris_admin_password" \
  https://agents.ciris.ai/api/datum/v1/audit/recent?limit=100
```

**Response:**
```json
{
  "data": {
    "events": [
      {
        "timestamp": "2025-08-14T13:30:00Z",
        "entity_id": "auth_service",
        "actor": "admin",
        "action": "login",
        "outcome": "success",
        "severity": "info",
        "resource": "api_auth",
        "metadata": {
          "ip_address": "192.168.1.1",
          "user_agent": "curl/7.68.0"
        }
      }
    ],
    "total_events": 100
  }
}
```

### 12. Security Incidents
```bash
GET /telemetry/security/incidents?hours=24

curl -H "Authorization: Bearer admin:ciris_admin_password" \
  https://agents.ciris.ai/api/datum/v1/telemetry/security/incidents?hours=24
```

---

## Agent State & Visibility

### 13. Current Cognitive State
```bash
GET /visibility/cognitive-state

curl -H "Authorization: Bearer admin:ciris_admin_password" \
  https://agents.ciris.ai/api/datum/v1/visibility/cognitive-state
```

**Response:**
```json
{
  "data": {
    "current_state": "WORK",
    "state_duration_seconds": 3456,
    "previous_state": "WAKEUP",
    "state_history": [
      {
        "state": "WAKEUP",
        "entered_at": "2025-08-14T12:00:00Z",
        "duration_seconds": 300
      }
    ],
    "allowed_transitions": ["PLAY", "SOLITUDE", "DREAM", "SHUTDOWN"]
  }
}
```

### 14. Active Thoughts
```bash
GET /visibility/thoughts

curl -H "Authorization: Bearer admin:ciris_admin_password" \
  https://agents.ciris.ai/api/datum/v1/visibility/thoughts
```

**Response:**
```json
{
  "data": {
    "thoughts": [
      {
        "thought_id": "thought_abc123",
        "created_at": "2025-08-14T13:29:00Z",
        "content": "Processing user message about telemetry",
        "handler": "MessageHandler",
        "priority": 1,
        "status": "processing",
        "metadata": {
          "channel": "discord",
          "user_id": "12345"
        }
      }
    ],
    "active_count": 3,
    "queued_count": 5
  }
}
```

### 15. System Snapshot
```bash
GET /visibility/system-snapshot

curl -H "Authorization: Bearer admin:ciris_admin_password" \
  https://agents.ciris.ai/api/datum/v1/visibility/system-snapshot
```

**Complete system awareness including:**
- Identity confirmation
- Current goals
- Active contexts
- Resource state
- Service health
- Recent decisions

---

## Processing Queue & Runtime

### 16. Processing Queue Status
```bash
GET /runtime/queue/status

curl -H "Authorization: Bearer admin:ciris_admin_password" \
  https://agents.ciris.ai/api/datum/v1/runtime/queue/status
```

**Response:**
```json
{
  "data": {
    "queue_depth": 12,
    "processing_rate": 5.6,  // items per second
    "average_latency_ms": 234.5,
    "items": [
      {
        "item_id": "queue_item_123",
        "type": "thought",
        "priority": 1,
        "created_at": "2025-08-14T13:29:00Z",
        "age_seconds": 60
      }
    ],
    "processor_state": "running",
    "paused": false
  }
}
```

### 17. Handler Metrics
```bash
GET /telemetry/handlers

curl -H "Authorization: Bearer admin:ciris_admin_password" \
  https://agents.ciris.ai/api/datum/v1/telemetry/handlers
```

**Response:**
```json
{
  "data": {
    "handlers": {
      "MessageHandler": {
        "invocations": 1234,
        "avg_duration_ms": 456.7,
        "error_count": 2,
        "last_invocation": "2025-08-14T13:29:00Z"
      },
      "SelfReflectionHandler": {
        "invocations": 567,
        "avg_duration_ms": 789.0,
        "error_count": 0,
        "last_invocation": "2025-08-14T13:00:00Z"
      }
    },
    "total_handlers": 42
  }
}
```

---

## Incident Management

### 18. Recent Incidents
```bash
GET /incidents/recent?hours=24

curl -H "Authorization: Bearer admin:ciris_admin_password" \
  https://agents.ciris.ai/api/datum/v1/incidents/recent?hours=24
```

**Response:**
```json
{
  "data": {
    "incidents": [
      {
        "incident_id": "inc_20250814_001",
        "timestamp": "2025-08-14T00:54:00Z",
        "severity": "high",
        "type": "service_failure",
        "service": "OpenAICompatibleClient",
        "description": "Connection error to API provider",
        "resolution": "Circuit breaker opened, service recovered",
        "duration_seconds": 300
      }
    ],
    "total_incidents": 3,
    "by_severity": {
      "critical": 0,
      "high": 1,
      "medium": 2,
      "low": 0
    }
  }
}
```

### 19. Incident Logs (Direct Container Access)
```bash
# SSH to server
ssh -i ~/.ssh/ciris_deploy root@108.61.119.117

# View latest incidents
docker exec ciris-datum tail -n 100 /app/logs/incidents_latest.log

# View all logs
docker exec ciris-datum ls -la /app/logs/

# Specific log files:
# - incidents_latest.log     # Current incidents
# - ciris_engine.log         # Main application log
# - audit.log                # Security audit trail
# - telemetry.log           # Telemetry events
```

---

## WebSocket Streaming

### 20. Real-time Telemetry Stream
```javascript
// WebSocket connection for real-time updates
const ws = new WebSocket('wss://agents.ciris.ai/api/datum/v1/ws/telemetry');

ws.on('open', () => {
  // Authenticate
  ws.send(JSON.stringify({
    type: 'auth',
    token: 'Bearer admin:ciris_admin_password'
  }));

  // Subscribe to telemetry
  ws.send(JSON.stringify({
    type: 'subscribe',
    channels: ['metrics', 'thoughts', 'incidents']
  }));
});

ws.on('message', (data) => {
  const event = JSON.parse(data);
  console.log('Telemetry event:', event);
  // {
  //   "type": "metric",
  //   "timestamp": "2025-08-14T13:30:00Z",
  //   "data": { ... }
  // }
});
```

---

## Manager-Specific Endpoints

### 21. Manager Health Check
```bash
GET /manager/v1/health

curl https://agents.ciris.ai/manager/v1/health
```

### 22. Deployment Status
```bash
GET /manager/v1/updates/status

curl -H "Authorization: Bearer service:MANAGER_TOKEN" \
  https://agents.ciris.ai/manager/v1/updates/status
```

**Response:**
```json
{
  "agents": {
    "datum": {
      "version": "1.4.1",
      "status": "running",
      "uptime_seconds": 129600,
      "last_deploy": "2025-08-13T00:00:00Z"
    },
    "sage": {
      "version": "1.4.1",
      "status": "running",
      "uptime_seconds": 127800,
      "last_deploy": "2025-08-13T00:30:00Z"
    }
  },
  "manager_version": "1.0.3",
  "last_check": "2025-08-14T13:30:00Z"
}
```

### 23. Aggregated Metrics (Manager Port 8888)
```bash
# From production server
curl http://localhost:8888/metrics/aggregate
```

---

## Metrics Aggregation

### 24. Hourly Aggregates
```bash
GET /telemetry/aggregates/hourly?hours=24

curl -H "Authorization: Bearer admin:ciris_admin_password" \
  https://agents.ciris.ai/api/datum/v1/telemetry/aggregates/hourly?hours=24
```

**Response:**
```json
{
  "data": {
    "aggregates": [
      {
        "hour": "2025-08-14T13:00:00Z",
        "metrics": {
          "total_requests": 567,
          "total_thoughts": 234,
          "llm_calls": 123,
          "memory_operations": 456,
          "avg_response_time_ms": 234.5,
          "error_rate": 0.02,
          "resource_usage": {
            "cpu_avg": 12.5,
            "memory_avg_mb": 512
          }
        }
      }
    ]
  }
}
```

### 25. Daily Summary
```bash
GET /telemetry/summary/daily

curl -H "Authorization: Bearer admin:ciris_admin_password" \
  https://agents.ciris.ai/api/datum/v1/telemetry/summary/daily
```

---

## Custom Metrics Queries

### 26. Graph Database Query (Advanced)
```bash
POST /memory/graph/query

curl -X POST -H "Authorization: Bearer admin:ciris_admin_password" \
  -H "Content-Type: application/json" \
  https://agents.ciris.ai/api/datum/v1/memory/graph/query \
  -d '{
    "query": "MATCH (t:Thought)-[:GENERATED_BY]->(h:Handler) WHERE t.created_at > $since RETURN t, h",
    "parameters": {
      "since": "2025-08-14T00:00:00Z"
    }
  }'
```

### 27. Time-Series Data Export
```bash
GET /telemetry/export?format=csv&start=2025-08-14T00:00:00Z&end=2025-08-14T23:59:59Z

curl -H "Authorization: Bearer admin:ciris_admin_password" \
  "https://agents.ciris.ai/api/datum/v1/telemetry/export?format=csv&start=2025-08-14T00:00:00Z&end=2025-08-14T23:59:59Z" \
  -o telemetry_export.csv
```

---

## Prometheus-Compatible Metrics

### 28. Prometheus Metrics Endpoint
```bash
GET /metrics

curl -H "Authorization: Bearer admin:ciris_admin_password" \
  https://agents.ciris.ai/api/datum/v1/metrics
```

**Response (Prometheus format):**
```
# HELP ciris_llm_requests_total Total LLM requests
# TYPE ciris_llm_requests_total counter
ciris_llm_requests_total{model="llama-4-scout",provider="together"} 10234

# HELP ciris_memory_nodes_total Total nodes in memory graph
# TYPE ciris_memory_nodes_total gauge
ciris_memory_nodes_total{scope="working"} 567

# HELP ciris_handler_duration_seconds Handler execution time
# TYPE ciris_handler_duration_seconds histogram
ciris_handler_duration_seconds_bucket{handler="MessageHandler",le="0.1"} 100
ciris_handler_duration_seconds_bucket{handler="MessageHandler",le="0.5"} 450
```

---

## Error Diagnostics

### 29. Error Logs
```bash
GET /telemetry/errors?hours=1

curl -H "Authorization: Bearer admin:ciris_admin_password" \
  https://agents.ciris.ai/api/datum/v1/telemetry/errors?hours=1
```

**Response:**
```json
{
  "data": {
    "errors": [
      {
        "timestamp": "2025-08-14T00:54:00Z",
        "error_type": "APIConnectionError",
        "service": "OpenAICompatibleClient",
        "message": "Connection refused",
        "stack_trace": "...",
        "handler": "MessageHandler",
        "resolved": true
      }
    ],
    "error_rate": 0.02,
    "by_type": {
      "APIConnectionError": 5,
      "ValidationError": 2
    }
  }
}
```

### 30. Debug Traces
```bash
GET /telemetry/traces/{trace_id}

curl -H "Authorization: Bearer admin:ciris_admin_password" \
  https://agents.ciris.ai/api/datum/v1/telemetry/traces/trace_abc123
```

---

## Rate Limits & Quotas

### 31. API Rate Limit Status
```bash
GET /telemetry/rate-limits

curl -H "Authorization: Bearer admin:ciris_admin_password" \
  https://agents.ciris.ai/api/datum/v1/telemetry/rate-limits
```

**Response:**
```json
{
  "data": {
    "limits": {
      "requests_per_minute": 600,
      "requests_per_hour": 10000,
      "tokens_per_day": 10000000
    },
    "current_usage": {
      "requests_this_minute": 45,
      "requests_this_hour": 2345,
      "tokens_today": 4567890
    },
    "reset_times": {
      "minute_reset": "2025-08-14T13:31:00Z",
      "hour_reset": "2025-08-14T14:00:00Z",
      "day_reset": "2025-08-15T00:00:00Z"
    }
  }
}
```

---

## Special Telemetry Endpoints

### 32. TSDB Consolidation Status
```bash
GET /telemetry/tsdb/status

curl -H "Authorization: Bearer admin:ciris_admin_password" \
  https://agents.ciris.ai/api/datum/v1/telemetry/tsdb/status
```

**Response:**
```json
{
  "data": {
    "last_consolidation": "2025-08-14T06:00:00Z",
    "next_consolidation": "2025-08-14T12:00:00Z",
    "consolidated_nodes": 45678,
    "consolidated_edges": 123456,
    "compression_ratio": 0.73,
    "storage_saved_mb": 156.7
  }
}
```

### 33. Discord Connection Status
```bash
GET /telemetry/discord/status

curl -H "Authorization: Bearer admin:ciris_admin_password" \
  https://agents.ciris.ai/api/datum/v1/telemetry/discord/status
```

**Response:**
```json
{
  "data": {
    "connected": true,
    "latency_ms": 45.6,
    "guilds_connected": 3,
    "uptime_seconds": 3600,
    "reconnections_today": 6,
    "last_disconnect": "2025-08-14T11:48:39Z",
    "messages_processed": 1234
  }
}
```

---

## Batch Telemetry Retrieval

### 34. Multi-Agent Telemetry (Manager)
```bash
# Get telemetry for all agents at once
GET /manager/v1/telemetry/all

curl -H "Authorization: Bearer service:MANAGER_TOKEN" \
  https://agents.ciris.ai/manager/v1/telemetry/all
```

**Response:**
```json
{
  "datum": {
    "health": "healthy",
    "uptime": 129600,
    "metrics": { ... }
  },
  "sage": {
    "health": "healthy",
    "uptime": 127800,
    "metrics": { ... }
  },
  "timestamp": "2025-08-14T13:30:00Z"
}
```

---

## Data Retention & History

### 35. Historical Data Access
```bash
# Get historical metrics (up to 30 days)
GET /telemetry/history?days=7&metric=llm_requests

curl -H "Authorization: Bearer admin:ciris_admin_password" \
  "https://agents.ciris.ai/api/datum/v1/telemetry/history?days=7&metric=llm_requests"
```

### 36. Backup Status
```bash
GET /telemetry/backups

curl -H "Authorization: Bearer admin:ciris_admin_password" \
  https://agents.ciris.ai/api/datum/v1/telemetry/backups
```

---

## Important Notes

1. **Authentication Required**: All endpoints require authentication except `/manager/v1/health`
2. **Rate Limits**: 600 requests/minute per API key
3. **Data Retention**:
   - Real-time metrics: 24 hours
   - Aggregated metrics: 30 days
   - Audit logs: 90 days
   - Incidents: Permanent
4. **Time Zones**: All timestamps are UTC
5. **Response Size**: Large responses are paginated (default limit: 1000 items)
6. **WebSocket**: Maintains connection for 30 minutes, then requires reconnection
7. **Circuit Breakers**: Automatically reset after 60 seconds if service recovers

---

## Troubleshooting

### No Data Returned?
1. Check authentication token
2. Verify agent name in URL
3. Check time range parameters
4. Ensure service is healthy

### Connection Refused?
1. Check if agent is running: `docker ps | grep ciris`
2. Verify port mapping: Port 8080 inside container → 8001/8003 on host
3. Check nginx proxy: `systemctl status nginx`

### Incomplete Metrics?
1. Some metrics require time to accumulate
2. TSDB consolidation runs every 6 hours
3. Circuit breakers may temporarily block metrics

---

## Contact

For CIRISManager integration support:
- GitHub Issues: https://github.com/CIRISAI/CIRISAgent/issues
- Production Monitoring: https://agents.ciris.ai/manager/v1/health

---

*Last Updated: 2025-08-14*
*Version: 1.0.0*
*Compatible with CIRIS Agent v1.4.1+*
