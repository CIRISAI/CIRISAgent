"""
Tests for native auth helper functions in auth.py

Covers:
- _decode_google_jwt_locally()
- _decode_apple_jwt_locally()
- _auto_mint_system_admin_if_needed()
"""

import base64
import json
import time
from unittest.mock import AsyncMock, Mock, patch

import pytest

from ciris_engine.logic.adapters.api.routes.auth import (
    _auto_mint_system_admin_if_needed,
    _decode_apple_jwt_locally,
    _decode_google_jwt_locally,
)
from ciris_engine.logic.adapters.api.services.auth_service import OAuthUser
from ciris_engine.schemas.api.auth import UserRole


def _create_test_jwt(payload: dict, header: dict | None = None) -> str:
    """Create a test JWT with given payload."""
    if header is None:
        header = {"alg": "RS256", "typ": "JWT"}

    def b64_encode(data: dict) -> str:
        json_bytes = json.dumps(data).encode("utf-8")
        return base64.urlsafe_b64encode(json_bytes).rstrip(b"=").decode("utf-8")

    header_b64 = b64_encode(header)
    payload_b64 = b64_encode(payload)
    # Fake signature (not verified in local decode)
    signature_b64 = base64.urlsafe_b64encode(b"fake_signature").rstrip(b"=").decode("utf-8")

    return f"{header_b64}.{payload_b64}.{signature_b64}"


class TestDecodeGoogleJwtLocally:
    """Tests for _decode_google_jwt_locally function."""

    def test_decodes_valid_google_jwt(self):
        """Decodes a valid Google JWT and extracts user info."""
        payload = {
            "iss": "accounts.google.com",
            "sub": "123456789",
            "email": "test@example.com",
            "name": "Test User",
            "picture": "https://example.com/photo.jpg",
            "exp": int(time.time()) + 3600,  # 1 hour from now
        }
        token = _create_test_jwt(payload)

        result = _decode_google_jwt_locally(token)

        assert result["external_id"] == "123456789"
        assert result["email"] == "test@example.com"
        assert result["name"] == "Test User"
        assert result["picture"] == "https://example.com/photo.jpg"

    def test_accepts_https_issuer(self):
        """Accepts https://accounts.google.com as valid issuer."""
        payload = {
            "iss": "https://accounts.google.com",
            "sub": "123456789",
            "email": "test@example.com",
            "exp": int(time.time()) + 3600,
        }
        token = _create_test_jwt(payload)

        result = _decode_google_jwt_locally(token)

        assert result["external_id"] == "123456789"

    def test_rejects_expired_token(self):
        """Rejects expired tokens."""
        payload = {
            "iss": "accounts.google.com",
            "sub": "123456789",
            "email": "test@example.com",
            "exp": int(time.time()) - 3600,  # 1 hour ago
        }
        token = _create_test_jwt(payload)

        with pytest.raises(ValueError, match="Token has expired"):
            _decode_google_jwt_locally(token)

    def test_rejects_invalid_issuer(self):
        """Rejects tokens with invalid issuer."""
        payload = {
            "iss": "https://evil.com",
            "sub": "123456789",
            "email": "test@example.com",
            "exp": int(time.time()) + 3600,
        }
        token = _create_test_jwt(payload)

        with pytest.raises(ValueError, match="Invalid issuer"):
            _decode_google_jwt_locally(token)

    def test_rejects_invalid_jwt_format(self):
        """Rejects tokens that don't have 3 parts."""
        with pytest.raises(ValueError, match="Invalid JWT format"):
            _decode_google_jwt_locally("not.a.valid.jwt.token")

        with pytest.raises(ValueError, match="Invalid JWT format"):
            _decode_google_jwt_locally("only_one_part")

    def test_handles_missing_optional_fields(self):
        """Handles tokens missing optional fields like name and picture."""
        payload = {
            "iss": "accounts.google.com",
            "sub": "123456789",
            "email": "test@example.com",
            "exp": int(time.time()) + 3600,
        }
        token = _create_test_jwt(payload)

        result = _decode_google_jwt_locally(token)

        assert result["external_id"] == "123456789"
        assert result["email"] == "test@example.com"
        assert result["name"] is None
        assert result["picture"] is None

    def test_handles_token_without_expiry(self):
        """Handles tokens without exp field (no expiry check)."""
        payload = {
            "iss": "accounts.google.com",
            "sub": "123456789",
            "email": "test@example.com",
            # No exp field
        }
        token = _create_test_jwt(payload)

        result = _decode_google_jwt_locally(token)

        assert result["external_id"] == "123456789"


