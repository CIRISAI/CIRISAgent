"""
Comprehensive tests for API key management endpoints.

This test file covers:
- POST /v1/auth/api-keys - Create API keys
- GET /v1/auth/api-keys - List user API keys
- DELETE /v1/auth/api-keys/{key_id} - Revoke API keys

Tests cover both success paths and error handling.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import HTTPException, status

from ciris_engine.logic.adapters.api.routes.auth import create_api_key, delete_api_key, list_api_keys
from ciris_engine.schemas.api.auth import APIKey, APIKeyCreateRequest, AuthContext, UserRole


class TestCreateAPIKey:
    """Test POST /v1/auth/api-keys endpoint."""

    @pytest.fixture
    def mock_auth_context(self):
        """Create mock auth context for a regular user."""
        auth = Mock(spec=AuthContext)
        auth.user_id = "user-123"
        auth.role = UserRole.OBSERVER
        return auth

    @pytest.fixture
    def mock_admin_auth_context(self):
        """Create mock auth context for an admin user."""
        auth = Mock(spec=AuthContext)
        auth.user_id = "admin-456"
        auth.role = UserRole.ADMIN
        return auth

    @pytest.fixture
    def mock_auth_service(self):
        """Create mock auth service."""
        service = Mock()
        service.store_api_key = Mock()
        return service

    @pytest.mark.asyncio
    async def test_create_api_key_minimum_expiry(self, mock_auth_context, mock_auth_service):
        """Test creating API key with minimum expiry (30 minutes)."""
        request = APIKeyCreateRequest(
            description="Test key",
            expires_in_minutes=30,
        )

        response = await create_api_key(request, mock_auth_context, mock_auth_service)

        # Verify API key format matches user role
        assert response.api_key.startswith("ciris_observer_")
        assert response.role == UserRole.OBSERVER
        assert response.description == "Test key"
        assert response.created_by == "user-123"

        # Verify expiry is approximately 30 minutes from now
        expected_expiry = datetime.now(timezone.utc) + timedelta(minutes=30)
        assert abs((response.expires_at - expected_expiry).total_seconds()) < 5

        # Verify store_api_key was called correctly
        mock_auth_service.store_api_key.assert_called_once()
        call_kwargs = mock_auth_service.store_api_key.call_args[1]
        assert call_kwargs["user_id"] == "user-123"
        assert call_kwargs["role"] == UserRole.OBSERVER
        assert call_kwargs["description"] == "Test key"
        assert call_kwargs["created_by"] == "user-123"

    @pytest.mark.asyncio
    async def test_create_api_key_maximum_expiry(self, mock_auth_context, mock_auth_service):
        """Test creating API key with maximum expiry (7 days / 10080 minutes)."""
        request = APIKeyCreateRequest(
            description="Long-lived key",
            expires_in_minutes=10080,  # 7 days
        )

        response = await create_api_key(request, mock_auth_context, mock_auth_service)

        # Verify expiry is approximately 7 days from now
        expected_expiry = datetime.now(timezone.utc) + timedelta(minutes=10080)
        assert abs((response.expires_at - expected_expiry).total_seconds()) < 5

    @pytest.mark.asyncio
    async def test_create_api_key_custom_expiry(self, mock_auth_context, mock_auth_service):
        """Test creating API key with custom expiry (1 day)."""
        request = APIKeyCreateRequest(
            description="Daily key",
            expires_in_minutes=1440,  # 1 day
        )

        response = await create_api_key(request, mock_auth_context, mock_auth_service)

        # Verify expiry is approximately 1 day from now
        expected_expiry = datetime.now(timezone.utc) + timedelta(minutes=1440)
        assert abs((response.expires_at - expected_expiry).total_seconds()) < 5

    @pytest.mark.asyncio
    async def test_create_api_key_without_description(self, mock_auth_context, mock_auth_service):
        """Test creating API key without description."""
        request = APIKeyCreateRequest(
            expires_in_minutes=60,
        )

        response = await create_api_key(request, mock_auth_context, mock_auth_service)

        assert response.description is None

    @pytest.mark.asyncio
    async def test_create_api_key_admin_role(self, mock_admin_auth_context, mock_auth_service):
        """Test creating API key for admin user - key should have admin role."""
        request = APIKeyCreateRequest(
            description="Admin key",
            expires_in_minutes=120,
        )

        response = await create_api_key(request, mock_admin_auth_context, mock_auth_service)

        # Verify API key format matches admin role
        assert response.api_key.startswith("ciris_admin_")
        assert response.role == UserRole.ADMIN

    @pytest.mark.asyncio
    async def test_create_api_key_validation_too_short(self):
        """Test that creating API key with expiry < 30 minutes fails validation."""
        with pytest.raises(Exception):  # Pydantic ValidationError
            APIKeyCreateRequest(
                description="Too short",
                expires_in_minutes=29,  # Below minimum
            )

    @pytest.mark.asyncio
    async def test_create_api_key_validation_too_long(self):
        """Test that creating API key with expiry > 7 days fails validation."""
        with pytest.raises(Exception):  # Pydantic ValidationError
            APIKeyCreateRequest(
                description="Too long",
                expires_in_minutes=10081,  # Above maximum (7 days)
            )


class TestListAPIKeys:
    """Test GET /v1/auth/api-keys endpoint."""

    @pytest.fixture
    def mock_auth_context(self):
        """Create mock auth context."""
        auth = Mock(spec=AuthContext)
        auth.user_id = "user-123"
        auth.role = UserRole.OBSERVER
        return auth

    @pytest.fixture
    def mock_auth_service_empty(self):
        """Create mock auth service with no keys."""
        service = Mock()
        service.list_user_api_keys = Mock(return_value=[])
        return service

    @pytest.fixture
    def mock_auth_service_with_keys(self):
        """Create mock auth service with multiple keys."""
        service = Mock()

        # Create mock API keys
        key1 = Mock(spec=APIKey)
        key1.key_id = "key-001"
        key1.role = UserRole.OBSERVER
        key1.expires_at = datetime.now(timezone.utc) + timedelta(days=1)
        key1.description = "First key"
        key1.created_at = datetime.now(timezone.utc) - timedelta(hours=1)
        key1.created_by = "user-123"
        key1.last_used = None
        key1.is_active = True

        key2 = Mock(spec=APIKey)
        key2.key_id = "key-002"
        key2.role = UserRole.OBSERVER
        key2.expires_at = datetime.now(timezone.utc) + timedelta(days=7)
        key2.description = "Second key"
        key2.created_at = datetime.now(timezone.utc) - timedelta(minutes=30)
        key2.created_by = "user-123"
        key2.last_used = datetime.now(timezone.utc) - timedelta(minutes=5)
        key2.is_active = True

        service.list_user_api_keys = Mock(return_value=[key1, key2])
        return service

    @pytest.mark.asyncio
    async def test_list_api_keys_empty(self, mock_auth_context, mock_auth_service_empty):
        """Test listing API keys when user has none."""
        response = await list_api_keys(mock_auth_context, mock_auth_service_empty)

        assert response.total == 0
        assert len(response.api_keys) == 0
        mock_auth_service_empty.list_user_api_keys.assert_called_once_with("user-123")

    @pytest.mark.asyncio
    async def test_list_api_keys_multiple(self, mock_auth_context, mock_auth_service_with_keys):
        """Test listing API keys when user has multiple."""
        response = await list_api_keys(mock_auth_context, mock_auth_service_with_keys)

        assert response.total == 2
        assert len(response.api_keys) == 2

        # Verify first key details
        key1 = response.api_keys[0]
        assert key1.key_id == "key-001"
        assert key1.role == UserRole.OBSERVER
        assert key1.description == "First key"
        assert key1.created_by == "user-123"
        assert key1.last_used is None
        assert key1.is_active is True

        # Verify second key details
        key2 = response.api_keys[1]
        assert key2.key_id == "key-002"
        assert key2.role == UserRole.OBSERVER
        assert key2.description == "Second key"
        assert key2.created_by == "user-123"
        assert key2.last_used is not None
        assert key2.is_active is True

    @pytest.mark.asyncio
    async def test_list_api_keys_only_users_keys(self, mock_auth_context, mock_auth_service_with_keys):
        """Test that list only returns the authenticated user's keys."""
        response = await list_api_keys(mock_auth_context, mock_auth_service_with_keys)

        # Verify all keys belong to the user
        for key in response.api_keys:
            assert key.created_by == "user-123"

        # Verify the service was called with the correct user ID
        mock_auth_service_with_keys.list_user_api_keys.assert_called_once_with("user-123")


