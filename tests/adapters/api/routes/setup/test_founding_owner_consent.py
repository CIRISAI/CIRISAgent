"""The founding owner's first interact finds their PARTNERED consent, never TEMPORARY.

THE REGRESSION. Setup wrote the founding partnership under the id the brain's
own OAuth login used to authenticate as, ``provider:subject``. Auth folded into
the node in 2.9.14 (201d76f02): every node login (password, Google, Apple, the
OAuth callback) resolves to the owner's ``wa_id``, which is the
``AuthContext.user_id`` interact looks consent up by. The OAuth owner's record
sat at ``consent/google:<sub>``, interact asked for ``consent/wa-root-...``,
found nothing, and handed the founding owner the default TEMPORARY consent plus
"We forget about you in 14 days". 78c1d3bf1 (2.9.44) carried the same keying
into the fabric-holder adoption branch.

THE FIX IS A DELETION. The node creates the user when it is claimed
(CIRISServer#9/#19/#37); setup mints nothing, reads that owner once, and keys
the founding partnership to its wa_id. These tests drive the real setup user
flow against a real graph store, then the real interact consent check, as the
id the node resolves the owner to.
"""

from __future__ import annotations

import os
import tempfile
from datetime import datetime, timezone
from typing import Any, Dict, Iterator, List
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ciris_engine.logic import persistence
from ciris_engine.logic.adapters.api.routes.agent import _handle_consent_for_user
from ciris_engine.logic.adapters.api.routes.setup import complete as C
from ciris_engine.logic.adapters.api.routes.setup.models import SetupCompleteRequest
from ciris_engine.logic.persistence import initialize_database
from ciris_engine.logic.persistence.db import core
from ciris_engine.schemas.api.auth import AuthContext, UserRole
from ciris_engine.schemas.consent.core import ConsentStream

#: What claim-remote leaves behind: the node-claimed owner, the one user.
OWNER_WA_ID = "wa-root-founder-node-1786857172-as6ffyvux6"
OWNER_NAME = "founder"
PROVIDER = "google"
SUBJECT = "102773749033681671083"

_NOTICE = "Privacy Notice"


@pytest.fixture
def graph_db() -> Iterator[str]:
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    initialize_database(db_path)
    original_test_db_path = core._test_db_path
    core._test_db_path = db_path
    original_db_path = getattr(persistence, "_db_path", None)
    persistence._db_path = db_path
    yield db_path
    try:
        os.unlink(db_path)
    except OSError:
        pass
    core._test_db_path = original_test_db_path
    if original_db_path:
        persistence._db_path = original_db_path


@pytest.fixture
def node_store(monkeypatch: pytest.MonkeyPatch) -> Dict[str, Any]:
    """The node's owner rows and provider-identity bindings (the user's own node holds :4243)."""
    import ciris_engine.logic.persistence.stores.authentication_store as store

    state: Dict[str, Any] = {"rows": [], "oauth_holders": []}

    def list_by_role(role: str, limit: int = 1000) -> List[Dict[str, Any]]:
        return [r for r in state["rows"] if str(r.get("role")) == role]

    monkeypatch.setattr(store, "_list_active_by_role", list_by_role, raising=True)
    monkeypatch.setattr(store, "live_oauth_holders", lambda p, s: list(state["oauth_holders"]), raising=True)
    return state


def _claimed(state: Dict[str, Any], name: str = OWNER_NAME, oauth_bound: bool = False) -> None:
    state["rows"] = [{"wa_id": OWNER_WA_ID, "name": name, "role": "root", "active": 1}]
    state["oauth_holders"] = [OWNER_WA_ID] if oauth_bound else []


def _setup(username: str = OWNER_NAME, oauth: bool = False) -> SetupCompleteRequest:
    fields: Dict[str, Any] = {
        "llm_provider": "openai",
        "llm_api_key": "sk-test",
        "template_id": "ally",
        "enabled_adapters": ["api"],
        "admin_username": username,
        "admin_password": "Password-12345",
    }
    if oauth:
        fields.update(oauth_provider=PROVIDER, oauth_external_id=SUBJECT, oauth_email="founder@example.com")
    return SetupCompleteRequest(**fields)


def _auth_service_mock() -> MagicMock:
    """The brain's auth service. Anything it is asked to mint is recorded."""
    auth = AsyncMock()
    auth.get_wa_by_oauth.return_value = None
    auth.list_was.return_value = []
    minted = MagicMock()
    minted.wa_id = "wa-2026-10-16-MINTED"
    auth.create_wa.return_value = minted
    auth.hash_password = MagicMock(return_value="hashed")
    return auth


