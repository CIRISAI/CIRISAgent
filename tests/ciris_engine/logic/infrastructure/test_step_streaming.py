"""
Unit tests for step result streaming infrastructure.
"""

import asyncio
import json
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ciris_engine.logic.infrastructure.step_streaming import ReasoningEventStream, reasoning_event_stream
from ciris_engine.schemas.services.runtime_control import (
    FinalizeActionStepData,
    PerformDMAsStepData,
    SpanAttribute,
    StepPoint,
    StepResultData,
    TraceContext,
)


def create_test_step_result_data(
    thought_id: str = "test-thought",
    task_id: str = "test-task",
    step_point: StepPoint = StepPoint.FINALIZE_ACTION,
    success: bool = True,
    processing_time_ms: float = 100.0,
    **kwargs,
) -> StepResultData:
    """Helper to create StepResultData for tests."""
    from datetime import datetime

    trace_context = TraceContext(
        trace_id=f"trace-{thought_id}",
        span_id=f"span-{step_point.value}",
        span_name=f"test-{step_point.value}",
        operation_name=f"test_{step_point.value}",
        start_time_ns=1000000000,
        end_time_ns=1000100000,
        duration_ns=100000,
    )

    timestamp = datetime.now().isoformat()

    # Create appropriate step data based on step point
    if step_point == StepPoint.PERFORM_DMAS:
        step_data = PerformDMAsStepData(
            timestamp=timestamp,
            thought_id=thought_id,
            task_id=task_id,
            processing_time_ms=processing_time_ms,
            success=success,
            dma_results=kwargs.get("dma_results", "test DMA results"),
            context=kwargs.get("context", "test context"),
        )
    else:  # Default to FINALIZE_ACTION
        step_data = FinalizeActionStepData(
            timestamp=timestamp,
            thought_id=thought_id,
            task_id=task_id,
            processing_time_ms=processing_time_ms,
            success=success,
            selected_action=kwargs.get("selected_action", "test_action"),
            selection_reasoning=kwargs.get("selection_reasoning", "test reasoning"),
        )

    return StepResultData(
        step_point=step_point.value,
        success=success,
        processing_time_ms=processing_time_ms,
        thought_id=thought_id,
        task_id=task_id,
        step_data=step_data,
        trace_context=trace_context,
        span_attributes=kwargs.get("span_attributes", []),
    )


class TestReasoningEventStream:
    """Test the ReasoningEventStream class."""

    def test_init(self):
        """Test stream initialization."""
        stream = ReasoningEventStream()

        assert stream._subscribers is not None
        assert stream._step_count == 0
        assert stream._is_enabled is True
        assert stream.get_stats()["enabled"] is True
        assert stream.get_stats()["subscriber_count"] == 0
        assert stream.get_stats()["steps_broadcast"] == 0

    def test_subscribe_unsubscribe(self):
        """Test subscriber management."""
        stream = ReasoningEventStream()
        queue = asyncio.Queue()

        # Subscribe
        stream.subscribe(queue)
        assert len(stream._subscribers) == 1
        assert stream.get_stats()["subscriber_count"] == 1

        # Unsubscribe
        stream.unsubscribe(queue)
        assert len(stream._subscribers) == 0
        assert stream.get_stats()["subscriber_count"] == 0

    def test_enable_disable(self):
        """Test enabling and disabling streaming."""
        stream = ReasoningEventStream()

        # Initially enabled
        assert stream._is_enabled is True

        # Disable
        stream.disable()
        assert stream._is_enabled is False
        assert stream.get_stats()["enabled"] is False

        # Enable
        stream.enable()
        assert stream._is_enabled is True
        assert stream.get_stats()["enabled"] is True

    @pytest.mark.asyncio
    async def test_broadcast_step_result_disabled(self):
        """Test broadcasting when disabled does nothing."""
        stream = ReasoningEventStream()
        queue = asyncio.Queue()
        stream.subscribe(queue)

        # Disable streaming
        stream.disable()

        step_result = create_test_step_result_data()
        await stream.broadcast_step_result(step_result)

        # Queue should be empty
        assert queue.empty()
        assert stream.get_stats()["steps_broadcast"] == 0

    @pytest.mark.asyncio
    async def test_broadcast_step_result_no_subscribers(self):
        """Test broadcasting with no subscribers does nothing."""
        stream = ReasoningEventStream()

        step_result = create_test_step_result_data()
        await stream.broadcast_step_result(step_result)

        # Should not increment step count
        assert stream.get_stats()["steps_broadcast"] == 0

    @pytest.mark.asyncio
    async def test_broadcast_step_result_success(self):
        """Test successful step result broadcasting."""
        stream = ReasoningEventStream()
        queue = asyncio.Queue()
        stream.subscribe(queue)

        step_result = {
            "thought_id": "test-thought",
            "task_id": "test-task",
            "round_id": 1,
            "step_point": StepPoint.FINALIZE_ACTION.value,
            "success": True,
            "processing_time_ms": 100.0,
            "step_data": {"thought_content": "Test thought content"},
        }

        with patch(
            "ciris_engine.schemas.streaming.reasoning_stream.create_stream_update_from_step_results"
        ) as mock_create:
            mock_stream_update = MagicMock()
            mock_stream_update.model_dump.return_value = {"test": "stream_update"}
            mock_create.return_value = mock_stream_update

            await stream.broadcast_step_result(step_result)

        # Check step count incremented
        assert stream.get_stats()["steps_broadcast"] == 1

        # Check queue received the update
        assert not queue.empty()
        broadcasted_result = await queue.get()

        # Should contain the stream update plus metadata
        assert "test" in broadcasted_result
        assert "broadcast_timestamp" in broadcasted_result
        assert "subscriber_count" in broadcasted_result
        assert broadcasted_result["subscriber_count"] == 1

    @pytest.mark.asyncio
    async def test_broadcast_step_result_error_handling(self):
        """Test that errors in stream update creation are handled gracefully."""
        stream = ReasoningEventStream()
        queue = asyncio.Queue()
        stream.subscribe(queue)

        step_result = create_test_step_result_data()

        with patch(
            "ciris_engine.schemas.streaming.reasoning_stream.create_stream_update_from_step_results",
            side_effect=Exception("Test error"),
        ):
            # Should fail fast and loud - no fallback
            with pytest.raises(Exception, match="Test error"):
                await stream.broadcast_step_result(step_result)

    @pytest.mark.asyncio
    async def test_broadcast_step_result_full_queue(self):
        """Test handling of full subscriber queues."""
        stream = ReasoningEventStream()

        # Create a queue with maxsize=1 and fill it
        queue = asyncio.Queue(maxsize=1)
        queue.put_nowait("blocking_item")
        stream.subscribe(queue)

        step_result = {"thought_id": "test-thought", "step_point": StepPoint.FINALIZE_ACTION.value, "success": True}

        with patch(
            "ciris_engine.schemas.streaming.reasoning_stream.create_stream_update_from_step_results"
        ) as mock_create:
            mock_stream_update = MagicMock()
            mock_stream_update.model_dump.return_value = {"test": "data"}
            mock_create.return_value = mock_stream_update

            await stream.broadcast_step_result(step_result)

        # Should handle the QueueFull exception gracefully
        assert stream.get_stats()["steps_broadcast"] == 1

    @pytest.mark.asyncio
    async def test_broadcast_multiple_subscribers(self):
        """Test broadcasting to multiple subscribers."""
        stream = ReasoningEventStream()

        # Create multiple queues
        queues = [asyncio.Queue() for _ in range(3)]
        for queue in queues:
            stream.subscribe(queue)

        step_result = {"thought_id": "test-thought", "step_point": StepPoint.FINALIZE_ACTION.value, "success": True}

        with patch(
            "ciris_engine.schemas.streaming.reasoning_stream.create_stream_update_from_step_results"
        ) as mock_create:
            mock_stream_update = MagicMock()
            mock_stream_update.model_dump.return_value = {"test": "data"}
            mock_create.return_value = mock_stream_update

            await stream.broadcast_step_result(step_result)

        # All queues should receive the broadcast
        for queue in queues:
            assert not queue.empty()
            result = await queue.get()
            assert "test" in result
            assert result["subscriber_count"] == 3

    def test_global_instance_exists(self):
        """Test that global reasoning_event_stream instance exists."""
        assert reasoning_event_stream is not None
        assert isinstance(reasoning_event_stream, ReasoningEventStream)


