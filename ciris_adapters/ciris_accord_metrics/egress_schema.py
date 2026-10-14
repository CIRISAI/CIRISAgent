"""Per-level trace egress schema, enforced before a component reaches the signer.

``AccordMetricsService._extract_component_data`` builds each component's
``data``. Before 2.13.x nothing checked that output against the trace-level
contract, so whatever a producer put on an event could ship. Examples: a DEFER
reason naming a person inside GENERIC ``verb_specific_data`` (CIRISAgent#1245),
or the mock LLM's whole message array inside DETAILED ``dsdma.flags``
(CIRISAgent#1244).

The contract comes from :class:`TraceDetailLevel`:

* **generic**: numeric scores only. No free text, no reasoning, no prompts.
  Allowed values are numbers, booleans and short enum-like tokens. There is
  one named exception: ``attestation_context`` is agent-authored, carries no
  LLM or user content, and FSD-001 requires it at every level.
* **detailed**: adds actionable lists and key identifiers. Lists are bounded in
  item count and item length. Short *reason* fields (a decision summary such as
  a defer reason or conscience reason) are allowed, capped at
  ``REASON_MAX_CHARS``. The reasoning chain itself is not
  ("without full reasoning exposure").
* **full_traces**: everything, but still bounded: free text up to
  ``FULL_TEXT_MAX_CHARS`` and opaque JSON with string, list and depth caps.

Enforcement FILTERS and never refuses the whole event:

* a field that is not in the level's schema is dropped (``unexpected_field``);
* a value whose type does not fit is dropped (``wrong_type``). For token and
  label kinds this includes "letters where an enum or number belongs": a
  sentence is not a token;
* an over-long text value is truncated, and an over-long list is cut to its cap
  (``over_cap``).

Every violation is a finding about the PRODUCER. It is logged as a WARNING
that names the event type, field path, level and kind, never the value, once
per (event, path, kind, level) per process, and it is counted. The filter is a
safety net; the fix belongs at the source.

The signed wire contract (CIRISLensCore ``PUBLIC_SCHEMA_CONTRACT.md``) is not
touched: filtering only removes or shortens values inside the existing
component ``data`` object.

Single source of truth (CIRISAgent#1249): every bound, pattern and per-event
field table is loaded at import from ``schemas/trace_format_v2_8_0.json``, the
published artifact whose SHA-256 the Constitution pins (``schemas/SCHEMA_SHA256``).
That file is the contract an admitter validates against; this module only
reads it. The enforcer applies each string kind's JSON ``pattern`` with
``fullmatch``, so whatever survives the filter also validates against the
schema. The bounds apply whichever trace format version is being emitted
(see :data:`TraceFormatVersion`): v2.7.0 emission is filtered to the same
contract, and v2.8.0 adds ``run_kind`` to the envelope.
"""

from __future__ import annotations

import json
import logging
import math
import re
import threading
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Dict, List, Mapping, Optional, Set, Tuple, cast
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field

from ciris_engine.schemas.types import JSONDict, JSONValue

logger = logging.getLogger(__name__)


class TraceLevel(str, Enum):
    """Mirror of ``services.TraceDetailLevel``, ordered. Kept here so the schema
    has no import cycle with the service module."""

    GENERIC = "generic"
    DETAILED = "detailed"
    FULL_TRACES = "full_traces"

    @property
    def rank(self) -> int:
        return _LEVEL_RANK[self]


_LEVEL_RANK: Dict[TraceLevel, int] = {
    TraceLevel.GENERIC: 0,
    TraceLevel.DETAILED: 1,
    TraceLevel.FULL_TRACES: 2,
}


