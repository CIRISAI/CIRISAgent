"""A node-claimed owner must count as "setup complete" — or upgrades bounce to the wizard.

THE BUG, reproduced on a real 2.9.14 upgrade of an installed agent:

    cirislens_wa_cert:
      wa-root-eric-moore-…   name=emoore   role=root   active=1
      apiplatform_observer / wallet_observer / …       (minted every boot)

    GET /v1/setup/status
      -> setup_required=true, first_run=false, config_exists=true
    client -> setup wizard, owner locked out, credentials intact on disk

Two individually-correct changes composed into a wrong answer:

  1. 2.9.14 moved identity to the substrate. The owner of a node-claimed
     install is a `wa-root-…` row in the node's store.
  2. CIRISAgent#922 made the brain's WA store deliberately SKIP those rows —
     they are substrate-owned federation identities, not brain
     `WACertificate`s — to fix a completeSetup 500.

`has_system_admin_user()` reads the BRAIN's user cache, which by (2) can no
longer see the only human. It answers "no admin", and `is_setup_required()`
takes the #794 bugged-install self-heal branch ("config exists but the founding
admin was lost"), which is exactly wrong here: nothing was lost.

The self-heal must survive. These tests pin both directions — a real owner
suppresses the wizard, a genuinely empty install still triggers it — because a
fix that only stopped the false positive would silently disable #794 recovery.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import pytest

from ciris_engine.logic.adapters.api.routes.setup import dependencies as deps


class _Req:
    """Stand-in for the FastAPI Request; only `.app.state` is consulted."""

    class _App:
        class _State:
            auth_service = None

        state = _State()

    app = _App()


@pytest.fixture
def req() -> Any:
    return _Req()


def _patch_roles(monkeypatch: pytest.MonkeyPatch, table: Dict[str, List[dict]]) -> None:
    """Fake the substrate's by-role listing (already active-filtered, as persist is)."""

    def fake(role: str, limit: int = 1000) -> List[dict]:
        return table.get(role, [])

    import ciris_engine.logic.persistence.stores.authentication_store as store

    monkeypatch.setattr(store, "_list_active_by_role", fake, raising=True)


def _no_brain_admin(monkeypatch: pytest.MonkeyPatch) -> None:
    """The brain reports no SYSTEM_ADMIN — what it does on a node-claimed install."""

    async def fake(_request: Any) -> Optional[bool]:
        return False

    monkeypatch.setattr(deps, "has_system_admin_user", fake, raising=True)


def _config_exists(monkeypatch: pytest.MonkeyPatch, exists: bool = True) -> None:
    class _P:
        def exists(self) -> bool:
            return exists

    monkeypatch.setattr(deps, "get_default_config_path", lambda: _P(), raising=True)
    monkeypatch.setattr(deps, "is_first_run", lambda: False, raising=True)


@pytest.mark.asyncio
async def test_node_root_owner_means_setup_is_not_required(monkeypatch, req) -> None:
    """THE REGRESSION: owner exists on the node, brain can't see it, no wizard."""
    _config_exists(monkeypatch)
    _no_brain_admin(monkeypatch)
    _patch_roles(
        monkeypatch,
        {"root": [{"wa_id": "wa-root-eric-moore-v2-portable-abc", "name": "emoore", "active": 1}]},
    )

    assert await deps.is_setup_required(req) is False, (
        "an active node-owner root certificate must count as setup-complete; "
        "otherwise every node-claimed install is bounced into the wizard on upgrade"
    )


@pytest.mark.asyncio
async def test_authority_role_also_counts(monkeypatch, req) -> None:
    """`authority` is an owner role too — only `observer` is self-minted."""
    _config_exists(monkeypatch)
    _no_brain_admin(monkeypatch)
    _patch_roles(monkeypatch, {"authority": [{"wa_id": "wa-2026-01-01-AAAAAA", "name": "ops"}]})

    assert await deps.is_setup_required(req) is False


@pytest.mark.asyncio
async def test_794_self_heal_still_fires_on_a_genuinely_empty_store(monkeypatch, req) -> None:
    """The other direction, and the reason this is not just `return False`.

    Config says configured, brain has no admin, and the node has no owner
    either — the real bugged-install state #794 exists to recover. If this ever
    returns False the recovery path is silently dead and the user has no way
    back in, which is strictly worse than the false wizard this fix removes.
    """
    _config_exists(monkeypatch)
    _no_brain_admin(monkeypatch)
    _patch_roles(monkeypatch, {})  # no root, no authority

    assert await deps.is_setup_required(req) is True


@pytest.mark.asyncio
async def test_observers_alone_do_not_count_as_an_owner(monkeypatch, req) -> None:
    """Adapter observers are minted on EVERY boot.

    Counting them would make a brand-new empty install report "setup complete"
    — the failure mode that makes a self-heal useless. Excluded by ROLE rather
    than by name matching, so a differently-named observer cannot slip through.
    """
    _config_exists(monkeypatch)
    _no_brain_admin(monkeypatch)
    _patch_roles(
        monkeypatch,
        {"observer": [{"wa_id": "wa-2026-08-14-2C136E", "name": "apiplatform_observer"}]},
    )

    assert await deps.is_setup_required(req) is True


@pytest.mark.asyncio
async def test_unreadable_substrate_defers_to_the_brain(monkeypatch, req) -> None:
    """A store that raises must not be read as "no owner".

    Asserting absence from a failed probe would force the wizard exactly when
    the substrate is unhealthy — the moment a spurious re-setup is most
    destructive. The probe returns None and the brain's answer stands.
    """
    _config_exists(monkeypatch)
    _no_brain_admin(monkeypatch)

    import ciris_engine.logic.persistence.stores.authentication_store as store

    def boom(role: str, limit: int = 1000) -> List[dict]:
        raise RuntimeError("persist engine not wired")

    monkeypatch.setattr(store, "_list_active_by_role", boom, raising=True)

    assert deps._node_owner_present() is None
    assert await deps.is_setup_required(req) is True


@pytest.mark.asyncio
async def test_first_run_still_short_circuits(monkeypatch, req) -> None:
    """A true first run stays a first run regardless of what the node holds."""
    monkeypatch.setattr(deps, "is_first_run", lambda: True, raising=True)
    _patch_roles(monkeypatch, {"root": [{"wa_id": "wa-root-x", "name": "someone"}]})

    assert await deps.is_setup_required(req) is True
