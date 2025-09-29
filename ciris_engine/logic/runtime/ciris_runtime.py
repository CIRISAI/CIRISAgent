"""
ciris_engine/runtime/ciris_runtime.py

New simplified runtime that properly orchestrates all components.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from ciris_engine.schemas.runtime.bootstrap import RuntimeBootstrapConfig

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
from ciris_engine.schemas.runtime.adapter_management import AdapterConfig
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
        bootstrap: Optional["RuntimeBootstrapConfig"] = None,
        startup_channel_id: Optional[str] = None,
        adapter_configs: Optional[Dict[str, AdapterConfig]] = None,
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

        # Import RuntimeBootstrapConfig here to avoid circular imports
        from ciris_engine.schemas.runtime.bootstrap import RuntimeBootstrapConfig

        # Use bootstrap config if provided, otherwise construct from legacy parameters
        if bootstrap is not None:
            self.bootstrap = bootstrap
            # Extract values from bootstrap config
            self.essential_config = essential_config or EssentialConfig()
            self.startup_channel_id = bootstrap.startup_channel_id or ""
            self.adapter_configs = bootstrap.adapter_overrides
            self.modules_to_load = bootstrap.modules
            self.debug = bootstrap.debug
            self._preload_tasks = bootstrap.preload_tasks
        else:
            # Legacy parameter handling for backward compatibility
            self.essential_config = essential_config
            self.startup_channel_id = startup_channel_id or ""
            self.adapter_configs = adapter_configs or {}
            self.modules_to_load = kwargs.get("modules", [])
            self.debug = kwargs.get("debug", False)
            self._preload_tasks = []

            # Create bootstrap config from legacy parameters for internal use
            from ciris_engine.schemas.runtime.adapter_management import AdapterLoadRequest
            adapter_load_requests = [
                AdapterLoadRequest(adapter_type=atype, adapter_id=atype, auto_start=True)
                for atype in adapter_types
            ]
            self.bootstrap = RuntimeBootstrapConfig(
                adapters=adapter_load_requests,
                adapter_overrides=self.adapter_configs,
                modules=self.modules_to_load,
                startup_channel_id=self.startup_channel_id,
                debug=self.debug,
                preload_tasks=self._preload_tasks,
            )

        self.adapters: List[BaseAdapterProtocol] = []

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
                adapter_instance = adapter_class(self, **adapter_kwargs)
                self.adapters.append(adapter_instance)
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
            # CRITICAL: Ensure all directories exist with correct permissions BEFORE anything else
            from ciris_engine.logic.utils.directory_setup import (
                DirectorySetupError,
                setup_application_directories,
                validate_directories,
            )

            try:
                # In production (when running in container), validate only
                # In development, create directories if needed
                import os

                is_production = os.environ.get("CIRIS_ENV", "dev").lower() == "prod"

                if is_production:
                    logger.info("Production environment detected - validating directories...")
                    validate_directories()
                else:
                    logger.info("Development environment - setting up directories...")
                    setup_application_directories(essential_config=self.essential_config)

            except DirectorySetupError as e:
                logger.critical(f"DIRECTORY SETUP FAILED: {e}")
                # This will already have printed clear error messages to stderr
                # and potentially exited the process
                raise RuntimeError(f"Cannot start: Directory setup failed - {e}")

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

            if not init_result:
                raise RuntimeError("Initialization sequence failed - check logs for details")

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

        # Initialize maintenance service and perform cleanup BEFORE components
        init_manager.register_step(
            phase=InitializationPhase.SERVICES,
            name="Initialize Maintenance Service",
            handler=self._initialize_maintenance_service,
            critical=True,
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

        # CRITICAL: File logging is REQUIRED for production
        # FAIL FAST AND LOUD if we can't set it up
        import os

        if not os.environ.get("PYTEST_CURRENT_TEST"):
            from ciris_engine.logic.utils.logging_config import setup_basic_logging

            # Get TimeService from service initializer
            time_service = self.service_initializer.time_service
            if not time_service:
                error_msg = "CRITICAL: TimeService not available - CANNOT INITIALIZE FILE LOGGING"
                logger.critical(error_msg)
                raise RuntimeError(error_msg)

            try:
                setup_basic_logging(
                    level=logging.DEBUG if self.debug else logging.INFO,
                    log_to_file=True,
                    console_output=False,  # Already logging to console from main.py
                    enable_incident_capture=True,
                    time_service=time_service,
                    log_dir="logs",
                )
                logger.info("[_initialize_infrastructure] File logging initialized successfully")
            except Exception as e:
                error_msg = f"CRITICAL: Failed to setup file logging: {e}"
                logger.critical(error_msg)
                raise RuntimeError(error_msg)
        else:
            logger.debug("[_initialize_infrastructure] Test mode detected, skipping file logging setup")

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
        # Pass the db path from our config - MUST pass the config!
        db_path = persistence.get_sqlite_db_full_path(self.essential_config)
        persistence.initialize_database(db_path)
        persistence.run_migrations(db_path)

        if not self.essential_config:
            # Use default essential config if none provided
            self.essential_config = EssentialConfig()
            logger.warning("No config provided, using defaults")

    async def _verify_database_integrity(self) -> bool:
        """Verify database integrity before proceeding."""
        try:
            # Check core tables exist - pass the correct db path!
            db_path = persistence.get_sqlite_db_full_path(self.essential_config)
            conn = persistence.get_db_connection(db_path)
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

        # Set runtime on audit service so it can create trace correlations
        if self.audit_service:
            self.audit_service._runtime = self
            logger.debug("Set runtime reference on audit service for trace correlations")

        # Set runtime on visibility service so it can access telemetry for traces
        if self.visibility_service:
            self.visibility_service._runtime = self
            logger.debug("Set runtime reference on visibility service for trace retrieval")

        # Update runtime control service with runtime reference
        if self.runtime_control_service:
            if hasattr(self.runtime_control_service, "_set_runtime"):
                self.runtime_control_service._set_runtime(self)
            else:
                self.runtime_control_service.runtime = self
            logger.info("Updated runtime control service with runtime reference")

        # Update telemetry service with runtime reference for aggregator
        if self.telemetry_service:
            if hasattr(self.telemetry_service, "_set_runtime"):
                self.telemetry_service._set_runtime(self)
                logger.info("Updated telemetry service with runtime reference for aggregator")

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

            # Set up thought tracking callback now that agent_processor exists
            # This avoids the race condition where RuntimeControlService tried to access
            # agent_processor during Phase 5 (SERVICES) before it was created in Phase 6 (COMPONENTS)
            if self.runtime_control_service:
                self.runtime_control_service.setup_thought_tracking()
                logger.debug("Thought tracking callback set up after agent_processor creation")

        except Exception as e:
            logger.error(f"[_build_components] Failed to build components: {e}", exc_info=True)
            raise

        # Register core services after components are built
        self._register_core_services()
        logger.info("[_build_components] Component building completed")

    async def _start_adapter_connections(self) -> None:
        """Start adapter connections and wait for them to be ready."""
        from .ciris_runtime_helpers import (
            create_adapter_lifecycle_tasks,
            log_adapter_configuration_details,
            verify_adapter_service_registration,
            wait_for_adapter_readiness,
        )

        # Log adapter configuration details
        log_adapter_configuration_details(self.adapters)

        # Create agent processor task and adapter lifecycle tasks
        agent_task = asyncio.create_task(self._create_agent_processor_when_ready(), name="AgentProcessorTask")
        self._adapter_tasks = create_adapter_lifecycle_tasks(self.adapters, agent_task)

        # Wait for adapters to be ready
        adapters_ready = await wait_for_adapter_readiness(self.adapters)
        if not adapters_ready:
            raise RuntimeError("Adapters failed to become ready within timeout")

        # Register services and verify availability
        services_available = await verify_adapter_service_registration(self)
        if not services_available:
            raise RuntimeError("Failed to establish adapter connections within timeout")

        # Final verification with the existing wait method
        await self._wait_for_critical_services(timeout=5.0)

    async def _create_agent_processor_when_ready(self) -> None:
        """Create and start agent processor once all services are ready.

        This replaces the placeholder task pattern with proper dependency injection.
        """
        logger.info("Waiting for services to be ready before starting agent processor...")

        # Wait for all critical services to be available
        await self._wait_for_critical_services(timeout=30.0)

        # Ensure agent processor is built
        if not self.agent_processor:
            raise RuntimeError("Agent processor not initialized - build components first")

        # Start the multi-service sink if available
        if self.bus_manager:
            _sink_task = asyncio.create_task(self.bus_manager.start())
            logger.info("Started multi-service sink as background task")

        # Start agent processing with default rounds
        effective_num_rounds = DEFAULT_NUM_ROUNDS
        logger.info(
            f"Starting agent processor (num_rounds={effective_num_rounds if effective_num_rounds != -1 else 'infinite'})..."
        )

        # Start the actual agent processing
        await self.agent_processor.start_processing(effective_num_rounds)

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

    async def run(self, _: Optional[int] = None) -> None:
        """Run the agent processing loop with shutdown monitoring."""
        from .ciris_runtime_helpers import (
            finalize_runtime_execution,
            handle_runtime_agent_task_completion,
            handle_runtime_task_failures,
            monitor_runtime_shutdown_signals,
            setup_runtime_monitoring_tasks,
        )

        if not self._initialized:
            await self.initialize()

        try:
            # Set up runtime monitoring tasks
            agent_task, adapter_tasks, all_tasks = setup_runtime_monitoring_tasks(self)
            if not agent_task:
                return

            # Keep monitoring until agent task completes
            shutdown_logged = False
            while not agent_task.done():
                done, pending = await asyncio.wait(all_tasks, return_when=asyncio.FIRST_COMPLETED)

                # Remove completed tasks from all_tasks to avoid re-processing
                all_tasks = [t for t in all_tasks if t not in done]

                # Monitor shutdown signals
                shutdown_logged = monitor_runtime_shutdown_signals(self, shutdown_logged)

                # Handle task completion based on type
                if (self._shutdown_event and self._shutdown_event.is_set()) or is_global_shutdown_requested():
                    # Continue loop - let graceful shutdown process handle everything
                    continue
                elif agent_task in done:
                    handle_runtime_agent_task_completion(self, agent_task, adapter_tasks)
                    break  # Exit the while loop
                else:
                    # Handle other task completions/failures
                    excluded_tasks = {
                        t for t in all_tasks if t.get_name() in ["ShutdownEventWait", "GlobalShutdownWait"]
                    }
                    handle_runtime_task_failures(self, done, excluded_tasks)

            # Finalize execution
            await finalize_runtime_execution(self, pending)

        except KeyboardInterrupt:
            logger.info("Received interrupt signal. Requesting shutdown.")
            self.request_shutdown("KeyboardInterrupt")
        except Exception as e:
            logger.error(f"Runtime error: {e}", exc_info=True)
        finally:
            logger.debug("Runtime.run() entering finally block")
            await self.shutdown()
            logger.debug("Runtime.run() exiting finally block")

    async def shutdown(self) -> None:
        """Gracefully shutdown all services with consciousness preservation."""
        from .ciris_runtime_helpers import (
            cleanup_runtime_resources,
            execute_final_maintenance_tasks,
            execute_service_shutdown_sequence,
            finalize_shutdown_logging,
            handle_adapter_shutdown_cleanup,
            handle_agent_processor_shutdown,
            prepare_shutdown_maintenance_tasks,
            preserve_critical_system_state,
            validate_shutdown_completion,
            validate_shutdown_preconditions,
        )

        # 1. Validate preconditions and early exit if needed
        if not validate_shutdown_preconditions(self):
            return

        logger.info("Shutting down CIRIS Runtime...")

        # 2. Prepare maintenance and stop scheduled services
        await prepare_shutdown_maintenance_tasks(self)

        # 3. Execute final maintenance tasks
        await execute_final_maintenance_tasks(self)

        # 4. Preserve critical system state
        await preserve_critical_system_state(self)

        # 5. Handle agent processor shutdown
        logger.info("Initiating shutdown sequence for CIRIS Runtime...")
        self._ensure_shutdown_event()
        if self._shutdown_event:
            self._shutdown_event.set()

        await handle_agent_processor_shutdown(self)

        # 6. Handle adapter cleanup
        await handle_adapter_shutdown_cleanup(self)

        # 7. Execute service shutdown sequence
        logger.debug("Stopping core services...")
        await execute_service_shutdown_sequence(self)

        # 8. Finalize logging and cleanup resources
        await finalize_shutdown_logging(self)
        await cleanup_runtime_resources(self)
        validate_shutdown_completion(self)
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
