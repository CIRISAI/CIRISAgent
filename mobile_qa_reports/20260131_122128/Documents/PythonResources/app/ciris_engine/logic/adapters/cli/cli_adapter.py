"""
Simplified CLI adapter implementing CommunicationService, WiseAuthorityService, and ToolService.
Following the pattern of the refactored Discord adapter.
"""

import asyncio
import logging
import sys
import uuid
from datetime import datetime
from typing import Any, Awaitable, Callable, Dict, List, Optional

import aiofiles

from ciris_engine.logic import persistence
from ciris_engine.logic.adapters.base import Service
from ciris_engine.protocols.services import CommunicationService, ToolService
from ciris_engine.protocols.services.lifecycle.time import TimeServiceProtocol
from ciris_engine.schemas.adapters.cli import (
    ListFilesToolParams,
    ListFilesToolResult,
    ReadFileToolParams,
    ReadFileToolResult,
    SystemInfoToolResult,
)
from ciris_engine.schemas.adapters.tools import ToolExecutionResult, ToolExecutionStatus, ToolInfo, ToolParameterSchema
from ciris_engine.schemas.runtime.enums import ServiceType
from ciris_engine.schemas.runtime.messages import FetchedMessage, IncomingMessage
from ciris_engine.schemas.runtime.system_context import ChannelContext
from ciris_engine.schemas.services.core import ServiceCapabilities, ServiceStatus
from ciris_engine.schemas.telemetry.core import (
    CorrelationType,
    ServiceCorrelation,
    ServiceCorrelationStatus,
    ServiceRequestData,
    ServiceResponseData,
)
from ciris_engine.schemas.types import JSONDict

logger = logging.getLogger(__name__)


