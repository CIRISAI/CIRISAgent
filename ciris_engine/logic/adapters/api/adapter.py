"""
API adapter for CIRIS v1.

Provides RESTful API and WebSocket interfaces to the CIRIS agent.
"""

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, List, Optional

import uvicorn
from fastapi import FastAPI
from uvicorn import Server

from ciris_engine.logic import persistence
from ciris_engine.logic.adapters.base import Service
from ciris_engine.logic.persistence.models.correlations import get_active_channels_by_adapter, is_admin_channel
from ciris_engine.logic.registries.base import Priority
from ciris_engine.logic.services.runtime.adapter_configuration import AdapterConfigurationService
from ciris_engine.schemas.adapters import AdapterServiceRegistration
from ciris_engine.schemas.runtime.enums import ServiceType
from ciris_engine.schemas.runtime.messages import IncomingMessage, MessageHandlingResult
from ciris_engine.schemas.runtime.system_context import ChannelContext
from ciris_engine.schemas.telemetry.core import (
    ServiceCorrelation,
    ServiceCorrelationStatus,
    ServiceRequestData,
    ServiceResponseData,
)

from .api_communication import APICommunicationService
from .api_observer import APIObserver
from .api_runtime_control import APIRuntimeControlService
from .api_tools import APIToolService
from .app import create_app
from .config import APIAdapterConfig
from .service_configuration import ApiServiceConfiguration
from .services.auth_service import APIAuthService

logger = logging.getLogger(__name__)

# Constants
MANIFEST_FILENAME = "manifest.json"


