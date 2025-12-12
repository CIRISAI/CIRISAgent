"""
MCP Server Adapter for CIRIS.

Exposes CIRIS as an MCP server, allowing external AI agents
and applications to interact with CIRIS via the Model Context Protocol.
"""

import asyncio
import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, TypedDict, Union, cast

from ciris_adapters.mcp_common.protocol import (
    ClientCapabilities,
    InitializeResult,
    MCPErrorCode,
    MCPMessage,
    MCPMessageType,
    ServerCapabilities,
    create_error_response,
    create_notification,
    create_success_response,
    validate_mcp_message,
)
from ciris_engine.logic.adapters.base import Service
from ciris_engine.logic.registries.base import Priority
from ciris_engine.schemas.adapters import AdapterServiceRegistration
from ciris_engine.schemas.runtime.enums import ServiceType
from ciris_engine.schemas.types import JSONDict

from .config import MCPServerAdapterConfig, TransportType
from .handlers import MCPPromptHandler, MCPResourceHandler, MCPToolHandler
from .security import AuthResult, ClientSession, MCPServerSecurityManager

logger = logging.getLogger(__name__)


class MCPServerAdapterKwargs(TypedDict, total=False):
    """Type-safe kwargs for MCPServerAdapter initialization."""

    adapter_config: Union[MCPServerAdapterConfig, Dict[str, Any]]
    config_service: Any


