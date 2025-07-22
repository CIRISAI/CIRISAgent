"""
Action parameter schemas for contract-driven architecture.

Typed parameters for each of the 10 action types.
"""

from typing import (
    Dict,
    List,
    Optional,
    Union
)
from pydantic import BaseModel, Field, ConfigDict
from ..services.graph_core import GraphScope, GraphNode
from ciris_engine.schemas.runtime.system_context import ChannelContext

class ObserveParams(BaseModel):
    """Parameters for OBSERVE action."""
    channel_context: Optional[ChannelContext] = None
    active: bool = True  # Always active - agent should always create follow-up thoughts
    context: Optional[Dict[str, str]] = Field(default=None)

    model_config = ConfigDict(extra="forbid")

class SpeakParams(BaseModel):
    """Parameters for SPEAK action."""
    channel_context: Optional[ChannelContext] = None
    content: str

    model_config = ConfigDict(extra="forbid")

class ToolParams(BaseModel):
    """Parameters for TOOL action."""
    name: str
    parameters: Dict[str, Union[str, int, float, bool, List[str], Dict[str, str]]] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid")

class PonderParams(BaseModel):
    """Parameters for PONDER action."""
    questions: List[str]

    model_config = ConfigDict(extra="forbid")

class RejectParams(BaseModel):
    """Parameters for REJECT action."""
    reason: str
    create_filter: bool = Field(default=False, description="Whether to create an adaptive filter to prevent similar requests")
    filter_pattern: Optional[str] = Field(default=None, description="Pattern to filter (regex or keywords)")
    filter_type: Optional[str] = Field(default="regex", description="Type of filter: regex, semantic, keyword")
    filter_priority: Optional[str] = Field(default="high", description="Priority level: critical, high, medium")

    model_config = ConfigDict(extra="forbid")

class DeferParams(BaseModel):
    """Parameters for DEFER action."""
    reason: str
    context: Optional[Dict[str, str]] = Field(default=None)
    defer_until: Optional[str] = Field(
        None,
        description="ISO timestamp to reactivate task (e.g., '2025-01-20T15:00:00Z')"
    )

    model_config = ConfigDict(extra="forbid")

class MemorizeParams(BaseModel):
    """Parameters for MEMORIZE action."""
    node: GraphNode

    model_config = ConfigDict(extra="forbid")

    @property
    def scope(self) -> GraphScope:
        return self.node.scope

class RecallParams(BaseModel):
    """Parameters for RECALL action."""
    query: Optional[str] = Field(None, description="Search query text")
    node_type: Optional[str] = Field(None, description="Type of nodes to recall")
    node_id: Optional[str] = Field(None, description="Specific node ID to recall")
    scope: Optional[GraphScope] = Field(None, description="Scope to search in")
    limit: int = Field(10, description="Maximum number of results")

    model_config = ConfigDict(extra="forbid")

class ForgetParams(BaseModel):
    """Parameters for FORGET action."""
    node: GraphNode
    reason: str
    no_audit: bool = False

    model_config = ConfigDict(extra="forbid")

    @property
    def scope(self) -> GraphScope:
        return self.node.scope

class TaskCompleteParams(BaseModel):
    """Parameters for TASK_COMPLETE action."""
    completion_reason: str = "Task completed successfully"
    context: Optional[Dict[str, str]] = Field(default=None)
    positive_moment: Optional[str] = Field(None, description="Optional note about positive vibes/joy from this task")

    model_config = ConfigDict(extra="forbid")
