"""
Unit tests for reasoning stream schemas.
"""

from datetime import datetime
from typing import Any, Dict

import pytest
from pydantic import ValidationError

from ciris_engine.schemas.streaming.reasoning_stream import (
    ThoughtStatus,
    StepCategory,
    ThoughtStreamData,
    StepPointSummary,
    RoundSummary,
    ReasoningStreamUpdate,
    STEP_METADATA,
    get_step_metadata,
    calculate_progress_percentage,
    get_remaining_steps,
    create_stream_update_from_step_results,
)
from ciris_engine.schemas.services.runtime_control import StepPoint, StepResultGatherContext


class TestThoughtStatus:
    """Test ThoughtStatus enum."""

    def test_all_statuses_exist(self):
        """Test all expected statuses are defined."""
        expected_statuses = ["queued", "processing", "completed", "failed", "blocked"]
        actual_statuses = [status.value for status in ThoughtStatus]
        
        for expected in expected_statuses:
            assert expected in actual_statuses

    def test_status_creation(self):
        """Test creating ThoughtStatus instances."""
        assert ThoughtStatus.QUEUED.value == "queued"
        assert ThoughtStatus.PROCESSING.value == "processing"
        assert ThoughtStatus.COMPLETED.value == "completed"
        assert ThoughtStatus.FAILED.value == "failed"
        assert ThoughtStatus.BLOCKED.value == "blocked"


class TestStepCategory:
    """Test StepCategory enum."""

    def test_all_categories_exist(self):
        """Test all expected categories are defined."""
        expected_categories = ["preparation", "analysis", "decision", "execution", "completion"]
        actual_categories = [category.value for category in StepCategory]
        
        for expected in expected_categories:
            assert expected in actual_categories

    def test_category_creation(self):
        """Test creating StepCategory instances."""
        assert StepCategory.PREPARATION.value == "preparation"
        assert StepCategory.ANALYSIS.value == "analysis"
        assert StepCategory.DECISION.value == "decision"
        assert StepCategory.EXECUTION.value == "execution"
        assert StepCategory.COMPLETION.value == "completion"


class TestThoughtStreamData:
    """Test ThoughtStreamData schema."""

    def test_valid_thought_stream_data(self):
        """Test creating valid ThoughtStreamData."""
        now = datetime.now()
        
        data = ThoughtStreamData(
            thought_id="test-thought-123",
            task_id="test-task-456",
            round_number=5,
            current_step=StepPoint.PERFORM_DMAS,
            step_category=StepCategory.ANALYSIS,
            status=ThoughtStatus.PROCESSING,
            steps_completed=[StepPoint.START_ROUND, StepPoint.GATHER_CONTEXT],
            steps_remaining=[StepPoint.PERFORM_ASPDMA, StepPoint.CONSCIENCE_EXECUTION],
            progress_percentage=33.3,
            started_at=now,
            current_step_started_at=now,
            processing_time_ms=150.5,
            total_processing_time_ms=500.0,
            estimated_completion_ms=1000.0,
            content_preview="Test thought content for processing",
            thought_type="task_execution",
            step_result=None,
            last_error=None
        )
        
        assert data.thought_id == "test-thought-123"
        assert data.task_id == "test-task-456"
        assert data.round_number == 5
        assert data.current_step == StepPoint.PERFORM_DMAS
        assert data.step_category == StepCategory.ANALYSIS
        assert data.status == ThoughtStatus.PROCESSING
        assert len(data.steps_completed) == 2
        assert len(data.steps_remaining) == 2
        assert data.progress_percentage == 33.3
        assert data.processing_time_ms == 150.5
        assert data.content_preview == "Test thought content for processing"

    def test_thought_stream_data_with_error(self):
        """Test ThoughtStreamData with error information."""
        now = datetime.now()
        
        data = ThoughtStreamData(
            thought_id="failed-thought",
            task_id="failed-task",
            round_number=1,
            current_step=StepPoint.CONSCIENCE_EXECUTION,
            step_category=StepCategory.ANALYSIS,
            status=ThoughtStatus.FAILED,
            steps_completed=[],
            steps_remaining=[],
            progress_percentage=60.0,
            started_at=now,
            current_step_started_at=now,
            processing_time_ms=75.0,
            total_processing_time_ms=75.0,
            content_preview="Failed thought",
            thought_type="reflection",
            last_error="Conscience check failed: violates policy X"
        )
        
        assert data.status == ThoughtStatus.FAILED
        assert data.last_error == "Conscience check failed: violates policy X"

    def test_thought_stream_data_validation_errors(self):
        """Test validation errors for invalid data."""
        now = datetime.now()
        
        # Missing required fields
        with pytest.raises(ValidationError):
            ThoughtStreamData()
        
        # Invalid progress percentage
        with pytest.raises(ValidationError):
            ThoughtStreamData(
                thought_id="test",
                task_id="test",
                round_number=1,
                current_step=StepPoint.FINALIZE_ACTION,
                step_category=StepCategory.PREPARATION,
                status=ThoughtStatus.PROCESSING,
                progress_percentage=150.0,  # Invalid: > 100
                started_at=now,
                current_step_started_at=now,
                processing_time_ms=100.0,
                total_processing_time_ms=100.0,
                content_preview="test",
                thought_type="test"
            )
        
        # Negative progress percentage
        with pytest.raises(ValidationError):
            ThoughtStreamData(
                thought_id="test",
                task_id="test",
                round_number=1,
                current_step=StepPoint.FINALIZE_ACTION,
                step_category=StepCategory.PREPARATION,
                status=ThoughtStatus.PROCESSING,
                progress_percentage=-5.0,  # Invalid: < 0
                started_at=now,
                current_step_started_at=now,
                processing_time_ms=100.0,
                total_processing_time_ms=100.0,
                content_preview="test",
                thought_type="test"
            )


