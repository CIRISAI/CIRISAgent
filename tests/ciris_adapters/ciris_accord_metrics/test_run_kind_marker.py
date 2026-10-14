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

import json
import sys
import types
from pathlib import Path
from typing import Any, Dict, List

import pytest

from ciris_adapters.ciris_accord_metrics import egress_schema
from ciris_adapters.ciris_accord_metrics.egress_schema import DEFAULT_TRACE_FORMAT_VERSION, TraceFormatVersion
from ciris_adapters.ciris_accord_metrics.services import TRACE_FORMAT_VERSION_ENV_VAR, AccordMetricsService


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


# ---------------------------------------------------------------------------
# trace_format version switch (CIRISAgent#1249). v2.8.0 is published but NOT
# emitted by default: persist v54.1 and earlier refuse v2.8.0 traces whole.
# ---------------------------------------------------------------------------


@pytest.fixture
def no_format_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(TRACE_FORMAT_VERSION_ENV_VAR, raising=False)
    monkeypatch.delenv("CIRIS_TRACE_RUN_KIND", raising=False)


def test_the_default_trace_format_is_still_2_7_0(
    no_format_env: None, real_llm_mode: None, lens_kwargs: List[Dict[str, Any]], tmp_path: Path
) -> None:
    assert DEFAULT_TRACE_FORMAT_VERSION == TraceFormatVersion.V2_7_0
    service = AccordMetricsService(config={"local_copy_dir": str(tmp_path), "consent_given": True})
    service._build_lens_client()
    assert service.get_metrics()["trace_format_version"] == "2.7.0"
    # Byte-identical to 2.15.0: exactly the six FSD §3.2 fields, nothing added.
    assert lens_kwargs[0]["deployment_profile"] == {
        "agent_role": "unknown",
        "agent_template": "unknown-default-unspecified",
        "deployment_domain": "general",
        "deployment_type": "production",
        "deployment_region": None,
        "deployment_trust_mode": "sovereign",
    }
    assert json.dumps(lens_kwargs[0]["deployment_profile"]) == (
        '{"agent_role": "unknown", "agent_template": "unknown-default-unspecified", '
        '"deployment_domain": "general", "deployment_type": "production", '
        '"deployment_region": null, "deployment_trust_mode": "sovereign"}'
    )
    _assert_wire_stamp_untouched(lens_kwargs[0])


def _assert_wire_stamp_untouched(kw: Dict[str, Any]) -> None:
    """trace_schema_version stays the substrate's "3.0.0" canonicalization epoch
    in both modes: the agent never passes it, so lens-core stamps its default."""
    from ciris_adapters.ciris_accord_metrics.services import TRACE_SCHEMA_VERSION

    assert TRACE_SCHEMA_VERSION == "3.0.0"
    assert "trace_schema_version" not in kw
    assert "trace_schema_version" not in kw["deployment_profile"]


@pytest.mark.parametrize("kind", ["qa", "battery"])
def test_2_7_0_keeps_the_marker_in_deployment_type(
    no_format_env: None,
    real_llm_mode: None,
    lens_kwargs: List[Dict[str, Any]],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    kind: str,
) -> None:
    monkeypatch.setenv("CIRIS_TRACE_RUN_KIND", kind)
    _build(tmp_path, deployment_type="research")
    assert lens_kwargs[0]["deployment_type"] == kind
    assert lens_kwargs[0]["deployment_profile"]["deployment_type"] == kind
    assert "run_kind" not in lens_kwargs[0]["deployment_profile"]
    assert "trace_format_version" not in lens_kwargs[0]["deployment_profile"]
    _assert_wire_stamp_untouched(lens_kwargs[0])


@pytest.mark.parametrize("via", ["env", "config"])
@pytest.mark.parametrize("kind", ["production", "qa", "battery"])
def test_2_8_0_moves_run_kind_into_the_envelope(
    no_format_env: None,
    real_llm_mode: None,
    lens_kwargs: List[Dict[str, Any]],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    via: str,
    kind: str,
) -> None:
    if kind != "production":
        monkeypatch.setenv("CIRIS_TRACE_RUN_KIND", kind)
    config: Dict[str, Any] = {"deployment_type": "research"}
    if via == "env":
        monkeypatch.setenv(TRACE_FORMAT_VERSION_ENV_VAR, "2.8.0")
    else:
        config["trace_format_version"] = "2.8.0"
    out = _build(tmp_path, **config)
    kw = lens_kwargs[0]
    assert kw["deployment_profile"]["run_kind"] == kind
    # The format is declared in its own signed member (CC 3.1.5).
    assert kw["deployment_profile"]["trace_format_version"] == "2.8.0"
    # deployment_type is the operator's value again; the run kind no longer rides it.
    assert kw["deployment_profile"]["deployment_type"] == "research"
    assert kw["deployment_type"] == "research"
    assert out["metrics_type"] == "research"
    _assert_wire_stamp_untouched(kw)


def test_2_8_0_marks_mock_in_the_envelope(
    no_format_env: None,
    mock_llm_mode: None,
    lens_kwargs: List[Dict[str, Any]],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(TRACE_FORMAT_VERSION_ENV_VAR, "2.8.0")
    monkeypatch.setenv("CIRIS_TRACE_RUN_KIND", "production")  # cannot hide the mock
    _build(tmp_path)
    kw = lens_kwargs[0]
    assert kw["deployment_profile"]["run_kind"] == "mock"
    assert kw["deployment_profile"]["deployment_type"] == "production"
    assert kw["deployment_type"] is None  # undeclared operator value
    assert kw["local_copy_dir"]  # mock stays local-only; the tee is still allowed


def test_2_8_0_profile_validates_against_the_published_schema(
    no_format_env: None,
    real_llm_mode: None,
    lens_kwargs: List[Dict[str, Any]],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    jsonschema = pytest.importorskip("jsonschema")
    doc = json.loads(egress_schema.EGRESS_SCHEMA_FILE.read_text(encoding="utf-8"))
    sub = {"$ref": "#/definitions/DeploymentProfile", "definitions": doc["definitions"]}
    monkeypatch.setenv(TRACE_FORMAT_VERSION_ENV_VAR, "2.8.0")
    jsonschema.Draft7Validator(sub).validate(_build(tmp_path)["profile"])
    # Negative control: the 2.7.0 profile has no run_kind and is refused.
    monkeypatch.delenv(TRACE_FORMAT_VERSION_ENV_VAR)
    assert list(jsonschema.Draft7Validator(sub).iter_errors(_build(tmp_path)["profile"]))


@pytest.mark.parametrize("raw", ["3.0.0", "2.8", "latest", "garbage"])
def test_an_unknown_format_value_falls_back_to_the_default(
    no_format_env: None, real_llm_mode: None, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, raw: str
) -> None:
    monkeypatch.setenv(TRACE_FORMAT_VERSION_ENV_VAR, raw)
    service = AccordMetricsService(config={"local_copy_dir": str(tmp_path), "consent_given": True})
    assert service.get_metrics()["trace_format_version"] == "2.7.0"
    assert "run_kind" not in service._build_deployment_profile()


def test_a_v_prefix_is_accepted(
    no_format_env: None, real_llm_mode: None, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(TRACE_FORMAT_VERSION_ENV_VAR, "v2.8.0")
    service = AccordMetricsService(config={"local_copy_dir": str(tmp_path), "consent_given": True})
    assert service.get_metrics()["trace_format_version"] == "2.8.0"
