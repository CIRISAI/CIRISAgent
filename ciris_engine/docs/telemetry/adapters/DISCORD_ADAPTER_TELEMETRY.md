# Discord Adapter Telemetry

## Overview
The Discord Adapter (DiscordAdapter) is a multi-protocol service implementing CommunicationService, WiseAuthorityService, and ToolService protocols for Discord platform integration. It provides comprehensive telemetry through graph-based metrics, service correlations, audit logging, and component-specific statistics tracking.

## Telemetry Data Collected

| Metric Name | Type | Storage | Update Frequency | Access Method |
|-------------|------|---------|------------------|---------------|
| discord.adapter.starting | counter | graph (TSDBGraphNode) | on start | memorize_metric |
| discord.adapter.started | counter | graph (TSDBGraphNode) | on start complete | memorize_metric |
| discord.adapter.stopping | counter | graph (TSDBGraphNode) | on stop | memorize_metric |
| discord.adapter.stopped | counter | graph (TSDBGraphNode) | on stop complete | memorize_metric |
| discord.message.sent | counter | graph (TSDBGraphNode) | per message sent | memorize_metric |
| discord.message.received | counter | graph (TSDBGraphNode) | per message received | memorize_metric |
| discord.tool.executed | counter | graph (TSDBGraphNode) | per tool execution | memorize_metric |
| discord.connection.established | counter | graph (TSDBGraphNode) | on connection | memorize_metric |
| discord.connection.lost | counter | graph (TSDBGraphNode) | on disconnect | memorize_metric |
| discord.connection.reconnecting | counter | graph (TSDBGraphNode) | on reconnect attempt | memorize_metric |
| discord.connection.failed | counter | graph (TSDBGraphNode) | on connection failure | memorize_metric |
| service_status | gauge | in-memory | on get_status() call | get_status() |
| service_capabilities | list | in-memory | static | get_capabilities() |
| latency_ms | gauge | calculated from client | real-time | client.latency * 1000 |
| uptime_seconds | gauge | calculated | real-time | time since start |
| rate_limiter_stats | dict | in-memory | per request | rate_limiter.get_stats() |
| error_handler_stats | dict | in-memory | per error | error_handler.get_error_stats() |
| service_correlations | records | persistent | per operation | ServiceCorrelation |
| audit_events | records | via audit service | per action | AuditLogger |

## Data Structures

### Service Status
```python
{
    "service_name": "DiscordAdapter",
    "service_type": "adapter",
    "is_healthy": True,
    "uptime_seconds": 3661.5,
    "metrics": {
        "latency": 45.2
    }
}
```

### Service Capabilities
```python
{
    "service_name": "DiscordAdapter",
    "actions": [
        # Communication capabilities
        "send_message",
        "fetch_messages",
        # Tool capabilities
        "execute_tool",
        "list_tools",
        # WiseAuthority capabilities
        "fetch_guidance",
        "send_deferral",
        "check_authorization",
        "request_approval",
        "get_guidance",
        "get_pending_deferrals",
        "resolve_deferral",
        "grant_permission",
        "revoke_permission",
        "list_permissions"
    ],
    "version": "1.0.0",
    "dependencies": ["discord.py"]
}
```

### Rate Limiter Statistics
```python
{
    "requests": 1523,
    "rate_limited": 12,
    "total_wait_time": 45.6,
    "max_wait_time": 8.2,
    "average_wait_time": 0.03
}
```

### Error Handler Statistics
```python
{
    "error_counts": {
        "channel_12345_HTTPException": 3,
        "connection_ConnectionClosed": 1,
        "api_messages_RateLimited": 2
    },
    "threshold": 5,
    "window_minutes": 5.0
}
```

