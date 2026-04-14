"""
Billing endpoints for CIRIS API.

Frontend proxy endpoints to CIRIS Billing backend.
Frontend should NEVER call the billing backend directly.
"""

import logging
import re
from typing import Any, Dict, Optional
from urllib.parse import quote, urlparse

import aiohttp
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from ciris_engine.config.ciris_services import get_billing_url
from ciris_engine.schemas.api.auth import AuthContext
from ciris_engine.schemas.types import JSONDict

from ._common import (
    RESPONSES_BILLING_503,
    RESPONSES_BILLING_PURCHASE_INITIATE,
    RESPONSES_BILLING_PURCHASE_STATUS,
    AuthObserverDep,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/billing", tags=["billing"])


# Error message constants (avoid duplication)
ERROR_RESOURCE_MONITOR_UNAVAILABLE = "Resource monitor not available"
ERROR_CREDIT_PROVIDER_NOT_CONFIGURED = "Credit provider not configured"
ERROR_BILLING_SERVICE_UNAVAILABLE = "Billing service unavailable"
ERROR_INVALID_PAYMENT_ID = "Invalid payment ID format"

# Regex pattern for valid payment IDs (Stripe format: pi_xxx or similar alphanumeric with underscores)
PAYMENT_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_-]{1,128}$")


def _sanitize_for_log(value: str, max_length: int = 64) -> str:
    """Sanitize user-controlled data for safe logging.

    Prevents log injection by:
    1. Removing newlines and control characters
    2. Truncating to max_length
    3. Escaping special characters
    """
    if not value:
        return "<empty>"
    # Remove control characters (C0: 0x00-0x1f, DEL+C1: 0x7f-0x9f)
    sanitized = re.sub(r"[\x00-\x1f\x7f-\x9f]", "", str(value))
    # Truncate to prevent log flooding
    if len(sanitized) > max_length:
        sanitized = sanitized[:max_length] + "..."
    return sanitized


# Trusted billing service hosts (prevents SSRF via env var manipulation)
_TRUSTED_BILLING_HOSTS_EXACT = frozenset({"billing.ciris.ai", "localhost", "127.0.0.1"})

# Pattern for CIRIS services hosts: billing*.ciris-services-N.ai where N is 1-99
_CIRIS_SERVICES_PATTERN = re.compile(r"^billing\d*\.ciris-services-\d{1,2}\.ai$")


def _is_trusted_billing_host(hostname: str | None) -> bool:
    """Check if hostname is a trusted billing service host.

    Trusted hosts:
    - billing.ciris.ai
    - localhost, 127.0.0.1
    - billing*.ciris-services-N.ai (where N is 1-99)
    """
    if hostname is None:
        return False
    if hostname in _TRUSTED_BILLING_HOSTS_EXACT:
        return True
    if _CIRIS_SERVICES_PATTERN.match(hostname):
        return True
    return False


def _validate_billing_url(url: str) -> str:
    """Validate billing URL to prevent SSRF attacks.

    Ensures the URL:
    1. Is well-formed
    2. Uses HTTPS (or HTTP for localhost only)
    3. Points to a trusted billing host

    Args:
        url: The billing URL to validate

    Returns:
        The validated URL

    Raises:
        ValueError: If URL is invalid or points to untrusted host
    """
    try:
        parsed = urlparse(url)
    except Exception as e:
        raise ValueError(f"Invalid billing URL format: {e}") from e

    # Require valid scheme
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"Invalid billing URL scheme: {parsed.scheme}")

    # Require HTTPS for non-localhost
    if parsed.scheme == "http" and parsed.hostname not in ("localhost", "127.0.0.1"):
        raise ValueError("Billing URL must use HTTPS for non-localhost hosts")

    # Validate against trusted hosts
    if not _is_trusted_billing_host(parsed.hostname):
        raise ValueError(f"Untrusted billing host: {parsed.hostname}")

    return url


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


