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

import logging
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Annotated, Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field

from ciris_engine.logic.persistence.models.tickets import (
    create_ticket,
    delete_ticket,
    get_ticket,
    list_tickets,
    update_ticket_metadata,
    update_ticket_status,
)
from ciris_engine.logic.services.governance.budget_envelope import NestingViolation, issue_grant
from ciris_engine.schemas.config.tickets import TicketsConfig, TicketSOPConfig
from ciris_engine.schemas.services.budget_envelope import (
    BUDGET_SPENT_METADATA_KEY,
    GRANTED_BUDGET_METADATA_KEY,
    REQUESTED_BUDGET_METADATA_KEY,
    is_unapproved_proposal,
)

from ..auth import get_current_user
from ..dependencies.auth import AuthContext, require_authority
from ..models import StandardResponse, TokenData

logger = logging.getLogger(__name__)

# Type alias for authenticated user dependency (S8410 compliance)
CurrentUserDep = Annotated[TokenData, Depends(get_current_user)]

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


@router.get(
    "/sops",
    responses={
        500: {"description": "Tickets configuration not available"},
    },
)
async def list_supported_sops(
    req: Request,
    current_user: CurrentUserDep,
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


@router.get(
    "/sops/{sop}",
    responses={
        404: {"description": "SOP not found or not supported"},
    },
)
async def get_sop_metadata(
    sop: str,
    req: Request,
    current_user: CurrentUserDep,
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


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    responses={
        500: {"description": "Ticket creation or retrieval failed"},
        501: {"description": "SOP not supported by this agent"},
    },
)
async def create_new_ticket(
    request: CreateTicketRequest,
    req: Request,
    current_user: CurrentUserDep,
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
        )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create ticket",
        )

    # Retrieve and return created ticket
    ticket = get_ticket(ticket_id)
    if not ticket:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Ticket created but failed to retrieve",
        )

    return TicketResponse(**ticket)


@router.get(
    "/{ticket_id}",
    responses={
        404: {"description": "Ticket not found"},
    },
)
async def get_ticket_by_id(
    ticket_id: str,
    req: Request,
    current_user: CurrentUserDep,
) -> TicketResponse:
    """Get a specific ticket by ID.

    Returns:
        Ticket data

    Raises:
        404: Ticket not found
    """
    ticket = get_ticket(ticket_id)
    if not ticket:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Ticket {ticket_id} not found",
        )

    return TicketResponse(**ticket)


@router.get("")
async def list_all_tickets(
    req: Request,
    current_user: CurrentUserDep,
    sop: Optional[str] = None,
    ticket_type: Optional[str] = None,
    status_filter: Optional[str] = None,
    email: Optional[str] = None,
    limit: Optional[int] = None,
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
        limit=limit
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


def _verify_ticket_exists(ticket_id: str) -> Dict[str, Any]:
    """Verify ticket exists and return it, raising 404 if not found."""
    ticket = get_ticket(ticket_id)
    if not ticket:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Ticket {ticket_id} not found",
        )
    return ticket


def _update_ticket_status_if_provided(ticket_id: str, request: UpdateTicketRequest) -> None:
    """Update ticket status if provided in request."""
    if not request.status:
        return

    success = update_ticket_status(
        ticket_id=ticket_id,
        new_status=request.status,
        notes=request.notes,
    )
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update ticket status",
        )


def _update_ticket_metadata_if_provided(
    ticket_id: str, request: UpdateTicketRequest, ticket: Dict[str, Any]
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
    )
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update ticket metadata",
        )


def _retrieve_updated_ticket(ticket_id: str) -> Dict[str, Any]:
    """Retrieve updated ticket, raising 500 if retrieval fails."""
    updated_ticket = get_ticket(ticket_id)
    if not updated_ticket:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Update succeeded but failed to retrieve ticket",
        )
    return updated_ticket


