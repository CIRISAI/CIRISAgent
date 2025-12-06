"""DSAR Ticket Persistence Layer - Compatibility Wrapper

This module provides backwards-compatible wrappers for DSAR operations.
As of migration 008, DSAR tickets are part of the universal tickets system.

This module exists for backwards compatibility and delegates to tickets.py.
New code should use tickets.py directly.

GDPR Requirements:
- Article 15 (Access): 30-day response window - tickets must survive restarts
- Article 16 (Rectification): Track correction requests
- Article 17 (Erasure): Track deletion requests with 90-day decay protocol
- Article 20 (Portability): Track export requests

Architecture:
- DSAR is now part of the universal tickets system (migration 008)
- This module provides backwards-compatible wrappers
- Translates old DSAR API to new tickets API
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .tickets import create_ticket, get_ticket, list_tickets, update_ticket_status

logger = logging.getLogger(__name__)


def _request_type_to_sop(request_type: str) -> str:
    """Map old request_type to new SOP identifier."""
    mapping = {
        "access": "DSAR_ACCESS",
        "delete": "DSAR_DELETE",
        "export": "DSAR_EXPORT",
        "correct": "DSAR_RECTIFY",
    }
    return mapping.get(request_type.lower(), "DSAR_ACCESS")


def _old_status_to_new(old_status: str) -> str:
    """Map old status names to new universal ticket status."""
    mapping = {
        "pending_review": "pending",
        "in_progress": "in_progress",
        "completed": "completed",
        "rejected": "cancelled",
    }
    return mapping.get(old_status, "pending")


def _new_status_to_old(new_status: str) -> str:
    """Map new status names back to old DSAR status for compatibility."""
    mapping = {
        "pending": "pending_review",
        "assigned": "in_progress",  # Map assigned to in_progress for backwards compat
        "in_progress": "in_progress",
        "completed": "completed",
        "cancelled": "rejected",
        "failed": "rejected",
        "blocked": "in_progress",  # Map blocked to in_progress
        "deferred": "pending_review",  # Map deferred to pending_review
    }
    return mapping.get(new_status, "pending_review")


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

    Backwards-compatible wrapper that delegates to create_ticket().

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
    # Map old parameters to new
    sop = _request_type_to_sop(request_type)
    new_status = _old_status_to_new(status)
    priority = 9 if urgent else 5

    # Build metadata from legacy fields
    metadata = {
        "legacy_request_type": request_type,
        "legacy_details": details or "",
        "access_package": access_package,
        "export_package": export_package,
        "stages": {},
    }

    # Delegate to new API
    return create_ticket(
        ticket_id=ticket_id,
        sop=sop,
        ticket_type="dsar",
        email=email,
        status=new_status,
        priority=priority,
        user_identifier=user_identifier,
        submitted_at=submitted_at,
        deadline=estimated_completion,
        metadata=metadata,
        notes=details,
        automated=automated,
        db_path=db_path,
    )


def get_dsar_ticket(ticket_id: str, db_path: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Retrieve a DSAR ticket by ID.

    Backwards-compatible wrapper that delegates to get_ticket().

    Args:
        ticket_id: Unique ticket identifier
        db_path: Optional database path override

    Returns:
        Dict containing ticket data in old format, or None if not found
    """
    ticket = get_ticket(ticket_id, db_path=db_path)
    if not ticket:
        return None

    # Transform to old format
    metadata = ticket.get("metadata", {})

    return {
        "ticket_id": ticket["ticket_id"],
        "request_type": metadata.get("legacy_request_type", ticket["sop"].replace("DSAR_", "").lower()),
        "email": ticket["email"],
        "user_identifier": ticket.get("user_identifier"),
        "details": metadata.get("legacy_details") or ticket.get("notes"),
        "urgent": ticket.get("priority", 5) >= 9,
        "status": _new_status_to_old(ticket["status"]),
        "submitted_at": ticket["submitted_at"],
        "estimated_completion": ticket.get("deadline"),
        "last_updated": ticket["last_updated"],
        "notes": ticket.get("notes"),
        "automated": ticket.get("automated", False),
        "access_package": metadata.get("access_package"),
        "export_package": metadata.get("export_package"),
        "created_at": ticket.get("created_at"),
    }


def update_dsar_ticket_status(
    ticket_id: str,
    new_status: str,
    notes: Optional[str] = None,
    db_path: Optional[str] = None,
) -> bool:
    """Update the status and notes of a DSAR ticket.

    Backwards-compatible wrapper that delegates to update_ticket_status().

    Args:
        ticket_id: Unique ticket identifier
        new_status: New status (pending_review|in_progress|completed|rejected)
        notes: Optional notes about the status update
        db_path: Optional database path override

    Returns:
        True if update was successful, False otherwise
    """
    mapped_status = _old_status_to_new(new_status)
    return update_ticket_status(
        ticket_id=ticket_id,
        new_status=mapped_status,
        notes=notes,
        db_path=db_path,
    )


def list_dsar_tickets_by_status(
    status: Optional[str] = None,
    db_path: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """List DSAR tickets, optionally filtered by status.

    Backwards-compatible wrapper that delegates to list_tickets().

    Args:
        status: Optional status filter (pending_review|in_progress|completed|rejected)
        db_path: Optional database path override

    Returns:
        List of ticket dicts in old format, sorted by submission date (newest first)
    """
    # Map old status to new if provided
    new_status = _old_status_to_new(status) if status else None

    # Get tickets from new API
    tickets = list_tickets(
        ticket_type="dsar",
        status=new_status,
        db_path=db_path,
    )

    # Transform each ticket to old format
    return [_transform_ticket_to_old_format(t) for t in tickets]


def list_dsar_tickets_by_email(
    email: str,
    db_path: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """List DSAR tickets for a specific email address.

    Backwards-compatible wrapper that delegates to list_tickets().

    Args:
        email: Email address to search for
        db_path: Optional database path override

    Returns:
        List of ticket dicts in old format, sorted by submission date (newest first)
    """
    tickets = list_tickets(
        ticket_type="dsar",
        email=email,
        db_path=db_path,
    )

    return [_transform_ticket_to_old_format(t) for t in tickets]


def _transform_ticket_to_old_format(ticket: Dict[str, Any]) -> Dict[str, Any]:
    """Transform a ticket from new format to old DSAR format."""
    metadata = ticket.get("metadata", {})

    return {
        "ticket_id": ticket["ticket_id"],
        "request_type": metadata.get("legacy_request_type", ticket["sop"].replace("DSAR_", "").lower()),
        "email": ticket["email"],
        "user_identifier": ticket.get("user_identifier"),
        "details": metadata.get("legacy_details") or ticket.get("notes"),
        "urgent": ticket.get("priority", 5) >= 9,
        "status": _new_status_to_old(ticket["status"]),
        "submitted_at": ticket["submitted_at"],
        "estimated_completion": ticket.get("deadline"),
        "last_updated": ticket["last_updated"],
        "notes": ticket.get("notes"),
        "automated": ticket.get("automated", False),
        "access_package": metadata.get("access_package"),
        "export_package": metadata.get("export_package"),
        "created_at": ticket.get("created_at"),
    }


def _row_to_dict(row: Any) -> Dict[str, Any]:
    """Deprecated - kept for backwards compatibility.

    This function is no longer used as the module now delegates to tickets.py.
    """
    raise NotImplementedError(
        "This function is deprecated. Use get_dsar_ticket() instead, which delegates to the new tickets API."
    )
