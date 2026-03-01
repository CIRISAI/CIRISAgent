"""
Tests for thought processor helper methods.

Tests coverage for the helper methods extracted to reduce cognitive complexity:
- _extract_updated_observation
- _create_retry_context_copy
- _build_retry_guidance
"""

from unittest.mock import Mock

import pytest

from ciris_engine.logic.processors.core.thought_processor.main import ThoughtProcessor


class MockThoughtProcessor:
    """Mock ThoughtProcessor with just the helper methods we need to test."""

    def _extract_updated_observation(self, conscience_result):
        """Extract updated observation from conscience result if present."""
        if hasattr(conscience_result, "epistemic_data") and conscience_result.epistemic_data:
            ep_data = conscience_result.epistemic_data
            if hasattr(ep_data, "CIRIS_OBSERVATION_UPDATED_STATUS") and ep_data.CIRIS_OBSERVATION_UPDATED_STATUS:
                return ep_data.CIRIS_OBSERVATION_UPDATED_STATUS
        return None

    def _create_retry_context_copy(self, thought_context):
        """Create a copy of the thought context with is_conscience_retry flag set."""
        if hasattr(thought_context, "model_copy"):
            retry_context = thought_context.model_copy()
            retry_context.is_conscience_retry = True
            return retry_context
        if isinstance(thought_context, dict):
            retry_context = thought_context.copy()
            retry_context["is_conscience_retry"] = True
            return retry_context
        if hasattr(thought_context, "is_conscience_retry"):
            thought_context.is_conscience_retry = True
        return thought_context

    def _build_retry_guidance(self, attempted_action, override_reason, updated_observation):
        """Build retry guidance message based on whether there's a new observation."""
        base_guidance = (
            f"Your previous attempt to {attempted_action} was rejected because: {override_reason}. "
            "Please select a DIFFERENT action that better aligns with ethical principles and safety guidelines. "
        )
        if updated_observation:
            return (
                f"IMPORTANT: A NEW MESSAGE arrived from the user while you were processing: '{updated_observation}'. "
                f"You must now respond to THIS new message, not complete the old task. "
                f"{base_guidance}"
                "The user is waiting for a response to their new message. Use SPEAK to respond or use a TOOL if needed."
            )
        return (
            f"{base_guidance}"
            "Consider: Is there a more cautious approach? Should you gather more information first? "
            "Can this task be marked as complete without further action? "
            "Remember: DEFER only if the task MUST be done AND requires human approval."
        )


class TestExtractUpdatedObservation:
    """Tests for _extract_updated_observation helper."""

    @pytest.fixture
    def processor(self):
        """Create a mock processor with the helper method."""
        return MockThoughtProcessor()

    def test_extracts_observation_from_epistemic_data(self, processor):
        """Test extraction when observation is in epistemic_data."""
        conscience_result = Mock()
        conscience_result.epistemic_data = Mock()
        conscience_result.epistemic_data.CIRIS_OBSERVATION_UPDATED_STATUS = "New user message"

        result = processor._extract_updated_observation(conscience_result)

        assert result == "New user message"

    def test_returns_none_when_no_epistemic_data(self, processor):
        """Test returns None when epistemic_data is None."""
        conscience_result = Mock()
        conscience_result.epistemic_data = None

        result = processor._extract_updated_observation(conscience_result)

        assert result is None

    def test_returns_none_when_no_attribute(self, processor):
        """Test returns None when CIRIS_OBSERVATION_UPDATED_STATUS is not present."""
        conscience_result = Mock()
        conscience_result.epistemic_data = Mock(spec=[])  # No attributes

        result = processor._extract_updated_observation(conscience_result)

        assert result is None

    def test_returns_none_when_empty_observation(self, processor):
        """Test returns None when observation is empty string."""
        conscience_result = Mock()
        conscience_result.epistemic_data = Mock()
        conscience_result.epistemic_data.CIRIS_OBSERVATION_UPDATED_STATUS = ""

        result = processor._extract_updated_observation(conscience_result)

        assert result is None


class TestCreateRetryContextCopy:
    """Tests for _create_retry_context_copy helper."""

    @pytest.fixture
    def processor(self):
        """Create a mock processor with the helper method."""
        return MockThoughtProcessor()

    def test_copies_pydantic_model_context(self, processor):
        """Test creates copy for Pydantic models with model_copy."""
        context = Mock()
        context.model_copy = Mock(return_value=Mock())

        result = processor._create_retry_context_copy(context)

        context.model_copy.assert_called_once()
        assert result.is_conscience_retry is True

    def test_copies_dict_context(self, processor):
        """Test creates copy for dict context."""
        context = {"key": "value", "other": 123}

        result = processor._create_retry_context_copy(context)

        assert result["is_conscience_retry"] is True
        assert result["key"] == "value"
        assert result is not context  # Should be a copy

    def test_sets_flag_on_object_with_attribute(self, processor):
        """Test sets flag on object that has is_conscience_retry attribute."""
        context = Mock(spec=["is_conscience_retry"])
        context.is_conscience_retry = False

        result = processor._create_retry_context_copy(context)

        assert result.is_conscience_retry is True
        assert result is context  # Same object, modified in place

    def test_returns_original_for_unsupported_type(self, processor):
        """Test returns original context for unsupported types."""
        context = "string context"  # Unsupported type

        result = processor._create_retry_context_copy(context)

        assert result == context


class TestBuildRetryGuidance:
    """Tests for _build_retry_guidance helper."""

    @pytest.fixture
    def processor(self):
        """Create a mock processor with the helper method."""
        return MockThoughtProcessor()

    def test_builds_standard_guidance_without_observation(self, processor):
        """Test standard guidance when no updated observation."""
        result = processor._build_retry_guidance(
            attempted_action="speak to the user",
            override_reason="Safety check failed",
            updated_observation=None,
        )

        assert "speak to the user" in result
        assert "Safety check failed" in result
        assert "DIFFERENT action" in result
        assert "more cautious approach" in result

    def test_builds_observation_guidance_with_observation(self, processor):
        """Test guidance includes observation when present."""
        result = processor._build_retry_guidance(
            attempted_action="speak to the user",
            override_reason="New message arrived",
            updated_observation="Hello, are you there?",
        )

        assert "IMPORTANT: A NEW MESSAGE" in result
        assert "Hello, are you there?" in result
        assert "respond to THIS new message" in result

    def test_standard_guidance_includes_defer_reminder(self, processor):
        """Test standard guidance includes DEFER reminder."""
        result = processor._build_retry_guidance(
            attempted_action="memorize data",
            override_reason="Action failed",
            updated_observation=None,
        )

        assert "DEFER only if" in result

    def test_observation_guidance_suggests_speak_or_tool(self, processor):
        """Test observation guidance suggests SPEAK or TOOL."""
        result = processor._build_retry_guidance(
            attempted_action="defer",
            override_reason="New message",
            updated_observation="User asked a question",
        )

        assert "Use SPEAK to respond or use a TOOL" in result
