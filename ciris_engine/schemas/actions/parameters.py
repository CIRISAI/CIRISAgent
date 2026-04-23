"""
Action parameter schemas for contract-driven architecture.

Typed parameters for each of the 10 action types.
"""

from typing import Dict, List, Optional, Union

from pydantic import BaseModel, ConfigDict, Field

from ciris_engine.schemas.runtime.system_context import ChannelContext
from ciris_engine.schemas.services.agent_credits import DomainCategory
from ciris_engine.schemas.services.deferral_taxonomy import DeferralNeedCategory, DeferralOperationalReason

from ..services.graph_core import GraphNode, GraphScope


class ObserveParams(BaseModel):
    """Parameters for OBSERVE action."""

    channel_id: Optional[str] = Field(None, description="Channel ID for observation")
    channel_context: Optional[ChannelContext] = None
    active: bool = True  # Always active - agent should always create follow-up thoughts
    context: Optional[Dict[str, Union[str, List[str]]]] = Field(default=None)

    model_config = ConfigDict(extra="forbid", defer_build=True)


class SpeakParams(BaseModel):
    """Parameters for SPEAK action."""

    channel_id: Optional[str] = Field(None, description="Channel ID to send message to")
    channel_context: Optional[ChannelContext] = None
    content: str

    model_config = ConfigDict(extra="forbid", defer_build=True)


class ToolParams(BaseModel):
    """Parameters for TOOL action."""

    channel_id: Optional[str] = Field(None, description="Channel ID for tool context")
    name: str
    parameters: Dict[str, Union[str, int, float, bool, List[str], Dict[str, str]]] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid", defer_build=True)


class PonderParams(BaseModel):
    """Parameters for PONDER action."""

    channel_id: Optional[str] = Field(None, description="Channel ID for context")
    questions: List[str]

    model_config = ConfigDict(extra="forbid", defer_build=True)


class RejectParams(BaseModel):
    """Parameters for REJECT action."""

    channel_id: Optional[str] = Field(None, description="Channel ID for context")
    reason: str
    create_filter: bool = Field(
        default=False, description="Whether to create an adaptive filter to prevent similar requests"
    )
    filter_pattern: Optional[str] = Field(default=None, description="Pattern to filter (regex or keywords)")
    filter_type: Optional[str] = Field(default="regex", description="Type of filter: regex, semantic, keyword")
    filter_priority: Optional[str] = Field(default="high", description="Priority level: critical, high, medium")

    model_config = ConfigDict(extra="forbid", defer_build=True)


class DeferParams(BaseModel):
    """Parameters for DEFER action."""

    channel_id: Optional[str] = Field(None, description="Channel ID for context")
    reason: str
    context: Optional[Dict[str, Union[str, List[str]]]] = Field(default=None)
    defer_until: Optional[str] = Field(
        None, description="ISO timestamp to reactivate task (e.g., '2025-01-20T15:00:00Z')"
    )
    reason_code: Optional[DeferralOperationalReason] = Field(
        None,
        description="Structured reason code for why this deferral is being created",
    )
    needs_category: Optional[DeferralNeedCategory] = Field(
        None,
        description="Primary rights/needs category implicated by this deferral",
    )
    secondary_needs_categories: List[DeferralNeedCategory] = Field(
        default_factory=list,
        description="Additional rights/needs categories implicated by this deferral",
    )
    rights_basis: List[str] = Field(
        default_factory=list,
        description="Human-rights basis labels that justify the deferral classification",
    )
    domain_hint: Optional[DomainCategory] = Field(
        None,
        description="Licensed domain hint for routing, when applicable",
    )

    model_config = ConfigDict(extra="forbid", defer_build=True)


class MemorizeParams(BaseModel):
    """Parameters for MEMORIZE action."""

    channel_id: Optional[str] = Field(None, description="Channel ID for context")
    node: GraphNode

    model_config = ConfigDict(extra="forbid", defer_build=True)

    @property
    def scope(self) -> GraphScope:
        return self.node.scope


class RecallParams(BaseModel):
    """Parameters for RECALL action."""

    channel_id: Optional[str] = Field(None, description="Channel ID for context")
    query: Optional[str] = Field(None, description="Search query text")
    node_type: Optional[str] = Field(None, description="Type of nodes to recall")
    node_id: Optional[str] = Field(None, description="Specific node ID to recall")
    scope: Optional[GraphScope] = Field(None, description="Scope to search in")
    limit: int = Field(10, description="Maximum number of results")

    model_config = ConfigDict(extra="forbid", defer_build=True)


class ForgetParams(BaseModel):
    """Parameters for FORGET action."""

    channel_id: Optional[str] = Field(None, description="Channel ID for context")
    node: GraphNode
    reason: str
    no_audit: bool = False

    model_config = ConfigDict(extra="forbid", defer_build=True)

    @property
    def scope(self) -> GraphScope:
        return self.node.scope


class TaskCompleteParams(BaseModel):
    """Parameters for TASK_COMPLETE action."""

    channel_id: Optional[str] = Field(None, description="Channel ID for context")
    completion_reason: str = "Task completed successfully"
    context: Optional[Dict[str, Union[str, List[str]]]] = Field(default=None)
    positive_moment: Optional[str] = Field(None, description="Optional note about positive vibes/joy from this task")
    persist_images: bool = Field(
        default=False,
        description="If True, preserve task images after completion. Default False purges images for privacy/storage.",
    )

    model_config = ConfigDict(extra="forbid", defer_build=True)


class DreamConsolidationParams(BaseModel):
    """
    Parameters for MEMORIZE action during DREAM state - creates exactly 3 edges.

    The dream consolidation process weaves memories together through:
    1. CONNECTS - Linking two memories that share a pattern (past-oriented)
    2. IMPLIES - Extracting behavioral insight from patterns (present-oriented)
    3. ASPIRES_TO - Defining who the agent wants to become (future-oriented)

    This creates triangulated, temporally-complete graph structures that
    move the agent toward sustainable adaptive coherence (M-1).
    """

    channel_id: Optional[str] = Field(None, description="Channel ID (typically 'dream')")

    # Edge 1: CONNECTS - Link two memories
    connect_from_id: str = Field(..., description="Source memory node ID to connect")
    connect_to_id: str = Field(..., description="Target memory node ID to connect")
    connect_pattern: str = Field(..., description="The pattern that links these memories")

    # Edge 2: IMPLIES - Behavioral insight
    pattern_insight: str = Field(..., description="The insight extracted from this pattern")
    implied_action: str = Field(..., description="How the agent should act differently")

    # Edge 3: ASPIRES_TO - Future aspiration
    aspiration: str = Field(..., description="Description of the ideal state to aspire to")
    aspiration_category: str = Field(
        default="growth", description="Category of aspiration: growth, coherence, service, understanding, connection"
    )

    # Optional context
    reflection_notes: Optional[str] = Field(None, description="Additional reflection on this consolidation")

    model_config = ConfigDict(extra="forbid", defer_build=True)
