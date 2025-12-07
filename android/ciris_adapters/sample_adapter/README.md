# Sample Adapter - Complete Template for CIRIS Adapters

This adapter serves as a **complete reference implementation** for building CIRIS adapters. Use it as a template when creating new adapters.

## What This Adapter Demonstrates

### 1. BaseAdapterProtocol Compliance (`adapter.py`)

The `adapter.py` file shows how to create a proper adapter wrapper that:
- Inherits from `ciris_engine.logic.adapters.base.Service`
- Takes `runtime` and optional `context` in `__init__`
- Implements `get_services_to_register()` returning `List[AdapterServiceRegistration]`
- Implements lifecycle methods: `start()`, `stop()`, `run_lifecycle()`
- Exports as `Adapter = YourAdapterClass` for dynamic loading

### 2. Multiple Service Types (`services.py`)

Shows how to implement services for each bus type:

| Bus Type | Service Class | Capabilities |
|----------|---------------|--------------|
| TOOL | `SampleToolService` | `tool:sample:echo`, `tool:sample:status`, `tool:sample:config` |
| COMMUNICATION | `SampleCommunicationService` | `communication:send_message`, `communication:fetch_messages` |
| WISE_AUTHORITY | `SampleWisdomService` | `get_guidance`, `fetch_guidance`, `domain:sample` |

### 3. Interactive Configuration (`configurable.py`)

Demonstrates `ConfigurableAdapterProtocol` with all configuration step types:

1. **Discovery** - Find services on network (mDNS, API scanning, etc.)
2. **OAuth** - OAuth2 with PKCE using RFC 8252 loopback redirect
3. **Select** - User selection from dynamic options (single or multiple)
4. **Input** - Manual configuration entry (required and optional fields)
5. **Confirm** - Review and apply configuration

### 4. Proper Manifest Structure (`manifest.json`)

Complete manifest showing:
- Module metadata (`module.name`, `module.version`, etc.)
- Service registrations with types, classes, and capabilities
- Interactive configuration workflow with all step types
- Dependencies (protocols, schemas, external packages)
- Configuration options with environment variables
- Metadata for discoverability

---

## Creating a New Adapter from This Template

### Step 1: Copy the Template

```bash
# Copy sample_adapter to your new adapter name
cp -r ciris_adapters/sample_adapter ciris_adapters/your_adapter_name

# Update all file references
cd ciris_adapters/your_adapter_name
```

### Step 2: Update `manifest.json`

1. **Module metadata**:
   ```json
   "module": {
     "name": "your_adapter_name",
     "version": "1.0.0",
     "description": "Your adapter description",
     "author": "Your Name"
   }
   ```

2. **Services**: Update service classes and capabilities
   ```json
   "services": [{
     "type": "TOOL",  // or COMMUNICATION, WISE_AUTHORITY, etc.
     "priority": "NORMAL",
     "class": "your_adapter_name.services.YourToolService",
     "capabilities": ["tool:your_feature"]
   }]
   ```

3. **Interactive config steps**: Customize for your adapter's needs
   - Remove steps you don't need
   - Add steps specific to your service
   - Update field definitions in `input` steps

### Step 3: Implement Services (`services.py`)

Replace the sample services with your actual implementations:

```python
class YourToolService:
    """Your tool service implementation."""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        # Read from environment variables set by configurable.apply_config()
        self.api_url = os.getenv("YOUR_ADAPTER_API_URL")
        self.api_key = os.getenv("YOUR_ADAPTER_API_KEY")

    async def start(self):
        """Initialize connections, start background tasks, etc."""
        pass

    async def stop(self):
        """Clean up resources."""
        pass

    def get_tools(self) -> List[Dict[str, Any]]:
        """Return list of available tools."""
        return [{
            "name": "your_adapter:action",
            "description": "Does something useful",
            "parameters": {
                "param1": {"type": "string", "required": True}
            }
        }]

    async def execute_tool(self, tool_name: str, parameters: Dict[str, Any]):
        """Execute a tool."""
        # Your implementation here
        pass
```

### Step 4: Implement ConfigurableAdapter (`configurable.py`)

Customize the configuration workflow:

