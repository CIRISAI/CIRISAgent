"""Additional tests for APIAuthService to increase coverage.

Covers uncovered code paths:
- _hash_key / _verify_key
- _get_key_id
- store_api_key / validate_api_key / revoke_api_key
- create_oauth_user
- _wa_role_to_api_role
- _user_role_to_api_role
- get_permissions_for_role
- validate_service_token
- list_user_api_keys
"""

import os
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from ciris_engine.logic.adapters.api.services.auth_service import APIAuthService, OAuthUser, StoredAPIKey, User
from ciris_engine.schemas.api.auth import UserRole
from ciris_engine.schemas.runtime.api import APIRole
from ciris_engine.schemas.services.authority_core import WARole


class TestAPIKeyHashing:
    """Tests for API key hashing and verification."""

    def test_hash_key_produces_hash(self):
        """_hash_key produces a bcrypt hash."""
        service = APIAuthService()
        key = "test-api-key-12345"
        hashed = service._hash_key(key)

        assert hashed != key
        assert hashed.startswith("$2b$")  # bcrypt prefix

    def test_verify_key_correct(self):
        """_verify_key returns True for correct key."""
        service = APIAuthService()
        key = "test-api-key-12345"
        hashed = service._hash_key(key)

        assert service._verify_key(key, hashed) is True

    def test_verify_key_incorrect(self):
        """_verify_key returns False for incorrect key."""
        service = APIAuthService()
        key = "test-api-key-12345"
        hashed = service._hash_key(key)

        assert service._verify_key("wrong-key", hashed) is False

    def test_verify_key_invalid_hash(self):
        """_verify_key returns False for invalid hash."""
        service = APIAuthService()
        assert service._verify_key("any-key", "invalid-hash") is False


class TestGetKeyId:
    """Tests for _get_key_id."""

    def test_returns_8_char_hash(self):
        """_get_key_id returns 8-character SHA256 prefix."""
        service = APIAuthService()
        key_id = service._get_key_id("test-api-key")

        assert len(key_id) == 8
        assert key_id.isalnum()

    def test_consistent_for_same_key(self):
        """Same key produces same key_id."""
        service = APIAuthService()
        key = "test-api-key"

        assert service._get_key_id(key) == service._get_key_id(key)

    def test_different_for_different_keys(self):
        """Different keys produce different key_ids."""
        service = APIAuthService()

        id1 = service._get_key_id("key-one")
        id2 = service._get_key_id("key-two")

        assert id1 != id2


class TestStoreAndValidateAPIKey:
    """Tests for store_api_key and validate_api_key."""

    def test_store_and_validate(self):
        """Can store and validate API key."""
        service = APIAuthService()
        key = "ciris_admin_testkeyvalue123"

        service.store_api_key(
            key=key,
            user_id="wa-test-user",
            role=UserRole.ADMIN,
            description="Test key",
        )

        result = service.validate_api_key(key)

        assert result is not None
        assert result.user_id == "wa-test-user"
        assert result.role == UserRole.ADMIN

    def test_validate_nonexistent_key(self):
        """validate_api_key returns None for nonexistent key."""
        service = APIAuthService()
        result = service.validate_api_key("nonexistent-key")

        assert result is None

    def test_validate_expired_key(self):
        """validate_api_key returns None for expired key."""
        service = APIAuthService()
        key = "ciris_admin_expiredkey123"

        service.store_api_key(
            key=key,
            user_id="wa-test-user",
            role=UserRole.ADMIN,
            expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
        )

        result = service.validate_api_key(key)

        assert result is None

    def test_validate_creates_system_admin_user(self):
        """validate_api_key creates system admin user if missing."""
        service = APIAuthService()
        key = "ciris_admin_sysadminkey123"

        service.store_api_key(
            key=key,
            user_id="wa-system-admin",
            role=UserRole.SYSTEM_ADMIN,
        )

        # Clear the user
        service._users.clear()

        result = service.validate_api_key(key)

        assert result is not None
        assert "wa-system-admin" in service._users


