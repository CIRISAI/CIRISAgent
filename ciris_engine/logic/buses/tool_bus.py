"""
Tool message bus - handles all tool service operations
"""

import logging
import uuid
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Set, cast

from ciris_engine.logic.utils.jsondict_helpers import get_int, get_list, get_str
from ciris_engine.protocols.services import ToolService
from ciris_engine.protocols.services.lifecycle.time import TimeServiceProtocol
from ciris_engine.schemas.adapters.tools import ToolExecutionResult, ToolExecutionStatus, ToolInfo
from ciris_engine.schemas.infrastructure.base import BusMetrics
from ciris_engine.schemas.runtime.enums import ServiceType
from ciris_engine.schemas.types import JSONDict

from .base_bus import BaseBus, BusMessage

if TYPE_CHECKING:
    from ciris_engine.logic.registries.base import ServiceRegistry

logger = logging.getLogger(__name__)


class ToolBus(BaseBus[ToolService]):
    """
    Message bus for all tool operations.

    Handles:
    - execute_tool (returns ToolExecutionResult)
    - get_available_tools
    - get_tool_result (returns ToolExecutionResult)
    - get_tool_info
    - get_all_tool_info
    - validate_parameters
    """

    def __init__(
        self,
        service_registry: "ServiceRegistry",
        time_service: TimeServiceProtocol,
        telemetry_service: Optional[Any] = None,
    ):
        super().__init__(service_type=ServiceType.TOOL, service_registry=service_registry)
        self._time_service = time_service
        self._start_time = time_service.now() if time_service else None

        # Metrics tracking
        self._executions_count = 0
        self._errors_count = 0
        self._cached_tools_count = 0  # Updated by collect_telemetry when available

    async def execute_tool(
        self, tool_name: str, parameters: JSONDict, handler_name: str = "default"
    ) -> ToolExecutionResult:
        """Execute a tool and return the result"""
        logger.debug(f"execute_tool called with tool_name={tool_name}, parameters={parameters}")

        # Step 1: Get ALL tool services to find which ones support this tool
        all_tool_services = []
        try:
            # Access the registry's internal services dict to get all tool services
            from ciris_engine.schemas.runtime.enums import ServiceType

            # Use reflection to access the registry's internal structure
            # This is a temporary solution until we add a proper method
            if hasattr(self.service_registry, "_services"):
                tool_providers = self.service_registry._services.get(ServiceType.TOOL, [])
                for provider in tool_providers:
                    if hasattr(provider, "instance") and hasattr(provider.instance, "get_available_tools"):
                        all_tool_services.append(provider.instance)

            logger.debug(f"Found {len(all_tool_services)} tool services")
        except Exception as e:
            logger.error(f"Failed to get all tool services: {e}")

        # If we couldn't get all services, fall back to getting at least one
        if not all_tool_services:
            service = await self.get_service(handler_name=handler_name, required_capabilities=["execute_tool"])
            if service:
                all_tool_services = [service]

        # Step 2: Find which services support this specific tool
        supporting_services = []
        for service in all_tool_services:
            try:
                # Service is guaranteed to exist in the list
                assert service is not None, "Service in list should not be None"
                available_tools = await service.get_available_tools()
                logger.debug(f"Service {type(service).__name__} supports tools: {available_tools}")
                if tool_name in available_tools:
                    supporting_services.append(service)
            except Exception as e:
                logger.warning(f"Failed to get tools from {type(service).__name__}: {e}")

        # Step 3: If no service supports this tool, return NOT_FOUND
        if not supporting_services:
            logger.error(f"No service supports tool: {tool_name}")

            # Track error metrics
            self._executions_count += 1
            self._errors_count += 1

            return ToolExecutionResult(
                tool_name=tool_name,
                status=ToolExecutionStatus.NOT_FOUND,
                success=False,
                data=None,
                error=f"No service supports tool: {tool_name}",
                correlation_id=str(uuid.uuid4()),
            )

        # Step 4: Select the appropriate service
        selected_service = None

        if len(supporting_services) == 1:
            # Only one service supports this tool
            selected_service = supporting_services[0]
            logger.debug(f"Using {type(selected_service).__name__} (only service with this tool)")
        else:
            # Multiple services support this tool - use routing logic
            # TODO: In future, extract channel_id/guild_id from context to route appropriately
            # For now, prefer APIToolService over SecretsToolService for general tools
            for service in supporting_services:
                if "APIToolService" in type(service).__name__:
                    selected_service = service
                    break

            if not selected_service:
                selected_service = supporting_services[0]

            logger.debug(f"Selected {type(selected_service).__name__} from {len(supporting_services)} options")

        # Step 5: Execute the tool
        try:
            # Logic guarantees selected_service is not None at this point
            assert selected_service is not None, "Selected service must not be None"
            logger.debug(f"Executing tool '{tool_name}' with {type(selected_service).__name__}")
            result: ToolExecutionResult = await selected_service.execute_tool(tool_name, parameters)

            # Track metrics
            self._executions_count += 1
            if not result.success:
                self._errors_count += 1

            return result
        except Exception as e:
            logger.error(f"Failed to execute tool {tool_name}: {e}", exc_info=True)

            # Track error metrics
            self._executions_count += 1
            self._errors_count += 1

            return ToolExecutionResult(
                tool_name=tool_name,
                status=ToolExecutionStatus.FAILED,
                success=False,
                data=None,
                error=str(e),
                correlation_id=str(uuid.uuid4()),
            )

    async def get_available_tools(self, handler_name: str = "default") -> List[str]:
        """Get list of available tool names"""
        service = await self.get_service(handler_name=handler_name, required_capabilities=["get_available_tools"])

        if not service:
            logger.error(f"No tool service available for {handler_name}")
            return []

        try:
            # Cast to Any to handle dynamic method access
            service_any = cast(Any, service)
            result: List[str] = await service_any.get_available_tools()
            return result
        except Exception as e:
            logger.error(f"Error getting available tools: {e}", exc_info=True)
            return []

    async def get_tool_result(
        self, correlation_id: str, timeout: float = 30.0, handler_name: str = "default"
    ) -> Optional[ToolExecutionResult]:
        """Get result of an async tool execution by correlation ID"""
        service = await self.get_service(handler_name=handler_name, required_capabilities=["get_tool_result"])

        if not service:
            logger.error(f"No tool service available for {handler_name}")
            return None

        try:
            # Cast to Any to handle dynamic method access
            service_any = cast(Any, service)
            result: Optional[ToolExecutionResult] = await service_any.get_tool_result(correlation_id, timeout)
            return result
        except Exception as e:
            logger.error(f"Error getting tool result: {e}", exc_info=True)
            return None

    async def validate_parameters(self, tool_name: str, parameters: JSONDict, handler_name: str = "default") -> bool:
        """Validate parameters for a tool"""
        service = await self.get_service(handler_name=handler_name, required_capabilities=["validate_parameters"])

        if not service:
            logger.error(f"No tool service available for {handler_name}")
            return False

        try:
            # Cast to Any to handle dynamic method access
            service_any = cast(Any, service)
            result: bool = await service_any.validate_parameters(tool_name, parameters)
            return result
        except Exception as e:
            logger.error(f"Error validating parameters: {e}", exc_info=True)
            return False

    async def is_healthy(self, handler_name: str = "default") -> bool:
        """Check if tool service is healthy"""
        service = await self.get_service(handler_name=handler_name)
        if not service:
            return False
        try:
            return await service.is_healthy()
        except Exception as e:
            logger.error(f"Failed to check health: {e}")
            return False

    async def get_tool_info(self, tool_name: str, handler_name: str = "default") -> Optional[ToolInfo]:
        """Get detailed information about a specific tool"""
        service = await self.get_service(handler_name=handler_name, required_capabilities=["get_tool_info"])

        if not service:
            logger.error(f"No tool service available for {handler_name}")
            return None

        try:
            # Cast to Any to handle dynamic method access
            service_any = cast(Any, service)
            result: Optional[ToolInfo] = await service_any.get_tool_info(tool_name)
            return result
        except Exception as e:
            logger.error(f"Error getting tool info: {e}", exc_info=True)
            return None

    async def get_all_tool_info(self, handler_name: str = "default") -> List[ToolInfo]:
        """Get detailed information about all available tools"""
        service = await self.get_service(handler_name=handler_name, required_capabilities=["get_all_tool_info"])

        if not service:
            logger.error(f"No tool service available for {handler_name}")
            return []

        try:
            # Cast to Any to handle dynamic method access
            service_any = cast(Any, service)
            result: List[ToolInfo] = await service_any.get_all_tool_info()
            return result
        except Exception as e:
            logger.error(f"Error getting all tool info: {e}", exc_info=True)
            return []

    async def get_capabilities(self, handler_name: str = "default") -> List[str]:
        """Get tool service capabilities"""
        service = await self.get_service(handler_name=handler_name)
        if not service:
            return []
        try:
            capabilities = service.get_capabilities()
            return capabilities.supports_operation_list if hasattr(capabilities, "supports_operation_list") else []
        except Exception as e:
            logger.error(f"Failed to get capabilities: {e}")
            return []

    async def _process_message(self, message: BusMessage) -> None:
        """Process a tool message - currently all tool operations are synchronous"""
        logger.warning(f"Tool operations should be synchronous, got queued message: {type(message)}")

    def _get_all_tool_services(self) -> List[Any]:
        """Get all tool services from the registry."""
        all_tool_services = []
        try:
            from ciris_engine.schemas.runtime.enums import ServiceType

            if hasattr(self.service_registry, "_services"):
                tool_providers = self.service_registry._services.get(ServiceType.TOOL, [])
                for provider in tool_providers:
                    if hasattr(provider, "instance"):
                        all_tool_services.append(provider.instance)
        except Exception as e:
            logger.error(f"Failed to get all tool services: {e}")

        return all_tool_services

    def _create_empty_tool_telemetry(self) -> dict[str, Any]:
        """Create empty telemetry response when no services available."""
        return {
            "service_name": "tool_bus",
            "healthy": False,
            "failed_count": 0,
            "processed_count": 0,
            "provider_count": 0,
            "total_tools": 0,
            "error": "No tool services available",
        }

    def _create_tool_telemetry_tasks(self, services: List[Any]) -> List[Any]:
        """Create telemetry collection tasks for all services."""
        import asyncio

        tasks = []
        for service in services:
            if hasattr(service, "get_telemetry"):
                tasks.append(asyncio.create_task(service.get_telemetry()))
        return tasks

    def _aggregate_tool_telemetry(self, telemetry: JSONDict, aggregated: JSONDict, unique_tools: Set[str]) -> None:
        """Aggregate a single telemetry result into the combined metrics."""
        if telemetry:
            service_name = get_str(telemetry, "service_name", "unknown")
            providers_list = aggregated["providers"]
            if isinstance(providers_list, list):
                providers_list.append(service_name)

            failed_count = aggregated["failed_count"]
            if isinstance(failed_count, int):
                aggregated["failed_count"] = failed_count + get_int(telemetry, "error_count", 0)

            processed_count = aggregated["processed_count"]
            if isinstance(processed_count, int):
                aggregated["processed_count"] = processed_count + get_int(telemetry, "tool_executions", 0)

            if "available_tools" in telemetry:
                # Use update() to add each tool from the list to the separate unique_tools set
                available_tools = get_list(telemetry, "available_tools", [])
                unique_tools.update(available_tools)

    def _collect_metrics(self) -> dict[str, float]:
        """Collect base metrics for the tool bus."""
        # Calculate uptime
        uptime_seconds = 0.0
        if hasattr(self, "_time_service") and self._time_service:
            if hasattr(self, "_start_time") and self._start_time:
                uptime_seconds = (self._time_service.now() - self._start_time).total_seconds()

        return {
            "tool_executions_total": float(self._executions_count),
            "tool_execution_errors": float(self._errors_count),
            "tools_available": float(self._cached_tools_count),
            "tool_uptime_seconds": uptime_seconds,
        }

    def get_metrics(self) -> BusMetrics:
        """Get all tool bus metrics as typed BusMetrics schema."""
        # Get registered tools count
        if self._cached_tools_count > 0:
            registered_tools_count = self._cached_tools_count
        else:
            tool_services = self._get_all_tool_services()
            registered_tools_count = len(tool_services) * 5  # Conservative estimate

        # Calculate uptime
        uptime_seconds = 0.0
        if hasattr(self, "_time_service") and self._time_service:
            if hasattr(self, "_start_time") and self._start_time:
                uptime_seconds = (self._time_service.now() - self._start_time).total_seconds()

        # Map to BusMetrics schema
        return BusMetrics(
            messages_sent=self._executions_count,  # Total tool executions
            messages_received=self._executions_count,  # Synchronous
            messages_dropped=0,  # Not tracked yet
            average_latency_ms=0.0,  # Not tracked yet
            active_subscriptions=len(self._get_all_tool_services()),
            queue_depth=self.get_queue_size(),
            errors_last_hour=self._errors_count,  # Total errors (not windowed yet)
            busiest_service=None,  # Could track which tool gets used most
            additional_metrics={
                "tool_executions_total": self._executions_count,
                "tool_execution_errors": self._errors_count,
                "tools_available": registered_tools_count,
                "tool_uptime_seconds": uptime_seconds,
            },
        )

    async def collect_telemetry(self) -> JSONDict:
        """
        Collect telemetry from all tool providers in parallel.

        Returns aggregated metrics including:
        - failed_count: Total tool executions failed
        - processed_count: Total tool executions processed
        - provider_count: Number of active providers
        - total_tools: Total unique tools available
        """
        import asyncio

        all_tool_services = self._get_all_tool_services()

        if not all_tool_services:
            return self._create_empty_tool_telemetry()

        # Create tasks to collect telemetry from all providers
        tasks = self._create_tool_telemetry_tasks(all_tool_services)

        # Initialize aggregated metrics (separate set from dict)
        unique_tools: Set[str] = set()
        aggregated: JSONDict = {
            "service_name": "tool_bus",
            "healthy": True,
            "failed_count": 0,
            "processed_count": 0,
            "provider_count": len(all_tool_services),
            "total_tools": 0,
            "providers": [],
        }

        if not tasks:
            aggregated["total_tools"] = len(unique_tools)
            return aggregated

        # Collect results with timeout
        done, pending = await asyncio.wait(tasks, timeout=2.0, return_when=asyncio.ALL_COMPLETED)

        # Cancel timed-out tasks
        for task in pending:
            task.cancel()

        # Aggregate results
        for task in done:
            try:
                telemetry = task.result()
                self._aggregate_tool_telemetry(telemetry, aggregated, unique_tools)
            except Exception as e:
                logger.warning(f"Failed to collect telemetry from tool provider: {e}")

        # Count unique tools and add to aggregated
        aggregated["total_tools"] = len(unique_tools)

        # Cache the tools count for get_metrics()
        self._cached_tools_count = len(unique_tools)

        return aggregated

    def get_tools_by_metadata(self, metadata_filter: Dict[str, Any]) -> List[Any]:
        """Get tool services matching metadata filter.

        Enables discovery of data sources for DSAR coordination.

        Args:
            metadata_filter: Dict of metadata key-value pairs to match
                Example: {"data_source": True}
                Example: {"data_source": True, "data_source_type": "sql"}
                Example: {"gdpr_applicable": True}

        Returns:
            List of tool service instances matching the filter

        Example:
            # Get all data sources
            data_sources = tool_bus.get_tools_by_metadata({"data_source": True})

            # Get SQL data sources only
            sql_sources = tool_bus.get_tools_by_metadata({
                "data_source": True,
                "data_source_type": "sql"
            })

            # Get GDPR-applicable sources
            gdpr_sources = tool_bus.get_tools_by_metadata({"gdpr_applicable": True})
        """
        matching_services = []

        for provider in self._get_all_tool_services():
            # Get service metadata
            metadata = provider.get_service_metadata()

            # Check if all filter criteria match
            matches = all(metadata.get(key) == value for key, value in metadata_filter.items())

            if matches:
                matching_services.append(provider)

        return matching_services
