"""
Billing endpoints for CIRIS API.

Frontend proxy endpoints to CIRIS Billing backend.
Frontend should NEVER call the billing backend directly.
"""

import logging
from typing import Any, Dict, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from ciris_engine.schemas.api.auth import AuthContext
from ciris_engine.schemas.types import JSONDict

from ..dependencies.auth import require_observer

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/billing", tags=["billing"])


# Error message constants (avoid duplication)
ERROR_RESOURCE_MONITOR_UNAVAILABLE = "Resource monitor not available"
ERROR_CREDIT_PROVIDER_NOT_CONFIGURED = "Credit provider not configured"
ERROR_BILLING_SERVICE_UNAVAILABLE = "Billing service unavailable"


# Request/Response schemas


class CreditStatusResponse(BaseModel):
    """Credit status for frontend display."""

    has_credit: bool = Field(..., description="Whether user has available credit")
    credits_remaining: int = Field(..., description="Remaining paid credits")
    free_uses_remaining: int = Field(..., description="Remaining free uses")
    total_uses: int = Field(..., description="Total uses so far")
    plan_name: Optional[str] = Field(None, description="Current plan name")
    purchase_required: bool = Field(..., description="Whether purchase is required to continue")
    purchase_options: Optional[JSONDict] = Field(None, description="Purchase options if required")


class PurchaseInitiateRequest(BaseModel):
    """Request to initiate purchase flow."""

    return_url: Optional[str] = Field(None, description="URL to return to after payment")


class PurchaseInitiateResponse(BaseModel):
    """Response with Stripe payment intent."""

    payment_id: str = Field(..., description="Payment intent ID")
    client_secret: str = Field(..., description="Stripe client secret for frontend")
    amount_minor: int = Field(..., description="Amount in minor units (cents)")
    currency: str = Field(..., description="Currency code (USD)")
    uses_purchased: int = Field(..., description="Number of uses being purchased")
    publishable_key: str = Field(..., description="Stripe publishable key")


class PurchaseStatusResponse(BaseModel):
    """Purchase status response."""

    status: str = Field(..., description="Payment status (succeeded, pending, failed)")
    credits_added: int = Field(..., description="Credits added (0 if not completed)")
    balance_after: Optional[int] = Field(None, description="Balance after credits added")


# Helper functions


def _get_billing_client(request: Request) -> httpx.AsyncClient:
    """Get billing API client from app state."""
    if not hasattr(request.app.state, "billing_client"):
        # Create billing client if not exists
        import os

        billing_url = os.getenv("CIRIS_BILLING_API_URL", "https://billing.ciris.ai")
        api_key = os.getenv("CIRIS_BILLING_API_KEY")
        if not api_key:
            raise HTTPException(status_code=500, detail="Billing API key not configured")

        headers = {
            "X-API-Key": api_key,
            "User-Agent": "CIRIS-Agent-Frontend/1.0",
        }
        new_client = httpx.AsyncClient(base_url=billing_url, timeout=10.0, headers=headers)
        request.app.state.billing_client = new_client
    client: httpx.AsyncClient = request.app.state.billing_client
    return client


def _get_stripe_publishable_key() -> str:
    """Get Stripe publishable key from environment."""
    import os

    key = os.getenv("STRIPE_PUBLISHABLE_KEY")
    if not key:
        raise HTTPException(status_code=500, detail="Stripe not configured")
    return key


def _extract_user_identity(auth: AuthContext, request: Request) -> JSONDict:
    """Extract user identity from auth context including marketing opt-in preference and email."""
    # Extract marketing_opt_in and email from user record if available
    marketing_opt_in = False
    user_email = None

    if hasattr(request.app.state, "auth_service") and request.app.state.auth_service is not None:
        auth_service = request.app.state.auth_service
        user = auth_service.get_user(auth.user_id)
        if user:
            marketing_opt_in = user.marketing_opt_in
            # Try to get email from OAuth user data
            user_email = user.oauth_email

    # Parse OAuth provider from user_id format (e.g., "google:115300315355793131383")
    oauth_provider = "oauth:api:internal"
    external_id = auth.user_id

    if ":" in auth.user_id:
        parts = auth.user_id.split(":", 1)
        oauth_provider = f"oauth:{parts[0]}"  # e.g., "oauth:google", "oauth:discord"
        external_id = parts[1]  # e.g., "115300315355793131383"

    identity = {
        "oauth_provider": oauth_provider,
        "external_id": external_id,
        "wa_id": auth.user_id,
        "tenant_id": None,
        "marketing_opt_in": marketing_opt_in,
        "customer_email": user_email,  # CRITICAL: Never use fallback - let validation catch missing email
        "user_role": auth.role.value.lower(),  # Use actual user role from auth context
    }
    logger.debug(
        f"Extracted identity: provider={oauth_provider}, external_id={external_id[:8]}..., has_email={user_email is not None}"
    )
    return identity


