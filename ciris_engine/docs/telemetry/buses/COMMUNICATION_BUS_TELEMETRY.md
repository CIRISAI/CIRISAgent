# Communication Bus Telemetry

## Overview
The Communication Bus manages all communication operations across multiple adapters (Discord, API, CLI). It handles message routing, channel-based switching, and adapter failover. Unlike other buses, it has minimal direct telemetry collection at the bus level, with most detailed metrics collected by individual communication service adapters.

## Telemetry Data Collected

### Bus-Level Metrics (from BaseBus)

| Metric Name | Type | Storage | Update Frequency | Access Method |
|------------|------|---------|------------------|---------------|
| queue_size | gauge | in-memory | real-time | `get_stats()` |
| processed | counter | in-memory | per-message | `get_stats()` |
| failed | counter | in-memory | on-error | `get_stats()` |
| running | boolean | in-memory | on-state-change | `get_stats()` |
| service_type | string | static | initialization | `get_stats()` |

### Adapter-Level Metrics (APICommunicationService Example)

| Metric Name | Type | Storage | Update Frequency | Access Method |
|------------|------|---------|------------------|---------------|
| requests_handled | counter | in-memory | per-request | `get_status()` |
| error_count | counter | in-memory | on-error | `get_status()` |
| avg_response_time_ms | gauge | in-memory | calculated | `get_status()` |
| queued_responses | gauge | in-memory | real-time | `get_status()` |
| websocket_clients | gauge | in-memory | real-time | `get_status()` |
| uptime_seconds | gauge | in-memory | on-demand | `get_status()` |

### Service Correlation Metrics (via persistence)

| Metric Name | Type | Storage | Update Frequency | Access Method |
|------------|------|---------|------------------|---------------|
| speak_correlations | counter | SQLite DB | per-send | correlation query |
| observe_correlations | counter | SQLite DB | per-receive | correlation query |
| correlation_response_times | histogram | SQLite DB | per-operation | correlation query |
| channel_activity_count | counter | SQLite DB | per-message | correlation query |
| adapter_usage_distribution | histogram | SQLite DB | per-operation | correlation query |

### Channel Routing Metrics (Implicit)

| Metric Name | Type | Storage | Update Frequency | Access Method |
|------------|------|---------|------------------|---------------|
| discord_routes | counter | logs only | per-route | log analysis |
| api_routes | counter | logs only | per-route | log analysis |
| cli_routes | counter | logs only | per-route | log analysis |
| default_channel_lookups | counter | logs only | per-lookup | log analysis |
| routing_failures | counter | logs only | on-failure | log analysis |

## Data Structures

### BaseBus Statistics
```python
{
    "service_type": "communication",    # Service type managed
    "queue_size": 12,                  # Messages queued for async processing
    "processed": 45678,                # Total messages processed
    "failed": 23,                      # Failed message processing attempts
    "running": true                    # Bus processing loop status
}
```

### Communication Adapter Status (API Example)
```python
{
    "service_name": "APICommunicationService",
    "service_type": "communication",
    "is_healthy": true,
    "uptime_seconds": 36420.5,
    "last_error": null,
    "metrics": {
        "requests_handled": 15234.0,       # Total send_message calls
        "error_count": 23.0,               # Failed operations
        "avg_response_time_ms": 12.3,      # Average response time
        "queued_responses": 5.0,           # Pending HTTP responses
        "websocket_clients": 3.0           # Active WebSocket connections
    }
}
```

### Service Correlation Record
```python
{
    "correlation_id": "uuid-4567",
    "service_type": "api",
    "handler_name": "APIAdapter",
    "action_type": "speak",               # "speak" | "observe"
    "request_data": {
        "service_type": "api",
        "method_name": "speak",
        "channel_id": "api_user123",
        "parameters": {
            "content": "Hello world",
            "channel_id": "api_user123"
        },
        "request_timestamp": "2025-08-14T13:30:00Z"
    },
    "response_data": {
        "success": true,
        "result_summary": "Message sent",
        "execution_time_ms": 12.3,
        "response_timestamp": "2025-08-14T13:30:00Z"
    },
    "status": "completed",
    "created_at": "2025-08-14T13:30:00Z"
}
```

### Channel Routing Patterns
```python
{
    "channel_prefixes": {
        "discord_": "DiscordAdapter",      # Discord channels
        "api_": "APICommunicationService", # API channels
        "ws:": "APICommunicationService",  # WebSocket channels
        "cli_": "CLIAdapter"               # CLI channels
    },
    "routing_stats": {
        "total_routes": 1523,
        "successful_routes": 1498,
        "failed_routes": 25,
        "default_channel_fallbacks": 45
    }
}
```

## API Access Patterns

### Current Access
- **Bus Stats**: `CommunicationBus.get_stats()` available but not exposed via API
- **Adapter Status**: `service.get_status()` available on individual adapters
- **Correlations**: Stored in persistence layer, accessible via database queries
- **No Direct Endpoints**: Communication telemetry not exposed through API

