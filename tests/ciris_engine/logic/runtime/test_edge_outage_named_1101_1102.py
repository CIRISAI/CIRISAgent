"""An Edge outage is named everywhere it is felt, and the transport is released at exit.

CIRISAgent#1101: session auth (`sess:` bearers) hard-depends on the in-process
substrate; with Edge down every session answered 503 while health stayed green.
CIRISAgent#1102: Python exited while the Rust transport threads held :4242/:4243,
so the next boot's Edge init failed with a generic error.
"""

from __future__ import annotations

import sys
import types
from typing import Any, List

import pytest

from ciris_engine.logic.adapters.api.dependencies.auth import _identity_unavailable_detail
from ciris_engine.logic.adapters.api.routes.system.health import _edge_runtime_warnings
from ciris_engine.logic.runtime import edge_runtime, node_fold


@pytest.fixture(autouse=True)
def _clean_edge_state():
    edge_runtime.reset_edge_runtime()
    yield
    edge_runtime.reset_edge_runtime()


def test_port_contention_is_diagnosed_in_operator_terms(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CIRIS_EDGE_LISTEN_ADDR", "0.0.0.0:4242")
    text = edge_runtime._describe_init_failure(OSError("bind failed: Address already in use (os error 98)"))
    assert "4242" in text and "4243" in text and "CIRISAgent#1102" in text and "ss -ltnp" in text


def test_other_failures_keep_their_own_words() -> None:
    assert edge_runtime._describe_init_failure(RuntimeError("identity load failure")) == "identity load failure"


def test_init_error_is_remembered_and_cleared_by_reset() -> None:
    edge_runtime._init_error = "Edge transport ports are held by another process"
    assert edge_runtime.get_init_error() == "Edge transport ports are held by another process"
    edge_runtime.reset_edge_runtime()
    assert edge_runtime.get_init_error() is None


def test_health_names_the_outage_and_the_503_carries_the_reason(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(edge_runtime, "_edge_disabled", lambda: False)
    edge_runtime._init_error = "Edge transport ports are held by another process (os error 98)"
    warnings = _edge_runtime_warnings()
    assert len(warnings) == 1
    w = warnings[0]
    assert w.code == "edge_runtime_unavailable" and w.severity == "error"
    assert "503" in w.message and "os error 98" in w.message
    detail = _identity_unavailable_detail()
    assert detail.startswith("Identity verification unavailable: edge runtime not initialized")
    assert "os error 98" in detail


def test_disabled_by_env_is_not_an_outage(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(edge_runtime, "_edge_disabled", lambda: True)
    assert _edge_runtime_warnings() == []
    assert _identity_unavailable_detail() == "Identity verification unavailable: edge runtime disabled by environment"


def test_a_live_edge_produces_no_warning(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(edge_runtime, "_edge_disabled", lambda: False)
    edge_runtime._edge = object()
    assert _edge_runtime_warnings() == []
    assert _identity_unavailable_detail() == "Identity verification unavailable"


class _FakeEdge:
    def __init__(self) -> None:
        self.closed = 0

    def close(self) -> None:
        self.closed += 1


def test_close_edge_runtime_releases_the_transport_and_is_idempotent() -> None:
    fake = _FakeEdge()
    edge_runtime._edge = fake
    assert edge_runtime.close_edge_runtime() is True
    assert fake.closed == 1 and not edge_runtime.is_available()
    assert edge_runtime.close_edge_runtime() is False  # nothing left to close


def test_close_never_raises_when_the_binding_raises() -> None:
    class _Bad:
        def close(self) -> None:
            raise RuntimeError("transport already gone")

    edge_runtime._edge = _Bad()
    assert edge_runtime.close_edge_runtime() is False
    assert not edge_runtime.is_available()


def test_stop_node_fold_calls_shutdown_node_only_when_this_process_started_a_node(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: List[Any] = []
    fake_server = types.SimpleNamespace(shutdown_node=lambda timeout_secs=30.0: calls.append(timeout_secs) or True)
    monkeypatch.setitem(sys.modules, "ciris_server", fake_server)

    monkeypatch.setattr(node_fold, "_node_thread", None)
    assert node_fold.stop_node_fold() is None and calls == []

    monkeypatch.setattr(node_fold, "_node_thread", object())
    monkeypatch.setattr(node_fold, "_node_ready", True)
    assert node_fold.stop_node_fold(timeout_secs=7.0) is True
    assert calls == [7.0] and node_fold._node_thread is None and node_fold._node_ready is False


# --- the branches that only fire when something is already wrong -------------


def test_stop_node_fold_when_ciris_server_is_not_importable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "ciris_server", None)  # `import ciris_server` raises ImportError
    monkeypatch.setattr(node_fold, "_node_thread", object())
    assert node_fold.stop_node_fold() is None


def test_stop_node_fold_when_the_binding_predates_shutdown_node(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "ciris_server", types.SimpleNamespace())
    monkeypatch.setattr(node_fold, "_node_thread", object())
    assert node_fold.stop_node_fold() is None


def test_stop_node_fold_never_raises_and_forgets_the_thread(monkeypatch: pytest.MonkeyPatch) -> None:
    def _boom(timeout_secs: float = 30.0) -> bool:
        raise RuntimeError("node already gone")

    monkeypatch.setitem(sys.modules, "ciris_server", types.SimpleNamespace(shutdown_node=_boom))
    monkeypatch.setattr(node_fold, "_node_thread", object())
    monkeypatch.setattr(node_fold, "_node_ready", True)
    assert node_fold.stop_node_fold() is False
    assert node_fold._node_thread is None and node_fold._node_ready is False


def test_close_edge_runtime_when_the_binding_has_no_close() -> None:
    edge_runtime._edge = object()  # pre-2.4.0 edge: nothing to call
    assert edge_runtime.close_edge_runtime() is False
    assert not edge_runtime.is_available()


def test_the_detail_and_the_warning_never_become_the_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    def _explode() -> bool:
        raise RuntimeError("edge module in a bad state")

    monkeypatch.setattr(edge_runtime, "is_available", _explode)
    assert _identity_unavailable_detail() == "Identity verification unavailable"
    assert _edge_runtime_warnings() == []


@pytest.mark.asyncio
async def test_release_substrate_is_bounded_and_never_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """A hung node stop and a raising edge close both log and let shutdown finish."""
    import asyncio
    import time

    from ciris_engine.logic.runtime.ciris_runtime import CIRISRuntime

    def _hangs(timeout_secs: float = 30.0) -> bool:
        time.sleep(0.3)
        return True

    def _raises() -> bool:
        raise RuntimeError("transport gone")

    monkeypatch.setattr(node_fold, "stop_node_fold", _hangs)
    monkeypatch.setattr(edge_runtime, "close_edge_runtime", _raises)

    # Shrink the budgets so the "hung" branch is exercised in well under a second.
    orig_wait_for = asyncio.wait_for

    async def _tight(awaitable: Any, timeout: float) -> Any:
        return await orig_wait_for(awaitable, timeout=0.05)

    monkeypatch.setattr(asyncio, "wait_for", _tight)
    await CIRISRuntime._release_substrate(object())  # type: ignore[arg-type]  -- only the module functions are used
    monkeypatch.setattr(asyncio, "wait_for", orig_wait_for)
    await asyncio.sleep(0.5)  # let the "hung" worker thread finish before the interpreter exits
