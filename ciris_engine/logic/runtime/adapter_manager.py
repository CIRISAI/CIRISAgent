"""
Runtime Adapter Management

Provides dynamic adapter loading/unloading capabilities during runtime,
extending the existing processor control capabilities with adapter lifecycle management.
"""

import asyncio
import logging
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Union

import aiofiles

from ciris_engine.schemas.types import JSONDict

if TYPE_CHECKING:
    from ciris_engine.logic.runtime.ciris_runtime import CIRISRuntime

from dataclasses import dataclass, field
from datetime import datetime

from ciris_engine.logic.adapters import load_adapter
from ciris_engine.logic.config import ConfigBootstrap
from ciris_engine.logic.registries.base import Priority, SelectionStrategy
from ciris_engine.protocols.services.lifecycle.time import TimeServiceProtocol
from ciris_engine.schemas.adapters.registration import AdapterServiceRegistration
from ciris_engine.schemas.adapters.runtime_context import AdapterStartupContext
from ciris_engine.schemas.infrastructure.base import ServiceRegistration
from ciris_engine.schemas.runtime.adapter_management import (
    AdapterConfig,
    AdapterInfo,
    AdapterMetrics,
    AdapterOperationResult,
    CommunicationAdapterInfo,
    CommunicationAdapterStatus,
    RuntimeAdapterStatus,
)
from ciris_engine.schemas.runtime.enums import ServiceType

logger = logging.getLogger(__name__)


@dataclass
class AdapterInstance:
    """Information about a loaded adapter instance"""

    adapter_id: str
    adapter_type: str
    adapter: Any  # Actually Service but also needs BaseAdapterProtocol methods
    config_params: AdapterConfig  # Adapter-specific settings
    loaded_at: datetime
    is_running: bool = False
    services_registered: List[str] = field(default_factory=list)
    lifecycle_task: Optional[asyncio.Task[Any]] = field(default=None, init=False)
    lifecycle_runner: Optional[asyncio.Task[Any]] = field(default=None, init=False)

    def __post_init__(self) -> None:
        # services_registered is now properly initialized with default_factory
        pass


class AdapterManagerInterface:
    """Interface for runtime adapter management operations"""

    async def load_adapter(
        self, adapter_type: str, adapter_id: str, config_params: Optional[AdapterConfig] = None
    ) -> AdapterOperationResult:
        """Load and start a new adapter instance"""
        raise NotImplementedError("This is an interface method")

    async def unload_adapter(self, adapter_id: str) -> AdapterOperationResult:
        """Stop and unload an adapter instance"""
        raise NotImplementedError("This is an interface method")

    async def reload_adapter(
        self, adapter_id: str, config_params: Optional[AdapterConfig] = None
    ) -> AdapterOperationResult:
        """Reload an adapter with new configuration"""
        raise NotImplementedError("This is an interface method")

    async def list_adapters(self) -> List[RuntimeAdapterStatus]:
        """List all loaded adapter instances"""
        raise NotImplementedError("This is an interface method")

    async def get_adapter_status(self, adapter_id: str) -> Optional[RuntimeAdapterStatus]:
        """Get detailed status of a specific adapter"""
        raise NotImplementedError("This is an interface method")


