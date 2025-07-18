"""Discord tool handling component for tool execution operations."""
import discord
import logging
import asyncio
import uuid
from typing import Dict, List, Optional, TYPE_CHECKING, Any

from ciris_engine.schemas.telemetry.core import (
    ServiceCorrelation,
    ServiceCorrelationStatus,
)
from ciris_engine.schemas.persistence.core import CorrelationUpdateRequest
from ciris_engine.schemas.adapters.tools import ToolInfo, ToolParameterSchema, ToolExecutionResult, ToolExecutionStatus
from ciris_engine.logic import persistence
from ciris_engine.schemas.telemetry.core import (
    CorrelationType,
    ServiceRequestData,
    ServiceResponseData,
    MetricData,
    LogData,
    TraceContext
)
from datetime import datetime, timezone
from ciris_engine.schemas.adapters.tool_execution import ToolExecutionArgs, ToolHandlerContext

if TYPE_CHECKING:
    from ciris_engine.protocols.services.lifecycle.time import TimeServiceProtocol

from ciris_engine.logic.services.lifecycle.time import TimeService

logger = logging.getLogger(__name__)

class DiscordToolHandler:
    """Handles Discord tool execution and result management."""

    def __init__(self, tool_registry: Optional[Any] = None, client: Optional[discord.Client] = None, time_service: Optional["TimeServiceProtocol"] = None) -> None:
        """Initialize the tool handler.

        Args:
            tool_registry: Registry of available tools
            client: Discord client instance
            time_service: Time service for consistent time operations
        """
        self.tool_registry = tool_registry
        self.client = client
        self._tool_results: Dict[str, ToolExecutionResult] = {}
        self._time_service = time_service

        # Ensure we have a time service
        if self._time_service is None:
            from ciris_engine.logic.services.lifecycle.time import TimeService
            self._time_service = TimeService()

    def set_client(self, client: discord.Client) -> None:
        """Set the Discord client after initialization.

        Args:
            client: Discord client instance
        """
        self.client = client

    def set_tool_registry(self, tool_registry: Any) -> None:
        """Set the tool registry after initialization.

        Args:
            tool_registry: Registry of available tools
        """
        self.tool_registry = tool_registry

    async def execute_tool(self, tool_name: str, tool_args: Dict[str, Any]) -> ToolExecutionResult:
        """Execute a registered Discord tool via the tool registry.

        Args:
            tool_name: Name of the tool to execute
            tool_args: Arguments to pass to the tool

        Returns:
            Tool execution result as a dictionary

        Raises:
            RuntimeError: If tool registry is not configured or tool not found
        """
        if not self.tool_registry:
            return ToolExecutionResult(
                tool_name=tool_name,
                status=ToolExecutionStatus.FAILED,
                success=False,
                data=None,
                error="Tool registry not configured",
                correlation_id=str(uuid.uuid4())
            )

        handler = self.tool_registry.get_handler(tool_name)
        if not handler:
            return ToolExecutionResult(
                tool_name=tool_name,
                status=ToolExecutionStatus.FAILED,
                success=False,
                data=None,
                error=f"Tool handler for '{tool_name}' not found",
                correlation_id=str(uuid.uuid4())
            )

        # Convert dict to typed args
        typed_args = ToolExecutionArgs(
            correlation_id=tool_args.get("correlation_id", str(uuid.uuid4())),
            thought_id=tool_args.get('thought_id'),
            task_id=tool_args.get('task_id'),
            channel_id=tool_args.get('channel_id'),
            timeout_seconds=tool_args.get('timeout_seconds', 30.0),
            tool_specific_params={k: v for k, v in tool_args.items() if k not in ['correlation_id', 'thought_id', 'task_id', 'channel_id', 'timeout_seconds']}
        )
        
        correlation_id = str(typed_args.correlation_id or uuid.uuid4())
        
        # Create properly typed request data
        now = self._time_service.now() if self._time_service else datetime.now(timezone.utc)
        request_data = ServiceRequestData(
            service_type="discord",
            method_name=tool_name,
            parameters={k: str(v) for k, v in typed_args.get_all_params().items()},
            request_timestamp=now,
            thought_id=typed_args.thought_id,
            task_id=typed_args.task_id,
            channel_id=typed_args.channel_id,
            timeout_seconds=typed_args.timeout_seconds
        )

        persistence.add_correlation(
            ServiceCorrelation(
                correlation_id=correlation_id,
                correlation_type=CorrelationType.SERVICE_INTERACTION,
                service_type="discord",
                handler_name="DiscordAdapter",
                action_type=tool_name,
                request_data=request_data,
                response_data=None,
                status=ServiceCorrelationStatus.PENDING,
                created_at=now,
                updated_at=now,
                timestamp=now,
                metric_data=None,
                log_data=None,
                trace_context=None,
                retention_policy="raw",
                ttl_seconds=None,
                parent_correlation_id=None
            ),
            time_service=self._time_service if self._time_service else TimeService()
        )

        try:
            import time
            start_time = time.time()
            # Create context for tool handler
            handler_context = ToolHandlerContext(
                tool_name=tool_name,
                handler_name="DiscordAdapter",
                bot_instance=self.client
            )
            
            # Merge all params with bot
            tool_args_with_bot = {**typed_args.get_all_params(), "bot": self.client}
            result = await handler(tool_args_with_bot)
            _execution_time = (time.time() - start_time) * 1000

            result_dict = result if isinstance(result, dict) else result.__dict__
            
            # Create properly typed response data
            response_now = self._time_service.now() if self._time_service else datetime.now(timezone.utc)
            ServiceResponseData(
                success=result_dict.get("success", True),
                result_summary=str(result_dict.get("data", {}))[:100] if result_dict.get("data") else None,
                result_type="dict",
                result_size=len(str(result_dict)),
                error_type=None,
                error_message=result_dict.get("error"),
                error_traceback=None,
                execution_time_ms=_execution_time,
                response_timestamp=response_now,
                tokens_used=None,
                memory_bytes=None
            )

            # Create ToolExecutionResult
            execution_result = ToolExecutionResult(
                tool_name=tool_name,
                status=ToolExecutionStatus.COMPLETED if result_dict.get("success", True) else ToolExecutionStatus.FAILED,
                success=result_dict.get("success", True),
                data=result_dict,
                error=result_dict.get("error"),
                correlation_id=correlation_id or str(uuid.uuid4())
            )

            if correlation_id:
                self._tool_results[correlation_id] = execution_result
                persistence.update_correlation(
                    CorrelationUpdateRequest(
                        correlation_id=correlation_id,
                        response_data=result_dict,
                        status=ServiceCorrelationStatus.COMPLETED,
                        metric_value=None,
                        tags=None
                    ),
                    correlation_or_time_service=self._time_service if self._time_service else TimeService()
                )

            return execution_result

        except Exception as e:
            logger.exception(f"Tool execution failed for {tool_name}: {e}")
            error_result = {"error": str(e), "tool_name": tool_name}

            if correlation_id:
                persistence.update_correlation(
                    CorrelationUpdateRequest(
                        correlation_id=correlation_id,
                        response_data=error_result,
                        status=ServiceCorrelationStatus.FAILED,
                        metric_value=None,
                        tags=None
                    ),
                    correlation_or_time_service=self._time_service if self._time_service else TimeService()
                )

            return ToolExecutionResult(
                tool_name=tool_name,
                status=ToolExecutionStatus.FAILED,
                success=False,
                data=None,
                error=str(e),
                correlation_id=correlation_id or str(uuid.uuid4())
            )

    async def get_tool_result(self, correlation_id: str, timeout: int = 10) -> Optional[ToolExecutionResult]:
        """Fetch a tool result by correlation ID from the internal cache.

        Args:
            correlation_id: The correlation ID of the tool execution
            timeout: Maximum time to wait for the result in seconds

        Returns:
            Tool result dictionary or not_found status
        """
        for _ in range(timeout * 10):  # Check every 0.1 seconds
            if correlation_id in self._tool_results:
                return self._tool_results.pop(correlation_id)
            await asyncio.sleep(0.1)

        logger.warning(f"Tool result for correlation_id {correlation_id} not found after {timeout}s")
        return None

    def get_available_tools(self) -> List[str]:
        """Return names of registered Discord tools.

        Returns:
            List of available tool names
        """
        if not self.tool_registry:
            return []

        if hasattr(self.tool_registry, 'tools'):
            return list(self.tool_registry.tools.keys())
        elif hasattr(self.tool_registry, 'get_tools'):
            return list(self.tool_registry.get_tools().keys())
        else:
            logger.warning("Tool registry interface not recognized")
            return []

    def get_tool_info(self, tool_name: str) -> Optional[ToolInfo]:
        """Get detailed information about a specific tool."""
        if not self.tool_registry:
            return None

        # Check if the tool registry has a method to get tool description
        if hasattr(self.tool_registry, 'get_tool_description'):
            tool_desc = self.tool_registry.get_tool_description(tool_name)
            if tool_desc:
                # Convert tool description to ToolInfo
                parameter_properties = {}
                required_params = []
                if hasattr(tool_desc, 'parameters'):
                    for param in tool_desc.parameters:
                        param_name = getattr(param, 'name', 'unknown')
                        parameter_properties[param_name] = {
                            "type": getattr(param.type, 'value', str(param.type)),
                            "description": getattr(param, 'description', ''),
                        }
                        if getattr(param, 'default', None) is not None:
                            parameter_properties[param_name]["default"] = getattr(param, 'default')
                        if getattr(param, 'enum', None) is not None:
                            parameter_properties[param_name]["enum"] = getattr(param, 'enum')
                        if getattr(param, 'required', True):
                            required_params.append(param_name)
                
                parameters = ToolParameterSchema(
                    type="object",
                    properties=parameter_properties,
                    required=required_params
                )

                return ToolInfo(
                    name=tool_desc.name,
                    description=tool_desc.description,
                    category=getattr(tool_desc, 'category', 'discord'),
                    parameters=parameters,
                    cost=0.0,
                    when_to_use=getattr(tool_desc, 'when_to_use', None)
                )

        # Fallback to basic info if tool exists
        if tool_name in self.get_available_tools():
            return ToolInfo(
                name=tool_name,
                description=f"Discord tool: {tool_name}",
                category="discord",
                parameters=ToolParameterSchema(
                    type="object",
                    properties={},
                    required=[]
                ),
                cost=0.0,
                when_to_use=None
            )

        return None

    async def get_all_tool_info(self) -> List[ToolInfo]:  # NOSONAR: ToolService protocol requires async signature
        """Get detailed information about all available tools."""
        tools = []
        for tool_name in self.get_available_tools():
            tool_info = self.get_tool_info(tool_name)
            if tool_info:
                tools.append(tool_info)
        return tools

    def validate_tool_parameters(self, tool_name: str, parameters: Dict[str, Any]) -> bool:
        """Basic parameter validation using tool registry schemas.

        Args:
            tool_name: Name of the tool to validate parameters for
            parameters: Parameters to validate

        Returns:
            True if parameters are valid, False otherwise
        """
        if not self.tool_registry:
            return False

        try:
            schema = self.tool_registry.get_schema(tool_name)
            if not schema:
                return False

            return all(k in parameters for k in schema.keys())

        except Exception as e:
            logger.warning(f"Parameter validation failed for {tool_name}: {e}")
            return False

    def clear_tool_results(self) -> None:
        """Clear all cached tool results."""
        self._tool_results.clear()

    def get_cached_result_count(self) -> int:
        """Get the number of cached tool results.

        Returns:
            Number of cached results
        """
        return len(self._tool_results)

    def remove_cached_result(self, correlation_id: str) -> bool:
        """Remove a specific cached result.

        Args:
            correlation_id: The correlation ID to remove

        Returns:
            True if result was removed, False if not found
        """
        if correlation_id in self._tool_results:
            del self._tool_results[correlation_id]
            return True
        return False