class TraceFormatVersion(str, Enum):
    """Which published ``trace_format`` contract the agent emits (CIRISAgent#1249).

    NOT the substrate's wire stamp (``services.TRACE_SCHEMA_VERSION``, set by
    lens-core at seal time and selecting the canonicalizer). This selects where
    the run kind travels in the signed envelope:

    * ``V2_7_0`` (default): the run-kind marker rides ``deployment_type``, as
      in 2.15.0.
    * ``V2_8_0``: ``deployment_profile.run_kind`` carries the closed run kind
      at every run (``production`` included), and ``deployment_type`` goes back
      to the operator's value.

    Persist v54.1 and earlier refuse v2.8.0 traces WHOLE
    (``schema_unsupported_version``), so the default stays v2.7.0 until a
    persist release that admits v2.8.0 is deployed on the receiving nodes.
    """

    V2_7_0 = "2.7.0"
    V2_8_0 = "2.8.0"


DEFAULT_TRACE_FORMAT_VERSION = TraceFormatVersion.V2_7_0

#: The published artifact for each emittable version.
TRACE_FORMAT_FILES: Dict[TraceFormatVersion, str] = {
    TraceFormatVersion.V2_7_0: "trace_format_v2_7_0.json",
    TraceFormatVersion.V2_8_0: "trace_format_v2_8_0.json",
}


G = TraceLevel.GENERIC
D = TraceLevel.DETAILED
F = TraceLevel.FULL_TRACES

# The contract lives in the published trace_format schema (CIRISAgent#1249).
# Bounds, patterns and every event's field table are LOADED from it, so the
# JSON artifact the Constitution pins by hash and this enforcer cannot drift.
# Changing a bound means changing that file, which changes its pinned SHA-256.
SCHEMA_DIR = Path(__file__).resolve().parent / "schemas"
EGRESS_SCHEMA_FILE = SCHEMA_DIR / "trace_format_v2_8_0.json"
_SCHEMA_DOC: JSONDict = json.loads(EGRESS_SCHEMA_FILE.read_text(encoding="utf-8"))
_EGRESS: JSONDict = cast(JSONDict, _SCHEMA_DOC["x-ciris-egress"])
_BOUNDS: Dict[str, int] = {k: int(cast(int, v)) for k, v in cast(JSONDict, _EGRESS["bounds"]).items()}
_PATTERNS: Dict[str, str] = {k: str(v) for k, v in cast(JSONDict, _EGRESS["patterns"]).items()}

TOKEN_MAX_CHARS = _BOUNDS["TOKEN_MAX_CHARS"]
IDENTIFIER_MAX_CHARS = _BOUNDS["IDENTIFIER_MAX_CHARS"]
LABEL_MAX_CHARS = _BOUNDS["LABEL_MAX_CHARS"]
URL_MAX_CHARS = _BOUNDS["URL_MAX_CHARS"]
REASON_MAX_CHARS = _BOUNDS["REASON_MAX_CHARS"]  # matches the existing DEFERRAL_ROUTED reason cap
SYSTEM_TEXT_MAX_CHARS = _BOUNDS["SYSTEM_TEXT_MAX_CHARS"]  # attestation_context
FULL_TEXT_MAX_CHARS = _BOUNDS["FULL_TEXT_MAX_CHARS"]
LIST_MAX_ITEMS = _BOUNDS["LIST_MAX_ITEMS"]
MAP_MAX_ITEMS = _BOUNDS["MAP_MAX_ITEMS"]
JSON_MAX_DEPTH = _BOUNDS["JSON_MAX_DEPTH"]
JSON_MAX_ITEMS = _BOUNDS["JSON_MAX_ITEMS"]
JSON_MAX_STRING_CHARS = _BOUNDS["JSON_MAX_STRING_CHARS"]
JSON_MAX_KEY_CHARS = _BOUNDS["JSON_MAX_KEY_CHARS"]  # object keys in opaque JSON


class FieldKind(str, Enum):
    NUMBER = "number"  # int or float, finite, never bool
    INTEGER = "integer"  # int, never bool
    BOOL = "bool"
    TOKEN = "token"  # enum-like: [A-Za-z0-9_.:/@+=-], no whitespace
    LABEL = "label"  # one short line of text (flags, source names, channel ids)
    TIMESTAMP = "timestamp"  # ISO-8601 string
    URL = "url"  # http(s) URL with no userinfo, query or fragment
    TEXT = "text"  # free text, truncated at max_chars
    LIST = "list"  # homogeneous list of `items`
    MAP = "map"  # {token: values}
    OBJECT = "object"  # fixed `children`
    JSON = "json"  # opaque JSON, bounded recursively (FULL only)


