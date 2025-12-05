"""
Universal Ticket System API Routes

Provides CRUD operations for the universal ticket system with SOP enforcement.
DSAR tickets are always available (GDPR compliance), agents can define custom ticket types.

Architecture:
- SOPs defined in agent templates
- Organic enforcement: only create tickets with supported SOPs
- Stage-based workflow tracking via metadata
- Task generation by WorkProcessor for incomplete tickets
"""

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from ciris_engine.logic.persistence.models.tickets import (
    create_ticket,
    delete_ticket,
    get_ticket,
    list_tickets,
    update_ticket_metadata,
    update_ticket_status,
)
from ciris_engine.schemas.config.tickets import TicketsConfig, TicketSOPConfig

from ..auth import get_current_user
from ..models import StandardResponse, TokenData

router = APIRouter(prefix="/tickets", tags=["Tickets"])


# ============================================================================
# Request/Response Models
# ============================================================================


class CreateTicketRequest(BaseModel):
    """Request to create a new ticket."""

    sop: str = Field(..., description="Standard Operating Procedure (e.g., 'DSAR_ACCESS')")
    email: str = Field(..., description="Contact email for the ticket")
    user_identifier: Optional[str] = Field(None, description="User identifier for data lookup")
    priority: Optional[int] = Field(None, ge=1, le=10, description="Priority 1-10 (defaults to SOP default)")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Additional metadata for the ticket")
    notes: Optional[str] = Field(None, description="Optional notes about the ticket")


class TicketResponse(BaseModel):
    """Response containing ticket data."""

    ticket_id: str
    sop: str
    ticket_type: str
    status: str
    priority: int
    email: str
    user_identifier: Optional[str]
    submitted_at: str
    deadline: Optional[str]
    last_updated: str
    completed_at: Optional[str]
    metadata: Dict[str, Any]
    notes: Optional[str]
    automated: bool
    correlation_id: Optional[str]
    agent_occurrence_id: str  # Which occurrence is handling this ticket


class UpdateTicketRequest(BaseModel):
    """Request to update ticket status or metadata."""

    status: Optional[str] = Field(None, description="New status (pending|in_progress|completed|cancelled|failed)")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Updated metadata")
    notes: Optional[str] = Field(None, description="Updated notes")


class SOPMetadataResponse(BaseModel):
    """Metadata about a Standard Operating Procedure."""

    sop: str
    ticket_type: str
    required_fields: List[str]
    deadline_days: Optional[int]
    priority_default: int
    description: Optional[str]
    stages: List[Dict[str, Any]]


# ============================================================================
# Helper Functions
# ============================================================================


async def _get_agent_tickets_config(req: Request) -> Optional[TicketsConfig]:
    """Get agent tickets configuration from the graph.

    Returns:
        TicketsConfig from graph, or None if not available
    """
    # Get config service from app state
    config_service = getattr(req.app.state, "config_service", None)
    if not config_service:
        return None

    # Get tickets config from graph (stored during first-run seeding)
    try:
        config_node = await config_service.get_config("tickets")
        if config_node and config_node.value and config_node.value.dict_value:
            return TicketsConfig(**config_node.value.dict_value)
    except Exception:
        pass

    return None


async def _get_sop_config(req: Request, sop_name: str) -> Optional[TicketSOPConfig]:
    """Get SOP configuration from graph.

    Args:
        req: FastAPI request
        sop_name: SOP identifier (e.g., "DSAR_ACCESS")

    Returns:
        TicketSOPConfig if found, None otherwise
    """
    tickets_config = await _get_agent_tickets_config(req)
    if not tickets_config:
        return None

    return tickets_config.get_sop(sop_name)


async def _is_sop_supported(req: Request, sop_name: str) -> bool:
    """Check if an SOP is supported by this agent.

    Args:
        req: FastAPI request
        sop_name: SOP identifier

    Returns:
        True if SOP is supported, False otherwise
    """
    tickets_config = await _get_agent_tickets_config(req)
    if not tickets_config:
        return False

    return tickets_config.is_sop_supported(sop_name)


def _initialize_ticket_metadata(sop_config: TicketSOPConfig) -> Dict[str, Any]:
    """Initialize metadata structure for a new ticket based on SOP stages.

    Args:
        sop_config: SOP configuration from agent template

    Returns:
        Initial metadata dict with empty stage statuses
    """
    stages_status = {}
    for stage in sop_config.stages:
        stages_status[stage.name] = {
            "status": "pending",
            "started_at": None,
            "completed_at": None,
            "result": None,
            "error": None,
        }

    return {
        "stages": stages_status,
        "current_stage": sop_config.stages[0].name if sop_config.stages else None,
        "sop_version": "1.0",  # Track SOP version for migration support
    }


