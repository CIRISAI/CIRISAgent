# Secrets Tool Service Telemetry

## Overview
The Secrets Tool Service provides secure access to stored secrets and secrets management capabilities through a tool-based interface. As one of CIRIS's Tool Services, it exposes three core tools: `recall_secret` for retrieving stored secrets, `update_secrets_filter` for managing secrets detection patterns (currently disabled), and `self_help` for accessing agent guidance documentation. The service prioritizes security through careful audit logging, request tracking, and access control while maintaining comprehensive observability for compliance and operational monitoring.

## Telemetry Data Collected

| Metric Name | Type | Storage | Update Frequency | Access Method |
|------------|------|---------|------------------|---------------|
| available_tools | gauge | in-memory calculation | constant | `_collect_custom_metrics()` |
| uptime_seconds | gauge | inherited from BaseService | continuous | `_calculate_uptime()` |
| request_count | counter | inherited from BaseService | per tool execution | `_track_request()` |
| error_count | counter | inherited from BaseService | per error | `_track_error()` |
| error_rate | gauge | inherited from BaseService | calculated | `error_count / request_count` |
| healthy | boolean | inherited from BaseService | per status check | `is_healthy()` |
| tool_executions_by_name | counter | **NOT IMPLEMENTED** | - | TODO: Track per-tool usage |
| secret_retrieval_success_rate | gauge | **NOT IMPLEMENTED** | - | TODO: Track secret access patterns |
| audit_events_generated | counter | **NOT IMPLEMENTED** | - | TODO: Track security audit events |
| self_help_access_count | counter | **NOT IMPLEMENTED** | - | TODO: Track knowledge access |
| failed_authorization_attempts | counter | **NOT IMPLEMENTED** | - | TODO: Track security violations |
| average_tool_execution_time | gauge | **NOT IMPLEMENTED** | - | TODO: Track performance metrics |

## Data Structures

### Service Status
```python
{
    "service_name": "SecretsToolService",     # Service identifier
    "service_type": "TOOL",                   # Service type enum
    "is_healthy": true,                       # Health status
    "uptime_seconds": 86400,                  # Uptime since start
    "adapter_name": "secrets",                # Tool adapter name
    "tool_count": 3,                          # Number of available tools
    "available_tools": ["recall_secret", "update_secrets_filter", "self_help"]
}
```

### Tool Execution Result
```python
{
    "tool_name": "recall_secret",             # Tool that was executed
    "status": "completed",                    # completed|failed|timeout|not_found|unauthorized
    "success": true,                          # Execution success indicator
    "data": {                                 # Tool-specific result data
        "value": "encrypted_secret_value",    # (recall_secret only)
        "decrypted": true,                    # Whether secret was decrypted
        "exists": true                        # Whether secret exists
    },
    "error": null,                            # Error message if failed
    "correlation_id": "secrets_recall_secret_1723644600.0"  # Unique execution ID
}
```

### Tool Information Schema
```python
{
    "name": "recall_secret",                  # Tool name
    "description": "Recall a stored secret by UUID",
    "parameters": {                           # JSON Schema for parameters
        "type": "object",
        "properties": {
            "secret_uuid": {
                "type": "string",
                "description": "UUID of the secret to recall"
            },
            "purpose": {
                "type": "string",
                "description": "Why the secret is needed (for audit)"
            },
            "decrypt": {
                "type": "boolean",
                "description": "Whether to decrypt the secret value",
                "default": false
            }
        },
        "required": ["secret_uuid", "purpose"]
    },
    "category": "security",                   # Tool category
    "cost": 0.0,                             # Execution cost
    "when_to_use": "When you need to retrieve a previously stored secret value"
}
```

