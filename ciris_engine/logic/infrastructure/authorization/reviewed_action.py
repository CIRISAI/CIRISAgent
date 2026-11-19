"""Review integrity: execute only what was reviewed (CIRISAgent#1366 items 10 + 19, rc21 §4).

FSD/PROMPT_CONTEXT_PROVENANCE.md §9 "Review integrity", and ``ReviewIntegrity``
in ``formal/h3ere_ctxflow/H3EREContextFlow.tla``: the executed action's
fingerprint must equal the fingerprint of the draft the consciences reviewed.
Otherwise it is not executed; it is re-reviewed.

ONE fingerprint (rc21 §4), written ``[-16, digest]`` (text ``"-16:<hex>"``)::

    SHA-256( CDE( ["CEG-call/2", verb, tool, arguments, channel] ) )

- ``verb``: ``"tool"`` for a tool call;
- ``tool``: the RESOLVED tool name (aliases are resolved before the consciences
  see the draft, so they review the tool that will actually run);
- ``arguments``: exactly as reviewed — secret REFERENCE text, never the
  decapsulated value, so a legitimate substitution never trips it and no
  secret enters a logged hash;
- ``channel``: the channel id, ``""`` when the call has none.

It is what the veto record names, what the review record names, what a Wise
Authority approves (``call_fingerprint``), and what dispatch recomputes.
Excluded because the handler adds them by rule after the check, from values
the model does not author: the ``channel_id`` copied into the argument map (it
is ``channel``), and ``task_id`` (handler-authoritative, CIRISAgent#938; a
model-supplied ``task_id`` argument IS hashed, then overwritten).

The CDE encoding is the shared pure-Python encoder
(:mod:`ciris_engine.logic.utils.cde`), the same one the profile digest uses;
the constitution's golden vectors pin its bytes
(``tests/fixtures/rc21_digest_vectors.json``). Numbers go by exact decimal
value and no float is written: an integral number is an integer, any other is
CBOR tag 4 ``[exponent, mantissa]`` normalised; an integer or mantissa outside
CBOR's integer range, or a non-finite value, is refused (``CdeError``, token
``call_argument_unrepresentable``). Arguments parsed from JSON text should be
parsed with ``cde.loads_exact``; ``ToolParams`` arguments arrive already
parsed as floats and are read as ``Decimal(repr(f))``, the shortest round-trip
decimal (the one a model writes), identically on the review and the dispatch
side.
"""

from __future__ import annotations

import hashlib
import inspect
import logging
from collections import OrderedDict
from typing import TYPE_CHECKING, Any, Dict, List, Mapping, Optional, Sequence, Tuple

from ciris_engine.logic.utils.cde import cde_encode, cde_set
from ciris_engine.schemas.runtime.reviewed_action_admission import (
    CEG_CALL_SCHEME,
    CEG_REVIEW_SCHEME,
    FINGERPRINT_PREFIX,
    REQUIRED_REVIEW_FACULTIES,
    SHA256_ALG_ID,
    ReviewEntry,
    ReviewOutcome,
    ReviewRecord,
)
from ciris_engine.schemas.runtime.veto_record import ObjectionType

if TYPE_CHECKING:
    from ciris_engine.schemas.dma.results import ActionSelectionDMAResult

logger = logging.getLogger(__name__)

TOOL_VERB = "tool"

# ---------------------------------------------------------------------------
# CDE
# ---------------------------------------------------------------------------


def _digest_text(encoded: bytes) -> str:
    return FINGERPRINT_PREFIX + hashlib.sha256(encoded).hexdigest()


def fingerprint_wire(fingerprint: str) -> List[Any]:
    """``"-16:<hex>"`` -> ``[-16, digest bytes]``, the wire form."""
    if not fingerprint.startswith(FINGERPRINT_PREFIX):
        raise ValueError(f"not a [-16, digest] fingerprint: {fingerprint!r}")
    return [SHA256_ALG_ID, bytes.fromhex(fingerprint[len(FINGERPRINT_PREFIX) :])]


def ceg_call_fingerprint(verb: str, tool: str, arguments: Mapping[str, Any], channel: Optional[str]) -> str:
    """``SHA-256(CDE(["CEG-call/2", verb, tool, arguments, channel]))`` as ``"-16:<hex>"``."""
    return _digest_text(cde_encode([CEG_CALL_SCHEME, verb, tool, dict(arguments), channel or ""]))