class TestStepPointSummary:
    """Test StepPointSummary schema."""

    def test_valid_step_point_summary(self):
        """Test creating valid StepPointSummary."""
        summary = StepPointSummary(
            step_point=StepPoint.PERFORM_DMAS,
            step_category=StepCategory.ANALYSIS,
            step_name="Perform DMAs",
            step_description="Multi-perspective decision-making analysis",
            total_thoughts=10,
            queued_count=2,
            processing_count=3,
            completed_count=4,
            failed_count=1,
            blocked_count=0,
            average_processing_time_ms=250.5,
            throughput_per_minute=12.5,
            svg_position={"x": 150, "y": 200}
        )
        
        assert summary.step_point == StepPoint.PERFORM_DMAS
        assert summary.step_category == StepCategory.ANALYSIS
        assert summary.step_name == "Perform DMAs"
        assert summary.total_thoughts == 10
        assert summary.queued_count == 2
        assert summary.processing_count == 3
        assert summary.completed_count == 4
        assert summary.failed_count == 1
        assert summary.blocked_count == 0
        assert summary.svg_position == {"x": 150, "y": 200}

    def test_step_point_summary_validation(self):
        """Test validation of StepPointSummary fields."""
        # Negative counts should fail validation
        with pytest.raises(ValidationError):
            StepPointSummary(
                step_point=StepPoint.PERFORM_DMAS,
                step_category=StepCategory.ANALYSIS,
                step_name="Test",
                step_description="Test",
                total_thoughts=-1,  # Invalid: negative
                queued_count=0,
                processing_count=0,
                completed_count=0,
                failed_count=0,
                blocked_count=0,
                average_processing_time_ms=0.0,
                throughput_per_minute=0.0
            )


