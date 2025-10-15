"""
Graph memory service schemas.

Provides typed schemas in memory service operations.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, ConfigDict, Field

from ciris_engine.schemas.types import JSONDict


class MemoryNodeData(BaseModel):
    """Attributes for a graph node."""

    # Core attributes
    created_at: Optional[datetime] = Field(None, description="Creation timestamp")
    updated_at: Optional[datetime] = Field(None, description="Last update timestamp")
    created_by: Optional[str] = Field(None, description="Creator identifier")

    # Secret references
    secret_refs: List[str] = Field(default_factory=list, description="Secret reference UUIDs")

    # Dynamic attributes - we use a constrained dict here since node attributes are truly dynamic
    # but we ensure they're JSON-serializable types
    data: JSONDict = Field(default_factory=dict, description="Node data attributes")

    model_config = ConfigDict(extra="allow")  # Allow additional fields for flexibility


class MemorySearchFilter(BaseModel):
    """Filters for memory search operations."""

    node_type: Optional[str] = Field(None, description="Filter by node type")
    scope: Optional[str] = Field(None, description="Filter by scope")
    created_after: Optional[datetime] = Field(None, description="Filter by creation date")
    created_before: Optional[datetime] = Field(None, description="Filter by creation date")
    created_by: Optional[str] = Field(None, description="Filter by creator")
    has_attributes: Optional[List[str]] = Field(None, description="Must have these attributes")
    attribute_values: Optional[Dict[str, Union[str, int, float, bool]]] = Field(
        None, description="Attribute value filters"
    )
    limit: Optional[int] = Field(None, description="Maximum results")
    offset: Optional[int] = Field(None, description="Results offset")


class GraphQuery(BaseModel):
    """Query parameters for graph operations."""

    # Query type
    query_type: str = Field(..., description="Type of query: match, traverse, aggregate")

    # Node filters
    node_filters: Optional[MemorySearchFilter] = Field(None, description="Node filters")

    # Relationship filters
    relationship_type: Optional[str] = Field(None, description="Filter by relationship type")
    relationship_direction: Optional[str] = Field("any", description="in, out, any")

    # Traversal options
    max_depth: Optional[int] = Field(None, description="Maximum traversal depth")
    include_relationships: bool = Field(False, description="Include relationships in results")

    # Aggregation options
    group_by: Optional[str] = Field(None, description="Attribute to group by")
    aggregations: Optional[List[str]] = Field(None, description="Aggregation functions")

    # Result options
    order_by: Optional[str] = Field(None, description="Attribute to order by")
    order_desc: bool = Field(False, description="Order descending")
    limit: Optional[int] = Field(None, description="Result limit")


class MemoryOperationContext(BaseModel):
    """Context for memory operations."""

    operation: str = Field(..., description="Operation being performed")
    action_type: Optional[str] = Field(None, description="Associated action type")
    auto_decrypt: bool = Field(False, description="Whether to auto-decrypt secrets")
    channel_id: Optional[str] = Field(None, description="Channel context")
    user_id: Optional[str] = Field(None, description="User context")
    metadata: Dict[str, str] = Field(default_factory=dict, description="Additional metadata")
