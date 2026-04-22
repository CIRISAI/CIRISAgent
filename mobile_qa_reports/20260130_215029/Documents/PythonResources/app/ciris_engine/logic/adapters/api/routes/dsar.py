"""
Data Subject Access Request (DSAR) endpoint for GDPR/privacy compliance.
Handles data access, deletion, and export requests.

INTEGRATED WITH CONSENSUAL EVOLUTION PROTOCOL v0.2:
- Delete requests trigger decay protocol (90-day anonymization)
- Access requests include consent status
- Export includes consent history
"""

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from ciris_engine.logic.persistence.models.dsar import (
    create_dsar_ticket,
    get_dsar_ticket,
    list_dsar_tickets_by_email,
    list_dsar_tickets_by_status,
    update_dsar_ticket_status,
)
from ciris_engine.logic.services.governance.consent import ConsentNotFoundError, ConsentService
from ciris_engine.logic.services.governance.consent.dsar_automation import DSARAutomationService
from ciris_engine.schemas.consent.core import (
    ConsentDecayStatus,
    ConsentStream,
    DSARAccessPackage,
    DSARExportFormat,
    DSARExportPackage,
)

from ..auth import get_current_user
from ..models import StandardResponse, TokenData

router = APIRouter(prefix="/dsar", tags=["DSAR"])


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


def _initialize_services(req: Request) -> tuple[ConsentService, DSARAutomationService]:
    """Initialize consent and DSAR automation services.

    Args:
        req: FastAPI request object

    Returns:
        Tuple of (consent_manager, dsar_automation)
    """
    from ciris_engine.logic.services.lifecycle.time.service import TimeService

    # Get or create consent manager
    if hasattr(req.app.state, "consent_manager") and req.app.state.consent_manager:
        consent_manager = req.app.state.consent_manager
    else:
        time_service = TimeService()
        consent_manager = ConsentService(time_service=time_service)

    # Get or create DSAR automation service
    if hasattr(req.app.state, "dsar_automation") and req.app.state.dsar_automation:
        dsar_automation = req.app.state.dsar_automation
    else:
        time_service = TimeService()
        memory_bus = getattr(req.app.state, "memory_bus", None)
        dsar_automation = DSARAutomationService(
            time_service=time_service, consent_service=consent_manager, memory_bus=memory_bus
        )

    return consent_manager, dsar_automation


async def _handle_access_request(
    dsar_automation: DSARAutomationService, user_identifier: str, ticket_id: str
) -> Optional[DSARAccessPackage]:
    """Handle automated access request.

    Args:
        dsar_automation: DSAR automation service
        user_identifier: User ID
        ticket_id: Request ticket ID

    Returns:
        Access package or None if failed
    """
    import logging

    logger = logging.getLogger(__name__)

    try:
        # Use automation service for instant response
        access_package = await dsar_automation.handle_access_request(user_id=user_identifier, request_id=ticket_id)
        logger.info(f"DSAR access request {ticket_id} completed instantly via automation")
        return access_package
    except ConsentNotFoundError:
        logger.info(f"DSAR access request {ticket_id} for user with no consent record")
        return None
    except Exception as e:
        logger.warning(f"Could not automate access request {ticket_id}: {e}")
        return None


async def _handle_export_request(
    dsar_automation: DSARAutomationService, user_identifier: str, ticket_id: str
) -> Optional[DSARExportPackage]:
    """Handle automated export request.

    Args:
        dsar_automation: DSAR automation service
        user_identifier: User ID
        ticket_id: Request ticket ID

    Returns:
        Export package or None if failed
    """
    import logging

    logger = logging.getLogger(__name__)
    export_format = DSARExportFormat.JSON

    try:
        # Use automation service for instant export
        export_package = await dsar_automation.handle_export_request(
            user_id=user_identifier, export_format=export_format, request_id=ticket_id
        )
        logger.info(f"DSAR export request {ticket_id} completed instantly via automation ({export_format})")
        return export_package
    except ConsentNotFoundError:
        logger.info(f"DSAR export request {ticket_id} for user with no consent record")
        return None
    except Exception as e:
        logger.warning(f"Could not automate export request {ticket_id}: {e}")
        return None


