"""Multi-source DSAR API endpoints.

Coordinates GDPR data subject requests across CIRIS + external data sources.
"""

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from ciris_engine.logic.persistence.models.dsar import create_dsar_ticket, get_dsar_ticket
from ciris_engine.logic.services.governance.consent import ConsentService
from ciris_engine.logic.services.governance.consent.dsar_automation import DSARAutomationService
from ciris_engine.logic.services.governance.dsar.orchestrator import DSAROrchestrator
from ciris_engine.logic.services.governance.dsar.schemas import (
    MultiSourceDSARAccessPackage,
    MultiSourceDSARCorrectionResult,
    MultiSourceDSARDeletionResult,
    MultiSourceDSARExportPackage,
)
from ciris_engine.schemas.consent.core import DSARExportFormat

from ..auth import get_current_user
from ..models import StandardResponse, TokenData

router = APIRouter(prefix="/dsar/multi-source", tags=["DSAR Multi-Source"])


class MultiSourceDSARRequest(BaseModel):
    """Request for multi-source DSAR operation."""

    request_type: str = Field(
        ...,
        description="Type of request: access, delete, export, or correct",
        pattern="^(access|delete|export|correct)$",
    )
    email: str = Field(..., description="Contact email for the request")
    user_identifier: str = Field(..., description="Primary user identifier (email, Discord ID, etc.)")
    export_format: Optional[str] = Field("json", description="Export format for export requests")
    corrections: Optional[Dict[str, Any]] = Field(None, description="Field corrections for correction requests")
    details: Optional[str] = Field(None, description="Additional details about the request")
    urgent: bool = Field(False, description="Whether this is an urgent request")


class MultiSourceDSARResponse(BaseModel):
    """Response for multi-source DSAR submission."""

    ticket_id: str = Field(..., description="Unique ticket ID for tracking")
    request_id: str = Field(..., description="Internal request ID")
    status: str = Field(..., description="Current status of the request")
    total_sources: int = Field(..., description="Total number of sources queried")
    estimated_completion: str = Field(..., description="Estimated completion time")
    contact_email: str = Field(..., description="Email for updates")
    message: str = Field(..., description="Confirmation message")


class MultiSourceDSARStatusResponse(BaseModel):
    """Status response for multi-source DSAR request."""

    ticket_id: str
    request_id: str
    status: str
    request_type: str
    total_sources: int
    sources_completed: int
    sources_failed: int
    submitted_at: str
    last_updated: str
    processing_time_seconds: float
    notes: Optional[str] = None


class PartialResultsResponse(BaseModel):
    """Partial results as sources complete."""

    ticket_id: str
    request_id: str
    sources_completed: int
    sources_remaining: int
    partial_data: Dict[str, Any]
    is_complete: bool


class CancellationResponse(BaseModel):
    """Response for cancellation request."""

    ticket_id: str
    cancelled: bool
    message: str


def _initialize_orchestrator(req: Request) -> DSAROrchestrator:
    """Initialize DSAR orchestrator with all dependencies.

    Args:
        req: FastAPI request object

    Returns:
        DSAROrchestrator instance
    """
    from ciris_engine.logic.services.lifecycle.time.service import TimeService

    # Get or create services
    time_service = TimeService()

    # Get or create consent service
    if hasattr(req.app.state, "consent_manager") and req.app.state.consent_manager:
        consent_service = req.app.state.consent_manager
    else:
        consent_service = ConsentService(time_service=time_service)

    # Get or create DSAR automation service
    if hasattr(req.app.state, "dsar_automation") and req.app.state.dsar_automation:
        dsar_automation = req.app.state.dsar_automation
    else:
        memory_bus = getattr(req.app.state, "memory_bus", None)
        dsar_automation = DSARAutomationService(
            time_service=time_service, consent_service=consent_service, memory_bus=memory_bus
        )

    # Get tool bus and memory bus
    tool_bus = getattr(req.app.state, "tool_bus", None)
    if not tool_bus:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Tool bus not available - multi-source DSAR requires tool bus",
        )

    memory_bus = getattr(req.app.state, "memory_bus", None)
    if not memory_bus:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Memory bus not available - multi-source DSAR requires memory bus",
        )

    # Create orchestrator with consent service
    return DSAROrchestrator(
        time_service=time_service,
        dsar_automation=dsar_automation,
        consent_service=consent_service,
        tool_bus=tool_bus,
        memory_bus=memory_bus,
    )


