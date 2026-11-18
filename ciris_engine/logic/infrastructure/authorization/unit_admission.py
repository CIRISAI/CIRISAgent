"""Code admission: `admission:unit` for units loaded beyond the attested build (rc21 CC 2.7.11).

WHAT IS "BEYOND THE BUILD". A unit inside the attested build (an adapter
directory under an installed ``ciris_adapters`` package root, i.e.
``AdapterDiscoveryService.bundled_roots()``, checked by CIRISVerify file
integrity) runs under the build's attestation and never reaches this module.
Everything else does: an adapter directory found under any other discovery
root (``~/ciris/adapters``, ``.ciris/adapters``, ``CIRIS_EXTRA_ADAPTERS``,
an ``extra_paths`` entry), which is where imported skills
(``skill_import.py``) and built skills (``skill_builder.py``) land, and the
tools such a unit registers at runtime (they run through its service class,
which is tagged with its unit record when it loads).

ONE RULE. A unit beyond the build loads only under a live admitting row naming
the digest of the bytes about to load, and each tool call it serves is checked
against the capabilities those rows admit, the parent unit's held set, and the
halt latch. With no substrate support for the read, NOTHING beyond the build
loads (``admission_none``, detail ``no_row``): fail closed, with an incident and
an operator notice.

THE SERVER ADAPTER. Rows come from ONE function, `read_admission_rows`, which
asks ``ciris_server.admission_unit_rows(sub, owner_key_id)`` when the substrate
has it (capability check by attribute). Assumed shape: a JSON list of
`UnitAdmissionRow` (signature-verified rows for that `sub`, with the server's
standing walk and the counted protocol's answer filled in).
"""

from __future__ import annotations

import asyncio
import contextvars
import hashlib
import json
import logging
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, FrozenSet, Iterable, Iterator, List, Mapping, Optional, Set

from ciris_engine.schemas.runtime.unit_admission import (
    EFFECT_CAPABILITIES,
    PERSON_IDENTITY_TYPES,
    UNIT_DIGEST_TAG_PREFIX,
    UNIT_LEASE_MAX_SECS,
    AdmissionRead,
    AdmissionSigner,
    UnitAdmissionDecision,
    UnitAdmissionNoneDetail,
    UnitAdmissionRow,
    UnitAdmissionToken,
    UnitCapability,
)

logger = logging.getLogger(__name__)

#: The attribute a loaded unit's service class carries (its `UnitRecord`).
UNIT_RECORD_ATTR = "__ciris_admitted_unit__"

#: A read of rows for one digest. Slower than this and the substrate is not answering.
ADMISSION_READ_TIMEOUT_SECONDS = 2.0

#: Directory entries never part of a unit's bytes (interpreter caches, not code the host loads as written).
_SKIP_PARTS = frozenset({"__pycache__", ".git", ".mypy_cache", ".pytest_cache"})
_SKIP_SUFFIXES = (".pyc", ".pyo")

_ALL_CAPABILITIES: FrozenSet[str] = frozenset(c.value for c in UnitCapability)

OPERATOR_NOTICE_NO_SUPPORT = (
    "This host cannot read admission:unit rows (the node substrate has no admission read), so no code "
    "beyond the attested build loads: imported skills and adapters from user or workspace directories "
    "are refused. Built-in adapters are unaffected. Update the node to a release with admission reads, "
    "then admit the unit by its digest."
)

OPERATOR_NOTICE_REFUSED = (
    "Unit {digest} is not admitted on this host ({reason}). To run it, its admission:unit row must name "
    "this exact digest: the host owner alone may admit it for this host; any other admission of an effect "
    "capability needs a counted row of at least two persons."
)


# ---------------------------------------------------------------------------
# Digest
# ---------------------------------------------------------------------------


def unit_manifest_digest(manifest: Mapping[str, bytes]) -> bytes:
    """THE manifest encoding (rc21 wire §1): SHA-256 over the CDE map ``{path: [-16, file digest]}``.

    A unit of several files is named by this digest; each path is text, each value the file's SHA-256 in its
    wire form. CDE orders the keys, so the digest is independent of the order the files were read in.
    """
    from ciris_engine.logic.utils.cde import cde_encode, digest_wire

    return hashlib.sha256(cde_encode({path: digest_wire(digest) for path, digest in manifest.items()})).digest()


def digest_tag(digest: bytes) -> str:
    """`canonical:sha256:{hex}`, the row's `sub`."""
    return f"{UNIT_DIGEST_TAG_PREFIX}{digest.hex()}"


