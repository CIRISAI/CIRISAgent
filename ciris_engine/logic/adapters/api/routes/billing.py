"""
Billing endpoints for CIRIS API.

Frontend proxy endpoints to CIRIS Billing backend.
Frontend should NEVER call the billing backend directly.
"""

import logging
import re
from typing import Any, Dict, Optional
from urllib.parse import quote

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from ciris_engine.config.ciris_services import get_billing_url
from ciris_engine.schemas.api.auth import AuthContext
from ciris_engine.schemas.types import JSONDict

from ..dependencies.auth import require_observer

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/billing", tags=["billing"])


# Error message constants (avoid duplication)
ERROR_RESOURCE_MONITOR_UNAVAILABLE = "Resource monitor not available"
ERROR_CREDIT_PROVIDER_NOT_CONFIGURED = "Credit provider not configured"
ERROR_BILLING_SERVICE_UNAVAILABLE = "Billing service unavailable"
ERROR_INVALID_PAYMENT_ID = "Invalid payment ID format"

# Regex pattern for valid payment IDs (Stripe format: pi_xxx or similar alphanumeric with underscores)
PAYMENT_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_-]{1,128}$")


# Request/Response schemas


class CreditStatusResponse(BaseModel):
    """Credit status for frontend display."""

    has_credit: bool = Field(..., description="Whether user has available credit")
    credits_remaining: int = Field(..., description="Remaining paid credits")
    free_uses_remaining: int = Field(..., description="Remaining free uses")
    daily_free_uses_remaining: int = Field(0, description="Remaining daily free uses")
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


class TransactionItem(BaseModel):
    """Individual transaction (charge or credit)."""

    transaction_id: str = Field(..., description="Unique transaction ID")
    type: str = Field(..., description="Transaction type: charge or credit")
    amount_minor: int = Field(..., description="Amount in minor units (negative for charges, positive for credits)")
    currency: str = Field(..., description="Currency code (USD)")
    description: str = Field(..., description="Transaction description")
    created_at: str = Field(..., description="Transaction timestamp (ISO format)")
    balance_after: int = Field(..., description="Account balance after this transaction")
    metadata: Optional[JSONDict] = Field(None, description="Additional metadata for charges")
    transaction_type: Optional[str] = Field(None, description="Type of credit transaction (purchase, refund, etc)")
    external_transaction_id: Optional[str] = Field(
        None, description="External payment ID (e.g., Stripe payment intent)"
    )


class TransactionListResponse(BaseModel):
    """Transaction history response."""

    transactions: list[TransactionItem] = Field(..., description="List of transactions")
    total_count: int = Field(..., description="Total number of transactions")
    has_more: bool = Field(..., description="Whether more transactions are available")


# Helper functions


def _get_billing_client(request: Request, google_id_token: Optional[str] = None) -> httpx.AsyncClient:
    """Get billing API client from app state.

    Supports two authentication modes:
    1. Server mode: Uses CIRIS_BILLING_API_KEY env var (for agents.ciris.ai)
    2. JWT pass-through mode: Uses Google ID token from request (for Android/native)

    Args:
        request: FastAPI request object
        google_id_token: Optional Google ID token for JWT pass-through mode
    """
    import os

    # Check if billing client already exists in app state (for testing or pre-configured)
    if hasattr(request.app.state, "billing_client") and request.app.state.billing_client is not None:
        existing_client: httpx.AsyncClient = request.app.state.billing_client
        return existing_client

    billing_url = get_billing_url()
    api_key = os.getenv("CIRIS_BILLING_API_KEY")

    # Determine authentication mode
    if api_key:
        # Server mode: use API key (cached client)
        if not hasattr(request.app.state, "billing_client"):
            headers = {
                "X-API-Key": api_key,
                "User-Agent": "CIRIS-Agent-Frontend/1.0",
            }
            new_client = httpx.AsyncClient(base_url=billing_url, timeout=10.0, headers=headers)
            request.app.state.billing_client = new_client
        client: httpx.AsyncClient = request.app.state.billing_client
        return client
    elif google_id_token:
        # JWT pass-through mode: create new client with Google ID token as Bearer
        # Don't cache this client since token changes per request
        headers = {
            "Authorization": f"Bearer {google_id_token}",
            "User-Agent": "CIRIS-Mobile/1.0",
        }
        logger.info(
            f"[BILLING_JWT] Creating JWT pass-through client with Google ID token ({len(google_id_token)} chars)"
        )
        return httpx.AsyncClient(base_url=billing_url, timeout=10.0, headers=headers)
    else:
        raise HTTPException(
            status_code=500,
            detail="Billing not configured: set CIRIS_BILLING_API_KEY or provide X-Google-ID-Token header",
        )


