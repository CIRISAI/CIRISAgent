"""Under the mock LLM the federation runtime runs normally; mock traces just never reach it (CIRISAgent#1244).

Two cuts of this fix broke every Staged QA leg by withholding the wrong layer:

* transport off: ``/v1/agent/status`` 503 "Identity verification unavailable";
* delivery controller off: ``resolve_bearer`` raises "federation delivery not
  started", so every authenticated request answers 503.

Session verification depends on both. So under the mock the edge transport,
``start_federation_delivery`` and the node-fold reprime all run, and the
no-egress guarantee lives upstream: mock traces are never sealed into the
federation store (``MockLocalOnlyEngine``, see
tests/ciris_adapters/ciris_accord_metrics/test_mock_traces_never_stored.py) and no
replication grant is authored (test_trace_sharing_mock_guard.py).

Drives ``initialize_edge_runtime`` against a real persist Engine. Only the Edge
transport and the delivery controller are stubbed, so nothing touches a network.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Iterator, List

import pytest


class _FakeEdge:
    def signer_key_id(self) -> str:
        return "test-key"


@pytest.fixture
def engine(tmp_path: Path) -> Iterator[Any]:
    import ciris_engine.logic.persistence.models.graph as graph_mod
    from ciris_engine.logic.persistence._substrate import Engine, reset_engine  # type: ignore[import-untyped]
    from ciris_engine.logic.persistence.models.graph import set_persist_engine

    (tmp_path / "local_signing.seed").write_bytes(os.urandom(32))
    (tmp_path / "local_pqc_signing.seed").write_bytes(os.urandom(32))
    prior_engine, prior_dsn = graph_mod._engine, graph_mod._engine_dsn
    reset_engine()
    dsn = f"sqlite:///{tmp_path}/t.db"
    real = Engine(
        dsn,
        "test-key",
        local_key_id="test-key",
        local_key_path=str(tmp_path / "local_signing.seed"),
        local_pqc_key_id="test-key",
        local_pqc_key_path=str(tmp_path / "local_pqc_signing.seed"),
    )
    set_persist_engine(real, dsn=dsn)
    try:
        yield real
    finally:
        graph_mod._engine, graph_mod._engine_dsn = prior_engine, prior_dsn


@pytest.fixture
def edge_boot(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Dict[str, List[Any]]:
    """Record what edge init asks for: transport kwargs and delivery starts."""
    import ciris_server  # type: ignore[import-not-found, import-untyped, unused-ignore]

    import ciris_engine.logic.persistence._substrate as substrate
    from ciris_engine.logic.runtime import edge_runtime

    seen: Dict[str, List[Any]] = {"init_kwargs": [], "delivery_starts": []}

    def _init(*args: Any, **kwargs: Any) -> _FakeEdge:
        seen["init_kwargs"].append(kwargs)
        return _FakeEdge()

    def _start(**kwargs: Any) -> int:
        seen["delivery_starts"].append(kwargs)
        return 1

    monkeypatch.setattr(edge_runtime, "_edge_disabled", lambda: False)
    monkeypatch.setattr(edge_runtime, "_edge", None)
    monkeypatch.setattr(edge_runtime, "_spawn_delivery_rooting_probe", lambda engine, edge: None)
    monkeypatch.setattr(substrate, "init_edge_runtime", _init)
    monkeypatch.setattr(ciris_server, "start_federation_delivery", _start, raising=False)
    monkeypatch.setenv("CIRIS_FEDERATION_DELIVERY", "true")
    monkeypatch.setenv("CIRIS_ACCORD_METRICS_CONSENT", "true")
    monkeypatch.setenv("CIRIS_HOME", str(tmp_path))
    return seen


class _SubstrateAuthModel:
    """resolve_bearer's precondition, as the substrate states it at runtime.

    ``ciris_server.resolve_bearer`` raises ``RuntimeError("resolve_bearer:
    federation delivery not started — cannot verify")`` until
    ``start_federation_delivery`` has run (Staged QA, 0267c85b8). The real call
    needs a live embedded edge that dials the canonical, which a unit test must
    not do, so this models exactly that precondition and is wired to the same
    two names the runtime and the auth dependency call.
    """

    def __init__(self) -> None:
        self.started = False

    def start_federation_delivery(self, **_: Any) -> int:
        self.started = True
        return 1

    def resolve_bearer(self, token: str) -> Dict[str, Any]:
        if not self.started:
            raise RuntimeError("resolve_bearer: federation delivery not started — cannot verify")
        return {"wa_id": "wa-qa", "name": "qa", "role": "ROOT", "scopes": [], "actor": None}


def test_mock_llm_boot_starts_delivery_so_sessions_verify(
    mock_llm_mode: None, engine: Any, edge_boot: Dict[str, List[Any]], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import ciris_server  # type: ignore[import-not-found, import-untyped, unused-ignore]

    from ciris_engine.logic.adapters.api.dependencies.auth import resolve_substrate_session
    from ciris_engine.logic.runtime import edge_runtime
    from ciris_engine.logic.runtime.edge_runtime import initialize_edge_runtime
    from ciris_engine.logic.utils.mock_llm_guard import is_mock_llm_active

    model = _SubstrateAuthModel()
    monkeypatch.setattr(ciris_server, "start_federation_delivery", model.start_federation_delivery, raising=False)
    monkeypatch.setattr(ciris_server, "resolve_bearer", model.resolve_bearer, raising=False)

    assert is_mock_llm_active(), "test premise: the guard is active"
    initialize_edge_runtime(tmp_path / "identity")

    assert edge_boot["init_kwargs"][0]["enable_transport"] is True
    assert edge_runtime.is_available() and edge_runtime.get_init_error() is None
    assert model.started, "the delivery controller must start under the mock: resolve_bearer depends on it"
    # The real auth dependency must not answer 503 for a well-formed session.
    assert resolve_substrate_session("sess:wa-qa:abc")["wa_id"] == "wa-qa"


def test_real_llm_boot_keeps_transport_and_delivery(
    real_llm_mode: None, engine: Any, edge_boot: Dict[str, List[Any]], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from ciris_engine.logic.runtime.edge_runtime import initialize_edge_runtime

    monkeypatch.setenv("CIRIS_FEDERATION_DELIVERY", "true")
    initialize_edge_runtime(tmp_path / "identity")

    assert edge_boot["init_kwargs"][0]["enable_transport"] is True
    assert len(edge_boot["delivery_starts"]) == 1


@pytest.mark.parametrize("mode", ["mock_llm_mode", "real_llm_mode"])
def test_node_fold_reprime_runs_in_both_modes(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    """The reprime keeps delivery 'started' across an in-process re-serve (mobile fold)."""
    import sys
    import types

    from ciris_engine.logic.runtime import node_fold

    request.getfixturevalue(mode)
    calls: List[int] = []
    fake = types.ModuleType("ciris_server")
    fake.reprime_federation_delivery = lambda: calls.append(1) or 1  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "ciris_server", fake)

    node_fold._reprime_federation_delivery("reuse")
    assert len(calls) == 1
