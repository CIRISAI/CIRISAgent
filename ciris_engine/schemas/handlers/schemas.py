"""
Handler schemas for contract-driven architecture.

Replaces Dict[str, Any] in handler contexts and results.
"""

from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, ConfigDict, Field

from ..actions import DeferParams as DeferParameters
from ..actions import ForgetParams as ForgetParameters
from ..actions import MemorizeParams as MemorizeParameters
from ..actions import ObserveParams as ObserveParameters
from ..actions import PonderParams as PonderParameters
from ..actions import RecallParams as RecallParameters
from ..actions import RejectParams as RejectParameters
from ..actions import SpeakParams as SpeakParameters
from ..actions import TaskCompleteParams as TaskCompleteParameters
from ..actions import ToolParams as ToolParameters
from ..secrets.service import DecapsulationContext
from ..services.metadata import ServiceMetadata
from .contexts import (
    DeferContext,
    ForgetContext,
    MemorizeContext,
    ObserveContext,
    PonderContext,
    RecallContext,
    RejectContext,
    SpeakContext,
    TaskCompleteContext,
    ToolContext,
)

# Union types for contexts and parameters
ActionContext = Union[
    SpeakContext,
    ToolContext,
    ObserveContext,
    MemorizeContext,
    RecallContext,
    ForgetContext,
    RejectContext,
    PonderContext,
    DeferContext,
    TaskCompleteContext,
]

ActionParameters = Union[
    SpeakParameters,
    ToolParameters,
    ObserveParameters,
    MemorizeParameters,
    RecallParameters,
    ForgetParameters,
    RejectParameters,
    PonderParameters,
    DeferParameters,
    TaskCompleteParameters,
]


class HandlerContext(BaseModel):
    """Typed context for all handlers."""

    action_type: str = Field(..., description="Type of action being handled")
    action_context: ActionContext = Field(..., description="Action-specific context")
    action_parameters: ActionParameters = Field(..., description="Action-specific parameters")
    metadata: ServiceMetadata = Field(..., description="Service metadata")

    model_config = ConfigDict(extra="forbid")


class HandlerResult(BaseModel):
    """Typed result from all handlers."""

    success: bool = Field(..., description="Whether the handler succeeded")
    message: Optional[str] = Field(None, description="Result message")
    data: Optional[Dict[str, Union[str, int, float, bool, List[Any]]]] = Field(None, description="Additional result data")
    error: Optional[str] = Field(None, description="Error message if failed")

    model_config = ConfigDict(extra="forbid")


class HandlerDecapsulatedParams(BaseModel):
    """Schema for decapsulated handler parameters."""

    action_type: str = Field(..., description="Type of action being handled")
    action_params: Dict[str, Union[str, int, float, bool, List[Any], Dict[str, Any]]] = Field(
        ..., description="Decapsulated action parameters"
    )
    context: DecapsulationContext = Field(..., description="Decapsulation context")

    model_config = ConfigDict(extra="forbid")