async def _handle_delete_request(
    consent_manager: ConsentService, user_identifier: str, ticket_id: str
) -> Optional[ConsentDecayStatus]:
    """Handle delete request via decay protocol.

    Args:
        consent_manager: Consent service
        user_identifier: User ID
        ticket_id: Request ticket ID

    Returns:
        Decay status or None if failed
    """
    import logging

    logger = logging.getLogger(__name__)

    try:
        # Start decay protocol
        decay_status = await consent_manager.revoke_consent(
            user_id=user_identifier, reason=f"DSAR deletion request {ticket_id}"
        )

        # Use structured logging to avoid log injection
        logger.info("Decay protocol initiated via DSAR", extra={"user_id": user_identifier, "ticket_id": ticket_id})
        return decay_status
    except ConsentNotFoundError:
        # User has no consent record - that's fine for DSAR
        return None
    except Exception as e:
        logger.warning(f"Could not initiate decay protocol for DSAR {ticket_id}: {e}")
        return None


def _calculate_estimated_completion(is_automated: bool, urgent: bool, submitted_at: datetime) -> datetime:
    """Calculate estimated completion time for DSAR request.

    Args:
        is_automated: Whether the request is automated (access/export)
        urgent: Whether the request is marked urgent
        submitted_at: When the request was submitted

    Returns:
        Estimated completion datetime
    """
    from datetime import timedelta

    if is_automated:
        return submitted_at

    days_to_complete = 3 if urgent else 14
    return submitted_at + timedelta(days=days_to_complete)


def _build_response_message(
    request_type: str,
    urgent: bool,
    contact_email: str,
    access_package: Optional[DSARAccessPackage],
    export_package: Optional[DSARExportPackage],
    decay_status: Optional[ConsentDecayStatus],
) -> str:
    """Build response message based on request type and results.

    Args:
        request_type: Type of request (access/export/delete/correct)
        urgent: Whether request is urgent
        contact_email: Contact email
        access_package: Access package if available
        export_package: Export package if available
        decay_status: Decay status if available

    Returns:
        Response message string
    """
    message = f"Your {request_type} request has been received. "

    if request_type == "access" and access_package:
        message += (
            "Your data has been compiled instantly and is included in this response. "
            "The package includes your consent status, audit history, interactions, and contributions."
        )
    elif request_type == "export" and export_package:
        message += (
            f"Your data export ({export_package.export_format}) has been generated instantly. "
            f"File size: {export_package.file_size_bytes} bytes. "
            f"Checksum: {export_package.checksum[:16]}... "
            "The export is included in this response."
        )
    elif request_type == "delete" and decay_status:
        message += (
            "Decay protocol initiated: identity severed immediately, "
            f"patterns will be anonymized over 90 days (complete by {decay_status.decay_complete_at.strftime('%Y-%m-%d')}). "
        )
    else:
        # Manual processing for non-automated requests
        timeline = "3 days" if urgent else "14 days"
        message += (
            f"We will process your request within {timeline} "
            f"during the pilot phase. You will receive updates at {contact_email}."
        )

    return message


