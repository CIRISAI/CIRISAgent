"""Under the mock LLM the edge carries no transport and starts no delivery (CIRISAgent#1244).

The transport auto-seeds the PRODUCTION canonical dial from persist's baked
hint, and the delivery controller is what ships sealed traces to it. A mock-LLM
boot with ``CIRIS_FEDERATION_DELIVERY=true`` (the default) and consent on must
therefore come up with ``enable_transport=False`` and never call
``start_federation_delivery``. Otherwise a replication grant left by an earlier
real-LLM run on the same DB would ship this run's mock traces.

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


def test_mock_llm_boot_has_no_transport_and_no_delivery(
    mock_llm_mode: None, engine: Any, edge_boot: Dict[str, List[Any]], tmp_path: Path
) -> None:
    from ciris_engine.logic.runtime.edge_runtime import initialize_edge_runtime

    initialize_edge_runtime(tmp_path / "identity")

    assert edge_boot["init_kwargs"], "edge init never ran: test premise broken"
    assert edge_boot["init_kwargs"][0]["enable_transport"] is False
    assert edge_boot["delivery_starts"] == []


def test_real_llm_boot_keeps_transport_and_delivery(
    real_llm_mode: None, engine: Any, edge_boot: Dict[str, List[Any]], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from ciris_engine.logic.runtime.edge_runtime import initialize_edge_runtime

    monkeypatch.setenv("CIRIS_FEDERATION_DELIVERY", "true")
    initialize_edge_runtime(tmp_path / "identity")

    assert edge_boot["init_kwargs"][0]["enable_transport"] is True
    assert len(edge_boot["delivery_starts"]) == 1


@pytest.mark.parametrize("mode,expected", [("mock_llm_mode", 0), ("real_llm_mode", 1)])
def test_node_fold_reprime_is_refused_under_the_mock_llm(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch, mode: str, expected: int
) -> None:
    """The node fold re-drives the canonical prime on reuse/post-bind; never under the mock."""
    import sys
    import types

    from ciris_engine.logic.runtime import node_fold

    request.getfixturevalue(mode)
    calls: List[int] = []
    fake = types.ModuleType("ciris_server")
    fake.reprime_federation_delivery = lambda: calls.append(1) or 1  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "ciris_server", fake)

    node_fold._reprime_federation_delivery("reuse")
    assert len(calls) == expected