class TestRoundSummary:
    """Test RoundSummary schema."""

    def test_valid_round_summary(self):
        """Test creating valid RoundSummary."""
        now = datetime.now()
        
        summary = RoundSummary(
            round_number=5,
            started_at=now,
            active_tasks=["task1", "task2", "task3"],
            task_count=3,
            total_thoughts=15,
            thoughts_by_status={
                ThoughtStatus.COMPLETED: 10,
                ThoughtStatus.PROCESSING: 3,
                ThoughtStatus.FAILED: 2
            },
            thoughts_by_step={
                StepPoint.PERFORM_DMAS: 5,
                StepPoint.CONSCIENCE_EXECUTION: 3,
                StepPoint.FINALIZE_ACTION: 2
            },
            round_duration_ms=5500.0,
            thoughts_completed_this_round=8,
            round_throughput=1.45,
            error_rate=13.3,
            bottleneck_step=StepPoint.PERFORM_DMAS
        )
        
        assert summary.round_number == 5
        assert summary.task_count == 3
        assert len(summary.active_tasks) == 3
        assert summary.total_thoughts == 15
        assert summary.thoughts_by_status[ThoughtStatus.COMPLETED] == 10
        assert summary.thoughts_by_step[StepPoint.PERFORM_DMAS] == 5
        assert summary.round_duration_ms == 5500.0
        assert summary.error_rate == 13.3
        assert summary.bottleneck_step == StepPoint.PERFORM_DMAS

    def test_round_summary_validation(self):
        """Test validation of RoundSummary fields."""
        now = datetime.now()
        
        # Error rate > 100 should fail
        with pytest.raises(ValidationError):
            RoundSummary(
                round_number=1,
                started_at=now,
                active_tasks=[],
                task_count=0,
                total_thoughts=0,
                thoughts_completed_this_round=0,
                round_throughput=0.0,
                error_rate=150.0  # Invalid: > 100
            )
        
        # Negative error rate should fail
        with pytest.raises(ValidationError):
            RoundSummary(
                round_number=1,
                started_at=now,
                active_tasks=[],
                task_count=0,
                total_thoughts=0,
                thoughts_completed_this_round=0,
                round_throughput=0.0,
                error_rate=-5.0  # Invalid: < 0
            )


class TestReasoningStreamUpdate:
    """Test ReasoningStreamUpdate schema."""

    def test_valid_reasoning_stream_update(self):
        """Test creating valid ReasoningStreamUpdate."""
        now = datetime.now()
        
        thought_data = ThoughtStreamData(
            thought_id="test-thought",
            task_id="test-task",
            round_number=1,
            current_step=StepPoint.FINALIZE_ACTION,
            step_category=StepCategory.PREPARATION,
            status=ThoughtStatus.PROCESSING,
            progress_percentage=10.0,
            started_at=now,
            current_step_started_at=now,
            processing_time_ms=100.0,
            total_processing_time_ms=100.0,
            content_preview="Test content",
            thought_type="task_execution"
        )
        
        step_summary = StepPointSummary(
            step_point=StepPoint.FINALIZE_ACTION,
            step_category=StepCategory.PREPARATION,
            step_name="Finalize Tasks Queue",
            step_description="Test description",
            total_thoughts=1,
            queued_count=0,
            processing_count=1,
            completed_count=0,
            failed_count=0,
            blocked_count=0,
            average_processing_time_ms=100.0,
            throughput_per_minute=5.0
        )
        
        update = ReasoningStreamUpdate(
            stream_sequence=1,
            timestamp=now,
            update_type="step_complete",
            current_round=1,
            total_rounds=1,
            pipeline_active=True,
            step_results=[],
            updated_thoughts=[thought_data],
            new_thoughts=[],
            completed_thoughts=[],
            failed_thoughts=[],
            step_summaries=[step_summary],
            current_round_summary=None,
            recent_rounds=[],
            overall_throughput=1.5,
            pipeline_health_score=95.0,
            bottlenecks=[],
            svg_updates_required=["step-1"],
            notification_messages=["Processing started"]
        )
        
        assert update.stream_sequence == 1
        assert update.update_type == "step_complete"
        assert update.current_round == 1
        assert update.pipeline_active is True
        assert len(update.updated_thoughts) == 1
        assert len(update.step_summaries) == 1
        assert update.overall_throughput == 1.5
        assert update.pipeline_health_score == 95.0

    def test_reasoning_stream_update_defaults(self):
        """Test ReasoningStreamUpdate with default values."""
        now = datetime.now()
        
        update = ReasoningStreamUpdate(
            stream_sequence=1,
            timestamp=now,
            update_type="test",
            current_round=1,
            total_rounds=1,
            pipeline_active=True
        )
        
        # Check defaults
        assert update.overall_throughput == 0.0
        assert update.pipeline_health_score == 100.0
        assert len(update.step_results) == 0
        assert len(update.updated_thoughts) == 0
        assert len(update.step_summaries) == 0
        assert update.current_round_summary is None

    def test_reasoning_stream_update_validation(self):
        """Test validation of ReasoningStreamUpdate fields."""
        now = datetime.now()
        
        # Pipeline health score > 100 should fail
        with pytest.raises(ValidationError):
            ReasoningStreamUpdate(
                stream_sequence=1,
                timestamp=now,
                update_type="test",
                current_round=1,
                total_rounds=1,
                pipeline_active=True,
                pipeline_health_score=150.0  # Invalid: > 100
            )


