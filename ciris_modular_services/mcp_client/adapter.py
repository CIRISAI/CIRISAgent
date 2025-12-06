"""
MCP (Model Context Protocol) Adapter for CIRIS.

This adapter enables integration with MCP servers, providing:
- Tool service integration (execute MCP tools) via ToolBus
- Communication service integration (MCP resources) via CommunicationBus
- Wise Authority service integration (MCP prompts) via WiseBus

The adapter supports dynamic configuration through the graph config service,
allowing the agent to self-configure which MCP servers connect to which buses.

Security features are implemented based on best practices from:
- https://modelcontextprotocol.io/specification/draft/basic/security_best_practices
- https://www.redhat.com/en/blog/model-context-protocol-mcp-understanding-security-risks-and-controls
"""

import asyncio
import logging
import subprocess
from contextlib import AsyncExitStack
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, TypedDict, Union, cast

from ciris_engine.logic.adapters.base import Service
from ciris_engine.logic.registries.base import Priority
from ciris_engine.schemas.adapters import AdapterServiceRegistration
from ciris_engine.schemas.runtime.enums import ServiceType
from ciris_engine.schemas.types import JSONDict

from .config import MCPAdapterConfig, MCPBusType, MCPServerConfig, MCPTransportType
from .mcp_communication_service import MCPCommunicationService
from .mcp_tool_service import MCPToolService
from .mcp_wise_service import MCPWiseService
from .security import MCPSecurityManager

logger = logging.getLogger(__name__)


class MCPAdapterKwargs(TypedDict, total=False):
    """Type-safe kwargs for MCPAdapter initialization."""

    adapter_config: Union[MCPAdapterConfig, Dict[str, Any]]
    config_service: Any  # GraphConfigService


class MCPClientContext:
    """Context for an MCP client connection."""

    def __init__(
        self,
        server_config: MCPServerConfig,
        client: Any,
        process: Optional[subprocess.Popen[bytes]] = None,
        exit_stack: Optional[AsyncExitStack] = None,
    ) -> None:
        self.server_config = server_config
        self.client = client
        self.process = process
        self.exit_stack = exit_stack  # Keeps context managers alive
        self.connected_at = datetime.now(timezone.utc)
        self.last_activity = self.connected_at

    async def close(self) -> None:
        """Close the client connection and clean up resources."""
        if self.exit_stack:
            try:
                await self.exit_stack.aclose()
            except Exception:
                pass  # Best effort cleanup
            self.exit_stack = None


