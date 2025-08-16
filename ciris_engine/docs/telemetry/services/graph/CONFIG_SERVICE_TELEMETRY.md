# Config Service Telemetry

## Overview
The Config Service is responsible for managing all configuration settings in CIRIS using a graph-based storage architecture. It implements the "everything is a memory" philosophy by storing all configurations as graph nodes with complete version history. This service provides typed configuration management, change listeners, and automated caching for performance.

## Telemetry Data Collected

| Metric Name | Type | Storage | Update Frequency | Access Method |
|------------|------|---------|------------------|---------------|
| total_configs | gauge | in-memory | per config operation | `_collect_custom_metrics()` |
| config_listeners | gauge | in-memory | on listener registration | `_collect_custom_metrics()` |
| memory_bus_available | gauge | in-memory | per health check | `_collect_custom_metrics()` (inherited) |
| uptime_seconds | gauge | in-memory | continuous | `get_status()` (inherited) |
| request_count | counter | in-memory | per method call | `_track_request()` (inherited) |
| error_count | counter | in-memory | per error | `_track_error()` (inherited) |
| error_rate | gauge | computed | per status check | calculated from counts (inherited) |
| healthy | gauge | in-memory | per health check | service state (inherited) |
| config_versions_created | counter | graph memory | per config update | graph query |
| config_cache_hits | counter | in-memory | per get_config() | internal tracking |
| config_listener_notifications | counter | in-memory | per notification | listener system |
| config_history_depth | histogram | graph memory | per config key | graph query |

## Data Structures

### ConfigNode (Stored in Graph)
```python
{
    "id": "config_adapter_memory_timeout_a1b2c3d4",
    "type": "CONFIG",
    "scope": "local",
    "attributes": {
        "created_at": "2025-08-14T13:30:00Z",
        "updated_at": "2025-08-14T13:30:00Z",
        "created_by": "admin",
        "tags": ["config", "adapter.memory.timeout"],
        "node_class": "ConfigNode",
        "key": "adapter.memory.timeout",
        "value": {
            "int_value": 30,
            "string_value": null,
            "float_value": null,
            "bool_value": null,
            "list_value": null,
            "dict_value": null
        },
        "version": 3,
        "updated_by": "admin",
        "previous_version": "config_adapter_memory_timeout_x9y8z7w6"
    },
    "version": 3,
    "updated_by": "admin",
    "updated_at": "2025-08-14T13:30:00Z"
}
```

### ConfigValue (Typed Value Wrapper)
```python
{
    "string_value": "production",  # Only one field populated
    "int_value": null,
    "float_value": null,
    "bool_value": null,
    "list_value": null,
    "dict_value": null
}
```

### Config Cache Entry (In-Memory)
```python
{
    "config_key": "adapter.memory.timeout",
    "cached_node": ConfigNode(...),
    "cache_time": "2025-08-14T13:30:00Z",
    "access_count": 45
}
```

### Config Listener Registration
```python
{
    "key_pattern": "adapter.*",
    "callback": <async function>,
    "registered_at": "2025-08-14T13:30:00Z",
    "notification_count": 12
}
```

## API Access Patterns

### Current Access
- **Internal Storage**: Configurations stored as graph nodes via LocalGraphMemoryService
- **No Direct API**: No REST endpoints expose config telemetry directly
- **Graph Queries Required**: Must query graph database for historical config data
- **Status Available**: Service status includes basic metrics

### Recommended Endpoints

#### Get Config Statistics
```
GET /v1/config/stats
```
Returns current configuration statistics:
```json
{
    "total_configs": 156,
    "config_listeners": 8,
    "cache_size": 45,
    "average_config_versions": 2.3,
    "most_updated_config": "adapter.memory.timeout",
    "oldest_config": "system.name",
    "config_creation_rate_per_hour": 1.2
}
```

#### Get Config History
```
GET /v1/config/{key}/history
```
Query parameters:
- `limit`: Max versions to return (default 10)

