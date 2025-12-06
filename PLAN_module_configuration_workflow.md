# Module Dynamic Configuration Workflow - Implementation Plan

## Overview

This plan introduces a **Module Configuration System** that enables modules to:
1. Declare they need interactive configuration (beyond static env vars)
2. Trigger discovery logic on module load
3. Drive multi-step configuration workflows via API
4. Support OAuth2 authentication flows for external services

## Current Architecture Analysis

### Existing Patterns

1. **ManifestSchema** (`ciris_engine/schemas/runtime/manifest.py`)
   - `ConfigurationParameter` has: `type`, `default`, `env`, `description`, `sensitivity`, `required`
   - Missing: interactive config, discovery, OAuth flows

2. **Setup Routes** (`routes/setup.py`)
   - Multi-step wizard: status → providers → validate → complete
   - Pattern: List options → User selects → Validate → Save

3. **Connectors Routes** (`routes/connectors.py`)
   - CRUD pattern for external connections
   - Pattern: Register → Test → Update → List

4. **ModularServiceLoader** (`logic/runtime/modular_service_loader.py`)
   - Discovers manifests, validates, loads classes
   - Missing: interactive configuration hooks

## New Architecture

### 1. Enhanced Manifest Schema

```python
# ciris_engine/schemas/runtime/manifest.py - additions

class ConfigurationStep(BaseModel):
    """A step in the configuration workflow."""
    step_id: str
    step_type: Literal["discovery", "oauth", "select", "input", "confirm"]
    title: str
    description: str
    # For discovery steps
    discovery_method: Optional[str] = None  # e.g., "mdns", "api_scan"
    # For oauth steps
    oauth_config: Optional[OAuthConfig] = None
    # For select steps
    options_method: Optional[str] = None  # method name to call for options
    # Dependencies
    depends_on: List[str] = []  # step_ids that must complete first

class OAuthConfig(BaseModel):
    """OAuth configuration for a module."""
    provider_name: str
    authorization_path: str  # e.g., "/auth/authorize"
    token_path: str  # e.g., "/auth/token"
    client_id_source: Literal["static", "indieauth"]  # IndieAuth = use our website URL
    scopes: List[str] = []
    pkce_required: bool = True

class InteractiveConfiguration(BaseModel):
    """Interactive configuration definition."""
    required: bool = False
    workflow_type: Literal["wizard", "discovery_then_config"]
    steps: List[ConfigurationStep]
    completion_method: str  # method to call when all steps complete

# Add to ServiceManifest:
class ServiceManifest(BaseModel):
    # ... existing fields ...
    interactive_config: Optional[InteractiveConfiguration] = None
```

### 2. Module Configuration Protocol

```python
# ciris_engine/protocols/module_config.py

from typing import Protocol, Optional, List, Dict, Any

class ConfigurableModule(Protocol):
    """Protocol for modules that support interactive configuration."""

    async def discover(self, discovery_type: str) -> List[Dict[str, Any]]:
        """Run discovery (mDNS, API scan, etc.) and return found items."""
        ...

    async def get_oauth_url(self, base_url: str, state: str) -> str:
        """Generate OAuth authorization URL for user redirect."""
        ...

    async def handle_oauth_callback(
        self, code: str, state: str, base_url: str
    ) -> Dict[str, Any]:
        """Exchange OAuth code for tokens."""
        ...

    async def get_config_options(
        self, step_id: str, context: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Get options for a selection step based on current context."""
        ...

    async def validate_config(
        self, config: Dict[str, Any]
    ) -> tuple[bool, Optional[str]]:
        """Validate configuration before saving."""
        ...

    async def apply_config(self, config: Dict[str, Any]) -> bool:
        """Apply the configuration to the module."""
        ...
```

### 3. Module Configuration Service

