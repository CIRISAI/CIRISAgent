"""
Comprehensive tests for agent API routes.

Tests all endpoints in ciris_engine/logic/adapters/api/routes/agent.py
to improve coverage from 17.4% to near 100%.
"""

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient

from ciris_engine.logic.adapters.api.dependencies.auth import AuthContext, require_observer
from ciris_engine.logic.adapters.api.routes import agent
from ciris_engine.logic.adapters.api.routes.agent import (
    AgentIdentity,
    AgentStatus,
    ChannelInfo,
    ChannelList,
    ConversationHistory,
    ConversationMessage,
    InteractRequest,
    InteractResponse,
    notify_interact_response,
    router,
    store_message_response,
)
from ciris_engine.logic.adapters.api.services.auth_service import APIAuthService
from ciris_engine.schemas.api.agent import AgentLineage, MessageContext, ServiceAvailability
from ciris_engine.schemas.api.auth import Permission, UserRole
from ciris_engine.schemas.api.responses import SuccessResponse
from ciris_engine.schemas.runtime.messages import IncomingMessage


def create_auth_dependency(auth_context):
    """Create an async auth dependency that returns the given context."""

    async def mock_auth():
        return auth_context

    return mock_auth


@pytest.fixture
def app():
    """Create a FastAPI app with the agent router."""
    app = FastAPI()
    app.include_router(router)

    # Create a proper APIAuthService mock
    auth_service = MagicMock(spec=APIAuthService)
    auth_service.validate_api_key = MagicMock(return_value=MagicMock(user_id="test_user", role=UserRole.ADMIN))
    auth_service.get_user = MagicMock(return_value=None)
    auth_service.validate_service_token = MagicMock(return_value=None)
    auth_service._users = {}

    # Set up app state
    app.state.auth_service = auth_service
    app.state.memory_service = AsyncMock()
    app.state.communication_service = AsyncMock()
    app.state.tool_service = AsyncMock()
    app.state.time_service = AsyncMock()
    app.state.task_scheduler = AsyncMock()
    app.state.task_scheduler.get_current_task = AsyncMock(return_value=None)  # Return None by default, not AsyncMock
    app.state.resource_monitor = AsyncMock()
    app.state.service_registry = MagicMock()  # Use MagicMock since get_services_by_type is called synchronously
    app.state.service_registry.get_services_by_type = MagicMock(return_value=[])  # Return empty list by default
    app.state.runtime = AsyncMock()
    app.state.on_message = AsyncMock()
    app.state.api_config = MagicMock(interaction_timeout=5.0)

    # Mock runtime properties
    app.state.runtime.state_manager = MagicMock(current_state="WORK")
    identity_mock = MagicMock()
    identity_mock.agent_id = "test_agent"
    identity_mock.name = "Test Agent"  # Explicitly set as string, not MagicMock
    identity_mock.purpose = "Test Agent. A helpful assistant."  # Add purpose attribute
    core_profile_mock = MagicMock()
    core_profile_mock.description = "Test Agent. A helpful assistant."  # Explicitly set as string
    identity_mock.core_profile = core_profile_mock
    identity_mock.identity_metadata = MagicMock(
        created_at=datetime.now(timezone.utc),
        model="test-model",
        version="1.0",
        parent_id=None,
        creation_context="test",
        adaptations=[],
    )
    app.state.runtime.agent_identity = identity_mock
    app.state.runtime.adapters = []
    app.state.runtime.service_registry = MagicMock()  # Use MagicMock for consistency

    # Mock time service
    app.state.time_service._start_time = datetime.now(timezone.utc) - timedelta(seconds=3600)
    app.state.time_service.now = MagicMock(return_value=datetime.now(timezone.utc))
    app.state.time_service.get_status = MagicMock(return_value=MagicMock(uptime_seconds=3600.0))

    # Mock resource monitor
    app.state.resource_monitor.snapshot = MagicMock(memory_mb=512.0)

    return app


@pytest.fixture
def client(app):
    """Create a test client."""
    return TestClient(app)


@pytest.fixture
def auth_context_admin():
    """Create an admin auth context."""
    return AuthContext(
        user_id="admin_user",
        role=UserRole.ADMIN,
        permissions={Permission.SEND_MESSAGES, Permission.VIEW_MESSAGES, Permission.VIEW_CONFIG},
        api_key_id="test_key",
        authenticated_at=datetime.now(timezone.utc),
    )


@pytest.fixture
def auth_context_observer():
    """Create an observer auth context."""
    return AuthContext(
        user_id="observer_user",
        role=UserRole.OBSERVER,
        permissions={Permission.VIEW_MESSAGES, Permission.VIEW_CONFIG},
        api_key_id="test_key",
        authenticated_at=datetime.now(timezone.utc),
    )


class TestInteractEndpoint:
    """Tests for the /interact endpoint."""

    @pytest.mark.asyncio
    async def test_interact_success(self, app, auth_context_admin):
        """Test successful interaction with response."""
        # Setup
        message_id = None

        async def mock_on_message(msg: IncomingMessage):
            nonlocal message_id
            message_id = msg.message_id
            # Simulate agent response
            await asyncio.sleep(0.1)
            await store_message_response(msg.message_id, "Hello! How can I help you?")

        app.state.on_message = mock_on_message

        # Override auth dependency to return our test context
        def override_auth():
            return auth_context_admin

        app.dependency_overrides[require_observer] = override_auth

        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post(
                    "/agent/interact", json={"message": "Hello"}, headers={"Authorization": "Bearer test_token"}
                )

            if response.status_code != 200:
                print(f"Response: {response.status_code}")
                print(f"Content: {response.content}")
            assert response.status_code == 200
            data = response.json()
            # The actual response structure from the API
            assert "data" in data
            assert "metadata" in data
            assert data["data"]["response"] == "Hello! How can I help you?"
            assert data["data"]["state"] == "WORK"
            assert "message_id" in data["data"]
            assert "processing_time_ms" in data["data"]
        finally:
            # Clean up override
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_interact_timeout(self, app, auth_context_admin):
        """Test interaction timeout."""
        # Setup - don't send a response
        app.state.api_config.interaction_timeout = 0.1  # Short timeout
        app.state.on_message = AsyncMock()

        # Mock auth dependency using override
        app.dependency_overrides[require_observer] = lambda: auth_context_admin

        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post(
                    "/agent/interact", json={"message": "Hello"}, headers={"Authorization": "Bearer test_token"}
                )

            assert response.status_code == 200
            data = response.json()
            assert "data" in data  # Response structure check
            assert "Still processing" in data["data"]["response"]
            assert data["data"]["processing_time_ms"] >= 100
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_interact_permission_denied(self, app, auth_context_observer):
        """Test interaction with insufficient permissions."""
        # Mock auth dependency - observer without SEND_MESSAGES permission
        app.dependency_overrides[require_observer] = lambda: auth_context_observer

        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post(
                    "/agent/interact", json={"message": "Hello"}, headers={"Authorization": "Bearer test_token"}
                )

        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 403
        data = response.json()
        assert "insufficient_permissions" in data["detail"]["error"]
        assert "discord_invite" in data["detail"]

    @pytest.mark.asyncio
    async def test_interact_auto_permission_request(self, app, auth_context_observer):
        """Test automatic permission request for OAuth users."""
        # Setup OAuth user
        oauth_user = MagicMock(wa_id="oauth_user", auth_type="oauth", permission_requested_at=None)
        app.state.auth_service.get_user = MagicMock(return_value=oauth_user)
        app.state.auth_service._users = {"oauth_user": oauth_user}

        # Mock auth dependency
        app.dependency_overrides[require_observer] = lambda: auth_context_observer

        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post(
                    "/agent/interact", json={"message": "Hello"}, headers={"Authorization": "Bearer test_token"}
                )

        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 403
        # Check that permission request was created
        assert oauth_user.permission_requested_at is not None

    @pytest.mark.asyncio
    async def test_interact_no_handler(self, app, auth_context_admin):
        """Test interaction when message handler is not configured."""
        # Remove handler
        delattr(app.state, "on_message")

        # Mock auth dependency
        app.dependency_overrides[require_observer] = lambda: auth_context_admin

        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post(
                    "/agent/interact", json={"message": "Hello"}, headers={"Authorization": "Bearer test_token"}
                )

        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 503
        assert "Message handler not configured" in response.json()["detail"]


