"""
Runtime Adapter Management

Provides dynamic adapter loading/unloading capabilities during runtime,
extending the existing processor control capabilities with adapter lifecycle management.
"""

import asyncio
import logging
from typing import Dict, List, Optional, TYPE_CHECKING, cast, Any, Union
import aiofiles

if TYPE_CHECKING:
    from ciris_engine.logic.runtime.ciris_runtime import CIRISRuntime
from dataclasses import dataclass, field
from datetime import datetime

from ciris_engine.logic.adapters.base import Service
from ciris_engine.schemas.infrastructure.base import ServiceRegistration
from ciris_engine.schemas.adapters.registration import AdapterServiceRegistration
from ciris_engine.schemas.runtime.enums import ServiceType
from ciris_engine.logic.adapters import load_adapter
from ciris_engine.protocols.runtime.base import BaseAdapterProtocol
from ciris_engine.logic.config import ConfigBootstrap
from ciris_engine.protocols.services.lifecycle.time import TimeServiceProtocol
from ciris_engine.schemas.runtime.adapter_management import (
    AdapterConfig, AdapterOperationResult, AdapterStatus,
    AdapterMetrics
)
from ciris_engine.logic.registries.base import Priority, SelectionStrategy

logger = logging.getLogger(__name__)

@dataclass
class AdapterInstance:
    """Information about a loaded adapter instance"""
    adapter_id: str
    adapter_type: str
    adapter: Any  # Actually Service but also needs BaseAdapterProtocol methods
    config_params: dict  # Adapter-specific settings
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

    async def load_adapter(self, adapter_type: str, adapter_id: str, config_params: Optional[dict] = None) -> AdapterOperationResult:
        """Load and start a new adapter instance"""
        raise NotImplementedError("This is an interface method")

    async def unload_adapter(self, adapter_id: str) -> AdapterOperationResult:
        """Stop and unload an adapter instance"""
        raise NotImplementedError("This is an interface method")

    async def reload_adapter(self, adapter_id: str, config_params: Optional[dict] = None) -> AdapterOperationResult:
        """Reload an adapter with new configuration"""
        raise NotImplementedError("This is an interface method")

    async def list_adapters(self) -> List[AdapterStatus]:
        """List all loaded adapter instances"""
        raise NotImplementedError("This is an interface method")

    async def get_adapter_status(self, adapter_id: str) -> Optional[AdapterStatus]:
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

    async def load_adapter(self, adapter_type: str, adapter_id: str, config_params: Optional[dict] = None) -> AdapterOperationResult:
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
                    details={}
                )

            logger.info(f"Loading adapter: type={adapter_type}, id={adapter_id}, params={config_params}")

            adapter_class = load_adapter(adapter_type)

            adapter_kwargs = config_params or {}
            # Adapters expect runtime as first argument, then kwargs
            adapter = adapter_class(self.runtime, **adapter_kwargs)  # type: ignore[call-arg]

            instance = AdapterInstance(
                adapter_id=adapter_id,
                adapter_type=adapter_type,
                adapter=adapter,
                config_params=adapter_kwargs,
                loaded_at=self.time_service.now()
            )

            await adapter.start()
            
            # For Discord adapters, we need to run the lifecycle to establish connection
            if adapter_type == "discord" and hasattr(adapter, 'run_lifecycle'):
                logger.info(f"Starting lifecycle for Discord adapter {adapter_id}")
                # Create a task that the Discord adapter will wait on
                # This mimics the behavior when running from main.py
                agent_task = asyncio.create_task(asyncio.Event().wait())
                instance.lifecycle_task = agent_task
                
                # Store the lifecycle runner task
                instance.lifecycle_runner = asyncio.create_task(
                    adapter.run_lifecycle(agent_task),
                    name=f"discord_lifecycle_{adapter_id}"
                )
                
                # Don't wait here - let it run in the background
                logger.info(f"Discord adapter {adapter_id} lifecycle started in background")
            
            instance.is_running = True

            self._register_adapter_services(instance)
            
            # Save adapter config to graph
            await self._save_adapter_config_to_graph(adapter_id, adapter_type, adapter_kwargs)

            # Don't add dynamically loaded adapters to runtime.adapters
            # to avoid duplicate bootstrap entries in control_service
            # self.runtime.adapters.append(adapter)
            self.loaded_adapters[adapter_id] = instance

            logger.info(f"Successfully loaded and started adapter {adapter_id}")
            return AdapterOperationResult(
                success=True,
                adapter_id=adapter_id,
                adapter_type=adapter_type,
                message=f"Successfully loaded adapter with {len(instance.services_registered)} services",
                error=None,
                details={"loaded_at": instance.loaded_at.isoformat(), "services": len(instance.services_registered)}
            )

        except Exception as e:
            logger.error(f"Failed to load adapter {adapter_type} with ID {adapter_id}: {e}", exc_info=True)
            return AdapterOperationResult(
                success=False,
                adapter_id=adapter_id,
                adapter_type=adapter_type,
                message=f"Failed to load adapter: {str(e)}",
                error=str(e),
                details={}
            )

    async def unload_adapter(self, adapter_id: str) -> AdapterOperationResult:
        """Stop and unload an adapter instance

        Args:
            adapter_id: Unique identifier of the adapter to unload

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
                    details={}
                )

            instance = self.loaded_adapters[adapter_id]

            communication_adapter_types = {"discord", "api", "cli"}
            if instance.adapter_type in communication_adapter_types:
                remaining_comm_adapters = sum(
                    1 for aid, inst in self.loaded_adapters.items()
                    if aid != adapter_id and inst.adapter_type in communication_adapter_types
                )

                if remaining_comm_adapters == 0:
                    return AdapterOperationResult(
                        success=False,
                        adapter_id=adapter_id,
                        adapter_type=instance.adapter_type,
                        message=f"Cannot unload {adapter_id}: it is one of the last communication-capable adapters",
                        error=f"Cannot unload {adapter_id}: it is one of the last communication-capable adapters",
                        details={}
                    )

            logger.info(f"Unloading adapter {adapter_id}")

            # Cancel lifecycle tasks for Discord adapters
            if hasattr(instance, 'lifecycle_runner') and instance.lifecycle_runner is not None:
                logger.debug(f"Cancelling lifecycle runner for {adapter_id}")
                instance.lifecycle_runner.cancel()
                try:
                    await instance.lifecycle_runner
                except asyncio.CancelledError:
                    # This is expected when we cancel the task
                    pass  # NOSONAR - Intentionally not re-raising in unload_adapter()
            
            if hasattr(instance, 'lifecycle_task') and instance.lifecycle_task is not None:
                logger.debug(f"Cancelling lifecycle task for {adapter_id}")
                instance.lifecycle_task.cancel()
                try:
                    await instance.lifecycle_task
                except asyncio.CancelledError:
                    # This is expected when we cancel the task
                    pass  # NOSONAR - Intentionally not re-raising in unload_adapter()

            if instance.is_running:
                await instance.adapter.stop()
                instance.is_running = False

            self._unregister_adapter_services(instance)

            # Remove adapter from runtime adapters list (if it was added there)
            # Note: Dynamically loaded adapters are no longer added to runtime.adapters
            # to avoid duplicate bootstrap entries
            if hasattr(self.runtime, 'adapters'):
                for i, adapter in enumerate(self.runtime.adapters):
                    if adapter is instance.adapter:
                        self.runtime.adapters.pop(i)
                        break

            # Remove adapter config from graph
            await self._remove_adapter_config_from_graph(adapter_id)
            
            del self.loaded_adapters[adapter_id]

            logger.info(f"Successfully unloaded adapter {adapter_id}")
            return AdapterOperationResult(
                success=True,
                adapter_id=adapter_id,
                adapter_type=instance.adapter_type,
                message=f"Successfully unloaded adapter with {len(instance.services_registered)} services unregistered",
                error=None,
                details={"services_unregistered": len(instance.services_registered), "was_running": True}
            )

        except asyncio.CancelledError:
            # Re-raise CancelledError to properly propagate cancellation
            logger.debug(f"Adapter unload for {adapter_id} was cancelled")
            raise
        except Exception as e:
            logger.error(f"Failed to unload adapter {adapter_id}: {e}", exc_info=True)
            return AdapterOperationResult(
                success=False,
                adapter_id=adapter_id,
                adapter_type="unknown",
                message=f"Failed to unload adapter: {str(e)}",
                error=str(e),
                details={}
            )

    async def reload_adapter(self, adapter_id: str, config_params: Optional[dict] = None) -> AdapterOperationResult:
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
                    details={}
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
                details={}
            )

    async def list_adapters(self) -> List[AdapterStatus]:
        """List all loaded adapter instances

        Returns:
            List of adapter information dictionaries
        """
        try:
            adapters = []
            for adapter_id, instance in self.loaded_adapters.items():
                health_status = "unknown"
                try:
                    if hasattr(instance.adapter, 'is_healthy'):
                        is_healthy = await instance.adapter.is_healthy()
                        health_status = "healthy" if is_healthy else "error"
                    elif instance.is_running:
                        health_status = "active"
                    else:
                        health_status = "stopped"
                except Exception:
                    health_status = "error"

                metrics_dict: Optional[dict] = None
                if health_status == "healthy":
                    uptime_seconds = (self.time_service.now() - instance.loaded_at).total_seconds()
                    metrics_dict = {
                        "uptime_seconds": uptime_seconds,
                        "health_status": health_status
                    }

                # Get tools from adapter if it has a tool service
                tools = None
                try:
                    if hasattr(instance.adapter, 'tool_service') and instance.adapter.tool_service:
                        tool_service = instance.adapter.tool_service
                        if hasattr(tool_service, 'get_all_tool_info'):
                            tool_infos = await tool_service.get_all_tool_info()
                            tools = [
                                {
                                    "name": info.name,
                                    "description": info.description,
                                    "schema": info.parameters.model_dump() if info.parameters else {}
                                }
                                for info in tool_infos
                            ]
                        elif hasattr(tool_service, 'list_tools'):
                            tool_names = await tool_service.list_tools()
                            tools = [{"name": name, "description": f"{name} tool", "schema": {}} for name in tool_names]
                except Exception as e:
                    logger.warning(f"Failed to get tools for adapter {adapter_id}: {e}")

                adapters.append(AdapterStatus(
                    adapter_id=adapter_id,
                    adapter_type=instance.adapter_type,
                    is_running=instance.is_running,
                    loaded_at=instance.loaded_at,
                    services_registered=instance.services_registered,
                    config_params=AdapterConfig(
                        adapter_type=instance.adapter_type,
                        enabled=instance.is_running,
                        settings=self._sanitize_config_params(instance.adapter_type, instance.config_params)
                    ),
                    metrics=metrics_dict,
                    last_activity=None,
                    tools=tools
                ))

            return adapters

        except Exception as e:
            logger.error(f"Failed to list adapters: {e}", exc_info=True)
            return []

    async def get_adapter_status(self, adapter_id: str) -> Optional[AdapterStatus]:
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

            health_status = "unknown"
            health_details = {}
            try:
                if hasattr(instance.adapter, 'is_healthy'):
                    is_healthy = await instance.adapter.is_healthy()
                    health_status = "healthy" if is_healthy else "error"
                elif instance.is_running:
                    health_status = "active"
                else:
                    health_status = "stopped"
            except Exception as e:
                health_status = "error"
                health_details["error"] = str(e)

            service_details = []
            try:
                if hasattr(instance.adapter, 'get_services_to_register'):
                    registrations = instance.adapter.get_services_to_register()
                    for reg in registrations:
                        service_details.append({
                            "service_type": reg.service_type.value if hasattr(reg.service_type, 'value') else str(reg.service_type),
                            "priority": reg.priority.name if hasattr(reg.priority, 'name') else str(reg.priority),
                            "handlers": reg.handlers,
                            "capabilities": reg.capabilities
                        })
                else:
                    service_details = [{"info": "Adapter does not provide service registration details"}]
            except Exception as e:
                service_details = [{"error": f"Failed to get service registrations: {e}"}]

            uptime_seconds = (self.time_service.now() - instance.loaded_at).total_seconds()

            metrics_dict: Optional[dict] = None
            if health_status == "healthy":
                metrics_dict = {
                    "uptime_seconds": uptime_seconds,
                    "health_status": health_status,
                    "service_details": service_details
                }

            # Get tools from adapter if it has a tool service
            tools = None
            try:
                if hasattr(instance.adapter, 'tool_service') and instance.adapter.tool_service:
                    tool_service = instance.adapter.tool_service
                    if hasattr(tool_service, 'get_all_tool_info'):
                        tool_infos = await tool_service.get_all_tool_info()
                        tools = [
                            {
                                "name": info.name,
                                "description": info.description,
                                "schema": info.parameters.model_dump() if info.parameters else {}
                            }
                            for info in tool_infos
                        ]
                    elif hasattr(tool_service, 'list_tools'):
                        tool_names = await tool_service.list_tools()
                        tools = [{"name": name, "description": f"{name} tool", "schema": {}} for name in tool_names]
            except Exception as e:
                logger.warning(f"Failed to get tools for adapter {adapter_id}: {e}")

            return AdapterStatus(
                adapter_id=adapter_id,
                adapter_type=instance.adapter_type,
                is_running=instance.is_running,
                loaded_at=instance.loaded_at,
                services_registered=instance.services_registered,
                config_params=AdapterConfig(
                    adapter_type=instance.adapter_type,
                    enabled=instance.is_running,
                    settings=self._sanitize_config_params(instance.adapter_type, instance.config_params)
                ),
                metrics=metrics_dict,
                last_activity=None,
                tools=tools
            )

        except Exception as e:
            logger.error(f"Failed to get adapter status for {adapter_id}: {e}", exc_info=True)
            return None
    
    def _sanitize_config_params(self, adapter_type: str, config_params: dict) -> dict:
        """Sanitize config parameters to remove sensitive information.
        
        Args:
            adapter_type: Type of adapter (discord, api, etc.)
            config_params: Raw configuration parameters
            
        Returns:
            Sanitized configuration with sensitive fields masked
        """
        if not config_params:
            return {}
            
        # Define sensitive fields per adapter type
        sensitive_fields = {
            'discord': ['bot_token', 'token', 'api_key', 'secret'],
            'api': ['api_key', 'secret_key', 'auth_token', 'password'],
            'cli': ['password', 'secret'],
            # Add more adapter types and their sensitive fields as needed
        }
        
        # Get sensitive fields for this adapter type
        fields_to_mask = sensitive_fields.get(adapter_type, ['token', 'password', 'secret', 'api_key'])
        
        # Create a copy of the config to avoid modifying the original
        sanitized = {}
        for key, value in config_params.items():
            # Check if this field should be masked
            if any(sensitive in key.lower() for sensitive in fields_to_mask):
                # Mask the value but show it exists
                if value:
                    sanitized[key] = "***MASKED***"
                else:
                    sanitized[key] = None  # type: ignore[assignment]
            elif isinstance(value, dict):
                # Recursively sanitize nested dictionaries
                sanitized[key] = self._sanitize_config_params(adapter_type, value)  # type: ignore[assignment]
            else:
                # Keep non-sensitive values as-is
                sanitized[key] = value
                
        return sanitized

    async def load_adapter_from_template(self, template_name: str, adapter_id: Optional[str] = None) -> AdapterOperationResult:
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
                    async with aiofiles.open(template_overlay_path, 'r') as f:
                        content = await f.read()
                        template_data = yaml.safe_load(content) or {}

                    if 'discord_config' in template_data or template_data.get('discord_config'):
                        adapter_types.append('discord')
                    if 'api_config' in template_data or template_data.get('api_config'):
                        adapter_types.append('api')
                    if 'cli_config' in template_data or template_data.get('cli_config'):
                        adapter_types.append('cli')
                except Exception:
                    adapter_types = ['discord', 'api', 'cli']

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
                details={}
            )

        except Exception as e:
            logger.error(f"Failed to load adapters from template {template_name}: {e}", exc_info=True)
            return AdapterOperationResult(
                success=False,
                adapter_id=adapter_id or "template",
                adapter_type="template",  # Default to "template" since this is template loading
                message=f"Failed to load template: {str(e)}",
                error=str(e),
                details={}
            )

    def _register_adapter_services(self, instance: AdapterInstance) -> None:
        """Register services for an adapter instance"""
        try:
            if not self.runtime.service_registry:
                logger.error("ServiceRegistry not initialized. Cannot register adapter services.")
                return

            if not hasattr(instance.adapter, 'get_services_to_register'):
                logger.warning(f"Adapter {instance.adapter_id} does not provide services to register")
                return

            registrations = instance.adapter.get_services_to_register()
            for reg in registrations:
                if not isinstance(reg, (ServiceRegistration, AdapterServiceRegistration)):
                    logger.error(f"Adapter {instance.adapter.__class__.__name__} provided invalid ServiceRegistration: {reg}")
                    continue

                # Handle both ServiceType enum and string
                service_type_str = reg.service_type.value if hasattr(reg.service_type, 'value') else str(reg.service_type)
                provider_name = reg.provider.__class__.__name__ if hasattr(reg, 'provider') else instance.adapter.__class__.__name__
                service_key = f"{service_type_str}:{provider_name}"

                # All services are global now
                # AdapterServiceRegistration doesn't have priority_group or strategy
                # Get provider from reg if available, otherwise use adapter itself
                provider = getattr(reg, 'provider', instance.adapter)
                priority = getattr(reg, 'priority', Priority.NORMAL)
                capabilities = getattr(reg, 'capabilities', [])
                
                # Handle both string and enum service_type
                # AdapterServiceRegistration has ServiceType enum, ServiceRegistration has string
                service_type_val: ServiceType
                if hasattr(reg, 'service_type') and isinstance(reg.service_type, ServiceType):
                    service_type_val = reg.service_type
                else:
                    # Must be a string from ServiceRegistration
                    service_type_val = ServiceType(str(reg.service_type))
                
                self.runtime.service_registry.register_service(
                    service_type=service_type_val,  # Ensure it's a ServiceType enum
                    provider=provider,
                    priority=priority,
                    capabilities=capabilities,
                    priority_group=getattr(reg, 'priority_group', 0),  # Default to 0
                    strategy=getattr(reg, 'strategy', SelectionStrategy.FALLBACK)  # Default strategy
                )
                instance.services_registered.append(f"global:{service_key}")

                logger.info(f"Registered {service_key} from adapter {instance.adapter_id}")

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

    def get_adapter_info(self, adapter_id: str) -> dict:
        """Get detailed information about a specific adapter."""
        if adapter_id not in self.loaded_adapters:
            return {}

        try:
            instance = self.loaded_adapters[adapter_id]

            return {
                "adapter_id": adapter_id,
                "adapter_type": instance.adapter_type,
                "config": instance.config_params,
                "load_time": instance.loaded_at.isoformat(),
                "is_running": instance.is_running
            }

        except Exception as e:
            logger.error(f"Failed to get adapter info for {adapter_id}: {e}", exc_info=True)
            return {}

    def get_communication_adapter_status(self) -> dict:
        """Get status of communication adapters."""
        communication_adapter_types = {"discord", "api", "cli"}  # Known communication adapter types

        communication_adapters = []
        running_count = 0

        for adapter_id, instance in self.loaded_adapters.items():
            if instance.adapter_type in communication_adapter_types:
                communication_adapters.append({
                    "adapter_id": adapter_id,
                    "adapter_type": instance.adapter_type,
                    "is_running": instance.is_running
                })
                if instance.is_running:
                    running_count += 1

        total_count = len(communication_adapters)
        safe_to_unload = total_count > 1  # Safe if more than one communication adapter

        warning_message = None
        if total_count == 1:
            warning_message = "Only one communication adapter remaining. Unloading it will disable communication."
        elif total_count == 0:
            warning_message = "No communication adapters are loaded."

        return {
            "total_communication_adapters": total_count,
            "running_communication_adapters": running_count,
            "communication_adapters": communication_adapters,
            "safe_to_unload": safe_to_unload,
            "warning_message": warning_message
        }
    
    async def _save_adapter_config_to_graph(self, adapter_id: str, adapter_type: str, config_params: dict) -> None:
        """Save adapter configuration to graph config service."""
        try:
            # Get config service from runtime
            config_service = None
            if hasattr(self.runtime, 'service_initializer') and self.runtime.service_initializer:
                config_service = getattr(self.runtime.service_initializer, 'config_service', None)
            
            if not config_service:
                logger.warning(f"Cannot save adapter config for {adapter_id} - GraphConfigService not available")
                return
            
            # Store the full config object
            await config_service.set_config(
                key=f"adapter.{adapter_id}.config",
                value=config_params,
                updated_by="runtime_adapter_manager"
            )
            
            # Store adapter type separately for easy identification
            await config_service.set_config(
                key=f"adapter.{adapter_id}.type",
                value=adapter_type,
                updated_by="runtime_adapter_manager"
            )
            
            # Also store individual config values for easy access
            if isinstance(config_params, dict):
                for key, value in config_params.items():
                    # Skip complex objects that might not serialize well
                    if isinstance(value, (str, int, float, bool, list)):
                        await config_service.set_config(
                            key=f"adapter.{adapter_id}.{key}",
                            value=value,
                            updated_by="runtime_adapter_manager"
                        )
            
            logger.info(f"Saved adapter config for {adapter_id} to graph")
            
        except Exception as e:
            logger.error(f"Failed to save adapter config for {adapter_id}: {e}")
    
    async def _remove_adapter_config_from_graph(self, adapter_id: str) -> None:
        """Remove adapter configuration from graph config service."""
        try:
            # Get config service from runtime
            config_service = None
            if hasattr(self.runtime, 'service_initializer') and self.runtime.service_initializer:
                config_service = getattr(self.runtime.service_initializer, 'config_service', None)
            
            if not config_service:
                logger.warning(f"Cannot remove adapter config for {adapter_id} - GraphConfigService not available")
                return
            
            # Get all config keys for this adapter
            all_configs = await config_service.get_all()
            adapter_prefix = f"adapter.{adapter_id}."
            
            # Remove all config entries for this adapter
            for config in all_configs:
                if config.key.startswith(adapter_prefix) or config.key == f"adapter.{adapter_id}.config":
                    await config_service.delete(config.key)
                    logger.debug(f"Removed config key: {config.key}")
            
            logger.info(f"Removed adapter config for {adapter_id} from graph")
            
        except Exception as e:
            logger.error(f"Failed to remove adapter config for {adapter_id}: {e}")
    
    def _register_config_listener(self) -> None:
        """Register to listen for adapter config changes."""
        if self._config_listener_registered:
            return
            
        try:
            # Get config service from runtime
            if hasattr(self.runtime, 'service_initializer') and self.runtime.service_initializer:
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
            await self.reload_adapter(adapter_id, new_value if isinstance(new_value, dict) else None)
            return
            
        # For individual config values, check if the adapter supports hot reload
        if hasattr(instance.adapter, 'update_config'):
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
            if hasattr(self.runtime, 'service_initializer') and self.runtime.service_initializer:
                config_service = getattr(self.runtime.service_initializer, 'config_service', None)
            
            if config_service:
                # Register to listen for all adapter config changes
                config_service.register_config_listener("adapter.*", self._on_adapter_config_change)
                self._config_listener_registered = True
                logger.info("Adapter manager registered for config change notifications")
            else:
                logger.warning("Cannot register for config changes - GraphConfigService not available")
                
        except Exception as e:
            logger.error(f"Failed to register config listener: {e}")
