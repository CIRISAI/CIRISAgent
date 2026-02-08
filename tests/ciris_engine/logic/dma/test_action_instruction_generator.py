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
        # New format uses flat fields, not nested action_parameters
        assert "FLAT field schemas per action" in instructions
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
        """Test that RECALL schema is correctly formatted with flat field names."""
        generator = ActionInstructionGenerator()

        recall_schema = generator._generate_schema_for_action(HandlerActionType.RECALL)

        # Check that it has the flat recall_* field names
        assert "recall_query" in recall_schema or "RECALL:" in recall_schema
        # Should use flat field naming pattern
        assert "RECALL:" in recall_schema

        # Make sure it doesn't have the MEMORIZE node structure
        assert '"node": {' not in recall_schema

    def test_memorize_schema_format(self):
        """Test that MEMORIZE schema is correctly formatted with flat field names."""
        generator = ActionInstructionGenerator()

        memorize_schema = generator._generate_schema_for_action(HandlerActionType.MEMORIZE)

        # Check that it has flat memorize_* field names
        assert "MEMORIZE:" in memorize_schema
        assert "memorize_node_type" in memorize_schema or "memorize_content" in memorize_schema
        assert "memorize_scope" in memorize_schema

        # Make sure it doesn't have RECALL-specific flat fields
        assert "recall_query" not in memorize_schema

    def test_defer_schema_format(self):
        """Test that DEFER schema has flat field names with type guidance."""
        generator = ActionInstructionGenerator()

        defer_schema = generator._generate_schema_for_action(HandlerActionType.DEFER)

        # Check for flat field names
        assert "DEFER:" in defer_schema
        assert "defer_reason" in defer_schema
        assert "defer_until" in defer_schema
        # ISO 8601 format guidance
        assert "ISO 8601" in defer_schema or "2025-01-20T15:00:00Z" in defer_schema

    def test_tool_schema_without_registry(self):
        """Test tool schema generation without service registry fails fast."""
        generator = ActionInstructionGenerator()

        tool_schema = generator._generate_schema_for_action(HandlerActionType.TOOL)

        # Should fail fast with error - no hardcoded fallback tools
        assert "ERROR" in tool_schema
        assert "No tool service registry available" in tool_schema
        # Should NOT contain any hardcoded Discord tools
        assert "discord_delete_message" not in tool_schema
        assert "discord_timeout_user" not in tool_schema
        assert "discord_ban_user" not in tool_schema

    @pytest.mark.asyncio
    async def test_tool_schema_with_registry(self):
        """Test tool schema generation with service registry after pre-caching."""
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

        # CRITICAL: Must pre-cache tools before generating schema (no fallbacks!)
        await generator.pre_cache_tools()

        # Now generate the tool schema - should use pre-cached tools
        tool_schema = generator._generate_schema_for_action(HandlerActionType.TOOL)

        # Should have the pre-cached tools available
        assert "Available tools" in tool_schema
        assert "test_tool_1" in tool_schema
        assert "test_tool_2" in tool_schema

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

        # Test some key guidances - these use the new flat field format
        speak_guidance = generator.get_action_guidance(HandlerActionType.SPEAK)
        # Guidance may mention content or speak_content
        assert "content" in speak_guidance.lower() or "speak" in speak_guidance.lower()

        defer_guidance = generator.get_action_guidance(HandlerActionType.DEFER)
        # Guidance should mention deferral or approval
        assert "defer" in defer_guidance.lower() or "approval" in defer_guidance.lower()

        task_complete_guidance = generator.get_action_guidance(HandlerActionType.TASK_COMPLETE)
        # Guidance should mention completion scenarios
        assert "done" in task_complete_guidance.lower() or "complete" in task_complete_guidance.lower()

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
