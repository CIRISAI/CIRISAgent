"""
Unit tests for ActionSequenceConscience.

Tests the heuristic conscience that prevents repeated SPEAK actions
without intervening actions within the same task.
"""

import tempfile
import uuid
from datetime import datetime, timezone
from unittest.mock import Mock

import pytest

from ciris_engine.logic.conscience.action_sequence_conscience import REPEATED_SPEAK_GUIDANCE, ActionSequenceConscience
from ciris_engine.logic.persistence.db import initialize_database
from ciris_engine.logic.persistence.models.tasks import add_task
from ciris_engine.logic.persistence.models.thoughts import add_thought, update_thought_status
from ciris_engine.schemas.actions.parameters import PonderParams, SpeakParams, ToolParams
from ciris_engine.schemas.conscience.context import ConscienceCheckContext
from ciris_engine.schemas.conscience.core import ConscienceStatus
from ciris_engine.schemas.dma.results import ActionSelectionDMAResult
from ciris_engine.schemas.runtime.enums import HandlerActionType, TaskStatus, ThoughtStatus
from ciris_engine.schemas.runtime.models import FinalAction, Task, TaskContext, Thought, ThoughtContext


class TestActionSequenceConscience:
    """Test ActionSequenceConscience check."""

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
        """Create ActionSequenceConscience instance."""
        return ActionSequenceConscience(time_service=mock_time_service)

    @pytest.fixture
    def patch_db_path(self, temp_db, monkeypatch):
        """Patch database functions to use temp_db."""
        from ciris_engine.logic import persistence as persistence_module
        from ciris_engine.logic.persistence import db as db_module
        from ciris_engine.logic.persistence.models import correlations as correlations_module
        from ciris_engine.logic.persistence.models import tasks as tasks_module
        from ciris_engine.logic.persistence.models import thoughts as thoughts_module

        original_get_db_connection = db_module.get_db_connection
        original_get_thoughts_by_task_id = thoughts_module.get_thoughts_by_task_id

        def patched_get_db_connection(db_path=None):
            return original_get_db_connection(db_path=temp_db)

        def patched_get_thoughts_by_task_id(task_id, occurrence_id="default", db_path=None):
            return original_get_thoughts_by_task_id(task_id, occurrence_id, db_path=temp_db)

        # Patch get_db_connection at all import locations
        monkeypatch.setattr(db_module, "get_db_connection", patched_get_db_connection)
        monkeypatch.setattr(correlations_module, "get_db_connection", patched_get_db_connection)
        monkeypatch.setattr(thoughts_module, "get_db_connection", patched_get_db_connection)
        monkeypatch.setattr(tasks_module, "get_db_connection", patched_get_db_connection)

        # Patch thoughts query function
        monkeypatch.setattr(thoughts_module, "get_thoughts_by_task_id", patched_get_thoughts_by_task_id)
        # Also patch at the action_sequence_conscience module level
        from ciris_engine.logic.conscience import action_sequence_conscience as asc_module

        monkeypatch.setattr(asc_module, "get_thoughts_by_task_id", patched_get_thoughts_by_task_id)

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
        """Create a sample thought (not saved to DB yet - represents current thought)."""
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

    @pytest.fixture
    def tool_action(self):
        """Create a sample TOOL action."""
        return ActionSelectionDMAResult(
            selected_action=HandlerActionType.TOOL,
            action_parameters=ToolParams(name="search", parameters={"query": "test"}),
            rationale="Using a tool",
            raw_llm_response=None,
        )

    @pytest.fixture
    def ponder_action(self):
        """Create a sample PONDER action."""
        return ActionSelectionDMAResult(
            selected_action=HandlerActionType.PONDER,
            action_parameters=PonderParams(questions=["What should I do?"]),
            rationale="Need to think",
            raw_llm_response=None,
        )

    def _create_completed_thought(
        self,
        task_id: str,
        action_type: str,
        mock_time_service,
        temp_db: str,
    ) -> Thought:
        """Helper to create and save a completed thought with a final action."""
        thought = Thought(
            thought_id=str(uuid.uuid4()),
            source_task_id=task_id,
            content=f"Completed thought with {action_type}",
            status=ThoughtStatus.COMPLETED,
            created_at=mock_time_service.now_iso(),
            updated_at=mock_time_service.now_iso(),
            thought_depth=0,
            final_action=FinalAction(
                action_type=action_type,
                action_params={"content": "test"} if action_type == "speak" else {"questions": ["test"]},
                reasoning=f"Decided to {action_type}",
            ),
            context=ThoughtContext(
                task_id=task_id,
                correlation_id=str(uuid.uuid4()),
                round_number=0,
                depth=0,
            ),
        )
        add_thought(thought, db_path=temp_db)
        return thought

    # ==================== CORE LOGIC TESTS ====================

    @pytest.mark.asyncio
    async def test_allows_first_speak_no_prior_actions(self, conscience, speak_action, sample_thought, patch_db_path):
        """Test that first SPEAK in a task is allowed (no prior actions)."""
        context = ConscienceCheckContext(thought=sample_thought)
        result = await conscience.check(speak_action, context)

        assert result.passed is True
        assert result.status == ConscienceStatus.PASSED
        assert result.action_sequence_triggered is False
        assert "First SPEAK" in result.reason

    @pytest.mark.asyncio
    async def test_blocks_speak_after_speak_no_intervening(
        self, conscience, speak_action, sample_task, sample_thought, mock_time_service, patch_db_path
    ):
        """Test that SPEAK after prior SPEAK with no intervening action is blocked."""
        # Create a completed SPEAK thought
        self._create_completed_thought(sample_task.task_id, "speak", mock_time_service, patch_db_path)

        context = ConscienceCheckContext(thought=sample_thought)
        result = await conscience.check(speak_action, context)

        assert result.passed is False
        assert result.status == ConscienceStatus.FAILED
        assert result.action_sequence_triggered is True
        assert REPEATED_SPEAK_GUIDANCE in result.reason
        # Should NOT have a replacement_action (soft bounce to recursive ASPDMA)
        assert result.replacement_action is None

    @pytest.mark.asyncio
    async def test_allows_speak_after_speak_with_ponder_intervening(
        self, conscience, speak_action, sample_task, sample_thought, mock_time_service, patch_db_path
    ):
        """Test that SPEAK is allowed after SPEAK → PONDER (PONDER intervenes)."""
        # Create SPEAK then PONDER
        self._create_completed_thought(sample_task.task_id, "speak", mock_time_service, patch_db_path)
        self._create_completed_thought(sample_task.task_id, "ponder", mock_time_service, patch_db_path)

        context = ConscienceCheckContext(thought=sample_thought)
        result = await conscience.check(speak_action, context)

        assert result.passed is True
        assert result.status == ConscienceStatus.PASSED
        assert result.action_sequence_triggered is False
        assert "intervening" in result.reason

    @pytest.mark.asyncio
    async def test_allows_speak_after_speak_with_tool_intervening(
        self, conscience, speak_action, sample_task, sample_thought, mock_time_service, patch_db_path
    ):
        """Test that SPEAK is allowed after SPEAK → TOOL (TOOL intervenes)."""
        # Create SPEAK then TOOL
        self._create_completed_thought(sample_task.task_id, "speak", mock_time_service, patch_db_path)
        self._create_completed_thought(sample_task.task_id, "tool", mock_time_service, patch_db_path)

        context = ConscienceCheckContext(thought=sample_thought)
        result = await conscience.check(speak_action, context)

        assert result.passed is True
        assert result.status == ConscienceStatus.PASSED
        assert result.action_sequence_triggered is False

    @pytest.mark.asyncio
    async def test_allows_speak_after_multiple_ponders(
        self, conscience, speak_action, sample_task, sample_thought, mock_time_service, patch_db_path
    ):
        """Test that SPEAK is allowed after SPEAK → PONDER → PONDER → PONDER."""
        # Create SPEAK then multiple PONDERs
        self._create_completed_thought(sample_task.task_id, "speak", mock_time_service, patch_db_path)
        self._create_completed_thought(sample_task.task_id, "ponder", mock_time_service, patch_db_path)
        self._create_completed_thought(sample_task.task_id, "ponder", mock_time_service, patch_db_path)
        self._create_completed_thought(sample_task.task_id, "ponder", mock_time_service, patch_db_path)

        context = ConscienceCheckContext(thought=sample_thought)
        result = await conscience.check(speak_action, context)

        assert result.passed is True
        assert result.status == ConscienceStatus.PASSED
        assert result.action_sequence_triggered is False

    @pytest.mark.asyncio
    async def test_blocks_speak_after_speak_tool_speak(
        self, conscience, speak_action, sample_task, sample_thought, mock_time_service, patch_db_path
    ):
        """Test that SPEAK is blocked after SPEAK → TOOL → SPEAK (last was SPEAK)."""
        # Create SPEAK → TOOL → SPEAK
        self._create_completed_thought(sample_task.task_id, "speak", mock_time_service, patch_db_path)
        self._create_completed_thought(sample_task.task_id, "tool", mock_time_service, patch_db_path)
        self._create_completed_thought(sample_task.task_id, "speak", mock_time_service, patch_db_path)

        context = ConscienceCheckContext(thought=sample_thought)
        result = await conscience.check(speak_action, context)

        assert result.passed is False
        assert result.status == ConscienceStatus.FAILED
        assert result.action_sequence_triggered is True

    # ==================== NON-SPEAK ACTION TESTS ====================

    @pytest.mark.asyncio
    async def test_allows_tool_action_always(
        self, conscience, tool_action, sample_task, sample_thought, mock_time_service, patch_db_path
    ):
        """Test that TOOL actions are always allowed (conscience only checks SPEAK)."""
        # Even with prior SPEAK, TOOL should pass
        self._create_completed_thought(sample_task.task_id, "speak", mock_time_service, patch_db_path)

        context = ConscienceCheckContext(thought=sample_thought)
        result = await conscience.check(tool_action, context)

        assert result.passed is True
        assert result.status == ConscienceStatus.PASSED
        assert result.action_sequence_triggered is False
        assert "not SPEAK" in result.reason

    @pytest.mark.asyncio
    async def test_allows_ponder_action_always(
        self, conscience, ponder_action, sample_task, sample_thought, mock_time_service, patch_db_path
    ):
        """Test that PONDER actions are always allowed."""
        # Even with prior SPEAK, PONDER should pass
        self._create_completed_thought(sample_task.task_id, "speak", mock_time_service, patch_db_path)

        context = ConscienceCheckContext(thought=sample_thought)
        result = await conscience.check(ponder_action, context)

        assert result.passed is True
        assert result.status == ConscienceStatus.PASSED
        assert result.action_sequence_triggered is False

    # ==================== EDGE CASE TESTS ====================

    @pytest.mark.asyncio
    async def test_allows_speak_when_no_thought_context(self, conscience, speak_action, patch_db_path):
        """Test that SPEAK is allowed when no thought context is provided."""
        context = ConscienceCheckContext(thought=None)
        result = await conscience.check(speak_action, context)

        assert result.passed is True
        assert result.status == ConscienceStatus.PASSED
        assert result.action_sequence_triggered is False

    @pytest.mark.asyncio
    async def test_allows_speak_when_only_non_speak_prior_actions(
        self, conscience, speak_action, sample_task, sample_thought, mock_time_service, patch_db_path
    ):
        """Test that SPEAK is allowed when prior actions are only non-SPEAK."""
        # Create TOOL → PONDER (no prior SPEAK)
        self._create_completed_thought(sample_task.task_id, "tool", mock_time_service, patch_db_path)
        self._create_completed_thought(sample_task.task_id, "ponder", mock_time_service, patch_db_path)

        context = ConscienceCheckContext(thought=sample_thought)
        result = await conscience.check(speak_action, context)

        assert result.passed is True
        assert result.status == ConscienceStatus.PASSED
        assert result.action_sequence_triggered is False
        assert "First SPEAK" in result.reason

    @pytest.mark.asyncio
    async def test_ignores_pending_thoughts(
        self, conscience, speak_action, sample_task, sample_thought, mock_time_service, patch_db_path
    ):
        """Test that pending/processing thoughts are ignored (only completed count)."""
        # Create a completed SPEAK
        self._create_completed_thought(sample_task.task_id, "speak", mock_time_service, patch_db_path)

        # Create a pending PONDER (should be ignored)
        pending_thought = Thought(
            thought_id=str(uuid.uuid4()),
            source_task_id=sample_task.task_id,
            content="Pending ponder",
            status=ThoughtStatus.PENDING,  # Not completed
            created_at=mock_time_service.now_iso(),
            updated_at=mock_time_service.now_iso(),
            thought_depth=0,
            final_action=FinalAction(
                action_type="ponder",
                action_params={"questions": ["test"]},
                reasoning="Pending",
            ),
            context=ThoughtContext(
                task_id=sample_task.task_id,
                correlation_id=str(uuid.uuid4()),
                round_number=0,
                depth=0,
            ),
        )
        add_thought(pending_thought, db_path=patch_db_path)

        context = ConscienceCheckContext(thought=sample_thought)
        result = await conscience.check(speak_action, context)

        # Should still be blocked because pending PONDER doesn't count as intervening
        assert result.passed is False
        assert result.status == ConscienceStatus.FAILED
        assert result.action_sequence_triggered is True

    @pytest.mark.asyncio
    async def test_excludes_current_thought_from_history(
        self, conscience, speak_action, sample_task, mock_time_service, patch_db_path
    ):
        """Test that the current thought is excluded from action history check."""
        # Create a completed SPEAK
        completed_speak = self._create_completed_thought(sample_task.task_id, "speak", mock_time_service, patch_db_path)

        # Create current thought with same ID as completed (edge case)
        # This should still be blocked because we exclude current thought
        current_thought = Thought(
            thought_id=str(uuid.uuid4()),  # Different ID
            source_task_id=sample_task.task_id,
            content="Current thought",
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

        context = ConscienceCheckContext(thought=current_thought)
        result = await conscience.check(speak_action, context)

        # Should be blocked - prior completed SPEAK exists
        assert result.passed is False
        assert result.action_sequence_triggered is True

    # ==================== TRACING/CORRELATION TESTS ====================

    @pytest.mark.asyncio
    async def test_creates_trace_correlation(
        self, conscience, speak_action, sample_thought, patch_db_path, monkeypatch
    ):
        """Test that conscience creates trace correlation for auditing."""
        from ciris_engine.logic import persistence

        correlations_added = []

        original_add_correlation = persistence.add_correlation

        def mock_add_correlation(correlation, time_service):
            correlations_added.append(correlation)
            return original_add_correlation(correlation, time_service)

        monkeypatch.setattr(persistence, "add_correlation", mock_add_correlation)

        context = ConscienceCheckContext(thought=sample_thought)
        await conscience.check(speak_action, context)

        assert len(correlations_added) == 1
        correlation = correlations_added[0]
        assert correlation.handler_name == "ActionSequenceConscience"
        assert correlation.service_type == "conscience"
        assert "action_sequence" in correlation.tags.get("conscience_type", "")