@pytest.fixture
def fresh_stream():
    """Provide a fresh ReasoningEventStream instance for each test."""
    return ReasoningEventStream()


class TestReasoningEventStreamIntegration:
    """Integration tests for step result streaming."""

    @pytest.mark.asyncio
    async def test_full_streaming_flow(self, fresh_stream):
        """Test complete streaming flow from step result to UI data."""
        stream = fresh_stream
        client_queue = asyncio.Queue()
        stream.subscribe(client_queue)

        # Simulate a complete step result
        step_result = create_test_step_result_data(
            thought_id="integration-test-thought",
            task_id="integration-test-task",
            step_point=StepPoint.PERFORM_DMAS,
            success=True,
            processing_time_ms=250.5,
            dma_results="DMA results: ethical, common_sense, domain_specific",
            context="Testing DMA performance analysis",
        )

        # Broadcast the result
        await stream.broadcast_step_result(step_result)

        # Verify client receives UI-friendly data
        assert not client_queue.empty()
        ui_update = await client_queue.get()

        # Should be a structured stream update with step result data
        assert "updated_thoughts" in ui_update
        assert len(ui_update["updated_thoughts"]) == 1

        thought = ui_update["updated_thoughts"][0]
        assert thought["thought_id"] == "integration-test-thought"
        assert thought["task_id"] == "integration-test-task"
        assert thought["current_step"] == StepPoint.PERFORM_DMAS
        assert "step_result" in thought

        # Should have enrichment metadata
        assert "broadcast_timestamp" in ui_update
        assert "subscriber_count" in ui_update
        assert ui_update["subscriber_count"] == 1

    @pytest.mark.asyncio
    async def test_concurrent_broadcasts(self, fresh_stream):
        """Test handling of concurrent step result broadcasts."""
        stream = fresh_stream
        queues = [asyncio.Queue() for _ in range(5)]

        for queue in queues:
            stream.subscribe(queue)

        # Create multiple step results to broadcast concurrently
        step_results = []
        step_points = list(StepPoint)
        for i in range(10):
            step_point = step_points[i % len(step_points)]
            step_results.append(
                create_test_step_result_data(
                    thought_id=f"concurrent-thought-{i}",
                    task_id=f"concurrent-task-{i}",
                    step_point=step_point,
                    success=True,
                    processing_time_ms=float(i * 10),
                )
            )

        # Broadcast all results concurrently
        tasks = [stream.broadcast_step_result(result) for result in step_results]
        await asyncio.gather(*tasks)

        # Verify all broadcasts completed
        assert stream.get_stats()["steps_broadcast"] == 10

        # Each queue should have received all broadcasts
        for queue in queues:
            received_count = 0
            while not queue.empty():
                await queue.get()
                received_count += 1
            assert received_count == 10
