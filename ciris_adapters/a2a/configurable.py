"""
A2A ConfigurableAdapterProtocol implementation.

Provides interactive configuration workflow for A2A (Agent-to-Agent) protocol:
1. Server Configuration - Host and port settings
2. Performance Settings - Timeout configuration
3. Confirm - Review and apply configuration

The A2A adapter enables inter-agent communication using JSON-RPC 2.0 protocol,
supporting ethical benchmarking via HE-300.
"""

import logging
import os
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class A2AConfigurableAdapter:
    """A2A configurable adapter.

    Implements ConfigurableAdapterProtocol for A2A server configuration.

    Configuration Flow:
    1. Configure server host and port
    2. Configure timeout settings
    3. Confirm and apply

    Usage via API:
        1. POST /adapters/a2a/configure/start
        2. POST /adapters/configure/{session_id}/step (server_config)
        3. POST /adapters/configure/{session_id}/step (performance_config - optional)
        4. POST /adapters/configure/{session_id}/complete
    """

    # Default configuration values
    DEFAULT_HOST = "0.0.0.0"
    DEFAULT_PORT = 8100
    DEFAULT_TIMEOUT = 60

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        """Initialize the A2A configurable adapter.

        Args:
            config: Optional existing configuration
        """
        self.config = config or {}
        self._applied_config: Optional[Dict[str, Any]] = None

        logger.info("A2AConfigurableAdapter initialized")

    def get_config_schema(self) -> Dict[str, Any]:
        """Get the interactive configuration schema.

        Returns:
            Configuration schema from manifest
        """
        return {
            "required": False,
            "workflow_type": "simple_config",
            "steps": [
                {
                    "step_id": "server_config",
                    "step_type": "input",
                    "title": "Server Configuration",
                    "description": "Configure the A2A server endpoint settings",
                    "fields": [
                        {
                            "name": "host",
                            "type": "string",
                            "label": "Host Address",
                            "description": "Network interface to bind (0.0.0.0 for all interfaces)",
                            "default": self.DEFAULT_HOST,
                            "required": False,
                        },
                        {
                            "name": "port",
                            "type": "integer",
                            "label": "Port",
                            "description": "Port number for the A2A server",
                            "default": self.DEFAULT_PORT,
                            "required": False,
                        },
                    ],
                },
                {
                    "step_id": "performance_config",
                    "step_type": "input",
                    "title": "Performance Settings (Optional)",
                    "description": "Configure timeout and performance options",
                    "optional": True,
                    "fields": [
                        {
                            "name": "timeout",
                            "type": "integer",
                            "label": "Pipeline Timeout (seconds)",
                            "description": "Maximum time for processing A2A requests",
                            "default": self.DEFAULT_TIMEOUT,
                            "required": False,
                        },
                    ],
                },
                {
                    "step_id": "confirm",
                    "step_type": "confirm",
                    "title": "Confirm Configuration",
                    "description": "Review and apply your A2A server configuration",
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
        # A2A doesn't have selection steps, but include for protocol compliance
        return []

    async def validate_config(self, config: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """Validate A2A configuration before applying.

        Performs:
        - Port range validation
        - Timeout range validation
        - Host format validation

        Args:
            config: Complete configuration to validate

        Returns:
            (is_valid, error_message) tuple
        """
        logger.info("Validating A2A configuration")

        if not config:
            # Empty config is valid - use defaults
            return True, None

        # Validate host if provided
        host = config.get("host", "").strip()
        if host:
            # Basic validation - should be IP address or hostname
            if not host.replace(".", "").replace(":", "").replace("-", "").replace("_", "").isalnum() and host != "0.0.0.0":
                return False, f"Invalid host format: {host}"

        # Validate port if provided
        port = config.get("port")
        if port is not None:
            try:
                port_int = int(port)
                if port_int < 1 or port_int > 65535:
                    return False, f"Port must be between 1 and 65535, got {port_int}"
                if port_int < 1024:
                    logger.warning(f"Port {port_int} is a privileged port (< 1024), may require elevated permissions")
            except (ValueError, TypeError):
                return False, "Port must be a valid integer"

        # Validate timeout if provided
        timeout = config.get("timeout")
        if timeout is not None:
            try:
                timeout_int = int(timeout)
                if timeout_int < 1:
                    return False, "Timeout must be at least 1 second"
                if timeout_int > 3600:
                    return False, "Timeout cannot exceed 3600 seconds (1 hour)"
            except (ValueError, TypeError):
                return False, "Timeout must be a valid integer"

        logger.info("A2A configuration validated successfully")
        return True, None

    async def apply_config(self, config: Dict[str, Any]) -> bool:
        """Apply the configuration.

        Stores configuration and sets up environment for the A2A adapter.

        Args:
            config: Validated configuration to apply

        Returns:
            True if applied successfully
        """
        logger.info("Applying A2A configuration")

        self._applied_config = config.copy()

        # Set environment variables for the A2A service
        if config.get("host"):
            os.environ["CIRIS_A2A_HOST"] = str(config["host"])

        if config.get("port") is not None:
            os.environ["CIRIS_A2A_PORT"] = str(config["port"])

        if config.get("timeout") is not None:
            os.environ["CIRIS_A2A_TIMEOUT"] = str(config["timeout"])

        # Log configuration (safe - no secrets)
        logger.info(f"A2A configuration applied: host={config.get('host', self.DEFAULT_HOST)}, "
                    f"port={config.get('port', self.DEFAULT_PORT)}, "
                    f"timeout={config.get('timeout', self.DEFAULT_TIMEOUT)}")

        return True

    def get_applied_config(self) -> Optional[Dict[str, Any]]:
        """Get the currently applied configuration.

        Returns:
            Applied configuration or None if not configured
        """
        return self._applied_config
