"""
Audit Schemas v1 - Audit event tracking for CIRIS Agent

Provides schemas for comprehensive audit logging of all agent actions and system events.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional, Tuple

from pydantic import BaseModel, ConfigDict, Field


class AuditEventType(str, Enum):
    """Types of audit events"""

    # Handler actions
    HANDLER_ACTION_SPEAK = "handler_action_speak"
    HANDLER_ACTION_MEMORIZE = "handler_action_memorize"
    HANDLER_ACTION_RECALL = "handler_action_recall"
    HANDLER_ACTION_FORGET = "handler_action_forget"
    HANDLER_ACTION_TOOL = "handler_action_tool"
    HANDLER_ACTION_DEFER = "handler_action_defer"
    HANDLER_ACTION_REJECT = "handler_action_reject"
    HANDLER_ACTION_PONDER = "handler_action_ponder"
    HANDLER_ACTION_OBSERVE = "handler_action_observe"
    HANDLER_ACTION_TASK_COMPLETE = "handler_action_task_complete"

    # System events
    SYSTEM_EVENT = "system_event"
    SECURITY_EVENT = "security_event"
    CONFIG_CHANGE = "config_change"
    SERVICE_LIFECYCLE = "service_lifecycle"
    ERROR_EVENT = "error_event"


class EventOutcome(str, Enum):
    """Outcome of an audited event"""

    SUCCESS = "success"
    FAILURE = "failure"
    PARTIAL = "partial"
    SKIPPED = "skipped"


class EventPayload(BaseModel):
    """Typed event payload data"""

    action: Optional[str] = Field(default=None, description="Action taken")
    result: Optional[str] = Field(default=None, description="Result of action")
    error: Optional[str] = Field(default=None, description="Error message if failed")
    duration_ms: Optional[float] = Field(default=None, ge=0.0, description="Duration in milliseconds")

    # Additional context
    user_id: Optional[str] = Field(default=None, description="User involved")
    channel_id: Optional[str] = Field(default=None, description="Channel involved")
    service_name: Optional[str] = Field(default=None, description="Service involved")

    model_config = ConfigDict(extra="forbid")


class AuditEvent(BaseModel):
    """Schema for audit events"""

    event_type: AuditEventType = Field(description="Type of audit event")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Event timestamp")
    thought_id: Optional[str] = Field(default=None, description="Associated thought ID")
    task_id: Optional[str] = Field(default=None, description="Associated task ID")
    handler_name: str = Field(description="Name of handler that generated event")
    event_data: EventPayload = Field(description="Structured event data")
    outcome: EventOutcome = Field(default=EventOutcome.SUCCESS, description="Event outcome")

    model_config = ConfigDict(extra="forbid")


class AuditLogEntry(BaseModel):
    """Schema for audit log entries"""

    event_id: str = Field(description="Unique event identifier")
    event_timestamp: datetime = Field(description="When event occurred")
    event_type: str = Field(description="Type of event")
    originator_id: str = Field(description="ID of originating component")
    target_id: Optional[str] = Field(default=None, description="ID of target component")
    event_summary: str = Field(description="Human-readable event summary")
    event_payload: Optional[EventPayload] = Field(default=None, description="Structured event data")

    # Additional metadata
    agent_template: Optional[str] = Field(default=None, description="Agent template in use")
    round_number: Optional[int] = Field(default=None, ge=0, description="Processing round number")
    thought_id: Optional[str] = Field(default=None, description="Associated thought ID")
    task_id: Optional[str] = Field(default=None, description="Associated task ID")

    # Hash chain fields
    previous_hash: Optional[str] = Field(default=None, description="Hash of previous entry for tamper detection")
    entry_hash: Optional[str] = Field(default=None, description="Hash of this entry")

    model_config = ConfigDict(extra="forbid")


class AuditSummary(BaseModel):
    """Summary statistics for audit entries"""

    total_events: int = Field(ge=0, description="Total number of events")
    events_by_type: List[Tuple[str, int]] = Field(default_factory=list, description="Count by event type")
    events_by_outcome: List[Tuple[str, int]] = Field(default_factory=list, description="Count by outcome")
    error_count: int = Field(ge=0, default=0, description="Number of error events")
    security_event_count: int = Field(ge=0, default=0, description="Number of security events")

    # Time range
    earliest_event: Optional[datetime] = Field(default=None, description="Timestamp of earliest event")
    latest_event: Optional[datetime] = Field(default=None, description="Timestamp of latest event")

    model_config = ConfigDict(extra="forbid")


class AuditQuery(BaseModel):
    """Query parameters for audit log search"""

    event_types: Optional[List[AuditEventType]] = Field(default=None, description="Filter by event types")
    start_time: Optional[datetime] = Field(default=None, description="Start of time range")
    end_time: Optional[datetime] = Field(default=None, description="End of time range")
    thought_id: Optional[str] = Field(default=None, description="Filter by thought ID")
    task_id: Optional[str] = Field(default=None, description="Filter by task ID")
    handler_name: Optional[str] = Field(default=None, description="Filter by handler name")
    outcome: Optional[EventOutcome] = Field(default=None, description="Filter by outcome")
    limit: int = Field(default=100, ge=1, le=1000, description="Maximum results to return")

    model_config = ConfigDict(extra="forbid")


__all__ = [
    "AuditEventType",
    "EventOutcome",
    "EventPayload",
    "AuditEvent",
    "AuditLogEntry",
    "AuditSummary",
    "AuditQuery",
]
