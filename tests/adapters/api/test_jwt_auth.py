"""
Tests for JWT authentication in auth.py
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import HTTPException, Request
from fastapi.security import HTTPBearer

from ciris_engine.logic.adapters.api.auth import get_current_user
from ciris_engine.schemas.services.authority.wise_authority import TokenVerification


class TestJWTAuthentication:
    """Test JWT authentication functionality."""

    def test_security_scheme_initialization(self):
        """Test that HTTPBearer security scheme is properly initialized."""
        from ciris_engine.logic.adapters.api.auth import security

        assert isinstance(security, HTTPBearer)
        assert security.auto_error is False

    @pytest.mark.asyncio
    async def test_missing_token_raises_401(self):
        """Test that missing token raises 401."""
        request = Mock(spec=Request)

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(request, None)

        assert exc_info.value.status_code == 401
        assert "Missing authentication token" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_no_auth_service_returns_dev_fallback(self):
        """Test fallback to development mode when auth service not available."""
        request = Mock(spec=Request)
        request.app.state.authentication_service = None

        result = await get_current_user(request, "test_token")

        assert result.username == "admin"
        assert result.email == "admin@ciris.ai"
        assert result.role == "SYSTEM_ADMIN"

    @pytest.mark.asyncio
    async def test_missing_auth_service_returns_dev_fallback(self):
        """Test fallback when auth service attribute doesn't exist."""
        request = Mock(spec=Request)
        # Mock app.state without authentication_service attribute
        request.app.state = Mock()
        (
            delattr(request.app.state, "authentication_service")
            if hasattr(request.app.state, "authentication_service")
            else None
        )

        result = await get_current_user(request, "test_token")

        assert result.username == "admin"
        assert result.email == "admin@ciris.ai"
        assert result.role == "SYSTEM_ADMIN"

    @pytest.mark.asyncio
    async def test_invalid_token_raises_401(self):
        """Test that invalid token raises 401."""
        request = Mock(spec=Request)
        auth_service = AsyncMock()
        auth_service.verify_token.return_value = TokenVerification(
            valid=False, wa_id=None, name=None, role=None, expires_at=None, error="Invalid token"
        )
        request.app.state.authentication_service = auth_service

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(request, "invalid_token")

        assert exc_info.value.status_code == 401
        assert "Invalid or expired token" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_verification_none_raises_401(self):
        """Test that None verification raises 401."""
        request = Mock(spec=Request)
        auth_service = AsyncMock()
        auth_service.verify_token.return_value = None
        request.app.state.authentication_service = auth_service

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(request, "token")

        assert exc_info.value.status_code == 401
        assert "Invalid or expired token" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_valid_observer_token(self):
        """Test valid token with OBSERVER role."""
        request = Mock(spec=Request)
        auth_service = AsyncMock()
        expires_at = datetime.now(timezone.utc)
        auth_service.verify_token.return_value = TokenVerification(
            valid=True,
            wa_id="wa-2025-01-05-ABC123",
            name="Test Observer",
            role="OBSERVER",
            expires_at=expires_at,
            error=None,
        )
        request.app.state.authentication_service = auth_service

        result = await get_current_user(request, "valid_token")

        assert result.username == "Test Observer"
        assert result.email is None
        assert result.role == "OBSERVER"
        assert result.exp == expires_at

    @pytest.mark.asyncio
    async def test_valid_admin_token(self):
        """Test valid token with ADMIN role."""
        request = Mock(spec=Request)
        auth_service = AsyncMock()
        expires_at = datetime.now(timezone.utc)
        auth_service.verify_token.return_value = TokenVerification(
            valid=True, wa_id="wa-2025-01-05-DEF456", name="Test Admin", role="ADMIN", expires_at=expires_at, error=None
        )
        request.app.state.authentication_service = auth_service

        result = await get_current_user(request, "admin_token")

        assert result.username == "Test Admin"
        assert result.email is None
        assert result.role == "ADMIN"
        assert result.exp == expires_at

    @pytest.mark.asyncio
    async def test_valid_authority_token(self):
        """Test valid token with AUTHORITY role."""
        request = Mock(spec=Request)
        auth_service = AsyncMock()
        expires_at = datetime.now(timezone.utc)
        auth_service.verify_token.return_value = TokenVerification(
            valid=True,
            wa_id="wa-2025-01-05-GHI789",
            name="Test Authority",
            role="AUTHORITY",
            expires_at=expires_at,
            error=None,
        )
        request.app.state.authentication_service = auth_service

        result = await get_current_user(request, "authority_token")

        assert result.username == "Test Authority"
        assert result.role == "AUTHORITY"

    @pytest.mark.asyncio
    async def test_valid_system_admin_token(self):
        """Test valid token with SYSTEM_ADMIN role."""
        request = Mock(spec=Request)
        auth_service = AsyncMock()
        expires_at = datetime.now(timezone.utc)
        auth_service.verify_token.return_value = TokenVerification(
            valid=True,
            wa_id="wa-2025-01-05-JKL012",
            name="Test System Admin",
            role="SYSTEM_ADMIN",
            expires_at=expires_at,
            error=None,
        )
        request.app.state.authentication_service = auth_service

        result = await get_current_user(request, "sysadmin_token")

        assert result.username == "Test System Admin"
        assert result.role == "SYSTEM_ADMIN"

    @pytest.mark.asyncio
    async def test_unknown_role_defaults_to_observer(self):
        """Test that unknown roles default to OBSERVER."""
        request = Mock(spec=Request)
        auth_service = AsyncMock()
        auth_service.verify_token.return_value = TokenVerification(
            valid=True,
            wa_id="wa-2025-01-05-XYZ999",
            name="Test Unknown",
            role="UNKNOWN_ROLE",
            expires_at=datetime.now(timezone.utc),
            error=None,
        )
        request.app.state.authentication_service = auth_service

        result = await get_current_user(request, "unknown_role_token")

        assert result.role == "OBSERVER"

    @pytest.mark.asyncio
    async def test_no_name_uses_wa_id(self):
        """Test that when name is None, wa_id is used as username."""
        request = Mock(spec=Request)
        auth_service = AsyncMock()
        auth_service.verify_token.return_value = TokenVerification(
            valid=True,
            wa_id="wa-2025-01-05-NO_NAME",
            name=None,
            role="OBSERVER",
            expires_at=datetime.now(timezone.utc),
            error=None,
        )
        request.app.state.authentication_service = auth_service

        result = await get_current_user(request, "no_name_token")

        assert result.username == "wa-2025-01-05-NO_NAME"

    @pytest.mark.asyncio
    async def test_auth_service_exception_raises_401(self):
        """Test that authentication service exceptions are handled properly."""
        request = Mock(spec=Request)
        auth_service = AsyncMock()
        auth_service.verify_token.side_effect = ValueError("Token decode error")
        request.app.state.authentication_service = auth_service

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(request, "error_token")

        assert exc_info.value.status_code == 401
        assert "Token validation failed: Token decode error" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_role_mapping_complete(self):
        """Test all role mappings are handled correctly."""
        role_tests = [
            ("OBSERVER", "OBSERVER"),
            ("ADMIN", "ADMIN"),
            ("AUTHORITY", "AUTHORITY"),
            ("SYSTEM_ADMIN", "SYSTEM_ADMIN"),
            ("UNKNOWN", "OBSERVER"),  # Default fallback
        ]

        for wa_role, expected_api_role in role_tests:
            request = Mock(spec=Request)
            auth_service = AsyncMock()
            auth_service.verify_token.return_value = TokenVerification(
                valid=True,
                wa_id="wa-2025-01-05-TEST01",
                name="Test User",
                role=wa_role,
                expires_at=datetime.now(timezone.utc),
                error=None,
            )
            request.app.state.authentication_service = auth_service

            result = await get_current_user(request, f"token_{wa_role.lower()}")

            assert result.role == expected_api_role, f"Role {wa_role} should map to {expected_api_role}"
