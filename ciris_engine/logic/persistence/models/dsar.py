"""DSAR Ticket Persistence Layer

This module provides database operations for DSAR (Data Subject Access Request) tickets.
It replaces the in-memory dict storage to ensure GDPR compliance by persisting tickets
across server restarts.

GDPR Requirements:
- Article 15 (Access): 30-day response window - tickets must survive restarts
- Article 16 (Rectification): Track correction requests
- Article 17 (Erasure): Track deletion requests with 90-day decay protocol
- Article 20 (Portability): Track export requests

Architecture:
- Uses get_db_connection for database-agnostic operations (SQLite/PostgreSQL)
- Stores access_package and export_package as JSON text
- Boolean fields stored as INTEGER (0/1) for SQLite compatibility
- Timestamps stored as TEXT (ISO8601) for cross-database compatibility
"""

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from ciris_engine.logic.persistence.db import get_db_connection

logger = logging.getLogger(__name__)


def create_dsar_ticket(
    ticket_id: str,
    request_type: str,
    email: str,
    status: str,
    submitted_at: datetime,
    estimated_completion: datetime,
    automated: bool,
    user_identifier: Optional[str] = None,
    details: Optional[str] = None,
    urgent: bool = False,
    access_package: Optional[Dict[str, Any]] = None,
    export_package: Optional[Dict[str, Any]] = None,
    db_path: Optional[str] = None,
) -> bool:
    """Create a new DSAR ticket in the database.

    Args:
        ticket_id: Unique ticket identifier (format: DSAR-YYYYMMDD-XXXXXX)
        request_type: Type of request (access|delete|export|correct)
        email: Contact email for the request
        status: Initial status (typically "pending_review" or "completed")
        submitted_at: Submission timestamp
        estimated_completion: Estimated completion timestamp
        automated: Whether this was handled automatically
        user_identifier: Optional user identifier for data lookup
        details: Optional additional details about the request
        urgent: Whether this is an urgent request
        access_package: Optional DSARAccessPackage dict
        export_package: Optional DSARExportPackage dict
        db_path: Optional database path override

    Returns:
        True if ticket was created successfully, False otherwise
    """
    sql = """
        INSERT INTO dsar_tickets (
            ticket_id, request_type, email, user_identifier, details, urgent,
            status, submitted_at, estimated_completion, last_updated, automated,
            access_package_json, export_package_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """

    params = (
        ticket_id,
        request_type,
        email,
        user_identifier,
        details,
        1 if urgent else 0,  # Convert bool to int for SQLite
        status,
        submitted_at.isoformat(),
        estimated_completion.isoformat(),
        submitted_at.isoformat(),  # last_updated = submitted_at initially
        1 if automated else 0,  # Convert bool to int for SQLite
        json.dumps(access_package) if access_package else None,
        json.dumps(export_package) if export_package else None,
    )

    try:
        with get_db_connection(db_path=db_path) as conn:
            conn.execute(sql, params)
            conn.commit()
        logger.info(f"Created DSAR ticket {ticket_id} (type: {request_type}, status: {status})")
        return True
    except Exception as e:
        logger.exception(f"Failed to create DSAR ticket {ticket_id}: {e}")
        return False


