"""
Protocol for Incident Management Service.

ITIL-aligned incident processing for agent self-improvement through
pattern detection and insight generation.
"""

from typing import TYPE_CHECKING, List, Protocol, runtime_checkable

from ...runtime.base import GraphServiceProtocol

# Import forward references
if TYPE_CHECKING:
    from ciris_engine.schemas.services.core import ServiceCapabilities, ServiceStatus
    from ciris_engine.schemas.services.graph.incident import IncidentInsightNode
    from ciris_engine.schemas.services.graph_core import GraphNode
    from ciris_engine.schemas.services.operations import MemoryQuery


@runtime_checkable
class IncidentManagementServiceProtocol(GraphServiceProtocol, Protocol):
    """Protocol for incident management service.

    Processes incidents from logs, detects patterns, identifies problems,
    and generates insights for continuous self-improvement.
    """

    async def process_recent_incidents(self, hours: int = 24) -> "IncidentInsightNode":
        """Process recent incidents to identify patterns and generate insights.

        Called during dream cycle for self-improvement analysis.

        Args:
            hours: Number of hours of incidents to analyze

        Returns:
            IncidentInsightNode with analysis results and recommendations
        """
        ...

    # Required methods from GraphServiceProtocol
    def get_node_type(self) -> str:
        """Get the type of nodes this service manages.

        Returns:
            Node type string
        """
        ...

    async def store_in_graph(self, node: "GraphNode") -> str:
        """Store a node in the graph.

        Args:
            node: GraphNode to store

        Returns:
            Node ID
        """
        ...

    async def query_graph(self, query: "MemoryQuery") -> List["GraphNode"]:
        """Query the graph.

        Args:
            query: Memory query

        Returns:
            List of matching GraphNodes
        """
        ...

    # Required methods from ServiceProtocol
    async def start(self) -> None:
        """Start the incident management service."""
        ...

    async def stop(self) -> None:
        """Stop the incident management service."""
        ...

    def get_capabilities(self) -> "ServiceCapabilities":
        """Return service capabilities.

        Returns:
            ServiceCapabilities object
        """
        ...

    def get_status(self) -> "ServiceStatus":
        """Get service status.

        Returns:
            ServiceStatus object
        """
        ...

    async def is_healthy(self) -> bool:
        """Check if service is healthy.

        Returns:
            True if service is healthy
        """
        ...