class TestRevokeAPIKey:
    """Tests for revoke_api_key."""

    def test_revoke_marks_inactive(self):
        """revoke_api_key marks key as inactive."""
        service = APIAuthService()
        key = "ciris_admin_revoketest123"

        service.store_api_key(
            key=key,
            user_id="wa-test-user",
            role=UserRole.ADMIN,
        )

        key_id = service._get_key_id(key)
        service.revoke_api_key(key_id)

        # Key should now be invalid
        result = service.validate_api_key(key)
        assert result is None

    def test_revoke_nonexistent_key(self):
        """revoke_api_key handles nonexistent key gracefully."""
        service = APIAuthService()
        service.revoke_api_key("nonexistent-key-id")
        # Should not raise


class TestCreateOAuthUser:
    """Tests for create_oauth_user."""

    def test_creates_new_user(self):
        """Creates new OAuth user."""
        service = APIAuthService()

        user = service.create_oauth_user(
            provider="google",
            external_id="12345",
            email="test@example.com",
            name="Test User",
            role=UserRole.OBSERVER,
        )

        assert user.user_id == "google:12345"
        assert user.email == "test@example.com"
        assert user.provider == "google"

    def test_updates_existing_user(self):
        """Updates existing OAuth user."""
        service = APIAuthService()

        # Create first
        service.create_oauth_user(
            provider="google",
            external_id="12345",
            email="old@example.com",
            name="Old Name",
            role=UserRole.OBSERVER,
        )

        # Update
        user = service.create_oauth_user(
            provider="google",
            external_id="12345",
            email="new@example.com",
            name="New Name",
            role=UserRole.ADMIN,
        )

        assert user.email == "new@example.com"
        assert user.name == "New Name"

    def test_marketing_opt_in(self):
        """Stores marketing opt-in preference."""
        service = APIAuthService()

        user = service.create_oauth_user(
            provider="google",
            external_id="12345",
            email="test@example.com",
            name="Test User",
            role=UserRole.OBSERVER,
            marketing_opt_in=True,
        )

        assert user.marketing_opt_in is True


class TestWARoleToAPIRole:
    """Tests for _wa_role_to_api_role."""

    def test_root_to_system_admin(self):
        """ROOT WA role maps to SYSTEM_ADMIN API role."""
        service = APIAuthService()
        result = service._wa_role_to_api_role(WARole.ROOT)
        assert result == APIRole.SYSTEM_ADMIN

    def test_authority_to_authority(self):
        """AUTHORITY WA role maps to AUTHORITY API role."""
        service = APIAuthService()
        result = service._wa_role_to_api_role(WARole.AUTHORITY)
        assert result == APIRole.AUTHORITY

    def test_observer_to_observer(self):
        """OBSERVER WA role maps to OBSERVER API role."""
        service = APIAuthService()
        result = service._wa_role_to_api_role(WARole.OBSERVER)
        assert result == APIRole.OBSERVER

    def test_none_to_observer(self):
        """None WA role maps to OBSERVER API role."""
        service = APIAuthService()
        result = service._wa_role_to_api_role(None)
        assert result == APIRole.OBSERVER


class TestUserRoleToAPIRole:
    """Tests for _user_role_to_api_role."""

    def test_observer_mapping(self):
        """OBSERVER UserRole maps correctly."""
        service = APIAuthService()
        result = service._user_role_to_api_role(UserRole.OBSERVER)
        assert result == APIRole.OBSERVER

    def test_admin_mapping(self):
        """ADMIN UserRole maps correctly."""
        service = APIAuthService()
        result = service._user_role_to_api_role(UserRole.ADMIN)
        assert result == APIRole.ADMIN

    def test_system_admin_mapping(self):
        """SYSTEM_ADMIN UserRole maps correctly."""
        service = APIAuthService()
        result = service._user_role_to_api_role(UserRole.SYSTEM_ADMIN)
        assert result == APIRole.SYSTEM_ADMIN


