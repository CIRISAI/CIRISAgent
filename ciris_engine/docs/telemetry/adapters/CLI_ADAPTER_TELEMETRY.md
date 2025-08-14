# CLI Adapter Telemetry

## Overview
The CLI Adapter (CLIAdapter) is a multi-protocol service implementing CommunicationService, ToolService, and WiseAuthorityService protocols for command-line interface interaction. It provides comprehensive telemetry through graph-based metrics, service correlations, audit logging, and component-specific statistics tracking. The CLI Adapter supports both interactive and non-interactive modes, with specialized telemetry for piped input processing and tool execution.

## Telemetry Data Collected

| Metric Name | Type | Storage | Update Frequency | Access Method |
|-------------|------|---------|------------------|---------------|
| cli.adapter.starting | counter | graph (TSDBGraphNode) | on start | memorize_metric |
| cli.adapter.started | counter | graph (TSDBGraphNode) | on start complete | memorize_metric |
| cli.adapter.stopping | counter | graph (TSDBGraphNode) | on stop | memorize_metric |
| cli.adapter.stopped | counter | graph (TSDBGraphNode) | on stop complete | memorize_metric |
| cli.tool.executed | counter | graph (TSDBGraphNode) | per tool execution | memorize_metric |
| cli.message.processed | counter | graph (TSDBGraphNode) | per message processed | memorize_metric |
| service_status | gauge | in-memory | on get_status() call | get_status() |
| service_capabilities | list | in-memory | static | get_capabilities() |
| uptime_seconds | gauge | calculated | real-time | time since start |
| available_tools_count | gauge | in-memory | static | len(available_tools) |
| interactive_mode | boolean | in-memory | static | configuration |
| service_correlations | records | persistent | per operation | ServiceCorrelation |
| piped_input_lines | counter | buffered | on piped input detection | observer |
| input_task_status | gauge | in-memory | runtime state | task monitoring |

## Data Structures

### Service Status
```python
{
    "service_name": "CLIAdapter",
    "service_type": "adapter",
    "is_healthy": True,
    "uptime_seconds": 3661.5,
    "metrics": {
        "interactive": True,
        "running": True,
        "available_tools": 3
    },
    "last_error": None,
    "custom_metrics": None,
    "last_health_check": "2025-08-14T14:20:15Z"
}
```

### Service Capabilities
```python
{
    "service_name": "CLIAdapter",
    "actions": [
        "send_message",
        "receive_message",
        "execute_tool",
        "list_tools"
    ],
    "version": "1.0.0",
    "dependencies": [],
    "metadata": {
        "service_type": "COMMUNICATION",
        "max_concurrent_operations": 1,
        "supports_streaming": False,
        "interactive": True,
        "available_tools": ["list_files", "read_file", "system_info"]
    }
}
```

### Tool Execution Result
```python
{
    "tool_name": "list_files",
    "status": "COMPLETED",
    "success": True,
    "data": {
        "success": True,
        "files": ["file1.txt", "file2.py"],
        "count": 2,
        "error": None
    },
    "error": None,
    "correlation_id": "uuid4-string"
}
```

### Service Correlation Example
```python
{
    "correlation_id": "uuid4-string",
    "service_type": "cli",
    "handler_name": "CLIAdapter",
    "action_type": "speak|observe|execute_tool",
    "request_data": {
        "service_type": "communication",
        "method_name": "send_message",
        "channel_id": "cli_12345_abcd1234",
        "parameters": {"content": "Hello from CLI"},
        "request_timestamp": datetime,
        "thought_id": None,
        "task_id": None,
        "timeout_seconds": None
    },
    "response_data": {
        "success": True,
        "result_summary": "Message sent to cli_12345_abcd1234",
        "execution_time_ms": 10.0,
        "response_timestamp": datetime,
        "result_type": None,
        "result_size": None,
        "error_type": None,
        "error_message": None,
        "error_traceback": None,
        "tokens_used": None,
        "memory_bytes": None
    },
    "status": "COMPLETED|PENDING|ERROR",
    "created_at": datetime,
    "updated_at": datetime,
    "timestamp": datetime,
    "correlation_type": "SERVICE_INTERACTION",
    "metric_data": None,
    "log_data": None,
    "trace_context": None,
    "retention_policy": "raw",
    "ttl_seconds": None,
    "parent_correlation_id": None
}
```

