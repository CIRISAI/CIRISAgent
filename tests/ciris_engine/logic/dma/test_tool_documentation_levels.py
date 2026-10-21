"""
Tests for tool documentation levels in ASPDMA vs TSASPDMA.

ASPDMA should receive CONCISE tool summaries (name + when_to_use only).
TSASPDMA should receive FULL documentation (detailed_instructions, examples, gotchas).

This ensures the LLM gets the right level of detail at each decision stage.
"""

import pytest

from ciris_engine.logic.dma.action_selection.action_instruction_generator import ActionInstructionGenerator
from ciris_engine.logic.dma.tsaspdma import TSASPDMAEvaluator
from ciris_engine.schemas.adapters.tools import (
    ToolDMAGuidance,
    ToolDocumentation,
    ToolGotcha,
    ToolInfo,
    ToolParameterSchema,
    UsageExample,
)


@pytest.fixture
def tool_with_full_documentation() -> ToolInfo:
    """Create a tool with full documentation for testing."""
    return ToolInfo(
        name="test_device_control",
        description="Control a test device",
        when_to_use="Use this to control test devices",
        parameters=ToolParameterSchema(
            type="object",
            properties={
                "entity_id": {"type": "string", "description": "Entity ID"},
                "action": {
                    "type": "string",
                    "enum": ["turn_on", "turn_off", "media_stop"],
                    "description": "Action to perform",
                },
            },
            required=["entity_id", "action"],
        ),
        documentation=ToolDocumentation(
            quick_start="Use entity_id + action to control devices",
            detailed_instructions="""
# Detailed Instructions for Test Device Control

## Media Player Actions
- **media_stop** - Stop playback (USE THIS to stop music!)
- **turn_off** - Power off device (NOT for stopping music)

## Common Mistakes
- Using turn_off to stop music → Use media_stop instead!
""",
            examples=[
                UsageExample(
                    title="Stop music",
                    description="Use media_stop to stop playback",
                    code='{"entity_id": "media_player.bedroom", "action": "media_stop"}',
                ),
            ],
            gotchas=[
                ToolGotcha(
                    title="Don't use turn_off to stop music",
                    description="Use media_stop instead of turn_off for stopping playback",
                ),
            ],
        ),
        dma_guidance=ToolDMAGuidance(
            when_not_to_use="Do not use for querying state",
            ethical_considerations="Verify user intent for irreversible actions",
        ),
    )


class TestASPDMAConciseToolInfo:
    """Tests that ASPDMA receives concise tool information."""

    def test_format_tools_excludes_detailed_instructions(self, tool_with_full_documentation: ToolInfo):
        """ASPDMA prompt should NOT contain detailed_instructions."""
        generator = ActionInstructionGenerator()

        # Simulate cached tools as they would appear in ASPDMA
        all_tools = {
            tool_with_full_documentation.name: {
                "name": tool_with_full_documentation.name,
                "description": tool_with_full_documentation.description,
                "when_to_use": tool_with_full_documentation.when_to_use,
                "service": "TestService",
            }
        }

        formatted = generator._format_tools_for_prompt(all_tools)

        # Should contain the tool name and concise guidance
        assert "test_device_control" in formatted
        assert "Use this to control test devices" in formatted

        # Should NOT contain detailed documentation
        assert "Detailed Instructions" not in formatted
        assert "Media Player Actions" not in formatted
        assert "Common Mistakes" not in formatted
        assert "Stop music" not in formatted  # Example title
        assert "Don't use turn_off" not in formatted  # Gotcha title

    def test_format_tools_uses_when_to_use(self, tool_with_full_documentation: ToolInfo):
        """ASPDMA should use when_to_use for concise guidance."""
        generator = ActionInstructionGenerator()

        all_tools = {
            tool_with_full_documentation.name: {
                "name": tool_with_full_documentation.name,
                "description": tool_with_full_documentation.description,
                "when_to_use": tool_with_full_documentation.when_to_use,
                "service": "TestService",
            }
        }

        formatted = generator._format_tools_for_prompt(all_tools)

        # Should use the when_to_use text
        assert "Use this to control test devices" in formatted

    def test_format_tools_truncates_long_descriptions(self):
        """ASPDMA should truncate long descriptions when when_to_use is missing."""
        generator = ActionInstructionGenerator()

        long_description = "A" * 100  # 100 character description

        all_tools = {
            "long_tool": {
                "name": "long_tool",
                "description": long_description,
                "when_to_use": "",  # No when_to_use
                "service": "TestService",
            }
        }

        formatted = generator._format_tools_for_prompt(all_tools)

        # Should be truncated to ~80 chars + "..."
        assert "A" * 80 in formatted
        assert "..." in formatted
        # Full 100 chars should NOT appear
        assert long_description not in formatted