@router.post("/", response_model=StandardResponse)
async def submit_dsar(
    request: DSARRequest,
    req: Request,
) -> StandardResponse:
    """
    Submit a Data Subject Access Request (DSAR).

    This endpoint handles GDPR Article 15-22 rights:
    - Right of access (Article 15) - INSTANT automated response with full data
    - Right to rectification (Article 16)
    - Right to erasure / "right to be forgotten" (Article 17) - Triggers decay protocol
    - Right to data portability (Article 20) - INSTANT automated export

    DELETE requests trigger Consensual Evolution Protocol:
    - Immediate identity severance
    - 90-day pattern decay
    - Safety patterns may be retained (anonymized)

    ACCESS and EXPORT requests use automated DSAR service for instant responses.

    Returns a ticket ID for tracking the request.
    """
    # Generate unique ticket ID
    ticket_id = f"DSAR-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{uuid.uuid4().hex[:8].upper()}"

    # Calculate timestamps and metadata
    submitted_at = datetime.now(timezone.utc)
    is_automated = request.request_type in ["access", "export"]
    estimated_completion = _calculate_estimated_completion(is_automated, request.urgent, submitted_at)

    # Initialize services
    consent_manager, dsar_automation = _initialize_services(req)

    # Handle requests based on type
    access_package = None
    export_package = None
    decay_status = None

    if request.request_type == "access" and request.user_identifier:
        access_package = await _handle_access_request(dsar_automation, request.user_identifier, ticket_id)
    elif request.request_type == "export" and request.user_identifier:
        export_package = await _handle_export_request(dsar_automation, request.user_identifier, ticket_id)
    elif request.request_type == "delete" and request.user_identifier:
        decay_status = await _handle_delete_request(consent_manager, request.user_identifier, ticket_id)

    # Store request (mark automated requests as completed instantly)
    request_status = "completed" if is_automated and (access_package or export_package) else "pending_review"

    # Store in database - CRITICAL: must succeed for GDPR compliance
    persistence_success = create_dsar_ticket(
        ticket_id=ticket_id,
        request_type=request.request_type,
        email=request.email,
        status=request_status,
        submitted_at=submitted_at,
        estimated_completion=estimated_completion,
        automated=is_automated,
        user_identifier=request.user_identifier,
        details=request.details,
        urgent=request.urgent,
        access_package=access_package.model_dump(mode="json") if access_package else None,
        export_package=export_package.model_dump(mode="json") if export_package else None,
    )

    # P1: Fail the request if persistence fails (GDPR tracking requirement)
    if not persistence_success:
        import logging

        from ciris_engine.logic.utils.log_sanitizer import sanitize_email, sanitize_for_log

        logger = logging.getLogger(__name__)
        # Sanitize user-controlled data before logging to prevent log injection
        safe_email = sanitize_email(request.email)
        safe_type = sanitize_for_log(request.request_type, max_length=50)
        logger.error(
            f"CRITICAL: Failed to persist DSAR ticket {ticket_id} - request_type={safe_type}, email={safe_email}"
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to persist DSAR request. Request was not recorded and cannot proceed.",
        )

    # Log for audit trail
    import logging

    from ciris_engine.logic.utils.log_sanitizer import sanitize_email, sanitize_for_log

    logger = logging.getLogger(__name__)
    # Sanitize user input before logging to prevent log injection
    safe_email = sanitize_email(request.email)
    safe_type = sanitize_for_log(request.request_type, max_length=50)
    logger.info(f"DSAR request submitted: {ticket_id} - Type: {safe_type} - Email: {safe_email}")

    # Build response message
    message = _build_response_message(
        request.request_type, request.urgent, request.email, access_package, export_package, decay_status
    )

    response_data = DSARResponse(
        ticket_id=ticket_id,
        status=request_status,
        estimated_completion=(
            estimated_completion.strftime("%Y-%m-%d %H:%M:%S")
            if is_automated
            else estimated_completion.strftime("%Y-%m-%d")
        ),
        contact_email=request.email,
        message=message,
    )

    # Build response with automation data
    response_dict = response_data.model_dump()
    if access_package:
        response_dict["access_package"] = access_package.model_dump()
    if export_package:
        response_dict["export_package"] = export_package.model_dump()

    return StandardResponse(
        success=True,
        data=response_dict,
        message="DSAR request completed" if request_status == "completed" else "DSAR request successfully submitted",
        metadata={
            "ticket_id": ticket_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "automated": is_automated,
            "instant_response": request_status == "completed",
        },
    )