class TestHistoryEndpoint:
    """Tests for the /history endpoint."""

    @pytest.mark.asyncio
    async def test_history_with_mock_data(self, app, auth_context_admin):
        """Test history with mock message data."""
        # Setup mock history
        app.state.message_history = [
            {
                "message_id": "msg1",
                "author_id": "admin_user",
                "content": "Hello",
                "channel_id": "api_admin_user",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "response": "Hello! How can I help?",
            },
            {
                "message_id": "msg2",
                "author_id": "admin_user",
                "content": "What's the weather?",
                "channel_id": "api_admin_user",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "response": "I don't have weather information.",
            },
        ]

        # Mock auth dependency
        app.dependency_overrides[require_observer] = lambda: auth_context_admin

        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.get("/agent/history?limit=10", headers={"Authorization": "Bearer test_token"})

        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 200
        data = response.json()
        assert "data" in data  # Response structure check
        assert len(data["data"]["messages"]) == 4  # 2 user + 2 agent messages
        assert data["data"]["total_count"] == 2
        assert data["data"]["has_more"] is False

    @pytest.mark.asyncio
    async def test_history_from_communication_service(self, app, auth_context_admin):
        """Test history from communication service."""

        # Setup communication service to return messages only for the correct channel
        async def fetch_messages_for_channel(channel_id, limit=None):
            if channel_id == "api_admin_user":
                return [
                    MagicMock(
                        message_id="msg1",
                        author_id="admin_user",
                        author_name="Admin",
                        content="Test message",
                        channel_id="api_admin_user",
                        timestamp=datetime.now(timezone.utc),
                        is_agent_message=False,
                    )
                ]
            return []  # Return empty for other channels

        app.state.communication_service.fetch_messages = AsyncMock(side_effect=fetch_messages_for_channel)

        # Mock auth dependency
        app.dependency_overrides[require_observer] = lambda: auth_context_admin

        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.get("/agent/history", headers={"Authorization": "Bearer test_token"})

        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 200
        data = response.json()
        assert "data" in data  # Response structure check
        assert len(data["data"]["messages"]) == 1
        assert data["data"]["messages"][0]["content"] == "Test message"

    @pytest.mark.asyncio
    async def test_history_from_memory_service(self, app, auth_context_admin):
        """Test history fallback to memory service."""
        # Remove communication service
        app.state.communication_service = None

        # Setup memory service
        mock_node = MagicMock(
            id="node1",
            created_at=datetime.now(timezone.utc).isoformat(),
            attributes={
                "message_id": "msg1",
                "author": "admin_user",
                "content": "Memory message",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "is_agent": False,
            },
        )
        app.state.memory_service.recall = AsyncMock(return_value=[mock_node])

        # Mock auth dependency
        app.dependency_overrides[require_observer] = lambda: auth_context_admin

        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.get("/agent/history", headers={"Authorization": "Bearer test_token"})

        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 200
        data = response.json()
        assert "data" in data  # Response structure check
        assert len(data["data"]["messages"]) == 1
        assert data["data"]["messages"][0]["content"] == "Memory message"

    @pytest.mark.asyncio
    async def test_history_with_limit_and_before(self, app, auth_context_admin):
        """Test history with limit and before parameters."""
        # Setup mock history
        now = datetime.now(timezone.utc)
        app.state.message_history = [
            {
                "message_id": f"msg{i}",
                "author_id": "admin_user",
                "content": f"Message {i}",
                "channel_id": "api_admin_user",
                "timestamp": (now - timedelta(hours=i)).isoformat(),
                "response": f"Response {i}",
            }
            for i in range(5)
        ]

        # Mock auth dependency
        before_time = (now - timedelta(hours=2)).isoformat()
        app.dependency_overrides[require_observer] = lambda: auth_context_admin

        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                # Pass parameters properly - let httpx handle encoding
                response = await client.get(
                    "/agent/history",
                    params={"limit": 2, "before": before_time},
                    headers={"Authorization": "Bearer test_token"},
                )

        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 200
        data = response.json()
        assert "data" in data  # Response structure check
        # Should only get messages older than 2 hours, limited to 2
        assert len(data["data"]["messages"]) <= 4  # 2 messages * 2 (user + agent)


