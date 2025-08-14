# API Adapter Telemetry

## Overview
The API Adapter (ApiPlatform) is a multi-service adapter providing REST API and WebSocket interfaces to the CIRIS agent. It implements three service protocols: CommunicationService, RuntimeControlService, and ToolService via separate service classes. The adapter provides comprehensive telemetry through service correlations, status metrics, component statistics, and health monitoring across all its constituent services.

## Telemetry Data Collected

| Metric Name | Type | Storage | Update Frequency | Access Method |
|-------------|------|---------|------------------|---------------|
| api.adapter.starting | counter | graph (TSDBGraphNode) | on start | memorize_metric |
| api.adapter.started | counter | graph (TSDBGraphNode) | on start complete | memorize_metric |
| api.adapter.stopping | counter | graph (TSDBGraphNode) | on stop | memorize_metric |
| api.adapter.stopped | counter | graph (TSDBGraphNode) | on stop complete | memorize_metric |
| api.message.observed | counter | graph (TSDBGraphNode) | per incoming message | memorize_metric |
| api.message.sent | counter | graph (TSDBGraphNode) | per outgoing message | memorize_metric |
| api.websocket.connected | counter | graph (TSDBGraphNode) | per WebSocket connection | memorize_metric |
| api.websocket.disconnected | counter | graph (TSDBGraphNode) | per WebSocket disconnection | memorize_metric |
| api.tool.executed | counter | graph (TSDBGraphNode) | per tool execution | memorize_metric |
| api.runtime_control.pause | counter | graph (TSDBGraphNode) | on processing pause | memorize_metric |
| api.runtime_control.resume | counter | graph (TSDBGraphNode) | on processing resume | memorize_metric |
| requests_handled | gauge | in-memory | per request | APICommunicationService |
| error_count | gauge | in-memory | per error | APICommunicationService |
| response_times | list | in-memory (bounded) | per request | APICommunicationService |
| websocket_clients | gauge | in-memory | on connect/disconnect | APICommunicationService |
| queued_responses | gauge | in-memory | real-time | APICommunicationService |
| paused_state | gauge | in-memory | on state change | APIRuntimeControlService |
| pause_duration | gauge | in-memory | real-time | APIRuntimeControlService |
| tools_count | gauge | in-memory | on tool registration | APIToolService |
| server_health | gauge | in-memory | real-time | ApiPlatform |
| service_correlations | records | persistent | per operation | ServiceCorrelation |
| rate_limit_buckets | dict | in-memory | per request | RateLimiter |

## Data Structures

### API Adapter Status
```python
{
    "service_name": "ApiPlatform",
    "service_type": "adapter",
    "is_healthy": True,
    "uptime_seconds": 7200.5,
    "server_running": True,
    "services": {
        "communication": True,
        "runtime_control": True,
        "tool_service": True,
        "message_observer": True
    }
}
```

### Communication Service Status
```python
{
    "service_name": "APICommunicationService",
    "service_type": "communication",
    "is_healthy": True,
    "uptime_seconds": 7200.5,
    "metrics": {
        "requests_handled": 1245.0,
        "error_count": 3.0,
        "avg_response_time_ms": 45.7,
        "queued_responses": 2.0,
        "websocket_clients": 5.0
    }
}
```

### Runtime Control Service Status
```python
{
    "service_name": "APIRuntimeControlService",
    "service_type": "RUNTIME_CONTROL",
    "is_healthy": True,
    "uptime_seconds": 7200.5,
    "metrics": {
        "paused": 0.0,
        "pause_duration": 0.0
    }
}
```

### Tool Service Status
```python
{
    "service_name": "APIToolService",
    "service_type": "tool",
    "is_healthy": True,
    "uptime_seconds": 7200.5,
    "metrics": {
        "tools_count": 12
    },
    "custom_metrics": {
        "tools": ["get_time", "memorize", "recall", "speak"]
    }
}
```

