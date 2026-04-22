"""
Audit protocol schemas.

Type-safe schemas for audit service operations.
"""

from datetime import datetime, timezone
from typing import Dict, Optional

from pydantic import BaseModel, ConfigDict, Field


class AuditActionContext(BaseModel):
    """Context for an audited action."""

    thought_id: str = Field(..., description="ID of the thought initiating action")
    task_id: str = Field(..., description="ID of the associated task")
    handler_name: str = Field(..., description="Name of the action handler")
    parameters: Dict[str, str] = Field(default_factory=dict, description="Action parameters")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    model_config = ConfigDict(extra="forbid")


class AuditConscienceResult(BaseModel):
    """Result from a conscience check in audit context."""

    allowed: bool = Field(..., description="Whether action is allowed")
    reason: Optional[str] = Field(None, description="Reason for allow/deny")
    modifications: Dict[str, str] = Field(default_factory=dict, description="Suggested modifications")
    risk_level: Optional[str] = Field(None, description="Assessed risk level")

    model_config = ConfigDict(extra="forbid")


class AuditRequest(BaseModel):
    """A request to create an audit entry."""

    entry_id: str = Field(..., description="Unique audit entry ID")
    timestamp: datetime = Field(..., description="When the event occurred")
    entity_id: str = Field(..., description="ID of entity being audited")
    event_type: str = Field(..., description="Type of event")
    actor: str = Field(..., description="Who/what performed the action")
    details: Dict[str, str] = Field(..., description="Event details")
    outcome: Optional[str] = Field(None, description="Event outcome")

    model_config = ConfigDict(extra="forbid")


__all__ = ["AuditActionContext", "AuditConscienceResult", "AuditRequest"]