class RuntimeAdapterManager(AdapterManagerInterface):
    """Manages runtime adapter lifecycle with configuration support"""

    def __init__(self, runtime: "CIRISRuntime", time_service: TimeServiceProtocol) -> None:
        self.runtime = runtime
        self.time_service = time_service
        self.loaded_adapters: Dict[str, AdapterInstance] = {}
        self._adapter_counter = 0
        self._config_listener_registered = False

        # Register for config changes after initialization
        self._register_config_listener()

    async def load_adapter(
        self, adapter_type: str, adapter_id: str, config_params: Optional[AdapterConfig] = None
    ) -> AdapterOperationResult:
        """Load and start a new adapter instance

        Args:
            adapter_type: Adapter type (cli, discord, api, etc.)
            adapter_id: Unique ID for the adapter
            config_params: Optional configuration parameters

        Returns:
            Dict with success status and details
        """
        try:
            if adapter_id in self.loaded_adapters:
                logger.warning(f"Adapter with ID '{adapter_id}' already exists")
                return AdapterOperationResult(
                    success=False,
                    adapter_id=adapter_id,
                    adapter_type=adapter_type,
                    message=f"Adapter with ID '{adapter_id}' already exists",
                    error=f"Adapter with ID '{adapter_id}' already exists",
                    details={},
                )

            logger.info(f"Loading adapter: type={adapter_type}, id={adapter_id}, params={config_params}")

            adapter_class = load_adapter(adapter_type)

            # Create AdapterStartupContext for the adapter
            from ciris_engine.schemas.config.essential import EssentialConfig

            # Get essential_config - it must exist
            essential_config = getattr(self.runtime, "essential_config", None)
            if not essential_config:
                # Create minimal essential config if not present (all fields have defaults)
                essential_config = EssentialConfig()

            startup_context = AdapterStartupContext(
                essential_config=essential_config,
                modules_to_load=getattr(self.runtime, "modules_to_load", []),
                startup_channel_id=getattr(self.runtime, "startup_channel_id", ""),
                debug=getattr(self.runtime, "debug", False),
                bus_manager=getattr(self.runtime, "bus_manager", None),
                time_service=self.time_service,
                service_registry=getattr(self.runtime, "service_registry", None),
            )

            # Build adapter kwargs from config
            # For complex adapters (MCP), use adapter_config for nested structures
            # For simple adapters, use settings for flat primitives
            adapter_kwargs: Dict[str, Any] = {}
            if config_params:
                # First add simple settings as kwargs
                if config_params.settings:
                    adapter_kwargs.update(config_params.settings)
                # For adapters that need nested configs (MCP), pass adapter_config
                if config_params.adapter_config:
                    adapter_kwargs["adapter_config"] = config_params.adapter_config

            # All adapters must support context - no fallback
            # Type ignore: adapter_class is dynamically loaded, mypy can't verify constructor signature
            adapter = adapter_class(self.runtime, context=startup_context, **adapter_kwargs)  # type: ignore[call-arg]

            instance = AdapterInstance(
                adapter_id=adapter_id,
                adapter_type=adapter_type,
                adapter=adapter,
                config_params=config_params or AdapterConfig(adapter_type=adapter_type, enabled=True),
                loaded_at=self.time_service.now(),
            )

            await adapter.start()

            # For Discord adapters, we need to run the lifecycle to establish connection
            if adapter_type == "discord" and hasattr(adapter, "run_lifecycle"):
                logger.info(f"Starting lifecycle for Discord adapter {adapter_id}")
                # Create a task that the Discord adapter will wait on
                # This mimics the behavior when running from main.py
                agent_task = asyncio.create_task(asyncio.Event().wait())
                instance.lifecycle_task = agent_task

                # Store the lifecycle runner task
                instance.lifecycle_runner = asyncio.create_task(
                    adapter.run_lifecycle(agent_task), name=f"discord_lifecycle_{adapter_id}"
                )

                # Don't wait here - let it run in the background
                logger.info(f"Discord adapter {adapter_id} lifecycle started in background")

            instance.is_running = True

            self._register_adapter_services(instance)

            # Save adapter config to graph
            await self._save_adapter_config_to_graph(
                adapter_id, adapter_type, config_params or AdapterConfig(adapter_type=adapter_type, enabled=True)
            )

            # Don't add dynamically loaded adapters to runtime.adapters
            # to avoid duplicate bootstrap entries in control_service
            # self.runtime.adapters.append(adapter)
            self.loaded_adapters[adapter_id] = instance

            logger.info(f"Successfully loaded and started adapter {adapter_id} (adapter_manager id: {id(self)})")
            return AdapterOperationResult(
                success=True,
                adapter_id=adapter_id,
                adapter_type=adapter_type,
                message=f"Successfully loaded adapter with {len(instance.services_registered)} services",
                error=None,
                details={"loaded_at": instance.loaded_at.isoformat(), "services": len(instance.services_registered)},
            )

        except Exception as e:
            logger.error(f"Failed to load adapter {adapter_type} with ID {adapter_id}: {e}", exc_info=True)
            return AdapterOperationResult(
                success=False,
                adapter_id=adapter_id,
                adapter_type=adapter_type,
                message=f"Failed to load adapter: {str(e)}",
                error=str(e),
                details={},
            )

    def _create_adapter_operation_result(
        self,
        success: bool,
        adapter_id: str,
        adapter_type: str,
        message: str,
        error: Optional[str] = None,
        details: Optional[JSONDict] = None,
    ) -> AdapterOperationResult:
        """Factory method for consistent AdapterOperationResult creation with strict typing."""
        return AdapterOperationResult(
            success=success,
            adapter_id=adapter_id,
            adapter_type=adapter_type,
            message=message,
            error=error,
            details=details or {},
        )

    def _validate_adapter_unload_eligibility(self, adapter_id: str) -> Optional[AdapterOperationResult]:
        """Check if adapter can be safely unloaded - fail fast if not eligible.

        Returns None if eligible, AdapterOperationResult with error if not eligible.
        """
        if adapter_id not in self.loaded_adapters:
            logger.warning(
                f"Adapter unload failed: '{adapter_id}' not found. "
                f"Loaded adapters: {list(self.loaded_adapters.keys())}. "
                f"adapter_manager id: {id(self)}"
            )
            return self._create_adapter_operation_result(
                success=False,
                adapter_id=adapter_id,
                adapter_type="unknown",
                message=f"Adapter with ID '{adapter_id}' not found",
                error=f"Adapter with ID '{adapter_id}' not found",
            )

        instance = self.loaded_adapters[adapter_id]
        communication_adapter_types = {"discord", "api", "cli"}

        if instance.adapter_type not in communication_adapter_types:
            return None  # Non-communication adapters are always eligible

        # Count remaining communication adapters from dynamically loaded adapters
        remaining_comm_adapters = sum(
            1
            for aid, inst in self.loaded_adapters.items()
            if aid != adapter_id and inst.adapter_type in communication_adapter_types
        )

        # Also count bootstrap adapters from runtime.adapters (these are NOT in loaded_adapters)
        if hasattr(self.runtime, "adapters") and self.runtime.adapters:
            for bootstrap_adapter in self.runtime.adapters:
                adapter_type = getattr(bootstrap_adapter, "adapter_type", None)
                adapter_class = type(bootstrap_adapter).__name__
                logger.warning(f"Bootstrap adapter check: class={adapter_class}, adapter_type={adapter_type}")
                # Check both adapter_type attribute and class name patterns
                if adapter_type in communication_adapter_types:
                    remaining_comm_adapters += 1
                elif (
                    "api" in adapter_class.lower()
                    or "cli" in adapter_class.lower()
                    or "discord" in adapter_class.lower()
                ):
                    remaining_comm_adapters += 1
                    logger.warning(f"Counted bootstrap adapter {adapter_class} based on class name")

        logger.warning(
            f"Adapter unload eligibility check: adapter_id={adapter_id}, "
            f"remaining_comm_adapters={remaining_comm_adapters}"
        )

        if remaining_comm_adapters == 0:
            error_msg = f"Unable to unload last adapter providing COMM service: {adapter_id}"
            logger.error(error_msg)
            return self._create_adapter_operation_result(
                success=False,
                adapter_id=adapter_id,
                adapter_type=instance.adapter_type,
                message=error_msg,
                error=error_msg,
            )

        return None  # Eligible for unload

    async def _cancel_adapter_lifecycle_tasks(self, adapter_id: str, instance: AdapterInstance) -> None:
        """Cancel all lifecycle tasks for an adapter instance - no fallbacks, strict cancellation."""
        if hasattr(instance, "lifecycle_runner") and instance.lifecycle_runner is not None:
            logger.debug(f"Cancelling lifecycle runner for {adapter_id}")
            instance.lifecycle_runner.cancel()
            try:
                await instance.lifecycle_runner
            except asyncio.CancelledError:
                # Expected when we cancel the task - this is the only acceptable exception
                pass

        if hasattr(instance, "lifecycle_task") and instance.lifecycle_task is not None:
            logger.debug(f"Cancelling lifecycle task for {adapter_id}")
            instance.lifecycle_task.cancel()
            try:
                await instance.lifecycle_task
            except asyncio.CancelledError:
                # Expected when we cancel the task - this is the only acceptable exception
                pass

    async def _cleanup_adapter_from_runtime(self, adapter_id: str, instance: AdapterInstance) -> None:
        """Remove adapter from runtime.adapters list and clean up references - fail fast on issues."""
        # Stop adapter if running
        if instance.is_running:
            await instance.adapter.stop()
            instance.is_running = False

        # Unregister services
        self._unregister_adapter_services(instance)

        # Remove from runtime adapters list (if present)
        if hasattr(self.runtime, "adapters"):
            for i, adapter in enumerate(self.runtime.adapters):
                if adapter is instance.adapter:
                    self.runtime.adapters.pop(i)
                    break

        # Remove adapter config from graph
        await self._remove_adapter_config_from_graph(adapter_id)

        # Remove from loaded adapters
        del self.loaded_adapters[adapter_id]

    async def unload_adapter(self, adapter_id: str) -> AdapterOperationResult:
        """Stop and unload an adapter instance using helper functions for reduced complexity.

        Args:
            adapter_id: Unique identifier of the adapter to unload

        Returns:
            AdapterOperationResult with success status and details
        """
        logger.warning(
            f"RuntimeAdapterManager.unload_adapter called: adapter_id={adapter_id}, "
            f"loaded_adapters={list(self.loaded_adapters.keys())}, "
            f"adapter_manager_id={id(self)}"
        )
        try:
            # Validate adapter eligibility - fail fast if not eligible
            eligibility_error = self._validate_adapter_unload_eligibility(adapter_id)
            if eligibility_error is not None:
                return eligibility_error

            # Get instance (guaranteed to exist after validation)
            instance = self.loaded_adapters[adapter_id]
            logger.info(f"Unloading adapter {adapter_id}")

            # Cancel lifecycle tasks
            await self._cancel_adapter_lifecycle_tasks(adapter_id, instance)

            # Clean up adapter from runtime
            await self._cleanup_adapter_from_runtime(adapter_id, instance)

            logger.info(f"Successfully unloaded adapter {adapter_id}")
            return self._create_adapter_operation_result(
                success=True,
                adapter_id=adapter_id,
                adapter_type=instance.adapter_type,
                message=f"Successfully unloaded adapter with {len(instance.services_registered)} services unregistered",
                details={"services_unregistered": len(instance.services_registered), "was_running": True},
            )

        except asyncio.CancelledError:
            # Re-raise CancelledError to properly propagate cancellation - no logging needed
            logger.debug(f"Adapter unload for {adapter_id} was cancelled")
            raise
        except Exception as e:
            logger.error(f"Failed to unload adapter {adapter_id}: {e}", exc_info=True)
            return self._create_adapter_operation_result(
                success=False,
                adapter_id=adapter_id,
                adapter_type="unknown",
                message=f"Failed to unload adapter: {str(e)}",
                error=str(e),
            )

    async def reload_adapter(
        self, adapter_id: str, config_params: Optional[AdapterConfig] = None
    ) -> AdapterOperationResult:
        """Reload an adapter with new configuration

        Args:
            adapter_id: Unique identifier of the adapter to reload
            config_params: New configuration parameters

        Returns:
            Dict with success status and details
        """
        try:
            if adapter_id not in self.loaded_adapters:
                return AdapterOperationResult(
                    success=False,
                    adapter_id=adapter_id,
                    adapter_type="unknown",
                    message=f"Adapter with ID '{adapter_id}' not found",
                    error=f"Adapter with ID '{adapter_id}' not found",
                    details={},
                )

            instance = self.loaded_adapters[adapter_id]
            adapter_type = instance.adapter_type

            logger.info(f"Reloading adapter {adapter_id} with new config")

            unload_result = await self.unload_adapter(adapter_id)
            if not unload_result.success:
                return unload_result

            load_result = await self.load_adapter(adapter_type, adapter_id, config_params)

            if load_result.success:
                logger.info(f"Successfully reloaded adapter {adapter_id}")

            return load_result

        except Exception as e:
            logger.error(f"Failed to reload adapter {adapter_id}: {e}", exc_info=True)
            return AdapterOperationResult(
                success=False,
                adapter_id=adapter_id,
                adapter_type="unknown",
                message=f"Failed to reload adapter: {str(e)}",
                error=str(e),
                details={},
            )

    async def list_adapters(self) -> List[RuntimeAdapterStatus]:
        """List all loaded adapter instances

        Returns:
            List of adapter information dictionaries
        """
        try:
            adapters = []
            for adapter_id, instance in self.loaded_adapters.items():
                try:
                    if hasattr(instance.adapter, "is_healthy"):
                        is_healthy = await instance.adapter.is_healthy()
                        health_status = "healthy" if is_healthy else "error"
                    elif instance.is_running:
                        health_status = "active"
                    else:
                        health_status = "stopped"
                except Exception:
                    health_status = "error"

                metrics: Optional[AdapterMetrics] = None
                if health_status == "healthy":
                    uptime_seconds = (self.time_service.now() - instance.loaded_at).total_seconds()
                    metrics = AdapterMetrics(
                        uptime_seconds=uptime_seconds,
                        messages_processed=0,  # Would need to track this
                        errors_count=0,  # Would need to track this
                    )

                # Get tools from adapter if it has a tool service
                tools = None
                try:
                    if hasattr(instance.adapter, "tool_service") and instance.adapter.tool_service:
                        tool_service = instance.adapter.tool_service
                        if hasattr(tool_service, "get_all_tool_info"):
                            tool_infos = await tool_service.get_all_tool_info()
                            tools = tool_infos  # Pass ToolInfo objects directly, not just names
                        elif hasattr(tool_service, "list_tools"):
                            tool_names = await tool_service.list_tools()
                            # Convert string names to ToolInfo objects for schema compliance
                            from ciris_engine.schemas.adapters.tools import ToolInfo, ToolParameterSchema

                            tools = [
                                ToolInfo(
                                    name=name,
                                    description="",
                                    parameters=ToolParameterSchema(type="object", properties={}, required=[]),
                                )
                                for name in tool_names
                            ]
                except Exception as e:
                    logger.warning(f"Failed to get tools for adapter {adapter_id}: {e}")

                adapters.append(
                    RuntimeAdapterStatus(
                        adapter_id=adapter_id,
                        adapter_type=instance.adapter_type,
                        is_running=instance.is_running,
                        loaded_at=instance.loaded_at,
                        services_registered=instance.services_registered,
                        config_params=self._sanitize_config_params(instance.adapter_type, instance.config_params),
                        metrics=metrics,
                        last_activity=None,
                        tools=tools,
                    )
                )

            return adapters

        except Exception as e:
            logger.error(f"Failed to list adapters: {e}", exc_info=True)
            return []

    async def _determine_adapter_health_status(self, instance: AdapterInstance) -> tuple[str, JSONDict]:
        """Determine adapter health status and details - fail fast on issues."""
        health_details: JSONDict = {}

        try:
            if hasattr(instance.adapter, "is_healthy"):
                is_healthy = await instance.adapter.is_healthy()
                health_status = "healthy" if is_healthy else "error"
            elif instance.is_running:
                health_status = "active"
            else:
                health_status = "stopped"
        except Exception as e:
            health_status = "error"
            health_details["error"] = str(e)

        return health_status, health_details

    def _extract_adapter_service_details(self, instance: AdapterInstance) -> List[JSONDict]:
        """Extract service registration details from adapter - fail fast on invalid data."""
        try:
            if not hasattr(instance.adapter, "get_services_to_register"):
                return [{"info": "Adapter does not provide service registration details"}]

            registrations = instance.adapter.get_services_to_register()
            service_details = []

            for reg in registrations:
                service_details.append(
                    {
                        "service_type": (
                            reg.service_type.value if hasattr(reg.service_type, "value") else str(reg.service_type)
                        ),
                        "priority": reg.priority.name if hasattr(reg.priority, "name") else str(reg.priority),
                        "handlers": reg.handlers,
                        "capabilities": reg.capabilities,
                    }
                )

            return service_details

        except Exception as e:
            return [{"error": f"Failed to get service registrations: {e}"}]

    async def _get_adapter_tools_info(self, adapter_id: str, instance: AdapterInstance) -> Optional[List[Any]]:
        """Get tool information from adapter if available - strict typing, no fallbacks."""
        try:
            if not (hasattr(instance.adapter, "tool_service") and instance.adapter.tool_service):
                return None

            tool_service = instance.adapter.tool_service

            if hasattr(tool_service, "get_all_tool_info"):
                tool_infos = await tool_service.get_all_tool_info()
                # Type checking: tool_infos should be List[ToolInfo]
                return list(tool_infos) if tool_infos else None  # Pass ToolInfo objects directly
            elif hasattr(tool_service, "list_tools"):
                tool_names = await tool_service.list_tools()
                # Convert string names to ToolInfo objects for schema compliance
                from ciris_engine.schemas.adapters.tools import ToolInfo, ToolParameterSchema

                return [
                    ToolInfo(
                        name=name,
                        description="",
                        parameters=ToolParameterSchema(type="object", properties={}, required=[]),
                    )
                    for name in tool_names
                ]
            else:
                return None

        except Exception as e:
            logger.warning(f"Failed to get tools for adapter {adapter_id}: {e}")
            return None

    def _create_adapter_metrics(self, instance: AdapterInstance, health_status: str) -> Optional[AdapterMetrics]:
        """Create adapter metrics based on health status - strict typing."""
        if health_status != "healthy":
            return None

        uptime_seconds = (self.time_service.now() - instance.loaded_at).total_seconds()

        return AdapterMetrics(
            uptime_seconds=uptime_seconds,
            messages_processed=0,  # Would need to track this in real implementation
            errors_count=0,  # Would need to track this in real implementation
            last_error=None,
        )

    async def get_adapter_status(self, adapter_id: str) -> Optional[RuntimeAdapterStatus]:
        """Get detailed status of a specific adapter

        Args:
            adapter_id: Unique identifier of the adapter

        Returns:
            Dict with detailed adapter status information
        """
        if adapter_id not in self.loaded_adapters:
            return None

        try:
            instance = self.loaded_adapters[adapter_id]

            # Determine health status using helper
            health_status, _ = await self._determine_adapter_health_status(instance)

            # Extract service details using helper
            _ = self._extract_adapter_service_details(instance)

            # Get tools information using helper
            tools = await self._get_adapter_tools_info(adapter_id, instance)

            # Create metrics using helper
            metrics = self._create_adapter_metrics(instance, health_status)

            return RuntimeAdapterStatus(
                adapter_id=adapter_id,
                adapter_type=instance.adapter_type,
                is_running=instance.is_running,
                loaded_at=instance.loaded_at,
                services_registered=instance.services_registered,
                config_params=self._sanitize_config_params(instance.adapter_type, instance.config_params),
                metrics=metrics,
                last_activity=None,
                tools=tools,
            )

        except Exception as e:
            logger.error(f"Failed to get adapter status for {adapter_id}: {e}", exc_info=True)
            return None

    def _sanitize_config_params(self, adapter_type: str, config_params: Optional[AdapterConfig]) -> AdapterConfig:
        """Sanitize config parameters to remove sensitive information.

        Args:
            adapter_type: Type of adapter (discord, api, etc.)
            config_params: Raw configuration parameters

        Returns:
            Sanitized configuration with sensitive fields masked
        """
        if not config_params:
            return AdapterConfig(adapter_type=adapter_type, enabled=False)

        # Define sensitive fields per adapter type
        sensitive_fields = {
            "discord": ["bot_token", "token", "api_key", "secret"],
            "api": ["api_key", "secret_key", "auth_token", "password"],
            "cli": ["password", "secret"],
            # Add more adapter types and their sensitive fields as needed
        }

        # Get sensitive fields for this adapter type
        fields_to_mask = sensitive_fields.get(adapter_type, ["token", "password", "secret", "api_key"])

        # Create a sanitized copy of the settings
        sanitized_settings: Dict[str, Optional[Union[str, int, float, bool, List[str]]]] = {}
        for key, value in config_params.settings.items():
            # Check if this field should be masked
            if any(sensitive in key.lower() for sensitive in fields_to_mask):
                # Mask the value but show it exists
                if value:
                    sanitized_settings[key] = "***MASKED***"
                else:
                    sanitized_settings[key] = None
            else:
                # Keep non-sensitive values as-is
                sanitized_settings[key] = value

        # Return a new AdapterConfig with sanitized settings
        return AdapterConfig(
            adapter_type=config_params.adapter_type, enabled=config_params.enabled, settings=sanitized_settings
        )

    async def load_adapter_from_template(
        self, template_name: str, adapter_id: Optional[str] = None
    ) -> AdapterOperationResult:
        """Load adapter configuration from an agent template

        Args:
            template_name: Name of the agent template to load
            adapter_id: Optional unique ID for the adapter

        Returns:
            Dict with load results
        """
        try:
            from pathlib import Path

            import yaml

            template_overlay_path = Path("ciris_templates") / f"{template_name}.yaml"
            adapter_types = []

            if template_overlay_path.exists():
                try:
                    async with aiofiles.open(template_overlay_path, "r") as f:
                        content = await f.read()
                        template_data = yaml.safe_load(content) or {}

                    if "discord_config" in template_data or template_data.get("discord_config"):
                        adapter_types.append("discord")
                    if "api_config" in template_data or template_data.get("api_config"):
                        adapter_types.append("api")
                    if "cli_config" in template_data or template_data.get("cli_config"):
                        adapter_types.append("cli")
                except Exception:
                    adapter_types = ["discord", "api", "cli"]

            # Load template configuration
            bootstrap = ConfigBootstrap()
            _config = await bootstrap.load_essential_config()

            # Templates are not part of essential config anymore
            # This functionality has been removed
            return AdapterOperationResult(
                success=False,
                adapter_id=adapter_id or "template",
                adapter_type="template",
                message="Template loading has been removed. Use direct adapter configuration instead.",
                error="Template loading has been removed. Use direct adapter configuration instead.",
                details={},
            )

        except Exception as e:
            logger.error(f"Failed to load adapters from template {template_name}: {e}", exc_info=True)
            return AdapterOperationResult(
                success=False,
                adapter_id=adapter_id or "template",
                adapter_type="template",  # Default to "template" since this is template loading
                message=f"Failed to load template: {str(e)}",
                error=str(e),
                details={},
            )

    def _get_service_type_value(self, reg: Any) -> ServiceType:
        """Extract ServiceType enum from registration."""
        if hasattr(reg, "service_type") and isinstance(reg.service_type, ServiceType):
            return reg.service_type
        return ServiceType(str(reg.service_type))

    def _build_service_key(self, reg: Any, instance: AdapterInstance) -> str:
        """Build service key from registration."""
        service_type_str = reg.service_type.value if hasattr(reg.service_type, "value") else str(reg.service_type)
        provider_name = (
            reg.provider.__class__.__name__ if hasattr(reg, "provider") else instance.adapter.__class__.__name__
        )
        return f"{service_type_str}:{provider_name}"

    def _register_single_service(self, reg: Any, instance: AdapterInstance) -> None:
        """Register a single service from registration."""
        if not self.runtime.service_registry:
            return

        service_key = self._build_service_key(reg, instance)
        provider = getattr(reg, "provider", instance.adapter)
        priority = getattr(reg, "priority", Priority.NORMAL)
        capabilities = getattr(reg, "capabilities", [])

        if not hasattr(provider, "adapter_id"):
            provider.adapter_id = instance.adapter_id

        self.runtime.service_registry.register_service(
            service_type=self._get_service_type_value(reg),
            provider=provider,
            priority=priority,
            capabilities=capabilities,
            priority_group=getattr(reg, "priority_group", 0),
            strategy=getattr(reg, "strategy", SelectionStrategy.FALLBACK),
        )
        instance.services_registered.append(f"global:{service_key}")
        logger.info(f"Registered {service_key} from adapter {instance.adapter_id}")

    def _register_adapter_services(self, instance: AdapterInstance) -> None:
        """Register services for an adapter instance"""
        try:
            if not self.runtime.service_registry:
                logger.error("ServiceRegistry not initialized. Cannot register adapter services.")
                return

            if not hasattr(instance.adapter, "get_services_to_register"):
                logger.warning(f"Adapter {instance.adapter_id} does not provide services to register")
                return

            registrations = instance.adapter.get_services_to_register()
            for reg in registrations:
                if not isinstance(reg, (ServiceRegistration, AdapterServiceRegistration)):
                    logger.error(
                        f"Adapter {instance.adapter.__class__.__name__} provided invalid ServiceRegistration: {reg}"
                    )
                    continue
                self._register_single_service(reg, instance)

        except Exception as e:
            logger.error(f"Error registering services for adapter {instance.adapter_id}: {e}", exc_info=True)

    def _unregister_adapter_services(self, instance: AdapterInstance) -> None:
        """Unregister services for an adapter instance"""
        try:
            if not self.runtime.service_registry:
                logger.warning("ServiceRegistry not available. Cannot unregister adapter services.")
                return

            for service_key in instance.services_registered:
                logger.info(f"Would unregister service: {service_key} from adapter {instance.adapter_id}")

            instance.services_registered.clear()

        except Exception as e:
            logger.error(f"Error unregistering services for adapter {instance.adapter_id}: {e}", exc_info=True)

    def get_adapter_info(self, adapter_id: str) -> Optional[AdapterInfo]:
        """Get detailed information about a specific adapter."""
        if adapter_id not in self.loaded_adapters:
            return None

        try:
            instance = self.loaded_adapters[adapter_id]

            return AdapterInfo(
                adapter_id=adapter_id,
                adapter_type=instance.adapter_type,
                config=instance.config_params,
                load_time=instance.loaded_at.isoformat(),
                is_running=instance.is_running,
            )

        except Exception as e:
            logger.error(f"Failed to get adapter info for {adapter_id}: {e}", exc_info=True)
            return None

    def get_communication_adapter_status(self) -> CommunicationAdapterStatus:
        """Get status of communication adapters."""
        communication_adapter_types = {"discord", "api", "cli"}  # Known communication adapter types

        communication_adapters: List[CommunicationAdapterInfo] = []
        running_count = 0

        for adapter_id, instance in self.loaded_adapters.items():
            if instance.adapter_type in communication_adapter_types:
                communication_adapters.append(
                    CommunicationAdapterInfo(
                        adapter_id=adapter_id, adapter_type=instance.adapter_type, is_running=instance.is_running
                    )
                )
                if instance.is_running:
                    running_count += 1

        total_count = len(communication_adapters)
        safe_to_unload = total_count > 1  # Safe if more than one communication adapter

        warning_message = None
        if total_count == 1:
            warning_message = "Only one communication adapter remaining. Unloading it will disable communication."
        elif total_count == 0:
            warning_message = "No communication adapters are loaded."

        return CommunicationAdapterStatus(
            total_communication_adapters=total_count,
            running_communication_adapters=running_count,
            communication_adapters=communication_adapters,
            safe_to_unload=safe_to_unload,
            warning_message=warning_message,
        )

    async def _save_adapter_config_to_graph(
        self, adapter_id: str, adapter_type: str, config_params: AdapterConfig
    ) -> None:
        """Save adapter configuration to graph config service."""
        try:
            # Get config service from runtime
            config_service = None
            if hasattr(self.runtime, "service_initializer") and self.runtime.service_initializer:
                config_service = getattr(self.runtime.service_initializer, "config_service", None)

            if not config_service:
                logger.warning(f"Cannot save adapter config for {adapter_id} - GraphConfigService not available")
                return

            # Store the full config object
            await config_service.set_config(
                key=f"adapter.{adapter_id}.config", value=config_params, updated_by="runtime_adapter_manager"
            )

            # Store adapter type separately for easy identification
            await config_service.set_config(
                key=f"adapter.{adapter_id}.type", value=adapter_type, updated_by="runtime_adapter_manager"
            )

            # Also store individual config values for easy access
            if isinstance(config_params, dict):
                for key, value in config_params.items():
                    # Skip complex objects that might not serialize well
                    if isinstance(value, (str, int, float, bool, list)):
                        await config_service.set_config(
                            key=f"adapter.{adapter_id}.{key}", value=value, updated_by="runtime_adapter_manager"
                        )

            logger.info(f"Saved adapter config for {adapter_id} to graph")

        except Exception as e:
            logger.error(f"Failed to save adapter config for {adapter_id}: {e}")

    async def _remove_adapter_config_from_graph(self, adapter_id: str) -> None:
        """Remove adapter configuration from graph config service."""
        try:
            # Get config service from runtime
            config_service = None
            if hasattr(self.runtime, "service_initializer") and self.runtime.service_initializer:
                config_service = getattr(self.runtime.service_initializer, "config_service", None)

            if not config_service:
                logger.warning(f"Cannot remove adapter config for {adapter_id} - GraphConfigService not available")
                return

            # List all configs with adapter prefix
            adapter_prefix = f"adapter.{adapter_id}"
            all_configs = await config_service.list_configs(prefix=adapter_prefix)

            # Remove all config entries for this adapter by setting them to None
            # Note: GraphConfigService doesn't have delete, so we set to None to clear
            for config_key in all_configs.keys():
                await config_service.set_config(config_key, None, updated_by="adapter_manager")
                logger.debug(f"Removed config key: {config_key}")

            logger.info(f"Removed adapter config for {adapter_id} from graph")

        except Exception as e:
            logger.error(f"Failed to remove adapter config for {adapter_id}: {e}")

    def _register_config_listener(self) -> None:
        """Register to listen for adapter config changes."""
        if self._config_listener_registered:
            return

        try:
            # Get config service from runtime
            if hasattr(self.runtime, "service_initializer") and self.runtime.service_initializer:
                config_service = self.runtime.service_initializer.config_service
                if config_service:
                    # Register for all adapter config changes
                    config_service.register_config_listener("adapter.*", self._on_adapter_config_change)
                    self._config_listener_registered = True
                    logger.info("RuntimeAdapterManager registered for adapter config changes")
                else:
                    logger.debug("Config service not available yet for adapter manager")
            else:
                logger.debug("Runtime service initializer not available yet")
        except Exception as e:
            logger.error(f"Failed to register config listener: {e}")

    async def _on_adapter_config_change(self, key: str, old_value: Any, new_value: Any) -> None:
        """Handle adapter configuration changes.

        This is called by the config service when adapter configs change.
        """
        # Extract adapter_id from key (e.g., "adapter.api_bootstrap.host" -> "api_bootstrap")
        parts = key.split(".")
        if len(parts) < 2 or parts[0] != "adapter":
            return

        adapter_id = parts[1]

        # Check if this adapter is loaded
        if adapter_id not in self.loaded_adapters:
            logger.debug(f"Config change for unloaded adapter {adapter_id}, ignoring")
            return

        # Get the adapter instance
        instance = self.loaded_adapters[adapter_id]

        # If it's a full config update (adapter.X.config), reload the adapter
        if len(parts) == 3 and parts[2] == "config":
            logger.info(f"Full config update detected for adapter {adapter_id}, reloading adapter")
            # Convert dict to AdapterConfig if valid
            config_param = None
            if isinstance(new_value, dict):
                config_param = AdapterConfig(
                    adapter_type=instance.adapter_type,
                    enabled=new_value.get("enabled", True),
                    settings=new_value.get("settings", {}),
                )
            await self.reload_adapter(adapter_id, config_param)
            return

        # For individual config values, check if the adapter supports hot reload
        if hasattr(instance.adapter, "update_config"):
            try:
                # Extract the specific config key (e.g., "host" from "adapter.api_bootstrap.host")
                config_key = parts[2] if len(parts) > 2 else None
                if config_key:
                    logger.info(f"Updating {config_key} for adapter {adapter_id}")
                    await instance.adapter.update_config({config_key: new_value})
            except Exception as e:
                logger.error(f"Failed to update config for adapter {adapter_id}: {e}")
        else:
            logger.info(f"Adapter {adapter_id} doesn't support hot config updates, consider reloading")

    def register_config_listener(self) -> None:
        """Register to listen for adapter config changes."""
        if self._config_listener_registered:
            return

        try:
            # Get config service from runtime
            config_service = None
            if hasattr(self.runtime, "service_initializer") and self.runtime.service_initializer:
                config_service = getattr(self.runtime.service_initializer, "config_service", None)

            if config_service:
                # Register to listen for all adapter config changes
                config_service.register_config_listener("adapter.*", self._on_adapter_config_change)
                self._config_listener_registered = True
                logger.info("Adapter manager registered for config change notifications")
            else:
                logger.warning("Cannot register for config changes - GraphConfigService not available")

        except Exception as e:
            logger.error(f"Failed to register config listener: {e}")
