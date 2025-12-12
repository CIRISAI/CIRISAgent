"""
MCP Server ConfigurableAdapterProtocol implementation.

Provides interactive configuration workflow for MCP Server:
1. Transport selection - Choose stdio, SSE, or HTTP
2. Server settings - Configure host, port, and server identity
3. Security settings - Configure authentication and access control
4. Exposure settings - Choose which CIRIS capabilities to expose
5. Confirm - Review and apply configuration
"""

import logging
import os
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class MCPServerConfigurableAdapter:
    """MCP Server configurable adapter.

    Implements ConfigurableAdapterProtocol for MCP Server configuration.

    Workflow:
    1. Select transport type (stdio, sse, http)
    2. Configure server settings (host, port, name)
    3. Configure security (auth, rate limiting)
    4. Select which CIRIS features to expose
    5. Confirm and apply configuration

    Usage via API:
        1. POST /adapters/mcp_server/configure/start
        2. POST /adapters/configure/{session_id}/step (transport)
        3. POST /adapters/configure/{session_id}/step (server settings)
        4. POST /adapters/configure/{session_id}/step (security)
        5. POST /adapters/configure/{session_id}/step (exposure)
        6. POST /adapters/configure/{session_id}/complete
    """

    # Transport types
    TRANSPORT_TYPES = {
        "stdio": {
            "label": "Standard I/O (stdio)",
            "description": "For Claude Desktop and local CLI tools - communicates via stdin/stdout",
            "default": True,
            "metadata": {
                "use_case": "Desktop integration",
                "requires_network": False,
            },
        },
        "sse": {
            "label": "Server-Sent Events (SSE)",
            "description": "HTTP-based streaming for web clients",
            "default": False,
            "metadata": {
                "use_case": "Web applications",
                "requires_network": True,
            },
        },
        "http": {
            "label": "HTTP",
            "description": "Standard HTTP for maximum compatibility",
            "default": False,
            "metadata": {
                "use_case": "Wide compatibility",
                "requires_network": True,
            },
        },
    }

    # Authentication methods
    AUTH_METHODS = {
        "none": {
            "label": "No Authentication",
            "description": "No authentication required (local only - USE WITH CAUTION)",
            "default": True,
            "metadata": {
                "security_level": "low",
                "recommended_for": "local_development",
            },
        },
        "api_key": {
            "label": "API Key",
            "description": "Simple API key authentication",
            "default": False,
            "metadata": {
                "security_level": "medium",
                "recommended_for": "production",
            },
        },
    }

    # Exposure options
    EXPOSURE_OPTIONS = {
        "tools": {
            "label": "CIRIS Tools",
            "description": "Expose CIRIS tools for memory search, task submission, status checks",
            "default": True,
        },
        "resources": {
            "label": "CIRIS Resources",
            "description": "Expose agent state and data as MCP resources",
            "default": True,
        },
        "prompts": {
            "label": "CIRIS Prompts",
            "description": "Expose guidance prompts from Wise Authority",
            "default": True,
        },
    }

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        """Initialize the MCP Server configurable adapter.

        Args:
            config: Optional existing configuration
        """
        self.config = config or {}
        self._applied_config: Optional[Dict[str, Any]] = None
        logger.info("MCPServerConfigurableAdapter initialized")

    async def discover(self, discovery_type: str) -> List[Dict[str, Any]]:
        """Run discovery (not applicable for MCP Server).

        MCP Server is a passive service that doesn't discover external services.
        This method returns an empty list to satisfy the ConfigurableAdapterProtocol.

        Args:
            discovery_type: Type of discovery (unused)

        Returns:
            Empty list (no discovery needed)
        """
        logger.debug(f"Discovery called with type: {discovery_type} (not applicable for MCP Server)")
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
        """Generate OAuth URL (not applicable for MCP Server).

        MCP Server doesn't use OAuth for client authentication.
        This method raises NotImplementedError to satisfy the protocol.

        Args:
            base_url: Base URL (unused)
            state: State parameter (unused)
            code_challenge: PKCE code challenge (unused)
            callback_base_url: Optional callback URL (unused)
            redirect_uri: Redirect URI (unused)
            platform: Platform hint (unused)

        Returns:
            Empty string

        Raises:
            NotImplementedError: OAuth not supported for MCP Server
        """
        logger.warning("OAuth not supported for MCP Server adapter")
        raise NotImplementedError("MCP Server does not use OAuth authentication")

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
        """Handle OAuth callback (not applicable for MCP Server).

        MCP Server doesn't use OAuth for client authentication.
        This method raises NotImplementedError to satisfy the protocol.

        Args:
            code: Authorization code (unused)
            state: State parameter (unused)
            base_url: Base URL (unused)
            code_verifier: PKCE code verifier (unused)
            callback_base_url: Optional callback URL (unused)
            redirect_uri: Redirect URI (unused)
            platform: Platform hint (unused)

        Returns:
            Empty dict

        Raises:
            NotImplementedError: OAuth not supported for MCP Server
        """
        logger.warning("OAuth callback not supported for MCP Server adapter")
        raise NotImplementedError("MCP Server does not use OAuth authentication")

    async def get_config_options(self, step_id: str, context: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Get options for a selection step.

        Args:
            step_id: ID of the configuration step
            context: Current configuration context

        Returns:
            List of available options
        """
        logger.info(f"Getting config options for step: {step_id}")

        if step_id == "select_transport":
            # Return transport type options
            return [
                {
                    "id": transport_id,
                    "label": transport["label"],
                    "description": transport["description"],
                    "metadata": {
                        **transport["metadata"],
                        "default": transport["default"],
                    },
                }
                for transport_id, transport in self.TRANSPORT_TYPES.items()
            ]

        elif step_id == "select_auth":
            # Return authentication method options
            return [
                {
                    "id": auth_id,
                    "label": auth["label"],
                    "description": auth["description"],
                    "metadata": {
                        **auth["metadata"],
                        "default": auth["default"],
                    },
                }
                for auth_id, auth in self.AUTH_METHODS.items()
            ]

        elif step_id == "select_exposure":
            # Return exposure options
            return [
                {
                    "id": exposure_id,
                    "label": exposure["label"],
                    "description": exposure["description"],
                    "metadata": {"default": exposure["default"]},
                }
                for exposure_id, exposure in self.EXPOSURE_OPTIONS.items()
            ]

        return []

    async def validate_config(self, config: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """Validate MCP Server configuration before applying.

        Performs:
        - Required field validation
        - Port range validation
        - Transport/host compatibility checks

        Args:
            config: Complete configuration to validate

        Returns:
            (is_valid, error_message) tuple
        """
        logger.info("Validating MCP Server configuration")

        if not config:
            return False, "Configuration is empty"

        # Check required fields
        transport_type = config.get("transport_type")
        if not transport_type:
            return False, "transport_type is required"

        if transport_type not in self.TRANSPORT_TYPES:
            return False, f"Invalid transport_type: {transport_type}"

        # Validate network transport settings
        if transport_type in ("sse", "http"):
            host = config.get("host")
            port = config.get("port")

            if not host:
                return False, "host is required for network transports"

            if not port:
                return False, "port is required for network transports"

            try:
                port_num = int(port)
                if not (1 <= port_num <= 65535):
                    return False, f"Invalid port: {port} (must be 1-65535)"
            except (ValueError, TypeError):
                return False, f"Invalid port: {port} (must be a number)"

        # Validate auth method
        auth_method = config.get("auth_method", "none")
        if auth_method not in self.AUTH_METHODS:
            return False, f"Invalid auth_method: {auth_method}"

        # Validate API keys if using API key auth
        if auth_method == "api_key":
            api_keys = config.get("api_keys", [])
            if not api_keys:
                return False, "api_keys are required when using API key authentication"

        # Validate exposure settings
        exposure = config.get("exposure", {})
        if not any(
            [
                exposure.get("expose_tools", False),
                exposure.get("expose_resources", False),
                exposure.get("expose_prompts", False),
            ]
        ):
            return False, "At least one exposure option (tools, resources, prompts) must be enabled"

        logger.info("MCP Server configuration validated successfully")
        return True, None

    async def apply_config(self, config: Dict[str, Any]) -> bool:
        """Apply the configuration.

        Stores configuration and sets up environment for the MCP Server.

        Args:
            config: Validated configuration to apply

        Returns:
            True if applied successfully
        """
        logger.info("Applying MCP Server configuration")

        self._applied_config = config.copy()

        # Set environment variables for the MCP Server
        transport_type = config.get("transport_type", "stdio")
        os.environ["MCP_SERVER_TRANSPORT"] = transport_type

        # Server identification
        if config.get("server_id"):
            os.environ["MCP_SERVER_ID"] = config["server_id"]
        if config.get("server_name"):
            os.environ["MCP_SERVER_NAME"] = config["server_name"]

        # Network settings (for http/sse transports)
        if transport_type in ("sse", "http"):
            if config.get("host"):
                os.environ["MCP_SERVER_HOST"] = config["host"]
            if config.get("port"):
                os.environ["MCP_SERVER_PORT"] = str(config["port"])

        # Security settings
        auth_method = config.get("auth_method", "none")
        if auth_method != "none":
            os.environ["MCP_SERVER_REQUIRE_AUTH"] = "true"

            if auth_method == "api_key":
                api_keys = config.get("api_keys", [])
                if api_keys:
                    os.environ["MCP_SERVER_API_KEYS"] = ",".join(api_keys)

        # Exposure settings
        exposure = config.get("exposure", {})
        if "expose_tools" in exposure:
            os.environ["MCP_SERVER_EXPOSE_TOOLS"] = str(exposure["expose_tools"]).lower()
        if "expose_resources" in exposure:
            os.environ["MCP_SERVER_EXPOSE_RESOURCES"] = str(exposure["expose_resources"]).lower()
        if "expose_prompts" in exposure:
            os.environ["MCP_SERVER_EXPOSE_PROMPTS"] = str(exposure["expose_prompts"]).lower()

        # Log sanitized config
        safe_config = {k: ("***" if "key" in k.lower() or "token" in k.lower() else v) for k, v in config.items()}
        logger.info(f"MCP Server configuration applied: {safe_config}")

        return True

    def get_applied_config(self) -> Optional[Dict[str, Any]]:
        """Get the currently applied configuration.

        Returns:
            Applied configuration or None if not configured
        """
        return self._applied_config


__all__ = ["MCPServerConfigurableAdapter"]
