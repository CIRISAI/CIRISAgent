"""Universal Ticket Persistence Layer

This module provides database operations for the universal ticket system.
Tickets are CIRIS's mechanism for tracking multi-stage workflows with SOP
(Standard Operating Procedure) enforcement.

Universal Ticket Types:
- DSAR (Data Subject Access Requests) - Required for all agents (GDPR compliance)
- Agent-specific types defined in agent templates (appointments, incidents, etc.)

Architecture:
- SOP: Links to agent template configuration defining stages, tools, requirements
- Status: pending → in_progress → completed/cancelled/failed
- Metadata: JSON storing stage progress, results, and SOP-specific data
- Correlation ID: Links ticket to all tasks/thoughts processing it

GDPR Requirements (Universal DSAR Support):
- Article 15 (Access): 30-day response window - tickets persist across restarts
- Article 16 (Rectification): Track correction requests
- Article 17 (Erasure): Track deletion requests with 90-day decay protocol
- Article 20 (Portability): Track export requests

Note (CIRISAgent#763): public function signatures preserved verbatim; internals
routed through ciris-persist's `ticket_*` substrate (CIRISPersist#58 fix).
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, cast

logger = logging.getLogger(__name__)


_TERMINAL_STATUSES = {"completed", "cancelled", "failed"}


def _sanitize_for_log(value: Any, max_length: int = 64) -> str:
    """Sanitize user-controlled data for safe logging."""
    if value is None:
        return "<none>"
    val_str = str(value)
    sanitized = re.sub(r"[\x00-\x1f\x7f-\x9f]", "", val_str)
    if len(sanitized) > max_length:
        sanitized = sanitized[:max_length] + "..."
    return sanitized


def _get_engine() -> Any:
    """Return the wired persist engine; raise if not yet bootstrapped."""
    from ciris_engine.logic.persistence.models.graph import get_persist_engine

    engine = get_persist_engine()
    if engine is None:
        raise RuntimeError(
            "persist engine not initialized — call initialize_database() "
            "before any ticket operation"
        )
    return engine


def _iso_or_str(value: Any) -> Optional[str]:
    """Coerce a datetime/ISO-string/None into RFC-3339 string."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _row_from_persist(row: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize a persist `ticket_get`/`ticket_list` row to the legacy `_row_to_dict` shape.

    Legacy callers expect:
        ticket_id, sop, ticket_type, status, priority,
        email, user_identifier,
        submitted_at, deadline, last_updated, completed_at,
        metadata (dict | None), notes, automated (bool),
        correlation_id, agent_occurrence_id
    """
    metadata_raw = row.get("metadata")
    metadata: Optional[Dict[str, Any]]
    if metadata_raw is None:
        metadata = None
    elif isinstance(metadata_raw, str):
        try:
            metadata = json.loads(metadata_raw)
        except json.JSONDecodeError:
            logger.warning("ticket %s: malformed metadata json, defaulting to empty", row.get("ticket_id"))
            metadata = {}
    elif isinstance(metadata_raw, dict):
        metadata = dict(metadata_raw)
    else:
        metadata = {}

    return {
        "ticket_id": row.get("ticket_id"),
        "sop": row.get("sop"),
        "ticket_type": row.get("ticket_type"),
        "status": row.get("status"),
        "priority": row.get("priority"),
        "email": row.get("email"),
        "user_identifier": row.get("user_identifier"),
        "submitted_at": _iso_or_str(row.get("submitted_at")),
        "deadline": _iso_or_str(row.get("deadline")),
        "last_updated": _iso_or_str(row.get("last_updated")),
        "completed_at": _iso_or_str(row.get("completed_at")),
        "metadata": metadata,
        "notes": row.get("notes"),
        "automated": bool(row.get("automated", False)),
        "correlation_id": row.get("correlation_id"),
        "agent_occurrence_id": row.get("agent_occurrence_id"),
    }


def _build_upsert_payload(
    *,
    ticket_id: str,
    sop: str,
    ticket_type: str,
    status: str,
    priority: int,
    email: str,
    user_identifier: Optional[str],
    submitted_at_iso: str,
    deadline_iso: Optional[str],
    last_updated_iso: str,
    completed_at_iso: Optional[str],
    metadata: Dict[str, Any],
    notes: Optional[str],
    automated: bool,
    correlation_id: Optional[str],
    agent_occurrence_id: str,
) -> Dict[str, Any]:
    """Build a persist ticket_upsert payload (drops None where persist treats absence as null)."""
    payload: Dict[str, Any] = {
        "ticket_id": ticket_id,
        "sop": sop,
        "ticket_type": ticket_type,
        "status": status,
        "priority": priority,
        "email": email,
        "submitted_at": submitted_at_iso,
        "last_updated": last_updated_iso,
        "created_at": submitted_at_iso,  # persist preserves created_at on conflict
        "metadata": metadata,
        "automated": automated,
        "agent_occurrence_id": agent_occurrence_id,
    }
    if user_identifier is not None:
        payload["user_identifier"] = user_identifier
    if deadline_iso is not None:
        payload["deadline"] = deadline_iso
    if completed_at_iso is not None:
        payload["completed_at"] = completed_at_iso
    if notes is not None:
        payload["notes"] = notes
    if correlation_id is not None:
        payload["correlation_id"] = correlation_id
    return payload


def create_ticket(
    ticket_id: str,
    sop: str,
    ticket_type: str,
    email: str,
    status: str = "pending",
    priority: int = 5,
    user_identifier: Optional[str] = None,
    submitted_at: Optional[datetime] = None,
    deadline: Optional[datetime] = None,
    metadata: Optional[Dict[str, Any]] = None,
    notes: Optional[str] = None,
    automated: bool = False,
    correlation_id: Optional[str] = None,
    agent_occurrence_id: Optional[str] = None,
    db_path: Optional[str] = None,
) -> bool:
    """Create a new ticket in the database (routed through persist `ticket_upsert`).

    `db_path` retained for signature compat; persist owns its connection.
    """
    submitted_dt = submitted_at if submitted_at is not None else datetime.now(timezone.utc)
    submitted_at_str = submitted_dt.isoformat() if isinstance(submitted_dt, datetime) else str(submitted_dt)
    deadline_str = _iso_or_str(deadline)

    if agent_occurrence_id is None:
        agent_occurrence_id = "__shared__"

    payload = _build_upsert_payload(
        ticket_id=ticket_id,
        sop=sop,
        ticket_type=ticket_type,
        status=status,
        priority=priority,
        email=email,
        user_identifier=user_identifier,
        submitted_at_iso=submitted_at_str,
        deadline_iso=deadline_str,
        last_updated_iso=submitted_at_str,
        completed_at_iso=None,
        metadata=dict(metadata or {}),
        notes=notes,
        automated=automated,
        correlation_id=correlation_id,
        agent_occurrence_id=agent_occurrence_id,
    )

    try:
        _get_engine().ticket_upsert(json.dumps(payload))
        logger.info(
            "Created ticket %s (sop: %s, type: %s, status: %s)",
            _sanitize_for_log(ticket_id),
            _sanitize_for_log(sop),
            _sanitize_for_log(ticket_type),
            _sanitize_for_log(status),
        )
        return True
    except Exception as e:
        logger.exception(f"Failed to create ticket {ticket_id}: {e}")
        return False


def get_ticket(ticket_id: str, db_path: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Retrieve a ticket by ID via persist `ticket_get`. Returns legacy-shaped dict or None."""
    try:
        engine = _get_engine()
        raw = engine.ticket_get(ticket_id)
        if raw is None:
            logger.debug(f"get_ticket: No row found for {ticket_id}")
            return None
        row = json.loads(raw) if isinstance(raw, str) else raw
        if not isinstance(row, dict):
            return None
        return _row_from_persist(row)
    except Exception as e:
        logger.exception("Failed to retrieve ticket %s: %s", _sanitize_for_log(ticket_id), e)
        return None


