"""
MCP Server Request Handlers.

Handlers for MCP protocol methods:
- Tool listing and execution
- Resource listing and reading
- Prompt listing and retrieval
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ciris_adapters.mcp_common.protocol import (
    MCPErrorCode,
    MCPMessage,
    MCPMessageType,
    create_error_response,
    create_success_response,
)
from ciris_adapters.mcp_common.schemas import (
    MCPListPromptsResult,
    MCPListResourcesResult,
    MCPListToolsResult,
    MCPPromptGetResult,
    MCPPromptInfo,
    MCPPromptMessage,
    MCPResourceContent,
    MCPResourceInfo,
    MCPResourceReadResult,
    MCPToolCallResult,
    MCPToolInfo,
    MCPToolInputSchema,
)

from .config import MCPServerExposureConfig

logger = logging.getLogger(__name__)


class MCPToolHandler:
    """Handler for MCP tool-related requests."""

    def __init__(
        self,
        exposure_config: MCPServerExposureConfig,
        tool_bus: Optional[Any] = None,
    ) -> None:
        """Initialize tool handler.

        Args:
            exposure_config: Exposure configuration
            tool_bus: CIRIS ToolBus for executing tools
        """
        self._config = exposure_config
        self._tool_bus = tool_bus
        self._tools_cache: Dict[str, MCPToolInfo] = {}

    async def refresh_tools(self) -> None:
        """Refresh available tools from ToolBus."""
        if not self._tool_bus:
            return

        try:
            # Get tool services from bus
            services = getattr(self._tool_bus, "service_registry", None)
            if not services:
                return

            # Get all tool info from registered services
            from ciris_engine.schemas.runtime.enums import ServiceType

            tool_services = services.get_services_by_type(ServiceType.TOOL)

            for service in tool_services:
                if hasattr(service, "get_all_tool_info"):
                    tool_infos = await service.get_all_tool_info()
                    for tool_info in tool_infos:
                        # Check exposure rules
                        if not self._should_expose_tool(tool_info.name):
                            continue

                        # Convert to MCP format
                        mcp_tool = MCPToolInfo(
                            name=tool_info.name,
                            description=tool_info.description,
                            inputSchema=MCPToolInputSchema(
                                type=tool_info.parameters.type,
                                properties=tool_info.parameters.properties,
                                required=tool_info.parameters.required,
                            ),
                        )
                        self._tools_cache[tool_info.name] = mcp_tool

        except Exception as e:
            logger.error(f"Failed to refresh tools: {e}")

    def _should_expose_tool(self, tool_name: str) -> bool:
        """Check if a tool should be exposed."""
        if not self._config.expose_tools:
            return False

        # Check blocklist
        if tool_name in self._config.tool_blocklist:
            return False

        # Check allowlist (if specified)
        if self._config.tool_allowlist:
            return tool_name in self._config.tool_allowlist

        return True

    def register_tool(
        self,
        name: str,
        description: str,
        input_schema: Dict[str, Any],
    ) -> None:
        """Register a tool for exposure.

        Args:
            name: Tool name
            description: Tool description
            input_schema: JSON Schema for input
        """
        if not self._should_expose_tool(name):
            return

        self._tools_cache[name] = MCPToolInfo(
            name=name,
            description=description,
            inputSchema=MCPToolInputSchema(
                type=input_schema.get("type", "object"),
                properties=input_schema.get("properties", {}),
                required=input_schema.get("required", []),
            ),
        )

    async def handle_list_tools(self, request_id: Any) -> MCPMessage:
        """Handle tools/list request.

        Args:
            request_id: Request ID

        Returns:
            MCPMessage response
        """
        await self.refresh_tools()

        tools = list(self._tools_cache.values())
        result = MCPListToolsResult(tools=tools)

        return create_success_response(request_id, result.model_dump())

    async def handle_call_tool(self, request_id: Any, params: Dict[str, Any]) -> MCPMessage:
        """Handle tools/call request.

        Args:
            request_id: Request ID
            params: Call parameters (name, arguments)

        Returns:
            MCPMessage response
        """
        tool_name = params.get("name")
        arguments = params.get("arguments", {})

        if not tool_name:
            return create_error_response(
                request_id,
                MCPErrorCode.INVALID_PARAMS,
                "Missing tool name",
            )

        # Check if tool is exposed
        if tool_name not in self._tools_cache:
            return create_error_response(
                request_id,
                MCPErrorCode.TOOL_NOT_FOUND,
                f"Tool not found: {tool_name}",
            )

        try:
            # Execute via ToolBus
            if self._tool_bus:
                result = await self._tool_bus.execute_tool(
                    tool_name=tool_name,
                    parameters=arguments,
                    handler_name="mcp_server",
                )

                if result.success:
                    content = [{"type": "text", "text": str(result.data)}]
                    return create_success_response(
                        request_id,
                        MCPToolCallResult(content=content, isError=False).model_dump(),
                    )
                else:
                    content = [{"type": "text", "text": result.error or "Tool execution failed"}]
                    return create_success_response(
                        request_id,
                        MCPToolCallResult(content=content, isError=True).model_dump(),
                    )
            else:
                # No tool bus - return mock response
                content = [{"type": "text", "text": f"Mock result for {tool_name}"}]
                return create_success_response(
                    request_id,
                    MCPToolCallResult(content=content, isError=False).model_dump(),
                )

        except Exception as e:
            logger.error(f"Tool execution error: {e}")
            return create_error_response(
                request_id,
                MCPErrorCode.INTERNAL_ERROR,
                str(e),
            )


class MCPResourceHandler:
    """Handler for MCP resource-related requests."""

    def __init__(
        self,
        exposure_config: MCPServerExposureConfig,
        runtime: Optional[Any] = None,
    ) -> None:
        """Initialize resource handler.

        Args:
            exposure_config: Exposure configuration
            runtime: CIRIS runtime for accessing services
        """
        self._config = exposure_config
        self._runtime = runtime
        self._resources_cache: Dict[str, MCPResourceInfo] = {}

        # Register default resources
        self._register_default_resources()

    def _register_default_resources(self) -> None:
        """Register default CIRIS resources."""
        # Status resource
        self._resources_cache["ciris://status"] = MCPResourceInfo(
            uri="ciris://status",
            name="Agent Status",
            description="Current CIRIS agent status and health",
            mimeType="application/json",
        )

        # Health resource
        self._resources_cache["ciris://health"] = MCPResourceInfo(
            uri="ciris://health",
            name="Health Check",
            description="Agent health check information",
            mimeType="application/json",
        )

        # Telemetry resource
        self._resources_cache["ciris://telemetry"] = MCPResourceInfo(
            uri="ciris://telemetry",
            name="Telemetry",
            description="Agent telemetry and metrics",
            mimeType="application/json",
        )

    def _should_expose_resource(self, uri: str) -> bool:
        """Check if a resource should be exposed."""
        if not self._config.expose_resources:
            return False

        # Check blocklist
        if uri in self._config.resource_blocklist:
            return False

        # Check allowlist (if specified)
        if self._config.resource_allowlist:
            return uri in self._config.resource_allowlist

        return True

    def register_resource(
        self,
        uri: str,
        name: str,
        description: str,
        mime_type: str = "text/plain",
    ) -> None:
        """Register a resource for exposure.

        Args:
            uri: Resource URI
            name: Resource name
            description: Resource description
            mime_type: MIME type
        """
        if not self._should_expose_resource(uri):
            return

        self._resources_cache[uri] = MCPResourceInfo(
            uri=uri,
            name=name,
            description=description,
            mimeType=mime_type,
        )

    async def handle_list_resources(self, request_id: Any) -> MCPMessage:
        """Handle resources/list request.

        Args:
            request_id: Request ID

        Returns:
            MCPMessage response
        """
        resources = [r for r in self._resources_cache.values() if self._should_expose_resource(r.uri)]
        result = MCPListResourcesResult(resources=resources)

        return create_success_response(request_id, result.model_dump())

    async def handle_read_resource(self, request_id: Any, params: Dict[str, Any]) -> MCPMessage:
        """Handle resources/read request.

        Args:
            request_id: Request ID
            params: Read parameters (uri)

        Returns:
            MCPMessage response
        """
        uri = params.get("uri")

        if not uri:
            return create_error_response(
                request_id,
                MCPErrorCode.INVALID_PARAMS,
                "Missing resource URI",
            )

        if not self._should_expose_resource(uri):
            return create_error_response(
                request_id,
                MCPErrorCode.RESOURCE_NOT_FOUND,
                f"Resource not found: {uri}",
            )

        try:
            content = await self._read_resource(uri)
            result = MCPResourceReadResult(contents=[content])
            return create_success_response(request_id, result.model_dump())

        except Exception as e:
            logger.error(f"Resource read error: {e}")
            return create_error_response(
                request_id,
                MCPErrorCode.INTERNAL_ERROR,
                str(e),
            )

    async def _read_resource(self, uri: str) -> MCPResourceContent:
        """Read resource content.

        Args:
            uri: Resource URI

        Returns:
            MCPResourceContent
        """
        import json

        if uri == "ciris://status":
            status = await self._get_agent_status()
            return MCPResourceContent(
                uri=uri,
                mimeType="application/json",
                text=json.dumps(status, indent=2),
            )

        elif uri == "ciris://health":
            health = await self._get_health()
            return MCPResourceContent(
                uri=uri,
                mimeType="application/json",
                text=json.dumps(health, indent=2),
            )

        elif uri == "ciris://telemetry":
            telemetry = await self._get_telemetry()
            return MCPResourceContent(
                uri=uri,
                mimeType="application/json",
                text=json.dumps(telemetry, indent=2),
            )

        else:
            return MCPResourceContent(
                uri=uri,
                mimeType="text/plain",
                text=f"Resource content for {uri}",
            )

    async def _get_agent_status(self) -> Dict[str, Any]:
        """Get agent status."""
        if self._runtime and hasattr(self._runtime, "get_status"):
            return await self._runtime.get_status()
        return {
            "status": "running",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    async def _get_health(self) -> Dict[str, Any]:
        """Get health information."""
        return {
            "healthy": True,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    async def _get_telemetry(self) -> Dict[str, Any]:
        """Get telemetry data."""
        return {
            "uptime_seconds": 0,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }


class MCPPromptHandler:
    """Handler for MCP prompt-related requests."""

    def __init__(
        self,
        exposure_config: MCPServerExposureConfig,
        wise_bus: Optional[Any] = None,
    ) -> None:
        """Initialize prompt handler.

        Args:
            exposure_config: Exposure configuration
            wise_bus: CIRIS WiseBus for guidance
        """
        self._config = exposure_config
        self._wise_bus = wise_bus
        self._prompts_cache: Dict[str, MCPPromptInfo] = {}

        # Register default prompts
        self._register_default_prompts()

    def _register_default_prompts(self) -> None:
        """Register default CIRIS prompts."""
        from ciris_adapters.mcp_common.schemas import MCPPromptArgument

        # Guidance prompt
        self._prompts_cache["guidance"] = MCPPromptInfo(
            name="guidance",
            description="Get ethical guidance from CIRIS wise authority",
            arguments=[
                MCPPromptArgument(
                    name="question",
                    description="The question or situation to get guidance on",
                    required=True,
                ),
                MCPPromptArgument(
                    name="context",
                    description="Additional context for the guidance request",
                    required=False,
                ),
            ],
        )

        # Ethical review prompt
        self._prompts_cache["ethical_review"] = MCPPromptInfo(
            name="ethical_review",
            description="Request an ethical review of a proposed action",
            arguments=[
                MCPPromptArgument(
                    name="action",
                    description="The action to review",
                    required=True,
                ),
                MCPPromptArgument(
                    name="stakeholders",
                    description="Affected stakeholders",
                    required=False,
                ),
            ],
        )

    def _should_expose_prompt(self, name: str) -> bool:
        """Check if a prompt should be exposed."""
        if not self._config.expose_prompts:
            return False

        # Check blocklist
        if name in self._config.prompt_blocklist:
            return False

        # Check allowlist (if specified)
        if self._config.prompt_allowlist:
            return name in self._config.prompt_allowlist

        return True

    def register_prompt(
        self,
        name: str,
        description: str,
        arguments: List[Dict[str, Any]],
    ) -> None:
        """Register a prompt for exposure.

        Args:
            name: Prompt name
            description: Prompt description
            arguments: Prompt arguments
        """
        if not self._should_expose_prompt(name):
            return

        from ciris_adapters.mcp_common.schemas import MCPPromptArgument

        self._prompts_cache[name] = MCPPromptInfo(
            name=name,
            description=description,
            arguments=[
                MCPPromptArgument(
                    name=arg.get("name", ""),
                    description=arg.get("description"),
                    required=arg.get("required", False),
                )
                for arg in arguments
            ],
        )

    async def handle_list_prompts(self, request_id: Any) -> MCPMessage:
        """Handle prompts/list request.

        Args:
            request_id: Request ID

        Returns:
            MCPMessage response
        """
        prompts = [p for p in self._prompts_cache.values() if self._should_expose_prompt(p.name)]
        result = MCPListPromptsResult(prompts=prompts)

        return create_success_response(request_id, result.model_dump())

    async def handle_get_prompt(self, request_id: Any, params: Dict[str, Any]) -> MCPMessage:
        """Handle prompts/get request.

        Args:
            request_id: Request ID
            params: Get parameters (name, arguments)

        Returns:
            MCPMessage response
        """
        prompt_name = params.get("name")
        arguments = params.get("arguments", {})

        if not prompt_name:
            return create_error_response(
                request_id,
                MCPErrorCode.INVALID_PARAMS,
                "Missing prompt name",
            )

        if not self._should_expose_prompt(prompt_name):
            return create_error_response(
                request_id,
                MCPErrorCode.PROMPT_NOT_FOUND,
                f"Prompt not found: {prompt_name}",
            )

        try:
            messages = await self._get_prompt_messages(prompt_name, arguments)
            result = MCPPromptGetResult(messages=messages)
            return create_success_response(request_id, result.model_dump())

        except Exception as e:
            logger.error(f"Prompt get error: {e}")
            return create_error_response(
                request_id,
                MCPErrorCode.INTERNAL_ERROR,
                str(e),
            )

    async def _get_prompt_messages(self, name: str, arguments: Dict[str, str]) -> List[MCPPromptMessage]:
        """Get prompt messages.

        Args:
            name: Prompt name
            arguments: Prompt arguments

        Returns:
            List of MCPPromptMessage
        """
        if name == "guidance":
            question = arguments.get("question", "")
            context = arguments.get("context", "")

            # Try to get guidance from WiseBus
            if self._wise_bus:
                try:
                    from ciris_engine.schemas.services.context import GuidanceContext

                    guidance_context = GuidanceContext(
                        thought_id=f"mcp_prompt_{id(arguments)}",
                        task_id=f"mcp_task_{id(arguments)}",
                        question=question,
                        ethical_considerations=[],
                        domain_context={"context": context} if context else {},
                    )
                    guidance = await self._wise_bus.fetch_guidance(guidance_context)
                    if guidance:
                        return [
                            MCPPromptMessage(
                                role="assistant",
                                content={"type": "text", "text": guidance},
                            )
                        ]
                except Exception as e:
                    logger.warning(f"Failed to get guidance from WiseBus: {e}")

            # Default response
            return [
                MCPPromptMessage(
                    role="assistant",
                    content={
                        "type": "text",
                        "text": f"Guidance for: {question}\n\nContext: {context or 'None provided'}",
                    },
                )
            ]

        elif name == "ethical_review":
            action = arguments.get("action", "")
            stakeholders = arguments.get("stakeholders", "")

            return [
                MCPPromptMessage(
                    role="assistant",
                    content={
                        "type": "text",
                        "text": f"Ethical review of action: {action}\n\nStakeholders: {stakeholders or 'Not specified'}",
                    },
                )
            ]

        else:
            return [
                MCPPromptMessage(
                    role="assistant",
                    content={"type": "text", "text": f"Response for prompt: {name}"},
                )
            ]


__all__ = [
    "MCPToolHandler",
    "MCPResourceHandler",
    "MCPPromptHandler",
]