class CLIAdapter(Service, CommunicationService, ToolService):
    """
    CLI adapter implementing CommunicationService and ToolService protocols.
    Provides command-line interface for interacting with the CIRIS agent.
    """

    def __init__(
        self,
        runtime: Optional[Any] = None,
        interactive: bool = True,
        on_message: Optional[Callable[[IncomingMessage], Awaitable[None]]] = None,
        bus_manager: Optional[Any] = None,
        config: Optional[Any] = None,
    ) -> None:
        """
        Initialize the CLI adapter.

        Args:
            runtime: Runtime instance with access to services
            interactive: Whether to run in interactive mode with user input
            on_message: Callback for handling incoming messages
            bus_manager: Multi-service sink for routing messages
            config: Optional CLIAdapterConfig
        """
        super().__init__()

        self.runtime = runtime
        self.interactive = interactive
        self.on_message = on_message
        self.bus_manager = bus_manager
        self._running = False
        self._input_task: Optional[asyncio.Task[None]] = None
        self.cli_config = config  # Store the CLI config
        self._time_service: Optional[TimeServiceProtocol] = None
        self._start_time: Optional[datetime] = None

        self._available_tools: Dict[str, Callable[[JSONDict], Awaitable[JSONDict]]] = {
            "list_files": self._tool_list_files,
            "read_file": self._tool_read_file,
            "system_info": self._tool_system_info,
        }

        self._guidance_queue: asyncio.Queue[str] = asyncio.Queue()

        # Metrics tracking
        self._commands_executed_count = 0
        self._errors_total_count = 0

    def _get_time_service(self) -> TimeServiceProtocol:
        """Get time service instance from runtime."""
        if self._time_service is None:
            if self.runtime and hasattr(self.runtime, "service_registry"):
                # Get time service from registry
                time_services = self.runtime.service_registry.get_services_by_type(ServiceType.TIME)
                if time_services:
                    self._time_service = time_services[0]
                else:
                    raise RuntimeError("TimeService not available in runtime")
            else:
                raise RuntimeError("Runtime not available or does not have service registry")
        return self._time_service

    async def _emit_telemetry(
        self, metric_name: str, value: float = 1.0, tags: Optional[Dict[str, str]] = None
    ) -> None:
        """Emit telemetry as TSDBGraphNode through memory bus."""
        if not self.bus_manager:
            return  # No bus manager, can't emit telemetry

        # Check if memory bus is available (it might not be during startup)
        if not hasattr(self.bus_manager, "memory") or not self.bus_manager.memory:
            return  # Memory bus not available yet

        try:
            # Use the provided value or extract from tags if available
            metric_value = value
            if tags and "value" in tags:
                metric_value = float(tags.pop("value"))
            elif tags and "execution_time_ms" in tags:
                metric_value = float(tags["execution_time_ms"])
            elif tags and "success" in tags:
                # For boolean success, use 1.0 for true, 0.0 for false
                metric_value = 1.0 if tags["success"] else 0.0

            # Convert all tag values to strings as required by memorize_metric
            string_tags = {k: str(v) for k, v in (tags or {}).items()}

            # Use memorize_metric instead of creating GraphNode directly
            await self.bus_manager.memory.memorize_metric(
                metric_name=metric_name, value=metric_value, tags=string_tags, scope="local", handler_name="adapter.cli"
            )
        except Exception as e:
            logger.debug(f"Failed to emit telemetry {metric_name}: {e}")

    async def send_message(self, channel_id: str, content: str) -> bool:
        """
        Send a message to the console.

        Args:
            channel_id: The channel identifier (used for categorization)
            content: The message content

        Returns:
            True if message was sent successfully
        """
        correlation_id = str(uuid.uuid4())
        try:
            # Get current timestamp for output
            timestamp = self._get_time_service().now().strftime("%H:%M:%S.%f")[:-3]

            if channel_id == "system":
                print(f"\n[{timestamp}] [SYSTEM] {content}")
            elif channel_id == "error":
                print(f"\n[{timestamp}] [ERROR] {content}", file=sys.stderr)
            else:
                print(f"\n[{timestamp}] [CIRIS] {content}")

            from ciris_engine.schemas.telemetry.core import ServiceRequestData, ServiceResponseData

            now = self._get_time_service().now()

            request_data = ServiceRequestData(
                service_type="communication",
                method_name="send_message",
                channel_id=channel_id,
                parameters={"content": content},
                request_timestamp=now,
                thought_id=None,
                task_id=None,
                timeout_seconds=None,
            )

            response_data = ServiceResponseData(
                success=True,
                result_summary=f"Message sent to {channel_id}",
                execution_time_ms=10.0,
                response_timestamp=now,
                result_type=None,
                result_size=None,
                error_type=None,
                error_message=None,
                error_traceback=None,
                tokens_used=None,
                memory_bytes=None,
            )

            persistence.add_correlation(
                ServiceCorrelation(
                    correlation_id=correlation_id,
                    service_type="cli",
                    handler_name="CLIAdapter",
                    action_type="speak",
                    request_data=request_data,
                    response_data=response_data,
                    status=ServiceCorrelationStatus.COMPLETED,
                    created_at=now,
                    updated_at=now,
                    timestamp=now,
                    correlation_type=CorrelationType.SERVICE_INTERACTION,
                    metric_data=None,
                    log_data=None,
                    trace_context=None,
                    retention_policy="raw",
                    ttl_seconds=None,
                    parent_correlation_id=None,
                ),
                self._get_time_service(),
            )
            return True
        except Exception as e:
            logger.error(f"Failed to send CLI message: {e}")
            # Track error
            self._errors_total_count += 1
            return False

    async def fetch_messages(
        self, channel_id: str, *, limit: int = 50, before: Optional[datetime] = None
    ) -> List[FetchedMessage]:
        """
        Fetch messages from correlations for CLI channel.

        Args:
            channel_id: The channel identifier
            limit: Maximum number of messages to fetch
            before: Optional datetime to fetch messages before

        Returns:
            List of FetchedMessage objects from correlations
        """
        from ciris_engine.logic.persistence import get_correlations_by_channel

        try:
            # Get correlations for this channel
            correlations = get_correlations_by_channel(channel_id=channel_id, limit=limit)

            messages = []
            for corr in correlations:
                # Extract message data from correlation
                if corr.action_type == "speak" and corr.request_data:
                    # This is an outgoing message from the agent
                    content = ""
                    if hasattr(corr.request_data, "parameters") and corr.request_data.parameters:
                        content = corr.request_data.parameters.get("content", "")

                    messages.append(
                        FetchedMessage(
                            message_id=corr.correlation_id,
                            author_id="ciris",
                            author_name="CIRIS",
                            content=content,
                            timestamp=(
                                (corr.timestamp or corr.created_at).isoformat()
                                if corr.timestamp or corr.created_at
                                else None
                            ),
                            is_bot=True,
                        )
                    )
                elif corr.action_type == "observe" and corr.request_data:
                    # This is an incoming message from a user
                    content = ""
                    author_id = "cli_user"
                    author_name = "User"

                    if hasattr(corr.request_data, "parameters") and corr.request_data.parameters:
                        params = corr.request_data.parameters
                        content = params.get("content", "")
                        author_id = params.get("author_id", "cli_user")
                        author_name = params.get("author_name", "User")

                    messages.append(
                        FetchedMessage(
                            message_id=corr.correlation_id,
                            author_id=author_id,
                            author_name=author_name,
                            content=content,
                            timestamp=(
                                (corr.timestamp or corr.created_at).isoformat()
                                if corr.timestamp or corr.created_at
                                else None
                            ),
                            is_bot=False,
                        )
                    )

            # Sort by timestamp
            messages.sort(key=lambda m: str(m.timestamp or ""))

            return messages

        except Exception as e:
            logger.error(f"Failed to fetch messages from correlations for CLI channel {channel_id}: {e}")
            return []

    async def execute_tool(self, tool_name: str, parameters: JSONDict) -> ToolExecutionResult:
        """
        Execute a CLI tool.

        Args:
            tool_name: Name of the tool to execute
            parameters: Tool parameters

        Returns:
            Tool execution result
        """
        correlation_id = str(uuid.uuid4())

        if tool_name not in self._available_tools:
            return ToolExecutionResult(
                tool_name=tool_name,
                status=ToolExecutionStatus.FAILED,
                success=False,
                data={"available_tools": list(self._available_tools.keys())},
                error=f"Unknown tool: {tool_name}",
                correlation_id=correlation_id,
            )

        try:
            import time

            start_time = time.time()
            result = await self._available_tools[tool_name](parameters)
            execution_time = (time.time() - start_time) * 1000

            # Track successful command execution
            self._commands_executed_count += 1

            # Emit telemetry for tool execution
            await self._emit_telemetry(
                "tool_executed",
                1.0,
                {
                    "adapter_type": "cli",
                    "tool_name": tool_name,
                    "execution_time_ms": str(execution_time),
                    "success": str(result.get("success", True)),
                },
            )

            now = self._get_time_service().now()
            persistence.add_correlation(
                ServiceCorrelation(
                    correlation_id=correlation_id,
                    service_type="cli",
                    handler_name="CLIAdapter",
                    action_type="execute_tool",
                    request_data=ServiceRequestData(
                        service_type="tool",
                        method_name="execute_tool",
                        parameters={"tool_name": tool_name, "parameters": str(parameters)},
                        request_timestamp=now,
                        thought_id=None,
                        task_id=None,
                        channel_id=None,
                        timeout_seconds=None,
                    ),
                    response_data=ServiceResponseData(
                        success=result.get("success", True),
                        result_summary=f"Tool {tool_name} executed",
                        execution_time_ms=execution_time,
                        response_timestamp=now,
                        result_type=None,
                        result_size=None,
                        error_type=None,
                        error_message=None,
                        error_traceback=None,
                        tokens_used=None,
                        memory_bytes=None,
                    ),
                    status=ServiceCorrelationStatus.COMPLETED,
                    created_at=now,
                    updated_at=now,
                    timestamp=now,
                    correlation_type=CorrelationType.SERVICE_INTERACTION,
                    metric_data=None,
                    log_data=None,
                    trace_context=None,
                    retention_policy="raw",
                    ttl_seconds=None,
                    parent_correlation_id=None,
                ),
                self._get_time_service(),
            )

            return ToolExecutionResult(
                tool_name=tool_name,
                status=ToolExecutionStatus.COMPLETED if result.get("success", True) else ToolExecutionStatus.FAILED,
                success=result.get("success", True),
                data=result,
                error=result.get("error"),
                correlation_id=correlation_id,
            )

        except Exception as e:
            logger.error(f"Error executing tool {tool_name}: {e}")
            # Track error
            self._errors_total_count += 1
            return ToolExecutionResult(
                tool_name=tool_name,
                status=ToolExecutionStatus.FAILED,
                success=False,
                data=None,
                error=str(e),
                correlation_id=correlation_id,
            )

    async def get_available_tools(self) -> List[str]:
        """Get list of available CLI tools."""
        return list(self._available_tools.keys())

    async def get_tool_result(self, correlation_id: str, timeout: float = 30.0) -> Optional[ToolExecutionResult]:
        """CLI tools execute synchronously, so results are immediate."""
        return None

    async def validate_parameters(self, tool_name: str, parameters: JSONDict) -> bool:
        """
        Validate parameters for a CLI tool.

        Args:
            tool_name: Name of the tool to validate parameters for
            parameters: Parameters to validate

        Returns:
            True if parameters are valid for the specified tool
        """
        if tool_name not in self._available_tools:
            return False

        if tool_name == "read_file":
            return "path" in parameters
        elif tool_name == "list_files":
            return True
        elif tool_name == "system_info":
            return True

        return True

    async def _get_user_input(self) -> str:
        """Get input from user asynchronously."""
        loop = asyncio.get_event_loop()

        # Check if we're still running before blocking on input
        if not self._running:
            raise asyncio.CancelledError("CLI adapter stopped")

        # Simple async input that works on all platforms
        try:
            return await loop.run_in_executor(None, input)
        except (EOFError, KeyboardInterrupt):
            raise asyncio.CancelledError("Input interrupted")

    async def _handle_interactive_input(self) -> None:
        """Handle interactive user input in a loop."""
        print("\n[CIRIS CLI] Interactive mode started. Type 'help' for commands or 'quit' to exit.\n")

        while self._running:
            try:
                user_input = await self._get_user_input()

                if not user_input.strip():
                    continue

                if user_input.lower() == "quit":
                    logger.info("User requested quit")
                    self._running = False
                    break
                elif user_input.lower() == "help":
                    await self._show_help()
                    continue

                msg = IncomingMessage(
                    message_id=str(uuid.uuid4()),
                    author_id="cli_user",
                    author_name="User",
                    content=user_input,
                    channel_id=self.get_home_channel_id(),
                    timestamp=self._get_time_service().now_iso(),
                    reference_message_id=None,
                )

                # Create an "observe" correlation for this incoming message
                from ciris_engine.schemas.telemetry.core import (
                    CorrelationType,
                    ServiceCorrelation,
                    ServiceCorrelationStatus,
                    ServiceRequestData,
                    ServiceResponseData,
                )

                now = self._get_time_service().now()
                correlation_id = str(uuid.uuid4())

                correlation = ServiceCorrelation(
                    correlation_id=correlation_id,
                    service_type="cli",
                    handler_name="CLIAdapter",
                    action_type="observe",
                    request_data=ServiceRequestData(
                        service_type="cli",
                        method_name="observe",
                        channel_id=msg.channel_id,
                        parameters={
                            "content": msg.content,
                            "author_id": msg.author_id,
                            "author_name": msg.author_name,
                            "message_id": msg.message_id,
                        },
                        request_timestamp=now,
                        thought_id=None,
                        task_id=None,
                        timeout_seconds=None,
                    ),
                    response_data=ServiceResponseData(
                        success=True,
                        result_summary="Message observed",
                        execution_time_ms=0,
                        response_timestamp=now,
                        result_type=None,
                        result_size=None,
                        error_type=None,
                        error_message=None,
                        error_traceback=None,
                        tokens_used=None,
                        memory_bytes=None,
                    ),
                    status=ServiceCorrelationStatus.COMPLETED,
                    created_at=now,
                    updated_at=now,
                    timestamp=now,
                    correlation_type=CorrelationType.SERVICE_INTERACTION,
                    metric_data=None,
                    log_data=None,
                    trace_context=None,
                    retention_policy="raw",
                    ttl_seconds=None,
                    parent_correlation_id=None,
                )

                persistence.add_correlation(correlation, self._get_time_service())
                logger.debug(f"Created observe correlation for CLI message {msg.message_id}")

                if self.on_message:
                    await self.on_message(msg)
                    # Emit telemetry for message processed
                    await self._emit_telemetry(
                        "message_processed", 1.0, {"adapter_type": "cli", "message_id": msg.message_id}
                    )
                else:
                    logger.warning("No message handler configured")

            except (EOFError, asyncio.CancelledError):
                logger.info("Input cancelled or EOF received, stopping interactive mode")
                # Don't set _running = False here - the adapter is still healthy
                # It just means interactive input has ended
                break
            except Exception as e:
                logger.error(f"Error in interactive input loop: {e}")
                # Track error
                self._errors_total_count += 1
                await asyncio.sleep(1)  # Prevent tight error loop

    async def _show_help(self) -> None:
        """Display help information."""
        help_text = """
[CIRIS CLI Help]
================
Commands:
  help     - Show this help message
  quit     - Exit the CLI

Tools available:
"""
        print(help_text)
        for tool in self._available_tools:
            print(f"  - {tool}")
        print("\nSimply type your message to interact with CIRIS.\n")

    async def _tool_list_files(self, params: JSONDict) -> JSONDict:
        """List files in a directory."""
        import os

        try:
            # Validate parameters using schema
            list_params = ListFilesToolParams.model_validate(params)
            files = os.listdir(list_params.path)
            result = ListFilesToolResult(success=True, files=files, count=len(files), error=None)
            return result.model_dump()
        except ValueError:
            result = ListFilesToolResult(success=False, error="Invalid parameters", files=[], count=0)
            return result.model_dump()
        except Exception as e:
            result = ListFilesToolResult(success=False, error=str(e), files=[], count=0)
            return result.model_dump()

    async def _tool_read_file(self, params: JSONDict) -> JSONDict:
        """Read a file's contents."""
        try:
            # Validate parameters using schema
            read_params = ReadFileToolParams.model_validate(params)
            async with aiofiles.open(read_params.path, "r") as f:
                content = await f.read()
            result = ReadFileToolResult(success=True, content=content, size=len(content), error=None)
            return result.model_dump()
        except ValueError:
            result = ReadFileToolResult(success=False, error="No path provided", content=None, size=None)
            return result.model_dump()
        except Exception as e:
            result = ReadFileToolResult(success=False, error=str(e), content=None, size=None)
            return result.model_dump()

    async def _tool_system_info(self, params: JSONDict) -> JSONDict:
        """Get system information."""
        import platform

        import psutil

        try:
            # Get memory info
            memory = psutil.virtual_memory()
            memory_mb = memory.total // (1024 * 1024)

            result = SystemInfoToolResult(
                success=True,
                platform=platform.system(),
                python_version=platform.python_version(),
                cpu_count=psutil.cpu_count() or 1,
                memory_mb=memory_mb,
                error=None,
            )
            return result.model_dump()
        except Exception as e:
            # Return error result if psutil fails
            result = SystemInfoToolResult(
                success=False,
                platform=platform.system(),
                python_version=platform.python_version(),
                cpu_count=1,
                memory_mb=0,
                error=str(e),
            )
            return result.model_dump()

    async def start(self) -> None:
        """Start the CLI adapter."""
        logger.info("Starting CLI adapter")
        logger.debug(f"CLI adapter start: _running was {self._running}")

        # Capture start time
        self._start_time = self._get_time_service().now()

        # Emit telemetry for adapter start
        await self._emit_telemetry(
            "adapter_starting", 1.0, {"adapter_type": "cli", "interactive": str(self.interactive)}
        )

        self._running = True
        logger.debug(f"CLI adapter start: _running now {self._running}")

        if self.interactive:
            # Start interactive input handler
            self._input_task = asyncio.create_task(self._handle_interactive_input())

        # Emit telemetry for successful start
        await self._emit_telemetry(
            "adapter_started", 1.0, {"adapter_type": "cli", "interactive": str(self.interactive)}
        )

    async def stop(self) -> None:
        """Stop the CLI adapter."""
        logger.info("Stopping CLI adapter")

        # Emit telemetry for adapter stopping
        await self._emit_telemetry("adapter_stopping", 1.0, {"adapter_type": "cli"})

        self._running = False

        if self._input_task and not self._input_task.done():
            self._input_task.cancel()
            try:
                await asyncio.wait_for(self._input_task, timeout=1.0)  # Increased timeout
            except (asyncio.CancelledError, asyncio.TimeoutError):
                logger.debug("CLI input task cancelled or timed out")
            except Exception as e:
                logger.warning(f"Error while waiting for input task: {e}")

        # Print message for user awareness
        print("\n[CIRIS CLI] Shutdown complete.")

        # Emit telemetry for successful stop
        await self._emit_telemetry("adapter_stopped", 1.0, {"adapter_type": "cli"})

        # NOTE: Removed os._exit(0) to allow proper cleanup
        # The EOFError handling in _handle_interactive_input should prevent hanging

    async def is_healthy(self) -> bool:
        """Check if the CLI adapter is healthy."""
        logger.debug(f"CLI adapter health check: _running={self._running}")
        return self._running

    def get_service_type(self) -> ServiceType:
        """Get the type of this service."""
        return ServiceType.ADAPTER

    def get_status(self) -> ServiceStatus:
        """Get current service status."""
        from ciris_engine.schemas.services.core import ServiceStatus

        return ServiceStatus(
            service_name="CLIAdapter",
            service_type="adapter",
            is_healthy=self._running,
            uptime_seconds=(
                (self._get_time_service().now() - self._start_time).total_seconds() if self._start_time else 0.0
            ),
            metrics={
                "interactive": self.interactive,
                "running": self._running,
                "available_tools": len(self._available_tools),
            },
            last_error=None,
            custom_metrics=None,
            last_health_check=self._get_time_service().now() if self._time_service else None,
        )

    def get_capabilities(self) -> ServiceCapabilities:
        """Get service capabilities."""
        return ServiceCapabilities(
            service_name="CLIAdapter",
            actions=["send_message", "receive_message", "execute_tool", "list_tools"],
            version="1.0.0",
            dependencies=[],
            metadata=None,
        )

    async def list_tools(self) -> List[str]:
        """List available tools."""
        return list(self._available_tools.keys())

    async def get_tool_schema(self, tool_name: str) -> Optional[ToolParameterSchema]:
        """Get schema for a specific tool."""
        if tool_name not in self._available_tools:
            return None

        # Return basic schema info for CLI tools
        from ciris_engine.schemas.adapters.tools import ToolParameterSchema

        schemas = {
            "list_files": ToolParameterSchema(
                type="object",
                properties={"path": {"type": "string", "description": "Directory path", "default": "."}},
                required=[],
            ),
            "read_file": ToolParameterSchema(
                type="object", properties={"path": {"type": "string", "description": "File path"}}, required=["path"]
            ),
            "system_info": ToolParameterSchema(type="object", properties={}, required=[]),
        }

        return schemas.get(tool_name)

    async def get_tool_info(self, tool_name: str) -> Optional[ToolInfo]:
        """Get detailed information about a specific tool."""
        if tool_name not in self._available_tools:
            return None

        from ciris_engine.schemas.adapters.tools import ToolParameterSchema

        # Define tool information
        tool_descriptions = {
            "list_files": "List files in a directory",
            "read_file": "Read a file's contents",
            "system_info": "Get system information",
        }

        # Define parameter schemas
        tool_parameters = {
            "list_files": ToolParameterSchema(
                type="object",
                properties={"path": {"type": "string", "description": "Directory path", "default": "."}},
                required=[],
            ),
            "read_file": ToolParameterSchema(
                type="object", properties={"path": {"type": "string", "description": "File path"}}, required=["path"]
            ),
            "system_info": ToolParameterSchema(type="object", properties={}, required=[]),
        }

        # Return tool info using the correct schema
        return ToolInfo(
            name=tool_name,
            description=tool_descriptions.get(tool_name, f"CLI tool: {tool_name}"),
            parameters=tool_parameters.get(tool_name, ToolParameterSchema(type="object", properties={}, required=[])),
            category="cli",
            cost=0.0,
            when_to_use=None,
        )

    async def get_all_tool_info(self) -> List[ToolInfo]:
        """Get detailed information about all available tools."""
        tools = []
        for tool_name in self._available_tools:
            tool_info = await self.get_tool_info(tool_name)
            if tool_info:
                tools.append(tool_info)
        return tools

    def get_home_channel_id(self) -> str:
        """Get the home channel ID for this CLI adapter instance."""
        if self.cli_config and hasattr(self.cli_config, "get_home_channel_id"):
            channel_id = self.cli_config.get_home_channel_id()
            if channel_id:
                return str(channel_id)

        # Generate unique channel ID for this CLI instance
        import os
        import uuid

        return f"cli_{os.getpid()}_{uuid.uuid4().hex[:8]}"

    def get_channel_list(self) -> List[ChannelContext]:
        """
        Get list of available CLI channels from correlations.

        Returns:
            List of ChannelContext objects for CLI channels.
        """
        from ciris_engine.logic.persistence.models.correlations import get_active_channels_by_adapter
        from ciris_engine.schemas.persistence.correlations import ChannelInfo

        # Get active channels from last 30 days
        channels_data: List[ChannelInfo] = get_active_channels_by_adapter("cli", since_days=30)

        # Convert to ChannelContext objects
        channels: List[ChannelContext] = []
        for data in channels_data:
            # Determine channel name
            channel_id_val = str(data.channel_id)
            channel_name = channel_id_val
            if "_" in channel_id_val:
                parts = channel_id_val.split("_", 2)
                if len(parts) >= 3:
                    channel_name = f"CLI Session {parts[1]}"

            # CLI channels support all actions
            allowed_actions = ["speak", "observe", "memorize", "recall", "tool", "wa_defer", "runtime_control"]

            channel = ChannelContext(
                channel_id=channel_id_val,
                channel_type="cli",
                created_at=data.last_activity or datetime.now(),
                channel_name=channel_name,
                is_private=True,  # CLI sessions are private
                participants=["user", "ciris"],  # CLI is 1-on-1
                is_active=data.is_active,
                last_activity=data.last_activity,
                message_count=data.message_count,
                allowed_actions=allowed_actions,
                moderation_level="minimal",  # CLI has minimal moderation
            )
            channels.append(channel)

        return channels

    def _collect_metrics(self) -> Dict[str, float]:
        """Collect base metrics for the CLI adapter."""
        uptime = 0.0
        if self._start_time:
            uptime = (self._get_time_service().now() - self._start_time).total_seconds()

        return {
            "healthy": True if self._running else False,
            "uptime_seconds": uptime,
            "request_count": float(self._commands_executed_count),
            "error_count": float(self._errors_total_count),
            "error_rate": float(self._errors_total_count) / max(1, self._commands_executed_count),
        }

    async def get_metrics(self) -> Dict[str, float]:
        """
        Get all CLI adapter metrics including base, custom, and v1.4.3 specific.

        Returns:
            Dictionary containing CLI-specific metrics from the v1.4.3 set:
            - cli_commands_executed: Total number of commands executed
            - cli_errors_total: Total number of errors encountered
            - cli_sessions_active: Number of active CLI sessions (1 if running, 0 if not)
        """
        # Get all base + custom metrics
        metrics = self._collect_metrics()

        # Add v1.4.3 specific metrics
        metrics.update(
            {
                "cli_commands_executed": float(self._commands_executed_count),
                "cli_errors_total": float(self._errors_total_count),
                "cli_sessions_active": 1.0 if self._running else 0.0,
            }
        )

        return metrics