### Recommended Endpoints

#### Communication Bus Statistics
```
GET /v1/telemetry/communication/bus
```
Returns bus-level operational metrics:
```json
{
    "bus": {
        "service_type": "communication",
        "queue_size": 12,
        "processed": 45678,
        "failed": 23,
        "running": true,
        "failure_rate": "0.05%"
    },
    "adapters": {
        "total_count": 3,
        "healthy_count": 3,
        "adapter_types": ["discord", "api", "cli"]
    }
}
```

#### Adapter Performance Metrics
```
GET /v1/telemetry/communication/adapters
```
Returns detailed adapter metrics:
```json
{
    "adapters": [
        {
            "name": "APICommunicationService",
            "type": "api",
            "is_healthy": true,
            "uptime_seconds": 36420.5,
            "metrics": {
                "requests_handled": 15234,
                "error_count": 23,
                "avg_response_time_ms": 12.3,
                "queued_responses": 5,
                "websocket_clients": 3
            }
        },
        {
            "name": "DiscordAdapter",
            "type": "discord",
            "is_healthy": true,
            "metrics": {
                "messages_sent": 8765,
                "guild_count": 1,
                "channel_count": 12
            }
        }
    ]
}
```

#### Message Flow Analytics
```
GET /v1/telemetry/communication/flows
```
Returns message flow patterns:
```json
{
    "time_period": "1h",
    "total_messages": 1523,
    "by_direction": {
        "outgoing": 856,  // "speak" correlations
        "incoming": 667   // "observe" correlations
    },
    "by_adapter": {
        "api": 756,
        "discord": 534,
        "cli": 233
    },
    "by_channel_type": {
        "api_channels": 756,
        "discord_channels": 534,
        "cli_channels": 233
    },
    "routing_stats": {
        "successful_routes": 1498,
        "failed_routes": 25,
        "default_fallbacks": 45
    }
}
```

## Graph Storage (via ServiceCorrelation)

### Correlation Records Stored
Communication operations create ServiceCorrelation records in the persistence layer:

- **Type**: `SERVICE_INTERACTION`
- **Action Types**: `"speak"` (outgoing), `"observe"` (incoming)
- **Storage**: SQLite correlations table
- **Indexing**: By channel_id, timestamp, correlation_id

### Database Schema
```sql
-- Correlations table stores all communication events
CREATE TABLE correlations (
    correlation_id TEXT PRIMARY KEY,
    service_type TEXT NOT NULL,
    handler_name TEXT NOT NULL,
    action_type TEXT NOT NULL,
    request_data TEXT,  -- JSON ServiceRequestData
    response_data TEXT, -- JSON ServiceResponseData
    status TEXT NOT NULL,
    created_at TIMESTAMP,
    updated_at TIMESTAMP,
    timestamp TIMESTAMP
);

-- Indexes for communication queries
CREATE INDEX idx_correlations_channel ON correlations
    ((json_extract(request_data, '$.channel_id')));
CREATE INDEX idx_correlations_action_type ON correlations (action_type);
CREATE INDEX idx_correlations_timestamp ON correlations (timestamp);
```

## Example Usage

### Get Communication Bus Stats
```python
# Access bus statistics
from ciris_engine.logic.registries.base import ServiceRegistry
from ciris_engine.schemas.runtime.enums import ServiceType

communication_bus = service_registry.get_service_bus(ServiceType.COMMUNICATION)
stats = communication_bus.get_stats()

print(f"Queue size: {stats['queue_size']}")
print(f"Messages processed: {stats['processed']}")
print(f"Failed messages: {stats['failed']}")
```

### Check Adapter Health
```python
# Get all communication adapters
adapters = service_registry.get_services_by_type(ServiceType.COMMUNICATION)

for adapter in adapters:
    if hasattr(adapter, 'get_status'):
        status = adapter.get_status()
        print(f"{status.service_name}: healthy={status.is_healthy}")
        print(f"  Requests handled: {status.metrics.get('requests_handled', 0)}")
```

### Query Message Correlations
```python
# Query recent communication activity
from ciris_engine.logic.persistence import get_correlations_by_channel

# Get recent messages for a specific channel
messages = get_correlations_by_channel(
    channel_id="api_user123",
    limit=50,
    before=None
)

print(f"Found {len(messages)} recent messages")
for msg in messages:
    print(f"  {msg.action_type}: {msg.request_data.get('content', '')}")
```

### Monitor Channel Routing
```python
# Check default channel configuration
communication_bus = service_registry.get_service_bus(ServiceType.COMMUNICATION)
default_channel = await communication_bus.get_default_channel()

if default_channel:
    print(f"Default channel: {default_channel}")

    # Determine which adapter handles this channel
    if default_channel.startswith("discord_"):
        print("  -> Routed to Discord adapter")
    elif default_channel.startswith("api_"):
        print("  -> Routed to API adapter")
    elif default_channel.startswith("cli_"):
        print("  -> Routed to CLI adapter")
```

