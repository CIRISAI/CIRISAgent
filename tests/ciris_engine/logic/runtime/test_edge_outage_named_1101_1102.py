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
