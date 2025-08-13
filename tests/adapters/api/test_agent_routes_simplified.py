"""
Simplified comprehensive tests for agent API routes.

Targets 100% coverage for ciris_engine/logic/adapters/api/routes/agent.py
"""

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient

from ciris_engine.logic.adapters.api.dependencies.auth import AuthContext, require_observer
from ciris_engine.logic.adapters.api.routes import agent
from ciris_engine.logic.adapters.api.routes.agent import (
    _calculate_uptime,
    _convert_to_channel_info,
    _count_active_services,
    _count_wakeup_tasks,
    _get_agent_identity_info,
    _get_cognitive_state,
    notify_interact_response,
    router,
    store_message_response,
)
from ciris_engine.logic.adapters.api.services.auth_service import APIAuthService
from ciris_engine.schemas.api.auth import Permission, UserRole
from ciris_engine.schemas.runtime.messages import IncomingMessage


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
    auth_service._get_key_id = MagicMock(return_value="test_key")

    # Set up app state
    app.state.auth_service = auth_service
    app.state.memory_service = AsyncMock()
    app.state.communication_service = AsyncMock()
    app.state.tool_service = AsyncMock()
    app.state.time_service = AsyncMock()
    app.state.task_scheduler = AsyncMock()
    app.state.task_scheduler.get_current_task = AsyncMock(return_value=None)  # Return None by default
    app.state.resource_monitor = AsyncMock()
    app.state.service_registry = MagicMock()  # Use MagicMock since get_services_by_type is called synchronously
    app.state.service_registry.get_services_by_type = MagicMock(return_value=[])  # Return empty list by default
    app.state.runtime = AsyncMock()
    app.state.on_message = AsyncMock()
    app.state.api_config = MagicMock(interaction_timeout=5.0)
    app.state.api_host = "127.0.0.1"
    app.state.api_port = "8080"

    # Mock runtime properties
    app.state.runtime.state_manager = MagicMock(current_state="WORK")

    # Create a more complete mock for agent identity
    identity_mock = MagicMock()
    identity_mock.agent_id = "test_agent"
    identity_mock.name = "Test Agent"  # Fix: Added space to match expected value
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