### Service Correlation Example
```python
{
    "correlation_id": "uuid4-string",
    "service_type": "discord",
    "handler_name": "DiscordAdapter",
    "action_type": "speak|send_deferral|fetch_guidance|execute_tool",
    "request_data": {
        "service_type": "discord",
        "method_name": "send_message",
        "channel_id": "12345",
        "parameters": {"content": "Hello"},
        "request_timestamp": datetime
    },
    "response_data": {
        "success": True,
        "result_summary": "Message sent successfully",
        "execution_time_ms": 156.7,
        "response_timestamp": datetime
    },
    "status": "COMPLETED|PENDING|ERROR",
    "created_at": datetime,
    "updated_at": datetime
}
```

### Graph-Based Telemetry Tags
```python
{
    "adapter_type": "discord",
    "channel_id": "12345",
    "author_id": "67890",
    "execution_time": "156.7",
    "success": "true",
    "tool_name": "get_channel_info",
    "status": "success",
    "guilds": "5",
    "users": "1250",
    "error": "connection_timeout",
    "attempt": "3",
    "max_attempts": "10"
}
```

## API Access Patterns

### Current Access
- **Telemetry**: All metrics accessible via memory graph queries and TSDB consolidation
- **Status**: `get_status()` method provides real-time service health
- **Capabilities**: `get_capabilities()` method lists all supported actions
- **Statistics**: Component-level stats via `rate_limiter.get_stats()` and `error_handler.get_error_stats()`

### Recommended API Endpoints

#### Discord Adapter Status
```
GET /v1/telemetry/discord-adapter
```
Returns complete adapter telemetry:
```json
{
    "service_name": "DiscordAdapter",
    "is_healthy": true,
    "uptime_seconds": 3661.5,
    "connection_status": {
        "connected": true,
        "guild_count": 5,
        "latency_ms": 45.2,
        "reconnect_attempts": 0
    },
    "message_stats": {
        "sent": 245,
        "received": 1876,
        "failed": 3
    },
    "tool_executions": {
        "total": 89,
        "successful": 85,
        "failed": 4
    },
    "deferrals": {
        "sent": 12,
        "resolved": 8,
        "pending": 4
    },
    "rate_limiting": {
        "requests": 1523,
        "rate_limited": 12,
        "average_wait_ms": 30
    },
    "errors": {
        "total_errors": 6,
        "error_types": ["HTTPException", "ConnectionClosed"],
        "within_threshold": true
    }
}
```

#### Discord Connection Health
```
GET /v1/telemetry/discord-connection
```
Returns connection-specific metrics:
```json
{
    "connected": true,
    "ready": true,
    "guilds": 5,
    "users": 1250,
    "latency_ms": 45.2,
    "uptime_seconds": 3661.5,
    "reconnections": {
        "total_attempts": 3,
        "successful": 3,
        "last_reconnect": "2025-08-14T14:20:15Z"
    },
    "monitored_channels": [
        {
            "channel_id": "discord_12345",
            "display_name": "#general",
            "is_active": true,
            "message_count": 1234
        }
    ]
}
```

#### Discord Rate Limiting
```
GET /v1/telemetry/discord-rate-limits
```
Returns rate limiting statistics:
```json
{
    "global_limits": {
        "limit": 50,
        "window_seconds": 60,
        "remaining": 47
    },
    "endpoint_limits": {
        "channels/{id}/messages": {
            "limit": 5,
            "window_seconds": 5,
            "remaining": 3
        }
    },
    "statistics": {
        "total_requests": 1523,
        "rate_limited_count": 12,
        "total_wait_time_seconds": 45.6,
        "average_wait_ms": 30
    }
}
```

## Graph Storage

### Telemetry Nodes
All Discord adapter metrics are stored as TSDBGraphNode objects in the memory graph:
- **Scope**: "local"
- **Handler**: "adapter.discord"
- **Node Type**: "TSDB"
- **Attributes**: Include metric name, value, tags, and timestamp

### Persistent Nodes
Long-term operational data stored as specialized graph nodes:

#### DiscordDeferralNode
```python
{
    "id": "discord_deferral/{correlation_id}",
    "scope": "LOCAL",
    "deferral_id": "uuid",
    "task_id": "task_123",
    "thought_id": "thought_456",
    "reason": "Uncertain about user intent",
    "status": "pending|resolved|expired",
    "channel_id": "12345",
    "context": {"priority": "high"},
    "updated_at": datetime
}
```

