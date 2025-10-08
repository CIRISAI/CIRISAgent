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

from ..dependencies.auth import require_observer

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/billing", tags=["billing"])


# Request/Response schemas


class CreditStatusResponse(BaseModel):
    """Credit status for frontend display."""

    has_credit: bool = Field(..., description="Whether user has available credit")
    credits_remaining: int = Field(..., description="Remaining paid credits")
    free_uses_remaining: int = Field(..., description="Remaining free uses")
    total_uses: int = Field(..., description="Total uses so far")
    plan_name: Optional[str] = Field(None, description="Current plan name")
    purchase_required: bool = Field(..., description="Whether purchase is required to continue")
    purchase_options: Optional[Dict[str, Any]] = Field(None, description="Purchase options if required")


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
        client = httpx.AsyncClient(base_url=billing_url, timeout=10.0)
        request.app.state.billing_client = client
    client: httpx.AsyncClient = request.app.state.billing_client
    return client


def _get_stripe_publishable_key() -> str:
    """Get Stripe publishable key from environment."""
    import os

    key = os.getenv("STRIPE_PUBLISHABLE_KEY")
    if not key:
        raise HTTPException(status_code=500, detail="Stripe not configured")
    return key


def _extract_user_identity(auth: AuthContext) -> Dict[str, Any]:
    """Extract user identity from auth context."""
    # TODO: Map auth context to OAuth provider/external_id
    # For now, use user_id as external_id
    return {
        "oauth_provider": "api:internal",  # Or extract from auth context
        "external_id": auth.user_id,
        "wa_id": auth.user_id,
        "tenant_id": None,
    }


# Endpoints


@router.get("/credits", response_model=CreditStatusResponse)
async def get_credits(
    request: Request,
    auth: AuthContext = Depends(require_observer),
) -> CreditStatusResponse:
    """
    Get user's credit balance and status.

    This endpoint proxies to the billing backend. The frontend calls this
    to display credit status and determine if purchase is needed.
    """
    billing_client = _get_billing_client(request)
    user_identity = _extract_user_identity(auth)

    try:
        # Check credit via billing backend
        response = await billing_client.post(
            "/v1/billing/credits/check",
            json={
                **user_identity,
                "context": {
                    "agent_id": request.app.state.runtime.agent_identity.agent_id
                    if hasattr(request.app.state, "runtime")
                    else "unknown",
                    "source": "frontend_credit_display",
                },
            },
        )
        response.raise_for_status()
        credit_data = response.json()

    except httpx.HTTPStatusError as e:
        logger.error(f"Billing API error: {e.response.status_code} - {e.response.text}")
        raise HTTPException(status_code=503, detail="Billing service unavailable")
    except httpx.RequestError as e:
        logger.error(f"Billing API request error: {e}")
        raise HTTPException(status_code=503, detail="Cannot reach billing service")

    # Format response for frontend
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


@router.post("/purchase/initiate", response_model=PurchaseInitiateResponse)
async def initiate_purchase(
    request: Request,
    body: PurchaseInitiateRequest,
    auth: AuthContext = Depends(require_observer),
) -> PurchaseInitiateResponse:
    """
    Initiate credit purchase (creates Stripe payment intent).

    This endpoint proxies to the billing backend to create a payment intent.
    The frontend receives the client_secret to complete payment with Stripe.js.
    """
    billing_client = _get_billing_client(request)
    user_identity = _extract_user_identity(auth)

    # Get user email (needed for Stripe)
    # TODO: Extract from auth context or user profile
    customer_email = f"{auth.user_id}@ciris.ai"  # Placeholder

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
    """
    # For now, just check current credit balance
    # In a full implementation, would verify the specific payment with Stripe
    billing_client = _get_billing_client(request)
    user_identity = _extract_user_identity(auth)

    try:
        # Get updated credit balance
        response = await billing_client.post(
            "/v1/billing/credits/check",
            json={
                **user_identity,
                "context": {"source": "purchase_status_check"},
            },
        )
        response.raise_for_status()
        credit_data = response.json()

    except (httpx.HTTPStatusError, httpx.RequestError) as e:
        logger.error(f"Billing API error: {e}")
        raise HTTPException(status_code=503, detail="Billing service unavailable")

    # TODO: Query Stripe or billing backend for specific payment status
    # For now, return generic success if credits exist
    has_credits = credit_data.get("credits_remaining", 0) > 0

    return PurchaseStatusResponse(
        status="succeeded" if has_credits else "pending",
        credits_added=20 if has_credits else 0,  # TODO: Get actual amount from payment record
        balance_after=credit_data.get("credits_remaining"),
    )
