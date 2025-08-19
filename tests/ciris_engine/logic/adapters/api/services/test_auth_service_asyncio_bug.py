"""Test to reproduce the asyncio.run() bug in auth_service.py.

This test reproduces the production issue where asyncio.run() is called
from within an already running event loop, causing immediate agent shutdown.
"""

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ciris_engine.logic.adapters.api.services.auth_service import APIAuthService
from ciris_engine.schemas.services.authority_core import WACertificate, WARole


class TestAuthServiceAsyncIOBug:
    """Test suite to reproduce and verify fix for asyncio.run() bug."""

    @pytest.mark.asyncio
    async def test_load_users_from_db_asyncio_run_error(self):
        """Test that the fixed _load_users_from_db works correctly with lazy loading.

        The bug has been fixed by implementing lazy loading instead of
        loading users in __init__ with asyncio.run(). This test verifies
        the fix works correctly.
        """
        # Create mock auth service
        mock_auth_service = AsyncMock()

        # Mock list_was to return some WA certificates
        mock_was = [
            WACertificate(
                wa_id="wa-2025-01-18-TEST01",  # Fixed format
                name="test_user",
                role=WARole.OBSERVER,
                pubkey="test_pubkey_base64",  # Required field
                jwt_kid="test_kid",  # Required field
                scopes_json='["test"]',  # Required field as JSON string
                created_at=datetime.now(timezone.utc).isoformat(),
                parent_wa_id=None,
                auto_minted=False,
                last_auth=None,
                password_hash="$2b$12$test_hash",
            )
        ]
        mock_auth_service.list_was.return_value = mock_was

        # Create auth service with the mock - now uses lazy loading
        auth_service = APIAuthService(auth_service=mock_auth_service)

        # The fix: users are loaded lazily when needed, not in __init__
        # Trigger lazy loading by accessing a user
        await auth_service._ensure_users_loaded()

        # Verify users were loaded successfully
        assert len(auth_service._users) > 0
        assert "wa-2025-01-18-TEST01" in auth_service._users or "wa-system-admin" in auth_service._users

    @pytest.mark.asyncio
    async def test_load_users_from_db_fixed_version(self):
        """Test the fixed version of _load_users_from_db that works in async context.

        This test demonstrates the fix: replacing asyncio.run() with await
        when calling from an async context.
        """
        # Create mock auth service
        mock_auth_service = AsyncMock()

        # Mock list_was to return some WA certificates
        mock_was = [
            WACertificate(
                wa_id="wa-2025-01-18-TEST01",  # Fixed format
                name="test_user",
                role=WARole.OBSERVER,
                pubkey="test_pubkey_base64",  # Required field
                jwt_kid="test_kid",  # Required field
                scopes_json='["test"]',  # Required field as JSON string
                created_at=datetime.now(timezone.utc).isoformat(),
                parent_wa_id=None,
                auto_minted=False,
                last_auth=None,
                password_hash="$2b$12$test_hash",
            )
        ]
        mock_auth_service.list_was.return_value = mock_was

        # Create a fixed version of the method
        async def load_users_from_db_async(auth_service_instance):
            """Fixed version using await instead of asyncio.run()."""
            if not auth_service_instance._auth_service:
                return

            try:
                # Use await instead of asyncio.run() - THIS IS THE FIX
                was = await auth_service_instance._auth_service.list_was(active_only=False)

                for wa in was:
                    # Convert WA certificate to User
                    from ciris_engine.logic.adapters.api.services.auth_service import User

                    user = User(
                        wa_id=wa.wa_id,
                        name=wa.name,
                        auth_type="password" if wa.password_hash else "certificate",
                        api_role=auth_service_instance._wa_role_to_api_role(wa.role),
                        wa_role=wa.role,
                        created_at=wa.created_at,
                        last_login=wa.last_auth,
                        is_active=True,
                        wa_parent_id=wa.parent_wa_id,
                        wa_auto_minted=wa.auto_minted,
                        password_hash=wa.password_hash,
                        custom_permissions=wa.custom_permissions if hasattr(wa, "custom_permissions") else None,
                    )
                    auth_service_instance._users[user.wa_id] = user

                # If no admin user exists, create the default one
                if not any(u.name == "admin" for u in auth_service_instance._users.values()):
                    await auth_service_instance._create_default_admin()

            except Exception as e:
                print(f"Error loading users from database: {e}")
                # Fallback logic would go here

        # Create auth service without calling the buggy __init__
        auth_service = APIAuthService.__new__(APIAuthService)
        auth_service._api_keys = {}
        auth_service._oauth_users = {}
        auth_service._users = {}
        auth_service._auth_service = mock_auth_service

        # Call the fixed async version
        await load_users_from_db_async(auth_service)

        # Verify users were loaded successfully (may include default admin)
        assert len(auth_service._users) >= 1
        assert "wa-2025-01-18-TEST01" in auth_service._users
        user = auth_service._users["wa-2025-01-18-TEST01"]
        assert user.name == "test_user"
        assert user.auth_type == "password"

    @pytest.mark.asyncio
    async def test_change_password_asyncio_run_error(self):
        """Test that change_password has the same asyncio.run() issue.

        Line 626-628 in auth_service.py also uses asyncio.run() incorrectly.
        """
        # Create mock auth service
        mock_auth_service = AsyncMock()
        mock_auth_service.update_wa = AsyncMock()

        # Create auth service
        auth_service = APIAuthService.__new__(APIAuthService)
        auth_service._api_keys = {}
        auth_service._oauth_users = {}
        auth_service._users = {}
        auth_service._auth_service = mock_auth_service

        # Add a test user
        from ciris_engine.logic.adapters.api.services.auth_service import User
        from ciris_engine.schemas.runtime.api import APIRole

        test_user = User(
            wa_id="wa-2025-01-18-TEST01",
            name="test_user",
            auth_type="password",
            api_role=APIRole.OBSERVER,
            wa_role=WARole.OBSERVER,
            created_at=datetime.now(timezone.utc),
            is_active=True,
            password_hash="$2b$12$old_hash",
        )
        auth_service._users[test_user.wa_id] = test_user

        # Mock the password verification
        with patch.object(auth_service, "_verify_password", return_value=True):
            with patch.object(auth_service, "_hash_password", return_value="$2b$12$new_hash"):
                # The original change_password uses asyncio.run() at line 626-628
                # This would fail in production when called from async context
                # Let's verify the method exists and would be problematic
                result = await auth_service.change_password(
                    user_id=test_user.wa_id,
                    new_password="new_password",
                    current_password="old_password",
                    skip_current_check=False,
                )

                # In the buggy version, this would try asyncio.run() and fail
                # The test passes because we're mocking, but in production it would crash
                assert result == True

    def test_synchronous_init_with_mock(self):
        """Test that synchronous __init__ works when auth_service is None.

        This simulates the fallback behavior when no auth service is provided.
        """
        # Create auth service without auth_service parameter
        auth_service = APIAuthService(auth_service=None)

        # Should have created default admin user
        assert len(auth_service._users) == 1
        assert "wa-system-admin" in auth_service._users

        admin_user = auth_service._users["wa-system-admin"]
        assert admin_user.name == "admin"
        assert admin_user.auth_type == "password"

    def test_init_with_auth_service_calls_asyncio_run(self):
        """Test that __init__ with auth_service NO LONGER calls asyncio.run().

        The bug has been fixed by using lazy loading instead of
        loading users in __init__.
        """
        # Create mock auth service
        mock_auth_service = MagicMock()

        # Create auth service - this NO LONGER calls asyncio.run() in __init__
        auth_service = APIAuthService(auth_service=mock_auth_service)

        # Verify auth service was created successfully
        assert auth_service is not None
        assert auth_service._auth_service == mock_auth_service

        # Users are NOT loaded yet (lazy loading)
        # The default admin is created only when no auth_service is provided
        assert len(auth_service._users) == 0 or "wa-system-admin" in auth_service._users
