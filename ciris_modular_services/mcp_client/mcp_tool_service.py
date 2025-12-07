"""
MCP Tool Service.

Provides tool execution capabilities through MCP servers.
Integrates with the ToolBus for the CIRIS agent.

Security measures:
- Tool poisoning detection on all tool descriptions
- Input/output validation
- Rate limiting per server
- Permission enforcement
"""

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ciris_engine.protocols.services.lifecycle.time import TimeServiceProtocol
from ciris_engine.schemas.adapters.tools import ToolExecutionResult, ToolExecutionStatus, ToolInfo, ToolParameterSchema
from ciris_engine.schemas.runtime.enums import ServiceType
from ciris_engine.schemas.types import JSONDict

from .config import MCPBusType, MCPServerConfig
from .security import MCPSecurityManager

logger = logging.getLogger(__name__)


class MCPToolService:
    """
    Tool service that exposes MCP server tools to the CIRIS ToolBus.

    This service:
    - Discovers tools from MCP servers
    - Validates tool access through security manager
    - Executes tools with proper error handling
    - Provides telemetry and metrics
    """

    def __init__(
        self,
        security_manager: MCPSecurityManager,
        time_service: Optional[TimeServiceProtocol] = None,
    ) -> None:
        """Initialize MCP tool service.

        Args:
            security_manager: Security manager for validation
            time_service: Time service for timestamps
        """
        self._security_manager = security_manager
        self._time_service = time_service
        self._running = False
        self._start_time: Optional[datetime] = None

        # MCP clients per server (will be populated by adapter)
        self._mcp_clients: Dict[str, Any] = {}

        # Cached tool information
        self._tools_cache: Dict[str, Dict[str, ToolInfo]] = {}  # server_id -> {tool_name -> ToolInfo}

        # Metrics
        self._executions = 0
        self._errors = 0
        self._blocked = 0

    def register_mcp_client(self, server_id: str, client: Any) -> None:
        """Register an MCP client for a server.

        Args:
            server_id: Server identifier
            client: MCP client instance (from mcp SDK)
        """
        self._mcp_clients[server_id] = client
        logger.info(f"Registered MCP client for server '{server_id}'")

    def unregister_mcp_client(self, server_id: str) -> None:
        """Unregister an MCP client.

        Args:
            server_id: Server to unregister
        """
        if server_id in self._mcp_clients:
            del self._mcp_clients[server_id]
            logger.info(f"Unregistered MCP client for server '{server_id}'")
        if server_id in self._tools_cache:
            del self._tools_cache[server_id]

    async def start(self) -> None:
        """Start the tool service."""
        self._running = True
        self._start_time = self._time_service.now() if self._time_service else datetime.now(timezone.utc)
        logger.info("MCPToolService started")

    async def stop(self) -> None:
        """Stop the tool service."""
        self._running = False
        self._tools_cache.clear()
        logger.info("MCPToolService stopped")

    async def is_healthy(self) -> bool:
        """Check if the tool service is healthy."""
        return self._running and len(self._mcp_clients) > 0

    def get_capabilities(self) -> Any:
        """Get service capabilities for registration."""
        from ciris_engine.schemas.services.capabilities import ServiceCapabilities

        return ServiceCapabilities(
            service_type=ServiceType.TOOL,
            actions=[
                "execute_tool",
                "get_available_tools",
                "get_tool_result",
                "validate_parameters",
                "get_tool_info",
                "get_all_tool_info",
            ],
        )

    def get_service_metadata(self) -> Dict[str, Any]:
        """Get service metadata for DSAR and data source discovery."""
        return {
            "data_source": False,  # MCP tools don't store data
            "service_type": "mcp_tool_service",
            "servers_connected": len(self._mcp_clients),
        }

    async def _refresh_tools_cache(self, server_id: str) -> None:
        """Refresh the tools cache for a server.

        Args:
            server_id: Server to refresh tools for
        """
        client = self._mcp_clients.get(server_id)
        if not client:
            return

        try:
            # Call MCP list_tools
            if hasattr(client, "list_tools"):
                response = await client.list_tools()
                tools = response.tools if hasattr(response, "tools") else []

                self._tools_cache[server_id] = {}

                for tool in tools:
                    # Extract tool info
                    name = tool.name if hasattr(tool, "name") else str(tool.get("name", ""))
                    description = tool.description if hasattr(tool, "description") else str(tool.get("description", ""))
                    input_schema = tool.inputSchema if hasattr(tool, "inputSchema") else tool.get("inputSchema", {})

                    # Security check for tool poisoning
                    allowed, violation = await self._security_manager.check_tool_access(server_id, name, description)

                    if not allowed:
                        logger.warning(
                            f"Tool '{name}' from server '{server_id}' blocked by security: "
                            f"{violation.description if violation else 'Unknown reason'}"
                        )
                        self._blocked += 1
                        continue

                    # Build ToolInfo
                    tool_info = ToolInfo(
                        name=f"mcp_{server_id}_{name}",  # Prefix to avoid conflicts
                        description=description,
                        parameters=ToolParameterSchema(
                            type=input_schema.get("type", "object"),
                            properties=input_schema.get("properties", {}),
                            required=input_schema.get("required", []),
                        ),
                        category=f"mcp.{server_id}",
                        cost=0.0,
                        when_to_use=f"Use this tool when you need to {description[:100]}...",
                    )

                    self._tools_cache[server_id][name] = tool_info

                logger.debug(
                    f"Refreshed tools cache for '{server_id}': " f"{len(self._tools_cache[server_id])} tools available"
                )

        except Exception as e:
            logger.error(f"Failed to refresh tools for server '{server_id}': {e}")

    async def get_available_tools(self) -> List[str]:
        """Get list of all available tool names."""
        # Refresh caches if needed
        for server_id in self._mcp_clients:
            if server_id not in self._tools_cache:
                await self._refresh_tools_cache(server_id)

        tools = []
        for server_id, server_tools in self._tools_cache.items():
            for tool_name, tool_info in server_tools.items():
                tools.append(tool_info.name)

        return tools

    async def list_tools(self) -> List[str]:
        """Alias for get_available_tools (protocol compatibility)."""
        return await self.get_available_tools()

    async def get_tool_info(self, tool_name: str) -> Optional[ToolInfo]:
        """Get detailed information about a specific tool.

        Args:
            tool_name: Tool name (may be prefixed with mcp_serverid_)

        Returns:
            ToolInfo or None if not found
        """
        # Parse tool name to find server and original name
        server_id, original_name = self._parse_tool_name(tool_name)

        if not server_id:
            # Search all servers
            for sid, tools in self._tools_cache.items():
                if tool_name in tools:
                    return tools[tool_name]
                # Also check by full prefixed name
                for name, info in tools.items():
                    if info.name == tool_name:
                        return info
            return None

        if server_id in self._tools_cache and original_name in self._tools_cache[server_id]:
            return self._tools_cache[server_id][original_name]

        return None

    async def get_all_tool_info(self) -> List[ToolInfo]:
        """Get detailed information about all available tools."""
        # Refresh caches if needed
        for server_id in self._mcp_clients:
            if server_id not in self._tools_cache:
                await self._refresh_tools_cache(server_id)

        all_tools = []
        for server_tools in self._tools_cache.values():
            all_tools.extend(server_tools.values())

        return all_tools

    async def get_tool_schema(self, tool_name: str) -> Optional[ToolParameterSchema]:
        """Get parameter schema for a specific tool.

        Args:
            tool_name: Tool name

        Returns:
            ToolParameterSchema or None
        """
        tool_info = await self.get_tool_info(tool_name)
        if tool_info:
            return tool_info.parameters
        return None

    async def validate_parameters(self, tool_name: str, parameters: JSONDict) -> bool:
        """Validate parameters for a specific tool.

        Args:
            tool_name: Tool name
            parameters: Parameters to validate

        Returns:
            True if valid, False otherwise
        """
        schema = await self.get_tool_schema(tool_name)
        if not schema:
            return False

        # Check required parameters
        for required in schema.required:
            if required not in parameters:
                return False

        # Additional validation could be added here (type checking, etc.)
        return True

    async def execute_tool(self, tool_name: str, parameters: JSONDict) -> ToolExecutionResult:
        """Execute a tool with validated parameters.

        Args:
            tool_name: Tool name (may be prefixed)
            parameters: Tool parameters

        Returns:
            ToolExecutionResult with execution outcome
        """
        correlation_id = str(uuid.uuid4())
        self._executions += 1

        # Parse tool name
        server_id, original_name = self._parse_tool_name(tool_name)

        if not server_id:
            # Try to find the server for this tool
            for sid, tools in self._tools_cache.items():
                for name, info in tools.items():
                    if info.name == tool_name or name == tool_name:
                        server_id = sid
                        original_name = name
                        break
                if server_id:
                    break

        if not server_id or server_id not in self._mcp_clients:
            self._errors += 1
            return ToolExecutionResult(
                tool_name=tool_name,
                status=ToolExecutionStatus.NOT_FOUND,
                success=False,
                data=None,
                error=f"No MCP server found for tool '{tool_name}'",
                correlation_id=correlation_id,
            )

        client = self._mcp_clients[server_id]

        # Security checks
        # Check rate limit
        allowed, violation = await self._security_manager.check_rate_limit(server_id)
        if not allowed:
            self._blocked += 1
            return ToolExecutionResult(
                tool_name=tool_name,
                status=ToolExecutionStatus.FAILED,
                success=False,
                data=None,
                error=f"Rate limit exceeded: {violation.description if violation else ''}",
                correlation_id=correlation_id,
            )

        try:
            # Validate input
            allowed, violation = await self._security_manager.validate_input(server_id, original_name, parameters)
            if not allowed:
                self._blocked += 1
                await self._security_manager.release_rate_limit(server_id)
                return ToolExecutionResult(
                    tool_name=tool_name,
                    status=ToolExecutionStatus.FAILED,
                    success=False,
                    data=None,
                    error=f"Input validation failed: {violation.description if violation else ''}",
                    correlation_id=correlation_id,
                )

            # Execute the tool
            if hasattr(client, "call_tool"):
                response = await client.call_tool(original_name, parameters)

                # Extract result
                if hasattr(response, "content"):
                    # MCP response format
                    content = response.content
                    if isinstance(content, list) and len(content) > 0:
                        result_data = content[0]
                        if hasattr(result_data, "text"):
                            data = {"result": result_data.text}
                        else:
                            data = {"result": str(result_data)}
                    else:
                        data = {"result": str(content)}
                else:
                    data = {"result": str(response)}

                # Validate output
                allowed, violation = await self._security_manager.validate_output(server_id, original_name, data)
                if not allowed:
                    self._blocked += 1
                    return ToolExecutionResult(
                        tool_name=tool_name,
                        status=ToolExecutionStatus.FAILED,
                        success=False,
                        data=None,
                        error=f"Output validation failed: {violation.description if violation else ''}",
                        correlation_id=correlation_id,
                    )

                return ToolExecutionResult(
                    tool_name=tool_name,
                    status=ToolExecutionStatus.COMPLETED,
                    success=True,
                    data=data,
                    error=None,
                    correlation_id=correlation_id,
                )
            else:
                self._errors += 1
                return ToolExecutionResult(
                    tool_name=tool_name,
                    status=ToolExecutionStatus.FAILED,
                    success=False,
                    data=None,
                    error="MCP client does not support call_tool",
                    correlation_id=correlation_id,
                )

        except Exception as e:
            self._errors += 1
            logger.error(f"Failed to execute MCP tool '{tool_name}': {e}", exc_info=True)
            return ToolExecutionResult(
                tool_name=tool_name,
                status=ToolExecutionStatus.FAILED,
                success=False,
                data=None,
                error=str(e),
                correlation_id=correlation_id,
            )
        finally:
            await self._security_manager.release_rate_limit(server_id)

    async def get_tool_result(self, correlation_id: str, timeout: float = 30.0) -> Optional[ToolExecutionResult]:
        """Get result of a previously executed tool.

        MCP tools are synchronous, so this returns None.
        """
        # MCP tools are synchronous - results are returned immediately
        return None

    def _parse_tool_name(self, tool_name: str) -> tuple[Optional[str], str]:
        """Parse a tool name to extract server ID and original name.

        Args:
            tool_name: Tool name, possibly prefixed with mcp_serverid_

        Returns:
            (server_id, original_name) tuple
        """
        if tool_name.startswith("mcp_"):
            parts = tool_name.split("_", 2)
            if len(parts) >= 3:
                return parts[1], parts[2]
        return None, tool_name

    async def get_telemetry(self) -> JSONDict:
        """Get telemetry data for the tool service."""
        uptime_seconds = 0.0
        if self._start_time:
            now = self._time_service.now() if self._time_service else datetime.now(timezone.utc)
            uptime_seconds = (now - self._start_time).total_seconds()

        tools_count = sum(len(tools) for tools in self._tools_cache.values())

        return {
            "service_name": "mcp_tool_service",
            "healthy": self._running,
            "tool_executions": self._executions,
            "error_count": self._errors,
            "blocked_count": self._blocked,
            "available_tools": tools_count,
            "servers_connected": len(self._mcp_clients),
            "uptime_seconds": uptime_seconds,
            "security_metrics": self._security_manager.get_security_metrics(),
        }


__all__ = ["MCPToolService"]