def reviewed_call_fingerprint(tool_name: str, arguments: Mapping[str, object], channel_id: Optional[str]) -> str:
    """The fingerprint of a TOOL call given its parts (the gate recomputes with the tool it runs)."""
    return ceg_call_fingerprint(TOOL_VERB, tool_name, arguments, channel_id)


def tool_call_fingerprint(tool_name: str, arguments: Mapping[str, object], channel_id: Optional[str] = None) -> str:
    """What a Wise Authority approves (``call_fingerprint``): the same rc21 call fingerprint."""
    return reviewed_call_fingerprint(tool_name, arguments, channel_id)


def reviewed_action_fingerprint(
    action: "ActionSelectionDMAResult", resolved_tool_name: Optional[str] = None
) -> Optional[str]:
    """Fingerprint of a TOOL action as reviewed, or ``None`` if it cannot be one.

    ``resolved_tool_name`` overrides the name in the params: the dispatch side
    passes the name the bus will actually run, so an alias registered after
    review changes the fingerprint. ``None`` for anything that is not a TOOL
    with typed ``ToolParams`` — the caller treats ``None`` as "not reviewable",
    which at dispatch is a refusal.
    """
    from ciris_engine.schemas.actions.parameters import ToolParams
    from ciris_engine.schemas.runtime.enums import HandlerActionType

    if action.selected_action != HandlerActionType.TOOL:
        return None
    params = action.action_parameters
    if not isinstance(params, ToolParams):
        return None
    return reviewed_call_fingerprint(
        resolved_tool_name if resolved_tool_name is not None else params.name,
        params.parameters,
        params.channel_id,
    )


#: Parameters that route an action rather than describe it; never part of a
#: non-TOOL action's arguments (the channel is its own member).
_ROUTING_FIELDS = ("channel_id", "channel_context")


def _params_dump(params: Any) -> Dict[str, Any]:
    if hasattr(params, "model_dump"):
        dumped = params.model_dump(mode="json")
        return dumped if isinstance(dumped, dict) else {}
    return dict(params) if isinstance(params, dict) else {}


def action_review_fingerprint(action: Any) -> str:
    """THE reviewed-action fingerprint, for any verb (the one the veto record carries).

    TOOL: exactly :func:`reviewed_action_fingerprint` (what dispatch admits).
    Other verbs: the same call form with the verb, an empty tool, the
    parameters (routing fields dropped) and the channel. Never ``None``.
    """
    from ciris_engine.schemas.dma.results import ActionSelectionDMAResult
    from ciris_engine.schemas.runtime.enums import HandlerActionType

    if isinstance(action, ActionSelectionDMAResult):
        tool_fp = reviewed_action_fingerprint(action)
        if tool_fp is not None:
            return tool_fp
    verb_obj = getattr(action, "selected_action", None)
    verb = verb_obj.value if isinstance(verb_obj, HandlerActionType) else str(verb_obj or "unknown")
    dumped = _params_dump(getattr(action, "action_parameters", None))
    channel = dumped.get("channel_id")
    params = {k: v for k, v in dumped.items() if k not in _ROUTING_FIELDS}
    try:
        return ceg_call_fingerprint(verb, "", params, channel if isinstance(channel, str) else None)
    except ValueError:
        return ceg_call_fingerprint(verb, "", {}, None)


# ---------------------------------------------------------------------------
# The review record (rc21 §4)
# ---------------------------------------------------------------------------


def _sorted_set(items: Sequence[Any]) -> List[Any]:
    """A CDE set: an array of distinct members ordered by their encoding."""
    return cde_set(items)


#: The edition constant of a row-ref (CC 2.6.1.3): ``[2, [-16, row id]]``.
ROW_REF_EDITION = 2


def row_ref_wire(row_id: str) -> Any:
    """A row id as the wire's row-ref ``[2, [-16, id]]``.

    The id may be bare 64-hex, ``sha256:<hex>`` or ``-16:<hex>``. An id in no
    digest form (a legacy node id) stays text: it names no signed row, so no
    row-ref can be written for it.
    """
    bare = row_id
    for prefix in ("sha256:", FINGERPRINT_PREFIX):
        if bare.startswith(prefix):
            bare = bare[len(prefix) :]
            break
    try:
        raw = bytes.fromhex(bare)
    except ValueError:
        return row_id
    if len(raw) != 32:
        return row_id
    return [ROW_REF_EDITION, [SHA256_ALG_ID, raw]]