# ============================================================================
# API Endpoints
# ============================================================================


@router.get("/sops", response_model=List[str])
async def list_supported_sops(
    req: Request,
    current_user: TokenData = Depends(get_current_user),
) -> List[str]:
    """List all supported Standard Operating Procedures for this agent.

    DSAR SOPs are always present (GDPR compliance).
    Additional SOPs defined in graph config (seeded from template on first run).

    Returns:
        List of SOP identifiers (e.g., ["DSAR_ACCESS", "DSAR_DELETE", ...])
    """
    tickets_config = await _get_agent_tickets_config(req)
    if not tickets_config:
        # Should never happen - DSAR SOPs always present
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Tickets configuration not available",
        )

    return tickets_config.list_sops()


@router.get("/sops/{sop}", response_model=SOPMetadataResponse)
async def get_sop_metadata(
    sop: str,
    req: Request,
    current_user: TokenData = Depends(get_current_user),
) -> SOPMetadataResponse:
    """Get metadata about a specific Standard Operating Procedure.

    Returns:
        SOP configuration including stages, required fields, deadline, etc.

    Raises:
        404: SOP not found/supported
    """
    sop_config = await _get_sop_config(req, sop)
    if not sop_config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"SOP '{sop}' not supported by this agent",
        )

    return SOPMetadataResponse(
        sop=sop_config.sop,
        ticket_type=sop_config.ticket_type,
        required_fields=sop_config.required_fields,
        deadline_days=sop_config.deadline_days,
        priority_default=sop_config.priority_default,
        description=sop_config.description,
        stages=[
            {
                "name": stage.name,
                "tools": stage.tools,
                "optional": stage.optional,
                "parallel": stage.parallel,
                "description": stage.description,
            }
            for stage in sop_config.stages
        ],
    )


@router.post("/", response_model=TicketResponse, status_code=status.HTTP_201_CREATED)
async def create_new_ticket(
    request: CreateTicketRequest,
    req: Request,
    current_user: TokenData = Depends(get_current_user),
) -> TicketResponse:
    """Create a new ticket.

    Validates that the SOP is supported by this agent (organic enforcement).
    Automatically calculates deadline based on SOP configuration.
    Initializes metadata with stage structure.

    Returns:
        Created ticket data

    Raises:
        501: SOP not supported by this agent
        500: Ticket creation failed
    """
    # Validate SOP is supported (organic enforcement)
    if not await _is_sop_supported(req, request.sop):
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail=f"SOP '{request.sop}' not supported by this agent",
        )

    # Get SOP configuration
    sop_config = await _get_sop_config(req, request.sop)
    if not sop_config:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to load SOP configuration",
        )

    # Generate ticket ID
    ticket_id = f"{sop_config.ticket_type.upper()}-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"

    # Calculate deadline
    submitted_at = datetime.now(timezone.utc)
    deadline = None
    if sop_config.deadline_days:
        deadline = submitted_at + timedelta(days=sop_config.deadline_days)

    # Initialize metadata with stage structure
    initial_metadata = _initialize_ticket_metadata(sop_config)
    if request.metadata:
        # Merge user-provided metadata
        initial_metadata.update(request.metadata)

    # Use SOP default priority if not provided
    priority = request.priority if request.priority is not None else sop_config.priority_default

    # Create ticket
    success = create_ticket(
        ticket_id=ticket_id,
        sop=request.sop,
        ticket_type=sop_config.ticket_type,
        email=request.email,
        status="pending",
        priority=priority,
        user_identifier=request.user_identifier,
        submitted_at=submitted_at,
        deadline=deadline,
        metadata=initial_metadata,
        notes=request.notes,
        automated=False,  # User-created
        db_path=getattr(req.app.state, "db_path", None),
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create ticket",
        )

    # Retrieve and return created ticket
    ticket = get_ticket(ticket_id, db_path=getattr(req.app.state, "db_path", None))
    if not ticket:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Ticket created but failed to retrieve",
        )

    return TicketResponse(**ticket)


@router.get("/{ticket_id}", response_model=TicketResponse)
async def get_ticket_by_id(
    ticket_id: str,
    req: Request,
    current_user: TokenData = Depends(get_current_user),
) -> TicketResponse:
    """Get a specific ticket by ID.

    Returns:
        Ticket data

    Raises:
        404: Ticket not found
    """
    ticket = get_ticket(ticket_id, db_path=getattr(req.app.state, "db_path", None))
    if not ticket:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Ticket {ticket_id} not found",
        )

    return TicketResponse(**ticket)


