"""
Tool-related API endpoints for CIRIS.

Provides endpoints for:
- Tool balance checking (web_search credits, etc.)
- Tool credit purchases via Google Play
- Available tools listing

These endpoints proxy to the CIRIS Billing backend for tool-specific credits,
which are tracked separately from LLM credits.
"""

import logging
import os
import re
from enum import Enum
from typing import Any, Dict, List, Optional, cast
from urllib.parse import quote, urljoin

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from ciris_engine.config.ciris_services import get_billing_url
from ciris_engine.schemas.api.auth import AuthContext

from ..dependencies.auth import require_observer

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/tools", tags=["tools"])

# Billing service URLs from central config
DEFAULT_BILLING_URL = get_billing_url()
FALLBACK_BILLING_URL = get_billing_url(use_fallback=True)


class BillingEndpoint(str, Enum):
    """Predefined billing API endpoints to prevent path injection."""

    BALANCE_ALL = "/v1/tools/balance"
    BALANCE_TOOL = "/v1/tools/balance/{tool_name}"
    CHECK_TOOL = "/v1/tools/check/{tool_name}"
    VERIFY_PURCHASE = "/v1/tools/purchase/verify"


def _build_endpoint_path(endpoint: BillingEndpoint, tool_name: Optional[str] = None) -> str:
    """
    Safely build endpoint path from predefined enum.

    This ensures paths are only constructed from known constants,
    with tool_name validated and URL-encoded to prevent injection.
    """
    path = endpoint.value
    if "{tool_name}" in path:
        if tool_name is None:
            raise ValueError(f"Endpoint {endpoint} requires tool_name")
        # Use quote() to safely encode the validated tool name
        safe_name = quote(tool_name, safe="")
        path = path.replace("{tool_name}", safe_name)
    return path


# Response schemas


class ToolBalanceResponse(BaseModel):
    """Balance information for a specific tool."""

    product_type: str = Field(..., description="Tool product type (e.g., 'web_search')")
    free_remaining: int = Field(..., description="Remaining free uses")
    paid_credits: int = Field(..., description="Paid credits available")
    total_available: int = Field(..., description="Total available uses (free + paid)")
    price_minor: int = Field(..., description="Price per credit in minor units (cents)")
    total_uses: int = Field(..., description="Total lifetime uses")


class AllToolBalancesResponse(BaseModel):
    """Balance information for all tools."""

    balances: List[ToolBalanceResponse] = Field(..., description="List of tool balances")


class ToolCreditCheckResponse(BaseModel):
    """Quick credit check for a tool."""

    has_credit: bool = Field(..., description="Whether user has credit for this tool")
    product_type: str = Field(..., description="Tool product type")
    free_remaining: int = Field(..., description="Remaining free uses")
    paid_credits: int = Field(..., description="Paid credits available")
    total_available: int = Field(..., description="Total available uses")


class ToolInfoResponse(BaseModel):
    """Information about an available tool."""

    name: str = Field(..., description="Tool name")
    description: str = Field(..., description="Tool description")
    cost: float = Field(..., description="Cost per use in credits")
    available: bool = Field(..., description="Whether tool is available on this platform")
    platform_requirements: List[str] = Field(default_factory=list, description="Platform requirements for this tool")


class AvailableToolsResponse(BaseModel):
    """List of available tools."""

    tools: List[ToolInfoResponse] = Field(..., description="Available tools")
    platform: str = Field(..., description="Current platform")
    has_google_auth: bool = Field(..., description="Whether Google auth is available")


class ToolPurchaseRequest(BaseModel):
    """Request to verify and process a tool credit purchase."""

    product_id: str = Field(..., description="Google Play product ID (e.g., 'web_search_10')")
    purchase_token: str = Field(..., description="Google Play purchase token")
    tool_name: str = Field(..., description="Tool to add credits to (e.g., 'web_search')")


