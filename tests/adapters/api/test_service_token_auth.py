"""Test service token authentication for CD operations."""

import os
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException, Request

from ciris_engine.logic.adapters.api.dependencies.auth import get_auth_context
from ciris_engine.logic.adapters.api.services.auth_service import APIAuthService
from ciris_engine.schemas.api.auth import UserRole
from ciris_engine.schemas.runtime.api import APIRole


class TestServiceTokenAuthentication:
    """Test service token authentication."""

    @pytest.fixture
    def auth_service(self):
        """Create auth service instance."""
        return APIAuthService()

    @pytest.fixture
    def mock_request(self):
        """Create mock request."""
        request = MagicMock(spec=Request)
        request.app.state.auth_service = None
        return request

    def test_service_token_validation_success(self, auth_service):
        """Test successful service token validation."""
        # Set environment variable
        test_token = "test-service-token-123"
        with patch.dict(os.environ, {"CIRIS_SERVICE_TOKEN": test_token}):
            # Validate correct token
            user = auth_service.validate_service_token(test_token)

            assert user is not None
            assert user.wa_id == "service-account"
            assert user.name == "Service Account"
            assert user.auth_type == "service_token"
            assert user.api_role == APIRole.SERVICE_ACCOUNT
            assert user.is_active is True

    def test_service_token_validation_wrong_token(self, auth_service):
        """Test service token validation with wrong token."""
        # Set environment variable
        with patch.dict(os.environ, {"CIRIS_SERVICE_TOKEN": "correct-token"}):
            # Try wrong token
            user = auth_service.validate_service_token("wrong-token")
            assert user is None

    def test_service_token_validation_no_env_var(self, auth_service):
        """Test service token validation when env var not set."""
        # Clear environment variable
        with patch.dict(os.environ, {}, clear=True):
            user = auth_service.validate_service_token("any-token")
            assert user is None

    def test_service_token_constant_time_comparison(self, auth_service):
        """Test that service token comparison is constant-time."""
        # This test verifies we're using hmac.compare_digest
        # by checking the import and usage
        import inspect

        source = inspect.getsource(auth_service.validate_service_token)
        assert "hmac.compare_digest" in source

    @pytest.mark.asyncio
    async def test_bearer_service_token_auth(self, auth_service, mock_request):
        """Test Bearer service:<token> authentication."""
        test_token = "test-service-token-456"

        # Remove audit service to avoid asyncio issues in the test
        mock_request.app.state.audit_service = None

        with patch.dict(os.environ, {"CIRIS_SERVICE_TOKEN": test_token}):
            # Test valid service token
            auth_context = await get_auth_context(mock_request, f"Bearer service:{test_token}", auth_service)

            assert auth_context.user_id == "service-account"
            assert auth_context.role == UserRole.SERVICE_ACCOUNT
            assert auth_context.api_key_id is None

    @pytest.mark.asyncio
    async def test_bearer_service_token_invalid(self, auth_service, mock_request):
        """Test Bearer service:<token> with invalid token."""
        # Remove audit service to avoid asyncio issues in the test
        mock_request.app.state.audit_service = None

        with patch.dict(os.environ, {"CIRIS_SERVICE_TOKEN": "correct-token"}):
            # Test invalid service token
            with pytest.raises(HTTPException) as exc_info:
                await get_auth_context(mock_request, "Bearer service:wrong-token", auth_service)

            assert exc_info.value.status_code == 401
            assert "Invalid service token" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_legacy_admin_password_auth(self, auth_service, mock_request):
        """Test legacy Bearer admin:password authentication."""
        # Remove audit service to avoid asyncio issues in the test
        mock_request.app.state.audit_service = None

        # Admin user should be created by default in __init__

        # Test valid admin credentials
        auth_context = await get_auth_context(mock_request, "Bearer admin:ciris_admin_password", auth_service)

        assert auth_context.user_id == "wa-system-admin"
        assert auth_context.role == UserRole.SYSTEM_ADMIN
        assert auth_context.api_key_id is None

    def test_service_account_permissions(self):
        """Test SERVICE_ACCOUNT role has correct permissions."""
        from ciris_engine.schemas.api.auth import ROLE_PERMISSIONS, Permission

        service_permissions = ROLE_PERMISSIONS[UserRole.SERVICE_ACCOUNT]

        # Should have runtime control for shutdown
        assert Permission.RUNTIME_CONTROL in service_permissions

        # Should have view permissions
        assert Permission.VIEW_TELEMETRY in service_permissions
        assert Permission.VIEW_CONFIG in service_permissions
        assert Permission.VIEW_LOGS in service_permissions

        # Should NOT have sensitive permissions
        assert Permission.EMERGENCY_SHUTDOWN not in service_permissions
        assert Permission.MANAGE_SENSITIVE_CONFIG not in service_permissions
        assert Permission.FULL_ACCESS not in service_permissions

    @pytest.mark.asyncio
    async def test_service_token_audit_logging(self, auth_service, mock_request):
        """Test that service token usage is audited."""
        from unittest.mock import AsyncMock

        from ciris_engine.schemas.services.graph.audit import AuditEventData

        # Create mock audit service
        mock_audit_service = AsyncMock()
        mock_audit_service.log_event = AsyncMock()

        # Add audit service to request state
        mock_request.app.state.audit_service = mock_audit_service

        test_token = "test-audit-token-789"

        with patch.dict(os.environ, {"CIRIS_SERVICE_TOKEN": test_token}):
            # Test successful authentication (should NOT audit)
            auth_context = await get_auth_context(mock_request, f"Bearer service:{test_token}", auth_service)

            # Verify audit was NOT called for successful service token auth
            # (We removed audit logging for successful service token auth to prevent spam)
            assert not mock_audit_service.log_event.called

            # Verify the auth context is correct
            assert auth_context.user_id == "service-account"
            assert auth_context.role == UserRole.SERVICE_ACCOUNT

            # Test failed authentication (should still audit)
            mock_audit_service.log_event.reset_mock()

            with pytest.raises(HTTPException):
                await get_auth_context(mock_request, "Bearer service:wrong-token", auth_service)

            # Verify audit was called for failure
            assert mock_audit_service.log_event.called
            call_args = mock_audit_service.log_event.call_args[0]

            # Check event type
            assert call_args[0] == "service_token_auth_failed"

            # Check event data
            event_data = call_args[1]
            assert isinstance(event_data, AuditEventData)
            assert event_data.outcome == "failure"
            assert event_data.severity == "warning"
