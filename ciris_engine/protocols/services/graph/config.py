"""Configuration Service Protocol."""

from abc import abstractmethod
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional, Protocol, Union

from ciris_engine.schemas.services.graph_core import GraphScope
from ciris_engine.schemas.types import ConfigValue

from ...runtime.base import GraphServiceProtocol

if TYPE_CHECKING:
    from ciris_engine.schemas.services.nodes import ConfigNode


class GraphConfigServiceProtocol(GraphServiceProtocol, Protocol):
    """Protocol for graph configuration service."""

    @abstractmethod
    async def get_config(self, key: str) -> Optional["ConfigNode"]:
        """Get configuration value."""
        ...

    @abstractmethod
    async def set_config(
        self,
        key: str,
        value: ConfigValue,
        updated_by: str,
        scope: GraphScope = GraphScope.LOCAL,
    ) -> None:
        """Set configuration value.

        Args:
            key: Configuration key
            value: Configuration value
            updated_by: Who is making the update
            scope: Graph scope (LOCAL for agent-modifiable, IDENTITY for WA-protected)
        """
        ...

    @abstractmethod
    async def list_configs(self, prefix: Optional[str] = None) -> Dict[str, ConfigValue]:
        """List all configurations with optional prefix filter."""
        ...

    @abstractmethod
    def register_config_listener(self, key_pattern: str, callback: Callable[..., Any]) -> None:
        """Register a callback for config changes matching the key pattern."""
        ...

    @abstractmethod
    def unregister_config_listener(self, key_pattern: str, callback: Callable[..., Any]) -> None:
        """Unregister a config change callback."""
        ...