# Endpoints


def _get_unlimited_credit_response() -> CreditStatusResponse:
    """Return unlimited credit response when no credit provider configured."""
    return CreditStatusResponse(
        has_credit=True,
        credits_remaining=999,
        free_uses_remaining=999,
        total_uses=0,
        plan_name="unlimited",
        purchase_required=False,
        purchase_options=None,
    )


def _get_simple_provider_response(has_credit: bool) -> CreditStatusResponse:
    """Return credit response for SimpleCreditProvider (1 free use)."""
    if has_credit:
        # Still have free credit
        return CreditStatusResponse(
            has_credit=True,
            credits_remaining=0,
            free_uses_remaining=1,
            total_uses=0,
            plan_name="free",
            purchase_required=False,
            purchase_options=None,
        )
    else:
        # Free credit exhausted, billing not enabled
        return CreditStatusResponse(
            has_credit=False,
            credits_remaining=0,
            free_uses_remaining=0,
            total_uses=1,
            plan_name="free",
            purchase_required=False,  # Can't purchase when billing disabled
            purchase_options={
                "price_minor": 0,
                "uses": 0,
                "currency": "USD",
                "message": "Contact administrator to enable billing",
            },
        )


def _build_credit_check_payload(user_identity: JSONDict, context: Any) -> JSONDict:
    """Build payload for billing backend credit check."""
    check_payload = {
        "oauth_provider": user_identity["oauth_provider"],
        "external_id": user_identity["external_id"],
    }
    if user_identity.get("wa_id"):
        check_payload["wa_id"] = user_identity["wa_id"]
    if user_identity.get("tenant_id"):
        check_payload["tenant_id"] = user_identity["tenant_id"]

    # Add agent_id at top level (not in context)
    check_payload["agent_id"] = context.agent_id

    # Add minimal context
    check_payload["context"] = {
        "channel_id": context.channel_id,
        "request_id": context.request_id,
    }

    return check_payload


async def _query_billing_backend(billing_client: httpx.AsyncClient, check_payload: JSONDict) -> JSONDict:
    """Query billing backend for credit status."""
    try:
        response = await billing_client.post(
            "/v1/billing/credits/check",
            json=check_payload,
        )
        response.raise_for_status()
        result: JSONDict = response.json()
        return result

    except (httpx.HTTPStatusError, httpx.RequestError) as e:
        logger.error(f"Billing API error: {e}", exc_info=True)
        raise HTTPException(status_code=503, detail=ERROR_BILLING_SERVICE_UNAVAILABLE)


def _format_billing_response(credit_data: JSONDict) -> CreditStatusResponse:
    """Format billing backend response for frontend."""
    purchase_options = None
    if credit_data.get("purchase_required"):
        purchase_options = {
            "price_minor": credit_data.get("purchase_price_minor"),
            "uses": credit_data.get("purchase_uses"),
            "currency": "USD",
        }

    return CreditStatusResponse(
        has_credit=credit_data["has_credit"],
        credits_remaining=credit_data.get("credits_remaining", 0),
        free_uses_remaining=credit_data.get("free_uses_remaining", 0),
        total_uses=credit_data.get("total_uses", 0),
        plan_name=credit_data.get("plan_name"),
        purchase_required=credit_data.get("purchase_required", False),
        purchase_options=purchase_options,
    )