def _unit_files(unit_dir: Path) -> Iterator[Path]:
    for path in sorted(unit_dir.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(unit_dir)
        if any(part in _SKIP_PARTS for part in rel.parts) or path.suffix in _SKIP_SUFFIXES:
            continue
        yield path


def unit_digest(unit: Path) -> bytes:
    """The digest of a unit as loaded: one file by its bytes, a directory by its path->digest manifest."""
    if unit.is_file():
        return hashlib.sha256(unit.read_bytes()).digest()
    manifest = {path.relative_to(unit).as_posix(): hashlib.sha256(path.read_bytes()).digest() for path in _unit_files(unit)}
    return unit_manifest_digest(manifest)


# ---------------------------------------------------------------------------
# Scope: what is beyond the build
# ---------------------------------------------------------------------------


def is_beyond_build(unit_dir: Path) -> bool:
    """True unless ``unit_dir`` lies under an installed adapter package root (the attested build)."""
    from ciris_engine.logic.services.tool.discovery_service import AdapterDiscoveryService

    try:
        resolved = unit_dir.resolve()
    except OSError:
        return True
    for root in AdapterDiscoveryService.bundled_roots():
        if resolved == root or root in resolved.parents:
            return False
    return True


# ---------------------------------------------------------------------------
# The one server adapter
# ---------------------------------------------------------------------------


def read_admission_rows(sub: str, owner_key_id: Optional[str]) -> AdmissionRead:
    """THE adapter: every admission row for ``sub``, as the substrate holds them. Blocking.

    Capability check: the substrate answers only if ``ciris_server`` exposes
    ``admission_unit_rows``. Without it (fold off, no substrate, an older
    release) the answer is ``supported=False`` and nothing beyond the build loads.
    """
    from ciris_engine.logic.runtime.node_fold import fold_status

    if fold_status() is None:
        return AdmissionRead(supported=False, read_error="no node in this process")
    try:
        import ciris_server  # type: ignore[import-not-found, import-untyped, unused-ignore]
    except ImportError:
        return AdmissionRead(supported=False, read_error="no ciris_server substrate")
    reader = getattr(ciris_server, "admission_unit_rows", None)
    if reader is None:
        return AdmissionRead(supported=False, read_error="substrate has no admission_unit_rows")
    try:
        raw = reader(sub, owner_key_id)
        items = json.loads(raw) if isinstance(raw, (str, bytes)) else raw
        rows = [UnitAdmissionRow.model_validate(item) for item in (items or [])]
    except Exception as e:  # noqa: BLE001 - a read that cannot be parsed admits nothing
        return AdmissionRead(supported=True, read_error=f"{type(e).__name__}: {e}")
    return AdmissionRead(supported=True, rows=rows)


def _program_key_ids() -> Set[str]:
    """This host's own program keys (node key, the agent's signing key). They admit nothing."""
    keys: Set[str] = set()
    try:
        from ciris_engine.logic.runtime.edge_runtime import get_node_key_id

        node_key = get_node_key_id()
        if node_key:
            keys.add(str(node_key))
    except Exception:  # noqa: BLE001
        pass
    try:
        from ciris_engine.logic.persistence.models.graph import get_persist_engine

        engine = get_persist_engine()
        local = getattr(engine, "local_derived_key_id", None)
        if local is not None:
            keys.add(str(local()))
    except Exception:  # noqa: BLE001
        pass
    return keys


def _host_owner_key_sync() -> Optional[str]:
    """The owner key from the node's owner-binding (CC 3.2), for the synchronous load path."""
    from ciris_engine.logic.utils import node_ownership

    cached = node_ownership._cached
    if cached is not None and not cached.unclaimed:
        return cached.owner_key_id
    try:
        from ciris_engine.logic.runtime.node_fold import fold_status

        if fold_status() is None:
            return None
        state = node_ownership._read_owner_sync()
    except Exception:  # noqa: BLE001 - no owner read: no owner-alone admission
        return None
    return None if state.unclaimed else state.owner_key_id


async def _host_owner_key() -> Optional[str]:
    from ciris_engine.logic.utils.node_ownership import node_owned

    state = await node_owned()
    return None if state.unclaimed else state.owner_key_id


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------

#: row_id -> when this host first held it (ms). The lease also ends UNIT_LEASE_MAX_SECS after this.
_first_held_ms: Dict[str, int] = {}
#: Digests already reported as an incident (one incident per digest and reason per process).
_reported: Set[str] = set()


def _now_ms() -> int:
    return int(time.time() * 1000)


def _is_person(signer: AdmissionSigner, program_keys: Set[str]) -> bool:
    if signer.key_id in program_keys:
        return False
    parts = {p.strip() for p in signer.identity_type.replace("|", ",").split(",") if p.strip()}
    if parts & {"node", "agent"}:
        return False
    return bool(parts & PERSON_IDENTITY_TYPES)


@dataclass
class _RowVerdict:
    capabilities: Set[UnitCapability] = field(default_factory=set)
    refusal: Optional[UnitAdmissionToken] = None
    none_detail: Optional[UnitAdmissionNoneDetail] = None


def _judge_row(
    row: UnitAdmissionRow, *, now_ms: int, owner_key_id: Optional[str], program_keys: Set[str]
) -> _RowVerdict:
    """One row: does it admit now, and what? (CC 2.7.11; the row itself is left as it is.)"""
    # Structure (verifier checks; a malformed row admits nothing).
    if (row.author is None) == (row.refs_head is None):
        return _RowVerdict(refusal=UnitAdmissionToken.NONE, none_detail=UnitAdmissionNoneDetail.NO_ROW)
    if not row.capabilities or any(c not in _ALL_CAPABILITIES for c in row.capabilities):
        return _RowVerdict(refusal=UnitAdmissionToken.NONE, none_detail=UnitAdmissionNoneDetail.NO_ROW)
    caps = {UnitCapability(c) for c in row.capabilities}
    max_ms = UNIT_LEASE_MAX_SECS * 1000
    if not (row.asserted_at_ms < row.valid_until_ms <= row.asserted_at_ms + max_ms):
        return _RowVerdict(refusal=UnitAdmissionToken.NONE, none_detail=UnitAdmissionNoneDetail.NO_ROW)

    # The end.
    if row.withdrawn:
        return _RowVerdict(refusal=UnitAdmissionToken.NONE, none_detail=UnitAdmissionNoneDetail.WITHDRAWN)
    first = _first_held_ms.setdefault(row.row_id, now_ms)
    if now_ms < row.asserted_at_ms:
        return _RowVerdict(refusal=UnitAdmissionToken.NONE, none_detail=UnitAdmissionNoneDetail.NO_ROW)
    if now_ms >= row.valid_until_ms or now_ms >= first + max_ms:
        return _RowVerdict(refusal=UnitAdmissionToken.NONE, none_detail=UnitAdmissionNoneDetail.LEASE_ENDED)

    has_effect = bool(caps & EFFECT_CAPABILITIES)
    if row.author is not None:
        # Authored: one person. A program's key admits nothing.
        if not _is_person(row.author, program_keys):
            return _RowVerdict(refusal=UnitAdmissionToken.ISSUER_NOT_PERSON)
        is_owner = owner_key_id is not None and row.author.key_id == owner_key_id
        if not (is_owner or row.standing):
            return _RowVerdict(refusal=UnitAdmissionToken.ISSUER_NOT_REACHED)
        if has_effect and not is_owner:
            # Owner's ruling: an authored effect admits only on a host its author owns;
            # anywhere else it needs a counted row of at least two persons.
            return _RowVerdict(refusal=UnitAdmissionToken.ISSUER_NOT_REACHED)
        return _RowVerdict(capabilities=caps)

    # Counted: never fewer than two persons; a program's voice is refused alone (not counted).
    if not row.standing:
        return _RowVerdict(refusal=UnitAdmissionToken.ISSUER_NOT_REACHED)
    persons = {v.key_id for v in row.voices if _is_person(v, program_keys)}
    if row.count_met is not True or len(persons) < 2:
        return _RowVerdict(refusal=UnitAdmissionToken.COUNT_UNMET)
    return _RowVerdict(capabilities=caps)


#: When no row admits, the most telling reason wins.
_REFUSAL_ORDER = [
    UnitAdmissionToken.COUNT_UNMET,
    UnitAdmissionToken.ISSUER_NOT_PERSON,
    UnitAdmissionToken.ISSUER_NOT_REACHED,
    UnitAdmissionToken.NONE,
]
_NONE_ORDER = [UnitAdmissionNoneDetail.WITHDRAWN, UnitAdmissionNoneDetail.LEASE_ENDED, UnitAdmissionNoneDetail.NO_ROW]


def evaluate_admission(
    sub: str,
    read: AdmissionRead,
    *,
    owner_key_id: Optional[str],
    now_ms: Optional[int] = None,
    program_keys: Optional[Set[str]] = None,
) -> UnitAdmissionDecision:
    """The host's answer for a unit: admitted with the union of live rows' capabilities, or a token."""
    if not read.supported or read.read_error is not None or not read.rows:
        return UnitAdmissionDecision(
            token=UnitAdmissionToken.NONE,
            detail=UnitAdmissionNoneDetail.NO_ROW.value,
            unit_digest=sub,
            operator_notice=OPERATOR_NOTICE_NO_SUPPORT if not read.supported else None,
        )
    now = _now_ms() if now_ms is None else now_ms
    keys = _program_key_ids() if program_keys is None else program_keys
    admitted: Set[UnitCapability] = set()
    admitting: List[str] = []
    refusals: Set[UnitAdmissionToken] = set()
    none_details: Set[UnitAdmissionNoneDetail] = set()
    for row in read.rows:
        if row.sub != sub:
            continue
        verdict = _judge_row(row, now_ms=now, owner_key_id=owner_key_id, program_keys=keys)
        if verdict.refusal is None:
            admitted |= verdict.capabilities
            admitting.append(row.row_id)
        else:
            refusals.add(verdict.refusal)
            if verdict.none_detail is not None:
                none_details.add(verdict.none_detail)
    if admitting:
        return UnitAdmissionDecision(
            token=UnitAdmissionToken.ADMITTED,
            unit_digest=sub,
            admitted_capabilities=sorted(admitted, key=lambda c: c.value),
            admitting_rows=admitting,
        )
    token = next((t for t in _REFUSAL_ORDER if t in refusals), UnitAdmissionToken.NONE)
    detail: Optional[str] = None
    if token == UnitAdmissionToken.NONE:
        detail = next((d for d in _NONE_ORDER if d in none_details), UnitAdmissionNoneDetail.NO_ROW).value
    return UnitAdmissionDecision(token=token, detail=detail, unit_digest=sub)


def decide_capabilities(
    decision: UnitAdmissionDecision,
    required: Iterable[UnitCapability],
    *,
    parent_held: Optional[FrozenSet[UnitCapability]],
    halted: bool,
) -> UnitAdmissionDecision:
    """One effect: every required capability admitted, held by the parent, and no effect under a halt."""
    if not decision.admitted:
        return decision
    admitted = set(decision.admitted_capabilities)
    for cap in sorted(set(required), key=lambda c: c.value):
        if cap not in admitted:
            return decision.model_copy(update={"token": UnitAdmissionToken.CAPABILITY_NOT_ADMITTED, "detail": cap.value})
        if parent_held is not None and cap not in parent_held:
            return decision.model_copy(update={"token": UnitAdmissionToken.CAPABILITY_NOT_HELD, "detail": cap.value})
        if halted and cap in EFFECT_CAPABILITIES:
            return decision.model_copy(update={"token": UnitAdmissionToken.HALTED, "detail": cap.value})
    return decision


def _report(decision: UnitAdmissionDecision, unit_name: str) -> UnitAdmissionDecision:
    """Incident once per digest and reason, and an operator notice on the decision."""
    if decision.admitted:
        return decision
    notice = decision.operator_notice or OPERATOR_NOTICE_REFUSED.format(
        digest=decision.unit_digest, reason=decision.message()
    )
    key = f"{decision.unit_digest}|{decision.message()}"
    if key not in _reported:
        _reported.add(key)
        logger.error("UNIT ADMISSION REFUSED: %s (%s): %s. %s", unit_name, decision.unit_digest, decision.message(), notice)
    return decision.model_copy(update={"operator_notice": notice})


# ---------------------------------------------------------------------------
# Load path
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class UnitRecord:
    """A unit beyond the build that was admitted to load (tagged on its service classes)."""

    name: str
    unit_dir: str
    digest: str
    #: The manifest's declared capabilities for its tools (None: undeclared, every effect).
    declared: Optional[FrozenSet[UnitCapability]]
    #: The held set of the unit that started this one (None: started by the host).
    parent_held: Optional[FrozenSet[UnitCapability]]


#: The capabilities held by the unit whose code is running now (attenuation, CC 2.7.11).
_current_held: contextvars.ContextVar[Optional[FrozenSet[UnitCapability]]] = contextvars.ContextVar(
    "ciris_unit_held", default=None
)


@contextmanager
def unit_scope(held: FrozenSet[UnitCapability]) -> Iterator[None]:
    """Run code as a unit holding ``held``; units started inside hold at most this."""
    parent = _current_held.get()
    effective = held if parent is None else held & parent
    token = _current_held.set(effective)
    try:
        yield
    finally:
        _current_held.reset(token)


def check_unit_load_sync(unit_dir: Path, name: str) -> Optional[UnitAdmissionDecision]:
    """Before a unit loads. None: inside the attested build (out of scope). Blocking."""
    if not is_beyond_build(unit_dir):
        return None
    try:
        sub = digest_tag(unit_digest(unit_dir))
    except OSError as e:
        return _report(
            UnitAdmissionDecision(
                token=UnitAdmissionToken.NONE, detail=UnitAdmissionNoneDetail.NO_ROW.value, unit_digest="unreadable"
            ),
            f"{name} ({e})",
        )
    owner = _host_owner_key_sync()
    decision = evaluate_admission(sub, read_admission_rows(sub, owner), owner_key_id=owner)
    return _report(decision, name)


def tag_unit_class(cls: Any, record: UnitRecord) -> None:
    """Mark a service class loaded from an admitted unit, so each tool call it serves is checked."""
    try:
        setattr(cls, UNIT_RECORD_ATTR, record)
    except (AttributeError, TypeError):
        logger.error("Unit %s: cannot tag %r; its tool calls would go unchecked", record.name, cls)
        raise


def unit_of(service: Any) -> Optional[UnitRecord]:
    record = getattr(type(service), UNIT_RECORD_ATTR, None)
    return record if isinstance(record, UnitRecord) else None


def admitted_unit_record(
    decision: UnitAdmissionDecision, unit_dir: Path, name: str, declared: Optional[FrozenSet[UnitCapability]]
) -> UnitRecord:
    """The record a loaded unit's service class carries; the parent is whatever unit is running now."""
    return UnitRecord(
        name=name,
        unit_dir=str(unit_dir),
        digest=decision.unit_digest,
        declared=declared,
        parent_held=_current_held.get(),
    )


# ---------------------------------------------------------------------------
# Effect path
# ---------------------------------------------------------------------------


def required_capabilities(tool_declared: Optional[Iterable[UnitCapability]], record: UnitRecord) -> FrozenSet[UnitCapability]:
    """The tool's declaration, else the unit manifest's, else every effect."""
    if tool_declared is not None:
        return frozenset(tool_declared)
    if record.declared is not None:
        return record.declared
    return EFFECT_CAPABILITIES


async def check_unit_tool_call(service: Any, tool_name: str) -> Optional[UnitAdmissionDecision]:
    """Before each tool call a unit serves. None: not a unit beyond the build. Re-reads the rows each time."""
    record = unit_of(service)
    if record is None:
        return None
    tool_declared: Optional[List[UnitCapability]] = None
    try:
        info = await service.get_tool_info(tool_name)
        tool_declared = getattr(info, "unit_capabilities", None)
    except Exception:  # noqa: BLE001 - undeclared: every effect
        tool_declared = None
    required = required_capabilities(tool_declared, record)

    owner = await _host_owner_key()
    try:
        read = await asyncio.wait_for(
            asyncio.to_thread(read_admission_rows, record.digest, owner), timeout=ADMISSION_READ_TIMEOUT_SECONDS
        )
    except asyncio.TimeoutError:
        read = AdmissionRead(supported=True, read_error="timeout")
    decision = evaluate_admission(record.digest, read, owner_key_id=owner)

    halted = False
    if required & EFFECT_CAPABILITIES:
        from ciris_engine.logic.utils.halt_latch import read_halt_latch

        halted = (await read_halt_latch(fresh=True)).halted
    parent = record.parent_held
    running = _current_held.get()
    if running is not None:
        parent = running if parent is None else parent & running
    decision = decide_capabilities(decision, required, parent_held=parent, halted=halted)
    if decision.admitted and parent is not None:
        held = sorted(set(decision.admitted_capabilities) & parent, key=lambda c: c.value)
        decision = decision.model_copy(update={"admitted_capabilities": held})
    return _report(decision, f"{record.name}:{tool_name}")


def held_for(decision: UnitAdmissionDecision) -> FrozenSet[UnitCapability]:
    return frozenset(decision.admitted_capabilities)


def _reset_for_tests() -> None:
    _first_held_ms.clear()
    _reported.clear()


__all__ = [
    "UNIT_RECORD_ATTR",
    "UnitRecord",
    "check_unit_load_sync",
    "check_unit_tool_call",
    "decide_capabilities",
    "digest_tag",
    "evaluate_admission",
    "held_for",
    "is_beyond_build",
    "admitted_unit_record",
    "read_admission_rows",
    "required_capabilities",
    "tag_unit_class",
    "unit_digest",
    "unit_manifest_digest",
    "unit_of",
    "unit_scope",
]
