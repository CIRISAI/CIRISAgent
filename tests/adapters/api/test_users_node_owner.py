"""GET /v1/users/{user_id} and GET /v1/users answer for the node-claimed owner.

The node owns identity: the brain's user table holds no row for the node-claimed
owner, so `get_user` answered 404 for the one user (#1287). CIRISServer 0.5.234
adds `ciris_server.owner_record()`; these tests stand it in with a fake module,
since the installed wheel predates it.
"""

import json
import sys
import types
from datetime import datetime, timezone
from typing import Callable, Optional
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import HTTPException

from ciris_engine.logic.adapters.api.routes.users import ERROR_OWNER_RECORD_UNREADABLE, get_user, list_users
from ciris_engine.logic.adapters.api.services.auth_service import (
    PERMISSION_USERS_DELETE,
    PERMISSION_WA_MINT,
    APIAuthService,
    User,
)
from ciris_engine.schemas.runtime.api import APIRole
from ciris_engine.schemas.services.authority_core import WARole

OWNER_WA_ID = "wa-2026-10-01-OWNER1"
OWNER_FED_ID = "fed-owner-key-1"
OWNER_CREATED = "2026-10-01T12:00:00Z"


def _record(**overrides: object) -> str:
    record = {
        "wa_id": OWNER_WA_ID,
        "name": "Node Owner",
        "role": "root",
        "user_role": "SYSTEM_ADMIN",
        "created_at": OWNER_CREATED,
        "owner_key_id": OWNER_FED_ID,
        "auth_type": "oauth",
        "has_password": False,
        "oauth_provider": "google",
    }
    record.update(overrides)
    return json.dumps(record)


def _install_server(monkeypatch: pytest.MonkeyPatch, owner_record: Optional[Callable[[], Optional[str]]]) -> None:
    """A stand-in `ciris_server` on a folded node; `owner_record=None` is a server older than 0.5.234."""
    from ciris_engine.logic.runtime import node_fold

    monkeypatch.setattr(node_fold, "fold_status", lambda: {"folded": True, "reachable": True})
    module = types.ModuleType("ciris_server")
    if owner_record is not None:
        module.owner_record = owner_record  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "ciris_server", module)


@pytest.fixture
def auth_service() -> APIAuthService:
    wa_store = Mock()
    wa_store.list_was = AsyncMock(return_value=[])
    service = APIAuthService(auth_service=wa_store)
    service._users["wa-2026-10-01-OTHER2"] = User(
        wa_id="wa-2026-10-01-OTHER2",
        name="Table User",
        auth_type="password",
        api_role=APIRole.OBSERVER,
        wa_role=WARole.OBSERVER,
        created_at=datetime(2026, 9, 1, tzinfo=timezone.utc),
        password_hash="$2b$12$test_hash",
    )
    service._users_loaded = True
    return service


@pytest.fixture
def auth() -> Mock:
    ctx = Mock()
    ctx.user_id = OWNER_WA_ID
    return ctx


