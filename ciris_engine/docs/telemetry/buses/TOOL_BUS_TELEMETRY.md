# Tool Bus Telemetry

## Overview
The Tool Bus manages all tool execution operations across the CIRIS system. It serves as the central routing hub for tool services provided by various adapters (API, CLI, Discord) and core services (SecretsToolService). The bus handles tool discovery, routing, execution, and provides basic operational metrics.

## Telemetry Data Collected

### Bus-Level Metrics (from BaseBus)

| Metric Name | Type | Storage | Update Frequency | Access Method |
|------------|------|---------|------------------|---------------|
| processed_count | counter | in-memory | per-message | `get_stats()` |
| failed_count | counter | in-memory | on-failure | `get_stats()` |
| queue_size | gauge | in-memory | real-time | `get_stats()` |
| running | boolean | in-memory | on-change | `get_stats()` |

### Tool Operation Metrics (Implicit)

| Metric Name | Type | Storage | Update Frequency | Access Method |
|------------|------|---------|------------------|---------------|
| tool_executions | counter | not tracked | per-call | not exposed |
| tool_failures | counter | not tracked | on-failure | not exposed |
| tool_routing_attempts | counter | not tracked | per-call | not exposed |
| service_discovery_calls | counter | not tracked | per-discovery | not exposed |
| multi_service_selections | counter | not tracked | per-routing | not exposed |

### Service-Level Metrics (from individual ToolServices)

| Metric Name | Type | Storage | Update Frequency | Access Method |
|------------|------|---------|------------------|---------------|
| request_count | counter | per-service | per-call | service `get_status()` |
| error_count | counter | per-service | on-error | service `get_status()` |
| error_rate | calculated | per-service | on-demand | service `get_status()` |
| uptime_seconds | gauge | per-service | on-demand | service `get_status()` |
| healthy | boolean | per-service | on-demand | service `is_healthy()` |
| available_tools | gauge | per-service | static | service `_collect_custom_metrics()` |

## Data Structures

### Bus Statistics (from BaseBus)
```python
{
    "service_type": "tool",                 # ServiceType.TOOL.value
    "queue_size": 0,                        # Current message queue size
    "processed": 0,                         # Total processed messages
    "failed": 0,                            # Total failed messages
    "running": True                         # Bus processing status
}
```

### Tool Execution Results (ToolExecutionResult)
```python
{
    "tool_name": "recall_secret",
    "status": "completed",                  # COMPLETED/FAILED/NOT_FOUND
    "success": True,
    "data": {"exists": True, "decrypted": False},
    "error": None,
    "correlation_id": "secrets_recall_secret_1723640100.5"
}
```

### Service Discovery Information (Implicit)
```python
{
    "total_tool_services": 3,               # Count of registered tool services
    "services_by_type": {
        "APIToolService": 1,
        "SecretsToolService": 1,
        "DiscordToolService": 1
    },
    "tools_available": {
        "curl": ["APIToolService"],
        "recall_secret": ["SecretsToolService"],
        "self_help": ["SecretsToolService"]
    },
    "routing_strategy": "prefer_api_service"  # Current routing logic
}
```

### Individual Service Metrics (from BaseService)
```python
{
    "service_name": "SecretsToolService",
    "uptime_seconds": 36420.5,
    "request_count": 156.0,                 # Tool executions
    "error_count": 3.0,
    "error_rate": 0.0192,                   # ~1.9% error rate
    "healthy": 1.0,                         # 1.0 if healthy, 0.0 if not
    "available_tools": 3.0                  # Custom metric: tool count
}
```

## API Access Patterns

### Current Access
- **No Bus-Level Metrics**: Tool bus doesn't expose metrics endpoint
- **No Aggregated Tool Metrics**: Individual service metrics not consolidated
- **Basic Service Registry**: Can discover services but not their metrics
- **Health Check Available**: `is_healthy()` method exists but not exposed

### Recommended Endpoints

#### Tool Bus Statistics
```
GET /v1/telemetry/tools/stats
```
Returns tool bus operational statistics:
```json
{
    "bus_stats": {
        "service_type": "tool",
        "queue_size": 0,
        "processed": 1543,
        "failed": 12,
        "running": true
    },
    "service_discovery": {
        "total_tool_services": 3,
        "healthy_services": 3,
        "available_tools": 15
    },
    "routing_metrics": {
        "total_executions": 1531,
        "routing_failures": 12,
        "multi_service_tools": 2
    }
}
```

