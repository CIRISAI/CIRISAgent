"""
Protocol for adapters that support interactive configuration workflows.

This protocol enables dynamic adapter configuration through:
- Discovery mechanisms (mDNS, API scanning, etc.)
- OAuth authentication flows
- Interactive step-by-step configuration
- Validation and application of settings
"""

from typing import Any, Dict, List, Optional, Protocol, Tuple, runtime_checkable


@runtime_checkable
class ConfigurableAdapterProtocol(Protocol):
    """Protocol for adapters that support interactive configuration workflows.

    Adapters implementing this protocol can be configured interactively
    by end users through the CIRIS management interface. The protocol
    supports discovery, OAuth flows, step-by-step configuration, and
    validation.

    Example:
        An adapter implementing this protocol might:
        1. Discover Home Assistant instances via mDNS
        2. Guide user through OAuth authentication
        3. Let user select which entities to monitor
        4. Validate the configuration
        5. Apply the settings to start monitoring
    """

    async def discover(self, discovery_type: str) -> List[Dict[str, Any]]:
        """Run discovery and return found items.

        Discovery mechanisms vary by adapter:
        - "mdns": Multicast DNS service discovery
        - "api_scan": API endpoint scanning
        - "local": Local system scanning
        - "manual": Manual entry (returns empty list)

        Args:
            discovery_type: Type of discovery to perform

        Returns:
            List of discovered items, each containing:
                - id: Unique identifier
                - label: Human-readable name
                - description: Additional details
                - metadata: Discovery-specific data (IP, port, etc.)

        Example:
            >>> items = await adapter.discover("mdns")
            >>> items[0]
            {
                "id": "homeassistant_abc123",
                "label": "Home Assistant (192.168.1.50)",
                "description": "Home Assistant Core 2024.1.0",
                "metadata": {
                    "host": "192.168.1.50",
                    "port": 8123,
                    "version": "2024.1.0"
                }
            }
        """
        ...

    async def get_oauth_url(
        self,
        base_url: str,
        state: str,
        code_challenge: Optional[str] = None,
        callback_base_url: Optional[str] = None,
        redirect_uri: Optional[str] = None,
        platform: Optional[str] = None,
    ) -> str:
        """Generate OAuth authorization URL for user redirect.

        Creates a properly formatted OAuth authorization URL that the
        user will be redirected to for authentication. The state parameter
        is used for CSRF protection.

        Args:
            base_url: Base URL of the OAuth provider (e.g., discovered instance)
            state: State parameter for CSRF protection (managed by CIRIS)
            code_challenge: Optional PKCE code challenge (S256). Some adapters
                          generate their own internally and ignore this parameter.
            callback_base_url: Optional base URL for OAuth callback (e.g., http://127.0.0.1:8080)
                             Used for local/mobile deployments where callback should go
                             to a local server instead of production.
            redirect_uri: Optional explicit redirect URI. For Android deep links,
                        this would be "ciris://oauth/callback". If not provided,
                        the callback_base_url or default production callback is used.
            platform: Optional platform hint (android, ios, web, desktop).
                    Used for platform-specific OAuth handling.

        Returns:
            Full OAuth authorization URL including all required parameters

        Example:
            >>> # Standard OAuth
            >>> url = await adapter.get_oauth_url(
            ...     "https://homeassistant.local:8123",
            ...     "csrf_token_abc123"
            ... )
            >>> url
            "https://homeassistant.local:8123/auth/authorize?client_id=...&state=csrf_token_abc123"

            >>> # Android deep link OAuth
            >>> url = await adapter.get_oauth_url(
            ...     "https://homeassistant.local:8123",
            ...     "csrf_token_abc123",
            ...     redirect_uri="ciris://oauth/callback",
            ...     platform="android"
            ... )
        """
        ...

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

        Called when the OAuth provider redirects back to CIRIS with an
        authorization code. Exchanges the code for access and refresh tokens.

        Args:
            code: Authorization code from OAuth provider
            state: State parameter for validation (must match original)
            base_url: Base URL of the OAuth provider

        Returns:
            Token response containing:
                - access_token: Access token for API calls
                - refresh_token: Token for refreshing access (optional)
                - expires_in: Token lifetime in seconds (optional)
                - token_type: Type of token (usually "Bearer")
                - scope: Granted scopes (optional)

        Raises:
            ValueError: If state validation fails
            RuntimeError: If token exchange fails

        Example:
            >>> tokens = await adapter.handle_oauth_callback(
            ...     code="auth_code_xyz",
            ...     state="csrf_token_abc123",
            ...     base_url="https://homeassistant.local:8123"
            ... )
            >>> tokens["access_token"]
            "eyJ0eXAiOiJKV1QiLCJhbGc..."
        """
        ...

    async def get_config_options(self, step_id: str, context: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Get options for a selection step based on current context.

        Dynamically generates configuration options based on the current
        step and accumulated context from previous steps. For example,
        after OAuth authentication, this might fetch available entities
        from the connected service.

        Args:
            step_id: ID of the configuration step requesting options
            context: Current configuration context (data from previous steps)
                May include: base_url, access_token, selected_items, etc.

        Returns:
            List of options, each containing:
                - id: Unique identifier for this option
                - label: Human-readable name
                - description: Additional details
                - metadata: Option-specific data

        Example:
            >>> options = await adapter.get_config_options(
            ...     step_id="select_entities",
            ...     context={
            ...         "base_url": "https://homeassistant.local:8123",
            ...         "access_token": "eyJ0eXAi..."
            ...     }
            ... )
            >>> options[0]
            {
                "id": "sensor.living_room_temperature",
                "label": "Living Room Temperature",
                "description": "23.5°C",
                "metadata": {
                    "entity_id": "sensor.living_room_temperature",
                    "domain": "sensor",
                    "state": "23.5"
                }
            }
        """
        ...

    async def validate_config(self, config: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """Validate configuration before saving.

        Performs comprehensive validation of the complete configuration,
        including connectivity tests, permission checks, and schema validation.

        Args:
            config: Complete configuration to validate
                Typically includes: base_url, access_token, selected options, etc.

        Returns:
            Tuple of (is_valid, error_message)
                - is_valid: True if configuration is valid
                - error_message: None if valid, error description if invalid

        Example:
            >>> valid, error = await adapter.validate_config({
            ...     "base_url": "https://homeassistant.local:8123",
            ...     "access_token": "eyJ0eXAi...",
            ...     "entities": ["sensor.temperature"]
            ... })
            >>> valid
            True
            >>> error
            None

            >>> valid, error = await adapter.validate_config({
            ...     "base_url": "https://invalid.local",
            ...     "access_token": "bad_token"
            ... })
            >>> valid
            False
            >>> error
            "Connection failed: Unable to reach https://invalid.local"
        """
        ...

    async def apply_config(self, config: Dict[str, Any]) -> bool:
        """Apply the configuration to the adapter.

        Applies the validated configuration, making it active for the adapter.
        This typically involves storing credentials, establishing connections,
        and starting monitoring or interaction with the configured service.

        Args:
            config: Configuration to apply (already validated)

        Returns:
            True if configuration was applied successfully, False otherwise

        Raises:
            RuntimeError: If configuration application fails critically

        Example:
            >>> success = await adapter.apply_config({
            ...     "base_url": "https://homeassistant.local:8123",
            ...     "access_token": "eyJ0eXAi...",
            ...     "entities": ["sensor.temperature", "light.living_room"]
            ... })
            >>> success
            True
        """
        ...
