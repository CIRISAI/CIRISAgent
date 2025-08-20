"""
Tool service for API adapter - provides curl functionality.
"""

import asyncio
import json
import logging
import uuid
from typing import Dict, List, Optional

import aiohttp

from ciris_engine.protocols.services import ToolService
from ciris_engine.protocols.services.lifecycle.time import TimeServiceProtocol
from ciris_engine.schemas.adapters.tools import ToolExecutionResult, ToolExecutionStatus, ToolInfo, ToolParameterSchema
from ciris_engine.schemas.runtime.enums import ServiceType
from ciris_engine.schemas.services.core import ServiceCapabilities, ServiceStatus

logger = logging.getLogger(__name__)

# Constants for tool parameter descriptions
HTTP_HEADERS_DESC = "HTTP headers"
REQUEST_TIMEOUT_DESC = "Request timeout in seconds"


class APIToolService(ToolService):
    """Tool service providing curl-like HTTP request functionality."""

    def __init__(self, time_service: Optional[TimeServiceProtocol] = None) -> None:
        super().__init__()
        self._time_service = time_service
        self._results: Dict[str, ToolExecutionResult] = {}
        self._tools = {
            "curl": self._curl,
            "http_get": self._http_get,
            "http_post": self._http_post,
        }

    async def start(self) -> None:
        """Start the API tool service."""
        # Don't call super() on abstract method
        logger.info("API tool service started")

    async def stop(self) -> None:
        """Stop the API tool service."""
        # Don't call super() on abstract method
        logger.info("API tool service stopped")

    async def execute_tool(self, tool_name: str, parameters: dict) -> ToolExecutionResult:
        """Execute a tool and return the result."""
        logger.info(f"[API_TOOLS] execute_tool called with tool_name={tool_name}, parameters={parameters}")

        # Debug: print stack trace to see where this is called from
        import traceback

        logger.info(f"[API_TOOLS] Stack trace:\n{''.join(traceback.format_stack())}")

        correlation_id = parameters.get("correlation_id", str(uuid.uuid4()))

        if tool_name not in self._tools:
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

            if correlation_id:
                self._results[correlation_id] = tool_result

            return tool_result

        except Exception as e:
            logger.error(f"Error executing tool {tool_name}: {e}", exc_info=True)
            return ToolExecutionResult(
                tool_name=tool_name,
                status=ToolExecutionStatus.FAILED,
                success=False,
                data=None,
                error=str(e),
                correlation_id=correlation_id,
            )

    async def _curl(self, params: dict) -> dict:
        """Execute a curl-like HTTP request."""
        logger.info(f"[API_TOOLS] _curl called with params: {params}")
        url = params.get("url")
        method = params.get("method", "GET").upper()
        headers = params.get("headers", {})
        data = params.get("data")
        timeout = params.get("timeout", 30)

        if not url:
            logger.error(f"[API_TOOLS] URL parameter missing. Params keys: {list(params.keys())}")
            return {"error": "URL parameter is required"}

        try:
            async with aiohttp.ClientSession() as session:
                kwargs = {"headers": headers, "timeout": aiohttp.ClientTimeout(total=timeout)}

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

    async def _http_get(self, params: dict) -> dict:
        """Perform an HTTP GET request."""
        params["method"] = "GET"
        return await self._curl(params)

    async def _http_post(self, params: dict) -> dict:
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

    async def validate_parameters(self, tool_name: str, parameters: dict) -> bool:
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
            metadata={"max_batch_size": 1, "supports_versioning": False, "supported_formats": ["json"]},
        )

    def get_status(self) -> ServiceStatus:
        """Get service status."""
        return ServiceStatus(
            service_name="APIToolService",
            service_type="tool",
            is_healthy=True,
            uptime_seconds=0,  # Not tracked
            last_error=None,
            metrics={"tools_count": len(self._tools)},
            custom_metrics={"tools_count": float(len(self._tools))},
        )
