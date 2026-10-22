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


def _ctx(role: UserRole, user_id: str = "fed-owner-key") -> AuthContext:
    return AuthContext(user_id=user_id, role=role, permissions=set(), authenticated_at=datetime.now(timezone.utc))


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
    await check(auth=_ctx(UserRole.SYSTEM_ADMIN), auth_service=_service(), authorization="Bearer sess:abc:def")


@pytest.mark.asyncio
async def test_substrate_session_role_still_bounds_permissions():
    check = check_permissions(["users.write"])
    with pytest.raises(HTTPException) as exc:
        await check(auth=_ctx(UserRole.OBSERVER), auth_service=_service(), authorization="Bearer sess:abc:def")
    assert exc.value.status_code == 403
    assert "Missing required permissions" in exc.value.detail


@pytest.mark.asyncio
async def test_unknown_subject_without_substrate_session_is_still_refused():
    check = check_permissions(["users.read"])
    for header in ("Bearer some-api-key", "Bearer user:pass", None):
        with pytest.raises(HTTPException) as exc:
            await check(auth=_ctx(UserRole.SYSTEM_ADMIN), auth_service=_service(), authorization=header)
        assert exc.value.status_code == 403
        assert exc.value.detail == "User not found"


@pytest.mark.asyncio
async def test_user_in_table_keeps_table_role_even_with_session_token():
    user = Mock(api_role=APIRole.OBSERVER, wa_role=None, custom_permissions=None)
    check = check_permissions(["users.write"])
    with pytest.raises(HTTPException) as exc:
        await check(auth=_ctx(UserRole.SYSTEM_ADMIN), auth_service=_service(user), authorization="Bearer sess:abc:def")
    assert exc.value.status_code == 403
