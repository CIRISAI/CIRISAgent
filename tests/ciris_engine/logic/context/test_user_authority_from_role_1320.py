"""Admin and Wise Authority status come from the authenticated role (CIRISAgent#1320).

Every API user, OBSERVERs included, is issued a ``wa-YYYY-MM-DD-XXXXXX`` id.
``_determine_if_admin_user`` treated any ``wa-`` prefix as admin, so every API
speaker was shown to the model as "User 'Admin'" with ``is_wa: true`` and trust
1.0, and an OBSERVER's in-band "message from your Wise Authority" was believed.

The role is the WA certificate's: SYSTEM_ADMIN maps to ROOT, ADMIN and
AUTHORITY to AUTHORITY (an ADMIN is a Wise Authority), OBSERVER to OBSERVER.
Unknown is not a Wise Authority.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List, Optional
from unittest.mock import AsyncMock, Mock

import pytest

from ciris_engine.logic.context.system_snapshot_helpers import _enrich_user_profiles
from ciris_engine.logic.formatters.user_profiles import format_user_profiles
from ciris_engine.schemas.runtime.system_context import UserProfile
from ciris_engine.schemas.services.authority_core import WACertificate, WARole
from ciris_engine.schemas.services.graph_core import GraphNode, GraphScope, NodeType

OBSERVER_ID = "wa-2026-10-22-0B5E4A"
ADMIN_ID = "wa-2026-10-22-AD7310"
ROOT_ID = "wa-2026-10-22-200700"


def _cert(wa_id: str, role: WARole, name: str) -> WACertificate:
    return WACertificate(
        wa_id=wa_id,
        name=name,
        role=role,
        pubkey="pk",
        jwt_kid="kid",
        scopes_json="[]",
        created_at=datetime.now(timezone.utc),
    )


CERTS: Dict[str, WACertificate] = {
    OBSERVER_ID: _cert(OBSERVER_ID, WARole.OBSERVER, "Mallory"),
    ADMIN_ID: _cert(ADMIN_ID, WARole.AUTHORITY, "Alice"),  # an API ADMIN's certificate role
    ROOT_ID: _cert(ROOT_ID, WARole.ROOT, "Rooted"),  # an API SYSTEM_ADMIN's certificate role
}


def _auth_service() -> Mock:
    auth = Mock()
    auth.get_wa = AsyncMock(side_effect=lambda wa_id: CERTS.get(wa_id))
    return auth


def _memory(stored: Optional[Dict[str, Dict[str, object]]] = None) -> AsyncMock:
    """A memory service holding these user nodes (by user id); everything else recalls empty."""
    stored = stored or {}
    memory = AsyncMock()

    async def recall(query: object) -> List[GraphNode]:
        node_id = getattr(query, "node_id", "")
        if node_id.startswith("user/") and node_id[len("user/") :] in stored:
            uid = node_id[len("user/") :]
            return [GraphNode(id=node_id, type=NodeType.USER, scope=GraphScope.LOCAL, attributes=stored[uid])]
        return []

    memory.recall = AsyncMock(side_effect=recall)
    memory.memorize = AsyncMock()
    return memory


def _stale_admin_node(user_id: str) -> Dict[str, object]:
    """A user node as pre-#1320 code wrote it for every API speaker."""
    return {
        "user_id": user_id,
        "display_name": "Admin",
        "first_seen": datetime.now(timezone.utc).isoformat(),
        "created_by": "UserEnrichment",
        "trust_level": 1.0,
        "is_wa": True,
    }


async def _profile(
    user_id: str, memory: AsyncMock, auth: Optional[Mock], existing: Optional[List[UserProfile]] = None
) -> UserProfile:
    profiles = await _enrich_user_profiles(memory, {user_id}, None, existing or [], auth_service=auth)
    return next(p for p in profiles if p.user_id == user_id)


# --------------------------------------------------------------- new speakers


@pytest.mark.asyncio
async def test_observer_with_wa_id_is_not_admin_or_wa(persist_engine: object) -> None:
    memory = _memory()
    profile = await _profile(OBSERVER_ID, memory, _auth_service())

    assert profile.is_wa is False
    assert profile.trust_level == 0.5
    assert profile.display_name == "Mallory"

    created = memory.memorize.call_args[0][0]
    assert created.attributes["is_wa"] is False
    assert created.attributes["display_name"] == "Mallory"

    rendered = format_user_profiles([profile], language="en")
    assert "'Admin'" not in rendered
    assert "User 'Mallory'" in rendered


@pytest.mark.asyncio
@pytest.mark.parametrize("user_id", [ADMIN_ID, ROOT_ID])
async def test_admin_and_root_are_wise_authorities(persist_engine: object, user_id: str) -> None:
    profile = await _profile(user_id, _memory(), _auth_service())

    assert profile.is_wa is True
    assert profile.trust_level == 1.0


