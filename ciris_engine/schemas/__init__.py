"""
Contract-driven architecture schemas.

This module provides typed replacements for all Dict[str, Any] usage
in the CIRIS codebase, ensuring type safety and validation throughout.
"""

# Re-export all schemas for convenience

from .actions import DeferParams as DeferParameters
from .actions import ForgetParams as ForgetParameters
from .actions import MemorizeParams as MemorizeParameters
from .actions import ObserveParams as ObserveParameters
from .actions import PonderParams as PonderParameters
from .actions import RecallParams as RecallParameters
from .actions import RejectParams as RejectParameters
from .actions import SpeakParams as SpeakParameters
from .actions import TaskCompleteParams as TaskCompleteParameters
from .actions import ToolParams as ToolParameters
from .conscience.results import ConscienceResult
from .handlers.contexts import (
    BaseActionContext,
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
from .handlers.schemas import ActionContext, ActionParameters, HandlerContext, HandlerResult
from .platform import PlatformCapabilities, PlatformRequirement, PlatformRequirementSet
from .processors.cognitive import DreamState, PlayState, ShutdownState, SolitudeState, WakeupState, WorkState
from .services.metadata import ServiceMetadata
from .services.requests import (
    AuditRequest,
    AuditResponse,
    LLMRequest,
    LLMResponse,
    MemorizeRequest,
    MemorizeResponse,
    RecallRequest,
    RecallResponse,
    ServiceRequest,
    ServiceResponse,
    ToolExecutionRequest,
    ToolExecutionResponse,
)

# Faculty assessments removed - merged into consciences


__all__ = [
    # Service schemas
    "ServiceMetadata",
    "ServiceRequest",
    "ServiceResponse",
    "MemorizeRequest",
    "MemorizeResponse",
    "RecallRequest",
    "RecallResponse",
    "ToolExecutionRequest",
    "ToolExecutionResponse",
    "LLMRequest",
    "LLMResponse",
    "AuditRequest",
    "AuditResponse",
    # Action contexts
    "BaseActionContext",
    "SpeakContext",
    "ToolContext",
    "ObserveContext",
    "MemorizeContext",
    "RecallContext",
    "ForgetContext",
    "RejectContext",
    "PonderContext",
    "DeferContext",
    "TaskCompleteContext",
    # Action parameters
    "SpeakParameters",
    "ToolParameters",
    "ObserveParameters",
    "MemorizeParameters",
    "RecallParameters",
    "ForgetParameters",
    "RejectParameters",
    "PonderParameters",
    "DeferParameters",
    "TaskCompleteParameters",
    # Cognitive states
    "WakeupState",
    "WorkState",
    "PlayState",
    "SolitudeState",
    "DreamState",
    "ShutdownState",
    # Handler schemas
    "HandlerContext",
    "HandlerResult",
    "ActionContext",
    "ActionParameters",
    # conscience results
    "ConscienceResult",
    # Platform requirements
    "PlatformRequirement",
    "PlatformCapabilities",
    "PlatformRequirementSet",
]
