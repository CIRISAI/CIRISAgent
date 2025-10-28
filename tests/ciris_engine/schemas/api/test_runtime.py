"""Tests for runtime API response schemas."""

import pytest
from pydantic import ValidationError

from ciris_engine.schemas.api.runtime import ProcessingSpeedResult, StateTransitionResult


class TestStateTransitionResult:
    """Tests for StateTransitionResult schema."""

    def test_valid_state_transition_result(self):
        """Test creating a valid StateTransitionResult."""
        result = StateTransitionResult(
            success=True,
            target_state="WORK",
            current_state="WORK",
            reason="Transition requested by user",
            transition_time_ms=15.5,
        )

        assert result.success is True
        assert result.target_state == "WORK"
        assert result.current_state == "WORK"
        assert result.reason == "Transition requested by user"
        assert result.transition_time_ms == 15.5

    def test_state_transition_without_optional_time(self):
        """Test StateTransitionResult without optional transition time."""
        result = StateTransitionResult(
            success=False,
            target_state="DREAM",
            current_state="WORK",
            reason="Transition blocked by active tasks",
        )

        assert result.success is False
        assert result.target_state == "DREAM"
        assert result.current_state == "WORK"
        assert result.reason == "Transition blocked by active tasks"
        assert result.transition_time_ms is None

    def test_state_transition_missing_required_fields(self):
        """Test that missing required fields raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            StateTransitionResult(
                success=True,
                target_state="WORK",
                # Missing current_state and reason
            )

        errors = exc_info.value.errors()
        assert len(errors) == 2
        error_fields = {e["loc"][0] for e in errors}
        assert "current_state" in error_fields
        assert "reason" in error_fields

    def test_state_transition_serialization(self):
        """Test StateTransitionResult serialization to dict."""
        result = StateTransitionResult(
            success=True,
            target_state="SOLITUDE",
            current_state="SOLITUDE",
            reason="Entering reflection mode",
            transition_time_ms=8.2,
        )

        data = result.model_dump()
        assert data["success"] is True
        assert data["target_state"] == "SOLITUDE"
        assert data["current_state"] == "SOLITUDE"
        assert data["reason"] == "Entering reflection mode"
        assert data["transition_time_ms"] == 8.2


class TestProcessingSpeedResult:
    """Tests for ProcessingSpeedResult schema."""

    def test_valid_processing_speed_result(self):
        """Test creating a valid ProcessingSpeedResult."""
        result = ProcessingSpeedResult(
            success=True,
            multiplier=2.0,
            description="Processing speed doubled",
            effective_immediately=True,
        )

        assert result.success is True
        assert result.multiplier == 2.0
        assert result.description == "Processing speed doubled"
        assert result.effective_immediately is True

    def test_processing_speed_default_effective_immediately(self):
        """Test ProcessingSpeedResult with default effective_immediately value."""
        result = ProcessingSpeedResult(
            success=True,
            multiplier=0.5,
            description="Processing speed halved",
        )

        assert result.success is True
        assert result.multiplier == 0.5
        assert result.description == "Processing speed halved"
        assert result.effective_immediately is True  # Default value

    def test_processing_speed_missing_required_fields(self):
        """Test that missing required fields raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            ProcessingSpeedResult(
                success=True,
                # Missing multiplier and description
            )

        errors = exc_info.value.errors()
        assert len(errors) == 2
        error_fields = {e["loc"][0] for e in errors}
        assert "multiplier" in error_fields
        assert "description" in error_fields

    def test_processing_speed_serialization(self):
        """Test ProcessingSpeedResult serialization to dict."""
        result = ProcessingSpeedResult(
            success=False,
            multiplier=1.0,
            description="Speed change failed",
            effective_immediately=False,
        )

        data = result.model_dump()
        assert data["success"] is False
        assert data["multiplier"] == 1.0
        assert data["description"] == "Speed change failed"
        assert data["effective_immediately"] is False

    def test_processing_speed_various_multipliers(self):
        """Test ProcessingSpeedResult with various multiplier values."""
        # Test fractional speed
        result_slow = ProcessingSpeedResult(
            success=True,
            multiplier=0.25,
            description="Quarter speed",
        )
        assert result_slow.multiplier == 0.25

        # Test normal speed
        result_normal = ProcessingSpeedResult(
            success=True,
            multiplier=1.0,
            description="Normal speed",
        )
        assert result_normal.multiplier == 1.0

        # Test fast speed
        result_fast = ProcessingSpeedResult(
            success=True,
            multiplier=10.0,
            description="10x speed",
        )
        assert result_fast.multiplier == 10.0