### Service Capabilities (Communication)
```python
{
    "service_name": "APICommunicationService",
    "actions": [
        "send_message",
        "fetch_messages",
        "broadcast",
        "get_response",
        "register_websocket",
        "unregister_websocket"
    ],
    "version": "1.0.0",
    "metadata": {
        "http_responses": True,
        "websocket_broadcast": True,
        "message_queueing": True,
        "channel_based_routing": True
    }
}
```

### Service Correlation Example
```python
{
    "correlation_id": "uuid4-string",
    "service_type": "api",
    "handler_name": "APIAdapter",
    "action_type": "observe|speak|execute_tool|pause_processing",
    "request_data": {
        "service_type": "api",
        "method_name": "observe",
        "channel_id": "api_127.0.0.1_8080",
        "parameters": {
            "content": "Hello API",
            "author_id": "user_123",
            "message_id": "msg_456"
        },
        "request_timestamp": datetime
    },
    "response_data": {
        "success": True,
        "result_summary": "Message observed",
        "execution_time_ms": 12.5,
        "response_timestamp": datetime
    },
    "status": "COMPLETED|PENDING|ERROR",
    "created_at": datetime,
    "updated_at": datetime
}
```

### Rate Limiter Statistics
```python
{
    "active_clients": 25,
    "rate_per_minute": 60,
    "clients_with_tokens": {
        "127.0.0.1": 45.2,
        "192.168.1.100": 12.8
    },
    "cleanup_last_run": datetime
}
```

## API Access Patterns

### Current Access
- **Service Status**: Each service provides `get_status()` method with typed ServiceStatus return
- **Service Capabilities**: Each service provides `get_capabilities()` method with ServiceCapabilities return
- **Health Check**: Main adapter provides `is_healthy()` method checking server and task status
- **Channel List**: Adapter provides `get_channel_list()` returning active API channels with permissions
- **Telemetry**: All metrics flow through memory graph via correlation tracking and service status methods

### Recommended API Endpoints

#### API Adapter Overview
```
GET /v1/telemetry/api-adapter
```
Returns comprehensive adapter telemetry:
```json
{
    "service_name": "ApiPlatform",
    "is_healthy": true,
    "uptime_seconds": 7200.5,
    "server_status": {
        "running": true,
        "host": "0.0.0.0",
        "port": 8080,
        "uvicorn_server": true
    },
    "services": {
        "communication": {
            "healthy": true,
            "requests_handled": 1245,
            "errors": 3,
            "websocket_clients": 5,
            "avg_response_time_ms": 45.7
        },
        "runtime_control": {
            "healthy": true,
            "paused": false,
            "pause_duration_seconds": 0
        },
        "tool_service": {
            "healthy": true,
            "tools_available": 12,
            "tools": ["get_time", "memorize", "recall", "speak"]
        },
        "message_observer": {
            "healthy": true,
            "active": true
        }
    },
    "channels": {
        "active_channels": 3,
        "total_messages_24h": 256,
        "admin_channels": 1
    }
}
```

#### API Communication Metrics
```
GET /v1/telemetry/api-communication
```
Returns communication-specific metrics:
```json
{
    "service_name": "APICommunicationService",
    "requests_handled": 1245,
    "error_count": 3,
    "error_rate_percent": 0.24,
    "response_times": {
        "average_ms": 45.7,
        "min_ms": 12.1,
        "max_ms": 287.4,
        "p95_ms": 156.3
    },
    "websockets": {
        "active_clients": 5,
        "clients": ["ws_client_1", "ws_client_2"],
        "messages_broadcasted": 89
    },
    "queuing": {
        "queued_responses": 2,
        "max_queue_size": 100
    },
    "channels": {
        "http_channels": 2,
        "websocket_channels": 3,
        "home_channel": "api_127.0.0.1_8080"
    }
}
```

