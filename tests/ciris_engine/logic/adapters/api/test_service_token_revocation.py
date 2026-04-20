"""Tests for service token revocation mechanism."""

import os
from datetime import datetime, timezone

import pytest

from ciris_engine.logic.adapters.api.services.auth_service import APIAuthService
from ciris_engine.schemas.runtime.api import APIRole


@pytest.fixture
def auth_service():
    """Create an auth service instance for testing."""
    return APIAuthService(auth_service=None)


@pytest.fixture
def mock_service_token(monkeypatch):
    """Set up a mock service token in environment."""
    token = "test_service_token_12345"
    monkeypatch.setenv("CIRIS_SERVICE_TOKEN", token)
    return token


class TestServiceTokenRevocation:
    """Test service token revocation mechanism."""

    def test_validate_service_token_success(self, auth_service, mock_service_token):
        """Test that a valid service token is accepted."""
        user = auth_service.validate_service_token(mock_service_token)
        assert user is not None
        assert user.wa_id == "service-account"
        assert user.auth_type == "service_token"
        assert user.api_role == APIRole.SERVICE_ACCOUNT

    def test_validate_service_token_invalid(self, auth_service, mock_service_token):
        """Test that an invalid service token is rejected."""
        user = auth_service.validate_service_token("wrong_token")
        assert user is None

    @pytest.mark.asyncio
    async def test_revoke_service_token(self, auth_service, mock_service_token):
        """Test that a service token can be revoked."""
        # First, verify token works
        user = auth_service.validate_service_token(mock_service_token)
        assert user is not None

        # Revoke the token
        result = await auth_service.revoke_service_token(
            token=mock_service_token, reason="security test", revoked_by="test-admin"
        )
        assert result is True

        # Verify token no longer works
        user = auth_service.validate_service_token(mock_service_token)
        assert user is None

    @pytest.mark.asyncio
    async def test_revoke_already_revoked_token(self, auth_service, mock_service_token):
        """Test that revoking an already-revoked token returns False."""
        # Revoke once
        result1 = await auth_service.revoke_service_token(
            token=mock_service_token, reason="first revocation", revoked_by="admin1"
        )
        assert result1 is True

        # Try to revoke again
        result2 = await auth_service.revoke_service_token(
            token=mock_service_token, reason="second revocation", revoked_by="admin2"
        )
        assert result2 is False

    def test_is_service_token_revoked(self, auth_service, mock_service_token):
        """Test the is_service_token_revoked check."""
        # Initially not revoked
        assert auth_service.is_service_token_revoked(mock_service_token) is False

        # Add to revoked set manually
        token_hash = auth_service._hash_service_token(mock_service_token)
        auth_service._revoked_service_tokens.add(token_hash)

        # Now should be revoked
        assert auth_service.is_service_token_revoked(mock_service_token) is True

    def test_hash_service_token_consistency(self, auth_service):
        """Test that token hashing is consistent."""
        token = "test_token_12345"
        hash1 = auth_service._hash_service_token(token)
        hash2 = auth_service._hash_service_token(token)
        assert hash1 == hash2

    def test_hash_service_token_different_for_different_tokens(self, auth_service):
        """Test that different tokens produce different hashes."""
        token1 = "test_token_12345"
        token2 = "test_token_67890"
        hash1 = auth_service._hash_service_token(token1)
        hash2 = auth_service._hash_service_token(token2)
        assert hash1 != hash2

    def test_validate_no_service_token_env(self, auth_service, monkeypatch):
        """Test validation when CIRIS_SERVICE_TOKEN env var is not set."""
        monkeypatch.delenv("CIRIS_SERVICE_TOKEN", raising=False)
        user = auth_service.validate_service_token("any_token")
        assert user is None

    @pytest.mark.asyncio
    async def test_revocation_persistence_across_instances(self, mock_service_token, tmp_path, monkeypatch):
        """Test that revocations persist across service instances (multi-occurrence support)."""
        # Set up a temporary database path
        db_path = str(tmp_path / "test_revocations.db")
        monkeypatch.setenv("CIRIS_DATA_DIR", str(tmp_path))

        # Create first instance and revoke a token
        service1 = APIAuthService(auth_service=None)
        result = await service1.revoke_service_token(
            token=mock_service_token, reason="security incident", revoked_by="admin"
        )
        assert result is True

        # Verify token is revoked in first instance
        user = service1.validate_service_token(mock_service_token)
        assert user is None

        # Create second instance (simulates new process/occurrence)
        service2 = APIAuthService(auth_service=None)

        # Load revoked tokens from database
        await service2._load_revoked_tokens()

        # Verify token is still revoked in second instance
        user = service2.validate_service_token(mock_service_token)
        assert user is None
        assert service2.is_service_token_revoked(mock_service_token) is True