### Graph-Based Telemetry Tags
```python
{
    "adapter_type": "cli",
    "interactive": "true",
    "tool_name": "list_files",
    "execution_time_ms": "45.2",
    "success": "true",
    "message_id": "cli_12345_message",
    "channel_id": "cli_12345_abcd1234",
    "piped_input": "false",
    "buffered_lines": "0"
}
```

### CLI Observer Telemetry
```python
{
    "buffered_input_lines": 5,
    "interactive_mode": False,
    "piped_input_detected": True,
    "stop_event_set": False,
    "input_task_running": True,
    "processed_messages": 12,
    "channel_id": "cli_user@hostname",
    "processing_delay_seconds": 5.0
}
```

## API Access Patterns

### Current Access
- **Telemetry**: All metrics accessible via memory graph queries and TSDB consolidation
- **Status**: `get_status()` method provides real-time service health
- **Capabilities**: `get_capabilities()` method lists all supported actions
- **Tool Information**: Tool schemas and info via `get_tool_info()` and `get_all_tool_info()`

### Recommended API Endpoints

#### CLI Adapter Status
```
GET /v1/telemetry/cli-adapter
```
Returns complete adapter telemetry:
```json
{
    "service_name": "CLIAdapter",
    "is_healthy": true,
    "uptime_seconds": 3661.5,
    "mode": {
        "interactive": true,
        "running": true,
        "piped_input": false
    },
    "tool_stats": {
        "available_tools": 3,
        "total_executions": 89,
        "successful_executions": 85,
        "failed_executions": 4,
        "tools": {
            "list_files": {"executions": 45, "avg_time_ms": 12.3},
            "read_file": {"executions": 32, "avg_time_ms": 23.1},
            "system_info": {"executions": 12, "avg_time_ms": 156.7}
        }
    },
    "message_stats": {
        "messages_sent": 245,
        "messages_received": 134,
        "messages_processed": 134,
        "processing_errors": 2
    },
    "input_handling": {
        "buffered_lines": 0,
        "input_task_active": true,
        "stop_event_set": false,
        "last_input_time": "2025-08-14T14:19:45Z"
    }
}
```

#### CLI Tools Status
```
GET /v1/telemetry/cli-tools
```
Returns tool-specific telemetry:
```json
{
    "available_tools": [
        {
            "name": "list_files",
            "category": "cli",
            "executions": 45,
            "success_rate": 0.96,
            "avg_execution_time_ms": 12.3,
            "last_execution": "2025-08-14T14:18:30Z",
            "parameters": {
                "path": {"type": "string", "default": ".", "required": false}
            }
        },
        {
            "name": "read_file",
            "category": "cli",
            "executions": 32,
            "success_rate": 0.94,
            "avg_execution_time_ms": 23.1,
            "last_execution": "2025-08-14T14:17:15Z",
            "parameters": {
                "path": {"type": "string", "required": true}
            }
        },
        {
            "name": "system_info",
            "category": "cli",
            "executions": 12,
            "success_rate": 1.0,
            "avg_execution_time_ms": 156.7,
            "last_execution": "2025-08-14T14:16:00Z",
            "parameters": {}
        }
    ],
    "total_executions": 89,
    "overall_success_rate": 0.96,
    "cost": 0.0
}
```

#### CLI Session Information
```
GET /v1/telemetry/cli-sessions
```
Returns session and channel information:
```json
{
    "active_sessions": [
        {
            "channel_id": "cli_12345_abcd1234",
            "channel_name": "CLI Session 12345",
            "is_active": true,
            "created_at": "2025-08-14T14:00:00Z",
            "last_activity": "2025-08-14T14:19:45Z",
            "message_count": 47,
            "is_private": true,
            "participants": ["user", "ciris"],
            "allowed_actions": [
                "speak", "observe", "memorize", "recall",
                "tool", "wa_defer", "runtime_control"
            ],
            "moderation_level": "minimal"
        }
    ],
    "total_sessions": 1,
    "home_channel_id": "cli_12345_abcd1234"
}
```

## Graph Storage