class ViolationKind(str, Enum):
    UNEXPECTED_FIELD = "unexpected_field"
    WRONG_TYPE = "wrong_type"
    OVER_CAP = "over_cap"


class FieldSpec(BaseModel):
    """One field of the egress schema."""

    model_config = ConfigDict(frozen=True)

    kind: FieldKind
    min_level: TraceLevel = G
    max_chars: Optional[int] = None
    max_items: Optional[int] = None
    items: Optional["FieldSpec"] = None
    values: Optional["FieldSpec"] = None
    children: Optional[Dict[str, "FieldSpec"]] = None


class SchemaViolation(BaseModel):
    """A finding: the producer emitted something the level's schema forbids."""

    model_config = ConfigDict(frozen=True)

    event_type: str
    level: TraceLevel
    path: str
    kind: ViolationKind
    detail: str = Field(..., description="Type name and size only, never the value")


class EnforcementResult(BaseModel):
    data: JSONDict
    violations: List[SchemaViolation] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# The schema: one spec tree per event type, LOADED from the published JSON
# artifact (``x-ciris-egress.events`` -> ``definitions.EventData_<EVENT>``).
# Each field names the lowest level at which it may ship (``level``) and its
# kind (``x-ciris-kind``). Mirrors services._extract_component_data. Where that
# builder emits something not listed, or at a lower level than listed, the
# builder is wrong and the enforcement log names it.
# ---------------------------------------------------------------------------

#: Pattern per string kind, applied with ``fullmatch`` so Python and ECMA-262
#: (JSON Schema ``pattern``) agree: ``$`` never admits a trailing newline here.
KIND_PATTERNS: Dict[str, "re.Pattern[str]"] = {kind: re.compile(pat) for kind, pat in _PATTERNS.items()}
_TOKEN_RE = KIND_PATTERNS[FieldKind.TOKEN.value]
_PATTERNED_KINDS = frozenset({FieldKind.TOKEN, FieldKind.LABEL, FieldKind.TIMESTAMP, FieldKind.URL})
_OPAQUE = FieldSpec(kind=FieldKind.JSON, min_level=F)


class EgressSchemaError(ValueError):
    """The published schema file is not a well-formed egress contract."""


def _resolve(ref: str) -> JSONDict:
    prefix = "#/definitions/"
    if not ref.startswith(prefix):
        raise EgressSchemaError(f"unsupported $ref {ref!r}")
    return cast(JSONDict, cast(JSONDict, _SCHEMA_DOC["definitions"])[ref[len(prefix) :]])


def _spec_from_json(node: JSONDict, path: str, parent_level: TraceLevel) -> FieldSpec:
    """One JSON Schema field -> FieldSpec.

    Strict: an unknown kind, or a pattern that is not its kind's pattern, is a
    malformed contract and fails the import rather than defaulting to "allow".
    """
    try:
        kind = FieldKind(str(node["x-ciris-kind"]))
    except (KeyError, ValueError) as exc:
        raise EgressSchemaError(f"{path}: missing or unknown x-ciris-kind") from exc
    level = TraceLevel(str(node["level"])) if "level" in node else parent_level
    if kind in _PATTERNED_KINDS and node.get("pattern") != _PATTERNS[kind.value]:
        raise EgressSchemaError(f"{path}: pattern is not the {kind.value} pattern")
    if kind == FieldKind.LIST:
        return FieldSpec(
            kind=kind,
            min_level=level,
            max_items=int(cast(int, node["maxItems"])),
            items=_spec_from_json(cast(JSONDict, node["items"]), f"{path}[]", level),
        )
    if kind == FieldKind.MAP:
        return FieldSpec(
            kind=kind,
            min_level=level,
            max_items=int(cast(int, node["maxProperties"])),
            values=_spec_from_json(cast(JSONDict, node["additionalProperties"]), f"{path}.*", level),
        )
    if kind == FieldKind.OBJECT:
        return FieldSpec(kind=kind, min_level=level, children=_fields_from_json(node, path, level))
    if kind == FieldKind.JSON:
        return FieldSpec(kind=kind, min_level=level)
    max_chars = node.get("maxLength")
    return FieldSpec(kind=kind, min_level=level, max_chars=None if max_chars is None else int(cast(int, max_chars)))


