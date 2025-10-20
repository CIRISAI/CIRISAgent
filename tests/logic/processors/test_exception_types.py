"""Tests for processor exception types."""

import pytest

from ciris_engine.logic.processors.exceptions import (
    ActionSelectionRetryFailed,
    ConscienceCheckFailed,
    ContextBuildingFailed,
    DMAExecutionFailed,
    ProcessorError,
)


def test_processor_error_base():
    """Test base ProcessorError."""
    error = ProcessorError("test message", {"key": "value"})
    assert error.message == "test message"
    assert error.context == {"key": "value"}
    assert str(error) == "test message"


def test_action_selection_retry_failed():
    """Test ActionSelectionRetryFailed exception."""
    error = ActionSelectionRetryFailed("thought_123", "LLM timeout")
    assert error.thought_id == "thought_123"
    assert "thought_123" in str(error)
    assert "LLM timeout" in error.context["error_details"]


def test_conscience_check_failed():
    """Test ConscienceCheckFailed exception."""
    original_error = ValueError("Invalid parameters")
    error = ConscienceCheckFailed("ThoughtDepthGuardrail", original_error)
    assert error.conscience_name == "ThoughtDepthGuardrail"
    assert error.original_error == original_error
    assert "ThoughtDepthGuardrail" in str(error)


def test_dma_execution_failed():
    """Test DMAExecutionFailed exception."""
    original_error = RuntimeError("DMA crashed")
    error = DMAExecutionFailed("StatusDMA", original_error)
    assert error.dma_name == "StatusDMA"
    assert error.original_error == original_error


def test_context_building_failed():
    """Test ContextBuildingFailed exception."""
    original_error = KeyError("missing_field")
    error = ContextBuildingFailed("thought_456", original_error)
    assert error.thought_id == "thought_456"
    assert error.original_error == original_error


def test_exception_inheritance():
    """Verify all exceptions inherit from ProcessorError."""
    assert issubclass(ActionSelectionRetryFailed, ProcessorError)
    assert issubclass(ConscienceCheckFailed, ProcessorError)
    assert issubclass(DMAExecutionFailed, ProcessorError)
    assert issubclass(ContextBuildingFailed, ProcessorError)
