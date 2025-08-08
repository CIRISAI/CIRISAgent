"""
Test to validate the guidance thought status bug and fix.

BUG: Guidance thoughts were being created with status=PROCESSING instead of PENDING,
causing them to never enter the processing queue and get stuck forever.

FIX: Guidance thoughts must be created with status=PENDING so they can be picked up
by the normal thought processing pipeline.
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ciris_engine.logic.adapters.discord.discord_observer import DiscordObserver
from ciris_engine.logic.persistence import add_thought, get_thought_by_id
from ciris_engine.schemas.runtime.enums import TaskStatus, ThoughtStatus, ThoughtType
from ciris_engine.schemas.runtime.messages import DiscordMessage
from ciris_engine.schemas.runtime.models import Task, TaskContext, Thought


class TestGuidanceThoughtStatusBug:
    """Test suite to validate the guidance thought status bug is fixed."""

    @pytest.fixture
    def mock_services(self):
        """Create mock services for the observer."""
        return {
            "memory_service": AsyncMock(),
            "bus_manager": MagicMock(),
            "filter_service": AsyncMock(),
            "secrets_service": AsyncMock(),
            "communication_service": AsyncMock(),
            "time_service": MagicMock(
                now=lambda: datetime.now(timezone.utc), now_iso=lambda: datetime.now(timezone.utc).isoformat()
            ),
            "auth_service": AsyncMock(),
        }

    @pytest.fixture
    def discord_observer(self, mock_services):
        """Create a DiscordObserver instance."""
        return DiscordObserver(
            monitored_channel_ids=["1234567890"],
            deferral_channel_id="1234567890",
            wa_user_ids=["537080239679864862"],
            memory_service=mock_services["memory_service"],
            agent_id="test_agent",
            bus_manager=mock_services["bus_manager"],
            filter_service=mock_services["filter_service"],
            secrets_service=mock_services["secrets_service"],
            communication_service=mock_services["communication_service"],
            time_service=mock_services["time_service"],
            auth_service=mock_services["auth_service"],
        )

    @pytest.fixture
    def deferred_task(self):
        """Create a task that has been deferred."""
        return Task(
            task_id="task_123",
            channel_id="discord_1234_5678",
            description="Test task for shutdown",
            priority=10,
            status=TaskStatus.ACTIVE,
            created_at=datetime.now(timezone.utc).isoformat(),
            updated_at=datetime.now(timezone.utc).isoformat(),
            context=TaskContext(
                channel_id="discord_1234_5678",
                user_id="system",
                correlation_id="test_corr",
                parent_task_id=None,
            ),
        )

    @pytest.fixture
    def deferred_thought(self, deferred_task):
        """Create a thought that resulted in deferral."""
        return Thought(
            thought_id="thought_defer_123",
            source_task_id=deferred_task.task_id,
            channel_id=deferred_task.channel_id,
            thought_type=ThoughtType.FOLLOW_UP,
            status=ThoughtStatus.DEFERRED,
            created_at=datetime.now(timezone.utc).isoformat(),
            updated_at=datetime.now(timezone.utc).isoformat(),
            round_number=1,
            content="Should I proceed with shutdown?",
            thought_depth=1,
        )

    @pytest.mark.asyncio
    async def test_guidance_thought_created_with_pending_status(
        self, discord_observer, deferred_task, deferred_thought
    ):
        """Test that guidance thoughts are created with PENDING status, not PROCESSING."""
        # Create a WA guidance message
        guidance_message = DiscordMessage(
            message_id="msg_456",
            content="GUIDANCE: DEFER:thought_defer_123: Proceed with the shutdown, this is a routine update.",
            author_id="537080239679864862",  # WA user
            author_name="WiseAuthority",
            channel_id="1234567890",  # Deferral channel
            is_bot=False,
            is_dm=False,
            raw_message=None,
        )

        # Mock the persistence methods
        with patch("ciris_engine.logic.persistence.get_thought_by_id") as mock_get_thought:
            with patch("ciris_engine.logic.persistence.get_task_by_id") as mock_get_task:
                with patch("ciris_engine.logic.persistence.add_thought") as mock_add_thought:
                    # Setup mocks
                    mock_get_thought.return_value = deferred_thought
                    mock_get_task.return_value = deferred_task

                    # Process the guidance message
                    await discord_observer._handle_wa_guidance(guidance_message)

                    # Verify a thought was added
                    mock_add_thought.assert_called_once()

                    # Get the created thought
                    created_thought = mock_add_thought.call_args[0][0]

                    # CRITICAL ASSERTION: Guidance thought must be PENDING, not PROCESSING
                    assert created_thought.status == ThoughtStatus.PENDING, (
                        f"Guidance thought created with status {created_thought.status}, "
                        f"but must be PENDING to enter processing queue!"
                    )

                    # Verify other properties
                    assert created_thought.thought_type == ThoughtType.GUIDANCE
                    assert created_thought.parent_thought_id == deferred_thought.thought_id
                    assert created_thought.source_task_id == deferred_task.task_id
                    assert created_thought.round_number == 0  # Guidance thoughts start at round 0
                    assert "GUIDANCE:" in created_thought.content
                    assert guidance_message.content in created_thought.content

    @pytest.mark.asyncio
    async def test_guidance_thought_enters_processing_queue(self):
        """Test that PENDING guidance thoughts can enter the processing queue."""
        from ciris_engine.logic.processors.support.processing_queue import ProcessingQueueItem
        from ciris_engine.logic.processors.support.thought_manager import ThoughtManager

        # Create a guidance thought with PENDING status
        guidance_thought = Thought(
            thought_id="guidance_test_123",
            source_task_id="task_123",
            channel_id="discord_1234_5678",
            thought_type=ThoughtType.GUIDANCE,
            status=ThoughtStatus.PENDING,  # Correct status
            created_at=datetime.now(timezone.utc).isoformat(),
            updated_at=datetime.now(timezone.utc).isoformat(),
            round_number=0,
            content="GUIDANCE: Proceed with shutdown",
            thought_depth=1,
            parent_thought_id="parent_thought_123",
        )

        # Create thought manager
        time_service = MagicMock()
        time_service.now.return_value = datetime.now(timezone.utc)
        manager = ThoughtManager(time_service=time_service)

        # Mock persistence to return our guidance thought
        with patch("ciris_engine.logic.persistence.get_thoughts_by_task_id") as mock_get_thoughts:
            mock_get_thoughts.return_value = [guidance_thought]

            # Populate the processing queue
            tasks = [MagicMock(task_id="task_123")]
            added = manager.populate_processing_queue(tasks, round_number=1)

            # Verify the guidance thought was added to the queue
            assert added == 1, "Guidance thought should be added to processing queue"
            assert len(manager.processing_queue) == 1

            queue_item = manager.processing_queue[0]
            assert queue_item.thought_id == guidance_thought.thought_id
            assert queue_item.thought_type == ThoughtType.GUIDANCE

    @pytest.mark.asyncio
    async def test_processing_status_thoughts_not_added_to_queue(self):
        """Test that thoughts already in PROCESSING status are NOT added to queue."""
        from ciris_engine.logic.processors.support.thought_manager import ThoughtManager

        # Create a thought incorrectly stuck in PROCESSING status (the bug)
        stuck_thought = Thought(
            thought_id="stuck_guidance_123",
            source_task_id="task_123",
            channel_id="discord_1234_5678",
            thought_type=ThoughtType.GUIDANCE,
            status=ThoughtStatus.PROCESSING,  # Wrong status - causes the bug!
            created_at=datetime.now(timezone.utc).isoformat(),
            updated_at=datetime.now(timezone.utc).isoformat(),
            round_number=0,
            content="GUIDANCE: This will be stuck forever",
            thought_depth=1,
        )

        # Create thought manager
        time_service = MagicMock()
        time_service.now.return_value = datetime.now(timezone.utc)
        manager = ThoughtManager(time_service=time_service)

        # Mock persistence to return the stuck thought
        with patch("ciris_engine.logic.persistence.get_thoughts_by_task_id") as mock_get_thoughts:
            mock_get_thoughts.return_value = [stuck_thought]

            # Try to populate the processing queue
            tasks = [MagicMock(task_id="task_123")]
            added = manager.populate_processing_queue(tasks, round_number=1)

            # Verify the stuck thought was NOT added (because it's already PROCESSING)
            assert added == 0, "PROCESSING status thoughts should not be added to queue"
            assert len(manager.processing_queue) == 0

    @pytest.mark.asyncio
    async def test_shutdown_processor_handles_pending_guidance_thoughts(self):
        """Test that ShutdownProcessor can process PENDING guidance thoughts."""
        from ciris_engine.logic.processors.states.shutdown_processor import ShutdownProcessor

        # Create mock services
        config_accessor = MagicMock()
        thought_processor = AsyncMock()
        action_dispatcher = AsyncMock()
        time_service = MagicMock()
        time_service.now.return_value = datetime.now(timezone.utc)
        time_service.now_iso.return_value = datetime.now(timezone.utc).isoformat()
        services = {"communication_bus": AsyncMock(), "time_service": time_service, "resource_monitor": MagicMock()}

        processor = ShutdownProcessor(
            config_accessor=config_accessor,
            thought_processor=thought_processor,
            action_dispatcher=action_dispatcher,
            services=services,
            time_service=time_service,
        )

        # Create shutdown task
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

        # Create PENDING guidance thought (correct status)
        guidance_thought = Thought(
            thought_id="guidance_pending",
            source_task_id=shutdown_task.task_id,
            channel_id=shutdown_task.channel_id,
            thought_type=ThoughtType.GUIDANCE,
            status=ThoughtStatus.PENDING,  # Correct status!
            created_at=time_service.now_iso(),
            updated_at=time_service.now_iso(),
            round_number=0,
            content="GUIDANCE: Proceed with shutdown",
            thought_depth=1,
            parent_thought_id="parent_thought",
        )

        # Mock persistence
        with patch("ciris_engine.logic.persistence.get_task_by_id") as mock_get_task:
            with patch("ciris_engine.logic.persistence.get_thoughts_by_task_id") as mock_get_thoughts:
                with patch("ciris_engine.logic.persistence.update_thought_status") as mock_update_status:
                    with patch.object(processor, "process_thought_item") as mock_process:
                        # Setup
                        processor.shutdown_task = shutdown_task
                        mock_get_task.return_value = shutdown_task
                        mock_get_thoughts.return_value = [guidance_thought]
                        mock_process.return_value = MagicMock(selected_action="TASK_COMPLETE")

                        # Process shutdown thoughts
                        await processor._process_shutdown_thoughts()

                        # Verify the PENDING thought was picked up and processed
                        mock_update_status.assert_called_with(
                            thought_id=guidance_thought.thought_id, status=ThoughtStatus.PROCESSING
                        )
                        mock_process.assert_called_once()

    def test_regression_guidance_thoughts_never_created_as_processing(self):
        """Regression test to ensure guidance thoughts are never created with PROCESSING status."""
        # This is a static code analysis test
        # Read the discord_observer.py file and check for the bug
        import ast
        from pathlib import Path

        observer_path = Path(__file__).parent.parent / "ciris_engine/logic/adapters/discord/discord_observer.py"
        if not observer_path.exists():
            pytest.skip("Discord observer file not found")

        with open(observer_path, "r") as f:
            tree = ast.parse(f.read())

        # Find all Thought() instantiations
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name) and node.func.id == "Thought":
                    # Check if this is a guidance thought
                    is_guidance = False
                    has_processing_status = False

                    for keyword in node.keywords:
                        if keyword.arg == "thought_type":
                            if isinstance(keyword.value, ast.Attribute) and keyword.value.attr == "GUIDANCE":
                                is_guidance = True
                        elif keyword.arg == "status":
                            if isinstance(keyword.value, ast.Attribute) and keyword.value.attr == "PROCESSING":
                                has_processing_status = True

                    # If it's a guidance thought with PROCESSING status, fail the test
                    assert not (is_guidance and has_processing_status), (
                        "Found guidance thought being created with PROCESSING status! "
                        "This is the bug that causes guidance thoughts to get stuck."
                    )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
