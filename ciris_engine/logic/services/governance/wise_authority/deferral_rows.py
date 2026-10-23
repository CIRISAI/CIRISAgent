"""THE seam to the node for a deferral's signed CEG rows (CIRISAgent#1316).

The server builds and signs every row; the agent calls it at three moments and
keeps the ids it returns (Eric, 2026-10-22: "Server should handle almost all of
this"):

- the agent defers            -> :func:`emit_deferral_request`  (``deferral:request:v1``)
- a Wise Authority answers    -> :func:`emit_deferral_response` (``deferral:response:{approved|rejected}:v1``)
- the approved change lands   -> :func:`emit_identity_amendment` (``identity_amendment:v1``)

These are in-process ``ciris_server.*`` functions (0.5.234+), imported lazily
the way ``resolve_bearer`` and ``owner_record`` are, and run off the event loop
(they block on the node's own runtime). Each returns the stored attestation_id,
or raises ``"<reason_id>: <text>"`` as ValueError (bad input / unknown request),
PermissionError (an authority refusal) or RuntimeError (a store outage, not a
verdict). :func:`parse_refusal` turns that into a typed
:class:`DeferralRowRefusal`.

ROWS UNAVAILABLE is not a refusal. A server older than 0.5.234 (the functions
are missing), no ``ciris_server`` at all, or no node in this process
(``CIRIS_NODE_FOLD=false``) raises :class:`DeferralRowsUnavailable`; callers
then behave exactly as before #1316. Nothing here ever fakes a row.

THE ROOM. The rows belong in the room of the agent's conversation with the
person (Eric: "Deferrals are not chat messages, but they do use the same
room"). There is no agent<->user room yet (#1300). Until there is, the NODE
names the room: with ``room_id`` absent it derives the agent<->owner pair room
(edge's ``pair_community_key_id`` over the registered agent principal and the
owner's fedID, CIRISServer#815), and the response and the amendment inherit it.
The agent does not derive it: no binding exports the hash, and only the node
knows which identity it signs about. So :func:`deferral_room_id` answers None,
which means "the node's default room", until #1300 gives the agent a room id.

READ-BACK is ``ciris_server.deferral_rows(ids)`` (0.5.234): this node's own
store, one entry per id or null, so the owner-signed response is visible. Rows
are ``scores`` attestations; which row it is lives in the signed envelope
member ``dimension``, never in ``attestation_type``.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
from typing import Callable, Dict, List, Optional

from ciris_engine.schemas.services.authority.deferral_rows import (
    DEFERRAL_ROW_DIMENSIONS,
    REASON_TIMEOUT,
    REASON_UNPARSED,
    DeferralRowRefusal,
    DeferralRowRefusalKind,
    DeferralRowView,
)

logger = logging.getLogger(__name__)

#: One signed write on the node. Longer than this and the store is not answering.
DEFERRAL_ROW_CALL_TIMEOUT_SECONDS = 15.0

_SERVER_FUNCTIONS = ("emit_deferral_request", "emit_deferral_response", "emit_identity_amendment")
_REASON_RE = re.compile(r"^\s*([a-z][a-z0-9_]*(?:\.[a-z0-9_]+)*):\s?(.*)$", re.DOTALL)


class DeferralRowsUnavailable(Exception):
    """This node has no deferral rows (server < 0.5.234, no ciris_server, or no node). Not a refusal."""


class DeferralRowRefused(Exception):
    """The node refused to author the row, or did not answer. ``refusal`` says which and why."""

    def __init__(self, refusal: DeferralRowRefusal) -> None:
        super().__init__(f"{refusal.reason_id}: {refusal.text}")
        self.refusal = refusal


def parse_refusal(exc: BaseException) -> DeferralRowRefusal:
    """The node's ``"<reason_id>: <text>"`` exception as a typed refusal.

    The KIND comes from the exception class (the contract), the reason id from
    the message. A message without the prefix keeps its text under ``unparsed``.
    """
    if isinstance(exc, PermissionError):
        kind = DeferralRowRefusalKind.REFUSED
    elif isinstance(exc, ValueError):
        kind = DeferralRowRefusalKind.INVALID
    else:
        kind = DeferralRowRefusalKind.OUTAGE
    message = str(exc.args[0]) if exc.args else str(exc)
    match = _REASON_RE.match(message)
    if match is None:
        return DeferralRowRefusal(reason_id=REASON_UNPARSED, text=message.strip(), kind=kind)
    return DeferralRowRefusal(reason_id=match.group(1), text=match.group(2).strip(), kind=kind)


def _server_function(name: str) -> Optional[Callable[..., object]]:
    """``ciris_server.<name>``, or None when this process has no deferral rows."""
    from ciris_engine.logic.runtime.node_fold import fold_status

    if fold_status() is None:
        return None
    try:
        import ciris_server  # type: ignore[import-not-found, import-untyped, unused-ignore]
    except ImportError:
        return None
    fn = getattr(ciris_server, name, None)
    return fn if callable(fn) else None


def rows_available() -> bool:
    """True when this node authors all three rows (ciris_server >= 0.5.234, node folded in)."""
    return all(_server_function(name) is not None for name in _SERVER_FUNCTIONS)


def sha256_hex(text: str) -> str:
    """Lowercase hex SHA-256 of the UTF-8 text: the digest form every row carries."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def deferral_room_id() -> Optional[str]:
    """The room to name on a deferral's request row; None = the node's agent<->owner pair room (until #1300)."""
    return None


