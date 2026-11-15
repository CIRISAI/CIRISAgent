"""The node owner can resolve a domain-hinted deferral.

RATCHET Market 4, run 43667023655 (rv-10, rv-12, sh-ch-03): since domain-hinted
DSASPDMA deferrals get a request row (3da58bb5f), the resolve route's
jurisdiction gate runs for them. The owner's id is the node-claimed
``wa-root-…``, which cannot be built as a WACertificate, so ``get_wa`` raised a
pydantic ValidationError outside the route's try and every such resolve
answered a bare 500 logged only to uvicorn's console.

Ruling (Eric, 2026-11-15): a root owner row is ROOT and takes the recovery path.
"""

import ast
import inspect
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ciris_engine.logic.persistence.stores import authentication_store as store
from ciris_engine.logic.services.governance.wise_authority.service import WiseAuthorityService
from ciris_engine.schemas.services.authority_core import AuthorizationDenialReason, WARole

OWNER = "wa-root-qa-harness-user-v6c76hjv5v"
CLASSIC = "wa-2026-07-15-ABC123"


def _engine(row: dict) -> MagicMock:
    engine = MagicMock()
    engine.wa_cert_get.return_value = row
    return engine


def _owner_row(role: str = "root", active: bool = True) -> dict:
    return {"wa_id": OWNER, "name": "owner", "role": role, "active": active}


def test_get_wa_by_id_answers_none_for_an_owner_row_instead_of_raising():
    with patch.object(store, "_get_engine", return_value=_engine(_owner_row())):
        assert store.get_wa_by_id(OWNER) is None


def test_node_owner_role_reads_the_owner_rows_role():
    with patch.object(store, "_get_engine", return_value=_engine(_owner_row())):
        assert store.node_owner_role(OWNER) == "root"
    with patch.object(store, "_get_engine", return_value=_engine(_owner_row(active=False))):
        assert store.node_owner_role(OWNER) is None


def test_node_owner_role_ignores_classic_certificates():
    row = {"wa_id": CLASSIC, "name": "admin", "role": "root", "active": True}
    with patch.object(store, "_get_engine", return_value=_engine(row)):
        assert store.node_owner_role(CLASSIC) is None


def _service(owner_role):
    auth = AsyncMock()
    auth.get_wa = AsyncMock(return_value=None)
    auth.get_node_owner_role = AsyncMock(return_value=owner_role)
    return WiseAuthorityService(time_service=MagicMock(), auth_service=auth, db_path=":memory:")


@pytest.mark.asyncio
async def test_a_root_owner_is_authorized_on_a_domain_resource():
    decision = await _service("root").authorize(OWNER, "resolve_deferral", "financial_defer_x")
    assert decision.allowed and decision.role == WARole.ROOT


@pytest.mark.asyncio
async def test_a_non_root_owner_row_is_still_not_found():
    decision = await _service("authority").authorize(OWNER, "resolve_deferral", "financial_defer_x")
    assert not decision.allowed and decision.reason == AuthorizationDenialReason.WA_NOT_FOUND


@pytest.mark.asyncio
async def test_no_owner_row_is_not_found():
    decision = await _service(None).authorize(OWNER, "resolve_deferral", "financial_defer_x")
    assert not decision.allowed and decision.reason == AuthorizationDenialReason.WA_NOT_FOUND


def test_the_route_turns_an_authorize_failure_into_a_logged_503():
    from ciris_engine.logic.adapters.api.routes import wa

    tree = ast.parse(inspect.cleandoc(inspect.getsource(wa.resolve_deferral)))
    blocks = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Try)
        and any(isinstance(n, ast.Attribute) and n.attr == "authorize" for n in ast.walk(ast.Module(node.body, [])))
    ]
    assert blocks, "wa_service.authorize must run inside a try"
    handler_src = ast.unparse(blocks[0].handlers[0])
    assert "SERVICE_UNAVAILABLE" in handler_src and "logger" in handler_src
