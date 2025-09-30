"""
Tests for pipeline control Pydantic model definitions.

Ensures that SingleStepResult and ThoughtProcessingResult Pydantic models
correctly validate the data returned by pipeline control functions.
"""

import pytest
from pydantic import ValidationError

from ciris_engine.protocols.pipeline_control import PipelineController, SingleStepResult, ThoughtProcessingResult


class TestSingleStepResultPydantic:
    """Test SingleStepResult Pydantic model."""

    def test_single_step_result_creates_valid_model(self):
        """Test that SingleStepResult creates a valid Pydantic model."""
        result = SingleStepResult(
            success=True,
            step_point="test_step",
            message="Test message",
            thoughts_advanced=1,
            step_results=[],
            processing_time_ms=100.0,
            pipeline_state={},
        )

        assert result.success is True
        assert result.step_point == "test_step"
        assert result.thoughts_advanced == 1

    def test_single_step_result_requires_mandatory_fields(self):
        """Test that SingleStepResult requires mandatory fields."""
        with pytest.raises(ValidationError) as exc_info:
            SingleStepResult(
                success=True,
                # Missing: step_point, message, processing_time_ms
            )

        errors = exc_info.value.errors()
        assert len(errors) >= 3  # At least 3 missing fields

    def test_single_step_result_optional_fields(self):
        """Test that SingleStepResult handles optional fields correctly."""
        result = SingleStepResult(
            success=True,
            step_point="test",
            message="Test",
            processing_time_ms=100.0,
            # Optional fields use defaults
        )

        assert result.thoughts_advanced == 0  # Default value
        assert result.thought_id is None  # Optional
        assert result.step_results == []  # Default factory
        assert result.pipeline_state == {}  # Default factory


class TestThoughtProcessingResultPydantic:
    """Test ThoughtProcessingResult Pydantic model."""

    def test_thought_processing_result_creates_valid_model(self):
        """Test that ThoughtProcessingResult creates a valid Pydantic model."""
        result = ThoughtProcessingResult(
            thought_id="thought_123",
            round_id=1,
            task_id="task_123",
            step_point="test_step",
            success=True,
            step_data={},
            processing_time_ms=100.0,
            timestamp=1234567890.0,
        )

        assert result.thought_id == "thought_123"
        assert result.success is True
        assert result.round_id == 1

    def test_thought_processing_result_requires_mandatory_fields(self):
        """Test that ThoughtProcessingResult requires mandatory fields."""
        with pytest.raises(ValidationError) as exc_info:
            ThoughtProcessingResult(
                thought_id="thought_123",
                # Missing all other required fields
            )

        errors = exc_info.value.errors()
        assert len(errors) >= 6  # Many required fields missing

    def test_thought_processing_result_defaults(self):
        """Test that ThoughtProcessingResult handles default values."""
        result = ThoughtProcessingResult(
            thought_id="thought_123",
            round_id=1,
            task_id="task_123",
            step_point="test_step",
            success=True,
            processing_time_ms=100.0,
            timestamp=1234567890.0,
            # step_data has default factory
        )

        assert result.step_data == {}  # Default factory


class TestPipelineControllerHelperMethods:
    """Test PipelineController helper methods return correct Pydantic models."""

    def test_single_step_result_structure_matches_expected(self):
        """Test that SingleStepResult Pydantic model matches expected structure."""
        result = SingleStepResult(
            success=True,
            step_point="test_step",
            message="Test message",
            thoughts_advanced=1,
            step_results=[],
            processing_time_ms=100.0,
            pipeline_state={},
        )

        assert isinstance(result, SingleStepResult)
        assert result.success is True
        assert result.step_point == "test_step"
        assert isinstance(result.processing_time_ms, (int, float))

    def test_thought_processing_result_structure_matches_expected(self):
        """Test that ThoughtProcessingResult Pydantic model matches expected structure."""
        result = ThoughtProcessingResult(
            thought_id="test_thought",
            round_id=1,
            task_id="test_task",
            step_point="test_step",
            success=True,
            step_data={},
            processing_time_ms=100.0,
            timestamp=1234567890.0,
        )

        assert isinstance(result, ThoughtProcessingResult)
        assert result.thought_id == "test_thought"
        assert result.success is True
        assert isinstance(result.timestamp, float)


class TestPydanticModelSerialization:
    """Test that Pydantic models serialize/deserialize correctly."""

    def test_single_step_result_serialization(self):
        """Test SingleStepResult can be serialized to dict."""
        result = SingleStepResult(
            success=True,
            step_point="test",
            message="Test",
            processing_time_ms=100.0,
        )

        result_dict = result.model_dump()
        assert result_dict["success"] is True
        assert result_dict["step_point"] == "test"

    def test_thought_processing_result_serialization(self):
        """Test ThoughtProcessingResult can be serialized to dict."""
        result = ThoughtProcessingResult(
            thought_id="test_thought",
            round_id=1,
            task_id="test_task",
            step_point="test_step",
            success=True,
            processing_time_ms=100.0,
            timestamp=1234567890.0,
        )

        result_dict = result.model_dump()
        assert result_dict["thought_id"] == "test_thought"
        assert result_dict["success"] is True
