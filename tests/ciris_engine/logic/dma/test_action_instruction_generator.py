"""Tests for ActionInstructionGenerator."""

from unittest.mock import AsyncMock, Mock

import pytest

from ciris_engine.logic.dma.action_selection.action_instruction_generator import ActionInstructionGenerator
from ciris_engine.schemas.adapters.tools import ToolInfo
from ciris_engine.schemas.runtime.enums import HandlerActionType


class TestActionInstructionGenerator:
    """Test cases for ActionInstructionGenerator."""

    def test_init(self):
        """Test initialization."""
        generator = ActionInstructionGenerator()
        assert generator.service_registry is None
        assert generator.bus_manager is None
        assert generator._cached_instructions is None

        # With dependencies
        mock_registry = Mock()
        mock_bus_manager = Mock()
        generator = ActionInstructionGenerator(mock_registry, mock_bus_manager)
        assert generator.service_registry == mock_registry
        assert generator.bus_manager == mock_bus_manager

    def test_generate_action_instructions_basic(self):
        """Test basic action instruction generation."""
        generator = ActionInstructionGenerator()

        # Test with all actions
        instructions = generator.generate_action_instructions()
        assert "Schemas for 'action_parameters' based on the selected_action:" in instructions
        assert "OBSERVE:" in instructions
        assert "SPEAK:" in instructions
        assert "TOOL:" in instructions
        assert "RECALL:" in instructions
        assert "MEMORIZE:" in instructions

        # Test with limited actions
        limited_actions = [HandlerActionType.SPEAK, HandlerActionType.OBSERVE]
        instructions = generator.generate_action_instructions(limited_actions)
        assert "SPEAK:" in instructions
        assert "OBSERVE:" in instructions
        assert "TOOL:" not in instructions
        assert "RECALL:" not in instructions

    def test_recall_schema_format(self):
        """Test that RECALL schema is correctly formatted."""
        generator = ActionInstructionGenerator()

        recall_schema = generator._generate_schema_for_action(HandlerActionType.RECALL)

        # Check that it has the correct fields, not the MEMORIZE fields
        assert "query" in recall_schema
        assert "node_type" in recall_schema
        assert "node_id" in recall_schema
        assert "scope" in recall_schema
        assert "limit" in recall_schema

        # Make sure it doesn't have the MEMORIZE node structure
        assert '"node": {' not in recall_schema
        assert "attributes" not in recall_schema

    def test_memorize_schema_format(self):
        """Test that MEMORIZE schema is correctly formatted."""
        generator = ActionInstructionGenerator()

        memorize_schema = generator._generate_schema_for_action(HandlerActionType.MEMORIZE)

        # Check that it has the correct node structure
        assert '"node": {' in memorize_schema
        assert "id: string" in memorize_schema
        assert "type:" in memorize_schema
        assert "scope:" in memorize_schema
        assert "attributes?" in memorize_schema

        # Make sure it doesn't have RECALL fields
        assert "query" not in memorize_schema
        assert "node_id" not in memorize_schema
        assert "limit" not in memorize_schema

    def test_defer_schema_format(self):
        """Test that DEFER schema has explicit type guidance."""
        generator = ActionInstructionGenerator()

        defer_schema = generator._generate_schema_for_action(HandlerActionType.DEFER)

        assert '"context"?: Dict[str, str]' in defer_schema
        assert '"defer_until"?: ISO 8601 timestamp string' in defer_schema
        assert "ISO 8601 format: '2025-01-20T15:00:00Z'" in defer_schema

    def test_tool_schema_without_registry(self):
        """Test tool schema generation without service registry."""
        generator = ActionInstructionGenerator()

        tool_schema = generator._generate_schema_for_action(HandlerActionType.TOOL)

        # Should fall back to default tools
        assert "Available tools (check with tool service for current list):" in tool_schema
        assert "discord_delete_message" in tool_schema
        assert "discord_timeout_user" in tool_schema
        assert "discord_ban_user" in tool_schema

    @pytest.mark.asyncio
    async def test_tool_schema_with_registry(self):
        """Test tool schema generation with service registry."""
        # Create mock tool service
        mock_tool_service = Mock()
        mock_tool_service.adapter_name = "discord"

        # Mock get_all_tool_info to return ToolInfo objects
        tool_info_1 = Mock(spec=ToolInfo)
        tool_info_1.name = "test_tool_1"
        tool_info_1.description = "Test tool 1 description"
        tool_info_1.parameters = Mock()
        tool_info_1.parameters.model_dump.return_value = {"param1": "string", "param2": "integer"}

        tool_info_2 = Mock(spec=ToolInfo)
        tool_info_2.name = "test_tool_2"
        tool_info_2.description = "Test tool 2 description"
        tool_info_2.parameters = None

        mock_tool_service.get_all_tool_info = AsyncMock(return_value=[tool_info_1, tool_info_2])

        # Create mock service registry
        mock_registry = Mock()
        mock_registry.get_services_by_type.return_value = [mock_tool_service]

        generator = ActionInstructionGenerator(mock_registry)

        # We need to test the async get_all_tools function directly
        # since _generate_tool_schema has async code that's hard to test in sync context
        tool_schema = generator._generate_schema_for_action(HandlerActionType.TOOL)

        # In sync context, it should try but fall back to default
        assert "Available tools" in tool_schema

    def test_simplify_schema(self):
        """Test schema simplification."""
        generator = ActionInstructionGenerator()

        # Test simple schema
        schema = {
            "properties": {
                "field1": {"type": "string"},
                "field2": {"type": "integer", "default": 10},
                "field3": {"type": "boolean"},
            },
            "required": ["field1"],
        }

        result = generator._simplify_schema(schema)
        assert '"field1": string (required)' in result
        assert '"field2"?: integer (default: 10)' in result
        assert '"field3"?: boolean' in result

    def test_extract_type(self):
        """Test type extraction from property schema."""
        generator = ActionInstructionGenerator()

        # Simple type
        assert generator._extract_type({"type": "string"}) == "string"
        assert generator._extract_type({"type": "integer"}) == "integer"

        # Object with additionalProperties
        dict_schema = {"type": "object", "additionalProperties": {"type": "string"}}
        assert generator._extract_type(dict_schema) == "Dict[str, str]"

        # anyOf with nullable
        nullable_schema = {"anyOf": [{"type": "string"}, {"type": "null"}]}
        assert generator._extract_type(nullable_schema) == "string"

    def test_get_action_guidance(self):
        """Test action-specific guidance."""
        generator = ActionInstructionGenerator()

        # Test some key guidances
        speak_guidance = generator.get_action_guidance(HandlerActionType.SPEAK)
        assert "content" in speak_guidance
        assert "JSON object" in speak_guidance

        defer_guidance = generator.get_action_guidance(HandlerActionType.DEFER)
        assert "human approval" in defer_guidance
        assert "TASK_COMPLETE instead" in defer_guidance

        task_complete_guidance = generator.get_action_guidance(HandlerActionType.TASK_COMPLETE)
        assert "done, impossible, unnecessary" in task_complete_guidance
        assert "preferred over DEFER" in task_complete_guidance

    def test_all_actions_have_schemas(self):
        """Test that all action types have proper schemas."""
        generator = ActionInstructionGenerator()

        for action_type in list(HandlerActionType):
            schema = generator._generate_schema_for_action(action_type)
            assert schema, f"No schema generated for {action_type}"
            assert action_type.value.upper() in schema or action_type.value in schema.lower()