class Adapter(Service):
    """
    MCP Server Adapter for CIRIS.

    Exposes CIRIS capabilities via the Model Context Protocol:
    - Tools from ToolBus
    - Resources from agent state/services
    - Prompts from WiseBus
    """

    def __init__(self, runtime: Any, context: Optional[Any] = None, **kwargs: Any) -> None:
        """Initialize MCP server adapter.

        Args:
            runtime: CIRIS runtime instance
            context: Optional adapter startup context
            **kwargs: Additional configuration options
        """
        super().__init__(config=None)

        self.runtime = runtime
        self.context = context
        self.adapter_id = "mcp_server"

        # Cast kwargs for type safety
        typed_kwargs = cast(MCPServerAdapterKwargs, kwargs)

        # Initialize configuration
        self._initialize_config(typed_kwargs)

        # Initialize security manager
        self._security_manager = MCPServerSecurityManager(self.config.security)

        # Initialize handlers
        self._tool_handler = MCPToolHandler(
            exposure_config=self.config.exposure,
            tool_bus=getattr(runtime, "tool_bus", None),
        )

        self._resource_handler = MCPResourceHandler(
            exposure_config=self.config.exposure,
            runtime=runtime,
        )

        self._prompt_handler = MCPPromptHandler(
            exposure_config=self.config.exposure,
            wise_bus=getattr(runtime, "wise_bus", None),
        )

        # Server state
        self._running = False
        self._start_time: Optional[datetime] = None
        self._sessions: Dict[str, ClientSession] = {}

        # Transport state
        self._server_task: Optional[asyncio.Task[Any]] = None
        self._shutdown_event = asyncio.Event()

        # Metrics
        self._requests_handled = 0
        self._errors = 0

    def _initialize_config(self, kwargs: MCPServerAdapterKwargs) -> None:
        """Initialize adapter configuration."""
        if "adapter_config" in kwargs and kwargs["adapter_config"] is not None:
            adapter_config = kwargs["adapter_config"]
            if isinstance(adapter_config, MCPServerAdapterConfig):
                self.config = adapter_config
            elif isinstance(adapter_config, dict):
                self.config = MCPServerAdapterConfig(**adapter_config)
            else:
                self.config = MCPServerAdapterConfig()
        else:
            self.config = MCPServerAdapterConfig()

        self.config.load_env_vars()
        self.adapter_id = f"mcp_server_{self.config.server_id}"

        logger.info(
            f"MCP Server configured: id={self.config.server_id}, " f"transport={self.config.transport.type.value}"
        )

    def get_services_to_register(self) -> List[AdapterServiceRegistration]:
        """Get services to register.

        MCP Server doesn't provide services to CIRIS buses,
        it exposes CIRIS services to external clients.
        """
        # No services to register - we expose, not provide
        return []

    async def start(self) -> None:
        """Start the MCP server adapter."""
        logger.info("Starting MCP Server Adapter...")

        self._running = True
        self._start_time = datetime.now(timezone.utc)

        # Register default tools for exposure
        await self._register_default_tools()

        if self.config.auto_start:
            await self._start_server()

        logger.info("MCP Server Adapter started")

    async def _register_default_tools(self) -> None:
        """Register default CIRIS tools for MCP exposure."""
        # These tools will be available via MCP
        self._tool_handler.register_tool(
            name="ciris_search_memory",
            description="Search CIRIS agent memory for information",
            input_schema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum results",
                        "default": 10,
                    },
                },
                "required": ["query"],
            },
        )

        self._tool_handler.register_tool(
            name="ciris_get_status",
            description="Get CIRIS agent status and health information",
            input_schema={
                "type": "object",
                "properties": {},
            },
        )

        self._tool_handler.register_tool(
            name="ciris_submit_task",
            description="Submit a task for CIRIS agent to process",
            input_schema={
                "type": "object",
                "properties": {
                    "task": {
                        "type": "string",
                        "description": "Task description",
                    },
                    "priority": {
                        "type": "string",
                        "enum": ["low", "normal", "high"],
                        "default": "normal",
                    },
                },
                "required": ["task"],
            },
        )

    async def _start_server(self) -> None:
        """Start the MCP server based on transport type."""
        transport = self.config.transport.type

        if transport == TransportType.STDIO:
            self._server_task = asyncio.create_task(
                self._run_stdio_server(),
                name="MCPServerStdio",
            )
        elif transport in (TransportType.SSE, TransportType.STREAMABLE_HTTP):
            self._server_task = asyncio.create_task(
                self._run_http_server(),
                name="MCPServerHTTP",
            )
        else:
            logger.warning(f"Unsupported transport: {transport}")

    async def _run_stdio_server(self) -> None:
        """Run MCP server over stdio transport."""
        logger.info("Starting MCP stdio server...")

        reader = asyncio.StreamReader()
        protocol = asyncio.StreamReaderProtocol(reader)

        # Get stdin/stdout
        loop = asyncio.get_event_loop()
        await loop.connect_read_pipe(lambda: protocol, sys.stdin)

        writer_transport, writer_protocol = await loop.connect_write_pipe(asyncio.streams.FlowControlMixin, sys.stdout)
        writer = asyncio.StreamWriter(writer_transport, writer_protocol, reader, loop)

        try:
            while not self._shutdown_event.is_set():
                try:
                    # Read line from stdin
                    line = await asyncio.wait_for(
                        reader.readline(),
                        timeout=1.0,
                    )

                    if not line:
                        break

                    # Parse and handle message
                    response = await self._handle_message(line.decode().strip())

                    if response:
                        writer.write((json.dumps(response.model_dump()) + "\n").encode())
                        await writer.drain()

                except asyncio.TimeoutError:
                    continue
                except Exception as e:
                    logger.error(f"Error handling stdio message: {e}")

        except asyncio.CancelledError:
            pass
        finally:
            writer.close()

    async def _run_http_server(self) -> None:
        """Run MCP server over HTTP/SSE transport."""
        logger.info(f"Starting MCP HTTP server on " f"{self.config.transport.host}:{self.config.transport.port}")

        # Simple HTTP server implementation
        # In production, would use aiohttp or similar
        try:
            server = await asyncio.start_server(
                self._handle_http_connection,
                self.config.transport.host,
                self.config.transport.port,
            )

            async with server:
                await self._shutdown_event.wait()

        except Exception as e:
            logger.error(f"HTTP server error: {e}")

    async def _handle_http_connection(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        """Handle an HTTP connection.

        Args:
            reader: Stream reader
            writer: Stream writer
        """
        try:
            # Read HTTP request
            request_line = await reader.readline()
            headers = {}

            while True:
                header_line = await reader.readline()
                if header_line == b"\r\n":
                    break
                if b":" in header_line:
                    key, value = header_line.decode().split(":", 1)
                    headers[key.strip().lower()] = value.strip()

            # Read body if present
            content_length = int(headers.get("content-length", 0))
            body = b""
            if content_length > 0:
                body = await reader.read(content_length)

            # Handle MCP message
            if body:
                response = await self._handle_message(body.decode())

                # Send HTTP response
                response_body = json.dumps(response.model_dump()) if response else "{}"
                http_response = (
                    "HTTP/1.1 200 OK\r\n"
                    "Content-Type: application/json\r\n"
                    f"Content-Length: {len(response_body)}\r\n"
                    "\r\n"
                    f"{response_body}"
                )
                writer.write(http_response.encode())
                await writer.drain()

        except Exception as e:
            logger.error(f"HTTP connection error: {e}")
        finally:
            writer.close()
            await writer.wait_closed()

    async def _handle_message(self, message_str: str) -> Optional[MCPMessage]:
        """Handle an incoming MCP message.

        Args:
            message_str: Raw message string

        Returns:
            Response MCPMessage or None
        """
        self._requests_handled += 1

        try:
            # Parse message
            data = json.loads(message_str)

            # Validate structure
            is_valid, error = validate_mcp_message(data)
            if not is_valid:
                self._errors += 1
                return create_error_response(
                    data.get("id"),
                    MCPErrorCode.INVALID_REQUEST,
                    error or "Invalid message",
                )

            message = MCPMessage(**data)

            # Handle based on method
            if message.is_notification():
                await self._handle_notification(message)
                return None  # Notifications don't get responses

            return await self._handle_request(message)

        except json.JSONDecodeError as e:
            self._errors += 1
            return create_error_response(
                None,
                MCPErrorCode.PARSE_ERROR,
                f"JSON parse error: {e}",
            )
        except Exception as e:
            self._errors += 1
            logger.error(f"Message handling error: {e}")
            return create_error_response(
                None,
                MCPErrorCode.INTERNAL_ERROR,
                str(e),
            )

    async def _handle_notification(self, message: MCPMessage) -> None:
        """Handle a notification message.

        Args:
            message: Notification message
        """
        method = message.method
        logger.debug(f"Received notification: {method}")

        if method == MCPMessageType.NOTIFICATION_CANCELLED.value:
            # Client cancelled a request
            pass
        elif method == MCPMessageType.INITIALIZED.value:
            # Client acknowledged initialization
            logger.info("Client initialized")

    async def _handle_request(self, message: MCPMessage) -> MCPMessage:
        """Handle a request message.

        Args:
            message: Request message

        Returns:
            Response message
        """
        method = message.method
        params = message.params or {}
        request_id = message.id

        logger.debug(f"Handling request: {method}")

        # Route to appropriate handler
        if method == MCPMessageType.INITIALIZE.value:
            return await self._handle_initialize(request_id, params)

        elif method == MCPMessageType.PING.value:
            return create_success_response(request_id, {})

        elif method == MCPMessageType.TOOLS_LIST.value:
            return await self._tool_handler.handle_list_tools(request_id)

        elif method == MCPMessageType.TOOLS_CALL.value:
            return await self._tool_handler.handle_call_tool(request_id, params)

        elif method == MCPMessageType.RESOURCES_LIST.value:
            return await self._resource_handler.handle_list_resources(request_id)

        elif method == MCPMessageType.RESOURCES_READ.value:
            return await self._resource_handler.handle_read_resource(request_id, params)

        elif method == MCPMessageType.PROMPTS_LIST.value:
            return await self._prompt_handler.handle_list_prompts(request_id)

        elif method == MCPMessageType.PROMPTS_GET.value:
            return await self._prompt_handler.handle_get_prompt(request_id, params)

        else:
            return create_error_response(
                request_id,
                MCPErrorCode.METHOD_NOT_FOUND,
                f"Unknown method: {method}",
            )

    async def _handle_initialize(self, request_id: Any, params: Dict[str, Any]) -> MCPMessage:
        """Handle initialize request.

        Args:
            request_id: Request ID
            params: Initialize parameters

        Returns:
            Initialize response
        """
        client_info = params.get("clientInfo", {})
        client_caps = params.get("capabilities", {})
        protocol_version = params.get("protocolVersion", "2024-11-05")

        logger.info(
            f"Client initializing: {client_info.get('name', 'unknown')} " f"v{client_info.get('version', 'unknown')}"
        )

        # Authenticate client
        result, session = await self._security_manager.authenticate_client(
            client_info=client_info,
        )

        # SECURITY: Enforce authentication result
        if result != AuthResult.SUCCESS:
            logger.warning(f"Client authentication failed: {result.value} for " f"{client_info.get('name', 'unknown')}")
            # Map auth result to appropriate error message
            error_messages = {
                AuthResult.FAILED: "Authentication failed",
                AuthResult.EXPIRED: "Authentication expired",
                AuthResult.BLOCKED: "Client blocked",
                AuthResult.RATE_LIMITED: "Rate limit exceeded",
            }
            return create_error_response(
                request_id,
                MCPErrorCode.UNAUTHORIZED,
                error_messages.get(result, f"Authentication error: {result.value}"),
            )

        if session:
            self._sessions[session.client_id] = session

        # Build server capabilities
        server_caps = ServerCapabilities(
            tools={"listChanged": True} if self.config.exposure.expose_tools else None,
            resources=(
                {
                    "subscribe": False,
                    "listChanged": True,
                }
                if self.config.exposure.expose_resources
                else None
            ),
            prompts={"listChanged": True} if self.config.exposure.expose_prompts else None,
        )

        response = InitializeResult(
            protocolVersion=protocol_version,
            capabilities=server_caps,
            serverInfo={
                "name": self.config.server_name,
                "version": self.config.server_version,
            },
            instructions=self.config.server_description,
        )

        return create_success_response(request_id, response.model_dump())

    async def run_lifecycle(self, agent_run_task: asyncio.Task[Any]) -> None:
        """Run the adapter lifecycle.

        Args:
            agent_run_task: Agent run task
        """
        logger.info("MCP Server Adapter lifecycle running")

        try:
            # Wait for either agent task completion or shutdown
            done, pending = await asyncio.wait(
                [agent_run_task],
                return_when=asyncio.FIRST_COMPLETED,
            )

        except asyncio.CancelledError:
            logger.info("MCP Server Adapter lifecycle cancelled")
            raise

    async def stop(self) -> None:
        """Stop the MCP server adapter."""
        logger.info("Stopping MCP Server Adapter...")

        self._running = False
        self._shutdown_event.set()

        # Cancel server task
        if self._server_task and not self._server_task.done():
            self._server_task.cancel()
            try:
                await self._server_task
            except asyncio.CancelledError:
                pass

        # End all sessions
        for client_id in list(self._sessions.keys()):
            await self._security_manager.authenticator.end_session(client_id)

        self._sessions.clear()

        logger.info("MCP Server Adapter stopped")

    async def is_healthy(self) -> bool:
        """Check if adapter is healthy."""
        return self._running

    async def get_telemetry(self) -> JSONDict:
        """Get adapter telemetry."""
        uptime_seconds = 0.0
        if self._start_time:
            uptime_seconds = (datetime.now(timezone.utc) - self._start_time).total_seconds()

        return {
            "adapter_id": self.adapter_id,
            "running": self._running,
            "transport": self.config.transport.type.value,
            "requests_handled": self._requests_handled,
            "errors": self._errors,
            "active_sessions": len(self._sessions),
            "uptime_seconds": uptime_seconds,
            "security_metrics": self._security_manager.get_metrics(),
        }


__all__ = ["Adapter", "MCPServerAdapterKwargs"]
