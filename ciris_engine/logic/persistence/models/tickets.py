"""Universal Ticket Persistence Layer

This module provides database operations for the universal ticket system.
Tickets are CIRIS's mechanism for tracking multi-stage workflows with SOP (Standard Operating Procedure) enforcement.

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
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from ciris_engine.logic.persistence.db import get_db_connection

logger = logging.getLogger(__name__)


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
    """Create a new ticket in the database.

    Args:
        ticket_id: Unique ticket identifier (format: TYPE-YYYYMMDD-XXXXXX)
        sop: Standard Operating Procedure (e.g., "DSAR_ACCESS", "APPOINTMENT_SCHEDULE")
        ticket_type: Category (e.g., "dsar", "appointment", "incident")
        email: Contact email for the ticket
        status: Initial status (default: "pending")
        priority: Priority level 1-10 (default: 5, urgent: 9-10)
        user_identifier: Optional user identifier for data lookup
        submitted_at: Submission timestamp (defaults to now)
        deadline: Deadline timestamp (calculated from SOP config if not provided)
        metadata: JSON metadata for stage progress and results
        notes: Optional notes about the ticket
        automated: Whether this was created automatically
        correlation_id: Optional correlation ID linking to tasks/thoughts
        agent_occurrence_id: Optional occurrence ID (defaults to __shared__ for pending, None for others)
        db_path: Optional database path override

    Returns:
        True if ticket was created successfully, False otherwise
    """
    if submitted_at is None:
        submitted_at = datetime.now(timezone.utc)

    # Handle both datetime objects and ISO strings
    submitted_at_str = submitted_at.isoformat() if isinstance(submitted_at, datetime) else submitted_at

    # Convert deadline to string format
    if deadline is None:
        deadline_str = None
    elif isinstance(deadline, datetime):
        deadline_str = deadline.isoformat()
    else:
        deadline_str = deadline

    # Default agent_occurrence_id to __shared__ so tickets can be claimed
    if agent_occurrence_id is None:
        agent_occurrence_id = "__shared__"

    sql = """
        INSERT INTO tickets (
            ticket_id, sop, ticket_type, status, priority,
            email, user_identifier,
            submitted_at, deadline, last_updated,
            metadata, notes, automated, correlation_id, agent_occurrence_id
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """

    params = (
        ticket_id,
        sop,
        ticket_type,
        status,
        priority,
        email,
        user_identifier,
        submitted_at_str,
        deadline_str,
        submitted_at_str,  # last_updated = submitted_at initially
        json.dumps(metadata or {}),
        notes,
        automated,  # Pass boolean directly - db adapter handles dialect conversion
        correlation_id,
        agent_occurrence_id,
    )

    try:
        with get_db_connection(db_path=db_path) as conn:
            conn.execute(sql, params)
            conn.commit()
        logger.info(f"Created ticket {ticket_id} (sop: {sop}, type: {ticket_type}, status: {status})")
        return True
    except Exception as e:
        logger.exception(f"Failed to create ticket {ticket_id}: {e}")
        return False


def get_ticket(ticket_id: str, db_path: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Retrieve a ticket by ID.

    Args:
        ticket_id: Unique ticket identifier
        db_path: Optional database path override

    Returns:
        Dict containing ticket data, or None if not found
    """
    sql = "SELECT * FROM tickets WHERE ticket_id = ?"

    try:
        with get_db_connection(db_path=db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(sql, (ticket_id,))
            row = cursor.fetchone()

            if row:
                logger.debug(f"get_ticket: Retrieved row for {ticket_id}, row type: {type(row)}")
                try:
                    result = _row_to_dict(row)
                    logger.debug(f"get_ticket: Converted to dict for {ticket_id}")
                    return result
                except Exception as convert_error:
                    logger.exception(f"get_ticket: Failed to convert row to dict for {ticket_id}: {convert_error}")
                    raise
            logger.debug(f"get_ticket: No row found for {ticket_id}")
            return None
    except Exception as e:
        logger.exception(f"Failed to retrieve ticket {ticket_id}: {e}")
        return None


def update_ticket_status(
    ticket_id: str,
    new_status: str,
    notes: Optional[str] = None,
    agent_occurrence_id: Optional[str] = None,
    require_current_occurrence_id: Optional[str] = None,
    db_path: Optional[str] = None,
) -> bool:
    """Update the status of a ticket.

    Args:
        ticket_id: Unique ticket identifier
        new_status: New status (pending|assigned|in_progress|blocked|deferred|completed|cancelled|failed)
        notes: Optional notes about the status update
        agent_occurrence_id: Optional occurrence ID to assign ticket to (for claiming)
        require_current_occurrence_id: If set, only update if ticket currently has this occurrence ID (for atomic claiming)
        db_path: Optional database path override

    Returns:
        True if update was successful, False otherwise
    """
    now = datetime.now(timezone.utc).isoformat()
    completed_at = now if new_status in ("completed", "cancelled", "failed") else None

    # Build SQL dynamically based on what's being updated
    updates = ["status = ?", "last_updated = ?", "completed_at = ?"]
    params = [new_status, now, completed_at]

    if notes:
        updates.append("notes = ?")
        params.append(notes)

    if agent_occurrence_id:
        updates.append("agent_occurrence_id = ?")
        params.append(agent_occurrence_id)

    # Build WHERE clause
    where_clauses = ["ticket_id = ?"]
    params.append(ticket_id)

    if require_current_occurrence_id is not None:
        where_clauses.append("agent_occurrence_id = ?")
        params.append(require_current_occurrence_id)

    sql = f"""
        UPDATE tickets
        SET {', '.join(updates)}
        WHERE {' AND '.join(where_clauses)}
    """

    try:
        with get_db_connection(db_path=db_path) as conn:
            cursor = conn.execute(sql, params)
            conn.commit()

            if cursor.rowcount > 0:
                logger.info(f"Updated ticket {ticket_id} status to {new_status}")
                return True
            else:
                logger.warning(f"Ticket {ticket_id} not found for status update")
                return False
    except Exception as e:
        logger.exception(f"Failed to update ticket {ticket_id}: {e}")
        return False


def update_ticket_metadata(
    ticket_id: str,
    metadata: Dict[str, Any],
    db_path: Optional[str] = None,
) -> bool:
    """Update the metadata of a ticket (used for stage progress tracking).

    Args:
        ticket_id: Unique ticket identifier
        metadata: New metadata dict (completely replaces existing metadata)
        db_path: Optional database path override

    Returns:
        True if update was successful, False otherwise
    """
    import time

    start_time = time.time()

    logger.debug(f"[DB_UPDATE_METADATA] T+0.000s START ticket_id={ticket_id} metadata={metadata}")

    sql = """
        UPDATE tickets
        SET metadata = ?, last_updated = ?
        WHERE ticket_id = ?
    """

    params = (
        json.dumps(metadata),
        datetime.now(timezone.utc).isoformat(),
        ticket_id,
    )

    try:
        logger.debug(f"[DB_UPDATE_METADATA] T+{time.time()-start_time:.3f}s EXECUTE_SQL ticket_id={ticket_id}")
        with get_db_connection(db_path=db_path) as conn:
            cursor = conn.execute(sql, params)
            logger.debug(f"[DB_UPDATE_METADATA] T+{time.time()-start_time:.3f}s PRE_COMMIT rowcount={cursor.rowcount}")
            conn.commit()
            logger.debug(f"[DB_UPDATE_METADATA] T+{time.time()-start_time:.3f}s POST_COMMIT")

            if cursor.rowcount > 0:
                logger.debug(f"[DB_UPDATE_METADATA] T+{time.time()-start_time:.3f}s SUCCESS ticket_id={ticket_id}")
                return True
            else:
                logger.warning(f"[DB_UPDATE_METADATA] T+{time.time()-start_time:.3f}s NOT_FOUND ticket_id={ticket_id}")
                return False
    except Exception as e:
        logger.exception(f"Failed to update ticket {ticket_id} metadata: {e}")
        return False


def list_tickets(
    sop: Optional[str] = None,
    ticket_type: Optional[str] = None,
    status: Optional[str] = None,
    email: Optional[str] = None,
    limit: Optional[int] = None,
    db_path: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """List tickets with optional filters.

    Args:
        sop: Optional SOP filter (e.g., "DSAR_ACCESS")
        ticket_type: Optional type filter (e.g., "dsar", "appointment")
        status: Optional status filter (pending|in_progress|completed|cancelled|failed)
        email: Optional email filter
        limit: Optional result limit
        db_path: Optional database path override

    Returns:
        List of ticket dicts sorted by submission date (newest first)
    """
    sql = "SELECT * FROM tickets WHERE 1=1"
    params: List[Any] = []

    if sop:
        sql += " AND sop = ?"
        params.append(sop)

    if ticket_type:
        sql += " AND ticket_type = ?"
        params.append(ticket_type)

    if status:
        sql += " AND status = ?"
        params.append(status)

    if email:
        sql += " AND email = ?"
        params.append(email)

    sql += " ORDER BY submitted_at DESC"

    if limit:
        sql += " LIMIT ?"
        params.append(limit)

    try:
        with get_db_connection(db_path=db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(sql, params)
            rows = cursor.fetchall()
            return [_row_to_dict(row) for row in rows]
    except Exception as e:
        logger.exception(f"Failed to list tickets (sop={sop}, type={ticket_type}, status={status}): {e}")
        return []


def delete_ticket(ticket_id: str, db_path: Optional[str] = None) -> bool:
    """Delete a ticket (used for cancellation).

    Args:
        ticket_id: Unique ticket identifier
        db_path: Optional database path override

    Returns:
        True if deletion was successful, False otherwise
    """
    sql = "DELETE FROM tickets WHERE ticket_id = ?"

    try:
        with get_db_connection(db_path=db_path) as conn:
            cursor = conn.execute(sql, (ticket_id,))
            conn.commit()

            if cursor.rowcount > 0:
                logger.info(f"Deleted ticket {ticket_id}")
                return True
            else:
                logger.warning(f"Ticket {ticket_id} not found for deletion")
                return False
    except Exception as e:
        logger.exception(f"Failed to delete ticket {ticket_id}: {e}")
        return False


def get_tickets_by_correlation_id(
    correlation_id: str,
    db_path: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Get all tickets linked to a correlation ID.

    Args:
        correlation_id: Correlation ID linking tickets to tasks/thoughts
        db_path: Optional database path override

    Returns:
        List of ticket dicts sorted by submission date (newest first)
    """
    sql = "SELECT * FROM tickets WHERE correlation_id = ? ORDER BY submitted_at DESC"

    try:
        with get_db_connection(db_path=db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(sql, (correlation_id,))
            rows = cursor.fetchall()
            return [_row_to_dict(row) for row in rows]
    except Exception as e:
        logger.exception(f"Failed to get tickets by correlation_id {correlation_id}: {e}")
        return []


def _parse_metadata_value(value: Any) -> Optional[Dict[str, Any]]:
    """Parse metadata value from database.

    Args:
        value: Metadata value (JSON string from SQLite or dict from PostgreSQL)

    Returns:
        Parsed metadata dict, empty dict on error, or None if value is None
    """
    if not value:
        return None  # Preserve None for missing metadata

    try:
        # PostgreSQL JSONB returns dict, SQLite returns string
        if isinstance(value, str):
            parsed: Dict[str, Any] = json.loads(value)
            return parsed
        # Already a dict from PostgreSQL JSONB
        return dict(value) if value else {}
    except (json.JSONDecodeError, TypeError) as e:
        logger.warning(
            f"_parse_metadata_value: Failed to parse metadata, using empty dict. Error: {e}, value type: {type(value)}"
        )
        return {}


def _parse_automated_value(value: Any) -> bool:
    """Parse automated boolean value from database.

    Args:
        value: Automated value (INTEGER from SQLite or BOOLEAN from PostgreSQL)

    Returns:
        Boolean value (defaults to False if None)
    """
    return bool(value) if value is not None else False


def _parse_datetime_value(value: Any) -> Optional[str]:
    """Parse datetime value from database.

    Args:
        value: Datetime value (ISO string from SQLite or datetime from PostgreSQL)

    Returns:
        ISO string or None
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        # PostgreSQL returns datetime objects
        return value.isoformat()
    # SQLite returns ISO strings already
    return str(value)


def _get_row_value(row: Any, key: str) -> Any:
    """Safely get value from database row.

    Args:
        row: Database row
        key: Column name

    Returns:
        Column value or None if not found
    """
    try:
        return row[key]
    except (KeyError, IndexError) as e:
        logger.debug(f"_get_row_value: Key {key} not found in row, using None. Error: {e}")
        return None


def _row_to_dict(row: Any) -> Dict[str, Any]:
    """Convert a database row to a dict.

    Args:
        row: Database row from cursor.fetchone() or cursor.fetchall()
            - SQLite: sqlite3.Row (supports both dict and int indexing)
            - PostgreSQL: psycopg2.extras.RealDictRow (dict-only access)

    Returns:
        Dict with ticket data
    """
    result: Dict[str, Any] = {}

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
        "created_at",
        "agent_occurrence_id",
    ]

    # Datetime columns that need special parsing
    datetime_columns = ("submitted_at", "deadline", "last_updated", "completed_at")

    for key in columns:
        # Skip internal-only column
        if key == "created_at":
            continue

        value = _get_row_value(row, key)

        # Apply type-specific parsing
        if key == "metadata":
            result[key] = _parse_metadata_value(value)
        elif key == "automated":
            result[key] = _parse_automated_value(value)
        elif key in datetime_columns:
            result[key] = _parse_datetime_value(value)
        else:
            result[key] = value

    return result
