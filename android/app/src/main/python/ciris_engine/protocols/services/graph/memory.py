"""Memory Service Protocol."""

from abc import abstractmethod
from datetime import datetime
from typing import TYPE_CHECKING, Dict, List, Optional, Protocol

from ciris_engine.schemas.runtime.memory import TimeSeriesDataPoint
from ciris_engine.schemas.services.graph.memory import MemorySearchFilter
from ciris_engine.schemas.services.graph_core import GraphEdge, GraphNode, GraphScope
from ciris_engine.schemas.services.operations import MemoryOpResult, MemoryQuery

from ...runtime.base import GraphServiceProtocol

if TYPE_CHECKING:
    from ciris_engine.schemas.services.operations import MemoryOpResult


class MemoryServiceProtocol(GraphServiceProtocol, Protocol):
    """Protocol for memory service - the three universal memory verbs."""

    @abstractmethod
    async def memorize(self, node: GraphNode) -> "MemoryOpResult[GraphNode]":
        """
        MEMORIZE - Store a graph node in memory.

        Returns:
            MemoryOpResult[GraphNode] with the stored node in data field
        """
        ...

    @abstractmethod
    async def recall(self, recall_query: MemoryQuery) -> List[GraphNode]:
        """
        RECALL - Retrieve nodes matching query.

        Returns:
            List of GraphNodes matching the query (empty list if none found)
        """
        ...

    @abstractmethod
    async def forget(self, node: GraphNode) -> "MemoryOpResult[GraphNode]":
        """
        FORGET - Remove a specific node from memory.

        Returns:
            MemoryOpResult[GraphNode] with the forgotten node in data field
        """
        ...

    @abstractmethod
    async def memorize_metric(
        self, metric_name: str, value: float, tags: Optional[Dict[str, str]] = None, scope: str = "local"
    ) -> "MemoryOpResult[GraphNode]":
        """
        Memorize a metric value (convenience for telemetry).

        Returns:
            MemoryOpResult[GraphNode] with the metric node in data field
        """
        ...

    @abstractmethod
    async def memorize_log(
        self, log_message: str, log_level: str = "INFO", tags: Optional[Dict[str, str]] = None, scope: str = "local"
    ) -> "MemoryOpResult[GraphNode]":
        """
        Memorize a log entry (convenience for logging).

        Returns:
            MemoryOpResult[GraphNode] with the log node in data field
        """
        ...

    @abstractmethod
    async def recall_timeseries(
        self,
        scope: str = "default",
        hours: int = 24,
        correlation_types: Optional[List[str]] = None,
        start_time: Optional["datetime"] = None,
        end_time: Optional["datetime"] = None,
    ) -> List[TimeSeriesDataPoint]:
        """Recall time-series data."""
        ...

    @abstractmethod
    async def export_identity_context(self) -> str:
        """Export identity nodes as string representation."""
        ...

    @abstractmethod
    async def search(self, query: str, filters: Optional["MemorySearchFilter"] = None) -> List[GraphNode]:
        """Search memories using text query."""
        ...

    @abstractmethod
    async def create_edge(self, edge: "GraphEdge") -> "MemoryOpResult[GraphEdge]":
        """
        Create an edge between two nodes in the memory graph.

        Returns:
            MemoryOpResult[GraphEdge] with the created edge in data field
        """
        ...

    @abstractmethod
    async def get_node_edges(self, node_id: str, scope: "GraphScope") -> List["GraphEdge"]:
        """Get all edges connected to a node."""
        ...