async def _run_setup(setup: SetupCompleteRequest, db: str) -> MagicMock:
    auth = _auth_service_mock()
    with patch(
        "ciris_engine.logic.services.infrastructure.authentication.service.AuthenticationService",
        return_value=auth,
    ):
        await C._create_setup_users(setup, db)
    return auth


async def _first_interact(user_id: str) -> str:
    """The real interact consent check, as the id the node resolves the caller to."""
    from ciris_engine.logic.services.governance.consent import ConsentService
    from ciris_engine.logic.services.lifecycle.time import TimeService

    request = MagicMock()
    request.app.state.consent_manager = ConsentService(time_service=TimeService())
    auth = AuthContext(
        user_id=user_id,
        role=UserRole.SYSTEM_ADMIN,
        permissions=set(),
        api_key_id=None,
        authenticated_at=datetime.now(timezone.utc),
    )
    notice = await _handle_consent_for_user(auth, "api_channel", request)
    status = await request.app.state.consent_manager.get_consent(user_id, extend_expiry=False)
    stream = status.stream.value if hasattr(status.stream, "value") else str(status.stream)
    return f"{stream}|{notice}"


async def _assert_owner_is_partnered() -> None:
    result = await _first_interact(OWNER_WA_ID)
    stream, notice = result.split("|", 1)
    assert notice == "", f"the founding owner got the TEMPORARY notice: {notice!r}"
    assert stream == ConsentStream.PARTNERED.value


@pytest.mark.asyncio
async def test_oauth_owner_via_fabric_holder(graph_db: str, node_store: Dict[str, Any]) -> None:
    """claim-remote bound google:<sub> to the owner; their first interact is PARTNERED."""
    _claimed(node_store, oauth_bound=True)
    auth = await _run_setup(_setup(oauth=True), graph_db)

    await _assert_owner_is_partnered()
    auth.create_wa.assert_not_awaited()


@pytest.mark.asyncio
async def test_oauth_owner_via_username(graph_db: str, node_store: Dict[str, Any]) -> None:
    """The provider binding is not visible, the owner row answers to the setup username."""
    _claimed(node_store, oauth_bound=False)
    auth = await _run_setup(_setup(oauth=True), graph_db)

    await _assert_owner_is_partnered()
    auth.create_wa.assert_not_awaited()
    auth.link_oauth_identity.assert_not_awaited()


@pytest.mark.asyncio
async def test_password_owner(graph_db: str, node_store: Dict[str, Any]) -> None:
    _claimed(node_store)
    auth = await _run_setup(_setup(), graph_db)

    await _assert_owner_is_partnered()
    auth.create_wa.assert_not_awaited()
    auth.update_wa.assert_not_awaited()  # the node owns the credential


@pytest.mark.asyncio
async def test_add_device_owner(graph_db: str, node_store: Dict[str, Any]) -> None:
    """Add-device: no owner password, no OAuth, and the wizard's default username.

    The node bound its owner through setup/root with the claim PIN; that row is the
    one user, found as the node's single owner even though no name matches.
    """
    _claimed(node_store, name="mooreericnyc")
    setup = _setup(username="owner")
    setup.admin_password = None
    auth = await _run_setup(setup, graph_db)

    await _assert_owner_is_partnered()
    auth.create_wa.assert_not_awaited()
    auth.update_wa.assert_not_awaited()


@pytest.mark.asyncio
async def test_the_founding_record_is_keyed_to_the_owner_wa_id_only(graph_db: str, node_store: Dict[str, Any]) -> None:
    """No second record under provider:subject for anything to read by mistake."""
    from ciris_engine.logic.persistence import get_graph_node
    from ciris_engine.schemas.services.graph_core import GraphScope

    _claimed(node_store, oauth_bound=True)
    await _run_setup(_setup(oauth=True), graph_db)

    assert get_graph_node(f"consent/{OWNER_WA_ID}", GraphScope.LOCAL) is not None
    assert get_graph_node(f"consent/{PROVIDER}:{SUBJECT}", GraphScope.LOCAL) is None


@pytest.mark.asyncio
async def test_unclaimed_node_refuses_and_mints_nothing(graph_db: str, node_store: Dict[str, Any]) -> None:
    """No owner: the node_unclaimed refusal (409 at the route), no mint, no record."""
    from ciris_engine.logic.persistence import get_graph_node
    from ciris_engine.schemas.services.graph_core import GraphScope

    auth = _auth_service_mock()
    with patch(
        "ciris_engine.logic.services.infrastructure.authentication.service.AuthenticationService",
        return_value=auth,
    ):
        with pytest.raises(C._NodeUnclaimedRefusal):
            await C._create_setup_users(_setup(), graph_db)

    auth.create_wa.assert_not_awaited()
    auth.update_wa.assert_not_awaited()
    assert get_graph_node(f"consent/{OWNER_WA_ID}", GraphScope.LOCAL) is None
    assert get_graph_node("consent/wa-2026-10-16-MINTED", GraphScope.LOCAL) is None