@router.get("/{ticket_id}", response_model=StandardResponse)
async def check_dsar_status(ticket_id: str) -> StandardResponse:
    """
    Check the status of a DSAR request.

    Anyone with the ticket ID can check status (like a tracking number).
    """
    record = get_dsar_ticket(ticket_id)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"DSAR ticket {ticket_id} not found",
        )

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

    # Get pending and in-progress requests from database
    all_pending = []
    for status_filter in ["pending_review", "in_progress"]:
        tickets = list_dsar_tickets_by_status(status_filter)
        all_pending.extend(tickets)

    # Format for response
    pending_requests = [
        {
            "ticket_id": r["ticket_id"],
            "request_type": r["request_type"],
            "submitted_at": r["submitted_at"],
            "urgent": r["urgent"],
            "status": r["status"],
        }
        for r in all_pending
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

    # Check if ticket exists
    record = get_dsar_ticket(ticket_id)
    if not record:
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

    # Update the record in database
    update_dsar_ticket_status(ticket_id, new_status, notes)

    # Log the update
    import logging

    from ciris_engine.logic.utils.log_sanitizer import sanitize_for_log, sanitize_username

    logger = logging.getLogger(__name__)
    # Sanitize ALL user input before logging to prevent log injection
    safe_ticket_id = sanitize_for_log(ticket_id, max_length=100)  # Sanitize ticket_id too
    safe_username = sanitize_username(current_user.username)
    safe_status = sanitize_for_log(new_status, max_length=50)
    logger.info(f"DSAR {safe_ticket_id} status updated to {safe_status} by {safe_username}")

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


@router.get("/{ticket_id}/deletion-status", response_model=StandardResponse)
async def get_deletion_status(
    ticket_id: str,
    req: Request,
) -> StandardResponse:
    """
    Get deletion progress for a DSAR deletion request.

    This endpoint tracks the 90-day decay protocol progress for deletion requests.
    Anyone with the ticket ID can check status (like a tracking number).
    """
    # Verify ticket exists and is a deletion request
    record = get_dsar_ticket(ticket_id)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"DSAR ticket {ticket_id} not found",
        )

    if record["request_type"] != "delete":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Ticket {ticket_id} is not a deletion request (type: {record['request_type']})",
        )

    user_identifier = record.get("user_identifier")
    if not user_identifier:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Deletion request has no user identifier",
        )

    # Get consent manager
    from ciris_engine.logic.services.lifecycle.time.service import TimeService

    if hasattr(req.app.state, "consent_manager") and req.app.state.consent_manager:
        consent_manager = req.app.state.consent_manager
    else:
        # Create default instance if not initialized
        time_service = TimeService()
        consent_manager = ConsentService(time_service=time_service)

    # Initialize DSAR automation service
    if hasattr(req.app.state, "dsar_automation") and req.app.state.dsar_automation:
        dsar_automation = req.app.state.dsar_automation
    else:
        # Create instance with available services
        time_service = TimeService()
        memory_bus = getattr(req.app.state, "memory_bus", None)
        dsar_automation = DSARAutomationService(
            time_service=time_service, consent_service=consent_manager, memory_bus=memory_bus
        )

    # Get deletion status from automation service
    try:
        deletion_status = await dsar_automation.get_deletion_status(user_id=user_identifier, ticket_id=ticket_id)

        if not deletion_status:
            return StandardResponse(
                success=True,
                data={
                    "ticket_id": ticket_id,
                    "user_id": user_identifier,
                    "status": "no_active_decay",
                    "message": "No active decay protocol found for this user. Deletion may be complete or not yet started.",
                },
                message="No active deletion in progress",
                metadata={
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            )

        return StandardResponse(
            success=True,
            data=deletion_status.model_dump(),
            message=f"Deletion {deletion_status.completion_percentage:.1f}% complete - Phase: {deletion_status.current_phase}",
            metadata={
                "ticket_id": ticket_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )

    except Exception as e:
        import logging

        logger = logging.getLogger(__name__)
        logger.error(f"Error retrieving deletion status for {ticket_id}: {e}")

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Could not retrieve deletion status: {str(e)}",
        )
