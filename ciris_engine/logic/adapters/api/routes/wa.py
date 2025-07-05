"""
Wise Authority Service endpoints for CIRIS API v3 (Simplified).

Manages human-in-the-loop deferrals and permissions.
"""
from typing import Optional
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Request, HTTPException, Depends, Query
import logging

from ciris_engine.schemas.api.responses import SuccessResponse, ErrorResponse, ErrorCode, ErrorDetail
from ciris_engine.schemas.api.wa import (
    ResolveDeferralRequest,
    ResolveDeferralResponse,
    PermissionsListResponse,
    WAStatusResponse,
    WAGuidanceRequest,
    WAGuidanceResponse
)
from ciris_engine.schemas.services.authority_core import DeferralResponse
from ciris_engine.protocols.services.governance.wise_authority import WiseAuthorityServiceProtocol
from ..dependencies.auth import require_authority, require_observer, AuthContext

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/wa", tags=["wise_authority"])


@router.get("/deferrals")
async def get_deferrals(
    request: Request,
    wa_id: Optional[str] = Query(None, description="Filter by WA ID"),
    auth: AuthContext = Depends(require_observer)
):
    """
    Get list of pending deferrals.

    Returns all pending deferrals that need WA review. Can optionally
    filter by WA ID to see deferrals assigned to a specific authority.

    Requires OBSERVER role or higher.
    """
    # Get WA service from app state
    if not hasattr(request.app.state, 'wise_authority_service'):
        raise HTTPException(
            status_code=503,
            detail=ErrorResponse(
                error=ErrorDetail(
                    code=ErrorCode.SERVICE_UNAVAILABLE,
                    message="Wise Authority service not available"
                )
            ).model_dump(mode='json')
        )

    wa_service: WiseAuthorityServiceProtocol = request.app.state.wise_authority_service

    try:
        # Get pending deferrals
        deferrals = await wa_service.get_pending_deferrals(wa_id=wa_id)
        
        # Transform PendingDeferral to include question from reason for UI compatibility
        # The TypeScript SDK expects a 'question' field
        transformed_deferrals = []
        for d in deferrals:
            # Create a dict representation and add the question field
            deferral_dict = d.model_dump()
            deferral_dict['question'] = d.reason  # Use reason as the question
            deferral_dict['context'] = {}  # Add empty context for compatibility
            deferral_dict['timeout_at'] = (d.created_at + timedelta(days=7)).isoformat()  # Default 7 day timeout
            transformed_deferrals.append(deferral_dict)

        response = {
            "deferrals": transformed_deferrals,
            "total": len(transformed_deferrals)
        }

        return SuccessResponse(data=response)

    except Exception as e:
        logger.error(f"Failed to get deferrals: {e}")
        raise HTTPException(
            status_code=500,
            detail=ErrorResponse(
                error=ErrorDetail(
                    code=ErrorCode.INTERNAL_ERROR,
                    message=f"Failed to retrieve deferrals: {str(e)}"
                )
            ).model_dump(mode='json')
        )




@router.post("/deferrals/{deferral_id}/resolve", response_model=SuccessResponse[ResolveDeferralResponse])
async def resolve_deferral(
    request: Request,
    deferral_id: str,
    resolve_request: ResolveDeferralRequest,
    auth: AuthContext = Depends(require_authority)
):
    """
    Resolve a pending deferral with guidance.

    Allows a WA with AUTHORITY role to approve, reject, or modify
    a deferred decision. The resolution includes wisdom guidance
    integrated into the decision.

    Requires AUTHORITY role.
    """
    # Get WA service from app state
    if not hasattr(request.app.state, 'wise_authority_service'):
        raise HTTPException(
            status_code=503,
            detail=ErrorResponse(
                error=ErrorDetail(
                    code=ErrorCode.SERVICE_UNAVAILABLE,
                    message="Wise Authority service not available"
                )
            ).model_dump(mode='json')
        )

    wa_service: WiseAuthorityServiceProtocol = request.app.state.wise_authority_service

    try:
        # Create deferral response with integrated guidance
        deferral_response = DeferralResponse(
            approved=(resolve_request.resolution == "approve"),
            reason=resolve_request.guidance or f"Resolved by {auth.user_id}",
            modified_time=None,  # Time modifications not needed in simplified version
            wa_id=auth.user_id,  # Use authenticated user as WA
            signature=f"api_{auth.user_id}_{datetime.now(timezone.utc).isoformat()}"
        )

        # Resolve the deferral
        success = await wa_service.resolve_deferral(deferral_id, deferral_response)

        if not success:
            raise HTTPException(
                status_code=400,
                detail=ErrorResponse(
                    error=ErrorDetail(
                        code=ErrorCode.VALIDATION_ERROR,
                        message="Failed to resolve deferral - it may have already been resolved"
                    )
                ).model_dump(mode='json')
            )

        response = ResolveDeferralResponse(
            success=True,
            deferral_id=deferral_id,
            resolved_at=datetime.now(timezone.utc)
        )

        logger.info(f"Deferral {deferral_id} resolved by {auth.user_id} with resolution: {resolve_request.resolution}")

        return SuccessResponse(data=response)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to resolve deferral {deferral_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=ErrorResponse(
                error=ErrorDetail(
                    code=ErrorCode.INTERNAL_ERROR,
                    message=f"Failed to resolve deferral: {str(e)}"
                )
            ).model_dump(mode='json')
        )




