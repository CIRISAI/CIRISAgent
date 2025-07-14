"""
Tool execution schemas for typed tool handler operations.

Replaces Dict[str, Any] usage in tool handlers.
"""

from typing import Optional, Dict, Any, Union
from pydantic import BaseModel, Field, ConfigDict
from uuid import UUID

class ToolExecutionArgs(BaseModel):
    """Typed arguments for tool execution."""
    correlation_id: Optional[Union[str, UUID]] = Field(None, description="Correlation ID for tracking tool execution")
    thought_id: Optional[str] = Field(None, description="ID of the thought triggering this tool")
    task_id: Optional[str] = Field(None, description="ID of the task associated with this tool")
    channel_id: Optional[str] = Field(None, description="Channel ID where the tool is being executed")
    timeout_seconds: float = Field(30.0, description="Timeout for tool execution in seconds")
    
    # Additional dynamic parameters for specific tools
    tool_specific_params: Dict[str, Any] = Field(
        default_factory=dict,
        description="Tool-specific parameters that vary by tool type"
    )
    
    model_config = ConfigDict(extra="allow")  # Allow extra fields for tool-specific params
    
    def get_all_params(self) -> Dict[str, Any]:
        """Get all parameters including tool-specific ones."""
        base_params = self.model_dump(exclude={"tool_specific_params"})
        # Merge with tool-specific params
        return {**base_params, **self.tool_specific_params}

class ToolHandlerContext(BaseModel):
    """Context for tool handler operations."""
    tool_name: str = Field(..., description="Name of the tool being executed")
    handler_name: str = Field(..., description="Name of the handler executing the tool")
    bot_instance: Optional[Any] = Field(None, description="Bot/client instance for tool execution")
    
    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)