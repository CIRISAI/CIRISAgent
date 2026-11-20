"""The identity profile is checked at boot, so an unanchored agent asks for its base link before any message.

RATCHET run 44748258728 (v2.23.0-stable): 120 s after setup nothing was pending; the base-link deferral opened only
when the first message built a context, so every agent's first conversation ran unanchored.
"""

from types import SimpleNamespace
from typing import Any, List

import pytest

from ciris_engine.logic.context import system_snapshot_helpers
from ciris_engine.logic.runtime.ciris_runtime import CIRISRuntime


async def _check(memory: object) -> None:
    """Run the boot check against a stand-in runtime: it reads only ``memory_service``."""
    await CIRISRuntime._check_identity_profile_at_boot(SimpleNamespace(memory_service=memory))  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_boot_runs_the_identity_load_that_opens_the_base_link(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: List[object] = []
    memory = object()

    async def extract(service: object) -> Any:
        seen.append(service)
        return SimpleNamespace(profile=None), None

    monkeypatch.setattr(system_snapshot_helpers, "_extract_agent_identity", extract)
    await _check(memory)
    assert seen == [memory]


@pytest.mark.asyncio
async def test_a_failed_boot_check_never_fails_boot(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    async def boom(service: object) -> Any:
        raise RuntimeError("graph unavailable")

    monkeypatch.setattr(system_snapshot_helpers, "_extract_agent_identity", boom)
    await _check(object())  # no raise
    assert any("boot check failed" in r.getMessage() for r in caplog.records)
