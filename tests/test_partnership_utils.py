"""
Comprehensive tests for partnership utilities.

Tests the helper functions used by ConsentService for managing partnership tasks.
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import Mock, patch

import pytest

from ciris_engine.logic.utils.consent.partnership_utils import PartnershipRequestHandler
from ciris_engine.schemas.runtime.enums import TaskStatus
from ciris_engine.schemas.runtime.models import Task, TaskContext


class MockTimeService:
    """Mock time service for testing."""
    
    def now(self):
        return datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)


class TestPartnershipUtils:
    """Test partnership request utility functions."""
    
    @pytest.fixture
    def time_service(self):
        """Provide mock time service."""
        return MockTimeService()
    
    @pytest.fixture
    def handler(self, time_service):
        """Create handler instance for testing."""
        return PartnershipRequestHandler(time_service=time_service)
    
    @pytest.fixture
    def mock_persistence(self):
        """Mock persistence for testing."""
        with patch('ciris_engine.logic.utils.consent.partnership_utils.persistence') as mock:
            yield mock
    
    def test_create_partnership_task_basic(self, handler, mock_persistence):
        """Test basic partnership task creation."""
        # Create task
        task = handler.create_partnership_task(
            user_id="test_user",
            categories=["data", "telemetry"],
            reason="For mutual learning",
            channel_id="test_channel"
        )
        
        # Verify task structure
        assert task.task_id.startswith("partnership_test_user_")
        assert task.channel_id == "test_channel"
        assert task.status == TaskStatus.ACTIVE
        assert task.priority == 5
        assert "data, telemetry" in task.description
        assert "For mutual learning" in task.description
        assert "TASK_COMPLETE" in task.description
        assert "REJECT" in task.description
        assert "DEFER" in task.description
        
        # Verify persistence was called
        mock_persistence.add_task.assert_called_once_with(task)
    
    def test_create_partnership_task_no_reason(self, handler, mock_persistence):
        """Test task creation without reason."""
        task = handler.create_partnership_task(
            user_id="user2",
            categories=["memory"],
            reason=None,
            channel_id=None
        )
        
        assert "memory" in task.description
        assert "Reason:" not in task.description
        assert task.channel_id == ""
    
    def test_create_partnership_task_empty_categories(self, handler, mock_persistence):
        """Test task creation with empty categories."""
        task = handler.create_partnership_task(
            user_id="user3",
            categories=[],
            reason="Testing",
            channel_id="channel3"
        )
        
        assert "all categories" in task.description
        assert "Testing" in task.description
    
    def test_create_partnership_task_context(self, handler, mock_persistence):
        """Test task context creation."""
        task = handler.create_partnership_task(
            user_id="context_user",
            categories=["audit"],
            reason="Context test",
            channel_id="context_channel"
        )
        
        assert task.context.user_id == "context_user"
        assert task.context.channel_id == "context_channel"
        assert task.context.correlation_id.startswith("consent_partnership_")
        assert task.context.parent_task_id is None
    
    def test_check_task_outcome_not_found(self, handler, mock_persistence):
        """Test checking outcome when task not found."""
        mock_persistence.get_task_by_id.return_value = None
        
        outcome, reason = handler.check_task_outcome("nonexistent")
        
        assert outcome == "failed"
        assert reason == "Task not found"
    
    def test_check_task_outcome_pending(self, handler, mock_persistence):
        """Test checking outcome for pending task."""
        mock_task = Mock(status=TaskStatus.PENDING)
        mock_persistence.get_task_by_id.return_value = mock_task
        
        outcome, reason = handler.check_task_outcome("task1")
        
        assert outcome == "pending"
        assert reason is None
    
    def test_check_task_outcome_active(self, handler, mock_persistence):
        """Test checking outcome for active task."""
        mock_task = Mock(status=TaskStatus.ACTIVE)
        mock_persistence.get_task_by_id.return_value = mock_task
        
        outcome, reason = handler.check_task_outcome("task2")
        
        assert outcome == "pending"
        assert reason is None
    
    def test_check_task_outcome_completed(self, handler, mock_persistence):
        """Test checking outcome for completed task."""
        mock_task = Mock(status=TaskStatus.COMPLETED)
        mock_persistence.get_task_by_id.return_value = mock_task
        
        outcome, reason = handler.check_task_outcome("task3")
        
        assert outcome == "accepted"
        assert reason == "Partnership approved by agent"
    
    def test_check_task_outcome_rejected_status(self, handler, mock_persistence):
        """Test checking outcome for rejected task (via status)."""
        mock_task = Mock(status=TaskStatus.REJECTED)
        mock_persistence.get_task_by_id.return_value = mock_task
        mock_persistence.get_thoughts_by_task_id.return_value = []
        
        outcome, reason = handler.check_task_outcome("task4")
        
        assert outcome == "rejected"
        assert reason == "Request was rejected"
    
    def test_check_task_outcome_deferred_status(self, handler, mock_persistence):
        """Test checking outcome for deferred task (via status)."""
        mock_task = Mock(status=TaskStatus.DEFERRED)
        mock_persistence.get_task_by_id.return_value = mock_task
        mock_persistence.get_thoughts_by_task_id.return_value = []
        
        outcome, reason = handler.check_task_outcome("task4b")
        
        assert outcome == "deferred"
        assert reason == "Request was deferred"
    
    def test_check_task_outcome_rejected(self, handler, mock_persistence):
        """Test checking outcome for rejected task."""
        mock_task = Mock(status=TaskStatus.FAILED)
        mock_thought = Mock()
        mock_thought.final_action = Mock(
            action_type="REJECT",
            action_params={"reason": "Not appropriate"}
        )
        
        mock_persistence.get_task_by_id.return_value = mock_task
        mock_persistence.get_thoughts_by_task_id.return_value = [mock_thought]
        
        outcome, reason = handler.check_task_outcome("task5")
        
        assert outcome == "rejected"
        assert reason == "Not appropriate"
    
    def test_check_task_outcome_rejected_no_reason(self, handler, mock_persistence):
        """Test checking outcome for rejected task without reason."""
        mock_task = Mock(status=TaskStatus.FAILED)
        mock_thought = Mock()
        mock_thought.final_action = Mock(
            action_type="REJECT",
            action_params={}
        )
        
        mock_persistence.get_task_by_id.return_value = mock_task
        mock_persistence.get_thoughts_by_task_id.return_value = [mock_thought]
        
        outcome, reason = handler.check_task_outcome("task6")
        
        assert outcome == "rejected"
        assert reason == "No reason provided"
    
    def test_check_task_outcome_deferred(self, handler, mock_persistence):
        """Test checking outcome for deferred task."""
        mock_task = Mock(status=TaskStatus.FAILED)
        mock_thought = Mock()
        mock_thought.final_action = Mock(
            action_type="DEFER",
            action_params={"reason": "Need more info"}
        )
        
        mock_persistence.get_task_by_id.return_value = mock_task
        mock_persistence.get_thoughts_by_task_id.return_value = [mock_thought]
        
        outcome, reason = handler.check_task_outcome("task7")
        
        assert outcome == "deferred"
        assert reason == "Need more info"
    
    def test_check_task_outcome_deferred_no_reason(self, handler, mock_persistence):
        """Test checking outcome for deferred task without reason."""
        mock_task = Mock(status=TaskStatus.FAILED)
        mock_thought = Mock()
        mock_thought.final_action = Mock(
            action_type="DEFER",
            action_params={}
        )
        
        mock_persistence.get_task_by_id.return_value = mock_task
        mock_persistence.get_thoughts_by_task_id.return_value = [mock_thought]
        
        outcome, reason = handler.check_task_outcome("task8")
        
        assert outcome == "deferred"
        assert reason == "More information needed"
    
    def test_check_task_outcome_failed_no_thoughts(self, handler, mock_persistence):
        """Test checking outcome for failed task with no thoughts."""
        mock_task = Mock(status=TaskStatus.FAILED)
        
        mock_persistence.get_task_by_id.return_value = mock_task
        mock_persistence.get_thoughts_by_task_id.return_value = []
        
        outcome, reason = handler.check_task_outcome("task9")
        
        assert outcome == "failed"
        assert reason == "Task failed without clear reason"
    
    def test_check_task_outcome_failed_no_action(self, handler, mock_persistence):
        """Test checking outcome for failed task with thought but no action."""
        mock_task = Mock(status=TaskStatus.FAILED)
        mock_thought = Mock()
        mock_thought.final_action = None
        
        mock_persistence.get_task_by_id.return_value = mock_task
        mock_persistence.get_thoughts_by_task_id.return_value = [mock_thought]
        
        outcome, reason = handler.check_task_outcome("task10")
        
        assert outcome == "failed"
        assert reason == "Task failed without clear reason"
    
    def test_check_task_outcome_multiple_thoughts(self, handler, mock_persistence):
        """Test checking outcome with multiple thoughts (uses latest)."""
        mock_task = Mock(status=TaskStatus.FAILED)
        
        # Earlier thought (will be ignored)
        mock_thought1 = Mock()
        mock_thought1.final_action = Mock(
            action_type="DEFER",
            action_params={"reason": "Old defer"}
        )
        
        # Latest thought (will be used)
        mock_thought2 = Mock()
        mock_thought2.final_action = Mock(
            action_type="REJECT",
            action_params={"reason": "Final rejection"}
        )
        
        mock_persistence.get_task_by_id.return_value = mock_task
        mock_persistence.get_thoughts_by_task_id.return_value = [mock_thought1, mock_thought2]
        
        outcome, reason = handler.check_task_outcome("task11")
        
        assert outcome == "rejected"
        assert reason == "Final rejection"
    
    def test_check_task_outcome_non_dict_params(self, handler, mock_persistence):
        """Test checking outcome with non-dict action params."""
        mock_task = Mock(status=TaskStatus.FAILED)
        mock_thought = Mock()
        mock_thought.final_action = Mock(
            action_type="REJECT",
            action_params="Not a dict"  # Invalid params type
        )
        
        mock_persistence.get_task_by_id.return_value = mock_task
        mock_persistence.get_thoughts_by_task_id.return_value = [mock_thought]
        
        outcome, reason = handler.check_task_outcome("task12")
        
        assert outcome == "rejected"
        assert reason == "No reason provided"
    
    def test_create_partnership_task_uuid_generation(self, handler, mock_persistence):
        """Test that task IDs are unique."""
        task1 = handler.create_partnership_task(
            user_id="same_user",
            categories=["test"],
            reason=None,
            channel_id=None
        )
        
        task2 = handler.create_partnership_task(
            user_id="same_user",
            categories=["test"],
            reason=None,
            channel_id=None
        )
        
        # Task IDs should be different due to UUID
        assert task1.task_id != task2.task_id
        assert task1.task_id.startswith("partnership_same_user_")
        assert task2.task_id.startswith("partnership_same_user_")


class TestPartnershipUtilsEdgeCases:
    """Test edge cases and error conditions."""
    
    @pytest.fixture
    def handler(self):
        """Create handler with mock time service."""
        return PartnershipRequestHandler(time_service=MockTimeService())
    
    def test_create_task_with_auth_service(self):
        """Test that auth_service parameter is accepted but not used."""
        mock_auth = Mock()
        handler = PartnershipRequestHandler(
            time_service=MockTimeService(),
            auth_service=mock_auth
        )
        
        assert handler.auth_service == mock_auth
        
        with patch('ciris_engine.logic.utils.consent.partnership_utils.persistence'):
            task = handler.create_partnership_task(
                user_id="auth_test",
                categories=["test"],
                reason=None,
                channel_id=None
            )
            assert task.task_id.startswith("partnership_auth_test_")
    
    def test_check_outcome_with_missing_final_action_attr(self, handler):
        """Test handling thought without final_action attribute."""
        with patch('ciris_engine.logic.utils.consent.partnership_utils.persistence') as mock_p:
            mock_task = Mock(status=TaskStatus.FAILED)
            mock_thought = Mock(spec=[])  # No final_action attribute
            
            mock_p.get_task_by_id.return_value = mock_task
            mock_p.get_thoughts_by_task_id.return_value = [mock_thought]
            
            outcome, reason = handler.check_task_outcome("task_no_attr")
            
            assert outcome == "failed"
            assert reason == "Task failed without clear reason"