def _extract_user_identity(auth: AuthContext, request: Request) -> JSONDict:
    """Extract user identity from auth context including marketing opt-in preference and email."""
    # Extract user information from auth service
    marketing_opt_in = False
    user_email = None
    oauth_provider = None
    external_id = None

    if hasattr(request.app.state, "auth_service") and request.app.state.auth_service is not None:
        auth_service = request.app.state.auth_service
        user = auth_service.get_user(auth.user_id)
        if user:
            marketing_opt_in = user.marketing_opt_in
            user_email = user.oauth_email
            # Get OAuth provider and external_id from user object (stored in database)
            if user.oauth_provider and user.oauth_external_id:
                oauth_provider = user.oauth_provider
                external_id = user.oauth_external_id

    # Fallback: Try to parse from user_id format (e.g., "google:115300315355793131383")
    if not oauth_provider or not external_id:
        if ":" in auth.user_id and not auth.user_id.startswith("wa-"):
            parts = auth.user_id.split(":", 1)
            oauth_provider = parts[0]  # e.g., "google", "discord"
            external_id = parts[1]  # e.g., "115300315355793131383"
        else:
            # Internal/API user without OAuth
            oauth_provider = "api:internal"
            external_id = auth.user_id

    # Format oauth_provider with "oauth:" prefix for billing backend
    if not oauth_provider.startswith("oauth:"):
        oauth_provider = f"oauth:{oauth_provider}"

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
        f"[BILLING_IDENTITY] Extracted identity: has_provider={oauth_provider is not None}, "
        f"has_external_id={external_id is not None}, has_email={user_email is not None}, "
        f"marketing_opt_in={marketing_opt_in}"
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
        daily_free_uses_remaining=credit_data.get("daily_free_uses_remaining", 0),
        total_uses=credit_data.get("total_uses", 0),
        plan_name=credit_data.get("plan_name"),
        purchase_required=credit_data.get("purchase_required", False),
        purchase_options=purchase_options,
    )


def _get_agent_id(request: Request) -> str:
    """Extract agent_id from request runtime."""
    if hasattr(request.app.state, "runtime") and request.app.state.runtime.agent_identity:
        agent_id: str = request.app.state.runtime.agent_identity.agent_id
        return agent_id
    return "pending"


def _get_credit_provider(request: Request) -> Optional[Any]:
    """Get credit provider from resource monitor, lazily initializing if token is available.

    This enables the billing provider to be created when:
    1. Server starts without token
    2. User logs in (Kotlin writes token to .env)
    3. Next API call triggers lazy initialization

    Returns:
        Credit provider instance or None if unavailable and no token to initialize.
    """
    if not hasattr(request.app.state, "resource_monitor"):
        return None
    resource_monitor = request.app.state.resource_monitor
    if not hasattr(resource_monitor, "credit_provider"):
        return None

    # Return existing provider if available
    if resource_monitor.credit_provider is not None:
        return resource_monitor.credit_provider

    # Lazy initialization: Try to create billing provider if token is now available
    return _try_lazy_init_billing_provider(request, resource_monitor)


def _try_lazy_init_billing_provider(request: Request, resource_monitor: Any) -> Optional[Any]:
    """Attempt to lazily initialize the billing provider if a token is now available.

    This handles the case where the Python server starts before the user logs in,
    and the token is written to .env after server startup.

    Args:
        request: FastAPI request with app state
        resource_monitor: Resource monitor instance to attach provider to

    Returns:
        Newly created billing provider or None if initialization fails
    """
    import os

    from dotenv import load_dotenv

    from ciris_engine.logic.services.infrastructure.resource_monitor.ciris_billing_provider import CIRISBillingProvider

    # Reload .env to pick up any new values written by Kotlin
    ciris_home = os.environ.get("CIRIS_HOME", "")
    if ciris_home:
        env_path = os.path.join(ciris_home, ".env")
        if os.path.exists(env_path):
            load_dotenv(env_path, override=True)
            logger.debug("[BILLING_LAZY_INIT] Reloaded .env from %s", env_path)

    # Check for Google ID token (written by Kotlin when user logs in)
    google_token = os.environ.get("CIRIS_BILLING_GOOGLE_ID_TOKEN", "")
    if not google_token:
        logger.debug("[BILLING_LAZY_INIT] No CIRIS_BILLING_GOOGLE_ID_TOKEN in environment")
        return None

    # Get billing URL from central config (checks env var first)
    billing_url = get_billing_url()

    logger.info(
        "[BILLING_LAZY_INIT] Token found (%d chars), creating CIRISBillingProvider...",
        len(google_token),
    )

    try:
        # Create the billing provider with JWT auth
        provider = CIRISBillingProvider(
            google_id_token=google_token,
            base_url=billing_url,
            fail_open=False,  # Don't fail open - we want accurate billing status
            cache_ttl_seconds=15,
        )

        # Attach to resource monitor
        resource_monitor.credit_provider = provider
        logger.info(
            "[BILLING_LAZY_INIT] Successfully created CIRISBillingProvider: base_url=%s, token_length=%d",
            billing_url,
            len(google_token),
        )
        return provider

    except Exception as exc:
        logger.error("[BILLING_LAZY_INIT] Failed to create CIRISBillingProvider: %s", exc, exc_info=True)
        return None


