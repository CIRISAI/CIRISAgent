# CIRIS Modular Services

This directory contains modular services that can be dynamically loaded into CIRIS.

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