@router.get("/credits", response_model=CreditStatusResponse)
async def get_credits(
    request: Request,
    auth: AuthContext = Depends(require_observer),
) -> CreditStatusResponse:
    """
    Get user's credit balance and status.

    Works with both:
    - SimpleCreditProvider (1 free credit per OAuth user, no billing backend needed)
    - CIRISBillingProvider (full billing backend with paid credits)

    The frontend calls this to display credit status.
    """
    user_identity = _extract_user_identity(auth, request)
    agent_id = request.app.state.runtime.agent_identity.agent_id if hasattr(request.app.state, "runtime") else "unknown"
    logger.debug(f"Credit check for user_id={auth.user_id} on agent {agent_id}")

    # Check if we have a resource monitor with credit provider
    if not hasattr(request.app.state, "resource_monitor"):
        raise HTTPException(status_code=503, detail=ERROR_RESOURCE_MONITOR_UNAVAILABLE)

    resource_monitor = request.app.state.resource_monitor

    # Check if credit provider is configured
    if not hasattr(resource_monitor, "credit_provider") or resource_monitor.credit_provider is None:
        return _get_unlimited_credit_response()

    # Query credit provider via resource monitor
    # CRITICAL: Use same credit account derivation as message interactions!
    from ciris_engine.logic.adapters.api.routes.agent import _derive_credit_account
    from ciris_engine.schemas.services.credit_gate import CreditContext

    account, _ = _derive_credit_account(auth, request)

    context = CreditContext(
        agent_id=(
            request.app.state.runtime.agent_identity.agent_id if hasattr(request.app.state, "runtime") else "unknown"
        ),
        channel_id="api:frontend",
        request_id=None,
    )

    try:
        result = await resource_monitor.check_credit(account, context)
    except Exception as e:
        logger.error(f"Credit check error: {e}", exc_info=True)
        raise HTTPException(status_code=503, detail=f"Credit check failed: {type(e).__name__}: {str(e)}")

    # Determine if this is SimpleCreditProvider or CIRISBillingProvider
    is_simple_provider = resource_monitor.credit_provider.__class__.__name__ == "SimpleCreditProvider"

    if is_simple_provider:
        return _get_simple_provider_response(result.has_credit)

    # CIRISBillingProvider: Query billing backend for full details
    billing_client = _get_billing_client(request)
    check_payload = _build_credit_check_payload(user_identity, context)
    credit_data = await _query_billing_backend(billing_client, check_payload)
    return _format_billing_response(credit_data)


@router.post("/purchase/initiate", response_model=PurchaseInitiateResponse)
async def initiate_purchase(
    request: Request,
    body: PurchaseInitiateRequest,
    auth: AuthContext = Depends(require_observer),
) -> PurchaseInitiateResponse:
    """
    Initiate credit purchase (creates Stripe payment intent).

    Only works when CIRIS_BILLING_ENABLED=true (CIRISBillingProvider).
    Returns error when SimpleCreditProvider is active (billing disabled).
    """
    # Check if billing is enabled (CIRISBillingProvider vs SimpleCreditProvider)
    if not hasattr(request.app.state, "resource_monitor"):
        raise HTTPException(status_code=503, detail=ERROR_RESOURCE_MONITOR_UNAVAILABLE)

    resource_monitor = request.app.state.resource_monitor

    if not hasattr(resource_monitor, "credit_provider") or resource_monitor.credit_provider is None:
        raise HTTPException(status_code=503, detail=ERROR_CREDIT_PROVIDER_NOT_CONFIGURED)

    is_simple_provider = resource_monitor.credit_provider.__class__.__name__ == "SimpleCreditProvider"

    if is_simple_provider:
        # Billing not enabled - can't purchase
        raise HTTPException(
            status_code=403,
            detail="Billing not enabled. Contact administrator to enable paid credits.",
        )

    # Billing enabled - proceed with purchase
    billing_client = _get_billing_client(request)
    user_identity = _extract_user_identity(auth, request)
    agent_id = request.app.state.runtime.agent_identity.agent_id if hasattr(request.app.state, "runtime") else "unknown"

    # Get user email (needed for Stripe) - extract from OAuth profile
    customer_email = user_identity.get("customer_email")
    logger.debug(f"Purchase initiate for user_id={auth.user_id} on agent {agent_id}")
    if not customer_email:
        raise HTTPException(
            status_code=400,
            detail="Email address required for purchase. Please authenticate with OAuth provider.",
        )

    try:
        # Create payment intent via billing backend
        response = await billing_client.post(
            "/v1/billing/purchases",
            json={
                **user_identity,
                "customer_email": customer_email,
                "return_url": body.return_url,
            },
        )
        response.raise_for_status()
        purchase_data = response.json()

    except httpx.HTTPStatusError as e:
        logger.error(f"Billing API error: {e.response.status_code} - {e.response.text}")
        if e.response.status_code == 400:
            raise HTTPException(status_code=400, detail="Invalid purchase request")
        raise HTTPException(status_code=503, detail="Billing service unavailable")
    except httpx.RequestError as e:
        logger.error(f"Billing API request error: {e}")
        raise HTTPException(status_code=503, detail="Cannot reach billing service")

    # Get Stripe publishable key for frontend
    try:
        publishable_key = _get_stripe_publishable_key()
    except HTTPException:
        # If Stripe not configured, still return payment intent data
        publishable_key = "pk_test_not_configured"

    return PurchaseInitiateResponse(
        payment_id=purchase_data["payment_id"],
        client_secret=purchase_data["client_secret"],
        amount_minor=purchase_data["amount_minor"],
        currency=purchase_data["currency"],
        uses_purchased=purchase_data["uses_purchased"],
        publishable_key=publishable_key,
    )


