"""A placeholder API key must degrade the agent, never stop it booting.

WHAT HAPPENED. 2.9.16 added `_is_placeholder_api_key` so the agent would stop
dialling a key it can see is fake — `sk-test` can only ever return 401. That part
was right. Raising from `OpenAICompatibleClient.__init__` was not: nothing on the
Core Services path catches it, so on a real install (2.9.15 -> 2.9.18) it read:

    ✗ Core Services failed: The openai API key is a placeholder, not a
      credential (length 7).
    RuntimeError: Initialization sequence failed
    ERROR: Server process exited with code 1

The agent would not start at all. That is strictly WORSE than the bug it
replaced — before, the agent ran and only the LLM call failed. A guard against
dialling a bad credential turned a degraded feature into a dead process.

THE SHAPE THAT WAS ALREADY THERE. Twelve lines above the guard, a MISSING key
logs and RETURNS, leaving the agent healthy-but-degraded and letting persisted
runtime providers load. `no_llm_provider` is a supported state with its own
health warning and UI affordance. A placeholder is functionally a missing key, so
it takes the same branch.

These tests assert the RUNTIME outcome — "initialization completes" — rather than
the message, because the message was never the problem.
"""

from __future__ import annotations

from typing import Any, List

import pytest


class _Registry:
    def __init__(self) -> None:
        self.registered: List[str] = []

    def register_service(self, **kw: Any) -> None:
        self.registered.append(str(kw.get("metadata", {}).get("provider", "?")))


def _initializer(monkeypatch: pytest.MonkeyPatch, registry: _Registry) -> Any:
    from ciris_engine.logic.runtime.service_initializer import ServiceInitializer

    si = ServiceInitializer.__new__(ServiceInitializer)
    si.telemetry_service = None
    si.time_service = None
    si.service_registry = registry
    si._skip_llm_init = False
    si.llm_service = None
    si._llm_replica_services = []
    si._services_started_count = 0
    si.bus_manager = None
    si.resource_monitor_service = None
    si.audit_service = None
    return si


class _Config:
    class services:  # noqa: N801 - mirrors the real config shape
        pass


#: Every one of these produced `RuntimeError: Initialization sequence failed`.
PLACEHOLDERS = ["sk-test", "changeme", "your-api-key-here", "SK-TEST", "  sk-test  "]


@pytest.mark.asyncio
@pytest.mark.parametrize("key", PLACEHOLDERS)
async def test_a_placeholder_key_does_not_raise(monkeypatch: pytest.MonkeyPatch, key: str) -> None:
    """THE REGRESSION: this raised, and the raise killed the whole agent."""
    monkeypatch.setenv("OPENAI_API_KEY", key)
    monkeypatch.delenv("CIRIS_OPENAI_API_BASE", raising=False)
    registry = _Registry()

    await _initializer(monkeypatch, registry)._initialize_llm_services(_Config())

    assert registry.registered == [], "a key that can only 401 must not be registered"


@pytest.mark.asyncio
async def test_a_real_key_is_still_registered(monkeypatch: pytest.MonkeyPatch) -> None:
    """The guard must not cost us the working case."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-" + "a" * 48)
    monkeypatch.delenv("CIRIS_OPENAI_API_BASE", raising=False)
    registry = _Registry()

    si = _initializer(monkeypatch, registry)
    import ciris_engine.logic.runtime.service_initializer as mod

    started: List[Any] = []

    class _Client:
        def __init__(self, **kw: Any) -> None:
            self.kw = kw

        async def start(self) -> None:
            started.append(self)

    monkeypatch.setattr(mod, "OpenAICompatibleClient", _Client, raising=True)

    await si._initialize_llm_services(_Config())

    assert started, "a real key must still produce a live provider"
    assert registry.registered, "a real key must still be registered"


@pytest.mark.asyncio
async def test_a_local_runtime_dummy_key_is_not_treated_as_placeholder(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Ollama/llama.cpp are handed dummy keys ON PURPOSE — that is correct config.

    Breaking local inference to catch a cloud typo would be a bad trade, and this
    is the case most likely to regress if someone widens the detector.
    """
    monkeypatch.setenv("OPENAI_API_KEY", "ollama")
    monkeypatch.setenv("CIRIS_OPENAI_API_BASE", "http://jetson.local:11434/v1")
    registry = _Registry()

    si = _initializer(monkeypatch, registry)
    import ciris_engine.logic.runtime.service_initializer as mod

    started: List[Any] = []

    class _Client:
        def __init__(self, **kw: Any) -> None: ...

        async def start(self) -> None:
            started.append(self)

    monkeypatch.setattr(mod, "OpenAICompatibleClient", _Client, raising=True)

    await si._initialize_llm_services(_Config())

    assert started, "a local runtime's dummy key is valid configuration, not a placeholder"


@pytest.mark.asyncio
async def test_the_secondary_provider_cannot_kill_boot_either(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`_initialize_secondary_llm` has no try/except around it either.

    An OPTIONAL fallback provider must never be able to take the process down;
    that is the same defect one layer over.

    The base URL matters: this method DEFAULTS to `http://localhost:11434/v1`,
    and a dummy key against a local runtime is correct configuration, not a
    placeholder. So the cloud endpoint has to be named explicitly to reach the
    guard at all — the first version of this test asserted against the local
    default and failed, which is the detector behaving exactly as intended.
    """
    monkeypatch.setenv("CIRIS_OPENAI_API_BASE_2", "https://api.openai.com/v1")
    registry = _Registry()
    si = _initializer(monkeypatch, registry)

    await si._initialize_secondary_llm(_Config(), "sk-test")

    assert registry.registered == []
