"""A node-claimed owner must get a founding partnership — stewardship and partnership co-establish.

Stewardship is over a NODE. Partnership is with an AGENT. Claiming a node
establishes both, at the same moment, by the same act.

On a live 2.9.15 install the substrate held up its half and the brain did not:

    attestation_subjects:
      ownership:responsible_party:node:v1   x4     <- stewardship, established
      consent:stream:*                      NONE   <- partnership, never happened

with the cause printed plainly in the boot log, on an install that owns a
perfectly good root certificate:

    [PARTNERSHIP_MIGRATION] No ROOT WAs found - nothing to backfill

`migrate_founding_partnerships()` enumerates via `auth_service.list_was()`,
which ends `if _is_brain_wa_row(r)` — excluding `wa-root-*` rows because they
are substrate-owned federation identities, not brain WACertificates (#922).
An owner minted by node self-claim is invisible to it.

That filter is correct. What was missing is that nothing on the self-claim path
does the work the brain's classic path does for a newly-minted owner. It is the
same filter behind the 2.9.15 setup-wizard lockout — third consequence of one
correct decision, which is why the last test here pins the *reason* rather than
the symptom.
"""

from __future__ import annotations

from typing import Any, List, Optional

import pytest

from ciris_engine.logic.runtime import config_migration as cm
from ciris_engine.schemas.services.authority_core import WARole


class _WA:
    def __init__(self, wa_id: str, name: str, role: Any) -> None:
        self.wa_id, self.name, self.role = wa_id, name, role


class _Auth:
    def __init__(self, was: List[_WA]) -> None:
        self._was = was

    async def list_was(self, active_only: bool = True) -> List[_WA]:
        # Mirrors the real filter: node-owner rows are NEVER returned here.
        return [w for w in self._was if not w.wa_id.startswith("wa-root-")]


class _Runtime:
    def __init__(self, was: List[_WA]) -> None:
        class _SI:
            auth_service = _Auth(was)

        self.service_initializer = _SI()


@pytest.fixture
def wiring(monkeypatch: pytest.MonkeyPatch):
    """Not first-run, nothing already recorded, and capture who gets a partnership."""
    monkeypatch.setattr(cm, "is_first_run", lambda: False, raising=False)
    import ciris_engine.logic.setup.first_run as fr

    monkeypatch.setattr(fr, "is_first_run", lambda: False, raising=True)

    import ciris_engine.logic.persistence.models.graph as graph

    monkeypatch.setattr(graph, "get_graph_node", lambda *a, **k: None, raising=True)

    created: List[str] = []
    import ciris_engine.logic.adapters.api.routes.setup.complete as complete

    monkeypatch.setattr(complete, "_create_founding_partnership", lambda wa_id: created.append(wa_id), raising=True)
    return created


def _patch_substrate_roots(monkeypatch: pytest.MonkeyPatch, rows: Optional[List[dict]], boom: bool = False) -> None:
    import ciris_engine.logic.persistence.stores.authentication_store as store

    def fake(role: str, limit: int = 1000) -> List[dict]:
        if boom:
            raise RuntimeError("persist engine not wired")
        return rows or []

    monkeypatch.setattr(store, "_list_active_by_role", fake, raising=True)


@pytest.mark.asyncio
async def test_node_owner_root_gets_a_founding_partnership(monkeypatch, wiring) -> None:
    """THE BUG: the only human is a wa-root-*, and list_was() cannot see them."""
    created = wiring
    _patch_substrate_roots(
        monkeypatch,
        [{"wa_id": "wa-root-eric-moore-v2-portable-abc", "name": "emoore"}],
    )

    # Brain-side list holds only observers — exactly the live install's shape.
    await cm.migrate_founding_partnerships(
        _Runtime([_WA("wa-2026-08-14-2C136E", "apiplatform_observer", WARole.OBSERVER)])
    )

    assert created == ["wa-root-eric-moore-v2-portable-abc"], (
        "the node-claimed owner must receive the partnership half of the claim; "
        "without this the install logs 'No ROOT WAs found' while holding a root"
    )


@pytest.mark.asyncio
async def test_classic_brain_root_still_backfills(monkeypatch, wiring) -> None:
    """The pre-existing path must not regress."""
    created = wiring
    _patch_substrate_roots(monkeypatch, [])

    await cm.migrate_founding_partnerships(_Runtime([_WA("wa-2026-01-01-AAAAAA", "founder", WARole.ROOT)]))

    assert created == ["wa-2026-01-01-AAAAAA"]


@pytest.mark.asyncio
async def test_no_duplicate_when_both_sources_name_the_same_root(monkeypatch, wiring) -> None:
    """Dedupe by wa_id — a root visible to both must be partnered once, not twice."""
    created = wiring
    _patch_substrate_roots(monkeypatch, [{"wa_id": "wa-2026-01-01-AAAAAA", "name": "founder"}])

    await cm.migrate_founding_partnerships(_Runtime([_WA("wa-2026-01-01-AAAAAA", "founder", WARole.ROOT)]))

    assert created == ["wa-2026-01-01-AAAAAA"]


@pytest.mark.asyncio
async def test_unreadable_substrate_still_backfills_brain_roots(monkeypatch, wiring) -> None:
    """A failed substrate read must not cost the roots we CAN see.

    Aborting here would turn a degraded substrate into a second missing
    partnership — the same "assert absence from a failed probe" mistake the
    2.9.15 setup fix avoids in the other direction.
    """
    created = wiring
    _patch_substrate_roots(monkeypatch, None, boom=True)

    await cm.migrate_founding_partnerships(_Runtime([_WA("wa-2026-01-01-AAAAAA", "founder", WARole.ROOT)]))

    assert created == ["wa-2026-01-01-AAAAAA"]


@pytest.mark.asyncio
async def test_existing_consent_is_not_recreated(monkeypatch, wiring) -> None:
    """Idempotent: a root that already has a consent node is skipped."""
    created = wiring
    import ciris_engine.logic.persistence.models.graph as graph

    monkeypatch.setattr(graph, "get_graph_node", lambda node_id, scope: object(), raising=True)
    _patch_substrate_roots(monkeypatch, [{"wa_id": "wa-root-x", "name": "someone"}])

    await cm.migrate_founding_partnerships(_Runtime([]))

    assert created == []
