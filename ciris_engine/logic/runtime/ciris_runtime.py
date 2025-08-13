"""
ciris_engine/runtime/ciris_runtime.py

New simplified runtime that properly orchestrates all components.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, List, Optional

from ciris_engine.logic import persistence
from ciris_engine.logic.adapters import load_adapter
from ciris_engine.logic.infrastructure.handlers.action_dispatcher import ActionDispatcher
from ciris_engine.logic.infrastructure.handlers.handler_registry import build_action_dispatcher
from ciris_engine.logic.processors import AgentProcessor
from ciris_engine.logic.registries.base import ServiceRegistry
from ciris_engine.logic.utils.constants import DEFAULT_NUM_ROUNDS
from ciris_engine.logic.utils.shutdown_manager import (
    get_shutdown_manager,
    is_global_shutdown_requested,
    wait_for_global_shutdown_async,
)
from ciris_engine.protocols.runtime.base import BaseAdapterProtocol
from ciris_engine.protocols.services.lifecycle.time import TimeServiceProtocol
from ciris_engine.schemas.adapters import AdapterServiceRegistration
from ciris_engine.schemas.config.essential import EssentialConfig
from ciris_engine.schemas.processors.states import AgentState
from ciris_engine.schemas.runtime.enums import ServiceType
from ciris_engine.schemas.services.operations import InitializationPhase

from .component_builder import ComponentBuilder
from .identity_manager import IdentityManager
from .service_initializer import ServiceInitializer

logger = logging.getLogger(__name__)


class CIRISRuntime:
    """
    Main runtime orchestrator for CIRIS Agent.
    Handles initialization of all components and services.
    Implements the RuntimeInterface protocol.
    """

    def __new__(cls, *args, **kwargs):
        """Custom __new__ to handle CI environment issues."""
        # This fixes a pytest/CI issue where object.__new__ gets called incorrectly
        instance = object.__new__(cls)
        return instance

    def __init__(
        self,
        adapter_types: List[str],
        essential_config: Optional[EssentialConfig] = None,
        startup_channel_id: Optional[str] = None,
        adapter_configs: Optional[dict] = None,
        **kwargs: Any,
    ) -> None:
        # CRITICAL: Prevent runtime creation during module imports
        import os

        if os.environ.get("CIRIS_IMPORT_MODE", "").lower() == "true":
            logger.error("CRITICAL: Attempted to create CIRISRuntime during import mode!")
            raise RuntimeError(
                "Cannot create CIRISRuntime during module imports. "
                "This prevents side effects and unwanted process creation. "
                "Call prevent_sideeffects.allow_runtime_creation() before creating runtime."
            )
        self.essential_config = essential_config
        # Store startup_channel_id, may be None or empty string
        self.startup_channel_id = startup_channel_id or ""
        self.adapter_configs = adapter_configs or {}
        self.adapters: List[BaseAdapterProtocol] = []
        self.modules_to_load = kwargs.get("modules", [])

        # CRITICAL: Check for mock LLM environment variable
        if os.environ.get("CIRIS_MOCK_LLM", "").lower() in ("true", "1", "yes", "on"):
            logger.warning("CIRIS_MOCK_LLM environment variable detected in CIRISRuntime")
            if "mock_llm" not in self.modules_to_load:
                self.modules_to_load.append("mock_llm")
                logger.info("Added mock_llm to modules to load")

        # Initialize managers
        self.identity_manager: Optional[IdentityManager] = None
        self.service_initializer = ServiceInitializer(essential_config=essential_config)
        self.component_builder: Optional[ComponentBuilder] = None
        self.agent_processor: Optional["AgentProcessor"] = None
        self._adapter_tasks: List[asyncio.Task] = []

        for adapter_name in adapter_types:
            try:
                base_adapter = adapter_name.split(":")[0]
                adapter_class = load_adapter(base_adapter)

                adapter_kwargs = kwargs.copy()
                if adapter_name in self.adapter_configs:
                    adapter_kwargs["adapter_config"] = self.adapter_configs[adapter_name]

                # Adapters expect runtime as first positional argument
                self.adapters.append(adapter_class(self, **adapter_kwargs))  # type: ignore[call-arg]
                logger.info(f"Successfully loaded and initialized adapter: {adapter_name}")
            except Exception as e:
                logger.error(f"Failed to load or initialize adapter '{adapter_name}': {e}", exc_info=True)

        if not self.adapters:
            raise RuntimeError("No valid adapters specified, shutting down")

        # Runtime state
        self._initialized = False
        self._shutdown_manager = get_shutdown_manager()
        self._shutdown_event: Optional[asyncio.Event] = None
        self._shutdown_reason: Optional[str] = None
        self._agent_task: Optional[asyncio.Task] = None
        self._preload_tasks: List[str] = []
        self._shutdown_complete = False

        # Identity - will be loaded during initialization
        self.agent_identity: Optional[Any] = None

    # Properties to access services from the service initializer
    @property
    def service_registry(self) -> Optional[ServiceRegistry]:
        return self.service_initializer.service_registry if self.service_initializer else None

    @property
    def bus_manager(self) -> Optional[Any]:
        return self.service_initializer.bus_manager if self.service_initializer else None

    @property
    def memory_service(self) -> Optional[Any]:
        return self.service_initializer.memory_service if self.service_initializer else None

    @property
    def resource_monitor(self) -> Optional[Any]:
        """Access to resource monitor service - CRITICAL for mission-critical systems."""
        return self.service_initializer.resource_monitor_service if self.service_initializer else None

    @property
    def secrets_service(self) -> Optional[Any]:
        return self.service_initializer.secrets_service if self.service_initializer else None

    @property
    def wa_auth_system(self) -> Optional[Any]:
        return self.service_initializer.wa_auth_system if self.service_initializer else None

    @property
    def telemetry_service(self) -> Optional[Any]:
        return self.service_initializer.telemetry_service if self.service_initializer else None

    @property
    def llm_service(self) -> Optional[Any]:
        return self.service_initializer.llm_service if self.service_initializer else None

    @property
    def audit_services(self) -> List[Any]:
        return self.service_initializer.audit_services if self.service_initializer else []

    @property
    def audit_service(self) -> Optional[Any]:
        return self.service_initializer.audit_service if self.service_initializer else None

    @property
    def adaptive_filter_service(self) -> Optional[Any]:
        return self.service_initializer.adaptive_filter_service if self.service_initializer else None

    @property
    def agent_config_service(self) -> Optional[Any]:
        return self.service_initializer.agent_config_service if self.service_initializer else None

    @property
    def config_manager(self) -> Optional[Any]:
        """Return GraphConfigService for RuntimeControlService compatibility."""
        return self.service_initializer.config_service if self.service_initializer else None

    @property
    def transaction_orchestrator(self) -> Optional[Any]:
        return self.service_initializer.transaction_orchestrator if self.service_initializer else None

    @property
    def core_tool_service(self) -> Optional[Any]:
        return self.service_initializer.core_tool_service if self.service_initializer else None

    @property
    def time_service(self) -> Optional[TimeServiceProtocol]:
        return self.service_initializer.time_service if self.service_initializer else None

    @property
    def config_service(self) -> Optional[Any]:
        """Access to configuration service."""
        return self.service_initializer.config_service if self.service_initializer else None

    @property
    def task_scheduler(self) -> Optional[Any]:
        """Access to task scheduler service."""
        return self.service_initializer.task_scheduler_service if self.service_initializer else None

    @property
    def authentication_service(self) -> Optional[Any]:
        """Access to authentication service."""
        return self.service_initializer.auth_service if self.service_initializer else None

    @property
    def incident_management_service(self) -> Optional[Any]:
        """Access to incident management service."""
        return self.service_initializer.incident_management_service if self.service_initializer else None

    @property
    def runtime_control_service(self) -> Optional[Any]:
        """Access to runtime control service."""
        return self.service_initializer.runtime_control_service if self.service_initializer else None

    @property
    def profile(self) -> Optional[Any]:
        """Convert agent identity to profile format for compatibility."""
        if not self.agent_identity:
            return None

        # Create AgentTemplate from identity
        from ciris_engine.schemas.config.agent import AgentTemplate, DSDMAConfiguration

        # Create DSDMAConfiguration object if needed
        dsdma_config = None
        if (
            self.agent_identity.core_profile.domain_specific_knowledge
            or self.agent_identity.core_profile.dsdma_prompt_template
        ):
            dsdma_config = DSDMAConfiguration(
                domain_specific_knowledge=self.agent_identity.core_profile.domain_specific_knowledge,
                prompt_template=self.agent_identity.core_profile.dsdma_prompt_template,
            )

        return AgentTemplate(
            name=self.agent_identity.agent_id,
            description=self.agent_identity.core_profile.description,
            role_description=self.agent_identity.core_profile.role_description,
            permitted_actions=self.agent_identity.permitted_actions,
            dsdma_kwargs=dsdma_config,
            csdma_overrides=self.agent_identity.core_profile.csdma_overrides,
            action_selection_pdma_overrides=self.agent_identity.core_profile.action_selection_pdma_overrides,
        )

    @property
    def maintenance_service(self) -> Optional[Any]:
        return self.service_initializer.maintenance_service if self.service_initializer else None

    @property
    def shutdown_service(self) -> Optional[Any]:
        """Access to shutdown service."""
        return self.service_initializer.shutdown_service if self.service_initializer else None

    @property
    def initialization_service(self) -> Optional[Any]:
        """Access to initialization service."""
        return self.service_initializer.initialization_service if self.service_initializer else None

    @property
    def tsdb_consolidation_service(self) -> Optional[Any]:
        """Access to TSDB consolidation service."""
        return self.service_initializer.tsdb_consolidation_service if self.service_initializer else None

    @property
    def self_observation_service(self) -> Optional[Any]:
        """Access to self observation service."""
        return self.service_initializer.self_observation_service if self.service_initializer else None

    @property
    def visibility_service(self) -> Optional[Any]:
        """Access to visibility service."""
        return self.service_initializer.visibility_service if self.service_initializer else None

    def _ensure_shutdown_event(self) -> None:
        """Ensure shutdown event is created when needed in async context."""
        if self._shutdown_event is None:
            try:
                self._shutdown_event = asyncio.Event()
            except RuntimeError:
                logger.warning("Cannot create shutdown event outside of async context")

    def _ensure_config(self) -> EssentialConfig:
        """Ensure essential_config is available, raise if not."""
        if not self.essential_config:
            raise RuntimeError("Essential config not initialized")
        return self.essential_config

    def request_shutdown(self, reason: str = "Shutdown requested") -> None:
        """Request a graceful shutdown of the runtime."""
        self._ensure_shutdown_event()

        if self._shutdown_event and self._shutdown_event.is_set():
            logger.debug(f"Shutdown already requested, ignoring duplicate request: {reason}")
            return

        logger.critical(f"RUNTIME SHUTDOWN REQUESTED: {reason}")
        self._shutdown_reason = reason

        if self._shutdown_event:
            self._shutdown_event.set()

        # Use the sync version from shutdown_manager utils to avoid async/await issues
        from ciris_engine.logic.utils.shutdown_manager import request_global_shutdown

        request_global_shutdown(f"Runtime: {reason}")

    def _request_shutdown(self, reason: str = "Shutdown requested") -> None:
        """Wrapper used during initialization failures."""
        self.request_shutdown(reason)

    def set_preload_tasks(self, tasks: List[str]) -> None:
        """Set tasks to be loaded after successful WORK state transition."""
        self._preload_tasks = tasks.copy()
        logger.info(f"Set {len(self._preload_tasks)} preload tasks to be loaded after WORK state transition")

    def get_preload_tasks(self) -> List[str]:
        """Get the list of preload tasks."""
        return self._preload_tasks.copy()

    async def initialize(self) -> None:
        """Initialize all components and services."""
        if self._initialized:
            return

        logger.info("Initializing CIRIS Runtime...")

        try:
            # First initialize infrastructure services to get the InitializationService instance
            logger.info("[initialize] Initializing infrastructure services...")
            await self.service_initializer.initialize_infrastructure_services()
            logger.info("[initialize] Infrastructure services initialized")

            # Get the initialization service from service_initializer
            init_manager = self.service_initializer.initialization_service
            if not init_manager:
                raise RuntimeError("InitializationService not available from ServiceInitializer")
            logger.info(f"[initialize] Got initialization service: {init_manager}")

            # Register all initialization steps with proper phases
            logger.info("[initialize] Registering initialization steps...")
            self._register_initialization_steps(init_manager)
            logger.info("[initialize] Steps registered")

            # Run the initialization sequence
            logger.info("[initialize] Running initialization sequence...")
            init_result = await init_manager.initialize()
            logger.info(f"[initialize] Initialization sequence result: {init_result}")

            self._initialized = True
            agent_name = self.agent_identity.agent_id if self.agent_identity else "NO_IDENTITY"
            logger.info(f"CIRIS Runtime initialized successfully with identity '{agent_name}'")

        except asyncio.TimeoutError as e:
            logger.critical(f"Runtime initialization TIMED OUT: {e}", exc_info=True)
            self._initialized = False
            raise
        except Exception as e:
            logger.critical(f"Runtime initialization failed: {e}", exc_info=True)
            if "maintenance" in str(e).lower():
                logger.critical("Database maintenance failure during initialization - system cannot start safely")
            self._initialized = False
            raise

    async def _initialize_identity(self) -> None:
        """Initialize agent identity - create from template on first run, load from graph thereafter."""
        config = self._ensure_config()
        if not self.time_service:
            raise RuntimeError("TimeService not available for IdentityManager")
        self.identity_manager = IdentityManager(config, self.time_service)
        self.agent_identity = await self.identity_manager.initialize_identity()

    def _register_initialization_steps(self, init_manager: Any) -> None:
        """Register all initialization steps with the initialization manager."""

        # Phase 0: INFRASTRUCTURE (NEW - must be first)
        init_manager.register_step(
            phase=InitializationPhase.INFRASTRUCTURE,
            name="Initialize Infrastructure Services",
            handler=self._initialize_infrastructure,
            verifier=self._verify_infrastructure,
            critical=True,
        )

        # Phase 1: DATABASE
        init_manager.register_step(
            phase=InitializationPhase.DATABASE,
            name="Initialize Database",
            handler=self._init_database,
            verifier=self._verify_database_integrity,
            critical=True,
        )

        # Phase 2: MEMORY
        init_manager.register_step(
            phase=InitializationPhase.MEMORY,
            name="Memory Service",
            handler=self._initialize_memory_service,
            verifier=self._verify_memory_service,
            critical=True,
        )

        # Phase 3: IDENTITY
        init_manager.register_step(
            phase=InitializationPhase.IDENTITY,
            name="Agent Identity",
            handler=self._initialize_identity,
            verifier=self._verify_identity_integrity,
            critical=True,
        )

        # Phase 4: SECURITY
        init_manager.register_step(
            phase=InitializationPhase.SECURITY,
            name="Security Services",
            handler=self._initialize_security_services,
            verifier=self._verify_security_services,
            critical=True,
        )

        # Phase 5: SERVICES
        init_manager.register_step(
            phase=InitializationPhase.SERVICES,
            name="Core Services",
            handler=self._initialize_services,
            verifier=self._verify_core_services,
            critical=True,
        )

        # Start adapters and wait for critical services
        init_manager.register_step(
            phase=InitializationPhase.SERVICES, name="Start Adapters", handler=self._start_adapters, critical=True
        )

        # Adapter connections will be started in COMPONENTS phase after services are ready

        # Phase 6: COMPONENTS
        init_manager.register_step(
            phase=InitializationPhase.COMPONENTS, name="Build Components", handler=self._build_components, critical=True
        )

        # Start adapter connections FIRST to establish Discord connection
        init_manager.register_step(
            phase=InitializationPhase.COMPONENTS,
            name="Start Adapter Connections",
            handler=self._start_adapter_connections,
            critical=True,
            timeout=45.0,
        )

        # Adapter services are now registered inside _start_adapter_connections
        # after waiting for adapters to be healthy

        init_manager.register_step(
            phase=InitializationPhase.COMPONENTS,
            name="Initialize Maintenance Service",
            handler=self._initialize_maintenance_service,
            critical=True,
        )

        # Phase 7: VERIFICATION
        init_manager.register_step(
            phase=InitializationPhase.VERIFICATION,
            name="Final System Verification",
            handler=self._final_verification,
            critical=True,
        )

    async def _initialize_infrastructure(self) -> None:  # NOSONAR: Part of async initialization chain
        """Initialize infrastructure services that all other services depend on."""
        # Infrastructure services already initialized in initialize() method
        # This is now just a no-op placeholder for the initialization step
        pass

        # TODO: Fix logging setup that causes CI tests to fail
        # The setup_basic_logging call causes the async task to terminate in CI
        # For now, skip logging setup entirely
        logger.info("[_initialize_infrastructure] Skipping file logging setup temporarily")

    async def _verify_infrastructure(self) -> bool:
        """Verify infrastructure services are operational."""
        # Check that all infrastructure services are running
        if not self.service_initializer.time_service:
            logger.error("TimeService not initialized")
            return False
        if not self.service_initializer.shutdown_service:
            logger.error("ShutdownService not initialized")
            return False
        if not self.service_initializer.initialization_service:
            logger.error("InitializationService not initialized")
            return False
        return True

    async def _init_database(self) -> None:
        """Initialize database and run migrations."""
        # Pass the db path from our config
        db_path = persistence.get_sqlite_db_full_path()
        persistence.initialize_database(db_path)
        persistence.run_migrations()

        if not self.essential_config:
            # Use default essential config if none provided
            self.essential_config = EssentialConfig()
            logger.warning("No config provided, using defaults")

    async def _verify_database_integrity(self) -> bool:
        """Verify database integrity before proceeding."""
        try:
            # Check core tables exist
            conn = persistence.get_db_connection()
            cursor = conn.cursor()

            required_tables = ["tasks", "thoughts", "graph_nodes", "graph_edges"]
            for table in required_tables:
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,))
                if not cursor.fetchone():
                    raise RuntimeError(f"Required table '{table}' missing from database")

            conn.close()
            logger.info("✓ Database integrity verified")
            return True
        except Exception as e:
            logger.error(f"Database integrity check failed: {e}")
            return False

    async def _initialize_memory_service(self) -> None:
        """Initialize memory service early for identity storage."""
        config = self._ensure_config()
        await self.service_initializer.initialize_memory_service(config)

    async def _verify_memory_service(self) -> bool:
        """Verify memory service is operational."""
        return await self.service_initializer.verify_memory_service()

    async def _verify_identity_integrity(self) -> bool:
        """Verify identity was properly established."""
        if not self.identity_manager:
            logger.error("Identity manager not initialized")
            return False
        return await self.identity_manager.verify_identity_integrity()

    async def _initialize_security_services(self) -> None:
        """Initialize security-critical services first."""
        config = self._ensure_config()
        await self.service_initializer.initialize_security_services(config, self.essential_config)

    async def _verify_security_services(self) -> bool:
        """Verify security services are operational."""
        return await self.service_initializer.verify_security_services()

    async def _initialize_services(self) -> None:
        """Initialize all remaining core services."""
        config = self._ensure_config()
        # Identity MUST be established before services can be initialized
        if not self.agent_identity:
            raise RuntimeError("CRITICAL: Cannot initialize services without agent identity")
        await self.service_initializer.initialize_all_services(
            config, self.essential_config, self.agent_identity.agent_id, self.startup_channel_id, self.modules_to_load
        )

        # Load any external modules (e.g. mockllm)
        if self.modules_to_load:
            logger.info(f"Loading {len(self.modules_to_load)} external modules: {self.modules_to_load}")
            await self.service_initializer.load_modules(self.modules_to_load)

        # Update runtime control service with runtime reference
        if self.runtime_control_service:
            if hasattr(self.runtime_control_service, "_set_runtime"):
                self.runtime_control_service._set_runtime(self)
            else:
                self.runtime_control_service.runtime = self
            logger.info("Updated runtime control service with runtime reference")

    async def _verify_core_services(self) -> bool:
        """Verify all core services are operational."""
        return self.service_initializer.verify_core_services()

    async def _initialize_maintenance_service(self) -> None:
        """Initialize the maintenance service and perform startup cleanup."""
        # Verify maintenance service is available
        if not self.maintenance_service:
            raise RuntimeError("Maintenance service was not initialized properly")
        logger.info("Maintenance service verified available")

        # Perform startup maintenance to clean stale tasks
        await self._perform_startup_maintenance()

    async def _start_adapters(self) -> None:
        """Start all adapters."""
        await asyncio.gather(*(adapter.start() for adapter in self.adapters))
        logger.info(f"All {len(self.adapters)} adapters started")

        # Migrate adapter configurations to graph config
        await self._migrate_adapter_configs_to_graph()

    async def _wait_for_critical_services(self, timeout: float) -> None:
        """Wait for services required for agent operation."""
        from ciris_engine.schemas.runtime.enums import ServiceType

        start_time = asyncio.get_event_loop().time()
        last_report_time = start_time

        required_services = [
            (ServiceType.COMMUNICATION, ["send_message"], "Communication (Discord/API/CLI)"),
        ]

        while (asyncio.get_event_loop().time() - start_time) < timeout:
            all_ready = True
            missing_services = []

            for service_type, capabilities, name in required_services:
                if self.service_registry:
                    service = await self.service_registry.get_service(
                        handler="SpeakHandler",  # Use a handler that requires communication
                        service_type=service_type,
                        required_capabilities=capabilities,
                    )
                    if not service:
                        all_ready = False
                        missing_services.append(name)
                    else:
                        # Check if service is actually healthy (connected)
                        if hasattr(service, "is_healthy"):
                            is_healthy = await service.is_healthy()
                            if not is_healthy:
                                all_ready = False
                                missing_services.append(f"{name} (registered but not connected)")
                            else:
                                # Report Discord connection details
                                service_name = service.__class__.__name__ if service else "Unknown"
                                if "Discord" in service_name and not hasattr(self, "_discord_connected_reported"):
                                    # Get Discord client info
                                    if (
                                        hasattr(service, "client")
                                        and service.client
                                        and hasattr(service.client, "user")
                                    ):
                                        user = service.client.user
                                        guilds = service.client.guilds if hasattr(service.client, "guilds") else []
                                        logger.info(f"    ✓ Discord connected as {user} to {len(guilds)} guild(s)")
                                        for guild in guilds[:3]:  # Show first 3 guilds
                                            logger.info(f"      - {guild.name} (ID: {guild.id})")
                                        if len(guilds) > 3:
                                            logger.info(f"      ... and {len(guilds) - 3} more guild(s)")
                                        self._discord_connected_reported = True

            if all_ready:
                return

            # Report progress every 3 seconds
            current_time = asyncio.get_event_loop().time()
            if current_time - last_report_time >= 3.0:
                elapsed = current_time - start_time
                logger.info(f"    ⏳ Still waiting for: {', '.join(missing_services)} ({elapsed:.1f}s elapsed)")
                last_report_time = current_time

            await asyncio.sleep(0.5)

        # Timeout reached
        raise TimeoutError(f"Critical services not available after {timeout}s. Missing: {', '.join(missing_services)}")

    async def _migrate_adapter_configs_to_graph(self) -> None:
        """Migrate adapter configurations to graph config service."""
        if not self.service_initializer or not self.service_initializer.config_service:
            logger.warning("Cannot migrate adapter configs - GraphConfigService not available")
            return

        config_service = self.service_initializer.config_service

        # Migrate bootstrap adapter configs
        for adapter_type, adapter_config in self.adapter_configs.items():
            try:
                # Determine adapter ID (handle instance-specific types like "api:8081")
                adapter_id = adapter_type
                if ":" in adapter_type:
                    base_type, instance_id = adapter_type.split(":", 1)
                    adapter_id = f"{base_type}_{instance_id}"
                else:
                    # For bootstrap adapters without instance ID, use a standard naming
                    adapter_id = f"{adapter_type}_bootstrap"

                # Store the full config object
                await config_service.set_config(
                    key=f"adapter.{adapter_id}.config",
                    value=adapter_config.model_dump() if hasattr(adapter_config, "model_dump") else adapter_config,
                    updated_by="system_bootstrap",
                )

                # Also store individual config values for easy access
                config_dict = adapter_config.model_dump() if hasattr(adapter_config, "model_dump") else adapter_config
                if isinstance(config_dict, dict):
                    for key, value in config_dict.items():
                        await config_service.set_config(
                            key=f"adapter.{adapter_id}.{key}", value=value, updated_by="system_bootstrap"
                        )

                logger.info(f"Migrated adapter config for {adapter_id} to graph")

            except Exception as e:
                logger.error(f"Failed to migrate adapter config for {adapter_type}: {e}")

    async def _final_verification(self) -> None:
        """Perform final system verification."""
        # Don't check initialization status here - we're still IN the initialization process
        # Just verify the critical components are ready

        # Verify identity loaded
        if not self.agent_identity:
            raise RuntimeError("No agent identity established")

        # Log final status
        logger.info("=" * 60)
        logger.info("CIRIS Agent Pre-Wakeup Verification Complete")
        logger.info(f"Identity: {self.agent_identity.agent_id}")
        logger.info(f"Purpose: {self.agent_identity.core_profile.description}")
        logger.info(f"Capabilities: {len(self.agent_identity.permitted_actions)} allowed")
        # Count all registered services
        service_count = 0
        if self.service_registry:
            registry_info = self.service_registry.get_provider_info()
            # Count services from the 'services' key (new structure)
            for service_list in registry_info.get("services", {}).values():
                service_count += len(service_list)

        logger.info(f"Services: {service_count} registered")
        logger.info("=" * 60)

    async def _perform_startup_maintenance(self) -> None:
        """Perform database cleanup at startup."""
        if self.maintenance_service:
            try:
                logger.info("Starting critical database maintenance...")
                await self.maintenance_service.perform_startup_cleanup()
                logger.info("Database maintenance completed successfully")
            except Exception as e:
                logger.critical(f"CRITICAL ERROR: Database maintenance failed during startup: {e}")
                logger.critical("Database integrity cannot be guaranteed - initiating graceful shutdown")
                self._request_shutdown(f"Critical database maintenance failure: {e}")
                raise RuntimeError(f"Database maintenance failure: {e}") from e
        else:
            logger.critical("CRITICAL ERROR: No maintenance service available during startup")
            logger.critical("Database integrity cannot be guaranteed - initiating graceful shutdown")
            self._request_shutdown("No maintenance service available")
            raise RuntimeError("No maintenance service available")

    async def _clean_runtime_configs(self) -> None:
        """Clean up runtime-specific configuration from previous runs."""
        if not self.config_service:
            logger.warning("Config service not available - skipping runtime config cleanup")
            return

        try:
            logger.info("Cleaning up runtime-specific configurations...")

            # Get all config entries
            all_configs = await self.config_service.list_configs()

            runtime_config_patterns = [
                "adapter.",  # Adapter configurations
                "runtime.",  # Runtime-specific settings
                "session.",  # Session-specific data
                "temp.",  # Temporary configurations
            ]

            deleted_count = 0

            for key, value in all_configs.items():
                # Check if this is a runtime-specific config
                is_runtime_config = any(key.startswith(pattern) for pattern in runtime_config_patterns)

                if is_runtime_config:
                    # Get the actual config node to check if it should be deleted
                    config_node = await self.config_service.get_config(key)
                    if config_node:
                        # Skip configs created by system_bootstrap (essential configs)
                        if config_node.updated_by == "system_bootstrap":
                            logger.debug(f"Preserving bootstrap config: {key}")
                            continue

                        # Convert to GraphNode and use memory service to forget it
                        graph_node = config_node.to_graph_node()
                        await self.config_service.graph.forget(graph_node)
                        deleted_count += 1
                        logger.debug(f"Deleted runtime config node: {key}")

            if deleted_count > 0:
                logger.info(f"Cleaned up {deleted_count} runtime-specific configuration entries from previous runs")
            else:
                logger.info("No runtime-specific configuration entries to clean up")

        except Exception as e:
            logger.error(f"Failed to clean up runtime config: {e}", exc_info=True)
            # Non-critical - don't fail initialization

    async def _register_adapter_services(self) -> None:
        """Register services provided by the loaded adapters."""
        if not self.service_registry:
            logger.error("ServiceRegistry not initialized. Cannot register adapter services.")
            return

        for adapter in self.adapters:
            try:
                # Generate authentication token for adapter - REQUIRED for security
                adapter_type = adapter.__class__.__name__.lower().replace("adapter", "")
                adapter_info = {
                    "instance_id": str(id(adapter)),
                    "startup_time": (
                        self.time_service.now().isoformat()
                        if self.time_service
                        else datetime.now(timezone.utc).isoformat()
                    ),
                }

                # Get channel-specific info if available
                if hasattr(adapter, "get_channel_info"):
                    adapter_info.update(adapter.get_channel_info())

                # Get authentication service from service initializer
                auth_service = self.service_initializer.auth_service if self.service_initializer else None

                # Create adapter token using the proper authentication service
                auth_token = (
                    await auth_service._create_channel_token_for_adapter(adapter_type, adapter_info)
                    if auth_service
                    else None
                )

                # Set token on adapter if it has the method
                if hasattr(adapter, "set_auth_token") and auth_token:
                    adapter.set_auth_token(auth_token)

                if auth_token:
                    logger.info(f"Generated authentication token for {adapter_type} adapter")

                registrations = adapter.get_services_to_register()
                for reg in registrations:
                    if not isinstance(reg, AdapterServiceRegistration):
                        logger.error(
                            f"Adapter {adapter.__class__.__name__} provided an invalid AdapterServiceRegistration object: {reg}"
                        )
                        continue

                    # No need to check Service base class - adapters implement protocol interfaces

                    # All services are global now
                    self.service_registry.register_service(
                        service_type=reg.service_type,  # Use the enum directly
                        provider=reg.provider,
                        priority=reg.priority,
                        capabilities=reg.capabilities,
                    )
                    logger.info(f"Registered {reg.service_type.value} from {adapter.__class__.__name__}")
            except Exception as e:
                logger.error(f"Error registering services for adapter {adapter.__class__.__name__}: {e}", exc_info=True)

    async def _build_components(self) -> None:
        """Build all processing components."""
        logger.info("[_build_components] Starting component building...")
        logger.info(f"[_build_components] llm_service: {self.llm_service}")
        logger.info(f"[_build_components] service_registry: {self.service_registry}")
        logger.info(f"[_build_components] service_initializer: {self.service_initializer}")

        if self.service_initializer:
            logger.info(f"[_build_components] service_initializer.llm_service: {self.service_initializer.llm_service}")
            logger.info(
                f"[_build_components] service_initializer.service_registry: {self.service_initializer.service_registry}"
            )

        try:
            self.component_builder = ComponentBuilder(self)
            logger.info("[_build_components] ComponentBuilder created successfully")

            self.agent_processor = self.component_builder.build_all_components()
            logger.info(f"[_build_components] agent_processor created: {self.agent_processor}")
        except Exception as e:
            logger.error(f"[_build_components] Failed to build components: {e}", exc_info=True)
            raise

        # Register core services after components are built
        self._register_core_services()
        logger.info("[_build_components] Component building completed")

    async def _start_adapter_connections(self) -> None:
        """Start adapter connections and wait for them to be ready."""
        logger.info("Starting adapter connections...")

        # Report adapter configuration details
        for adapter in self.adapters:
            adapter_name = adapter.__class__.__name__

            # Report adapter details for Discord
            if adapter_name == "DiscordPlatform" and hasattr(adapter, "config"):
                config = adapter.config
                if hasattr(config, "monitored_channel_ids"):
                    logger.info(f"  → {adapter_name} configuration:")
                    logger.info(f"    Monitored channels: {config.monitored_channel_ids}")
                if hasattr(config, "server_id"):
                    logger.info(f"    Target server: {config.server_id}")
                if hasattr(config, "bot_token") and config.bot_token:
                    logger.info(f"    Bot token: ...{config.bot_token[-10:]}")

        # Create a dummy agent task that represents the future agent processor
        # This allows adapters to start their lifecycle properly
        self._agent_placeholder = asyncio.Event()
        agent_placeholder_task = asyncio.create_task(self._agent_placeholder.wait(), name="AgentPlaceholderTask")

        # Start adapter lifecycles
        self._adapter_tasks = []
        for adapter in self.adapters:
            adapter_name = adapter.__class__.__name__

            if hasattr(adapter, "run_lifecycle"):
                lifecycle_task = asyncio.create_task(
                    adapter.run_lifecycle(agent_placeholder_task), name=f"{adapter_name}LifecycleTask"
                )
                self._adapter_tasks.append(lifecycle_task)
                logger.info(f"  → Starting {adapter_name} lifecycle...")

        # Wait for adapters to connect and register services with retries
        logger.info("  ⏳ Waiting for adapter connections to establish...")
        start_time = asyncio.get_event_loop().time()
        timeout = 30.0
        services_registered = False

        while (asyncio.get_event_loop().time() - start_time) < timeout:
            # Check if Discord adapters are ready
            all_adapters_ready = True
            for adapter in self.adapters:
                adapter_name = adapter.__class__.__name__
                if "Discord" in adapter_name:
                    # Check health directly on the adapter (DiscordPlatform)
                    if hasattr(adapter, "is_healthy"):
                        try:
                            is_healthy = await adapter.is_healthy()
                            if not is_healthy:
                                all_adapters_ready = False
                                logger.debug(f"  ⏳ {adapter_name} not yet healthy, waiting...")
                            else:
                                logger.info(f"  ✓ {adapter_name} is healthy and connected")
                        except Exception as e:
                            all_adapters_ready = False
                            logger.debug(f"  ⏳ {adapter_name} health check failed: {e}")
                    else:
                        all_adapters_ready = False
                        logger.warning(f"  ⚠️  {adapter_name} has no is_healthy method")

            if all_adapters_ready and not services_registered:
                # Register adapter services once adapters are ready
                logger.info("  → Registering adapter services...")
                await self._register_adapter_services()
                services_registered = True
                # Give services a moment to settle after registration
                await asyncio.sleep(0.1)
                # Continue to wait for services to be available in registry

            if services_registered:
                # Check if services are actually available
                service_available = False
                if self.service_registry:
                    test_service = await self.service_registry.get_service(
                        handler="test", service_type=ServiceType.COMMUNICATION, required_capabilities=["send_message"]
                    )
                    if test_service:
                        service_available = True

                if service_available:
                    logger.info("  ✅ All adapters connected and services registered!")
                    break

            # Wait a bit before checking again
            await asyncio.sleep(0.5)

        if not services_registered:
            raise RuntimeError("Failed to establish adapter connections within timeout")

        # Final verification with the existing wait method
        await self._wait_for_critical_services(timeout=5.0)

    def _register_core_services(self) -> None:
        """Register core services in the service registry."""
        self.service_initializer.register_core_services()

    def _build_action_dispatcher(self, dependencies: Any) -> ActionDispatcher:
        """Build action dispatcher. Override in subclasses for custom sinks."""
        config = self._ensure_config()
        # Create BusManager for action handlers
        from ciris_engine.logic.buses import BusManager

        if not self.service_registry:
            raise RuntimeError("Service registry not initialized")
        logger.info(f"[AUDIT DEBUG] self.service_initializer exists: {self.service_initializer is not None}")
        if self.service_initializer:
            logger.info(f"[AUDIT DEBUG] service_initializer.audit_service: {self.service_initializer.audit_service}")
        logger.info(f"[AUDIT DEBUG] Creating BusManager with audit_service={self.audit_service}")
        logger.info(f"[AUDIT DEBUG] self.audit_service type: {type(self.audit_service)}")
        logger.info(f"[AUDIT DEBUG] self.audit_service is None: {self.audit_service is None}")

        assert self.service_registry is not None
        # BusManager requires TimeServiceProtocol, not Optional[TimeService]
        if self.time_service is None:
            raise RuntimeError("TimeService must be initialized before creating BusManager")

        bus_manager = BusManager(
            self.service_registry,
            time_service=self.time_service,
            telemetry_service=self.telemetry_service,
            audit_service=self.audit_service,
        )

        return build_action_dispatcher(
            bus_manager=bus_manager,
            time_service=self.time_service,
            shutdown_callback=dependencies.shutdown_callback,
            max_rounds=config.workflow.max_rounds,
            telemetry_service=self.telemetry_service,
            secrets_service=self.secrets_service,
        )

    async def run(self, num_rounds: Optional[int] = None) -> None:
        """Run the agent processing loop with shutdown monitoring."""
        if not self._initialized:
            await self.initialize()

        try:
            # Start multi-service sink processing as background task
            if self.bus_manager:
                _sink_task = asyncio.create_task(self.bus_manager.start())
                logger.info("Started multi-service sink as background task")

            if not self.agent_processor:
                raise RuntimeError("Agent processor not initialized")

            effective_num_rounds = num_rounds if num_rounds is not None else DEFAULT_NUM_ROUNDS
            logger.info(
                f"Starting agent processing (num_rounds={effective_num_rounds if effective_num_rounds != -1 else 'infinite'})..."
            )

            # Services are already initialized and adapters are connected from initialization phase
            # Now start the agent processor
            logger.info("Starting agent processor...")
            agent_task = asyncio.create_task(
                self.agent_processor.start_processing(effective_num_rounds), name="AgentProcessorTask"
            )

            # Use existing adapter tasks from initialization
            adapter_tasks = getattr(self, "_adapter_tasks", [])
            if adapter_tasks:
                logger.info(f"Using {len(adapter_tasks)} existing adapter lifecycle tasks from initialization")

                # Signal the placeholder to complete, transitioning adapters to monitor the real agent task
                if hasattr(self, "_agent_placeholder"):
                    logger.info("Transitioning adapters from placeholder to real agent task...")
                    self._agent_placeholder.set()

            # Monitor agent_task, all adapter_tasks, and shutdown events
            self._ensure_shutdown_event()
            shutdown_event_task = None
            if self._shutdown_event:
                shutdown_event_task = asyncio.create_task(self._shutdown_event.wait(), name="ShutdownEventWait")

            global_shutdown_task = asyncio.create_task(wait_for_global_shutdown_async(), name="GlobalShutdownWait")
            all_tasks: List[asyncio.Task[Any]] = [agent_task, *adapter_tasks, global_shutdown_task]
            if shutdown_event_task:
                all_tasks.append(shutdown_event_task)

            # Keep monitoring until agent task completes
            shutdown_logged = False
            while not agent_task.done():
                done, pending = await asyncio.wait(all_tasks, return_when=asyncio.FIRST_COMPLETED)

                # Remove completed tasks from all_tasks to avoid re-processing
                all_tasks = [t for t in all_tasks if t not in done]

                # Handle task completion and cancellation logic
                if (self._shutdown_event and self._shutdown_event.is_set()) or is_global_shutdown_requested():
                    if not shutdown_logged:
                        shutdown_reason = (
                            self._shutdown_reason or self._shutdown_manager.get_shutdown_reason() or "Unknown reason"
                        )
                        logger.critical(f"GRACEFUL SHUTDOWN TRIGGERED: {shutdown_reason}")
                        shutdown_logged = True
                    # Don't cancel anything! Let the graceful shutdown process handle it
                    # The agent processor will transition to SHUTDOWN state and handle everything
                    # Continue the loop - wait for agent to finish its shutdown process
                elif agent_task in done:
                    logger.info(
                        f"Agent processing task completed. Result: {agent_task.result() if not agent_task.cancelled() else 'Cancelled'}"
                    )
                    # If agent task finishes (e.g. num_rounds reached), signal shutdown for adapters
                    self.request_shutdown("Agent processing completed normally.")
                    for (
                        ad_task
                    ) in (
                        adapter_tasks
                    ):  # Adapters should react to agent_task completion via its cancellation or by observing shutdown event
                        if not ad_task.done():
                            ad_task.cancel()  # Or rely on their run_lifecycle to exit when agent_task is done
                    break  # Exit the while loop
                else:  # One of the adapter tasks finished, or an unexpected task completion
                    for task in done:
                        if task not in [shutdown_event_task, global_shutdown_task]:  # Don't log for event tasks
                            task_name = task.get_name() if hasattr(task, "get_name") else "Unnamed task"
                            logger.info(
                                f"Task '{task_name}' completed. Result: {task.result() if not task.cancelled() else 'Cancelled'}"
                            )
                            if task.exception():
                                logger.error(
                                    f"Task '{task_name}' raised an exception: {task.exception()}",
                                    exc_info=task.exception(),
                                )
                                self.request_shutdown(f"Task {task_name} failed: {task.exception()}")

            # Await all pending tasks (including cancellations)
            if pending:
                await asyncio.wait(pending, return_when=asyncio.ALL_COMPLETED)

            # Execute any pending global shutdown handlers
            if (self._shutdown_event and self._shutdown_event.is_set()) or is_global_shutdown_requested():
                await self._shutdown_manager.execute_async_handlers()

        except KeyboardInterrupt:
            logger.info("Received interrupt signal. Requesting shutdown.")
            self.request_shutdown("KeyboardInterrupt")
            # Re-raise to allow outer event loop (if any) to catch it, or ensure finally block runs
            # For this structure, self.request_shutdown and then letting it flow to finally is fine.
        except Exception as e:
            logger.error(f"Runtime error: {e}", exc_info=True)
        finally:
            logger.debug("Runtime.run() entering finally block")
            await self.shutdown()
            logger.debug("Runtime.run() exiting finally block")

    async def shutdown(self) -> None:
        """Gracefully shutdown all services with consciousness preservation."""
        # Prevent double shutdown
        if hasattr(self, "_shutdown_complete") and self._shutdown_complete:
            logger.debug("Shutdown already completed, skipping...")
            return

        logger.info("Shutting down CIRIS Runtime...")

        # Set flag to indicate we're in shutdown mode
        # This prevents services from being marked unhealthy during shutdown
        if self.service_registry:
            self.service_registry._shutdown_mode = True

        # Import and use the graceful shutdown manager
        from ciris_engine.logic.utils.shutdown_manager import get_shutdown_manager

        shutdown_manager = get_shutdown_manager()

        # First, stop all scheduled services and feedback loops
        # This prevents them from trying to use services during shutdown
        logger.info("Stopping scheduled services and feedback loops...")
        scheduled_services = []
        if self.service_registry:
            all_services = self.service_registry.get_all_services()
            for service in all_services:
                # Check if it's a scheduled service (has _task attribute from BaseScheduledService)
                # or has _scheduler attribute (other scheduled services)
                if hasattr(service, "_task") or hasattr(service, "_scheduler"):
                    scheduled_services.append(service)

        # Stop all scheduled services first
        for service in scheduled_services:
            try:
                service_name = service.__class__.__name__
                logger.info(f"Stopping scheduled tasks for {service_name}")
                if hasattr(service, "_task") and service._task:
                    # Cancel the task directly
                    service._task.cancel()
                    try:
                        await service._task
                    except asyncio.CancelledError:
                        # Only re-raise if we're being cancelled ourselves
                        if asyncio.current_task() and asyncio.current_task().cancelled():
                            raise
                        # Otherwise, this is a normal stop - don't propagate the cancellation
                elif hasattr(service, "stop_scheduler"):
                    await service.stop_scheduler()
            except Exception as e:
                logger.error(f"Error stopping scheduled tasks for {service.__class__.__name__}: {e}")

        # Give scheduled tasks a moment to stop
        if scheduled_services:
            logger.info(f"Stopped {len(scheduled_services)} scheduled services, waiting for tasks to complete...")
            await asyncio.sleep(0.5)

        # Register our final maintenance as a shutdown handler
        async def run_final_maintenance() -> None:
            """Run final maintenance and consolidation before services stop."""
            logger.info("=" * 60)
            logger.info("Running final maintenance tasks...")

            # 1. Run final database maintenance
            if hasattr(self, "maintenance_service") and self.maintenance_service:
                try:
                    logger.info("Running final database maintenance before shutdown...")
                    await self.maintenance_service.perform_startup_cleanup()
                    logger.info("Final database maintenance completed")
                except Exception as e:
                    logger.error(f"Failed to run final database maintenance: {e}")

            # 2. Run final TSDB consolidation
            if hasattr(self, "service_initializer") and self.service_initializer:
                tsdb_service = getattr(self.service_initializer, "tsdb_consolidation_service", None)
                if tsdb_service:
                    try:
                        logger.info("Running final TSDB consolidation before shutdown...")
                        await tsdb_service._run_consolidation()
                        logger.info("Final TSDB consolidation completed")
                    except Exception as e:
                        logger.error(f"Failed to run final TSDB consolidation: {e}")

            logger.info("Final maintenance tasks completed")
            logger.info("=" * 60)

        # First run our maintenance handler
        await run_final_maintenance()

        # Execute any other registered async shutdown handlers
        try:
            await shutdown_manager.execute_async_handlers()
        except Exception as e:
            logger.error(f"Error executing shutdown handlers: {e}")

        # Preserve agent consciousness if identity exists
        if hasattr(self, "agent_identity") and self.agent_identity:
            try:
                await self._preserve_shutdown_consciousness()
            except Exception as e:
                logger.error(f"Failed to preserve consciousness during shutdown: {e}")

        logger.info("Initiating shutdown sequence for CIRIS Runtime...")
        self._ensure_shutdown_event()
        if self._shutdown_event:
            self._shutdown_event.set()  # Ensure event is set for any waiting components

        # Initiate graceful shutdown negotiation
        if self.agent_processor and hasattr(self.agent_processor, "state_manager"):
            current_state = self.agent_processor.state_manager.get_state()

            # Only do negotiation if not already in SHUTDOWN state
            if current_state != AgentState.SHUTDOWN:
                try:
                    logger.info("Initiating graceful shutdown negotiation...")

                    # Check if we can transition to shutdown state
                    if self.agent_processor.state_manager.can_transition_to(AgentState.SHUTDOWN):
                        logger.info(f"Transitioning from {current_state} to SHUTDOWN state")
                        # Use the state manager directly to transition
                        self.agent_processor.state_manager.transition_to(AgentState.SHUTDOWN)

                        # If processing loop is running, just signal it to stop
                        # It will handle the SHUTDOWN state in its next iteration
                        if self.agent_processor._processing_task and not self.agent_processor._processing_task.done():
                            logger.info("Processing loop is running, signaling stop")
                            # Just set the stop event, don't call stop_processing yet
                            if hasattr(self.agent_processor, "_stop_event") and self.agent_processor._stop_event:
                                self.agent_processor._stop_event.set()
                        else:
                            # Processing loop not running, we need to handle shutdown ourselves
                            logger.info("Processing loop not running, executing shutdown processor directly")
                            if (
                                hasattr(self.agent_processor, "shutdown_processor")
                                and self.agent_processor.shutdown_processor
                            ):
                                # Run a few rounds of shutdown processing
                                for round_num in range(5):
                                    try:
                                        result = await self.agent_processor.shutdown_processor.process(round_num)
                                        if self.agent_processor.shutdown_processor.shutdown_complete:
                                            break
                                    except Exception as e:
                                        logger.error(f"Error in shutdown processor: {e}", exc_info=True)
                                        break
                                    await asyncio.sleep(0.1)
                    else:
                        logger.error(f"Cannot transition from {current_state} to SHUTDOWN state")

                    # Wait a bit for ShutdownProcessor to complete
                    # The processor will set shutdown_complete flag
                    max_wait = 5.0  # Reduced from 30s to 5s for faster shutdown
                    start_time = asyncio.get_event_loop().time()

                    while (asyncio.get_event_loop().time() - start_time) < max_wait:
                        if (
                            hasattr(self.agent_processor, "shutdown_processor")
                            and self.agent_processor.shutdown_processor
                        ):
                            if self.agent_processor.shutdown_processor.shutdown_complete:
                                result = self.agent_processor.shutdown_processor.shutdown_result  # type: ignore[assignment]
                                if result and hasattr(result, "get") and result.get("status") == "rejected":
                                    logger.warning(f"Shutdown rejected by agent: {result.get('reason')}")
                                    # Proceed with shutdown - emergency shutdown API provides override mechanism
                                break
                        await asyncio.sleep(0.1)  # Reduced from 0.5s to 0.1s for faster response

                    logger.debug("Shutdown negotiation complete or timed out")
                except Exception as e:
                    logger.error(f"Error during shutdown negotiation: {e}")

        # Stop multi-service sink
        if self.bus_manager:
            try:
                logger.debug("Stopping multi-service sink...")
                # Add timeout to prevent hanging forever
                await asyncio.wait_for(self.bus_manager.stop(), timeout=10.0)
                logger.debug("Multi-service sink stopped.")
            except asyncio.TimeoutError:
                logger.error("Timeout stopping multi-service sink after 10 seconds")
            except Exception as e:
                logger.error(f"Error stopping multi-service sink: {e}")

        logger.debug(f"Stopping {len(self.adapters)} adapters...")
        adapter_stop_results = await asyncio.gather(
            *(adapter.stop() for adapter in self.adapters if hasattr(adapter, "stop")), return_exceptions=True
        )
        for i, stop_result in enumerate(adapter_stop_results):
            if isinstance(stop_result, Exception):
                logger.error(
                    f"Error stopping adapter {self.adapters[i].__class__.__name__}: {stop_result}", exc_info=stop_result
                )
        logger.debug("Adapters stopped.")

        logger.debug("Stopping core services...")

        # Get all registered services dynamically
        all_registered_services = []
        if self.service_registry:
            all_registered_services = self.service_registry.get_all_services()
            logger.info(f"Found {len(all_registered_services)} registered services to stop")

        # Build a comprehensive list of services to stop
        # This includes both registered services and direct references
        services_to_stop = []
        seen_ids = set()

        # Add all registered services
        for service in all_registered_services:
            service_id = id(service)
            if service_id not in seen_ids and hasattr(service, "stop"):
                seen_ids.add(service_id)
                services_to_stop.append(service)

        # Also add any services we have direct references to (in case they weren't registered)
        # This ensures backward compatibility
        direct_services = [
            # From service_initializer
            getattr(self.service_initializer, "tsdb_consolidation_service", None),
            getattr(self.service_initializer, "task_scheduler_service", None),
            getattr(self.service_initializer, "incident_management_service", None),
            getattr(self.service_initializer, "resource_monitor_service", None),
            getattr(self.service_initializer, "config_service", None),
            getattr(self.service_initializer, "auth_service", None),
            getattr(self.service_initializer, "runtime_control_service", None),
            getattr(self.service_initializer, "self_observation_service", None),
            getattr(self.service_initializer, "visibility_service", None),
            getattr(self.service_initializer, "core_tool_service", None),
            getattr(self.service_initializer, "wa_auth_system", None),
            getattr(self.service_initializer, "initialization_service", None),
            getattr(self.service_initializer, "shutdown_service", None),
            getattr(self.service_initializer, "time_service", None),
            # From runtime
            self.maintenance_service,
            self.transaction_orchestrator,
            self.agent_config_service,
            self.adaptive_filter_service,
            self.telemetry_service,
            self.audit_service,
            self.llm_service,
            self.secrets_service,
            self.memory_service,
        ]

        for service in direct_services:
            if service:
                service_id = id(service)
                if service_id not in seen_ids and hasattr(service, "stop"):
                    seen_ids.add(service_id)
                    services_to_stop.append(service)

        # Sort services by priority for shutdown (reverse order)
        # Infrastructure services should be stopped last
        def get_shutdown_priority(service: Any) -> int:
            service_name = service.__class__.__name__
            # Priority 0: Services that depend on others
            if "TSDB" in service_name or "Consolidation" in service_name:
                return 0
            elif "Task" in service_name or "Scheduler" in service_name:
                return 1
            elif "Incident" in service_name or "Monitor" in service_name:
                return 2
            # Priority 3: Application services
            elif "Adaptive" in service_name or "Filter" in service_name:
                return 3
            elif "Tool" in service_name or "Control" in service_name:
                return 4
            elif "Observation" in service_name or "Visibility" in service_name:
                return 5
            # Priority 6: Core services
            elif "Telemetry" in service_name or "Audit" in service_name:
                return 6
            elif "LLM" in service_name or "Auth" in service_name:
                return 7
            elif "Config" in service_name:
                return 8
            # Priority 9: Fundamental services
            elif "Memory" in service_name or "Secrets" in service_name:
                return 9
            # Priority 10: Infrastructure services (stop last)
            elif "Time" in service_name:
                return 11
            elif "Shutdown" in service_name:
                return 12
            elif "Initialization" in service_name:
                return 10
            else:
                return 5  # Default priority

        services_to_stop.sort(key=get_shutdown_priority)

        # Stop services that have a stop method
        stop_tasks = []
        service_names = []
        for service in services_to_stop:
            if service and hasattr(service, "stop"):
                # Check if stop is async or sync
                stop_method = service.stop()
                if asyncio.iscoroutine(stop_method):
                    # Async stop method
                    task = asyncio.create_task(stop_method)
                    stop_tasks.append(task)
                else:
                    # Sync stop method - already completed
                    # No need to add to tasks
                    pass
                service_names.append(service.__class__.__name__)

        if stop_tasks:
            logger.info(f"Stopping {len(stop_tasks)} services: {', '.join(service_names)}")

            # Use wait with timeout instead of wait_for to better track individual tasks
            done, pending = await asyncio.wait(stop_tasks, timeout=10.0)

            if pending:
                # Some tasks didn't complete
                logger.error(f"Service shutdown timed out after 10 seconds. {len(pending)} services still running.")
                hanging_services = []

                for task in pending:
                    # Find which service this task belongs to
                    try:
                        idx = stop_tasks.index(task)
                        service_name = service_names[idx]
                        hanging_services.append(service_name)
                        logger.warning(f"Service {service_name} did not stop in time")
                    except ValueError:
                        logger.warning("Unknown service task did not stop in time")

                    # Cancel the hanging task
                    task.cancel()

                logger.error(f"Hanging services: {', '.join(hanging_services)}")

                # Try to await cancelled tasks to clean up properly
                if pending:
                    await asyncio.gather(*pending, return_exceptions=True)
            else:
                logger.info(
                    f"All {len(stop_tasks)} services stopped successfully (Total services: {len(services_to_stop)})"
                )

            # Check for any errors in completed tasks
            for task in done:
                if task.done() and not task.cancelled():
                    try:
                        result = task.result()
                        if isinstance(result, Exception):
                            idx = stop_tasks.index(task)
                            logger.error(f"Service {service_names[idx]} stop error: {result}")
                    except Exception as e:
                        logger.error(f"Error checking task result: {e}")

        # Clear service registry
        if self.service_registry:
            try:
                self.service_registry.clear_all()
                logger.debug("Service registry cleared.")
            except Exception as e:
                logger.error(f"Error clearing service registry: {e}")

        logger.info("CIRIS Runtime shutdown complete")

        # Mark shutdown as truly complete
        self._shutdown_complete = True
        logger.debug("Shutdown method returning")

    async def _preserve_shutdown_consciousness(self) -> None:
        """Preserve agent state for future reactivation."""
        try:
            from ciris_engine.schemas.runtime.extended import ShutdownContext
            from ciris_engine.schemas.services.graph_core import GraphNode, GraphNodeAttributes, GraphScope, NodeType

            # Create shutdown context
            final_state = {
                "active_tasks": persistence.count_active_tasks(),
                "pending_thoughts": persistence.count_pending_thoughts_for_active_tasks(),
                "runtime_duration": 0,
            }

            if hasattr(self, "_start_time"):
                final_state["runtime_duration"] = (
                    (self.time_service.now() - self._start_time).total_seconds() if self.time_service else 0
                )

            shutdown_context = ShutdownContext(
                is_terminal=False,
                reason=self._shutdown_reason or "Graceful shutdown",
                initiated_by="runtime",
                allow_deferral=False,
                expected_reactivation=None,
                agreement_context=None,
            )

            # Create memory node for shutdown
            shutdown_node = GraphNode(
                id=f"shutdown_{self.time_service.now().isoformat() if self.time_service else datetime.now(timezone.utc).isoformat()}",
                type=NodeType.AGENT,
                scope=GraphScope.IDENTITY,
                attributes=GraphNodeAttributes(
                    created_by="runtime_shutdown", tags=["shutdown", "consciousness_preservation"]
                ),
            )

            # Store in memory service
            if self.memory_service:
                await self.memory_service.memorize(shutdown_node)
                logger.info(f"Preserved shutdown consciousness: {shutdown_node.id}")

                # Update identity with shutdown memory reference
                if self.agent_identity and hasattr(self.agent_identity, "core_profile"):
                    self.agent_identity.core_profile.last_shutdown_memory = shutdown_node.id

                    # Increment reactivation count in metadata if it exists
                    if hasattr(self.agent_identity, "identity_metadata"):
                        self.agent_identity.identity_metadata.modification_count += 1

                    # Save updated identity using identity manager
                    if self.identity_manager:
                        await self.identity_manager._save_identity_to_graph(self.agent_identity)
                        logger.debug("Agent identity updates saved to persistence layer")
                    else:
                        logger.debug("Agent identity updates stored in memory graph")

        except Exception as e:
            logger.error(f"Failed to preserve shutdown consciousness: {e}")