def update_ticket_status(
    ticket_id: str,
    new_status: str,
    notes: Optional[str] = None,
    agent_occurrence_id: Optional[str] = None,
    require_current_occurrence_id: Optional[str] = None,
    db_path: Optional[str] = None,
) -> bool:
    """Update ticket status via persist substrate.

    Persist's `ticket_update_status` handles status + completed_at + notes but
    does NOT update `agent_occurrence_id`. When a caller asks to assign a new
    occurrence (e.g., atomic claiming from `__shared__`), we read-verify-upsert.
    """
    now_iso = datetime.now(timezone.utc).isoformat()
    completed_at_iso: Optional[str] = now_iso if new_status in _TERMINAL_STATUSES else None

    try:
        engine = _get_engine()

        # If caller wants to reassign occurrence or enforce a current-occurrence
        # gate, we have to go through a read-verify-upsert path because persist's
        # focused update_status doesn't expose those.
        if agent_occurrence_id is not None or require_current_occurrence_id is not None:
            raw = engine.ticket_get(ticket_id)
            if raw is None:
                logger.warning("Ticket %s not found for status update", _sanitize_for_log(ticket_id))
                return False
            existing_dict = json.loads(raw) if isinstance(raw, str) else raw
            if not isinstance(existing_dict, dict):
                return False

            if require_current_occurrence_id is not None:
                current = existing_dict.get("agent_occurrence_id")
                if current != require_current_occurrence_id:
                    logger.debug(
                        "Ticket %s claim failed: current occurrence=%s, required=%s",
                        _sanitize_for_log(ticket_id),
                        _sanitize_for_log(current),
                        _sanitize_for_log(require_current_occurrence_id),
                    )
                    return False

            existing = _row_from_persist(existing_dict)
            new_metadata = existing["metadata"] or {}
            target_occurrence_id = (
                agent_occurrence_id
                if agent_occurrence_id is not None
                else existing["agent_occurrence_id"]
            )
            payload = _build_upsert_payload(
                ticket_id=ticket_id,
                sop=existing["sop"],
                ticket_type=existing["ticket_type"],
                status=new_status,
                priority=existing["priority"] if existing["priority"] is not None else 5,
                email=existing["email"],
                user_identifier=existing["user_identifier"],
                submitted_at_iso=existing["submitted_at"] or now_iso,
                deadline_iso=existing["deadline"],
                last_updated_iso=now_iso,
                completed_at_iso=completed_at_iso,
                metadata=cast(Dict[str, Any], new_metadata),
                notes=notes if notes is not None else existing["notes"],
                automated=existing["automated"],
                correlation_id=existing["correlation_id"],
                agent_occurrence_id=target_occurrence_id or "__shared__",
            )
            engine.ticket_upsert(json.dumps(payload))
            logger.info(
                "Updated ticket %s status to %s (via upsert)",
                _sanitize_for_log(ticket_id),
                _sanitize_for_log(new_status),
            )
            return True

        # Fast path: focused status update.
        success = bool(engine.ticket_update_status(ticket_id, new_status, completed_at_iso, notes))
        if success:
            logger.info(
                "Updated ticket %s status to %s",
                _sanitize_for_log(ticket_id),
                _sanitize_for_log(new_status),
            )
        else:
            logger.warning("Ticket %s not found for status update", _sanitize_for_log(ticket_id))
        return success
    except Exception as e:
        logger.exception("Failed to update ticket %s: %s", _sanitize_for_log(ticket_id), e)
        return False


