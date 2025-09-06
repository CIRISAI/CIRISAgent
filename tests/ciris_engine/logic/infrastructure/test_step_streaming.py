"""
Unit tests for step result streaming infrastructure.
"""

import asyncio
import json
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ciris_engine.logic.infrastructure.step_streaming import StepResultStream, step_result_stream
from ciris_engine.schemas.services.runtime_control import StepPoint


class TestStepResultStream:
    """Test the StepResultStream class."""

    def test_init(self):
        """Test stream initialization."""
        stream = StepResultStream()
        
        assert stream._subscribers is not None
        assert stream._step_count == 0
        assert stream._is_enabled is True
        assert stream.get_stats()["enabled"] is True
        assert stream.get_stats()["subscriber_count"] == 0
        assert stream.get_stats()["steps_broadcast"] == 0

    def test_subscribe_unsubscribe(self):
        """Test subscriber management."""
        stream = StepResultStream()
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
        stream = StepResultStream()
        
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
        stream = StepResultStream()
        queue = asyncio.Queue()
        stream.subscribe(queue)
        
        # Disable streaming
        stream.disable()
        
        step_result = {
            "thought_id": "test-thought",
            "step_point": StepPoint.FINALIZE_TASKS_QUEUE.value,
            "success": True,
            "processing_time_ms": 100.0
        }
        
        await stream.broadcast_step_result(step_result)
        
        # Queue should be empty
        assert queue.empty()
        assert stream.get_stats()["steps_broadcast"] == 0

    @pytest.mark.asyncio
    async def test_broadcast_step_result_no_subscribers(self):
        """Test broadcasting with no subscribers does nothing."""
        stream = StepResultStream()
        
        step_result = {
            "thought_id": "test-thought",
            "step_point": StepPoint.FINALIZE_TASKS_QUEUE.value,
            "success": True,
            "processing_time_ms": 100.0
        }
        
        await stream.broadcast_step_result(step_result)
        
        # Should not increment step count
        assert stream.get_stats()["steps_broadcast"] == 0

    @pytest.mark.asyncio
    async def test_broadcast_step_result_success(self):
        """Test successful step result broadcasting."""
        stream = StepResultStream()
        queue = asyncio.Queue()
        stream.subscribe(queue)
        
        step_result = {
            "thought_id": "test-thought",
            "task_id": "test-task", 
            "round_id": 1,
            "step_point": StepPoint.FINALIZE_TASKS_QUEUE.value,
            "success": True,
            "processing_time_ms": 100.0,
            "step_data": {"thought_content": "Test thought content"}
        }
        
        with patch('ciris_engine.schemas.streaming.reasoning_stream.create_stream_update_from_step_results') as mock_create:
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
    async def test_broadcast_step_result_fallback_on_error(self):
        """Test fallback to raw result when stream update creation fails."""
        stream = StepResultStream()
        queue = asyncio.Queue()
        stream.subscribe(queue)
        
        step_result = {
            "thought_id": "test-thought",
            "step_point": StepPoint.FINALIZE_TASKS_QUEUE.value,
            "success": True,
            "processing_time_ms": 100.0
        }
        
        with patch('ciris_engine.schemas.streaming.reasoning_stream.create_stream_update_from_step_results', side_effect=Exception("Test error")):
            await stream.broadcast_step_result(step_result)
        
        # Should still broadcast raw result with metadata
        assert not queue.empty()
        broadcasted_result = await queue.get()
        
        assert broadcasted_result["thought_id"] == "test-thought"
        assert broadcasted_result["step_point"] == StepPoint.FINALIZE_TASKS_QUEUE.value
        assert "stream_sequence" in broadcasted_result
        assert "broadcast_timestamp" in broadcasted_result

    @pytest.mark.asyncio
    async def test_broadcast_step_result_full_queue(self):
        """Test handling of full subscriber queues."""
        stream = StepResultStream()
        
        # Create a queue with maxsize=1 and fill it
        queue = asyncio.Queue(maxsize=1)
        queue.put_nowait("blocking_item")
        stream.subscribe(queue)
        
        step_result = {
            "thought_id": "test-thought",
            "step_point": StepPoint.FINALIZE_TASKS_QUEUE.value,
            "success": True
        }
        
        with patch('ciris_engine.schemas.streaming.reasoning_stream.create_stream_update_from_step_results') as mock_create:
            mock_stream_update = MagicMock()
            mock_stream_update.model_dump.return_value = {"test": "data"}
            mock_create.return_value = mock_stream_update
            
            await stream.broadcast_step_result(step_result)
        
        # Should handle the QueueFull exception gracefully
        assert stream.get_stats()["steps_broadcast"] == 1

    @pytest.mark.asyncio
    async def test_broadcast_multiple_subscribers(self):
        """Test broadcasting to multiple subscribers."""
        stream = StepResultStream()
        
        # Create multiple queues
        queues = [asyncio.Queue() for _ in range(3)]
        for queue in queues:
            stream.subscribe(queue)
        
        step_result = {
            "thought_id": "test-thought",
            "step_point": StepPoint.FINALIZE_TASKS_QUEUE.value,
            "success": True
        }
        
        with patch('ciris_engine.schemas.streaming.reasoning_stream.create_stream_update_from_step_results') as mock_create:
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
        """Test that global step_result_stream instance exists."""
        assert step_result_stream is not None
        assert isinstance(step_result_stream, StepResultStream)


@pytest.fixture
def fresh_stream():
    """Provide a fresh StepResultStream instance for each test."""
    return StepResultStream()


class TestStepResultStreamIntegration:
    """Integration tests for step result streaming."""

    @pytest.mark.asyncio
    async def test_full_streaming_flow(self, fresh_stream):
        """Test complete streaming flow from step result to UI data."""
        stream = fresh_stream
        client_queue = asyncio.Queue()
        stream.subscribe(client_queue)
        
        # Simulate a complete step result
        step_result = {
            "thought_id": "integration-test-thought",
            "task_id": "integration-test-task",
            "round_id": 5,
            "step_point": StepPoint.PERFORM_DMAS.value,
            "success": True,
            "processing_time_ms": 250.5,
            "step_data": {
                "thought_content": "Testing DMA performance analysis",
                "dmas_executed": ["ethical", "common_sense", "domain_specific"],
                "analysis_depth": "comprehensive"
            }
        }
        
        # Broadcast the result
        await stream.broadcast_step_result(step_result)
        
        # Verify client receives UI-friendly data
        assert not client_queue.empty()
        ui_update = await client_queue.get()
        
        # Should be a structured stream update
        assert "updated_thoughts" in ui_update
        assert "step_summaries" in ui_update
        assert "current_round" in ui_update
        assert "pipeline_active" in ui_update
        
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
        for i in range(10):
            step_results.append({
                "thought_id": f"concurrent-thought-{i}",
                "task_id": f"concurrent-task-{i}",
                "round_id": i + 1,
                "step_point": list(StepPoint)[i % len(StepPoint)].value,
                "success": True,
                "processing_time_ms": float(i * 10)
            })
        
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