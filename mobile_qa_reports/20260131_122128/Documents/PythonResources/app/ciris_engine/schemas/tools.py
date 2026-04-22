"""
Tool schemas for CLI tools testing.

These schemas are used by the CLI tools test suite.
"""

from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from ciris_engine.schemas.types import ConfigValue, JSONDict


class ParameterType(str, Enum):
    """Parameter types for tools."""

    STRING = "string"
    NUMBER = "number"
    BOOLEAN = "boolean"
    OBJECT = "object"
    ARRAY = "array"


class ToolStatus(str, Enum):
    """Status of tool execution."""

    SUCCESS = "success"
    ERROR = "error"
    TIMEOUT = "timeout"
    NOT_FOUND = "not_found"
    UNAUTHORIZED = "unauthorized"


class ToolParameter(BaseModel):
    """Definition of a tool parameter."""

    name: str = Field(..., description="Parameter name")
    type: ParameterType = Field(..., description="Parameter type")
    description: str = Field(..., description="Parameter description")
    required: bool = Field(True, description="Whether parameter is required")
    default: Optional[ConfigValue] = Field(None, description="Default value if not provided")

    model_config = ConfigDict(extra="forbid")


class Tool(BaseModel):
    """Tool definition."""

    name: str = Field(..., description="Tool name")
    display_name: str = Field(..., description="Display name for the tool")
    description: str = Field(..., description="What the tool does")
    category: str = Field("general", description="Tool category")
    parameters: List[ToolParameter] = Field(default_factory=list, description="Tool parameters")

    model_config = ConfigDict(extra="forbid")


class ToolResult(BaseModel):
    """Result from tool execution."""

    status: ToolStatus = Field(..., description="Execution status")
    output: Optional[JSONDict] = Field(None, description="Tool output data")
    error: Optional[str] = Field(None, description="Error message if failed")
    execution_time: Optional[float] = Field(None, description="Execution time in seconds")
    timestamp: Optional[datetime] = Field(None, description="When the tool was executed")

    model_config = ConfigDict(extra="forbid")


__all__ = ["ParameterType", "ToolStatus", "ToolParameter", "Tool", "ToolResult"]