class Adapter(Service):
    """
    MCP Modular Adapter for CIRIS.

    This adapter:
    1. Loads MCP server configurations from config or graph
    2. Establishes connections to MCP servers
    3. Registers services with appropriate buses based on configuration
    4. Handles security validation for all operations
    5. Supports dynamic reconfiguration through the config service
    """

    def __init__(self, runtime: Any, context: Optional[Any] = None, **kwargs: Any) -> None:
        """Initialize MCP adapter.

        Args:
            runtime: CIRIS runtime instance
            context: Optional adapter startup context
            **kwargs: Additional configuration options
        """
        super().__init__(config=None)

        self.runtime = runtime
        self.context = context
        self.adapter_id = "mcp_adapter"

        # Cast kwargs for type safety
        typed_kwargs = cast(MCPAdapterKwargs, kwargs)

        # Initialize configuration
        self._initialize_config(typed_kwargs)

        # Initialize security manager with global security config
        self._security_manager = MCPSecurityManager(self.config.global_security)

        # Initialize services
        time_service = getattr(runtime, "time_service", None)

        self._tool_service = MCPToolService(
            security_manager=self._security_manager,
            time_service=time_service,
        )

        self._wise_service = MCPWiseService(
            security_manager=self._security_manager,
            time_service=time_service,
        )

        self._communication_service = MCPCommunicationService(
            security_manager=self._security_manager,
            time_service=time_service,
        )

        # MCP client contexts
        self._client_contexts: Dict[str, MCPClientContext] = {}

        # Config service for graph-based configuration
        self._config_service = typed_kwargs.get("config_service")

        # Track running state
        self._running = False

    def _initialize_config(self, kwargs: MCPAdapterKwargs) -> None:
        """Initialize adapter configuration.

        Args:
            kwargs: Typed configuration kwargs
        """
        if "adapter_config" in kwargs and kwargs["adapter_config"] is not None:
            adapter_config = kwargs["adapter_config"]
            if isinstance(adapter_config, MCPAdapterConfig):
                self.config = adapter_config
            elif isinstance(adapter_config, dict):
                self.config = MCPAdapterConfig(**adapter_config)
            else:
                logger.warning(f"Invalid adapter_config type: {type(adapter_config)}")
                self.config = MCPAdapterConfig()
        else:
            self.config = MCPAdapterConfig()

        # Load environment variables
        self.config.load_env_vars()

        # Update adapter_id
        self.adapter_id = f"mcp_{self.config.adapter_id}"

        logger.info(
            f"MCP Adapter configured with {len(self.config.servers)} server(s), " f"adapter_id={self.adapter_id}"
        )

    async def _load_config_from_graph(self) -> None:
        """Load MCP server configurations from the graph config service.

        This enables agent self-configuration of MCP servers.
        """
        if not self._config_service:
            return

        try:
            # List all MCP configurations
            configs = await self._config_service.list_configs(prefix=self.config.config_key_prefix)

            for key, value in configs.items():
                if not isinstance(value, dict):
                    continue

                # Parse server configuration
                try:
                    server_config = MCPServerConfig(**value)

                    # Check if this server is already configured
                    existing = next(
                        (s for s in self.config.servers if s.server_id == server_config.server_id),
                        None,
                    )

                    if existing:
                        # Update existing configuration
                        existing_index = self.config.servers.index(existing)
                        self.config.servers[existing_index] = server_config
                        logger.info(f"Updated MCP server config from graph: {server_config.server_id}")
                    else:
                        # Add new server
                        self.config.servers.append(server_config)
                        logger.info(f"Added MCP server config from graph: {server_config.server_id}")

                except Exception as e:
                    logger.warning(f"Failed to parse MCP config '{key}': {e}")

        except Exception as e:
            logger.error(f"Failed to load MCP configs from graph: {e}")

    async def _save_server_config_to_graph(self, server_config: MCPServerConfig) -> None:
        """Save a server configuration to the graph.

        Args:
            server_config: Server configuration to save
        """
        if not self._config_service:
            return

        try:
            key = f"{self.config.config_key_prefix}.{server_config.server_id}"
            await self._config_service.set_config(
                key=key,
                value=server_config.model_dump(),
                updated_by="mcp_adapter",
            )
            logger.info(f"Saved MCP server config to graph: {server_config.server_id}")
        except Exception as e:
            logger.error(f"Failed to save MCP config to graph: {e}")

    async def _connect_mcp_server(
        self, server_config: MCPServerConfig
    ) -> Optional[tuple[Any, Optional[AsyncExitStack]]]:
        """Connect to an MCP server.

        Args:
            server_config: Server configuration

        Returns:
            Tuple of (MCP client instance, exit_stack) or None on failure.
            The exit_stack keeps context managers alive and must be closed on disconnect.
        """
        # Register server with security manager
        self._security_manager.register_server(server_config)

        try:
            if server_config.transport == MCPTransportType.STDIO:
                return await self._connect_stdio_server(server_config)
            elif server_config.transport == MCPTransportType.SSE:
                return await self._connect_sse_server(server_config)
            elif server_config.transport == MCPTransportType.STREAMABLE_HTTP:
                return await self._connect_streamable_http_server(server_config)
            elif server_config.transport == MCPTransportType.WEBSOCKET:
                return await self._connect_websocket_server(server_config)
            else:
                logger.error(f"Unsupported transport type: {server_config.transport}")
                return None
        except Exception as e:
            logger.error(f"Failed to connect to MCP server '{server_config.server_id}': {e}")
            return None

    async def _connect_stdio_server(
        self, server_config: MCPServerConfig
    ) -> Optional[tuple[Any, Optional[AsyncExitStack]]]:
        """Connect to a stdio MCP server.

        Args:
            server_config: Server configuration

        Returns:
            Tuple of (MCP client session, exit_stack) or None.
            The exit_stack keeps the transport and session alive.
        """
        if not server_config.command:
            logger.error(f"No command specified for stdio server '{server_config.server_id}'")
            return None

        try:
            # Try to import the MCP SDK
            try:
                from mcp import ClientSession, StdioServerParameters
                from mcp.client.stdio import stdio_client
            except ImportError:
                logger.warning(
                    "MCP SDK not installed. Install with: pip install mcp" "\nUsing mock client for development."
                )
                return (self._create_mock_client(server_config), None)

            # Build environment
            env = dict(server_config.env)

            # Create server parameters
            server_params = StdioServerParameters(
                command=server_config.command,
                args=server_config.args,
                env=env if env else None,
            )

            # Use AsyncExitStack to keep context managers alive
            stack = AsyncExitStack()
            try:
                # Enter the stdio client context manager
                read, write = await stack.enter_async_context(stdio_client(server_params))

                # Enter the ClientSession context manager
                session = await stack.enter_async_context(ClientSession(read, write))

                # Initialize the session
                await session.initialize()

                logger.info(f"Connected to MCP server '{server_config.server_id}' via stdio")

                return (session, stack)

            except Exception:
                # Clean up on failure
                await stack.aclose()
                raise

        except Exception as e:
            logger.error(f"Failed to connect to stdio MCP server '{server_config.server_id}': {e}")
            return None

    async def _connect_sse_server(
        self, server_config: MCPServerConfig
    ) -> Optional[tuple[Any, Optional[AsyncExitStack]]]:
        """Connect to an SSE MCP server.

        Args:
            server_config: Server configuration

        Returns:
            Tuple of (MCP client session, exit_stack) or None.
            The exit_stack keeps the transport and session alive.
        """
        if not server_config.url:
            logger.error(f"No URL specified for SSE server '{server_config.server_id}'")
            return None

        try:
            from mcp import ClientSession
            from mcp.client.sse import sse_client
        except ImportError:
            logger.warning("MCP SDK not installed, using mock client")
            return (self._create_mock_client(server_config), None)

        try:
            # Use AsyncExitStack to keep context managers alive
            stack = AsyncExitStack()
            try:
                # Enter the SSE client context manager
                read, write = await stack.enter_async_context(sse_client(server_config.url))

                # Enter the ClientSession context manager
                session = await stack.enter_async_context(ClientSession(read, write))

                # Initialize the session
                await session.initialize()

                logger.info(f"Connected to MCP server '{server_config.server_id}' via SSE")
                return (session, stack)

            except Exception:
                # Clean up on failure
                await stack.aclose()
                raise

        except Exception as e:
            logger.error(f"Failed to connect to SSE server: {e}")
            return None

    async def _connect_streamable_http_server(
        self, server_config: MCPServerConfig
    ) -> Optional[tuple[Any, Optional[AsyncExitStack]]]:
        """Connect to a Streamable HTTP MCP server."""
        # Similar to SSE, but uses streamable HTTP transport
        return await self._connect_sse_server(server_config)

    async def _connect_websocket_server(
        self, server_config: MCPServerConfig
    ) -> Optional[tuple[Any, Optional[AsyncExitStack]]]:
        """Connect to a WebSocket MCP server."""
        if not server_config.url:
            logger.error(f"No URL specified for WebSocket server '{server_config.server_id}'")
            return None

        logger.warning("WebSocket transport not yet implemented, using mock client")
        return (self._create_mock_client(server_config), None)

    def _create_mock_client(self, server_config: MCPServerConfig) -> Any:
        """Create a mock MCP client for development/testing.

        Args:
            server_config: Server configuration

        Returns:
            Mock client instance
        """

        class MockMCPClient:
            """Mock MCP client for when SDK is not available."""

            def __init__(self, mock_config: MCPServerConfig) -> None:
                self.config = mock_config

            async def list_tools(self) -> Any:
                """Return mock tools."""
                server_name = self.config.name

                class MockTools:
                    tools = [
                        {
                            "name": "mock_tool",
                            "description": f"Mock tool from {server_name}",
                            "inputSchema": {
                                "type": "object",
                                "properties": {"input": {"type": "string"}},
                                "required": ["input"],
                            },
                        }
                    ]

                return MockTools()

            async def call_tool(self, name: str, arguments: Dict[str, Any]) -> Any:
                """Execute mock tool."""

                class MockResult:
                    content = [type("Content", (), {"text": f"Mock result for {name}"})()]

                return MockResult()

            async def list_prompts(self) -> Any:
                """Return mock prompts."""

                class MockPrompts:
                    prompts = [
                        {
                            "name": "mock_guidance",
                            "description": "Mock guidance prompt",
                            "arguments": [{"name": "question"}],
                        }
                    ]

                return MockPrompts()

            async def get_prompt(self, name: str, arguments: Dict[str, Any]) -> Any:
                """Get mock prompt response."""

                class MockContent:
                    text = f"Mock guidance response for: {arguments.get('question', 'unknown')}"

                class MockMessage:
                    content = MockContent()

                class MockResponse:
                    messages = [MockMessage()]

                return MockResponse()

            async def list_resources(self) -> Any:
                """Return mock resources."""

                class MockResources:
                    resources = [
                        {
                            "uri": "mock://resource",
                            "name": "Mock Resource",
                            "description": "A mock resource for testing",
                            "mimeType": "text/plain",
                        }
                    ]

                return MockResources()

            async def read_resource(self, uri: str) -> Any:
                """Read mock resource."""

                class MockContent:
                    text = f"Mock content from {uri}"

                class MockResponse:
                    contents = [MockContent()]

                return MockResponse()

        return MockMCPClient(server_config)

    def get_services_to_register(self) -> List[AdapterServiceRegistration]:
        """Get list of services to register with the runtime.

        Returns services based on bus bindings configured for each server.
        """
        registrations: List[AdapterServiceRegistration] = []

        # Collect which buses need services
        has_tool_binding = any(
            any(b.bus_type == MCPBusType.TOOL for b in s.bus_bindings) for s in self.config.servers if s.enabled
        )

        has_wise_binding = any(
            any(b.bus_type == MCPBusType.WISE for b in s.bus_bindings) for s in self.config.servers if s.enabled
        )

        has_comm_binding = any(
            any(b.bus_type == MCPBusType.COMMUNICATION for b in s.bus_bindings)
            for s in self.config.servers
            if s.enabled
        )

        # Register tool service if any server has tool binding
        if has_tool_binding:
            registrations.append(
                AdapterServiceRegistration(
                    service_type=ServiceType.TOOL,
                    provider=self._tool_service,
                    priority=Priority.LOW,  # Lower priority than native tools
                    handlers=["ToolHandler"],
                    capabilities=[
                        "execute_tool",
                        "get_available_tools",
                        "get_tool_result",
                        "validate_parameters",
                        "get_tool_info",
                        "get_all_tool_info",
                    ],
                )
            )
            logger.info("MCP Adapter registering ToolBus service")

        # Register wise authority service if any server has wise binding
        if has_wise_binding:
            registrations.append(
                AdapterServiceRegistration(
                    service_type=ServiceType.WISE_AUTHORITY,
                    provider=self._wise_service,
                    priority=Priority.LOW,
                    handlers=["DeferHandler", "SpeakHandler"],
                    capabilities=["fetch_guidance", "send_deferral", "get_guidance"],
                )
            )
            logger.info("MCP Adapter registering WiseBus service")

        # Register communication service if any server has communication binding
        if has_comm_binding:
            registrations.append(
                AdapterServiceRegistration(
                    service_type=ServiceType.COMMUNICATION,
                    provider=self._communication_service,
                    priority=Priority.LOW,
                    handlers=["SpeakHandler", "ObserveHandler"],
                    capabilities=["send_message", "fetch_messages"],
                )
            )
            logger.info("MCP Adapter registering CommunicationBus service")

        logger.info(f"MCP Adapter registering {len(registrations)} service(s)")
        return registrations

    async def start(self) -> None:
        """Start the MCP adapter."""
        logger.info("Starting MCP Adapter...")

        # Load configurations from graph if available
        await self._load_config_from_graph()

        # Start services
        await self._tool_service.start()
        await self._wise_service.start()
        await self._communication_service.start()

        # Connect to all enabled servers
        for server_config in self.config.servers:
            if not server_config.enabled:
                continue
            if not server_config.auto_start:
                continue

            # Connect to server - returns (client, exit_stack) tuple
            result = await self._connect_mcp_server(server_config)
            if not result:
                logger.warning(f"Failed to connect to MCP server '{server_config.server_id}'")
                continue

            client, exit_stack = result

            # Store client context with exit_stack to keep session alive
            self._client_contexts[server_config.server_id] = MCPClientContext(
                server_config=server_config,
                client=client,
                exit_stack=exit_stack,
            )

            # Register client with appropriate services based on bus bindings
            for binding in server_config.bus_bindings:
                if not binding.enabled:
                    continue

                if binding.bus_type == MCPBusType.TOOL:
                    self._tool_service.register_mcp_client(server_config.server_id, client)
                elif binding.bus_type == MCPBusType.WISE:
                    self._wise_service.register_mcp_client(server_config.server_id, client)
                elif binding.bus_type == MCPBusType.COMMUNICATION:
                    self._communication_service.register_mcp_client(server_config.server_id, client)

            logger.info(f"Connected to MCP server '{server_config.server_id}'")

        self._running = True
        logger.info("MCP Adapter started")

    async def run_lifecycle(self, agent_run_task: asyncio.Task[Any]) -> None:
        """Run the adapter lifecycle.

        MCP adapter doesn't have its own event loop like Discord,
        so we just wait for the agent task to complete.
        """
        logger.info("MCP Adapter lifecycle running")

        try:
            # Just wait for the agent task
            await agent_run_task
        except asyncio.CancelledError:
            logger.info("MCP Adapter lifecycle cancelled")
            raise

    async def stop(self) -> None:
        """Stop the MCP adapter."""
        logger.info("Stopping MCP Adapter...")

        self._running = False

        # Disconnect all servers
        for server_id, ctx in list(self._client_contexts.items()):
            try:
                # Unregister from services
                self._tool_service.unregister_mcp_client(server_id)
                self._wise_service.unregister_mcp_client(server_id)
                self._communication_service.unregister_mcp_client(server_id)

                # Close the session and transport via exit stack
                await ctx.close()

                # Kill process if stdio (backup cleanup)
                if ctx.process:
                    ctx.process.terminate()
                    try:
                        ctx.process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        ctx.process.kill()

                logger.info(f"Disconnected from MCP server '{server_id}'")
            except Exception as e:
                logger.error(f"Error disconnecting from MCP server '{server_id}': {e}")

        self._client_contexts.clear()

        # Stop services
        await self._tool_service.stop()
        await self._wise_service.stop()
        await self._communication_service.stop()

        logger.info("MCP Adapter stopped")

    async def is_healthy(self) -> bool:
        """Check if the adapter is healthy."""
        if not self._running:
            return False

        # Check if at least one service is healthy
        tool_healthy = await self._tool_service.is_healthy()
        wise_healthy = await self._wise_service.is_healthy()
        comm_healthy = await self._communication_service.is_healthy()

        return tool_healthy or wise_healthy or comm_healthy

    # Dynamic configuration methods for agent self-configuration

    async def add_mcp_server(self, server_config: MCPServerConfig) -> bool:
        """Add a new MCP server dynamically.

        Args:
            server_config: New server configuration

        Returns:
            True if server was added successfully
        """
        # Check if server already exists
        existing = next(
            (s for s in self.config.servers if s.server_id == server_config.server_id),
            None,
        )
        if existing:
            logger.warning(f"MCP server '{server_config.server_id}' already exists")
            return False

        # Register with security manager
        self._security_manager.register_server(server_config)

        # Connect to server - returns (client, exit_stack) tuple
        result = await self._connect_mcp_server(server_config)
        if not result:
            logger.error(f"Failed to connect to new MCP server '{server_config.server_id}'")
            return False

        client, exit_stack = result

        # Add to configuration
        self.config.servers.append(server_config)

        # Store client context with exit_stack to keep session alive
        self._client_contexts[server_config.server_id] = MCPClientContext(
            server_config=server_config,
            client=client,
            exit_stack=exit_stack,
        )

        # Register with services
        for binding in server_config.bus_bindings:
            if not binding.enabled:
                continue

            if binding.bus_type == MCPBusType.TOOL:
                self._tool_service.register_mcp_client(server_config.server_id, client)
            elif binding.bus_type == MCPBusType.WISE:
                self._wise_service.register_mcp_client(server_config.server_id, client)
            elif binding.bus_type == MCPBusType.COMMUNICATION:
                self._communication_service.register_mcp_client(server_config.server_id, client)

        # Save to graph for persistence
        await self._save_server_config_to_graph(server_config)

        logger.info(f"Added MCP server '{server_config.server_id}'")
        return True

    async def remove_mcp_server(self, server_id: str) -> bool:
        """Remove an MCP server dynamically.

        Args:
            server_id: Server to remove

        Returns:
            True if server was removed
        """
        # Find and remove from config
        server_config = next(
            (s for s in self.config.servers if s.server_id == server_id),
            None,
        )
        if not server_config:
            logger.warning(f"MCP server '{server_id}' not found")
            return False

        # Unregister from services
        self._tool_service.unregister_mcp_client(server_id)
        self._wise_service.unregister_mcp_client(server_id)
        self._communication_service.unregister_mcp_client(server_id)

        # Clean up client context
        if server_id in self._client_contexts:
            ctx = self._client_contexts[server_id]
            # Close the session and transport via exit stack
            await ctx.close()
            # Kill process if stdio (backup cleanup)
            if ctx.process:
                ctx.process.terminate()
            del self._client_contexts[server_id]

        # Remove from config
        self.config.servers.remove(server_config)

        logger.info(f"Removed MCP server '{server_id}'")
        return True

    async def update_server_bus_bindings(self, server_id: str, bus_bindings: List[Dict[str, Any]]) -> bool:
        """Update bus bindings for a server.

        Args:
            server_id: Server to update
            bus_bindings: New bus bindings

        Returns:
            True if updated successfully
        """
        from .config import MCPBusBinding

        server_config = next(
            (s for s in self.config.servers if s.server_id == server_id),
            None,
        )
        if not server_config:
            logger.warning(f"MCP server '{server_id}' not found")
            return False

        # Parse new bindings
        new_bindings = [MCPBusBinding(**b) for b in bus_bindings]

        # Get current client
        ctx = self._client_contexts.get(server_id)
        if not ctx:
            logger.warning(f"MCP server '{server_id}' not connected")
            return False

        client = ctx.client

        # Unregister from all services first
        self._tool_service.unregister_mcp_client(server_id)
        self._wise_service.unregister_mcp_client(server_id)
        self._communication_service.unregister_mcp_client(server_id)

        # Update bindings
        server_config.bus_bindings = new_bindings

        # Re-register with new bindings
        for binding in new_bindings:
            if not binding.enabled:
                continue

            if binding.bus_type == MCPBusType.TOOL:
                self._tool_service.register_mcp_client(server_id, client)
            elif binding.bus_type == MCPBusType.WISE:
                self._wise_service.register_mcp_client(server_id, client)
            elif binding.bus_type == MCPBusType.COMMUNICATION:
                self._communication_service.register_mcp_client(server_id, client)

        # Save to graph
        await self._save_server_config_to_graph(server_config)

        logger.info(f"Updated bus bindings for MCP server '{server_id}'")
        return True

    def get_security_metrics(self) -> Dict[str, Any]:
        """Get security metrics from the security manager."""
        return self._security_manager.get_security_metrics()

    async def get_telemetry(self) -> JSONDict:
        """Get combined telemetry from all services."""
        tool_telemetry = await self._tool_service.get_telemetry()
        wise_telemetry = await self._wise_service.get_telemetry()
        comm_telemetry = await self._communication_service.get_telemetry()

        return {
            "adapter_id": self.adapter_id,
            "running": self._running,
            "servers_configured": len(self.config.servers),
            "servers_connected": len(self._client_contexts),
            "tool_service": tool_telemetry,
            "wise_service": wise_telemetry,
            "communication_service": comm_telemetry,
            "security_metrics": self.get_security_metrics(),
        }


__all__ = ["Adapter", "MCPAdapterKwargs", "MCPClientContext"]
