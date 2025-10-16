"""
OAuth Permission System Tests

Tests the complete OAuth user permission workflow using fast mocks:
1. OAuth user creation
2. Permission requests
3. Admin permission grants
4. Access control enforcement
"""

import secrets
import sys
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import status
from httpx import ASGITransport, AsyncClient

from ciris_engine.logic.adapters.api.services.auth_service import UserRole


@pytest.fixture
def oauth_test_app(app, mock_runtime):
    """Create test app with OAuth support and fast mocks."""

    # Set up a simple message handler that returns immediately
    async def mock_message_handler(msg):
        # Store the message for response correlation
        from ciris_engine.logic.adapters.api.routes.agent import store_message_response

        await store_message_response(msg.message_id, f"Mock response to: {msg.content}")

    app.state.on_message = mock_message_handler

    # Configure mock runtime to return proper state strings
    mock_runtime.state_manager = Mock()
    mock_runtime.state_manager.current_state = "WORK"  # String, not mock
    app.state.runtime = mock_runtime

    # Add additional state needed for OAuth tests
    app.state.consent_manager = AsyncMock()
    mock_consent = Mock()
    mock_consent.user_id = "test-user-123"
    mock_consent.stream = "TEMPORARY"
    app.state.consent_manager.get_consent.return_value = mock_consent
    app.state.consent_manager.grant_consent.return_value = mock_consent

    return app