def _fields_from_json(node: JSONDict, path: str = "", level: TraceLevel = TraceLevel.GENERIC) -> Dict[str, FieldSpec]:
    props = cast(JSONDict, node.get("properties") or {})
    return {
        name: _spec_from_json(cast(JSONDict, child), f"{path}.{name}" if path else name, level)
        for name, child in props.items()
    }


EVENT_SCHEMAS: Dict[str, Dict[str, FieldSpec]] = {
    event: _fields_from_json(_resolve(str(ref))) for event, ref in cast(JSONDict, _EGRESS["events"]).items()
}

#: Event types without a dedicated builder fall through to the minimal shape.
FALLBACK_SCHEMA: Dict[str, FieldSpec] = _fields_from_json(_resolve(str(_EGRESS["fallback"])))


def _is_empty(value: object) -> bool:
    return value is None or value == "" or value == [] or value == {}


def _describe(value: object) -> str:
    """Type and size only. NEVER the value: it is the sensitive content."""
    if isinstance(value, (str, list, tuple, dict)):
        return f"{type(value).__name__}(len={len(value)})"
    return type(value).__name__


class _Enforcer:
    def __init__(self, event_type: str, level: TraceLevel) -> None:
        self.event_type = event_type
        self.level = level
        self.violations: List[SchemaViolation] = []

    def _flag(self, path: str, kind: ViolationKind, value: object, why: str) -> None:
        self.violations.append(
            SchemaViolation(
                event_type=self.event_type,
                level=self.level,
                path=path,
                kind=kind,
                detail=f"{_describe(value)}: {why}",
            )
        )

    def fields(self, spec: Mapping[str, FieldSpec], data: Mapping[str, object], prefix: str) -> JSONDict:
        out: JSONDict = {}
        for key, value in data.items():
            path = f"{prefix}{key}"
            field = spec.get(key)
            if field is None or field.min_level.rank > self.level.rank:
                if not _is_empty(value):
                    why = "not in schema" if field is None else f"allowed from {field.min_level.value} up"
                    self._flag(path, ViolationKind.UNEXPECTED_FIELD, value, why)
                continue
            if value is None:
                out[key] = None
                continue
            ok, cleaned = self.value(field, value, path)
            if ok:
                out[key] = cleaned
        return out

    def value(self, spec: FieldSpec, value: object, path: str) -> Tuple[bool, JSONValue]:
        kind = spec.kind
        if kind == FieldKind.BOOL:
            if isinstance(value, bool):
                return True, value
            return self._wrong(path, value, "expected bool")
        if kind in (FieldKind.NUMBER, FieldKind.INTEGER):
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                return self._wrong(path, value, f"expected {kind.value}")
            if kind == FieldKind.INTEGER and not isinstance(value, int):
                return self._wrong(path, value, "expected integer")
            if isinstance(value, float) and not math.isfinite(value):
                return self._wrong(path, value, "non-finite number")
            return True, value
        if kind in (FieldKind.TOKEN, FieldKind.LABEL, FieldKind.TIMESTAMP, FieldKind.URL, FieldKind.TEXT):
            if not isinstance(value, str):
                return self._wrong(path, value, f"expected {kind.value} string")
            return self.string(spec, value, path)
        if kind == FieldKind.LIST:
            return self.list_(spec, value, path)
        if kind == FieldKind.MAP:
            return self.map_(spec, value, path)
        if kind == FieldKind.OBJECT:
            if not isinstance(value, dict):
                return self._wrong(path, value, "expected object")
            return True, self.fields(spec.children or {}, value, f"{path}.")
        return True, self.json_(value, path, 0)

    def _wrong(self, path: str, value: object, why: str) -> Tuple[bool, JSONValue]:
        self._flag(path, ViolationKind.WRONG_TYPE, value, why)
        return False, None

    def string(self, spec: FieldSpec, value: str, path: str) -> Tuple[bool, JSONValue]:
        cap = spec.max_chars
        kind = spec.kind
        if kind == FieldKind.TEXT:
            if cap is not None and len(value) > cap:
                self._flag(path, ViolationKind.OVER_CAP, value, f"truncated to {cap} chars")
                return True, value[:cap]
            return True, value
        # Token-like kinds: an over-long value is not a token at all, so it is
        # dropped rather than truncated (a 96 KB "flag" is not a flag).
        if cap is not None and len(value) > cap:
            return self._wrong(path, value, f"{kind.value} longer than {cap} chars")
        # The schema's own pattern for the kind, so the agent never keeps a
        # value the published JSON Schema would refuse (refuse-never-truncate
        # at the admitter would cost the whole trace).
        if not KIND_PATTERNS[kind.value].fullmatch(value):
            why = {
                FieldKind.TOKEN: "free text where an enum/identifier token belongs",
                FieldKind.LABEL: "multi-line text where a one-line label belongs",
                FieldKind.TIMESTAMP: "not an ISO-8601 timestamp",
            }.get(kind, "not an http(s) URL")
            return self._wrong(path, value, why)
        if kind == FieldKind.TIMESTAMP:
            try:
                datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                return self._wrong(path, value, "not an ISO-8601 timestamp")
        if kind == FieldKind.URL:
            try:
                parts = urlsplit(value)
            except ValueError:
                return self._wrong(path, value, "unparseable URL")
            if parts.scheme not in ("http", "https") or not parts.hostname:
                return self._wrong(path, value, "not an http(s) URL")
            if parts.username or parts.password or parts.query or parts.fragment:
                return self._wrong(path, value, "URL carries userinfo/query/fragment")
        return True, value

    def list_(self, spec: FieldSpec, value: object, path: str) -> Tuple[bool, JSONValue]:
        if not isinstance(value, (list, tuple)):
            return self._wrong(path, value, "expected list")
        item_spec = spec.items or _OPAQUE
        out: List[JSONValue] = []
        for i, item in enumerate(value):
            if item is None:
                continue
            ok, cleaned = self.value(item_spec, item, f"{path}[{i}]")
            if ok:
                out.append(cleaned)
        cap = spec.max_items
        if cap is not None and len(out) > cap:
            self._flag(path, ViolationKind.OVER_CAP, out, f"cut to {cap} items")
            out = out[:cap]
        return True, out

    def map_(self, spec: FieldSpec, value: object, path: str) -> Tuple[bool, JSONValue]:
        if not isinstance(value, dict):
            return self._wrong(path, value, "expected map")
        value_spec = spec.values or _OPAQUE
        out: JSONDict = {}
        for key, item in value.items():
            if not isinstance(key, str) or len(key) > IDENTIFIER_MAX_CHARS or not _TOKEN_RE.fullmatch(key):
                self._flag(f"{path}.<key>", ViolationKind.WRONG_TYPE, key, "map key is not a token")
                continue
            if item is None:
                out[key] = None
                continue
            ok, cleaned = self.value(value_spec, item, f"{path}.{key}")
            if ok:
                out[key] = cleaned
        cap = spec.max_items
        if cap is not None and len(out) > cap:
            self._flag(path, ViolationKind.OVER_CAP, out, f"cut to {cap} entries")
            out = dict(list(out.items())[:cap])
        return True, out

    def json_(self, value: object, path: str, depth: int) -> JSONValue:
        if value is None or isinstance(value, (bool, int)):
            return value
        if isinstance(value, float):
            return value if math.isfinite(value) else None
        if isinstance(value, str):
            if len(value) > JSON_MAX_STRING_CHARS:
                self._flag(path, ViolationKind.OVER_CAP, value, f"truncated to {JSON_MAX_STRING_CHARS} chars")
                return value[:JSON_MAX_STRING_CHARS]
            return value
        if depth >= JSON_MAX_DEPTH:
            self._flag(path, ViolationKind.OVER_CAP, value, f"nested deeper than {JSON_MAX_DEPTH}")
            return None
        if isinstance(value, (list, tuple)):
            items = list(value)
            if len(items) > JSON_MAX_ITEMS:
                self._flag(path, ViolationKind.OVER_CAP, items, f"cut to {JSON_MAX_ITEMS} items")
                items = items[:JSON_MAX_ITEMS]
            return [self.json_(v, f"{path}[{i}]", depth + 1) for i, v in enumerate(items)]
        if isinstance(value, dict):
            entries = list(value.items())
            if len(entries) > JSON_MAX_ITEMS:
                self._flag(path, ViolationKind.OVER_CAP, entries, f"cut to {JSON_MAX_ITEMS} entries")
                entries = entries[:JSON_MAX_ITEMS]
            out: JSONDict = {}
            for k, v in entries:
                key = str(k)
                if len(key) > JSON_MAX_KEY_CHARS:
                    # Keys are producer-controlled content too: cap them, count
                    # it, and never echo the key into the path (the log names
                    # the path, so a long key would leak through it).
                    self._flag(f"{path}.<key>", ViolationKind.OVER_CAP, key, f"key truncated to {JSON_MAX_KEY_CHARS}")
                    key = key[:JSON_MAX_KEY_CHARS]
                    out[key] = self.json_(v, f"{path}.<key>", depth + 1)
                else:
                    out[key] = self.json_(v, f"{path}.{key}", depth + 1)
            return out
        self._flag(path, ViolationKind.WRONG_TYPE, value, "not JSON-serializable")
        return None