### Service Capabilities Metadata
```python
{
    "service_name": "SecretsToolService",     # Service name
    "actions": ["recall_secret", "update_secrets_filter", "self_help"],
    "version": "1.0.0",                       # Service version
    "dependencies": ["SecretsService"],       # Required dependencies
    "metadata": {                             # Service-specific metadata
        "service_name": "SecretsToolService",
        "method_name": "_get_metadata",
        "correlation_id": "uuid-1234",
        "adapter": "secrets",
        "tool_count": 3
    }
}
```

### Secret Retrieval Context (Audit)
```python
{
    "operation": "recall",                    # Operation type
    "request_id": "recall_uuid-123_1723644600.0",  # Unique request identifier
    "metadata": {                             # Additional context
        "purpose": "User authentication",     # Stated purpose
        "timestamp": "2025-08-14T13:30:00Z", # When accessed
        "result": "success"                   # Access result
    }
}
```

## API Access Patterns

### Current Access
- **Internal Service Access**: Via dependency injection and service registry
- **Tool Bus Integration**: Registered as tool provider via ToolBus
- **Audit Integration**: Secret access generates audit contexts
- **Request Tracking**: All tool executions tracked for metrics

### Recommended Endpoints

#### Get Secrets Tool Service Status
```
GET /v1/telemetry/tools/secrets/status
```
Returns comprehensive service status:
```json
{
    "service_name": "SecretsToolService",
    "adapter_name": "secrets",
    "is_healthy": true,
    "uptime_seconds": 86400,
    "available_tools": 3,
    "tools": [
        {
            "name": "recall_secret",
            "category": "security",
            "description": "Recall a stored secret by UUID",
            "executions": 45,
            "success_rate": 0.978
        },
        {
            "name": "update_secrets_filter",
            "category": "security",
            "description": "Update secrets detection filter configuration",
            "executions": 0,
            "success_rate": 0.0,
            "status": "disabled"
        },
        {
            "name": "self_help",
            "category": "knowledge",
            "description": "Access your experience document for guidance",
            "executions": 12,
            "success_rate": 1.0
        }
    ],
    "metrics": {
        "request_count": 57,
        "error_count": 1,
        "error_rate": 0.018,
        "healthy": 1.0
    }
}
```

#### Get Tool Usage Analytics
```
GET /v1/telemetry/tools/secrets/usage
```
Query parameters:
- `period`: 1h|1d|7d|30d
- `tool`: Filter by specific tool name

Returns tool usage analysis:
```json
{
    "period": "1d",
    "total_executions": 57,
    "tools_breakdown": {
        "recall_secret": {
            "executions": 45,
            "success_rate": 0.978,
            "avg_execution_time_ms": 15,
            "errors": ["Secret uuid-456 not found"]
        },
        "update_secrets_filter": {
            "executions": 0,
            "success_rate": 0.0,
            "status": "disabled",
            "reason": "Filter operations not currently exposed"
        },
        "self_help": {
            "executions": 12,
            "success_rate": 1.0,
            "avg_execution_time_ms": 5,
            "knowledge_access_patterns": ["agent_experience.md"]
        }
    },
    "security_metrics": {
        "unique_secrets_accessed": 23,
        "failed_authorization_attempts": 0,
        "audit_events_generated": 45
    }
}
```

#### Get Security Audit Trail
```
GET /v1/telemetry/tools/secrets/audit
```
Query parameters:
- `timeframe`: 1h|1d|7d|30d
- `operation`: recall|filter_update|help_access
- `secret_uuid`: Filter by specific secret

Returns security audit information:
```json
{
    "timeframe": "1d",
    "total_security_events": 45,
    "operations": [
        {
            "operation": "recall",
            "timestamp": "2025-08-14T13:30:00Z",
            "request_id": "recall_uuid-123_1723644600.0",
            "secret_uuid": "uuid-123",
            "purpose": "User authentication",
            "result": "success",
            "decrypt": true,
            "correlation_id": "secrets_recall_secret_1723644600.0"
        },
        {
            "operation": "recall",
            "timestamp": "2025-08-14T14:15:00Z",
            "request_id": "recall_uuid-456_1723647300.0",
            "secret_uuid": "uuid-456",
            "purpose": "API integration",
            "result": "not_found",
            "error": "Secret uuid-456 not found"
        }
    ],
    "security_summary": {
        "successful_accesses": 44,
        "failed_accesses": 1,
        "unique_secrets": 23,
        "most_accessed_purpose": "User authentication"
    }
}
```