#### API Runtime Control Status
```
GET /v1/telemetry/api-runtime-control
```
Returns runtime control metrics:
```json
{
    "service_name": "APIRuntimeControlService",
    "is_paused": false,
    "pause_duration_seconds": 0,
    "last_state_change": "2025-08-14T14:30:15Z",
    "capabilities": {
        "pause_resume": true,
        "state_transitions": true,
        "emergency_shutdown": true
    },
    "adapter_management": {
        "adapters_loaded": 3,
        "adapters": ["api", "discord", "cli"]
    }
}
```

#### API Rate Limiting
```
GET /v1/telemetry/api-rate-limits
```
Returns rate limiting statistics:
```json
{
    "rate_limiter": {
        "requests_per_minute": 60,
        "active_clients": 25,
        "cleanup_interval_seconds": 300,
        "last_cleanup": "2025-08-14T14:25:00Z"
    },
    "client_buckets": {
        "total_clients": 25,
        "clients_with_tokens": 18,
        "clients_rate_limited": 7
    },
    "statistics": {
        "requests_allowed": 2456,
        "requests_blocked": 34,
        "block_rate_percent": 1.37
    }
}
```

## Graph Storage

### Telemetry Nodes
API adapter metrics are stored as TSDBGraphNode objects in the memory graph:
- **Scope**: "local"
- **Handler**: "adapter.api"
- **Node Type**: "TSDB"
- **Attributes**: Include metric name, value, tags, and timestamp

### Persistent Nodes
Long-term operational data stored as specialized graph nodes:

#### API Channel Context
```python
{
    "id": "api_channel/{channel_id}",
    "scope": "LOCAL",
    "channel_id": "api_127.0.0.1_8080",
    "channel_type": "api",
    "channel_name": "API Home Channel",
    "is_private": False,
    "is_active": True,
    "last_activity": datetime,
    "message_count": 256,
    "allowed_actions": ["speak", "observe", "memorize", "recall", "tool", "wa_defer", "runtime_control"],
    "moderation_level": "standard"
}
```

#### WebSocket Connection Node
```python
{
    "id": "api_websocket/{client_id}",
    "scope": "LOCAL",
    "client_id": "ws_client_123",
    "channel_id": "ws:client_123",
    "connected_at": datetime,
    "last_message": datetime,
    "messages_sent": 45,
    "messages_received": 23,
    "connection_status": "active|inactive|error"
}
```

## Example Usage

### Query API Adapter Metrics
```python
# Get all API adapter metrics from last hour
from ciris_engine.logic.services.graph.memory import MemoryService

memory = get_memory_service()
metrics = await memory.search({
    "handler_name": "adapter.api",
    "node_type": "TSDB",
    "created_at": {"$gte": datetime.now() - timedelta(hours=1)}
})

# Get message handling metrics
message_metrics = [m for m in metrics if "message" in m.metric_name]
total_messages = sum(float(m.value) for m in message_metrics)
```

### Get Real-Time Service Status
```python
# Get adapter health status
adapter = get_api_adapter()
is_healthy = adapter.is_healthy()
print(f"API server healthy: {is_healthy}")

# Get communication service status
comm_status = adapter.communication.get_status()
print(f"Requests handled: {comm_status.metrics['requests_handled']}")
print(f"Error rate: {comm_status.metrics['error_count'] / comm_status.metrics['requests_handled'] * 100:.2f}%")

# Get runtime control status
runtime_status = adapter.runtime_control.get_status()
print(f"Processing paused: {bool(runtime_status.metrics['paused'])}")
```

### Monitor WebSocket Connections
```python
# Get WebSocket client information
comm_service = adapter.communication
client_count = len(comm_service._websocket_clients)
client_ids = list(comm_service._websocket_clients.keys())
print(f"Active WebSocket clients: {client_count}")

# Track WebSocket metrics from correlations
correlations = get_correlations_by_service("api")
websocket_events = [
    c for c in correlations
    if c.request_data.channel_id.startswith("ws:")
]
```

