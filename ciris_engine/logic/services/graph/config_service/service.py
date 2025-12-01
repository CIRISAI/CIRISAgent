"""
Graph Configuration Service for CIRIS Trinity Architecture.

All configuration is stored as memories in the graph, with full history tracking.
This replaces the old config_manager_service and agent_config_service.
"""

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Union, cast

from ciris_engine.logic.services.base_graph_service import BaseGraphService, GraphNodeConvertible
from ciris_engine.logic.services.graph.memory_service import LocalGraphMemoryService
from ciris_engine.protocols.services.graph.config import GraphConfigServiceProtocol
from ciris_engine.protocols.services.lifecycle.time import TimeServiceProtocol
from ciris_engine.schemas.runtime.enums import ServiceType
from ciris_engine.schemas.services.graph_core import GraphNode, GraphScope
from ciris_engine.schemas.services.nodes import ConfigNode, ConfigValue
from ciris_engine.schemas.services.operations import MemoryQuery
from ciris_engine.schemas.types import ConfigValue as ConfigValueType
from ciris_engine.schemas.types import JSONDict, JSONList, JSONValue

# No psutil needed - only resource_monitor uses it


logger = logging.getLogger(__name__)


class GraphConfigService(BaseGraphService, GraphConfigServiceProtocol):
    """Configuration service that stores all config as graph memories."""

    def __init__(self, graph_memory_service: LocalGraphMemoryService, time_service: TimeServiceProtocol):
        """Initialize with graph memory service."""
        # Initialize BaseGraphService without memory_bus (we'll use graph_memory_service directly)
        super().__init__(memory_bus=None, time_service=time_service)

        self.graph = graph_memory_service
        self._running = False
        self._start_time: Optional[datetime] = None
        # No process tracking here - resource_monitor handles that
        self._config_cache: Dict[str, ConfigNode] = {}  # Cache for config nodes
        self._config_listeners: Dict[str, List[Callable[..., Any]]] = {}  # key_pattern -> [callbacks]

        # Track cache metrics for v1.4.3
        self._cache_hits = 0
        self._cache_misses = 0

    async def start(self) -> None:
        """Start the service."""
        await super().start()
        self._running = True
        self._start_time = self._time_service.now() if self._time_service else datetime.now(timezone.utc)

    async def stop(self) -> None:
        """Stop the service."""
        self._running = False
        # Nothing to clean up
        await super().stop()

    async def get_metrics(self) -> Dict[str, float]:
        """
        Get all config service metrics including base, custom, and v1.4.3 specific.
        """
        # Get all base + custom metrics
        metrics = self._collect_metrics()

        # Get total config values count from graph
        config_count = 0
        try:
            # Query all config nodes to get total count
            nodes = await self.graph.search("type:config")
            config_count = len(nodes)
        except Exception:
            # Fallback to cache count if graph query fails
            config_count = len(self._config_cache)

        # Calculate uptime
        uptime_seconds = 0.0
        if self._started and self._start_time:
            uptime_delta = (self._now() - self._start_time).total_seconds()
            uptime_seconds = max(0.0, uptime_delta)  # Ensure non-negative

        # Add v1.4.3 specific metrics
        metrics.update(
            {
                "config_cache_hits": float(self._cache_hits),
                "config_cache_misses": float(self._cache_misses),
                "config_values_total": float(config_count),
                "config_uptime_seconds": uptime_seconds,
            }
        )

        return metrics

    async def store_in_graph(self, node: Union[GraphNode, GraphNodeConvertible]) -> str:
        """Store config node in graph."""
        # If it's a ConfigNode, use it directly, otherwise convert
        if isinstance(node, ConfigNode):
            graph_node = node.to_graph_node()
        elif hasattr(node, "to_graph_node"):
            graph_node = node.to_graph_node()
        else:
            # node must be a GraphNode already
            graph_node = node
        result = await self.graph.memorize(graph_node)
        # MemoryOpResult has data field, not node_id
        if result.status == "ok" and result.data:
            return result.data if isinstance(result.data, str) else str(result.data)
        return ""

    async def query_graph(self, query: MemoryQuery) -> List[GraphNode]:
        """Query config nodes from graph.

        This method is required by BaseGraphService but not used in ConfigService.
        Config queries should use _query_config_by_key() instead.
        """
        # For config service, we always query all config nodes
        # The MemoryQuery parameter is ignored as it's not applicable to config queries
        nodes = await self.graph.search("type:config")
        return nodes

    async def _query_config_by_key(self, key: str) -> List[GraphNode]:
        """Query config nodes by key."""
        # Get all config nodes
        nodes = await self.graph.search("type:config")

        # Filter by key
        filtered_nodes = []
        for node in nodes:
            try:
                # Convert to ConfigNode to check key
                config_node = ConfigNode.from_graph_node(node)
                if config_node.key == key:
                    filtered_nodes.append(node)
            except Exception as e:
                # Skip nodes that can't be converted (might be old format)
                logger.warning(f"Failed to convert node {node.id} to ConfigNode: {e}")
                continue

        return filtered_nodes

    def get_node_type(self) -> str:
        """Get the node type this service manages."""
        return "CONFIG"

    async def get_config(self, key: str) -> Optional[ConfigNode]:
        """Get current configuration value."""
        # Check cache first
        if key in self._config_cache:
            self._cache_hits += 1
            return self._config_cache[key]

        # Cache miss - query from graph
        self._cache_misses += 1

        # Query config nodes by key
        graph_nodes = await self._query_config_by_key(key)
        if not graph_nodes:
            return None

        # Convert GraphNodes to ConfigNodes and sort by version
        config_nodes = []
        for node in graph_nodes:
            try:
                config_node = ConfigNode.from_graph_node(node)
                config_nodes.append(config_node)
            except Exception as e:
                logger.warning(f"Failed to convert node to ConfigNode: {e}")
                continue

        if not config_nodes:
            return None

        # Sort by version, get latest
        config_nodes.sort(key=lambda n: n.version, reverse=True)
        latest_config = config_nodes[0]

        # Cache the result
        self._config_cache[key] = latest_config

        return latest_config

    async def set_config(
        self,
        key: str,
        value: Union[str, int, float, bool, JSONList, JSONDict, Path],
        updated_by: str,
        scope: Optional[GraphScope] = None,
    ) -> None:
        """Set configuration value with history.

        Args:
            key: Configuration key
            value: Configuration value
            updated_by: Who is making the update
            scope: Graph scope (LOCAL for agent-modifiable, IDENTITY for WA-protected).
                   Defaults to LOCAL if not specified.
        """
        import uuid

        from ciris_engine.schemas.services.nodes import ConfigValue

        # Default to LOCAL scope if not specified
        config_scope = scope if scope is not None else GraphScope.LOCAL

        # Get current version
        current = await self.get_config(key)

        # Wrap value in ConfigValue
        config_value = ConfigValue()
        # Check Path first before other types
        if isinstance(value, Path):
            config_value.string_value = str(value)  # Convert Path to string
        elif isinstance(value, bool):  # Check bool before int (bool is subclass of int)
            config_value.bool_value = value
        elif isinstance(value, int):
            config_value.int_value = value
        elif isinstance(value, float):
            config_value.float_value = value
        elif isinstance(value, str):
            config_value.string_value = value
        elif isinstance(value, list):
            # Cast to the expected list type for ConfigValue
            config_value.list_value = cast(List[Union[str, int, float, bool]], value)
        else:  # isinstance(value, dict)
            # dict_value already matches JSONDict type
            config_value.dict_value = value

        # Check if value has changed
        if current:
            current_value = current.value.value  # Use the @property method
            # Convert Path objects for comparison
            compare_value = str(value) if isinstance(value, Path) else value
            if current_value == compare_value:
                # No change needed
                # Sanitize key for logging
                from ciris_engine.logic.utils.log_sanitizer import sanitize_for_log

                safe_key = sanitize_for_log(key, max_length=100)
                logger.debug(f"Config {safe_key} unchanged, skipping update")
                return

        # Create new config node with all required fields
        now = self._time_service.now() if self._time_service else datetime.now(timezone.utc)
        new_config = ConfigNode(
            # GraphNode required fields
            id=f"config_{key.replace('.', '_')}_{uuid.uuid4().hex[:8]}",
            # type will use default from ConfigNode
            scope=config_scope,  # Use provided scope (LOCAL=agent-modifiable, IDENTITY=WA-protected)
            attributes={
                "created_at": now.isoformat(),
                "created_by": updated_by,
            },  # Include created_at/created_by for compliance
            # ConfigNode specific fields
            key=key,
            value=config_value,
            version=(current.version + 1) if current else 1,
            updated_by=updated_by,
            updated_at=now,
            previous_version=current.id if current else None,
        )

        # Store in graph (base class will handle conversion)
        await self.store_in_graph(new_config)

        # Update cache with new config
        self._config_cache[key] = new_config

        # Notify listeners of the change
        await self._notify_listeners(key, current.value if current else None, config_value)

    async def list_configs(
        self, prefix: Optional[str] = None
    ) -> Dict[str, Union[str, int, float, bool, JSONList, JSONDict]]:
        """List all configurations with optional prefix filter."""
        # Get all config nodes
        all_nodes = await self.graph.search("type:config")

        # Convert to ConfigNodes and group by key to get latest version of each
        config_map: Dict[str, ConfigNode] = {}
        for node in all_nodes:
            try:
                config_node = ConfigNode.from_graph_node(node)
                if prefix and not config_node.key.startswith(prefix):
                    continue
                if config_node.key not in config_map or config_node.version > config_map[config_node.key].version:
                    config_map[config_node.key] = config_node
            except Exception as e:
                logger.warning(f"Failed to convert node to ConfigNode: {e}")
                continue

        # Return key->value mapping (extract actual value from ConfigValue)
        result: Dict[str, Union[str, int, float, bool, JSONList, JSONDict]] = {}
        for key, node in config_map.items():
            val = node.value.value
            if val is not None:  # Skip None values to match return type
                # Cast to the expected type since we know it's not None
                result[key] = cast(Union[str, int, float, bool, JSONList, JSONDict], val)
        return result

    def register_config_listener(self, key_pattern: str, callback: Callable[..., Any]) -> None:
        """Register a callback for config changes matching the key pattern.

        Args:
            key_pattern: Config key pattern (e.g., "adapter.*" for all adapter configs)
            callback: Async function to call with (key, old_value, new_value)
        """
        if key_pattern not in self._config_listeners:
            self._config_listeners[key_pattern] = []
        self._config_listeners[key_pattern].append(callback)
        # Sanitize pattern for logging
        from ciris_engine.logic.utils.log_sanitizer import sanitize_for_log

        safe_pattern = sanitize_for_log(key_pattern, max_length=100)
        logger.info(f"Registered config listener for pattern: {safe_pattern}")

    def unregister_config_listener(self, key_pattern: str, callback: Callable[..., Any]) -> None:
        """Unregister a config change callback."""
        if key_pattern in self._config_listeners:
            self._config_listeners[key_pattern].remove(callback)
            if not self._config_listeners[key_pattern]:
                del self._config_listeners[key_pattern]

    async def _notify_listeners(self, key: str, old_value: Optional[ConfigValue], new_value: ConfigValue) -> None:
        """Notify registered listeners of config changes."""
        import fnmatch

        for pattern, callbacks in self._config_listeners.items():
            if fnmatch.fnmatch(key, pattern):
                for callback in callbacks:
                    try:
                        # Support both sync and async callbacks
                        import asyncio

                        if asyncio.iscoroutinefunction(callback):
                            await callback(key, old_value, new_value)
                        else:
                            callback(key, old_value, new_value)
                    except Exception as e:
                        # Use centralized log sanitization to prevent log injection
                        from ciris_engine.logic.utils.log_sanitizer import sanitize_for_log

                        safe_key = sanitize_for_log(key, max_length=100)
                        safe_pattern = sanitize_for_log(pattern, max_length=50)
                        safe_error = sanitize_for_log(str(e), max_length=200)

                        logger.error(
                            f"Error notifying config listener for config key: {safe_key}, pattern: {safe_pattern}, error: {safe_error}"
                        )

    # Required methods for BaseGraphService

    def get_service_type(self) -> ServiceType:
        """Get the service type."""
        return ServiceType.CONFIG

    def _get_actions(self) -> List[str]:
        """Get the list of actions this service supports."""
        return [
            "get_config",
            "set_config",
            "list_configs",
            "delete_config",
            "register_config_listener",
            "unregister_config_listener",
        ]

    def _check_dependencies(self) -> bool:
        """Check if all dependencies are satisfied."""
        # Config service uses LocalGraphMemoryService directly instead of memory bus
        return self.graph is not None