#### Tool Execution Summary
```
GET /v1/telemetry/tools/execution
```
Returns tool execution statistics:
```json
{
    "execution_stats": {
        "total_executions": 1531,
        "successful_executions": 1519,
        "failed_executions": 12,
        "success_rate": "99.22%"
    },
    "tools_by_usage": {
        "recall_secret": 856,
        "curl": 523,
        "http_get": 152
    },
    "services_by_usage": {
        "SecretsToolService": 856,
        "APIToolService": 675
    }
}
```

#### Service Health Overview
```
GET /v1/telemetry/tools/services
```
Returns individual tool service metrics:
```json
{
    "services": {
        "SecretsToolService": {
            "healthy": true,
            "uptime_seconds": 36420.5,
            "request_count": 856,
            "error_count": 3,
            "error_rate": "0.35%",
            "available_tools": 3,
            "tools": ["recall_secret", "update_secrets_filter", "self_help"]
        },
        "APIToolService": {
            "healthy": true,
            "uptime_seconds": 36420.5,
            "request_count": 675,
            "error_count": 9,
            "error_rate": "1.33%",
            "available_tools": 3,
            "tools": ["curl", "http_get", "http_post"]
        }
    }
}
```

## Graph Storage

### Current State
- **No Direct Graph Storage**: Tool bus doesn't store metrics in graph
- **Service Metrics Only**: Individual tool services may track via BaseService
- **No Execution History**: Tool execution results not persisted

### Potential Graph Storage (Future Enhancement)
- **Tool Execution Nodes**: Store ToolExecutionResult objects
- **Service Performance Metrics**: Track service-level performance
- **Tool Usage Patterns**: Analyze tool usage trends over time

### Recommended Graph Nodes
```python
# Tool execution events
{
    "type": "TOOL_EXECUTION",
    "properties": {
        "tool_name": "recall_secret",
        "service_name": "SecretsToolService",
        "execution_time_ms": 12.5,
        "success": True,
        "timestamp": "2025-08-14T13:30:00Z"
    }
}

# Service performance snapshots
{
    "type": "TOOL_SERVICE_METRICS",
    "properties": {
        "service_name": "SecretsToolService",
        "request_count": 856,
        "error_rate": 0.0035,
        "available_tools": 3,
        "timestamp": "2025-08-14T13:30:00Z"
    }
}
```

## Example Usage

### Get Tool Bus Statistics
```python
# Within CIRIS codebase
tool_bus = service_registry.get_service(ServiceType.TOOL)
stats = tool_bus.get_stats()
# Returns: {"service_type": "tool", "queue_size": 0, "processed": 1543, ...}
```

### Execute Tool and Track Result
```python
# Execute a tool
result = await tool_bus.execute_tool(
    tool_name="recall_secret",
    parameters={"secret_uuid": "abc123", "purpose": "test"},
    handler_name="default"
)

# Result contains execution metadata
print(f"Tool: {result.tool_name}")
print(f"Status: {result.status}")
print(f"Success: {result.success}")
print(f"Correlation ID: {result.correlation_id}")
```

### Check Service Health
```python
# Check individual service health
is_healthy = await tool_bus.is_healthy()

# Get detailed service information
available_tools = await tool_bus.get_available_tools()
capabilities = await tool_bus.get_capabilities()
```

### Service Discovery Example
```python
# Get all available tools (aggregated across services)
all_tools = await tool_bus.get_available_tools()

# Get detailed tool information
tool_info = await tool_bus.get_tool_info("recall_secret")
all_tool_info = await tool_bus.get_all_tool_info()
```

## Testing

### Test Files
- **Bus Tests**: `tests/logic/buses/test_tool_bus.py` (missing - should be created)
- **Service Tests**: `tests/logic/services/tools/test_secrets_tool_service.py` - Exists

### Validation Steps
1. Execute a tool through the bus
2. Verify tool routing works correctly
3. Check service discovery finds appropriate services
4. Confirm error handling for unknown tools
5. Test multi-service tool routing logic