### Access Channel Activity
```python
# Get active API channels
channels = adapter.get_channel_list()
for channel in channels:
    print(f"Channel {channel.channel_id}: {channel.message_count} messages")
    print(f"  Actions: {', '.join(channel.allowed_actions)}")
    print(f"  Last activity: {channel.last_activity}")
```

## Testing

### Test Files
- `tests/logic/adapters/api/test_api_adapter.py` - Main adapter tests
- `tests/logic/adapters/api/test_api_communication.py` - Communication service tests
- `tests/logic/adapters/api/test_api_runtime_control.py` - Runtime control tests
- `tests/logic/adapters/api/test_api_tools.py` - Tool service tests
- `tests/logic/adapters/api/test_api_telemetry.py` - Telemetry-specific tests
- `tests/logic/adapters/api/test_rate_limiter.py` - Rate limiter tests

### Validation Steps
1. **Telemetry Emission**: Verify correlations created for all major operations
2. **Service Status**: Check each service's `get_status()` returns accurate data
3. **Health Monitoring**: Validate `is_healthy()` reflects actual server state
4. **WebSocket Tracking**: Confirm client registration/unregistration metrics
5. **Rate Limiting**: Test statistics tracking during rate-limited scenarios
6. **Channel Management**: Verify active channel discovery and permissions

```python
async def test_api_telemetry():
    adapter = ApiPlatform(runtime=mock_runtime, adapter_config=test_config)
    await adapter.start()

    # Test service status methods
    comm_status = adapter.communication.get_status()
    assert comm_status.service_name == "APICommunicationService"
    assert comm_status.is_healthy == True

    # Test health check
    assert adapter.is_healthy() == True

    # Test correlation creation
    msg = IncomingMessage(content="test", channel_id="api_test", author_id="user")
    await adapter._create_message_correlation(msg)

    # Verify correlation in persistence
    correlations = get_correlations_by_service("api")
    assert len(correlations) >= 1
    assert correlations[0].action_type == "observe"
```

## Configuration

### Adapter Configuration
```python
# API adapter configuration affects telemetry collection
api_config = APIAdapterConfig(
    host="0.0.0.0",
    port=8080,
    interaction_timeout=30,  # Affects response time metrics
    max_connections=100      # Affects connection capacity tracking
)

# Rate limiter configuration
rate_limiter = RateLimiter(requests_per_minute=60)
# Affects rate limiting statistics and client tracking
```

### Service Settings
```python
# Communication service settings
communication = APICommunicationService(config=api_config)
communication._max_response_times = 100  # Response time history size
communication._response_queue = asyncio.Queue(maxsize=1000)  # Queue capacity

# WebSocket client tracking
communication._websocket_clients = {}  # Client registry for metrics
```

### uvicorn Server Settings
```python
# Server configuration affects health monitoring
uvicorn_config = uvicorn.Config(
    app=adapter.app,
    host=api_config.host,
    port=api_config.port,
    log_level="info",
    access_log=True  # Enables request logging
)
```

## Known Limitations

1. **Memory-Only Statistics**: Service metrics reset on restart (requests_handled, error_count)
2. **No Historical Aggregation**: Response times only maintain last 100 samples
3. **Rate Limiter Persistence**: Rate limiting buckets not persisted across restarts
4. **Limited WebSocket Analytics**: No per-client message rate or connection duration tracking
5. **No Cross-Request Correlation**: Individual HTTP requests not linked to agent processing
6. **Server Dependency**: Health status depends on uvicorn server task state
7. **Missing Tool Metrics**: Individual tool execution statistics not tracked by APIToolService
8. **No Error Categorization**: Generic error counting without classification

## Future Enhancements