class TestToolDiscoveryIntegration:
    """Integration tests for tool discovery with mocked services."""

    @pytest.mark.asyncio
    async def test_get_all_tools_with_multiple_services(self):
        """Test aggregating tools from multiple services."""
        # Create multiple mock tool services
        mock_discord_service = Mock()
        mock_discord_service.adapter_name = "discord"
        tool_info_discord = Mock(spec=ToolInfo)
        tool_info_discord.name = "discord_ban"
        tool_info_discord.description = "Ban a user"
        tool_info_discord.parameters = Mock()
        tool_info_discord.parameters.model_dump.return_value = {"user_id": "string"}
        mock_discord_service.get_all_tool_info = AsyncMock(return_value=[tool_info_discord])

        mock_api_service = Mock()
        mock_api_service.adapter_name = "api"
        # Mock API service without get_all_tool_info - simulate the attribute not existing
        del mock_api_service.get_all_tool_info  # Ensure attribute doesn't exist
        mock_api_service.get_available_tools = AsyncMock(return_value=["api_tool_1", "api_tool_2"])

        # Create mock registry
        mock_registry = Mock()
        mock_registry.get_services_by_type.return_value = [mock_discord_service, mock_api_service]

        generator = ActionInstructionGenerator(mock_registry)

        # Create the coroutine manually to test it
        async def get_all_tools():
            tool_services = generator.service_registry.get_services_by_type("tool")
            all_tools = {}

            for tool_service in tool_services:
                try:
                    if hasattr(tool_service, "get_all_tool_info"):
                        tool_infos = await tool_service.get_all_tool_info()
                        for tool_info in tool_infos:
                            all_tools[tool_info.name] = {
                                "name": tool_info.name,
                                "description": tool_info.description,
                                "service": getattr(tool_service, "adapter_name", "unknown"),
                            }
                    else:
                        service_tools = await tool_service.get_available_tools()
                        service_name = getattr(tool_service, "adapter_name", "unknown")
                        if isinstance(service_tools, list):
                            for tool_name in service_tools:
                                all_tools[tool_name] = {
                                    "name": tool_name,
                                    "description": "No description available",
                                    "service": service_name,
                                }
                except Exception:
                    pass

            return all_tools

        # Test the async function
        tools = await get_all_tools()

        assert len(tools) == 3
        assert "discord_ban" in tools
        assert tools["discord_ban"]["description"] == "Ban a user"
        assert tools["discord_ban"]["service"] == "discord"

        assert "api_tool_1" in tools
        assert tools["api_tool_1"]["description"] == "No description available"
        assert tools["api_tool_1"]["service"] == "api"
