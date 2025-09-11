"""
Comprehensive test suite for refactored authentication dependencies.

Tests coverage for the newly extracted helper methods that reduce cognitive complexity:
- _extract_bearer_token
- _handle_service_token_auth
- _handle_password_auth
- _build_permissions_set
- _handle_api_key_auth
- get_auth_context (main function)

These tests ensure robust coverage of all authentication paths and edge cases.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException, Request

from ciris_engine.logic.adapters.api.dependencies.auth import (
    _build_permissions_set,
    _extract_bearer_token,
    _handle_api_key_auth,
    _handle_password_auth,
    _handle_service_token_auth,
    get_auth_context,
)
from ciris_engine.schemas.api.auth import AuthContext, Permission, UserRole


class TestExtractBearerToken:
    """Test _extract_bearer_token helper method."""

    def test_extract_bearer_token_success(self):
        """Test successful bearer token extraction."""
        authorization = "Bearer abc123token"
        token = _extract_bearer_token(authorization)
        assert token == "abc123token"

    def test_extract_bearer_token_missing_header(self):
        """Test handling of missing authorization header."""
        with pytest.raises(HTTPException) as exc_info:
            _extract_bearer_token(None)
        
        assert exc_info.value.status_code == 401
        assert "Missing authorization header" in exc_info.value.detail
        assert exc_info.value.headers == {"WWW-Authenticate": "Bearer"}

    def test_extract_bearer_token_empty_header(self):
        """Test handling of empty authorization header."""
        with pytest.raises(HTTPException) as exc_info:
            _extract_bearer_token("")
        
        assert exc_info.value.status_code == 401
        assert "Missing authorization header" in exc_info.value.detail

    def test_extract_bearer_token_invalid_format(self):
        """Test handling of invalid authorization format."""
        with pytest.raises(HTTPException) as exc_info:
            _extract_bearer_token("Basic abc123token")
        
        assert exc_info.value.status_code == 401
        assert "Invalid authorization format" in exc_info.value.detail
        assert exc_info.value.headers == {"WWW-Authenticate": "Bearer"}

    def test_extract_bearer_token_no_space(self):
        """Test handling of bearer format without space."""
        with pytest.raises(HTTPException) as exc_info:
            _extract_bearer_token("Bearerabc123token")
        
        assert exc_info.value.status_code == 401
        assert "Invalid authorization format" in exc_info.value.detail

    def test_extract_bearer_token_case_sensitive(self):
        """Test that bearer token extraction is case sensitive."""
        with pytest.raises(HTTPException):
            _extract_bearer_token("bearer abc123token")  # lowercase 'bearer'


class TestHandleServiceTokenAuth:
    """Test _handle_service_token_auth helper method."""

    def test_handle_service_token_auth_success(self):
        """Test successful service token authentication."""
        mock_request = Mock(spec=Request)
        mock_auth_service = Mock()
        mock_service_user = Mock()
        mock_service_user.wa_id = "service-user-123"
        
        mock_auth_service.validate_service_token.return_value = mock_service_user
        
        context = _handle_service_token_auth(mock_request, mock_auth_service, "valid-service-token")
        
        assert isinstance(context, AuthContext)
        assert context.user_id == "service-user-123"
        assert context.role == UserRole.SERVICE_ACCOUNT
        assert context.request == mock_request
        assert context.api_key_id is None

    def test_handle_service_token_auth_invalid_token(self):
        """Test handling of invalid service token."""
        mock_request = Mock(spec=Request)
        mock_auth_service = Mock()
        mock_auth_service.validate_service_token.return_value = None
        
        with pytest.raises(HTTPException) as exc_info:
            _handle_service_token_auth(mock_request, mock_auth_service, "invalid-token")
        
        assert exc_info.value.status_code == 401
        assert "Invalid service token" in exc_info.value.detail


class TestHandlePasswordAuth:
    """Test _handle_password_auth helper method."""

    @pytest.mark.asyncio
    async def test_handle_password_auth_success(self):
        """Test successful password authentication."""
        mock_request = Mock(spec=Request)
        mock_auth_service = Mock()
        mock_user = Mock()
        mock_user.wa_id = "user-123"
        mock_user.api_role = Mock()
        mock_user.api_role.value = "ADMIN"
        
        mock_auth_service.verify_user_password = AsyncMock(return_value=mock_user)
        
        context = await _handle_password_auth(mock_request, mock_auth_service, "username:password")
        
        assert isinstance(context, AuthContext)
        assert context.user_id == "user-123"
        assert context.role == UserRole.ADMIN
        assert context.request == mock_request
        assert context.api_key_id is None

    @pytest.mark.asyncio
    async def test_handle_password_auth_invalid_credentials(self):
        """Test handling of invalid username/password."""
        mock_request = Mock(spec=Request)
        mock_auth_service = Mock()
        mock_auth_service.verify_user_password = AsyncMock(return_value=None)
        
        with pytest.raises(HTTPException) as exc_info:
            await _handle_password_auth(mock_request, mock_auth_service, "username:wrong_password")
        
        assert exc_info.value.status_code == 401
        assert "Invalid username or password" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_handle_password_auth_malformed(self):
        """Test handling of malformed password format."""
        mock_request = Mock(spec=Request)
        mock_auth_service = Mock()
        
        # This would raise an exception when trying to split
        with pytest.raises(ValueError):
            await _handle_password_auth(mock_request, mock_auth_service, "no_colon_here")


class TestBuildPermissionsSet:
    """Test _build_permissions_set helper method."""

    def test_build_permissions_set_role_only(self):
        """Test building permissions from role only."""
        mock_key_info = Mock()
        mock_key_info.role = UserRole.ADMIN
        
        permissions = _build_permissions_set(mock_key_info, None)
        
        # Should have role-based permissions
        assert isinstance(permissions, set)
        # Admin role should have permissions
        assert len(permissions) > 0

    def test_build_permissions_set_with_custom_permissions(self):
        """Test building permissions with custom user permissions."""
        mock_key_info = Mock()
        mock_key_info.role = UserRole.OBSERVER
        
        mock_user = Mock()
        mock_user.custom_permissions = ["send_messages", "view_logs"]  # Use enum values, not names
        
        permissions = _build_permissions_set(mock_key_info, mock_user)
        
        assert isinstance(permissions, set)
        # Should include custom permissions if they're valid
        # Note: OBSERVER role doesn't have SEND_MESSAGES by default, but custom permissions can add it
        assert Permission.SEND_MESSAGES in permissions

    def test_build_permissions_set_invalid_custom_permissions(self):
        """Test handling of invalid custom permissions."""
        mock_key_info = Mock()
        mock_key_info.role = UserRole.OBSERVER
        
        mock_user = Mock()
        mock_user.custom_permissions = ["INVALID_PERMISSION", "ANOTHER_INVALID"]
        
        permissions = _build_permissions_set(mock_key_info, mock_user)
        
        assert isinstance(permissions, set)
        # Should only have role-based permissions, invalid ones skipped

    def test_build_permissions_set_no_custom_permissions(self):
        """Test building permissions when user has no custom permissions."""
        mock_key_info = Mock()
        mock_key_info.role = UserRole.ADMIN
        
        mock_user = Mock()
        mock_user.custom_permissions = None
        
        permissions = _build_permissions_set(mock_key_info, mock_user)
        
        assert isinstance(permissions, set)


class TestHandleApiKeyAuth:
    """Test _handle_api_key_auth helper method."""

    def test_handle_api_key_auth_success(self):
        """Test successful API key authentication."""
        mock_request = Mock(spec=Request)
        mock_auth_service = Mock()
        mock_key_info = Mock()
        mock_key_info.user_id = "user-123"
        mock_key_info.role = UserRole.ADMIN
        mock_user = Mock()
        mock_user.custom_permissions = []  # Fix: Make it iterable
        
        mock_auth_service.validate_api_key.return_value = mock_key_info
        mock_auth_service.get_user.return_value = mock_user
        mock_auth_service._get_key_id.return_value = "key-id-123"
        
        context = _handle_api_key_auth(mock_request, mock_auth_service, "valid-api-key")
        
        assert isinstance(context, AuthContext)
        assert context.user_id == "user-123"
        assert context.role == UserRole.ADMIN
        assert context.request == mock_request
        assert context.api_key_id == "key-id-123"

    def test_handle_api_key_auth_invalid_key(self):
        """Test handling of invalid API key."""
        mock_request = Mock(spec=Request)
        mock_auth_service = Mock()
        mock_auth_service.validate_api_key.return_value = None
        
        with pytest.raises(HTTPException) as exc_info:
            _handle_api_key_auth(mock_request, mock_auth_service, "invalid-api-key")
        
        assert exc_info.value.status_code == 401
        assert "Invalid API key" in exc_info.value.detail


class TestGetAuthContextIntegration:
    """Test the refactored get_auth_context main function."""

    @pytest.mark.asyncio
    async def test_get_auth_context_service_token_flow(self):
        """Test complete service token authentication flow."""
        mock_request = Mock(spec=Request)
        mock_auth_service = Mock()
        mock_service_user = Mock()
        mock_service_user.wa_id = "service-123"
        
        mock_auth_service.validate_service_token.return_value = mock_service_user
        
        context = await get_auth_context(mock_request, "Bearer service:valid-token", mock_auth_service)
        
        assert isinstance(context, AuthContext)
        assert context.user_id == "service-123"
        assert context.role == UserRole.SERVICE_ACCOUNT

    @pytest.mark.asyncio
    async def test_get_auth_context_password_flow(self):
        """Test complete username:password authentication flow."""
        mock_request = Mock(spec=Request)
        mock_auth_service = Mock()
        mock_user = Mock()
        mock_user.wa_id = "user-123"
        mock_user.api_role = Mock()
        mock_user.api_role.value = "ADMIN"
        
        mock_auth_service.verify_user_password = AsyncMock(return_value=mock_user)
        
        context = await get_auth_context(mock_request, "Bearer username:password", mock_auth_service)
        
        assert isinstance(context, AuthContext)
        assert context.user_id == "user-123"
        assert context.role == UserRole.ADMIN

    @pytest.mark.asyncio
    async def test_get_auth_context_api_key_flow(self):
        """Test complete API key authentication flow."""
        mock_request = Mock(spec=Request)
        mock_auth_service = Mock()
        mock_key_info = Mock()
        mock_key_info.user_id = "user-123"
        mock_key_info.role = UserRole.OBSERVER
        mock_user = Mock()
        mock_user.custom_permissions = []  # Fix: Make it iterable
        
        mock_auth_service.validate_api_key.return_value = mock_key_info
        mock_auth_service.get_user.return_value = mock_user
        mock_auth_service._get_key_id.return_value = "key-123"
        
        context = await get_auth_context(mock_request, "Bearer api-key-123", mock_auth_service)
        
        assert isinstance(context, AuthContext)
        assert context.user_id == "user-123"
        assert context.role == UserRole.OBSERVER

    @pytest.mark.asyncio
    async def test_get_auth_context_missing_header(self):
        """Test handling of missing authorization header."""
        mock_request = Mock(spec=Request)
        mock_auth_service = Mock()
        
        with pytest.raises(HTTPException) as exc_info:
            await get_auth_context(mock_request, None, mock_auth_service)
        
        assert exc_info.value.status_code == 401
        assert "Missing authorization header" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_get_auth_context_invalid_format(self):
        """Test handling of invalid authorization format."""
        mock_request = Mock(spec=Request)
        mock_auth_service = Mock()
        
        with pytest.raises(HTTPException) as exc_info:
            await get_auth_context(mock_request, "Basic invalid", mock_auth_service)
        
        assert exc_info.value.status_code == 401
        assert "Invalid authorization format" in exc_info.value.detail


class TestAuthContextProperties:
    """Test AuthContext object properties and methods."""

    def test_auth_context_creation(self):
        """Test AuthContext creation with all properties."""
        permissions = {Permission.VIEW_MESSAGES}  # Use an actual permission
        auth_time = datetime.now(timezone.utc)
        
        context = AuthContext(
            user_id="user-123",
            role=UserRole.ADMIN,
            permissions=permissions,
            api_key_id="key-123",
            authenticated_at=auth_time,
        )
        
        assert context.user_id == "user-123"
        assert context.role == UserRole.ADMIN
        assert context.permissions == permissions
        assert context.api_key_id == "key-123"
        assert context.authenticated_at == auth_time

    def test_auth_context_has_permission(self):
        """Test AuthContext has_permission method."""
        permissions = {Permission.VIEW_MESSAGES}
        
        context = AuthContext(
            user_id="user-123",
            role=UserRole.ADMIN,
            permissions=permissions,
            api_key_id=None,
            authenticated_at=datetime.now(timezone.utc),
        )
        
        assert context.has_permission(Permission.VIEW_MESSAGES) is True
        # Test with permission not in set
        assert context.has_permission(Permission.SEND_MESSAGES) is False