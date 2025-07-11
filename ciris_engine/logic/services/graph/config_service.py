"""
Graph Configuration Service for CIRIS Trinity Architecture.

All configuration is stored as memories in the graph, with full history tracking.
This replaces the old config_manager_service and agent_config_service.
"""
import logging
from datetime import datetime
from typing import Dict, List, Optional, Union

# Optional import for psutil
try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    psutil = None
    PSUTIL_AVAILABLE = False

from ciris_engine.protocols.services.graph.config import GraphConfigServiceProtocol
from ciris_engine.protocols.runtime.base import ServiceProtocol
from ciris_engine.schemas.services.nodes import ConfigNode
from ciris_engine.schemas.services.core import ServiceCapabilities, ServiceStatus
from ciris_engine.logic.services.graph.memory_service import LocalGraphMemoryService
from ciris_engine.protocols.services.lifecycle.time import TimeServiceProtocol

logger = logging.getLogger(__name__)

class GraphConfigService(GraphConfigServiceProtocol, ServiceProtocol):
    """Configuration service that stores all config as graph memories."""

    def __init__(self, graph_memory_service: LocalGraphMemoryService, time_service: TimeServiceProtocol):
        """Initialize with graph memory service."""
        self.graph = graph_memory_service
        self._running = False
        self._time_service = time_service
        self._start_time: Optional[datetime] = None
        self._process = psutil.Process() if PSUTIL_AVAILABLE else None  # For memory tracking
        self._config_cache: Dict[str, ConfigNode] = {}  # Cache for config nodes
        self._config_listeners: Dict[str, List[callable]] = {}  # key_pattern -> [callbacks]

    async def start(self) -> None:
        """Start the service."""
        self._running = True
        self._start_time = self._time_service.now()

    async def stop(self) -> None:
        """Stop the service."""
        self._running = False
        # Nothing to clean up

    def get_capabilities(self) -> ServiceCapabilities:
        """Get service capabilities."""
        return ServiceCapabilities(
            service_name="GraphConfigService",
            actions=[
                "get_config",
                "set_config",
                "list_configs"
            ],
            version="1.0.0",
            dependencies=["GraphMemoryService", "TimeService"]
        )

    def get_status(self) -> ServiceStatus:
        """Get service status."""
        uptime = 0.0
        if self._start_time:
            uptime = (self._time_service.now() - self._start_time).total_seconds()
        
        # Calculate memory usage
        memory_mb = 0.0
        try:
            if self._process:
                memory_info = self._process.memory_info()
                memory_mb = memory_info.rss / 1024 / 1024  # Convert bytes to MB
        except Exception as e:
            logger.debug(f"Could not get memory info: {e}")
            
        return ServiceStatus(
            service_name="GraphConfigService",
            service_type="graph_service",
            is_healthy=self._running,
            uptime_seconds=uptime,
            metrics={
                "total_configs": float(len(self._config_cache)),
                "memory_mb": memory_mb
            }
        )

    async def store_in_graph(self, node: ConfigNode) -> str:
        """Store config node in graph."""
        # Convert typed node to GraphNode for storage
        graph_node = node.to_graph_node()
        result = await self.graph.memorize(graph_node)
        # MemoryOpResult has data field, not node_id
        if result.status == "ok" and result.data:
            return result.data if isinstance(result.data, str) else str(result.data)
        return ""

    async def query_graph(self, query: dict) -> List[ConfigNode]:
        """Query config nodes from graph."""
        # Get all config nodes (use lowercase enum value)
        nodes = await self.graph.search("type:config")

        # Convert GraphNodes to ConfigNodes
        config_nodes = []
        for node in nodes:
            try:
                config_node = ConfigNode.from_graph_node(node)

                # Apply query filters
                matches = True
                for k, v in query.items():
                    if k == "key" and config_node.key != v:
                        matches = False
                        break
                    elif k == "version" and config_node.version != v:
                        matches = False
                        break

                if matches:
                    config_nodes.append(config_node)
            except Exception as e:
                # Skip nodes that can't be converted (might be old format)
                logger.warning(f"Failed to convert node {node.id} to ConfigNode: {e}")
                continue

        return config_nodes

    def get_node_type(self) -> str:
        """Get the node type this service manages."""
        return "CONFIG"

    async def get_config(self, key: str) -> Optional[ConfigNode]:
        """Get current configuration value."""
        # Find latest version
        nodes = await self.query_graph({"key": key})
        if not nodes:
            return None

        # Sort by version, get latest
        nodes.sort(key=lambda n: n.version, reverse=True)
        return nodes[0]

    async def set_config(self, key: str, value: Union[str, int, float, bool, List, Dict], updated_by: str) -> None:
        """Set configuration value with history."""
        import uuid
        from ciris_engine.schemas.services.graph_core import GraphScope
        from ciris_engine.schemas.services.nodes import ConfigValue

        # Get current version
        current = await self.get_config(key)

        # Wrap value in ConfigValue
        from pathlib import Path
        config_value = ConfigValue()
        if isinstance(value, str):
            config_value.string_value = value
        elif isinstance(value, Path):
            config_value.string_value = str(value)  # Convert Path to string
        elif isinstance(value, bool):  # Check bool before int (bool is subclass of int)
            config_value.bool_value = value
        elif isinstance(value, int):
            config_value.int_value = value
        elif isinstance(value, float):
            config_value.float_value = value
        elif isinstance(value, list):
            config_value.list_value = value
        elif isinstance(value, dict):
            config_value.dict_value = value
        else:
            # Log unexpected type with sanitized values to prevent log injection
            safe_key = ''.join(c if c.isprintable() and c not in '\n\r\t' else ' ' for c in str(key))
            safe_value = ''.join(c if c.isprintable() and c not in '\n\r\t' else ' ' for c in str(value)[:100])  # Limit length
            logger.warning(f"Unexpected config value type for key {safe_key}: {type(value).__name__} = {safe_value}")

        # Check if value has changed
        if current:
            current_value = current.value.value  # Use the @property method
            # Convert Path objects for comparison
            if isinstance(value, Path):
                value = str(value)
            if current_value == value:
                # No change needed
                logger.debug(f"Config {key} unchanged, skipping update")
                return

        # Create new config node with all required fields
        new_config = ConfigNode(
            # GraphNode required fields
            id=f"config_{key.replace('.', '_')}_{uuid.uuid4().hex[:8]}",
            # type will use default from ConfigNode
            scope=GraphScope.LOCAL,  # Config is always local scope
            attributes={},  # Empty dict for base GraphNode
            # ConfigNode specific fields
            key=key,
            value=config_value,
            version=(current.version + 1) if current else 1,
            updated_by=updated_by,
            updated_at=self._time_service.now(),
            previous_version=current.id if current else None
        )

        # Store in graph (base class will handle conversion)
        await self.store_in_graph(new_config)
        
        # Notify listeners of the change
        old_value = current.value.value if current else None
        await self._notify_listeners(key, old_value, value)


    async def list_configs(self, prefix: Optional[str] = None) -> Dict[str, Union[str, int, float, bool, List, Dict]]:
        """List all configurations with optional prefix filter."""
        # Get all config nodes
        all_configs = await self.query_graph({})

        # Group by key to get latest version of each
        config_map: Dict[str, ConfigNode] = {}
        for config in all_configs:
            if prefix and not config.key.startswith(prefix):
                continue
            if config.key not in config_map or config.version > config_map[config.key].version:
                config_map[config.key] = config

        # Return key->value mapping
        return {key: node.value for key, node in config_map.items()}

    async def is_healthy(self) -> bool:
        """Check if service is healthy."""
        return self._running
    
    def register_config_listener(self, key_pattern: str, callback: callable) -> None:
        """Register a callback for config changes matching the key pattern.
        
        Args:
            key_pattern: Config key pattern (e.g., "adapter.*" for all adapter configs)
            callback: Async function to call with (key, old_value, new_value)
        """
        if key_pattern not in self._config_listeners:
            self._config_listeners[key_pattern] = []
        self._config_listeners[key_pattern].append(callback)
        logger.info(f"Registered config listener for pattern: {key_pattern}")
    
    def unregister_config_listener(self, key_pattern: str, callback: callable) -> None:
        """Unregister a config change callback."""
        if key_pattern in self._config_listeners:
            self._config_listeners[key_pattern].remove(callback)
            if not self._config_listeners[key_pattern]:
                del self._config_listeners[key_pattern]
    
    async def _notify_listeners(self, key: str, old_value: any, new_value: any) -> None:
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
                        logger.error(f"Error notifying config listener for {key}: {e}")
