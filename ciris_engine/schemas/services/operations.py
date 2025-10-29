"""
Memory operation schemas for CIRIS Trinity Architecture.

All memory operations are typed - no Dict[str, Any].
"""

from datetime import datetime
from enum import Enum
from typing import Any, Generic, List, Optional, TypeVar

from pydantic import BaseModel, ConfigDict, Field

from ciris_engine.schemas.runtime.enums import CaseInsensitiveEnum
from ciris_engine.schemas.services.graph_core import GraphNode, GraphScope, NodeType


class InitializationPhase(str, Enum):
    """Initialization phases in order."""

    INFRASTRUCTURE = "infrastructure"  # Time, shutdown, initialization services
    DATABASE = "database"
    MEMORY = "memory"
    IDENTITY = "identity"
    SECURITY = "security"
    SERVICES = "services"
    COMPONENTS = "components"
    VERIFICATION = "verification"


class InitializationStatus(str, Enum):
    """Status of initialization phases."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    VERIFIED = "verified"


class MemoryOpStatus(CaseInsensitiveEnum):
    """Status of a memory operation."""

    OK = "ok"
    SUCCESS = "ok"  # Alias for OK
    DEFERRED = "deferred"
    DENIED = "denied"
    PENDING = "pending"
    ERROR = "error"
    FAILED = "error"  # Alias for ERROR


class MemoryOpAction(str, Enum):
    """Memory operation types."""

    MEMORIZE = "memorize"
    RECALL = "recall"
    FORGET = "forget"


T = TypeVar("T")


class MemoryOpResult(BaseModel, Generic[T]):
    """
    Parametrized result of a memory operation.

    Type parameter T specifies the data type returned by the operation:
    - MemoryOpResult[GraphNode] for single node operations (memorize, forget)
    - MemoryOpResult[List[GraphNode]] for multi-node operations (recall, search)
    - MemoryOpResult[None] for operations with no data return
    """

    status: MemoryOpStatus
    reason: Optional[str] = None
    data: Optional[T] = None
    error: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    metadata: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid")

    @property
    def nodes(self) -> List[GraphNode]:
        """
        Backward compatibility property - return data as list of nodes.

        This allows existing code using result.nodes to continue working
        while we transition to typed result.data access.
        """
        if self.data is None:
            return []
        if isinstance(self.data, list):
            return self.data
        # Single node - wrap in list (T is GraphNode at runtime)
        return [self.data]  # type: ignore[list-item]


class MemoryQuery(BaseModel):
    """Query parameters for memory recall operations."""

    node_id: str = Field(..., description="Unique identifier of the node to recall")
    scope: GraphScope = Field(..., description="Memory scope (LOCAL, IDENTITY, ENVIRONMENT)")
    type: Optional[NodeType] = Field(None, description="Optional node type filter")
    include_edges: bool = Field(False, description="Whether to include connected edges")
    depth: int = Field(1, ge=1, le=10, description="Graph traversal depth for connected nodes")

    model_config = ConfigDict(extra="forbid")


class MemoryRecallResult(BaseModel):
    """Result of a memory recall operation."""

    nodes: List[GraphNode] = Field(default_factory=list, description="Retrieved graph nodes")
    total_count: int = Field(0, ge=0, description="Total number of nodes found")

    model_config = ConfigDict(extra="forbid")


__all__ = [
    "GraphScope",
    "MemoryOpStatus",
    "MemoryOpAction",
    "MemoryOpResult",
    "MemoryQuery",
    "MemoryRecallResult",
]