class TestGetUserNodeOwner:
    @pytest.mark.asyncio
    async def test_owner_by_wa_id_gets_their_detail(self, monkeypatch, auth, auth_service):
        """NEGATIVE on the old code: this answered 404 for the node-claimed owner."""
        _install_server(monkeypatch, lambda: _record())

        detail = await get_user(OWNER_WA_ID, auth, auth_service, None)

        assert detail.user_id == OWNER_WA_ID
        assert detail.wa_id == OWNER_WA_ID
        assert detail.username == "Node Owner"
        assert detail.auth_type == "oauth"
        assert detail.oauth_provider == "google"
        assert detail.api_role == APIRole.SYSTEM_ADMIN
        assert detail.wa_role == WARole.ROOT
        assert detail.created_at == datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)
        # The auth service's role mapping: ROOT is SYSTEM_ADMIN plus AUTHORITY.
        assert set(detail.permissions) == set(auth_service.get_permissions_for_role(APIRole.SYSTEM_ADMIN)) | set(
            auth_service.get_permissions_for_role(APIRole.AUTHORITY)
        )
        assert PERMISSION_WA_MINT in detail.permissions
        assert PERMISSION_USERS_DELETE in detail.permissions
        # Nothing the record does not carry is filled in.
        assert detail.oauth_email is None
        assert detail.oauth_name is None
        assert detail.oauth_external_id is None
        assert detail.last_login is None
        assert detail.custom_permissions is None
        assert detail.wa_parent_id is None
        assert detail.api_keys_count == 0
        assert detail.linked_oauth_accounts == []

    @pytest.mark.asyncio
    async def test_owner_by_fed_id_gets_their_detail(self, monkeypatch, auth, auth_service):
        _install_server(monkeypatch, lambda: _record())

        detail = await get_user(OWNER_FED_ID, auth, auth_service, None)

        assert detail.user_id == OWNER_FED_ID
        assert detail.wa_id == OWNER_WA_ID

    @pytest.mark.asyncio
    async def test_legacy_root_is_not_matched_by_a_null_fed_id(self, monkeypatch, auth, auth_service):
        _install_server(monkeypatch, lambda: _record(owner_key_id=None))

        assert (await get_user(OWNER_WA_ID, auth, auth_service, None)).wa_id == OWNER_WA_ID
        with pytest.raises(HTTPException) as exc:
            await get_user(OWNER_FED_ID, auth, auth_service, None)
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_non_owner_id_is_still_404(self, monkeypatch, auth, auth_service):
        _install_server(monkeypatch, lambda: _record())

        with pytest.raises(HTTPException) as exc:
            await get_user("wa-2026-10-01-NOBODY", auth, auth_service, None)
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_old_server_without_owner_record_keeps_404(self, monkeypatch, auth, auth_service):
        _install_server(monkeypatch, None)

        with pytest.raises(HTTPException) as exc:
            await get_user(OWNER_WA_ID, auth, auth_service, None)
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_node_with_no_root_keeps_404(self, monkeypatch, auth, auth_service):
        _install_server(monkeypatch, lambda: None)

        with pytest.raises(HTTPException) as exc:
            await get_user(OWNER_WA_ID, auth, auth_service, None)
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_raising_server_is_503_not_404(self, monkeypatch, auth, auth_service):
        def boom() -> Optional[str]:
            raise RuntimeError("store unavailable")

        _install_server(monkeypatch, boom)

        with pytest.raises(HTTPException) as exc:
            await get_user(OWNER_WA_ID, auth, auth_service, None)
        assert exc.value.status_code == 503
        assert exc.value.detail == ERROR_OWNER_RECORD_UNREADABLE

    @pytest.mark.asyncio
    async def test_unparseable_record_is_503(self, monkeypatch, auth, auth_service):
        _install_server(monkeypatch, lambda: _record(role="SYSTEM_ADMIN"))

        with pytest.raises(HTTPException) as exc:
            await get_user(OWNER_WA_ID, auth, auth_service, None)
        assert exc.value.status_code == 503

    @pytest.mark.asyncio
    async def test_a_password_owner_is_answered_from_the_record(self, monkeypatch, auth, auth_service):
        """A non-OAuth owner (including a legacy ROOT) is answered: the record states has_password."""
        _install_server(
            monkeypatch,
            lambda: _record(oauth_provider=None, auth_type="standard", has_password=True, owner_key_id=None),
        )

        detail = await get_user(OWNER_WA_ID, auth, auth_service, None)
        assert detail.auth_type == "password"
        assert detail.oauth_provider is None

    @pytest.mark.asyncio
    async def test_a_key_only_owner_is_a_certificate_user(self, monkeypatch, auth, auth_service):
        _install_server(monkeypatch, lambda: _record(oauth_provider=None, auth_type="standard", has_password=False))

        detail = await get_user(OWNER_WA_ID, auth, auth_service, None)
        assert detail.auth_type == "certificate"

    @pytest.mark.asyncio
    async def test_the_session_role_spelling_is_not_a_wa_role(self, monkeypatch, auth, auth_service):
        """The 0.5.234 pre-fix bug: role "SYSTEM_ADMIN" is not a WaRole, so the record is unreadable (503)."""
        _install_server(monkeypatch, lambda: _record(role="SYSTEM_ADMIN"))

        with pytest.raises(HTTPException) as exc:
            await get_user(OWNER_WA_ID, auth, auth_service, None)
        assert exc.value.status_code == 503

    @pytest.mark.asyncio
    async def test_table_row_answers_without_asking_the_node(self, monkeypatch, auth, auth_service):
        def boom() -> Optional[str]:
            raise AssertionError("the node must not be asked when the table has the row")

        _install_server(monkeypatch, boom)

        detail = await get_user("wa-2026-10-01-OTHER2", auth, auth_service, None)
        assert detail.username == "Table User"


