"""
MCP Server Adapter for CIRIS.

Exposes CIRIS as an MCP server with 3 simple tools:
- status: Get agent status
- message: Send a message to user's channel
- history: Get message history
"""

import asyncio
import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, TypedDict, Union, cast

from ciris_adapters.mcp_common.protocol import (
    InitializeResult,
    MCPErrorCode,
    MCPMessage,
    MCPMessageType,
    ServerCapabilities,
    create_error_response,
    create_success_response,
    validate_mcp_message,
)
from ciris_engine.logic.adapters.base import Service
from ciris_engine.schemas.adapters import AdapterServiceRegistration
from ciris_engine.schemas.types import JSONDict

from .config import MCPServerConfig, MCPTransportType
from .handlers import MCPServerHandler

logger = logging.getLogger(__name__)


class MCPServerAdapterKwargs(TypedDict, total=False):
    """Type-safe kwargs for MCPServerAdapter initialization."""

    adapter_config: Union[MCPServerConfig, Dict[str, Any]]


class Adapter(Service):
    """
    MCP Server Adapter for CIRIS.

    Exposes 3 simple tools via the Model Context Protocol:
    - status: Get agent status
    - message: Send message to user's channel
    - history: Get message history from user's channel

    Authentication uses API key to identify user, which maps to api_{user_id} channel.
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

        # Get communication service for messaging
        communication = None
        if hasattr(runtime, "communication_bus"):
            communication = runtime.communication_bus
        elif hasattr(runtime, "communication_service"):
            communication = runtime.communication_service

        # Initialize handler
        self._handler = MCPServerHandler(
            runtime=runtime,
            communication_service=communication,
        )

        # Server state
        self._running = False
        self._start_time: Optional[datetime] = None
        self._server_task: Optional[asyncio.Task[Any]] = None
        self._shutdown_event = asyncio.Event()

        # Metrics
        self._requests_handled = 0
        self._errors = 0

        # Active sessions (api_key -> user_id)
        self._authenticated_users: Dict[str, str] = {}

    def _initialize_config(self, kwargs: MCPServerAdapterKwargs) -> None:
        """Initialize adapter configuration."""
        if "adapter_config" in kwargs and kwargs["adapter_config"] is not None:
            adapter_config = kwargs["adapter_config"]
            if isinstance(adapter_config, MCPServerConfig):
                self._config = adapter_config
            elif isinstance(adapter_config, dict):
                self._config = MCPServerConfig(**adapter_config)
            else:
                self._config = MCPServerConfig()
        else:
            self._config = MCPServerConfig()

        self._config.load_env_vars()
        self.adapter_id = f"mcp_server_{self._config.server_id}"

        logger.info(f"MCP Server configured: id={self._config.server_id}, " f"transport={self._config.transport.value}")

    def _get_request_id(self, message: MCPMessage) -> Union[str, int]:
        """Get request ID from message, defaulting to 0 if None."""
        return message.id if message.id is not None else 0

    def get_services_to_register(self) -> List[AdapterServiceRegistration]:
        """Get services to register.

        MCP Server doesn't provide services to CIRIS buses,
        it exposes CIRIS services to external clients.
        """
        return []

    async def start(self) -> None:
        """Start the MCP server adapter."""
        logger.info("Starting MCP Server Adapter...")

        self._running = True
        self._start_time = datetime.now(timezone.utc)

        if self._config.enabled:
            await self._start_server()

        logger.info("MCP Server Adapter started")

    async def _start_server(self) -> None:
        """Start the MCP server based on transport type."""
        transport = self._config.transport

        if transport == MCPTransportType.STDIO:
            self._server_task = asyncio.create_task(
                self._run_stdio_server(),
                name="MCPServerStdio",
            )
        elif transport in (MCPTransportType.SSE, MCPTransportType.HTTP):
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

        loop = asyncio.get_event_loop()
        await loop.connect_read_pipe(lambda: protocol, sys.stdin)

        writer_transport, writer_protocol = await loop.connect_write_pipe(asyncio.streams.FlowControlMixin, sys.stdout)
        writer = asyncio.StreamWriter(writer_transport, writer_protocol, reader, loop)

        # For stdio transport, provide a default user_id when auth is not required
        # This allows message/history tools to work for local stdio clients
        stdio_user_id: Optional[str] = None
        if not self._config.require_auth:
            stdio_user_id = "stdio_user"
            logger.info("Stdio transport: using default user 'stdio_user' (auth not required)")

        try:
            while not self._shutdown_event.is_set():
                try:
                    line = await asyncio.wait_for(reader.readline(), timeout=1.0)

                    if not line:
                        break

                    response = await self._handle_message(line.decode().strip(), stdio_user_id)

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
        """Run MCP server over HTTP transport."""
        logger.info(f"Starting MCP HTTP server on {self._config.host}:{self._config.port}")

        try:
            server = await asyncio.start_server(
                self._handle_http_connection,
                self._config.host,
                self._config.port,
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
        """Handle an HTTP connection."""
        try:
            # Read HTTP request
            await reader.readline()  # Request line
            headers: Dict[str, str] = {}

            while True:
                header_line = await reader.readline()
                if header_line == b"\r\n":
                    break
                if b":" in header_line:
                    key, value = header_line.decode().split(":", 1)
                    headers[key.strip().lower()] = value.strip()

            # Extract API key from Authorization header
            user_id = None
            auth_header = headers.get("authorization", "")
            if auth_header.startswith("Bearer "):
                api_key = auth_header[7:]
                user_id = self._authenticate(api_key)

            # Read body
            content_length = int(headers.get("content-length", 0))
            body = b""
            if content_length > 0:
                body = await reader.read(content_length)

            # Handle MCP message
            if body:
                response = await self._handle_message(body.decode(), user_id)

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

    def _authenticate(self, api_key: str) -> Optional[str]:
        """Authenticate using API key.

        Args:
            api_key: The API key

        Returns:
            User ID if authenticated, None otherwise
        """
        # Check configured API key
        if self._config.api_key and api_key == self._config.api_key:
            return "api_user"

        # Could integrate with auth service here
        # For now, treat api_key as user_id if no configured key
        if not self._config.require_auth:
            return api_key or "anonymous"

        return None

    async def _handle_message(
        self,
        message_str: str,
        user_id: Optional[str] = None,
    ) -> Optional[MCPMessage]:
        """Handle an incoming MCP message.

        Args:
            message_str: Raw message string
            user_id: Authenticated user ID

        Returns:
            Response MCPMessage or None
        """
        self._requests_handled += 1

        try:
            data = json.loads(message_str)

            is_valid, error = validate_mcp_message(data)
            if not is_valid:
                self._errors += 1
                return create_error_response(
                    data.get("id"),
                    MCPErrorCode.INVALID_REQUEST,
                    error or "Invalid message",
                )

            message = MCPMessage(**data)

            # Handle notification (no response)
            if message.is_notification():
                return None

            # Handle initialize
            if message.method == MCPMessageType.INITIALIZE.value:
                return await self._handle_initialize(message)

            # Handle ping
            if message.method == "ping":
                return create_success_response(self._get_request_id(message), {})

            # Delegate to handler
            return await self._handler.handle_request(message, user_id)

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

    async def _handle_initialize(self, message: MCPMessage) -> MCPMessage:
        """Handle initialize request."""
        params = message.params or {}
        client_info = params.get("clientInfo", {})
        protocol_version = params.get("protocolVersion", "2024-11-05")

        logger.info(
            f"Client initializing: {client_info.get('name', 'unknown')} " f"v{client_info.get('version', 'unknown')}"
        )

        server_caps = ServerCapabilities(
            tools={"listChanged": False},
            resources=None,
            prompts=None,
        )

        response = InitializeResult(
            protocolVersion=protocol_version,
            capabilities=server_caps,
            serverInfo={
                "name": self._config.server_name,
                "version": "1.0.0",
            },
            instructions="CIRIS Agent MCP Server. Tools: status, message, history",
        )

        return create_success_response(self._get_request_id(message), response.model_dump())

    async def run_lifecycle(self, agent_run_task: asyncio.Task[Any]) -> None:
        """Run the adapter lifecycle."""
        logger.info("MCP Server Adapter lifecycle running")

        try:
            await asyncio.wait([agent_run_task], return_when=asyncio.FIRST_COMPLETED)
        except asyncio.CancelledError:
            logger.info("MCP Server Adapter lifecycle cancelled")
            raise

    async def stop(self) -> None:
        """Stop the MCP server adapter."""
        logger.info("Stopping MCP Server Adapter...")

        self._running = False
        self._shutdown_event.set()

        if self._server_task and not self._server_task.done():
            self._server_task.cancel()
            try:
                await self._server_task
            except asyncio.CancelledError:
                pass

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
            "transport": self._config.transport.value,
            "requests_handled": self._requests_handled,
            "errors": self._errors,
            "uptime_seconds": uptime_seconds,
        }


__all__ = ["Adapter", "MCPServerAdapterKwargs"]