def update_ticket_metadata(
    ticket_id: str,
    metadata: Dict[str, Any],
    db_path: Optional[str] = None,
) -> bool:
    """Replace metadata for a ticket via read-modify-upsert.

    Persist doesn't expose a focused `metadata` update; we re-upsert the full
    ticket payload.
    """
    try:
        engine = _get_engine()
        raw = engine.ticket_get(ticket_id)
        if raw is None:
            logger.warning(
                "[DB_UPDATE_METADATA] NOT_FOUND ticket_id=%s",
                _sanitize_for_log(ticket_id),
            )
            return False
        existing_dict = json.loads(raw) if isinstance(raw, str) else raw
        if not isinstance(existing_dict, dict):
            return False
        existing = _row_from_persist(existing_dict)

        now_iso = datetime.now(timezone.utc).isoformat()
        payload = _build_upsert_payload(
            ticket_id=ticket_id,
            sop=existing["sop"],
            ticket_type=existing["ticket_type"],
            status=existing["status"],
            priority=existing["priority"] if existing["priority"] is not None else 5,
            email=existing["email"],
            user_identifier=existing["user_identifier"],
            submitted_at_iso=existing["submitted_at"] or now_iso,
            deadline_iso=existing["deadline"],
            last_updated_iso=now_iso,
            completed_at_iso=existing["completed_at"],
            metadata=dict(metadata),
            notes=existing["notes"],
            automated=existing["automated"],
            correlation_id=existing["correlation_id"],
            agent_occurrence_id=existing["agent_occurrence_id"] or "__shared__",
        )
        engine.ticket_upsert(json.dumps(payload))
        return True
    except Exception as e:
        logger.exception("Failed to update ticket %s metadata: %s", _sanitize_for_log(ticket_id), e)
        return False


