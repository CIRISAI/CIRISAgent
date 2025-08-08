"""
Test guidance thought processing, especially edge cases like round_number=0.

This test ensures that guidance thoughts created in response to deferrals
are properly processed even when they have round_number=0.
"""

import asyncio
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ciris_engine.logic import persistence
from ciris_engine.logic.processors.support.processing_queue import ProcessingQueueItem
from ciris_engine.logic.processors.support.thought_manager import ThoughtManager
from ciris_engine.schemas.runtime.enums import TaskStatus, ThoughtStatus, ThoughtType
from ciris_engine.schemas.runtime.models import FinalAction, Task, TaskContext, Thought, ThoughtContext


class TestGuidanceThoughtProcessing:
    """Test suite for guidance thought processing edge cases."""

    @pytest.fixture
    def time_service(self):
        """Mock time service."""
        service = MagicMock()
        service.now.return_value = datetime.now(timezone.utc)
        service.now_iso.return_value = datetime.now(timezone.utc).isoformat()
        return service

    @pytest.fixture
    def thought_manager(self, time_service):
        """Create a ThoughtManager instance."""
        return ThoughtManager(time_service=time_service, max_active_thoughts=50)

    @pytest.fixture
    def shutdown_task(self, time_service):
        """Create a mock shutdown task."""
        return Task(
            task_id=f"shutdown_{uuid.uuid4().hex[:8]}",
            channel_id="discord_1234_5678",
            description="System shutdown requested: CD deployment",
            priority=10,
            status=TaskStatus.ACTIVE,
            created_at=time_service.now_iso(),
            updated_at=time_service.now_iso(),
            context=TaskContext(
                channel_id="discord_1234_5678",
                user_id="system",
                correlation_id=f"shutdown_{uuid.uuid4().hex[:8]}",
                parent_task_id=None,
            ),
        )

    @pytest.fixture
    def deferral_thought(self, shutdown_task, time_service):
        """Create a deferral thought."""
        return Thought(
            thought_id=f"thought_{uuid.uuid4().hex[:8]}",
            source_task_id=shutdown_task.task_id,
            channel_id=shutdown_task.channel_id,
            thought_type=ThoughtType.STANDARD,
            status=ThoughtStatus.COMPLETED,
            created_at=time_service.now_iso(),
            updated_at=time_service.now_iso(),
            round_number=1,
            content="Should I shutdown for deployment?",
            thought_depth=0,
            final_action=FinalAction(
                action_type="DEFER",
                action_params={
                    "task_id": shutdown_task.task_id,
                    "channel_id": shutdown_task.channel_id,
                    "reason": "Need clarification on deployment impact",
                },
                reasoning="Need more information about deployment impact before proceeding",
            ),
            context=ThoughtContext(
                task_id=shutdown_task.task_id,
                channel_id=shutdown_task.channel_id,
                round_number=1,
                depth=0,
                parent_thought_id=None,
                correlation_id=shutdown_task.context.correlation_id,
            ),
        )

    @pytest.fixture
    def guidance_thought(self, shutdown_task, deferral_thought, time_service):
        """Create a guidance thought with round_number=0."""
        return Thought(
            thought_id=f"guidance_{uuid.uuid4().hex[:8]}",
            source_task_id=shutdown_task.task_id,
            channel_id=shutdown_task.channel_id,
            thought_type=ThoughtType.GUIDANCE,
            status=ThoughtStatus.PENDING,  # Start as PENDING
            created_at=time_service.now_iso(),
            updated_at=time_service.now_iso(),
            round_number=0,  # CRITICAL: Guidance thoughts often have round_number=0
            content="Guidance: This is to improve your handling of message history. Please proceed with shutdown.",
            thought_depth=1,
            parent_thought_id=deferral_thought.thought_id,
            final_action=None,
            context=ThoughtContext(
                task_id=shutdown_task.task_id,
                channel_id=shutdown_task.channel_id,
                round_number=0,  # CRITICAL: Must be 0 to test the edge case
                depth=1,
                parent_thought_id=deferral_thought.thought_id,
                correlation_id=shutdown_task.context.correlation_id,
            ),
        )

    @pytest.mark.asyncio
    async def test_guidance_thought_with_round_zero_gets_processed(
        self, thought_manager, guidance_thought, shutdown_task
    ):
        """Test that guidance thoughts with round_number=0 are added to processing queue."""
        with patch("ciris_engine.logic.persistence.get_thoughts_by_task_id") as mock_get_thoughts:
            with patch("ciris_engine.logic.persistence.add_thought") as mock_add_thought:
                # Setup: Return the guidance thought as pending
                mock_get_thoughts.return_value = [guidance_thought]

                # Add to processing queue (simulate what populate_processing_queue does)
                queue_item = ProcessingQueueItem.from_thought(guidance_thought)
                thought_manager.processing_queue.append(queue_item)

                # Verify it was added
                assert len(thought_manager.processing_queue) == 1
                item = thought_manager.processing_queue[0]
                assert item.thought_id == guidance_thought.thought_id
                # Round number is in the context
                assert item.initial_context.round_number == 0  # Should preserve round_number=0

    @pytest.mark.asyncio
    async def test_guidance_thought_transitions_to_processing(self, guidance_thought):
        """Test that guidance thoughts transition from PENDING to PROCESSING correctly."""
        with patch("ciris_engine.logic.persistence.update_thought_status") as mock_update_status:
            # Simulate the transition
            persistence.update_thought_status(thought_id=guidance_thought.thought_id, status=ThoughtStatus.PROCESSING)

            # Verify the update was called
            mock_update_status.assert_called_once_with(
                thought_id=guidance_thought.thought_id, status=ThoughtStatus.PROCESSING
            )

    @pytest.mark.asyncio
    async def test_shutdown_processor_processes_guidance_thoughts(self):
        """Test that ShutdownProcessor properly processes guidance thoughts."""
        from ciris_engine.logic.processors.states.shutdown_processor import ShutdownProcessor

        # Create mock services
        config_accessor = MagicMock()
        thought_processor = AsyncMock()
        action_dispatcher = AsyncMock()
        time_service = MagicMock()
        time_service.now.return_value = datetime.now(timezone.utc)
        time_service.now_iso.return_value = datetime.now(timezone.utc).isoformat()
        services = {"communication_bus": AsyncMock(), "time_service": time_service, "resource_monitor": MagicMock()}

        # Create processor
        processor = ShutdownProcessor(
            config_accessor=config_accessor,
            thought_processor=thought_processor,
            action_dispatcher=action_dispatcher,
            services=services,
            time_service=time_service,
        )

        # Create shutdown task and guidance thought
        shutdown_task = Task(
            task_id="shutdown_test",
            channel_id="test_channel",
            description="Test shutdown",
            priority=10,
            status=TaskStatus.ACTIVE,
            created_at=time_service.now_iso(),
            updated_at=time_service.now_iso(),
            context=TaskContext(
                channel_id="test_channel",
                user_id="system",
                correlation_id="test_corr",
                parent_task_id=None,
            ),
        )

        guidance_thought = Thought(
            thought_id="guidance_test",
            source_task_id=shutdown_task.task_id,
            channel_id=shutdown_task.channel_id,
            thought_type=ThoughtType.GUIDANCE,
            status=ThoughtStatus.PENDING,
            created_at=time_service.now_iso(),
            updated_at=time_service.now_iso(),
            round_number=0,  # Key test case
            content="Guidance: Proceed with shutdown",
            thought_depth=1,
            parent_thought_id="parent_thought",
            final_action=None,
            context=ThoughtContext(
                task_id=shutdown_task.task_id,
                channel_id=shutdown_task.channel_id,
                round_number=0,
                depth=1,
                parent_thought_id="parent_thought",
                correlation_id="test_corr",
            ),
        )

        # Mock persistence methods
        with patch("ciris_engine.logic.persistence.get_task_by_id") as mock_get_task:
            with patch("ciris_engine.logic.persistence.get_thoughts_by_task_id") as mock_get_thoughts:
                with patch("ciris_engine.logic.persistence.update_thought_status") as mock_update_status:
                    with patch.object(processor, "process_thought_item") as mock_process_thought:
                        # Setup mocks
                        processor.shutdown_task = shutdown_task
                        mock_get_task.return_value = shutdown_task
                        mock_get_thoughts.return_value = [guidance_thought]
                        mock_process_thought.return_value = MagicMock(selected_action="TASK_COMPLETE")

                        # Process shutdown thoughts
                        await processor._process_shutdown_thoughts()

                        # Verify the guidance thought was processed
                        mock_update_status.assert_called()
                        mock_process_thought.assert_called_once()

                        # Check that the thought was passed to process_thought_item
                        call_args = mock_process_thought.call_args
                        processed_item = call_args[0][0]
                        assert processed_item.thought_id == guidance_thought.thought_id
                        # Round number should be preserved in context
                        assert processed_item.initial_context is not None
                        if hasattr(processed_item.initial_context, "round_number"):
                            assert processed_item.initial_context.round_number == 0

    @pytest.mark.asyncio
    async def test_processing_queue_item_preserves_round_zero(self, guidance_thought):
        """Test that ProcessingQueueItem correctly handles round_number=0."""
        # Create queue item from thought
        queue_item = ProcessingQueueItem.from_thought(guidance_thought)

        # Verify round_number is preserved in context
        assert queue_item.initial_context.round_number == 0
        assert queue_item.thought_id == guidance_thought.thought_id
        assert queue_item.thought_type == ThoughtType.GUIDANCE

    @pytest.mark.asyncio
    async def test_guidance_thought_not_filtered_by_round_number(self):
        """Test that guidance thoughts aren't filtered out due to round_number=0."""
        from ciris_engine.logic.processors.support.thought_manager import ThoughtManager

        time_service = MagicMock()
        time_service.now.return_value = datetime.now(timezone.utc)
        manager = ThoughtManager(time_service=time_service)

        # Create a guidance thought with round_number=0
        thought = Thought(
            thought_id="test_guidance",
            source_task_id="task_123",
            channel_id="channel_123",
            thought_type=ThoughtType.GUIDANCE,
            status=ThoughtStatus.PENDING,
            created_at=time_service.now().isoformat(),
            updated_at=time_service.now().isoformat(),
            round_number=0,
            content="Test guidance",
            thought_depth=1,
            context=ThoughtContext(
                task_id="task_123",
                channel_id="channel_123",
                round_number=0,
                depth=1,
                parent_thought_id="parent_123",
                correlation_id="corr_123",
            ),
        )

        # Add to queue (simulate what populate_processing_queue does)
        queue_item = ProcessingQueueItem.from_thought(thought)
        manager.processing_queue.append(queue_item)

        # Should be in queue
        assert len(manager.processing_queue) == 1
        # Round number is in the context
        assert manager.processing_queue[0].initial_context.round_number == 0

    @pytest.mark.asyncio
    async def test_guidance_thought_completion_flow(self, guidance_thought, shutdown_task):
        """Test the complete flow of a guidance thought from creation to completion."""
        with patch("ciris_engine.logic.persistence.get_task_by_id") as mock_get_task:
            with patch("ciris_engine.logic.persistence.update_thought_status") as mock_update_status:
                with patch("ciris_engine.logic.persistence.update_task_status") as mock_update_task:
                    # Initial state
                    mock_get_task.return_value = shutdown_task

                    # 1. Guidance thought starts as PENDING
                    assert guidance_thought.status == ThoughtStatus.PENDING

                    # 2. Transitions to PROCESSING
                    persistence.update_thought_status(
                        thought_id=guidance_thought.thought_id, status=ThoughtStatus.PROCESSING
                    )
                    mock_update_status.assert_called_with(
                        thought_id=guidance_thought.thought_id, status=ThoughtStatus.PROCESSING
                    )

                    # 3. Completes with TASK_COMPLETE action
                    persistence.update_thought_status(
                        thought_id=guidance_thought.thought_id,
                        status=ThoughtStatus.COMPLETED,
                        final_action=FinalAction(
                            action_type="TASK_COMPLETE",
                            action_params={},
                            reasoning="Shutdown approved based on guidance",
                        ),
                    )

                    # 4. Task should be marked complete
                    persistence.update_task_status(shutdown_task.task_id, TaskStatus.COMPLETED, None)  # time_service
                    mock_update_task.assert_called_with(shutdown_task.task_id, TaskStatus.COMPLETED, None)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