```python
# Example test for tool bus metrics
async def test_tool_bus_metrics():
    tool_bus = get_service(ServiceType.TOOL)

    # Get initial stats
    initial_stats = tool_bus.get_stats()
    initial_processed = initial_stats["processed"]

    # Execute a tool
    result = await tool_bus.execute_tool(
        tool_name="self_help",
        parameters={},
        handler_name="default"
    )

    # Verify execution succeeded
    assert result.success is True
    assert result.tool_name == "self_help"

    # Check if stats updated (if queued messages are used)
    # Note: Current implementation is synchronous, so no queue stats change
    current_stats = tool_bus.get_stats()
    # assert current_stats["processed"] >= initial_processed
```

## Configuration

### Bus Configuration
```python
{
    "max_queue_size": 1000,                 # Maximum queued messages
    "service_discovery_timeout": 5.0,       # Service discovery timeout
    "tool_execution_timeout": 30.0,         # Default tool execution timeout
}
```

### Service Selection Strategy
- **Single Service Tools**: Use the only service that supports the tool
- **Multi-Service Tools**: Prefer APIToolService over SecretsToolService
- **Future Enhancement**: Context-aware routing based on channel/guild/domain

### Tool Categories
- **Security Tools**: `recall_secret`, `update_secrets_filter` (SecretsToolService)
- **HTTP Tools**: `curl`, `http_get`, `http_post` (APIToolService)
- **Knowledge Tools**: `self_help` (SecretsToolService)

## Known Limitations

1. **No Bus-Level Tool Metrics**: Tool execution counts, latencies, and patterns not tracked
2. **No Service Performance Tracking**: Service-level metrics not aggregated or exposed
3. **Limited Routing Logic**: Simple preference-based routing without load balancing
4. **No Tool Execution History**: Results not persisted for analysis
5. **No Rate Limiting**: No protection against tool execution flooding
6. **Synchronous Operations**: All tool operations block the calling thread
7. **No Circuit Breaker**: No protection against failing tool services
8. **No Caching**: Tool results not cached for repeated calls

## Future Enhancements

1. **Comprehensive Tool Metrics**: Track execution counts, success rates, latencies per tool
2. **Service Load Balancing**: Intelligent routing based on service health and load
3. **Tool Execution Cache**: Cache results for idempotent tools
4. **Circuit Breaker Pattern**: Protect against failing services
5. **Rate Limiting**: Per-service and per-handler rate limiting
6. **Execution History**: Store tool execution patterns in graph for analysis
7. **Advanced Routing**: Context-aware routing (channel, domain, user permissions)
8. **Async Tool Support**: Better support for long-running tools
9. **Tool Performance Analytics**: Analyze tool usage patterns and optimization opportunities
10. **Service Metrics Aggregation**: Consolidated metrics across all tool services

## Integration Points

- **ServiceRegistry**: Discovers and manages tool service instances
- **TimeService**: Provides consistent timestamps for correlation IDs
- **Individual Tool Services**: SecretsToolService, APIToolService, DiscordToolService
- **Adapter Services**: CLI, API, Discord adapters provide tool services
- **BaseService**: All tool services inherit metrics and health checking

## Monitoring Recommendations

1. **Tool Execution Success Rate**: Alert on elevated failure rates (>5%)
2. **Service Health**: Monitor individual tool service health status
3. **Tool Usage Patterns**: Track which tools are used most frequently
4. **Service Discovery Failures**: Alert when no service supports requested tools
5. **Queue Depth**: Monitor message queue size (currently minimal usage)
6. **Response Times**: Track tool execution latencies for performance optimization
7. **Service Distribution**: Monitor which services handle most tool executions
8. **Error Categories**: Categorize tool failures for better troubleshooting

## Performance Considerations

1. **Service Discovery Overhead**: Each tool execution triggers service discovery
2. **Reflection-Based Access**: Uses reflection to access registry internal structure
3. **No Connection Pooling**: Each tool execution creates new service connections
4. **Synchronous Execution**: All operations block until completion
5. **No Batch Operations**: Tools executed individually, not in batches
6. **Memory Growth**: Tool services may accumulate results in memory (APIToolService)

## Security Considerations

1. **Tool Access Control**: No built-in authorization for tool execution
2. **Parameter Validation**: Relies on individual services for parameter validation
3. **Secret Exposure**: Secrets tools handle sensitive data (properly secured in SecretsToolService)
4. **HTTP Tools**: API tools can make external requests (require careful parameter validation)
5. **Service Isolation**: Tool services run in same process space (no sandboxing)