@router.get("/purchase/status/{payment_id}", response_model=PurchaseStatusResponse)
async def get_purchase_status(
    payment_id: str,
    request: Request,
    auth: AuthContext = Depends(require_observer),
) -> PurchaseStatusResponse:
    """
    Check payment status (optional - for polling after payment).

    Frontend can poll this after initiating payment to confirm credits were added.
    Only works when CIRIS_BILLING_ENABLED=true (CIRISBillingProvider).
    """
    # Check if billing is enabled
    if not hasattr(request.app.state, "resource_monitor"):
        raise HTTPException(status_code=503, detail=ERROR_RESOURCE_MONITOR_UNAVAILABLE)

    resource_monitor = request.app.state.resource_monitor

    if not hasattr(resource_monitor, "credit_provider") or resource_monitor.credit_provider is None:
        raise HTTPException(status_code=503, detail=ERROR_CREDIT_PROVIDER_NOT_CONFIGURED)

    is_simple_provider = resource_monitor.credit_provider.__class__.__name__ == "SimpleCreditProvider"

    if is_simple_provider:
        # No purchases possible with SimpleCreditProvider
        raise HTTPException(
            status_code=404,
            detail="Payment not found. Billing not enabled.",
        )

    # Billing enabled - check payment status
    billing_client = _get_billing_client(request)
    user_identity = _extract_user_identity(auth, request)

    payment_data = None
    credit_data = None

    try:
        from typing import Mapping, cast

        # Query billing backend for specific payment status
        payment_response = await billing_client.get(
            f"/v1/billing/purchases/{payment_id}/status",
            params=cast(Mapping[str, str | int | float | bool | None], user_identity),
        )
        payment_response.raise_for_status()
        payment_data = payment_response.json()

        # Get updated credit balance
        credits_response = await billing_client.post(
            "/v1/billing/credits/check",
            json={
                **user_identity,
                "context": {"source": "purchase_status_check"},
            },
        )
        credits_response.raise_for_status()
        credit_data = credits_response.json()

    except httpx.HTTPStatusError as e:
        # If payment not found, return pending status
        if e.response.status_code == 404:
            return PurchaseStatusResponse(
                status="pending",
                credits_added=0,
                balance_after=None,
            )
        logger.error(f"Billing API error: {e}")
        raise HTTPException(status_code=503, detail=ERROR_BILLING_SERVICE_UNAVAILABLE)
    except httpx.RequestError as e:
        logger.error(f"Billing API request error: {e}")
        raise HTTPException(status_code=503, detail=ERROR_BILLING_SERVICE_UNAVAILABLE)

    # Extract payment status and amount from billing backend response
    payment_status = payment_data.get("status", "unknown")
    credits_added = payment_data.get("credits_added", 0)

    return PurchaseStatusResponse(
        status=payment_status,
        credits_added=credits_added,
        balance_after=credit_data.get("credits_remaining"),
    )
