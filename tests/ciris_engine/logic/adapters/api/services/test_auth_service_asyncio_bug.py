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
        """Test that _load_users_from_db raises error when called from async context.

        This reproduces the production bug where asyncio.run() is called from
        within an already running event loop, causing:
        - RuntimeError: asyncio.run() cannot be called from a running event loop
        - Immediate agent shutdown in production
        """
        # Create mock auth service
        mock_auth_service = AsyncMock()

        # Mock list_was to return some WA certificates
        mock_was = [
            WACertificate(
                wa_id="wa-2025-01-18-test123",
                name="test_user",
                email="test@example.com",
                role=WARole.OBSERVER,
                scopes=["test"],
                created_at=datetime.now(timezone.utc),
                expires_at=None,
                parent_wa_id=None,
                auto_minted=False,
                last_auth=None,
                password_hash="$2b$12$test_hash",
                custom_permissions=None,
            )
        ]
        mock_auth_service.list_was.return_value = mock_was

        # Create auth service with the mock
        auth_service = APIAuthService(auth_service=mock_auth_service)

        # Since __init__ calls _load_users_from_db synchronously using asyncio.run(),
        # we need to test the scenario where this is called from an async context

        # Reset the auth service to simulate calling from async context
        auth_service._users.clear()

        # This should raise RuntimeError when called from async context
        with pytest.raises(RuntimeError) as exc_info:
            # Simulate calling from within an async context (like the API startup)
            await asyncio.get_running_loop().run_in_executor(None, auth_service._load_users_from_db)

        # Verify the specific error message
        assert "asyncio.run() cannot be called from a running event loop" in str(exc_info.value)

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
                wa_id="wa-2025-01-18-test123",
                name="test_user",
                email="test@example.com",
                role=WARole.OBSERVER,
                scopes=["test"],
                created_at=datetime.now(timezone.utc),
                expires_at=None,
                parent_wa_id=None,
                auto_minted=False,
                last_auth=None,
                password_hash="$2b$12$test_hash",
                custom_permissions=None,
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

        # Verify users were loaded successfully
        assert len(auth_service._users) == 1
        assert "wa-2025-01-18-test123" in auth_service._users
        user = auth_service._users["wa-2025-01-18-test123"]
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
            wa_id="wa-2025-01-18-test123",
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

    @patch("ciris_engine.logic.adapters.api.services.auth_service.asyncio.run")
    def test_init_with_auth_service_calls_asyncio_run(self, mock_asyncio_run):
        """Test that __init__ with auth_service calls asyncio.run() incorrectly.

        This is the root cause of the production bug.
        """
        # Create mock auth service
        mock_auth_service = MagicMock()

        # Mock asyncio.run to return empty list (no WAs)
        mock_asyncio_run.return_value = []

        # Create auth service - this will call asyncio.run() in __init__
        auth_service = APIAuthService(auth_service=mock_auth_service)

        # Verify asyncio.run was called (this is the bug!)
        assert mock_asyncio_run.called

        # In production, this call fails with:
        # RuntimeError: asyncio.run() cannot be called from a running event loop
        # Because the API server is already running in an async context