class TestDeleteAPIKey:
    """Test DELETE /v1/auth/api-keys/{key_id} endpoint."""

    @pytest.fixture
    def mock_auth_context(self):
        """Create mock auth context."""
        auth = Mock(spec=AuthContext)
        auth.user_id = "user-123"
        auth.role = UserRole.OBSERVER
        return auth

    @pytest.fixture
    def mock_other_user_auth_context(self):
        """Create mock auth context for a different user."""
        auth = Mock(spec=AuthContext)
        auth.user_id = "other-user-456"
        auth.role = UserRole.OBSERVER
        return auth

    @pytest.fixture
    def mock_auth_service_with_key(self):
        """Create mock auth service with a key owned by user-123."""
        service = Mock()

        key = Mock(spec=APIKey)
        key.key_id = "key-to-delete"
        key.created_by = "user-123"
        key.role = UserRole.OBSERVER

        service.list_user_api_keys = Mock(return_value=[key])
        service.revoke_api_key = Mock()
        return service

    @pytest.fixture
    def mock_auth_service_empty(self):
        """Create mock auth service with no keys."""
        service = Mock()
        service.list_user_api_keys = Mock(return_value=[])
        service.revoke_api_key = Mock()
        return service

    @pytest.mark.asyncio
    async def test_delete_api_key_success(self, mock_auth_context, mock_auth_service_with_key):
        """Test successfully deleting own API key."""
        result = await delete_api_key("key-to-delete", mock_auth_context, mock_auth_service_with_key)

        # Verify key was revoked
        mock_auth_service_with_key.revoke_api_key.assert_called_once_with("key-to-delete")

        # Verify response is None (204 No Content)
        assert result is None

    @pytest.mark.asyncio
    async def test_delete_api_key_not_found(self, mock_auth_context, mock_auth_service_empty):
        """Test deleting non-existent API key returns 404."""
        with pytest.raises(HTTPException) as exc_info:
            await delete_api_key("non-existent-key", mock_auth_context, mock_auth_service_empty)

        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND
        assert exc_info.value.detail == "API key not found"

        # Verify revoke was NOT called
        mock_auth_service_empty.revoke_api_key.assert_not_called()

    @pytest.mark.asyncio
    async def test_delete_api_key_wrong_user(self, mock_other_user_auth_context, mock_auth_service_with_key):
        """Test that user cannot delete another user's API key."""
        # The key exists but belongs to user-123, not other-user-456
        # list_user_api_keys will return empty for other-user-456
        mock_auth_service_with_key.list_user_api_keys = Mock(return_value=[])

        with pytest.raises(HTTPException) as exc_info:
            await delete_api_key("key-to-delete", mock_other_user_auth_context, mock_auth_service_with_key)

        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND
        assert exc_info.value.detail == "API key not found"

        # Verify revoke was NOT called
        mock_auth_service_with_key.revoke_api_key.assert_not_called()

    @pytest.mark.asyncio
    async def test_delete_api_key_ownership_validation(self, mock_auth_context, mock_auth_service_with_key):
        """Test that ownership validation works correctly."""
        # This should succeed because the key belongs to user-123
        await delete_api_key("key-to-delete", mock_auth_context, mock_auth_service_with_key)

        # Verify list_user_api_keys was called to check ownership
        mock_auth_service_with_key.list_user_api_keys.assert_called_once_with("user-123")


