"""
Extended identity schemas for creation ceremonies and continuity awareness.

Provides type-safe structures for agent lifecycle management.
"""

from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from ciris_engine.schemas.runtime.enums import HandlerActionType


class IdentityLineage(BaseModel):
    """Records the collaborative creation of an agent."""

    creator_agent_id: str = Field(..., description="ID of the facilitating CIRIS agent")
    creator_human_id: str = Field(..., description="Unique identifier of human collaborator")
    wise_authority_id: str = Field(..., description="WA who sanctioned the creation")
    creation_ceremony_id: str = Field(..., description="Unique ID of the creation ceremony event")

    model_config = ConfigDict(extra="forbid")


class IdentityUpdateEntry(BaseModel):
    """Audit log entry for identity evolution."""

    version: int = Field(..., description="New version number after change")
    timestamp: datetime = Field(..., description="Timestamp of update")
    attribute_changed: str = Field(..., description="Key of modified attribute")
    old_value: str = Field(..., description="Previous value (serialized)")
    new_value: str = Field(..., description="New value (serialized)")
    justification: str = Field(..., description="Reason provided by human collaborator")
    change_hash: str = Field(..., description="Hash of old and new values for integrity")
    wise_authority_approval: str = Field(..., description="WA approval signature")

    model_config = ConfigDict(extra="forbid")


class IdentityRoot(BaseModel):
    """
    The foundational identity of a CIRIS agent.

    This is the first node created in an agent's graph database and serves as the
    ultimate source of truth for the agent's existence. All other nodes have a
    relationship back to this root, establishing clear provenance for all knowledge.
    """

    # Core Identity - Immutable after creation
    name: str = Field(..., description="Agent's unique given name (e.g., Teacher-Alpha-01)")
    purpose: str = Field(..., description="Clear, concise statement of agent's reason for existence")
    description: str = Field(..., description="Detailed description of role and function")
    lineage: IdentityLineage = Field(..., description="Creation provenance")
    covenant_hash: str = Field(..., description="SHA-256 hash of covenant at creation time")
    creation_timestamp: datetime = Field(..., description="Timestamp of creation")

    # Evolution Tracking
    version: int = Field(default=1, description="Increments with each approved change")
    update_log: List[IdentityUpdateEntry] = Field(
        default_factory=list, description="Append-only log of all approved identity changes"
    )

    # Capabilities and Configuration
    permitted_actions: List[HandlerActionType] = Field(..., description="Definitive list of allowed actions")
    dsdma_overrides: Dict[str, str] = Field(default_factory=dict, description="DSDMA overrides")
    csdma_overrides: Dict[str, str] = Field(default_factory=dict, description="CSDMA overrides")
    action_selection_pdma_overrides: Dict[str, str] = Field(
        default_factory=dict, description="Action selection overrides"
    )
    conscience_config: Dict[str, str] = Field(default_factory=dict, description="conscience configuration")

    # Continuity Awareness
    last_shutdown_memory: Optional[str] = Field(
        None, description="Node ID of the last shutdown continuity awareness memory"
    )
    reactivation_count: int = Field(default=0, description="Number of times agent has been reactivated")

    model_config = ConfigDict(extra="forbid")


class CreationCeremonyRequest(BaseModel):
    """Request to create a new CIRIS agent through collaborative ceremony."""

    # Human Collaborator
    human_id: str = Field(..., description="Unique identifier of requesting human")
    human_name: str = Field(..., description="Name of human collaborator")

    # Agent Template (from profile YAML)
    template_profile: str = Field(..., description="Profile YAML content as template")
    proposed_name: str = Field(..., description="Proposed unique name for new agent")
    proposed_purpose: str = Field(..., description="Clear statement of agent's purpose")
    proposed_description: str = Field(..., description="Detailed role description")

    # Justification
    creation_justification: str = Field(..., description="Why this agent should exist")
    expected_capabilities: List[str] = Field(..., description="What the agent will be able to do")
    ethical_considerations: str = Field(..., description="Ethical implications considered")

    # WA Approval
    wise_authority_id: Optional[str] = Field(None, description="Pre-approved by WA")
    approval_signature: Optional[str] = Field(None, description="WA approval signature")

    model_config = ConfigDict(extra="forbid")


class CreationCeremonyResponse(BaseModel):
    """Response from agent creation ceremony."""

    success: bool = Field(..., description="Whether creation succeeded")
    agent_id: Optional[str] = Field(None, description="ID of created agent")
    agent_name: Optional[str] = Field(None, description="Name of created agent")
    database_path: Optional[str] = Field(None, description="Path to agent's database")
    identity_root_hash: Optional[str] = Field(None, description="Hash of identity root")
    error_message: Optional[str] = Field(None, description="Error if creation failed")
    ceremony_transcript: List[str] = Field(default_factory=list, description="Log of ceremony steps")

    model_config = ConfigDict(extra="forbid")