class TestCoreEndpoints:
    """Test the main agent endpoints."""

    @pytest.mark.asyncio
    async def test_interact_success(self, app, auth_context_admin):
        """Test successful interaction."""

        async def mock_on_message(msg: IncomingMessage):
            await asyncio.sleep(0.05)
            await store_message_response(msg.message_id, "Hello! How can I help you?")

        app.state.on_message = mock_on_message
        app.dependency_overrides[require_observer] = lambda: auth_context_admin

        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post(
                    "/agent/interact", json={"message": "Hello"}, headers={"Authorization": "Bearer test_token"}
                )

            assert response.status_code == 200
            data = response.json()
            assert data["data"]["response"] == "Hello! How can I help you?"
            assert data["data"]["state"] == "WORK"
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_interact_timeout(self, app, auth_context_admin):
        """Test interaction timeout."""
        app.state.api_config.interaction_timeout = 0.1
        app.state.on_message = AsyncMock()  # Don't send response
        app.dependency_overrides[require_observer] = lambda: auth_context_admin

        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post(
                    "/agent/interact", json={"message": "Hello"}, headers={"Authorization": "Bearer test_token"}
                )

            assert response.status_code == 200
            data = response.json()
            assert "Still processing" in data["data"]["response"]
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_interact_permission_denied(self, app, auth_context_observer):
        """Test interaction without SEND_MESSAGES permission."""
        app.dependency_overrides[require_observer] = lambda: auth_context_observer

        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post(
                    "/agent/interact", json={"message": "Hello"}, headers={"Authorization": "Bearer test_token"}
                )

            assert response.status_code == 403
            data = response.json()
            assert "insufficient_permissions" in data["detail"]["error"]
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_status(self, app, auth_context_observer):
        """Test status endpoint."""
        app.dependency_overrides[require_observer] = lambda: auth_context_observer

        # Mock the task scheduler's get_current_task
        app.state.task_scheduler.get_current_task = AsyncMock(return_value=None)

        with patch("ciris_engine.logic.adapters.api.routes.agent._count_wakeup_tasks", return_value=5):
            with patch("ciris_engine.logic.adapters.api.routes.agent._count_active_services", return_value=(21, {})):
                try:
                    transport = ASGITransport(app=app)
                    async with AsyncClient(transport=transport, base_url="http://test") as client:
                        response = await client.get("/agent/status", headers={"Authorization": "Bearer test_token"})

                    if response.status_code != 200:
                        print(f"Status error: {response.json()}")
                    assert response.status_code == 200
                    data = response.json()
                    assert data["data"]["agent_id"] == "test_agent"
                    assert data["data"]["cognitive_state"] == "WORK"
                    assert data["data"]["uptime_seconds"] == 3600.0
                finally:
                    app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_identity(self, app, auth_context_observer):
        """Test identity endpoint."""
        app.state.memory_service.recall = AsyncMock(return_value=[])
        # Keep tool_service as AsyncMock since list_tools is awaited
        app.state.tool_service.list_tools = AsyncMock(return_value=["tool1", "tool2"])
        app.dependency_overrides[require_observer] = lambda: auth_context_observer

        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.get("/agent/identity", headers={"Authorization": "Bearer test_token"})

            if response.status_code != 200:
                print(f"Identity error: {response.json()}")
            assert response.status_code == 200
            data = response.json()
            assert data["data"]["agent_id"] == "test_agent"
            assert len(data["data"]["tools"]) == 2
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_history(self, app, auth_context_admin):
        """Test history endpoint."""
        app.state.message_history = [
            {
                "message_id": "msg1",
                "author_id": "admin_user",
                "content": "Hello",
                "channel_id": "api_admin_user",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "response": "Hi there!",
            }
        ]
        app.dependency_overrides[require_observer] = lambda: auth_context_admin

        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.get("/agent/history", headers={"Authorization": "Bearer test_token"})

            assert response.status_code == 200
            data = response.json()
            assert len(data["data"]["messages"]) == 2  # User + agent messages
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_channels(self, app, auth_context_observer):
        """Test channels endpoint."""
        app.dependency_overrides[require_observer] = lambda: auth_context_observer

        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.get("/agent/channels", headers={"Authorization": "Bearer test_token"})

            assert response.status_code == 200
            data = response.json()
            assert len(data["data"]["channels"]) >= 2  # At least default API channels
        finally:
            app.dependency_overrides.clear()


