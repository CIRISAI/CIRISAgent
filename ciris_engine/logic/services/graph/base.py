"""
Base Graph Service - Common implementation for all graph services.

Provides default implementations of GraphServiceProtocol methods.
All graph services use the MemoryBus for actual persistence operations.
"""

import logging
import time
from abc import ABC, abstractmethod
from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from ciris_engine.protocols.runtime.base import GraphServiceProtocol
from ciris_engine.protocols.services.lifecycle.time import TimeServiceProtocol
from ciris_engine.schemas.services.core import ServiceCapabilities, ServiceStatus
from ciris_engine.schemas.services.graph_core import GraphNode, GraphScope, NodeType
from ciris_engine.schemas.services.operations import MemoryOpStatus, MemoryQuery

if TYPE_CHECKING:
    from ciris_engine.logic.buses import MemoryBus

logger = logging.getLogger(__name__)


class BaseGraphService(ABC, GraphServiceProtocol):
    """Base class for all graph services providing common functionality.

    Graph services store their data through the MemoryBus, which provides:
    - Multiple backend support (Neo4j, ArangoDB, in-memory)
    - Secret detection and encryption
    - Audit trail integration
    - Typed schema validation
    """

    def __init__(
        self, memory_bus: Optional["MemoryBus"] = None, time_service: Optional[TimeServiceProtocol] = None
    ) -> None:
        """Initialize base graph service.

        Args:
            memory_bus: MemoryBus for graph persistence operations
            time_service: TimeService for consistent timestamps
        """
        self.service_name = self.__class__.__name__
        self._memory_bus = memory_bus
        self._time_service = time_service
        self._request_count = 0
        self._error_count = 0
        self._total_response_time = 0.0
        self._start_time: Optional[datetime] = None
        self._started = False

    def _set_memory_bus(self, memory_bus: "MemoryBus") -> None:
        """Set the memory bus for graph operations."""
        self._memory_bus = memory_bus

    def _set_time_service(self, time_service: TimeServiceProtocol) -> None:
        """Set the time service for timestamps."""
        self._time_service = time_service

    def start(self) -> None:
        """Start the service."""
        self._start_time = datetime.now()
        self._started = True
        logger.info(f"{self.service_name} started")

    def stop(self) -> None:
        """Stop the service."""
        self._started = False
        logger.info(f"{self.service_name} stopped")

    def get_capabilities(self) -> ServiceCapabilities:
        """Get service capabilities."""
        return ServiceCapabilities(
            service_name=self.service_name,
            actions=["store_in_graph", "query_graph", self.get_node_type()],
            version="1.0.0",
        )

    def _check_dependencies(self) -> bool:
        """Check if all dependencies are satisfied."""
        return self._memory_bus is not None

    def _collect_metrics(self) -> Dict[str, float]:
        """
        Collect all metrics for this graph service.
        
        This follows the pattern from BaseService but adapted for graph services.
        Returns base metrics plus custom metrics.
        """
        # Calculate uptime
        uptime = 0.0
        if self._start_time:
            uptime = (datetime.now() - self._start_time).total_seconds()
        
        # Calculate average response time
        avg_response_time = 0.0
        if self._request_count > 0:
            avg_response_time = self._total_response_time / self._request_count
        
        # Base metrics
        base_metrics = {
            "uptime_seconds": uptime,
            "request_count": float(self._request_count),
            "error_count": float(self._error_count),
            "avg_response_time_ms": avg_response_time,
            "healthy": 1.0 if self._started and self._check_dependencies() else 0.0,
        }
        
        # Add custom metrics
        custom_metrics = self._collect_custom_metrics()
        base_metrics.update(custom_metrics)
        
        return base_metrics
    
    def _collect_custom_metrics(self) -> Dict[str, float]:
        """
        Collect graph service specific metrics.
        
        Subclasses should override this to add their own metrics.
        """
        return {
            "memory_bus_available": 1.0 if self._memory_bus else 0.0,
            "time_service_available": 1.0 if self._time_service else 0.0,
            "graph_operations_total": float(self._request_count),
            "graph_errors_total": float(self._error_count),
        }
    
    async def get_metrics(self) -> Dict[str, float]:
        """
        Public async method to get all service metrics.
        
        Returns combined base metrics and custom metrics.
        This is the standard interface for metric collection.
        """
        return self._collect_metrics()

    def _get_actions(self) -> List[str]:
        """Get the list of actions this service supports."""
        return ["store_in_graph", "query_graph", self.get_node_type()]

    def _track_request(self, response_time_ms: float) -> None:
        """Track a successful request with response time."""
        self._request_count += 1
        self._total_response_time += response_time_ms

    def _track_error(self) -> None:
        """Track an error occurrence."""
        self._error_count += 1

    async def store_in_graph(self, node: GraphNode) -> str:
        """Store a node in the graph using MemoryBus.

        Args:
            node: GraphNode to store (or any object with to_graph_node method)

        Returns:
            Node ID if successful, empty string if failed
        """
        if not self._memory_bus:
            raise RuntimeError(f"{self.service_name}: Memory bus not available")

        # Convert to GraphNode if it has a to_graph_node method
        if hasattr(node, "to_graph_node") and callable(getattr(node, "to_graph_node")):
            graph_node = node.to_graph_node()
        else:
            graph_node = node

        result = await self._memory_bus.memorize(graph_node)
        return graph_node.id if result.status == MemoryOpStatus.OK else ""

    async def query_graph(self, query: MemoryQuery) -> List[GraphNode]:
        """Query the graph using MemoryBus.

        Args:
            query: MemoryQuery with filters and options

        Returns:
            List of matching GraphNodes
        """
        if not self._memory_bus:
            logger.warning(f"{self.service_name}: Memory bus not available for query")
            return []

        result = await self._memory_bus.recall(query)

        # Handle different result types
        if hasattr(result, "status") and hasattr(result, "data"):
            # It's a MemoryOpResult
            if result.status == MemoryOpStatus.OK and result.data:
                if isinstance(result.data, list):
                    return result.data
                else:
                    return [result.data]
        elif isinstance(result, list):
            # Direct list of nodes
            return result

        return []

    async def recall_node(self, node_id: str, scope: Optional[GraphScope] = None) -> Optional[GraphNode]:
        """Recall a specific node by ID.
        
        Args:
            node_id: The ID of the node to recall
            scope: Optional scope to limit the recall
            
        Returns:
            The GraphNode if found, None otherwise
        """
        query = MemoryQuery(
            node_id=node_id,
            scope=scope or GraphScope.LOCAL
        )
        
        start_time = time.time()
        try:
            async with self._memory_bus.get_connection() as memory:
                nodes = await memory.recall(query)
                response_time = (time.time() - start_time) * 1000
                self._track_request(response_time)
                return nodes[0] if nodes else None
        except Exception as e:
            self._track_error()
            logger.error(f"{self.service_name}: Error recalling node {node_id}: {e}")
            return None
    
    async def search_nodes(
        self, 
        node_type: Optional[NodeType] = None,
        metadata_filter: Optional[Dict[str, Any]] = None,
        limit: int = 10,
        scope: Optional[GraphScope] = None
    ) -> List[GraphNode]:
        """Search for nodes by type and/or metadata filters.
        
        Args:
            node_type: Optional NodeType to filter by
            metadata_filter: Optional metadata key-value pairs to match
            limit: Maximum number of results to return
            scope: Optional scope to limit the search
            
        Returns:
            List of matching GraphNodes
        """
        from ciris_engine.schemas.services.graph_core import GraphScope
        
        # Build a search query
        # Since MemoryQuery requires node_id for recall, we'll use a wildcard
        # This is a known architectural issue - MemoryQuery isn't designed for search
        query = MemoryQuery(
            node_id="*",  # Wildcard for search queries
            scope=scope or GraphScope.LOCAL,
            type=node_type  # Use the type field for filtering
        )
        
        start_time = time.time()
        try:
            async with self._memory_bus.get_connection() as memory:
                # Get all nodes and filter locally
                # This is inefficient but necessary until MemoryQuery is fixed
                all_nodes = await memory.recall(query)
                response_time = (time.time() - start_time) * 1000
                self._track_request(response_time)
                
                if not all_nodes:
                    return []
                
                # Filter results based on criteria
                results = []
                for node in all_nodes:
                    if not isinstance(node, GraphNode):
                        continue
                        
                    # Check node type filter
                    if node_type and node.type != node_type:
                        continue
                    
                    # Check metadata filter
                    if metadata_filter:
                        # Get metadata from attributes
                        node_meta = {}
                        if hasattr(node.attributes, 'metadata'):
                            node_meta = node.attributes.metadata or {}
                        elif isinstance(node.attributes, dict):
                            node_meta = node.attributes.get('metadata', {})
                        
                        if not all(node_meta.get(k) == v for k, v in metadata_filter.items()):
                            continue
                    
                    results.append(node)
                    if len(results) >= limit:
                        break
                
                return results
        except Exception as e:
            self._track_error()
            logger.error(f"{self.service_name}: Error searching nodes: {e}")
            return []
    
    async def query_memory(self, query: MemoryQuery) -> List[GraphNode]:
        """Legacy method - delegates to recall_node or search_nodes based on query type.
        
        Args:
            query: MemoryQuery object
            
        Returns:
            List of GraphNodes (empty list if none found)
        """
        if query.node_id and query.node_id != "*":
            # This is a recall query for a specific node
            node = await self.recall_node(query.node_id, query.scope)
            return [node] if node else []
        else:
            # This is a search query - use search with type filter if provided
            return await self.search_nodes(node_type=query.type, scope=query.scope)

    @abstractmethod
    def get_node_type(self) -> str:
        """Get the type of nodes this service manages - must be implemented by subclass."""
        raise NotImplementedError