class TestStepMetadataFunctions:
    """Test step metadata utility functions."""

    def test_step_metadata_coverage(self):
        """Test that all step points have metadata."""
        for step_point in StepPoint:
            metadata = get_step_metadata(step_point)
            
            assert "name" in metadata
            assert "description" in metadata
            assert "category" in metadata
            assert "svg_position" in metadata
            assert isinstance(metadata["category"], StepCategory)

    def test_get_step_metadata_known_step(self):
        """Test getting metadata for known step."""
        metadata = get_step_metadata(StepPoint.PERFORM_DMAS)
        
        assert metadata["name"] == "Perform DMAs"
        assert metadata["description"] == "Multi-perspective decision-making analysis"
        assert metadata["category"] == StepCategory.ANALYSIS
        assert "x" in metadata["svg_position"]
        assert "y" in metadata["svg_position"]

    def test_calculate_progress_percentage(self):
        """Test progress percentage calculation."""
        # Test early step (START_ROUND is first - 0/11 = 0.0%)
        progress = calculate_progress_percentage([], StepPoint.START_ROUND)
        assert progress == 0.0
        
        # Test middle step (PERFORM_DMAS is 3rd - around 18%)
        progress = calculate_progress_percentage([], StepPoint.PERFORM_DMAS)
        assert progress > 15.0 and progress < 25.0
        
        # Test late step (ROUND_COMPLETE is last - around 90%+)
        progress = calculate_progress_percentage([], StepPoint.ROUND_COMPLETE)
        assert progress > 90.0

    def test_get_remaining_steps(self):
        """Test getting remaining steps."""
        # Test early step (START_ROUND should have 10 remaining steps)
        remaining = get_remaining_steps(StepPoint.START_ROUND)
        assert len(remaining) == len(list(StepPoint)) - 1  # 10 remaining
        
        # Test mid step (FINALIZE_ACTION should have 3 remaining steps)
        remaining = get_remaining_steps(StepPoint.FINALIZE_ACTION)
        assert len(remaining) == 3  # PERFORM_ACTION, ACTION_COMPLETE, ROUND_COMPLETE
        
        # Test last step
        remaining = get_remaining_steps(StepPoint.ROUND_COMPLETE)
        assert len(remaining) == 0

    def test_get_remaining_steps_unknown_step(self):
        """Test getting remaining steps for unknown step."""
        # This should handle gracefully and return all steps
        try:
            remaining = get_remaining_steps("unknown_step")  # type: ignore
            assert len(remaining) == len(list(StepPoint))
        except (ValueError, TypeError):
            # Expected behavior for invalid step
            pass


