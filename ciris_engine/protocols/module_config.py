"""
Module Configuration Protocol.

Defines the protocol for modules that support interactive configuration workflows.
"""

from abc import abstractmethod
from typing import List, Optional, Protocol, Tuple

from ciris_engine.schemas.runtime.manifest import (
    DiscoveredInstance,
    OAuthConfig,
    SelectionOption,
)


class ConfigurableModule(Protocol):
    """
    Protocol for modules that support interactive configuration.

    Modules implementing this protocol can provide multi-step configuration
    workflows including discovery, OAuth authentication, and option selection.
    """

    @abstractmethod
    async def discover(self, discovery_type: str) -> List[DiscoveredInstance]:
        """
        Run discovery and return typed instances.

        Args:
            discovery_type: Type of discovery to perform (e.g., "mdns", "network_scan")

        Returns:
            List of discovered service instances

        Raises:
            ValueError: If discovery_type is not supported
        """
        ...

    @abstractmethod
    async def get_oauth_provider_config(self) -> OAuthConfig:
        """
        Get OAuth configuration for registration with auth service.

        Returns:
            OAuth configuration including provider name, paths, and PKCE settings

        Raises:
            ValueError: If OAuth is not supported by this module
        """
        ...

    @abstractmethod
    async def handle_oauth_tokens(
        self, access_token: str, refresh_token: str, expires_in: int
    ) -> bool:
        """
        Store OAuth tokens securely.

        Args:
            access_token: OAuth access token
            refresh_token: OAuth refresh token (may be empty)
            expires_in: Token expiration time in seconds

        Returns:
            True if tokens were stored successfully

        Raises:
            ValueError: If token storage fails
        """
        ...

    @abstractmethod
    async def get_config_options(
        self, step_id: str, context: dict[str, str]
    ) -> List[SelectionOption]:
        """
        Get typed options for selection step.

        Args:
            step_id: Identifier of the configuration step
            context: Previously collected configuration values

        Returns:
            List of selection options for the user

        Raises:
            ValueError: If step_id is not recognized or context is invalid
        """
        ...

    @abstractmethod
    async def validate_config(
        self, config: dict[str, str]
    ) -> Tuple[bool, Optional[str]]:
        """
        Validate configuration before applying.

        Args:
            config: Complete configuration dictionary (string values only)

        Returns:
            Tuple of (is_valid, error_message)
            - is_valid: True if configuration is valid
            - error_message: Error description if invalid, None otherwise
        """
        ...

    @abstractmethod
    async def apply_config(self, config: dict[str, str]) -> bool:
        """
        Apply validated configuration to module.

        Args:
            config: Complete configuration dictionary (string values only)

        Returns:
            True if configuration was applied successfully

        Raises:
            ValueError: If configuration cannot be applied
        """
        ...
