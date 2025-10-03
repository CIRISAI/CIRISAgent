"""
Comprehensive tests for the /agent/message endpoint.

Tests the new async message submission endpoint that returns task_id immediately.
This serves as a blueprint for how to test endpoints with proper mocking and fixtures.
"""

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from ciris_engine.logic.adapters.api.routes import agent
from ciris_engine.logic.adapters.api.routes.agent import (
    MessageRequest,
    MessageRejectionReason,
    MessageSubmissionResponse,
    router,
)
from ciris_engine.logic.adapters.base_observer import CreditCheckFailed, CreditDenied
from ciris_engine.schemas.api.auth import AuthContext, Permission, UserRole
from ciris_engine.schemas.runtime.messages import (
    MessageHandlingResult,
    MessageHandlingStatus,
    PassiveObservationResult,
)


def create_auth_dependency(auth_context):
    """Create an async auth dependency that returns the given context."""

    async def mock_auth():
        return auth_context

    return mock_auth


@pytest.fixture
def app():
    """Create a FastAPI app with the agent router and mock state."""
    app = FastAPI()
    app.include_router(router)

    # Mock auth service
    auth_service = Mock()
    auth_service.get_user = Mock(return_value=None)
    auth_service._users = {}
    app.state.auth_service = auth_service

    # Mock agent processor (not paused)
    agent_processor = Mock()
    agent_processor._is_paused = False
    agent_processor.state_manager = Mock(current_state="WORK")

    # Mock runtime
    runtime = Mock()
    runtime.agent_processor = agent_processor
    runtime.agent_identity = Mock(agent_id="test_agent", name="Test Agent")
    app.state.runtime = runtime

    # Mock API config
    app.state.api_config = Mock(interaction_timeout=55.0)

    # Mock consent service
    app.state.consent_manager = AsyncMock()
    app.state.consent_manager.get_consent = AsyncMock(return_value=Mock(user_id="test_user"))

    # Mock resource monitor (no credit provider by default)
    app.state.resource_monitor = Mock(spec=[])

    # Mock message handler - returns MessageHandlingResult
    app.state.on_message = AsyncMock()

    return app


@pytest.fixture
def client(app):
    """Create a test client."""
    return TestClient(app)


@pytest.fixture
def auth_context_admin():
    """Create an admin auth context with SEND_MESSAGES permission."""
    return AuthContext(
        user_id="admin_user",
        role=UserRole.ADMIN,
        permissions={Permission.SEND_MESSAGES, Permission.VIEW_MESSAGES},
        api_key_id="test_key",
        authenticated_at=datetime.now(timezone.utc),
    )


@pytest.fixture
def auth_context_observer_no_permission():
    """Create an observer auth context WITHOUT SEND_MESSAGES permission."""
    return AuthContext(
        user_id="observer_user",
        role=UserRole.OBSERVER,
        permissions={Permission.VIEW_MESSAGES},
        api_key_id="test_key",
        authenticated_at=datetime.now(timezone.utc),
    )


@pytest.fixture
def mock_message_handling_result_success():
    """Create a successful MessageHandlingResult with new task created."""
    return MessageHandlingResult(
        status=MessageHandlingStatus.TASK_CREATED,
        task_id="task-12345",
        message_id="msg-67890",
        channel_id="api_admin_user",
        task_priority=0,
        existing_task_updated=False,
    )


@pytest.fixture
def mock_message_handling_result_updated():
    """Create a MessageHandlingResult for existing task update."""
    return MessageHandlingResult(
        status=MessageHandlingStatus.UPDATED_EXISTING_TASK,
        task_id="existing-task-999",
        message_id="msg-67890",
        channel_id="api_admin_user",
        task_priority=0,
        existing_task_updated=True,
    )


@pytest.fixture
def mock_message_handling_result_filtered():
    """Create a MessageHandlingResult for filtered message."""
    return MessageHandlingResult(
        status=MessageHandlingStatus.FILTERED_OUT,
        task_id=None,
        message_id="msg-67890",
        channel_id="api_admin_user",
        filtered=True,
        filter_reasoning="Message contains spam keywords",
        task_priority=0,
        existing_task_updated=False,
    )


