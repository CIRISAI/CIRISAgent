"""
Context schemas for CIRIS Trinity Architecture.

Type-safe contexts for action dispatch and processing.
"""

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from ciris_engine.schemas.conscience.core import EpistemicData

from ..conscience.results import ConscienceResult
from .enums import HandlerActionType
from .system_context import ChannelContext


class DispatchContext(BaseModel):
    """Type-safe context for action handler dispatch.

    This replaces the generic Dict[str, Any] with proper typed fields
    for mission-critical production use. All core fields are REQUIRED.
    """

    # Core identification - ALL REQUIRED
    channel_context: ChannelContext = Field(..., description="Channel context where action originated")
    author_id: str = Field(..., description="ID of user/entity initiating action")
    author_name: str = Field(..., description="Display name of initiator")

    # Service references - ALL REQUIRED
    origin_service: str = Field(..., description="Service that originated the request")
    handler_name: str = Field(..., description="Handler processing this action")

    # Action context - ALL REQUIRED
    action_type: HandlerActionType = Field(..., description="Type of action being handled")
    thought_id: str = Field(..., description="Associated thought ID")
    task_id: str = Field(..., description="Associated task ID")
    source_task_id: str = Field(..., description="Source task ID from thought")

    # Event details - ALL REQUIRED
    event_summary: str = Field(..., description="Summary of the event/action")
    event_timestamp: str = Field(..., description="ISO8601 timestamp of event")

    # Additional context - REQUIRED with sensible defaults
    wa_id: Optional[str] = Field(None, description="Wise Authority ID if applicable")
    wa_authorized: bool = Field(False, description="Whether WA authorized this action")
    wa_context: Optional[str] = Field(None, description="WA context if applicable")

    # conscience and processing context - OPTIONAL
    conscience_failure_context: Optional[ConscienceResult] = Field(None, description="Context from conscience failures")
    epistemic_data: Optional[EpistemicData] = Field(None, description="Epistemic faculty evaluation data")

    # Correlation tracking
    correlation_id: Optional[str] = Field(None, description="Correlation ID for distributed tracing")
    span_id: Optional[str] = Field(None, description="Span ID for tracing")
    trace_id: Optional[str] = Field(None, description="Trace ID for distributed tracing")

    model_config = ConfigDict(extra="forbid")  # Strict - no extra fields allowed


__all__ = ["DispatchContext"]