#### Get Tool Performance Metrics
```
GET /v1/telemetry/tools/secrets/performance
```
Returns performance analysis:
```json
{
    "service_health": {
        "is_healthy": true,
        "uptime_seconds": 86400,
        "last_error": null,
        "error_rate": 0.018
    },
    "tool_performance": {
        "recall_secret": {
            "avg_execution_time_ms": 15,
            "p95_execution_time_ms": 25,
            "p99_execution_time_ms": 45,
            "success_rate": 0.978
        },
        "self_help": {
            "avg_execution_time_ms": 5,
            "p95_execution_time_ms": 8,
            "p99_execution_time_ms": 12,
            "success_rate": 1.0
        }
    },
    "resource_usage": {
        "memory_usage_mb": 2.1,
        "dependencies_healthy": true,
        "secrets_service_status": "healthy"
    }
}
```

## Graph Storage

### Telemetry Service Integration
When `telemetry_service` is available, the Secrets Tool Service could record:
- `secrets_tool_execution`: Tool execution events
- `secrets_access_audit`: Security audit events
- `tool_performance_metric`: Performance measurements

### Memory Graph Nodes
Tool execution data can be stored as graph nodes via the telemetry service:
```python
# Via TelemetryService.memorize_metric()
{
    "node_type": "metric",
    "metric_name": "secrets_tool_execution",
    "timestamp": "2025-08-14T13:30:00Z",
    "data": {
        "tool_name": "recall_secret",
        "status": "completed",
        "success": true,
        "secret_uuid": "uuid-123",
        "purpose": "User authentication",
        "execution_time_ms": 15,
        "correlation_id": "secrets_recall_secret_1723644600.0"
    }
}
```

### Security Audit Graph Storage
```python
{
    "node_type": "audit_event",
    "event_type": "secrets_access",
    "timestamp": "2025-08-14T13:30:00Z",
    "data": {
        "operation": "recall",
        "secret_uuid": "uuid-123",
        "purpose": "User authentication",
        "result": "success",
        "request_id": "recall_uuid-123_1723644600.0",
        "service": "SecretsToolService"
    }
}
```

## Example Usage

### Get Service Status
```python
secrets_tool = get_service(ServiceType.TOOL, adapter="secrets")
status = secrets_tool.get_status()

print(f"Service: {status.service_name}")
print(f"Healthy: {status.is_healthy}")
print(f"Uptime: {status.uptime_seconds}s")
print(f"Tools: {len(secrets_tool._get_actions())}")
print(f"Requests: {status.metrics['request_count']}")
print(f"Error Rate: {status.metrics['error_rate']:.3f}")
```

### Execute Secret Recall Tool
```python
secrets_tool = get_service(ServiceType.TOOL, adapter="secrets")

# Execute tool and track metrics automatically
result = await secrets_tool.execute_tool(
    "recall_secret",
    {
        "secret_uuid": "uuid-123",
        "purpose": "User authentication",
        "decrypt": True
    }
)

print(f"Tool: {result.tool_name}")
print(f"Status: {result.status}")
print(f"Success: {result.success}")
print(f"Correlation ID: {result.correlation_id}")

if result.success:
    print(f"Secret retrieved: {result.data['decrypted']}")
else:
    print(f"Error: {result.error}")
```