@router.get("/", response_model=List[TicketResponse])
async def list_all_tickets(
    req: Request,
    sop: Optional[str] = None,
    ticket_type: Optional[str] = None,
    status_filter: Optional[str] = None,
    email: Optional[str] = None,
    limit: Optional[int] = None,
    current_user: TokenData = Depends(get_current_user),
) -> List[TicketResponse]:
    """List tickets with optional filters.

    Args:
        sop: Filter by SOP (e.g., "DSAR_ACCESS")
        ticket_type: Filter by type (e.g., "dsar")
        status_filter: Filter by status (pending|in_progress|completed|cancelled|failed)
        email: Filter by email
        limit: Maximum number of results

    Returns:
        List of matching tickets (sorted by submission date, newest first)
    """
    tickets = list_tickets(
        sop=sop,
        ticket_type=ticket_type,
        status=status_filter,
        email=email,
        limit=limit,
        db_path=getattr(req.app.state, "db_path", None),
    )

    return [TicketResponse(**ticket) for ticket in tickets]


def _deep_merge(base: Dict[str, Any], update: Dict[str, Any]) -> Dict[str, Any]:
    """Deep merge update into base dictionary."""
    result = base.copy()
    for key, value in update.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _get_db_path(req: Request) -> Optional[str]:
    """Get database path from request app state."""
    return getattr(req.app.state, "db_path", None)


def _verify_ticket_exists(ticket_id: str, db_path: Optional[str]) -> Dict[str, Any]:
    """Verify ticket exists and return it, raising 404 if not found."""
    ticket = get_ticket(ticket_id, db_path=db_path)
    if not ticket:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Ticket {ticket_id} not found",
        )
    return ticket


def _update_ticket_status_if_provided(ticket_id: str, request: UpdateTicketRequest, db_path: Optional[str]) -> None:
    """Update ticket status if provided in request."""
    if not request.status:
        return

    success = update_ticket_status(
        ticket_id=ticket_id,
        new_status=request.status,
        notes=request.notes,
        db_path=db_path,
    )
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update ticket status",
        )


def _update_ticket_metadata_if_provided(
    ticket_id: str, request: UpdateTicketRequest, ticket: Dict[str, Any], db_path: Optional[str]
) -> None:
    """Update ticket metadata if provided in request (deep merge with existing)."""
    if not request.metadata:
        return

    # Get current metadata and merge with new data
    existing_metadata = ticket.get("metadata", {})
    merged_metadata = _deep_merge(existing_metadata, request.metadata)

    success = update_ticket_metadata(
        ticket_id=ticket_id,
        metadata=merged_metadata,
        db_path=db_path,
    )
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update ticket metadata",
        )


def _retrieve_updated_ticket(ticket_id: str, db_path: Optional[str]) -> Dict[str, Any]:
    """Retrieve updated ticket, raising 500 if retrieval fails."""
    updated_ticket = get_ticket(ticket_id, db_path=db_path)
    if not updated_ticket:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Update succeeded but failed to retrieve ticket",
        )
    return updated_ticket


@router.patch("/{ticket_id}", response_model=TicketResponse)
async def update_existing_ticket(
    ticket_id: str,
    request: UpdateTicketRequest,
    req: Request,
    current_user: TokenData = Depends(get_current_user),
) -> TicketResponse:
    """Update ticket status, metadata, or notes.

    Returns:
        Updated ticket data

    Raises:
        404: Ticket not found
        500: Update failed
    """
    db_path = _get_db_path(req)

    # Verify ticket exists
    ticket = _verify_ticket_exists(ticket_id, db_path)

    # Update status if provided
    _update_ticket_status_if_provided(ticket_id, request, db_path)

    # Update metadata if provided (merge with existing)
    _update_ticket_metadata_if_provided(ticket_id, request, ticket, db_path)

    # Retrieve and return updated ticket
    updated_ticket = _retrieve_updated_ticket(ticket_id, db_path)

    return TicketResponse(**updated_ticket)


@router.delete("/{ticket_id}", response_model=StandardResponse)
async def cancel_ticket(
    ticket_id: str,
    req: Request,
    current_user: TokenData = Depends(get_current_user),
) -> StandardResponse:
    """Cancel/delete a ticket.

    Returns:
        Success confirmation

    Raises:
        404: Ticket not found
        500: Deletion failed
    """
    # Verify ticket exists
    ticket = get_ticket(ticket_id, db_path=getattr(req.app.state, "db_path", None))
    if not ticket:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Ticket {ticket_id} not found",
        )

    # Delete ticket
    success = delete_ticket(ticket_id, db_path=getattr(req.app.state, "db_path", None))
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete ticket",
        )

    return StandardResponse(
        success=True,
        message=f"Ticket {ticket_id} cancelled/deleted successfully",
    )