# Register both slash and non-slash variants to support clients with and without
# redirect handling. The non-slash variant is the canonical route.
@router.post("", response_model=StandardResponse)
@router.post("/", response_model=StandardResponse)
async def submit_multi_source_dsar(
    request: MultiSourceDSARRequest,
    req: Request,
    current_user: TokenData = Depends(get_current_user),
) -> StandardResponse:
    """
    Submit a multi-source Data Subject Access Request (DSAR).

    Coordinates GDPR requests across CIRIS + all registered external data sources:
    - SQL databases
    - REST APIs
    - HL7 systems (future)

    Requires authentication (admin or authorized user).

    Returns aggregated results from all sources.
    """
    import logging

    from ciris_engine.logic.utils.log_sanitizer import sanitize_email, sanitize_for_log

    logger = logging.getLogger(__name__)

    # Generate ticket ID and request ID
    ticket_id = f"MDSAR-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{uuid.uuid4().hex[:8].upper()}"
    request_id = f"REQ-{uuid.uuid4().hex[:12].upper()}"

    # Initialize orchestrator
    try:
        orchestrator = _initialize_orchestrator(req)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to initialize DSAR orchestrator: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not initialize multi-source DSAR orchestrator",
        )

    # Validate request before processing
    if request.request_type == "correct" and not request.corrections:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Corrections field is required for correction requests",
        )

    # Process request based on type
    result_package: Optional[
        MultiSourceDSARAccessPackage
        | MultiSourceDSARExportPackage
        | MultiSourceDSARDeletionResult
        | MultiSourceDSARCorrectionResult
    ] = None
    total_sources = 0
    processing_time = 0.0

    try:
        if request.request_type == "access":
            access_result = await orchestrator.handle_access_request_multi_source(
                user_identifier=request.user_identifier, request_id=request_id
            )
            result_package = access_result
            total_sources = access_result.total_sources
            processing_time = access_result.processing_time_seconds

        elif request.request_type == "export":
            export_format = DSARExportFormat(request.export_format or "json")
            export_result = await orchestrator.handle_export_request_multi_source(
                user_identifier=request.user_identifier, export_format=export_format, request_id=request_id
            )
            result_package = export_result
            total_sources = export_result.total_sources
            processing_time = export_result.processing_time_seconds

        elif request.request_type == "delete":
            deletion_result = await orchestrator.handle_deletion_request_multi_source(
                user_identifier=request.user_identifier, request_id=request_id
            )
            result_package = deletion_result
            total_sources = deletion_result.total_sources
            processing_time = deletion_result.processing_time_seconds

        elif request.request_type == "correct":
            if request.corrections is None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Corrections field cannot be None",
                )
            correction_result = await orchestrator.handle_correction_request_multi_source(
                user_identifier=request.user_identifier, corrections=request.corrections, request_id=request_id
            )
            result_package = correction_result
            total_sources = correction_result.total_sources
            processing_time = correction_result.processing_time_seconds

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Multi-source DSAR request failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Multi-source DSAR request failed: {str(e)}",
        )

    # Store request (mark as completed since orchestration is instant)
    submitted_at = datetime.now(timezone.utc)
    estimated_completion = submitted_at  # Instant for multi-source

    persistence_success = create_dsar_ticket(
        ticket_id=ticket_id,
        request_type=request.request_type,
        email=request.email,
        status="completed",
        submitted_at=submitted_at,
        estimated_completion=estimated_completion,
        automated=True,
        user_identifier=request.user_identifier,
        details=request.details,
        urgent=request.urgent,
        access_package=result_package.model_dump(mode="json") if result_package else None,
        export_package=None,  # Multi-source packages stored in access_package field
    )

    if not persistence_success:
        from ciris_engine.logic.utils.log_sanitizer import sanitize_email, sanitize_for_log

        safe_email = sanitize_email(request.email)
        safe_type = sanitize_for_log(request.request_type, max_length=50)
        logger.error(
            f"CRITICAL: Failed to persist multi-source DSAR ticket {ticket_id} - "
            f"request_type={safe_type}, email={safe_email}"
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to persist DSAR request. Request was not recorded and cannot proceed.",
        )

    # Log for audit trail
    safe_email = sanitize_email(request.email)
    safe_type = sanitize_for_log(request.request_type, max_length=50)
    logger.info(
        f"Multi-source DSAR submitted: {ticket_id} - Type: {safe_type} - "
        f"Email: {safe_email} - Sources: {total_sources} - Time: {processing_time:.2f}s"
    )

    # Build response
    message = (
        f"Your multi-source {request.request_type} request has been completed. "
        f"Data retrieved from {total_sources} source(s) in {processing_time:.2f} seconds. "
        f"Results are included in this response."
    )

    response_data = MultiSourceDSARResponse(
        ticket_id=ticket_id,
        request_id=request_id,
        status="completed",
        total_sources=total_sources,
        estimated_completion=estimated_completion.strftime("%Y-%m-%d %H:%M:%S"),
        contact_email=request.email,
        message=message,
    )

    # Build response with package data
    response_dict = response_data.model_dump()
    if result_package:
        response_dict["data_package"] = result_package.model_dump()

    return StandardResponse(
        success=True,
        data=response_dict,
        message=f"Multi-source DSAR request completed - {total_sources} source(s) queried",
        metadata={
            "ticket_id": ticket_id,
            "request_id": request_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "automated": True,
            "multi_source": True,
            "total_sources": total_sources,
            "processing_time_seconds": processing_time,
        },
    )


