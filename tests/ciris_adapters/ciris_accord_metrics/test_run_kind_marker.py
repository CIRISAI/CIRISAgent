"""Run-kind marker on sealed traces + the local tee under the mock LLM (#1244 / #1245).

The marker rides the existing ``deployment_type`` string of the signed
deployment_profile / correlation_metadata blocks, so the canonical sees it at
every trace level with no wire change. ``mock`` comes only from the mock LLM and
cannot be overridden; ``qa`` / ``battery`` come from the harness.

The local tee is an ALLOWED sink under the mock LLM: the LensClient still gets
its ``local_copy_dir``, so QA keeps its on-disk trace stream while nothing
ships remotely.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path
from typing import Any, Dict, List

import pytest

from ciris_adapters.ciris_accord_metrics.services import AccordMetricsService


class _StubEngine:
    def local_key_id(self) -> str:
        return "k"

    def local_derived_key_id(self) -> str:
        return "k-derived"


@pytest.fixture
def lens_kwargs(monkeypatch: pytest.MonkeyPatch) -> List[Dict[str, Any]]:
    """Capture LensClient construction; no substrate, no network."""
    captured: List[Dict[str, Any]] = []

    class _LensClient:
        def __init__(self, consent_ts: Any, level: str, **kwargs: Any) -> None:
            captured.append({"consent_ts": consent_ts, "level": level, **kwargs})

    fake = types.ModuleType("ciris_server")
    fake.LensClient = _LensClient  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "ciris_server", fake)

    import ciris_engine.logic.persistence.models.graph as graph_mod
    import ciris_engine.logic.runtime.edge_runtime as edge_mod

    monkeypatch.setattr(graph_mod, "get_persist_engine", lambda: _StubEngine())
    monkeypatch.setattr(edge_mod, "get_federation_address", lambda: None)
    return captured


def _build(tmp_path: Path, **config: Any) -> Dict[str, Any]:
    service = AccordMetricsService(config={"local_copy_dir": str(tmp_path), "consent_given": True, **config})
    service._build_lens_client()
    return {"profile": service._build_deployment_profile(), "metrics_type": service.get_metrics()["deployment_type"]}


def test_mock_llm_marks_mock_and_keeps_the_local_tee(
    mock_llm_mode: None, lens_kwargs: List[Dict[str, Any]], tmp_path: Path
) -> None:
    out = _build(tmp_path, deployment_type="production")  # operator config cannot hide it
    kw = lens_kwargs[0]
    assert kw["deployment_type"] == "mock"
    assert kw["deployment_profile"]["deployment_type"] == "mock"
    assert out["metrics_type"] == "mock"
    assert kw["local_copy_dir"] and Path(kw["local_copy_dir"]).parent == tmp_path


@pytest.mark.parametrize("kind", ["qa", "battery"])
def test_harness_declared_run_kind_is_marked(
    real_llm_mode: None,
    lens_kwargs: List[Dict[str, Any]],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    kind: str,
) -> None:
    monkeypatch.setenv("CIRIS_TRACE_RUN_KIND", kind)
    _build(tmp_path)
    assert lens_kwargs[0]["deployment_type"] == kind
    assert lens_kwargs[0]["deployment_profile"]["deployment_type"] == kind


def test_production_run_is_unchanged(real_llm_mode: None, lens_kwargs: List[Dict[str, Any]], tmp_path: Path) -> None:
    _build(tmp_path)
    assert lens_kwargs[0]["deployment_type"] is None  # undeclared, exactly as before
    assert lens_kwargs[0]["deployment_profile"]["deployment_type"] == "production"


def test_operator_value_survives_on_a_production_run(
    real_llm_mode: None, lens_kwargs: List[Dict[str, Any]], tmp_path: Path
) -> None:
    _build(tmp_path, deployment_type="research")
    assert lens_kwargs[0]["deployment_type"] == "research"
