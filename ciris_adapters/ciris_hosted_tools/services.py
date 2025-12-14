"""
CIRIS Hosted Tools - Tool service implementations.

Provides tools that call out to CIRIS hosted services (proxy):
- web_search: Search the web using Brave Search API via CIRIS proxy

These tools require platform-level security guarantees (proof of possession)
that can only be satisfied on platforms with device attestation:
- Android: Google Play Integrity API
- iOS: App Attest (future)
- Web: DPoP (future)
"""

import logging
import os
from typing import Any, Dict, List, Optional
from uuid import uuid4

import httpx

from ciris_engine.schemas.adapters.tools import (
    ToolExecutionResult,
    ToolExecutionStatus,
    ToolInfo,
    ToolParameterSchema,
)
from ciris_engine.schemas.platform import PlatformRequirement

logger = logging.getLogger(__name__)

# Default proxy URL - can be overridden by config
DEFAULT_PROXY_URL = "https://llm.ciris.ai"


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
                "real-time data, recent news, or information beyond your training cutoff. "
                "Returns titles, URLs, and descriptions of relevant web pages."
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
                "Use when you need current information, recent events, live data, "
                "or to verify facts that may have changed since your training cutoff."
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
                - proxy_url: Base URL for CIRIS proxy (default: https://llm.ciris.ai)
                - timeout: Request timeout in seconds (default: 30)
        """
        self.config = config or {}
        self._proxy_url = self.config.get("proxy_url", DEFAULT_PROXY_URL)
        self._timeout = self.config.get("timeout", 30.0)
        self._call_count = 0
        self._error_count = 0
        logger.info(f"CIRISHostedToolService initialized with proxy: {self._proxy_url}")

    async def start(self) -> None:
        """Start the service."""
        logger.info("CIRISHostedToolService started")

    async def stop(self) -> None:
        """Stop the service."""
        logger.info("CIRISHostedToolService stopped")

    def _get_google_id_token(self) -> Optional[str]:
        """Get the Google ID token from environment.

        The token is set by:
        - Android: After native Google Sign-In, stored in CIRIS_BILLING_GOOGLE_ID_TOKEN
        - API: After native token exchange, stored in environment

        Returns:
            Google ID token if available, None otherwise
        """
        # Try multiple env var names for compatibility
        token = os.environ.get("CIRIS_BILLING_GOOGLE_ID_TOKEN")
        if not token:
            token = os.environ.get("GOOGLE_ID_TOKEN")
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

    async def get_tool_result(
        self, correlation_id: str, timeout: float = 30.0
    ) -> Optional[ToolExecutionResult]:
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

    async def _execute_web_search(
        self, parameters: Dict[str, Any], correlation_id: str
    ) -> ToolExecutionResult:
        """Execute a web search via CIRIS proxy.

        Args:
            parameters: Search parameters (q, count)
            correlation_id: Correlation ID for tracking

        Returns:
            ToolExecutionResult with search results or error
        """
        query = parameters.get("q", "")
        count = min(parameters.get("count", 10), 20)  # Cap at 20

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

        # Make request to CIRIS proxy
        search_url = f"{self._proxy_url}/v1/search"
        headers = {
            "Authorization": f"Bearer {google_token}",
            "Content-Type": "application/json",
        }
        payload = {"q": query, "count": count}

        logger.info(f"[WEB_SEARCH] Searching for: {query[:50]}...")

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(search_url, json=payload, headers=headers)

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
                            "You have 3 free searches per day. "
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

                result = response.json()

                # Extract web results from response
                web_results = result.get("results", {}).get("web", {}).get("results", [])

                # Format results for agent consumption
                formatted_results = []
                for r in web_results:
                    formatted_results.append({
                        "title": r.get("title", ""),
                        "url": r.get("url", ""),
                        "description": r.get("description", ""),
                    })

                logger.info(f"[WEB_SEARCH] Got {len(formatted_results)} results for: {query[:50]}")

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

        except httpx.TimeoutException:
            return ToolExecutionResult(
                tool_name="web_search",
                status=ToolExecutionStatus.TIMEOUT,
                success=False,
                data=None,
                error=f"Search timed out after {self._timeout} seconds",
                correlation_id=correlation_id,
            )
        except httpx.RequestError as e:
            return ToolExecutionResult(
                tool_name="web_search",
                status=ToolExecutionStatus.FAILED,
                success=False,
                data=None,
                error=f"Network error: {str(e)}",
                correlation_id=correlation_id,
            )
