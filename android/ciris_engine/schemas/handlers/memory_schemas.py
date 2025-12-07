"""
Memory handler schemas for typed memory operations.

Provides typed schemas usage in memory handlers.
"""

from typing import Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from ciris_engine.schemas.types import JSONDict


class ConnectedNodeInfo(BaseModel):
    """Information about a node connected to a recalled node."""

    node_id: str = Field(..., description="ID of the connected node")
    node_type: str = Field(..., description="Type of the connected node")
    relationship: str = Field(..., description="Type of relationship/edge")
    direction: str = Field(..., description="Direction of the relationship (incoming/outgoing)")
    attributes: JSONDict = Field(default_factory=dict, description="Attributes of the connected node")

    model_config = ConfigDict(extra="forbid")


class RecalledNodeInfo(BaseModel):
    """Structured information about a recalled node."""

    type: str = Field(..., description="Type of the node")
    scope: str = Field(..., description="Scope of the node (LOCAL/GLOBAL)")
    attributes: JSONDict = Field(default_factory=dict, description="Node attributes")
    connected_nodes: Optional[List[ConnectedNodeInfo]] = Field(None, description="Connected nodes information")

    model_config = ConfigDict(extra="forbid")


class RecallResult(BaseModel):
    """Result of a memory recall operation."""

    success: bool = Field(..., description="Whether the recall was successful")
    nodes: Dict[str, RecalledNodeInfo] = Field(default_factory=dict, description="Map of node IDs to their information")
    query_description: str = Field(..., description="Description of the query that was executed")
    total_results: int = Field(0, description="Total number of results found")
    truncated: bool = Field(False, description="Whether results were truncated")

    model_config = ConfigDict(extra="forbid")

    def to_follow_up_content(self) -> str:
        """Convert recall result to follow-up thought content."""
        import json

        if not self.success or not self.nodes:
            return f"CIRIS_FOLLOW_UP_THOUGHT: No memories found for query '{self.query_description}'"

        # Convert nodes to enhanced data format
        enhanced_data = {}
        for node_id, node_info in self.nodes.items():
            enhanced_data[node_id] = node_info.model_dump()

        data_str = json.dumps(enhanced_data, indent=2, default=str)

        if len(data_str) > 10000:
            # Truncate to first 10k characters
            truncated_data = data_str[:10000]
            return f"CIRIS_FOLLOW_UP_THOUGHT: Memory query '{self.query_description}' returned over {len(data_str)} characters, first 10000 characters: {truncated_data}"
        else:
            return f"CIRIS_FOLLOW_UP_THOUGHT: Memory query '{self.query_description}' returned: {data_str}"