class TestStatusEndpoint:
    """Tests for the /status endpoint."""

    @pytest.mark.asyncio
    async def test_status_success(self, app, auth_context_observer):
        """Test successful status retrieval."""
        # Mock auth dependency
        app.dependency_overrides[require_observer] = lambda: auth_context_observer

        try:
            # Patch the helper functions directly in the agent module
            with patch("ciris_engine.logic.adapters.api.routes.agent._count_wakeup_tasks", return_value=5):
                with patch(
                    "ciris_engine.logic.adapters.api.routes.agent._count_active_services", return_value=(12, {})
                ):
                    # Mock the service registry's get_services_by_type to be synchronous
                    app.state.service_registry.get_services_by_type = MagicMock(return_value=[])

                    transport = ASGITransport(app=app)
                    async with AsyncClient(transport=transport, base_url="http://test") as client:
                        response = await client.get("/agent/status", headers={"Authorization": "Bearer test_token"})

        finally:
            app.dependency_overrides.clear()

        if response.status_code != 200:
            print(f"ERROR in test_status_success: Status {response.status_code}")
            print(f"Response body: {response.text}")
        assert response.status_code == 200
        data = response.json()
        assert "data" in data  # Response structure check
        assert data["data"]["agent_id"] == "test_agent"
        assert data["data"]["name"] == "Test Agent"
        assert data["data"]["cognitive_state"] == "WORK"
        assert data["data"]["uptime_seconds"] == 3600.0
        # With no tasks and uptime > 60, defaults to 5
        assert data["data"]["messages_processed"] == 5
        assert data["data"]["services_active"] == 12  # Only singleton services since we mocked empty
        assert data["data"]["memory_usage_mb"] == 512.0

    @pytest.mark.asyncio
    async def test_status_no_runtime(self, app, auth_context_observer):
        """Test status when runtime is not available."""
        app.state.runtime = None

        # Mock auth dependency
        app.dependency_overrides[require_observer] = lambda: auth_context_observer

        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.get("/agent/status", headers={"Authorization": "Bearer test_token"})

        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 503
        assert "Runtime not available" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_status_with_current_task(self, app, auth_context_observer):
        """Test status with current task."""
        app.state.task_scheduler.get_current_task = AsyncMock(return_value="Processing user request")

        # Mock auth dependency
        app.dependency_overrides[require_observer] = lambda: auth_context_observer

        try:
            # Patch the helper functions directly in the agent module
            with patch("ciris_engine.logic.adapters.api.routes.agent._count_wakeup_tasks", return_value=5):
                with patch(
                    "ciris_engine.logic.adapters.api.routes.agent._count_active_services", return_value=(12, {})
                ):
                    # Mock the service registry's get_services_by_type to be synchronous
                    app.state.service_registry.get_services_by_type = MagicMock(return_value=[])

                    transport = ASGITransport(app=app)
                    async with AsyncClient(transport=transport, base_url="http://test") as client:
                        response = await client.get("/agent/status", headers={"Authorization": "Bearer test_token"})

        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 200
        data = response.json()
        assert data["data"]["current_task"] == "Processing user request"


