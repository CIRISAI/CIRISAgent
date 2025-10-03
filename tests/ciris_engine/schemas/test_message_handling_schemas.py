"""
Tests for message handling schemas.

Tests the new MessageHandlingStatus, PassiveObservationResult, and MessageHandlingResult
schemas to ensure they work correctly and serve as documentation.
"""

import pytest
from pydantic import ValidationError

from ciris_engine.schemas.runtime.messages import MessageHandlingResult, MessageHandlingStatus, PassiveObservationResult


class TestMessageHandlingStatus:
    """Tests for MessageHandlingStatus enum."""

    def test_all_status_values_available(self):
        """Test that all expected status values are available."""
        expected_statuses = [
            "TASK_CREATED",
            "UPDATED_EXISTING_TASK",
            "AGENT_OWN_MESSAGE",
            "FILTERED_OUT",
            "CREDIT_DENIED",
            "CREDIT_CHECK_FAILED",
            "PROCESSOR_PAUSED",
            "RATE_LIMITED",
            "CHANNEL_RESTRICTED",
        ]

        for status_name in expected_statuses:
            assert hasattr(MessageHandlingStatus, status_name)
            status = getattr(MessageHandlingStatus, status_name)
            assert status.value == status_name

    def test_status_is_string_enum(self):
        """Test that status values are strings."""
        status = MessageHandlingStatus.TASK_CREATED
        assert isinstance(status.value, str)
        assert status == "TASK_CREATED"


class TestPassiveObservationResult:
    """Tests for PassiveObservationResult schema."""

    def test_create_new_task_result(self):
        """Test creating result for a new task."""
        result = PassiveObservationResult(
            task_id="task-123",
            task_created=True,
            thought_id="thought-456",
            existing_task_updated=False,
        )

        assert result.task_id == "task-123"
        assert result.task_created is True
        assert result.thought_id == "thought-456"
        assert result.existing_task_updated is False

    def test_create_updated_task_result(self):
        """Test creating result for an existing task update."""
        result = PassiveObservationResult(
            task_id="existing-task-999",
            task_created=False,
            existing_task_updated=True,
        )

        assert result.task_id == "existing-task-999"
        assert result.task_created is False
        assert result.thought_id is None  # No thought created for update
        assert result.existing_task_updated is True

    def test_required_fields(self):
        """Test that required fields are enforced."""
        # Missing both task_id and task_created
        with pytest.raises(ValidationError) as exc_info:
            PassiveObservationResult()

        errors = exc_info.value.errors()
        field_names = [error["loc"][0] for error in errors]
        assert "task_id" in field_names
        assert "task_created" in field_names  # Also required

    def test_optional_fields_have_defaults(self):
        """Test that optional fields have sensible defaults."""
        result = PassiveObservationResult(
            task_id="task-123",
            task_created=True,
        )

        assert result.thought_id is None
        assert result.existing_task_updated is False