```python
# ciris_engine/logic/services/module_configuration.py

class ModuleConfigurationService:
    """Manages interactive configuration for modules."""

    def __init__(self, module_loader: ModularServiceLoader):
        self.module_loader = module_loader
        self.active_configs: Dict[str, ModuleConfigSession] = {}

    async def start_configuration(
        self, module_name: str, user_id: str
    ) -> ModuleConfigSession:
        """Start a configuration session for a module."""
        manifest = self._get_manifest(module_name)
        if not manifest.interactive_config:
            raise ValueError(f"Module {module_name} doesn't support interactive config")

        session = ModuleConfigSession(
            session_id=str(uuid.uuid4()),
            module_name=module_name,
            user_id=user_id,
            steps=manifest.interactive_config.steps,
            current_step=0,
            collected_config={},
        )
        self.active_configs[session.session_id] = session
        return session

    async def execute_step(
        self, session_id: str, step_data: Dict[str, Any]
    ) -> StepResult:
        """Execute a configuration step and return results."""
        session = self.active_configs[session_id]
        step = session.steps[session.current_step]
        module_instance = self._get_module_instance(session.module_name)

        if step.step_type == "discovery":
            results = await module_instance.discover(step.discovery_method)
            return StepResult(
                step_id=step.step_id,
                success=True,
                data={"discovered_items": results},
                next_step=session.current_step + 1 if results else None,
            )

        elif step.step_type == "oauth":
            if "code" in step_data:
                # Handle OAuth callback
                tokens = await module_instance.handle_oauth_callback(
                    code=step_data["code"],
                    state=step_data["state"],
                    base_url=session.collected_config.get("base_url", ""),
                )
                session.collected_config["oauth_tokens"] = tokens
                return StepResult(step_id=step.step_id, success=True, next_step=session.current_step + 1)
            else:
                # Generate OAuth URL
                oauth_url = await module_instance.get_oauth_url(
                    base_url=session.collected_config.get("base_url", ""),
                    state=session.session_id,
                )
                return StepResult(
                    step_id=step.step_id,
                    success=True,
                    data={"oauth_url": oauth_url, "awaiting_callback": True},
                )

        elif step.step_type == "select":
            if "selection" in step_data:
                # User made selection
                session.collected_config[step.step_id] = step_data["selection"]
                return StepResult(step_id=step.step_id, success=True, next_step=session.current_step + 1)
            else:
                # Get options for selection
                options = await module_instance.get_config_options(
                    step.step_id, session.collected_config
                )
                return StepResult(
                    step_id=step.step_id,
                    success=True,
                    data={"options": options},
                )

        # ... handle other step types ...
```

### 4. API Routes for Module Configuration

```python
# ciris_engine/logic/adapters/api/routes/modules.py

router = APIRouter(prefix="/modules", tags=["modules"])

@router.get("", response_model=SuccessResponse[List[ModuleInfo]])
async def list_modules(request: Request):
    """List all available modules with their configuration status."""
    ...

@router.get("/{module_name}", response_model=SuccessResponse[ModuleDetail])
async def get_module(module_name: str, request: Request):
    """Get detailed information about a module including config requirements."""
    ...

@router.post("/{module_name}/configure/start", response_model=SuccessResponse[ConfigSessionInfo])
async def start_configuration(
    module_name: str,
    request: Request,
    auth: AuthContext = Depends(require_admin)
):
    """Start interactive configuration for a module."""
    ...

@router.get("/configure/{session_id}/status", response_model=SuccessResponse[ConfigSessionStatus])
async def get_config_status(session_id: str, request: Request):
    """Get current status of a configuration session."""
    ...

@router.post("/configure/{session_id}/step", response_model=SuccessResponse[StepResult])
async def execute_config_step(
    session_id: str,
    step_data: Dict[str, Any],
    request: Request
):
    """Execute the current configuration step."""
    ...

@router.get("/configure/{session_id}/oauth/callback")
async def oauth_callback(
    session_id: str,
    code: str,
    state: str,
    request: Request
):
    """Handle OAuth callback from external service."""
    ...

@router.post("/configure/{session_id}/complete", response_model=SuccessResponse[Dict])
async def complete_configuration(session_id: str, request: Request):
    """Finalize and apply the configuration."""
    ...
```

### 5. HA Integration Module Updates

```json
// ciris_modular_services/ha_integration/manifest.json - additions
{
  "interactive_config": {
    "required": false,
    "workflow_type": "discovery_then_config",
    "steps": [
      {
        "step_id": "discover_ha",
        "step_type": "discovery",
        "title": "Find Home Assistant",
        "description": "Scanning network for Home Assistant instances...",
        "discovery_method": "mdns"
      },
      {
        "step_id": "select_ha",
        "step_type": "select",
        "title": "Select Home Assistant",
        "description": "Choose which Home Assistant instance to connect to",
        "depends_on": ["discover_ha"]
      },
      {
        "step_id": "authenticate",
        "step_type": "oauth",
        "title": "Authenticate",
        "description": "Log in to Home Assistant to authorize CIRIS",
        "oauth_config": {
          "provider_name": "home_assistant",
          "authorization_path": "/auth/authorize",
          "token_path": "/auth/token",
          "client_id_source": "indieauth",
          "pkce_required": true
        },
        "depends_on": ["select_ha"]
      },
      {
        "step_id": "discover_cameras",
        "step_type": "discovery",
        "title": "Find Cameras",
        "description": "Discovering available cameras...",
        "discovery_method": "ha_cameras",
        "depends_on": ["authenticate"]
      },
      {
        "step_id": "select_cameras",
        "step_type": "select",
        "title": "Select Cameras",
        "description": "Choose which cameras to enable for event detection",
        "depends_on": ["discover_cameras"]
      },
      {
        "step_id": "confirm",
        "step_type": "confirm",
        "title": "Confirm Configuration",
        "description": "Review and apply your Home Assistant configuration",
        "depends_on": ["select_cameras"]
      }
    ],
    "completion_method": "apply_config"
  }
}
```