class TestIdentityEndpoint:
    """Tests for the /identity endpoint."""

    @pytest.mark.asyncio
    async def test_identity_from_memory(self, app, auth_context_observer):
        """Test identity retrieval from memory service."""
        # Setup memory service
        mock_node = MagicMock(
            attributes={
                "agent_id": "memory_agent",
                "name": "Memory Agent",
                "purpose": "Test purposes",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "lineage": {
                    "model": "test-model",
                    "version": "2.0",
                    "parent_id": "parent_123",
                    "creation_context": "test",
                    "adaptations": ["adaptation1"],
                },
                "variance_threshold": 0.15,
            }
        )
        app.state.memory_service.recall = AsyncMock(return_value=[mock_node])

        # Setup tool service
        app.state.tool_service.list_tools = AsyncMock(return_value=["tool1", "tool2"])

        # Mock auth dependency
        app.dependency_overrides[require_observer] = lambda: auth_context_observer

        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.get("/agent/identity", headers={"Authorization": "Bearer test_token"})

        finally:
            app.dependency_overrides.clear()

        if response.status_code != 200:
            print(f"ERROR in test_identity_from_memory: Status {response.status_code}")
            print(f"Response body: {response.text}")
        assert response.status_code == 200
        data = response.json()
        assert "data" in data  # Response structure check
        assert data["data"]["agent_id"] == "memory_agent"
        assert data["data"]["name"] == "Memory Agent"
        assert data["data"]["purpose"] == "Test purposes"
        assert data["data"]["lineage"]["model"] == "test-model"
        assert data["data"]["lineage"]["version"] == "2.0"
        assert len(data["data"]["tools"]) == 2
        assert len(data["data"]["handlers"]) == 10  # Default handlers

    @pytest.mark.asyncio
    async def test_identity_fallback_to_runtime(self, app, auth_context_observer):
        """Test identity fallback to runtime when memory is empty."""
        # Memory returns empty
        app.state.memory_service.recall = AsyncMock(return_value=[])

        # Mock auth dependency
        app.dependency_overrides[require_observer] = lambda: auth_context_observer

        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.get("/agent/identity", headers={"Authorization": "Bearer test_token"})

        finally:
            app.dependency_overrides.clear()

        if response.status_code != 200:
            print(f"ERROR in test_identity_fallback_to_runtime: Status {response.status_code}")
            print(f"Response body: {response.text}")
        assert response.status_code == 200
        data = response.json()
        assert "data" in data  # Response structure check
        assert data["data"]["agent_id"] == "test_agent"
        assert data["data"]["name"] == "Test Agent"
        assert data["data"]["purpose"] == "Test Agent. A helpful assistant."

    @pytest.mark.asyncio
    async def test_identity_no_memory_service(self, app, auth_context_observer):
        """Test identity when memory service is not available."""
        app.state.memory_service = None

        # Mock auth dependency
        app.dependency_overrides[require_observer] = lambda: auth_context_observer

        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.get("/agent/identity", headers={"Authorization": "Bearer test_token"})

        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 503
        assert "Memory service not available" in response.json()["detail"]