def review_record_wire(record: ReviewRecord) -> Dict[str, Any]:
    """The record as the CDE map rc21 §4 defines.

    ``discharges``, ``considered`` and ``derived_from`` are ``passed``-only and
    ABSENT where there is none (the golden vectors' plain pass has four members).
    """
    wire: Dict[str, Any] = {
        "fingerprint": fingerprint_wire(record.fingerprint),
        "thought": record.thought,
        "outcome": record.outcome.value,
        "faculties": _sorted_set(list(record.faculties)),
    }
    if record.outcome is ReviewOutcome.PASSED:
        if record.discharges:
            wire["discharges"] = _sorted_set(
                [[fingerprint_wire(d.objection), row_ref_wire(d.evidence)] for d in record.discharges]
            )
        if record.considered:
            wire["considered"] = _sorted_set([fingerprint_wire(c) for c in record.considered])
        if record.derived_from:
            wire["derived_from"] = _sorted_set(list(record.derived_from))
    return wire


def review_record_digest(record: ReviewRecord) -> str:
    """``SHA-256(CDE(["CEG-review/2", record]))`` as ``"-16:<hex>"``."""
    return _digest_text(cde_encode([CEG_REVIEW_SCHEME, review_record_wire(record)]))


def make_review_entry(
    record: ReviewRecord,
    *,
    task_id: str,
    objection_types: Sequence[ObjectionType] = (),
    derived_from: Sequence[str] = (),
) -> ReviewEntry:
    """A record with its digest and the node-local facts dispatch needs."""
    return ReviewEntry(
        record=record,
        digest=review_record_digest(record),
        task_id=task_id,
        objection_types=tuple(objection_types),
        derived_from=tuple(derived_from),
    )


def resolve_tool_name_via_bus(bus_manager: Any, tool_name: str) -> str:
    """The tool ``ToolBus.execute_tool`` would run for ``tool_name`` (alias-resolved).

    The one resolver both sides of the review use: the thought processor before
    the consciences see a draft, and ``ToolHandler`` just before dispatch. A bus
    without alias support, or an answer that is not a non-empty string,
    resolves to the name itself — an unresolvable alias is then caught by the
    dispatch-side fingerprint comparison, never silently trusted.
    """
    tool_bus = getattr(bus_manager, "tool", None)
    resolver = getattr(tool_bus, "resolve_tool_name", None)
    if not callable(resolver):
        return tool_name
    resolved = resolver(tool_name)
    if inspect.iscoroutine(resolved):
        resolved.close()
        return tool_name
    if isinstance(resolved, str) and resolved:
        return resolved
    return tool_name


# ---------------------------------------------------------------------------
# Admission: the records of a thought, held for dispatch.
# ---------------------------------------------------------------------------

#: Review entries by thought id. Bounded: a thought whose tool never
#: dispatches must not hold memory forever.
_MAX_THOUGHTS = 1024
_RECORDS: "OrderedDict[str, List[ReviewEntry]]" = OrderedDict()


def _hold(entry: ReviewEntry) -> None:
    thought = entry.record.thought
    _RECORDS.setdefault(thought, []).append(entry)
    _RECORDS.move_to_end(thought)
    while len(_RECORDS) > _MAX_THOUGHTS:
        _RECORDS.popitem(last=False)


def admit_reviewed_action(entry: ReviewEntry) -> Optional[ReviewEntry]:
    """Record a review, and admit it for dispatch when it is a complete pass. THE seam for rc21.

    An ``objected`` record is recorded (trace + held, so dispatch can require
    its discharge) and returned. A ``passed`` record is admitted only with all
    four faculties (fail closed: logged, nothing held, ``None``). Today the
    record goes to the trace as a log line and on the conscience result, which
    streams; when the trace format carries it signed (rc21: the record is
    node-local, signed with the ``trace:complete`` that anchors the act), that
    write replaces the log line here and nothing else changes.
    """
    record = entry.record
    if record.outcome is ReviewOutcome.PASSED and record.missing_faculties:
        logger.warning(
            "[REVIEW_RECORD] passed record NOT stamped for %s (thought %s): missing faculties %s",
            record.fingerprint,
            record.thought,
            sorted(record.missing_faculties),
        )
        return None
    _hold(entry)
    logger.info(
        "[REVIEW_RECORD] %s %s thought=%s task=%s faculties=%s discharges=%d considered=%d digest=%s",
        record.outcome.value,
        record.fingerprint,
        record.thought,
        entry.task_id,
        ",".join(record.faculties),
        len(record.discharges),
        len(record.considered),
        entry.digest,
    )
    return entry