### Monitor Tool Usage Patterns
```python
secrets_tool = get_service(ServiceType.TOOL, adapter="secrets")
status = secrets_tool.get_status()

# Check overall health
if not status.is_healthy:
    logger.error("Secrets tool service unhealthy")

# Monitor error rates
if status.metrics['error_rate'] > 0.05:
    logger.warning(f"High error rate: {status.metrics['error_rate']:.2%}")

# Check available tools
available_tools = await secrets_tool.get_available_tools()
logger.info(f"Available tools: {available_tools}")

# Get tool-specific information
for tool_name in available_tools:
    tool_info = await secrets_tool.get_tool_info(tool_name)
    logger.info(f"{tool_name}: {tool_info.description}")
```

### Validate Tool Parameters
```python
secrets_tool = get_service(ServiceType.TOOL, adapter="secrets")

# Validate recall_secret parameters
params = {"secret_uuid": "uuid-123", "purpose": "Testing"}
is_valid = await secrets_tool.validate_parameters("recall_secret", params)
print(f"Parameters valid: {is_valid}")

# Check required parameters
tool_info = await secrets_tool.get_tool_info("recall_secret")
required_params = tool_info.parameters.required
print(f"Required parameters: {required_params}")
```

### Access Self-Help Documentation
```python
secrets_tool = get_service(ServiceType.TOOL, adapter="secrets")

# Get agent guidance
result = await secrets_tool.execute_tool("self_help", {})

if result.success:
    content = result.data["content"]
    source = result.data["source"]
    length = result.data["length"]

    print(f"Documentation loaded from {source}")
    print(f"Content length: {length} characters")
    print(f"First 200 chars: {content[:200]}...")
else:
    print(f"Failed to load documentation: {result.error}")
```

## Testing

### Test Files
- `tests/ciris_engine/logic/services/tools/test_secrets_tool_service.py`
- `tests/integration/test_secrets_tool_audit.py` (future)
- `tests/telemetry/test_secrets_tool_telemetry.py` (future)

### Validation Steps
1. Initialize SecretsToolService with dependencies
2. Execute each tool type and verify result structure
3. Test parameter validation for all tools
4. Verify error tracking and metrics collection
5. Test service lifecycle (start/stop)
6. Validate audit context generation for secret access
7. Test self-help documentation access

```python
async def test_secrets_tool_telemetry():
    # Setup service with dependencies
    secrets_service = Mock()
    secrets_service.retrieve_secret = AsyncMock(return_value="test-secret")
    time_service = Mock()
    time_service.now.return_value = datetime.now()

    tool_service = SecretsToolService(
        secrets_service=secrets_service,
        time_service=time_service
    )

    await tool_service.start()

    # Execute tool and verify telemetry
    result = await tool_service.execute_tool(
        "recall_secret",
        {"secret_uuid": "test-uuid", "purpose": "testing", "decrypt": True}
    )

    # Verify execution result
    assert result.tool_name == "recall_secret"
    assert result.status == ToolExecutionStatus.COMPLETED
    assert result.success is True
    assert "correlation_id" in result.__dict__

    # Verify metrics collection
    status = tool_service.get_status()
    assert status.metrics["request_count"] == 1
    assert status.metrics["error_count"] == 0
    assert status.metrics["available_tools"] == 3

    # Verify custom metrics
    custom_metrics = tool_service._collect_custom_metrics()
    assert custom_metrics["available_tools"] == 3.0
```

## Configuration

### Service Dependencies
```python
{
    "secrets_service": SecretsService,        # Required for secret retrieval
    "time_service": TimeServiceProtocol       # Required for timestamps
}
```

### Tool Configuration
```python
{
    "adapter_name": "secrets",                # Tool adapter identifier
    "version": "1.0.0",                      # Service version
    "available_tools": [                     # Supported tools
        "recall_secret",
        "update_secrets_filter",
        "self_help"
    ]
}
```

### Filter Operations Configuration (Currently Disabled)
```python
{
    "filter_operations_enabled": false,      # Filter operations disabled
    "supported_operations": [                # Operations that would be supported
        "add_pattern",
        "remove_pattern",
        "list_patterns",
        "enable"
    ],
    "pattern_types": ["regex", "exact"]     # Supported pattern types
}
```