def _iter_ticket_pages(
    filter_dict: Dict[str, Any],
    *,
    page_size: int = 200,
) -> List[Dict[str, Any]]:
    """Iterate all pages of `ticket_list` for the given filter."""
    engine = _get_engine()
    last_ts = "9999-12-31T23:59:59Z"
    last_id = ""
    collected: List[Dict[str, Any]] = []

    while True:
        cursor_json = json.dumps(
            {"version": "v1", "last_ts": last_ts, "last_id": last_id}
        )
        raw = engine.ticket_list(json.dumps(filter_dict), cursor_json, page_size)
        try:
            parsed = json.loads(raw) if isinstance(raw, str) else raw
        except json.JSONDecodeError:
            break
        items = (parsed.get("items") if isinstance(parsed, dict) else None) or []
        if not items:
            break
        for row in items:
            if isinstance(row, dict):
                collected.append(row)
                last_ts = str(row.get("submitted_at", last_ts))
                last_id = str(row.get("ticket_id", ""))
        if len(items) < page_size:
            break
    return collected


def list_tickets(
    sop: Optional[str] = None,
    ticket_type: Optional[str] = None,
    status: Optional[str] = None,
    email: Optional[str] = None,
    limit: Optional[int] = None,
    db_path: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """List tickets with optional filters (newest-first by submitted_at)."""
    filter_dict: Dict[str, Any] = {}
    if sop:
        filter_dict["sop"] = sop
    if ticket_type:
        filter_dict["ticket_type"] = ticket_type
    if status:
        filter_dict["status"] = status
    if email:
        filter_dict["email"] = email

    try:
        rows = _iter_ticket_pages(filter_dict)
        result = [_row_from_persist(r) for r in rows]
        if limit is not None and limit >= 0:
            result = result[:limit]
        return result
    except Exception as e:
        logger.exception(
            "Failed to list tickets (sop=%s, type=%s, status=%s): %s",
            _sanitize_for_log(sop),
            _sanitize_for_log(ticket_type),
            _sanitize_for_log(status),
            e,
        )
        return []


def delete_ticket(ticket_id: str, db_path: Optional[str] = None) -> bool:
    """Delete a ticket.

    NOTE (CIRISAgent#763 / CIRISPersist follow-up): persist 1.5.19 does not
    expose a `ticket_delete` substrate yet. Use status-cancel instead — the
    only production caller paths funnel through cancellation flows. This
    function now marks the ticket as `cancelled` if it exists, returning True
    on successful state transition, False otherwise. Hard-delete will return
    once persist adds the API.
    """
    try:
        engine = _get_engine()
        raw = engine.ticket_get(ticket_id)
        if raw is None:
            logger.warning("Ticket %s not found for deletion", _sanitize_for_log(ticket_id))
            return False
        # Soft-delete via cancel status; warn so call-site reviewers see this.
        logger.warning(
            "delete_ticket(%s): persist substrate has no hard-delete; marking cancelled. "
            "See CIRISAgent#763.",
            _sanitize_for_log(ticket_id),
        )
        success = bool(
            engine.ticket_update_status(
                ticket_id, "cancelled", datetime.now(timezone.utc).isoformat(), None
            )
        )
        if success:
            logger.info("Cancelled ticket %s (delete path)", _sanitize_for_log(ticket_id))
        return success
    except Exception as e:
        logger.exception("Failed to delete ticket %s: %s", _sanitize_for_log(ticket_id), e)
        return False


def get_tickets_by_correlation_id(
    correlation_id: str,
    db_path: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Get all tickets linked to a correlation_id.

    Persist's `ticket_list` accepts `correlation_id` in the filter dict but as
    of 1.5.19 silently ignores it. We paginate everything and filter
    client-side; this matches the legacy ordering (newest-first).
    """
    try:
        rows = _iter_ticket_pages({})
        return [_row_from_persist(r) for r in rows if r.get("correlation_id") == correlation_id]
    except Exception as e:
        logger.exception(f"Failed to get tickets by correlation_id {correlation_id}: {e}")
        return []


# ---------------------------------------------------------------------------
# Internal helpers kept for backwards compat with test imports.
# ---------------------------------------------------------------------------


def _parse_metadata_value(value: Any) -> Optional[Dict[str, Any]]:
    """Parse metadata value from database row.

    Preserves legacy semantics for tests that exercise this helper directly.
    """
    if not value:
        return None
    try:
        if isinstance(value, str):
            parsed: Dict[str, Any] = json.loads(value)
            return parsed
        return dict(value) if value else {}
    except (json.JSONDecodeError, TypeError) as e:
        logger.warning(
            "_parse_metadata_value: Failed to parse metadata, using empty dict. Error: %s, value type: %s",
            e,
            type(value),
        )
        return {}


def _parse_automated_value(value: Any) -> bool:
    return bool(value) if value is not None else False


def _parse_datetime_value(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _get_row_value(row: Any, key: str) -> Any:
    try:
        return row[key]
    except (KeyError, IndexError, TypeError):
        return None


def _row_to_dict(row: Any) -> Dict[str, Any]:
    """Compat wrapper for legacy callers expecting a row → dict converter.

    With the persist migration in place, `row` is now expected to be a dict
    returned from persist; legacy sqlite3.Row callers should already be gone.
    """
    columns = [
        "ticket_id",
        "sop",
        "ticket_type",
        "status",
        "priority",
        "email",
        "user_identifier",
        "submitted_at",
        "deadline",
        "last_updated",
        "completed_at",
        "metadata",
        "notes",
        "automated",
        "correlation_id",
        "agent_occurrence_id",
    ]
    datetime_columns = ("submitted_at", "deadline", "last_updated", "completed_at")
    result: Dict[str, Any] = {}
    for key in columns:
        value = _get_row_value(row, key)
        if key == "metadata":
            result[key] = _parse_metadata_value(value)
        elif key == "automated":
            result[key] = _parse_automated_value(value)
        elif key in datetime_columns:
            result[key] = _parse_datetime_value(value)
        else:
            result[key] = value
    return result
