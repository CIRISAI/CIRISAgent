"""
Tool schemas for adapter-provided tools.

Tools are provided by adapters (Discord, API, CLI) not by the runtime.
This is the single source of truth for all tool-related schemas.
"""

from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from ciris_engine.schemas.platform import PlatformRequirement
from ciris_engine.schemas.types import JSONDict


class ToolExecutionStatus(str, Enum):
    """Status of tool execution."""

    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"
    NOT_FOUND = "not_found"
    UNAUTHORIZED = "unauthorized"


class ToolParameterSchema(BaseModel):
    """Schema definition for tool parameters."""

    type: str = Field(..., description="JSON Schema type")
    properties: JSONDict = Field(..., description="Parameter properties")
    required: List[str] = Field(default_factory=list, description="Required parameters")

    model_config = ConfigDict(extra="forbid")


class ToolInfo(BaseModel):
    """Information about a tool provided by an adapter."""

    name: str = Field(..., description="Tool name")
    description: str = Field(..., description="What the tool does")
    parameters: ToolParameterSchema = Field(..., description="Tool parameters schema")
    category: str = Field("general", description="Tool category")
    cost: float = Field(0.0, description="Cost to execute the tool")
    when_to_use: Optional[str] = Field(None, description="Guidance on when to use the tool")

    # Context enrichment: if True, this tool is automatically run during context gathering
    # and its results are added to the system snapshot for use in action selection
    context_enrichment: bool = Field(
        False,
        description="If True, tool is automatically run during context gathering to enrich ASPDMA prompt",
    )
    # Default parameters to use when running as context enrichment tool
    context_enrichment_params: Optional[JSONDict] = Field(
        None, description="Default parameters when running as context enrichment (e.g., {'domain': 'light'})"
    )

    # Platform requirements: security/platform features required to use this tool
    # If not satisfied, the tool will not be available in the agent's tool list
    platform_requirements: List[PlatformRequirement] = Field(
        default_factory=list,
        description="Platform security requirements (e.g., ANDROID_PLAY_INTEGRITY, DPOP)",
    )
    # Human-readable explanation of why platform requirements exist
    platform_requirements_rationale: Optional[str] = Field(
        None,
        description="Why these requirements exist (shown if requirements not met)",
    )

    model_config = ConfigDict(extra="forbid")


class ToolResult(BaseModel):
    """Result from tool execution."""

    success: bool = Field(..., description="Whether execution succeeded")
    data: Optional[JSONDict] = Field(None, description="Result data")
    error: Optional[str] = Field(None, description="Error message if failed")

    model_config = ConfigDict(extra="forbid")


class ToolExecutionResult(BaseModel):
    """Complete tool execution result with metadata."""

    tool_name: str = Field(..., description="Name of executed tool")
    status: ToolExecutionStatus = Field(..., description="Execution status")
    success: bool = Field(..., description="Whether execution succeeded")
    data: Optional[JSONDict] = Field(None, description="Result data")
    error: Optional[str] = Field(None, description="Error message if failed")
    correlation_id: str = Field(..., description="Correlation ID for tracking")

    model_config = ConfigDict(extra="forbid")


__all__ = ["ToolExecutionStatus", "ToolParameterSchema", "ToolInfo", "ToolResult", "ToolExecutionResult"]