@pytest.mark.asyncio
async def test_fold_off_is_no_owner_and_does_not_ask_the_server(monkeypatch, auth, auth_service):
    def boom() -> Optional[str]:
        raise AssertionError("no node in this process: the server must not be asked")

    _install_server(monkeypatch, boom)
    from ciris_engine.logic.runtime import node_fold

    monkeypatch.setattr(node_fold, "fold_status", lambda: None)

    with pytest.raises(HTTPException) as exc:
        await get_user(OWNER_WA_ID, auth, auth_service, None)
    assert exc.value.status_code == 404


class TestListUsersNodeOwner:
    async def _list(self, auth, auth_service, **filters):
        params = {
            "page": 1,
            "page_size": 20,
            "search": None,
            "auth_type": None,
            "api_role": None,
            "wa_role": None,
            "is_active": None,
        }
        params.update(filters)
        return await list_users(auth, auth_service, None, **params)

    @pytest.mark.asyncio
    async def test_owner_is_listed_when_the_table_lacks_them(self, monkeypatch, auth, auth_service):
        _install_server(monkeypatch, lambda: _record())

        page = await self._list(auth, auth_service)

        assert page.total == 2
        assert [item.user_id for item in page.items] == [OWNER_WA_ID, "wa-2026-10-01-OTHER2"]
        owner = page.items[0]
        assert owner.api_role == APIRole.SYSTEM_ADMIN
        assert owner.wa_role == WARole.ROOT
        assert owner.auth_type == "oauth"

    @pytest.mark.asyncio
    async def test_filters_apply_to_the_owner(self, monkeypatch, auth, auth_service):
        _install_server(monkeypatch, lambda: _record())

        page = await self._list(auth, auth_service, api_role=APIRole.OBSERVER)

        assert [item.user_id for item in page.items] == ["wa-2026-10-01-OTHER2"]

    @pytest.mark.asyncio
    async def test_owner_already_in_table_is_not_listed_twice(self, monkeypatch, auth, auth_service):
        _install_server(monkeypatch, lambda: _record(wa_id="wa-2026-10-01-OTHER2"))

        page = await self._list(auth, auth_service)

        assert [item.user_id for item in page.items] == ["wa-2026-10-01-OTHER2"]

    @pytest.mark.asyncio
    async def test_old_server_lists_the_table_only(self, monkeypatch, auth, auth_service):
        _install_server(monkeypatch, None)

        page = await self._list(auth, auth_service)

        assert [item.user_id for item in page.items] == ["wa-2026-10-01-OTHER2"]

    @pytest.mark.asyncio
    async def test_raising_server_is_503(self, monkeypatch, auth, auth_service):
        def boom() -> Optional[str]:
            raise RuntimeError("store unavailable")

        _install_server(monkeypatch, boom)

        with pytest.raises(HTTPException) as exc:
            await self._list(auth, auth_service)
        assert exc.value.status_code == 503
