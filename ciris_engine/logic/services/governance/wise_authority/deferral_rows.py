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
room"). There is no agent<->user room yet (#1300), and the stop-gap derivation,
edge's ``pair_community_key_id(agent_identity, owner_fedID)``, cannot be made
reliably from here: no ciris_server/ciris_edge binding exports it, and the
"agent identity" the node signs about is persist's
``active_identity_for_occurrence(occurrence)``, which no Python binding exposes
(``lookup_identity_for_occurrence_json`` is the historical LIMIT-1 read persist
warns is not an admission resolver). A Python copy of the hash over a guessed
identity would place well-formed rows in a room nobody installs, so
:func:`deferral_room_id` answers None until the node can name the room.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
from typing import Callable, List, Optional

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

#: Pages of one dimension a read-back walks before it gives up (newest first).
_READ_PAGE_SIZE = 100
_READ_MAX_PAGES = 20

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
    """The room a deferral's rows belong in, or None. None until #1300: see the module docstring."""
    return None


async def _call(name: str, *args: object) -> str:
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


async def emit_identity_amendment(amendment_text: str, authorized_by: str) -> str:
    """Sign ``identity_amendment:v1`` citing the approved response. The node checks CC 3.1.5 first."""
    return await _call("emit_identity_amendment", sha256_hex(amendment_text), authorized_by)


# --------------------------------------------------------------------- read back


def _view(item: object) -> Optional[DeferralRowView]:
    if not isinstance(item, dict):
        return None
    envelope = item.get("attestation_envelope")
    env = envelope if isinstance(envelope, dict) else {}

    def text(key: str) -> Optional[str]:
        value = env.get(key)
        return str(value) if isinstance(value, str) and value else None

    refs = env.get("evidence_refs")
    evidence: List[str] = [str(r) for r in refs] if isinstance(refs, list) else []
    return DeferralRowView(
        attestation_id=str(item.get("attestation_id", "")),
        attestation_type=str(item.get("attestation_type", "")),
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


def _read_deferral_row_sync(attestation_id: str) -> Optional[DeferralRowView]:
    """Find one deferral-family row by id in the node's store. Blocking; never call on the event loop."""
    from ciris_engine.logic.persistence.models.graph import get_persist_engine
    from ciris_engine.logic.runtime.edge_runtime import get_federation_address

    engine = get_persist_engine()
    list_attestations = getattr(engine, "list_attestations", None)
    if list_attestations is None:
        raise DeferralRowsUnavailable("no persist engine to read rows from")
    caller = get_federation_address()
    for dimension in DEFERRAL_ROW_DIMENSIONS:
        cursor: Optional[str] = None
        for _ in range(_READ_MAX_PAGES):
            page = json.loads(
                list_attestations(json.dumps({"attestation_type": dimension}), cursor, _READ_PAGE_SIZE, caller)
            )
            for item in page.get("items", []) if isinstance(page, dict) else []:
                if isinstance(item, dict) and item.get("attestation_id") == attestation_id:
                    return _view(item)
            next_cursor = page.get("next_cursor") if isinstance(page, dict) else None
            if not next_cursor:
                break
            cursor = json.dumps(next_cursor)
    return None


async def read_deferral_row(attestation_id: str) -> Optional[DeferralRowView]:
    """One of the three rows by id, or None when this node's store does not hold it."""
    if not rows_available():
        raise DeferralRowsUnavailable("this node has no deferral rows")
    return await asyncio.wait_for(
        asyncio.to_thread(_read_deferral_row_sync, attestation_id), timeout=DEFERRAL_ROW_CALL_TIMEOUT_SECONDS
    )


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
    "rows_available",
    "sha256_hex",
]
