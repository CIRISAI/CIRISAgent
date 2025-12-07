"""
MCP Client ConfigurableAdapterProtocol implementation.

Provides interactive configuration workflow for MCP server connections:
1. Transport Selection - Choose connection type (stdio, http, websocket)
2. Server Configuration - Enter server details (URL, command, etc.)
3. Security Settings - Configure security options
4. Bus Bindings - Select which buses to bind to
5. Confirm - Review and apply configuration

This adapter connects CIRIS to external MCP servers, providing tool,
communication, and wise authority services.
"""

import logging
import os
from typing import Any, Dict, List, Optional, Tuple

from .config import MCPBusBinding, MCPBusType, MCPServerConfig, MCPTransportType

logger = logging.getLogger(__name__)


class MCPClientConfigurableAdapter:
    """MCP Client configurable adapter.

    Implements ConfigurableAdapterProtocol for MCP server configuration.

    Configuration Flow:
    1. Select transport type (stdio, sse, streamable_http, websocket)
    2. Enter server-specific details based on transport
    3. Configure security settings
    4. Select bus bindings (tool, wise, communication)
    5. Confirm and apply

    Usage via API:
        1. POST /adapters/mcp_client/configure/start
        2. POST /adapters/configure/{session_id}/step (select_transport)
        3. POST /adapters/configure/{session_id}/step (server_config)
        4. POST /adapters/configure/{session_id}/step (security_config)
        5. POST /adapters/configure/{session_id}/step (bus_bindings)
        6. POST /adapters/configure/{session_id}/complete
    """

    # Available transport types
    TRANSPORT_TYPES = {
        "stdio": {
            "label": "Standard I/O (Local Process)",
            "description": "Run MCP server as a local process using stdin/stdout",
            "requires": ["command"],
        },
        "sse": {
            "label": "Server-Sent Events (HTTP)",
            "description": "Connect to MCP server via HTTP Server-Sent Events",
            "requires": ["url"],
        },
        "streamable_http": {
            "label": "Streamable HTTP",
            "description": "Connect to MCP server via streamable HTTP transport",
            "requires": ["url"],
        },
        "websocket": {
            "label": "WebSocket",
            "description": "Connect to MCP server via WebSocket (coming soon)",
            "requires": ["url"],
        },
    }

    # Available bus types
    BUS_TYPES = {
        "tool": {
            "label": "Tool Bus",
            "description": "Execute MCP tools via CIRIS ToolBus",
            "default": True,
        },
        "wise": {
            "label": "Wise Authority Bus",
            "description": "Use MCP prompts for guidance via WiseBus",
            "default": False,
        },
        "communication": {
            "label": "Communication Bus",
            "description": "Access MCP resources as messages via CommunicationBus",
            "default": False,
        },
    }

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        """Initialize the MCP configurable adapter.

        Args:
            config: Optional existing configuration
        """
        self.config = config or {}
        self._applied_config: Optional[Dict[str, Any]] = None

        logger.info("MCPClientConfigurableAdapter initialized")

    def get_config_schema(self) -> Dict[str, Any]:
        """Get the interactive configuration schema.

        Returns:
            Configuration schema from manifest
        """
        return {
            "required": False,
            "workflow_type": "step_by_step",
            "steps": [
                {
                    "step_id": "select_transport",
                    "step_type": "select",
                    "title": "Select Transport Type",
                    "description": "Choose how to connect to the MCP server",
                    "field_name": "transport",
                    "required": True,
                },
                {
                    "step_id": "server_config",
                    "step_type": "input",
                    "title": "Configure Server Connection",
                    "description": "Enter connection details for the MCP server",
                    "fields": [],  # Dynamic based on transport
                    "depends_on": ["select_transport"],
                },
                {
                    "step_id": "security_config",
                    "step_type": "input",
                    "title": "Security Settings (Optional)",
                    "description": "Configure security and rate limiting",
                    "optional": True,
                    "fields": [
                        {
                            "name": "max_calls_per_minute",
                            "type": "integer",
                            "label": "Max Calls Per Minute",
                            "default": 60,
                            "required": False,
                        },
                        {
                            "name": "max_concurrent_calls",
                            "type": "integer",
                            "label": "Max Concurrent Calls",
                            "default": 5,
                            "required": False,
                        },
                    ],
                },
                {
                    "step_id": "bus_bindings",
                    "step_type": "select",
                    "title": "Select Bus Bindings",
                    "description": "Choose which CIRIS buses to bind this server to",
                    "field_name": "enabled_buses",
                    "multiple": True,
                    "required": True,
                },
                {
                    "step_id": "confirm",
                    "step_type": "confirm",
                    "title": "Confirm Configuration",
                    "description": "Review and apply your MCP server configuration",
                },
            ],
            "completion_method": "apply_config",
        }

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
            # Return available transport types
            return [
                {
                    "id": transport_id,
                    "label": transport["label"],
                    "description": transport["description"],
                    "metadata": {"requires": transport["requires"]},
                }
                for transport_id, transport in self.TRANSPORT_TYPES.items()
            ]

        elif step_id == "bus_bindings":
            # Return available bus types
            return [
                {
                    "id": bus_id,
                    "label": bus["label"],
                    "description": bus["description"],
                    "metadata": {"default": bus["default"]},
                }
                for bus_id, bus in self.BUS_TYPES.items()
            ]

        elif step_id == "server_config":
            # Return dynamic fields based on selected transport
            transport = context.get("transport")
            if not transport:
                return []

            # Common fields
            fields = [
                {
                    "name": "server_id",
                    "type": "text",
                    "label": "Server ID",
                    "description": "Unique identifier for this server",
                    "required": True,
                },
                {
                    "name": "name",
                    "type": "text",
                    "label": "Server Name",
                    "description": "Human-readable name",
                    "required": True,
                },
                {
                    "name": "description",
                    "type": "text",
                    "label": "Description",
                    "description": "What this server provides",
                    "required": False,
                },
            ]

            # Transport-specific fields
            if transport == "stdio":
                fields.extend(
                    [
                        {
                            "name": "command",
                            "type": "text",
                            "label": "Command",
                            "description": "Command to start the server (e.g., 'npx', 'python')",
                            "required": True,
                        },
                        {
                            "name": "args",
                            "type": "text",
                            "label": "Arguments",
                            "description": "Comma-separated arguments (e.g., '-y,@modelcontextprotocol/server-weather')",
                            "required": False,
                        },
                    ]
                )
            else:
                # HTTP-based transports
                fields.append(
                    {
                        "name": "url",
                        "type": "text",
                        "label": "Server URL",
                        "description": f"URL of the MCP server (e.g., https://mcp.example.com)",
                        "required": True,
                    }
                )

            return fields

        return []

    async def validate_config(self, config: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """Validate MCP configuration before applying.

        Performs:
        - Required field validation
        - Transport-specific validation
        - Bus binding validation

        Args:
            config: Complete configuration to validate

        Returns:
            (is_valid, error_message) tuple
        """
        logger.info("Validating MCP configuration")

        if not config:
            return False, "Configuration is empty"

        # Check required fields
        transport = config.get("transport")
        if not transport:
            return False, "transport is required"

        if transport not in self.TRANSPORT_TYPES:
            return False, f"Invalid transport: {transport}"

        server_id = config.get("server_id")
        if not server_id:
            return False, "server_id is required"

        name = config.get("name")
        if not name:
            return False, "name is required"

        # Validate transport-specific requirements
        if transport == "stdio":
            command = config.get("command")
            if not command:
                return False, "command is required for stdio transport"
        else:
            url = config.get("url")
            if not url:
                return False, "url is required for HTTP-based transports"

            if not url.startswith(("http://", "https://")):
                return False, f"Invalid URL: {url} (must start with http:// or https://)"

        # Validate bus bindings
        enabled_buses = config.get("enabled_buses", [])
        if not enabled_buses:
            return False, "At least one bus binding is required"

        valid_buses = set(self.BUS_TYPES.keys())
        invalid_buses = set(enabled_buses) - valid_buses
        if invalid_buses:
            return False, f"Invalid bus bindings: {invalid_buses}"

        logger.info("MCP configuration validated successfully")
        return True, None

    async def apply_config(self, config: Dict[str, Any]) -> bool:
        """Apply the configuration.

        Stores configuration and sets up environment for the MCP adapter.

        Args:
            config: Validated configuration to apply

        Returns:
            True if applied successfully
        """
        logger.info("Applying MCP configuration")

        self._applied_config = config.copy()

        # Build server configuration
        server_id = config["server_id"]
        transport_str = config["transport"]

        # Parse transport type
        try:
            transport = MCPTransportType(transport_str)
        except ValueError:
            logger.error(f"Invalid transport type: {transport_str}")
            return False

        # Parse bus bindings
        enabled_buses = config.get("enabled_buses", ["tool"])
        bus_bindings = []
        for bus_str in enabled_buses:
            try:
                bus_type = MCPBusType(bus_str)
                bus_bindings.append(MCPBusBinding(bus_type=bus_type, enabled=True))
            except ValueError:
                logger.warning(f"Invalid bus type: {bus_str}, skipping")

        # Build server config based on transport
        server_config_dict = {
            "server_id": server_id,
            "name": config["name"],
            "description": config.get("description", ""),
            "transport": transport.value,
            "bus_bindings": [b.model_dump() for b in bus_bindings],
            "enabled": True,
            "auto_start": True,
            "source": "interactive_config",
        }

        if transport == MCPTransportType.STDIO:
            server_config_dict["command"] = config["command"]
            args_str = config.get("args", "")
            server_config_dict["args"] = [a.strip() for a in args_str.split(",") if a.strip()]
        else:
            server_config_dict["url"] = config["url"]

        # Add security settings if provided
        if config.get("max_calls_per_minute"):
            server_config_dict.setdefault("security", {})
            server_config_dict["security"]["max_calls_per_minute"] = config["max_calls_per_minute"]
        if config.get("max_concurrent_calls"):
            server_config_dict.setdefault("security", {})
            server_config_dict["security"]["max_concurrent_calls"] = config["max_concurrent_calls"]

        # Set environment variable with server configuration
        # The MCP adapter will pick this up on next start
        env_prefix = f"MCP_SERVER_{server_id.upper()}_"
        os.environ[f"{env_prefix}NAME"] = config["name"]
        os.environ[f"{env_prefix}TRANSPORT"] = transport.value

        if transport == MCPTransportType.STDIO:
            os.environ[f"{env_prefix}COMMAND"] = config["command"]
            if server_config_dict.get("args"):
                os.environ[f"{env_prefix}ARGS"] = ",".join(server_config_dict["args"])
        else:
            os.environ[f"{env_prefix}URL"] = config["url"]

        # Set bus bindings
        os.environ[f"{env_prefix}BUSES"] = ",".join(enabled_buses)

        # Log sanitized config
        safe_config = {k: ("***" if "token" in k.lower() or "password" in k.lower() else v) for k, v in config.items()}
        logger.info(f"MCP configuration applied: {safe_config}")

        return True

    def get_applied_config(self) -> Optional[Dict[str, Any]]:
        """Get the currently applied configuration.

        Returns:
            Applied configuration or None if not configured
        """
        return self._applied_config