def _get_billing_config(request: Request, google_id_token: Optional[str] = None) -> tuple[str, Dict[str, str]]:
    """Get billing API configuration (base URL and headers).

    Supports two authentication modes:
    1. Server mode: Uses CIRIS_BILLING_API_KEY env var (for agents.ciris.ai)
    2. JWT pass-through mode: Uses Google ID token from request (for Android/native)

    Args:
        request: FastAPI request object
        google_id_token: Optional Google ID token for JWT pass-through mode

    Returns:
        Tuple of (base_url, headers)
    """
    import os

    # Get and validate billing URL to prevent SSRF
    billing_url_raw = get_billing_url()
    try:
        billing_url = _validate_billing_url(billing_url_raw)
    except ValueError as e:
        logger.error(f"[BILLING] Invalid billing URL configuration: {e}")
        raise HTTPException(status_code=500, detail="Billing service misconfigured") from e

    api_key = os.getenv("CIRIS_BILLING_API_KEY")

    # Determine authentication mode
    if api_key:
        # Server mode: use API key
        headers = {
            "X-API-Key": api_key,
            "User-Agent": "CIRIS-Agent-Frontend/1.0",
        }
        return billing_url, headers
    elif google_id_token:
        # JWT pass-through mode: use Google ID token as Bearer
        headers = {
            "Authorization": f"Bearer {google_id_token}",
            "User-Agent": "CIRIS-Mobile/1.0",
        }
        logger.info(
            f"[BILLING_JWT] Creating JWT pass-through config with Google ID token ({len(google_id_token)} chars)"
        )
        return billing_url, headers
    else:
        raise HTTPException(
            status_code=500,
            detail="Billing not configured: set CIRIS_BILLING_API_KEY or provide X-Google-ID-Token header",
        )


async def _billing_post(base_url: str, path: str, headers: Dict[str, str], json_data: JSONDict) -> JSONDict:
    """Make a POST request to the billing API.

    Args:
        base_url: Base URL for billing API
        path: API path (e.g., "/v1/billing/credits/check")
        headers: HTTP headers including auth
        json_data: JSON payload

    Returns:
        JSON response as dict

    Raises:
        HTTPException: On HTTP errors or network failures
    """
    timeout = aiohttp.ClientTimeout(total=10.0)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        url = f"{base_url}{path}"
        try:
            async with session.post(url, json=json_data, headers=headers) as response:
                if response.status >= 400:
                    error_text = await response.text()
                    if response.status == 400:
                        raise HTTPException(status_code=400, detail="Invalid request")
                    elif response.status == 401:
                        logger.error("401 Unauthorized - API key may be invalid or missing")
                        raise HTTPException(status_code=503, detail=ERROR_BILLING_SERVICE_UNAVAILABLE)
                    elif response.status == 404:
                        raise HTTPException(status_code=404, detail="Not found")
                    else:
                        logger.error(f"Billing API error: {response.status} - {error_text}")
                        raise HTTPException(status_code=503, detail=ERROR_BILLING_SERVICE_UNAVAILABLE)
                result: JSONDict = await response.json()
                return result
        except aiohttp.ClientError as e:
            logger.error(f"Billing API request error: {e}")
            raise HTTPException(status_code=503, detail=ERROR_BILLING_SERVICE_UNAVAILABLE)


async def _billing_get(
    base_url: str, path: str, headers: Dict[str, str], params: Optional[Dict[str, Any]] = None
) -> JSONDict:
    """Make a GET request to the billing API.

    Args:
        base_url: Base URL for billing API
        path: API path (e.g., "/v1/billing/transactions")
        headers: HTTP headers including auth
        params: Optional query parameters

    Returns:
        JSON response as dict

    Raises:
        HTTPException: On HTTP errors or network failures
    """
    timeout = aiohttp.ClientTimeout(total=10.0)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        url = f"{base_url}{path}"
        try:
            async with session.get(url, params=params, headers=headers) as response:
                if response.status >= 400:
                    error_text = await response.text()
                    if response.status == 401:
                        logger.error("401 Unauthorized - API key may be invalid or missing")
                    elif response.status == 404:
                        # Return empty response for 404 (account/payment not found)
                        return {"transactions": [], "total_count": 0, "has_more": False}
                    else:
                        logger.error(f"Billing API error: {response.status} - {error_text}")
                    raise HTTPException(status_code=503, detail=ERROR_BILLING_SERVICE_UNAVAILABLE)
                result: JSONDict = await response.json()
                return result
        except aiohttp.ClientError as e:
            logger.error(f"Billing API request error: {e}")
            raise HTTPException(status_code=503, detail=ERROR_BILLING_SERVICE_UNAVAILABLE)


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
            # NOTE: purchase_options set to None for SDK compatibility
            purchase_options=None,
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