```python
class YourConfigurableAdapter:
    """ConfigurableAdapterProtocol implementation."""

    async def discover(self, discovery_type: str) -> List[Dict[str, Any]]:
        """Discover instances of your service."""
        # Return list of discovered items with:
        # - id: unique identifier
        # - label: display name
        # - description: description
        # - metadata: any additional info
        pass

    async def get_oauth_url(self, base_url: str, state: str) -> str:
        """Generate OAuth URL (if using OAuth)."""
        pass

    async def handle_oauth_callback(self, code: str, state: str, base_url: str):
        """Exchange OAuth code for tokens."""
        pass

    async def get_config_options(self, step_id: str, context: Dict[str, Any]):
        """Return options for select steps."""
        if step_id == "select_devices":
            # Query your service for available devices
            return [...]
        pass

    async def validate_config(self, config: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """Validate configuration before applying."""
        # Check required fields, test connectivity, etc.
        pass

    async def apply_config(self, config: Dict[str, Any]) -> bool:
        """Apply configuration."""
        # Store config, set environment variables for services
        os.environ["YOUR_ADAPTER_API_URL"] = config["base_url"]
        os.environ["YOUR_ADAPTER_API_KEY"] = config["access_token"]
        return True
```

### Step 5: Create Adapter Wrapper (`adapter.py`)

Update the adapter class:

```python
from .services import YourToolService, YourCommService  # Import your services

class YourAdapter(Service):
    """Your adapter wrapper."""

    def __init__(self, runtime: Any, context: Optional[Any] = None, **kwargs: Any):
        super().__init__(config=kwargs.get("adapter_config"))
        self.runtime = runtime
        self.context = context

        # Create your services
        adapter_config = kwargs.get("adapter_config", {})
        self.tool_service = YourToolService(config=adapter_config)
        self.comm_service = YourCommService(config=adapter_config)

        self._running = False

    def get_services_to_register(self) -> List[AdapterServiceRegistration]:
        """Register your services."""
        return [
            AdapterServiceRegistration(
                service_type=ServiceType.TOOL,
                provider=self.tool_service,
                priority=Priority.NORMAL,
                capabilities=["tool:your_feature"],
            ),
            # Add more service registrations
        ]

    async def start(self):
        """Start all services."""
        await self.tool_service.start()
        await self.comm_service.start()
        self._running = True

    async def stop(self):
        """Stop all services."""
        self._running = False
        await self.tool_service.stop()
        await self.comm_service.stop()

    async def run_lifecycle(self, agent_task: Any):
        """Run adapter lifecycle."""
        try:
            await agent_task
        finally:
            await self.stop()

# CRITICAL: Export as Adapter for dynamic loading
Adapter = YourAdapter
```

### Step 6: Update `__init__.py`

```python
from .adapter import YourAdapter
from .configurable import YourConfigurableAdapter
from .services import YourToolService, YourCommService

# CRITICAL: Export Adapter
Adapter = YourAdapter

__all__ = [
    "Adapter",
    "YourAdapter",
    "YourToolService",
    "YourCommService",
    "YourConfigurableAdapter",
]
```

---

## Interactive Configuration Step Types

### Discovery Step
```json
{
  "step_id": "discover",
  "step_type": "discovery",
  "title": "Discover Services",
  "description": "Find available services",
  "discovery_method": "mdns"
}
```
- Calls `discover(discovery_type)` method
- Returns list of discovered items
- Items have: `id`, `label`, `description`, `metadata`

### OAuth Step
```json
{
  "step_id": "oauth",
  "step_type": "oauth",
  "title": "Authenticate",
  "oauth_config": {
    "provider_name": "Service Name",
    "authorization_path": "/oauth/authorize",
    "token_path": "/oauth/token",
    "client_id_source": "static",
    "scopes": ["read", "write"],
    "pkce_required": true
  }
}
```
- Calls `get_oauth_url(base_url, state)` for authorization URL
- Calls `handle_oauth_callback(code, state, base_url)` for token exchange
- Returns tokens in context as `oauth_tokens`

### Select Step (Required, Single)
```json
{
  "step_id": "select_instance",
  "step_type": "select",
  "title": "Select Instance",
  "multiple": false,
  "optional": false
}
```
- Calls `get_config_options(step_id, context)`
- User must select exactly one item
- Selected item stored in context

