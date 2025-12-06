"""Tests for MCP common schemas."""

import pytest

from ciris_modular_services.mcp_common.schemas import (
    MCPListPromptsResult,
    MCPListResourcesResult,
    MCPListToolsResult,
    MCPPromptArgument,
    MCPPromptGetParams,
    MCPPromptGetResult,
    MCPPromptInfo,
    MCPPromptMessage,
    MCPResourceContent,
    MCPResourceInfo,
    MCPResourceReadParams,
    MCPResourceReadResult,
    MCPToolCallParams,
    MCPToolCallResult,
    MCPToolInfo,
    MCPToolInputSchema,
    ciris_tool_to_mcp,
    mcp_tool_to_ciris,
)


class TestMCPToolInputSchema:
    """Tests for MCPToolInputSchema model."""

    def test_default_schema(self) -> None:
        """Test default input schema."""
        schema = MCPToolInputSchema()
        assert schema.type == "object"
        assert schema.properties == {}
        assert schema.required == []
        assert schema.additionalProperties is False

    def test_with_properties(self) -> None:
        """Test schema with properties."""
        schema = MCPToolInputSchema(
            type="object",
            properties={
                "query": {"type": "string", "description": "Search query"},
                "limit": {"type": "integer", "default": 10},
            },
            required=["query"],
        )
        assert "query" in schema.properties
        assert "limit" in schema.properties
        assert schema.required == ["query"]


class TestMCPToolInfo:
    """Tests for MCPToolInfo model."""

    def test_create_tool_info(self) -> None:
        """Test creating tool info."""
        tool = MCPToolInfo(
            name="weather",
            description="Get weather information",
            inputSchema=MCPToolInputSchema(
                properties={"city": {"type": "string"}},
                required=["city"],
            ),
        )
        assert tool.name == "weather"
        assert tool.description == "Get weather information"
        assert tool.inputSchema.required == ["city"]


class TestMCPToolCallParams:
    """Tests for MCPToolCallParams model."""

    def test_create_call_params(self) -> None:
        """Test creating tool call params."""
        params = MCPToolCallParams(
            name="weather",
            arguments={"city": "New York"},
        )
        assert params.name == "weather"
        assert params.arguments == {"city": "New York"}

    def test_default_arguments(self) -> None:
        """Test default empty arguments."""
        params = MCPToolCallParams(name="simple_tool")
        assert params.arguments == {}


class TestMCPToolCallResult:
    """Tests for MCPToolCallResult model."""

    def test_success_result(self) -> None:
        """Test successful tool result."""
        result = MCPToolCallResult(
            content=[{"type": "text", "text": "Weather: Sunny"}],
            isError=False,
        )
        assert len(result.content) == 1
        assert result.isError is False

    def test_error_result(self) -> None:
        """Test error tool result."""
        result = MCPToolCallResult(
            content=[{"type": "text", "text": "Error: City not found"}],
            isError=True,
        )
        assert result.isError is True


class TestMCPResourceInfo:
    """Tests for MCPResourceInfo model."""

    def test_create_resource_info(self) -> None:
        """Test creating resource info."""
        resource = MCPResourceInfo(
            uri="file:///path/to/file.txt",
            name="File",
            description="A text file",
            mimeType="text/plain",
        )
        assert resource.uri == "file:///path/to/file.txt"
        assert resource.name == "File"
        assert resource.mimeType == "text/plain"


class TestMCPResourceContent:
    """Tests for MCPResourceContent model."""

    def test_text_content(self) -> None:
        """Test text resource content."""
        content = MCPResourceContent(
            uri="file:///test.txt",
            mimeType="text/plain",
            text="Hello, world!",
        )
        assert content.text == "Hello, world!"
        assert content.blob is None

    def test_binary_content(self) -> None:
        """Test binary resource content."""
        content = MCPResourceContent(
            uri="file:///image.png",
            mimeType="image/png",
            blob="iVBORw0KGgo...",  # Base64
        )
        assert content.blob is not None
        assert content.text is None