class TestGetPermissionsForRole:
    """Tests for get_permissions_for_role."""

    def test_observer_permissions(self):
        """OBSERVER role has read-only permissions."""
        service = APIAuthService()
        perms = service.get_permissions_for_role(APIRole.OBSERVER)

        assert "system.read" in perms
        assert "system.write" not in perms
        assert "users.write" not in perms

    def test_admin_permissions(self):
        """ADMIN role has read/write permissions."""
        service = APIAuthService()
        perms = service.get_permissions_for_role(APIRole.ADMIN)

        assert "system.read" in perms
        assert "system.write" in perms
        assert "config.write" in perms

    def test_system_admin_permissions(self):
        """SYSTEM_ADMIN role has all permissions."""
        service = APIAuthService()
        perms = service.get_permissions_for_role(APIRole.SYSTEM_ADMIN)

        assert "system.read" in perms
        assert "system.write" in perms
        assert "users.delete" in perms
        assert "wa.mint" in perms
        assert "emergency.shutdown" in perms


class TestValidateServiceToken:
    """Tests for validate_service_token."""

    def test_valid_token(self):
        """Returns service user for valid token."""
        service = APIAuthService()

        with patch.dict(os.environ, {"CIRIS_SERVICE_TOKEN": "valid-token-123"}):
            user = service.validate_service_token("valid-token-123")

            assert user is not None
            assert user.wa_id == "service-account"
            assert user.api_role == APIRole.SERVICE_ACCOUNT

    def test_invalid_token(self):
        """Returns None for invalid token."""
        service = APIAuthService()

        with patch.dict(os.environ, {"CIRIS_SERVICE_TOKEN": "valid-token-123"}):
            user = service.validate_service_token("wrong-token")

            assert user is None

    def test_no_token_configured(self):
        """Returns None when no token configured."""
        service = APIAuthService()

        with patch.dict(os.environ, {}, clear=True):
            # Ensure CIRIS_SERVICE_TOKEN is not set
            os.environ.pop("CIRIS_SERVICE_TOKEN", None)
            user = service.validate_service_token("any-token")

            assert user is None


class TestListUserAPIKeys:
    """Tests for list_user_api_keys."""

    def test_returns_keys_for_user(self):
        """Returns API keys for specific user."""
        service = APIAuthService()

        # Store multiple keys for different users
        service.store_api_key(
            key="key1-user1",
            user_id="user1",
            role=UserRole.ADMIN,
        )
        service.store_api_key(
            key="key2-user1",
            user_id="user1",
            role=UserRole.OBSERVER,
        )
        service.store_api_key(
            key="key3-user2",
            user_id="user2",
            role=UserRole.ADMIN,
        )

        keys = service.list_user_api_keys("user1")

        assert len(keys) == 2
        assert all(k.user_id == "user1" for k in keys)

    def test_returns_empty_for_no_keys(self):
        """Returns empty list when user has no keys."""
        service = APIAuthService()

        keys = service.list_user_api_keys("nonexistent-user")

        assert keys == []


class TestHashPassword:
    """Tests for _hash_password."""

    def test_produces_hash(self):
        """_hash_password produces a hash."""
        service = APIAuthService()
        password = "test-password-123"

        hashed = service._hash_password(password)

        assert hashed != password
        assert len(hashed) > 0

    def test_different_hashes_for_same_password(self):
        """Different calls produce different hashes (due to salt)."""
        service = APIAuthService()
        password = "test-password-123"

        hash1 = service._hash_password(password)
        hash2 = service._hash_password(password)

        # Should be different due to random salt
        assert hash1 != hash2


class TestVerifyPassword:
    """Tests for _verify_password."""

    def test_verifies_correct_password(self):
        """_verify_password returns True for correct password."""
        service = APIAuthService()
        password = "test-password-123"
        hashed = service._hash_password(password)

        assert service._verify_password(password, hashed) is True

    def test_rejects_wrong_password(self):
        """_verify_password returns False for wrong password."""
        service = APIAuthService()
        hashed = service._hash_password("correct-password")

        assert service._verify_password("wrong-password", hashed) is False

    def test_handles_invalid_hash(self):
        """_verify_password returns False for invalid hash."""
        service = APIAuthService()

        assert service._verify_password("any-password", "invalid-hash") is False