class TestMessageEndpointSuccess:
    """Tests for successful message submissions."""

    @pytest.mark.asyncio
    async def test_message_submission_new_task_created(
        self, app, auth_context_admin, mock_message_handling_result_success
    ):
        """Test successful message submission that creates a new task."""
        # Override auth dependency
        app.dependency_overrides[agent.require_observer] = create_auth_dependency(auth_context_admin)

        # Mock on_message to return success result
        app.state.on_message.return_value = mock_message_handling_result_success

        client = TestClient(app)
        response = client.post(
            "/agent/message",
            json={"message": "Hello agent!"},
        )

        # Verify response
        assert response.status_code == 200
        data = response.json()["data"]

        assert data["message_id"] is not None
        assert data["task_id"] == "task-12345"
        assert data["channel_id"] == "api_admin_user"
        assert data["accepted"] is True
        assert data["rejection_reason"] is None
        assert data["rejection_detail"] is None
        assert "submitted_at" in data

        # Verify on_message was called
        app.state.on_message.assert_called_once()
        call_args = app.state.on_message.call_args[0][0]
        assert call_args.content == "Hello agent!"
        assert call_args.author_id == "admin_user"

    @pytest.mark.asyncio
    async def test_message_submission_existing_task_updated(
        self, app, auth_context_admin, mock_message_handling_result_updated
    ):
        """Test message submission that updates an existing task."""
        app.dependency_overrides[agent.require_observer] = create_auth_dependency(auth_context_admin)
        app.state.on_message.return_value = mock_message_handling_result_updated

        client = TestClient(app)
        response = client.post(
            "/agent/message",
            json={"message": "Follow-up message"},
        )

        assert response.status_code == 200
        data = response.json()["data"]

        assert data["task_id"] == "existing-task-999"
        assert data["accepted"] is True
        assert data["rejection_detail"] == "Existing task updated with new information"


class TestMessageEndpointRejections:
    """Tests for message rejections with various reasons."""

    @pytest.mark.asyncio
    async def test_message_rejected_no_permission(self, app, auth_context_observer_no_permission):
        """Test message rejected due to missing SEND_MESSAGES permission."""
        app.dependency_overrides[agent.require_observer] = create_auth_dependency(
            auth_context_observer_no_permission
        )

        client = TestClient(app)
        response = client.post(
            "/agent/message",
            json={"message": "Hello agent!"},
        )

        # Should return 403 Forbidden
        assert response.status_code == 403
        detail = response.json()["detail"]
        assert detail["error"] == "insufficient_permissions"

    @pytest.mark.asyncio
    async def test_message_rejected_filtered_out(
        self, app, auth_context_admin, mock_message_handling_result_filtered
    ):
        """Test message rejected by adaptive filter."""
        app.dependency_overrides[agent.require_observer] = create_auth_dependency(auth_context_admin)
        app.state.on_message.return_value = mock_message_handling_result_filtered

        client = TestClient(app)
        response = client.post(
            "/agent/message",
            json={"message": "Spam spam spam!"},
        )

        assert response.status_code == 200
        data = response.json()["data"]

        assert data["accepted"] is False
        assert data["task_id"] is None
        assert data["rejection_reason"] == "FILTERED_OUT"
        assert "spam" in data["rejection_detail"].lower()

    @pytest.mark.asyncio
    async def test_message_rejected_credit_denied(self, app, auth_context_admin):
        """Test message rejected due to insufficient credits."""
        app.dependency_overrides[agent.require_observer] = create_auth_dependency(auth_context_admin)

        # Mock on_message to raise CreditDenied
        app.state.on_message.side_effect = CreditDenied("Insufficient credits for API usage")

        client = TestClient(app)
        response = client.post(
            "/agent/message",
            json={"message": "Hello agent!"},
        )

        assert response.status_code == 200
        data = response.json()["data"]

        assert data["accepted"] is False
        assert data["task_id"] is None
        assert data["rejection_reason"] == "CREDIT_DENIED"
        assert "Insufficient credits" in data["rejection_detail"]

    @pytest.mark.asyncio
    async def test_message_rejected_credit_check_failed(self, app, auth_context_admin):
        """Test message rejected due to credit provider failure."""
        app.dependency_overrides[agent.require_observer] = create_auth_dependency(auth_context_admin)

        # Mock on_message to raise CreditCheckFailed
        app.state.on_message.side_effect = CreditCheckFailed("Credit provider timeout")

        client = TestClient(app)
        response = client.post(
            "/agent/message",
            json={"message": "Hello agent!"},
        )

        assert response.status_code == 200
        data = response.json()["data"]

        assert data["accepted"] is False
        assert data["task_id"] is None
        assert data["rejection_reason"] == "CREDIT_CHECK_FAILED"
        assert "timeout" in data["rejection_detail"].lower()

    @pytest.mark.asyncio
    async def test_message_rejected_processor_paused(self, app, auth_context_admin):
        """Test message rejected when agent processor is paused."""
        app.dependency_overrides[agent.require_observer] = create_auth_dependency(auth_context_admin)

        # Mark processor as paused
        app.state.runtime.agent_processor._is_paused = True

        client = TestClient(app)
        response = client.post(
            "/agent/message",
            json={"message": "Hello agent!"},
        )

        assert response.status_code == 200
        data = response.json()["data"]

        assert data["accepted"] is False
        assert data["task_id"] is None
        assert data["rejection_reason"] == "PROCESSOR_PAUSED"
        assert "paused" in data["rejection_detail"].lower()


