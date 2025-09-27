"""
Test OAuth WA Minting Fix - Ensure no duplicate user records.

This test verifies that when an OAuth user is minted as a WA,
their existing user record is updated with WA status instead of
creating a separate WA user record.

Addresses the issue where:
- OAuth user: user_id="google:12345", wa_role=null
- WA minting created: user_id="wa-2025-09-09-87E57F", wa_role="authority"
- Result: Two separate user records for same person

Fixed behavior:
- OAuth user: user_id="google:12345", wa_role="authority"
- No duplicate records
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock, patch

import pytest

from ciris_engine.logic.adapters.api.services.auth_service import APIAuthService
from ciris_engine.schemas.runtime.api import APIRole
from ciris_engine.schemas.services.authority_core import WACertificate, WARole


class TestOAuthWAMintingFix:
    """Test the fix for OAuth WA minting duplicate records."""

    @pytest.fixture
    def mock_auth_service(self):
        """Mock authentication service."""
        auth_service = Mock()
        auth_service.get_wa = AsyncMock(return_value=None)  # No existing WA
        auth_service._store_wa_certificate = AsyncMock()
        auth_service._generate_wa_id = Mock(return_value="wa-2025-09-09-ABC123")  # Mock WA ID generation
        return auth_service

    @pytest.fixture
    def api_auth_service(self, mock_auth_service):
        """Create API auth service with mocked dependencies."""
        service = APIAuthService(mock_auth_service)
        return service

    @pytest.fixture
    def oauth_user(self, api_auth_service):
        """Create OAuth user for testing."""
        from ciris_engine.logic.adapters.api.services.auth_service import User

        user = User(
            wa_id="google:110265575142761676421",  # Primary ID
            name="Eric Moore",
            auth_type="oauth",
            api_role=APIRole.ADMIN,
            wa_role=None,
            oauth_provider="google",
            oauth_email="eric@ciris.ai",
            oauth_external_id="110265575142761676421",
            created_at=datetime.now(timezone.utc),
            last_login=datetime.now(timezone.utc),
            is_active=True,
            oauth_name="Eric Moore",
            oauth_picture="https://example.com/pic.jpg",
            permission_requested_at=None,
            wa_parent_id=None,
            wa_auto_minted=False,
            password_hash=None,
            custom_permissions=None,
        )

        # Add user to service
        api_auth_service._users[user.wa_id] = user
        return user

    @pytest.mark.asyncio
    async def test_oauth_wa_minting_no_duplicates(self, api_auth_service, oauth_user, mock_auth_service):
        """Test that OAuth WA minting updates existing user instead of creating duplicate."""
        original_user_id = oauth_user.wa_id

        # Mint user as WA
        result_user = await api_auth_service.mint_wise_authority(
            user_id=original_user_id, wa_role=WARole.AUTHORITY, minted_by="admin-user"
        )

        # Verify result
        assert result_user is not None
        assert result_user.wa_role == WARole.AUTHORITY  # WA role updated
        assert result_user.wa_id is not None  # Has a WA ID
        assert result_user.wa_id != original_user_id  # WA ID is different from OAuth user_id
        assert result_user.wa_id.startswith("wa-")  # Proper WA ID format
        assert result_user.api_role == APIRole.AUTHORITY  # API role upgraded

        # Verify only one user record exists (OAuth user updated, not duplicated)
        assert len(api_auth_service._users) == 1
        assert original_user_id in api_auth_service._users  # Still accessible by OAuth user_id

        # Verify no separate WA user record was created in the users dict
        oauth_user_in_dict = api_auth_service._users[original_user_id]
        assert oauth_user_in_dict.wa_role == WARole.AUTHORITY
        assert oauth_user_in_dict.wa_id.startswith("wa-")

        # Verify WA certificate was stored with proper wa_id format
        mock_auth_service._store_wa_certificate.assert_called_once()
        stored_wa_cert = mock_auth_service._store_wa_certificate.call_args[0][0]
        assert stored_wa_cert.wa_id.startswith("wa-")  # Proper format
        assert stored_wa_cert.oauth_provider == "google"
        assert stored_wa_cert.oauth_external_id == "110265575142761676421"
        assert stored_wa_cert.role == WARole.AUTHORITY

    @pytest.mark.asyncio
    async def test_oauth_wa_certificate_fields(self, api_auth_service, oauth_user, mock_auth_service):
        """Test that OAuth WA certificate has correct fields."""
        original_user_id = oauth_user.wa_id

        # Mint user as WA
        await api_auth_service.mint_wise_authority(
            user_id=original_user_id, wa_role=WARole.OBSERVER, minted_by="admin-user"
        )

        # Verify WA certificate fields
        mock_auth_service._store_wa_certificate.assert_called_once()
        wa_cert = mock_auth_service._store_wa_certificate.call_args[0][0]

        assert wa_cert.wa_id.startswith("wa-")  # Proper WA ID format
        assert wa_cert.name == "Eric Moore"
        assert wa_cert.role == WARole.OBSERVER
        assert wa_cert.pubkey == "oauth-google-110265575142761676421"
        assert wa_cert.jwt_kid.startswith("wa-jwt-oauth-")  # Proper format
        assert wa_cert.oauth_provider == "google"
        assert wa_cert.oauth_external_id == "110265575142761676421"
        assert wa_cert.auto_minted is True

        # Verify scopes are properly serialized
        import json

        scopes = json.loads(wa_cert.scopes_json)
        assert "wa.resolve_deferral" in scopes
        assert "wa.mint" in scopes

    @pytest.mark.asyncio
    async def test_existing_wa_update_path(self, api_auth_service, oauth_user, mock_auth_service):
        """Test that existing WA is updated instead of recreated."""
        original_user_id = oauth_user.wa_id

        # Mock existing WA with proper wa_id format
        existing_wa = WACertificate(
            wa_id="wa-2025-09-09-DEF456",  # Proper format
            name="Eric Moore",
            role=WARole.OBSERVER,
            pubkey="existing-key",
            jwt_kid="existing-kid",
            oauth_provider="google",
            oauth_external_id="110265575142761676421",
            auto_minted=True,
            scopes_json='["read:any"]',
            created_at=datetime.now(timezone.utc),
            last_auth=datetime.now(timezone.utc),
        )

        # Set up the existing WA to be found by user_id lookup
        mock_auth_service.get_wa.return_value = existing_wa
        mock_auth_service.update_wa = AsyncMock()

        # Mint user as WA (upgrade)
        await api_auth_service.mint_wise_authority(
            user_id=original_user_id, wa_role=WARole.AUTHORITY, minted_by="admin-user"
        )

        # Verify existing WA was updated, not recreated
        from ciris_engine.schemas.services.authority.wise_authority import WAUpdate

        mock_auth_service.update_wa.assert_called_once()
        call_args = mock_auth_service.update_wa.call_args
        assert call_args[0][0] == original_user_id  # First arg should be user_id
        assert call_args[1]["updates"].role == "authority"  # WAUpdate.role should be 'authority'
        mock_auth_service._store_wa_certificate.assert_not_called()

    @pytest.mark.asyncio
    async def test_non_oauth_user_behavior_unchanged(self, api_auth_service, mock_auth_service):
        """Test that non-OAuth users (password users) still work correctly."""
        from ciris_engine.logic.adapters.api.services.auth_service import User

        # Create password user (no ":" in wa_id)
        password_user = User(
            wa_id="password-user-123",
            name="Password User",
            auth_type="password",
            api_role=APIRole.ADMIN,
            wa_role=None,
            oauth_provider=None,
            oauth_email=None,
            oauth_external_id=None,
            created_at=datetime.now(timezone.utc),
            last_login=datetime.now(timezone.utc),
            is_active=True,
            oauth_name=None,
            oauth_picture=None,
            permission_requested_at=None,
            wa_parent_id=None,
            wa_auto_minted=False,
            password_hash="hashed_password",
            custom_permissions=None,
        )

        api_auth_service._users[password_user.wa_id] = password_user

        # Mint password user as WA
        await api_auth_service.mint_wise_authority(
            user_id=password_user.wa_id, wa_role=WARole.OBSERVER, minted_by="admin-user"
        )

        # Verify WA certificate for non-OAuth user
        mock_auth_service._store_wa_certificate.assert_called_once()
        wa_cert = mock_auth_service._store_wa_certificate.call_args[0][0]

        assert wa_cert.wa_id == "wa-2025-09-09-ABC123"  # Uses generated wa_id
        assert wa_cert.oauth_provider is None
        assert wa_cert.oauth_external_id is None
        assert wa_cert.pubkey == "password-user-123"  # Falls back to wa_id

    def test_wa_permissions_include_required_scopes(self, api_auth_service, oauth_user):
        """Test that WA permissions include required deferral and mint scopes."""
        permissions = api_auth_service._get_wa_permissions(oauth_user)

        # Should include base ADMIN permissions plus WA-specific permissions
        assert "wa.resolve_deferral" in permissions
        assert "wa.mint" in permissions

        # Should include base API permissions
        base_permissions = api_auth_service.get_permissions_for_role(APIRole.ADMIN)
        for perm in base_permissions:
            assert perm in permissions

    def test_wa_email_generation(self, api_auth_service):
        """Test WA email generation from name."""
        # Test normal name
        email1 = api_auth_service._create_wa_email("Eric Moore")
        assert email1 == "Eric Moore@ciris.local"

        # Test name that already has @
        email2 = api_auth_service._create_wa_email("john@example.com")
        assert email2 == "john@example.com"

        # Test single name
        email3 = api_auth_service._create_wa_email("Madonna")
        assert email3 == "Madonna@ciris.local"