class ApiPlatform(Service):
    """API adapter platform for CIRIS v1."""

    config: APIAdapterConfig  # type: ignore[assignment]

    def __init__(self, runtime: Any, context: Optional[Any] = None, **kwargs: Any) -> None:
        """Initialize API adapter."""
        super().__init__(config=kwargs.get("adapter_config"))
        self.runtime = runtime

        # Initialize and load configuration
        self.config = self._load_config(kwargs)

        # Create FastAPI app - services will be injected later in start()
        self.app: FastAPI = create_app(runtime, self.config)
        self._server: Server | None = None
        self._server_task: asyncio.Task[Any] | None = None
        self._startup_error: str | None = None  # Track server startup errors

        # Message observer for handling incoming messages (will be created in start())
        self.message_observer: APIObserver | None = None

        # Communication service for API responses
        self.communication = APICommunicationService(config=self.config)
        # Pass time service if available
        if hasattr(runtime, "time_service"):
            self.communication._time_service = runtime.time_service
        # Pass app state reference for message tracking
        self.communication._app_state = self.app.state  # type: ignore[attr-defined]

        # Runtime control service
        self.runtime_control = APIRuntimeControlService(runtime, time_service=getattr(runtime, "time_service", None))

        # Tool service
        self.tool_service = APIToolService(time_service=getattr(runtime, "time_service", None))

        # Adapter configuration service for interactive adapter setup
        self.adapter_configuration_service = AdapterConfigurationService()

        # Debug logging
        logger.debug(f"[DEBUG] adapter_config in kwargs: {'adapter_config' in kwargs}")
        if "adapter_config" in kwargs and kwargs["adapter_config"] is not None:
            logger.debug(f"[DEBUG] adapter_config type: {type(kwargs['adapter_config'])}")
            if hasattr(kwargs["adapter_config"], "host"):
                logger.debug(f"[DEBUG] adapter_config.host: {kwargs['adapter_config'].host}")

        logger.info(f"API adapter initialized - host: {self.config.host}, " f"port: {self.config.port}")

    def _load_config(self, kwargs: dict[str, Any]) -> APIAdapterConfig:
        """Load and merge configuration from various sources.

        Priority (highest to lowest):
        1. adapter_config parameter (APIAdapterConfig object or dict)
        2. Flat kwargs (host, port)
        3. Environment variables
        """
        config = APIAdapterConfig()
        config.load_env_vars()

        logger.info(f"[API_ADAPTER_INIT] kwargs keys: {list(kwargs.keys())}")
        logger.info(f"[API_ADAPTER_INIT] adapter_config in kwargs: {'adapter_config' in kwargs}")

        adapter_config = kwargs.get("adapter_config")
        if adapter_config is not None:
            logger.info(f"[API_ADAPTER_INIT] adapter_config value: {adapter_config}, type: {type(adapter_config)}")
            config = self._apply_adapter_config(config, adapter_config)
        elif "host" in kwargs or "port" in kwargs:
            config = self._apply_flat_kwargs(config, kwargs)
        else:
            logger.info(f"[API_ADAPTER_INIT] No config provided, using env defaults, port={config.port}")

        return config

    def _apply_adapter_config(self, config: APIAdapterConfig, adapter_config: Any) -> APIAdapterConfig:
        """Apply adapter_config parameter to configuration."""
        if isinstance(adapter_config, APIAdapterConfig):
            logger.info(f"[API_ADAPTER_INIT] Using APIAdapterConfig object, port={adapter_config.port}")
            return adapter_config
        elif isinstance(adapter_config, dict):
            new_config = APIAdapterConfig(**adapter_config)
            logger.info(f"[API_ADAPTER_INIT] Created APIAdapterConfig from dict, port={new_config.port}")
            return new_config
        # If adapter_config is provided but not dict/APIAdapterConfig, keep env-loaded config
        return config

    def _apply_flat_kwargs(self, config: APIAdapterConfig, kwargs: dict[str, Any]) -> APIAdapterConfig:
        """Apply flat kwargs (host, port) to configuration."""
        if "host" in kwargs:
            config.host = kwargs["host"]
        if "port" in kwargs:
            config.port = kwargs["port"]
        logger.info(f"[API_ADAPTER_INIT] Applied flat kwargs: host={config.host}, port={config.port}")
        return config

    def get_services_to_register(self) -> List[AdapterServiceRegistration]:
        """Get services provided by this adapter."""
        registrations = []

        # Register communication service with all capabilities
        registrations.append(
            AdapterServiceRegistration(
                service_type=ServiceType.COMMUNICATION,
                provider=self.communication,
                priority=Priority.CRITICAL,
                capabilities=["send_message", "fetch_messages"],
            )
        )

        # Register runtime control service
        registrations.append(
            AdapterServiceRegistration(
                service_type=ServiceType.RUNTIME_CONTROL,
                provider=self.runtime_control,
                priority=Priority.CRITICAL,
                capabilities=[
                    "pause_processing",
                    "resume_processing",
                    "request_state_transition",
                    "get_runtime_status",
                ],
            )
        )

        # Register tool service
        registrations.append(
            AdapterServiceRegistration(
                service_type=ServiceType.TOOL,
                provider=self.tool_service,
                priority=Priority.CRITICAL,
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

        return registrations

    def _inject_services(self) -> None:
        """Inject services into FastAPI app state after initialization."""
        logger.info("Injecting services into FastAPI app state...")

        # Store adapter config for routes to access
        self.app.state.api_config = self.config
        self.app.state.agent_template = getattr(self.runtime, "agent_template", None)
        self.app.state.db_path = getattr(self.runtime.essential_config, "database_path", None)
        logger.info(f"Injected API config with interaction_timeout={self.config.interaction_timeout}s")

        # Get service mappings from declarative configuration
        service_mappings = ApiServiceConfiguration.get_current_mappings_as_tuples()

        # Inject services using mapping
        for runtime_attr, app_attrs, handler_name in service_mappings:
            # Convert handler name to actual method if provided
            handler = getattr(self, handler_name) if handler_name else None
            self._inject_service(runtime_attr, app_attrs, handler)

        # Inject adapter-created services using configuration
        for adapter_service in ApiServiceConfiguration.ADAPTER_CREATED_SERVICES:
            service = getattr(self, adapter_service.attr_name)
            setattr(self.app.state, adapter_service.app_state_name, service)
            logger.info(f"Injected {adapter_service.app_state_name} ({adapter_service.description})")

        # Set up message handling
        self._setup_message_handling()

    def reinject_services(self) -> None:
        """Re-inject services after they become available (e.g., after first-run setup).

        This is called from resume_from_first_run() to update the FastAPI app state
        with services that were None during initial adapter startup in first-run mode.
        """
        logger.info("Re-injecting services into FastAPI app state after first-run setup...")

        # Get service mappings from declarative configuration
        service_mappings = ApiServiceConfiguration.get_current_mappings_as_tuples()

        # Count how many services we successfully inject
        injected_count = 0
        skipped_count = 0

        # Re-inject services using mapping
        for runtime_attr, app_attrs, handler_name in service_mappings:
            runtime = self.runtime
            if hasattr(runtime, runtime_attr) and getattr(runtime, runtime_attr) is not None:
                service = getattr(runtime, runtime_attr)
                setattr(self.app.state, app_attrs, service)

                # Call special handler if provided
                if handler_name:
                    handler = getattr(self, handler_name)
                    handler(service)

                injected_count += 1
                logger.debug(f"Re-injected {runtime_attr}")
            else:
                skipped_count += 1

        logger.info(f"Re-injection complete: {injected_count} services injected, {skipped_count} still unavailable")

        # Now that services are available, inject adapter_manager into APIRuntimeControlService
        # This was skipped during first-run startup because RuntimeControlService didn't exist
        try:
            self._inject_adapter_manager_to_api_runtime_control()
        except RuntimeError as e:
            logger.warning(f"Could not inject adapter_manager during re-injection: {e}")

    def _log_service_registry(self, service: Any) -> None:
        """Log service registry details."""
        try:
            all_services = service.get_all_services()
            service_count = len(all_services) if hasattr(all_services, "__len__") else 0
            logger.info(f"[API] Injected service_registry {id(service)} with {service_count} services")
            service_names = [s.__class__.__name__ for s in all_services] if all_services else []
            logger.info(f"[API] Services in injected registry: {service_names}")
        except (TypeError, AttributeError):
            logger.info("[API] Injected service_registry (mock or test mode)")

    def _inject_service(
        self, runtime_attr: str, app_state_name: str, handler: Callable[[Any], None] | None = None
    ) -> None:
        """Inject a single service from runtime to app state."""
        runtime = self.runtime
        if hasattr(runtime, runtime_attr) and getattr(runtime, runtime_attr) is not None:
            service = getattr(runtime, runtime_attr)
            setattr(self.app.state, app_state_name, service)

            # Call special handler if provided
            if handler:
                handler(service)

            # Special logging for service_registry
            if runtime_attr == "service_registry":
                self._log_service_registry(service)
            else:
                logger.info(f"Injected {runtime_attr}")
        else:
            # Log when service is not injected
            if not hasattr(runtime, runtime_attr):
                logger.warning(f"Runtime does not have attribute '{runtime_attr}' - skipping injection")
            else:
                logger.warning(f"Runtime attribute '{runtime_attr}' is None - skipping injection")

    def _inject_adapter_manager_to_api_runtime_control(self) -> None:
        """Inject main RuntimeControlService's adapter_manager into APIRuntimeControlService.

        This ensures a single source of truth for loaded adapters. Without this,
        adapters loaded via one service won't be visible in the other.

        CRITICAL: This must be called after _inject_services() so main_runtime_control_service
        is available in app.state.

        In first-run mode, RuntimeControlService is not yet initialized (services start after
        the setup wizard completes), so we skip this injection. It will be called again
        during reinject_services() after resume_from_first_run().
        """
        from ciris_engine.logic.setup.first_run import is_first_run

        # In first-run mode, RuntimeControlService doesn't exist yet - skip injection
        # It will be injected after resume_from_first_run() completes
        if is_first_run():
            logger.info("First-run mode: Skipping adapter_manager injection (will inject after setup)")
            return

        main_runtime_control = getattr(self.app.state, "main_runtime_control_service", None)
        if not main_runtime_control:
            raise RuntimeError(
                "CRITICAL: main_runtime_control_service not available in app.state. "
                "This indicates a startup sequencing issue. Cannot inject adapter_manager."
            )

        # Trigger lazy initialization of adapter_manager if needed
        # The main RuntimeControlService has _ensure_adapter_manager_initialized() for this
        if hasattr(main_runtime_control, "_ensure_adapter_manager_initialized"):
            main_runtime_control._ensure_adapter_manager_initialized()

        adapter_manager = getattr(main_runtime_control, "adapter_manager", None)
        if not adapter_manager:
            raise RuntimeError(
                "CRITICAL: main_runtime_control_service has no adapter_manager even after "
                "_ensure_adapter_manager_initialized(). This indicates the main RuntimeControlService "
                "has no runtime reference. Check service initialization order."
            )

        # Inject into APIRuntimeControlService
        self.runtime_control.adapter_manager = adapter_manager
        logger.info(
            f"Injected main RuntimeControlService's adapter_manager (id: {id(adapter_manager)}) "
            f"into APIRuntimeControlService - single source of truth established"
        )

    def _handle_auth_service(self, auth_service: Any) -> None:
        """Special handler for authentication service."""
        # CRITICAL: Preserve existing APIAuthService if it already exists (has stored API keys)
        # During re-injection after first-run setup, we must NOT create a new instance
        # because the existing instance has in-memory API keys that would be lost!
        existing_auth_service = getattr(self.app.state, "auth_service", None)
        if existing_auth_service is not None and isinstance(existing_auth_service, APIAuthService):
            # Update the existing instance's auth_service reference but preserve API keys
            existing_auth_service._auth_service = auth_service
            logger.info(
                f"[AUTH SERVICE DEBUG] Preserved existing APIAuthService (instance #{existing_auth_service._instance_id}) with {len(existing_auth_service._api_keys)} API keys - updated _auth_service reference"
            )
        else:
            # First time initialization - create new instance
            self.app.state.auth_service = APIAuthService(auth_service)
            logger.info("Initialized APIAuthService with authentication service for persistence")

    def _handle_bus_manager(self, bus_manager: Any) -> None:
        """Special handler for bus manager - inject individual buses into app.state."""
        # Inject tool_bus and memory_bus for DSAR multi-source operations
        self.app.state.tool_bus = bus_manager.tool
        self.app.state.memory_bus = bus_manager.memory
        logger.info("Injected tool_bus and memory_bus from bus_manager for multi-source DSAR operations")

    def _setup_message_handling(self) -> None:
        """Set up message handling and correlation tracking."""
        # Store message ID to channel mapping for response routing
        self.app.state.message_channel_map = {}

        # Create and assign message handler
        self.app.state.on_message = self._create_message_handler()
        logger.info("Set up message handler via observer pattern with correlation tracking")

    def _create_message_handler(self) -> Callable[[IncomingMessage], Awaitable[MessageHandlingResult]]:
        """Create the message handler function."""

        async def handle_message_via_observer(msg: IncomingMessage) -> MessageHandlingResult:
            """Handle incoming messages by creating passive observations."""
            try:
                logger.info(f"handle_message_via_observer called for message {msg.message_id}")
                if self.message_observer:
                    # Store the message ID to channel mapping
                    self.app.state.message_channel_map[msg.channel_id] = msg.message_id

                    # Create correlation
                    await self._create_message_correlation(msg)

                    # Pass to observer for task creation and get result
                    result = await self.message_observer.handle_incoming_message(msg)
                    if result:
                        logger.info(f"Message {msg.message_id} passed to observer, result: {result.status}")
                        return result
                    else:
                        logger.warning(f"Message {msg.message_id} passed to observer but no result returned")
                        # Return a default result for backward compatibility with tests
                        from ciris_engine.schemas.runtime.messages import MessageHandlingResult, MessageHandlingStatus

                        return MessageHandlingResult(
                            status=MessageHandlingStatus.TASK_CREATED,
                            message_id=msg.message_id,
                            channel_id=msg.channel_id or "unknown",
                        )
                else:
                    logger.error("Message observer not available")
                    raise RuntimeError("Message observer not available")
            except Exception as e:
                logger.error(f"Error in handle_message_via_observer: {e}", exc_info=True)
                raise

        return handle_message_via_observer

    async def _create_message_correlation(self, msg: Any) -> None:
        """Create an observe correlation for incoming message."""
        correlation_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)

        # Create correlation for the incoming message
        correlation = ServiceCorrelation(
            correlation_id=correlation_id,
            service_type="api",
            handler_name="APIAdapter",
            action_type="observe",
            request_data=ServiceRequestData(
                service_type="api",
                method_name="observe",
                channel_id=msg.channel_id,
                parameters={
                    "content": msg.content,
                    "author_id": msg.author_id,
                    "author_name": msg.author_name,
                    "message_id": msg.message_id,
                },
                request_timestamp=now,
            ),
            response_data=ServiceResponseData(
                success=True, result_summary="Message observed", execution_time_ms=0, response_timestamp=now
            ),
            status=ServiceCorrelationStatus.COMPLETED,
            created_at=now,
            updated_at=now,
            timestamp=now,
        )

        # Get time service if available
        time_service = getattr(self.runtime, "time_service", None)
        persistence.add_correlation(correlation, time_service)
        logger.debug(f"Created observe correlation for message {msg.message_id}")

    def _discover_and_register_configurable_adapters(self) -> None:
        """Discover and register adapters that support interactive configuration.

        Scans the ciris_adapters directory for adapter manifests that define
        interactive_config sections and registers them with the AdapterConfigurationService.
        """
        from pathlib import Path

        # Find ciris_adapters directory - try multiple methods for Android compatibility
        adapters_dir = Path(__file__).resolve().parent.parent.parent.parent.parent / "ciris_adapters"

        if not adapters_dir.exists():
            # Fallback for Android: use importlib.resources to discover adapters dynamically
            logger.info(f"Filesystem adapters directory not found ({adapters_dir}), using importlib discovery")
            self._discover_adapters_via_importlib()
            return

        registered_count = 0
        for adapter_path in adapters_dir.iterdir():
            if self._process_adapter_path(adapter_path):
                registered_count += 1

        logger.info(f"Discovered and registered {registered_count} configurable adapter(s)")

    def _process_adapter_path(self, adapter_path: Any) -> bool:
        """Process a single adapter directory and register if configurable.

        Returns True if adapter was successfully registered.
        """
        import json

        if not adapter_path.is_dir():
            return False

        manifest_path = adapter_path / MANIFEST_FILENAME
        if not manifest_path.exists():
            return False

        try:
            with open(manifest_path) as f:
                manifest_data = json.load(f)
            return self._register_adapter_from_manifest(manifest_data, adapter_path.name)
        except Exception as e:
            logger.warning(f"Failed to process manifest for {adapter_path.name}: {e}")
            return False

    def _register_adapter_from_manifest(self, manifest_data: dict[str, Any], adapter_type: str) -> bool:
        """Register an adapter from its manifest data.

        Returns True if adapter was successfully registered.
        """
        interactive_config_data = manifest_data.get("interactive_config")
        if not interactive_config_data:
            return False

        interactive_config = self._parse_interactive_config(interactive_config_data)
        exports = manifest_data.get("exports", {})
        configurable_class_path = exports.get("configurable")

        if not configurable_class_path:
            logger.debug(f"Adapter {adapter_type} has interactive_config but no configurable export")
            return False

        return self._load_and_register_configurable(adapter_type, interactive_config, configurable_class_path)

    def _parse_interactive_config(self, config_data: dict[str, Any]) -> Any:
        """Parse interactive configuration data into InteractiveConfiguration object."""
        from ciris_engine.schemas.runtime.manifest import ConfigurationStep, InteractiveConfiguration

        steps = [ConfigurationStep.model_validate(step_data) for step_data in config_data.get("steps", [])]

        return InteractiveConfiguration(
            required=config_data.get("required", False),
            workflow_type=config_data.get("workflow_type", "wizard"),
            steps=steps,
            completion_method=config_data.get("completion_method", "apply_config"),
        )

    def _load_and_register_configurable(
        self, adapter_type: str, interactive_config: Any, configurable_class_path: str
    ) -> bool:
        """Load configurable class and register with configuration service.

        Returns True if successful.
        """
        import importlib

        try:
            module_path, class_name = configurable_class_path.rsplit(".", 1)
            if not module_path.startswith("ciris_adapters"):
                module_path = f"ciris_adapters.{module_path}"
            module = importlib.import_module(module_path)
            configurable_class = getattr(module, class_name)
            adapter_instance = configurable_class()

            self.adapter_configuration_service.register_adapter_config(
                adapter_type=adapter_type,
                interactive_config=interactive_config,
                adapter_instance=adapter_instance,
            )
            logger.info(f"Registered configurable adapter: {adapter_type}")
            return True
        except Exception as e:
            logger.warning(f"Failed to load configurable class for {adapter_type}: {e}")
            return False

    def _discover_adapters_via_importlib(self) -> None:
        """Discover adapters dynamically using importlib (Android/Chaquopy compatible).

        Uses pkgutil.iter_modules to find all subpackages in ciris_adapters,
        then checks each for a manifest.json with interactive_config.
        """
        adapter_names = self._get_adapter_package_names()
        if not adapter_names:
            return

        registered_count = 0
        for adapter_name in adapter_names:
            if self._process_adapter_via_importlib(adapter_name):
                registered_count += 1

        logger.info(f"Discovered and registered {registered_count} configurable adapter(s) via importlib")

    def _get_adapter_package_names(self) -> list[str]:
        """Get list of adapter package names via pkgutil."""
        import pkgutil

        try:
            import ciris_adapters

            adapter_names = [
                name
                for importer, name, ispkg in pkgutil.iter_modules(ciris_adapters.__path__)
                if ispkg and not name.startswith("_")
            ]
            logger.info(f"Discovered {len(adapter_names)} adapter packages via pkgutil: {adapter_names}")
            return adapter_names
        except ImportError:
            logger.warning("ciris_adapters package not found, no adapters to discover")
            return []

    def _process_adapter_via_importlib(self, adapter_name: str) -> bool:
        """Process a single adapter package via importlib.

        Returns True if adapter was successfully registered.
        """
        import importlib

        try:
            importlib.import_module(f"ciris_adapters.{adapter_name}")
        except ImportError:
            logger.debug(f"Adapter package not found: ciris_adapters.{adapter_name}")
            return False

        manifest_data = self._read_manifest_via_importlib(adapter_name)
        if manifest_data is None:
            return False

        try:
            return self._register_adapter_from_manifest(manifest_data, adapter_name)
        except Exception as e:
            logger.warning(f"Failed to process adapter {adapter_name}: {e}")
            return False

    def _read_manifest_via_importlib(self, adapter_name: str) -> dict[str, Any] | None:
        """Read manifest.json using importlib.resources.

        Returns manifest data dict or None if not found.
        """
        import importlib.resources as pkg_resources
        import json

        package_name = f"ciris_adapters.{adapter_name}"
        try:
            # Try files() API first (Python 3.9+)
            files = pkg_resources.files(package_name)
            manifest_path = files.joinpath(MANIFEST_FILENAME)
            manifest_text = manifest_path.read_text()
        except (TypeError, AttributeError):
            # Fallback for older API
            try:
                with pkg_resources.open_text(package_name, MANIFEST_FILENAME) as f:
                    manifest_text = f.read()
            except Exception as e:
                logger.warning(f"Could not read manifest for {adapter_name}: {e}")
                return None
        except Exception as e:
            logger.warning(f"Could not read manifest for {adapter_name}: {e}")
            return None

        logger.info(f"Successfully read manifest for {adapter_name}")
        result: dict[str, Any] = json.loads(manifest_text)
        return result

    async def _restore_persisted_adapter_configs(self) -> None:
        """Restore adapter configurations that were persisted for load-on-startup.

        This is called during API adapter startup to restore adapters that were
        previously configured and marked for automatic loading.
        """
        # Get config service from runtime
        config_service = getattr(self.runtime, "config_service", None)
        if not config_service:
            logger.debug("No config_service available - skipping persisted adapter restoration")
            return

        # Get runtime control service for loading adapters
        runtime_control_service = self.runtime_control

        try:
            restored_count = await self.adapter_configuration_service.restore_persisted_adapters(
                config_service=config_service,
                runtime_control_service=runtime_control_service,
            )
            if restored_count > 0:
                logger.info(f"Restored {restored_count} persisted adapter configuration(s)")
        except Exception as e:
            logger.warning(f"Failed to restore persisted adapter configurations: {e}")

    def _is_android_platform(self) -> bool:
        """Check if running on Android platform."""
        import os

        return os.environ.get("ANDROID_DATA") is not None or os.path.exists("/data/data")

    def _has_google_auth(self) -> bool:
        """Check if Google authentication token is available."""
        import os

        return bool(os.environ.get("CIRIS_BILLING_GOOGLE_ID_TOKEN"))

    def _is_hosted_tools_loaded(self) -> bool:
        """Check if ciris_hosted_tools adapter is already loaded."""
        runtime_control = self.runtime_control
        if not runtime_control or not hasattr(runtime_control, "adapter_manager"):
            return False
        adapter_manager = runtime_control.adapter_manager
        if not adapter_manager or not adapter_manager.loaded_adapters:
            return False
        return any("ciris_hosted_tools" in adapter_id for adapter_id in adapter_manager.loaded_adapters.keys())

    async def _auto_enable_android_adapters(self) -> None:
        """Auto-enable Android-specific adapters when conditions are met.

        This enables ciris_hosted_tools (web_search) when:
        1. Running on Android platform (detected via env var or platform check)
        2. Google authentication is available (CIRIS_BILLING_GOOGLE_ID_TOKEN is set)
        3. The adapter is not already loaded

        Called at startup and after resume_from_first_run().
        """
        if not self._is_android_platform():
            logger.debug("[AUTO_ENABLE] Not on Android, skipping auto-enable of ciris_hosted_tools")
            return

        if not self._has_google_auth():
            logger.debug("[AUTO_ENABLE] No Google auth token found, skipping auto-enable of ciris_hosted_tools")
            return

        if self._is_hosted_tools_loaded():
            logger.debug("[AUTO_ENABLE] ciris_hosted_tools already loaded, skipping")
            return

        logger.info("[AUTO_ENABLE] Android platform with Google auth detected - enabling ciris_hosted_tools adapter")
        await self._load_hosted_tools_adapter()

    async def _load_hosted_tools_adapter(self) -> None:
        """Load the ciris_hosted_tools adapter."""
        try:
            main_runtime_control = getattr(self.runtime, "runtime_control_service", None) or self.runtime_control
            if not main_runtime_control:
                logger.warning("[AUTO_ENABLE] No runtime control service available for adapter loading")
                return

            result = await main_runtime_control.load_adapter(
                adapter_type="ciris_hosted_tools",
                adapter_id="ciris_hosted_tools_auto",
                config={},
            )

            if result.success:
                logger.info(f"[AUTO_ENABLE] Successfully enabled ciris_hosted_tools adapter (id: {result.adapter_id})")
                logger.info("[AUTO_ENABLE] web_search tool is now available")
            else:
                logger.warning(f"[AUTO_ENABLE] Failed to enable ciris_hosted_tools: {result.error}")
        except Exception as e:
            logger.warning(f"[AUTO_ENABLE] Error enabling ciris_hosted_tools: {e}")

    async def _wait_for_port_available(self, max_retries: int = 10, retry_delay: float = 1.0) -> None:
        """Wait for port to become available, with retries for TIME_WAIT state.

        Raises:
            RuntimeError: If port remains in use after all retries.
        """
        import socket

        for attempt in range(max_retries):
            if self._check_port_available():
                if attempt > 0:
                    logger.info(f"[API_ADAPTER] Port {self.config.port} became available after {attempt} retries")
                return

            if attempt < max_retries - 1:
                logger.warning(
                    f"[API_ADAPTER] Port {self.config.port} in use, waiting {retry_delay}s "
                    f"(attempt {attempt + 1}/{max_retries})"
                )
                await asyncio.sleep(retry_delay)
            else:
                error_msg = f"Port {self.config.port} is already in use on {self.config.host}"
                logger.error(f"[API_ADAPTER] {error_msg}")
                self._startup_error = error_msg
                raise RuntimeError(error_msg)

    def _check_port_available(self) -> bool:
        """Check if the configured port is available."""
        import socket

        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(1)
                host = self.config.host if self.config.host != "0.0.0.0" else "127.0.0.1"
                result = s.connect_ex((host, self.config.port))
                return result != 0  # Non-zero means port is available
        except Exception as e:
            logger.warning(f"Could not check port availability: {e}, will attempt to start anyway")
            return True

    async def start(self) -> None:
        """Start the API server."""
        logger.debug(f"[DEBUG] At start() - config.host: {self.config.host}, config.port: {self.config.port}")
        await super().start()

        # Track start time for metrics
        import time

        self._start_time = time.time()

        # Start the communication service
        await self.communication.start()
        logger.info("Started API communication service")

        # Start the tool service
        await self.tool_service.start()
        logger.info("Started API tool service")

        # Create message observer for handling incoming messages
        resource_monitor_from_runtime = getattr(self.runtime, "resource_monitor_service", None)
        logger.info(
            f"[OBSERVER_INIT] resource_monitor_service from runtime: {resource_monitor_from_runtime is not None}, type={type(resource_monitor_from_runtime).__name__ if resource_monitor_from_runtime else 'None'}"
        )

        self.message_observer = APIObserver(
            on_observe=lambda _: asyncio.sleep(0),
            bus_manager=getattr(self.runtime, "bus_manager", None),
            memory_service=getattr(self.runtime, "memory_service", None),
            agent_id=getattr(self.runtime, "agent_id", None),
            filter_service=getattr(self.runtime, "adaptive_filter_service", None),
            secrets_service=getattr(self.runtime, "secrets_service", None),
            time_service=getattr(self.runtime, "time_service", None),
            agent_occurrence_id=getattr(self.runtime.essential_config, "agent_occurrence_id", "default"),
            origin_service="api",
            resource_monitor=resource_monitor_from_runtime,
        )
        await self.message_observer.start()
        logger.info("Started API message observer")

        # Inject services now that they're initialized
        self._inject_services()

        # Inject main RuntimeControlService's adapter_manager into APIRuntimeControlService
        # This ensures a single source of truth for loaded adapters
        self._inject_adapter_manager_to_api_runtime_control()

        # Discover and register configurable adapters
        self._discover_and_register_configurable_adapters()

        # Restore any persisted adapter configurations from previous sessions
        await self._restore_persisted_adapter_configs()

        # Auto-enable Android-specific adapters (ciris_hosted_tools with web_search)
        await self._auto_enable_android_adapters()

        # Start runtime control service now that services are available
        await self.runtime_control.start()
        logger.info("Started API runtime control service")

        # Wait for port to become available (handles TIME_WAIT from previous shutdown)
        await self._wait_for_port_available()

        # Configure uvicorn
        config = uvicorn.Config(
            self.app,
            host=self.config.host,
            port=self.config.port,
            log_level="info",
            access_log=True,
            timeout_graceful_shutdown=30,  # Force shutdown after 30s to prevent hang
        )

        # Create and start server with error handling wrapper
        self._server = uvicorn.Server(config)
        assert self._server is not None

        async def _run_server_safely() -> None:
            """Run server and catch SystemExit to prevent process crash."""
            try:
                await self._server.serve()  # type: ignore[union-attr]
            except SystemExit as e:
                # uvicorn calls sys.exit(1) on startup failures - catch it!
                logger.error(f"[API_ADAPTER] Server startup failed with SystemExit: {e}")
                self._startup_error = f"Server startup failed: {e}"
                raise RuntimeError(self._startup_error) from e
            except Exception as e:
                logger.error(f"[API_ADAPTER] Server error: {e}", exc_info=True)
                self._startup_error = str(e)
                raise RuntimeError(self._startup_error) from e

        self._server_task = asyncio.create_task(_run_server_safely())

        logger.info(f"API server starting on http://{self.config.host}:{self.config.port}")

        # Show setup wizard message if this is a first run
        from ciris_engine.logic.setup.first_run import is_first_run
        if is_first_run():
            # Use print for visibility - this is important user-facing info
            url = f"http://{self.config.host}:{self.config.port}"
            print("\n" + "=" * 60)
            print("  CIRIS Setup Required")
            print("=" * 60)
            print(f"\n  Open your browser to complete setup:\n")
            print(f"    {url}")
            print("\n" + "=" * 60 + "\n")

        # Wait a moment for server to start and check for immediate failures
        await asyncio.sleep(1)

        # Check if server task failed immediately
        if self._server_task.done():
            error = getattr(self, "_startup_error", None)
            if error:
                raise RuntimeError(f"API server failed to start: {error}")

    async def stop(self) -> None:
        """Stop the API server."""
        logger.info("Stopping API server...")

        # Stop runtime control service
        await self.runtime_control.stop()

        # Stop communication service
        await self.communication.stop()

        # Stop tool service
        await self.tool_service.stop()

        # Stop server
        if self._server:
            self._server.should_exit = True
            if self._server_task:
                await self._server_task

        await super().stop()

    def get_channel_list(self) -> List[ChannelContext]:
        """
        Get list of available API channels from correlations.

        Returns:
            List of ChannelContext objects for API channels.
        """
        from datetime import datetime

        # Get active channels from last 30 days
        channels_data = get_active_channels_by_adapter("api", since_days=30)

        # Convert to ChannelContext objects
        channels = []
        for data in channels_data:
            # Determine allowed actions based on admin status
            is_admin = is_admin_channel(data.channel_id)
            allowed_actions = ["speak", "observe", "memorize", "recall", "tool"]
            if is_admin:
                allowed_actions.extend(["wa_defer", "runtime_control"])

            channel = ChannelContext(
                channel_id=data.channel_id,
                channel_type="api",
                created_at=data.last_activity if data.last_activity else datetime.now(timezone.utc),
                channel_name=data.channel_name or data.channel_id,  # API channels use ID as name if no name
                is_private=False,  # API channels are not private
                participants=[],  # Could track user IDs if needed
                is_active=data.is_active,
                last_activity=data.last_activity,
                message_count=data.message_count,
                allowed_actions=allowed_actions,
                moderation_level="standard",
            )
            channels.append(channel)

        return channels

    def is_healthy(self) -> bool:
        """Check if the API server is healthy and running."""
        if self._server is None or self._server_task is None:
            return False

        # Check if the server task is still running
        return not self._server_task.done()

    def get_metrics(self) -> dict[str, float]:
        """Get all metrics including base, custom, and v1.4.3 specific."""
        # Initialize base metrics
        import time

        uptime = time.time() - self._start_time if hasattr(self, "_start_time") else 0.0
        metrics = {
            "uptime_seconds": uptime,
            "healthy": self.is_healthy(),
        }

        # Add v1.4.3 specific metrics
        try:
            # Get metrics from communication service
            comm_status = self.communication.get_status()
            comm_metrics = comm_status.metrics if hasattr(comm_status, "metrics") else {}

            # Get active WebSocket connections count
            active_connections = 0
            if hasattr(self.communication, "_websocket_clients"):
                try:
                    active_connections = len(self.communication._websocket_clients)
                except (TypeError, AttributeError):
                    active_connections = 0

            # Extract values with defaults
            requests_total = float(comm_metrics.get("requests_handled", 0))
            errors_total = float(comm_metrics.get("error_count", 0))
            avg_response_time = float(comm_metrics.get("avg_response_time_ms", 0.0))

            metrics.update(
                {
                    "api_requests_total": requests_total,
                    "api_errors_total": errors_total,
                    "api_response_time_ms": avg_response_time,
                    "api_active_connections": float(active_connections),
                }
            )

        except Exception as e:
            logger.warning(f"Failed to get API adapter metrics: {e}")
            # Return zeros on error rather than failing
            metrics.update(
                {
                    "api_requests_total": 0.0,
                    "api_errors_total": 0.0,
                    "api_response_time_ms": 0.0,
                    "api_active_connections": 0.0,
                }
            )

        return metrics

    async def run_lifecycle(self, agent_run_task: Optional[asyncio.Task[Any]]) -> None:
        """Run the adapter lifecycle - API runs until agent stops."""
        logger.info("API adapter running lifecycle")

        try:
            # In first-run mode, agent_run_task is None - just keep server running
            if agent_run_task is None:
                logger.info("First-run mode: API server will run until manually stopped")
                # Just wait for server task to complete (or CTRL+C)
                if self._server_task:
                    await self._server_task
                return

            # Normal mode: Wait for either the agent task or server task to complete
            while not agent_run_task.done():
                # Check if server is still running
                if not self._server_task or self._server_task.done():
                    # Server stopped unexpectedly
                    if self._server_task:
                        exc = self._server_task.exception()
                        if exc:
                            logger.error(f"API server stopped with error: {exc}")
                            raise exc
                    logger.warning("API server stopped unexpectedly")
                    break

                await asyncio.sleep(0.1)

        except asyncio.CancelledError:
            logger.info("API adapter lifecycle cancelled")
            raise
        except Exception as e:
            logger.error(f"API adapter lifecycle error: {e}")
            raise
        finally:
            logger.info("API adapter lifecycle ending")