@router.get("/permissions", response_model=SuccessResponse[PermissionsListResponse])
async def get_permissions(
    request: Request,
    wa_id: Optional[str] = Query(None, description="WA ID to get permissions for (defaults to current user)"),
    auth: AuthContext = Depends(require_observer)
):
    """
    Get WA permission status.

    Returns permission status for a specific WA. If no WA ID
    is provided, returns permissions for the authenticated user.
    This simplified endpoint focuses on viewing permissions only.

    Requires OBSERVER role or higher.
    """
    # Get WA service from app state
    if not hasattr(request.app.state, 'wise_authority_service'):
        raise HTTPException(
            status_code=503,
            detail=ErrorResponse(
                error=ErrorDetail(
                    code=ErrorCode.SERVICE_UNAVAILABLE,
                    message="Wise Authority service not available"
                )
            ).model_dump(mode='json')
        )

    wa_service: WiseAuthorityServiceProtocol = request.app.state.wise_authority_service

    try:
        # Use authenticated user's ID if no WA ID provided
        target_wa_id = wa_id or auth.user_id

        # Get permissions
        permissions = await wa_service.list_permissions(target_wa_id)

        response = PermissionsListResponse(
            permissions=permissions,
            wa_id=target_wa_id
        )

        return SuccessResponse(data=response)

    except Exception as e:
        logger.error(f"Failed to get permissions for {target_wa_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=ErrorResponse(
                error=ErrorDetail(
                    code=ErrorCode.INTERNAL_ERROR,
                    message=f"Failed to retrieve permissions: {str(e)}"
                )
            ).model_dump(mode='json')
        )


@router.get("/status", response_model=SuccessResponse[WAStatusResponse])
async def get_wa_status(
    request: Request,
    auth: AuthContext = Depends(require_observer)
):
    """
    Get current WA service status.

    Returns information about the WA service including:
    - Number of active WAs
    - Number of pending deferrals
    - Service health status

    Requires OBSERVER role or higher.
    """
    # Get WA service from app state
    if not hasattr(request.app.state, 'wise_authority_service'):
        raise HTTPException(
            status_code=503,
            detail=ErrorResponse(
                error=ErrorDetail(
                    code=ErrorCode.SERVICE_UNAVAILABLE,
                    message="Wise Authority service not available"
                )
            ).model_dump(mode='json')
        )

    wa_service: WiseAuthorityServiceProtocol = request.app.state.wise_authority_service

    try:
        # Get service status
        is_healthy = True
        if hasattr(wa_service, 'is_healthy'):
            is_healthy = await wa_service.is_healthy()

        # Get pending deferrals count
        pending_deferrals = await wa_service.get_pending_deferrals()
        
        # Get active WAs (in a real implementation, this would query WA registry)
        # For now, we'll just report if the service is available
        active_was = 1 if is_healthy else 0

        response = WAStatusResponse(
            service_healthy=is_healthy,
            active_was=active_was,
            pending_deferrals=len(pending_deferrals),
            deferrals_24h=len(pending_deferrals),  # Simplified - would track over time
            average_resolution_time_minutes=0.0,  # Would calculate from historical data
            timestamp=datetime.now(timezone.utc)
        )

        return SuccessResponse(data=response)

    except Exception as e:
        logger.error(f"Failed to get WA status: {e}")
        raise HTTPException(
            status_code=500,
            detail=ErrorResponse(
                error=ErrorDetail(
                    code=ErrorCode.INTERNAL_ERROR,
                    message=f"Failed to retrieve WA status: {str(e)}"
                )
            ).model_dump(mode='json')
        )


@router.post("/guidance", response_model=SuccessResponse[WAGuidanceResponse])
async def request_guidance(
    request: Request,
    guidance_request: WAGuidanceRequest,
    auth: AuthContext = Depends(require_observer)
):
    """
    Request guidance from WA on a specific topic.

    This endpoint allows requesting wisdom guidance without
    creating a formal deferral. Useful for proactive wisdom
    integration.

    Requires OBSERVER role or higher.
    """
    # Get WA service from app state
    if not hasattr(request.app.state, 'wise_authority_service'):
        raise HTTPException(
            status_code=503,
            detail=ErrorResponse(
                error=ErrorDetail(
                    code=ErrorCode.SERVICE_UNAVAILABLE,
                    message="Wise Authority service not available"
                )
            ).model_dump(mode='json')
        )

    wa_service: WiseAuthorityServiceProtocol = request.app.state.wise_authority_service

    try:
        # In a real implementation, this would query available WAs for guidance
        # For now, we'll provide a simple response
        
        # Check if this is about an ethical concern
        is_ethical = any(word in guidance_request.topic.lower() 
                        for word in ['ethical', 'moral', 'right', 'wrong', 'should'])
        
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
            wa_id="system",  # In production, would be the actual WA who provided guidance
            confidence=0.85 if is_ethical else 0.75,
            additional_context={
                "topic": guidance_request.topic,
                "context_provided": bool(guidance_request.context),
                "urgency": guidance_request.urgency.value if guidance_request.urgency else "normal"
            },
            timestamp=datetime.now(timezone.utc)
        )

        return SuccessResponse(data=response)

    except Exception as e:
        logger.error(f"Failed to get guidance: {e}")
        raise HTTPException(
            status_code=500,
            detail=ErrorResponse(
                error=ErrorDetail(
                    code=ErrorCode.INTERNAL_ERROR,
                    message=f"Failed to retrieve guidance: {str(e)}"
                )
            ).model_dump(mode='json')
        )