@router.patch(
    "/{ticket_id}",
    responses={
        404: {"description": "Ticket not found"},
        500: {"description": "Update failed"},
    },
)
async def update_existing_ticket(
    ticket_id: str,
    request: UpdateTicketRequest,
    req: Request,
    current_user: CurrentUserDep,
) -> TicketResponse:
    """Update ticket status, metadata, or notes.

    Returns:
        Updated ticket data

    Raises:
        404: Ticket not found
        500: Update failed
    """
    # Verify ticket exists
    ticket = _verify_ticket_exists(ticket_id)

    # Update status if provided
    _update_ticket_status_if_provided(ticket_id, request)

    # Update metadata if provided (merge with existing)
    _update_ticket_metadata_if_provided(ticket_id, request, ticket)

    # Retrieve and return updated ticket
    updated_ticket = _retrieve_updated_ticket(ticket_id)

    return TicketResponse(**updated_ticket)


@router.delete(
    "/{ticket_id}",
    responses={
        404: {"description": "Ticket not found"},
        500: {"description": "Deletion failed"},
    },
)
async def cancel_ticket(
    ticket_id: str,
    req: Request,
    current_user: CurrentUserDep,
) -> StandardResponse:
    """Cancel/delete a ticket.

    Returns:
        Success confirmation

    Raises:
        404: Ticket not found
        500: Deletion failed
    """
    # Verify ticket exists
    ticket = get_ticket(ticket_id)
    if not ticket:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Ticket {ticket_id} not found",
        )

    # Delete ticket
    success = delete_ticket(ticket_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete ticket",
        )

    return StandardResponse(
        success=True,
        message=f"Ticket {ticket_id} cancelled/deleted successfully",
    )


# ============================================================================
# Budget envelope — the issuance event (#938)
#
# This is the ONLY write path for a granted budget. It requires the AUTHORITY
# role and lives outside the reasoning loop entirely: no tool, no handler and no
# DMA can reach it. The agent may propose an envelope (create_ticket) but never
# mint or widen one.
# ============================================================================


class GrantBudgetRequest(BaseModel):
    """Request to grant a spend budget on a ticket. Requires AUTHORITY role.

    An AUTHORITY user may grant **above** what the agent requested — the agent
    may simply have asked for too little. There is no ``granted ≤ requested``
    bound anywhere in the system. The real bound is ``granted ≤ trust ceiling``.
    Over-request grants are *recorded* (see ``GrantedBudget.exceeds_request``),
    which is derived server-side, never taken from this body.
    """

    amount: Decimal = Field(..., gt=0, description="Maximum total spend authorized against this ticket")
    currency: str = Field(..., min_length=2, max_length=8, description="Currency code, e.g. USDC")
    purpose: str = Field(..., min_length=1, description="What this grant authorizes spend for")
    expires_in_hours: float = Field(
        24.0, gt=0, le=8760, description="Grant lifetime in hours (default 24, max 1 year)"
    )
    wa_id: Optional[str] = Field(None, description="WA identity to sign as (defaults to the calling user)")

    # `extra="forbid"`: an unknown field is a loud 422 rather than a silent
    # default. On a money endpoint that matters — a typo'd `expires_in_hours`
    # would otherwise quietly take the 24h default. It also means a client
    # cannot assert the over-grant audit marking (`exceeds_request`,
    # `requested_amount_at_grant`): those are derived server-side in
    # `issue_grant` from the ticket, and a request that tries to supply them is
    # rejected outright rather than silently ignored.
    model_config = ConfigDict(extra="forbid")


class GrantBudgetResponse(BaseModel):
    """The granted budget, as written to the ticket."""

    ticket_id: str
    granted_amount: str
    granted_currency: str
    purpose: str
    expires_at: str
    granted_by_wa_id: str
    granted_by_user_id: str
    granted_at: str
    signed: bool = Field(..., description="Whether the grant carries a verifiable signature")
    exceeds_request: bool = Field(
        ..., description="True when the grant exceeded the agent's request (permitted, but recorded)"
    )
    requested_amount_at_grant: Optional[str] = Field(
        None, description="What the agent requested, as of issuance; null when it requested nothing"
    )