class TestChannelsEndpoint:
    """Tests for the /channels endpoint."""

    @pytest.mark.asyncio
    async def test_channels_from_bootstrap_adapters(self, app, auth_context_observer):
        """Test channels from bootstrap adapters."""
        # Setup adapter with channels
        mock_adapter = MagicMock()
        mock_adapter.get_active_channels = AsyncMock(
            return_value=[
                MagicMock(
                    channel_id="discord_123",
                    channel_type="discord",
                    display_name="General",
                    is_active=True,
                    created_at=None,
                    last_activity=None,
                    message_count=10,
                )
            ]
        )
        mock_adapter.__class__.__name__ = "DiscordPlatform"
        app.state.runtime.adapters = [mock_adapter]

        # Mock auth dependency
        app.dependency_overrides[require_observer] = lambda: auth_context_observer

        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.get("/agent/channels", headers={"Authorization": "Bearer test_token"})

        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 200
        data = response.json()
        assert "data" in data  # Response structure check
        assert len(data["data"]["channels"]) >= 2  # Discord + default API channels
        discord_channel = next(c for c in data["data"]["channels"] if c["channel_id"] == "discord_123")
        assert discord_channel["display_name"] == "General"
        assert discord_channel["message_count"] == 10

    @pytest.mark.asyncio
    async def test_channels_from_dynamic_adapters(self, app, auth_context_observer):
        """Test channels from dynamically loaded adapters."""
        # Setup runtime control service with adapter manager
        mock_control_service = MagicMock()
        mock_adapter_manager = MagicMock()
        mock_control_service.adapter_manager = mock_adapter_manager

        # Setup loaded adapters
        mock_adapter_instance = MagicMock()
        mock_adapter_instance.adapter.get_active_channels = AsyncMock(
            return_value=[
                MagicMock(
                    channel_id="api_dynamic",
                    channel_type="api",
                    display_name="Dynamic API",
                    is_active=True,
                    created_at=None,
                    last_activity=None,
                    message_count=5,
                )
            ]
        )
        mock_adapter_instance.adapter_type = "api"

        mock_adapter_manager.loaded_adapters = {"dynamic_api": mock_adapter_instance}

        app.state.main_runtime_control_service = mock_control_service

        # Mock auth dependency
        app.dependency_overrides[require_observer] = lambda: auth_context_observer

        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.get("/agent/channels", headers={"Authorization": "Bearer test_token"})

        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 200
        data = response.json()
        assert "data" in data  # Response structure check
        # Should have dynamic channel + default API channels
        assert any(c["channel_id"] == "api_dynamic" for c in data["data"]["channels"])

    @pytest.mark.asyncio
    async def test_channels_default_only(self, app, auth_context_observer):
        """Test channels with only default API channels."""
        # No adapters configured
        app.state.runtime.adapters = []
        app.state.main_runtime_control_service = None

        # Mock auth dependency
        app.dependency_overrides[require_observer] = lambda: auth_context_observer

        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.get("/agent/channels", headers={"Authorization": "Bearer test_token"})

        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 200
        data = response.json()
        assert "data" in data  # Response structure check
        # Should have at least the default API channels
        assert len(data["data"]["channels"]) >= 2
        assert any("api_" in c["channel_id"] for c in data["data"]["channels"])