```python
# ciris_modular_services/ha_integration/discovery.py

import asyncio
import hashlib
import secrets
import base64
from typing import Any, Dict, List, Optional
from zeroconf import ServiceBrowser, ServiceListener, Zeroconf
import aiohttp

class HADiscoveryService:
    """Handles Home Assistant discovery and OAuth flows."""

    HA_SERVICE_TYPE = "_home-assistant._tcp.local."

    async def discover_mdns(self, timeout: float = 5.0) -> List[Dict[str, Any]]:
        """Discover Home Assistant instances via mDNS."""
        instances: List[Dict[str, Any]] = []

        class HAListener(ServiceListener):
            def add_service(self, zc: Zeroconf, type_: str, name: str) -> None:
                info = zc.get_service_info(type_, name)
                if info:
                    # Parse TXT records
                    properties = {}
                    for key, value in info.properties.items():
                        if isinstance(value, bytes):
                            value = value.decode('utf-8')
                        properties[key.decode('utf-8') if isinstance(key, bytes) else key] = value

                    instances.append({
                        "name": name,
                        "host": info.server,
                        "port": info.port,
                        "addresses": [str(addr) for addr in info.parsed_addresses()],
                        "base_url": properties.get("base_url") or properties.get("internal_url"),
                        "version": properties.get("version"),
                        "location_name": properties.get("location_name"),
                        "uuid": properties.get("uuid"),
                        "requires_api_password": properties.get("requires_api_password") == "true",
                    })

            def remove_service(self, zc: Zeroconf, type_: str, name: str) -> None:
                pass

            def update_service(self, zc: Zeroconf, type_: str, name: str) -> None:
                pass

        zeroconf = Zeroconf()
        listener = HAListener()
        browser = ServiceBrowser(zeroconf, self.HA_SERVICE_TYPE, listener)

        await asyncio.sleep(timeout)

        zeroconf.close()
        return instances

    def generate_pkce(self) -> tuple[str, str]:
        """Generate PKCE code verifier and challenge."""
        code_verifier = secrets.token_urlsafe(32)
        code_challenge = base64.urlsafe_b64encode(
            hashlib.sha256(code_verifier.encode()).digest()
        ).decode().rstrip('=')
        return code_verifier, code_challenge

    def get_oauth_url(
        self,
        ha_base_url: str,
        redirect_uri: str,
        state: str,
        code_challenge: str,
    ) -> str:
        """Generate Home Assistant OAuth authorization URL."""
        # IndieAuth: client_id is our website URL
        client_id = "https://ciris.ai"

        params = {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "state": state,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
        }

        query = "&".join(f"{k}={v}" for k, v in params.items())
        return f"{ha_base_url.rstrip('/')}/auth/authorize?{query}"

    async def exchange_code_for_tokens(
        self,
        ha_base_url: str,
        code: str,
        code_verifier: str,
        redirect_uri: str,
    ) -> Dict[str, Any]:
        """Exchange authorization code for access and refresh tokens."""
        client_id = "https://ciris.ai"

        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{ha_base_url.rstrip('/')}/auth/token",
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "client_id": client_id,
                    "redirect_uri": redirect_uri,
                    "code_verifier": code_verifier,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            ) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    error = await response.text()
                    raise Exception(f"Token exchange failed: {error}")

    async def refresh_access_token(
        self,
        ha_base_url: str,
        refresh_token: str,
    ) -> Dict[str, Any]:
        """Refresh the access token using refresh token."""
        client_id = "https://ciris.ai"

        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{ha_base_url.rstrip('/')}/auth/token",
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                    "client_id": client_id,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            ) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    raise Exception("Token refresh failed")

    async def discover_cameras_from_ha(
        self,
        ha_base_url: str,
        access_token: str,
    ) -> List[Dict[str, Any]]:
        """Discover cameras from Home Assistant API."""
        cameras = []

        async with aiohttp.ClientSession() as session:
            # Get all camera entities
            async with session.get(
                f"{ha_base_url.rstrip('/')}/api/states",
                headers={"Authorization": f"Bearer {access_token}"},
            ) as response:
                if response.status == 200:
                    entities = await response.json()
                    for entity in entities:
                        entity_id = entity.get("entity_id", "")
                        if entity_id.startswith("camera."):
                            cameras.append({
                                "entity_id": entity_id,
                                "name": entity.get("attributes", {}).get("friendly_name", entity_id),
                                "state": entity.get("state"),
                                "supported_features": entity.get("attributes", {}).get("supported_features", 0),
                            })

            # Also check go2rtc if available (HA 2024.11+)
            try:
                async with session.get(
                    f"{ha_base_url.rstrip('/')}/api/go2rtc/streams",
                    headers={"Authorization": f"Bearer {access_token}"},
                ) as response:
                    if response.status == 200:
                        streams = await response.json()
                        for stream_name, stream_info in streams.items():
                            if not any(c["entity_id"] == f"camera.{stream_name}" for c in cameras):
                                cameras.append({
                                    "entity_id": f"go2rtc.{stream_name}",
                                    "name": stream_name,
                                    "state": "available",
                                    "source": "go2rtc",
                                    "producers": stream_info.get("producers", []),
                                })
            except Exception:
                pass  # go2rtc may not be available

        return cameras
```