class TestHelperFunctions:
    """Test helper functions for coverage."""

    @pytest.mark.asyncio
    async def test_store_message_response(self):
        """Test message response storage."""
        agent._message_responses.clear()
        agent._response_events.clear()

        event = asyncio.Event()
        agent._response_events["test_id"] = event

        await store_message_response("test_id", "Test response")

        assert agent._message_responses["test_id"] == "Test response"
        assert event.is_set()

    @pytest.mark.asyncio
    async def test_notify_interact_response(self):
        """Test response notification."""
        agent._message_responses.clear()
        agent._response_events.clear()

        event = asyncio.Event()
        agent._response_events["msg123"] = event

        await notify_interact_response("msg123", "Content")

        assert agent._message_responses["msg123"] == "Content"
        assert event.is_set()

    def test_get_cognitive_state(self):
        """Test cognitive state helper."""
        runtime = MagicMock()
        runtime.state_manager = MagicMock(current_state="DREAM")
        assert _get_cognitive_state(runtime) == "DREAM"

        runtime = MagicMock(spec=[])
        assert _get_cognitive_state(runtime) == "WORK"

    def test_calculate_uptime(self):
        """Test uptime calculation."""
        assert _calculate_uptime(None) == 0.0

        time_service = MagicMock()
        time_service.get_status = MagicMock(return_value=MagicMock(uptime_seconds=1234.5))
        assert _calculate_uptime(time_service) == 1234.5

    def test_count_wakeup_tasks(self):
        """Test wakeup task counting."""
        import ciris_engine.logic.persistence as persistence_module

        with patch.object(persistence_module, "get_tasks_by_status") as mock_get_tasks:
            from ciris_engine.schemas.runtime.enums import TaskStatus

            mock_tasks = [
                MagicMock(task_id="VERIFY_IDENTITY_123"),
                MagicMock(task_id="VALIDATE_INTEGRITY_456"),
            ]
            mock_get_tasks.return_value = mock_tasks

            count = _count_wakeup_tasks(100.0)
            assert count == 2

    def test_count_active_services(self):
        """Test service counting."""
        service_registry = MagicMock()

        from ciris_engine.schemas.runtime.enums import ServiceType

        def mock_get_services(service_type):
            if service_type == ServiceType.LLM:
                return ["provider1", "provider2"]
            return []

        service_registry.get_services_by_type = MagicMock(side_effect=mock_get_services)

        count, multi_provider = _count_active_services(service_registry)
        assert count >= 12
        # Check for either uppercase or lowercase
        assert "LLM" in multi_provider or "llm" in multi_provider

    def test_get_agent_identity_info(self):
        """Test identity info extraction."""
        runtime = MagicMock()
        identity = MagicMock()
        identity.agent_id = "custom_agent"
        identity.name = "Custom Agent"  # Explicitly set as string
        runtime.agent_identity = identity
        agent_id, name = _get_agent_identity_info(runtime)
        assert agent_id == "custom_agent"
        assert name == "Custom Agent"

    def test_convert_to_channel_info(self):
        """Test channel info conversion."""
        channel = MagicMock(
            channel_id="test_channel",
            channel_type="discord",
            display_name="Test",
            is_active=True,
            message_count=10,
        )
        info = _convert_to_channel_info(channel, "discord")
        assert info.channel_id == "test_channel"
        assert info.message_count == 10


class TestEdgeCases:
    """Test edge cases and error handling."""

    @pytest.mark.asyncio
    async def test_interact_no_handler(self, app, auth_context_admin):
        """Test when message handler is not configured."""
        delattr(app.state, "on_message")
        app.dependency_overrides[require_observer] = lambda: auth_context_admin

        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post(
                    "/agent/interact", json={"message": "Hello"}, headers={"Authorization": "Bearer test_token"}
                )

            assert response.status_code == 503
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_status_no_runtime(self, app, auth_context_observer):
        """Test status when runtime is not available."""
        app.state.runtime = None
        app.dependency_overrides[require_observer] = lambda: auth_context_observer

        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.get("/agent/status", headers={"Authorization": "Bearer test_token"})

            assert response.status_code == 503
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_identity_no_memory_service(self, app, auth_context_observer):
        """Test identity when memory service is not available."""
        app.state.memory_service = None
        app.dependency_overrides[require_observer] = lambda: auth_context_observer

        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.get("/agent/identity", headers={"Authorization": "Bearer test_token"})

            assert response.status_code == 503
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_history_from_memory_fallback(self, app, auth_context_admin):
        """Test history fallback to memory service."""
        app.state.communication_service = None
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
        app.dependency_overrides[require_observer] = lambda: auth_context_admin

        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.get("/agent/history", headers={"Authorization": "Bearer test_token"})

            assert response.status_code == 200
            data = response.json()
            assert data["data"]["messages"][0]["content"] == "Memory message"
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_interact_oauth_permission_request(self, app, auth_context_observer):
        """Test automatic permission request for OAuth users."""
        oauth_user = MagicMock(wa_id="oauth_user", auth_type="oauth", permission_requested_at=None)
        app.state.auth_service.get_user = MagicMock(return_value=oauth_user)
        app.state.auth_service._users = {"oauth_user": oauth_user}
        app.dependency_overrides[require_observer] = lambda: auth_context_observer

        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post(
                    "/agent/interact", json={"message": "Hello"}, headers={"Authorization": "Bearer test_token"}
                )

            assert response.status_code == 403
            assert oauth_user.permission_requested_at is not None
        finally:
            app.dependency_overrides.clear()