class TestAPIKeyEndToEnd:
    """End-to-end tests for API key lifecycle."""

    @pytest.mark.asyncio
    async def test_create_list_delete_lifecycle(self):
        """Test complete API key lifecycle: create -> list -> delete."""
        # Setup
        auth_context = Mock(spec=AuthContext)
        auth_context.user_id = "user-123"
        auth_context.role = UserRole.ADMIN

        auth_service = Mock()
        auth_service.store_api_key = Mock()
        auth_service.list_user_api_keys = Mock()
        auth_service.revoke_api_key = Mock()

        # Step 1: Create API key
        create_request = APIKeyCreateRequest(
            description="Test lifecycle key",
            expires_in_minutes=60,
        )
        created_key = await create_api_key(create_request, auth_context, auth_service)

        assert created_key.api_key.startswith("ciris_admin_")
        assert created_key.description == "Test lifecycle key"

        # Step 2: Mock the key being stored and list it
        mock_stored_key = Mock(spec=APIKey)
        mock_stored_key.key_id = "lifecycle-key-id"
        mock_stored_key.role = UserRole.ADMIN
        mock_stored_key.description = "Test lifecycle key"
        mock_stored_key.created_by = "user-123"
        mock_stored_key.created_at = datetime.now(timezone.utc)
        mock_stored_key.expires_at = datetime.now(timezone.utc) + timedelta(minutes=60)
        mock_stored_key.last_used = None
        mock_stored_key.is_active = True

        auth_service.list_user_api_keys = Mock(return_value=[mock_stored_key])

        listed_keys = await list_api_keys(auth_context, auth_service)
        assert listed_keys.total == 1
        assert listed_keys.api_keys[0].key_id == "lifecycle-key-id"

        # Step 3: Delete the key
        result = await delete_api_key("lifecycle-key-id", auth_context, auth_service)
        assert result is None
        auth_service.revoke_api_key.assert_called_once_with("lifecycle-key-id")
