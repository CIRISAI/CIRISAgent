"""
Unit tests for UpdatedStatusConscience.

Tests the 6th conscience check that detects when new observations
arrive during task processing.
"""

import sqlite3
import tempfile
import uuid
from datetime import datetime, timezone
from unittest.mock import Mock

import pytest

from ciris_engine.logic.conscience.updated_status_conscience import UpdatedStatusConscience
from ciris_engine.logic.persistence.db import initialize_database
from ciris_engine.logic.persistence.models.tasks import add_task, get_task_by_id, set_task_updated_info_flag
from ciris_engine.schemas.actions.parameters import PonderParams, SpeakParams
from ciris_engine.schemas.conscience.core import ConscienceStatus
from ciris_engine.schemas.dma.results import ActionSelectionDMAResult
from ciris_engine.schemas.runtime.enums import HandlerActionType, TaskStatus, ThoughtStatus
from ciris_engine.schemas.runtime.models import Task, TaskContext, Thought, ThoughtContext


class TestUpdatedStatusConscience:
    """Test UpdatedStatusConscience check."""

    @pytest.fixture
    def temp_db(self):
        """Create temporary database with schema."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        # Initialize database schema with migrations
        initialize_database(db_path)

        yield db_path

        # Cleanup
        import os
        try:
            os.unlink(db_path)
        except OSError:
            pass

    @pytest.fixture
    def mock_time_service(self):
        """Create mock time service."""
        mock_time = Mock()
        mock_time.now.return_value = datetime.now(timezone.utc)
        mock_time.now_iso.return_value = datetime.now(timezone.utc).isoformat()
        return mock_time

    @pytest.fixture
    def conscience(self, mock_time_service):
        """Create UpdatedStatusConscience instance."""
        return UpdatedStatusConscience(time_service=mock_time_service)

    @pytest.fixture
    def patch_db_path(self, temp_db, monkeypatch):
        """Patch database functions to use temp_db."""
        from ciris_engine.logic.persistence.models import tasks as tasks_module
        from ciris_engine.logic.persistence import db as db_module

        original_get_task = tasks_module.get_task_by_id
        original_get_db_connection = db_module.get_db_connection

        def patched_get_task(task_id, db_path=None):
            return original_get_task(task_id, db_path=temp_db)

        def patched_get_db_connection(db_path=None):
            return original_get_db_connection(db_path=temp_db)

        monkeypatch.setattr(tasks_module, "get_task_by_id", patched_get_task)
        monkeypatch.setattr(db_module, "get_db_connection", patched_get_db_connection)

        return temp_db

    @pytest.fixture
    def sample_task(self, temp_db, mock_time_service):
        """Create and save a sample task."""
        task = Task(
            task_id=str(uuid.uuid4()),
            channel_id="test-channel-123",
            description="Test task",
            status=TaskStatus.ACTIVE,
            priority=5,
            created_at=mock_time_service.now_iso(),
            updated_at=mock_time_service.now_iso(),
            context=TaskContext(
                channel_id="test-channel-123",
                user_id="user-123",
                correlation_id=str(uuid.uuid4()),
                parent_task_id=None,
            ),
        )
        add_task(task, db_path=temp_db)
        return task

    @pytest.fixture
    def sample_thought(self, sample_task, mock_time_service):
        """Create a sample thought."""
        return Thought(
            thought_id=str(uuid.uuid4()),
            source_task_id=sample_task.task_id,
            content="Processing task",
            status=ThoughtStatus.PENDING,
            created_at=mock_time_service.now_iso(),
            updated_at=mock_time_service.now_iso(),
            thought_depth=0,
            context=ThoughtContext(
                task_id=sample_task.task_id,
                correlation_id=str(uuid.uuid4()),
                round_number=0,
                depth=0,
            ),
        )

    @pytest.fixture
    def speak_action(self):
        """Create a sample SPEAK action."""
        return ActionSelectionDMAResult(
            selected_action=HandlerActionType.SPEAK,
            action_parameters=SpeakParams(content="Hello there"),
            rationale="Ready to respond",
            raw_llm_response=None,
        )

    @pytest.mark.asyncio
    async def test_passes_when_no_update_flag(self, conscience, speak_action, sample_thought, patch_db_path):
        """Test that check passes when no update flag is set."""
        context = {"thought": sample_thought}
        result = await conscience.check(speak_action, context)

        assert result.passed is True
        assert result.status == ConscienceStatus.PASSED

    @pytest.mark.asyncio
    async def test_fails_when_update_flag_set(self, conscience, speak_action, sample_thought, sample_task, patch_db_path, mock_time_service):
        """Test that check fails when update flag is set."""
        # Set the update flag
        set_task_updated_info_flag(
            sample_task.task_id,
            "@newuser said: Actually, I changed my mind",
            mock_time_service,
            db_path=patch_db_path
        )

        context = {"thought": sample_thought}
        result = await conscience.check(speak_action, context)

        assert result.passed is False
        assert result.status == ConscienceStatus.FAILED
        assert "New observation arrived" in result.reason
        assert result.epistemic_data is not None
        assert result.epistemic_data.replacement_action is not None

    @pytest.mark.asyncio
    async def test_clears_flag_after_detection(self, conscience, speak_action, sample_thought, sample_task, patch_db_path, mock_time_service):
        """Test that update flag is cleared after detection."""
        # Set the update flag
        set_task_updated_info_flag(
            sample_task.task_id,
            "New content",
            mock_time_service,
            db_path=patch_db_path
        )

        context = {"thought": sample_thought}

        # First check should detect and clear flag
        result = await conscience.check(speak_action, context)
        assert result.passed is False

        # Verify flag is cleared in database
        updated_task = get_task_by_id(sample_task.task_id, db_path=patch_db_path)
        assert updated_task.updated_info_available is False

        # Second check should pass
        result2 = await conscience.check(speak_action, context)
        assert result2.passed is True

    @pytest.mark.asyncio
    async def test_replacement_action_is_ponder(self, conscience, speak_action, sample_thought, sample_task, patch_db_path, mock_time_service):
        """Test that replacement action is PONDER with update content."""
        # Set the update flag with specific content
        update_content = "@alice: I need help with something else"
        set_task_updated_info_flag(
            sample_task.task_id,
            update_content,
            mock_time_service,
            db_path=patch_db_path
        )

        context = {"thought": sample_thought}
        result = await conscience.check(speak_action, context)

        assert result.passed is False
        assert result.epistemic_data is not None

        # Verify replacement action
        replacement_data = result.epistemic_data.replacement_action
        replacement_action = ActionSelectionDMAResult.model_validate(replacement_data)

        assert replacement_action.selected_action == HandlerActionType.PONDER
        assert isinstance(replacement_action.action_parameters, PonderParams)

        # Verify PONDER questions include update content and proper format
        questions = replacement_action.action_parameters.questions
        assert any(update_content in q for q in questions)
        assert any("was going to" in q for q in questions)
        assert any("Should I revise" in q for q in questions)

    @pytest.mark.asyncio
    async def test_passes_when_no_thought_in_context(self, conscience, speak_action):
        """Test that check passes when no thought in context."""
        context = {}  # No thought
        result = await conscience.check(speak_action, context)

        assert result.passed is True
        assert result.status == ConscienceStatus.PASSED

    @pytest.mark.asyncio
    async def test_passes_when_task_not_found(self, conscience, speak_action, patch_db_path):
        """Test that check passes when task doesn't exist."""
        # Create thought with nonexistent task ID
        fake_thought = Thought(
            thought_id=str(uuid.uuid4()),
            source_task_id="nonexistent-task-id",
            content="Processing",
            status=ThoughtStatus.PENDING,
            created_at=datetime.now(timezone.utc).isoformat(),
            updated_at=datetime.now(timezone.utc).isoformat(),
            thought_depth=0,
            context=ThoughtContext(
                task_id="nonexistent-task-id",
                correlation_id=str(uuid.uuid4()),
                round_number=0,
                depth=0,
            ),
        )

        context = {"thought": fake_thought}
        result = await conscience.check(speak_action, context)

        assert result.passed is True
        assert result.status == ConscienceStatus.PASSED

    @pytest.mark.asyncio
    async def test_update_message_formatting(self, conscience, speak_action, sample_thought, sample_task, patch_db_path, mock_time_service):
        """Test that update message is properly formatted."""
        update_content = "@alice (ID: 12345): Actually never mind"
        set_task_updated_info_flag(
            sample_task.task_id,
            update_content,
            mock_time_service,
            db_path=patch_db_path
        )

        context = {"thought": sample_thought}
        result = await conscience.check(speak_action, context)

        # Verify the formatted update message
        replacement_data = result.epistemic_data.replacement_action
        replacement_action = ActionSelectionDMAResult.model_validate(replacement_data)
        questions = replacement_action.action_parameters.questions

        # Should have the update content and contextual question
        assert any(update_content in q for q in questions)
        assert any("was going to" in q for q in questions)
