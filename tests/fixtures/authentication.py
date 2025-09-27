"""
Authentication service fixtures for test mocking.

Provides comprehensive typed fixtures for authentication testing.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest

from ciris_engine.logic.adapters.api.services.auth_service import User
from ciris_engine.schemas.runtime.api import APIRole
from ciris_engine.schemas.services.authority.wise_authority import AuthenticationResult, TokenVerification
from ciris_engine.schemas.services.authority_core import TokenType, WARole


@pytest.fixture
def mock_authentication_service():
    """Mock authentication service with proper typed responses."""
    mock = AsyncMock()

    # Mock authenticate_user method (for API login)
    mock.authenticate_user = AsyncMock(return_value="fake_jwt_token")

    # Mock authenticate method
    future_time = datetime.now(timezone.utc) + timedelta(hours=1)
    auth_result = AuthenticationResult(
        authenticated=True,
        wa_id="test-admin-wa",
        name="Test Admin",
        role="ADMIN",
        expires_at=future_time,
        permissions=["system:read", "system:write", "runtime:control"],
        metadata={"test": "true"},
    )
    mock.authenticate = AsyncMock(return_value=auth_result)

    # Mock verify_token method
    token_verification = TokenVerification(
        valid=True, wa_id="test-admin-wa", name="Test Admin", role="ADMIN", expires_at=future_time, error=None
    )
    mock.verify_token = AsyncMock(return_value=token_verification)

    # Mock create_token method
    mock.create_token = AsyncMock(return_value="fake_jwt_token")

    # Mock other methods that might be called
    mock.create_wa = AsyncMock(return_value=None)
    mock.revoke_wa = AsyncMock(return_value=True)

    return mock


@pytest.fixture
def mock_api_auth_service():
    """Mock API authentication service for API endpoints."""
    mock = AsyncMock()

    # Mock verify_user_password method (used by login)
    test_user = User(
        wa_id="test-admin-wa", name="Test Admin", auth_type="password", api_role=APIRole.ADMIN, is_active=True
    )
    mock.verify_user_password = AsyncMock(return_value=test_user)

    # Mock store_api_key method
    mock.store_api_key = AsyncMock(return_value=None)

    # Mock other methods that might be called
    mock.validate_api_key = AsyncMock(return_value=test_user)
    mock.get_user_permissions = AsyncMock(return_value=["system:read", "system:write"])

    return mock
