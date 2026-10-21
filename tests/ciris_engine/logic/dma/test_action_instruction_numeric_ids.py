"""
Unit tests for ActionInstructionGenerator numeric ID guidance.
Tests that the generator properly instructs the agent to use numeric Discord IDs.
"""

import pytest

from ciris_engine.logic.dma.action_selection.action_instruction_generator import ActionInstructionGenerator
from ciris_engine.schemas.runtime.enums import HandlerActionType


class TestActionInstructionNumericIds:
    """Test action instruction generator provides proper numeric ID guidance."""

    @pytest.fixture
    def generator(self):
        """Create action instruction generator."""
        return ActionInstructionGenerator()

    def test_memorize_instruction_uses_flat_field_names(self, generator):
        """Test MEMORIZE action uses flat field names (memorize_* prefix)."""
        schema = generator._generate_schema_for_action(HandlerActionType.MEMORIZE)

        # Check that the schema uses flat field names
        assert "MEMORIZE:" in schema
        assert "memorize_node_type" in schema
        assert "memorize_content" in schema
        assert "memorize_scope" in schema

    def test_recall_instruction_uses_flat_field_names(self, generator):
        """Test RECALL action uses flat field names (recall_* prefix)."""
        schema = generator._generate_schema_for_action(HandlerActionType.RECALL)

        # Check that the schema uses flat field names
        assert "RECALL:" in schema
        assert "recall_query" in schema
        assert "recall_node_type" in schema or "recall_scope" in schema
        assert "recall_limit" in schema

    def test_forget_instruction_includes_numeric_id_guidance(self, generator):
        """Test FORGET action includes guidance about numeric IDs."""
        schema = generator._generate_schema_for_action(HandlerActionType.FORGET)

        # Check that the schema includes numeric ID guidance
        assert "numeric Discord IDs" in schema
        assert "user/537080239679864862" in schema

    def test_full_action_instructions_include_memory_guidance(self, generator):
        """Test that full action instructions include all memory-related guidance."""
        # Generate instructions for memory-related actions
        instructions = generator.generate_action_instructions(
            [HandlerActionType.MEMORIZE, HandlerActionType.RECALL, HandlerActionType.FORGET]
        )

        # Verify all memory actions are present with flat field names
        assert "MEMORIZE:" in instructions
        assert "RECALL:" in instructions
        assert "FORGET:" in instructions
        # FORGET still has numeric ID guidance
        assert "numeric Discord IDs" in instructions

    def test_memorize_schema_format(self, generator):
        """Test that MEMORIZE schema is properly formatted with flat fields."""
        schema = generator._format_memory_action_schema("MEMORIZE")

        # Check basic structure with flat field names
        assert "MEMORIZE:" in schema
        assert "memorize_node_type" in schema
        assert "memorize_content" in schema
        assert "memorize_scope" in schema
        assert "local|identity|environment" in schema

        # Check guidance sections
        assert "For memorize_node_type:" in schema or "user" in schema
        assert "For memorize_scope:" in schema or "local" in schema

    def test_recall_schema_format(self, generator):
        """Test that RECALL schema is properly formatted with flat fields."""
        schema = generator._format_memory_action_schema("RECALL")

        # Check basic structure with flat field names
        assert "RECALL:" in schema
        assert "recall_query" in schema
        assert "recall_node_type" in schema
        assert "recall_scope" in schema
        assert "recall_limit" in schema

        # Check guidance
        assert "text" in schema.lower() or "search" in schema.lower()
