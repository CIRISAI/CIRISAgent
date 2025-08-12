"""
Data Subject Access Request (DSAR) endpoint for GDPR/privacy compliance.
Handles data access, deletion, and export requests.
"""

import json
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from ..auth import get_current_user
from ..models import StandardResponse, TokenData

router = APIRouter(prefix="/dsr", tags=["DSAR"])


class DSARRequest(BaseModel):
    """Schema for Data Subject Access Request."""

    request_type: str = Field(
        ...,
        description="Type of request: access, delete, export, or correct",
        pattern="^(access|delete|export|correct)$",
    )
    email: str = Field(..., description="Contact email for the request")
    user_identifier: Optional[str] = Field(None, description="Discord ID, username, or other identifier")
    details: Optional[str] = Field(None, description="Additional details about the request")
    urgent: bool = Field(False, description="Whether this is an urgent request")


class DSARResponse(BaseModel):
    """Response for DSAR submission."""

    ticket_id: str = Field(..., description="Unique ticket ID for tracking")
    status: str = Field(..., description="Current status of the request")
    estimated_completion: str = Field(..., description="Estimated completion date (30 days max)")
    contact_email: str = Field(..., description="Email for updates")
    message: str = Field(..., description="Confirmation message")


class DSARStatus(BaseModel):
    """Status check for existing DSAR."""

    ticket_id: str
    status: str
    submitted_at: str
    request_type: str
    last_updated: str
    notes: Optional[str] = None


# In-memory storage for pilot (replace with database in production)
_dsar_requests = {}


@router.post("/", response_model=StandardResponse)
async def submit_dsar(
    request: DSARRequest,
) -> StandardResponse:
    """
    Submit a Data Subject Access Request (DSAR).

    This endpoint handles GDPR Article 15-22 rights:
    - Right of access (Article 15)
    - Right to rectification (Article 16)
    - Right to erasure / "right to be forgotten" (Article 17)
    - Right to data portability (Article 20)

    Returns a ticket ID for tracking the request.
    """
    # Generate unique ticket ID
    ticket_id = f"DSAR-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{uuid.uuid4().hex[:8].upper()}"

    # Calculate estimated completion (14 days for pilot, urgent in 3 days)
    from datetime import timedelta

    submitted_at = datetime.now(timezone.utc)
    estimated_completion = submitted_at + timedelta(days=14 if not request.urgent else 3)

    # Store request (in production, this would go to a database)
    dsar_record = {
        "ticket_id": ticket_id,
        "request_type": request.request_type,
        "email": request.email,
        "user_identifier": request.user_identifier,
        "details": request.details,
        "urgent": request.urgent,
        "status": "pending_review",
        "submitted_at": submitted_at.isoformat(),
        "estimated_completion": estimated_completion.isoformat(),
        "last_updated": submitted_at.isoformat(),
        "notes": None,
    }

    _dsar_requests[ticket_id] = dsar_record

    # Log for audit trail
    import logging

    from ciris_engine.logic.utils.log_sanitizer import sanitize_email, sanitize_for_log

    logger = logging.getLogger(__name__)
    # Sanitize user input before logging to prevent log injection
    safe_email = sanitize_email(request.email)
    safe_type = sanitize_for_log(request.request_type, max_length=50)
    logger.info(f"DSAR request submitted: {ticket_id} - Type: {safe_type} - Email: {safe_email}")

    # Prepare response
    response_data = DSARResponse(
        ticket_id=ticket_id,
        status="pending_review",
        estimated_completion=estimated_completion.strftime("%Y-%m-%d"),
        contact_email=request.email,
        message=f"Your {request.request_type} request has been received. "
        f"We will process it within {'3 days' if request.urgent else '14 days'} "
        f"during the pilot phase. You will receive updates at {request.email}.",
    )

    return StandardResponse(
        success=True,
        data=response_data.model_dump(),
        message="DSAR request successfully submitted",
        metadata={
            "ticket_id": ticket_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )


@router.get("/{ticket_id}", response_model=StandardResponse)
async def check_dsar_status(ticket_id: str) -> StandardResponse:
    """
    Check the status of a DSAR request.

    Anyone with the ticket ID can check status (like a tracking number).
    """
    if ticket_id not in _dsar_requests:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"DSAR ticket {ticket_id} not found",
        )

    record = _dsar_requests[ticket_id]

    status_data = DSARStatus(
        ticket_id=ticket_id,
        status=record["status"],
        submitted_at=record["submitted_at"],
        request_type=record["request_type"],
        last_updated=record["last_updated"],
        notes=record.get("notes"),
    )

    return StandardResponse(
        success=True,
        data=status_data.model_dump(),
        message="DSAR status retrieved",
        metadata={
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )


@router.get("/", response_model=StandardResponse)
async def list_dsar_requests(
    current_user: TokenData = Depends(get_current_user),
) -> StandardResponse:
    """
    List all DSAR requests (admin only).

    This endpoint is for administrators to review pending requests.
    """
    if current_user.role not in ["ADMIN", "SYSTEM_ADMIN"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only administrators can list DSAR requests",
        )

    # Filter to show only pending requests
    pending_requests = [
        {
            "ticket_id": r["ticket_id"],
            "request_type": r["request_type"],
            "submitted_at": r["submitted_at"],
            "urgent": r["urgent"],
            "status": r["status"],
        }
        for r in _dsar_requests.values()
        if r["status"] in ["pending_review", "in_progress"]
    ]

    return StandardResponse(
        success=True,
        data={"requests": pending_requests, "total": len(pending_requests)},
        message=f"Found {len(pending_requests)} pending DSAR requests",
        metadata={
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )


@router.put("/{ticket_id}/status", response_model=StandardResponse)
async def update_dsar_status(
    ticket_id: str,
    new_status: str,
    notes: Optional[str] = None,
    current_user: TokenData = Depends(get_current_user),
) -> StandardResponse:
    """
    Update the status of a DSAR request (admin only).

    Status workflow:
    - pending_review → in_progress → completed/rejected
    """
    if current_user.role not in ["ADMIN", "SYSTEM_ADMIN"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only administrators can update DSAR status",
        )

    if ticket_id not in _dsar_requests:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"DSAR ticket {ticket_id} not found",
        )

    valid_statuses = ["pending_review", "in_progress", "completed", "rejected"]
    if new_status not in valid_statuses:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid status. Must be one of: {valid_statuses}",
        )

    # Update the record
    _dsar_requests[ticket_id]["status"] = new_status
    _dsar_requests[ticket_id]["last_updated"] = datetime.now(timezone.utc).isoformat()
    if notes:
        _dsar_requests[ticket_id]["notes"] = notes

    # Log the update
    import logging

    from ciris_engine.logic.utils.log_sanitizer import sanitize_for_log, sanitize_username

    logger = logging.getLogger(__name__)
    # Sanitize user input before logging to prevent log injection
    safe_username = sanitize_username(current_user.username)
    safe_status = sanitize_for_log(new_status, max_length=50)
    logger.info(f"DSAR {ticket_id} status updated to {safe_status} by {safe_username}")

    return StandardResponse(
        success=True,
        data={
            "ticket_id": ticket_id,
            "new_status": new_status,
            "updated_by": current_user.username,
        },
        message=f"DSAR {ticket_id} status updated to {new_status}",
        metadata={
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )
