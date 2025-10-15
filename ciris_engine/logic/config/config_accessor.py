"""
Unified Configuration Access with Graph + Bootstrap Fallback.

Provides a consistent interface for services to access configuration,
whether from the graph or bootstrap phase.
"""

import logging
from pathlib import Path
from typing import Any, Dict, Optional

from ciris_engine.protocols.services.graph.config import GraphConfigServiceProtocol
from ciris_engine.schemas.config.essential import EssentialConfig
from ciris_engine.schemas.types import ConfigDict

logger = logging.getLogger(__name__)


class ConfigAccessor:
    """
    Unified config access with graph + fallback.

    Services use this instead of direct config objects, enabling:
    - Runtime config updates without restart
    - Graceful fallback during bootstrap
    - Type-safe access patterns
    """

    def __init__(self, graph_config: Optional[GraphConfigServiceProtocol], bootstrap_config: EssentialConfig):
        """
        Initialize config accessor.

        Args:
            graph_config: GraphConfigService (may be None during bootstrap)
            bootstrap_config: Essential config loaded at startup
        """
        self.graph = graph_config
        self.bootstrap = bootstrap_config
        self._graph_available = graph_config is not None

    def set_graph_service(self, graph_config: GraphConfigServiceProtocol) -> None:
        """Set graph service after it becomes available."""
        self.graph = graph_config
        self._graph_available = True
        logger.info("GraphConfigService now available for configuration")

    async def get(self, key: str, default: Any = None) -> Any:
        """
        Get configuration value.

        Args:
            key: Dot-separated config key (e.g., "database.main_db")
            default: Default value if not found

        Returns:
            Configuration value or default
        """
        # Try graph first if available
        if self._graph_available and self.graph:
            try:
                node = await self.graph.get_config(key)
                if node and node.value:
                    # Handle ConfigValue wrapper
                    if hasattr(node.value, "string_value"):
                        # It's a ConfigValue object
                        if node.value.string_value is not None:
                            return node.value.string_value
                        elif node.value.int_value is not None:
                            return node.value.int_value
                        elif node.value.float_value is not None:
                            return node.value.float_value
                        elif node.value.bool_value is not None:
                            return node.value.bool_value
                        elif node.value.list_value is not None:
                            return node.value.list_value
                        elif node.value.dict_value is not None:
                            return node.value.dict_value
                    else:
                        # Direct value
                        return node.value
            except Exception as e:
                logger.warning(f"Failed to get config '{key}' from graph: {e}")

        # Fall back to bootstrap config
        return self._get_from_bootstrap(key, default)

    def _get_from_bootstrap(self, key: str, default: Any = None) -> Any:
        """Get value from bootstrap config."""
        parts = key.split(".")
        value = self.bootstrap

        try:
            for part in parts:
                if hasattr(value, part):
                    value = getattr(value, part)
                elif hasattr(value, "__getitem__"):
                    try:
                        value = value[part]
                    except (KeyError, TypeError):
                        return default
                else:
                    return default

            # Convert Path objects to strings for compatibility
            if isinstance(value, Path):
                return str(value)

            return value
        except Exception as e:
            logger.debug(f"Failed to get '{key}' from bootstrap: {e}")
            return default

    async def get_int(self, key: str, default: int = 0) -> int:
        """Get integer configuration value."""
        value = await self.get(key, default)
        try:
            return int(value)
        except (TypeError, ValueError):
            logger.warning(f"Config value '{key}' is not a valid integer: {value}")
            return default

    async def get_float(self, key: str, default: float = 0.0) -> float:
        """Get float configuration value."""
        value = await self.get(key, default)
        try:
            return float(value)
        except (TypeError, ValueError):
            logger.warning(f"Config value '{key}' is not a valid float: {value}")
            return default

    async def get_bool(self, key: str, default: bool = False) -> bool:
        """Get boolean configuration value."""
        value = await self.get(key, default)
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.lower() in ("true", "1", "yes", "on")
        return bool(value)

    async def get_str(self, key: str, default: str = "") -> str:
        """Get string configuration value."""
        value = await self.get(key, default)
        return str(value) if value is not None else default

    async def get_path(self, key: str, default: Optional[Path] = None) -> Path:
        """Get Path configuration value."""
        value = await self.get(key, default)
        if value is None:
            return default or Path()
        if isinstance(value, Path):
            return value
        return Path(str(value))

    async def exists(self, key: str) -> bool:
        """Check if configuration key exists."""
        value = await self.get(key, sentinel := object())
        return value is not sentinel

    async def get_section(self, prefix: str) -> ConfigDict:
        """
        Get all config values under a prefix.

        Args:
            prefix: Key prefix (e.g., "database")

        Returns:
            Dict of config values under that prefix
        """
        if self._graph_available and self.graph:
            try:
                configs = await self.graph.list_configs(prefix=prefix)
                return configs
            except Exception as e:
                logger.warning(f"Failed to get config section '{prefix}' from graph: {e}")

        # Fall back to bootstrap
        return self._get_section_from_bootstrap(prefix)

    def _get_section_from_bootstrap(self, prefix: str) -> ConfigDict:
        """Get config section from bootstrap config."""
        parts = prefix.split(".")
        value = self.bootstrap

        try:
            for part in parts:
                if hasattr(value, part):
                    value = getattr(value, part)
                else:
                    return {}

            # Convert to dict if it's a Pydantic model
            if hasattr(value, "model_dump"):
                return value.model_dump()
            elif hasattr(value, "dict"):
                return value.dict()
            elif hasattr(value, "__getitem__") and hasattr(value, "keys"):
                return dict(value)
            else:
                return {}
        except Exception as e:
            logger.debug(f"Failed to get section '{prefix}' from bootstrap: {e}")
            return {}