class TestTSASPDMAFullDocumentation:
    """Tests that TSASPDMA receives full tool documentation."""

    @pytest.fixture
    def tsaspdma_evaluator(self):
        """Create a TSASPDMA evaluator for testing."""
        # Create with minimal dependencies for unit testing
        from unittest.mock import MagicMock

        mock_registry = MagicMock()
        return TSASPDMAEvaluator(service_registry=mock_registry)

    def test_format_tool_documentation_includes_detailed_instructions(
        self, tsaspdma_evaluator: TSASPDMAEvaluator, tool_with_full_documentation: ToolInfo
    ):
        """TSASPDMA should include detailed_instructions in formatted output."""
        formatted = tsaspdma_evaluator._format_tool_documentation(tool_with_full_documentation)

        # Should contain detailed instructions
        assert "Detailed Instructions" in formatted
        assert "Media Player Actions" in formatted
        assert "media_stop" in formatted
        assert "NOT for stopping music" in formatted

    def test_format_tool_documentation_includes_examples(
        self, tsaspdma_evaluator: TSASPDMAEvaluator, tool_with_full_documentation: ToolInfo
    ):
        """TSASPDMA should include examples in formatted output."""
        formatted = tsaspdma_evaluator._format_tool_documentation(tool_with_full_documentation)

        # Should contain examples section
        assert "Examples" in formatted
        assert "Stop music" in formatted  # Example title
        assert "media_player.bedroom" in formatted
        assert "media_stop" in formatted

    def test_format_tool_documentation_includes_gotchas(
        self, tsaspdma_evaluator: TSASPDMAEvaluator, tool_with_full_documentation: ToolInfo
    ):
        """TSASPDMA should include gotchas in formatted output."""
        formatted = tsaspdma_evaluator._format_tool_documentation(tool_with_full_documentation)

        # Should contain gotchas section
        assert "Gotchas" in formatted
        assert "Don't use turn_off to stop music" in formatted

    def test_format_tool_documentation_includes_dma_guidance(
        self, tsaspdma_evaluator: TSASPDMAEvaluator, tool_with_full_documentation: ToolInfo
    ):
        """TSASPDMA should include DMA guidance in formatted output."""
        formatted = tsaspdma_evaluator._format_tool_documentation(tool_with_full_documentation)

        # Should contain DMA guidance
        assert "Do not use for querying state" in formatted
        assert "Verify user intent" in formatted

    def test_format_tool_documentation_includes_parameter_schema(
        self, tsaspdma_evaluator: TSASPDMAEvaluator, tool_with_full_documentation: ToolInfo
    ):
        """TSASPDMA should include parameter schema in formatted output."""
        formatted = tsaspdma_evaluator._format_tool_documentation(tool_with_full_documentation)

        # Should contain parameter info
        assert "entity_id" in formatted
        assert "action" in formatted
        assert "turn_on" in formatted or "media_stop" in formatted


class TestHomeAssistantToolDocumentation:
    """Tests that the HA adapter's ha_device_control tool has proper documentation."""

    def test_ha_device_control_has_documentation(self):
        """ha_device_control tool should have ToolDocumentation."""
        from ciris_adapters.home_assistant.tool_service import HAToolService

        tool = HAToolService.TOOL_DEFINITIONS.get("ha_device_control")
        assert tool is not None
        assert tool.documentation is not None
        assert tool.documentation.detailed_instructions is not None
        assert len(tool.documentation.detailed_instructions) > 100

    def test_ha_device_control_has_media_stop_guidance(self):
        """ha_device_control should document media_stop for stopping music."""
        from ciris_adapters.home_assistant.tool_service import HAToolService

        tool = HAToolService.TOOL_DEFINITIONS.get("ha_device_control")
        assert tool is not None
        assert tool.documentation is not None

        instructions = tool.documentation.detailed_instructions or ""
        assert "media_stop" in instructions.lower()
        assert "stop" in instructions.lower()

    def test_ha_device_control_has_gotchas(self):
        """ha_device_control should have gotchas warning about turn_off vs media_stop."""
        from ciris_adapters.home_assistant.tool_service import HAToolService

        tool = HAToolService.TOOL_DEFINITIONS.get("ha_device_control")
        assert tool is not None
        assert tool.documentation is not None
        assert tool.documentation.gotchas is not None
        assert len(tool.documentation.gotchas) > 0

        # Check that at least one gotcha mentions turn_off and media_stop
        gotcha_text = " ".join(g.description for g in tool.documentation.gotchas)
        assert "turn_off" in gotcha_text.lower() or "media_stop" in gotcha_text.lower()

    def test_ha_device_control_has_dma_guidance(self):
        """ha_device_control should have DMA guidance."""
        from ciris_adapters.home_assistant.tool_service import HAToolService

        tool = HAToolService.TOOL_DEFINITIONS.get("ha_device_control")
        assert tool is not None
        assert tool.dma_guidance is not None

    def test_ha_device_control_action_enum_includes_media_actions(self):
        """ha_device_control action enum should include media player actions."""
        from ciris_adapters.home_assistant.tool_service import HAToolService

        tool = HAToolService.TOOL_DEFINITIONS.get("ha_device_control")
        assert tool is not None

        action_enum = tool.parameters.properties.get("action", {}).get("enum", [])
        assert "media_stop" in action_enum
        assert "media_play" in action_enum
        assert "media_pause" in action_enum
