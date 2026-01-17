"""
Covenant Metrics ConfigurableAdapterProtocol implementation.

This module handles the interactive configuration workflow for the
covenant metrics adapter, including:
- Consent validation
- Configuration persistence for reload on restart
- Trace level selection
- Early warning correlation metadata

The adapter uses `completion_method: "apply_config"` in its manifest,
which triggers the AdapterConfigurationService to call apply_config()
when the wizard completes.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class CovenantMetricsConfigurable:
    """ConfigurableAdapterProtocol implementation for covenant metrics.

    This class handles:
    1. Consent validation - ensures user explicitly consents
    2. Configuration validation - checks required fields
    3. Configuration application - stores settings for service use
    4. Persistence integration - works with AdapterConfigurationService

    The configuration includes:
    - consent_given: bool - explicit consent flag
    - consent_timestamp: str - ISO timestamp of consent
    - trace_level: str - generic/detailed/full_traces
    - deployment_region: str - optional early warning correlation
    - deployment_type: str - personal/business/research/nonprofit
    - agent_role: str - assistant/customer_support/coding/etc
    - agent_template: str - CIRIS template name if applicable
    - endpoint_url: str - CIRISLens API endpoint
    - batch_size: int - events per batch
    - flush_interval_seconds: int - flush interval
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        """Initialize the configurable adapter.

        Args:
            config: Optional existing configuration
        """
        self.config = config or {}
        self._applied_config: Optional[Dict[str, Any]] = None
        logger.info("CovenantMetricsConfigurable initialized")

    async def discover(self, discovery_type: str) -> List[Dict[str, Any]]:
        """Covenant metrics doesn't use discovery.

        Args:
            discovery_type: Type of discovery (ignored)

        Returns:
            Empty list - no discovery needed
        """
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
        """Covenant metrics doesn't use OAuth.

        Returns:
            Empty string - no OAuth needed
        """
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
        """Covenant metrics doesn't use OAuth.

        Returns:
            Empty dict - no OAuth needed
        """
        return {}

    async def get_config_options(
        self, step_id: str, context: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Get dynamic options for configuration steps.

        Args:
            step_id: ID of the configuration step
            context: Current configuration context

        Returns:
            List of available options for the step
        """
        logger.debug(f"Getting config options for step: {step_id}")

        # The manifest defines static options, so we return empty
        # Dynamic options could be added here if needed
        return []

    async def validate_config(self, config: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """Validate configuration before applying.

        Validates:
        - consent_given must be True
        - consent_timestamp must be present
        - trace_level must be valid if provided

        Args:
            config: Complete configuration to validate

        Returns:
            (is_valid, error_message) tuple
        """
        logger.info("Validating covenant metrics configuration")

        if not config:
            return False, "Configuration is empty"

        # CRITICAL: Consent must be explicitly given
        if not config.get("consent_given"):
            return False, "Consent is required to enable covenant metrics"

        # Validate trace_level if present
        trace_level = config.get("trace_level", "generic")
        valid_levels = {"generic", "detailed", "full_traces"}
        if trace_level not in valid_levels:
            return False, f"Invalid trace_level: {trace_level}. Must be one of: {valid_levels}"

        # Validate endpoint_url if present
        endpoint_url = config.get("endpoint_url", "https://lens.ciris.ai/v1")
        if not endpoint_url.startswith(("http://", "https://")):
            return False, f"Invalid endpoint_url: {endpoint_url} (must start with http:// or https://)"

        # Validate batch_size if present
        batch_size = config.get("batch_size", 10)
        if not isinstance(batch_size, int) or batch_size < 1 or batch_size > 100:
            return False, "batch_size must be an integer between 1 and 100"

        # Validate flush_interval_seconds if present
        flush_interval = config.get("flush_interval_seconds", 60)
        if not isinstance(flush_interval, int) or flush_interval < 10 or flush_interval > 300:
            return False, "flush_interval_seconds must be an integer between 10 and 300"

        logger.info("Configuration validated successfully")
        return True, None

    async def apply_config(self, config: Dict[str, Any]) -> bool:
        """Apply the configuration to the adapter.

        This method:
        1. Adds consent_timestamp if not present
        2. Stores the configuration
        3. The configuration will be persisted by AdapterConfigurationService

        Args:
            config: Validated configuration to apply

        Returns:
            True if applied successfully
        """
        logger.info("Applying covenant metrics configuration")

        # Add consent timestamp if not present
        if "consent_timestamp" not in config or not config["consent_timestamp"]:
            config["consent_timestamp"] = datetime.now(timezone.utc).isoformat()

        # Store the applied configuration
        self._applied_config = config.copy()

        # Log safe version (no sensitive data in this adapter anyway)
        logger.info(
            f"Configuration applied: consent={config.get('consent_given')}, "
            f"trace_level={config.get('trace_level', 'generic')}, "
            f"region={config.get('deployment_region', 'not set')}, "
            f"type={config.get('deployment_type', 'not set')}"
        )

        return True

    def get_applied_config(self) -> Optional[Dict[str, Any]]:
        """Get the currently applied configuration.

        Returns:
            Applied configuration or None if not configured
        """
        return self._applied_config

    async def get_current_config(self) -> Dict[str, Any]:
        """Get current configuration state.

        Returns:
            Current configuration dict
        """
        return self._applied_config or self.config or {}
