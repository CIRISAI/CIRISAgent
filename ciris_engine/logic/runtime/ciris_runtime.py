"""
ciris_engine/runtime/ciris_runtime.py

New simplified runtime that properly orchestrates all components.
"""

import asyncio
import logging
import os
import time
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional

from ciris_engine.config.ciris_services import get_billing_url
from ciris_engine.schemas.types import JSONDict

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
from ciris_engine.protocols.infrastructure.base import BusManagerProtocol
from ciris_engine.protocols.runtime.base import BaseAdapterProtocol
from ciris_engine.protocols.services.adaptation.self_observation import SelfObservationServiceProtocol

# Governance service protocols
# Note: WiseAuthorityService doesn't have a unified protocol - it's a complex system with multiple protocols
from ciris_engine.protocols.services.governance.filter import AdaptiveFilterServiceProtocol
from ciris_engine.protocols.services.governance.visibility import VisibilityServiceProtocol
from ciris_engine.protocols.services.graph.audit import AuditServiceProtocol
from ciris_engine.protocols.services.graph.config import GraphConfigServiceProtocol
from ciris_engine.protocols.services.graph.incident_management import IncidentManagementServiceProtocol

# Graph service protocols
from ciris_engine.protocols.services.graph.memory import MemoryServiceProtocol
from ciris_engine.protocols.services.graph.telemetry import TelemetryServiceProtocol
from ciris_engine.protocols.services.graph.tsdb_consolidation import TSDBConsolidationServiceProtocol

# Infrastructure service protocols
from ciris_engine.protocols.services.infrastructure.authentication import AuthenticationServiceProtocol
from ciris_engine.protocols.services.infrastructure.database_maintenance import DatabaseMaintenanceServiceProtocol
from ciris_engine.protocols.services.infrastructure.resource_monitor import ResourceMonitorServiceProtocol
from ciris_engine.protocols.services.lifecycle.initialization import InitializationServiceProtocol

# Lifecycle service protocols
from ciris_engine.protocols.services.lifecycle.scheduler import TaskSchedulerServiceProtocol
from ciris_engine.protocols.services.lifecycle.shutdown import ShutdownServiceProtocol
from ciris_engine.protocols.services.lifecycle.time import TimeServiceProtocol

# Runtime service protocols
from ciris_engine.protocols.services.runtime.llm import LLMServiceProtocol
from ciris_engine.protocols.services.runtime.runtime_control import RuntimeControlServiceProtocol
from ciris_engine.protocols.services.runtime.secrets import SecretsServiceProtocol
from ciris_engine.protocols.services.runtime.tool import ToolServiceProtocol
from ciris_engine.schemas.adapters import AdapterServiceRegistration
from ciris_engine.schemas.config.essential import EssentialConfig
from ciris_engine.schemas.processors.states import AgentState
from ciris_engine.schemas.runtime.adapter_management import AdapterConfig
from ciris_engine.schemas.runtime.core import AgentIdentityRoot
from ciris_engine.schemas.runtime.enums import ServiceType
from ciris_engine.schemas.services.operations import InitializationPhase

from .component_builder import ComponentBuilder
from .identity_manager import IdentityManager
from .service_initializer import ServiceInitializer

logger = logging.getLogger(__name__)

# Domain identifiers for CIRIS proxy services (LLM, billing)
# Includes legacy ciris.ai and new ciris-services infrastructure
CIRIS_PROXY_DOMAINS = ("ciris.ai", "ciris-services")
# Keep single domain for backwards compatibility (tests)
CIRIS_PROXY_DOMAIN = "ciris.ai"


