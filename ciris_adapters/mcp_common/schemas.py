"""
MCP Shared Schemas.

Common schema definitions for MCP tools, resources, and prompts.
Used by both client and server implementations.
"""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class MCPToolInputSchema(BaseModel):
    """JSON Schema for tool input parameters."""

    type: str = Field("object", description="Schema type (usually 'object')")
    properties: Dict[str, Any] = Field(default_factory=dict, description="Property definitions")
    required: List[str] = Field(default_factory=list, description="Required properties")
    additionalProperties: bool = Field(False, description="Allow additional properties")

    model_config = ConfigDict(extra="allow")  # Allow additional JSON Schema fields


class MCPToolInfo(BaseModel):
    """MCP tool definition."""

    name: str = Field(..., description="Tool name")
    description: str = Field(..., description="Tool description")
    inputSchema: MCPToolInputSchema = Field(..., description="Input parameter schema")

    model_config = ConfigDict(extra="forbid")


class MCPToolCallParams(BaseModel):
    """Parameters for tools/call request."""

    name: str = Field(..., description="Tool name to call")
    arguments: Dict[str, Any] = Field(default_factory=dict, description="Tool arguments")

    model_config = ConfigDict(extra="forbid")


class MCPToolCallResult(BaseModel):
    """Result from tools/call request."""

    content: List[Dict[str, Any]] = Field(..., description="Result content")
    isError: bool = Field(False, description="Whether result is an error")

    model_config = ConfigDict(extra="forbid")


class MCPResourceInfo(BaseModel):
    """MCP resource definition."""

    uri: str = Field(..., description="Resource URI")
    name: str = Field(..., description="Resource name")
    description: Optional[str] = Field(None, description="Resource description")
    mimeType: Optional[str] = Field(None, description="Resource MIME type")

    model_config = ConfigDict(extra="forbid")


class MCPResourceContent(BaseModel):
    """Content from a resource read."""

    uri: str = Field(..., description="Resource URI")
    mimeType: Optional[str] = Field(None, description="Content MIME type")
    text: Optional[str] = Field(None, description="Text content")
    blob: Optional[str] = Field(None, description="Base64-encoded binary content")

    model_config = ConfigDict(extra="forbid")


class MCPResourceReadParams(BaseModel):
    """Parameters for resources/read request."""

    uri: str = Field(..., description="Resource URI to read")

    model_config = ConfigDict(extra="forbid")


class MCPResourceReadResult(BaseModel):
    """Result from resources/read request."""

    contents: List[MCPResourceContent] = Field(..., description="Resource contents")

    model_config = ConfigDict(extra="forbid")


class MCPPromptArgument(BaseModel):
    """MCP prompt argument definition."""

    name: str = Field(..., description="Argument name")
    description: Optional[str] = Field(None, description="Argument description")
    required: bool = Field(False, description="Whether argument is required")

    model_config = ConfigDict(extra="forbid")


class MCPPromptInfo(BaseModel):
    """MCP prompt definition."""

    name: str = Field(..., description="Prompt name")
    description: Optional[str] = Field(None, description="Prompt description")
    arguments: List[MCPPromptArgument] = Field(default_factory=list, description="Prompt arguments")

    model_config = ConfigDict(extra="forbid")


class MCPPromptMessage(BaseModel):
    """Message in a prompt response."""

    role: str = Field(..., description="Message role (user/assistant)")
    content: Dict[str, Any] = Field(..., description="Message content")

    model_config = ConfigDict(extra="forbid")


class MCPPromptGetParams(BaseModel):
    """Parameters for prompts/get request."""

    name: str = Field(..., description="Prompt name")
    arguments: Dict[str, str] = Field(default_factory=dict, description="Prompt arguments")

    model_config = ConfigDict(extra="forbid")


class MCPPromptGetResult(BaseModel):
    """Result from prompts/get request."""

    description: Optional[str] = Field(None, description="Prompt description")
    messages: List[MCPPromptMessage] = Field(..., description="Prompt messages")

    model_config = ConfigDict(extra="forbid")


class MCPListToolsResult(BaseModel):
    """Result from tools/list request."""

    tools: List[MCPToolInfo] = Field(default_factory=list, description="Available tools")

    model_config = ConfigDict(extra="forbid")


class MCPListResourcesResult(BaseModel):
    """Result from resources/list request."""

    resources: List[MCPResourceInfo] = Field(default_factory=list, description="Available resources")

    model_config = ConfigDict(extra="forbid")


class MCPListPromptsResult(BaseModel):
    """Result from prompts/list request."""

    prompts: List[MCPPromptInfo] = Field(default_factory=list, description="Available prompts")

    model_config = ConfigDict(extra="forbid")


# Conversion utilities


def ciris_tool_to_mcp(tool_name: str, description: str, parameters: Dict[str, Any]) -> MCPToolInfo:
    """Convert a CIRIS tool definition to MCP format.

    Args:
        tool_name: Tool name
        description: Tool description
        parameters: Tool parameter schema (JSON Schema format)

    Returns:
        MCPToolInfo instance
    """
    return MCPToolInfo(
        name=tool_name,
        description=description,
        inputSchema=MCPToolInputSchema(
            type=parameters.get("type", "object"),
            properties=parameters.get("properties", {}),
            required=parameters.get("required", []),
        ),
    )


def mcp_tool_to_ciris(mcp_tool: MCPToolInfo) -> Dict[str, Any]:
    """Convert an MCP tool definition to CIRIS format.

    Args:
        mcp_tool: MCP tool info

    Returns:
        Dict with CIRIS tool schema fields
    """
    return {
        "name": mcp_tool.name,
        "description": mcp_tool.description,
        "parameters": {
            "type": mcp_tool.inputSchema.type,
            "properties": mcp_tool.inputSchema.properties,
            "required": mcp_tool.inputSchema.required,
        },
    }


__all__ = [
    "MCPToolInputSchema",
    "MCPToolInfo",
    "MCPToolCallParams",
    "MCPToolCallResult",
    "MCPResourceInfo",
    "MCPResourceContent",
    "MCPResourceReadParams",
    "MCPResourceReadResult",
    "MCPPromptArgument",
    "MCPPromptInfo",
    "MCPPromptMessage",
    "MCPPromptGetParams",
    "MCPPromptGetResult",
    "MCPListToolsResult",
    "MCPListResourcesResult",
    "MCPListPromptsResult",
    "ciris_tool_to_mcp",
    "mcp_tool_to_ciris",
]
