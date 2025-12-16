"""
CIRIS Hosted Tools - Tool service implementations.

Provides tools that call out to CIRIS hosted services (proxy):
- web_search: Search the web using Brave Search API via CIRIS proxy

These tools require platform-level security guarantees (proof of possession)
that can only be satisfied on platforms with device attestation:
- Android: Google Play Integrity API
- iOS: App Attest (future)
- Web: DPoP (future)

Credit Model:
- 10 free searches for new users (one-time welcome bonus)
- 3 free searches per day (resets at UTC midnight)
- 1 credit per search after free tier exhausted
- Credits can be purchased via in-app billing
"""

import logging
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from uuid import uuid4

import httpx

from ciris_engine.config.ciris_services import (
    DEFAULT_BILLING_URL,
    DEFAULT_PROXY_URL,
    FALLBACK_BILLING_URL,
    FALLBACK_PROXY_URL,
)
from ciris_engine.schemas.adapters.tools import ToolExecutionResult, ToolExecutionStatus, ToolInfo, ToolParameterSchema
from ciris_engine.schemas.platform import PlatformRequirement

logger = logging.getLogger(__name__)


@dataclass
class ToolBalance:
    """Balance information for a hosted tool."""

    product_type: str
    free_remaining: int
    paid_credits: int
    total_available: int
    price_minor: int  # Price in minor currency units (e.g., cents)
    total_uses: int


