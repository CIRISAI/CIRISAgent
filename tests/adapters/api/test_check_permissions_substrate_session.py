"""check_permissions for a node-issued session whose subject the brain's user table does not hold.

The node-claimed owner of a node is a federation identity. The brain's user table
skips those rows, so check_permissions answered 403 "User not found" to the owner
on /v1/users and every other check_permissions route, although get_auth_context
had already verified the session with the substrate (found running the ai-safety-claims
Market 4 harness, RATCHET run 39707238812).
"""

from datetime import datetime, timezone
from unittest.mock import Mock

import pytest
from fastapi import HTTPException

from ciris_engine.logic.adapters.api.dependencies.auth import AuthContext, check_permissions
from ciris_engine.schemas.api.auth import UserRole
from ciris_engine.schemas.runtime.api import APIRole


def _ctx(role: UserRole, *, substrate: bool, user_id: str = "fed-owner-key") -> AuthContext:
    return AuthContext(
        user_id=user_id, role=role, permissions=set(), authenticated_at=datetime.now(timezone.utc),
        substrate_verified=substrate,
    )


def _service(user=None):
    svc = Mock()
    svc.get_user.return_value = user
    table = {
        APIRole.OBSERVER: ["agent.read"],
        APIRole.ADMIN: ["agent.read", "users.read"],
        APIRole.AUTHORITY: ["agent.read", "users.read", "wa.resolve_deferral"],
        APIRole.SYSTEM_ADMIN: ["agent.read", "users.read", "users.write", "wa.mint"],
    }
    svc.get_permissions_for_role.side_effect = lambda role: table.get(role, [])
    return svc


@pytest.mark.asyncio
async def test_substrate_session_owner_not_in_table_gets_its_role_permissions():
    check = check_permissions(["users.write"])
    await check(auth=_ctx(UserRole.SYSTEM_ADMIN, substrate=True), auth_service=_service())


@pytest.mark.asyncio
async def test_substrate_session_role_still_bounds_permissions():
    check = check_permissions(["users.write"])
    with pytest.raises(HTTPException) as exc:
        await check(auth=_ctx(UserRole.OBSERVER, substrate=True), auth_service=_service())
    assert exc.value.status_code == 403
    assert "Missing required permissions" in exc.value.detail


@pytest.mark.asyncio
async def test_unknown_subject_without_substrate_session_is_still_refused():
    check = check_permissions(["users.read"])
    with pytest.raises(HTTPException) as exc:
        await check(auth=_ctx(UserRole.SYSTEM_ADMIN, substrate=False), auth_service=_service())
    assert exc.value.status_code == 403
    assert exc.value.detail == "User not found"


@pytest.mark.asyncio
async def test_user_in_table_keeps_table_role_even_with_session_token():
    user = Mock(api_role=APIRole.OBSERVER, wa_role=None, custom_permissions=None)
    check = check_permissions(["users.write"])
    with pytest.raises(HTTPException) as exc:
        await check(auth=_ctx(UserRole.SYSTEM_ADMIN, substrate=True), auth_service=_service(user))
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_ingress_context_with_session_shaped_header_is_still_refused():
    """get_auth_context tries ingress providers before reading the bearer, so a `Bearer sess:` header
    on an ingress-authenticated request proves nothing. Only the substrate path sets the flag."""
    from unittest.mock import patch

    from fastapi import Request

    from ciris_engine.logic.adapters.api.dependencies import auth as auth_mod

    ingress_ctx = _ctx(UserRole.SYSTEM_ADMIN, substrate=False, user_id="ingress-user-not-in-table")
    request = Mock(spec=Request)
    with patch.object(auth_mod, "_ingress_auth_providers", [object()]), patch.object(
        auth_mod, "_try_ingress_auth", return_value=ingress_ctx
    ):
        ctx = await auth_mod.get_auth_context(request, authorization="Bearer sess:x", auth_service=_service())
    assert ctx.substrate_verified is False
    with pytest.raises(HTTPException) as exc:
        await check_permissions(["users.read"])(auth=ctx, auth_service=_service())
    assert exc.value.status_code == 403
    assert exc.value.detail == "User not found"


def test_only_the_substrate_authenticator_sets_the_flag():
    from unittest.mock import patch

    from ciris_engine.logic.adapters.api.dependencies import auth as auth_mod

    with patch.object(auth_mod, "resolve_substrate_session", return_value={"wa_id": "fed-owner", "role": "SYSTEM_ADMIN"}):
        ctx = auth_mod._handle_substrate_session_auth(Mock(), Mock(), "sess:abc:def")
    assert ctx.substrate_verified is True
    assert ctx.user_id == "fed-owner"
    assert AuthContext(user_id="u", role=UserRole.OBSERVER, permissions=set(), authenticated_at=datetime.now(timezone.utc)).substrate_verified is False