class TestDecodeAppleJwtLocally:
    """Tests for _decode_apple_jwt_locally function."""

    def test_decodes_valid_apple_jwt(self):
        """Decodes a valid Apple JWT and extracts user info."""
        payload = {
            "iss": "https://appleid.apple.com",
            "sub": "000123.abc456.789",
            "email": "user@privaterelay.appleid.com",
            "name": "Apple User",
            "exp": int(time.time()) + 3600,
        }
        token = _create_test_jwt(payload)

        result = _decode_apple_jwt_locally(token)

        assert result["external_id"] == "000123.abc456.789"
        assert result["email"] == "user@privaterelay.appleid.com"
        assert result["name"] == "Apple User"
        assert result["picture"] is None  # Apple doesn't provide pictures

    def test_rejects_invalid_apple_issuer(self):
        """Rejects tokens not from Apple."""
        payload = {
            "iss": "https://accounts.google.com",
            "sub": "123456789",
            "email": "test@example.com",
            "exp": int(time.time()) + 3600,
        }
        token = _create_test_jwt(payload)

        with pytest.raises(ValueError, match="Invalid issuer"):
            _decode_apple_jwt_locally(token)

    def test_rejects_expired_apple_token(self):
        """Rejects expired Apple tokens."""
        payload = {
            "iss": "https://appleid.apple.com",
            "sub": "000123.abc456.789",
            "email": "user@example.com",
            "exp": int(time.time()) - 3600,
        }
        token = _create_test_jwt(payload)

        with pytest.raises(ValueError, match="Token has expired"):
            _decode_apple_jwt_locally(token)

    def test_rejects_invalid_jwt_format(self):
        """Rejects tokens that don't have 3 parts."""
        with pytest.raises(ValueError, match="Invalid JWT format"):
            _decode_apple_jwt_locally("invalid")

    def test_handles_missing_name(self):
        """Handles tokens without name (Apple only sends name on first auth)."""
        payload = {
            "iss": "https://appleid.apple.com",
            "sub": "000123.abc456.789",
            "email": "user@example.com",
            "exp": int(time.time()) + 3600,
            # No name field
        }
        token = _create_test_jwt(payload)

        result = _decode_apple_jwt_locally(token)

        assert result["external_id"] == "000123.abc456.789"
        assert result["name"] is None


class TestAutoMintSystemAdminIfNeeded:
    """Tests for _auto_mint_system_admin_if_needed function."""

    @pytest.mark.asyncio
    async def test_skips_non_system_admin_users(self):
        """Skips minting for non-SYSTEM_ADMIN users."""
        oauth_user = Mock(spec=OAuthUser)
        oauth_user.role = UserRole.OBSERVER
        oauth_user.user_id = "google:123"

        auth_service = Mock()

        await _auto_mint_system_admin_if_needed(oauth_user, auth_service, "TestAuth")

        # Should not attempt to get user or mint
        auth_service.get_user.assert_not_called()
        auth_service.mint_wise_authority.assert_not_called()

    @pytest.mark.asyncio
    async def test_mints_new_system_admin(self):
        """Mints new SYSTEM_ADMIN user as ROOT WA."""
        oauth_user = Mock(spec=OAuthUser)
        oauth_user.role = UserRole.SYSTEM_ADMIN
        oauth_user.user_id = "google:123"

        auth_service = Mock()
        auth_service.get_user.return_value = None  # No existing user
        auth_service.mint_wise_authority = AsyncMock()

        await _auto_mint_system_admin_if_needed(oauth_user, auth_service, "TestAuth")

        auth_service.get_user.assert_called_once_with("google:123")
        auth_service.mint_wise_authority.assert_called_once()
        call_kwargs = auth_service.mint_wise_authority.call_args[1]
        assert call_kwargs["user_id"] == "google:123"
        assert call_kwargs["minted_by"] == "system_auto_mint"

    @pytest.mark.asyncio
    async def test_skips_already_minted_user(self):
        """Skips minting for already-minted users."""
        oauth_user = Mock(spec=OAuthUser)
        oauth_user.role = UserRole.SYSTEM_ADMIN
        oauth_user.user_id = "google:123"

        existing_user = Mock()
        existing_user.wa_id = "wa:456"  # Different from user_id = already minted
        existing_user.wa_role = "ROOT"

        auth_service = Mock()
        auth_service.get_user.return_value = existing_user
        auth_service.mint_wise_authority = AsyncMock()

        await _auto_mint_system_admin_if_needed(oauth_user, auth_service, "TestAuth")

        auth_service.get_user.assert_called_once_with("google:123")
        auth_service.mint_wise_authority.assert_not_called()

    @pytest.mark.asyncio
    async def test_mints_user_with_wa_id_same_as_user_id(self):
        """Mints user whose wa_id equals user_id (not properly minted)."""
        oauth_user = Mock(spec=OAuthUser)
        oauth_user.role = UserRole.SYSTEM_ADMIN
        oauth_user.user_id = "google:123"

        existing_user = Mock()
        existing_user.wa_id = "google:123"  # Same as user_id = needs minting
        existing_user.wa_role = None

        auth_service = Mock()
        auth_service.get_user.return_value = existing_user
        auth_service.mint_wise_authority = AsyncMock()

        await _auto_mint_system_admin_if_needed(oauth_user, auth_service, "TestAuth")

        auth_service.mint_wise_authority.assert_called_once()

    @pytest.mark.asyncio
    async def test_mints_user_with_no_wa_id(self):
        """Mints user who has no wa_id set."""
        oauth_user = Mock(spec=OAuthUser)
        oauth_user.role = UserRole.SYSTEM_ADMIN
        oauth_user.user_id = "google:123"

        existing_user = Mock()
        existing_user.wa_id = None  # No WA ID = needs minting
        existing_user.wa_role = None

        auth_service = Mock()
        auth_service.get_user.return_value = existing_user
        auth_service.mint_wise_authority = AsyncMock()

        await _auto_mint_system_admin_if_needed(oauth_user, auth_service, "TestAuth")

        auth_service.mint_wise_authority.assert_called_once()

    @pytest.mark.asyncio
    async def test_handles_mint_failure_gracefully(self):
        """Continues without raising if minting fails."""
        oauth_user = Mock(spec=OAuthUser)
        oauth_user.role = UserRole.SYSTEM_ADMIN
        oauth_user.user_id = "google:123"

        auth_service = Mock()
        auth_service.get_user.return_value = None
        auth_service.mint_wise_authority = AsyncMock(side_effect=Exception("Mint failed"))

        # Should not raise
        await _auto_mint_system_admin_if_needed(oauth_user, auth_service, "TestAuth")

        auth_service.mint_wise_authority.assert_called_once()