Returns:
```json
{
    "config_key": "adapter.memory.timeout",
    "current_value": 30,
    "total_versions": 5,
    "versions": [
        {
            "version": 5,
            "value": 30,
            "updated_by": "admin",
            "updated_at": "2025-08-14T13:30:00Z"
        },
        {
            "version": 4,
            "value": 25,
            "updated_by": "system",
            "updated_at": "2025-08-14T12:15:00Z"
        }
    ]
}
```

#### Get Config Metrics Summary
```
GET /v1/config/metrics
```
Returns telemetry metrics:
```json
{
    "service_metrics": {
        "total_configs": 156,
        "config_listeners": 8,
        "uptime_seconds": 86400,
        "request_count": 1234,
        "error_count": 2,
        "error_rate": 0.0016,
        "healthy": 1.0
    },
    "config_metrics": {
        "configs_by_prefix": {
            "adapter": 45,
            "system": 12,
            "service": 89,
            "user": 10
        },
        "average_versions_per_config": 2.1,
        "most_active_configs": [
            "adapter.memory.timeout",
            "service.llm.provider",
            "system.log_level"
        ]
    }
}
```

#### Get Listener Activity
```
GET /v1/config/listeners/activity
```
Returns config listener telemetry:
```json
{
    "active_listeners": 8,
    "total_notifications_sent": 234,
    "listeners_by_pattern": {
        "adapter.*": 3,
        "service.*": 2,
        "system.*": 2,
        "user.*": 1
    },
    "notification_frequency": {
        "last_hour": 12,
        "last_day": 89,
        "last_week": 456
    }
}
```

## Graph Storage

### Node Types Created
- `CONFIG` - All configuration values with versioning

### Edge Relationships
- `PREVIOUS_VERSION` - Links to previous config version
- `UPDATED_BY` - Links to user/system that made the change
- `LISTENED_BY` - Links to services that listen to config changes

### Memory Types
All config nodes use `OPERATIONAL` memory type as they represent system operational parameters.

### Version Chain Structure
```python
# Config versions form a linked list in the graph
CONFIG_NODE_V1 ← PREVIOUS_VERSION ← CONFIG_NODE_V2 ← PREVIOUS_VERSION ← CONFIG_NODE_V3
```

## Example Usage

### Record Config Change
```python
config_service = get_service(ServiceType.CONFIG)

await config_service.set_config(
    key="adapter.memory.timeout",
    value=30,
    updated_by="admin"
)
```

### Get Config with Telemetry
```python
config_node = await config_service.get_config("adapter.memory.timeout")
if config_node:
    print(f"Version: {config_node.version}")
    print(f"Updated by: {config_node.updated_by}")
    print(f"Updated at: {config_node.updated_at}")
    print(f"Value: {config_node.value.value}")
```

### Register Config Listener with Tracking
```python
async def config_change_handler(key: str, old_value, new_value):
    # Handler automatically tracked for telemetry
    logger.info(f"Config {key} changed from {old_value} to {new_value}")

config_service.register_config_listener("adapter.*", config_change_handler)
```

### List All Configs with Metrics
```python
all_configs = await config_service.list_configs()
print(f"Total configurations: {len(all_configs)}")

# Get service metrics
status = config_service.get_status()
print(f"Cache size: {status.metrics.get('total_configs', 0)}")
print(f"Listeners: {status.metrics.get('config_listeners', 0)}")
```

## Testing

### Test Files
- `tests/logic/services/graph/test_config_service.py` - Service tests
- `tests/integration/test_config_flow.py` - End-to-end tests

### Validation Steps
1. Set config via `set_config()`
2. Verify config appears in graph as CONFIG node
3. Check config in `_config_cache`
4. Verify version incrementing
5. Test listener notifications
6. Validate history tracking

```python
async def test_config_telemetry():
    config = get_service(ServiceType.CONFIG)

    # Initial state
    initial_status = config.get_status()
    initial_count = initial_status.metrics.get('total_configs', 0)

    # Set config
    await config.set_config(
        "test.metric",
        value="test_value",
        updated_by="test_user"
    )

    # Check metrics updated
    updated_status = config.get_status()
    new_count = updated_status.metrics.get('total_configs', 0)

    assert new_count > initial_count

    # Check version tracking
    config_node = await config.get_config("test.metric")
    assert config_node.version == 1
    assert config_node.updated_by == "test_user"
```