@pytest.fixture
async def oauth_client(oauth_test_app):
    """Create async test client."""
    transport = ASGITransport(app=oauth_test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.fixture
async def admin_token(oauth_client):
    """Get admin authentication token."""
    response = await oauth_client.post("/v1/auth/login", json={"username": "admin", "password": "ciris_admin_password"})
    assert response.status_code == status.HTTP_200_OK
    return response.json()["access_token"]


@pytest.fixture
def oauth_user(oauth_test_app):
    """Create an OAuth user for testing."""
    # Get the auth service from the app state
    auth_service = oauth_test_app.state.auth_service

    external_id = f"google-user-{secrets.token_hex(8)}"
    email = f"testuser.{secrets.token_hex(4)}@gmail.com"
    name = "Test OAuth User"

    oauth_user = auth_service.create_oauth_user(
        provider="google", external_id=external_id, email=email, name=name, role=UserRole.OBSERVER
    )

    # Generate API key for the user
    api_key = f"ciris_observer_test_oauth_key_{secrets.token_hex(8)}"
    auth_service.store_api_key(
        key=api_key, user_id=oauth_user.user_id, role=oauth_user.role, description="OAuth login via google"
    )

    return {"user": oauth_user, "api_key": api_key, "email": email, "name": name}


@pytest.mark.skipif(
    sys.version_info >= (3, 12, 10),
    reason="Skipping due to Python 3.12.10+ ABC instantiation issue (TypeError: object.__new__() takes exactly one argument)",
)
class TestOAuthPermissions:
    """Test OAuth permission request and grant workflow."""

    async def test_oauth_user_creation(self, oauth_client, admin_token, oauth_user):
        """Test that OAuth users are created correctly."""
        # Check user appears in user list
        response = await oauth_client.get("/v1/users", headers={"Authorization": f"Bearer {admin_token}"})
        assert response.status_code == status.HTTP_200_OK

        users = response.json()["items"]
        oauth_user_found = False
        # Debug: print what we're looking for and what we got
        print(f"Looking for OAuth user with ID: {oauth_user['user'].user_id}")
        print(f"Found {len(users)} users in list")
        for user in users:
            print(f"  User: {user.get('user_id')} - {user.get('username')} - {user.get('auth_type')}")
            if user["user_id"] == oauth_user["user"].user_id:
                oauth_user_found = True
                assert user["oauth_provider"] == "google"
                assert user["oauth_email"] == oauth_user["email"]
                assert user["oauth_name"] == oauth_user["name"]
                # Note: picture field not currently supported in OAuthUser
                break

        assert oauth_user_found, "OAuth user not found in user list"

    async def test_oauth_user_can_interact_with_observer_role(self, oauth_client, oauth_user):
        """Test that OAuth users with OBSERVER role can interact (SEND_MESSAGES is now in OBSERVER role)."""
        # OBSERVER role now includes SEND_MESSAGES permission by default
        # Access control is handled by billing/credit system instead
        response = await oauth_client.post(
            "/v1/agent/interact",
            headers={"Authorization": f"Bearer {oauth_user['api_key']}"},
            json={"message": "Hello", "channel_id": f"api_oauth_{oauth_user['user'].user_id}"},
        )
        # Should succeed with 200, not 403
        assert response.status_code == status.HTTP_200_OK
        result = response.json()
        assert "data" in result

    async def test_observer_role_has_send_messages(self, oauth_client, oauth_user):
        """Test that OBSERVER role includes SEND_MESSAGES permission by default."""
        # Check that OAuth OBSERVER users have send_messages permission
        response = await oauth_client.get("/v1/auth/me", headers={"Authorization": f"Bearer {oauth_user['api_key']}"})
        assert response.status_code == status.HTTP_200_OK

        current = response.json()
        # OBSERVER role should include send_messages permission
        assert "send_messages" in current["permissions"]
        assert current["role"] == "OBSERVER"

    async def test_admin_can_view_user_permissions(self, oauth_client, admin_token, oauth_user):
        """Test that admins can view user permissions via user list."""
        # Admin views users to see OAuth user permissions
        response = await oauth_client.get("/v1/users", headers={"Authorization": f"Bearer {admin_token}"})
        assert response.status_code == status.HTTP_200_OK

        users = response.json()["items"]
        found = False
        for user in users:
            if user["user_id"] == oauth_user["user"].user_id:
                found = True
                assert user["api_role"] == "OBSERVER"  # Field is api_role not role
                assert user["oauth_provider"] == "google"
                assert user["oauth_email"] == oauth_user["email"]
                break

        assert found, "OAuth user not found in user list"

    async def test_admin_grant_permission(self, oauth_client, admin_token, oauth_user):
        """Test that admins can grant permissions to OAuth users."""
        # Create permission request
        await oauth_client.post(
            "/v1/agent/interact",
            headers={"Authorization": f"Bearer {oauth_user['api_key']}"},
            json={"message": "Hello", "channel_id": f"api_oauth_{oauth_user['user'].user_id}"},
        )

        # Admin grants send_messages permission
        response = await oauth_client.put(
            f"/v1/users/{oauth_user['user'].user_id}/permissions",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"permissions": ["send_messages"]},
        )
        assert response.status_code == status.HTTP_200_OK

        # Verify user details show the permission
        result = response.json()
        assert "send_messages" in result["custom_permissions"]

    async def test_oauth_user_can_interact_after_permission(self, oauth_client, admin_token, oauth_user):
        """Test that OAuth users can interact after permission is granted."""
        # Create permission request
        await oauth_client.post(
            "/v1/agent/interact",
            headers={"Authorization": f"Bearer {oauth_user['api_key']}"},
            json={"message": "Hello", "channel_id": f"api_oauth_{oauth_user['user'].user_id}"},
        )

        # Admin grants permission
        await oauth_client.put(
            f"/v1/users/{oauth_user['user'].user_id}/permissions",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"permissions": ["send_messages"]},
        )

        # Now user can interact successfully
        response = await oauth_client.post(
            "/v1/agent/interact",
            headers={"Authorization": f"Bearer {oauth_user['api_key']}"},
            json={"message": "Hello CIRIS", "channel_id": f"api_oauth_{oauth_user['user'].user_id}"},
        )
        assert response.status_code == status.HTTP_200_OK
        result = response.json()
        # Response should have data with the message response
        assert "data" in result
        assert "response" in result["data"]
        assert "message_id" in result["data"]

    async def test_oauth_permission_persistence(self, oauth_client, admin_token, oauth_user):
        """Test that permissions persist across sessions."""
        # Grant permission
        await oauth_client.post(
            "/v1/agent/interact",
            headers={"Authorization": f"Bearer {oauth_user['api_key']}"},
            json={"message": "Hello", "channel_id": f"api_oauth_{oauth_user['user'].user_id}"},
        )

        await oauth_client.put(
            f"/v1/users/{oauth_user['user'].user_id}/permissions",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"permissions": ["send_messages"]},
        )

        # Check current user shows granted permission
        response = await oauth_client.get("/v1/auth/me", headers={"Authorization": f"Bearer {oauth_user['api_key']}"})
        assert response.status_code == status.HTTP_200_OK

        current = response.json()
        # The /auth/me endpoint returns permissions list
        assert "send_messages" in current["permissions"]
