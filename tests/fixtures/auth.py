"""Centralized authentication fixtures for testing.

This module provides standardized auth fixtures that work with the
dynamically generated fallback admin password introduced for security.

SECURITY NOTE:
The fallback admin password is randomly generated at process start.
Tests must use these fixtures to get valid credentials.
The hardcoded 'ciris_admin_password' no longer works.
"""

import pytest
from typing import Dict


def get_test_admin_password() -> str:
    """Get the current test admin password.

    SECURITY: Returns the dynamically generated fallback password,
    not a hardcoded value. This password is valid only for the
    current process and is printed to stdout on first generation.
    """
    from ciris_engine.logic.adapters.api.services.auth_service import APIAuthService
    return APIAuthService._get_fallback_admin_password()


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
