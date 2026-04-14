"""Tests for the setup LLM route authentication gates.

Focus: ``/start-local-server`` spawns a background subprocess. After setup
completes it must NOT be callable by plain observers — only admins (and
the setup wizard during first-run) may trigger it.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest import mock

import pytest
from fastapi import HTTPException

from ciris_engine.logic.adapters.api.routes.setup.llm_routes import (
    _require_setup_or_admin,
    _require_setup_or_auth,
)
from ciris_engine.schemas.api.auth import AuthContext, UserRole


def _fake_auth_context(role: UserRole) -> AuthContext:
    return AuthContext(
        user_id="test-user",
        role=role,
        permissions=set(),
        api_key_id=None,
        authenticated_at=datetime.now(timezone.utc),
    )


def _fake_request_with_auth_header() -> mock.MagicMock:
    request = mock.MagicMock()
    request.headers = {"Authorization": "Bearer test-token"}
    request.app.state.auth_service = mock.MagicMock()
    return request


@pytest.mark.asyncio
class TestRequireSetupOrAdmin:
    async def test_allows_during_first_run_without_auth(self) -> None:
        """During setup the wizard runs without credentials."""
        request = mock.MagicMock()
        with mock.patch(
            "ciris_engine.logic.adapters.api.routes.setup.llm_routes._is_setup_allowed_without_auth",
            return_value=True,
        ):
            # Should not raise — first-run bypass keeps the wizard working.
            await _require_setup_or_admin(request)

    async def test_rejects_observer_post_setup(self) -> None:
        """Non-admin users must be blocked once setup is complete."""
        request = _fake_request_with_auth_header()
        with mock.patch(
            "ciris_engine.logic.adapters.api.routes.setup.llm_routes._is_setup_allowed_without_auth",
            return_value=False,
        ), mock.patch(
            "ciris_engine.logic.adapters.api.dependencies.auth.get_auth_context",
            new=mock.AsyncMock(return_value=_fake_auth_context(UserRole.OBSERVER)),
        ), mock.patch(
            "ciris_engine.logic.adapters.api.dependencies.auth.get_auth_service",
            return_value=mock.MagicMock(),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await _require_setup_or_admin(request)
            assert exc_info.value.status_code == 403
            assert "admin" in exc_info.value.detail.lower()

    async def test_allows_admin_post_setup(self) -> None:
        request = _fake_request_with_auth_header()
        with mock.patch(
            "ciris_engine.logic.adapters.api.routes.setup.llm_routes._is_setup_allowed_without_auth",
            return_value=False,
        ), mock.patch(
            "ciris_engine.logic.adapters.api.dependencies.auth.get_auth_context",
            new=mock.AsyncMock(return_value=_fake_auth_context(UserRole.ADMIN)),
        ), mock.patch(
            "ciris_engine.logic.adapters.api.dependencies.auth.get_auth_service",
            return_value=mock.MagicMock(),
        ):
            # Admin is permitted — should not raise.
            await _require_setup_or_admin(request)

    async def test_allows_higher_privilege_roles(self) -> None:
        """AUTHORITY / SYSTEM_ADMIN inherit admin permissions via has_permission."""
        request = _fake_request_with_auth_header()
        for role in (UserRole.AUTHORITY, UserRole.SYSTEM_ADMIN):
            with mock.patch(
                "ciris_engine.logic.adapters.api.routes.setup.llm_routes._is_setup_allowed_without_auth",
                return_value=False,
            ), mock.patch(
                "ciris_engine.logic.adapters.api.dependencies.auth.get_auth_context",
                new=mock.AsyncMock(return_value=_fake_auth_context(role)),
            ), mock.patch(
                "ciris_engine.logic.adapters.api.dependencies.auth.get_auth_service",
                return_value=mock.MagicMock(),
            ):
                await _require_setup_or_admin(request)


@pytest.mark.asyncio
class TestRequireSetupOrAuth:
    async def test_accepts_observer_post_setup(self) -> None:
        """The weaker ``SetupOrAuth`` guard still admits observers — only the
        admin-only variant restricts them."""
        request = _fake_request_with_auth_header()
        with mock.patch(
            "ciris_engine.logic.adapters.api.routes.setup.llm_routes._is_setup_allowed_without_auth",
            return_value=False,
        ), mock.patch(
            "ciris_engine.logic.adapters.api.dependencies.auth.get_auth_context",
            new=mock.AsyncMock(return_value=_fake_auth_context(UserRole.OBSERVER)),
        ), mock.patch(
            "ciris_engine.logic.adapters.api.dependencies.auth.get_auth_service",
            return_value=mock.MagicMock(),
        ):
            await _require_setup_or_auth(request)