@router.post(
    "/{ticket_id}/budget/grant",
    responses={
        403: {"description": "AUTHORITY role required"},
        404: {"description": "Ticket not found"},
        422: {"description": "Grant would exceed the trust-driven envelope"},
    },
)
async def grant_ticket_budget(
    ticket_id: str,
    request: GrantBudgetRequest,
    req: Request,
    auth: Annotated[AuthContext, Depends(require_authority)],
) -> StandardResponse:
    """Grant a spend budget on a ticket. **Requires AUTHORITY role.**

    This is the human decision point that converts an agent's *request* into an
    *authorization*. The resulting grant is bound to this ticket, expires, and
    is enforced at every spend as ``min(granted remaining, trust envelope
    remaining)``.

    A grant cannot widen the deployment's trust-driven envelope: it is checked
    against the configured ceiling here, and bounded again at spend time.
    """
    ticket = get_ticket(ticket_id)
    if not ticket:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_ticket_not_found_detail(ticket_id))

    auth_service = getattr(req.app.state, "authentication_service", None)
    expires_at = datetime.now(timezone.utc) + timedelta(hours=request.expires_in_hours)

    try:
        grant = await issue_grant(
            ticket_id=ticket_id,
            granted_amount=request.amount,
            granted_currency=request.currency,
            purpose=request.purpose,
            expires_at=expires_at,
            granted_by_wa_id=request.wa_id or auth.user_id,
            granted_by_user_id=auth.user_id,
            trust_ceiling=_resolve_trust_ceiling(req),
            auth_service=auth_service,
        )
    except NestingViolation as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)) from e

    return StandardResponse(
        success=True,
        data=GrantBudgetResponse(
            ticket_id=grant.ticket_id,
            granted_amount=str(grant.granted_amount),
            granted_currency=grant.granted_currency,
            purpose=grant.purpose,
            expires_at=grant.expires_at.isoformat(),
            granted_by_wa_id=grant.granted_by_wa_id,
            granted_by_user_id=grant.granted_by_user_id,
            granted_at=grant.granted_at.isoformat(),
            signed=grant.signature is not None,
            exceeds_request=grant.exceeds_request,
            requested_amount_at_grant=(
                str(grant.requested_amount_at_grant) if grant.requested_amount_at_grant is not None else None
            ),
        ).model_dump(),
        message=f"Budget granted on ticket {ticket_id}",
    )


#: Machine-readable error code for "this ticket does not exist", as opposed to
#: "this endpoint does not exist" (which FastAPI answers with a bare
#: ``{"detail": "Not Found"}`` on servers predating the budget feature).
#: Clients should pin on ``detail.error_code``, never on prose.
TICKET_NOT_FOUND_ERROR_CODE = "TICKET_NOT_FOUND"


def _ticket_not_found_detail(ticket_id: str) -> Dict[str, str]:
    """404 body for a missing ticket, disambiguable from a missing endpoint.

    Returns a structured detail so a client can branch on ``error_code`` instead
    of substring-matching prose. The message also contains the lowercase word
    "ticket" so prose-matching clients still work.
    """
    return {
        "error_code": TICKET_NOT_FOUND_ERROR_CODE,
        "message": f"Ticket {ticket_id} not found — no such ticket on this node",
    }


class TrustHeadroomResponse(BaseModel):
    """Remaining room in the deployment trust envelope a grant must nest inside."""

    amount: str = Field(..., description="Remaining headroom, decimal as string")
    currency: str = Field(..., description="Currency the headroom applies to")
    max_transaction: str = Field(..., description="Per-transaction ceiling")
    daily_remaining: str = Field(..., description="Remaining daily allowance")
    source: str = Field(..., description="'wallet' when resolved from the live gate")


class TicketBudgetResponse(BaseModel):
    """Everything a human needs to decide on a budget for one ticket."""

    ticket_id: str
    is_proposal: bool = Field(..., description="True when this is an unapproved agent proposal")
    requested_budget: Optional[Dict[str, Any]] = Field(None, description="What the agent asked for")
    granted_budget: Optional[Dict[str, Any]] = Field(None, description="What a human authorized, if any")
    spent: Optional[Dict[str, Any]] = Field(None, description="Running ledger against the grant")
    trust_headroom: Optional[TrustHeadroomResponse] = Field(
        None, description="Remaining trust envelope; null when no wallet is loaded"
    )


