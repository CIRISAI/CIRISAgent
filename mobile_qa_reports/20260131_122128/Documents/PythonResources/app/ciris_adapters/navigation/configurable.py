"""
Navigation ConfigurableAdapterProtocol implementation.

Provides interactive configuration workflow for Navigation integration:
1. Configure User Agent - Required by OpenStreetMap usage policy
2. Configure Rate Limiting - Optional rate limit settings
3. Confirm - Review and apply configuration

OpenStreetMap Usage Policy (per https://operations.osmfoundation.org/policies/nominatim/):
- User-Agent header is REQUIRED
- Maximum 1 request per second
- No API key required (free service)

SAFE DOMAIN: Navigation and geographic information only.
"""

import logging
import os
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class NavigationConfigurableAdapter:
    """Navigation configurable adapter.

    Implements ConfigurableAdapterProtocol for Navigation service configuration
    using OpenStreetMap's Nominatim (geocoding) and OSRM (routing) services.

    OpenStreetMap Requirements:
    - User-Agent header (email/app identifier)
    - Rate limiting (1 request/second recommended)
    - No API key or OAuth required

    Usage via API:
        1. POST /adapters/navigation/configure/start
        2. POST /adapters/configure/{session_id}/step (user_agent)
        3. POST /adapters/configure/{session_id}/step (rate_limit - optional)
        4. POST /adapters/configure/{session_id}/complete
    """

    # Default configuration values
    DEFAULT_USER_AGENT = "CIRIS/1.0 (contact@ciris.ai)"
    DEFAULT_RATE_LIMIT = 1.0  # seconds

    # Recommended contact patterns for user agent
    CONTACT_PATTERNS = [
        "email",
        "website",
        "app_name",
    ]

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        """Initialize the Navigation configurable adapter.

        Args:
            config: Optional existing configuration
        """
        self.config = config or {}
        self._applied_config: Optional[Dict[str, Any]] = None

        logger.info("NavigationConfigurableAdapter initialized")

    async def get_config_options(self, step_id: str, context: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Get options for a selection step.

        Args:
            step_id: ID of the configuration step
            context: Current configuration context

        Returns:
            List of available options
        """
        logger.info(f"Getting config options for step: {step_id}")

        if step_id == "select_rate_limit":
            # Return rate limit preset options
            return [
                {
                    "id": "conservative",
                    "label": "Conservative (2 seconds)",
                    "description": "Wait 2 seconds between requests (slowest, most respectful)",
                    "metadata": {"value": 2.0},
                },
                {
                    "id": "standard",
                    "label": "Standard (1 second)",
                    "description": "Wait 1 second between requests (OSM recommended minimum)",
                    "metadata": {"value": 1.0},
                },
                {
                    "id": "fast",
                    "label": "Fast (0.5 seconds)",
                    "description": "Wait 0.5 seconds between requests (use sparingly)",
                    "metadata": {"value": 0.5},
                },
                {
                    "id": "custom",
                    "label": "Custom",
                    "description": "Enter a custom rate limit value",
                    "metadata": {"value": None},
                },
            ]

        return []

    async def validate_config(self, config: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """Validate Navigation configuration before applying.

        Performs:
        - User agent format validation
        - Rate limit range validation

        Args:
            config: Complete configuration to validate

        Returns:
            (is_valid, error_message) tuple
        """
        logger.info("Validating Navigation configuration")

        if not config:
            return False, "Configuration is empty"

        # Check user agent
        user_agent = config.get("user_agent", "").strip()
        if not user_agent:
            return False, "user_agent is required (OpenStreetMap policy)"

        # Validate user agent format
        if len(user_agent) < 10:
            return False, "user_agent must be at least 10 characters (e.g., 'MyApp/1.0 (email@example.com)')"

        # Check if user agent contains contact information
        has_contact = (
            "@" in user_agent  # email
            or "http" in user_agent.lower()  # URL
            or "contact" in user_agent.lower()  # contact keyword
        )

        if not has_contact:
            logger.warning(
                "User agent should include contact information (email, website, etc.) " "per OpenStreetMap usage policy"
            )

        # Validate rate limit if provided
        rate_limit = config.get("rate_limit_seconds")
        if rate_limit is not None:
            try:
                rate_limit_float = float(rate_limit)
                if rate_limit_float < 0.1:
                    return False, "rate_limit_seconds must be at least 0.1 seconds"
                if rate_limit_float > 60:
                    return False, "rate_limit_seconds cannot exceed 60 seconds"
            except (ValueError, TypeError):
                return False, "rate_limit_seconds must be a valid number"

        logger.info("Navigation configuration validated successfully")
        return True, None

    async def apply_config(self, config: Dict[str, Any]) -> bool:
        """Apply the configuration.

        Stores configuration and sets up environment for the service.

        Args:
            config: Validated configuration to apply

        Returns:
            True if applied successfully
        """
        logger.info("Applying Navigation configuration")

        self._applied_config = config.copy()

        # Set environment variables for the Navigation service
        if config.get("user_agent"):
            os.environ["CIRIS_OSM_USER_AGENT"] = config["user_agent"]

        if config.get("rate_limit_seconds") is not None:
            os.environ["CIRIS_OSM_RATE_LIMIT"] = str(config["rate_limit_seconds"])

        # Log sanitized config
        logger.info(f"Navigation configuration applied: {config}")

        return True

    def get_applied_config(self) -> Optional[Dict[str, Any]]:
        """Get the currently applied configuration.

        Returns:
            Applied configuration or None if not configured
        """
        return self._applied_config

    def get_config_schema(self) -> Dict[str, Any]:
        """Get the configuration schema.

        Returns:
            Configuration schema matching manifest.json interactive_config
        """
        # This is typically read from manifest.json, but we can provide it here
        # for programmatic access
        return {
            "required": False,
            "workflow_type": "simple_config",
            "steps": [
                {
                    "step_id": "user_agent",
                    "step_type": "input",
                    "title": "Configure User Agent",
                    "description": "Enter a user agent for OpenStreetMap API requests (required by OSM policy)",
                    "field": "user_agent",
                    "required": True,
                    "placeholder": "CIRIS/1.0 (your.email@example.com)",
                    "validation": {
                        "min_length": 10,
                        "pattern": ".*",
                    },
                },
                {
                    "step_id": "rate_limit",
                    "step_type": "select",
                    "title": "Configure Rate Limiting",
                    "description": "Select how long to wait between API requests (OSM recommends 1+ seconds)",
                    "field": "rate_limit_seconds",
                    "required": False,
                    "optional": True,
                    "options_method": "get_config_options",
                },
                {
                    "step_id": "confirm",
                    "step_type": "confirm",
                    "title": "Confirm Configuration",
                    "description": "Review and apply your Navigation configuration",
                },
            ],
            "completion_method": "apply_config",
        }