def _build_mobile_credit_response(result: Any) -> CreditStatusResponse:
    """Build credit response for mobile/JWT mode (no API key)."""
    return CreditStatusResponse(
        has_credit=result.has_credit,
        credits_remaining=result.credits_remaining or 0,
        free_uses_remaining=result.free_uses_remaining or 0,
        daily_free_uses_remaining=result.daily_free_uses_remaining or 0,
        total_uses=0,
        plan_name="CIRIS Mobile",
        purchase_required=not result.has_credit,
        purchase_options={"price_minor": 499, "uses": 100, "currency": "USD"} if not result.has_credit else None,
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
    import os

    from ciris_engine.logic.adapters.api.routes.agent import _derive_credit_account
    from ciris_engine.schemas.services.credit_gate import CreditContext

    logger.info("[BILLING_API] get_credits called for user_id=%s", auth.user_id)
    user_identity = _extract_user_identity(auth, request)
    agent_id = _get_agent_id(request)
    logger.info("[BILLING_API] agent_id=%s, user_identity=%s", agent_id, user_identity)

    # Check credit provider availability
    credit_provider = _get_credit_provider(request)
    if credit_provider is None:
        if not hasattr(request.app.state, "resource_monitor"):
            logger.error("[BILLING_API] No resource_monitor on app.state")
            raise HTTPException(status_code=503, detail=ERROR_RESOURCE_MONITOR_UNAVAILABLE)
        logger.info("[BILLING_API] No credit provider, returning unlimited response")
        return _get_unlimited_credit_response()

    # Query credit provider
    resource_monitor = request.app.state.resource_monitor
    account, _ = _derive_credit_account(auth, request)
    context = CreditContext(agent_id=agent_id, channel_id="api:frontend", request_id=None)

    try:
        result = await resource_monitor.check_credit(account, context)
    except Exception as e:
        logger.error("Credit check error: %s", e, exc_info=True)
        raise HTTPException(status_code=503, detail=f"Credit check failed: {type(e).__name__}: {e!s}")

    # Handle SimpleCreditProvider
    if credit_provider.__class__.__name__ == "SimpleCreditProvider":
        return _get_simple_provider_response(result.has_credit)

    # CIRISBillingProvider: mobile mode (no API key) or server mode
    if not os.getenv("CIRIS_BILLING_API_KEY"):
        logger.info(
            "[BILLING_CREDITS] Using CreditCheckResult (no API key): " "free=%s, paid=%s, has_credit=%s",
            result.free_uses_remaining,
            result.credits_remaining,
            result.has_credit,
        )
        return _build_mobile_credit_response(result)

    # Server mode with API key - query billing backend
    billing_client = _get_billing_client(request)
    credit_data = await _query_billing_backend(billing_client, _build_credit_check_payload(user_identity, context))
    response = _format_billing_response(credit_data)
    logger.info(
        "[BILLING_CREDITS] Credit check complete: free=%s, paid=%s, has_credit=%s",
        response.free_uses_remaining,
        response.credits_remaining,
        response.has_credit,
    )
    return response


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
    agent_id = (
        request.app.state.runtime.agent_identity.agent_id
        if hasattr(request.app.state, "runtime") and request.app.state.runtime.agent_identity
        else "pending"
    )

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

    # Get Stripe publishable key from billing backend response (single source of truth)
    publishable_key = purchase_data.get("publishable_key", "pk_test_not_configured")

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
    # Validate payment_id to prevent path traversal attacks
    if not PAYMENT_ID_PATTERN.match(payment_id):
        raise HTTPException(status_code=400, detail=ERROR_INVALID_PAYMENT_ID)

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
        # URL-encode payment_id to prevent path traversal (already validated by PAYMENT_ID_PATTERN)
        safe_payment_id = quote(payment_id, safe="")
        payment_response = await billing_client.get(
            f"/v1/billing/purchases/{safe_payment_id}/status",
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


@router.get("/transactions", response_model=TransactionListResponse)
async def get_transactions(
    request: Request,
    auth: AuthContext = Depends(require_observer),
    limit: int = 50,
    offset: int = 0,
) -> TransactionListResponse:
    """
    Get transaction history for the current user.

    Returns a paginated list of all transactions (charges and credits) in reverse chronological order.

    Only works when CIRIS_BILLING_ENABLED=true (CIRISBillingProvider).
    Returns empty list when SimpleCreditProvider is active (billing disabled).
    """
    # Check if billing is enabled (CIRISBillingProvider vs SimpleCreditProvider)
    if not hasattr(request.app.state, "resource_monitor"):
        raise HTTPException(status_code=503, detail=ERROR_RESOURCE_MONITOR_UNAVAILABLE)

    resource_monitor = request.app.state.resource_monitor

    if not hasattr(resource_monitor, "credit_provider") or resource_monitor.credit_provider is None:
        # No credit provider - return empty list
        return TransactionListResponse(transactions=[], total_count=0, has_more=False)

    is_simple_provider = resource_monitor.credit_provider.__class__.__name__ == "SimpleCreditProvider"

    if is_simple_provider:
        # SimpleCreditProvider doesn't track transactions - return empty list
        return TransactionListResponse(transactions=[], total_count=0, has_more=False)

    # CIRISBillingProvider - query billing backend for transaction history
    logger.info(f"[BILLING_TRANSACTIONS] Fetching transactions (limit={limit}, offset={offset})")
    billing_client = _get_billing_client(request)
    user_identity = _extract_user_identity(auth, request)

    try:
        from typing import Mapping, cast

        # Build query parameters for billing backend - cast to expected types
        oauth_provider = str(user_identity["oauth_provider"])
        external_id = str(user_identity["external_id"])

        params: dict[str, str | int] = {
            "oauth_provider": oauth_provider,
            "external_id": external_id,
            "limit": limit,
            "offset": offset,
        }

        # Add optional parameters if present
        wa_id = user_identity.get("wa_id")
        if wa_id:
            params["wa_id"] = str(wa_id)
        tenant_id = user_identity.get("tenant_id")
        if tenant_id:
            params["tenant_id"] = str(tenant_id)

        # Log request details for debugging (without PII)
        logger.debug(
            f"[BILLING_TRANSACTIONS] Request to billing backend: "
            f"oauth_provider={params.get('oauth_provider')}, "
            f"external_id={params.get('external_id')}, "
            f"wa_id={params.get('wa_id')}, "
            f"has_email={user_identity.get('customer_email') is not None}"
        )

        # Query billing backend
        response = await billing_client.get(
            "/v1/billing/transactions",
            params=cast(Mapping[str, str | int | float | bool | None], params),
        )
        response.raise_for_status()
        transaction_data: JSONDict = response.json()

        # Map backend response to our schema - safely extract and validate transactions list
        transactions_raw = transaction_data.get("transactions", [])
        if not isinstance(transactions_raw, list):
            transactions_raw = []
        transactions = [TransactionItem(**txn) for txn in transactions_raw if isinstance(txn, dict)]

        logger.info(
            f"[BILLING_TRANSACTIONS] Returning {len(transactions)} transactions "
            f"(total={transaction_data.get('total_count', 0)}, has_more={transaction_data.get('has_more', False)})"
        )
        return TransactionListResponse(
            transactions=transactions,
            total_count=transaction_data.get("total_count", 0),
            has_more=transaction_data.get("has_more", False),
        )

    except httpx.HTTPStatusError as e:
        # Safely extract request details for logging
        try:
            headers_str = str(dict(e.request.headers))
        except (TypeError, AttributeError):
            headers_str = "<unavailable>"

        logger.error(
            f"Billing API error fetching transactions: {e.response.status_code} - {e.response.text}\n"
            f"Request URL: {e.request.url}\n"
            f"Request headers: {headers_str}"
        )
        if e.response.status_code == 404:
            # Account not found - return empty list
            return TransactionListResponse(transactions=[], total_count=0, has_more=False)
        if e.response.status_code == 401:
            # Authentication failed - log details and return empty
            logger.error("401 Unauthorized - API key may be invalid or missing")
            return TransactionListResponse(transactions=[], total_count=0, has_more=False)
        raise HTTPException(status_code=503, detail=ERROR_BILLING_SERVICE_UNAVAILABLE)
    except httpx.RequestError as e:
        logger.error(f"Billing API request error: {e}")
        raise HTTPException(status_code=503, detail=ERROR_BILLING_SERVICE_UNAVAILABLE)


# Google Play verification models


class GooglePlayVerifyRequest(BaseModel):
    """Request to verify a Google Play purchase."""

    purchase_token: str = Field(..., description="Google Play purchase token")
    product_id: str = Field(..., description="Product SKU (e.g., 'credits_100')")
    package_name: str = Field(..., description="App package name")


class GooglePlayVerifyResponse(BaseModel):
    """Response from Google Play purchase verification."""

    success: bool = Field(..., description="Whether verification succeeded")
    credits_added: int = Field(0, description="Credits added from this purchase")
    new_balance: int = Field(0, description="New credit balance after purchase")
    already_processed: bool = Field(False, description="Whether purchase was already processed")
    error: Optional[str] = Field(None, description="Error message if verification failed")


@router.post("/google-play/verify", response_model=GooglePlayVerifyResponse)
async def verify_google_play_purchase(
    request: Request,
    body: GooglePlayVerifyRequest,
    auth: AuthContext = Depends(require_observer),
) -> GooglePlayVerifyResponse:
    """
    Verify a Google Play purchase and add credits.

    This endpoint proxies the verification request to the billing backend,
    which validates the purchase token with Google Play and adds credits.

    Supports two authentication modes:
    1. Server mode: Uses CIRIS_BILLING_API_KEY (agents.ciris.ai)
    2. JWT pass-through: Uses Bearer token from request (Android/native)

    Only works when CIRISBillingProvider is configured.
    """
    logger.info(f"[GOOGLE_PLAY_VERIFY] Verifying purchase for user_id={auth.user_id}, product={body.product_id}")

    # Check if billing is enabled
    if not hasattr(request.app.state, "resource_monitor"):
        return GooglePlayVerifyResponse(success=False, error=ERROR_RESOURCE_MONITOR_UNAVAILABLE)

    resource_monitor = request.app.state.resource_monitor

    if not hasattr(resource_monitor, "credit_provider") or resource_monitor.credit_provider is None:
        return GooglePlayVerifyResponse(success=False, error=ERROR_CREDIT_PROVIDER_NOT_CONFIGURED)

    is_simple_provider = resource_monitor.credit_provider.__class__.__name__ == "SimpleCreditProvider"

    if is_simple_provider:
        return GooglePlayVerifyResponse(
            success=False, error="Google Play purchases not supported - billing backend not configured"
        )

    # Extract user identity for billing backend
    user_identity = _extract_user_identity(auth, request)

    # Build verification request for billing backend
    verify_payload = {
        "oauth_provider": user_identity["oauth_provider"],
        "external_id": user_identity["external_id"],
        "email": user_identity.get("customer_email"),
        "display_name": None,  # Not needed for verification
        "purchase_token": body.purchase_token,
        "product_id": body.product_id,
        "package_name": body.package_name,
    }

    logger.info(
        f"[GOOGLE_PLAY_VERIFY] Sending to billing backend: oauth_provider={verify_payload['oauth_provider']}"
    )  # NOSONAR - provider type not secret

    # Get Google ID token for JWT pass-through mode (Android/native)
    # Android sends this in X-Google-ID-Token header for billing backend auth
    google_id_token = request.headers.get("X-Google-ID-Token")
    if google_id_token:
        logger.info(f"[GOOGLE_PLAY_VERIFY] Using JWT pass-through with Google ID token ({len(google_id_token)} chars)")
    billing_client = _get_billing_client(request, google_id_token=google_id_token)

    try:
        response = await billing_client.post(
            "/v1/billing/google-play/verify",
            json=verify_payload,
        )
        response.raise_for_status()
        result = response.json()

        logger.info(
            f"[GOOGLE_PLAY_VERIFY] Success: credits_added={result.get('credits_added')}, "
            f"new_balance={result.get('new_balance')}, already_processed={result.get('already_processed')}"
        )

        return GooglePlayVerifyResponse(
            success=result.get("success", False),
            credits_added=result.get("credits_added", 0),
            new_balance=result.get("new_balance", 0),
            already_processed=result.get("already_processed", False),
        )

    except httpx.HTTPStatusError as e:
        logger.error(f"[GOOGLE_PLAY_VERIFY] Billing API error: {e.response.status_code} - {e.response.text}")
        return GooglePlayVerifyResponse(success=False, error=f"Verification failed: {e.response.status_code}")
    except httpx.RequestError as e:
        logger.error(f"[GOOGLE_PLAY_VERIFY] Request error: {e}")
        return GooglePlayVerifyResponse(success=False, error=f"Network error: {str(e)}")