## Implementation Order

### Phase 1: Schema Extensions
1. Add `InteractiveConfiguration` to manifest schema
2. Add `ConfigurationStep` and `OAuthConfig` schemas
3. Add `ConfigurableModule` protocol

### Phase 2: Configuration Service
1. Create `ModuleConfigurationService`
2. Implement session management
3. Implement step execution engine

### Phase 3: API Routes
1. Create `/modules` routes
2. Implement configuration workflow endpoints
3. Add OAuth callback handling

### Phase 4: HA Integration Module
1. Add discovery.py with mDNS and OAuth
2. Update manifest.json with interactive_config
3. Implement `ConfigurableModule` protocol in service.py
4. Add token storage and refresh logic

### Phase 5: Frontend Support (CIRISGUI)
1. Create module configuration wizard component
2. Implement OAuth redirect handling
3. Add discovery results display
4. Create camera selection UI

## API Flow Example

```
1. User opens Module Settings in GUI
   GET /v1/modules
   → Returns list with ha_integration showing "requires_configuration: true"

2. User clicks "Configure" on ha_integration
   POST /v1/modules/ha_integration/configure/start
   → Returns { session_id: "abc123", current_step: "discover_ha" }

3. Frontend triggers discovery
   POST /v1/modules/configure/abc123/step
   Body: {}
   → Returns { discovered_items: [{ name: "Home", base_url: "http://192.168.1.50:8123", ... }] }

4. User selects Home Assistant instance
   POST /v1/modules/configure/abc123/step
   Body: { selection: { base_url: "http://192.168.1.50:8123" } }
   → Returns { next_step: "authenticate" }

5. Frontend requests OAuth URL
   POST /v1/modules/configure/abc123/step
   Body: {}
   → Returns { oauth_url: "http://192.168.1.50:8123/auth/authorize?...", awaiting_callback: true }

6. User is redirected to HA, logs in, redirected back
   GET /v1/modules/configure/abc123/oauth/callback?code=XYZ&state=abc123
   → Exchanges code for tokens, returns success

7. Camera discovery runs automatically
   POST /v1/modules/configure/abc123/step
   Body: {}
   → Returns { discovered_items: [{ entity_id: "camera.front_door", name: "Front Door", ... }] }

8. User selects cameras
   POST /v1/modules/configure/abc123/step
   Body: { selection: ["camera.front_door", "camera.backyard"] }
   → Returns { next_step: "confirm" }

9. User confirms
   POST /v1/modules/configure/abc123/complete
   → Saves config, starts HA integration service
   → Returns { status: "configured", message: "Home Assistant integration active" }
```

## Security Considerations

1. **OAuth State Validation**: Session ID in state param prevents CSRF
2. **PKCE**: Required for all OAuth flows (native app security)
3. **Token Storage**: Encrypted in config service, never exposed in API
4. **Refresh Token Handling**: Automatic refresh before expiry
5. **Session Cleanup**: Config sessions expire after 30 minutes of inactivity

## Testing Plan

1. Unit tests for discovery service
2. Unit tests for OAuth flow (mock HA responses)
3. Integration tests for full config workflow
4. E2E tests with actual HA instance (manual)
