# CIRIS Modular Services

This directory contains modular services that can be dynamically loaded into CIRIS.

## Adapter Status

| Adapter | Version | Description | QA Tests | Live Tested |
|---------|---------|-------------|----------|-------------|
| `ciris_covenant_metrics` | 1.0.0 | CIRIS Covenant compliance metrics - reports WBD and PDMA events to CIRISLens | `covenant_metrics_tests.py` | ✅ 2026-01-21 |
| `ciris_hosted_tools` | 1.0.0 | CIRIS-hosted tools requiring platform attestation (web search, etc.) | - | ❌ |
| `external_data_sql` | 1.0.0 | SQL database connector for DSAR automation and external data access | `sql_external_data_tests.py` | ✅ 2026-01-21 (100%) |
| `home_assistant` | 1.0.0 | Enhanced Home Assistant integration with event detection | - | ❌ |
| `mcp_client` | 1.0.0 | MCP client - connects CIRIS to external MCP servers | `mcp_tests.py` | ✅ 2026-01-21 (95.5%) |
| `mcp_common` | 1.0.0 | Shared utilities for MCP client and server adapters | - | N/A (library) |
| `mcp_server` | 1.0.0 | MCP server - exposes CIRIS capabilities to external AI agents | `mcp_tests.py` | ✅ 2026-01-21 (95.5%) |
| `mock_llm` | 1.0.0 | Mock LLM service for testing - simulates AI responses | ✅ (built-in) | ✅ (test only) |
| `navigation` | 1.0.0 | Navigation tool service using OpenStreetMap | - | ❌ |
| `reddit` | 1.0.0 | Reddit adapter with tool, communication, and observation services | `reddit_tests.py` | ❌ |
| `sample_adapter` | 1.0.0 | Reference adapter demonstrating all bus types and interactive config | - | N/A (reference) |
| `weather` | 1.0.0 | Weather tool service using NOAA National Weather Service API | - | ❌ |

### Testing Priority

1. **High Priority** (production use):
   - `ciris_covenant_metrics` ✅ - Live tested 2026-01-21
   - `mcp_client` / `mcp_server` ✅ - Live tested 2026-01-21 (95.5%)
   - `external_data_sql` ✅ - Live tested 2026-01-21 (100%)

2. **Medium Priority** (feature expansion):
   - `ciris_hosted_tools` - Platform tools
   - `reddit` - Social platform
   - `home_assistant` - IoT integration

3. **Low Priority** (utility):
   - `weather` - Example tool
   - `navigation` - Example tool

## Philosophy

Services should be:
- **Self-contained**: All code, schemas, and protocols in one directory
- **Declarative**: manifest.json describes the service
- **Protocol-compliant**: Implement standard CIRIS protocols
- **Zero backwards compatibility**: Move forward only

## Directory Structure

```
ciris_adapters/
├── mock_llm/              # Example: Mock LLM service (test only)
├── your_service/          # Your modular service here
└── README.md              # This file
```

## Creating a Modular Service

### 1. Create Directory Structure

```
your_service/
├── manifest.json          # REQUIRED: Service declaration
├── protocol.py            # REQUIRED: Protocol definition
├── schemas.py             # REQUIRED: Pydantic schemas
├── service.py             # REQUIRED: Implementation
├── __init__.py            # REQUIRED: Package init
└── README.md              # RECOMMENDED: Documentation
```

### 2. Write manifest.json

```json
{
  "service": {
    "name": "YourService",
    "version": "1.0.0",
    "type": "CUSTOM",
    "priority": "NORMAL",
    "description": "What your service does"
  },
  "capabilities": ["capability1", "capability2"],
  "dependencies": {
    "protocols": ["ciris_engine.protocols.services.ServiceProtocol"],
    "schemas": ["ciris_engine.schemas.runtime.models"]
  },
  "exports": {
    "service_class": "your_service.service.YourService",
    "protocol": "your_service.protocol.YourServiceProtocol",
    "schemas": "your_service.schemas"
  }
}
```

### 3. Implement Protocol

Your protocol should extend appropriate CIRIS base protocols:

```python
from ciris_engine.protocols.services import ServiceProtocol

class YourServiceProtocol(ServiceProtocol, Protocol):
    async def your_method(self) -> None: ...
```

### 4. Define Schemas

Use Pydantic for all data structures:

```python
from pydantic import BaseModel

class YourConfig(BaseModel):
    setting: str = "default"
```

### 5. Implement Service

```python
class YourService(YourServiceProtocol):
    async def start(self) -> None:
        await super().start()
        # Your initialization
```

## Loading

Modular services are loaded at runtime when:
1. Placed in this directory
2. Have valid manifest.json
3. Dependencies are satisfied
4. No conflicts with core services

## Adapter Persistence

Adapters can be configured to automatically restore on agent restart using the `persist=True` flag.

### Loading with Persistence

**Via API:**
```bash
curl -X POST http://localhost:8000/v1/system/adapters/your_adapter/load \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"config": {...}, "persist": true}'
```

**Via RuntimeControlService:**
```python
await runtime_control.load_adapter(
    adapter_type="your_adapter",
    adapter_id="your_adapter_instance",
    config={"persist": True, "setting1": "value1"}
)
```

### How Persistence Works

When `persist=True`:
1. Adapter config is saved to the graph as `adapter.{adapter_id}.*` nodes
2. On agent restart, the "Load Saved Adapters" initialization step restores them
3. Only adapters with `persist=True` flag are restored

**Graph nodes created:**
- `adapter.{adapter_id}.config` - Configuration data
- `adapter.{adapter_id}.type` - Adapter type
- `adapter.{adapter_id}.occurrence_id` - Which occurrence saved it
- `adapter.{adapter_id}.persist` - Must be `True` for auto-restore

### Multi-Occurrence Support

In multi-occurrence deployments, each occurrence only loads adapters saved with its occurrence_id:
```bash
export AGENT_OCCURRENCE_ID="occurrence-1"
```

Adapters are de-duplicated by (adapter_type, occurrence_id, config_hash) - same config on different occurrences is valid.

## Guidelines

- **Test services**: Set `"test_only": true` in manifest
- **Production services**: Must pass security review
- **External dependencies**: Declare in manifest
- **Configuration**: Use schemas, not dicts
- **Protocols**: Always implement base protocols
- **No backwards compatibility**: Version via manifest

## Examples

- `mock_llm/` - Mock LLM for testing (first modular service)
- `geo_wisdom/` - Geographic navigation via OpenStreetMap (safe domain)
- `weather_wisdom/` - Weather advisories via NOAA API (safe domain)
- `sensor_wisdom/` - IoT sensor interpretation via Home Assistant (safe domain, filters medical sensors)