#### DiscordApprovalNode
```python
{
    "id": "discord_approval/{message_id}",
    "scope": "LOCAL",
    "approval_id": "message_id",
    "action": "execute_command",
    "status": "approved|denied|timeout",
    "channel_id": "12345",
    "task_id": "task_123",
    "requester_id": "user_789",
    "resolver_id": "wa_456",
    "resolved_at": datetime
}
```

## Example Usage

### Query Discord Metrics
```python
# Get all Discord adapter metrics from last hour
from ciris_engine.logic.services.graph.memory import MemoryService

memory = get_memory_service()
metrics = await memory.search({
    "handler_name": "adapter.discord",
    "node_type": "TSDB",
    "created_at": {"$gte": datetime.now() - timedelta(hours=1)}
})

# Get message sent count
message_metrics = [m for m in metrics if m.metric_name == "discord.message.sent"]
total_messages = sum(float(m.value) for m in message_metrics)
```

### Get Real-Time Status
```python
# Get current adapter status
adapter = get_discord_adapter()
status = adapter.get_status()
print(f"Latency: {status.metrics['latency']:.1f}ms")
print(f"Healthy: {status.is_healthy}")

# Get rate limiting stats
rate_stats = adapter._rate_limiter.get_stats()
print(f"Rate limited: {rate_stats['rate_limited']} times")
```

### Monitor Connection Events
```python
# Query connection events from correlations
correlations = get_correlations_by_service("discord")
connection_events = [
    c for c in correlations
    if c.action_type in ["connection_established", "connection_lost"]
]

for event in connection_events:
    print(f"{event.action_type}: {event.timestamp}")
```

### Access Deferral History
```python
# Get pending deferrals from graph
deferrals = await memory.search({
    "node_type": "DISCORD_DEFERRAL",
    "status": "pending"
})

for deferral in deferrals:
    node = DiscordDeferralNode.from_graph_node(deferral)
    print(f"Deferral {node.deferral_id}: {node.reason}")
```

## Testing

### Test Files
- `tests/logic/adapters/discord/test_discord_adapter.py` - Main adapter tests
- `tests/logic/adapters/discord/test_discord_telemetry.py` - Telemetry-specific tests
- `tests/logic/adapters/discord/test_discord_rate_limiter.py` - Rate limiter tests
- `tests/logic/adapters/discord/test_discord_error_handler.py` - Error handler tests

### Validation Steps
1. **Telemetry Emission**: Verify metrics emitted for all major operations
2. **Graph Storage**: Confirm TSDBGraphNode creation and storage
3. **Service Correlations**: Validate correlation tracking for operations
4. **Status Accuracy**: Check health status reflects actual connection state
5. **Rate Limiting**: Test statistics tracking during rate-limited scenarios
6. **Error Handling**: Verify error statistics and escalation tracking

```python
async def test_discord_telemetry():
    adapter = DiscordAdapter(token="test", config=test_config)

    # Test telemetry emission
    await adapter._emit_telemetry("test.metric", 1.0, {"test": "tag"})

    # Verify graph storage
    memory = get_memory_service()
    nodes = await memory.search({
        "handler_name": "adapter.discord",
        "metric_name": "test.metric"
    })
    assert len(nodes) == 1
    assert nodes[0].value == 1.0

    # Test status method
    status = adapter.get_status()
    assert status.service_name == "DiscordAdapter"
    assert "latency" in status.metrics
```

## Configuration

### Telemetry Settings
```python
# Retry configuration affects correlation timing
retry_config = {
    "retry": {
        "global": {
            "max_retries": 3,
            "base_delay": 2.0,
            "max_delay": 30.0
        }
    }
}

# Rate limiter safety margin
rate_limiter = DiscordRateLimiter(safety_margin=0.1)  # 10% extra wait

# Error handler escalation
error_handler = DiscordErrorHandler()
error_handler._error_threshold = 5  # Errors before escalation
error_handler._error_window = timedelta(minutes=5)
```