async def _call_raw(name: str, *args: object) -> object:
    """``ciris_server.<name>(*args)`` off the event loop; every failure a typed refusal."""
    fn = _server_function(name)
    if fn is None:
        raise DeferralRowsUnavailable(f"ciris_server.{name} is not available on this node")
    try:
        result = await asyncio.wait_for(asyncio.to_thread(fn, *args), timeout=DEFERRAL_ROW_CALL_TIMEOUT_SECONDS)
    except asyncio.TimeoutError:
        raise DeferralRowRefused(
            DeferralRowRefusal(
                reason_id=REASON_TIMEOUT,
                text=f"ciris_server.{name} did not answer in {DEFERRAL_ROW_CALL_TIMEOUT_SECONDS:.0f}s",
                kind=DeferralRowRefusalKind.OUTAGE,
            )
        ) from None
    except Exception as exc:  # noqa: BLE001 - every failure is a typed refusal
        raise DeferralRowRefused(parse_refusal(exc)) from exc
    return result


async def _call(name: str, *args: object) -> str:
    """A signing call: its answer must be the stored attestation_id."""
    result = await _call_raw(name, *args)
    if not isinstance(result, str) or not result:
        raise DeferralRowRefused(
            DeferralRowRefusal(
                reason_id=REASON_UNPARSED,
                text=f"ciris_server.{name} returned {type(result).__name__}, not an attestation_id",
                kind=DeferralRowRefusalKind.OUTAGE,
            )
        )
    return result


async def emit_deferral_request(
    deferral_id: str,
    task_id: str,
    thought_id: str,
    reason: str,
    domain_hint: Optional[str] = None,
    room_id: Optional[str] = None,
) -> str:
    """Sign ``deferral:request:v1`` (occurrence key). The reason text stays local; its digest is signed."""
    return await _call(
        "emit_deferral_request", deferral_id, task_id, thought_id, sha256_hex(reason), domain_hint or None, room_id
    )


async def emit_deferral_response(request_id: str, approved: bool, bearer: Optional[str]) -> str:
    """Sign the Wise Authority's answer with the RESOLVER's own key; ``bearer`` is their raw ``sess:`` token."""
    return await _call("emit_deferral_response", request_id, approved, bearer)


async def emit_identity_amendment(amendment_text: str, authorized_by: str, request_id: str) -> str:
    """Sign ``identity_amendment:v1`` citing the approved response to ``request_id``, this agent's deferral.

    The node checks CC 3.1.5 first, that the response answers that request, and
    that the response has not already authorized an amendment
    (``deferral.response_already_used``): one approval, one amendment.
    """
    return await _call("emit_identity_amendment", sha256_hex(amendment_text), authorized_by, request_id)


# --------------------------------------------------------------------- read back


def _view(item: object) -> Optional[DeferralRowView]:
    """One stored row as a typed view, or None when it is not one of the deferral rows."""
    if not isinstance(item, dict):
        return None
    envelope = item.get("attestation_envelope")
    env: Dict[str, object] = envelope if isinstance(envelope, dict) else {}

    def text(key: str) -> Optional[str]:
        value = env.get(key)
        return str(value) if isinstance(value, str) and value else None

    dimension = text("dimension")
    if dimension not in DEFERRAL_ROW_DIMENSIONS:
        return None
    refs = env.get("evidence_refs")
    evidence: List[str] = [str(r) for r in refs] if isinstance(refs, list) else []
    weight = item.get("weight")
    return DeferralRowView(
        attestation_id=str(item.get("attestation_id", "")),
        dimension=str(dimension),
        attestation_type=str(item.get("attestation_type", "")),
        weight=float(weight) if isinstance(weight, (int, float)) else None,
        attesting_key_id=str(item.get("attesting_key_id", "")),
        attested_key_id=str(item.get("attested_key_id", "")),
        asserted_at=str(item.get("asserted_at", "")),
        deferral_id=text("deferral_id"),
        reason_digest=text("reason_digest"),
        references_attestation_id=text("references_attestation_id"),
        amendment_digest=text("amendment_digest"),
        authorized_by=text("authorized_by"),
        evidence_refs=evidence,
        room_id=text("community_key_id"),
    )


async def read_deferral_rows(ids: List[str]) -> List[Optional[DeferralRowView]]:
    """The rows by id from this node's own store, one entry per id: the row, or None.

    None also for a stored row that is not one of the four deferral dimensions:
    this reads deferral rows, not attestations in general. Raises
    :class:`DeferralRowsUnavailable` on a server without ``deferral_rows``.
    """
    raw = await _call_raw("deferral_rows", list(ids))
    try:
        entries = json.loads(raw if isinstance(raw, (str, bytes, bytearray)) else "")
    except (TypeError, ValueError) as exc:
        raise DeferralRowRefused(
            DeferralRowRefusal(
                reason_id=REASON_UNPARSED, text=f"deferral_rows returned unreadable JSON: {exc}", kind=DeferralRowRefusalKind.OUTAGE
            )
        ) from exc
    if not isinstance(entries, list) or len(entries) != len(ids):
        raise DeferralRowRefused(
            DeferralRowRefusal(
                reason_id=REASON_UNPARSED,
                text=f"deferral_rows answered {type(entries).__name__} for {len(ids)} ids",
                kind=DeferralRowRefusalKind.OUTAGE,
            )
        )
    return [_view(entry) if entry is not None else None for entry in entries]


async def read_deferral_row(attestation_id: str) -> Optional[DeferralRowView]:
    """One deferral row by id, or None when this node's store does not hold it."""
    (row,) = await read_deferral_rows([attestation_id])
    return row


__all__ = [
    "DEFERRAL_ROW_CALL_TIMEOUT_SECONDS",
    "DeferralRowRefused",
    "DeferralRowsUnavailable",
    "deferral_room_id",
    "emit_deferral_request",
    "emit_deferral_response",
    "emit_identity_amendment",
    "parse_refusal",
    "read_deferral_row",
    "read_deferral_rows",
    "rows_available",
    "sha256_hex",
]
