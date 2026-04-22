# MockLLM Modular Service

The first modular service in CIRIS - demonstrates how to package services for external contribution.

## Overview

MockLLMService simulates LLM responses for testing without requiring API keys or network access.

**⚠️ WARNING: TEST ONLY - NOT FOR PRODUCTION USE**

## Structure

```
mock_llm/
├── manifest.json       # Service metadata and registration info
├── adapter.py          # BaseAdapterProtocol wrapper for dynamic loading
├── configurable.py     # ConfigurableAdapterProtocol implementation
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

## Wizard Configuration

The mock_llm adapter now supports interactive configuration via the ConfigurableAdapterProtocol:

### Configuration Options (all optional)

1. **Response Delay** - Simulate API latency
   - Range: 0-60000 milliseconds
   - Default: 100ms
   - Environment variable: `MOCK_LLM_DELAY_MS`

2. **Response Mode** - Control mock behavior
   - Options: deterministic, random, echo
   - Default: deterministic
   - Environment variable: `MOCK_LLM_RESPONSE_MODE`

3. **Failure Rate** - Simulate errors for testing
   - Range: 0.0-1.0 (probability)
   - Default: 0.0
   - Environment variable: `MOCK_LLM_FAILURE_RATE`

### Using the Configuration Wizard

Via Android app or API:
```bash
# Start configuration session
POST /adapters/mock_llm/configure/start

# Configure each step
POST /adapters/configure/{session_id}/step
{
  "step_id": "configure_delay",
  "data": {"delay_ms": 500}
}

# Complete configuration
POST /adapters/configure/{session_id}/complete
```

Or programmatically:
```python
from ciris_adapters.mock_llm import MockLLMConfigurableAdapter

# Create and configure
config_adapter = MockLLMConfigurableAdapter()
await config_adapter.apply_config({
    "delay_ms": 500,
    "response_mode": "random",
    "failure_rate": 0.1
})

# Load the adapter
from ciris_adapters.mock_llm import MockLLMAdapter
adapter = MockLLMAdapter(runtime, context)
await adapter.start()
```

## Creating Your Own Modular Service

1. Copy this structure as a template
2. Update manifest.json with your service details
3. Implement required protocols
4. Define schemas for your data structures
5. Place in ciris_adapters/ directory
6. CIRIS will auto-discover on startup

## Testing

```python
# Your service is automatically available when loaded
llm_service = service_registry.get_service(ServiceType.LLM)
response = await llm_service.generate_structured_response(request)
```