class TestMessageHandlingResult:
    """Tests for MessageHandlingResult schema."""

    def test_create_successful_result(self):
        """Test creating a successful message handling result."""
        result = MessageHandlingResult(
            status=MessageHandlingStatus.TASK_CREATED,
            task_id="task-123",
            message_id="msg-456",
            channel_id="api_user123",
            task_priority=0,
        )

        assert result.status == MessageHandlingStatus.TASK_CREATED
        assert result.task_id == "task-123"
        assert result.message_id == "msg-456"
        assert result.channel_id == "api_user123"
        assert result.task_priority == 0
        assert result.filtered is False
        assert result.existing_task_updated is False

    def test_create_filtered_result(self):
        """Test creating a filtered message result."""
        result = MessageHandlingResult(
            status=MessageHandlingStatus.FILTERED_OUT,
            task_id=None,
            message_id="msg-789",
            channel_id="api_user456",
            filtered=True,
            filter_reasoning="Message contains spam keywords",
        )

        assert result.status == MessageHandlingStatus.FILTERED_OUT
        assert result.task_id is None
        assert result.filtered is True
        assert result.filter_reasoning == "Message contains spam keywords"

    def test_create_credit_denied_result(self):
        """Test creating a credit denied result."""
        result = MessageHandlingResult(
            status=MessageHandlingStatus.CREDIT_DENIED,
            task_id=None,
            message_id="msg-999",
            channel_id="api_user789",
            credit_denied=True,
            credit_denial_reason="Insufficient credits",
        )

        assert result.status == MessageHandlingStatus.CREDIT_DENIED
        assert result.credit_denied is True
        assert result.credit_denial_reason == "Insufficient credits"

    def test_create_updated_task_result(self):
        """Test creating result for existing task update."""
        result = MessageHandlingResult(
            status=MessageHandlingStatus.UPDATED_EXISTING_TASK,
            task_id="existing-task-555",
            message_id="msg-111",
            channel_id="api_user999",
            existing_task_updated=True,
            task_priority=5,
        )

        assert result.status == MessageHandlingStatus.UPDATED_EXISTING_TASK
        assert result.task_id == "existing-task-555"
        assert result.existing_task_updated is True
        assert result.task_priority == 5

    def test_required_fields(self):
        """Test that required fields are enforced."""
        with pytest.raises(ValidationError) as exc_info:
            MessageHandlingResult()

        errors = exc_info.value.errors()
        field_names = [error["loc"][0] for error in errors]

        # These fields are required
        assert "status" in field_names
        assert "message_id" in field_names
        assert "channel_id" in field_names

    def test_optional_fields_have_defaults(self):
        """Test that optional fields have sensible defaults."""
        result = MessageHandlingResult(
            status=MessageHandlingStatus.TASK_CREATED,
            message_id="msg-123",
            channel_id="api_user",
        )

        assert result.task_id is None
        assert result.filtered is False
        assert result.filter_reasoning is None
        assert result.credit_denied is False
        assert result.credit_denial_reason is None
        assert result.task_priority == 0
        assert result.existing_task_updated is False

    def test_priority_levels(self):
        """Test different priority levels."""
        # Passive (0)
        passive = MessageHandlingResult(
            status=MessageHandlingStatus.TASK_CREATED,
            message_id="msg-1",
            channel_id="api_user",
            task_priority=0,
        )
        assert passive.task_priority == 0

        # High (5)
        high = MessageHandlingResult(
            status=MessageHandlingStatus.TASK_CREATED,
            message_id="msg-2",
            channel_id="api_user",
            task_priority=5,
        )
        assert high.task_priority == 5

        # Critical (10)
        critical = MessageHandlingResult(
            status=MessageHandlingStatus.TASK_CREATED,
            message_id="msg-3",
            channel_id="api_user",
            task_priority=10,
        )
        assert critical.task_priority == 10

    def test_serialization_to_dict(self):
        """Test that schema can be serialized to dict."""
        result = MessageHandlingResult(
            status=MessageHandlingStatus.TASK_CREATED,
            task_id="task-123",
            message_id="msg-456",
            channel_id="api_user",
            task_priority=5,
        )

        result_dict = result.model_dump()

        assert result_dict["status"] == "TASK_CREATED"
        assert result_dict["task_id"] == "task-123"
        assert result_dict["message_id"] == "msg-456"
        assert result_dict["channel_id"] == "api_user"
        assert result_dict["task_priority"] == 5

    def test_deserialization_from_dict(self):
        """Test that schema can be created from dict."""
        data = {
            "status": "FILTERED_OUT",
            "message_id": "msg-789",
            "channel_id": "api_user",
            "filtered": True,
            "filter_reasoning": "Spam detected",
        }

        result = MessageHandlingResult(**data)

        assert result.status == MessageHandlingStatus.FILTERED_OUT
        assert result.message_id == "msg-789"
        assert result.filtered is True
        assert result.filter_reasoning == "Spam detected"