class TestMessageEndpointCreditEnforcement:
    """Tests for credit policy enforcement."""

    @pytest.mark.asyncio
    async def test_credit_metadata_attached_when_provider_configured(
        self, app, auth_context_admin, mock_message_handling_result_success
    ):
        """Test that credit metadata is attached to messages when provider is configured."""
        app.dependency_overrides[agent.require_observer] = create_auth_dependency(auth_context_admin)
        app.state.on_message.return_value = mock_message_handling_result_success

        # Add credit provider to resource monitor
        app.state.resource_monitor = Mock()
        app.state.resource_monitor.credit_provider = Mock()  # Provider exists

        client = TestClient(app)
        response = client.post(
            "/agent/message",
            json={"message": "Hello agent!"},
        )

        assert response.status_code == 200

        # Verify credit metadata was attached
        call_args = app.state.on_message.call_args[0][0]
        assert hasattr(call_args, "credit_account") or "credit_account" in dir(call_args)


class TestMessageEndpointValidation:
    """Tests for input validation."""

    @pytest.mark.asyncio
    async def test_message_missing_required_field(self, app, auth_context_admin):
        """Test request rejected when message field is missing."""
        app.dependency_overrides[agent.require_observer] = create_auth_dependency(auth_context_admin)

        client = TestClient(app)
        response = client.post(
            "/agent/message",
            json={},  # Missing "message" field
        )

        assert response.status_code == 422  # Validation error

    @pytest.mark.asyncio
    async def test_message_with_context(
        self, app, auth_context_admin, mock_message_handling_result_success
    ):
        """Test message submission with optional context."""
        app.dependency_overrides[agent.require_observer] = create_auth_dependency(auth_context_admin)
        app.state.on_message.return_value = mock_message_handling_result_success

        client = TestClient(app)
        response = client.post(
            "/agent/message",
            json={
                "message": "Hello agent!",
                "context": {
                    "thread_id": "thread-123",
                    "metadata": {"priority": "high"},
                },
            },
        )

        assert response.status_code == 200
        data = response.json()["data"]
        assert data["accepted"] is True


class TestMessageEndpointConsentHandling:
    """Tests for consent handling during message submission."""

    @pytest.mark.asyncio
    async def test_consent_checked_for_new_user(
        self, app, auth_context_admin, mock_message_handling_result_success
    ):
        """Test that consent is checked when user submits a message."""
        app.dependency_overrides[agent.require_observer] = create_auth_dependency(auth_context_admin)
        app.state.on_message.return_value = mock_message_handling_result_success

        # Mock consent service to indicate existing consent
        app.state.consent_manager.get_consent = AsyncMock(return_value=Mock(user_id="admin_user"))

        client = TestClient(app)
        response = client.post(
            "/agent/message",
            json={"message": "Hello agent!"},
        )

        assert response.status_code == 200

        # Verify consent was checked
        app.state.consent_manager.get_consent.assert_called_once_with("admin_user")


class TestMessageEndpointResponseSchema:
    """Tests to verify response schema matches specification."""

    @pytest.mark.asyncio
    async def test_response_schema_all_fields_present(
        self, app, auth_context_admin, mock_message_handling_result_success
    ):
        """Test that response contains all required fields."""
        app.dependency_overrides[agent.require_observer] = create_auth_dependency(auth_context_admin)
        app.state.on_message.return_value = mock_message_handling_result_success

        client = TestClient(app)
        response = client.post(
            "/agent/message",
            json={"message": "Hello agent!"},
        )

        assert response.status_code == 200
        data = response.json()["data"]

        # Verify all required fields are present
        required_fields = [
            "message_id",
            "task_id",
            "channel_id",
            "submitted_at",
            "accepted",
            "rejection_reason",
            "rejection_detail",
        ]

        for field in required_fields:
            assert field in data, f"Missing required field: {field}"

    @pytest.mark.asyncio
    async def test_response_schema_types_correct(
        self, app, auth_context_admin, mock_message_handling_result_success
    ):
        """Test that response field types are correct."""
        app.dependency_overrides[agent.require_observer] = create_auth_dependency(auth_context_admin)
        app.state.on_message.return_value = mock_message_handling_result_success

        client = TestClient(app)
        response = client.post(
            "/agent/message",
            json={"message": "Hello agent!"},
        )

        assert response.status_code == 200
        data = response.json()["data"]

        # Verify types
        assert isinstance(data["message_id"], str)
        assert isinstance(data["task_id"], str) or data["task_id"] is None
        assert isinstance(data["channel_id"], str)
        assert isinstance(data["submitted_at"], str)
        assert isinstance(data["accepted"], bool)
        assert data["rejection_reason"] is None or isinstance(data["rejection_reason"], str)
        assert data["rejection_detail"] is None or isinstance(data["rejection_detail"], str)