class CIRISRuntime:
    """
    Main runtime orchestrator for CIRIS Agent.
    Handles initialization of all components and services.
    Implements the RuntimeInterface protocol.
    """

    def __new__(cls, *args: Any, **kwargs: Any) -> "CIRISRuntime":
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

        # Declare attributes that will be set in _parse_bootstrap_config
        self.essential_config: EssentialConfig
        self.startup_channel_id: str
        self.adapter_configs: Dict[str, AdapterConfig]
        self.modules_to_load: List[str]
        self.debug: bool
        self._preload_tasks: List[Any]
        self.bootstrap: RuntimeBootstrapConfig

        # Use bootstrap config if provided, otherwise construct from legacy parameters
        self._parse_bootstrap_config(
            bootstrap, essential_config, startup_channel_id, adapter_types, adapter_configs, kwargs
        )

        self.adapters: List[BaseAdapterProtocol] = []

        # CRITICAL: Check for mock LLM environment variable
        self._check_mock_llm()

        # Initialize managers
        self.identity_manager: Optional[IdentityManager] = None
        self.service_initializer = ServiceInitializer(essential_config=essential_config)
        self.component_builder: Optional[ComponentBuilder] = None
        self.agent_processor: Optional["AgentProcessor"] = None
        self._adapter_tasks: List[asyncio.Task[Any]] = []

        # Load adapters from bootstrap config
        self._load_adapters_from_bootstrap()

        if not self.adapters:
            raise RuntimeError("No valid adapters specified, shutting down")

        # Runtime state
        self._initialized = False
        self._shutdown_manager = get_shutdown_manager()
        self._shutdown_event: Optional[asyncio.Event] = None
        self._shutdown_reason: Optional[str] = None
        self._agent_task: Optional[asyncio.Task[Any]] = None
        self._shutdown_complete = False
        self._shutdown_in_progress = False  # Set when shutdown has been initiated

        # Resume protection - prevents SmartStartup from killing server mid-initialization
        self._resume_in_progress = False  # Set during resume_from_first_run
        self._resume_started_at: Optional[float] = None  # Timestamp for timeout detection
        self._startup_time: float = time.time()  # For uptime calculation

        # Identity - will be loaded during initialization
        self.agent_identity: Optional[AgentIdentityRoot] = None

    # Properties to access services from the service initializer
    @property
    def service_registry(self) -> Optional[ServiceRegistry]:
        return self.service_initializer.service_registry if self.service_initializer else None

    @property
    def bus_manager(self) -> Optional[BusManagerProtocol]:
        return self.service_initializer.bus_manager if self.service_initializer else None

    @property
    def memory_service(self) -> Optional[MemoryServiceProtocol]:
        return self.service_initializer.memory_service if self.service_initializer else None

    @property
    def resource_monitor(self) -> Optional[ResourceMonitorServiceProtocol]:
        """Access to resource monitor service - CRITICAL for mission-critical systems."""
        return self.service_initializer.resource_monitor_service if self.service_initializer else None

    @property
    def secrets_service(self) -> Optional[SecretsServiceProtocol]:
        return self.service_initializer.secrets_service if self.service_initializer else None

    @property
    def wa_auth_system(self) -> Optional[Any]:
        """WiseAuthorityService - complex system without unified protocol."""
        return self.service_initializer.wa_auth_system if self.service_initializer else None

    @property
    def telemetry_service(self) -> Optional[TelemetryServiceProtocol]:
        return self.service_initializer.telemetry_service if self.service_initializer else None

    @property
    def llm_service(self) -> Optional[LLMServiceProtocol]:
        return self.service_initializer.llm_service if self.service_initializer else None

    @property
    def audit_service(self) -> Optional[AuditServiceProtocol]:
        return self.service_initializer.audit_service if self.service_initializer else None

    @property
    def adaptive_filter_service(self) -> Optional[AdaptiveFilterServiceProtocol]:
        return self.service_initializer.adaptive_filter_service if self.service_initializer else None

    @property
    def config_manager(self) -> Optional[GraphConfigServiceProtocol]:
        """Return GraphConfigService for RuntimeControlService compatibility."""
        return self.service_initializer.config_service if self.service_initializer else None

    @property
    def secrets_tool_service(self) -> Optional[ToolServiceProtocol]:
        return self.service_initializer.secrets_tool_service if self.service_initializer else None

    @property
    def time_service(self) -> Optional[TimeServiceProtocol]:
        return self.service_initializer.time_service if self.service_initializer else None

    @property
    def config_service(self) -> Optional[GraphConfigServiceProtocol]:
        """Access to configuration service."""
        return self.service_initializer.config_service if self.service_initializer else None

    @property
    def task_scheduler(self) -> Optional[TaskSchedulerServiceProtocol]:
        """Access to task scheduler service."""
        return self.service_initializer.task_scheduler_service if self.service_initializer else None

    @property
    def authentication_service(self) -> Optional[AuthenticationServiceProtocol]:
        """Access to authentication service."""
        return self.service_initializer.auth_service if self.service_initializer else None

    @property
    def incident_management_service(self) -> Optional[IncidentManagementServiceProtocol]:
        """Access to incident management service."""
        return self.service_initializer.incident_management_service if self.service_initializer else None

    @property
    def runtime_control_service(self) -> Optional[RuntimeControlServiceProtocol]:
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
    def maintenance_service(self) -> Optional[DatabaseMaintenanceServiceProtocol]:
        return self.service_initializer.maintenance_service if self.service_initializer else None

    @property
    def database_maintenance_service(self) -> Optional[DatabaseMaintenanceServiceProtocol]:
        """Alias for maintenance_service - used by API adapter service injection.

        The API adapter's service configuration expects 'database_maintenance_service'
        while the internal runtime property is named 'maintenance_service'. This alias
        maintains backward compatibility and ensures all 22 core services are accessible.
        """
        return self.maintenance_service

    @property
    def shutdown_service(self) -> Optional[ShutdownServiceProtocol]:
        """Access to shutdown service."""
        return self.service_initializer.shutdown_service if self.service_initializer else None

    @property
    def initialization_service(self) -> Optional[InitializationServiceProtocol]:
        """Access to initialization service."""
        return self.service_initializer.initialization_service if self.service_initializer else None

    @property
    def tsdb_consolidation_service(self) -> Optional[TSDBConsolidationServiceProtocol]:
        """Access to TSDB consolidation service."""
        return self.service_initializer.tsdb_consolidation_service if self.service_initializer else None

    @property
    def self_observation_service(self) -> Optional[SelfObservationServiceProtocol]:
        """Access to self observation service."""
        return self.service_initializer.self_observation_service if self.service_initializer else None

    @property
    def visibility_service(self) -> Optional[VisibilityServiceProtocol]:
        """Access to visibility service."""
        return self.service_initializer.visibility_service if self.service_initializer else None

    @property
    def consent_service(self) -> Optional[Any]:
        """Access to consent service - manages user consent, data retention, and DSAR automation."""
        return self.service_initializer.consent_service if self.service_initializer else None

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

        # Use the sync version from shutdown_manager utils to avoid async/await issues
        from ciris_engine.logic.utils.shutdown_manager import request_global_shutdown

        request_global_shutdown(f"Runtime: {reason}")

    def _request_shutdown(self, reason: str = "Shutdown requested") -> None:
        """Wrapper used during initialization failures."""
        self.request_shutdown(reason)

    def set_preload_tasks(self, tasks: List[str]) -> None:
        """Set tasks to be loaded after successful WORK state transition."""
        self._preload_tasks = tasks.copy()

    async def request_state_transition(self, target_state: str, reason: str) -> bool:
        """Request a cognitive state transition.

        Args:
            target_state: Target state name (e.g., "DREAM", "PLAY", "SOLITUDE", "WORK")
            reason: Reason for the transition request

        Returns:
            True if transition was successful, False otherwise
        """
        if not self.agent_processor:
            logger.error("Cannot transition state: agent processor not initialized")
            return False

        # Convert string to AgentState enum (values are lowercase)
        try:
            target = AgentState(target_state.lower())
        except ValueError:
            logger.error(f"Invalid target state: {target_state}")
            return False

        current_state = self.agent_processor.state_manager.get_state()
        logger.info(f"State transition requested: {current_state.value} -> {target.value} (reason: {reason})")

        # Use the state manager's transition_to method
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
        """Initialize agent identity - create from template on first run, load from graph thereafter.

        In first-run mode, this only creates the IdentityManager but does NOT seed the graph.
        The actual identity seeding happens in resume_from_first_run() AFTER the user selects
        their template in the setup wizard.
        """
        from ciris_engine.logic.setup.first_run import is_first_run

        config = self._ensure_config()
        if not self.time_service:
            raise RuntimeError("TimeService not available for IdentityManager")
        self.identity_manager = IdentityManager(config, self.time_service)

        # In first-run mode, skip identity seeding - user hasn't selected template yet
        # Identity will be seeded in resume_from_first_run() after setup completes
        if is_first_run():
            logger.info("First-run mode: Skipping identity seeding (will seed after setup wizard)")
            return

        self.agent_identity = await self.identity_manager.initialize_identity()

        # Create startup node for continuity tracking
        await self._create_startup_node()

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

        # Register adapter services immediately after adapters start
        # This ensures communication and other adapter services are available before components build
        init_manager.register_step(
            phase=InitializationPhase.SERVICES,
            name="Register Adapter Services",
            handler=self._register_adapter_services,
            critical=True,
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
                    # log_dir defaults to None, which uses path_resolution.get_logs_dir()
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
        # Use environment-based database URL if set, otherwise use SQLite path from config
        # This allows PostgreSQL support via CIRIS_DB_URL environment variable
        from ciris_engine.logic.persistence.db.dialect import get_adapter

        adapter = get_adapter()
        if adapter.is_postgresql():
            # PostgreSQL: Use None to trigger environment-based connection
            db_path = None
            logger.info("Using PostgreSQL database from environment (CIRIS_DB_URL)")
        else:
            # SQLite: Use direct path from essential_config to avoid config service dependency
            db_path = str(self.essential_config.database.main_db)
            logger.info(f"Using SQLite database: {db_path}")

        persistence.initialize_database(db_path)
        persistence.run_migrations(db_path)

        if not self.essential_config:
            # Use default essential config if none provided
            self.essential_config = EssentialConfig()
            self.essential_config.load_env_vars()  # Load CIRIS_DB_URL and other env vars
            logger.warning("No config provided, using defaults")

    async def _verify_database_integrity(self) -> bool:
        """Verify database integrity before proceeding."""
        try:
            from ciris_engine.logic.persistence.db.dialect import get_adapter

            adapter = get_adapter()
            # Use environment-based connection for PostgreSQL, direct path for SQLite
            db_path = None if adapter.is_postgresql() else str(self.essential_config.database.main_db)
            conn = persistence.get_db_connection(db_path)
            cursor = conn.cursor()

            adapter = get_adapter()
            required_tables = ["tasks", "thoughts", "graph_nodes", "graph_edges"]

            for table in required_tables:
                # Use database-specific query
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
        """Verify identity was properly established.

        In first-run mode, identity is not seeded yet (waiting for user to select template),
        so we only verify that the identity manager was created.
        """
        from ciris_engine.logic.setup.first_run import is_first_run

        if not self.identity_manager:
            logger.error("Identity manager not initialized")
            return False

        # In first-run mode, identity isn't seeded yet - just verify manager exists
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
        """Initialize all remaining core services.

        In first-run mode, identity is not yet established (user selects template in setup wizard).
        We skip full service initialization - only the API adapter runs for the setup wizard.
        """
        from ciris_engine.logic.setup.first_run import is_first_run

        config = self._ensure_config()

        # In first-run mode, skip service initialization - we only need the API server
        if is_first_run():
            logger.info("First-run mode: Skipping core service initialization (setup wizard only)")
            return

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
            self.audit_service._runtime = self  # type: ignore[attr-defined]
            logger.debug("Set runtime reference on audit service for trace correlations")

        # Set runtime on visibility service so it can access telemetry for traces
        if self.visibility_service:
            self.visibility_service._runtime = self  # type: ignore[attr-defined]
            logger.debug("Set runtime reference on visibility service for trace retrieval")

        # Update runtime control service with runtime reference
        if self.runtime_control_service:
            if hasattr(self.runtime_control_service, "_set_runtime"):
                self.runtime_control_service._set_runtime(self)
            else:
                self.runtime_control_service.runtime = self  # type: ignore[attr-defined]
            logger.info("Updated runtime control service with runtime reference")

        # Update telemetry service with runtime reference for aggregator
        if self.telemetry_service:
            if hasattr(self.telemetry_service, "_set_runtime"):
                self.telemetry_service._set_runtime(self)
                logger.info("Updated telemetry service with runtime reference for aggregator")

    async def _verify_core_services(self) -> bool:
        """Verify all core services are operational.

        In first-run mode, services aren't initialized yet - just return True.
        """
        from ciris_engine.logic.setup.first_run import is_first_run

        if is_first_run():
            logger.info("First-run mode: Core services verification skipped")
            return True

        return self.service_initializer.verify_core_services()

    async def _initialize_maintenance_service(self) -> None:
        """Initialize the maintenance service and perform startup cleanup.

        In first-run mode, services aren't initialized - skip maintenance.
        """
        from ciris_engine.logic.setup.first_run import is_first_run

        if is_first_run():
            logger.info("First-run mode: Skipping maintenance service initialization")
            return

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

        # Migrate tickets config from template (first-run only)
        await self._migrate_tickets_config_to_graph()

        # Migrate cognitive state behaviors (pre-1.7 compatibility)
        await self._migrate_cognitive_state_behaviors_to_graph()

    async def _migrate_tickets_config_to_graph(self) -> None:
        """Migrate tickets config to graph.

        This handles two scenarios:
        1. First-run: Seeds tickets config from template to graph
        2. Pre-1.7.0 upgrade: Adds default DSAR SOPs for existing agents without tickets config

        After migration, tickets.py retrieves config from graph, not template.
        """
        if not self.service_initializer or not self.service_initializer.config_service:
            logger.warning("Cannot migrate tickets config - GraphConfigService not available")
            return

        config_service = self.service_initializer.config_service

        # Check if tickets config already exists in graph
        try:
            existing_config = await config_service.get_config("tickets")
            if existing_config and existing_config.value and existing_config.value.dict_value:
                logger.debug("Tickets config already exists in graph - skipping migration")
                return
        except Exception:
            pass  # Config doesn't exist, proceed with migration

        # Try to get tickets config from template (first-run scenario)
        tickets_config = None
        if self.identity_manager and self.identity_manager.agent_template:
            tickets_config = self.identity_manager.agent_template.tickets

        # If no template available (pre-1.7.0 agent upgrade), create default DSAR SOPs
        if not tickets_config:
            logger.info("No tickets config found - creating default DSAR SOPs for pre-1.7.0 compatibility")
            from ciris_engine.schemas.config.default_dsar_sops import DEFAULT_DSAR_SOPS
            from ciris_engine.schemas.config.tickets import TicketsConfig

            tickets_config = TicketsConfig(enabled=True, sops=DEFAULT_DSAR_SOPS)

        try:
            # Store tickets config as a dict in the graph with IDENTITY scope (WA-protected)
            from ciris_engine.schemas.services.graph_core import GraphScope

            await config_service.set_config(
                key="tickets",
                value=tickets_config.model_dump(),
                updated_by="system_bootstrap",
                scope=GraphScope.IDENTITY,  # Protected - agent cannot modify
            )
            logger.info("Migrated tickets config to graph (IDENTITY scope - WA-protected)")
        except Exception as e:
            logger.error(f"Failed to migrate tickets config to graph: {e}")

    def _should_skip_cognitive_migration(self, force_from_template: bool) -> bool:
        """Check if cognitive migration should be skipped (first-run mode without force)."""
        from ciris_engine.logic.setup.first_run import is_first_run

        if is_first_run() and not force_from_template:
            logger.info("[COGNITIVE_MIGRATION] First-run mode: Skipping migration (will seed after setup wizard)")
            return True
        return False

    async def _check_existing_cognitive_config(self, config_service: Any) -> bool:
        """Check if cognitive config already exists in graph.

        Returns True if config exists and should skip migration.
        """
        try:
            existing_config = await config_service.get_config("cognitive_state_behaviors")
            if existing_config and existing_config.value and existing_config.value.dict_value:
                existing_wakeup = existing_config.value.dict_value.get("wakeup", {})
                logger.info(
                    f"[COGNITIVE_MIGRATION] Config already exists in graph - wakeup.enabled={existing_wakeup.get('enabled', 'MISSING')}"
                )
                logger.info("[COGNITIVE_MIGRATION] Skipping migration (existing config preserved)")
                return True
        except Exception as e:
            logger.info(f"[COGNITIVE_MIGRATION] No existing config in graph (will migrate): {e}")
        return False

    def _get_cognitive_behaviors_from_template(self) -> Optional[Any]:
        """Get cognitive behaviors from the agent template if available."""
        logger.info(f"[COGNITIVE_MIGRATION] identity_manager={self.identity_manager is not None}")
        if not self.identity_manager or not self.identity_manager.agent_template:
            logger.info("[COGNITIVE_MIGRATION] No template available (identity_manager or agent_template is None)")
            return None

        template = self.identity_manager.agent_template
        logger.info(f"[COGNITIVE_MIGRATION] Template loaded: name={getattr(template, 'name', 'UNKNOWN')}")
        cognitive_behaviors = getattr(template, "cognitive_state_behaviors", None)
        if cognitive_behaviors:
            logger.info(
                f"[COGNITIVE_MIGRATION] Template has cognitive_state_behaviors: wakeup.enabled={cognitive_behaviors.wakeup.enabled}"
            )
        else:
            logger.info("[COGNITIVE_MIGRATION] Template has NO cognitive_state_behaviors attribute")
        return cognitive_behaviors

    def _create_legacy_cognitive_behaviors(self) -> Any:
        """Create pre-1.7 compatible cognitive behaviors config."""
        from ciris_engine.schemas.config.cognitive_state_behaviors import (
            CognitiveStateBehaviors,
            DreamBehavior,
            StateBehavior,
            StatePreservationBehavior,
        )

        logger.info("No cognitive state behaviors found - creating pre-1.7 compatible config")
        return CognitiveStateBehaviors(
            play=StateBehavior(
                enabled=False,
                rationale="Pre-1.7 agent: PLAY state not available in legacy version",
            ),
            dream=DreamBehavior(
                enabled=False,
                auto_schedule=False,
                rationale="Pre-1.7 agent: DREAM state not available in legacy version",
            ),
            solitude=StateBehavior(
                enabled=False,
                rationale="Pre-1.7 agent: SOLITUDE state not available in legacy version",
            ),
            state_preservation=StatePreservationBehavior(
                enabled=True,
                resume_silently=False,
                rationale="Pre-1.7 agent: preserve state across restarts",
            ),
        )

    async def _save_cognitive_behaviors_to_graph(self, config_service: Any, cognitive_behaviors: Any) -> None:
        """Save cognitive behaviors to the graph with IDENTITY scope."""
        from ciris_engine.schemas.services.graph_core import GraphScope

        config_dict = cognitive_behaviors.model_dump()
        logger.info(
            f"[COGNITIVE_MIGRATION] Saving to graph: wakeup.enabled={config_dict.get('wakeup', {}).get('enabled', 'MISSING')}"
        )
        await config_service.set_config(
            key="cognitive_state_behaviors",
            value=config_dict,
            updated_by="system_bootstrap",
            scope=GraphScope.IDENTITY,
        )
        logger.info("[COGNITIVE_MIGRATION] SUCCESS - Migrated cognitive state behaviors to graph (IDENTITY scope)")

    async def _migrate_cognitive_state_behaviors_to_graph(self, force_from_template: bool = False) -> None:
        """Migrate cognitive state behaviors to graph.

        This handles two scenarios:
        1. First-run: Seeds cognitive behaviors from template to graph
        2. Pre-1.7.0 upgrade: Adds legacy-compatible behaviors (PLAY/DREAM/SOLITUDE disabled)

        Pre-1.7 agents get:
        - Wakeup: enabled (full identity ceremony)
        - Shutdown: always_consent (Covenant compliance)
        - Play/Dream/Solitude: DISABLED (these states didn't exist pre-1.7)

        After migration, StateManager retrieves config from graph, not template.

        Args:
            force_from_template: If True, always seed from template (used during resume_from_first_run
                when template is now available). This overwrites any pre-existing config.
        """
        if self._should_skip_cognitive_migration(force_from_template):
            return

        if not self.service_initializer or not self.service_initializer.config_service:
            logger.warning("[COGNITIVE_MIGRATION] Cannot migrate - GraphConfigService not available")
            return

        config_service = self.service_initializer.config_service

        logger.info("[COGNITIVE_MIGRATION] Starting cognitive state behaviors migration check...")
        logger.info(f"[COGNITIVE_MIGRATION] force_from_template={force_from_template}")

        if not force_from_template:
            if await self._check_existing_cognitive_config(config_service):
                return
        else:
            logger.info("[COGNITIVE_MIGRATION] Force mode: Will overwrite existing config with template values")

        # Try to get cognitive behaviors from template
        cognitive_behaviors = self._get_cognitive_behaviors_from_template()

        # If no template available, use Covenant-compliant defaults (all states enabled)
        # This applies to fresh installs without templates (e.g., QA testing, API-only mode)
        # Note: The old pre-1.7 upgrade logic disabled PLAY/DREAM/SOLITUDE, but this was
        # overly conservative. Default behavior should enable all states - users can disable
        # specific states via template configuration if needed.
        if not cognitive_behaviors:
            from ciris_engine.schemas.config.cognitive_state_behaviors import CognitiveStateBehaviors

            logger.info("[COGNITIVE_MIGRATION] No template - using Covenant-compliant defaults (all states enabled)")
            cognitive_behaviors = CognitiveStateBehaviors()

        try:
            await self._save_cognitive_behaviors_to_graph(config_service, cognitive_behaviors)
        except Exception as e:
            logger.error(f"[COGNITIVE_MIGRATION] FAILED to migrate cognitive state behaviors to graph: {e}")

    async def _final_verification(self) -> None:
        """Perform final system verification.

        In first-run mode, identity isn't established yet - skip full verification.
        """
        from ciris_engine.logic.setup.first_run import is_first_run

        # In first-run mode, identity isn't established yet
        if is_first_run():
            logger.info("First-run mode: Skipping final verification (waiting for setup wizard)")
            logger.info("=" * 60)
            logger.info("CIRIS Agent First-Run Mode Active")
            logger.info("Setup wizard is ready at http://127.0.0.1:8080/setup")
            logger.info("=" * 60)
            return

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
                        await self.config_service.graph.forget(graph_node)  # type: ignore[attr-defined]
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
        """Register services provided by the loaded adapters.

        In first-run mode, skip registration since services aren't initialized.
        """
        from ciris_engine.logic.setup.first_run import is_first_run

        if is_first_run():
            logger.info("First-run mode: Skipping adapter service registration")
            return

        if not self.service_registry:
            logger.error("ServiceRegistry not initialized. Cannot register adapter services.")
            return

        for adapter in self.adapters:
            try:
                # Generate authentication token for adapter - REQUIRED for security
                adapter_type = adapter.__class__.__name__.lower().replace("adapter", "")
                # Explicitly type as JSONDict for authentication service compatibility
                adapter_info: JSONDict = {
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

    def _build_adapter_info(self, adapter: Any) -> JSONDict:
        """Build adapter info dictionary for authentication token creation."""
        adapter_info: JSONDict = {
            "instance_id": str(id(adapter)),
            "startup_time": (
                self.time_service.now().isoformat() if self.time_service else datetime.now(timezone.utc).isoformat()
            ),
        }
        # Get channel-specific info if available
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
        """Register adapter services during resume_from_first_run.

        This is identical to _register_adapter_services but without the is_first_run check,
        since we explicitly want to register during resume.
        """
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

        # Check if LLM service is available - if not, check if this is first-run setup mode
        if not self.llm_service:
            from ciris_engine.logic.setup.first_run import is_first_run

            if is_first_run():
                logger.info("[_build_components] First-run setup mode - LLM not yet configured")
                logger.info("[_build_components] Setup wizard will guide LLM configuration")
            else:
                logger.error("[_build_components] LLM service not available but setup was completed!")
                logger.error(
                    "[_build_components] Check your LLM configuration - the agent cannot operate without an LLM"
                )
            return

        try:
            self.component_builder = ComponentBuilder(self)
            logger.info("[_build_components] ComponentBuilder created successfully")

            self.agent_processor = await self.component_builder.build_all_components()
            logger.info(f"[_build_components] agent_processor created: {self.agent_processor}")

            # Set up thought tracking callback now that agent_processor exists
            # This avoids the race condition where RuntimeControlService tried to access
            # agent_processor during Phase 5 (SERVICES) before it was created in Phase 6 (COMPONENTS)
            if self.runtime_control_service:
                self.runtime_control_service.setup_thought_tracking()  # type: ignore[attr-defined]
                logger.debug("Thought tracking callback set up after agent_processor creation")

        except Exception as e:
            logger.error(f"[_build_components] Failed to build components: {e}", exc_info=True)
            raise

        # Register core services after components are built
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

        # Log adapter configuration details
        log_adapter_configuration_details(self.adapters)

        # Check if this is first-run - skip agent processor if so
        first_run = is_first_run()
        if first_run:
            logger.info("")
            logger.info("=" * 70)
            logger.info("🔧 FIRST RUN DETECTED - Setup Wizard Mode")
            logger.info("=" * 70)
            logger.info("")
            logger.info("The agent processor will NOT start in first-run mode.")
            logger.info("Only the API server is running to provide the setup wizard.")
            logger.info("")
            logger.info("📋 Next Steps:")
            logger.info("  1. Open your browser to: http://localhost:8080")
            logger.info("  2. Complete the setup wizard")
            logger.info("  3. Restart the agent with: ciris-agent")
            logger.info("")
            logger.info("After restart, the full agent will start normally.")
            logger.info("=" * 70)
            logger.info("")

            # Only wait for adapters to be ready, but don't start agent processor
            adapters_ready = await wait_for_adapter_readiness(self.adapters)
            if not adapters_ready:
                raise RuntimeError("Adapters failed to become ready within timeout")

            # No agent processor task in first-run mode
            self._adapter_tasks = create_adapter_lifecycle_tasks(self.adapters, agent_task=None)

            # Skip service registration and processor - API will handle setup
            logger.info("✅ Setup wizard ready at http://localhost:8080")
            logger.info("Waiting for setup completion... (Press CTRL+C to exit)")
            return

        # Normal mode - create agent processor task and adapter lifecycle tasks
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

    def _is_using_ciris_proxy(self) -> bool:
        """Check if runtime is configured to use CIRIS proxy."""
        llm_base_url = os.getenv("OPENAI_API_BASE", "")
        return any(domain in llm_base_url for domain in CIRIS_PROXY_DOMAINS)

    def _create_billing_token_handler(self, credit_provider: Any) -> Callable[..., Any]:
        """Create handler for billing token refresh signals."""

        async def handle_billing_token_refreshed(signal: str, resource: str) -> None:
            new_token = os.getenv("CIRIS_BILLING_GOOGLE_ID_TOKEN", "")
            if new_token and credit_provider:
                credit_provider.update_google_id_token(new_token)
                logger.info("✓ Updated billing provider with refreshed Google ID token")

        return handle_billing_token_refreshed

    def _create_llm_token_handler(self) -> Callable[..., Any]:
        """Create handler for LLM service token refresh signals."""

        async def handle_llm_token_refreshed(signal: str, resource: str) -> None:
            new_token = os.getenv("OPENAI_API_KEY", "")
            if not new_token:
                logger.warning("[LLM_TOKEN] No OPENAI_API_KEY in env after token refresh")
                return

            self._update_llm_services_token(new_token)

        return handle_llm_token_refreshed

    def _update_llm_services_token(self, new_token: str) -> None:
        """Update all LLM services that use CIRIS proxy with new token."""
        if self.service_registry:
            llm_services = self.service_registry.get_services_by_type(ServiceType.LLM)
            for service in llm_services:
                self._update_service_token_if_ciris_proxy(service, new_token)

        if self.llm_service:
            self._update_service_token_if_ciris_proxy(self.llm_service, new_token, is_primary=True)

    def _update_service_token_if_ciris_proxy(self, service: Any, new_token: str, is_primary: bool = False) -> None:
        """Update a service's API key if it uses CIRIS proxy."""
        if not hasattr(service, "openai_config") or not service.openai_config:
            return
        if not hasattr(service, "update_api_key"):
            return

        base_url = getattr(service.openai_config, "base_url", "") or ""
        if not any(domain in base_url for domain in CIRIS_PROXY_DOMAINS):
            return

        service.update_api_key(new_token)
        label = "primary LLM service" if is_primary else type(service).__name__
        logger.info(f"✓ Updated {label} with refreshed token")

    async def _reinitialize_billing_provider(self) -> None:
        """Reinitialize billing provider after setup completes.

        Called during resume_from_first_run to set up billing now that
        environment variables (OPENAI_API_BASE, CIRIS_BILLING_GOOGLE_ID_TOKEN)
        are available from the newly created .env file.
        """
        resource_monitor = self._get_resource_monitor_for_billing()
        if not resource_monitor:
            return

        is_android = "ANDROID_DATA" in os.environ
        using_ciris_proxy = self._is_using_ciris_proxy()

        logger.info(f"Billing provider check: is_android={is_android}, using_ciris_proxy={using_ciris_proxy}")
        logger.info(f"  OPENAI_API_BASE={os.getenv('OPENAI_API_BASE', '')}")

        if not (is_android and using_ciris_proxy):
            logger.info("Billing provider not needed (not using CIRIS proxy or not Android)")
            return

        google_id_token = os.getenv("CIRIS_BILLING_GOOGLE_ID_TOKEN", "")
        if not google_id_token:
            logger.warning("Android using CIRIS LLM proxy without Google ID token - billing provider not configured")
            return

        credit_provider = self._create_billing_provider(google_id_token)
        resource_monitor.credit_provider = credit_provider

        # Register token refresh handlers
        resource_monitor.signal_bus.register("token_refreshed", self._create_billing_token_handler(credit_provider))
        logger.info("✓ Reinitialized CIRISBillingProvider with JWT auth (CIRIS LLM proxy)")
        logger.info("✓ Registered token_refreshed handler for billing provider")

        resource_monitor.signal_bus.register("token_refreshed", self._create_llm_token_handler())
        logger.info("✓ Registered token_refreshed handler for LLM service")

    def _get_resource_monitor_for_billing(self) -> Any:
        """Get resource monitor service for billing initialization.

        Returns the resource monitor service or None if not available.
        Uses Any type since we access implementation-specific attributes
        (credit_provider, signal_bus) not in the protocol.
        """
        if not self.service_initializer:
            logger.warning("Cannot reinitialize billing - service_initializer not available")
            return None

        resource_monitor = self.service_initializer.resource_monitor_service
        if not resource_monitor:
            logger.warning("Cannot reinitialize billing - resource_monitor_service not available")
            return None

        return resource_monitor

    def _create_billing_provider(self, google_id_token: str) -> Any:
        """Create and configure the CIRIS billing provider."""
        from ciris_engine.logic.services.infrastructure.resource_monitor import CIRISBillingProvider

        base_url = get_billing_url()  # Checks env var first, then falls back to central config
        timeout = float(os.getenv("CIRIS_BILLING_TIMEOUT_SECONDS", "5.0"))
        cache_ttl = int(os.getenv("CIRIS_BILLING_CACHE_TTL_SECONDS", "15"))
        fail_open = os.getenv("CIRIS_BILLING_FAIL_OPEN", "false").lower() == "true"

        def get_fresh_token() -> str:
            return os.getenv("CIRIS_BILLING_GOOGLE_ID_TOKEN", "")

        return CIRISBillingProvider(
            google_id_token=google_id_token,
            token_refresh_callback=get_fresh_token,
            base_url=base_url,
            timeout_seconds=timeout,
            cache_ttl_seconds=cache_ttl,
            fail_open=fail_open,
        )

    def _resume_reload_environment(
        self, log_step: Callable[[int, int, str], None], total_steps: int
    ) -> "EssentialConfig":
        """Reload environment and config during resume from first-run."""
        from dotenv import load_dotenv

        from ciris_engine.logic.setup.first_run import get_default_config_path

        config_path = get_default_config_path()
        log_step(2, total_steps, f"Config path: {config_path}, exists: {config_path.exists()}")
        if config_path.exists():
            load_dotenv(config_path, override=True)
            log_step(2, total_steps, f"✓ Reloaded environment from {config_path}")
        else:
            log_step(2, total_steps, f"⚠️ Config path does not exist: {config_path}")

        config = self._ensure_config()
        config.load_env_vars()
        log_step(3, total_steps, f"✓ Config reloaded - default_template: {config.default_template}")
        return config

    async def _resume_initialize_identity(
        self, config: "EssentialConfig", log_step: Callable[[int, int, str], None], total_steps: int
    ) -> None:
        """Initialize identity with user-selected template during resume."""
        log_step(
            4,
            total_steps,
            f"Initializing identity... identity_manager={self.identity_manager is not None}, "
            f"time_service={self.time_service is not None}",
        )
        if self.identity_manager and self.time_service:
            self.identity_manager = IdentityManager(config, self.time_service)
            self.agent_identity = await self.identity_manager.initialize_identity()
            await self._create_startup_node()
            log_step(
                4,
                total_steps,
                f"✓ Agent identity initialized: {self.agent_identity.agent_id if self.agent_identity else 'None'}",
            )
        else:
            log_step(4, total_steps, "⚠️ Skipped identity init - missing identity_manager or time_service")

    async def _resume_migrate_cognitive_behaviors(
        self, log_step: Callable[[int, int, str], None], total_steps: int
    ) -> None:
        """Migrate cognitive state behaviors from template during resume."""
        log_step(5, total_steps, "Migrating cognitive state behaviors from template...")
        if self.identity_manager and self.identity_manager.agent_template:
            template_name = getattr(self.identity_manager.agent_template, "name", "UNKNOWN")
            cognitive_behaviors = getattr(self.identity_manager.agent_template, "cognitive_state_behaviors", None)
            if cognitive_behaviors:
                log_step(
                    5,
                    total_steps,
                    f"Template '{template_name}' has cognitive_state_behaviors: "
                    f"wakeup.enabled={cognitive_behaviors.wakeup.enabled}",
                )
            else:
                log_step(
                    5, total_steps, f"Template '{template_name}' has no cognitive_state_behaviors (will use defaults)"
                )
            await self._migrate_cognitive_state_behaviors_to_graph(force_from_template=True)
            log_step(5, total_steps, "✓ Cognitive state behaviors migrated from template")
        else:
            log_step(5, total_steps, "⚠️ No template available - using default cognitive behaviors")
            await self._migrate_cognitive_state_behaviors_to_graph(force_from_template=False)

    def _set_service_runtime_references(self) -> None:
        """Set runtime references on services that need them."""
        if self.audit_service:
            self.audit_service._runtime = self  # type: ignore[attr-defined]
            logger.debug("Set runtime reference on audit service for trace correlations")

        if self.visibility_service:
            self.visibility_service._runtime = self  # type: ignore[attr-defined]
            logger.debug("Set runtime reference on visibility service for trace retrieval")

        if self.runtime_control_service:
            if hasattr(self.runtime_control_service, "_set_runtime"):
                self.runtime_control_service._set_runtime(self)
            else:
                self.runtime_control_service.runtime = self  # type: ignore[attr-defined]
            logger.info("Updated runtime control service with runtime reference")

        if self.telemetry_service and hasattr(self.telemetry_service, "_set_runtime"):
            self.telemetry_service._set_runtime(self)
            logger.info("Updated telemetry service with runtime reference for aggregator")

    async def _resume_initialize_core_services(
        self, config: "EssentialConfig", log_step: Callable[[int, int, str], None], total_steps: int
    ) -> None:
        """Initialize core services during resume."""
        log_step(
            6,
            total_steps,
            f"Initializing core services... service_initializer={self.service_initializer is not None}, "
            f"agent_identity={self.agent_identity is not None}",
        )
        if not (self.service_initializer and self.agent_identity):
            log_step(6, total_steps, "⚠️ Skipped core services - missing service_initializer or agent_identity")
            return

        await self.service_initializer.initialize_all_services(
            config,
            self.essential_config,
            self.agent_identity.agent_id,
            self.startup_channel_id,
            self.modules_to_load,
        )
        log_step(6, total_steps, "✓ Core services initialized")

        self._set_service_runtime_references()

        if self.modules_to_load:
            log_step(6, total_steps, f"Loading {len(self.modules_to_load)} external modules: {self.modules_to_load}")
            await self.service_initializer.load_modules(self.modules_to_load)

    async def _resume_initialize_llm(self, log_step: Callable[[int, int, str], None], total_steps: int) -> None:
        """Initialize LLM service during resume."""
        log_step(
            10, total_steps, f"Initializing LLM service... service_initializer={self.service_initializer is not None}"
        )
        if self.service_initializer:
            config = self._ensure_config()
            await self.service_initializer._initialize_llm_services(config, self.modules_to_load)
            log_step(10, total_steps, "✓ LLM service initialized")
        else:
            log_step(10, total_steps, "⚠️ Skipped LLM init - no service_initializer")

    def _resume_reinject_adapters(self, log_step: Callable[[int, int, str], None], total_steps: int) -> None:
        """Re-inject services into running adapters during resume."""
        log_step(11, total_steps, f"Re-injecting services into {len(self.adapters)} adapters...")
        for adapter in self.adapters:
            if hasattr(adapter, "reinject_services"):
                adapter.reinject_services()
                log_step(11, total_steps, f"✓ Re-injected services into {adapter.__class__.__name__}")

    async def _resume_auto_enable_android_adapters(self) -> None:
        """Auto-enable Android-specific adapters after resume.

        Calls _auto_enable_android_adapters on any adapters that have it,
        which enables ciris_hosted_tools (web_search) when:
        - Running on Android with Google auth
        - The adapter is not already loaded
        """
        for adapter in self.adapters:
            if hasattr(adapter, "_auto_enable_android_adapters"):
                try:
                    await adapter._auto_enable_android_adapters()
                    logger.info(f"[RESUME] Called _auto_enable_android_adapters on {adapter.__class__.__name__}")
                except Exception as e:
                    logger.warning(
                        f"[RESUME] Failed to auto-enable Android adapters on {adapter.__class__.__name__}: {e}"
                    )

    async def resume_from_first_run(self) -> None:
        """Resume initialization after setup wizard completes.

        This continues from the point where first-run mode paused (line 1088).
        It executes the same steps as normal mode initialization.
        """
        # Set flag AND timestamp to prevent premature shutdown during resume
        # The timestamp allows timeout detection for stuck resume scenarios
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
        logger.warning("🔄 RESUMING FROM FIRST-RUN MODE")
        logger.warning("=" * 70)
        logger.warning("")
        log_step(1, total_steps, "Starting resume from first-run...")

        # Steps 2-3: Reload environment and config
        config = self._resume_reload_environment(log_step, total_steps)

        # Step 4: Initialize identity with user-selected template
        await self._resume_initialize_identity(config, log_step, total_steps)

        # Step 5: Migrate cognitive behaviors from template
        await self._resume_migrate_cognitive_behaviors(log_step, total_steps)

        # Step 6: Initialize core services
        await self._resume_initialize_core_services(config, log_step, total_steps)

        # Step 7: Register adapter services
        log_step(7, total_steps, "Registering adapter services...")
        await self._register_adapter_services_for_resume()
        log_step(7, total_steps, "✓ Adapter services registered")

        # Step 8: Initialize maintenance service
        log_step(
            8, total_steps, f"Initializing maintenance... maintenance_service={self.maintenance_service is not None}"
        )
        if self.maintenance_service:
            await self._perform_startup_maintenance()
            log_step(8, total_steps, "✓ Maintenance service initialized")
        else:
            log_step(8, total_steps, "⚠️ Skipped maintenance - no maintenance_service")

        # Step 9: Reinitialize billing provider
        log_step(9, total_steps, "Reinitializing billing provider...")
        await self._reinitialize_billing_provider()
        log_step(9, total_steps, "✓ Billing provider reinitialized")

        # Step 10: Initialize LLM service
        await self._resume_initialize_llm(log_step, total_steps)

        # Step 11: Re-inject services into adapters
        self._resume_reinject_adapters(log_step, total_steps)

        # Step 12: Auto-enable Android-specific adapters (ciris_hosted_tools with web_search)
        log_step(12, total_steps, "Auto-enabling Android adapters...")
        await self._resume_auto_enable_android_adapters()
        log_step(12, total_steps, "✓ Android adapters auto-enabled")

        # Step 13: Build cognitive components
        log_step(13, total_steps, "Building cognitive components...")
        await self._build_components()
        log_step(13, total_steps, "✓ Cognitive components built")

        # Step 14: Create agent processor task
        log_step(14, total_steps, "Creating agent processor task...")
        self._agent_task = asyncio.create_task(self._create_agent_processor_when_ready(), name="AgentProcessorTask")
        log_step(14, total_steps, "Waiting for critical services (timeout=10s)...")
        await self._wait_for_critical_services(timeout=10.0)

        elapsed = time.time() - start_time
        logger.warning("")
        logger.warning(f"✅ RESUME COMPLETE in {elapsed:.2f}s - Agent processor started!")
        logger.warning("=" * 70)
        logger.warning("")

        # Clear the resume flag and timestamp - safe to shutdown now
        self._resume_in_progress = False
        self._resume_started_at = None
        logger.info(f"[RESUME] Completed in {elapsed:.2f}s, _resume_in_progress=False")

    async def _create_agent_processor_when_ready(self) -> None:
        """Create and start agent processor once all services are ready.

        This replaces the placeholder task pattern with proper dependency injection.
        """
        logger.info("Waiting for services to be ready before starting agent processor...")

        # Wait for all critical services to be available
        await self._wait_for_critical_services(timeout=30.0)

        # Check if agent processor is built (may be None in first-run setup mode)
        if not self.agent_processor:
            from ciris_engine.logic.setup.first_run import is_first_run

            if is_first_run():
                logger.info("Agent processor not started - first-run setup mode active")
            else:
                logger.error("Agent processor not initialized but setup was completed!")
                logger.error("This indicates a configuration error - check LLM settings")
            return

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
        logger.debug(f"[AUDIT self.service_initializer exists: {self.service_initializer is not None}")
        if self.service_initializer:
            logger.debug(f"[AUDIT service_initializer.audit_service: {self.service_initializer.audit_service}")
        logger.debug(f"[AUDIT Creating BusManager with audit_service={self.audit_service}")
        logger.debug(f"[AUDIT self.audit_service type: {type(self.audit_service)}")
        logger.debug(f"[AUDIT self.audit_service is None: {self.audit_service is None}")

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

    def _should_exit_runtime_loop(
        self, agent_task: Optional[asyncio.Task[Any]], shutdown_logged: bool
    ) -> tuple[bool, bool]:
        """Check if runtime loop should exit.

        Returns:
            Tuple of (should_exit, shutdown_logged)
        """
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
        """Handle completed runtime tasks.

        Returns:
            Tuple of (should_break, is_shutdown)
        """
        from .ciris_runtime_helpers import handle_runtime_agent_task_completion, handle_runtime_task_failures

        # Check for shutdown signal
        if (self._shutdown_event and self._shutdown_event.is_set()) or is_global_shutdown_requested():
            return True, True

        # Check if agent task completed
        if agent_task and agent_task in done:
            handle_runtime_agent_task_completion(self, agent_task, adapter_tasks)
            return True, False

        # Handle other task failures
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
            # Set up runtime monitoring tasks
            agent_task, adapter_tasks, all_tasks = setup_runtime_monitoring_tasks(self)
            if not all_tasks:
                logger.error("No tasks to monitor - exiting")
                return

            # Keep monitoring until shutdown or agent task completes
            shutdown_logged = False
            while True:
                # Check exit conditions
                should_exit, shutdown_logged = self._should_exit_runtime_loop(agent_task, shutdown_logged)
                if should_exit:
                    break

                done, pending = await asyncio.wait(all_tasks, return_when=asyncio.FIRST_COMPLETED, timeout=1.0)

                # Remove completed tasks from all_tasks to avoid re-processing
                all_tasks = [t for t in all_tasks if t not in done]

                # Monitor shutdown signals
                shutdown_logged = monitor_runtime_shutdown_signals(self, shutdown_logged)

                # Handle task completion
                should_break, _ = self._handle_completed_runtime_tasks(done, agent_task, adapter_tasks, all_tasks)
                if should_break:
                    break

            # Finalize execution
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

    async def _create_startup_node(self) -> None:
        """Create startup node for continuity tracking."""
        try:
            from ciris_engine.schemas.services.graph_core import GraphNode, GraphScope, NodeType
            from ciris_engine.schemas.types import JSONDict

            # Create memory node for startup
            startup_node = GraphNode(
                id=f"startup_{self.time_service.now().isoformat() if self.time_service else datetime.now(timezone.utc).isoformat()}",
                type=NodeType.AGENT,
                scope=GraphScope.IDENTITY,
                attributes={"created_by": "runtime_startup", "tags": ["startup", "continuity_awareness"]},
            )

            # Store in memory service
            if self.memory_service:
                await self.memory_service.memorize(startup_node)
                logger.info(f"Created startup continuity node: {startup_node.id}")

        except Exception as e:
            logger.error(f"Failed to create startup node: {e}")

    def _determine_shutdown_consent_status(self) -> str:
        """Determine if shutdown was consensual based on agent processor result.

        Returns:
            Consent status: 'accepted', 'rejected', or 'manual'
        """
        if not self.agent_processor or not hasattr(self.agent_processor, "shutdown_processor"):
            return "manual"

        shutdown_proc = self.agent_processor.shutdown_processor
        if not shutdown_proc or not hasattr(shutdown_proc, "shutdown_result"):
            return "manual"

        result = shutdown_proc.shutdown_result
        if not result:
            return "manual"

        if result.action == "shutdown_accepted" or result.status == "completed":
            return "accepted"
        elif result.action == "shutdown_rejected" or result.status == "rejected":
            return "rejected"

        return "manual"

    def _build_shutdown_node_attributes(self, reason: str, consent_status: str) -> JSONDict:
        """Build attributes dict for shutdown memory node.

        Args:
            reason: Shutdown reason text
            consent_status: Consent status ('accepted', 'rejected', 'manual')

        Returns:
            Dictionary of node attributes
        """
        now = self.time_service.now() if self.time_service else datetime.now(timezone.utc)
        return {
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
            "created_by": "runtime_shutdown",
            "tags": ["shutdown", "continuity_awareness"],
            "reason": reason,
            "consent_status": consent_status,
        }

    async def _update_identity_with_shutdown_reference(self, shutdown_node_id: str) -> None:
        """Update agent identity with shutdown memory reference.

        Args:
            shutdown_node_id: ID of the shutdown node created
        """
        if not self.agent_identity or not hasattr(self.agent_identity, "core_profile"):
            return

        self.agent_identity.core_profile.last_shutdown_memory = shutdown_node_id

        # Increment modification count
        if hasattr(self.agent_identity, "identity_metadata"):
            self.agent_identity.identity_metadata.modification_count += 1

        # Save updated identity
        if self.identity_manager:
            await self.identity_manager._save_identity_to_graph(self.agent_identity)
            logger.debug("Agent identity updates saved to persistence layer")
        else:
            logger.debug("Agent identity updates stored in memory graph")

    async def _preserve_shutdown_continuity(self) -> None:
        """Preserve agent state for future reactivation."""
        try:
            from ciris_engine.schemas.runtime.extended import ShutdownContext
            from ciris_engine.schemas.services.graph_core import GraphNode, GraphScope, NodeType

            # Create shutdown context
            shutdown_context = ShutdownContext(
                is_terminal=False,
                reason=self._shutdown_reason or "Graceful shutdown",
                initiated_by="runtime",
                allow_deferral=False,
                expected_reactivation=None,
                agreement_context=None,
            )

            # Determine consent status and build node
            consent_status = self._determine_shutdown_consent_status()
            now = self.time_service.now() if self.time_service else datetime.now(timezone.utc)

            shutdown_node = GraphNode(
                id=f"shutdown_{now.isoformat()}",
                type=NodeType.AGENT,
                scope=GraphScope.IDENTITY,
                attributes=self._build_shutdown_node_attributes(shutdown_context.reason, consent_status),
            )

            # Store in memory service
            if self.memory_service:
                await self.memory_service.memorize(shutdown_node)
                logger.info(f"Preserved shutdown continuity: {shutdown_node.id}")
                await self._update_identity_with_shutdown_reference(shutdown_node.id)

        except Exception as e:
            logger.error(f"Failed to preserve shutdown continuity: {e}")

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
        if bootstrap is not None:
            self.bootstrap = bootstrap
            self.essential_config = essential_config or EssentialConfig()
            self.essential_config.load_env_vars()  # Load environment variables
            self.startup_channel_id = bootstrap.startup_channel_id or ""
            self.adapter_configs = bootstrap.adapter_overrides
            self.modules_to_load = bootstrap.modules
            self.debug = bootstrap.debug
            self._preload_tasks = bootstrap.preload_tasks
        else:
            self._create_bootstrap_from_legacy(
                essential_config, startup_channel_id, adapter_types, adapter_configs, kwargs
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
        self.essential_config = essential_config or EssentialConfig()
        self.essential_config.load_env_vars()  # Load environment variables
        self.startup_channel_id = startup_channel_id or ""
        self.adapter_configs = adapter_configs or {}
        # Type narrow: kwargs.get returns JSONDict value, narrow to expected types
        modules_raw = kwargs.get("modules", [])
        self.modules_to_load = modules_raw if isinstance(modules_raw, list) else []
        debug_raw = kwargs.get("debug", False)
        self.debug = debug_raw if isinstance(debug_raw, bool) else False
        self._preload_tasks = []

        from ciris_engine.schemas.runtime.adapter_management import AdapterLoadRequest
        from ciris_engine.schemas.runtime.bootstrap import RuntimeBootstrapConfig

        adapter_load_requests = [
            AdapterLoadRequest(adapter_type=atype, adapter_id=atype, auto_start=True) for atype in adapter_types
        ]
        self.bootstrap = RuntimeBootstrapConfig(
            adapters=adapter_load_requests,
            adapter_overrides=self.adapter_configs,
            modules=self.modules_to_load,
            startup_channel_id=self.startup_channel_id,
            debug=self.debug,
            preload_tasks=self._preload_tasks,
        )

    def _check_mock_llm(self) -> None:
        """Check for mock LLM environment variable and add to modules if needed."""
        if os.environ.get("CIRIS_MOCK_LLM", "").lower() in ("true", "1", "yes", "on"):
            logger.warning("CIRIS_MOCK_LLM environment variable detected in CIRISRuntime")
            if "mock_llm" not in self.modules_to_load:
                self.modules_to_load.append("mock_llm")
                logger.info("Added mock_llm to modules to load")

    def _load_adapters_from_bootstrap(self) -> None:
        """Load adapters from bootstrap configuration."""
        for load_request in self.bootstrap.adapters:
            try:
                adapter_class = load_adapter(load_request.adapter_type)

                # Create AdapterStartupContext
                from ciris_engine.schemas.adapters.runtime_context import AdapterStartupContext

                context = AdapterStartupContext(
                    essential_config=self.essential_config or EssentialConfig(),
                    modules_to_load=self.modules_to_load,
                    startup_channel_id=self.startup_channel_id or "",
                    debug=self.debug,
                    bus_manager=None,  # Will be set after initialization
                    time_service=None,  # Will be set after initialization
                    service_registry=None,  # Will be set after initialization
                )

                # Apply overrides if present
                config = load_request.config or AdapterConfig(adapter_type=load_request.adapter_type)
                if load_request.adapter_id in self.adapter_configs:
                    config = self.adapter_configs[load_request.adapter_id]

                # Create adapter with context
                # Pass the settings as adapter_config so adapters can find them
                adapter_instance = adapter_class(self, context=context, adapter_config=config.settings)  # type: ignore[call-arg]
                self.adapters.append(adapter_instance)
                logger.info(f"Successfully loaded adapter: {load_request.adapter_id}")
            except Exception as e:
                logger.error(f"Failed to load adapter '{load_request.adapter_id}': {e}", exc_info=True)
