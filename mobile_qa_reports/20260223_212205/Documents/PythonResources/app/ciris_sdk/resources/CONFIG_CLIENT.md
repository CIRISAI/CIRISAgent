# CIRIS SDK Config Client

The Config client provides a simple interface for managing CIRIS configuration through the `/v1/config` endpoints.

## Overview

The config client supports:
- Listing all configurations with role-based filtering
- Getting specific configuration values
- Setting/updating configuration values
- Deleting configuration keys
- Searching for configurations by pattern
- Bulk operations for efficiency
- Transparent handling of sensitive configurations

## Usage

```python
from ciris_sdk.client import CIRISClient

async with CIRISClient(base_url="http://localhost:8080") as client:
    # List all configs
    configs = await client.config.list_configs()

    # Get specific config
    value = await client.config.get_config("llm.model")

    # Set config
    result = await client.config.set_config(
        key="app.feature_flag",
        value=True,
        description="Enable new feature"
    )

    # Delete config
    result = await client.config.delete_config("app.old_setting")
```

## API Methods

### list_configs(include_sensitive=False)
List all configuration items. Sensitive values are automatically redacted based on your role.

**Parameters:**
- `include_sensitive` (bool): Attempt to retrieve sensitive values (requires ADMIN role)

**Returns:** List[ConfigItem]

### get_config(key)
Get a specific configuration value by key.

**Parameters:**
- `key` (str): The configuration key to retrieve

**Returns:** ConfigValue

### set_config(key, value, description=None, sensitive=False)
Set or update a configuration value.

**Parameters:**
- `key` (str): The configuration key
- `value` (Any): The value to set (must be JSON-serializable)
- `description` (str, optional): Description of the configuration
- `sensitive` (bool): Whether this contains sensitive data

**Returns:** ConfigOperationResponse

### delete_config(key)
Delete a configuration key. Requires ADMIN role or higher.

**Parameters:**
- `key` (str): The configuration key to delete

**Returns:** ConfigOperationResponse

### update_config(key, value, description=None)
Alias for set_config() for convenience.

### bulk_set(configs)
Set multiple configuration values at once.

**Parameters:**
- `configs` (Dict[str, Any]): Dictionary mapping keys to values

**Returns:** Dict[str, ConfigOperationResponse]

### search_configs(pattern)
Search for configuration keys matching a pattern (client-side).

**Parameters:**
- `pattern` (str): Search pattern (supports wildcards like `llm.*`)

**Returns:** List[ConfigItem]

## Role-Based Access

The config client transparently handles role-based access control:

- **OBSERVER**: Can read non-sensitive configurations
- **ADMIN**: Can read all configs and modify non-system configs
- **AUTHORITY**: Can modify all configurations
- **ROOT**: Full access to all operations

Sensitive configurations are automatically redacted for users without appropriate permissions. The `redacted` field in ConfigItem indicates when a value has been hidden.

## Examples

### Basic Configuration Management
```python
# Get current LLM model
llm_config = await client.config.get_config("llm.model")
print(f"Current model: {llm_config.value}")

# Update to a different model
result = await client.config.set_config("llm.model", "gpt-4")
if result.success:
    print(f"Updated from {result.old_value} to {result.new_value}")
```

### Working with Sensitive Configs
```python
# List configs, sensitive values will be redacted
configs = await client.config.list_configs()
for config in configs:
    if config.sensitive and config.redacted:
        print(f"{config.key}: [REDACTED]")
    else:
        print(f"{config.key}: {config.value}")

# Try to get sensitive values (requires ADMIN role)
try:
    configs = await client.config.list_configs(include_sensitive=True)
except CIRISAPIError as e:
    print(f"Access denied: {e}")
```

### Bulk Operations
```python
# Update multiple related configs at once
app_configs = {
    "app.debug": False,
    "app.log_level": "WARNING",
    "app.max_workers": 4,
    "app.timeout": 30
}

results = await client.config.bulk_set(app_configs)
successful = sum(1 for r in results.values() if r.success)
print(f"Updated {successful}/{len(app_configs)} configurations")
```

### Pattern Search
```python
# Find all LLM-related configurations
llm_configs = await client.config.search_configs("llm.*")
for config in llm_configs:
    print(f"{config.key}: {config.value}")

# Find all feature flags
features = await client.config.search_configs("*.feature.*")
enabled = sum(1 for f in features if f.value is True)
print(f"{enabled}/{len(features)} features enabled")
```

## Error Handling

The config client raises `CIRISAPIError` for API errors:

```python
from ciris_sdk.exceptions import CIRISAPIError

try:
    await client.config.get_config("nonexistent.key")
except CIRISAPIError as e:
    if e.status_code == 404:
        print("Configuration key not found")
    elif e.status_code == 403:
        print("Access denied")
    else:
        print(f"API error: {e}")
```

## Migration from Runtime Config

If migrating from the old runtime config endpoints:

| Old Endpoint | New Method |
|-------------|------------|
| GET /v1/runtime/config | client.config.list_configs() |
| GET /v1/runtime/config?path=X | client.config.get_config(X) |
| PUT /v1/runtime/config | client.config.set_config() |
| POST /v1/runtime/config/validate | (Removed - validation automatic) |
| GET /v1/config/values/{key} | client.config.get_config(key) |
| GET /v1/config/{key}/history | (Removed - use audit logs) |

The new config client is simpler and more consistent with RESTful conventions.