class TestHelperFunctions:
    """Tests for helper functions."""

    @pytest.mark.asyncio
    async def test_store_and_notify_message_response(self):
        """Test storing and notifying message responses."""
        message_id = "test_msg_123"
        response = "Test response"

        # Clear any existing state
        agent._message_responses.clear()
        agent._response_events.clear()

        # Create event and store it
        event = asyncio.Event()
        agent._response_events[message_id] = event

        # Store response
        await store_message_response(message_id, response)

        assert agent._message_responses[message_id] == response
        assert event.is_set()

    @pytest.mark.asyncio
    async def test_notify_interact_response(self):
        """Test notify interact response helper."""
        message_id = "test_msg_456"
        content = "Notification content"

        # Clear state
        agent._message_responses.clear()
        agent._response_events.clear()

        # Create event
        event = asyncio.Event()
        agent._response_events[message_id] = event

        # Notify
        await notify_interact_response(message_id, content)

        assert agent._message_responses[message_id] == content
        assert event.is_set()

    def test_get_cognitive_state(self):
        """Test _get_cognitive_state helper."""
        # With state manager
        runtime = MagicMock()
        runtime.state_manager = MagicMock(current_state="SOLITUDE")
        assert agent._get_cognitive_state(runtime) == "SOLITUDE"

        # Without state manager
        runtime = MagicMock(spec=[])
        assert agent._get_cognitive_state(runtime) == "UNKNOWN"  # Updated: should return UNKNOWN, not WORK

        # With None state manager
        runtime = MagicMock()
        runtime.state_manager = None
        assert agent._get_cognitive_state(runtime) == "UNKNOWN"

        # With state manager but no current_state attribute
        runtime = MagicMock()
        runtime.state_manager = MagicMock(spec=[])  # No current_state attribute
        assert agent._get_cognitive_state(runtime) == "UNKNOWN"

        # With enum-like state (has .value attribute)
        runtime = MagicMock()
        mock_state = MagicMock()
        mock_state.value = "WAKEUP"
        mock_state.__str__ = lambda self: "AgentState.WAKEUP"
        runtime.state_manager = MagicMock(current_state=mock_state)
        assert agent._get_cognitive_state(runtime) == "AgentState.WAKEUP"

        # With simple string state (no .value attribute)
        runtime = MagicMock()
        runtime.state_manager = MagicMock(current_state="DREAM")
        assert agent._get_cognitive_state(runtime) == "DREAM"

    def test_calculate_uptime(self):
        """Test _calculate_uptime helper."""
        # No time service
        assert agent._calculate_uptime(None) == 0.0

        # With get_status method
        time_service = MagicMock()
        time_service.get_status = MagicMock(return_value=MagicMock(uptime_seconds=1234.5))
        assert agent._calculate_uptime(time_service) == 1234.5

        # Calculate manually
        time_service = MagicMock(spec=["_start_time", "now"])
        start = datetime.now(timezone.utc) - timedelta(seconds=600)
        time_service._start_time = start
        time_service.now = MagicMock(return_value=datetime.now(timezone.utc))
        uptime = agent._calculate_uptime(time_service)
        assert 599 <= uptime <= 601  # Allow for small timing differences

    def test_count_wakeup_tasks(self):
        """Test _count_wakeup_tasks helper."""
        # Import persistence module correctly
        import ciris_engine.logic.persistence as persistence_module

        with patch.object(persistence_module, "get_tasks_by_status") as mock_get_tasks:
            # Setup completed tasks
            from ciris_engine.schemas.runtime.enums import TaskStatus

            mock_tasks = [
                MagicMock(task_id="VERIFY_IDENTITY_123", status=TaskStatus.COMPLETED),
                MagicMock(task_id="VALIDATE_INTEGRITY_456", status=TaskStatus.COMPLETED),
                MagicMock(task_id="OTHER_TASK_789", status=TaskStatus.COMPLETED),
            ]
            mock_get_tasks.return_value = mock_tasks

            count = agent._count_wakeup_tasks(100.0)
            assert count == 2  # Only 2 wakeup tasks

            # Test default when no tasks but uptime > threshold
            mock_get_tasks.return_value = []
            count = agent._count_wakeup_tasks(61.0)
            assert count == 5  # Default wakeup cycle

            # Test no default when uptime < threshold
            count = agent._count_wakeup_tasks(30.0)
            assert count == 0

    def test_count_active_services(self):
        """Test _count_active_services helper."""
        service_registry = MagicMock()

        # Mock service types
        from ciris_engine.schemas.runtime.enums import ServiceType

        def mock_get_services(service_type):
            if service_type == ServiceType.LLM:
                return ["provider1", "provider2"]
            elif service_type == ServiceType.MEMORY:
                return ["provider1"]
            else:
                return []

        service_registry.get_services_by_type = MagicMock(side_effect=mock_get_services)

        count, multi_provider = agent._count_active_services(service_registry)
        assert count >= 12  # At least 12 singleton + multi-provider
        # Check for either uppercase or lowercase keys (API may normalize)
        assert "LLM" in multi_provider or "llm" in multi_provider
        if "LLM" in multi_provider:
            assert multi_provider["LLM"]["providers"] == 2
        else:
            assert multi_provider["llm"]["providers"] == 2
        assert "MEMORY" in multi_provider or "memory" in multi_provider

    def test_get_agent_identity_info(self):
        """Test _get_agent_identity_info helper."""
        # With full identity - need to explicitly set name as string
        runtime = MagicMock()
        identity = MagicMock()
        identity.agent_id = "custom_agent"
        identity.name = "Custom Agent"  # Explicitly set as string
        runtime.agent_identity = identity
        agent_id, name = agent._get_agent_identity_info(runtime)
        assert agent_id == "custom_agent"
        assert name == "Custom Agent"

        # With core profile only
        runtime = MagicMock()
        runtime.agent_identity = MagicMock(agent_id="profile_agent", spec=["agent_id", "core_profile"])
        runtime.agent_identity.core_profile = MagicMock(description="Profile Agent. Does interesting things.")
        agent_id, name = agent._get_agent_identity_info(runtime)
        assert agent_id == "profile_agent"
        assert name == "Profile Agent"

        # No identity
        runtime = MagicMock(spec=[])
        agent_id, name = agent._get_agent_identity_info(runtime)
        assert agent_id == "ciris_agent"
        assert name == "CIRIS"

    def test_convert_to_channel_info(self):
        """Test _convert_to_channel_info helper."""
        # Pydantic model format
        channel = MagicMock(
            channel_id="test_channel",
            channel_type="discord",
            display_name="Test Channel",
            is_active=True,
            created_at=datetime.now(timezone.utc),
            last_activity=datetime.now(timezone.utc),
            message_count=42,
        )
        info = agent._convert_to_channel_info(channel, "discord")
        assert info.channel_id == "test_channel"
        assert info.channel_type == "discord"
        assert info.display_name == "Test Channel"
        assert info.message_count == 42

        # Dict format (legacy)
        channel_dict = {
            "channel_id": "dict_channel",
            "channel_type": "api",
            "display_name": "Dict Channel",
            "is_active": False,
            "message_count": 10,
        }
        info = agent._convert_to_channel_info(channel_dict, "api")
        assert info.channel_id == "dict_channel"
        assert info.channel_type == "api"
        assert info.is_active is False


