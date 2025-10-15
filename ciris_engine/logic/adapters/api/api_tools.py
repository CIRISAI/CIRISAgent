"""
Tool service for API adapter - provides curl functionality.
"""

import asyncio
import json
import logging
import uuid
from typing import Any, Dict, List, Optional

import aiohttp

from ciris_engine.logic.services.base_service import BaseService
from ciris_engine.logic.utils.jsondict_helpers import get_dict, get_float, get_int, get_str
from ciris_engine.protocols.services import ToolService
from ciris_engine.protocols.services.lifecycle.time import TimeServiceProtocol
from ciris_engine.schemas.adapters.tools import ToolExecutionResult, ToolExecutionStatus, ToolInfo, ToolParameterSchema
from ciris_engine.schemas.runtime.enums import ServiceType
from ciris_engine.schemas.services.core import ServiceCapabilities, ServiceStatus
from ciris_engine.schemas.types import JSONDict

logger = logging.getLogger(__name__)

# Constants for tool parameter descriptions
HTTP_HEADERS_DESC = "HTTP headers"
REQUEST_TIMEOUT_DESC = "Request timeout in seconds"


class APIToolService(BaseService, ToolService):
    """Tool service providing curl-like HTTP request functionality."""

    def __init__(self, time_service: Optional[TimeServiceProtocol] = None) -> None:
        # Initialize BaseService with proper arguments
        super().__init__(time_service=time_service, service_name="APIToolService")
        # ToolService is a Protocol, no need to call its __init__
        self._results: Dict[str, ToolExecutionResult] = {}
        self._tools = {
            "curl": self._curl,
            "http_get": self._http_get,
            "http_post": self._http_post,
        }
        # Track tool executions
        self._tool_executions = 0
        self._tool_failures = 0

    async def start(self) -> None:
        """Start the API tool service."""
        await BaseService.start(self)
        logger.info("API tool service started")

    async def stop(self) -> None:
        """Stop the API tool service."""
        await BaseService.stop(self)
        logger.info("API tool service stopped")

    async def execute_tool(self, tool_name: str, parameters: JSONDict) -> ToolExecutionResult:
        """Execute a tool and return the result."""
        # Track request for telemetry
        self._track_request()
        self._tool_executions += 1

        logger.info(f"[API_TOOLS] execute_tool called with tool_name={tool_name}, parameters={parameters}")

        # Debug: print stack trace to see where this is called from
        import traceback

        logger.info(f"[API_TOOLS] Stack trace:\n{''.join(traceback.format_stack())}")

        correlation_id = parameters.get("correlation_id", str(uuid.uuid4()))

        if tool_name not in self._tools:
            self._tool_executions += 1  # Must increment total count
            self._tool_failures += 1  # Unknown tool is a failure!
            return ToolExecutionResult(
                tool_name=tool_name,
                status=ToolExecutionStatus.NOT_FOUND,
                success=False,
                data=None,
                error=f"Unknown tool: {tool_name}",
                correlation_id=correlation_id,
            )

        try:
            result = await self._tools[tool_name](parameters)
            success = result.get("error") is None
            error_msg = result.get("error")

            tool_result = ToolExecutionResult(
                tool_name=tool_name,
                status=ToolExecutionStatus.COMPLETED if success else ToolExecutionStatus.FAILED,
                success=success,
                data=result,
                error=error_msg,
                correlation_id=correlation_id,
            )

            # Type narrow correlation_id to str for dict indexing
            if correlation_id and isinstance(correlation_id, str):
                self._results[correlation_id] = tool_result

            return tool_result

        except Exception as e:
            # Track error for telemetry
            self._track_error(e)
            self._tool_failures += 1
            logger.error(f"Error executing tool {tool_name}: {e}", exc_info=True)
            return ToolExecutionResult(
                tool_name=tool_name,
                status=ToolExecutionStatus.FAILED,
                success=False,
                data=None,
                error=str(e),
                correlation_id=correlation_id,
            )

    async def _curl(self, params: JSONDict) -> JSONDict:
        """Execute a curl-like HTTP request."""
        logger.info(f"[API_TOOLS] _curl called with params: {params}")
        url = get_str(params, "url", "")
        method = get_str(params, "method", "GET").upper()
        headers = get_dict(params, "headers", {})
        data = params.get("data")
        timeout = get_float(params, "timeout", 30.0)

        if not url:
            logger.error(f"[API_TOOLS] URL parameter missing. Params keys: {list(params.keys())}")
            return {"error": "URL parameter is required"}

        try:
            async with aiohttp.ClientSession() as session:
                # Build kwargs with proper types
                timeout_obj = aiohttp.ClientTimeout(total=timeout)
                kwargs: Dict[str, Any] = {"headers": headers, "timeout": timeout_obj}

                if data:
                    if isinstance(data, dict):
                        kwargs["json"] = data
                    else:
                        kwargs["data"] = data

                async with session.request(method, url, **kwargs) as response:
                    text = await response.text()

                    # Try to parse as JSON
                    try:
                        body = json.loads(text)
                    except json.JSONDecodeError:
                        body = text

                    return {
                        "status_code": response.status,
                        "headers": dict(response.headers),
                        "body": body,
                        "url": str(response.url),
                    }

        except asyncio.TimeoutError:
            return {"error": f"Request timed out after {timeout} seconds"}
        except Exception as e:
            return {"error": str(e)}

    async def _http_get(self, params: JSONDict) -> JSONDict:
        """Perform an HTTP GET request."""
        params["method"] = "GET"
        return await self._curl(params)

    async def _http_post(self, params: JSONDict) -> JSONDict:
        """Perform an HTTP POST request."""
        params["method"] = "POST"
        return await self._curl(params)

    async def get_available_tools(self) -> List[str]:
        """Get list of available tool names."""
        return list(self._tools.keys())

    async def get_tool_result(self, correlation_id: str, timeout: float = 30.0) -> Optional[ToolExecutionResult]:
        """Get result of an async tool execution by correlation ID."""
        # All our tools are synchronous, so results should be available immediately
        return self._results.get(correlation_id)

    async def validate_parameters(self, tool_name: str, parameters: JSONDict) -> bool:
        """Validate parameters for a tool."""
        if tool_name in ["curl", "http_get", "http_post"]:
            return "url" in parameters
        return False

    async def list_tools(self) -> List[str]:
        """List available tools - required by ToolServiceProtocol."""
        return list(self._tools.keys())

    async def get_tool_schema(self, tool_name: str) -> Optional[ToolParameterSchema]:
        """Get parameter schema for a specific tool."""
        schemas = {
            "curl": ToolParameterSchema(
                type="object",
                properties={
                    "url": {"type": "string", "description": "URL to request"},
                    "method": {"type": "string", "description": "HTTP method (GET, POST, etc.)", "default": "GET"},
                    "headers": {"type": "object", "description": HTTP_HEADERS_DESC},
                    "data": {"type": ["object", "string"], "description": "Request body data"},
                    "timeout": {"type": "number", "description": REQUEST_TIMEOUT_DESC, "default": 30},
                },
                required=["url"],
            ),
            "http_get": ToolParameterSchema(
                type="object",
                properties={
                    "url": {"type": "string", "description": "URL to GET"},
                    "headers": {"type": "object", "description": HTTP_HEADERS_DESC},
                    "timeout": {"type": "number", "description": REQUEST_TIMEOUT_DESC, "default": 30},
                },
                required=["url"],
            ),
            "http_post": ToolParameterSchema(
                type="object",
                properties={
                    "url": {"type": "string", "description": "URL to POST to"},
                    "headers": {"type": "object", "description": HTTP_HEADERS_DESC},
                    "data": {"type": ["object", "string"], "description": "POST body data"},
                    "timeout": {"type": "number", "description": REQUEST_TIMEOUT_DESC, "default": 30},
                },
                required=["url"],
            ),
        }
        return schemas.get(tool_name)

    async def get_tool_info(self, tool_name: str) -> Optional[ToolInfo]:
        """Get detailed information about a specific tool."""
        descriptions = {
            "curl": "Execute HTTP requests with curl-like functionality",
            "http_get": "Perform HTTP GET requests",
            "http_post": "Perform HTTP POST requests",
        }

        schema = await self.get_tool_schema(tool_name)
        if not schema:
            return None

        return ToolInfo(name=tool_name, description=descriptions.get(tool_name, ""), parameters=schema)

    async def get_all_tool_info(self) -> List[ToolInfo]:
        """Get detailed information about all available tools."""
        infos = []
        for tool_name in self._tools:
            info = await self.get_tool_info(tool_name)
            if info:
                infos.append(info)
        return infos

    async def is_healthy(self) -> bool:
        """Check if the service is healthy."""
        return True

    def get_service_type(self) -> ServiceType:
        """Get the type of this service."""
        return ServiceType.ADAPTER

    def get_capabilities(self) -> ServiceCapabilities:
        """Get service capabilities."""
        return ServiceCapabilities(
            service_name="APIToolService",
            actions=[
                "execute_tool",
                "get_available_tools",
                "get_tool_result",
                "validate_parameters",
                "get_tool_info",
                "get_all_tool_info",
            ],
            version="1.0.0",
            dependencies=[],
            metadata=None,
        )

    def _collect_custom_metrics(self) -> Dict[str, float]:
        """Collect API tool service specific metrics."""
        return {
            "tools_count": float(len(self._tools)),
            "tool_executions_total": float(self._tool_executions),
            "tool_failures_total": float(self._tool_failures),
            "tool_success_rate": float(self._tool_executions - self._tool_failures) / max(1, self._tool_executions),
        }

    def _get_actions(self) -> List[str]:
        """Get the list of actions this service supports."""
        return [
            "execute_tool",
            "get_available_tools",
            "get_tool_result",
            "validate_parameters",
            "get_tool_info",
            "get_all_tool_info",
        ]

    def _check_dependencies(self) -> bool:
        """Check if all dependencies are satisfied."""
        # APIToolService has no hard dependencies
        return True