@pytest.mark.asyncio
async def test_unclaimed_refusal_is_409_at_the_route(
    node_store: Dict[str, Any], monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> None:
    """The refusal reaches the client as 409 node_unclaimed, with the config rolled back."""
    from types import SimpleNamespace

    from fastapi import HTTPException

    from ciris_engine.logic.persistence.models import graph
    from ciris_engine.schemas.runtime.node_ownership import NODE_UNCLAIMED_ERROR, NodeOwnership, NodeOwnershipReading

    config = tmp_path / ".env"

    def save(setup: Any) -> Any:
        config.write_text('CIRIS_CONFIGURED="true"\n', encoding="utf-8")
        return config

    async def owned(*, fresh: bool = False) -> NodeOwnership:
        # The node reports an owner, but none this setup can name.
        from datetime import datetime, timezone

        return NodeOwnership(
            reading=NodeOwnershipReading.OWNED,
            owner_key_id="k",
            read_at=datetime.now(timezone.utc),
            claim_pin_file=str(tmp_path / "claim_pin"),
        )

    monkeypatch.setattr(C, "_save_and_reload_config", save)
    monkeypatch.setattr(C, "node_owned", owned)
    monkeypatch.setattr(C, "_schedule_runtime_resume", AsyncMock())
    monkeypatch.setattr(C, "get_sqlite_db_full_path", lambda cfg: str(tmp_path / "ciris_engine.db"))
    monkeypatch.setattr(C, "_try_get_ingress_user", AsyncMock(return_value=(None, None, None)))
    monkeypatch.setattr(graph, "get_persist_engine", lambda: SimpleNamespace(local_derived_key_id=lambda: "agent-k"))
    request = MagicMock()
    request.app.state.audit_service = None
    request.app.state.auth_service = None

    auth = _auth_service_mock()
    with patch(
        "ciris_engine.logic.services.infrastructure.authentication.service.AuthenticationService",
        return_value=auth,
    ):
        with pytest.raises(HTTPException) as exc:
            await C.complete_setup(_setup(), request, MagicMock())

    assert exc.value.status_code == 409
    assert exc.value.detail["error"] == NODE_UNCLAIMED_ERROR
    auth.create_wa.assert_not_awaited()
    assert not config.exists()


@pytest.mark.asyncio
async def test_a_non_owner_first_interact_still_gets_temporary_and_the_notice(
    graph_db: str, node_store: Dict[str, Any]
) -> None:
    _claimed(node_store, oauth_bound=True)
    await _run_setup(_setup(oauth=True), graph_db)

    result = await _first_interact("wa-root-someone-else-node-xyz")
    stream, notice = result.split("|", 1)
    assert stream == ConsentStream.TEMPORARY.value
    assert notice.startswith(f"\n\n{_NOTICE}: We forget about you in 14 days")


def test_the_notice_is_ascii() -> None:
    """Windows cp1252 consoles cannot encode emoji; runtime output stays ASCII."""
    import inspect

    from ciris_engine.logic.adapters.api.routes import agent

    source = inspect.getsource(agent._handle_consent_for_user)
    line = next(ln for ln in source.splitlines() if _NOTICE in ln)
    line.encode("ascii")


# --------------------------------------------------------------------------- one id per OAuth user


def _graph_node_ids() -> List[str]:
    """Every LOCAL graph node id in the store."""
    import json

    from ciris_engine.logic.persistence.models.graph import get_persist_engine

    engine = get_persist_engine()
    ids: List[str] = []
    cursor = None
    while True:
        blob = engine.cirisgraph_query_nodes(
            json.dumps({"scope": "LOCAL"}), json.dumps({"cursor": cursor}) if cursor else None, 100
        )
        page = json.loads(blob) if isinstance(blob, str) else blob
        items = page.get("items", []) if isinstance(page, dict) else []
        for it in items:
            d = json.loads(it) if isinstance(it, str) else it
            ids.append(str(d.get("node_id", "")))
        cursor = page.get("next_cursor") if isinstance(page, dict) else None
        if not items or not cursor:
            break
    return ids


@pytest.mark.asyncio
async def test_an_oauth_user_resolves_to_one_id_everywhere(graph_db: str, node_store: Dict[str, Any]) -> None:
    """Login (the node's wa_id) -> interact -> consent -> prefs: one id, no provider:subject anywhere."""
    from ciris_engine.logic.persistence import get_graph_node
    from ciris_engine.schemas.services.graph_core import GraphScope

    _claimed(node_store, oauth_bound=True)
    setup = _setup(oauth=True)
    setup.preferred_language = "am"
    await _run_setup(setup, graph_db)
    await _assert_owner_is_partnered()

    assert get_graph_node(f"preferences/{OWNER_WA_ID}", GraphScope.LOCAL) is not None
    ids = _graph_node_ids()
    assert f"consent/{OWNER_WA_ID}" in ids
    offenders = [
        i for i in ids if SUBJECT in i or f"{PROVIDER}:" in i or i.startswith(("consent/oauth-", "consent/wa-2"))
    ]
    assert offenders == [], f"an OAuth-derived or minted id was written as a user key: {offenders}"


@pytest.mark.asyncio
async def test_boot_rekeys_a_founding_record_stranded_under_provider_subject(
    graph_db: str, node_store: Dict[str, Any]
) -> None:
    """Already-deployed OAuth owners: the boot backfill moves PARTNERED onto the wa_id, over the bug's TEMPORARY."""
    from ciris_engine.logic.persistence import get_graph_node
    from ciris_engine.logic.runtime.config_migration import migrate_founding_partnerships
    from ciris_engine.schemas.services.graph_core import GraphScope

    # What 2.10.0-2.16.x left behind: founding record at provider:subject ...
    C._create_founding_partnership(OWNER_WA_ID, f"{PROVIDER}:{SUBJECT}")
    # ... and the TEMPORARY the owner's first interact created at their real id.
    await _first_interact(OWNER_WA_ID)
    node_store["rows"] = [
        {
            "wa_id": OWNER_WA_ID,
            "name": OWNER_NAME,
            "role": "root",
            "active": 1,
            "oauth_provider": PROVIDER,
            "oauth_external_id": SUBJECT,
        }
    ]
    runtime = MagicMock()
    runtime.service_initializer.auth_service.list_was = AsyncMock(return_value=[])

    with patch("ciris_engine.logic.setup.first_run.is_first_run", return_value=False):
        await migrate_founding_partnerships(runtime)

    await _assert_owner_is_partnered()
    assert get_graph_node(f"consent/{PROVIDER}:{SUBJECT}", GraphScope.LOCAL) is None


@pytest.mark.asyncio
async def test_boot_leaves_a_temporary_with_no_stranded_founding_record(
    graph_db: str, node_store: Dict[str, Any]
) -> None:
    """A TEMPORARY the bug did not cause (no stranded founding record) is the user's, and stays."""
    from ciris_engine.logic.runtime.config_migration import migrate_founding_partnerships

    await _first_interact(OWNER_WA_ID)
    node_store["rows"] = [{"wa_id": OWNER_WA_ID, "name": OWNER_NAME, "role": "root", "active": 1}]
    runtime = MagicMock()
    runtime.service_initializer.auth_service.list_was = AsyncMock(return_value=[])

    with patch("ciris_engine.logic.setup.first_run.is_first_run", return_value=False):
        await migrate_founding_partnerships(runtime)

    stream, _ = (await _first_interact(OWNER_WA_ID)).split("|", 1)
    assert stream == ConsentStream.TEMPORARY.value


@pytest.mark.asyncio
async def test_boot_leaves_an_ingress_founding_record_alone(graph_db: str, node_store: Dict[str, Any]) -> None:
    """Ingress auth authenticates as provider:id, so its founding record is correctly keyed there."""
    from ciris_engine.logic.persistence import get_graph_node
    from ciris_engine.logic.runtime.config_migration import migrate_founding_partnerships
    from ciris_engine.schemas.services.graph_core import GraphScope

    ingress_wa = MagicMock()
    ingress_wa.wa_id = "wa-2026-10-16-INGRES"
    ingress_wa.role = "root"
    from ciris_engine.schemas.services.authority_core import WARole

    ingress_wa.role = WARole.ROOT
    C._create_founding_partnership(ingress_wa.wa_id, "home_assistant:abc123")
    node_store["rows"] = []
    runtime = MagicMock()
    runtime.service_initializer.auth_service.list_was = AsyncMock(return_value=[ingress_wa])

    with patch("ciris_engine.logic.setup.first_run.is_first_run", return_value=False):
        await migrate_founding_partnerships(runtime)

    assert get_graph_node("consent/home_assistant:abc123", GraphScope.LOCAL) is not None
