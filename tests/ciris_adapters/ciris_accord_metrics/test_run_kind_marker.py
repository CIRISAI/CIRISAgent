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
from ciris_adapters.ciris_accord_metrics.services import (
    DEPLOYMENT_REGION_ENV_VAR,
    TRACE_FORMAT_VERSION_ENV_VAR,
    AccordMetricsService,
)


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
    monkeypatch.delenv("CIRIS_MANAGED", raising=False)
    monkeypatch.delenv(DEPLOYMENT_REGION_ENV_VAR, raising=False)
    # Empty, not unset: an unset var would fall through to a developer's ~/ciris/.env.
    monkeypatch.setenv("CIRIS_TEMPLATE", "")


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
@pytest.mark.parametrize("kind", ["prod-personal", "qa", "battery"])
def test_2_8_0_moves_run_kind_into_the_envelope(
    no_format_env: None,
    real_llm_mode: None,
    lens_kwargs: List[Dict[str, Any]],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    via: str,
    kind: str,
) -> None:
    if kind != "prod-personal":  # undeclared, not managed: a personal production run
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


# ---------------------------------------------------------------------------
# Managed vs personal (direct user ruling 2026-10-14): two more run_kind
# values, v2.8.0 only. v2.7.0 bytes do not move.
# ---------------------------------------------------------------------------

V270_DEFAULT_PROFILE = (
    '{"agent_role": "unknown", "agent_template": "unknown-default-unspecified", '
    '"deployment_domain": "general", "deployment_type": "production", '
    '"deployment_region": null, "deployment_trust_mode": "sovereign"}'
)


@pytest.mark.parametrize(
    "env",
    [
        {"CIRIS_MANAGED": "true"},
        {"CIRIS_TRACE_RUN_KIND": "prod-managed"},
        {"CIRIS_TRACE_RUN_KIND": "prod-personal"},
        {"CIRIS_TEMPLATE": "ally"},
        {DEPLOYMENT_REGION_ENV_VAR: "eu"},
    ],
    ids=["managed", "declared_managed", "declared_personal", "template_env", "region_env"],
)
def test_2_7_0_bytes_do_not_move_for_any_new_input(
    no_format_env: None,
    real_llm_mode: None,
    lens_kwargs: List[Dict[str, Any]],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    env: Dict[str, str],
) -> None:
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    service = AccordMetricsService(
        config={"local_copy_dir": str(tmp_path), "consent_given": True, "run_kind": "prod-managed"}
    )
    service.set_agent_id("", identity_hash="ab" * 32)  # ignored: invalid agent id
    service._build_lens_client()
    kw = lens_kwargs[0]
    assert json.dumps(kw["deployment_profile"]) == V270_DEFAULT_PROFILE
    assert kw["deployment_type"] is None
    assert kw["deployment_region"] is None
    assert kw["agent_template"] is None


@pytest.mark.parametrize(
    "managed,declared,override,expected",
    [
        (None, None, None, "prod-personal"),
        ("true", None, None, "prod-managed"),
        ("false", None, None, "prod-personal"),
        ("true", "production", None, "production"),
        ("true", None, "prod-personal", "prod-personal"),
        (None, None, "production", "production"),
        (None, "qa", "prod-managed", "qa"),
        (None, "battery", None, "battery"),
    ],
)
def test_2_8_0_run_kind_resolution(
    no_format_env: None,
    real_llm_mode: None,
    lens_kwargs: List[Dict[str, Any]],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    managed: Any,
    declared: Any,
    override: Any,
    expected: str,
) -> None:
    monkeypatch.setenv(TRACE_FORMAT_VERSION_ENV_VAR, "2.8.0")
    if managed is not None:
        monkeypatch.setenv("CIRIS_MANAGED", managed)
    if declared is not None:
        monkeypatch.setenv("CIRIS_TRACE_RUN_KIND", declared)
    config: Dict[str, Any] = {} if override is None else {"run_kind": override}
    _build(tmp_path, **config)
    assert lens_kwargs[0]["deployment_profile"]["run_kind"] == expected
    # The run kind never rides deployment_type under v2.8.0.
    assert lens_kwargs[0]["deployment_profile"]["deployment_type"] == "production"