## Known Limitations

1. **Filter Operations Disabled**: All `update_secrets_filter` operations except `list_patterns` are disabled
2. **No Performance Tracking**: Tool execution times not measured or recorded
3. **Limited Audit Integration**: Secret access audit contexts created but not fully integrated
4. **No Usage Analytics**: Per-tool usage statistics not collected
5. **Missing Security Metrics**: No tracking of authorization failures or suspicious access patterns
6. **No Rate Limiting**: No built-in protection against tool abuse
7. **Synchronous Execution Only**: All tools execute synchronously, no async tool support
8. **No Tool Caching**: Results not cached, every execution hits underlying services
9. **Limited Error Classification**: Errors not categorized by type for better analytics

## Future Enhancements

1. **Enhanced Performance Tracking**: Measure and record tool execution times
2. **Comprehensive Audit Integration**: Full security audit trail with correlation
3. **Advanced Usage Analytics**: Per-tool statistics, usage patterns, trends
4. **Security Monitoring**: Track authorization failures, suspicious patterns, rate limiting
5. **Filter Operations**: Enable secure management of secrets detection patterns
6. **Async Tool Support**: Support for long-running or background tool execution
7. **Result Caching**: Cache appropriate tool results to improve performance
8. **Tool Categories**: Better organization and discovery of available tools
9. **Access Control**: Fine-grained permissions per tool and operation
10. **Integration Dashboards**: Real-time tool usage and security monitoring
11. **Predictive Analytics**: Identify unusual access patterns or potential security issues
12. **Tool Versioning**: Support multiple versions of tools with backward compatibility

## Integration Points

- **SecretsService**: Core dependency for secret retrieval and management
- **TimeService**: Consistent timestamps for all operations and audit events
- **ToolBus**: Registration as tool provider for cross-adapter access
- **Audit Service**: Security audit trail for secret access operations
- **TelemetryService**: Metrics collection and performance monitoring
- **Memory Graph**: Persistent storage of telemetry and audit data
- **API Layer**: Exposes tool capabilities via REST endpoints
- **RuntimeControl**: Tool execution management and lifecycle control

## Monitoring Recommendations

1. **Service Health Alerts**: Monitor service availability and dependency health
2. **Security Monitoring**: Track secret access patterns, failed attempts, unusual usage
3. **Performance Tracking**: Monitor tool execution times and identify bottlenecks
4. **Audit Compliance**: Ensure all secret accesses are properly logged and auditable
5. **Error Rate Monitoring**: Alert on elevated error rates or new error patterns
6. **Tool Usage Analytics**: Track which tools are used most/least, optimization opportunities
7. **Dependency Monitoring**: Ensure SecretsService remains healthy and responsive
8. **Resource Usage**: Monitor memory usage and service resource consumption

## Performance Considerations

1. **Synchronous Operations**: All tools execute synchronously, blocking until completion
2. **Secret Retrieval Latency**: Performance dependent on underlying SecretsService
3. **No Caching Overhead**: No result caching means consistent performance but repeated work
4. **Minimal Memory Footprint**: Stateless design keeps memory usage low
5. **Audit Context Creation**: Small overhead for creating security audit contexts
6. **Parameter Validation**: Schema validation adds minimal latency
7. **Error Tracking**: Metrics collection adds negligible overhead
8. **File System Access**: `self_help` tool requires file system access for documentation

## System Integration

The Secrets Tool Service is a critical security component in CIRIS's tool ecosystem:
- Provides secure, auditable access to stored secrets through standardized tool interface
- Maintains comprehensive security audit trail for compliance and monitoring
- Integrates with broader tool bus architecture for cross-adapter accessibility
- Implements responsible secrets access with purpose tracking and audit logging
- Supports operational needs while maintaining security and observability standards

The service acts as a "secure gateway" to sensitive data, ensuring that all secret accesses are tracked, audited, and controlled while providing the operational flexibility needed by other CIRIS components and adapters.