class TestMCPPromptInfo:
    """Tests for MCPPromptInfo model."""

    def test_create_prompt_info(self) -> None:
        """Test creating prompt info."""
        prompt = MCPPromptInfo(
            name="code_review",
            description="Review code for best practices",
            arguments=[
                MCPPromptArgument(
                    name="code",
                    description="Code to review",
                    required=True,
                ),
                MCPPromptArgument(
                    name="language",
                    description="Programming language",
                    required=False,
                ),
            ],
        )
        assert prompt.name == "code_review"
        assert len(prompt.arguments) == 2
        assert prompt.arguments[0].required is True


class TestMCPPromptMessage:
    """Tests for MCPPromptMessage model."""

    def test_create_message(self) -> None:
        """Test creating prompt message."""
        message = MCPPromptMessage(
            role="assistant",
            content={"type": "text", "text": "Here is my review..."},
        )
        assert message.role == "assistant"
        assert message.content["type"] == "text"


class TestMCPListResults:
    """Tests for list result models."""

    def test_list_tools_result(self) -> None:
        """Test tools list result."""
        result = MCPListToolsResult(
            tools=[
                MCPToolInfo(
                    name="tool1",
                    description="First tool",
                    inputSchema=MCPToolInputSchema(),
                ),
                MCPToolInfo(
                    name="tool2",
                    description="Second tool",
                    inputSchema=MCPToolInputSchema(),
                ),
            ]
        )
        assert len(result.tools) == 2

    def test_list_resources_result(self) -> None:
        """Test resources list result."""
        result = MCPListResourcesResult(
            resources=[
                MCPResourceInfo(uri="res1", name="Resource 1"),
            ]
        )
        assert len(result.resources) == 1

    def test_list_prompts_result(self) -> None:
        """Test prompts list result."""
        result = MCPListPromptsResult(
            prompts=[
                MCPPromptInfo(name="prompt1"),
            ]
        )
        assert len(result.prompts) == 1


class TestConversionUtilities:
    """Tests for conversion utilities."""

    def test_ciris_tool_to_mcp(self) -> None:
        """Test converting CIRIS tool to MCP format."""
        mcp_tool = ciris_tool_to_mcp(
            tool_name="my_tool",
            description="A helpful tool",
            parameters={
                "type": "object",
                "properties": {
                    "input": {"type": "string"},
                },
                "required": ["input"],
            },
        )
        assert mcp_tool.name == "my_tool"
        assert mcp_tool.description == "A helpful tool"
        assert mcp_tool.inputSchema.type == "object"
        assert "input" in mcp_tool.inputSchema.properties
        assert mcp_tool.inputSchema.required == ["input"]

    def test_mcp_tool_to_ciris(self) -> None:
        """Test converting MCP tool to CIRIS format."""
        mcp_tool = MCPToolInfo(
            name="mcp_tool",
            description="An MCP tool",
            inputSchema=MCPToolInputSchema(
                type="object",
                properties={"param": {"type": "string"}},
                required=["param"],
            ),
        )
        ciris_tool = mcp_tool_to_ciris(mcp_tool)

        assert ciris_tool["name"] == "mcp_tool"
        assert ciris_tool["description"] == "An MCP tool"
        assert ciris_tool["parameters"]["type"] == "object"
        assert "param" in ciris_tool["parameters"]["properties"]
        assert ciris_tool["parameters"]["required"] == ["param"]

    def test_roundtrip_conversion(self) -> None:
        """Test roundtrip conversion maintains data."""
        original_params = {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "limit": {"type": "integer"},
            },
            "required": ["query"],
        }

        mcp_tool = ciris_tool_to_mcp("test_tool", "Test description", original_params)
        ciris_tool = mcp_tool_to_ciris(mcp_tool)

        assert ciris_tool["name"] == "test_tool"
        assert ciris_tool["description"] == "Test description"
        assert ciris_tool["parameters"]["type"] == original_params["type"]
        assert ciris_tool["parameters"]["required"] == original_params["required"]
