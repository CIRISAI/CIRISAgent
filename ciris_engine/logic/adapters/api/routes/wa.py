"""
Wise Authority Service endpoints for CIRIS API v3 (Simplified).

Manages human-in-the-loop deferrals and permissions.
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Annotated, NoReturn, Optional, TypeVar, cast

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
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
from ciris_engine.logic.services.governance.wise_authority.deferral_rows import (
    DeferralRowRefused,
    DeferralRowsUnavailable,
    emit_deferral_response,
    read_deferral_row,
    rows_available,
)
from ciris_engine.schemas.services.authority.deferral_rows import (
    REASON_UNKNOWN_REQUEST,
    DeferralRowRefusal,
    DeferralRowRefusalKind,
    DeferralRowView,
)
from ciris_engine.schemas.services.authority.wise_authority import PendingDeferral
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


async def resolve_certificate_id(request: Request, auth: AuthContext) -> str:
    """Map the authenticated caller onto the WA CERTIFICATE id.

    These are not the same identifier, and the jurisdiction gate needs the
    certificate one because ``WiseAuthorityService.authorize()`` resolves it
    with an exact ``get_wa()`` lookup.

    * Node logins (password, Google, Apple, OAuth callback) and API keys
      already carry it: the node resolves every session to the ``wa_id``.
    * Ingress auth does NOT. ``dependencies/auth.py`` builds
      ``user_id`` as ``"{provider}:{external_id}"`` while the certificate is
      stored under a generated ``wa-YYYY-MM-DD-XXXXXX`` id and merely LINKED
      to that OAuth identity via ``oauth_provider`` / ``oauth_external_id``.
      Passing the external identity straight through made every ingress
      authority a ``WA_NOT_FOUND`` and therefore a 403 on every domain-tagged
      deferral.

    Returns the caller's id unchanged when it cannot be mapped: the gate then
    reports WA_NOT_FOUND naming that id, which is diagnosable, rather than
    this helper inventing a certificate.
    """
    user_id = (auth.user_id or "").strip()
    if ":" not in user_id:
        return user_id

    provider, _, external_id = user_id.partition(":")
    auth_service = getattr(request.app.state, "authentication_service", None)
    if auth_service is None or not hasattr(auth_service, "get_wa_by_oauth"):
        return user_id

    try:
        cert = await auth_service.get_wa_by_oauth(provider, external_id)
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Could not resolve WA certificate for %s: %s", user_id, exc)
        return user_id

    return str(cert.wa_id) if cert is not None else user_id


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


def _presented_session_token(request: Request) -> Optional[str]:
    """The resolver's raw node session token, exactly as it reached the API, or None.

    Only a ``sess:`` token opens a Wise Authority's own pen on the node. Any
    other credential (an API key, a service token, an ingress identity) is not
    handed to the node at all; the node then answers ``deferral.not_signed_in``.
    """
    from ..dependencies.auth import SUBSTRATE_SESSION_PREFIX

    header = request.headers.get("authorization") or ""
    if not header.startswith("Bearer "):
        return None
    token = header[len("Bearer ") :].strip()
    return token if token.startswith(SUBSTRATE_SESSION_PREFIX) else None


def _row_refusal_status(refusal: DeferralRowRefusal) -> tuple[int, str]:
    """HTTP status and error code for a node refusal of the response row."""
    if refusal.kind is DeferralRowRefusalKind.REFUSED:
        return status.HTTP_403_FORBIDDEN, ErrorCode.FORBIDDEN
    if refusal.kind is DeferralRowRefusalKind.OUTAGE:
        return status.HTTP_503_SERVICE_UNAVAILABLE, ErrorCode.SERVICE_UNAVAILABLE
    if refusal.reason_id == REASON_UNKNOWN_REQUEST:
        # The deferral's recorded request row is not an admitted row on this
        # node: the record and the store disagree, and retrying will not help.
        return status.HTTP_409_CONFLICT, ErrorCode.CONFLICT
    return status.HTTP_400_BAD_REQUEST, ErrorCode.VALIDATION_ERROR


async def _sign_response_row(
    request: Request, deferral_id: str, pending: Optional[PendingDeferral], approved: bool
) -> Optional[str]:
    """Have the node sign the Wise Authority's answer with their own key (#1316); its attestation_id.

    None, and the resolution proceeds as before #1316, when the node has no
    deferral rows, or when this deferral has no signed request row to answer
    (its emit failed, or it predates rows). Such an answer is recorded but
    carries no response row, so an identity change it approves is NOT applied
    where the node authors rows (MemorizeHandler). Every node refusal raises,
    so the resolution is not recorded.
    """
    if not rows_available():
        return None
    request_id = pending.request_attestation_id if pending is not None else None
    if not request_id:
        logger.warning(  # NOSONAR - deferral_id sanitized via sanitize_for_log()
            "Deferral %s has no signed request row; resolving it without a response row "
            "(an identity change it approves will not be applied)",
            sanitize_for_log(deferral_id),
        )
        return None
    try:
        return await emit_deferral_response(request_id, approved, _presented_session_token(request))
    except DeferralRowsUnavailable:
        return None
    except DeferralRowRefused as refused:
        refusal = refused.refusal
        code, error_code = _row_refusal_status(refusal)
        logger.warning(  # NOSONAR - deferral_id sanitized via sanitize_for_log()
            "Deferral %s NOT resolved: the node refused the Wise Authority's response row (%s): %s",
            sanitize_for_log(deferral_id),
            refusal.reason_id,
            sanitize_for_log(refusal.text),
        )
        raise HTTPException(
            status_code=code,
            detail=ErrorResponse(
                error=ErrorDetail(
                    code=error_code,
                    message=f"The resolution was not recorded: {refusal.reason_id}: {refusal.text}",
                    details={"reason_id": refusal.reason_id, "kind": refusal.kind.value},
                )
            ).model_dump(mode="json"),
        ) from refused


@router.get(
    "/rows/{attestation_id}",
    responses={404: {"description": "No such deferral row"}, 503: {"description": "This node has no deferral rows"}},
)
async def get_deferral_row(
    attestation_id: str,
    auth: Annotated[AuthContext, Depends(require_observer)],
) -> SuccessResponse[DeferralRowView]:
    """Read back one of a deferral's signed rows (request, response, amendment) from the node's store (#1316)."""
    try:
        row = await read_deferral_row(attestation_id)
    except DeferralRowsUnavailable:
        raise_wa_error("This node has no deferral rows (ciris-server 0.5.234 or later)", status_code=503)
    except Exception as exc:  # noqa: BLE001 - a read that failed is not "no such row"
        logger.warning("Could not read deferral row %s: %s", sanitize_for_log(attestation_id), exc)
        raise_wa_error(f"Could not read the row ({type(exc).__name__})", status_code=503)
    if row is None:
        raise_wa_error("No deferral row with that attestation_id on this node", status_code=404)
    return create_wa_success_response(row)


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

    # JURISDICTION IS CHECKED HERE, NOT ONLY IN THE SERVICE (NULLWORKS RC3 / F1).
    #
    # `require_authority` gates on ROLE alone. That was the entire finding: an
    # authority holder can be structurally over-broad for a decision domain, and
    # the RC3 retest reproduced resource-invariant authorization at exactly this
    # boundary. The service-layer fix landed alongside this one, but this handler
    # never called it — so the surface an auditor actually hits stayed
    # role-only, and closing F1 without this would have been closing it on paper.
    #
    # The resource is the deferral's DOMAIN (MEDICAL / FINANCIAL / LEGAL / ...),
    # which is the taxonomy the deferral rail already routes on via
    # `DeferralContext.domain_hint`, prefixed onto the deferral id. That is the
    # shape `scope_grants` matches with fnmatchcase, so a certificate reading
    # `resolve_deferral:medical_*` covers `medical_defer_001` and a medical
    # authority resolving a financial deferral is a denial — the auditors' own
    # example. The action is SINGULAR `resolve_deferral`: that is the spelling
    # every certificate fixture and every other caller uses, and the plural was
    # already caught once inside the service (see the note at
    # tests/test_deferral_permissions.py, "plural, and so matching no action
    # anyone actually requests"). Requesting the plural here would have denied
    # every correctly scoped authority instead of the wrong ones.
    #
    # Two failure modes that look alike and must not be treated alike:
    #
    #   no domain on the deferral -> role-only, as before. Most deferrals carry
    #       no domain_hint today and denying them takes the whole human-
    #       resolution path down. Under-specified, not unenforced.
    #   domain could not be READ  -> refuse. A transient persistence failure
    #       must not be a way to resolve a MEDICAL deferral without
    #       jurisdiction; "we could not check" is not "there was nothing to
    #       check". Fail closed, and say it is a lookup failure so an operator
    #       retries rather than hunting a permissions ghost.
    _domain = None
    _pending: Optional[PendingDeferral] = None
    try:
        for _pd in await wa_service.get_pending_deferrals():
            if _pd.deferral_id == deferral_id:
                _pending = _pd
                # PendingDeferral.context is Dict[str, str] with default_factory=dict —
                # never None, and there is no `metadata` field. The WA service copies
                # every stored deferral-context key into it unfiltered, so the
                # domain_hint wise_bus writes (wise_bus.py:275) arrives here.
                _domain = _pd.context.get("domain_hint")
                break
    except Exception as exc:
        logger.warning(  # NOSONAR - deferral_id sanitized via sanitize_for_log()
            "JURISDICTION UNVERIFIABLE: could not read domain for deferral %s: %s",
            sanitize_for_log(deferral_id),
            exc,
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Cannot verify jurisdiction for this deferral right now, so it cannot be resolved. "
                "This is a lookup failure, not a permissions decision — please retry."
            ),
        ) from exc

    if _domain:
        _scope_resource = f"{str(_domain).lower()}_{deferral_id}"
        _wa_id = await resolve_certificate_id(request, auth)
        _decision = await wa_service.authorize(_wa_id, "resolve_deferral", _scope_resource)
        if not _decision.allowed:
            logger.warning(  # NOSONAR - all user-controlled values sanitized via sanitize_for_log()
                "JURISDICTION DENIED: %s (caller %s) may not resolve %s deferral %s (%s; required scope %s)",
                sanitize_for_log(_wa_id),
                sanitize_for_log(auth.user_id or ""),
                sanitize_for_log(str(_domain)),
                sanitize_for_log(deferral_id),
                _decision.reason.value if _decision.reason else "no reason",
                sanitize_for_log(_decision.required_scope or "-"),
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"Not authorized to resolve a {_domain} deferral. Role permits the action; "
                    f"jurisdiction does not. Required scope: "
                    f"{_decision.required_scope or f'resolve_deferral:{str(_domain).lower()}_*'}."
                ),
            )

    try:
        # SIGN THE DECISION (#944). This used to be
        # f"api_{auth.user_id}_{timestamp}" — an identifier and a clock reading,
        # forgeable by anything able to write the row, on the record that governs
        # the agent's most consequential actions. Under #938 it is the
        # budget-issuance event, so it has to be attributable to the authority
        # who made it rather than merely asserted to be.
        #
        # The signature is hybrid (Ed25519 + ML-DSA-65) by the node's persist
        # key, and carries the owner's CEG federation identity that delegated to
        # that key. Fails closed: an approval nobody can verify is refused.
        #
        # KEPT alongside the #1316 response row below, on purpose. The row is
        # signed with the resolver's OWN key (CIRISServer#342's owner pen) but
        # commits only to the verdict and the request it answers; this signature
        # is the only one over the guidance text the guidance task carries, it
        # is what `resolve_deferral` verifies before it issues a WAAuthorization,
        # and it is the only signature at all on a node without rows (< 0.5.234).
        #
        # #342 is addressed for the OWNER: the node's owner is the seated Wise
        # Authority for their own agent (Eric, 2026-10-22), and their session
        # opens their pen. A non-owner WA signing with their own key is
        # CIRISServer#814; until it lands, where the node authors rows, a
        # non-owner's resolution is refused (403 deferral.resolver_has_no_key),
        # fail closed, rather than recorded without the WA's own signature.
        #
        # "modify" is not an approval of what was asked. As before #1316 it is
        # recorded approved=False with the WA's guidance (`resolve_deferral`
        # creates no guidance task for it, so it authorizes nothing), and its
        # row is therefore deferral:response:rejected:v1. Signing it "approved"
        # would let an identity amendment cite it for the unmodified request.
        approved = resolve_request.resolution == "approve"
        signed_at = datetime.now(timezone.utc).isoformat()
        deferral_response = DeferralResponse(
            approved=approved,
            reason=resolve_request.guidance or f"Resolved by {auth.user_id}",
            modified_time=None,
            wa_id=auth.user_id,
            signature="",
        )
        auth_service = getattr(request.app.state, "authentication_service", None)
        if auth_service is None:
            raise_wa_error(
                "Cannot resolve deferral: authentication service unavailable, so the decision could not be signed",
                status_code=503,
            )
        try:
            deferral_response = await auth_service.sign_deferral_resolution(deferral_id, deferral_response, signed_at)
        except Exception as exc:
            logger.error(f"Refusing to record an unsigned deferral resolution for {sanitize_for_log(deferral_id)}")
            raise_wa_error(f"Cannot resolve deferral: signing failed ({type(exc).__name__})", status_code=503)

        # THE WA'S OWN SIGNED ANSWER (#1316), before anything is recorded: if the
        # node refuses it, the resolution is not recorded at all.
        response_row = await _sign_response_row(request, deferral_id, _pending, approved)
        if response_row is not None:
            deferral_response = deferral_response.model_copy(update={"response_attestation_id": response_row})

        success = await wa_service.resolve_deferral(deferral_id, deferral_response)

        if not success:
            if response_row is not None:
                logger.warning(
                    "Deferral %s: the node signed response row %s but the resolution was not recorded",
                    sanitize_for_log(deferral_id),
                    response_row,
                )
            raise_wa_error("Failed to resolve deferral - it may have already been resolved", status_code=400)

        response = ResolveDeferralResponse(
            success=True,
            deferral_id=deferral_id,
            resolved_at=datetime.now(timezone.utc),
            request_attestation_id=_pending.request_attestation_id if _pending else None,
            response_attestation_id=response_row,
        )

        logger.info(  # NOSONAR - all values sanitized via sanitize_for_log()
            "Deferral %s resolved by %s with resolution: %s",
            sanitize_for_log(deferral_id),
            sanitize_for_log(auth.user_id),
            sanitize_for_log(resolve_request.resolution),
        )

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
    wa_id: Annotated[
        Optional[str], Query(description="WA ID to get permissions for (defaults to current user)")
    ] = None,
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
    - List of WA bus subscribers (adapters/services registered for WA events)

    Requires OBSERVER role or higher.
    """
    wa_service = get_wa_service(request)

    try:
        is_healthy = True
        if hasattr(wa_service, "is_healthy"):
            is_healthy = await wa_service.is_healthy()

        pending_deferrals = await wa_service.get_pending_deferrals()
        active_was = 1 if is_healthy else 0

        # Get WA bus subscribers from service registry
        subscribers: list[str] = []
        try:
            from ciris_engine.schemas.runtime.enums import ServiceType

            if hasattr(request.app.state, "service_registry"):
                registry = request.app.state.service_registry
                wa_services = registry.get_services_by_type(ServiceType.WISE_AUTHORITY)
                for svc in wa_services:
                    # Get human-friendly name from service
                    svc_name = getattr(svc, "service_name", None)
                    if not svc_name:
                        svc_name = svc.__class__.__name__
                    # Clean up the name
                    svc_name = svc_name.replace("Service", "").replace("_", " ").strip()
                    if svc_name and svc_name not in subscribers:
                        subscribers.append(svc_name)
        except Exception as e:
            logger.debug(f"Could not get WA subscribers: {e}")

        response = WAStatusResponse(
            service_healthy=is_healthy,
            active_was=active_was,
            pending_deferrals=len(pending_deferrals),
            deferrals_24h=len(pending_deferrals),
            average_resolution_time_minutes=0.0,
            timestamp=datetime.now(timezone.utc),
            subscribers=subscribers,
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
