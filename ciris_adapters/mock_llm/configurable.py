"""
Mock LLM ConfigurableAdapterProtocol implementation.

Provides minimal interactive configuration workflow for Mock LLM adapter.
This is a testing adapter, so configuration is optional and simple.

Configuration options:
1. Response delay - Simulate API latency (optional)
2. Response mode - Deterministic, random, or echo (optional)
3. Failure simulation - Enable random failures for testing (optional)
"""

import logging
import os
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class MockLLMConfigurableAdapter:
    """Mock LLM configurable adapter with minimal configuration.

    Implements ConfigurableAdapterProtocol for Mock LLM with a simple
    configuration workflow. Since this is a testing adapter, all options
    are optional and have sensible defaults.

    Configuration workflow:
        1. Configure response delay (optional)
        2. Select response mode (optional)
        3. Configure failure simulation (optional)
        4. Confirm configuration
    """

    # Available response modes
    RESPONSE_MODES = {
        "deterministic": {
            "label": "Deterministic",
            "description": "Consistent responses based on input patterns",
            "default": True,
        },
        "random": {
            "label": "Random",
            "description": "Randomized responses for variety testing",
            "default": False,
        },
        "echo": {
            "label": "Echo",
            "description": "Echo user input back (minimal processing)",
            "default": False,
        },
    }

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        """Initialize the Mock LLM configurable adapter.

        Args:
            config: Optional existing configuration
        """
        self.config = config or {}
        self._applied_config: Optional[Dict[str, Any]] = None

        logger.info("MockLLMConfigurableAdapter initialized")

    async def discover(self, discovery_type: str) -> List[Dict[str, Any]]:
        """Mock LLM doesn't require discovery.

        Args:
            discovery_type: Type of discovery to perform (unused)

        Returns:
            Empty list (no discovery needed)
        """
        logger.info("Mock LLM discovery called (no-op)")
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
        """Mock LLM doesn't use OAuth.

        Args:
            base_url: Base URL (unused)
            state: State parameter (unused)
            code_challenge: PKCE code challenge (unused)
            callback_base_url: Callback base URL (unused)
            redirect_uri: Redirect URI (unused)
            platform: Platform hint (unused)

        Returns:
            Empty string (OAuth not supported)
        """
        logger.info("Mock LLM OAuth URL requested (not supported)")
        return ""

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
        """Mock LLM doesn't use OAuth.

        Args:
            code: Authorization code (unused)
            state: State parameter (unused)
            base_url: Base URL (unused)
            code_verifier: PKCE verifier (unused)
            callback_base_url: Callback base URL (unused)
            redirect_uri: Redirect URI (unused)
            platform: Platform hint (unused)

        Returns:
            Empty dict (OAuth not supported)
        """
        logger.info("Mock LLM OAuth callback called (not supported)")
        return {}

    async def get_config_options(self, step_id: str, context: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Get options for a selection step.

        Args:
            step_id: ID of the configuration step
            context: Current configuration context

        Returns:
            List of available options
        """
        logger.info(f"Getting config options for step: {step_id}")

        if step_id == "select_mode":
            # Return available response modes
            return [
                {
                    "id": mode_id,
                    "label": mode["label"],
                    "description": mode["description"],
                    "metadata": {"default": mode["default"]},
                }
                for mode_id, mode in self.RESPONSE_MODES.items()
            ]

        return []

    async def validate_config(self, config: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """Validate Mock LLM configuration.

        Performs basic validation:
        - Response delay must be non-negative
        - Failure rate must be between 0.0 and 1.0
        - Response mode must be valid

        Args:
            config: Complete configuration to validate

        Returns:
            (is_valid, error_message) tuple
        """
        logger.info("Validating Mock LLM configuration")

        if not config:
            # Empty config is valid - use defaults
            return True, None

        # Validate response delay if present
        delay_ms = config.get("delay_ms")
        if delay_ms is not None:
            if not isinstance(delay_ms, (int, float)):
                return False, "delay_ms must be a number"
            if delay_ms < 0:
                return False, "delay_ms must be non-negative"
            if delay_ms > 60000:
                return False, "delay_ms must be <= 60000 (1 minute max)"

        # Validate failure rate if present
        failure_rate = config.get("failure_rate")
        if failure_rate is not None:
            if not isinstance(failure_rate, (int, float)):
                return False, "failure_rate must be a number"
            if failure_rate < 0.0 or failure_rate > 1.0:
                return False, "failure_rate must be between 0.0 and 1.0"

        # Validate response mode if present
        mode = config.get("response_mode")
        if mode is not None:
            if mode not in self.RESPONSE_MODES:
                valid_modes = ", ".join(self.RESPONSE_MODES.keys())
                return False, f"Invalid response_mode: {mode}. Valid modes: {valid_modes}"

        logger.info("Mock LLM configuration validated successfully")
        return True, None

    async def apply_config(self, config: Dict[str, Any]) -> bool:
        """Apply the configuration.

        Stores configuration and sets up environment for the service.

        Args:
            config: Validated configuration to apply

        Returns:
            True if applied successfully
        """
        logger.info("Applying Mock LLM configuration")

        self._applied_config = config.copy()

        # Set environment variables for the Mock LLM service
        # These match the configuration schema in manifest.json
        if "delay_ms" in config:
            os.environ["MOCK_LLM_DELAY_MS"] = str(config["delay_ms"])
        if "failure_rate" in config:
            os.environ["MOCK_LLM_FAILURE_RATE"] = str(config["failure_rate"])
        if "response_mode" in config:
            os.environ["MOCK_LLM_RESPONSE_MODE"] = config["response_mode"]

        # Log sanitized config
        logger.info(f"Mock LLM configuration applied: {config}")

        return True

    def get_applied_config(self) -> Optional[Dict[str, Any]]:
        """Get the currently applied configuration.

        Returns:
            Applied configuration or None if not configured
        """
        return self._applied_config
