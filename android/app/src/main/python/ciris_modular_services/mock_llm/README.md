# MockLLM Modular Service

The first modular service in CIRIS - demonstrates how to package services for external contribution.

## Overview

MockLLMService simulates LLM responses for testing without requiring API keys or network access.

**⚠️ WARNING: TEST ONLY - NOT FOR PRODUCTION USE**

## Structure

```
mock_llm/
├── manifest.json       # Service metadata and registration info
├── protocol.py         # Protocol definition (extends LLMService)
├── schemas.py          # Pydantic schemas for config/status
├── service.py          # Main service implementation
├── responses.py        # Base response templates
├── responses_*.py      # Specialized response modules
├── __init__.py         # Package initialization
└── README.md          # This file
```

## Manifest Format

The `manifest.json` file declares:
- Service metadata (name, version, type)
- Capabilities provided
- Dependencies on core CIRIS protocols/schemas
- Configuration options
- Export paths for dynamic loading

## Integration

When CIRIS starts with `--mock-llm` flag:
1. Service loader reads manifest.json
2. Validates dependencies are available
3. Dynamically imports service class
4. Registers with ServiceRegistry
5. Service is available through standard bus

## Creating Your Own Modular Service

1. Copy this structure as a template
2. Update manifest.json with your service details
3. Implement required protocols
4. Define schemas for your data structures
5. Place in ciris_modular_services/ directory
6. CIRIS will auto-discover on startup

## Testing

```python
# Your service is automatically available when loaded
llm_service = service_registry.get_service(ServiceType.LLM)
response = await llm_service.generate_structured_response(request)
```
