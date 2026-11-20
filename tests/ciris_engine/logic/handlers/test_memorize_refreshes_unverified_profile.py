"""An approved amendment reads its chain head from a fresh profile check when the cached one is not VERIFIED.

RATCHET runs 44776804283 / 44780287540: the base link landed 0.3 s after the boot check, so a cached UNANCHORED
check would leave an approved amendment with no chain head to follow.
"""

import logging
from types import SimpleNamespace
from typing import Any, List

import pytest

from ciris_engine.logic.context import identity_profile, system_snapshot_helpers
from ciris_engine.logic.handlers.memory.memorize_handler import MemorizeHandler
from ciris_engine.schemas.infrastructure.identity_variance import IdentityProfileStatus


def _handler(memory: object) -> Any:
    return SimpleNamespace(bus_manager=SimpleNamespace(memory=memory), logger=logging.getLogger("t"))


async def _refresh(handler: Any) -> None:
    await MemorizeHandler._refresh_unverified_profile(handler)  # type: ignore[arg-type]


@pytest.mark.asyncio
@pytest.mark.parametrize("cached", [None, IdentityProfileStatus.UNANCHORED, IdentityProfileStatus.MISMATCH])
async def test_an_unverified_cached_check_is_refreshed(monkeypatch: pytest.MonkeyPatch, cached: Any) -> None:
    seen: List[object] = []
    memory = object()
    profile = None if cached is None else SimpleNamespace(status=cached)
    monkeypatch.setattr(identity_profile, "latest_identity_profile", lambda: profile)

    async def extract(service: object) -> Any:
        seen.append(service)
        return SimpleNamespace(profile=None), None

    monkeypatch.setattr(system_snapshot_helpers, "_extract_agent_identity", extract)
    await _refresh(_handler(memory))
    assert seen == [memory]


@pytest.mark.asyncio
async def test_a_verified_check_is_kept(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        identity_profile, "latest_identity_profile", lambda: SimpleNamespace(status=IdentityProfileStatus.VERIFIED)
    )

    async def extract(service: object) -> Any:
        raise AssertionError("a VERIFIED check is not re-run")

    monkeypatch.setattr(system_snapshot_helpers, "_extract_agent_identity", extract)
    await _refresh(_handler(object()))


@pytest.mark.asyncio
async def test_a_failed_refresh_never_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(identity_profile, "latest_identity_profile", lambda: None)

    async def boom(service: object) -> Any:
        raise RuntimeError("graph down")

    monkeypatch.setattr(system_snapshot_helpers, "_extract_agent_identity", boom)
    await _refresh(_handler(object()))
