"""
Test OAuth WA minting duplicate user fix.

This test suite covers the fix for the issue where OAuth users
who get minted as WAs would create duplicate user records.

Fixed Components:
1. _load_users_from_db() - prevents duplicate OAuth WA records
2. list_users() - returns (user_id, user) tuples with correct user_ids
3. API endpoints - return proper user_id instead of wa_id
"""

from datetime import datetime, timezone
from typing import List, Tuple
from unittest.mock import AsyncMock, Mock

import pytest

from ciris_engine.logic.adapters.api.services.auth_service import APIAuthService, User
from ciris_engine.schemas.runtime.api import APIRole
from ciris_engine.schemas.services.authority_core import WACertificate, WARole


class TestAuthServiceOAuthWAFix:
    """Test the OAuth WA duplicate user fix."""

    @pytest.fixture
    def mock_auth_service(self):
        """Mock authentication service."""
        auth_service = Mock()
        auth_service.get_wa = AsyncMock(return_value=None)
        auth_service._store_wa_certificate = AsyncMock()
        auth_service._generate_wa_id = Mock(return_value="wa-2025-09-10-T123AB")
        auth_service.list_was = AsyncMock(return_value=[])
        return auth_service

    @pytest.fixture
    def api_auth_service(self, mock_auth_service):
        """Create API auth service with mocked dependencies."""
        service = APIAuthService(auth_service=mock_auth_service)
        return service

    @pytest.fixture
    def oauth_user(self):
        """Create OAuth user for testing."""
        return User(
            wa_id="google:110265575142761676421",
            name="Test User",
            auth_type="oauth",
            api_role=APIRole.ADMIN,
            wa_role=None,
            oauth_provider="google",
            oauth_email="test@ciris.ai",
            oauth_external_id="110265575142761676421",
            oauth_name="Test User",
            created_at=datetime.now(timezone.utc),
            last_login=datetime.now(timezone.utc),
            is_active=True,
        )

    @pytest.fixture
    def oauth_wa_certificate(self):
        """Create OAuth-linked WA certificate for testing."""
        return WACertificate(
            wa_id="wa-2025-09-10-T123AB",
            name="Test User",
            role=WARole.AUTHORITY,
            pubkey="oauth-google-110265575142761676421",
            jwt_kid="wa-jwt-oauth-test123",
            oauth_provider="google",
            oauth_external_id="110265575142761676421",
            auto_minted=True,
            scopes_json='["wa.resolve_deferral", "wa.mint"]',
            created_at=datetime.now(timezone.utc),
            last_auth=datetime.now(timezone.utc),
        )

    @pytest.fixture
    def non_oauth_wa_certificate(self):
        """Create non-OAuth WA certificate for testing."""
        return WACertificate(
            wa_id="wa-2025-09-10-P123AB",
            name="Password User",
            role=WARole.OBSERVER,
            pubkey="password-user-123",
            jwt_kid="wa-jwt-pwd-123",
            oauth_provider=None,
            oauth_external_id=None,
            auto_minted=False,
            scopes_json='["wa.read"]',
            created_at=datetime.now(timezone.utc),
            last_auth=datetime.now(timezone.utc),
            password_hash="$2b$12$test_hash",
        )

    @pytest.mark.asyncio
    async def test_load_users_from_db_oauth_wa_no_duplicates(
        self, api_auth_service, oauth_user, oauth_wa_certificate, mock_auth_service
    ):
        """Test that _load_users_from_db stores OAuth WAs under both WA ID and OAuth keys."""
        # Setup: Add OAuth user first (simulates user creation during OAuth login)
        oauth_user_id = "google:110265575142761676421"
        api_auth_service._users[oauth_user_id] = oauth_user

        # Setup: Mock list_was to return OAuth WA certificate
        mock_auth_service.list_was.return_value = [oauth_wa_certificate]

        # Test: Load users from database
        await api_auth_service._load_users_from_db()

        # Verify: Should have user stored under BOTH keys (WA ID and OAuth key) pointing to same User object
        assert len(api_auth_service._users) == 2  # Both wa_id and oauth keys point to same user
        assert oauth_user_id in api_auth_service._users
        assert "wa-2025-09-10-T123AB" in api_auth_service._users

        # Verify: Both keys point to the same user object
        assert api_auth_service._users[oauth_user_id] is api_auth_service._users["wa-2025-09-10-T123AB"]

        # Verify: OAuth user record is updated with WA information
        updated_user = api_auth_service._users[oauth_user_id]
        assert updated_user.wa_role == WARole.AUTHORITY
        assert updated_user.wa_id == "wa-2025-09-10-T123AB"
        assert updated_user.wa_auto_minted == True
        assert updated_user.api_role == APIRole.AUTHORITY  # Should be upgraded

    @pytest.mark.asyncio
    async def test_load_users_from_db_oauth_wa_without_existing_user(
        self, api_auth_service, oauth_wa_certificate, mock_auth_service
    ):
        """Test that _load_users_from_db creates user under both OAuth and WA ID keys."""
        # Setup: Mock list_was to return OAuth WA certificate, no existing user
        mock_auth_service.list_was.return_value = [oauth_wa_certificate]

        # Test: Load users from database
        await api_auth_service._load_users_from_db()

        # Verify: Should create user with BOTH OAuth key and WA ID key
        oauth_user_id = "google:110265575142761676421"
        assert len(api_auth_service._users) == 2  # Both keys present
        assert oauth_user_id in api_auth_service._users
        assert "wa-2025-09-10-T123AB" in api_auth_service._users  # WA ID key also present

        # Verify: Both keys point to same user object
        assert api_auth_service._users[oauth_user_id] is api_auth_service._users["wa-2025-09-10-T123AB"]

        # Verify: User has correct WA information
        user = api_auth_service._users[oauth_user_id]
        assert user.wa_role == WARole.AUTHORITY
        assert user.wa_id == "wa-2025-09-10-T123AB"
        assert user.oauth_provider == "google"
        assert user.oauth_external_id == "110265575142761676421"

    @pytest.mark.asyncio
    async def test_load_users_from_db_non_oauth_wa_uses_wa_id_key(
        self, api_auth_service, non_oauth_wa_certificate, mock_auth_service
    ):
        """Test that _load_users_from_db uses wa_id as key for non-OAuth WAs."""
        # Setup: Mock list_was to return non-OAuth WA certificate
        mock_auth_service.list_was.return_value = [non_oauth_wa_certificate]

        # Test: Load users from database
        await api_auth_service._load_users_from_db()

        # Verify: Should create user with wa_id as key (traditional behavior)
        wa_id = "wa-2025-09-10-P123AB"
        assert len(api_auth_service._users) == 1
        assert wa_id in api_auth_service._users

        # Verify: User has correct information
        user = api_auth_service._users[wa_id]
        assert user.wa_role == WARole.OBSERVER
        assert user.wa_id == wa_id
        assert user.oauth_provider is None
        assert user.oauth_external_id is None

    @pytest.mark.asyncio
    async def test_load_users_from_db_mixed_oauth_and_non_oauth(
        self, api_auth_service, oauth_user, oauth_wa_certificate, non_oauth_wa_certificate, mock_auth_service
    ):
        """Test that _load_users_from_db handles mixed OAuth and non-OAuth WAs correctly."""
        # Setup: Add OAuth user first
        oauth_user_id = "google:110265575142761676421"
        api_auth_service._users[oauth_user_id] = oauth_user

        # Setup: Mock list_was to return both types of certificates
        mock_auth_service.list_was.return_value = [oauth_wa_certificate, non_oauth_wa_certificate]

        # Test: Load users from database
        await api_auth_service._load_users_from_db()

        # Verify: Should have 3 keys (OAuth WA has 2 keys: wa_id + oauth key, non-OAuth has 1 key: wa_id)
        assert len(api_auth_service._users) == 3
        assert oauth_user_id in api_auth_service._users  # OAuth user OAuth key
        assert "wa-2025-09-10-T123AB" in api_auth_service._users  # OAuth user WA ID key
        assert "wa-2025-09-10-P123AB" in api_auth_service._users  # Non-OAuth user uses wa_id

        # Verify: OAuth user keys point to same object
        assert api_auth_service._users[oauth_user_id] is api_auth_service._users["wa-2025-09-10-T123AB"]

        # Verify: OAuth user updated correctly
        oauth_user_record = api_auth_service._users[oauth_user_id]
        assert oauth_user_record.wa_role == WARole.AUTHORITY
        assert oauth_user_record.wa_id == "wa-2025-09-10-T123AB"

        # Verify: Non-OAuth user created correctly
        non_oauth_user_record = api_auth_service._users["wa-2025-09-10-P123AB"]
        assert non_oauth_user_record.wa_role == WARole.OBSERVER
        assert non_oauth_user_record.wa_id == "wa-2025-09-10-P123AB"

    @pytest.mark.asyncio
    async def test_list_users_returns_tuples_with_correct_user_ids(self, api_auth_service):
        """Test that list_users returns (user_id, user) tuples with correct user_ids."""
        # Setup: Add users with different key types
        oauth_user = User(
            wa_id="google:12345",
            name="OAuth User",
            auth_type="oauth",
            api_role=APIRole.ADMIN,
            wa_role=WARole.AUTHORITY,
            created_at=datetime.now(timezone.utc),
        )

        password_user = User(
            wa_id="wa-2025-09-10-PWD456",
            name="Password User",
            auth_type="password",
            api_role=APIRole.OBSERVER,
            wa_role=WARole.OBSERVER,
            created_at=datetime.now(timezone.utc),
        )

        api_auth_service._users["google:12345"] = oauth_user
        api_auth_service._users["wa-2025-09-10-PWD456"] = password_user
        api_auth_service._users_loaded = True  # Mark as loaded to skip DB load

        # Test: List users
        result = await api_auth_service.list_users()

        # Verify: Returns list of tuples
        assert isinstance(result, list)
        assert len(result) == 2
        assert all(isinstance(item, tuple) and len(item) == 2 for item in result)

        # Verify: Tuples contain correct (user_id, user) pairs
        user_ids = [user_id for user_id, user in result]
        assert "google:12345" in user_ids
        assert "wa-2025-09-10-PWD456" in user_ids

        # Verify: Users are returned with their correct keys
        for user_id, user in result:
            if user_id == "google:12345":
                assert user.name == "OAuth User"
                assert user.auth_type == "oauth"
            elif user_id == "wa-2025-09-10-PWD456":
                assert user.name == "Password User"
                assert user.auth_type == "password"

    @pytest.mark.asyncio
    async def test_list_users_filtering_works_with_tuples(self, api_auth_service):
        """Test that list_users filtering still works with tuple return format."""
        # Setup: Add users with different attributes
        oauth_admin = User(
            wa_id="google:admin",
            name="Admin User",
            auth_type="oauth",
            api_role=APIRole.ADMIN,
            wa_role=WARole.AUTHORITY,
            created_at=datetime.now(timezone.utc),
            is_active=True,
        )

        password_observer = User(
            wa_id="wa-observer",
            name="Observer User",
            auth_type="password",
            api_role=APIRole.OBSERVER,
            wa_role=WARole.OBSERVER,
            created_at=datetime.now(timezone.utc),
            is_active=False,
        )

        api_auth_service._users["google:admin"] = oauth_admin
        api_auth_service._users["wa-observer"] = password_observer
        api_auth_service._users_loaded = True  # Mark as loaded to skip DB load

        # Test: Filter by auth_type
        oauth_result = await api_auth_service.list_users(auth_type="oauth")
        assert len(oauth_result) == 1
        assert oauth_result[0][0] == "google:admin"  # user_id
        assert oauth_result[0][1].auth_type == "oauth"  # user

        # Test: Filter by api_role
        admin_result = await api_auth_service.list_users(api_role=APIRole.ADMIN)
        assert len(admin_result) == 1
        assert admin_result[0][0] == "google:admin"

        # Test: Filter by is_active
        active_result = await api_auth_service.list_users(is_active=True)
        assert len(active_result) == 1
        assert active_result[0][0] == "google:admin"

        inactive_result = await api_auth_service.list_users(is_active=False)
        assert len(inactive_result) == 1
        assert inactive_result[0][0] == "wa-observer"

    @pytest.mark.asyncio
    async def test_list_users_search_functionality(self, api_auth_service):
        """Test that list_users search functionality works with tuple format."""
        # Setup: Add users with searchable names
        user1 = User(
            wa_id="google:john",
            name="John Smith",
            auth_type="oauth",
            api_role=APIRole.ADMIN,
            created_at=datetime.now(timezone.utc),
        )

        user2 = User(
            wa_id="wa-jane",
            name="Jane Doe",
            auth_type="password",
            api_role=APIRole.OBSERVER,
            created_at=datetime.now(timezone.utc),
        )

        api_auth_service._users["google:john"] = user1
        api_auth_service._users["wa-jane"] = user2
        api_auth_service._users_loaded = True  # Mark as loaded to skip DB load

        # Test: Search by name
        john_result = await api_auth_service.list_users(search="john")
        assert len(john_result) == 1
        assert john_result[0][0] == "google:john"
        assert john_result[0][1].name == "John Smith"

        smith_result = await api_auth_service.list_users(search="Smith")
        assert len(smith_result) == 1
        assert smith_result[0][0] == "google:john"

        # Test: Search is case-insensitive
        JANE_result = await api_auth_service.list_users(search="JANE")
        assert len(JANE_result) == 1
        assert JANE_result[0][0] == "wa-jane"
        assert JANE_result[0][1].name == "Jane Doe"

    @pytest.mark.asyncio
    async def test_list_users_sorting_by_created_at(self, api_auth_service):
        """Test that list_users sorting by created_at works with tuple format."""
        # Setup: Add users with different creation times
        older_time = datetime(2025, 1, 1, tzinfo=timezone.utc)
        newer_time = datetime(2025, 9, 10, tzinfo=timezone.utc)

        older_user = User(
            wa_id="google:older",
            name="Older User",
            auth_type="oauth",
            api_role=APIRole.ADMIN,
            created_at=older_time,
        )

        newer_user = User(
            wa_id="wa-newer",
            name="Newer User",
            auth_type="password",
            api_role=APIRole.OBSERVER,
            created_at=newer_time,
        )

        api_auth_service._users["google:older"] = older_user
        api_auth_service._users["wa-newer"] = newer_user
        api_auth_service._users_loaded = True  # Mark as loaded to skip DB load

        # Test: Users should be sorted by created_at, newest first
        result = await api_auth_service.list_users()
        assert len(result) == 2

        # First user should be the newer one
        assert result[0][0] == "wa-newer"
        assert result[0][1].name == "Newer User"

        # Second user should be the older one
        assert result[1][0] == "google:older"
        assert result[1][1].name == "Older User"

    @pytest.mark.asyncio
    async def test_list_users_loads_from_database_when_not_loaded(
        self, api_auth_service, oauth_wa_certificate, mock_auth_service
    ):
        """Test that list_users loads from database when users haven't been loaded yet."""
        # Setup: Mock list_was to return OAuth WA certificate
        mock_auth_service.list_was.return_value = [oauth_wa_certificate]

        # Verify: Initially _users_loaded is False and _users is empty
        assert api_auth_service._users_loaded is False
        assert len(api_auth_service._users) == 0

        # Test: Call list_users (should trigger database load)
        result = await api_auth_service.list_users()

        # Verify: Database was loaded
        assert api_auth_service._users_loaded is True

        # Verify: Users were populated from database
        oauth_user_id = "google:110265575142761676421"
        assert len(api_auth_service._users) == 2  # OAuth key + WA ID key
        assert oauth_user_id in api_auth_service._users
        assert "wa-2025-09-10-T123AB" in api_auth_service._users

        # Verify: Result contains the loaded user (returned with both keys)
        assert len(result) == 2  # Both keys are returned (wa_id and oauth key)
        user_ids = [user_id for user_id, user in result]
        assert oauth_user_id in user_ids
        assert "wa-2025-09-10-T123AB" in user_ids

        # Verify: Both entries point to the same user object with correct data
        for user_id, user in result:
            assert user.name == "Test User"
            assert user.wa_role == WARole.AUTHORITY
            assert user.wa_id == "wa-2025-09-10-T123AB"

    def test_authority_role_includes_wa_resolve_deferral_permission(self, api_auth_service):
        """Test that AUTHORITY role includes wa.resolve_deferral permission for deferral resolution."""
        # Test: Get permissions for AUTHORITY role
        authority_permissions = api_auth_service.get_permissions_for_role(APIRole.AUTHORITY)

        # Verify: wa.resolve_deferral is included
        assert "wa.resolve_deferral" in authority_permissions

        # Verify: Other expected WA permissions are also included
        assert "wa.read" in authority_permissions
        assert "wa.write" in authority_permissions

        # Verify: Basic authority permissions are included
        assert "system.read" in authority_permissions
        assert "system.write" in authority_permissions
        assert "users.read" in authority_permissions

        # Test: Ensure OBSERVER role does not have wa.resolve_deferral
        observer_permissions = api_auth_service.get_permissions_for_role(APIRole.OBSERVER)
        assert "wa.resolve_deferral" not in observer_permissions

        # Test: Ensure ADMIN role does not have wa.resolve_deferral (only AUTHORITY+ should)
        admin_permissions = api_auth_service.get_permissions_for_role(APIRole.ADMIN)
        assert "wa.resolve_deferral" not in admin_permissions