### Discord Client Settings
```python
# Connection affects latency metrics
intents = discord.Intents.default()
intents.message_content = True
intents.guild_messages = True

client = discord.Client(intents=intents)
# client.latency provides real-time latency data
```

## Known Limitations

1. **Memory-Only Statistics**: Rate limiter and error handler stats reset on restart
2. **No Historical Aggregation**: Component stats don't maintain time-series data
3. **Discord API Dependency**: Latency and connection metrics depend on discord.py client
4. **Graph Query Performance**: Large telemetry datasets may slow graph queries
5. **No Cross-Guild Metrics**: Statistics not separated by Discord guild/server
6. **Limited Channel Analytics**: No per-channel performance metrics
7. **Audit Service Dependency**: Audit logging requires configured audit service

## Future Enhancements

1. **Persistent Statistics**: Store component statistics in Redis/database
2. **Historical Metrics**: Time-series data for rate limiting and error patterns
3. **Per-Guild Analytics**: Separate metrics by Discord server
4. **Channel Performance**: Per-channel message rates and response times
5. **Advanced Alerting**: Threshold-based alerts for connection issues
6. **Batch Telemetry**: Batch metric emissions for high-volume scenarios
7. **Prometheus Integration**: Export metrics to Prometheus for external monitoring
8. **Dashboard Support**: Real-time dashboard data endpoints

## Integration Points

### Memory Bus Integration
- **Metric Storage**: All telemetry flows through memory.memorize_metric()
- **Node Queries**: Persistent nodes accessible via memory.search()
- **Graph Relationships**: Links between deferrals, approvals, and messages

### Audit Service Integration
- **Connection Events**: Login/logout and connection state changes
- **Permission Changes**: Role grants and revocations
- **Message Events**: Sent/received message logging
- **Tool Executions**: Tool usage tracking
- **Deferral Operations**: WA requests and resolutions

### TSDB Consolidation
- **6-Hour Cycles**: Metrics consolidated for long-term storage
- **Aggregation**: Counts, averages, and trends computed
- **Retention**: Historical data management

## Monitoring Recommendations

### Critical Alerts
1. **Connection Loss**: Alert when `discord.connection.lost` exceeds threshold
2. **High Error Rate**: Monitor error handler statistics for escalation
3. **Rate Limiting**: Alert on excessive rate limiting events
4. **Service Unhealthy**: Monitor `is_healthy` status changes
5. **Deferral Backlog**: Alert on high pending deferral counts

### Performance Monitoring
1. **Latency Tracking**: Monitor `client.latency` for performance degradation
2. **Message Processing**: Track time between received and processed
3. **Tool Execution**: Monitor tool success rates and execution times
4. **Memory Usage**: Graph node count growth monitoring

### Operational Insights
1. **Usage Patterns**: Peak hours, channel activity, tool popularity
2. **Error Trends**: Common failure patterns and recovery effectiveness
3. **WA Effectiveness**: Deferral resolution times and approval rates
4. **Capacity Planning**: Message volumes and connection scaling needs

## Security Considerations

1. **Token Protection**: Bot tokens not logged in telemetry data
2. **Content Filtering**: Message content excluded from general telemetry
3. **User Privacy**: User IDs hashed in long-term storage where possible
4. **Permission Auditing**: All authorization changes fully logged
5. **Deferral Context**: Sensitive context data sanitized before storage
6. **Channel Access**: Telemetry respects Discord channel permissions

## Performance Considerations

1. **Async Operations**: All telemetry operations are non-blocking
2. **Memory Efficiency**: Component statistics use bounded collections
3. **Graph Writes**: Telemetry batched where possible to reduce graph load
4. **Query Optimization**: Indexed fields for common telemetry queries
5. **Connection Pooling**: Shared Discord client connection across components
6. **Rate Limit Compliance**: Telemetry doesn't trigger additional API calls