def test_2_8_0_mock_beats_a_managed_override(
    no_format_env: None,
    mock_llm_mode: None,
    lens_kwargs: List[Dict[str, Any]],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(TRACE_FORMAT_VERSION_ENV_VAR, "2.8.0")
    monkeypatch.setenv("CIRIS_MANAGED", "true")
    _build(tmp_path, run_kind="prod-managed")
    assert lens_kwargs[0]["deployment_profile"]["run_kind"] == "mock"


# ---------------------------------------------------------------------------
# v2.8.0 provenance members (#1245, #878, #820, #832)
# ---------------------------------------------------------------------------


def _v280_service(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, **config: Any) -> AccordMetricsService:
    monkeypatch.setenv(TRACE_FORMAT_VERSION_ENV_VAR, "2.8.0")
    return AccordMetricsService(config={"local_copy_dir": str(tmp_path), "consent_given": True, **config})


def test_2_8_0_pipeline_metadata_and_calibration(
    no_format_env: None, real_llm_mode: None, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from ciris_engine.constants import ACCORD_VERSION, CIRIS_VERSION

    fake = types.ModuleType("ciris_server")
    fake.AXIS_CALIBRATION_VERSION = "crc-v2"  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "ciris_server", fake)
    service = _v280_service(tmp_path, monkeypatch)
    service.set_agent_id("Ally", identity_hash="ab" * 32)
    profile = service._build_deployment_profile()
    assert profile["pipeline_metadata"] == {
        "agent_version": CIRIS_VERSION,
        "accord_version": ACCORD_VERSION,
        "identity_hash": "ab" * 32,
        "pdma_version": None,
        "dsdma_domain_registry_version": None,
    }
    assert profile["calibration_version"] == "crc-v2"
    assert list(profile) == list(egress_schema.DEPLOYMENT_PROFILE_REQUIRED)


def test_2_8_0_unsourced_values_are_null(
    no_format_env: None, real_llm_mode: None, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setitem(sys.modules, "ciris_server", types.ModuleType("ciris_server"))
    profile = _v280_service(tmp_path, monkeypatch)._build_deployment_profile()
    assert profile["calibration_version"] is None
    assert profile["deployment_region"] is None
    assert profile["pipeline_metadata"]["identity_hash"] is None
    assert profile["agent_template"] == "unknown-default-unspecified"


def test_2_8_0_template_and_region_sources(
    no_format_env: None,
    real_llm_mode: None,
    lens_kwargs: List[Dict[str, Any]],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CIRIS_TEMPLATE", "ally")
    monkeypatch.setenv(DEPLOYMENT_REGION_ENV_VAR, "eu")
    service = _v280_service(tmp_path, monkeypatch)
    service.set_agent_id("Ally")
    service._build_lens_client()
    kw = lens_kwargs[0]
    assert kw["deployment_profile"]["agent_template"] == "ally"
    assert kw["deployment_profile"]["deployment_region"] == "eu"
    # The unsigned correlation copies mirror the signed profile.
    assert kw["agent_template"] == "ally"
    assert kw["deployment_region"] == "eu"
    # Operator config wins over both env channels.
    service = _v280_service(tmp_path, monkeypatch, agent_template="ally-v3", deployment_region="uk")
    profile = service._build_deployment_profile()
    assert profile["agent_template"] == "ally-v3"
    assert profile["deployment_region"] == "uk"


def test_2_8_0_a_bad_operator_value_falls_back_to_the_default(
    no_format_env: None, real_llm_mode: None, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A dropped REQUIRED member would get the whole trace refused; the default goes in instead."""
    jsonschema = pytest.importorskip("jsonschema")
    service = _v280_service(tmp_path, monkeypatch, agent_role="two\nlines", deployment_region="not a token")
    profile = service._build_deployment_profile()
    assert profile["agent_role"] == "unknown"
    assert profile["deployment_region"] is None
    doc = json.loads(egress_schema.EGRESS_SCHEMA_FILE.read_text(encoding="utf-8"))
    sub = {"$ref": "#/definitions/DeploymentProfile", "definitions": doc["definitions"]}
    jsonschema.Draft7Validator(sub).validate(profile)
    assert service.get_metrics()["schema_violations_wrong_type"] >= 2


@pytest.mark.parametrize("fmt,present", [("2.7.0", False), ("2.8.0", True)])
def test_disclosure_version_is_emitted_only_under_2_8_0(
    no_format_env: None,
    real_llm_mode: None,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    fmt: str,
    present: bool,
) -> None:
    monkeypatch.setenv(TRACE_FORMAT_VERSION_ENV_VAR, fmt)
    service = AccordMetricsService(config={"local_copy_dir": str(tmp_path), "consent_given": True})
    event = {"system_snapshot": {"verify_attestation": {"attestation_level": 1, "disclosure_severity": "info"}}}
    data = service._extract_component_data("SNAPSHOT_AND_CONTEXT", event)
    assert ("disclosure_version" in data) is present
    if present:
        assert data["disclosure_version"] is None  # CIRISVerify publishes no version today
