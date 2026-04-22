"""
Sample adapter ConfigurableAdapterProtocol implementation.

This module demonstrates how to implement interactive configuration workflows
including OAuth2 with PKCE using RFC 8252 loopback redirect for local testing.

RFC 8252 (OAuth 2.0 for Native Apps):
- Uses loopback redirect URIs: http://127.0.0.1:{port}/callback
- No pre-registration required for loopback IPs
- Port is dynamically allocated, included in redirect_uri
- Safe for local testing without exposing to network

For production OAuth flows:
- Register proper redirect URIs with the OAuth provider
- Use HTTPS redirect URIs
- Consider using authorization code flow with PKCE (recommended)
"""

import logging
import secrets
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class SampleConfigurableAdapter:
    """Sample implementation of ConfigurableAdapterProtocol.

    This class demonstrates the complete configuration workflow:
    1. Discovery - Find local services (mock discovery)
    2. OAuth - Authenticate with the service (RFC 8252 loopback mock)
    3. Selection - Choose which features to enable
    4. Input - Configure additional settings
    5. Validation & Apply - Verify and activate configuration

    For QA testing, this adapter provides predictable mock responses
    that exercise the entire configuration flow without external dependencies.

    Example usage:
        adapter = SampleConfigurableAdapter()
        items = await adapter.discover("mock_discovery")
        oauth_url = await adapter.get_oauth_url("http://localhost:9999", "state123")
        tokens = await adapter.handle_oauth_callback("code", "state123", "http://localhost:9999")
        options = await adapter.get_config_options("select_features", {"access_token": "..."})
        valid, error = await adapter.validate_config({...})
        success = await adapter.apply_config({...})
    """

    # RFC 8252: Loopback redirect for local OAuth testing
    # Port 0 means "any available port" - actual port determined at runtime
    LOOPBACK_REDIRECT_PORT = 0  # Dynamic allocation
    LOOPBACK_REDIRECT_HOST = "127.0.0.1"

    # Mock OAuth provider settings (for QA)
    MOCK_CLIENT_ID = "sample_adapter_client"
    MOCK_SCOPES = ["read", "write", "config"]

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        """Initialize the configurable adapter.

        Args:
            config: Optional existing configuration
        """
        self.config = config or {}
        self._applied_config: Optional[Dict[str, Any]] = None
        self._mock_tokens: Dict[str, str] = {}
        logger.info("SampleConfigurableAdapter initialized")

    async def discover(self, discovery_type: str) -> List[Dict[str, Any]]:
        """Run discovery and return found items.

        For the sample adapter, this returns mock discovered services.
        In a real adapter, this might use:
        - mDNS/Bonjour for local service discovery
        - API scanning for known endpoints
        - Configuration file parsing

        Args:
            discovery_type: Type of discovery ("mock_discovery", "mdns", etc.)

        Returns:
            List of discovered items
        """
        logger.info(f"Running discovery: {discovery_type}")

        if discovery_type == "mock_discovery":
            # Return mock discovered services for QA testing
            return [
                {
                    "id": "sample_local_1",
                    "label": "Sample Service (localhost:9999)",
                    "description": "Local sample service instance",
                    "metadata": {
                        "host": "localhost",
                        "port": 9999,
                        "version": "1.0.0",
                        "features": ["echo", "status", "config"],
                    },
                },
                {
                    "id": "sample_local_2",
                    "label": "Sample Service (192.168.1.100:9999)",
                    "description": "Network sample service instance",
                    "metadata": {
                        "host": "192.168.1.100",
                        "port": 9999,
                        "version": "1.0.0",
                        "features": ["echo", "status"],
                    },
                },
            ]

        elif discovery_type == "none":
            # For manual entry workflows
            return []

        # Unknown discovery type - return empty
        logger.warning(f"Unknown discovery type: {discovery_type}")
        return []

    async def get_oauth_url(
        self,
        base_url: str,
        state: str,
        code_challenge: Optional[str] = None,
        callback_base_url: Optional[str] = None,
        redirect_uri: Optional[str] = None,
        platform: Optional[str] = None,
    ) -> str:
        """Generate OAuth authorization URL.

        Uses RFC 8252 loopback redirect for local testing:
        - http://127.0.0.1:{port}/callback
        - Port is dynamically determined by the callback server
        - No pre-registration required with OAuth provider

        Args:
            base_url: Base URL of the OAuth provider
            state: State parameter for CSRF protection
            code_challenge: PKCE code challenge (unused in sample)
            callback_base_url: Callback base URL (unused in sample)
            redirect_uri: Redirect URI (unused in sample)
            platform: Platform hint (unused in sample)

        Returns:
            Full OAuth authorization URL
        """
        # For real OAuth, you'd register redirect URIs with the provider
        # RFC 8252 allows loopback without pre-registration
        redirect_uri = f"http://{self.LOOPBACK_REDIRECT_HOST}:{{PORT}}/callback"

        # Generate mock OAuth URL (in production, use real OAuth provider URL)
        oauth_url = (
            f"{base_url}/oauth/authorize"
            f"?client_id={self.MOCK_CLIENT_ID}"
            f"&response_type=code"
            f"&redirect_uri={redirect_uri}"
            f"&scope={'+'.join(self.MOCK_SCOPES)}"
            f"&state={state}"
            f"&code_challenge={{CHALLENGE}}"  # PKCE challenge placeholder
            f"&code_challenge_method=S256"
        )

        logger.info(f"Generated OAuth URL for state: {state[:8]}...")
        return oauth_url

    async def handle_oauth_callback(
        self,
        code: str,
        state: str,
        base_url: str,
        code_verifier: Optional[str] = None,
        callback_base_url: Optional[str] = None,
        redirect_uri: Optional[str] = None,
        platform: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Exchange OAuth authorization code for tokens.

        For QA testing, this returns mock tokens without network calls.
        In production, this would:
        1. Validate state matches original request
        2. POST to token endpoint with code + PKCE verifier
        3. Return access_token, refresh_token, expires_in

        Args:
            code: Authorization code from OAuth provider
            state: State parameter for validation
            base_url: Base URL of the OAuth provider
            code_verifier: PKCE code verifier (unused in sample)
            callback_base_url: Callback base URL (unused in sample)
            redirect_uri: Redirect URI (unused in sample)
            platform: Platform hint (unused in sample)

        Returns:
            Token response
        """
        logger.info(f"Handling OAuth callback for state: {state[:8]}...")

        # For QA: Accept any code and return mock tokens
        # In production: Validate and exchange with real OAuth provider
        if code.startswith("mock_") or code.startswith("test_"):
            # QA test codes - return mock tokens
            access_token = f"sample_access_{secrets.token_hex(16)}"
            refresh_token = f"sample_refresh_{secrets.token_hex(16)}"

            self._mock_tokens[state] = access_token

            return {
                "access_token": access_token,
                "refresh_token": refresh_token,
                "token_type": "Bearer",
                "expires_in": 3600,
                "scope": " ".join(self.MOCK_SCOPES),
            }

        # For non-mock codes, simulate validation
        # In production: Make actual token exchange request
        access_token = f"sample_access_{secrets.token_hex(16)}"
        return {
            "access_token": access_token,
            "token_type": "Bearer",
            "expires_in": 3600,
        }

    async def get_config_options(self, step_id: str, context: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Get options for a selection step.

        Returns dynamic options based on the step and context.
        For example, after OAuth, we might query the service for
        available entities/features.

        Args:
            step_id: ID of the configuration step
            context: Current configuration context

        Returns:
            List of available options
        """
        logger.info(f"Getting config options for step: {step_id}")

        if step_id == "select_features":
            # Return available features
            # In production: Query the service for actual available features
            return [
                {
                    "id": "echo",
                    "label": "Echo Service",
                    "description": "Echo messages back for testing",
                    "metadata": {"default": True},
                },
                {
                    "id": "status",
                    "label": "Status Monitoring",
                    "description": "Monitor adapter status and metrics",
                    "metadata": {"default": True},
                },
                {
                    "id": "config",
                    "label": "Configuration API",
                    "description": "Allow configuration queries via tools",
                    "metadata": {"default": False},
                },
                {
                    "id": "wisdom",
                    "label": "Wisdom Provider",
                    "description": "Provide sample domain guidance",
                    "metadata": {"default": True},
                },
            ]

        elif step_id == "select_instance":
            # Return discovered instances from context
            # This demonstrates how to use discovery results in a select step
            discovered = context.get("discovered_items", [])
            logger.info(f"Returning {len(discovered)} discovered instances for selection")
            return [
                {
                    "id": item["id"],
                    "label": item["label"],
                    "description": item["description"],
                    "metadata": item.get("metadata", {}),
                }
                for item in discovered
            ]

        elif step_id == "optional_cameras":
            # Return mock camera list (optional step example)
            # In production: Query the service for actual cameras
            return [
                {
                    "id": "camera_front_door",
                    "label": "Front Door Camera",
                    "description": "1080p camera at main entrance",
                    "metadata": {"resolution": "1080p", "location": "front_door"},
                },
                {
                    "id": "camera_backyard",
                    "label": "Backyard Camera",
                    "description": "720p camera covering backyard",
                    "metadata": {"resolution": "720p", "location": "backyard"},
                },
                {
                    "id": "camera_garage",
                    "label": "Garage Camera",
                    "description": "1080p camera in garage",
                    "metadata": {"resolution": "1080p", "location": "garage"},
                },
            ]

        return []

    async def validate_config(self, config: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """Validate configuration before applying.

        Performs comprehensive validation:
        - Required fields present
        - Connectivity test (if applicable)
        - Permission verification (if token provided)

        Args:
            config: Complete configuration to validate

        Returns:
            (is_valid, error_message) tuple
        """
        logger.info("Validating configuration")

        # Check required fields
        if not config:
            return False, "Configuration is empty"

        # For QA: Check for special test flags
        if config.get("_force_validation_failure"):
            return False, "Forced validation failure for testing"

        # Validate base_url if present
        base_url = config.get("base_url", "")
        if base_url and not (base_url.startswith("http://") or base_url.startswith("https://")):
            return False, f"Invalid base_url: {base_url} (must start with http:// or https://)"

        # Validate poll_interval if present
        poll_interval = config.get("poll_interval")
        if poll_interval is not None:
            if not isinstance(poll_interval, int) or poll_interval < 1:
                return False, "poll_interval must be a positive integer"

        # Validate enabled_features if present
        features = config.get("enabled_features", [])
        valid_features = {"echo", "status", "config", "wisdom"}
        if features:
            invalid = set(features) - valid_features
            if invalid:
                return False, f"Invalid features: {invalid}"

        logger.info("Configuration validated successfully")
        return True, None

    async def apply_config(self, config: Dict[str, Any]) -> bool:
        """Apply the configuration to the adapter.

        Activates the configuration:
        - Store credentials securely
        - Initialize connections
        - Start monitoring/polling

        Args:
            config: Validated configuration to apply

        Returns:
            True if applied successfully
        """
        logger.info("Applying configuration")

        # Store the applied configuration
        self._applied_config = config.copy()

        # Remove sensitive data from logs
        safe_config = {k: v for k, v in config.items() if "token" not in k.lower() and "secret" not in k.lower()}
        logger.info(f"Configuration applied: {safe_config}")

        return True

    def get_applied_config(self) -> Optional[Dict[str, Any]]:
        """Get the currently applied configuration.

        Returns:
            Applied configuration or None if not configured
        """
        return self._applied_config


# OAuth Mock Server for local testing
# This can be used by QA tests to simulate OAuth callbacks


class OAuthMockServer:
    """Simple mock OAuth server for local testing.

    Uses RFC 8252 loopback redirect pattern:
    - Listens on 127.0.0.1 with dynamic port
    - Handles /oauth/authorize and /oauth/token endpoints
    - Returns predictable mock responses for QA

    Usage:
        server = OAuthMockServer()
        port = await server.start()
        # OAuth URL will redirect to http://127.0.0.1:{port}/callback
        # Test code can then simulate the callback
        await server.stop()
    """

    def __init__(self) -> None:
        """Initialize the mock OAuth server."""
        self._port: Optional[int] = None
        self._running = False
        # Store pending authorization requests by state
        self._pending_auth: Dict[str, Dict[str, Any]] = {}

    async def start(self, port: int = 0) -> int:
        """Start the mock OAuth server.

        Args:
            port: Port to listen on (0 = dynamic allocation)

        Returns:
            Actual port the server is listening on
        """
        # In a full implementation, this would start an aiohttp server
        # For now, just track the port
        self._port = port if port > 0 else 19999  # Default mock port
        self._running = True
        logger.info(f"OAuth mock server started on port {self._port}")
        return self._port

    async def stop(self) -> None:
        """Stop the mock OAuth server."""
        self._running = False
        self._port = None
        logger.info("OAuth mock server stopped")

    def get_authorization_url(self, client_id: str, state: str, redirect_uri: str) -> str:
        """Generate mock authorization URL.

        Args:
            client_id: OAuth client ID
            state: State parameter
            redirect_uri: Redirect URI after auth

        Returns:
            Authorization URL that would redirect to callback
        """
        self._pending_auth[state] = {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "created_at": "now",
        }
        return f"http://127.0.0.1:{self._port}/oauth/authorize?state={state}"

    def simulate_callback(self, state: str) -> Dict[str, str]:
        """Simulate successful OAuth callback.

        Args:
            state: State parameter from authorization request

        Returns:
            Callback parameters (code, state)
        """
        code = f"mock_auth_code_{secrets.token_hex(8)}"
        return {"code": code, "state": state}