class ToolPurchaseResponse(BaseModel):
    """Response from purchase verification."""

    success: bool = Field(..., description="Whether purchase was verified and processed")
    product_type: str = Field(..., description="Tool product type")
    credits_added: int = Field(..., description="Number of credits added")
    new_balance: int = Field(..., description="New total available credits")
    message: str = Field(..., description="Status message")


# Error message constants
ERR_GOOGLE_SIGNIN_REQUIRED = "Google Sign-In required. Tool credits require device authentication."
ERR_AUTH_FAILED = "Authentication failed. Please sign in again."
ERR_BILLING_UNAVAILABLE = "Billing service unavailable"

# Helper functions

# Valid tool names: alphanumeric and underscores only, 1-64 chars
# Note: \w also includes underscore, so [a-zA-Z]\w{0,63} is equivalent
TOOL_NAME_PATTERN = re.compile(r"^[a-zA-Z]\w{0,63}$")


def _validate_tool_name(tool_name: str) -> str:
    """
    Validate and sanitize tool name to prevent path injection.

    Tool names must:
    - Start with a letter
    - Contain only alphanumeric characters and underscores
    - Be 1-64 characters long

    Raises HTTPException 400 if invalid.
    """
    if not tool_name or not TOOL_NAME_PATTERN.match(tool_name):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid tool name: '{tool_name}'. Must be alphanumeric with underscores, starting with a letter.",
        )
    return tool_name


def _get_billing_url() -> str:
    """Get the billing service URL."""
    return os.environ.get("CIRIS_BILLING_API_URL", DEFAULT_BILLING_URL)


def _get_google_id_token(request: Request) -> Optional[str]:
    """Get Google ID token from request headers or environment."""
    # Try header first (set by Android)
    token = request.headers.get("X-Google-ID-Token")
    if token:
        return token

    # Try environment (set after login)
    token = os.environ.get("CIRIS_BILLING_GOOGLE_ID_TOKEN")
    if token:
        return token

    token = os.environ.get("GOOGLE_ID_TOKEN")
    return token