class ScheduledTask(BaseModel):
    """
    A scheduled goal or future commitment.

    Tasks represent higher-level goals that generate Thoughts when triggered.
    This integrates with the DEFER time-based system for agent self-scheduling.
    """

    task_id: str = Field(..., description="Unique identifier")
    name: str = Field(..., description="Human-readable task name")
    goal_description: str = Field(..., description="What the task aims to achieve")
    status: str = Field(default="PENDING", description="PENDING, ACTIVE, COMPLETE, FAILED")

    # Scheduling - integrates with DEFER system
    defer_until: Optional[datetime] = Field(None, description="Timestamp for one-time execution")
    schedule_cron: Optional[str] = Field(None, description="Cron expression for recurring tasks")

    # Execution
    trigger_prompt: str = Field(..., description="Prompt for thought creation when triggered")
    origin_thought_id: str = Field(..., description="Thought that created this task")
    created_at: datetime = Field(..., description="Creation timestamp")
    last_triggered_at: Optional[datetime] = Field(None, description="Last execution timestamp")

    # Self-deferral tracking
    deferral_count: int = Field(default=0, description="Times agent has self-deferred")
    deferral_history: List[Dict[str, str]] = Field(
        default_factory=list, description="History of self-deferrals with reasons"
    )

    model_config = ConfigDict(extra="forbid")


class ScheduledTaskInfo(BaseModel):
    """Information about a scheduled task for API responses."""

    task_id: str = Field(..., description="Unique identifier")
    name: str = Field(..., description="Human-readable task name")
    goal_description: str = Field(..., description="What the task aims to achieve")
    status: str = Field(default="PENDING", description="PENDING, ACTIVE, COMPLETE, FAILED")
    defer_until: Optional[str] = Field(None, description="ISO timestamp for one-time execution")
    schedule_cron: Optional[str] = Field(None, description="Cron expression for recurring tasks")
    created_at: str = Field(..., description="Creation timestamp (ISO format)")
    last_triggered_at: Optional[str] = Field(None, description="Last execution timestamp (ISO format)")
    deferral_count: int = Field(default=0, description="Times agent has self-deferred")

    model_config = ConfigDict(extra="forbid")


class ShutdownContext(BaseModel):
    """Context provided to agent during graceful shutdown."""

    is_terminal: bool = Field(..., description="Whether shutdown is permanent")
    reason: str = Field(..., description="Reason for shutdown")
    expected_reactivation: Optional[datetime] = Field(None, description="Timestamp of expected reactivation")
    agreement_context: Optional[str] = Field(None, description="Message if shutdown is at previously negotiated time")
    initiated_by: str = Field(..., description="Who initiated the shutdown")
    allow_deferral: bool = Field(default=True, description="Whether agent can defer the shutdown")

    model_config = ConfigDict(extra="forbid")


class ContinuityAwarenessMemory(BaseModel):
    """Final memory created during graceful shutdown."""

    shutdown_context: ShutdownContext = Field(..., description="Shutdown context")
    final_thoughts: str = Field(..., description="Agent's final reflections")
    unfinished_tasks: List[str] = Field(default_factory=list, description="Task IDs that were pending")
    preservation_timestamp: datetime = Field(..., description="Timestamp of preservation")

    # Continuity planning
    reactivation_instructions: Optional[str] = Field(None, description="Agent's notes for its future sel")
    deferred_goals: List[Dict[str, str]] = Field(default_factory=list, description="Goals to pursue upon reactivation")

    model_config = ConfigDict(extra="forbid")


class IdentityEvolutionRequest(BaseModel):
    """Request to evolve an agent's identity (requires WA approval)."""

    attribute_path: str = Field(..., description="Dot-notation path to attribute")
    new_value: str = Field(..., description="Proposed new value (serialized)")
    justification: str = Field(..., description="Detailed reason for change")
    impact_assessment: str = Field(..., description="Expected impact on agent behavior")
    human_sponsor_id: str = Field(..., description="Human requesting the change")
    urgency: str = Field(default="normal", description="normal, high, critical")

    model_config = ConfigDict(extra="forbid")


# Graph node type extension for Identity Root
class IdentityNodeType(str, Enum):
    """Extended node types for identity system."""

    IDENTITY_ROOT = "identity_root"
    CREATION_CEREMONY = "creation_ceremony"
    CONTINUITY_AWARENESS = "continuity_awareness"
    SCHEDULED_TASK = "scheduled_task"


__all__ = [
    "IdentityLineage",
    "IdentityUpdateEntry",
    "IdentityRoot",
    "CreationCeremonyRequest",
    "CreationCeremonyResponse",
    "ScheduledTask",
    "ShutdownContext",
    "ContinuityAwarenessMemory",
    "IdentityEvolutionRequest",
    "IdentityNodeType",
]
