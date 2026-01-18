"""
ciris_engine/runtime/ciris_runtime.py

New simplified runtime that properly orchestrates all components.

This file has been refactored to use extracted helper modules for better
separation of concerns and reduced complexity:
- service_property_mixin.py: Service property accessors
- initialization_steps.py: Initialization step handlers
- config_migration.py: Configuration migration utilities
- billing_helpers.py: Billing provider helpers
- resume_helpers.py: Resume from first-run helpers
- shutdown_continuity.py: Shutdown continuity helpers
- bootstrap_helpers.py: Bootstrap configuration helpers
- ciris_runtime_helpers.py: Runtime execution helpers (existing)
"""

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from ciris_engine.schemas.types import JSONDict

if TYPE_CHECKING:
    from ciris_engine.schemas.runtime.bootstrap import RuntimeBootstrapConfig

from ciris_engine.logic.infrastructure.handlers.action_dispatcher import ActionDispatcher
from ciris_engine.logic.infrastructure.handlers.handler_registry import build_action_dispatcher
from ciris_engine.logic.processors import AgentProcessor
from ciris_engine.logic.utils.constants import DEFAULT_NUM_ROUNDS
from ciris_engine.logic.utils.shutdown_manager import (
    get_shutdown_manager,
    is_global_shutdown_requested,
    wait_for_global_shutdown_async,
)
from ciris_engine.protocols.runtime.base import BaseAdapterProtocol
from ciris_engine.schemas.adapters import AdapterServiceRegistration
from ciris_engine.schemas.config.essential import EssentialConfig
from ciris_engine.schemas.processors.states import AgentState
from ciris_engine.schemas.runtime.adapter_management import AdapterConfig
from ciris_engine.schemas.runtime.core import AgentIdentityRoot
from ciris_engine.schemas.runtime.enums import ServiceType

from .billing_helpers import (
    CIRIS_PROXY_DOMAINS,
    create_billing_provider,
    create_billing_token_handler,
    create_llm_token_handler,
    get_resource_monitor_for_billing,
    is_using_ciris_proxy,
    reinitialize_billing_provider,
    update_llm_services_token,
    update_service_token_if_ciris_proxy,
)
from .bootstrap_helpers import (
    check_mock_llm,
    create_bootstrap_from_legacy,
    load_adapters_from_bootstrap,
    parse_bootstrap_config,
)
from .component_builder import ComponentBuilder
from .config_migration import (
    check_existing_cognitive_config,
    create_legacy_cognitive_behaviors,
    get_cognitive_behaviors_from_template,
    migrate_adapter_configs_to_graph,
    migrate_cognitive_state_behaviors_to_graph,
    migrate_tickets_config_to_graph,
    save_cognitive_behaviors_to_graph,
    should_skip_cognitive_migration,
)
from .identity_manager import IdentityManager
from .resume_helpers import (
    auto_enable_android_adapters_for_resume,
    initialize_core_services_for_resume,
    initialize_identity_for_resume,
    initialize_llm_for_resume,
    migrate_cognitive_behaviors_for_resume,
    reinject_adapters_for_resume,
    reload_environment_for_resume,
    set_service_runtime_references,
)
from .service_initializer import ServiceInitializer
from .service_property_mixin import ServicePropertyMixin
from .shutdown_continuity import (
    build_shutdown_node_attributes,
    create_startup_node,
    determine_shutdown_consent_status,
    preserve_shutdown_continuity,
    update_identity_with_shutdown_reference,
)

logger = logging.getLogger(__name__)

# Keep single domain for backwards compatibility (tests)
CIRIS_PROXY_DOMAIN = "ciris.ai"