async def _make_billing_request(
    method: str,
    endpoint: BillingEndpoint,
    google_token: str,
    tool_name: Optional[str] = None,
    use_fallback: bool = False,
    json_data: Optional[Dict[str, str]] = None,
) -> httpx.Response:
    """Make a request to the billing service.

    Args:
        method: HTTP method (GET or POST)
        endpoint: Predefined billing endpoint from BillingEndpoint enum
        google_token: Google ID token for authentication
        tool_name: Optional tool name (required for endpoints with {tool_name})
        use_fallback: Whether to use fallback billing URL
        json_data: Optional JSON data for POST requests
    """
    base_url = FALLBACK_BILLING_URL if use_fallback else _get_billing_url()
    # Build path from enum - this is the ONLY place paths are constructed
    path = _build_endpoint_path(endpoint, tool_name)
    # Construct full URL from base + predefined path
    url = base_url.rstrip("/") + path

    headers = {
        "Authorization": f"Bearer {google_token}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=10.0) as client:
        if method.upper() == "GET":
            return await client.get(url, headers=headers)
        elif method.upper() == "POST":
            return await client.post(url, headers=headers, json=json_data)
        else:
            raise ValueError(f"Unsupported method: {method}")


# Endpoints


@router.get("/balance/{tool_name}", response_model=ToolBalanceResponse)
async def get_tool_balance(
    tool_name: str,
    request: Request,
    auth: AuthContext = Depends(require_observer),
) -> ToolBalanceResponse:
    """
    Get balance for a specific tool.

    Returns the user's credit balance for the specified tool (e.g., web_search).
    Requires Google Sign-In authentication.
    """
    # Validate tool name to prevent path injection
    tool_name = _validate_tool_name(tool_name)
    logger.info(f"[TOOL_BALANCE] Getting balance for {tool_name}, user={auth.user_id}")

    google_token = _get_google_id_token(request)
    if not google_token:
        raise HTTPException(status_code=401, detail=ERR_GOOGLE_SIGNIN_REQUIRED)

    try:
        response = await _make_billing_request("GET", BillingEndpoint.BALANCE_TOOL, google_token, tool_name=tool_name)

        if response.status_code == 401:
            raise HTTPException(status_code=401, detail=ERR_AUTH_FAILED)

        if response.status_code == 404:
            raise HTTPException(status_code=404, detail=f"Tool not found: {tool_name}")

        if response.status_code != 200:
            logger.error(f"[TOOL_BALANCE] Billing error: {response.status_code} - {response.text}")
            raise HTTPException(status_code=503, detail=ERR_BILLING_UNAVAILABLE)

        data = response.json()
        return ToolBalanceResponse(
            product_type=data.get("product_type", tool_name),
            free_remaining=data.get("free_remaining", 0),
            paid_credits=data.get("paid_credits", 0),
            total_available=data.get("total_available", 0),
            price_minor=data.get("price_minor", 1),
            total_uses=data.get("total_uses", 0),
        )

    except httpx.RequestError as e:
        # Try fallback
        logger.warning(f"[TOOL_BALANCE] Primary failed, trying fallback: {e}")
        try:
            response = await _make_billing_request(
                "GET", BillingEndpoint.BALANCE_TOOL, google_token, tool_name=tool_name, use_fallback=True
            )
            if response.status_code == 200:
                data = response.json()
                return ToolBalanceResponse(
                    product_type=data.get("product_type", tool_name),
                    free_remaining=data.get("free_remaining", 0),
                    paid_credits=data.get("paid_credits", 0),
                    total_available=data.get("total_available", 0),
                    price_minor=data.get("price_minor", 1),
                    total_uses=data.get("total_uses", 0),
                )
        except httpx.RequestError as fallback_err:
            logger.warning(f"[TOOL_BALANCE] Fallback also failed: {fallback_err}")
        raise HTTPException(status_code=503, detail=ERR_BILLING_UNAVAILABLE)


@router.get("/balance", response_model=AllToolBalancesResponse)
async def get_all_tool_balances(
    request: Request,
    auth: AuthContext = Depends(require_observer),
) -> AllToolBalancesResponse:
    """
    Get balance for all tools.

    Returns the user's credit balance for all available tools.
    Requires Google Sign-In authentication.
    """
    logger.info(f"[TOOL_BALANCE] Getting all balances for user={auth.user_id}")

    google_token = _get_google_id_token(request)
    if not google_token:
        raise HTTPException(
            status_code=401,
            detail=ERR_GOOGLE_SIGNIN_REQUIRED,
        )

    try:
        response = await _make_billing_request("GET", BillingEndpoint.BALANCE_ALL, google_token)

        if response.status_code == 401:
            raise HTTPException(status_code=401, detail=ERR_AUTH_FAILED)

        if response.status_code != 200:
            logger.error(f"[TOOL_BALANCE] Billing error: {response.status_code} - {response.text}")
            raise HTTPException(status_code=503, detail=ERR_BILLING_UNAVAILABLE)

        data = response.json()
        balances = []
        for item in data.get("balances", []):
            balances.append(
                ToolBalanceResponse(
                    product_type=item.get("product_type", "unknown"),
                    free_remaining=item.get("free_remaining", 0),
                    paid_credits=item.get("paid_credits", 0),
                    total_available=item.get("total_available", 0),
                    price_minor=item.get("price_minor", 1),
                    total_uses=item.get("total_uses", 0),
                )
            )
        return AllToolBalancesResponse(balances=balances)

    except httpx.RequestError as e:
        logger.warning(f"[TOOL_BALANCE] Primary failed, trying fallback: {e}")
        try:
            response = await _make_billing_request("GET", BillingEndpoint.BALANCE_ALL, google_token, use_fallback=True)
            if response.status_code == 200:
                data = response.json()
                balances = []
                for item in data.get("balances", []):
                    balances.append(
                        ToolBalanceResponse(
                            product_type=item.get("product_type", "unknown"),
                            free_remaining=item.get("free_remaining", 0),
                            paid_credits=item.get("paid_credits", 0),
                            total_available=item.get("total_available", 0),
                            price_minor=item.get("price_minor", 1),
                            total_uses=item.get("total_uses", 0),
                        )
                    )
                return AllToolBalancesResponse(balances=balances)
        except httpx.RequestError as fallback_err:
            logger.warning(f"[TOOL_BALANCE] Fallback also failed: {fallback_err}")
        raise HTTPException(status_code=503, detail=ERR_BILLING_UNAVAILABLE)


@router.get("/check/{tool_name}", response_model=ToolCreditCheckResponse)
async def check_tool_credit(
    tool_name: str,
    request: Request,
    auth: AuthContext = Depends(require_observer),
) -> ToolCreditCheckResponse:
    """
    Quick credit check for a tool.

    Lightweight endpoint to check if user has credit for a specific tool.
    Requires Google Sign-In authentication.
    """
    # Validate tool name to prevent path injection
    tool_name = _validate_tool_name(tool_name)
    logger.info(f"[TOOL_CHECK] Checking credit for {tool_name}, user={auth.user_id}")

    google_token = _get_google_id_token(request)
    if not google_token:
        raise HTTPException(
            status_code=401,
            detail=ERR_GOOGLE_SIGNIN_REQUIRED,
        )

    try:
        response = await _make_billing_request("GET", BillingEndpoint.CHECK_TOOL, google_token, tool_name=tool_name)

        if response.status_code == 401:
            raise HTTPException(status_code=401, detail=ERR_AUTH_FAILED)

        if response.status_code == 404:
            raise HTTPException(status_code=404, detail=f"Tool not found: {tool_name}")

        if response.status_code != 200:
            logger.error(f"[TOOL_CHECK] Billing error: {response.status_code} - {response.text}")
            raise HTTPException(status_code=503, detail=ERR_BILLING_UNAVAILABLE)

        data = response.json()
        return ToolCreditCheckResponse(
            has_credit=data.get("has_credit", False),
            product_type=data.get("product_type", tool_name),
            free_remaining=data.get("free_remaining", 0),
            paid_credits=data.get("paid_credits", 0),
            total_available=data.get("total_available", 0),
        )

    except httpx.RequestError as e:
        logger.warning(f"[TOOL_CHECK] Primary failed, trying fallback: {e}")
        try:
            response = await _make_billing_request(
                "GET", BillingEndpoint.CHECK_TOOL, google_token, tool_name=tool_name, use_fallback=True
            )
            if response.status_code == 200:
                data = response.json()
                return ToolCreditCheckResponse(
                    has_credit=data.get("has_credit", False),
                    product_type=data.get("product_type", tool_name),
                    free_remaining=data.get("free_remaining", 0),
                    paid_credits=data.get("paid_credits", 0),
                    total_available=data.get("total_available", 0),
                )
        except httpx.RequestError as fallback_err:
            logger.warning(f"[TOOL_CHECK] Fallback also failed: {fallback_err}")
        raise HTTPException(status_code=503, detail=ERR_BILLING_UNAVAILABLE)


@router.get("/available", response_model=AvailableToolsResponse)
async def get_available_tools(
    request: Request,
    auth: AuthContext = Depends(require_observer),
) -> AvailableToolsResponse:
    """
    Get list of available tools for this platform.

    Returns tools available based on current platform capabilities.
    Some tools require specific platform features (e.g., Google Play Services).
    """
    from ciris_engine.logic.utils.platform_detection import detect_platform_capabilities
    from ciris_engine.schemas.platform import PlatformRequirement

    logger.info(f"[TOOLS] Getting available tools for user={auth.user_id}")

    # Detect platform capabilities
    caps = detect_platform_capabilities()

    # Define available tools with their requirements
    all_tools = [
        {
            "name": "web_search",
            "description": "Search the web for current information",
            "cost": 1.0,
            "requirements": [
                PlatformRequirement.ANDROID_PLAY_INTEGRITY,
                PlatformRequirement.GOOGLE_NATIVE_AUTH,
            ],
        },
    ]

    # Filter based on platform capabilities
    tools = []
    for tool in all_tools:
        requirements = cast(List[PlatformRequirement], tool.get("requirements", []))
        available = caps.satisfies(requirements)
        tools.append(
            ToolInfoResponse(
                name=tool["name"],
                description=tool["description"],
                cost=tool["cost"],
                available=available,
                platform_requirements=[req.value for req in requirements],
            )
        )

    return AvailableToolsResponse(
        tools=tools,
        platform=caps.platform,
        has_google_auth=caps.google_native_auth_available,
    )


@router.post("/purchase", response_model=ToolPurchaseResponse)
async def verify_tool_purchase(
    purchase: ToolPurchaseRequest,
    request: Request,
    auth: AuthContext = Depends(require_observer),
) -> ToolPurchaseResponse:
    """
    Verify and process a Google Play tool credit purchase.

    After a successful Google Play purchase, the app should call this endpoint
    with the purchase token to verify the purchase and grant credits.
    Requires Google Sign-In authentication.
    """
    # Validate tool name to prevent path injection
    _validate_tool_name(purchase.tool_name)
    logger.info(
        f"[TOOL_PURCHASE] Verifying purchase for {purchase.tool_name}, "
        f"product={purchase.product_id}, user={auth.user_id}"
    )

    google_token = _get_google_id_token(request)
    if not google_token:
        raise HTTPException(
            status_code=401,
            detail=ERR_GOOGLE_SIGNIN_REQUIRED,
        )

    purchase_data = {
        "product_id": purchase.product_id,
        "purchase_token": purchase.purchase_token,
        "tool_name": purchase.tool_name,
    }

    try:
        response = await _make_billing_request(
            "POST", BillingEndpoint.VERIFY_PURCHASE, google_token, json_data=purchase_data
        )

        if response.status_code == 401:
            raise HTTPException(status_code=401, detail=ERR_AUTH_FAILED)

        if response.status_code == 400:
            data = response.json()
            raise HTTPException(status_code=400, detail=data.get("detail", "Invalid purchase"))

        if response.status_code == 409:
            data = response.json()
            raise HTTPException(status_code=409, detail=data.get("detail", "Purchase already processed"))

        if response.status_code != 200:
            logger.error(f"[TOOL_PURCHASE] Billing error: {response.status_code} - {response.text}")
            raise HTTPException(status_code=503, detail=ERR_BILLING_UNAVAILABLE)

        data = response.json()
        return ToolPurchaseResponse(
            success=data.get("success", False),
            product_type=data.get("product_type", purchase.tool_name),
            credits_added=data.get("credits_added", 0),
            new_balance=data.get("new_balance", 0),
            message=data.get("message", "Purchase processed"),
        )

    except httpx.RequestError as e:
        # Try fallback
        logger.warning(f"[TOOL_PURCHASE] Primary failed, trying fallback: {e}")
        try:
            response = await _make_billing_request(
                "POST", BillingEndpoint.VERIFY_PURCHASE, google_token, use_fallback=True, json_data=purchase_data
            )
            if response.status_code == 200:
                data = response.json()
                return ToolPurchaseResponse(
                    success=data.get("success", False),
                    product_type=data.get("product_type", purchase.tool_name),
                    credits_added=data.get("credits_added", 0),
                    new_balance=data.get("new_balance", 0),
                    message=data.get("message", "Purchase processed"),
                )
        except httpx.RequestError as fallback_err:
            logger.warning(f"[TOOL_PURCHASE] Fallback also failed: {fallback_err}")
        raise HTTPException(status_code=503, detail=ERR_BILLING_UNAVAILABLE)
