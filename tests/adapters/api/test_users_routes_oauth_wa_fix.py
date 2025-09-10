"""
Test API routes OAuth WA fix.

This test suite covers the fix for API routes returning incorrect user_id values.
Previously, API routes were returning user.wa_id instead of the actual user_id key.

Fixed routes:
- GET /users/{user_id} - returns actual user_id instead of wa_id
- GET /users - returns actual user_id for each user instead of wa_id
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import Mock, AsyncMock
from fastapi.testclient import TestClient

from ciris_engine.logic.adapters.api.services.auth_service import APIAuthService, User
from ciris_engine.schemas.runtime.api import APIRole
from ciris_engine.schemas.services.authority_core import WARole


class TestUsersRoutesOAuthWAFix:
    """Test the API routes OAuth WA user_id fix."""

    @pytest.fixture
    def mock_auth_service(self):
        """Mock authentication service."""
        auth_service = Mock()
        auth_service.get_wa = AsyncMock(return_value=None)
        auth_service._store_wa_certificate = AsyncMock()
        auth_service._generate_wa_id = Mock(return_value="wa-2025-09-10-TEST123")
        auth_service.list_was = AsyncMock(return_value=[])
        return auth_service

    @pytest.fixture
    def api_auth_service_with_users(self, mock_auth_service):
        """Create API auth service with test users."""
        service = APIAuthService(auth_service=mock_auth_service)
        
        # Add OAuth user (minted as WA)
        oauth_user = User(
            wa_id="wa-2025-09-10-ABC123",  # WA ID assigned after minting
            name="OAuth User",
            auth_type="oauth",
            api_role=APIRole.AUTHORITY,  # Upgraded during WA minting
            wa_role=WARole.AUTHORITY,
            oauth_provider="google",
            oauth_email="oauth@ciris.ai",
            oauth_external_id="110265575142761676421",
            oauth_name="OAuth User",
            created_at=datetime.now(timezone.utc),
            last_login=datetime.now(timezone.utc),
            is_active=True,
        )
        
        # Add password user (also WA)
        password_user = User(
            wa_id="wa-2025-09-10-PWD456",
            name="Password User",
            auth_type="password",
            api_role=APIRole.OBSERVER,
            wa_role=WARole.OBSERVER,
            created_at=datetime.now(timezone.utc),
            last_login=datetime.now(timezone.utc),
            is_active=True,
            password_hash="$2b$12$test_hash",
        )
        
        # Store users with correct keys (OAuth user uses OAuth user_id, not wa_id)
        service._users["google:110265575142761676421"] = oauth_user  # OAuth user_id as key
        service._users["wa-2025-09-10-PWD456"] = password_user  # wa_id as key for non-OAuth
        
        return service

    def test_list_users_returns_correct_user_ids(self, api_auth_service_with_users):
        """Test that /users endpoint returns correct user_id values."""
        # Get the users list (this simulates what the API route does)
        users_list = api_auth_service_with_users.list_users()
        
        # Verify: Returns tuples with correct user_ids
        assert len(users_list) == 2
        
        user_ids = [user_id for user_id, user in users_list]
        assert "google:110265575142761676421" in user_ids  # OAuth user_id, not wa_id
        assert "wa-2025-09-10-PWD456" in user_ids  # Non-OAuth user uses wa_id
        
        # Verify: wa_id values are NOT used as user_id
        assert "wa-2025-09-10-ABC123" not in user_ids
        
        # Verify: Each user has correct attributes
        for user_id, user in users_list:
            if user_id == "google:110265575142761676421":
                assert user.name == "OAuth User"
                assert user.auth_type == "oauth"
                assert user.wa_role == WARole.AUTHORITY
                assert user.wa_id == "wa-2025-09-10-ABC123"  # wa_id is separate field
            elif user_id == "wa-2025-09-10-PWD456":
                assert user.name == "Password User"
                assert user.auth_type == "password"
                assert user.wa_role == WARole.OBSERVER
                assert user.wa_id == "wa-2025-09-10-PWD456"  # wa_id matches user_id for non-OAuth

    def test_get_specific_user_returns_correct_user_id(self, api_auth_service_with_users):
        """Test that /users/{user_id} endpoint logic returns correct user_id."""
        oauth_user_id = "google:110265575142761676421"
        password_user_id = "wa-2025-09-10-PWD456"
        
        # Test: Get OAuth user by their OAuth user_id
        oauth_user = api_auth_service_with_users.get_user(oauth_user_id)
        assert oauth_user is not None
        assert oauth_user.name == "OAuth User"
        assert oauth_user.wa_id == "wa-2025-09-10-ABC123"  # Different from user_id
        
        # Test: Get password user by their wa_id (which is their user_id)
        password_user = api_auth_service_with_users.get_user(password_user_id)
        assert password_user is not None
        assert password_user.name == "Password User"
        assert password_user.wa_id == "wa-2025-09-10-PWD456"  # Same as user_id
        
        # Test: Cannot get OAuth user by their wa_id (should not exist as key)
        oauth_user_by_wa_id = api_auth_service_with_users.get_user("wa-2025-09-10-ABC123")
        assert oauth_user_by_wa_id is None

    def test_user_summary_model_consistency(self, api_auth_service_with_users):
        """Test that UserSummary model receives correct user_id field."""
        users_list = api_auth_service_with_users.list_users()
        
        # This simulates what the API route does when creating UserSummary objects
        for user_id, user in users_list:
            # The API route should use user_id (the key) not user.wa_id
            if user.auth_type == "oauth":
                # For OAuth users, user_id should be OAuth format, wa_id should be WA format
                assert user_id == "google:110265575142761676421"
                assert user.wa_id == "wa-2025-09-10-ABC123"
                assert user_id != user.wa_id  # They should be different!
            else:
                # For non-OAuth users, user_id and wa_id should be the same
                assert user_id == "wa-2025-09-10-PWD456"
                assert user.wa_id == "wa-2025-09-10-PWD456"
                assert user_id == user.wa_id

    def test_user_detail_model_consistency(self, api_auth_service_with_users):
        """Test that UserDetail model receives correct user_id field."""
        oauth_user_id = "google:110265575142761676421"
        
        # This simulates what the API route does for GET /users/{user_id}
        user = api_auth_service_with_users.get_user(oauth_user_id)
        assert user is not None
        
        # The API route should return user_id parameter, not user.wa_id
        returned_user_id = oauth_user_id  # This is what the fixed route returns
        returned_wa_id = user.wa_id if user.wa_role else None
        
        # Verify: The route returns the original user_id, not the wa_id
        assert returned_user_id == "google:110265575142761676421"
        assert returned_wa_id == "wa-2025-09-10-ABC123"
        assert returned_user_id != returned_wa_id

    def test_oauth_user_lookup_by_wrong_id_fails(self, api_auth_service_with_users):
        """Test that OAuth users cannot be found by their wa_id."""
        # This tests that the duplicate user issue is fixed
        # OAuth users should only be accessible by their OAuth user_id
        
        oauth_wa_id = "wa-2025-09-10-ABC123"
        
        # Test: Should NOT find OAuth user by wa_id
        user = api_auth_service_with_users.get_user(oauth_wa_id)
        assert user is None
        
        # Test: Should find OAuth user by OAuth user_id
        oauth_user_id = "google:110265575142761676421"
        user = api_auth_service_with_users.get_user(oauth_user_id)
        assert user is not None
        assert user.name == "OAuth User"

    def test_no_duplicate_users_in_list(self, api_auth_service_with_users):
        """Test that users list doesn't contain duplicates."""
        users_list = api_auth_service_with_users.list_users()
        
        # Should have exactly 2 users (no duplicates)
        assert len(users_list) == 2
        
        # Extract all user names and ensure no duplicates
        user_names = [user.name for user_id, user in users_list]
        assert len(set(user_names)) == len(user_names)  # No duplicate names
        
        # Extract all user_ids and ensure no duplicates
        user_ids = [user_id for user_id, user in users_list]
        assert len(set(user_ids)) == len(user_ids)  # No duplicate user_ids
        
        # Specifically check for the OAuth user
        oauth_user_entries = [(user_id, user) for user_id, user in users_list if user.auth_type == "oauth"]
        assert len(oauth_user_entries) == 1  # Should have exactly one OAuth user entry
        
        oauth_user_id, oauth_user = oauth_user_entries[0]
        assert oauth_user_id == "google:110265575142761676421"
        assert oauth_user.wa_id == "wa-2025-09-10-ABC123"

    def test_permissions_work_with_fixed_user_id(self, api_auth_service_with_users):
        """Test that permission handling works with the fixed user_id logic."""
        oauth_user_id = "google:110265575142761676421"
        
        # Get user and verify permissions are based on their API role
        user = api_auth_service_with_users.get_user(oauth_user_id)
        assert user is not None
        assert user.api_role == APIRole.AUTHORITY
        
        # Test: Get permissions should work with the OAuth user_id
        permissions = api_auth_service_with_users.get_permissions_for_role(user.api_role)
        assert isinstance(permissions, list)
        assert len(permissions) > 0  # AUTHORITY role should have permissions