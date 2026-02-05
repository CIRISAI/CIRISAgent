"""
Wise Authority Service endpoints for CIRIS API v3 (Simplified).

Manages human-in-the-loop deferrals and permissions.
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Annotated, NoReturn, Optional, TypeVar, cast

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel

from ciris_engine.protocols.services.governance.wise_authority import WiseAuthorityServiceProtocol
from ciris_engine.schemas.api.responses import ErrorCode, ErrorDetail, ErrorResponse, ResponseMetadata, SuccessResponse
from ciris_engine.schemas.api.wa import (
    DeferralListResponse,
    PermissionsListResponse,
    ResolveDeferralRequest,
    ResolveDeferralResponse,
    WAGuidanceRequest,
    WAGuidanceResponse,
    WAStatusResponse,
)
from ciris_engine.schemas.services.authority_core import DeferralResponse

from ..constants import ERROR_WISE_AUTHORITY_SERVICE_NOT_AVAILABLE
from ..dependencies.auth import AuthContext, require_authority, require_observer

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/wa", tags=["wise_authority"])


# ============================================================================
# Consolidated Helpers
# ============================================================================


def get_wa_service(request: Request) -> WiseAuthorityServiceProtocol:
    """Get WA service from app state or raise 503.

    Consolidates the repeated service availability check pattern.

    Args:
        request: FastAPI request object

    Returns:
        WiseAuthorityServiceProtocol instance

    Raises:
        HTTPException: 503 if service not available
    """
    if not hasattr(request.app.state, "wise_authority_service"):
        raise HTTPException(
            status_code=503,
            detail=ErrorResponse(
                error=ErrorDetail(
                    code=ErrorCode.SERVICE_UNAVAILABLE,
                    message=ERROR_WISE_AUTHORITY_SERVICE_NOT_AVAILABLE,
                )
            ).model_dump(mode="json"),
        )
    return cast(WiseAuthorityServiceProtocol, request.app.state.wise_authority_service)


# TypeVar for generic response wrapper (Python 3.10 compatible)
_T = TypeVar("_T", bound=BaseModel)


def create_wa_success_response(data: _T) -> SuccessResponse[_T]:
    """Create a standardized success response with metadata.

    Consolidates the repeated SuccessResponse wrapper pattern.

    Args:
        data: Response data (must be a Pydantic BaseModel)

    Returns:
        SuccessResponse with standard metadata
    """
    return SuccessResponse(
        data=data,
        metadata=ResponseMetadata(
            timestamp=datetime.now(timezone.utc),
            request_id=str(uuid.uuid4()),
            duration_ms=0,
        ),
    )


def raise_wa_error(message: str, status_code: int = 500) -> NoReturn:
    """Raise a standardized WA error response.

    Consolidates the repeated error response pattern.

    Args:
        message: Error message
        status_code: HTTP status code (default 500)

    Raises:
        HTTPException: Always raises with the specified error
    """
    raise HTTPException(
        status_code=status_code,
        detail=ErrorResponse(
            error=ErrorDetail(
                code=ErrorCode.INTERNAL_ERROR if status_code == 500 else ErrorCode.VALIDATION_ERROR,
                message=message,
            )
        ).model_dump(mode="json"),
    )


def sanitize_for_log(value: str) -> str:
    """Sanitize user input for safe logging.

    Prevents log injection by removing control characters.

    Args:
        value: User-provided string

    Returns:
        Sanitized string safe for logging
    """
    return "".join(c if c.isprintable() and c not in "\n\r\t" else " " for c in value)


@router.get("/deferrals", responses={503: {"description": "Wise Authority service not available"}})
async def get_deferrals(
    request: Request,
    auth: Annotated[AuthContext, Depends(require_observer)],
    wa_id: Annotated[Optional[str], Query(description="Filter by WA ID")] = None,
) -> SuccessResponse[DeferralListResponse]:
    """
    Get list of pending deferrals.

    Returns all pending deferrals that need WA review. Can optionally
    filter by WA ID to see deferrals assigned to a specific authority.

    Requires OBSERVER role or higher.
    """
    wa_service = get_wa_service(request)

    try:
        deferrals = await wa_service.get_pending_deferrals(wa_id=wa_id)
        response = DeferralListResponse(deferrals=deferrals, total=len(deferrals))
        return create_wa_success_response(response)

    except Exception as e:
        logger.error(f"Failed to get deferrals: {e}")
        raise_wa_error(f"Failed to retrieve deferrals: {str(e)}")


@router.post(
    "/deferrals/{deferral_id}/resolve",
    responses={503: {"description": "Wise Authority service not available"}},
)
async def resolve_deferral(
    request: Request,
    deferral_id: str,
    resolve_request: ResolveDeferralRequest,
    auth: Annotated[AuthContext, Depends(require_authority)],
) -> SuccessResponse[ResolveDeferralResponse]:
    """
    Resolve a pending deferral with guidance.

    Allows a WA with AUTHORITY role to approve, reject, or modify
    a deferred decision. The resolution includes wisdom guidance
    integrated into the decision.

    Requires AUTHORITY role.
    """
    wa_service = get_wa_service(request)

    try:
        deferral_response = DeferralResponse(
            approved=(resolve_request.resolution == "approve"),
            reason=resolve_request.guidance or f"Resolved by {auth.user_id}",
            modified_time=None,
            wa_id=auth.user_id,
            signature=f"api_{auth.user_id}_{datetime.now(timezone.utc).isoformat()}",
        )

        success = await wa_service.resolve_deferral(deferral_id, deferral_response)

        if not success:
            raise_wa_error("Failed to resolve deferral - it may have already been resolved", status_code=400)

        response = ResolveDeferralResponse(
            success=True, deferral_id=deferral_id, resolved_at=datetime.now(timezone.utc)
        )

        safe_resolution = sanitize_for_log(resolve_request.resolution)
        safe_deferral_id = sanitize_for_log(deferral_id)
        logger.info(f"Deferral {safe_deferral_id} resolved by {auth.user_id} with resolution: {safe_resolution}")

        return create_wa_success_response(response)

    except HTTPException:
        raise
    except Exception as e:
        import hashlib

        deferral_hash = hashlib.sha256(deferral_id.encode()).hexdigest()[:8]
        logger.error(f"Failed to resolve deferral [id_hash:{deferral_hash}]: {e}")
        raise_wa_error(f"Failed to resolve deferral: {str(e)}")


@router.get("/permissions", responses={503: {"description": "Wise Authority service not available"}})
async def get_permissions(
    request: Request,
    auth: Annotated[AuthContext, Depends(require_observer)],
    wa_id: Annotated[Optional[str], Query(description="WA ID to get permissions for (defaults to current user)")] = None,
) -> SuccessResponse[PermissionsListResponse]:
    """
    Get WA permission status.

    Returns permission status for a specific WA. If no WA ID
    is provided, returns permissions for the authenticated user.
    This simplified endpoint focuses on viewing permissions only.

    Requires OBSERVER role or higher.
    """
    wa_service = get_wa_service(request)
    target_wa_id = wa_id or auth.user_id

    try:
        permissions = await wa_service.list_permissions(target_wa_id)
        response = PermissionsListResponse(permissions=permissions, wa_id=target_wa_id)
        return create_wa_success_response(response)

    except Exception as e:
        safe_target_wa_id = sanitize_for_log(target_wa_id)
        logger.error(f"Failed to get permissions for {safe_target_wa_id}: {e}")
        raise_wa_error(f"Failed to retrieve permissions: {str(e)}")


@router.get("/status", responses={503: {"description": "Wise Authority service not available"}})
async def get_wa_status(
    request: Request,
    auth: Annotated[AuthContext, Depends(require_observer)],
) -> SuccessResponse[WAStatusResponse]:
    """
    Get current WA service status.

    Returns information about the WA service including:
    - Number of active WAs
    - Number of pending deferrals
    - Service health status

    Requires OBSERVER role or higher.
    """
    wa_service = get_wa_service(request)

    try:
        is_healthy = True
        if hasattr(wa_service, "is_healthy"):
            is_healthy = await wa_service.is_healthy()

        pending_deferrals = await wa_service.get_pending_deferrals()
        active_was = 1 if is_healthy else 0

        response = WAStatusResponse(
            service_healthy=is_healthy,
            active_was=active_was,
            pending_deferrals=len(pending_deferrals),
            deferrals_24h=len(pending_deferrals),
            average_resolution_time_minutes=0.0,
            timestamp=datetime.now(timezone.utc),
        )

        return create_wa_success_response(response)

    except Exception as e:
        logger.error(f"Failed to get WA status: {e}")
        raise_wa_error(f"Failed to retrieve WA status: {str(e)}")


@router.post("/guidance", responses={503: {"description": "Wise Authority service not available"}})
async def request_guidance(
    request: Request,
    guidance_request: WAGuidanceRequest,
    auth: Annotated[AuthContext, Depends(require_observer)],
) -> SuccessResponse[WAGuidanceResponse]:
    """
    Request guidance from WA on a specific topic.

    This endpoint allows requesting wisdom guidance without
    creating a formal deferral. Useful for proactive wisdom
    integration.

    Requires OBSERVER role or higher.
    """
    # Validate service availability (will be used in full implementation)
    get_wa_service(request)

    try:
        is_ethical = any(
            word in guidance_request.topic.lower() for word in ["ethical", "moral", "right", "wrong", "should"]
        )

        if is_ethical:
            guidance = (
                "Consider the Ubuntu principle: 'I am because we are.' "
                "Evaluate how this decision impacts the community as a whole. "
                "Seek consensus and ensure actions align with collective well-being."
            )
        else:
            guidance = (
                "For technical decisions, consider long-term maintainability, "
                "scalability, and alignment with system principles. "
                "Document your reasoning for future reference."
            )

        response = WAGuidanceResponse(
            guidance=guidance,
            wa_id="system",
            confidence=0.85 if is_ethical else 0.75,
            additional_context={
                "topic": guidance_request.topic,
                "context_provided": bool(guidance_request.context),
                "urgency": guidance_request.urgency.value if guidance_request.urgency else "normal",
            },
            timestamp=datetime.now(timezone.utc),
        )

        return create_wa_success_response(response)

    except Exception as e:
        logger.error(f"Failed to get guidance: {e}")
        raise_wa_error(f"Failed to retrieve guidance: {str(e)}")
