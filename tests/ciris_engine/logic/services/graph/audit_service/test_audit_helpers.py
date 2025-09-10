"""Unit tests for audit service helper functions.

Tests for functions extracted during complexity refactoring to improve maintainability
and test coverage of individual components.
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import Mock, MagicMock, patch
import pytest

from ciris_engine.logic.services.graph.audit_service.service import AuditService
from ciris_engine.schemas.services.graph.audit import AuditRequest


class TestAuditServiceHelpers:
    """Test suite for audit service helper functions."""
    
    @pytest.fixture
    def audit_service(self):
        """Create an audit service instance for testing."""
        time_service = Mock()
        time_service.now.return_value = datetime(2023, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        
        service = AuditService()
        service._time_service = time_service
        return service

    def test_extract_thought_id_from_audit_node_with_data(self, audit_service):
        """Test thought ID extraction when additional_data exists with thought_id."""
        # Arrange
        context = Mock()
        context.additional_data = {"thought_id": "test-thought-123"}
        
        audit_node = Mock()
        audit_node.context = context

        # Act
        result = audit_service._extract_thought_id_from_audit_node(audit_node)

        # Assert
        assert result == "test-thought-123"

    def test_extract_thought_id_from_audit_node_no_additional_data(self, audit_service):
        """Test thought ID extraction when additional_data is None."""
        # Arrange
        context = Mock()
        context.additional_data = None
        
        audit_node = Mock()
        audit_node.context = context

        # Act
        result = audit_service._extract_thought_id_from_audit_node(audit_node)

        # Assert
        assert result == ""

    def test_extract_thought_id_from_audit_node_missing_thought_id(self, audit_service):
        """Test thought ID extraction when thought_id key is missing."""
        # Arrange
        context = Mock()
        context.additional_data = {"other_key": "other_value"}
        
        audit_node = Mock()
        audit_node.context = context

        # Act
        result = audit_service._extract_thought_id_from_audit_node(audit_node)

        # Assert
        assert result == ""

    def test_extract_task_id_from_audit_node_with_data(self, audit_service):
        """Test task ID extraction when additional_data exists with task_id."""
        # Arrange
        context = Mock()
        context.additional_data = {"task_id": "test-task-456"}
        
        audit_node = Mock()
        audit_node.context = context

        # Act
        result = audit_service._extract_task_id_from_audit_node(audit_node)

        # Assert
        assert result == "test-task-456"

    def test_extract_task_id_from_audit_node_no_additional_data(self, audit_service):
        """Test task ID extraction when additional_data is None."""
        # Arrange
        context = Mock()
        context.additional_data = None
        
        audit_node = Mock()
        audit_node.context = context

        # Act
        result = audit_service._extract_task_id_from_audit_node(audit_node)

        # Assert
        assert result == ""

    def test_extract_outcome_from_audit_node_with_outcome(self, audit_service):
        """Test outcome extraction when additional_data exists with outcome."""
        # Arrange
        context = Mock()
        context.additional_data = {"outcome": "success"}
        
        audit_node = Mock()
        audit_node.context = context

        # Act
        result = audit_service._extract_outcome_from_audit_node(audit_node)

        # Assert
        assert result == "success"

    def test_extract_outcome_from_audit_node_no_additional_data(self, audit_service):
        """Test outcome extraction when additional_data is None."""
        # Arrange
        context = Mock()
        context.additional_data = None
        
        audit_node = Mock()
        audit_node.context = context

        # Act
        result = audit_service._extract_outcome_from_audit_node(audit_node)

        # Assert
        assert result is None

    def test_extract_outcome_from_audit_node_no_outcome_key(self, audit_service):
        """Test outcome extraction when outcome key is missing."""
        # Arrange
        context = Mock()
        context.additional_data = {"other_key": "other_value"}
        
        audit_node = Mock()
        audit_node.context = context

        # Act
        result = audit_service._extract_outcome_from_audit_node(audit_node)

        # Assert
        assert result is None

    def test_convert_audit_entry_node_complete(self, audit_service):
        """Test complete audit entry node conversion with all data."""
        # Arrange
        context = Mock()
        context.correlation_id = "corr-123"
        context.service_name = "test_service"
        context.additional_data = {
            "thought_id": "thought-789",
            "task_id": "task-456",
            "outcome": "completed"
        }
        context.model_dump.return_value = {"service": "test_service"}
        
        timestamp = datetime(2023, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
        
        audit_node = Mock()
        audit_node.id = "audit_test_id"
        audit_node.timestamp = timestamp
        audit_node.context = context
        audit_node.action = "test_action"
        audit_node.actor = "test_actor"

        # Act
        result = audit_service._convert_audit_entry_node(audit_node)

        # Assert
        assert isinstance(result, AuditRequest)
        assert result.entry_id == "test_id"  # Should remove "audit_" prefix
        assert result.timestamp == timestamp
        assert result.entity_id == "corr-123"
        assert result.event_type == "test_action"
        assert result.actor == "test_actor"
        assert result.details["action_type"] == "test_action"
        assert result.details["thought_id"] == "thought-789"
        assert result.details["task_id"] == "task-456"
        assert result.details["handler_name"] == "test_service"
        assert result.details["context"] == {"service": "test_service"}
        assert result.outcome == "completed"

    def test_convert_audit_entry_node_minimal(self, audit_service):
        """Test audit entry node conversion with minimal data."""
        # Arrange
        context = Mock()
        context.correlation_id = ""
        context.service_name = ""
        context.additional_data = None
        context.model_dump.return_value = {}
        
        timestamp = datetime(2023, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
        
        audit_node = Mock()
        audit_node.id = "audit_minimal"
        audit_node.timestamp = timestamp
        audit_node.context = context
        audit_node.action = "minimal_action"
        audit_node.actor = "minimal_actor"

        # Act
        result = audit_service._convert_audit_entry_node(audit_node)

        # Assert
        assert isinstance(result, AuditRequest)
        assert result.entry_id == "minimal"
        assert result.timestamp == timestamp
        assert result.entity_id == ""
        assert result.event_type == "minimal_action"
        assert result.actor == "minimal_actor"
        assert result.details["thought_id"] == ""
        assert result.details["task_id"] == ""
        assert result.details["handler_name"] == ""
        assert result.outcome is None

    def test_get_timestamp_from_data_with_created_at(self, audit_service):
        """Test timestamp extraction when created_at exists."""
        # Arrange
        timestamp = datetime(2023, 1, 1, 15, 0, 0, tzinfo=timezone.utc)
        
        attributes = Mock()
        attributes.created_at = timestamp
        
        data = Mock()
        data.attributes = attributes
        data.updated_at = datetime(2023, 1, 1, 14, 0, 0, tzinfo=timezone.utc)  # Different time

        # Act
        result = audit_service._get_timestamp_from_data(data)

        # Assert
        assert result == timestamp  # Should prefer created_at

    def test_get_timestamp_from_data_with_updated_at(self, audit_service):
        """Test timestamp extraction when only updated_at exists."""
        # Arrange
        timestamp = datetime(2023, 1, 1, 16, 0, 0, tzinfo=timezone.utc)
        
        attributes = Mock()
        del attributes.created_at  # Remove created_at attribute
        
        data = Mock()
        data.attributes = attributes
        data.updated_at = timestamp

        # Act
        result = audit_service._get_timestamp_from_data(data)

        # Assert
        assert result == timestamp

    def test_get_timestamp_from_data_fallback_to_service(self, audit_service):
        """Test timestamp extraction fallback to time service."""
        # Arrange
        attributes = Mock()
        del attributes.created_at
        
        data = Mock()
        data.attributes = attributes
        data.updated_at = None
        
        service_time = datetime(2023, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        audit_service._time_service.now.return_value = service_time

        # Act
        result = audit_service._get_timestamp_from_data(data)

        # Assert
        assert result == service_time

    def test_get_timestamp_from_data_fallback_to_now(self, audit_service):
        """Test timestamp extraction fallback to datetime.now when no time service."""
        # Arrange
        attributes = Mock()
        del attributes.created_at
        
        data = Mock()
        data.attributes = attributes
        data.updated_at = None
        
        audit_service._time_service = None  # No time service

        # Act
        with patch('ciris_engine.logic.services.graph.audit_service.service.datetime') as mock_datetime:
            mock_now = datetime(2023, 1, 1, 13, 0, 0, tzinfo=timezone.utc)
            mock_datetime.now.return_value = mock_now
            
            result = audit_service._get_timestamp_from_data(data)

        # Assert
        assert result == mock_now

    def test_extract_action_type_from_attrs_direct_key(self, audit_service):
        """Test action type extraction when key exists directly."""
        # Arrange
        attrs = {"action_type": "direct_action"}

        # Act
        result = audit_service._extract_action_type_from_attrs(attrs)

        # Assert
        assert result == "direct_action"

    def test_extract_action_type_from_attrs_fallback_check(self, audit_service):
        """Test action type extraction with fallback logic."""
        # Arrange - First get() returns None, but key exists
        attrs = {"action_type": "fallback_action"}
        
        # Mock the first get() to return None to test the fallback
        original_get = attrs.get
        def mock_get(key, default=None):
            if key == "action_type" and not hasattr(mock_get, 'called'):
                mock_get.called = True
                return None
            return original_get(key, default)
        
        attrs.get = mock_get

        # Act
        result = audit_service._extract_action_type_from_attrs(attrs)

        # Assert
        assert result == "fallback_action"

    def test_extract_action_type_from_attrs_not_found(self, audit_service):
        """Test action type extraction when key doesn't exist."""
        # Arrange
        attrs = {"other_key": "other_value"}

        # Act
        result = audit_service._extract_action_type_from_attrs(attrs)

        # Assert
        assert result is None

    def test_create_audit_request_from_attrs_complete(self, audit_service):
        """Test audit request creation from attributes with complete data."""
        # Arrange
        timestamp = datetime(2023, 1, 1, 17, 0, 0, tzinfo=timezone.utc)
        attrs = {
            "event_id": "event-123",
            "thought_id": "thought-456",
            "task_id": "task-789",
            "actor": "test_actor",
            "handler_name": "test_handler",
            "outcome": "success",
            "extra_field": "extra_value"
        }
        action_type = "test_action"

        # Act
        result = audit_service._create_audit_request_from_attrs(attrs, timestamp, action_type)

        # Assert
        assert isinstance(result, AuditRequest)
        assert result.entry_id == "event-123"
        assert result.timestamp == timestamp
        assert result.entity_id == "thought-456"  # Should prefer thought_id
        assert result.event_type == "test_action"
        assert result.actor == "test_actor"
        assert result.details["action_type"] == "test_action"
        assert result.details["thought_id"] == "thought-456"
        assert result.details["task_id"] == "task-789"
        assert result.details["handler_name"] == "test_handler"
        assert result.details["attributes"] == attrs
        assert result.outcome == "success"

    def test_create_audit_request_from_attrs_fallbacks(self, audit_service):
        """Test audit request creation with fallback values."""
        # Arrange
        timestamp = datetime(2023, 1, 1, 18, 0, 0, tzinfo=timezone.utc)
        attrs = {
            "task_id": "fallback-task",  # Should use this since no thought_id
            "handler_name": "fallback_handler"  # Should use this since no actor
        }
        action_type = "fallback_action"

        # Act
        result = audit_service._create_audit_request_from_attrs(attrs, timestamp, action_type)

        # Assert
        assert isinstance(result, AuditRequest)
        assert len(result.entry_id) > 0  # Should generate UUID
        assert result.timestamp == timestamp
        assert result.entity_id == "fallback-task"  # Should use task_id as fallback
        assert result.event_type == "fallback_action"
        assert result.actor == "fallback_handler"  # Should use handler_name as fallback for actor
        assert result.details["handler_name"] == "fallback_handler"
        assert result.outcome is None

    def test_create_audit_request_from_attrs_minimal(self, audit_service):
        """Test audit request creation with minimal data."""
        # Arrange
        timestamp = datetime(2023, 1, 1, 19, 0, 0, tzinfo=timezone.utc)
        attrs = {}
        action_type = "minimal_action"

        # Act
        result = audit_service._create_audit_request_from_attrs(attrs, timestamp, action_type)

        # Assert
        assert isinstance(result, AuditRequest)
        assert len(result.entry_id) > 0  # Should generate UUID
        assert result.timestamp == timestamp
        assert result.entity_id == ""  # No thought_id or task_id
        assert result.event_type == "minimal_action"
        assert result.actor == "system"  # Default fallback
        assert result.details["action_type"] == "minimal_action"
        assert result.details["thought_id"] == ""
        assert result.details["task_id"] == ""
        assert result.details["handler_name"] == ""
        assert result.details["attributes"] == {}
        assert result.outcome is None