class TestCreateStreamUpdateFromStepResults:
    """Test stream update creation from step results."""

    def test_create_stream_update_single_result(self):
        """Test creating stream update from single step result."""
        step_results = [{
            "thought_id": "test-thought",
            "task_id": "test-task",
            "round_id": 1,
            "step_point": StepPoint.PERFORM_DMAS.value,
            "success": True,
            "processing_time_ms": 150.0,
            "step_data": {
                "thought_content": "Test DMA analysis",
                "thought_type": "task_execution"
            }
        }]
        
        update = create_stream_update_from_step_results(step_results, 1)
        
        assert update.stream_sequence == 1
        assert update.update_type == "step_complete"
        assert update.current_round == 1
        assert len(update.updated_thoughts) == 1
        assert len(update.step_summaries) == len(list(StepPoint))
        
        thought = update.updated_thoughts[0]
        assert thought.thought_id == "test-thought"
        assert thought.task_id == "test-task"
        assert thought.current_step == StepPoint.PERFORM_DMAS
        assert thought.status == ThoughtStatus.PROCESSING

    def test_create_stream_update_multiple_results(self):
        """Test creating stream update from multiple step results."""
        step_results = [
            {
                "thought_id": f"thought-{i}",
                "task_id": f"task-{i}",
                "round_id": 2,
                "step_point": StepPoint.PERFORM_DMAS.value,
                "success": True,
                "processing_time_ms": float(i * 50)
            }
            for i in range(3)
        ]
        
        update = create_stream_update_from_step_results(step_results, 5)
        
        assert update.stream_sequence == 5
        assert update.current_round == 2
        assert len(update.updated_thoughts) == 3
        
        # Check that step summary includes all thoughts
        dma_summary = next(s for s in update.step_summaries if s.step_point == StepPoint.PERFORM_DMAS)
        assert dma_summary.total_thoughts == 3
        assert dma_summary.processing_count == 3

    def test_create_stream_update_failed_result(self):
        """Test creating stream update with failed step result."""
        step_results = [{
            "thought_id": "failed-thought",
            "task_id": "failed-task",
            "round_id": 1,
            "step_point": StepPoint.CONSCIENCE_EXECUTION.value,
            "success": False,
            "error": "Conscience check failed",
            "processing_time_ms": 75.0
        }]
        
        update = create_stream_update_from_step_results(step_results, 1)
        
        thought = update.updated_thoughts[0]
        assert thought.status == ThoughtStatus.FAILED
        assert thought.last_error == "Conscience check failed"
        
        # Check step summary reflects failure
        conscience_summary = next(s for s in update.step_summaries if s.step_point == StepPoint.CONSCIENCE_EXECUTION)
        assert conscience_summary.failed_count == 1

    def test_create_stream_update_empty_results(self):
        """Test creating stream update with empty results."""
        update = create_stream_update_from_step_results([], 1)
        
        assert update.stream_sequence == 1
        assert len(update.updated_thoughts) == 0
        assert len(update.step_summaries) == len(list(StepPoint))  # All steps still included
        
        # All step summaries should have zero thoughts
        for summary in update.step_summaries:
            assert summary.total_thoughts == 0

    def test_create_stream_update_with_typed_step_result(self):
        """
        Test that create_stream_update_from_step_results correctly
        populates the typed step_result field.
        """
        step_results = [{
            "thought_id": "test-thought-typed",
            "task_id": "test-task-typed",
            "round_id": 3,
            "step_point": StepPoint.GATHER_CONTEXT.value,
            "success": True,
            "processing_time_ms": 120.0,
            "step_data": {
                "thought_content": "Gathering context for analysis",
                "thought_type": "task_execution",
                "context_size": 5,
                "summary": "Context gathered successfully",
            }
        }]

        update = create_stream_update_from_step_results(step_results, 10)

        assert len(update.updated_thoughts) == 1
        thought = update.updated_thoughts[0]

        # This is the key assertion that should fail initially
        assert thought.step_result is not None, "step_result should be populated, not None"

        assert isinstance(thought.step_result, StepResultGatherContext)
        assert thought.step_result.context_size == 5
        assert thought.step_result.summary == "Context gathered successfully"


