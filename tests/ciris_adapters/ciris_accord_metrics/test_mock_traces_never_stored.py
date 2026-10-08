"""Mock-LLM traces never enter the replicable federation store (CIRISAgent#1244, Codex P1).

Turning the transport off while the mock runs is not enough. A trace sealed into
the local store sits in the backlog that the substrate's
``promote_consented_backlog`` lifts once a ``trace:`` replication grant covers
it, for example after a restart on a real LLM. Promotion is substrate-owned
(Rust) with no agent-side filter. So under the mock LLM the LensClient seals,
signs and tees through ``MockLocalOnlyEngine``, and ``receive_and_persist``
becomes a no-op: zero trace rows, so nothing is ever eligible.

Real persist Engine + real substrate LensClient; nothing touches a network.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Any, Dict, Iterator, List

import pytest

from ciris_adapters.ciris_accord_metrics.services import AccordMetricsService, MockLocalOnlyEngine

lens_core = pytest.importorskip("ciris_server")


@pytest.fixture
def engine(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Any]:
    import ciris_engine.logic.persistence.models.graph as graph_mod
    import ciris_engine.logic.runtime.edge_runtime as edge_mod
    from ciris_engine.logic.persistence._substrate import Engine, reset_engine  # type: ignore[import-untyped]
    from ciris_engine.logic.persistence.models.graph import set_persist_engine

    (tmp_path / "s.seed").write_bytes(os.urandom(32))
    (tmp_path / "p.seed").write_bytes(os.urandom(32))
    prior = graph_mod._engine, graph_mod._engine_dsn
    reset_engine()
    dsn = f"sqlite:///{tmp_path}/t.db"
    real = Engine(
        dsn,
        "test-key",
        local_key_id="test-key",
        local_key_path=str(tmp_path / "s.seed"),
        local_pqc_key_id="test-key",
        local_pqc_key_path=str(tmp_path / "p.seed"),
    )
    real.register_self_federation_key("agent", "test-key", None, None, None)
    recording = _RecordingEngine(real)
    set_persist_engine(recording, dsn=dsn)
    monkeypatch.setattr(edge_mod, "get_federation_address", lambda: None)
    try:
        yield recording
    finally:
        graph_mod._engine, graph_mod._engine_dsn = prior


class _RecordingEngine:
    """The real Engine, recording every batch that reaches ``receive_and_persist``.

    Asserting on what reaches the store's ingest call (and what it inserted)
    rather than on a sqlite file keeps the test independent of which DB the
    process-wide persist singleton happens to be pinned to under xdist.
    """

    def __init__(self, inner: Any) -> None:
        self._inner = inner
        self.persisted: List[Dict[str, Any]] = []

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)

    def receive_and_persist(self, batch_bytes: bytes, pre_verified: bool = False) -> Any:
        result = self._inner.receive_and_persist(batch_bytes, pre_verified)
        self.persisted.append({"batch": bytes(batch_bytes).decode("utf-8", "replace"), "result": dict(result)})
        return result


def _stored(engine: _RecordingEngine, thought_id: str) -> int:
    """trace_events inserted into the federation store for batches naming thought_id."""
    return sum(int(p["result"].get("trace_events_inserted", 0)) for p in engine.persisted if thought_id in p["batch"])


def _reached_store(engine: _RecordingEngine, thought_id: str) -> bool:
    return any(thought_id in p["batch"] for p in engine.persisted)


def _seal_one(tmp_path: Path, thought_id: str, tee: Path) -> List[Dict[str, Any]]:
    service = AccordMetricsService(
        config={"trace_level": "detailed", "consent_given": True, "local_copy_dir": str(tee), "adapter_id": thought_id}
    )
    service._lens = service._build_lens_client()
    outcomes = []
    for event_type in ("THOUGHT_START", "ACTION_RESULT"):
        event = {"event_type": event_type, "thought_id": thought_id, "round_number": 1, "execution_success": True}
        asyncio.run(service._process_single_event(event))
    outcomes.append({"local_only": service._lens_local_only, "completed": service._traces_completed})
    outcomes.append(service.get_metrics())
    return outcomes


def test_mock_trace_is_teed_but_never_stored_then_a_real_restart_has_nothing_to_promote(
    engine: Any, tmp_path: Path, request: pytest.FixtureRequest
) -> None:
    tee = tmp_path / "tee"

    # 1. Mock-LLM run: sealed + teed, zero rows in the federation store.
    request.getfixturevalue("mock_llm_mode")
    mock = _seal_one(tmp_path, "th_mock_1", tee)
    assert mock[0] == {"local_only": True, "completed": 1}
    assert list((tee / "th_mock_1").glob("lens-batch-*.json")), "the local tee is an allowed sink and must still work"
    assert not _reached_store(engine, "th_mock_1"), "a mock trace reached the federation store"

    # 2. "Restart" on a real LLM against the same store: a real trace persists
    #    normally, and the mock trace is still absent, so no trace: grant can
    #    ever promote it (there is nothing to promote).
    from ciris_engine.logic.utils import mock_llm_guard

    os.environ.pop("CIRIS_MOCK_LLM", None)
    mock_llm_guard._reset_for_tests()
    assert not mock_llm_guard.is_mock_llm_active()
    real = _seal_one(tmp_path, "th_real_1", tee)
    assert real[0]["local_only"] is False
    assert _stored(engine, "th_real_1") > 0, "a real-LLM trace must still persist"
    assert not _reached_store(engine, "th_mock_1")


def test_a_late_mock_latch_rebuilds_the_client_as_local_only(engine: Any, tmp_path: Path, real_llm_mode: None) -> None:
    service = AccordMetricsService(config={"trace_level": "detailed", "consent_given": True})
    service._lens = service._build_lens_client()
    assert service._lens_local_only is False

    from ciris_engine.logic.utils.mock_llm_guard import mark_mock_llm_active

    mark_mock_llm_active("test-late")
    for event_type in ("THOUGHT_START", "ACTION_RESULT"):
        asyncio.run(service._process_single_event({"event_type": event_type, "thought_id": "th_late"}))
    assert service._lens_local_only is True
    assert not _reached_store(engine, "th_late")


def test_wrapper_delegates_everything_but_persist() -> None:
    class _Inner:
        def local_key_id(self) -> str:
            return "k"

        def receive_and_persist(self, *_: Any, **__: Any) -> Dict[str, int]:
            raise AssertionError("mock traces must not reach the store")

    wrapped = MockLocalOnlyEngine(_Inner())
    assert wrapped.local_key_id() == "k"
    assert wrapped.receive_and_persist(b"{}")["trace_events_inserted"] == 0