class CIRISRuntime(ServicePropertyMixin):
    """
    Main runtime orchestrator for CIRIS Agent.
    Handles initialization of all components and services.
    Implements the RuntimeInterface protocol.
    """

    def __new__(cls, *args: Any, **kwargs: Any) -> "CIRISRuntime":
        """Custom __new__ to handle CI environment issues."""
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

        # Declare attributes that will be set in parse_bootstrap_config
        self.essential_config: EssentialConfig
        self.startup_channel_id: str
        self.adapter_configs: Dict[str, AdapterConfig]
        self.modules_to_load: List[str]
        self.debug: bool
        self._preload_tasks: List[Any]

        # Import RuntimeBootstrapConfig here to avoid circular imports
        from ciris_engine.schemas.runtime.bootstrap import RuntimeBootstrapConfig

        self.bootstrap: RuntimeBootstrapConfig

        # Use bootstrap helpers to parse configuration
        parse_bootstrap_config(
            self, bootstrap, essential_config, startup_channel_id, adapter_types, adapter_configs, kwargs
        )

        self.adapters: List[BaseAdapterProtocol] = []

        # CRITICAL: Check for mock LLM environment variable
        check_mock_llm(self)

        # Initialize managers
        self.identity_manager: Optional[IdentityManager] = None
        self.service_initializer = ServiceInitializer(essential_config=essential_config)
        self.component_builder: Optional[ComponentBuilder] = None
        self.agent_processor: Optional["AgentProcessor"] = None
        self._adapter_tasks: List[asyncio.Task[Any]] = []

        # Load adapters from bootstrap config
        load_adapters_from_bootstrap(self)

        if not self.adapters:
            raise RuntimeError("No valid adapters specified, shutting down")

        # Runtime state
        self._initialized = False
        self._shutdown_manager = get_shutdown_manager()
        self._shutdown_event: Optional[asyncio.Event] = None
        self._shutdown_reason: Optional[str] = None
        self._agent_task: Optional[asyncio.Task[Any]] = None
        self._shutdown_complete = False
        self._shutdown_in_progress = False

        # Resume protection
        self._resume_in_progress = False
        self._resume_started_at: Optional[float] = None
        self._startup_time: float = time.time()

        # Identity - will be loaded during initialization
        self.agent_identity: Optional[AgentIdentityRoot] = None

    # Profile property - converts agent identity to profile format
    @property
    def profile(self) -> Optional[Any]:
        """Convert agent identity to profile format for compatibility."""
        if not self.agent_identity:
            return None

        from ciris_engine.schemas.config.agent import AgentTemplate, DSDMAConfiguration

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
    def agent_template(self) -> Optional[Any]:
        """Access to full agent template - includes tickets config and all template data."""
        return self.identity_manager.agent_template if self.identity_manager else None

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

        from ciris_engine.logic.utils.shutdown_manager import request_global_shutdown

        request_global_shutdown(f"Runtime: {reason}")

    def _request_shutdown(self, reason: str = "Shutdown requested") -> None:
        """Wrapper used during initialization failures."""
        self.request_shutdown(reason)

    def set_preload_tasks(self, tasks: List[str]) -> None:
        """Set tasks to be loaded after successful WORK state transition."""
        self._preload_tasks = tasks.copy()

    async def request_state_transition(self, target_state: str, reason: str) -> bool:
        """Request a cognitive state transition."""
        if not self.agent_processor:
            logger.error("Cannot transition state: agent processor not initialized")
            return False

        try:
            target = AgentState(target_state.lower())
        except ValueError:
            logger.error(f"Invalid target state: {target_state}")
            return False

        current_state = self.agent_processor.state_manager.get_state()
        logger.info(f"State transition requested: {current_state.value} -> {target.value} (reason: {reason})")

        success = await self.agent_processor.state_manager.transition_to(target)

        if success:
            logger.info(f"State transition successful: {current_state.value} -> {target.value}")
        else:
            logger.warning(f"State transition failed: {current_state.value} -> {target.value}")

        return success

    def get_preload_tasks(self) -> List[str]:
        """Get the list of preload tasks."""
        return self._preload_tasks.copy()

    async def initialize(self) -> None:
        """Initialize all components and services."""
        if self._initialized:
            return

        logger.info("Initializing CIRIS Runtime...")

        try:
            # CRITICAL: Ensure all directories exist with correct permissions
            from ciris_engine.logic.utils.directory_setup import (
                DirectorySetupError,
                setup_application_directories,
                validate_directories,
            )

            try:
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
                raise RuntimeError(f"Cannot start: Directory setup failed - {e}")

            # Initialize infrastructure services first
            logger.info("[initialize] Initializing infrastructure services...")
            await self.service_initializer.initialize_infrastructure_services()
            logger.info("[initialize] Infrastructure services initialized")

            # Get the initialization service
            init_manager = self.service_initializer.initialization_service
            if not init_manager:
                raise RuntimeError("InitializationService not available from ServiceInitializer")
            logger.info(f"[initialize] Got initialization service: {init_manager}")

            # Register all initialization steps
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
        """Initialize agent identity.

        If --identity-update flag is set, refresh identity from template after normal init.
        """
        from ciris_engine.logic.setup.first_run import is_first_run

        config = self._ensure_config()
        if not self.time_service:
            raise RuntimeError("TimeService not available for IdentityManager")
        self.identity_manager = IdentityManager(config, self.time_service)

        if is_first_run():
            logger.info("First-run mode: Skipping identity seeding (will seed after setup wizard)")
            return

        self.agent_identity = await self.identity_manager.initialize_identity()

        # Handle --identity-update flag for admin template refresh
        identity_update = getattr(self, "_identity_update", False)
        template_name = getattr(self, "_template_name", None) or getattr(config, "default_template", "default")
        logger.info(f"[IDENTITY_UPDATE] Checking flag: _identity_update={identity_update}, template_name={template_name}")

        if identity_update:
            logger.info(f"Identity update requested - refreshing from template '{template_name}'")
            success = await self.identity_manager.refresh_identity_from_template(
                template_name=template_name,
                updated_by="admin",
            )
            if success:
                self.agent_identity = self.identity_manager.agent_identity
                logger.info("Identity successfully updated from template")
            else:
                logger.error("Failed to update identity from template")
                raise RuntimeError("Identity update failed - cannot proceed")

        await self._create_startup_node()

    def _register_initialization_steps(self, init_manager: Any) -> None:
        """Register all initialization steps with the initialization manager."""
        from ciris_engine.schemas.services.operations import InitializationPhase

        # Phase 0: INFRASTRUCTURE
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

        init_manager.register_step(
            phase=InitializationPhase.SERVICES,
            name="Start Adapters",
            handler=self._start_adapters,
            critical=True,
        )

        init_manager.register_step(
            phase=InitializationPhase.SERVICES,
            name="Register Adapter Services",
            handler=self._register_adapter_services,
            critical=True,
        )

        init_manager.register_step(
            phase=InitializationPhase.SERVICES,
            name="Initialize Maintenance Service",
            handler=self._initialize_maintenance_service,
            critical=True,
        )

        # Phase 6: COMPONENTS
        init_manager.register_step(
            phase=InitializationPhase.COMPONENTS,
            name="Build Components",
            handler=self._build_components,
            critical=True,
        )

        init_manager.register_step(
            phase=InitializationPhase.COMPONENTS,
            name="Start Adapter Connections",
            handler=self._start_adapter_connections,
            critical=True,
            timeout=45.0,
        )

        # Phase 7: VERIFICATION
        init_manager.register_step(
            phase=InitializationPhase.VERIFICATION,
            name="Final System Verification",
            handler=self._final_verification,
            critical=True,
        )

    async def _initialize_infrastructure(self) -> None:
        """Initialize infrastructure services."""
        import os

        if not os.environ.get("PYTEST_CURRENT_TEST"):
            from ciris_engine.logic.utils.logging_config import setup_basic_logging

            time_service = self.service_initializer.time_service
            if not time_service:
                raise RuntimeError("CRITICAL: TimeService not available - CANNOT INITIALIZE FILE LOGGING")

            try:
                setup_basic_logging(
                    level=logging.DEBUG if self.debug else logging.INFO,
                    log_to_file=True,
                    console_output=False,
                    enable_incident_capture=True,
                    time_service=time_service,
                )
                logger.info("[_initialize_infrastructure] File logging initialized successfully")
            except Exception as e:
                raise RuntimeError(f"CRITICAL: Failed to setup file logging: {e}")

    async def _verify_infrastructure(self) -> bool:
        """Verify infrastructure services are operational."""
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
        from ciris_engine.logic import persistence
        from ciris_engine.logic.persistence.db.dialect import get_adapter

        adapter = get_adapter()
        if adapter.is_postgresql():
            db_path = None
            logger.info("Using PostgreSQL database from environment (CIRIS_DB_URL)")
        else:
            db_path = str(self.essential_config.database.main_db)
            logger.info(f"Using SQLite database: {db_path}")

        persistence.initialize_database(db_path)
        persistence.run_migrations(db_path)

        if not self.essential_config:
            self.essential_config = EssentialConfig()
            self.essential_config.load_env_vars()
            logger.warning("No config provided, using defaults")

    async def _verify_database_integrity(self) -> bool:
        """Verify database integrity before proceeding."""
        try:
            from ciris_engine.logic import persistence
            from ciris_engine.logic.persistence.db.dialect import get_adapter

            adapter = get_adapter()
            db_path = None if adapter.is_postgresql() else str(self.essential_config.database.main_db)
            conn = persistence.get_db_connection(db_path)
            cursor = conn.cursor()

            required_tables = ["tasks", "thoughts", "graph_nodes", "graph_edges"]

            for table in required_tables:
                if adapter.is_postgresql():
                    cursor.execute(
                        "SELECT table_name FROM information_schema.tables WHERE table_schema='public' AND table_name=%s",
                        (table,),
                    )
                else:
                    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,))

                if not cursor.fetchone():
                    raise RuntimeError(f"Required table '{table}' missing from database")

            conn.close()
            logger.info("Database integrity verified")
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
        from ciris_engine.logic.setup.first_run import is_first_run

        if not self.identity_manager:
            logger.error("Identity manager not initialized")
            return False

        if is_first_run():
            logger.info("First-run mode: Identity manager created (identity will be seeded after setup)")
            return True

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
        from ciris_engine.logic.setup.first_run import is_first_run

        config = self._ensure_config()

        if is_first_run():
            logger.info("First-run mode: Skipping core service initialization (setup wizard only)")
            return

        if not self.agent_identity:
            raise RuntimeError("CRITICAL: Cannot initialize services without agent identity")

        await self.service_initializer.initialize_all_services(
            config,
            self.essential_config,
            self.agent_identity.agent_id,
            self.startup_channel_id,
            self.modules_to_load,
        )

        if self.modules_to_load:
            logger.info(f"Loading {len(self.modules_to_load)} external modules: {self.modules_to_load}")
            await self.service_initializer.load_modules(self.modules_to_load)

        # Set runtime references on services
        set_service_runtime_references(self)

    async def _verify_core_services(self) -> bool:
        """Verify all core services are operational."""
        from ciris_engine.logic.setup.first_run import is_first_run

        if is_first_run():
            logger.info("First-run mode: Core services verification skipped")
            return True

        return self.service_initializer.verify_core_services()

    async def _initialize_maintenance_service(self) -> None:
        """Initialize the maintenance service and perform startup cleanup."""
        from ciris_engine.logic.setup.first_run import is_first_run

        if is_first_run():
            logger.info("First-run mode: Skipping maintenance service initialization")
            return

        if not self.maintenance_service:
            raise RuntimeError("Maintenance service was not initialized properly")
        logger.info("Maintenance service verified available")

        await self._perform_startup_maintenance()

    async def _start_adapters(self) -> None:
        """Start all adapters."""
        await asyncio.gather(*(adapter.start() for adapter in self.adapters))
        logger.info(f"All {len(self.adapters)} adapters started")
        await self._migrate_adapter_configs_to_graph()

    async def _wait_for_critical_services(self, timeout: float) -> None:
        """Wait for services required for agent operation."""
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
                        handler="SpeakHandler",
                        service_type=service_type,
                        required_capabilities=capabilities,
                    )
                    if not service:
                        all_ready = False
                        missing_services.append(name)
                    else:
                        if hasattr(service, "is_healthy"):
                            is_healthy = await service.is_healthy()
                            if not is_healthy:
                                all_ready = False
                                missing_services.append(f"{name} (registered but not connected)")
                            else:
                                service_name = service.__class__.__name__ if service else "Unknown"
                                if "Discord" in service_name and not hasattr(self, "_discord_connected_reported"):
                                    if (
                                        hasattr(service, "client")
                                        and service.client
                                        and hasattr(service.client, "user")
                                    ):
                                        user = service.client.user
                                        guilds = service.client.guilds if hasattr(service.client, "guilds") else []
                                        logger.info(f"    Discord connected as {user} to {len(guilds)} guild(s)")
                                        for guild in guilds[:3]:
                                            logger.info(f"      - {guild.name} (ID: {guild.id})")
                                        if len(guilds) > 3:
                                            logger.info(f"      ... and {len(guilds) - 3} more guild(s)")
                                        self._discord_connected_reported = True

            if all_ready:
                return

            current_time = asyncio.get_event_loop().time()
            if current_time - last_report_time >= 3.0:
                elapsed = current_time - start_time
                logger.info(f"    Still waiting for: {', '.join(missing_services)} ({elapsed:.1f}s elapsed)")
                last_report_time = current_time

            await asyncio.sleep(0.5)

        raise TimeoutError(f"Critical services not available after {timeout}s. Missing: {', '.join(missing_services)}")

    async def _migrate_adapter_configs_to_graph(self) -> None:
        """Migrate adapter configurations to graph config service."""
        await migrate_adapter_configs_to_graph(self)

    async def _migrate_tickets_config_to_graph(self) -> None:
        """Migrate tickets config to graph."""
        await migrate_tickets_config_to_graph(self)

    def _should_skip_cognitive_migration(self, force_from_template: bool) -> bool:
        """Check if cognitive migration should be skipped."""
        return should_skip_cognitive_migration(force_from_template)

    async def _check_existing_cognitive_config(self, config_service: Any) -> bool:
        """Check if cognitive config already exists in graph."""
        return await check_existing_cognitive_config(config_service)

    def _get_cognitive_behaviors_from_template(self) -> Optional[Any]:
        """Get cognitive behaviors from the agent template if available."""
        return get_cognitive_behaviors_from_template(self)

    def _create_legacy_cognitive_behaviors(self) -> Any:
        """Create pre-1.7 compatible cognitive behaviors config."""
        return create_legacy_cognitive_behaviors()

    async def _save_cognitive_behaviors_to_graph(self, config_service: Any, cognitive_behaviors: Any) -> None:
        """Save cognitive behaviors to the graph with IDENTITY scope."""
        await save_cognitive_behaviors_to_graph(config_service, cognitive_behaviors)

    async def _migrate_cognitive_state_behaviors_to_graph(self, force_from_template: bool = False) -> None:
        """Migrate cognitive state behaviors to graph."""
        await migrate_cognitive_state_behaviors_to_graph(self, force_from_template)

    async def _final_verification(self) -> None:
        """Perform final system verification."""
        from ciris_engine.logic.setup.first_run import is_first_run

        if is_first_run():
            logger.info("First-run mode: Skipping final verification (waiting for setup wizard)")
            logger.info("=" * 60)
            logger.info("CIRIS Agent First-Run Mode Active")
            logger.info("Setup wizard is ready at http://127.0.0.1:8080/setup")
            logger.info("=" * 60)
            return

        if not self.agent_identity:
            raise RuntimeError("No agent identity established")

        logger.info("=" * 60)
        logger.info("CIRIS Agent Pre-Wakeup Verification Complete")
        logger.info(f"Identity: {self.agent_identity.agent_id}")
        logger.info(f"Purpose: {self.agent_identity.core_profile.description}")
        logger.info(f"Capabilities: {len(self.agent_identity.permitted_actions)} allowed")

        service_count = 0
        if self.service_registry:
            registry_info = self.service_registry.get_provider_info()
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
            all_configs = await self.config_service.list_configs()

            runtime_config_patterns = ["adapter.", "runtime.", "session.", "temp."]
            deleted_count = 0

            for key, value in all_configs.items():
                is_runtime_config = any(key.startswith(pattern) for pattern in runtime_config_patterns)

                if is_runtime_config:
                    config_node = await self.config_service.get_config(key)
                    if config_node:
                        if config_node.updated_by == "system_bootstrap":
                            logger.debug(f"Preserving bootstrap config: {key}")
                            continue

                        graph_node = config_node.to_graph_node()
                        await self.config_service.graph.forget(graph_node)  # type: ignore[attr-defined]
                        deleted_count += 1
                        logger.debug(f"Deleted runtime config node: {key}")

            if deleted_count > 0:
                logger.info(f"Cleaned up {deleted_count} runtime-specific configuration entries from previous runs")
            else:
                logger.info("No runtime-specific configuration entries to clean up")

        except Exception as e:
            logger.error(f"Failed to clean up runtime config: {e}", exc_info=True)

    async def _register_adapter_services(self) -> None:
        """Register services provided by the loaded adapters."""
        from ciris_engine.logic.setup.first_run import is_first_run

        if is_first_run():
            logger.info("First-run mode: Skipping adapter service registration")
            return

        if not self.service_registry:
            logger.error("ServiceRegistry not initialized. Cannot register adapter services.")
            return

        for adapter in self.adapters:
            try:
                adapter_type = adapter.__class__.__name__.lower().replace("adapter", "")
                adapter_info = self._build_adapter_info(adapter)
                await self._create_adapter_auth_token(adapter, adapter_type, adapter_info)

                registrations = adapter.get_services_to_register()
                for reg in registrations:
                    self._register_adapter_service(reg, adapter)
            except Exception as e:
                logger.error(f"Error registering services for adapter {adapter.__class__.__name__}: {e}", exc_info=True)

    def _build_adapter_info(self, adapter: Any) -> JSONDict:
        """Build adapter info dictionary for authentication token creation."""
        adapter_info: JSONDict = {
            "instance_id": str(id(adapter)),
            "startup_time": (
                self.time_service.now().isoformat() if self.time_service else datetime.now(timezone.utc).isoformat()
            ),
        }
        if hasattr(adapter, "get_channel_info"):
            adapter_info.update(adapter.get_channel_info())
        return adapter_info

    async def _create_adapter_auth_token(
        self, adapter: Any, adapter_type: str, adapter_info: JSONDict
    ) -> Optional[str]:
        """Create and set authentication token for an adapter."""
        auth_service = self.service_initializer.auth_service if self.service_initializer else None
        if not auth_service:
            return None

        auth_token = await auth_service._create_channel_token_for_adapter(adapter_type, adapter_info)

        if hasattr(adapter, "set_auth_token") and auth_token:
            adapter.set_auth_token(auth_token)

        if auth_token:
            logger.info(f"Generated authentication token for {adapter_type} adapter")

        return auth_token

    def _register_adapter_service(self, reg: AdapterServiceRegistration, adapter: Any) -> bool:
        """Register a single adapter service. Returns True if successful."""
        if not isinstance(reg, AdapterServiceRegistration):
            logger.error(
                f"Adapter {adapter.__class__.__name__} provided an invalid AdapterServiceRegistration object: {reg}"
            )
            return False

        if self.service_registry is None:
            logger.error("Cannot register adapter service: service_registry is None")
            return False

        self.service_registry.register_service(
            service_type=reg.service_type,
            provider=reg.provider,
            priority=reg.priority,
            capabilities=reg.capabilities,
        )
        logger.info(f"Registered {reg.service_type.value} from {adapter.__class__.__name__}")
        return True

    async def _register_adapter_services_for_resume(self) -> None:
        """Register adapter services during resume_from_first_run."""
        if not self.service_registry:
            logger.error("ServiceRegistry not initialized. Cannot register adapter services.")
            return

        for adapter in self.adapters:
            try:
                adapter_type = adapter.__class__.__name__.lower().replace("adapter", "")
                adapter_info = self._build_adapter_info(adapter)
                await self._create_adapter_auth_token(adapter, adapter_type, adapter_info)

                for reg in adapter.get_services_to_register():
                    self._register_adapter_service(reg, adapter)
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

        if not self.llm_service:
            from ciris_engine.logic.setup.first_run import is_first_run

            if is_first_run():
                logger.info("[_build_components] First-run setup mode - LLM not yet configured")
                logger.info("[_build_components] Setup wizard will guide LLM configuration")
            else:
                logger.error("[_build_components] LLM service not available but setup was completed!")
                logger.error("[_build_components] Check your LLM configuration")
            return

        try:
            self.component_builder = ComponentBuilder(self)
            logger.info("[_build_components] ComponentBuilder created successfully")

            self.agent_processor = await self.component_builder.build_all_components()
            logger.info(f"[_build_components] agent_processor created: {self.agent_processor}")

            if self.runtime_control_service:
                self.runtime_control_service.setup_thought_tracking()  # type: ignore[attr-defined]
                logger.debug("Thought tracking callback set up after agent_processor creation")

        except Exception as e:
            logger.error(f"[_build_components] Failed to build components: {e}", exc_info=True)
            raise

        self._register_core_services()
        logger.info("[_build_components] Component building completed")

    async def _start_adapter_connections(self) -> None:
        """Start adapter connections and wait for them to be ready."""
        from ciris_engine.logic.setup.first_run import is_first_run

        from .ciris_runtime_helpers import (
            create_adapter_lifecycle_tasks,
            log_adapter_configuration_details,
            verify_adapter_service_registration,
            wait_for_adapter_readiness,
        )

        log_adapter_configuration_details(self.adapters)

        first_run = is_first_run()
        if first_run:
            logger.info("")
            logger.info("=" * 70)
            logger.info("FIRST RUN DETECTED - Setup Wizard Mode")
            logger.info("=" * 70)
            logger.info("")
            logger.info("The agent processor will NOT start in first-run mode.")
            logger.info("Only the API server is running to provide the setup wizard.")
            logger.info("")
            logger.info("Next Steps:")
            logger.info("  1. Open your browser to: http://localhost:8080")
            logger.info("  2. Complete the setup wizard")
            logger.info("  3. Restart the agent with: ciris-agent")
            logger.info("")
            logger.info("After restart, the full agent will start normally.")
            logger.info("=" * 70)
            logger.info("")

            adapters_ready = await wait_for_adapter_readiness(self.adapters)
            if not adapters_ready:
                raise RuntimeError("Adapters failed to become ready within timeout")

            self._adapter_tasks = create_adapter_lifecycle_tasks(self.adapters, agent_task=None)

            logger.info("Setup wizard ready at http://localhost:8080")
            logger.info("Waiting for setup completion... (Press CTRL+C to exit)")
            return

        agent_task = asyncio.create_task(self._create_agent_processor_when_ready(), name="AgentProcessorTask")
        self._adapter_tasks = create_adapter_lifecycle_tasks(self.adapters, agent_task)

        adapters_ready = await wait_for_adapter_readiness(self.adapters)
        if not adapters_ready:
            raise RuntimeError("Adapters failed to become ready within timeout")

        services_available = await verify_adapter_service_registration(self)
        if not services_available:
            raise RuntimeError("Failed to establish adapter connections within timeout")

        await self._wait_for_critical_services(timeout=5.0)

    def _is_using_ciris_proxy(self) -> bool:
        """Check if runtime is configured to use CIRIS proxy."""
        return is_using_ciris_proxy()

    def _create_billing_token_handler(self, credit_provider: Any) -> Any:
        """Create handler for billing token refresh signals."""
        return create_billing_token_handler(credit_provider)

    def _create_llm_token_handler(self) -> Any:
        """Create handler for LLM service token refresh signals."""
        return create_llm_token_handler(self)

    def _update_llm_services_token(self, new_token: str) -> None:
        """Update all LLM services that use CIRIS proxy with new token."""
        update_llm_services_token(self, new_token)

    def _update_service_token_if_ciris_proxy(self, service: Any, new_token: str, is_primary: bool = False) -> None:
        """Update a service's API key if it uses CIRIS proxy."""
        update_service_token_if_ciris_proxy(service, new_token, is_primary)

    async def _reinitialize_billing_provider(self) -> None:
        """Reinitialize billing provider after setup completes."""
        await reinitialize_billing_provider(self)

    def _get_resource_monitor_for_billing(self) -> Any:
        """Get resource monitor service for billing initialization."""
        return get_resource_monitor_for_billing(self)

    def _create_billing_provider(self, google_id_token: str) -> Any:
        """Create and configure the CIRIS billing provider."""
        return create_billing_provider(google_id_token)

    def _resume_reload_environment(self, log_step: Any, total_steps: int) -> "EssentialConfig":
        """Reload environment and config during resume from first-run."""
        return reload_environment_for_resume(self, log_step, total_steps)

    async def _resume_initialize_identity(self, config: "EssentialConfig", log_step: Any, total_steps: int) -> None:
        """Initialize identity with user-selected template during resume."""
        await initialize_identity_for_resume(self, config, log_step, total_steps)

    async def _resume_migrate_cognitive_behaviors(self, log_step: Any, total_steps: int) -> None:
        """Migrate cognitive state behaviors from template during resume."""
        await migrate_cognitive_behaviors_for_resume(self, log_step, total_steps)

    def _set_service_runtime_references(self) -> None:
        """Set runtime references on services that need them."""
        set_service_runtime_references(self)

    async def _resume_initialize_core_services(
        self, config: "EssentialConfig", log_step: Any, total_steps: int
    ) -> None:
        """Initialize core services during resume."""
        await initialize_core_services_for_resume(self, config, log_step, total_steps)

    async def _resume_initialize_llm(self, log_step: Any, total_steps: int) -> None:
        """Initialize LLM service during resume."""
        await initialize_llm_for_resume(self, log_step, total_steps)

    def _resume_reinject_adapters(self, log_step: Any, total_steps: int) -> None:
        """Re-inject services into running adapters during resume."""
        reinject_adapters_for_resume(self, log_step, total_steps)

    async def _resume_auto_enable_android_adapters(self) -> None:
        """Auto-enable Android-specific adapters after resume."""
        await auto_enable_android_adapters_for_resume(self)

    async def resume_from_first_run(self) -> None:
        """Resume initialization after setup wizard completes."""
        self._resume_in_progress = True
        self._resume_started_at = time.time()
        logger.info(f"[RESUME] Started at {self._resume_started_at:.3f}, _resume_in_progress=True")

        start_time = time.time()
        total_steps = 14

        def log_step(step_num: int, total: int, msg: str) -> None:
            elapsed = time.time() - start_time
            logger.warning(f"[RESUME {step_num}/{total}] [{elapsed:.2f}s] {msg}")

        logger.warning("")
        logger.warning("=" * 70)
        logger.warning("RESUMING FROM FIRST-RUN MODE")
        logger.warning("=" * 70)
        logger.warning("")
        log_step(1, total_steps, "Starting resume from first-run...")

        # Steps 2-3: Reload environment and config
        config = self._resume_reload_environment(log_step, total_steps)

        # Step 4: Initialize identity
        await self._resume_initialize_identity(config, log_step, total_steps)

        # Step 5: Migrate cognitive behaviors
        await self._resume_migrate_cognitive_behaviors(log_step, total_steps)

        # Step 6: Initialize core services
        await self._resume_initialize_core_services(config, log_step, total_steps)

        # Step 7: Register adapter services
        log_step(7, total_steps, "Registering adapter services...")
        await self._register_adapter_services_for_resume()
        log_step(7, total_steps, "Adapter services registered")

        # Step 8: Initialize maintenance service
        log_step(
            8, total_steps, f"Initializing maintenance... maintenance_service={self.maintenance_service is not None}"
        )
        if self.maintenance_service:
            await self._perform_startup_maintenance()
            log_step(8, total_steps, "Maintenance service initialized")
        else:
            log_step(8, total_steps, "Skipped maintenance - no maintenance_service")

        # Step 9: Reinitialize billing provider
        log_step(9, total_steps, "Reinitializing billing provider...")
        await self._reinitialize_billing_provider()
        log_step(9, total_steps, "Billing provider reinitialized")

        # Step 10: Initialize LLM service
        await self._resume_initialize_llm(log_step, total_steps)

        # Step 11: Re-inject services into adapters
        self._resume_reinject_adapters(log_step, total_steps)

        # Step 12: Auto-enable Android-specific adapters
        log_step(12, total_steps, "Auto-enabling Android adapters...")
        await self._resume_auto_enable_android_adapters()
        log_step(12, total_steps, "Android adapters auto-enabled")

        # Step 13: Build cognitive components
        log_step(13, total_steps, "Building cognitive components...")
        await self._build_components()
        log_step(13, total_steps, "Cognitive components built")

        # Step 14: Create agent processor task
        log_step(14, total_steps, "Creating agent processor task...")
        self._agent_task = asyncio.create_task(self._create_agent_processor_when_ready(), name="AgentProcessorTask")
        log_step(14, total_steps, "Waiting for critical services (timeout=10s)...")
        await self._wait_for_critical_services(timeout=10.0)

        elapsed = time.time() - start_time
        logger.warning("")
        logger.warning(f"RESUME COMPLETE in {elapsed:.2f}s - Agent processor started!")
        logger.warning("=" * 70)
        logger.warning("")

        self._resume_in_progress = False
        self._resume_started_at = None
        logger.info(f"[RESUME] Completed in {elapsed:.2f}s, _resume_in_progress=False")

    async def _create_agent_processor_when_ready(self) -> None:
        """Create and start agent processor once all services are ready."""
        logger.info("Waiting for services to be ready before starting agent processor...")

        await self._wait_for_critical_services(timeout=30.0)

        if not self.agent_processor:
            from ciris_engine.logic.setup.first_run import is_first_run

            if is_first_run():
                logger.info("Agent processor not started - first-run setup mode active")
            else:
                logger.error("Agent processor not initialized but setup was completed!")
                logger.error("This indicates a configuration error - check LLM settings")
            return

        if self.bus_manager:
            _sink_task = asyncio.create_task(self.bus_manager.start())
            logger.info("Started multi-service sink as background task")

        effective_num_rounds = DEFAULT_NUM_ROUNDS
        logger.info(
            f"Starting agent processor (num_rounds={effective_num_rounds if effective_num_rounds != -1 else 'infinite'})..."
        )

        await self.agent_processor.start_processing(effective_num_rounds)

    def _register_core_services(self) -> None:
        """Register core services in the service registry."""
        self.service_initializer.register_core_services()

    def _build_action_dispatcher(self, dependencies: Any) -> ActionDispatcher:
        """Build action dispatcher. Override in subclasses for custom sinks."""
        config = self._ensure_config()
        from ciris_engine.logic.buses import BusManager

        if not self.service_registry:
            raise RuntimeError("Service registry not initialized")
        logger.debug(f"[AUDIT self.service_initializer exists: {self.service_initializer is not None}")
        if self.service_initializer:
            logger.debug(f"[AUDIT service_initializer.audit_service: {self.service_initializer.audit_service}")
        logger.debug(f"[AUDIT Creating BusManager with audit_service={self.audit_service}")
        logger.debug(f"[AUDIT self.audit_service type: {type(self.audit_service)}")
        logger.debug(f"[AUDIT self.audit_service is None: {self.audit_service is None}")

        assert self.service_registry is not None
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

    def _should_exit_runtime_loop(
        self, agent_task: Optional[asyncio.Task[Any]], shutdown_logged: bool
    ) -> tuple[bool, bool]:
        """Check if runtime loop should exit."""
        if agent_task and agent_task.done():
            return True, shutdown_logged
        if (self._shutdown_event and self._shutdown_event.is_set()) or is_global_shutdown_requested():
            return True, True
        return False, shutdown_logged

    def _handle_completed_runtime_tasks(
        self,
        done: set[asyncio.Task[Any]],
        agent_task: Optional[asyncio.Task[Any]],
        adapter_tasks: List[asyncio.Task[Any]],
        all_tasks: list[asyncio.Task[Any]],
    ) -> tuple[bool, bool]:
        """Handle completed runtime tasks."""
        from .ciris_runtime_helpers import handle_runtime_agent_task_completion, handle_runtime_task_failures

        if (self._shutdown_event and self._shutdown_event.is_set()) or is_global_shutdown_requested():
            return True, True

        if agent_task and agent_task in done:
            handle_runtime_agent_task_completion(self, agent_task, adapter_tasks)
            return True, False

        excluded_tasks = {t for t in all_tasks if t.get_name() in ["ShutdownEventWait", "GlobalShutdownWait"]}
        handle_runtime_task_failures(self, done, excluded_tasks)
        return False, False

    async def run(self, _: Optional[int] = None) -> None:
        """Run the agent processing loop with shutdown monitoring."""
        from .ciris_runtime_helpers import (
            finalize_runtime_execution,
            monitor_runtime_shutdown_signals,
            setup_runtime_monitoring_tasks,
        )

        if not self._initialized:
            await self.initialize()

        try:
            agent_task, adapter_tasks, all_tasks = setup_runtime_monitoring_tasks(self)
            if not all_tasks:
                logger.error("No tasks to monitor - exiting")
                return

            shutdown_logged = False
            while True:
                should_exit, shutdown_logged = self._should_exit_runtime_loop(agent_task, shutdown_logged)
                if should_exit:
                    break

                done, pending = await asyncio.wait(all_tasks, return_when=asyncio.FIRST_COMPLETED, timeout=1.0)
                all_tasks = [t for t in all_tasks if t not in done]

                shutdown_logged = monitor_runtime_shutdown_signals(self, shutdown_logged)

                should_break, _ = self._handle_completed_runtime_tasks(done, agent_task, adapter_tasks, all_tasks)
                if should_break:
                    break

            await finalize_runtime_execution(self, set(pending) if "pending" in locals() else set())

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
        """Gracefully shutdown all services with continuity awareness."""
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

        if not validate_shutdown_preconditions(self):
            return

        logger.info("Shutting down CIRIS Runtime...")

        await prepare_shutdown_maintenance_tasks(self)
        await execute_final_maintenance_tasks(self)
        await preserve_critical_system_state(self)

        logger.info("Initiating shutdown sequence for CIRIS Runtime...")
        self._ensure_shutdown_event()
        if self._shutdown_event:
            self._shutdown_event.set()

        await handle_agent_processor_shutdown(self)
        await handle_adapter_shutdown_cleanup(self)

        logger.debug("Stopping core services...")
        await execute_service_shutdown_sequence(self)

        await finalize_shutdown_logging(self)
        await cleanup_runtime_resources(self)
        validate_shutdown_completion(self)
        logger.debug("Shutdown method returning")

    async def _create_startup_node(self) -> None:
        """Create startup node for continuity tracking."""
        await create_startup_node(self)

    def _determine_shutdown_consent_status(self) -> str:
        """Determine if shutdown was consensual based on agent processor result."""
        return determine_shutdown_consent_status(self)

    def _build_shutdown_node_attributes(self, reason: str, consent_status: str) -> JSONDict:
        """Build attributes dict for shutdown memory node."""
        return build_shutdown_node_attributes(self, reason, consent_status)

    async def _update_identity_with_shutdown_reference(self, shutdown_node_id: str) -> None:
        """Update agent identity with shutdown memory reference."""
        await update_identity_with_shutdown_reference(self, shutdown_node_id)

    async def _preserve_shutdown_continuity(self) -> None:
        """Preserve agent state for future reactivation."""
        await preserve_shutdown_continuity(self)

    def _parse_bootstrap_config(
        self,
        bootstrap: Optional["RuntimeBootstrapConfig"],
        essential_config: Optional[EssentialConfig],
        startup_channel_id: Optional[str],
        adapter_types: List[str],
        adapter_configs: Optional[Dict[str, AdapterConfig]],
        kwargs: JSONDict,
    ) -> None:
        """Parse bootstrap configuration or create from legacy parameters."""
        parse_bootstrap_config(
            self, bootstrap, essential_config, startup_channel_id, adapter_types, adapter_configs, kwargs
        )

    def _create_bootstrap_from_legacy(
        self,
        essential_config: Optional[EssentialConfig],
        startup_channel_id: Optional[str],
        adapter_types: List[str],
        adapter_configs: Optional[Dict[str, AdapterConfig]],
        kwargs: JSONDict,
    ) -> None:
        """Create bootstrap config from legacy parameters."""
        create_bootstrap_from_legacy(self, essential_config, startup_channel_id, adapter_types, adapter_configs, kwargs)

    def _check_mock_llm(self) -> None:
        """Check for mock LLM environment variable and add to modules if needed."""
        check_mock_llm(self)

    def _load_adapters_from_bootstrap(self) -> None:
        """Load adapters from bootstrap configuration."""
        load_adapters_from_bootstrap(self)