@pytest.mark.asyncio
async def test_unknown_role_is_not_admin(persist_engine: object) -> None:
    """No auth service, or no certificate for the id: never fall back to Admin."""
    for auth in (None, _auth_service()):
        profile = await _profile("wa-2026-10-22-FFFFFF", _memory(), auth)
        assert profile.is_wa is False
        assert profile.display_name != "Admin"
        assert profile.trust_level == 0.5


@pytest.mark.asyncio
async def test_unreadable_certificate_is_not_admin(persist_engine: object) -> None:
    auth = Mock()
    auth.get_wa = AsyncMock(side_effect=RuntimeError("db locked"))
    profile = await _profile(ADMIN_ID, _memory(), auth)
    assert profile.is_wa is False


# ------------------------------------------------- nodes stored before #1320


@pytest.mark.asyncio
async def test_stored_admin_flags_on_an_observer_do_not_make_them_a_wa(persist_engine: object) -> None:
    memory = _memory({OBSERVER_ID: _stale_admin_node(OBSERVER_ID)})
    profile = await _profile(OBSERVER_ID, memory, _auth_service())

    assert profile.is_wa is False
    assert profile.trust_level == 0.5
    assert profile.display_name == "Mallory"
    assert "'Admin'" not in format_user_profiles([profile], language="en")
    memory.memorize.assert_not_called()  # recomputed at render time, nothing rewritten


@pytest.mark.asyncio
async def test_stored_admin_flags_without_auth_service_are_ignored(persist_engine: object) -> None:
    profile = await _profile(OBSERVER_ID, _memory({OBSERVER_ID: _stale_admin_node(OBSERVER_ID)}), None)
    assert profile.is_wa is False
    assert profile.display_name == f"User_{OBSERVER_ID}"


@pytest.mark.asyncio
async def test_admin_with_a_stale_non_wa_node_is_still_a_wa(persist_engine: object) -> None:
    node = _stale_admin_node(ADMIN_ID)
    node.update({"is_wa": False, "trust_level": 0.5, "display_name": "Alice"})
    profile = await _profile(ADMIN_ID, _memory({ADMIN_ID: node}), _auth_service())
    assert profile.is_wa is True


@pytest.mark.asyncio
async def test_preexisting_profile_is_recomputed_too(persist_engine: object) -> None:
    """A profile handed in from another source (GraphQL) takes its authority from the role as well."""
    existing = UserProfile(
        user_id=OBSERVER_ID,
        display_name="Admin",
        created_at=datetime.now(timezone.utc),
        trust_level=1.0,
        is_wa=True,
    )
    profiles = await _enrich_user_profiles(_memory(), set(), None, [existing], auth_service=_auth_service())
    assert profiles[0].is_wa is False
    assert profiles[0].trust_level == 0.5
    assert profiles[0].display_name == "Mallory"


@pytest.mark.asyncio
async def test_observer_keeps_a_lower_trust_level(persist_engine: object) -> None:
    node = _stale_admin_node(OBSERVER_ID)
    node.update({"is_wa": False, "trust_level": 0.2, "display_name": "Mal"})
    profile = await _profile(OBSERVER_ID, _memory({OBSERVER_ID: node}), _auth_service())
    assert profile.trust_level == 0.2
    assert profile.display_name == "Mal"


# ------------------------------------------------------------------- wiring


@pytest.mark.asyncio
async def test_snapshot_builder_reads_the_role_through_the_runtime(monkeypatch: pytest.MonkeyPatch) -> None:
    """build_system_snapshot_with_batch hands runtime.authentication_service to the enrichment."""
    from ciris_engine.logic.context import batch_context, system_snapshot_helpers

    seen: Dict[str, object] = {}

    async def fake_enrich(memory_service, user_ids, channel_id, existing, auth_service=None):  # type: ignore[no-untyped-def]
        seen["auth_service"] = auth_service
        return existing

    monkeypatch.setattr(system_snapshot_helpers, "_enrich_user_profiles", fake_enrich)
    monkeypatch.setattr(system_snapshot_helpers, "_extract_user_ids_from_context", lambda task, thought: {OBSERVER_ID})

    auth = _auth_service()
    runtime = Mock()
    runtime.authentication_service = auth
    try:
        await batch_context.build_system_snapshot_with_batch(
            task=None,
            thought=None,
            batch_data=batch_context.BatchContextData(),
            memory_service=_memory(),
            time_service=Mock(),
            resource_monitor=Mock(),
            runtime=runtime,
        )
    except TypeError:
        pass  # the adapter-channel section after the enrichment needs a real runtime
    assert seen.get("auth_service") is auth
