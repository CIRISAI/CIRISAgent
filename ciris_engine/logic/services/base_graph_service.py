"""
Enhanced Base Graph Service - Extends BaseService for graph-backed services.
"""
from typing import Optional, List, Dict, Any, TYPE_CHECKING

from ciris_engine.logic.services.base_service import BaseService
from ciris_engine.schemas.services.graph_core import GraphNode
from ciris_engine.schemas.services.operations import MemoryQuery, MemoryOpStatus

if TYPE_CHECKING:
    from ciris_engine.logic.buses import MemoryBus


class BaseGraphService(BaseService):
    """
    Base class for graph services with memory bus integration.
    
    Provides:
    - Memory bus dependency management
    - Graph storage and querying methods
    - Automatic metrics for memory bus availability
    
    Subclasses MUST still implement:
    - get_service_type() -> ServiceType
    - _get_actions() -> List[str]
    - get_node_type() -> str (specific to graph services)
    """
    
    def __init__(
        self,
        *,
        memory_bus: Optional['MemoryBus'] = None,
        **kwargs: Any
    ) -> None:
        """
        Initialize base graph service.
        
        Args:
            memory_bus: MemoryBus for graph persistence operations
            **kwargs: Additional arguments passed to BaseService
        """
        super().__init__(**kwargs)
        self._memory_bus = memory_bus
    
    def set_memory_bus(self, memory_bus: 'MemoryBus') -> None:
        """Set the memory bus for graph operations."""
        self._memory_bus = memory_bus
        self._logger.info(f"{self.service_name}: Memory bus updated")
    
    def _register_dependencies(self) -> None:
        """Register graph service dependencies."""
        super()._register_dependencies()
        self._dependencies.add("MemoryBus")
    
    def _check_dependencies(self) -> bool:
        """Check if memory bus is available."""
        return self._memory_bus is not None
    
    def _collect_custom_metrics(self) -> Dict[str, float]:
        """Collect graph service metrics."""
        metrics = super()._collect_custom_metrics()
        metrics.update({
            "memory_bus_available": 1.0 if self._memory_bus else 0.0
        })
        return metrics
    
    # Graph-specific abstract method
    
    def get_node_type(self) -> str:
        """
        Get the type of nodes this service manages.
        
        Default implementation returns service type, but can be overridden
        for more specific node types.
        """
        return self.get_service_type().value
    
    # Graph operations
    
    async def store_in_graph(self, node: GraphNode) -> str:
        """
        Store a node in the graph using MemoryBus.
        
        Args:
            node: GraphNode to store (or any object with to_graph_node method)
            
        Returns:
            Node ID if successful, empty string if failed
            
        Raises:
            RuntimeError: If memory bus is not available
        """
        if not self._memory_bus:
            raise RuntimeError(f"{self.service_name}: Memory bus not available")
        
        self._track_request()
        
        try:
            # Convert to GraphNode if it has a to_graph_node method
            if hasattr(node, 'to_graph_node') and callable(getattr(node, 'to_graph_node')):
                graph_node = node.to_graph_node()
            else:
                graph_node = node
            
            result = await self._memory_bus.memorize(graph_node)
            
            if result.status == MemoryOpStatus.OK:
                self._logger.debug(f"{self.service_name}: Stored node {graph_node.id}")
                return graph_node.id
            else:
                self._logger.warning(f"{self.service_name}: Failed to store node {graph_node.id}")
                return ""
                
        except Exception as e:
            self._track_error(e)
            raise
    
    async def query_graph(self, query: MemoryQuery) -> List[GraphNode]:
        """
        Query the graph using MemoryBus.
        
        Args:
            query: MemoryQuery with filters and options
            
        Returns:
            List of matching GraphNodes
        """
        if not self._memory_bus:
            self._logger.warning(f"{self.service_name}: Memory bus not available for query")
            return []
        
        self._track_request()
        
        try:
            result = await self._memory_bus.recall(query)
            
            # Handle different result types
            if hasattr(result, 'status') and hasattr(result, 'data'):
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
            
        except Exception as e:
            self._track_error(e)
            return []