## Configuration

### Cache Settings
```python
{
    "max_cached_configs": 1000,      # Maximum configs to cache
    "cache_ttl_seconds": 300,        # Cache time-to-live
    "enable_config_cache": True      # Enable/disable caching
}
```

### Listener Settings
```python
{
    "max_listeners_per_pattern": 10,  # Limit listeners per pattern
    "async_notification": True,       # Use async notifications
    "notification_timeout": 5.0       # Timeout for listener notifications
}
```

### Version Management
```python
{
    "max_versions_per_config": 100,   # Keep last N versions
    "enable_version_history": True,   # Track version history
    "compress_old_versions": False    # Compress old config versions
}
```

## Known Limitations

1. **No Version Cleanup**: Old config versions never auto-expire
2. **Cache Size Unbounded**: Config cache can grow without limit
3. **Graph Dependency**: All configs stored in graph, no backup storage
4. **No Bulk Operations**: Must set configs individually
5. **Listener Error Handling**: Failed listener notifications don't retry
6. **No Config Validation**: Values not validated against schemas
7. **Memory Usage**: Large config dictionaries not optimized for storage

## Future Enhancements

1. **Config Schema Validation**: Type checking for config values
2. **Version Expiration**: Automatic cleanup of old config versions
3. **Bulk Configuration**: Set multiple configs in single transaction
4. **Config Templates**: Predefined config sets for common scenarios
5. **Change Approval Workflow**: Require approval for sensitive configs
6. **Config Encryption**: Encrypt sensitive configuration values
7. **Export/Import**: Backup and restore configuration sets
8. **Config Diff Visualization**: Show differences between versions
9. **Performance Optimization**: Batch config operations
10. **Config Dependencies**: Track config interdependencies

## Integration Points

- **LocalGraphMemoryService**: Direct storage of config nodes
- **TimeService**: Provides consistent timestamps for versioning
- **All Services**: Consume configurations from this service
- **AuditService**: Logs config changes for compliance
- **ServiceRegistry**: Uses configs for service initialization

## Monitoring Recommendations

1. **Config Change Rate**: Monitor frequency of configuration updates
2. **Cache Hit Rate**: Track effectiveness of config caching
3. **Listener Performance**: Monitor notification latency and failures
4. **Version Growth**: Watch for configs with excessive versions
5. **Memory Usage**: Monitor service memory consumption
6. **Error Rate**: Track config-related errors and failures
7. **Access Patterns**: Identify most frequently accessed configs
8. **Historical Trends**: Analyze config change patterns over time

## Performance Considerations

1. **Graph Query Cost**: Each config lookup requires graph query
2. **Cache Memory**: Large configs can consume significant memory
3. **Listener Overhead**: Many listeners can slow config updates
4. **Version Storage**: Each change creates new graph node
5. **No Indexing**: Config queries scan all CONFIG nodes
6. **Serialization Cost**: Complex values require JSON serialization
7. **Network Overhead**: Graph storage may involve network calls

## Architecture Notes

The Config Service implements key CIRIS architectural principles:

### "Everything is a Memory"
- All configurations are stored as memories in the graph
- Version history becomes a chain of related memories
- Configuration changes create new memories rather than modifying existing ones

### Type Safety First
- Uses ConfigValue wrapper to ensure type safety
- All configuration types explicitly defined
- No `Dict[str, Any]` usage - fully typed throughout

### Graph-Based History
- Complete audit trail of all configuration changes
- Immutable history - previous versions never deleted
- Links between versions maintain temporal relationships

### Service Integration
- Direct integration with LocalGraphMemoryService
- No dependency on MemoryBus (uses direct service calls)
- Integrates with broader CIRIS telemetry ecosystem

This service demonstrates how operational state (configurations) becomes part of the system's memory, enabling analysis, learning, and adaptation while maintaining complete historical context.