### Telemetry Nodes
All CLI adapter metrics are stored as TSDBGraphNode objects in the memory graph:
- **Scope**: "local"
- **Handler**: "adapter.cli"
- **Node Type**: "TSDB"
- **Attributes**: Include metric name, value, tags, and timestamp

### Persistent Nodes
CLI adapter does not create specialized persistent graph nodes beyond standard telemetry nodes and service correlations.

### Channel and Session Tracking
Channel information is tracked through correlation history:
- **Channel Format**: `cli_{pid}_{random_hex}`
- **User Identification**: Based on system user and hostname
- **Session Persistence**: Maintained through correlation database

## Example Usage

### Query CLI Metrics
```python
# Get all CLI adapter metrics from last hour
from ciris_engine.logic.services.graph.memory import MemoryService

memory = get_memory_service()
metrics = await memory.search({
    "handler_name": "adapter.cli",
    "node_type": "TSDB",
    "created_at": {"$gte": datetime.now() - timedelta(hours=1)}
})

# Get tool execution count
tool_metrics = [m for m in metrics if m.metric_name == "tool_executed"]
total_tools = sum(float(m.value) for m in tool_metrics)
```

### Get Real-Time Status
```python
# Get current adapter status
adapter = get_cli_adapter()
status = adapter.get_status()
print(f"Interactive: {status.metrics['interactive']}")
print(f"Tools available: {status.metrics['available_tools']}")
print(f"Healthy: {status.is_healthy}")

# Get tool capabilities
capabilities = adapter.get_capabilities()
print(f"Available tools: {capabilities.metadata['available_tools']}")
```

### Monitor Tool Executions
```python
# Query tool execution correlations
from ciris_engine.logic.persistence import get_correlations_by_service

correlations = get_correlations_by_service("cli")
tool_events = [
    c for c in correlations
    if c.action_type == "execute_tool"
]

for event in tool_events:
    tool_name = event.request_data.parameters.get("tool_name")
    exec_time = event.response_data.execution_time_ms
    print(f"{tool_name}: {exec_time:.1f}ms")
```

### Access Session Information
```python
# Get active CLI channels
adapter = get_cli_adapter()
channels = adapter.get_channel_list()

for channel in channels:
    print(f"Channel: {channel.channel_name}")
    print(f"Messages: {channel.message_count}")
    print(f"Active: {channel.is_active}")
```

## Testing

### Test Files
- `tests/logic/adapters/cli/test_cli_adapter.py` - Main adapter tests
- `tests/logic/adapters/cli/test_cli_observer.py` - Observer-specific tests
- `tests/logic/adapters/cli/test_cli_tools.py` - Tool execution tests
- `tests/logic/adapters/cli/test_cli_telemetry.py` - Telemetry-specific tests

### Validation Steps
1. **Telemetry Emission**: Verify metrics emitted for all major operations
2. **Graph Storage**: Confirm TSDBGraphNode creation and storage
3. **Service Correlations**: Validate correlation tracking for operations
4. **Status Accuracy**: Check health status reflects actual adapter state
5. **Tool Execution**: Test tool telemetry and performance tracking
6. **Interactive vs Non-Interactive**: Validate different mode telemetry

```python
async def test_cli_telemetry():
    adapter = CLIAdapter(runtime=test_runtime, interactive=True)

    # Test telemetry emission
    await adapter._emit_telemetry("test.metric", 1.0, {"test": "tag"})

    # Verify graph storage
    memory = get_memory_service()
    nodes = await memory.search({
        "handler_name": "adapter.cli",
        "metric_name": "test.metric"
    })
    assert len(nodes) == 1
    assert nodes[0].value == 1.0

    # Test status method
    status = adapter.get_status()
    assert status.service_name == "CLIAdapter"
    assert "interactive" in status.metrics

    # Test tool execution telemetry
    result = await adapter.execute_tool("system_info", {})
    assert result.success
    assert result.correlation_id
```

## Configuration

### CLI Adapter Settings
```python
# Interactive mode configuration
cli_config = CLIAdapterConfig(
    interactive=True,
    home_channel_id="cli_custom_channel"
)

# Non-interactive mode for piped input
cli_config = CLIAdapterConfig(
    interactive=False,
    process_piped_input=True
)
```