def get_dsar_ticket(ticket_id: str, db_path: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Retrieve a DSAR ticket by ID.

    Args:
        ticket_id: Unique ticket identifier
        db_path: Optional database path override

    Returns:
        Dict containing ticket data, or None if not found
    """
    sql = "SELECT * FROM dsar_tickets WHERE ticket_id = ?"

    try:
        with get_db_connection(db_path=db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(sql, (ticket_id,))
            row = cursor.fetchone()

            if row:
                return _row_to_dict(row)
            return None
    except Exception as e:
        logger.exception(f"Failed to retrieve DSAR ticket {ticket_id}: {e}")
        return None


def update_dsar_ticket_status(
    ticket_id: str,
    new_status: str,
    notes: Optional[str] = None,
    db_path: Optional[str] = None,
) -> bool:
    """Update the status and notes of a DSAR ticket.

    Args:
        ticket_id: Unique ticket identifier
        new_status: New status (pending_review|in_progress|completed|rejected)
        notes: Optional notes about the status update
        db_path: Optional database path override

    Returns:
        True if update was successful, False otherwise
    """
    # Build SQL dynamically based on whether notes are provided
    if notes:
        sql = """
            UPDATE dsar_tickets
            SET status = ?, notes = ?, last_updated = ?
            WHERE ticket_id = ?
        """
        params = (new_status, notes, datetime.utcnow().isoformat(), ticket_id)
    else:
        sql = """
            UPDATE dsar_tickets
            SET status = ?, last_updated = ?
            WHERE ticket_id = ?
        """
        params = (new_status, datetime.utcnow().isoformat(), ticket_id)

    try:
        with get_db_connection(db_path=db_path) as conn:
            cursor = conn.execute(sql, params)
            conn.commit()

            if cursor.rowcount > 0:
                logger.info(f"Updated DSAR ticket {ticket_id} status to {new_status}")
                return True
            else:
                logger.warning(f"DSAR ticket {ticket_id} not found for status update")
                return False
    except Exception as e:
        logger.exception(f"Failed to update DSAR ticket {ticket_id}: {e}")
        return False


def list_dsar_tickets_by_status(
    status: Optional[str] = None,
    db_path: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """List DSAR tickets, optionally filtered by status.

    Args:
        status: Optional status filter (pending_review|in_progress|completed|rejected)
        db_path: Optional database path override

    Returns:
        List of ticket dicts sorted by submission date (newest first)
    """
    if status:
        sql = "SELECT * FROM dsar_tickets WHERE status = ? ORDER BY submitted_at DESC"
        params = (status,)
    else:
        sql = "SELECT * FROM dsar_tickets ORDER BY submitted_at DESC"
        params = ()

    try:
        with get_db_connection(db_path=db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(sql, params)
            rows = cursor.fetchall()
            return [_row_to_dict(row) for row in rows]
    except Exception as e:
        logger.exception(f"Failed to list DSAR tickets (status={status}): {e}")
        return []


def list_dsar_tickets_by_email(
    email: str,
    db_path: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """List DSAR tickets for a specific email address.

    Args:
        email: Email address to search for
        db_path: Optional database path override

    Returns:
        List of ticket dicts sorted by submission date (newest first)
    """
    sql = "SELECT * FROM dsar_tickets WHERE email = ? ORDER BY submitted_at DESC"

    try:
        with get_db_connection(db_path=db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(sql, (email,))
            rows = cursor.fetchall()
            return [_row_to_dict(row) for row in rows]
    except Exception as e:
        logger.exception(f"Failed to list DSAR tickets for email {email}: {e}")
        return []


def _row_to_dict(row) -> Dict[str, Any]:
    """Convert a database row to a dict matching the original _dsar_requests format.

    Args:
        row: Database row from cursor.fetchone() or cursor.fetchall()

    Returns:
        Dict with keys matching the original in-memory dict format
    """
    # Get column names from the row description
    keys = [desc[0] for desc in row.cursor_description] if hasattr(row, "cursor_description") else []

    # If keys not available from row, use standard column order
    if not keys:
        keys = [
            "ticket_id",
            "request_type",
            "email",
            "user_identifier",
            "details",
            "urgent",
            "status",
            "submitted_at",
            "estimated_completion",
            "last_updated",
            "notes",
            "automated",
            "access_package_json",
            "export_package_json",
            "created_at",
        ]

    # Create dict from row
    result: Dict[str, Any] = {}
    for i, key in enumerate(keys):
        value = row[i]

        # Convert JSON strings back to dicts
        if key in ("access_package_json", "export_package_json") and value:
            try:
                result[key.replace("_json", "")] = json.loads(value)
            except (json.JSONDecodeError, TypeError):
                result[key.replace("_json", "")] = None
        # Convert INTEGER booleans to Python bools
        elif key in ("urgent", "automated"):
            result[key] = bool(value)
        # Skip the _json and created_at fields (created_at is internal)
        elif key.endswith("_json") or key == "created_at":
            continue
        else:
            result[key] = value

    return result