### Select Step (Optional, Multiple)
```json
{
  "step_id": "select_cameras",
  "step_type": "select",
  "title": "Select Cameras",
  "multiple": true,
  "optional": true
}
```
- Calls `get_config_options(step_id, context)`
- User can select 0 or more items
- Step can be skipped entirely

### Input Step (Required Fields)
```json
{
  "step_id": "settings",
  "step_type": "input",
  "fields": [
    {
      "name": "api_url",
      "type": "string",
      "label": "API URL",
      "required": true,
      "default": "http://localhost:8080"
    },
    {
      "name": "timeout",
      "type": "integer",
      "label": "Timeout (seconds)",
      "required": true,
      "default": 30,
      "min": 1,
      "max": 300
    }
  ]
}
```
- Field types: `string`, `integer`, `float`, `boolean`
- Fields can be `required: true` or `required: false`
- Can have `default`, `min`, `max` values

### Input Step (Optional Step)
```json
{
  "step_id": "advanced",
  "step_type": "input",
  "optional": true,
  "fields": [...]
}
```
- Entire step can be skipped
- Fields are optional within the step

### Confirm Step
```json
{
  "step_id": "confirm",
  "step_type": "confirm",
  "title": "Confirm Configuration"
}
```
- Shows summary of all collected configuration
- User confirms to trigger `apply_config()`
- Final step before completion

---

## Required Files Checklist

- [ ] `manifest.json` - Adapter metadata and configuration
- [ ] `adapter.py` - BaseAdapterProtocol wrapper with `Adapter` export
- [ ] `services.py` - Service implementations (TOOL, COMMUNICATION, etc.)
- [ ] `configurable.py` - ConfigurableAdapterProtocol implementation
- [ ] `__init__.py` - Package exports with `Adapter` export
- [ ] `README.md` - Documentation

---

## Testing Your Adapter

### Load with CIRIS

```bash
python main.py --adapter api --adapter your_adapter_name
```

### Test Configuration Flow

```bash
# Start API server
python main.py --adapter api --port 8000

# Test configuration via API
curl -X POST http://localhost:8000/v1/system/adapters/your_adapter_name/configure/start
```

### Write QA Tests

See `/home/emoore/CIRISAgent/tools/qa_runner/modules/adapter_config.py` for examples.

---

## Common Patterns

### Reading Environment Variables

In `apply_config()`, set environment variables:
```python
async def apply_config(self, config: Dict[str, Any]) -> bool:
    os.environ["YOUR_SERVICE_URL"] = config["base_url"]
    os.environ["YOUR_SERVICE_TOKEN"] = config["access_token"]
    return True
```

In your service `__init__()`, read them:
```python
def __init__(self, config: Optional[Dict[str, Any]] = None):
    self.url = os.getenv("YOUR_SERVICE_URL", "http://localhost:8080")
    self.token = os.getenv("YOUR_SERVICE_TOKEN")
```

### OAuth with PKCE

See `configurable.py` for complete OAuth2 + PKCE example:
1. Generate PKCE challenge in `get_oauth_url()`
2. Store verifier keyed by state
3. Exchange code + verifier in `handle_oauth_callback()`

### Discovery via mDNS

```python
from zeroconf import ServiceBrowser, Zeroconf

async def _discover_mdns(self):
    zeroconf = Zeroconf()
    listener = YourDiscoveryListener()
    browser = ServiceBrowser(zeroconf, "_your-service._tcp.local.", listener)
    await asyncio.sleep(3)  # Wait for discovery
    browser.cancel()
    zeroconf.close()
    return listener.services
```

### Validation Before Apply

```python
async def validate_config(self, config: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
    # Check required fields
    if not config.get("base_url"):
        return False, "base_url is required"

    # Test connectivity
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{config['base_url']}/health") as resp:
                if resp.status != 200:
                    return False, f"Service unreachable: HTTP {resp.status}"
    except Exception as e:
        return False, f"Connection error: {e}"

    return True, None
```

---

## Getting Help

- **Reference Implementation**: This adapter (sample_adapter)
- **Production Example**: `ciris_adapters/home_assistant/`
- **Issues**: https://github.com/CIRISAI/CIRISAgent/issues
- **Protocols**: See `ciris_engine/protocols/adapters/` for interface definitions

---

**Remember**: The best way to create a new adapter is to copy this entire directory and modify it step by step!