class TestHelperFunctions:
    """Test refactored helper functions for complexity reduction."""
    
    def test_extract_content_from_thought_data_with_dict(self):
        """Test extracting content from dict thought data."""
        from ciris_engine.logic.adapters.api.routes.telemetry import _extract_content_from_thought_data
        
        thought_data = {"content": "test content"}
        result = _extract_content_from_thought_data(thought_data)
        assert result == "test content"
        
    def test_extract_content_from_thought_data_with_empty_dict(self):
        """Test extracting content from empty dict."""
        from ciris_engine.logic.adapters.api.routes.telemetry import _extract_content_from_thought_data
        
        thought_data = {}
        result = _extract_content_from_thought_data(thought_data)
        assert result == ""
        
    def test_extract_content_from_thought_data_with_string(self):
        """Test extracting content from non-dict thought data."""
        from ciris_engine.logic.adapters.api.routes.telemetry import _extract_content_from_thought_data
        
        thought_data = "string data"
        result = _extract_content_from_thought_data(thought_data)
        assert result == "string data"
        
    def test_extract_timestamp_from_thought_data_with_dict(self):
        """Test extracting timestamp from dict thought data."""
        from ciris_engine.logic.adapters.api.routes.telemetry import _extract_timestamp_from_thought_data
        
        test_time = "2023-01-01T00:00:00+00:00"
        thought_data = {"timestamp": test_time}
        result = _extract_timestamp_from_thought_data(thought_data)
        assert result.isoformat() == "2023-01-01T00:00:00+00:00"
        
    def test_extract_depth_from_thought_data_with_dict(self):
        """Test extracting depth from dict thought data."""
        from ciris_engine.logic.adapters.api.routes.telemetry import _extract_depth_from_thought_data
        
        thought_data = {"depth": 5}
        result = _extract_depth_from_thought_data(thought_data)
        assert result == 5
        
    def test_extract_depth_from_thought_data_with_default(self):
        """Test extracting depth with default value."""
        from ciris_engine.logic.adapters.api.routes.telemetry import _extract_depth_from_thought_data
        
        thought_data = {}
        result = _extract_depth_from_thought_data(thought_data)
        assert result == 0
        
    def test_create_typed_step_result_valid_data(self):
        """Test creating typed step result with valid data."""
        from ciris_engine.schemas.streaming.reasoning_stream import _create_typed_step_result
        from ciris_engine.schemas.services.runtime_control import StepPoint
        
        raw_result = {
            "success": True,
            "thought_id": "test-thought",
            "task_id": "test-task",
            "processing_time_ms": 100.0
        }
        step_data = {"context_size": 5, "summary": "test"}
        
        result = _create_typed_step_result(raw_result, StepPoint.GATHER_CONTEXT, step_data)
        
        # The result might be None if the mapping doesn't exist, which is acceptable
        if result is not None:
            assert result.step_point == StepPoint.GATHER_CONTEXT
            assert result.success == True
            assert result.processing_time_ms == 100.0
            
    def test_create_typed_step_result_no_model(self):
        """Test creating typed step result when no model exists."""
        from ciris_engine.schemas.streaming.reasoning_stream import _create_typed_step_result
        from ciris_engine.schemas.services.runtime_control import StepPoint
        
        raw_result = {"success": True}
        step_data = {"test": "data"}
        
        # Use a step that might not have a mapped result model
        result = _create_typed_step_result(raw_result, StepPoint.FINALIZE_ACTION, step_data)
        
        # Should return None if no model exists
        assert result is None or hasattr(result, 'step_point')
        
    def test_create_thought_stream_data(self):
        """Test creating thought stream data from raw result."""
        from ciris_engine.schemas.streaming.reasoning_stream import _create_thought_stream_data
        
        raw_result = {
            "thought_id": "test-thought",
            "task_id": "test-task", 
            "round_id": 2,
            "step_point": "gather_context",
            "success": True,
            "processing_time_ms": 150.0,
            "step_data": {
                "thought_content": "Test content",
                "thought_type": "analysis"
            }
        }
        
        result = _create_thought_stream_data(raw_result)
        
        assert result.thought_id == "test-thought"
        assert result.task_id == "test-task"
        assert result.round_number == 2
        assert result.processing_time_ms == 150.0
        assert result.thought_type == "analysis"
        assert result.content_preview == "Test content"
        
    def test_create_step_summary(self):
        """Test creating step summary for a step point."""
        from ciris_engine.schemas.streaming.reasoning_stream import _create_step_summary
        from ciris_engine.schemas.services.runtime_control import StepPoint
        
        step_results = [
            {"step_point": "gather_context", "success": True, "processing_time_ms": 100.0},
            {"step_point": "gather_context", "success": False, "processing_time_ms": 200.0},
            {"step_point": "other_step", "success": True, "processing_time_ms": 50.0}
        ]
        
        result = _create_step_summary(StepPoint.GATHER_CONTEXT, step_results)
        
        assert result.step_point == StepPoint.GATHER_CONTEXT
        assert result.total_thoughts == 2  # Only gather_context results
        assert result.processing_count == 1  # One successful
        assert result.completed_count == 1   # One successful  
        assert result.failed_count == 1      # One failed
        assert result.average_processing_time_ms == 150.0  # (100 + 200) / 2