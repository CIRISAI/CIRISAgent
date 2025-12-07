# Sample Adapter - Reference Implementation

This adapter serves as a reference implementation for CIRIS adapter developers and for QA testing.

## Features Demonstrated

### Bus Types

| Bus Type | Service | Description |
|----------|---------|-------------|
| TOOL | `SampleToolService` | Echo, status, and config tools |
| COMMUNICATION | `SampleCommunicationService` | Message send/receive |
| WISE_AUTHORITY | `SampleWisdomService` | Domain guidance provider |

### Interactive Configuration

Demonstrates `ConfigurableAdapterProtocol` with all step types:

1. **Discovery** - Mock service discovery (simulates mDNS)
2. **OAuth** - RFC 8252 loopback redirect for local testing
3. **Selection** - Feature selection from dynamic options
4. **Input** - Manual configuration entry
5. **Confirmation** - Review and apply

## OAuth Mock Testing (RFC 8252)

The adapter uses RFC 8252 "OAuth 2.0 for Native Apps" for local OAuth testing:

```
Redirect URI: http://127.0.0.1:{PORT}/callback
```

- **No pre-registration required** for loopback IPs
- **Dynamic port allocation** - server picks available port
- **PKCE required** - S256 code challenge method

### How It Works

1. QA starts local OAuth mock server on loopback
2. `get_oauth_url()` returns URL with `http://127.0.0.1:{PORT}/callback`
3. Test simulates user authorization
4. Mock server receives callback at `/callback?code=...&state=...`
5. `handle_oauth_callback()` exchanges code for mock tokens

## Usage

### Load with CIRIS

```bash
python main.py --adapter api --adapter sample_adapter
```

### Run QA Tests

```bash
python -m tools.qa_runner adapter_config
```

### Use as Template

```python
from ciris_adapters.sample_adapter import (
    SampleToolService,
    SampleCommunicationService,
    SampleWisdomService,
    SampleConfigurableAdapter,
)

# Copy and modify for your adapter
class MyToolService(SampleToolService):
    def get_tools(self):
        return [{"name": "my:tool", ...}]
```

## Manifest Structure

See `manifest.json` for the complete structure including:

- Module metadata (`module.name`, `module.version`)
- Service registrations (`services[].type`, `services[].class`)
- Capabilities list
- Interactive configuration (`interactive_config.steps`)
- Dependencies (protocols, schemas, external packages)
- Configuration options

## Files

| File | Purpose |
|------|---------|
| `manifest.json` | Adapter metadata and registration |
| `services.py` | TOOL, COMMUNICATION, WISE_AUTHORITY implementations |
| `configurable.py` | ConfigurableAdapterProtocol + OAuth mock |
| `__init__.py` | Package exports |
| `README.md` | This documentation |

## QA Test Coverage

The `adapter_config` QA module tests:

- List configurable adapters endpoint
- Session lifecycle (start, get, expire)
- All 5 step types (discovery, oauth, select, input, confirm)
- OAuth URL generation and callback handling
- Configuration validation and application
- Error handling (invalid adapter, expired session)