@router.get("/{ticket_id}", response_model=StandardResponse)
async def get_multi_source_status(
    ticket_id: str,
    current_user: TokenData = Depends(get_current_user),
) -> StandardResponse:
    """
    Get real-time status of multi-source DSAR request.

    Returns current progress across all data sources.
    """
    record = get_dsar_ticket(ticket_id)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Multi-source DSAR ticket {ticket_id} not found",
        )

    # Extract package data if available
    package_data = record.get("access_package")
    total_sources = 0
    sources_completed = 0
    sources_failed = 0
    processing_time = 0.0

    if package_data:
        total_sources = package_data.get("total_sources", 0)
        # For now, completed means all sources (instant orchestration)
        sources_completed = total_sources
        processing_time = package_data.get("processing_time_seconds", 0.0)

    status_data = MultiSourceDSARStatusResponse(
        ticket_id=ticket_id,
        request_id=package_data.get("request_id", "UNKNOWN") if package_data else "UNKNOWN",
        status=record["status"],
        request_type=record["request_type"],
        total_sources=total_sources,
        sources_completed=sources_completed,
        sources_failed=sources_failed,
        submitted_at=record["submitted_at"],
        last_updated=record["last_updated"],
        processing_time_seconds=processing_time,
        notes=record.get("notes"),
    )

    return StandardResponse(
        success=True,
        data=status_data.model_dump(),
        message=f"Multi-source DSAR status: {sources_completed}/{total_sources} sources completed",
        metadata={
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )


@router.get("/{ticket_id}/partial", response_model=StandardResponse)
async def get_partial_results(
    ticket_id: str,
    current_user: TokenData = Depends(get_current_user),
) -> StandardResponse:
    """
    Get partial results as sources complete.

    Returns data from completed sources while others are still processing.

    Note: Current implementation completes all sources instantly,
    but this endpoint supports future async multi-source operations.
    """
    record = get_dsar_ticket(ticket_id)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Multi-source DSAR ticket {ticket_id} not found",
        )

    # Extract package data
    package_data = record.get("access_package", {})
    total_sources = package_data.get("total_sources", 0)

    # For instant orchestration, all sources are complete
    is_complete = record["status"] == "completed"
    sources_completed = total_sources if is_complete else 0

    partial_response = PartialResultsResponse(
        ticket_id=ticket_id,
        request_id=package_data.get("request_id", "UNKNOWN"),
        sources_completed=sources_completed,
        sources_remaining=total_sources - sources_completed,
        partial_data=package_data,
        is_complete=is_complete,
    )

    return StandardResponse(
        success=True,
        data=partial_response.model_dump(),
        message=f"Partial results: {sources_completed}/{total_sources} sources complete",
        metadata={
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )


@router.delete("/{ticket_id}", response_model=StandardResponse)
async def cancel_multi_source_request(
    ticket_id: str,
    current_user: TokenData = Depends(get_current_user),
) -> StandardResponse:
    """
    Cancel in-progress multi-source DSAR request.

    Note: Current implementation completes requests instantly,
    so cancellation may not be possible for most requests.
    """
    record = get_dsar_ticket(ticket_id)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Multi-source DSAR ticket {ticket_id} not found",
        )

    if record["status"] == "completed":
        return StandardResponse(
            success=False,
            data=CancellationResponse(
                ticket_id=ticket_id,
                cancelled=False,
                message="Request already completed - cannot cancel",
            ).model_dump(),
            message="Request already completed",
            metadata={
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )

    # Update status to cancelled
    from ciris_engine.logic.persistence.models.dsar import update_dsar_ticket_status

    update_dsar_ticket_status(ticket_id, "cancelled", "Cancelled by user request")

    return StandardResponse(
        success=True,
        data=CancellationResponse(
            ticket_id=ticket_id,
            cancelled=True,
            message="Multi-source DSAR request cancelled successfully",
        ).model_dump(),
        message="Request cancelled",
        metadata={
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )
