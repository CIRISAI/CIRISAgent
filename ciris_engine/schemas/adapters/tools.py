"""
Tool schemas for adapter-provided tools.

Tools are provided by adapters (Discord, API, CLI) not by the runtime.
This is the single source of truth for all tool-related schemas.
"""
from typing import Dict, List, Optional, Union, Any
from enum import Enum
from pydantic import BaseModel, Field, ConfigDict


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
    properties: Dict[str, Any] = Field(..., description="Parameter properties")
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
    
    model_config = ConfigDict(extra="forbid")


class ToolResult(BaseModel):
    """Result from tool execution."""
    success: bool = Field(..., description="Whether execution succeeded")
    data: Optional[Dict[str, Any]] = Field(None, description="Result data")
    error: Optional[str] = Field(None, description="Error message if failed")
    
    model_config = ConfigDict(extra="forbid")


class ToolExecutionResult(BaseModel):
    """Complete tool execution result with metadata."""
    tool_name: str = Field(..., description="Name of executed tool")
    status: ToolExecutionStatus = Field(..., description="Execution status")
    success: bool = Field(..., description="Whether execution succeeded")
    data: Optional[Dict[str, Any]] = Field(None, description="Result data")
    error: Optional[str] = Field(None, description="Error message if failed")
    correlation_id: str = Field(..., description="Correlation ID for tracking")
    
    model_config = ConfigDict(extra="forbid")


__all__ = [
    "ToolExecutionStatus",
    "ToolParameterSchema", 
    "ToolInfo",
    "ToolResult",
    "ToolExecutionResult"
]