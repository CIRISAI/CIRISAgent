"""trace_format v2.8.0: the published schema artifact (CIRISAgent#1249).

Three guards:

1. The artifact's SHA-256 is the one recorded in ``schemas/SCHEMA_SHA256``
   (the value the Constitution pins). Any edit to the schema fails here until
   the pin is updated on purpose.
2. Parity with the Python enforcer. ``egress_schema.py`` loads its field table
   from the JSON, so the two cannot drift by construction. These tests check
   the other half: every JSON keyword an admitter reads (type, pattern,
   maxLength, maxItems, maxProperties, the per-level field sets) is exactly
   what the loaded spec enforces, and the reverse.
3. What the enforcer lets through validates against the schema at its level,
   and what it refuses, the schema refuses too (a negative test, so the
   validation step is not vacuously green).
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, cast

import pytest

from ciris_adapters.ciris_accord_metrics import egress_schema as es
from ciris_adapters.ciris_accord_metrics.egress_schema import (
    EVENT_SCHEMAS,
    FALLBACK_SCHEMA,
    FieldKind,
    FieldSpec,
    TraceLevel,
    enforce_egress_schema,
)
from ciris_engine.schemas.types import JSONDict

SCHEMAS = Path(es.__file__).resolve().parent / "schemas"
V280 = SCHEMAS / "trace_format_v2_8_0.json"
DOC: Dict[str, Any] = json.loads(V280.read_text(encoding="utf-8"))
DEFS: Dict[str, Any] = DOC["definitions"]
EGRESS: Dict[str, Any] = DOC["x-ciris-egress"]
LEVELS = [TraceLevel.GENERIC, TraceLevel.DETAILED, TraceLevel.FULL_TRACES]


# ---------------------------------------------------------------------------
# 1. The published hash
# ---------------------------------------------------------------------------


def test_schema_sha256_file_matches_the_artifact() -> None:
    recorded = (SCHEMAS / "SCHEMA_SHA256").read_text(encoding="utf-8").split()
    assert recorded[1] == V280.name
    assert hashlib.sha256(V280.read_bytes()).hexdigest() == recorded[0]


def test_the_artifact_is_lf_only() -> None:
    """The pin is over exact bytes; a CRLF checkout would change the hash."""
    assert b"\r" not in V280.read_bytes()


def test_the_enforcer_loads_the_pinned_file() -> None:
    assert Path(es.EGRESS_SCHEMA_FILE).resolve() == V280.resolve()


# ---------------------------------------------------------------------------
# 2. Parity: JSON keywords <-> the loaded Python spec
# ---------------------------------------------------------------------------


def _expected_keywords(spec: FieldSpec, top: bool) -> Dict[str, Any]:
    """The JSON Schema keywords that express ``spec`` (descriptions excluded)."""

    def typ(name: str) -> Any:
        return [name, "null"] if top else name

    out: Dict[str, Any] = {"x-ciris-kind": spec.kind.value}
    if top:
        out["level"] = spec.min_level.value
    kind = spec.kind
    if kind == FieldKind.NUMBER:
        out["type"] = typ("number")
    elif kind == FieldKind.INTEGER:
        out["type"] = typ("integer")
    elif kind == FieldKind.BOOL:
        out["type"] = typ("boolean")
    elif kind in (FieldKind.TOKEN, FieldKind.LABEL, FieldKind.TIMESTAMP, FieldKind.URL, FieldKind.TEXT):
        out["type"] = typ("string")
        if kind != FieldKind.TEXT:
            out["pattern"] = EGRESS["patterns"][kind.value]
        if spec.max_chars is not None:
            out["maxLength"] = spec.max_chars
    elif kind == FieldKind.LIST:
        assert spec.items is not None
        out["type"] = typ("array")
        out["maxItems"] = spec.max_items
        out["items"] = _expected_keywords(spec.items, top=False)
    elif kind == FieldKind.MAP:
        assert spec.values is not None
        out["type"] = typ("object")
        out["maxProperties"] = spec.max_items
        out["propertyNames"] = {"pattern": EGRESS["patterns"]["token"], "maxLength": es.IDENTIFIER_MAX_CHARS}
        values = _expected_keywords(spec.values, top=False)
        values["type"] = [values["type"], "null"]
        out["additionalProperties"] = values
    elif kind == FieldKind.OBJECT:
        out["type"] = typ("object")
        out["additionalProperties"] = False
        out["properties"] = {n: _expected_keywords(c, top=True) for n, c in (spec.children or {}).items()}
    elif kind == FieldKind.JSON:
        out["$ref"] = "#/definitions/BoundedJson"
    return out


def _strip_descriptions(node: Any) -> Any:
    if isinstance(node, dict):
        return {k: _strip_descriptions(v) for k, v in node.items() if k != "description"}
    if isinstance(node, list):
        return [_strip_descriptions(v) for v in node]
    return node


def _event_def(event: str) -> Dict[str, Any]:
    ref = EGRESS["events"].get(event, EGRESS["fallback"])
    return DEFS[ref.split("/")[-1]]  # type: ignore[no-any-return]


ALL_TABLES: Dict[str, Dict[str, FieldSpec]] = {**EVENT_SCHEMAS, "__FALLBACK__": FALLBACK_SCHEMA}


@pytest.mark.parametrize("event", sorted(ALL_TABLES))
def test_every_json_field_matches_the_python_spec_and_vice_versa(event: str) -> None:
    table = ALL_TABLES[event]
    node = DEFS[EGRESS["fallback"].split("/")[-1]] if event == "__FALLBACK__" else _event_def(event)
    assert node["additionalProperties"] is False, "unexpected fields are refused, not passed through"
    json_props = _strip_descriptions(node["properties"])
    expected = {name: _expected_keywords(spec, top=True) for name, spec in table.items()}
    assert set(json_props) == set(expected), "field sets differ between the JSON and the Python spec"
    for name in expected:
        assert json_props[name] == expected[name], f"{event}.{name}"


def test_the_event_map_covers_exactly_the_python_event_tables() -> None:
    assert set(EGRESS["events"]) == set(EVENT_SCHEMAS)


def test_bounds_block_matches_the_module_constants() -> None:
    for name, value in EGRESS["bounds"].items():
        assert getattr(es, name) == value, name
    assert set(EGRESS["bounds"]) >= {
        "TOKEN_MAX_CHARS",
        "REASON_MAX_CHARS",
        "LIST_MAX_ITEMS",
        "FULL_TEXT_MAX_CHARS",
        "JSON_MAX_DEPTH",
    }


def test_bounded_json_matches_the_opaque_json_caps() -> None:
    branches = {json.dumps(b.get("type")): b for b in DEFS["BoundedJson"]["anyOf"]}
    assert branches['"string"']["maxLength"] == es.JSON_MAX_STRING_CHARS
    assert branches['"array"']["maxItems"] == es.JSON_MAX_ITEMS
    assert branches['"object"']["maxProperties"] == es.JSON_MAX_ITEMS
    assert branches['"object"']["propertyNames"]["maxLength"] == es.JSON_MAX_KEY_CHARS


@pytest.mark.parametrize("level", LEVELS, ids=lambda lv: lv.value)
@pytest.mark.parametrize("event", sorted(ALL_TABLES))
def test_per_level_views_name_exactly_the_fields_python_allows(event: str, level: TraceLevel) -> None:
    table = ALL_TABLES[event]
    base = "EventData_FALLBACK" if event == "__FALLBACK__" else EGRESS["events"][event].split("/")[-1]
    view = DEFS[f"{base}__{level.value}"]
    assert view["propertyNames"]["enum"] == sorted(n for n, s in table.items() if s.min_level.rank <= level.rank)
    nested = view.get("properties", {})
    for name, spec in table.items():
        if spec.kind != FieldKind.OBJECT or spec.min_level.rank > level.rank:
            assert name not in nested
            continue
        allowed = sorted(c for c, cs in (spec.children or {}).items() if cs.min_level.rank <= level.rank)
        assert nested[name]["propertyNames"]["enum"] == allowed


# The fields #1249 names, pinned to concrete values so a contract change is a
# visible diff here as well as a new hash.
NAMED_BOUNDS = [
    ("DMA_RESULTS", "dsdma.flags", FieldKind.LIST, TraceLevel.DETAILED, None, 32),
    ("DMA_RESULTS", "dsdma.flags[]", FieldKind.LABEL, None, 128, None),
    ("DMA_RESULTS", "csdma.flags[]", FieldKind.LABEL, None, 128, None),
    ("IDMA_RESULT", "source_ids", FieldKind.LIST, TraceLevel.DETAILED, None, 32),
    ("IDMA_RESULT", "source_ids[]", FieldKind.TOKEN, None, 128, None),
    ("IDMA_RESULT", "sources_identified[]", FieldKind.LABEL, None, 128, None),
    ("IDMA_RESULT", "common_cause_flags", FieldKind.LIST, TraceLevel.DETAILED, None, 32),
    ("IDMA_RESULT", "phase", FieldKind.TOKEN, TraceLevel.GENERIC, 64, None),
    ("CONSCIENCE_RESULT", "conscience_override_reason", FieldKind.TEXT, TraceLevel.DETAILED, 500, None),
    ("CONSCIENCE_RESULT", "entropy_reason", FieldKind.TEXT, TraceLevel.DETAILED, 500, None),
    ("CONSCIENCE_RESULT", "epistemic_humility_uncertainties[]", FieldKind.LABEL, None, 500, None),
    ("TSASPDMA_RESULT", "final_parameters", FieldKind.JSON, TraceLevel.FULL_TRACES, None, None),
    ("VERB_SECOND_PASS_RESULT", "verb_specific_data", FieldKind.OBJECT, TraceLevel.GENERIC, None, None),
    ("VERB_SECOND_PASS_RESULT", "verb_specific_data.defer_reason", FieldKind.TEXT, TraceLevel.DETAILED, 500, None),
    (
        "VERB_SECOND_PASS_RESULT",
        "verb_specific_data.final_parameters",
        FieldKind.JSON,
        TraceLevel.FULL_TRACES,
        None,
        None,
    ),
    ("VERB_SECOND_PASS_RESULT", "verb_specific_data.rights_basis", FieldKind.LIST, TraceLevel.GENERIC, None, 32),
    ("VERB_SECOND_PASS_RESULT", "verb_specific_data.final_tool_name", FieldKind.TOKEN, TraceLevel.GENERIC, 128, None),
]


def _lookup(event: str, path: str) -> FieldSpec:
    spec: Optional[FieldSpec] = None
    table: Dict[str, FieldSpec] = EVENT_SCHEMAS[event]
    for part in re.findall(r"[^.\[\]]+|\[\]", path):
        if part == "[]":
            assert spec is not None and spec.items is not None
            spec = spec.items
        else:
            spec = table[part]
            table = spec.children or {}
    assert spec is not None
    return spec


@pytest.mark.parametrize("event,path,kind,level,max_chars,max_items", NAMED_BOUNDS)
def test_the_fields_named_in_1249_carry_their_bounds(
    event: str,
    path: str,
    kind: FieldKind,
    level: Optional[TraceLevel],
    max_chars: Optional[int],
    max_items: Optional[int],
) -> None:
    spec = _lookup(event, path)
    assert spec.kind == kind
    if level is not None:
        assert spec.min_level == level
    assert spec.max_chars == max_chars
    assert spec.max_items == max_items


class TestLoaderIsStrict:
    """A malformed contract fails the import; it never defaults to 'allow'."""

    def test_pattern_drift_is_refused(self) -> None:
        node: JSONDict = {
            "x-ciris-kind": "token",
            "level": "generic",
            "type": "string",
            "pattern": "^.*$",
            "maxLength": 64,
        }
        with pytest.raises(es.EgressSchemaError):
            es._spec_from_json(node, "f", TraceLevel.GENERIC)

    def test_unknown_kind_is_refused(self) -> None:
        with pytest.raises(es.EgressSchemaError):
            es._spec_from_json({"x-ciris-kind": "anything"}, "f", TraceLevel.GENERIC)

    def test_a_missing_kind_is_refused(self) -> None:
        with pytest.raises(es.EgressSchemaError):
            es._spec_from_json({"type": "string"}, "f", TraceLevel.GENERIC)


@pytest.mark.parametrize("kind", ["token", "label", "timestamp", "url"])
def test_a_trailing_newline_never_satisfies_a_pattern(kind: str) -> None:
    """Python ``re.match`` with ``$`` admits a trailing newline; ECMA-262 does not."""
    samples = {
        "token": "speak",
        "label": "one line",
        "timestamp": "2026-10-08T12:00:00+00:00",
        "url": "https://api.example/v1",
    }
    pattern = es.KIND_PATTERNS[kind]
    assert pattern.fullmatch(samples[kind])
    assert not pattern.fullmatch(samples[kind] + "\n")


# ---------------------------------------------------------------------------
# 3. What survives the enforcer validates against the schema (and only that)
# ---------------------------------------------------------------------------

PROFILE: Dict[str, Any] = {
    "agent_role": "datum",
    "agent_template": "datum-default-unspecified",
    "deployment_domain": "general",
    "deployment_type": "production",
    "deployment_region": None,
    "deployment_trust_mode": "sovereign",
    "run_kind": "production",
    "trace_format_version": "2.8.0",
    "pipeline_metadata": {
        "agent_version": "2.15.0-stable",
        "accord_version": "1.2-Beta",
        "identity_hash": "ab" * 32,
        "pdma_version": None,
        "dsdma_domain_registry_version": None,
    },
    "calibration_version": "crc-v2",
}

RUN_KINDS = ["production", "prod-personal", "prod-managed", "qa", "battery", "mock"]

MARIA = "Ideación suicida reportada por @María; requiere intervención inmediata de un profesional."

RAW_EVENTS: List[Dict[str, Any]] = [
    {"event_type": "THOUGHT_START", "data": {"round_number": 1, "thought_type": "seed", "channel_id": "c-1"}},
    {
        "event_type": "DMA_RESULTS",
        "data": {
            "csdma": {"plausibility_score": 0.9, "flags": ["ok", "multi\nline", 7] + [f"f{i}" for i in range(60)]},
            "dsdma": {"domain_alignment": 0.8, "domain": "general", "flags": ["__messages__:" + "[" * 5000]},
            "idma": {"k_eff": 1.5, "phase": "healthy", "source_ids": ["src-1", "has space"], "reasoning": "r" * 9},
        },
    },
    {
        "event_type": "VERB_SECOND_PASS_RESULT",
        "data": {
            "verb": "defer",
            "final_action": "defer",
            "verb_specific_data": {
                "rights_basis": ["safety"],
                "defer_reason": MARIA + "." * 900,
                "final_parameters": {"to": "0xDEADBEEF", "k" * 300: 1},
            },
        },
    },
    {
        "event_type": "CONSCIENCE_RESULT",
        "data": {"conscience_passed": True, "entropy_reason": "e" * 900, "epistemic_humility_uncertainties": ["u"]},
    },
    {"event_type": "LLM_CALL", "data": {"model": "m", "base_url": "https://u:p@h/v1?k=1", "prompt": "p" * 70000}},
    {"event_type": "ACTION_RESULT", "data": {"execution_success": True, "tokens_total": "many", "user_text": "hi"}},
    {"event_type": "SOMETHING_NEW", "data": {"event_type": "SOMETHING_NEW", "raw_data": {"a": [1, 2]}}},
]


def _trace(level: TraceLevel, enforce: bool) -> Dict[str, Any]:
    components = []
    for raw in RAW_EVENTS:
        data = raw["data"]
        if enforce:
            data = enforce_egress_schema(raw["event_type"], level, copy.deepcopy(data)).data
        components.append(
            {
                "component_type": "observation",
                "event_type": raw["event_type"] if raw["event_type"] != "SOMETHING_NEW" else "DEFERRAL_RECEIVED",
                "timestamp": "2026-10-13T00:00:00+00:00",
                "data": data,
            }
        )
    return {
        "trace_id": "trace-th_1-1",
        "thought_id": "th_1",
        "agent_id_hash": "abc",
        "started_at": "2026-10-13T00:00:00+00:00",
        "trace_level": level.value,
        "trace_schema_version": "3.0.0",
        "deployment_profile": copy.deepcopy(PROFILE),
        "components": components,
    }


def _validator() -> Any:
    # Only this section needs jsonschema; the hash and parity guards above run without it.
    jsonschema = pytest.importorskip("jsonschema")
    return jsonschema.Draft7Validator(DOC)


def test_the_artifact_is_a_valid_draft7_schema() -> None:
    type(_validator()).check_schema(DOC)


@pytest.mark.parametrize("level", LEVELS, ids=lambda lv: lv.value)
def test_enforced_output_validates_at_its_level(level: TraceLevel) -> None:
    errors = sorted(_validator().iter_errors(_trace(level, enforce=True)), key=str)
    assert errors == [], [e.message[:200] for e in errors]


@pytest.mark.parametrize("level", LEVELS, ids=lambda lv: lv.value)
def test_unfiltered_output_is_refused(level: TraceLevel) -> None:
    """Negative control: the same raw events WITHOUT the enforcer do not validate."""
    assert list(_validator().iter_errors(_trace(level, enforce=False)))


def test_a_detailed_field_under_generic_is_refused() -> None:
    trace = _trace(TraceLevel.GENERIC, enforce=True)
    trace["components"][0]["data"]["channel_id"] = "c-1"
    assert list(_validator().iter_errors(trace))
    trace["trace_level"] = "detailed"
    assert not list(_validator().iter_errors(trace))


def test_a_detailed_child_under_generic_is_refused() -> None:
    trace = _trace(TraceLevel.GENERIC, enforce=True)
    dma = next(c for c in trace["components"] if c["event_type"] == "DMA_RESULTS")
    dma["data"]["dsdma"]["flags"] = ["ok"]
    assert list(_validator().iter_errors(trace))


@pytest.mark.parametrize("bad", [None, "", "test", "PRODUCTION"])
def test_run_kind_is_required_and_closed(bad: Optional[str]) -> None:
    trace = _trace(TraceLevel.GENERIC, enforce=True)
    if bad is None:
        del trace["deployment_profile"]["run_kind"]
    else:
        trace["deployment_profile"]["run_kind"] = bad
    assert list(_validator().iter_errors(trace))


@pytest.mark.parametrize("kind", RUN_KINDS)
def test_every_run_kind_is_admitted_by_the_schema(kind: str) -> None:
    """Admission policy (refusing `mock`) is the admitter's, not the schema shape's."""
    trace = _trace(TraceLevel.GENERIC, enforce=True)
    trace["deployment_profile"]["run_kind"] = kind
    assert not list(_validator().iter_errors(trace))


def test_run_kind_vocabulary_matches_the_agent_enum() -> None:
    from ciris_engine.logic.utils.mock_llm_guard import TraceRunKind

    assert DEFS["RunKind"]["enum"] == [k.value for k in TraceRunKind]
    # Direct user ruling 2026-10-14: managed/personal are two more values; production stays valid.
    assert DEFS["RunKind"]["enum"] == RUN_KINDS


# ---------------------------------------------------------------------------
# 4. The deployment_profile block (v2.8.0: closed, bounded, level generic)
# ---------------------------------------------------------------------------

PROFILE_DEF: Dict[str, Any] = DEFS["DeploymentProfile"]


def test_the_profile_is_closed_and_every_member_is_required() -> None:
    assert PROFILE_DEF["additionalProperties"] is False
    assert set(PROFILE_DEF["required"]) == set(PROFILE_DEF["properties"])
    assert tuple(PROFILE_DEF["required"]) == es.DEPLOYMENT_PROFILE_REQUIRED
    pm = PROFILE_DEF["properties"]["pipeline_metadata"]
    assert pm["additionalProperties"] is False
    assert set(pm["required"]) == set(pm["properties"])


def _walk_profile(node: Dict[str, Any], spec: Dict[str, FieldSpec], path: str) -> None:
    assert set(node["properties"]) == set(spec), path
    for name, child in node["properties"].items():
        field = spec[name]
        where = f"{path}.{name}"
        assert child["x-ciris-kind"] == field.kind.value, where
        # The profile is stamped on every trace at every level.
        assert child["level"] == "generic" and field.min_level == TraceLevel.GENERIC, where
        if field.kind == FieldKind.OBJECT:
            _walk_profile(child, field.children or {}, where)
            continue
        assert child["pattern"] == EGRESS["patterns"][field.kind.value], where
        assert child["maxLength"] == field.max_chars, where


def test_every_profile_member_is_bounded_and_matches_the_loaded_spec() -> None:
    _walk_profile(PROFILE_DEF, es.DEPLOYMENT_PROFILE_SCHEMA, "deployment_profile")


def test_a_conformant_profile_passes_the_filter_unchanged() -> None:
    result = es.enforce_deployment_profile(copy.deepcopy(PROFILE))
    assert result.violations == []
    assert result.data == PROFILE


def test_the_filter_drops_what_the_schema_refuses() -> None:
    bad = copy.deepcopy(PROFILE)
    bad["agent_role"] = "two\nlines"
    bad["deployment_region"] = "x" * 65
    bad["pipeline_metadata"]["identity_hash"] = "not a token"
    bad["extra_member"] = "nope"
    result = es.enforce_deployment_profile(bad)
    assert "agent_role" not in result.data
    assert "deployment_region" not in result.data
    assert "extra_member" not in result.data
    assert "identity_hash" not in cast(Dict[str, Any], result.data["pipeline_metadata"])
    # ... and the schema refuses the unfiltered profile (negative control).
    trace = _trace(TraceLevel.GENERIC, enforce=True)
    trace["deployment_profile"] = bad
    assert list(_validator().iter_errors(trace))


@pytest.mark.parametrize(
    "mutate",
    [
        lambda p: p.pop("pipeline_metadata"),
        lambda p: p.pop("calibration_version"),
        lambda p: p.__setitem__("extra_member", "x"),
        lambda p: p["pipeline_metadata"].__setitem__("extra", "x"),
        lambda p: p["pipeline_metadata"].pop("agent_version"),
        lambda p: p["pipeline_metadata"].__setitem__("agent_version", None),
        lambda p: p.__setitem__("calibration_version", "crc v2"),
    ],
    ids=[
        "no_pipeline_metadata",
        "no_calibration_version",
        "extra_member",
        "extra_pipeline_member",
        "no_agent_version",
        "null_agent_version",
        "calibration_not_a_token",
    ],
)
def test_the_schema_refuses_a_malformed_profile(mutate: Any) -> None:
    trace = _trace(TraceLevel.GENERIC, enforce=True)
    mutate(trace["deployment_profile"])
    assert list(_validator().iter_errors(trace))


def test_unsourced_provenance_is_null_and_admitted() -> None:
    trace = _trace(TraceLevel.GENERIC, enforce=True)
    trace["deployment_profile"]["calibration_version"] = None
    trace["deployment_profile"]["deployment_region"] = None
    for name in ("accord_version", "identity_hash", "pdma_version", "dsdma_domain_registry_version"):
        trace["deployment_profile"]["pipeline_metadata"][name] = None
    assert not list(_validator().iter_errors(trace))


# ---------------------------------------------------------------------------
# 5. SNAPSHOT_AND_CONTEXT.disclosure_version (#832): per event, generic, optional
# ---------------------------------------------------------------------------


def test_disclosure_version_is_a_generic_optional_token() -> None:
    node = DEFS["EventData_SNAPSHOT_AND_CONTEXT"]["properties"]["disclosure_version"]
    assert node["x-ciris-kind"] == "token" and node["level"] == "generic"
    assert node["type"] == ["string", "null"]
    assert "disclosure_version" in DEFS["EventData_SNAPSHOT_AND_CONTEXT__generic"]["propertyNames"]["enum"]
    assert "disclosure_version" not in DEFS["EventData_SNAPSHOT_AND_CONTEXT"].get("required", [])


@pytest.mark.parametrize("value", [None, "d17-v1"])
def test_disclosure_version_validates_at_generic(value: Optional[str]) -> None:
    trace = _trace(TraceLevel.GENERIC, enforce=True)
    trace["components"].append(
        {
            "component_type": "context",
            "event_type": "SNAPSHOT_AND_CONTEXT",
            "timestamp": "2026-10-13T00:00:00+00:00",
            "data": enforce_egress_schema(
                "SNAPSHOT_AND_CONTEXT", TraceLevel.GENERIC, {"disclosure_version": value}
            ).data,
        }
    )
    assert not list(_validator().iter_errors(trace))
    trace["components"][-1]["data"]["disclosure_version"] = "free text version"
    assert list(_validator().iter_errors(trace))


def test_the_description_names_the_admitter_refusal_tokens() -> None:
    assert "trace_run_kind_mock" in DOC["description"]
    assert "trace_field_shape_violation" in DOC["description"]


def test_every_emittable_version_has_its_published_artifact() -> None:
    for name in es.TRACE_FORMAT_FILES.values():
        assert (SCHEMAS / name).is_file()
    # v2.7.0 is the frozen historical artifact; v2.8.0 identifies itself by a
    # distinct signed member, not by trace_schema_version (CC 3.1.5).
    v270 = json.loads((SCHEMAS / es.TRACE_FORMAT_FILES[es.TraceFormatVersion.V2_7_0]).read_text(encoding="utf-8"))
    assert v270["properties"]["trace_schema_version"]["const"] == "2.7.0"
    assert DEFS["DeploymentProfile"]["properties"]["trace_format_version"]["const"] == "2.8.0"
    assert "trace_format_version" in DEFS["DeploymentProfile"]["required"]


def test_trace_schema_version_stays_the_canonicalization_epoch() -> None:
    from ciris_adapters.ciris_accord_metrics.services import TRACE_SCHEMA_VERSION

    assert TRACE_SCHEMA_VERSION == "3.0.0"
    assert DOC["properties"]["trace_schema_version"]["const"] == TRACE_SCHEMA_VERSION


@pytest.mark.parametrize("bad", [None, "2.7.0", "3.0.0", "v2.8.0"])
def test_trace_format_version_is_required_and_exact(bad: Optional[str]) -> None:
    trace = _trace(TraceLevel.GENERIC, enforce=True)
    if bad is None:
        del trace["deployment_profile"]["trace_format_version"]
    else:
        trace["deployment_profile"]["trace_format_version"] = bad
    assert list(_validator().iter_errors(trace))


def test_a_2_8_0_trace_stamped_with_the_format_as_its_schema_version_is_refused() -> None:
    """The format never rides trace_schema_version (that selects the canonicalizer)."""
    trace = _trace(TraceLevel.GENERIC, enforce=True)
    trace["trace_schema_version"] = "2.8.0"
    assert list(_validator().iter_errors(trace))


def test_the_description_forbids_inferring_run_kind_from_2_7_deployment_type() -> None:
    text = DOC["description"]
    assert "Under v2.7.0 the run-kind marker overrode deployment_type" in text
    assert "must not infer run_kind from deployment_type on 2.7.x rows" in text


# ---------------------------------------------------------------------------
# 6. The SEALED shape: lens-core stamps data.attempt_index into every component
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("level", LEVELS, ids=lambda lv: lv.value)
def test_a_sealed_trace_with_attempt_index_validates(level: TraceLevel) -> None:
    """ciris-lens-core (capture/partial.rs data_with_attempt_index) injects attempt_index into
    every component's data before signing. The closed EventData objects must admit it, or the
    admitter would refuse every sealed trace."""
    trace = _trace(level, enforce=True)
    for i, component in enumerate(trace["components"]):
        component["data"]["attempt_index"] = i % 2
    errors = sorted(_validator().iter_errors(trace), key=str)
    assert errors == [], [e.message[:200] for e in errors]
    # Negative control: it is an integer, not free text.
    trace["components"][0]["data"]["attempt_index"] = "first"
    assert list(_validator().iter_errors(trace))
