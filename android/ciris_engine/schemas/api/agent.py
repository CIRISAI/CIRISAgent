"""
Agent API response schemas - fully typed replacements for Dict[str, Any].
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from ciris_engine.schemas.types import JSONDict


class MessageContext(BaseModel):
    """Context information for messages."""

    channel_id: Optional[str] = Field(None, description="Channel/conversation ID")
    thread_id: Optional[str] = Field(None, description="Thread ID if in thread")
    reply_to_id: Optional[str] = Field(None, description="Message being replied to")
    metadata: Optional[JSONDict] = Field(None, description="Additional metadata")


class AgentLineage(BaseModel):
    """Agent lineage information."""

    model: str = Field(..., description="Base model used")
    version: str = Field(..., description="Agent version")
    parent_id: Optional[str] = Field(None, description="Parent agent ID if derived")
    creation_context: str = Field(..., description="How agent was created")
    adaptations: List[str] = Field(default_factory=list, description="Applied adaptations")


class ServiceAvailability(BaseModel):
    """Service availability counts by type."""

    graph: int = Field(0, description="Graph services available")
    core: int = Field(0, description="Core services available")
    infrastructure: int = Field(0, description="Infrastructure services available")
    governance: int = Field(0, description="Governance services available")
    special: int = Field(0, description="Special services available")


class ActiveTask(BaseModel):
    """Active task information."""

    task_id: str = Field(..., description="Unique task ID")
    type: str = Field(..., description="Task type")
    status: str = Field(..., description="Current status")
    description: Optional[str] = Field(None, description="Task description")
    created_at: datetime = Field(..., description="When task was created")
    priority: Optional[str] = Field(None, description="Task priority")