@router.get(
    "/{ticket_id}/budget",
    responses={404: {"description": "Ticket not found"}},
)
async def get_ticket_budget(
    ticket_id: str,
    req: Request,
    current_user: CurrentUserDep,
) -> StandardResponse:
    """Read the budget state of a ticket, including remaining trust headroom.

    Exists so a human approving a budget can see how much room the deployment
    has left. Approving an amount with no view of the remaining envelope is not
    meaningful consent.

    ``trust_headroom`` is the **same number the spend gate applies** — resolved
    through the wallet tool service's own `_resolve_trust_envelope`, not a
    re-derivation. It is null when no wallet adapter is loaded.
    """
    ticket = get_ticket(ticket_id)
    if not ticket:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_ticket_not_found_detail(ticket_id))

    metadata = ticket.get("metadata") or {}
    if not isinstance(metadata, dict):
        metadata = {}

    requested = metadata.get(REQUESTED_BUDGET_METADATA_KEY)
    granted = metadata.get(GRANTED_BUDGET_METADATA_KEY)
    currency = None
    if isinstance(granted, dict):
        currency = granted.get("granted_currency")
    if currency is None and isinstance(requested, dict):
        currency = requested.get("requested_currency")

    return StandardResponse(
        success=True,
        data=TicketBudgetResponse(
            ticket_id=ticket_id,
            is_proposal=is_unapproved_proposal(ticket),
            requested_budget=requested if isinstance(requested, dict) else None,
            granted_budget=granted if isinstance(granted, dict) else None,
            spent=metadata.get(BUDGET_SPENT_METADATA_KEY)
            if isinstance(metadata.get(BUDGET_SPENT_METADATA_KEY), dict)
            else None,
            trust_headroom=_resolve_trust_headroom(req, str(currency) if currency else "USDC"),
        ).model_dump(),
        message=f"Budget state for ticket {ticket_id}",
    )


def _find_wallet_tool_service(req: Request) -> Optional[Any]:
    """Find a registered TOOL service exposing the wallet spend gate."""
    try:
        registry = getattr(req.app.state, "service_registry", None)
        if registry is None or not hasattr(registry, "_services"):
            return None
        from ciris_engine.schemas.runtime.enums import ServiceType

        for provider in registry._services.get(ServiceType.TOOL, []):
            instance = getattr(provider, "instance", None)
            if instance is not None and hasattr(instance, "_resolve_trust_envelope"):
                return instance
    except Exception as e:  # pragma: no cover - defensive
        logger.warning(f"Could not locate wallet tool service: {e}")
    return None


def _resolve_trust_headroom(req: Request, currency: str) -> Optional[TrustHeadroomResponse]:
    """Resolve remaining trust-envelope headroom via the wallet's own gate logic."""
    service = _find_wallet_tool_service(req)
    if service is None:
        return None
    try:
        provider = service._get_provider_for_currency(currency)
        envelope = service._resolve_trust_envelope(currency, provider)
        return TrustHeadroomResponse(
            amount=str(envelope.remaining),
            currency=envelope.currency or currency,
            max_transaction=str(envelope.max_transaction),
            daily_remaining=str(envelope.daily_remaining),
            source="wallet",
        )
    except Exception as e:  # pragma: no cover - defensive
        logger.warning(f"Could not resolve trust headroom for {currency}: {e}")
        return None


def _resolve_trust_ceiling(req: Request) -> Optional[Decimal]:
    """Resolve the deployment trust-envelope ceiling a grant must nest inside.

    Reads the wallet adapter's ``spending_limits`` when a wallet tool service is
    registered. Returns None when no wallet is loaded — in which case issuance is
    unbounded here but every spend is still bounded by the ``min()`` in
    ``authorize_spend``, which is the authoritative check.
    """
    try:
        registry = getattr(req.app.state, "service_registry", None)
        if registry is None or not hasattr(registry, "_services"):
            return None
        from ciris_engine.schemas.runtime.enums import ServiceType

        for provider in registry._services.get(ServiceType.TOOL, []):
            instance = getattr(provider, "instance", None)
            config = getattr(instance, "config", None)
            limits = getattr(config, "spending_limits", None)
            if limits is not None:
                ceiling: Decimal = limits.daily_limit
                return ceiling
    except Exception as e:  # pragma: no cover - defensive
        logger.warning(f"Could not resolve trust ceiling for budget grant: {e}")
    return None
