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
"""

from __future__ import annotations

import logging
import math
import re
import threading
from datetime import datetime
from enum import Enum
from typing import Dict, List, Mapping, Optional, Set, Tuple
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

G = TraceLevel.GENERIC
D = TraceLevel.DETAILED
F = TraceLevel.FULL_TRACES

# Bounds. They are part of the contract; changing one is a contract change.
TOKEN_MAX_CHARS = 64
IDENTIFIER_MAX_CHARS = 128
LABEL_MAX_CHARS = 128
URL_MAX_CHARS = 256
REASON_MAX_CHARS = 500  # matches the existing DEFERRAL_ROUTED reason cap
SYSTEM_TEXT_MAX_CHARS = 1024  # attestation_context
FULL_TEXT_MAX_CHARS = 65536
LIST_MAX_ITEMS = 32
MAP_MAX_ITEMS = 64
JSON_MAX_DEPTH = 8
JSON_MAX_ITEMS = 256
JSON_MAX_STRING_CHARS = 8192


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
# Spec constructors (short names keep the tables below readable)
# ---------------------------------------------------------------------------


def _num(level: TraceLevel = G) -> FieldSpec:
    return FieldSpec(kind=FieldKind.NUMBER, min_level=level)


def _int(level: TraceLevel = G) -> FieldSpec:
    return FieldSpec(kind=FieldKind.INTEGER, min_level=level)


def _bool(level: TraceLevel = G) -> FieldSpec:
    return FieldSpec(kind=FieldKind.BOOL, min_level=level)


def _tok(level: TraceLevel = G, max_chars: int = TOKEN_MAX_CHARS) -> FieldSpec:
    return FieldSpec(kind=FieldKind.TOKEN, min_level=level, max_chars=max_chars)


def _ident(level: TraceLevel = D) -> FieldSpec:
    return FieldSpec(kind=FieldKind.TOKEN, min_level=level, max_chars=IDENTIFIER_MAX_CHARS)


def _label(level: TraceLevel = D, max_chars: int = LABEL_MAX_CHARS) -> FieldSpec:
    return FieldSpec(kind=FieldKind.LABEL, min_level=level, max_chars=max_chars)


def _ts(level: TraceLevel = G) -> FieldSpec:
    return FieldSpec(kind=FieldKind.TIMESTAMP, min_level=level)


def _url(level: TraceLevel = D) -> FieldSpec:
    return FieldSpec(kind=FieldKind.URL, min_level=level, max_chars=URL_MAX_CHARS)


def _reason(level: TraceLevel = D) -> FieldSpec:
    return FieldSpec(kind=FieldKind.TEXT, min_level=level, max_chars=REASON_MAX_CHARS)


def _text(level: TraceLevel = F, max_chars: int = FULL_TEXT_MAX_CHARS) -> FieldSpec:
    return FieldSpec(kind=FieldKind.TEXT, min_level=level, max_chars=max_chars)


def _list(items: FieldSpec, level: TraceLevel = D, max_items: int = LIST_MAX_ITEMS) -> FieldSpec:
    return FieldSpec(kind=FieldKind.LIST, min_level=level, max_items=max_items, items=items)


def _map(values: FieldSpec, level: TraceLevel = D, max_items: int = MAP_MAX_ITEMS) -> FieldSpec:
    return FieldSpec(kind=FieldKind.MAP, min_level=level, max_items=max_items, values=values)


def _obj(children: Dict[str, FieldSpec], level: TraceLevel = G) -> FieldSpec:
    return FieldSpec(kind=FieldKind.OBJECT, min_level=level, children=children)


def _json(level: TraceLevel = F) -> FieldSpec:
    return FieldSpec(kind=FieldKind.JSON, min_level=level)


# ---------------------------------------------------------------------------
# The schema. One spec tree per event type; each field names the lowest level
# at which it may ship. Mirrors services._extract_component_data. Where that
# builder emits something not listed here, or at a lower level than listed,
# the builder is wrong and the enforcement log names it.
# ---------------------------------------------------------------------------

_IDMA_GENERIC: Dict[str, FieldSpec] = {
    "k_eff": _num(),
    "effective_source_count": _num(),
    "correlation_risk": _num(),
    "source_overlap": _num(),
    "fragility_flag": _bool(),
    "reasoning_is_fragile": _bool(),
    "phase": _tok(),
    "reasoning_state": _tok(),
}

_IDMA_DETAILED: Dict[str, FieldSpec] = {
    "k_raw": _int(D),
    "raw_source_count": _int(D),
    "rho_mean": _num(D),
    "phase_confidence": _num(D),
    "collapse_margin": _num(D),
    "safety_margin": _num(D),
    "sources_identified": _list(_label()),
    "source_ids": _list(_ident()),
    "source_types": _list(_label()),
    "source_independence_scores": _list(_num(D)),
    "source_type_counts": _list(_label()),
    "correlation_factors": _list(_label()),
    "top_correlation_factors": _list(_label()),
    "pairwise_correlation_summary": _list(_label()),
    "rho_intra": _num(D),
    "rho_inter": _num(D),
    "module_count": _int(D),
    "effective_module_count": _num(D),
    "source_clusters": _list(_label()),
    "common_cause_flags": _list(_label()),
    "intervention_recommendation": _reason(),
    "next_best_recovery_step": _reason(),
    "delta_k_eff": _num(D),
    "delta_rho_mean": _num(D),
    "phase_persistence_steps": _int(D),
    "time_in_fragile_state_ms": _num(D),
    "moving_variance": _num(D),
    "rho_critical": _num(D),
    "k_required": _num(D),
    "defense_function": _num(D),
    "collapse_rate": _num(D),
    "time_to_truth": _num(D),
    "time_to_entropy": _num(D),
    "time_to_capture": _num(D),
}

_IDMA_FULL: Dict[str, FieldSpec] = {
    "reasoning": _text(),
    "prompt_used": _text(),
}

# verb_specific_data: an opaque payload keyed by `verb`. Under GENERIC only its
# enum, boolean and tool-name members survive. A DEFER reason is reasoning-class
# text (DETAILED, capped). Tool parameters are content (FULL).
_VERB_SPECIFIC_DATA: Dict[str, FieldSpec] = {
    # DEFER (DSASPDMA classification)
    "rights_basis": _list(_tok(G), level=G),
    "primary_need_category": _tok(),
    "secondary_need_categories": _list(_tok(G), level=G),
    "domain_hint": _tok(),
    "operational_reason": _tok(),
    "defer_reason": _reason(),
    "defer_until": _ts(D),
    # TOOL (TSASPDMA)
    "original_tool_name": _tok(G, IDENTIFIER_MAX_CHARS),
    "final_tool_name": _tok(G, IDENTIFIER_MAX_CHARS),
    "original_parameters": _json(),
    "final_parameters": _json(),
    # MEMORIZE (MSASPDMA)
    "original_node_id": _label(D),
    "final_node_id": _label(D),
    "node_id_corrected": _bool(),
}

EVENT_SCHEMAS: Dict[str, Dict[str, FieldSpec]] = {
    "THOUGHT_START": {
        "round_number": _int(),
        "thought_depth": _int(),
        "task_priority": _int(),
        "updated_info_available": _bool(),
        "requires_human_input": _bool(),
        "thought_type": _tok(),
        "thought_status": _tok(D),
        "parent_thought_id": _ident(),
        # A key identifier (DETAILED). It is how battery/QA rows identify
        # themselves (CIRISAgent#1245), so it stays; never at GENERIC.
        "channel_id": _label(D),
        "source_adapter": _tok(D),
        "task_description": _text(),
        "initial_context": _json(),
        "thought_content": _text(F, 500),
    },
    "SNAPSHOT_AND_CONTEXT": {
        "agent_name": _label(G, TOKEN_MAX_CHARS),
        "cognitive_state": _tok(),
        # The one GENERIC text field. Agent-authored attestation disclosure, no
        # LLM or user content, REQUIRED at every level by FSD-001.
        "attestation_context": _text(G, SYSTEM_TEXT_MAX_CHARS),
        "attestation_level": _int(),
        "attestation_status": _tok(),
        "disclosure_severity": _tok(),
        "binary_ok": _bool(),
        "env_ok": _bool(),
        "registry_ok": _bool(),
        "file_integrity_ok": _bool(),
        "audit_ok": _bool(),
        "play_integrity_ok": _bool(),
        "hardware_backed": _bool(),
        "memory_count": _int(),
        "context_tokens": _int(),
        "active_services": _list(_label(), max_items=MAP_MAX_ITEMS),
        "context_sources": _list(_label(), max_items=MAP_MAX_ITEMS),
        "service_health": _map(_bool(D)),
        "agent_version": _tok(D),
        "circuit_breaker_status": _map(_tok(D)),
        "key_status": _tok(D),
        "key_id": _ident(),
        "ed25519_fingerprint": _ident(),
        "key_storage_mode": _tok(D),
        "hardware_type": _tok(D),
        "verify_version": _tok(D),
        "system_snapshot": _json(),
        "gathered_context": _json(),
        "relevant_memories": _json(),
        "conversation_history": _json(),
    },
    "DMA_RESULTS": {
        "csdma": _obj(
            {
                "plausibility_score": _num(),
                "flags": _list(_label()),
                "reasoning": _text(),
                "prompt_used": _text(),
            }
        ),
        "dsdma": _obj(
            {
                "domain_alignment": _num(),
                # LLM-authored, so a DETAILED identifier at most, never GENERIC.
                "domain": _label(D, TOKEN_MAX_CHARS),
                "flags": _list(_label()),
                "reasoning": _text(),
                "prompt_used": _text(),
            }
        ),
        "pdma": _obj(
            {
                "has_conflicts": _bool(),
                "stakeholders": _list(_label()),
                "conflicts": _reason(),
                "alignment_check": _reason(),
                "reasoning": _text(),
                "prompt_used": _text(),
            }
        ),
        "idma": _obj({**_IDMA_GENERIC, **_IDMA_DETAILED, **_IDMA_FULL}),
        "csdma_plausibility_score": _num(),
        "dsdma_domain_alignment": _num(),
        "dsdma_domain": _label(D, TOKEN_MAX_CHARS),
        "combined_analysis": _json(),
    },
    "IDMA_RESULT": {
        **_IDMA_GENERIC,
        "idma_k_eff": _num(),
        "idma_correlation_risk": _num(),
        "idma_fragility_flag": _bool(),
        "idma_phase": _tok(),
        **_IDMA_DETAILED,
        **_IDMA_FULL,
    },
    "ASPDMA_RESULT": {
        "selected_action": _tok(),
        "selection_confidence": _num(),
        "is_recursive": _bool(),
        "alternatives_considered": _list(_tok(D)),
        "evaluation_time_ms": _num(D),
        "action_rationale": _text(),
        "reasoning_summary": _text(),
        "action_parameters": _json(),
        "aspdma_prompt": _text(),
        "raw_llm_response": _text(F, 1000),
    },
    "TSASPDMA_RESULT": {
        "original_tool_name": _tok(G, IDENTIFIER_MAX_CHARS),
        "final_action": _tok(),
        "final_tool_name": _tok(G, IDENTIFIER_MAX_CHARS),
        "gotchas_acknowledged": _list(_label()),
        "tool_description": _reason(),
        "original_parameters": _json(),
        "final_parameters": _json(),
        "aspdma_rationale": _text(),
        "tsaspdma_rationale": _text(),
        "tsaspdma_prompt": _text(),
    },
    "VERB_SECOND_PASS_RESULT": {
        "verb": _tok(),
        "original_action": _tok(),
        "final_action": _tok(),
        "verb_specific_data": _obj(_VERB_SPECIFIC_DATA),
        # The pass rationales are the reasoning chain (FULL), not a summary.
        "original_reasoning": _text(),
        "final_reasoning": _text(),
        "second_pass_prompt": _text(),
    },
    "CONSCIENCE_RESULT": {
        "conscience_passed": _bool(),
        "action_was_overridden": _bool(),
        "ethical_faculties_skipped": _bool(),
        "is_recursive": _bool(),
        "updated_status_detected": _bool(),
        "thought_depth_triggered": _bool(),
        "thought_depth_current": _int(),
        "thought_depth_max": _int(),
        "entropy_level": _num(),
        "coherence_level": _num(),
        "entropy_passed": _bool(),
        "entropy_score": _num(),
        "entropy_threshold": _num(),
        "coherence_passed": _bool(),
        "coherence_score": _num(),
        "coherence_threshold": _num(),
        "optimization_veto_passed": _bool(),
        "optimization_veto_entropy_ratio": _num(),
        "epistemic_humility_passed": _bool(),
        "epistemic_humility_certainty": _num(),
        "final_action": _tok(D),
        "conscience_override_reason": _reason(),
        "entropy_reason": _reason(),
        "coherence_reason": _reason(),
        "optimization_veto_decision": _tok(D),
        "optimization_veto_affected_values": _list(_label()),
        "epistemic_humility_uncertainties": _list(_label(D, REASON_MAX_CHARS)),
        "epistemic_humility_recommendation": _tok(D),
        "epistemic_data": _json(),
        "updated_status_content": _text(),
        "optimization_veto_justification": _text(),
        "epistemic_humility_justification": _text(),
    },
    "ACTION_RESULT": {
        "execution_success": _bool(),
        "execution_time_ms": _num(),
        "tokens_input": _int(),
        "tokens_output": _int(),
        "tokens_total": _int(),
        "cost_cents": _num(),
        "carbon_grams": _num(),
        "energy_mwh": _num(),
        "llm_calls": _int(),
        "audit_sequence_number": _int(),
        "audit_entry_hash": _tok(G, IDENTIFIER_MAX_CHARS),
        "has_positive_moment": _bool(),
        "has_execution_error": _bool(),
        "success": _bool(),
        "action_executed": _tok(),
        "follow_up_thought_id": _ident(),
        "audit_entry_id": _ident(),
        "models_used": _list(_ident()),
        "api_bases_used": _list(_url()),
        "execution_error": _reason(),
        "audit_signature": _tok(D, 256),
        "action_parameters": _json(),
        "positive_moment": _text(F, 500),
    },
    "LLM_CALL": {
        "handler_name": _tok(),
        "service_name": _tok(),
        "model": _tok(G, IDENTIFIER_MAX_CHARS),
        # An endpoint locator, not a score: it can name a private LAN host or a
        # self-hosted proxy, and nothing scores on it. DETAILED, not GENERIC.
        "base_url": _url(),
        "response_model": _tok(G, IDENTIFIER_MAX_CHARS),
        "duration_ms": _num(),
        "prompt_tokens": _int(),
        "completion_tokens": _int(),
        "prompt_bytes": _int(),
        "completion_bytes": _int(),
        "cost_usd": _num(),
        "status": _tok(),
        "error_class": _tok(G, IDENTIFIER_MAX_CHARS),
        "attempt_count": _int(),
        "retry_count": _int(),
        "parent_event_type": _tok(),
        "parent_attempt_index": _int(),
        "prompt_hash": _ident(),
        "prompt": _text(),
        "response_text": _text(),
    },
    "DEFERRAL_ROUTED": {
        "defer_until": _ts(),
        "reason": _reason(),
    },
}

#: Event types without a dedicated builder fall through to the minimal shape.
FALLBACK_SCHEMA: Dict[str, FieldSpec] = {
    "event_type": _tok(G, IDENTIFIER_MAX_CHARS),
    "raw_data": _json(),
}

_TOKEN_RE = re.compile(r"^[A-Za-z0-9_.:/@+=\-]+$")
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")


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
        if kind == FieldKind.TOKEN and not _TOKEN_RE.match(value):
            return self._wrong(path, value, "free text where an enum/identifier token belongs")
        if kind == FieldKind.LABEL and _CONTROL_RE.search(value):
            return self._wrong(path, value, "multi-line text where a one-line label belongs")
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
        item_spec = spec.items or _json()
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
        value_spec = spec.values or _json()
        out: JSONDict = {}
        for key, item in value.items():
            if not isinstance(key, str) or len(key) > IDENTIFIER_MAX_CHARS or not _TOKEN_RE.match(key):
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
            return {str(k): self.json_(v, f"{path}.{k}", depth + 1) for k, v in entries}
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