class CIRISHostedToolService:
    """Tool service for CIRIS hosted tools via proxy.

    These tools require device attestation because:
    1. The CIRIS proxy provides free/subsidized API access
    2. Without proof of possession, tokens could be extracted and abused
    3. Device attestation (Play Integrity) proves the request comes from
       a real device running the official app, not a bot farm

    On Android:
    - Google Play Integrity API provides device attestation
    - Native Google Sign-In provides cryptographic user binding
    - The combination prevents token extraction and replay

    Future platforms:
    - iOS: App Attest + native Apple Sign-In
    - Web: DPoP token binding (RFC 9449)
    """

    TOOL_DEFINITIONS: Dict[str, ToolInfo] = {
        "web_search": ToolInfo(
            name="web_search",
            description=(
                "Search the web for current information. Use this when you need "
                "recent news, general information, or facts beyond your training cutoff. "
                "Returns titles, URLs, and descriptions of relevant web pages. "
                "IMPORTANT: Do NOT use for weather queries - web search returns unreliable "
                "weather data. For weather, tell the user you cannot provide current weather."
            ),
            parameters=ToolParameterSchema(
                type="object",
                properties={
                    "q": {
                        "type": "string",
                        "description": "Search query - be specific and include relevant keywords",
                    },
                    "count": {
                        "type": "integer",
                        "description": "Number of results to return (default: 10, max: 20)",
                        "default": 10,
                    },
                },
                required=["q"],
            ),
            category="information",
            cost=1.0,  # 1 web_search credit per query
            when_to_use=(
                "Use when you need current information, recent news, or to verify facts "
                "that may have changed since your training cutoff. "
                "DO NOT use for: weather queries (returns unreliable data), "
                "stock prices, or other real-time numerical data."
            ),
            # Platform requirements: needs device attestation + native auth
            platform_requirements=[
                PlatformRequirement.ANDROID_PLAY_INTEGRITY,
                PlatformRequirement.GOOGLE_NATIVE_AUTH,
            ],
            platform_requirements_rationale=(
                "Web search requires device attestation to prevent API abuse. "
                "This tool is only available on Android devices with Google Play Services. "
                "Future support: iOS (App Attest), Web (DPoP)."
            ),
        ),
    }

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        """Initialize the hosted tool service.

        Args:
            config: Optional configuration dictionary with:
                - proxy_url: Base URL for CIRIS proxy (default: proxy1.ciris-services-1.ai)
                - proxy_fallback_url: Fallback proxy URL (default: proxy1.ciris-services-2.ai)
                - billing_url: Base URL for billing service (default: billing1.ciris-services-1.ai)
                - billing_fallback_url: Fallback billing URL (default: billing1.ciris-services-2.ai)
                - timeout: Request timeout in seconds (default: 30)
        """
        self.config = config or {}
        # Proxy URLs for tool execution
        self._proxy_url = self.config.get("proxy_url", DEFAULT_PROXY_URL)
        self._proxy_fallback_url = self.config.get("proxy_fallback_url", FALLBACK_PROXY_URL)
        # Billing URLs for balance/credit checking
        self._billing_url = self.config.get("billing_url", DEFAULT_BILLING_URL)
        self._billing_fallback_url = self.config.get("billing_fallback_url", FALLBACK_BILLING_URL)
        self._timeout = self.config.get("timeout", 30.0)
        self._call_count = 0
        self._error_count = 0
        self._cached_balance: Optional[ToolBalance] = None
        logger.info(f"CIRISHostedToolService initialized with proxy: {self._proxy_url}, billing: {self._billing_url}")

    async def start(self) -> None:
        """Start the service."""
        logger.info("CIRISHostedToolService started")

    async def stop(self) -> None:
        """Stop the service."""
        logger.info("CIRISHostedToolService stopped")

    def _get_google_id_token(self) -> Optional[str]:
        """Get the Google ID token from environment or .env file.

        The token is set by:
        - Android: After native Google Sign-In, stored in CIRIS_BILLING_GOOGLE_ID_TOKEN
        - API: After native token exchange, stored in environment

        On Android, the .env file may be updated after Python starts (by Kotlin
        TokenRefreshManager), so we re-read from the file if not in environment.

        Returns:
            Google ID token if available, None otherwise
        """
        # First try environment (direct or loaded at startup)
        token = os.environ.get("CIRIS_BILLING_GOOGLE_ID_TOKEN")
        if token:
            logger.info(f"[HOSTED_TOOLS] Got token from env CIRIS_BILLING_GOOGLE_ID_TOKEN (len={len(token)})")
        else:
            token = os.environ.get("GOOGLE_ID_TOKEN")
            if token:
                logger.info(f"[HOSTED_TOOLS] Got token from env GOOGLE_ID_TOKEN (len={len(token)})")

        # If not in environment, try re-reading from .env file
        # This handles the case where Kotlin updates the file after Python starts
        if not token:
            logger.info("[HOSTED_TOOLS] No token in environment, reading from .env file...")
            try:
                from pathlib import Path

                # Try common .env locations - Android path first
                env_paths = [
                    Path("/data/data/ai.ciris.mobile/files/ciris/.env"),  # Android
                    Path(os.environ.get("CIRIS_HOME", ".")) / ".env",
                    Path.home() / ".env",
                    Path(".env"),
                ]
                for env_path in env_paths:
                    logger.info(f"[HOSTED_TOOLS] Checking {env_path} exists={env_path.exists()}")
                    if env_path.exists():
                        with open(env_path) as f:
                            for line in f:
                                line = line.strip()
                                if line.startswith("CIRIS_BILLING_GOOGLE_ID_TOKEN="):
                                    # Handle quoted and unquoted values
                                    value = line.split("=", 1)[1].strip()
                                    if value.startswith('"') and value.endswith('"'):
                                        value = value[1:-1]
                                    elif value.startswith("'") and value.endswith("'"):
                                        value = value[1:-1]
                                    if value:
                                        token = value
                                        logger.info(
                                            f"[HOSTED_TOOLS] ✓ Loaded fresh token from {env_path} (len={len(value)})"
                                        )
                                        break
                        if token:
                            break
                        else:
                            logger.warning(f"[HOSTED_TOOLS] .env exists but no CIRIS_BILLING_GOOGLE_ID_TOKEN found")

                if not token:
                    logger.error("[HOSTED_TOOLS] ✗ No token found in any .env location!")
            except Exception as e:
                logger.error(f"[HOSTED_TOOLS] ✗ Failed to read .env file: {e}")

        return token

    async def get_available_tools(self) -> List[str]:
        """Get available tool names."""
        return list(self.TOOL_DEFINITIONS.keys())

    async def list_tools(self) -> List[str]:
        """Legacy alias for get_available_tools()."""
        return await self.get_available_tools()

    async def get_tool_info(self, tool_name: str) -> Optional[ToolInfo]:
        """Get detailed info for a specific tool."""
        return self.TOOL_DEFINITIONS.get(tool_name)

    async def get_all_tool_info(self) -> List[ToolInfo]:
        """Get info for all tools."""
        return list(self.TOOL_DEFINITIONS.values())

    async def get_tool_schema(self, tool_name: str) -> Optional[ToolParameterSchema]:
        """Get parameter schema for a tool."""
        tool_info = self.TOOL_DEFINITIONS.get(tool_name)
        return tool_info.parameters if tool_info else None

    async def validate_parameters(self, tool_name: str, parameters: Dict[str, Any]) -> bool:
        """Validate parameters for a tool without executing it."""
        if tool_name not in self.TOOL_DEFINITIONS:
            return False
        tool_info = self.TOOL_DEFINITIONS[tool_name]
        if not tool_info.parameters:
            return True
        required = tool_info.parameters.required or []
        return all(param in parameters for param in required)

    async def get_tool_result(self, correlation_id: str, timeout: float = 30.0) -> Optional[ToolExecutionResult]:
        """Get result of previously executed tool. Not used for sync tools."""
        return None

    def get_tools(self) -> List[Dict[str, Any]]:
        """Return list of available tools (legacy format)."""
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters.model_dump() if tool.parameters else {},
                "platform_requirements": [req.value for req in tool.platform_requirements],
            }
            for tool in self.TOOL_DEFINITIONS.values()
        ]

    # =========================================================================
    # Balance Checking Methods
    # =========================================================================

    async def _make_request(
        self,
        method: str,
        path: str,
        json_data: Optional[Dict[str, Any]] = None,
        use_fallback: bool = False,
        service: str = "proxy",
    ) -> httpx.Response:
        """Make a request to a CIRIS service with fallback support.

        Args:
            method: HTTP method (GET, POST, etc.)
            path: URL path (e.g., /v1/search)
            json_data: Optional JSON body for POST requests
            use_fallback: If True, use fallback URL instead of primary
            service: Which service to call ("proxy" or "billing")

        Returns:
            httpx.Response object

        Raises:
            httpx.RequestError: If request fails
        """
        google_token = self._get_google_id_token()
        headers = {
            "Authorization": f"Bearer {google_token}" if google_token else "",
            "Content-Type": "application/json",
        }

        # Select the appropriate URL based on service and fallback
        if service == "billing":
            base_url = self._billing_fallback_url if use_fallback else self._billing_url
        else:  # proxy
            base_url = self._proxy_fallback_url if use_fallback else self._proxy_url

        url = f"{base_url}{path}"

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            if method.upper() == "GET":
                return await client.get(url, headers=headers)
            elif method.upper() == "POST":
                return await client.post(url, json=json_data, headers=headers)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")

    async def check_credit(self, tool_name: str = "web_search") -> Optional[bool]:
        """Quick check if user has credit for a tool.

        This is a lightweight check that doesn't return full balance details.

        Args:
            tool_name: Name of the tool to check credit for

        Returns:
            True if user has credit, False if not, None if check failed
        """
        google_token = self._get_google_id_token()
        if not google_token:
            return None

        try:
            response = await self._make_request("GET", f"/v1/tools/check/{tool_name}", service="billing")
            if response.status_code == 200:
                data = response.json()
                return data.get("has_credit", False)
            return None
        except httpx.RequestError:
            # Try fallback
            try:
                response = await self._make_request(
                    "GET", f"/v1/tools/check/{tool_name}", use_fallback=True, service="billing"
                )
                if response.status_code == 200:
                    data = response.json()
                    return data.get("has_credit", False)
            except httpx.RequestError:
                pass
            return None

    async def get_balance(self, tool_name: str = "web_search") -> Optional[ToolBalance]:
        """Get detailed balance information for a tool.

        Args:
            tool_name: Name of the tool to get balance for

        Returns:
            ToolBalance object with credit details, or None if request failed
        """
        google_token = self._get_google_id_token()
        if not google_token:
            return None

        try:
            response = await self._make_request("GET", f"/v1/tools/balance/{tool_name}", service="billing")
            if response.status_code == 200:
                data = response.json()
                balance = ToolBalance(
                    product_type=data.get("product_type", tool_name),
                    free_remaining=data.get("free_remaining", 0),
                    paid_credits=data.get("paid_credits", 0),
                    total_available=data.get("total_available", 0),
                    price_minor=data.get("price_minor", 1),
                    total_uses=data.get("total_uses", 0),
                )
                self._cached_balance = balance
                return balance
            return None
        except httpx.RequestError:
            # Try fallback
            try:
                response = await self._make_request(
                    "GET", f"/v1/tools/balance/{tool_name}", use_fallback=True, service="billing"
                )
                if response.status_code == 200:
                    data = response.json()
                    balance = ToolBalance(
                        product_type=data.get("product_type", tool_name),
                        free_remaining=data.get("free_remaining", 0),
                        paid_credits=data.get("paid_credits", 0),
                        total_available=data.get("total_available", 0),
                        price_minor=data.get("price_minor", 1),
                        total_uses=data.get("total_uses", 0),
                    )
                    self._cached_balance = balance
                    return balance
            except httpx.RequestError:
                pass
            return None

    async def get_all_balances(self) -> List[ToolBalance]:
        """Get balance information for all tools.

        Returns:
            List of ToolBalance objects for all hosted tools
        """
        google_token = self._get_google_id_token()
        if not google_token:
            return []

        try:
            response = await self._make_request("GET", "/v1/tools/balance", service="billing")
            if response.status_code == 200:
                data = response.json()
                balances = []
                for item in data.get("balances", []):
                    balances.append(
                        ToolBalance(
                            product_type=item.get("product_type", "unknown"),
                            free_remaining=item.get("free_remaining", 0),
                            paid_credits=item.get("paid_credits", 0),
                            total_available=item.get("total_available", 0),
                            price_minor=item.get("price_minor", 1),
                            total_uses=item.get("total_uses", 0),
                        )
                    )
                return balances
            return []
        except httpx.RequestError:
            # Try fallback
            try:
                response = await self._make_request("GET", "/v1/tools/balance", use_fallback=True, service="billing")
                if response.status_code == 200:
                    data = response.json()
                    balances = []
                    for item in data.get("balances", []):
                        balances.append(
                            ToolBalance(
                                product_type=item.get("product_type", "unknown"),
                                free_remaining=item.get("free_remaining", 0),
                                paid_credits=item.get("paid_credits", 0),
                                total_available=item.get("total_available", 0),
                                price_minor=item.get("price_minor", 1),
                                total_uses=item.get("total_uses", 0),
                            )
                        )
                    return balances
            except httpx.RequestError:
                pass
            return []

    def get_cached_balance(self) -> Optional[ToolBalance]:
        """Get the last cached balance (useful for UI display without API call)."""
        return self._cached_balance

    # =========================================================================
    # Tool Execution
    # =========================================================================

    async def execute_tool(
        self,
        tool_name: str,
        parameters: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> ToolExecutionResult:
        """Execute a tool and return results.

        Args:
            tool_name: Name of the tool to execute
            parameters: Tool parameters
            context: Optional execution context

        Returns:
            ToolExecutionResult with status, success, data, and error
        """
        self._call_count += 1
        correlation_id = str(uuid4())

        if tool_name not in self.TOOL_DEFINITIONS:
            return ToolExecutionResult(
                tool_name=tool_name,
                status=ToolExecutionStatus.NOT_FOUND,
                success=False,
                data=None,
                error=f"Unknown tool: {tool_name}",
                correlation_id=correlation_id,
            )

        try:
            if tool_name == "web_search":
                return await self._execute_web_search(parameters, correlation_id)

            return ToolExecutionResult(
                tool_name=tool_name,
                status=ToolExecutionStatus.FAILED,
                success=False,
                data=None,
                error=f"Tool not implemented: {tool_name}",
                correlation_id=correlation_id,
            )

        except Exception as e:
            self._error_count += 1
            logger.error(f"Error executing tool {tool_name}: {e}", exc_info=True)
            return ToolExecutionResult(
                tool_name=tool_name,
                status=ToolExecutionStatus.FAILED,
                success=False,
                data=None,
                error=str(e),
                correlation_id=correlation_id,
            )

    async def _try_search_request(
        self, payload: Dict[str, Any], use_fallback: bool = False
    ) -> Optional[httpx.Response]:
        """Try to make a search request to the proxy.

        Args:
            payload: Search parameters
            use_fallback: If True, use fallback proxy URL

        Returns:
            Response object if successful, None if request failed
        """
        response, _ = await self._try_search_request_with_error(payload, use_fallback)
        return response

    async def _try_search_request_with_error(
        self, payload: Dict[str, Any], use_fallback: bool = False
    ) -> tuple[Optional[httpx.Response], Optional[Exception]]:
        """Try to make a search request to the proxy, returning error info.

        Args:
            payload: Search parameters
            use_fallback: If True, use fallback proxy URL

        Returns:
            Tuple of (response, error). On success, error is None.
        """
        region = "EU-fallback" if use_fallback else "US-primary"
        try:
            response = await self._make_request(
                "POST", "/v1/web/search", json_data=payload, use_fallback=use_fallback, service="proxy"
            )
            logger.info(f"[WEB_SEARCH] ✓ Request succeeded via {region}")
            return response, None
        except httpx.ConnectTimeout as e:
            logger.warning(f"[WEB_SEARCH] ✗ {region} TIMEOUT: {e}")
            return None, e
        except httpx.ConnectError as e:
            logger.warning(f"[WEB_SEARCH] ✗ {region} CONNECTION_ERROR: {e}")
            return None, e
        except httpx.TimeoutException as e:
            logger.warning(f"[WEB_SEARCH] ✗ {region} TIMEOUT: {e}")
            return None, e
        except httpx.RequestError as e:
            logger.warning(f"[WEB_SEARCH] ✗ {region} NETWORK_ERROR: {e}")
            return None, e

    @staticmethod
    def _categorize_request_error(error: Optional[Exception]) -> str:
        """Categorize a request error for retry metadata.

        Returns:
            Error category string: TIMEOUT, CONNECTION_ERROR, NETWORK_ERROR, or UNKNOWN
        """
        if error is None:
            return "UNKNOWN"
        if isinstance(error, (httpx.ConnectTimeout, httpx.ReadTimeout, httpx.WriteTimeout)):
            return "TIMEOUT"
        if isinstance(error, httpx.ConnectError):
            return "CONNECTION_ERROR"
        if isinstance(error, httpx.TimeoutException):
            return "TIMEOUT"
        if isinstance(error, httpx.RequestError):
            return "NETWORK_ERROR"
        return "UNKNOWN"

    async def _execute_web_search(self, parameters: Dict[str, Any], correlation_id: str) -> ToolExecutionResult:
        """Execute a web search via CIRIS proxy.

        The proxy handles credit charging internally by calling the billing service.

        Args:
            parameters: Search parameters (q, count)
            correlation_id: Correlation ID for tracking

        Returns:
            ToolExecutionResult with search results or error
        """
        query = parameters.get("q", "")
        # Ensure count is an int (LLM may pass string)
        raw_count = parameters.get("count", 10)
        try:
            count = min(int(raw_count), 20)  # Cap at 20
        except (ValueError, TypeError):
            count = 10  # Default if conversion fails

        if not query:
            return ToolExecutionResult(
                tool_name="web_search",
                status=ToolExecutionStatus.FAILED,
                success=False,
                data=None,
                error="Search query 'q' is required",
                correlation_id=correlation_id,
            )

        # Get authentication token
        google_token = self._get_google_id_token()
        if not google_token:
            return ToolExecutionResult(
                tool_name="web_search",
                status=ToolExecutionStatus.UNAUTHORIZED,
                success=False,
                data=None,
                error=(
                    "Not authenticated. Web search requires Google Sign-In with device attestation. "
                    "This tool is only available on Android devices."
                ),
                correlation_id=correlation_id,
            )

        # Generate IDs for billing tracking and retry correlation
        import hashlib
        import uuid

        interaction_id = hashlib.sha256(correlation_id.encode()).hexdigest()[:32]
        request_id = uuid.uuid4().hex[:12]

        payload = {
            "q": query,
            "count": count,
            "metadata": {
                "interaction_id": interaction_id,
                "request_id": request_id,
            },
        }
        logger.info(
            f"[WEB_SEARCH] Searching for: {query[:50]}... (interaction_id={interaction_id}, request_id={request_id})"
        )

        # Try primary proxy first, then fallback with retry metadata
        response, primary_error = await self._try_search_request_with_error(payload, use_fallback=False)
        if response is None:
            # Add retry metadata for fallback attempt
            error_category = self._categorize_request_error(primary_error)
            payload["metadata"]["retry_count"] = 1
            payload["metadata"]["previous_error"] = error_category
            payload["metadata"]["original_request_id"] = request_id

            logger.warning(f"[WEB_SEARCH] Primary proxy failed ({error_category}), trying EU fallback...")
            response, _ = await self._try_search_request_with_error(payload, use_fallback=True)

        if response is None:
            return ToolExecutionResult(
                tool_name="web_search",
                status=ToolExecutionStatus.FAILED,
                success=False,
                data=None,
                error="Search failed: Unable to connect to any proxy server",
                correlation_id=correlation_id,
            )

        # Handle response status codes
        if response.status_code == 401:
            return ToolExecutionResult(
                tool_name="web_search",
                status=ToolExecutionStatus.UNAUTHORIZED,
                success=False,
                data=None,
                error="Authentication failed. Please sign in again with Google.",
                correlation_id=correlation_id,
            )

        if response.status_code == 402:
            return ToolExecutionResult(
                tool_name="web_search",
                status=ToolExecutionStatus.FAILED,
                success=False,
                data=None,
                error=(
                    "No web search credits available. "
                    "New users get 10 free searches, then 3 free per day. "
                    "Purchase credits for more searches."
                ),
                correlation_id=correlation_id,
            )

        if response.status_code != 200:
            error_text = response.text[:200] if response.text else "Unknown error"
            return ToolExecutionResult(
                tool_name="web_search",
                status=ToolExecutionStatus.FAILED,
                success=False,
                data=None,
                error=f"Search failed: HTTP {response.status_code} - {error_text}",
                correlation_id=correlation_id,
            )

        # Parse successful response
        try:
            result = response.json()
        except Exception as e:
            return ToolExecutionResult(
                tool_name="web_search",
                status=ToolExecutionStatus.FAILED,
                success=False,
                data=None,
                error=f"Failed to parse search response: {e}",
                correlation_id=correlation_id,
            )

        # Extract web results from response
        web_results = result.get("results", {}).get("web", {}).get("results", [])

        # Format results for agent consumption
        formatted_results = []
        for r in web_results:
            formatted_results.append(
                {
                    "title": r.get("title", ""),
                    "url": r.get("url", ""),
                    "description": r.get("description", ""),
                }
            )

        logger.info(f"[WEB_SEARCH] Got {len(formatted_results)} results for: {query}")

        # Log full results for debugging
        for i, r in enumerate(formatted_results):
            logger.info(f"[WEB_SEARCH] Result {i+1}: title='{r.get('title', '')}'")
            logger.info(f"[WEB_SEARCH] Result {i+1}: url='{r.get('url', '')}'")
            desc = r.get("description", "")
            logger.info(f"[WEB_SEARCH] Result {i+1}: description='{desc}'")

        return ToolExecutionResult(
            tool_name="web_search",
            status=ToolExecutionStatus.COMPLETED,
            success=True,
            data={
                "query": query,
                "count": len(formatted_results),
                "results": formatted_results,
            },
            error=None,
            correlation_id=correlation_id,
        )