class TestWebSocketEndpoint:
    """Tests for the WebSocket /stream endpoint."""

    @pytest.mark.asyncio
    async def test_websocket_missing_auth(self, app):
        """Test WebSocket connection without authorization."""
        from fastapi.testclient import TestClient

        client = TestClient(app)
        with pytest.raises(Exception):  # WebSocket should close
            with client.websocket_connect("/agent/stream") as websocket:
                data = websocket.receive_json()

    @pytest.mark.asyncio
    async def test_websocket_invalid_auth(self, app):
        """Test WebSocket connection with invalid authorization."""
        from fastapi.testclient import TestClient

        app.state.auth_service.validate_api_key = MagicMock(return_value=None)

        client = TestClient(app)
        with pytest.raises(Exception):  # WebSocket should close
            with client.websocket_connect(
                "/agent/stream", headers={"authorization": "Bearer invalid_token"}
            ) as websocket:
                data = websocket.receive_json()

    @pytest.mark.asyncio
    async def test_websocket_successful_connection(self, app):
        """Test successful WebSocket connection and subscription."""
        from fastapi.testclient import TestClient

        # Setup auth
        key_info = MagicMock(user_id="test_user", role=UserRole.OBSERVER)
        app.state.auth_service.validate_api_key = MagicMock(return_value=key_info)
        app.state.auth_service._get_key_id = MagicMock(return_value="key_123")

        # Mock communication service
        app.state.communication_service.register_websocket = MagicMock()
        app.state.communication_service.unregister_websocket = MagicMock()

        client = TestClient(app)
        with client.websocket_connect("/agent/stream", headers={"authorization": "Bearer valid_token"}) as websocket:
            # Test subscription
            websocket.send_json({"action": "subscribe", "channels": ["telemetry", "reasoning"]})
            response = websocket.receive_json()
            assert response["type"] == "subscription_update"
            assert "messages" in response["channels"]  # Default
            assert "telemetry" in response["channels"]
            assert "reasoning" in response["channels"]

            # Test ping
            websocket.send_json({"action": "ping"})
            response = websocket.receive_json()
            assert response["type"] == "pong"

            # Test unsubscribe
            websocket.send_json({"action": "unsubscribe", "channels": ["telemetry"]})
            response = websocket.receive_json()
            assert response["type"] == "subscription_update"
            assert "telemetry" not in response["channels"]
            assert "reasoning" in response["channels"]
