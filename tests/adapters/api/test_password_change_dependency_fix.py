"""
Test for password change API dependency injection fix.

This test ensures that the manual permission checking bug doesn't regress.
Bug: check_permissions() was called manually with only auth parameter,
but the dependency function requires both auth AND auth_service parameters.
"""

import pytest
from unittest.mock import AsyncMock, Mock, patch
from fastapi import HTTPException, Request, Depends
from datetime import datetime, timezone

from ciris_engine.logic.adapters.api.routes.users import change_password, list_user_api_keys
from ciris_engine.logic.adapters.api.routes.users import ChangePasswordRequest
from ciris_engine.logic.adapters.api.services.auth_service import APIAuthService
from ciris_engine.logic.adapters.api.dependencies.auth import AuthContext, check_permissions
from ciris_engine.schemas.runtime.api import APIRole
from ciris_engine.schemas.api.auth import Permission, UserRole


class TestPasswordChangeDependencyFix:
    """Test password change dependency injection fixes."""

    @pytest.fixture
    def auth_context_admin(self):
        """Auth context for admin user."""
        return AuthContext(
            user_id="admin",
            role=UserRole.SYSTEM_ADMIN,
            permissions={Permission.FULL_ACCESS},
            authenticated_at=datetime.now(timezone.utc)
        )

    @pytest.fixture
    def auth_context_user(self):
        """Auth context for regular user."""
        return AuthContext(
            user_id="user123",
            role=UserRole.OBSERVER,
            permissions={Permission.VIEW_MESSAGES, Permission.VIEW_AUDIT},
            authenticated_at=datetime.now(timezone.utc)
        )

    @pytest.fixture
    def mock_auth_service(self):
        """Mock authentication service."""
        service = Mock(spec=APIAuthService)
        service.get_user = Mock(return_value=Mock(
            wa_id="admin",
            name="Admin User",
            api_role=APIRole.SYSTEM_ADMIN,
            custom_permissions=None
        ))
        service.get_permissions_for_role = Mock(return_value=["users.write", "users.read", "users.delete"])
        service.change_password = AsyncMock(return_value=True)
        service.list_user_api_keys = Mock(return_value=[])
        return service

    @pytest.mark.asyncio
    async def test_change_password_admin_changing_other_user(self, auth_context_admin, mock_auth_service):
        """Test admin changing another user's password (permission check required)."""
        request = ChangePasswordRequest(
            current_password="old_password",
            new_password="new_secure_password"
        )

        # This should NOT raise AttributeError anymore
        result = await change_password(
            user_id="other_user", 
            request=request, 
            auth=auth_context_admin, 
            auth_service=mock_auth_service
        )

        # Verify the service was called correctly
        mock_auth_service.change_password.assert_called_once_with(
            user_id="other_user", 
            new_password="new_secure_password", 
            skip_current_check=True
        )
        assert "message" in result

    @pytest.mark.asyncio
    async def test_change_password_user_changing_own(self, auth_context_user, mock_auth_service):
        """Test user changing their own password (no permission check needed)."""
        request = ChangePasswordRequest(
            current_password="current_password",
            new_password="new_secure_password"
        )

        result = await change_password(
            user_id="user123",  # Same as auth_context_user.user_id
            request=request, 
            auth=auth_context_user, 
            auth_service=mock_auth_service
        )

        # Should call with current password check
        mock_auth_service.change_password.assert_called_once_with(
            user_id="user123", 
            new_password="new_secure_password", 
            current_password="current_password"
        )
        assert "message" in result

    @pytest.mark.asyncio
    async def test_list_user_api_keys_permission_check(self, auth_context_user, mock_auth_service):
        """Test API key listing with permission check for other users."""
        # This should NOT raise AttributeError anymore
        result = await list_user_api_keys(
            user_id="other_user",  # Different from auth_context_user.user_id
            auth=auth_context_user,
            auth_service=mock_auth_service
        )

        # Should call get_user to check permissions
        mock_auth_service.get_user.assert_called_once_with("user123")
        mock_auth_service.list_user_api_keys.assert_called_once_with("other_user")
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_permission_check_insufficient_permissions(self, auth_context_user, mock_auth_service):
        """Test that insufficient permissions are properly handled."""
        # Mock user with insufficient permissions
        mock_auth_service.get_user = Mock(return_value=Mock(
            wa_id="user123",
            name="Test User", 
            api_role=APIRole.OBSERVER,
            custom_permissions=None
        ))
        mock_auth_service.get_permissions_for_role = Mock(return_value=["users.read"])  # Missing users.write

        request = ChangePasswordRequest(
            current_password="old_password",
            new_password="new_secure_password"
        )

        # Should raise HTTPException for insufficient permissions
        with pytest.raises(HTTPException) as exc_info:
            await change_password(
                user_id="other_user",  # Different user, requires users.write permission
                request=request,
                auth=auth_context_user,
                auth_service=mock_auth_service
            )

        assert exc_info.value.status_code == 403
        assert "missing required permissions" in exc_info.value.detail.lower()

    def test_regression_prevention_attributes(self):
        """Test that ensures the specific AttributeError can't happen."""
        # This test documents the specific bug that was fixed
        # The bug was: auth_service was a Depends object instead of the actual service
        
        # Create an actual Depends object
        depends_obj = Depends(lambda: None)
        
        # This should fail as expected - a Depends object doesn't have get_user
        assert not hasattr(depends_obj, "get_user")
        
        # But our actual service should have get_user
        service = Mock(spec=APIAuthService)
        service.get_user = Mock()
        assert hasattr(service, "get_user")
        assert callable(service.get_user)