## Testing

### Test Files
Communication bus tests would typically be in:
- `tests/logic/buses/test_communication_bus.py` (not yet created)
- `tests/adapters/api/test_api_communication.py` (exists)
- `tests/adapters/discord/test_discord_adapter.py` (likely exists)

### Validation Steps
1. Send message through bus
2. Verify correlation record created
3. Check adapter metrics increment
4. Confirm channel routing works
5. Test fallback to default channel

```python
async def test_communication_bus_metrics():
    comm_bus = get_service_bus(ServiceType.COMMUNICATION)

    # Get initial stats
    initial_stats = comm_bus.get_stats()
    initial_processed = initial_stats['processed']

    # Send a message
    success = await comm_bus.send_message(
        channel_id="api_test123",
        content="Test message",
        handler_name="test_handler"
    )

    # Wait for processing
    await asyncio.sleep(0.1)

    # Check metrics updated
    final_stats = comm_bus.get_stats()
    assert final_stats['processed'] > initial_processed
    assert success == True
```

## Known Limitations

1. **No Real-Time Metrics**: Communication bus lacks comprehensive real-time telemetry collection
2. **Limited Routing Analytics**: Channel routing patterns not systematically tracked
3. **No Performance Baselines**: No SLA tracking or performance trend analysis
4. **Adapter Inconsistency**: Different adapters implement different levels of metrics
5. **No Cross-Adapter Analytics**: No unified view across all communication channels
6. **Missing Rate Limiting**: No built-in rate limiting or throttling metrics
7. **No Message Size Tracking**: Message payload sizes not tracked systematically

## Future Enhancements

1. **Comprehensive Bus Metrics**: Track routing decisions, latencies, and throughput
2. **Unified Adapter Interface**: Standardize metrics collection across all adapters
3. **Real-Time Dashboards**: Live monitoring of communication flows and health
4. **Performance Baselines**: SLA tracking and alerting for communication operations
5. **Message Analytics**: Content size, type distribution, and pattern analysis
6. **Rate Limiting**: Built-in rate limiting with configurable policies
7. **Load Balancing**: Intelligent routing based on adapter health and load
8. **Historical Analytics**: Trend analysis and capacity planning
9. **Channel Health Scores**: Composite health metrics per channel/adapter

## Integration Points

- **TimeService**: Provides timestamps for correlation records and bus metrics
- **ServiceRegistry**: Manages communication adapter discovery and routing
- **Persistence Layer**: Stores ServiceCorrelation records for all communication events
- **TelemetryService**: Could integrate for unified metrics collection (not currently implemented)
- **AuditService**: May track communication events for compliance (via correlations)

## Monitoring Recommendations

1. **Bus Queue Health**: Monitor queue size and processing rates
   - Alert if queue size > 100 for >1 minute
   - Alert if failure rate > 5% over 10 minutes

2. **Adapter Health**: Track individual adapter availability and performance
   - Alert if any adapter unhealthy for >30 seconds
   - Alert if response time increases >200% from baseline

3. **Channel Routing**: Monitor routing success and fallback usage
   - Alert if routing failures >1% of requests
   - Alert if default channel fallbacks increase significantly

4. **Message Flow Patterns**: Track communication volume and distribution
   - Alert on unusual spikes or drops in message volume
   - Monitor for imbalanced load across adapters

5. **Correlation Data Growth**: Monitor persistence layer growth
   - Track correlation record accumulation rate
   - Implement archival/cleanup policies for old records

## Configuration

### Bus Settings
```python
{
    "max_queue_size": 1000,           # Maximum queued messages
    "processing_timeout": 0.1,        # Queue polling timeout (seconds)
    "enable_routing_logs": true,      # Log channel routing decisions
    "default_channel_priority": [     # Adapter priority for default channel
        "discord", "api", "cli"
    ]
}
```

### Adapter Configuration
Each communication adapter may have specific telemetry settings:

```python
{
    "api_adapter": {
        "max_response_times": 100,     # Response time history size
        "websocket_timeout": 30,       # WebSocket connection timeout
        "enable_correlations": true    # Create correlation records
    },
    "discord_adapter": {
        "rate_limit_tracking": true,   # Track Discord rate limits
        "guild_metrics": true,         # Collect per-guild metrics
        "enable_correlations": true
    }
}
```

## Performance Considerations

1. **Queue Management**: Bus queue can become bottleneck under high load
2. **Correlation Overhead**: Creating correlation records adds latency
3. **Memory Usage**: Adapter metrics stored in memory, not persistent
4. **Database Growth**: Correlation records accumulate without cleanup
5. **Synchronous Operations**: Some operations bypass async queue, limiting scalability
6. **Channel Resolution**: Default channel lookup requires registry iteration
7. **Adapter Discovery**: Service discovery overhead on each routing decision