1. **Persistent Statistics**: Store service metrics in Redis or database for restart persistence
2. **Historical Metrics**: Time-series data for request rates, response times, and error patterns
3. **WebSocket Analytics**: Per-client connection duration, message rates, and lifecycle tracking
4. **Request Tracing**: End-to-end correlation from HTTP request to agent response
5. **Tool Execution Metrics**: Individual tool performance and usage statistics
6. **Error Classification**: Categorized error tracking (auth, rate limit, server, validation)
7. **Performance Profiling**: Request latency breakdown and bottleneck identification
8. **Prometheus Integration**: Export metrics to Prometheus for external monitoring
9. **Dashboard Support**: Real-time dashboard data endpoints for monitoring UI
10. **SLA Monitoring**: Response time percentiles and availability tracking

## Integration Points

### Memory Bus Integration
- **Metric Storage**: All telemetry flows through memory.memorize_metric() via service correlations
- **Node Queries**: Persistent nodes accessible via memory.search() for channel and connection data
- **Graph Relationships**: Links between messages, channels, users, and tool executions

### Service Registry Integration
- **Multi-Provider Support**: API adapter registers multiple service providers with different capabilities
- **Priority Management**: Critical priority services for communication, runtime control, and tools
- **Capability Advertising**: Each service declares specific actions and metadata

### TSDB Consolidation
- **6-Hour Cycles**: Metrics consolidated for long-term storage and trending
- **Aggregation**: Request counts, average response times, and error rates computed
- **Retention**: Historical data management for capacity planning

### Audit Service Integration
- **Request Logging**: All API requests logged with user context and outcomes
- **Authentication Events**: Login, logout, and permission changes tracked
- **Administrative Actions**: Runtime control operations and emergency shutdowns audited
- **Tool Usage**: Tool executions tracked with parameters and results

## Monitoring Recommendations

### Critical Alerts
1. **Server Down**: Alert when `is_healthy()` returns False or server task fails
2. **High Error Rate**: Monitor error_count vs requests_handled ratio above 5%
3. **Response Time Degradation**: Alert on average response time > 1000ms
4. **WebSocket Failures**: Alert on rapid client disconnections
5. **Rate Limiting Abuse**: Monitor blocked request percentages above 10%

### Performance Monitoring
1. **Request Throughput**: Track requests_handled growth rate and capacity utilization
2. **Response Time Distribution**: Monitor P95, P99 response times and outliers
3. **Queue Depth**: Monitor queued_responses for backlog detection
4. **Memory Usage**: Track WebSocket client count and response time history size
5. **Connection Health**: Monitor WebSocket connection stability and reconnection rates

### Operational Insights
1. **Usage Patterns**: Peak hours, channel activity, and user behavior analysis
2. **Feature Adoption**: Tool usage statistics and API endpoint popularity
3. **Error Trends**: Common failure patterns and recovery effectiveness
4. **Capacity Planning**: Connection scaling needs and resource growth trends
5. **Security Monitoring**: Rate limiting effectiveness and authentication patterns

## Security Considerations

1. **Credential Protection**: API credentials and tokens not logged in telemetry data
2. **Content Filtering**: Message content excluded from general telemetry (only in correlations)
3. **User Privacy**: User IDs hashed in long-term storage where possible
4. **Permission Auditing**: All authentication and authorization changes fully logged
5. **Rate Limit Monitoring**: Client identification without exposing sensitive data
6. **WebSocket Security**: Client session data sanitized before telemetry storage

## Performance Considerations

1. **Async Operations**: All telemetry operations are non-blocking and async-compatible
2. **Memory Efficiency**: Bounded collections for response times and rate limiting buckets
3. **Correlation Batching**: Service correlations batched where possible to reduce graph load
4. **Query Optimization**: Indexed fields for common telemetry queries (handler_name, node_type)
5. **Connection Pooling**: Shared uvicorn server and FastAPI app across all services
6. **Rate Limit Efficiency**: Token bucket algorithm with periodic cleanup to manage memory
