"""Centralized authentication fixtures for testing.

This module provides standardized auth fixtures that work with the
QA test admin password created by the setup wizard.

NOTE:
The QA runner always wipes data and uses the setup wizard to create
an admin user with the known test password 'qa_test_password_12345'.

For unit tests using TestClient (which don't go through the setup wizard),
use the `setup_test_admin_user()` function to populate the auth service
with a test admin user.
"""

import base64
import secrets
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Dict

import pytest

if TYPE_CHECKING:
    from ciris_engine.logic.adapters.api.services.auth_service import APIAuthService

# Known test password used by QA runner's setup wizard
QA_TEST_PASSWORD = "qa_test_password_12345"


def _hash_password(password: str) -> str:
    """Hash a password using PBKDF2 (same as auth_service)."""
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

    salt = secrets.token_bytes(32)
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=100000,
    )
    key = kdf.derive(password.encode())
    return base64.b64encode(salt + key).decode()


def setup_test_admin_user(auth_service: "APIAuthService") -> None:
    """Set up a test admin user in the auth service.

    This function populates the auth service's in-memory user cache
    with a test admin user. Use this in test fixtures when tests
    don't go through the setup wizard (e.g., unit tests with TestClient).

    The admin user is created with SYSTEM_ADMIN role to match the
    original fallback admin behavior and provide full permissions.

    Args:
        auth_service: The APIAuthService instance to populate
    """
    from ciris_engine.logic.adapters.api.services.auth_service import User
    from ciris_engine.schemas.runtime.api import APIRole
    from ciris_engine.schemas.services.authority_core import WARole

    # Create admin user with known password
    # Use consistent ID to match expected test assertions
    user_id = "wa-system-admin"
    admin_user = User(
        wa_id=user_id,
        name="admin",
        auth_type="password",
        api_role=APIRole.SYSTEM_ADMIN,  # Full permissions for tests
        wa_role=WARole.ROOT,
        created_at=datetime.now(timezone.utc),
        is_active=True,
        password_hash=_hash_password(QA_TEST_PASSWORD),
    )

    # Add to auth service's user cache
    auth_service._users[user_id] = admin_user
    # Mark as loaded to prevent DB reload attempts
    auth_service._users_loaded = True


def get_test_admin_password() -> str:
    """Get the test admin password.

    Returns the known QA test password used by the setup wizard.
    """
    return QA_TEST_PASSWORD


def get_test_admin_credentials() -> tuple[str, str]:
    """Get admin username and password for testing.

    Returns:
        Tuple of (username, password)
    """
    return ("admin", get_test_admin_password())


@pytest.fixture
def test_admin_password() -> str:
    """Get the dynamically generated admin password for tests.

    Use this when you need just the password value.
    """
    return get_test_admin_password()


@pytest.fixture
def test_admin_credentials() -> tuple[str, str]:
    """Get admin credentials as (username, password) tuple.

    Use this when you need both username and password.
    """
    return get_test_admin_credentials()


@pytest.fixture
def auth_headers() -> Dict[str, str]:
    """Get Bearer auth headers using dev credentials.

    Uses the username:password format supported in dev mode.
    This is the recommended fixture for most API tests.
    """
    username, password = get_test_admin_credentials()
    return {"Authorization": f"Bearer {username}:{password}"}


@pytest.fixture
def admin_auth_headers() -> Dict[str, str]:
    """Alias for auth_headers - admin-level auth headers.

    Provides same credentials as auth_headers, named explicitly
    for tests that distinguish between admin and other roles.
    """
    username, password = get_test_admin_credentials()
    return {"Authorization": f"Bearer {username}:{password}"}


@pytest.fixture
def observer_auth_headers() -> Dict[str, str]:
    """Get observer-level auth headers.

    NOTE: Currently uses same admin credentials since observer
    accounts require database setup. Tests should mock role
    checks if they need to test observer-specific behavior.
    """
    username, password = get_test_admin_credentials()
    return {"Authorization": f"Bearer {username}:{password}"}


def make_login_request(client, username: str = None, password: str = None) -> Dict[str, str]:
    """Helper to perform login and return auth headers.

    Args:
        client: TestClient instance
        username: Username (defaults to admin)
        password: Password (defaults to dynamic fallback password)

    Returns:
        Auth headers dict with Bearer token

    Raises:
        AssertionError: If login fails
    """
    if username is None:
        username = "admin"
    if password is None:
        password = get_test_admin_password()

    response = client.post(
        "/v1/auth/login",
        json={"username": username, "password": password}
    )
    assert response.status_code == 200, f"Login failed: {response.json()}"
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def login_auth_headers(client):
    """Get auth headers via actual login endpoint.

    Use this fixture when you need a real JWT token instead of
    the dev-mode username:password format.

    Requires 'client' fixture to be available.
    """
    return make_login_request(client)


# Re-export for convenience
__all__ = [
    "QA_TEST_PASSWORD",
    "setup_test_admin_user",
    "get_test_admin_password",
    "get_test_admin_credentials",
    "test_admin_password",
    "test_admin_credentials",
    "auth_headers",
    "admin_auth_headers",
    "observer_auth_headers",
    "make_login_request",
    "login_auth_headers",
]