### Tool Configuration
```python
# Available tools are built-in
available_tools = {
    "list_files": _tool_list_files,
    "read_file": _tool_read_file,
    "system_info": _tool_system_info
}

# Tool schemas defined statically
tool_schemas = {
    "list_files": {"path": {"type": "string", "default": "."}},
    "read_file": {"path": {"type": "string", "required": True}},
    "system_info": {}
}
```

### Observer Configuration
```python
# Interactive input handling
observer_config = {
    "interactive": True,
    "buffer_piped_input": True,
    "processing_delay_seconds": 5.0,
    "passive_context_limit": 10
}
```

## Known Limitations

1. **Memory-Only Statistics**: Tool execution stats reset on restart
2. **No Historical Aggregation**: Tool performance data not maintained over time
3. **Single Session Support**: Only one active CLI session per adapter instance
4. **Limited Channel Analytics**: No per-channel performance metrics beyond message counts
5. **Synchronous Tool Execution**: All CLI tools execute synchronously (no async tool telemetry)
6. **Platform Dependency**: Some telemetry (system info) depends on psutil availability
7. **Input Handling Dependency**: Interactive mode requires proper terminal support

## Future Enhancements

1. **Persistent Tool Statistics**: Store tool performance metrics in Redis/database
2. **Historical Metrics**: Time-series data for tool usage patterns
3. **Multi-Session Support**: Handle multiple concurrent CLI sessions
4. **Advanced Tool Analytics**: Tool dependency tracking and usage optimization
5. **Async Tool Support**: Telemetry for long-running asynchronous tools
6. **Input Method Analytics**: Distinguish between keyboard, piped, and scripted input
7. **Performance Benchmarking**: Tool execution performance baselines and alerts
8. **Command History Analytics**: Pattern analysis of user command sequences

## Integration Points

### Memory Bus Integration
- **Metric Storage**: All telemetry flows through memory.memorize_metric()
- **Node Queries**: Tool and session data accessible via memory.search()
- **Correlation Tracking**: Links between messages, tool executions, and responses

### Service Correlation Integration
- **Message Events**: Send/receive message logging with timing
- **Tool Executions**: Complete tool execution tracking with parameters
- **Observer Events**: Input processing and message handling
- **Session Management**: Channel creation and activity tracking

### TSDB Consolidation
- **6-Hour Cycles**: Metrics consolidated for long-term storage
- **Aggregation**: Tool usage counts, averages, and success rates
- **Retention**: Historical CLI interaction data management

## Monitoring Recommendations

### Critical Alerts
1. **Adapter Health**: Alert when `is_healthy` becomes false
2. **Tool Failures**: Monitor tool execution failure rates
3. **Input Task Issues**: Alert when interactive input task fails
4. **Memory Leaks**: Monitor correlation history growth
5. **Channel Starvation**: Alert when no messages processed for extended period

### Performance Monitoring
1. **Tool Execution Times**: Track performance degradation of built-in tools
2. **Message Processing**: Monitor time between received and processed
3. **Memory Usage**: Graph node count and correlation table growth
4. **Response Times**: End-to-end response time for CLI interactions

### Operational Insights
1. **Usage Patterns**: Peak usage hours, most used tools, command patterns
2. **Tool Effectiveness**: Success rates, error patterns, optimization opportunities
3. **Session Analytics**: Average session length, message volume trends
4. **Input Method Distribution**: Interactive vs piped input usage patterns

## Security Considerations

1. **Input Sanitization**: All user input processed through secrets service
2. **File System Access**: Tool file operations restricted to safe paths
3. **Command Injection**: Tool parameters validated against schemas
4. **Session Isolation**: Each CLI session maintains separate correlation tracking
5. **Sensitive Data**: File contents and system info filtered for secrets
6. **Process Information**: System info tool limits exposed process details

## Performance Considerations

1. **Async Operations**: All telemetry operations are non-blocking
2. **Memory Efficiency**: Tool results use bounded data structures
3. **Graph Writes**: Telemetry batched where possible to reduce graph load
4. **Query Optimization**: Indexed fields for common CLI telemetry queries
5. **Input Buffering**: Piped input processed with delays to prevent overwhelming
6. **Correlation Cleanup**: Old correlation records cleaned up based on retention policy
