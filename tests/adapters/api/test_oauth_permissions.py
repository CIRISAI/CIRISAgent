"""
OAuth Permission System Tests

Tests the complete OAuth user permission workflow:
1. OAuth user creation
2. Permission requests
3. Admin permission grants
4. Access control enforcement
"""

import secrets
import sys

import pytest
import pytest_asyncio
from fastapi import status
from httpx import ASGITransport, AsyncClient

from ciris_engine.logic.adapters.api.app import create_app
from ciris_engine.logic.adapters.api.services.auth_service import UserRole
from ciris_engine.logic.runtime.ciris_runtime import CIRISRuntime
from ciris_engine.logic.runtime.prevent_sideeffects import allow_runtime_creation
from ciris_engine.schemas.config.essential import EssentialConfig

# Import the existing central mock fixture
from tests.conftest_config_mock import mock_runtime_db_setup


@pytest_asyncio.fixture
async def test_runtime(random_api_port, mock_runtime_db_setup):
    """Create a test runtime for OAuth testing."""
    # Allow runtime creation for this test
    allow_runtime_creation()

    try:
        config = EssentialConfig()
        config.services.llm_endpoint = "mock://localhost"
        config.services.llm_model = "mock"

        # Use the randomized API port to avoid conflicts
        import os

        os.environ["CIRIS_API_PORT"] = str(random_api_port)

        runtime = CIRISRuntime(
            adapter_types=["api"], essential_config=config, startup_channel_id="test_oauth", mock_llm=True
        )

        await runtime.initialize()
        yield runtime
        # Fast shutdown by skipping some cleanup
        try:
            await runtime.shutdown()
        except Exception as e:
            # Log but don't fail test if shutdown has issues
            print(f"Warning: Runtime shutdown error: {e}")
    finally:
        # Restore original state to avoid affecting other tests
        import os

        if os.environ.get("CIRIS_IMPORT_MODE") is None:
            os.environ["CIRIS_IMPORT_MODE"] = "true"


@pytest.fixture
def oauth_test_app(test_runtime):
    """Create test app with OAuth support."""
    app = create_app(test_runtime)

    # Set up a simple message handler that returns immediately
    # This prevents 503 errors when testing interaction endpoints
    async def mock_message_handler(msg):
        # Store the message for response correlation
        from ciris_engine.logic.adapters.api.routes.agent import store_message_response

        await store_message_response(msg.message_id, f"Mock response to: {msg.content}")

    app.state.on_message = mock_message_handler
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
async def oauth_user(oauth_test_app):
    """Create an OAuth user for testing."""
    # Get the auth service from the app state
    auth_service = oauth_test_app.state.auth_service

    external_id = f"google-user-{secrets.token_hex(8)}"
    email = f"testuser.{secrets.token_hex(4)}@gmail.com"
    name = "Test OAuth User"
    picture = "https://lh3.googleusercontent.com/a/ACg8ocKt3P4yBmK8sLB2uPCmpvR0N7V_ybpGmQ"

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

    async def test_oauth_user_denied_without_permission(self, oauth_client, oauth_user):
        """Test that OAuth users cannot interact without permission."""
        # Try to interact without permission
        response = await oauth_client.post(
            "/v1/agent/interact",
            headers={"Authorization": f"Bearer {oauth_user['api_key']}"},
            json={"message": "Hello", "channel_id": f"api_oauth_{oauth_user['user'].user_id}"},
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN
        detail = response.json()["detail"]
        assert detail["error"] == "insufficient_permissions"
        assert "permission" in detail["message"].lower()

    async def test_permission_request_creation(self, oauth_client, oauth_user, admin_token):
        """Test that permission requests are created when OAuth users try to interact."""
        # First interaction attempt creates permission request
        response = await oauth_client.post(
            "/v1/agent/interact",
            headers={"Authorization": f"Bearer {oauth_user['api_key']}"},
            json={"message": "Hello", "channel_id": f"api_oauth_{oauth_user['user'].user_id}"},
        )
        # Should get 403 forbidden
        assert response.status_code == status.HTTP_403_FORBIDDEN

        # Verify permission request was created by checking admin endpoint
        response = await oauth_client.get(
            "/v1/users/permission-requests", headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == status.HTTP_200_OK

        requests = response.json()
        found = False
        for req in requests:
            if req["id"] == oauth_user["user"].user_id:
                found = True
                assert req["email"] == oauth_user["email"]
                assert req["oauth_name"] == oauth_user["name"]
                assert req["permission_requested_at"] is not None
                assert req["has_send_messages"] is False
                break

        assert found, "Permission request not found in admin list"

    async def test_admin_view_permission_requests(self, oauth_client, admin_token, oauth_user):
        """Test that admins can view permission requests."""
        # Create permission request
        await oauth_client.post(
            "/v1/agent/interact",
            headers={"Authorization": f"Bearer {oauth_user['api_key']}"},
            json={"message": "Hello", "channel_id": f"api_oauth_{oauth_user['user'].user_id}"},
        )

        # Admin views permission requests
        response = await oauth_client.get(
            "/v1/users/permission-requests", headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == status.HTTP_200_OK

        # Response is a list, not a dict with items
        requests = response.json()
        found = False
        for req in requests:
            if req["id"] == oauth_user["user"].user_id:
                found = True
                assert req["email"] == oauth_user["email"]
                assert req["oauth_name"] == oauth_user["name"]
                assert req["role"] == "OBSERVER"
                assert req["permission_requested_at"] is not None
                assert req["has_send_messages"] is False
                break

        assert found, "Permission request not found"

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