def schema_for(event_type: str) -> Dict[str, FieldSpec]:
    return EVENT_SCHEMAS.get(event_type, FALLBACK_SCHEMA)


def enforce_egress_schema(event_type: str, level: TraceLevel, data: Mapping[str, object]) -> EnforcementResult:
    """Filter ``data`` to what ``level`` allows for ``event_type``. Pure; does not log."""
    enforcer = _Enforcer(event_type, level)
    cleaned = enforcer.fields(schema_for(event_type), data, "")
    return EnforcementResult(data=cleaned, violations=enforcer.violations)


class ViolationReporter:
    """Counts every violation and logs each distinct one once per process.

    Distinct means a distinct (event_type, path, kind, level). List indices are
    folded (``flags[3]`` and ``flags[7]`` are one finding) so a long list cannot
    turn into log spam. The log names the producer's mistake, never the value.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._seen: Set[Tuple[str, str, str, str]] = set()
        self.counts: Dict[ViolationKind, int] = {kind: 0 for kind in ViolationKind}

    def report(self, violations: List[SchemaViolation], instance: str = "default") -> None:
        for v in violations:
            folded = re.sub(r"\[\d+\]", "[]", v.path)
            key = (v.event_type, folded, v.kind.value, v.level.value)
            with self._lock:
                self.counts[v.kind] += 1
                first = key not in self._seen
                self._seen.add(key)
            if first:
                logger.warning(
                    "[TRACE-SCHEMA] [%s] schema violation: event=%s field=%s level=%s kind=%s (%s). "
                    "Filtered before signing. Fix the PRODUCER of this field; the filter is a safety net "
                    "(logged once per event/field/kind/level).",
                    instance,
                    v.event_type,
                    folded,
                    v.level.value,
                    v.kind.value,
                    v.detail,
                )

    def snapshot(self) -> Dict[str, int]:
        with self._lock:
            return {f"schema_violations_{kind.value}": n for kind, n in self.counts.items()}