async def _query_billing_backend(base_url: str, headers: Dict[str, str], check_payload: JSONDict) -> JSONDict:
    """Query billing backend for credit status."""
    return await _billing_post(base_url, "/v1/billing/credits/check", headers, check_payload)


def _format_billing_response(credit_data: JSONDict) -> CreditStatusResponse:
    """Format billing backend response for frontend."""
    # NOTE: purchase_options intentionally set to None for SDK compatibility
    # The mobile SDK expects a complex object type, not simple primitives

    return CreditStatusResponse(
        has_credit=credit_data["has_credit"],
        credits_remaining=credit_data.get("credits_remaining", 0),
        free_uses_remaining=credit_data.get("free_uses_remaining", 0),
        daily_free_uses_remaining=credit_data.get("daily_free_uses_remaining", 0),
        total_uses=credit_data.get("total_uses", 0),
        plan_name=credit_data.get("plan_name"),
        purchase_required=credit_data.get("purchase_required", False),
        purchase_options=None,
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

    # Check for OAuth ID token (written by Kotlin when user logs in - Google on Android, Apple on iOS)
    google_token = os.environ.get("CIRIS_BILLING_GOOGLE_ID_TOKEN", "") or os.environ.get(
        "CIRIS_BILLING_APPLE_ID_TOKEN", ""
    )
    if not google_token:
        logger.debug(
            "[BILLING_LAZY_INIT] No CIRIS_BILLING_GOOGLE_ID_TOKEN or CIRIS_BILLING_APPLE_ID_TOKEN in environment"
        )
        return None

    # Get billing URL from central config (checks env var first)
    billing_url = get_billing_url()

    logger.debug(
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
        # Log only hostname to avoid logging full URL  # NOSONAR - sanitized
        try:
            host_only = urlparse(billing_url).hostname or "unknown"
        except Exception:
            host_only = "parse-error"
        logger.debug(
            "[BILLING_LAZY_INIT] Successfully created CIRISBillingProvider: host=%s",
            host_only,
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
        # NOTE: purchase_options intentionally set to None for SDK compatibility
        # The mobile SDK expects a complex object type, not simple primitives
        purchase_options=None,
    )


@router.get("/credits", responses=RESPONSES_BILLING_503)
async def get_credits(
    request: Request,
    auth: AuthObserverDep,
) -> CreditStatusResponse:
    """
    Get user's credit balance and status.

    Works with both:
    - SimpleCreditProvider (1 free credit per OAuth user, no billing backend needed)
    - CIRISBillingProvider (full billing backend with paid credits)

    The frontend calls this to display credit status.
    """
    import os

    from ciris_engine.logic.adapters.api.routes._common import derive_credit_account
    from ciris_engine.schemas.services.credit_gate import CreditContext

    logger.debug("[BILLING_API] get_credits called")
    user_identity = _extract_user_identity(auth, request)
    agent_id = _get_agent_id(request)

    # Check credit provider availability
    credit_provider = _get_credit_provider(request)
    if credit_provider is None:
        if not hasattr(request.app.state, "resource_monitor"):
            logger.error("[BILLING_API] No resource_monitor on app.state")
            raise HTTPException(status_code=503, detail=ERROR_RESOURCE_MONITOR_UNAVAILABLE)
        logger.debug("[BILLING_API] No credit provider, returning unlimited response")
        return _get_unlimited_credit_response()

    # Query credit provider
    resource_monitor = request.app.state.resource_monitor
    account, _ = derive_credit_account(auth, request)
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
            "[BILLING_CREDITS] Using CreditCheckResult (no API key): free=%s, paid=%s, has_credit=%s",
            result.free_uses_remaining,
            result.credits_remaining,
            result.has_credit,
        )
        return _build_mobile_credit_response(result)

    # Server mode with API key - query billing backend
    base_url, headers = _get_billing_config(request)
    credit_data = await _query_billing_backend(base_url, headers, _build_credit_check_payload(user_identity, context))
    response = _format_billing_response(credit_data)
    logger.info(
        "[BILLING_CREDITS] Credit check complete: free=%s, paid=%s, has_credit=%s",
        response.free_uses_remaining,
        response.credits_remaining,
        response.has_credit,
    )
    return response


@router.post("/purchase/initiate", responses=RESPONSES_BILLING_PURCHASE_INITIATE)
async def initiate_purchase(
    request: Request,
    body: PurchaseInitiateRequest,
    auth: AuthObserverDep,
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
    base_url, headers = _get_billing_config(request)
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

    # Create payment intent via billing backend
    purchase_data = await _billing_post(
        base_url,
        "/v1/billing/purchases",
        headers,
        {
            **user_identity,
            "customer_email": customer_email,
            "return_url": body.return_url,
        },
    )

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


@router.get("/purchase/status/{payment_id}", responses=RESPONSES_BILLING_PURCHASE_STATUS)
async def get_purchase_status(
    payment_id: str,
    request: Request,
    auth: AuthObserverDep,
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
    base_url, headers = _get_billing_config(request)
    user_identity = _extract_user_identity(auth, request)

    # Query billing backend for specific payment status
    # URL-encode payment_id to prevent path traversal (already validated by PAYMENT_ID_PATTERN)
    safe_payment_id = quote(payment_id, safe="")
    payment_data = await _billing_get(
        base_url,
        f"/v1/billing/purchases/{safe_payment_id}/status",
        headers,
        user_identity,
    )

    # If payment not found (empty response from _billing_get), return pending
    if not payment_data or payment_data.get("transactions") == []:
        return PurchaseStatusResponse(
            status="pending",
            credits_added=0,
            balance_after=None,
        )

    # Get updated credit balance
    credit_data = await _billing_post(
        base_url,
        "/v1/billing/credits/check",
        headers,
        {
            **user_identity,
            "context": {"source": "purchase_status_check"},
        },
    )

    # Extract payment status and amount from billing backend response
    payment_status = payment_data.get("status", "unknown")
    credits_added = payment_data.get("credits_added", 0)

    return PurchaseStatusResponse(
        status=payment_status,
        credits_added=credits_added,
        balance_after=credit_data.get("credits_remaining"),
    )


@router.get("/transactions", responses=RESPONSES_BILLING_503)
async def get_transactions(
    request: Request,
    auth: AuthObserverDep,
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
    logger.debug("[BILLING_TRANSACTIONS] Fetching transactions (limit=%d, offset=%d)", limit, offset)
    base_url, headers = _get_billing_config(request)
    user_identity = _extract_user_identity(auth, request)

    # Build query parameters for billing backend
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
    transaction_data = await _billing_get(base_url, "/v1/billing/transactions", headers, params)

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


@router.post("/google-play/verify")
async def verify_google_play_purchase(
    request: Request,
    body: GooglePlayVerifyRequest,
    auth: AuthObserverDep,
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
    # Sanitize user-controlled data before logging to prevent log injection
    logger.info(
        "[GOOGLE_PLAY_VERIFY] Verifying purchase for user_id=%s, product=%s",
        _sanitize_for_log(auth.user_id),
        _sanitize_for_log(body.product_id),
    )

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
    # First check header, then fallback to environment (written by Kotlin EnvFileUpdater)
    google_id_token = request.headers.get("X-Google-ID-Token")
    if not google_id_token:
        import os

        google_id_token = os.environ.get("CIRIS_BILLING_GOOGLE_ID_TOKEN") or os.environ.get(
            "CIRIS_BILLING_APPLE_ID_TOKEN"
        )
        if google_id_token:
            logger.info(f"[GOOGLE_PLAY_VERIFY] Using OAuth ID token from environment ({len(google_id_token)} chars)")
    else:
        logger.info(f"[GOOGLE_PLAY_VERIFY] Using JWT pass-through with Google ID token ({len(google_id_token)} chars)")

    try:
        base_url, headers = _get_billing_config(request, google_id_token=google_id_token)
        result = await _billing_post(base_url, "/v1/billing/google-play/verify", headers, verify_payload)

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

    except HTTPException as e:
        logger.error(f"[GOOGLE_PLAY_VERIFY] Billing API error: {e.status_code} - {e.detail}")
        return GooglePlayVerifyResponse(success=False, error=f"Verification failed: {e.status_code}")
    except aiohttp.ClientError as e:
        logger.error(f"[GOOGLE_PLAY_VERIFY] Request error: {e}")
        return GooglePlayVerifyResponse(success=False, error=f"Network error: {str(e)}")