def record_review(entry: ReviewEntry) -> Optional[ReviewEntry]:
    """Alias of :func:`admit_reviewed_action` for objected records (reads better at that call site)."""
    return admit_reviewed_action(entry)


def review_entries_for(thought_id: str) -> Tuple[ReviewEntry, ...]:
    """Every record held for ``thought_id`` (passed and objected), oldest first. Read-only."""
    return tuple(_RECORDS.get(thought_id, ()))


def objection_digests_for(thought_id: str) -> Tuple[str, ...]:
    """Digests of the thought's objected records so far: what a later pass names as ``considered``."""
    return tuple(e.digest for e in review_entries_for(thought_id) if e.record.outcome is ReviewOutcome.OBJECTED)


def passed_entry_for(thought_id: str, fingerprint: str) -> Optional[ReviewEntry]:
    """The newest ``passed`` record of ``thought_id`` naming ``fingerprint``."""
    for entry in reversed(review_entries_for(thought_id)):
        if entry.record.outcome is ReviewOutcome.PASSED and entry.record.fingerprint == fingerprint:
            return entry
    return None


def undischarged_objections(passed: ReviewEntry, entries: Sequence[ReviewEntry]) -> List[ReviewEntry]:
    """The thought's objections this pass may not dispatch over (THE rule, isolated).

    Constitution answer 2026-11-18: objections bind their own fingerprint. A
    changed action is a new action, reviewed afresh by all four; an objection
    against a DIFFERENT fingerprint is carried as evidence (``considered``)
    and does not block. Against the SAME fingerprint:

    - an EVIDENCE objection needs a person's discharge: a trusted row id named
      in the passed record's ``discharges``;
    - a SUBSTANTIVE objection cannot be discharged by evidence (it is a ban):
      it blocks;
    - a JUSTIFICATION objection does not (the drafter may restate it).
    """
    discharged = {d.objection for d in passed.record.discharges}
    blocking: List[ReviewEntry] = []
    for entry in entries:
        if entry.record.outcome is not ReviewOutcome.OBJECTED:
            continue
        if entry.record.fingerprint != passed.record.fingerprint:
            continue
        kinds = set(entry.objection_types) or {ObjectionType.SUBSTANTIVE}
        if ObjectionType.SUBSTANTIVE in kinds:
            blocking.append(entry)
        elif ObjectionType.EVIDENCE in kinds and entry.digest not in discharged:
            blocking.append(entry)
    return blocking


def uncarried_objections(passed: ReviewEntry, entries: Sequence[ReviewEntry]) -> List[ReviewEntry]:
    """The thought's earlier objections against ANOTHER fingerprint that ``passed`` does not carry.

    rc21 rev 2 (``action_objection_not_carried``): every objection record of
    the thought raised against another fingerprint before this pass must be
    named, by its digest, in the pass's ``considered``, so a retry never loses
    the evidence. Objections against the SAME fingerprint are the discharge
    rule's (:func:`undischarged_objections`), not this one's.
    """
    considered = set(passed.record.considered)
    missing: List[ReviewEntry] = []
    for entry in entries:
        if entry is passed:
            break
        record = entry.record
        if record.outcome is not ReviewOutcome.OBJECTED or record.fingerprint == passed.record.fingerprint:
            continue
        if entry.digest not in considered:
            missing.append(entry)
    return missing


def consume_passed_record(thought_id: str, fingerprint: str) -> None:
    """Spend the admission: one review admits one execution."""
    entries = _RECORDS.get(thought_id)
    if not entries:
        return
    for index in range(len(entries) - 1, -1, -1):
        record = entries[index].record
        if record.outcome is ReviewOutcome.PASSED and record.fingerprint == fingerprint:
            del entries[index]
            return


def reset_admitted_records() -> None:
    """For tests and runtime teardown."""
    _RECORDS.clear()


__all__ = [
    "FINGERPRINT_PREFIX",
    "REQUIRED_REVIEW_FACULTIES",
    "TOOL_VERB",
    "action_review_fingerprint",
    "admit_reviewed_action",
    "cde_encode",
    "ceg_call_fingerprint",
    "consume_passed_record",
    "fingerprint_wire",
    "make_review_entry",
    "objection_digests_for",
    "passed_entry_for",
    "record_review",
    "reset_admitted_records",
    "resolve_tool_name_via_bus",
    "row_ref_wire",
    "review_entries_for",
    "review_record_digest",
    "review_record_wire",
    "reviewed_action_fingerprint",
    "reviewed_call_fingerprint",
    "tool_call_fingerprint",
    "uncarried_objections",
    "undischarged_objections",
]
