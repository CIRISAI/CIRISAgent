"""
Initialization step handlers for CIRISRuntime.

Contains the individual initialization step implementations that are registered
with the InitializationService for phased startup.
"""

import asyncio
import logging
import os
from typing import TYPE_CHECKING, Any, Optional

from ciris_engine.logic import persistence
from ciris_engine.schemas.config.essential import EssentialConfig
from ciris_engine.schemas.services.operations import InitializationPhase

if TYPE_CHECKING:
    from ciris_engine.logic.runtime.identity_manager import IdentityManager

logger = logging.getLogger(__name__)


def register_all_initialization_steps(
    runtime: Any,
    init_manager: Any,
) -> None:
    """Register all initialization steps with the initialization manager.

    Args:
        runtime: The CIRISRuntime instance
        init_manager: The InitializationService instance
    """
    # Phase 0: INFRASTRUCTURE (must be first)
    init_manager.register_step(
        phase=InitializationPhase.INFRASTRUCTURE,
        name="Initialize Infrastructure Services",
        handler=lambda: initialize_infrastructure(runtime),
        verifier=lambda: verify_infrastructure(runtime),
        critical=True,
    )

    # Phase 1: DATABASE
    init_manager.register_step(
        phase=InitializationPhase.DATABASE,
        name="Initialize Database",
        handler=lambda: init_database(runtime),
        verifier=lambda: verify_database_integrity(runtime),
        critical=True,
    )

    # Phase 2: MEMORY
    init_manager.register_step(
        phase=InitializationPhase.MEMORY,
        name="Memory Service",
        handler=lambda: initialize_memory_service(runtime),
        verifier=lambda: verify_memory_service(runtime),
        critical=True,
    )

    # Phase 3: IDENTITY
    init_manager.register_step(
        phase=InitializationPhase.IDENTITY,
        name="Agent Identity",
        handler=lambda: initialize_identity(runtime),
        verifier=lambda: verify_identity_integrity(runtime),
        critical=True,
    )

    # Phase 4: SECURITY
    init_manager.register_step(
        phase=InitializationPhase.SECURITY,
        name="Security Services",
        handler=lambda: initialize_security_services(runtime),
        verifier=lambda: verify_security_services(runtime),
        critical=True,
    )

    # Phase 5: SERVICES
    init_manager.register_step(
        phase=InitializationPhase.SERVICES,
        name="Core Services",
        handler=lambda: initialize_services(runtime),
        verifier=lambda: verify_core_services(runtime),
        critical=True,
    )

    init_manager.register_step(
        phase=InitializationPhase.SERVICES,
        name="Start Adapters",
        handler=lambda: start_adapters(runtime),
        critical=True,
    )

    init_manager.register_step(
        phase=InitializationPhase.SERVICES,
        name="Register Adapter Services",
        handler=lambda: register_adapter_services(runtime),
        critical=True,
    )

    init_manager.register_step(
        phase=InitializationPhase.SERVICES,
        name="Initialize Maintenance Service",
        handler=lambda: initialize_maintenance_service(runtime),
        critical=True,
    )

    # Phase 6: COMPONENTS
    init_manager.register_step(
        phase=InitializationPhase.COMPONENTS,
        name="Build Components",
        handler=lambda: build_components(runtime),
        critical=True,
    )

    init_manager.register_step(
        phase=InitializationPhase.COMPONENTS,
        name="Start Adapter Connections",
        handler=lambda: start_adapter_connections(runtime),
        critical=True,
        timeout=45.0,
    )

    # Phase 7: VERIFICATION
    init_manager.register_step(
        phase=InitializationPhase.VERIFICATION,
        name="Final System Verification",
        handler=lambda: final_verification(runtime),
        critical=True,
    )


async def initialize_infrastructure(runtime: Any) -> None:
    """Initialize infrastructure services that all other services depend on."""
    if not os.environ.get("PYTEST_CURRENT_TEST"):
        from ciris_engine.logic.utils.logging_config import setup_basic_logging

        time_service = runtime.service_initializer.time_service
        if not time_service:
            error_msg = "CRITICAL: TimeService not available - CANNOT INITIALIZE FILE LOGGING"
            logger.critical(error_msg)
            raise RuntimeError(error_msg)

        try:
            setup_basic_logging(
                level=logging.DEBUG if runtime.debug else logging.INFO,
                log_to_file=True,
                console_output=False,
                enable_incident_capture=True,
                time_service=time_service,
            )
            logger.info("[_initialize_infrastructure] File logging initialized successfully")
        except Exception as e:
            error_msg = f"CRITICAL: Failed to setup file logging: {e}"
            logger.critical(error_msg)
            raise RuntimeError(error_msg)
    else:
        logger.debug("[_initialize_infrastructure] Test mode detected, skipping file logging setup")


async def verify_infrastructure(runtime: Any) -> bool:
    """Verify infrastructure services are operational."""
    if not runtime.service_initializer.time_service:
        logger.error("TimeService not initialized")
        return False
    if not runtime.service_initializer.shutdown_service:
        logger.error("ShutdownService not initialized")
        return False
    if not runtime.service_initializer.initialization_service:
        logger.error("InitializationService not initialized")
        return False
    return True


async def init_database(runtime: Any) -> None:
    """Initialize database and run migrations."""
    from ciris_engine.logic.persistence.db.dialect import get_adapter

    adapter = get_adapter()
    if adapter.is_postgresql():
        db_path = None
        logger.info("Using PostgreSQL database from environment (CIRIS_DB_URL)")
    else:
        db_path = str(runtime.essential_config.database.main_db)
        logger.info(f"Using SQLite database: {db_path}")

    persistence.initialize_database(db_path)
    persistence.run_migrations(db_path)

    if not runtime.essential_config:
        runtime.essential_config = EssentialConfig()
        runtime.essential_config.load_env_vars()
        logger.warning("No config provided, using defaults")


async def verify_database_integrity(runtime: Any) -> bool:
    """Verify database integrity before proceeding."""
    try:
        from ciris_engine.logic.persistence.db.dialect import get_adapter

        adapter = get_adapter()
        db_path = None if adapter.is_postgresql() else str(runtime.essential_config.database.main_db)
        conn = persistence.get_db_connection(db_path)
        cursor = conn.cursor()

        adapter = get_adapter()
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


async def initialize_memory_service(runtime: Any) -> None:
    """Initialize memory service early for identity storage."""
    config = _ensure_config(runtime)
    await runtime.service_initializer.initialize_memory_service(config)


async def verify_memory_service(runtime: Any) -> bool:
    """Verify memory service is operational."""
    result: bool = await runtime.service_initializer.verify_memory_service()
    return result


async def initialize_identity(runtime: Any) -> None:
    """Initialize agent identity.

    In first-run mode, this only creates the IdentityManager but does NOT seed the graph.
    The actual identity seeding happens in resume_from_first_run() AFTER the user selects
    their template in the setup wizard.

    If --identity-update flag is set, refresh identity from template after normal init.
    """
    from ciris_engine.logic.runtime.identity_manager import IdentityManager
    from ciris_engine.logic.setup.first_run import is_first_run

    config = _ensure_config(runtime)
    if not runtime.time_service:
        raise RuntimeError("TimeService not available for IdentityManager")
    runtime.identity_manager = IdentityManager(config, runtime.time_service)

    if is_first_run():
        logger.info("First-run mode: Skipping identity seeding (will seed after setup wizard)")
        return

    runtime.agent_identity = await runtime.identity_manager.initialize_identity()

    # Handle --identity-update flag for admin template refresh
    identity_update = getattr(runtime, "_identity_update", False)
    logger.info(f"[IDENTITY_UPDATE] Checking flag: _identity_update={identity_update}, bootstrap.identity_update={getattr(runtime.bootstrap, 'identity_update', 'N/A')}")
    if identity_update:
        template_name = getattr(config, "default_template", "default")
        logger.info(f"Identity update requested - refreshing from template '{template_name}'")
        success = await runtime.identity_manager.refresh_identity_from_template(
            template_name=template_name,
            updated_by="admin",
        )
        if success:
            runtime.agent_identity = runtime.identity_manager.agent_identity
            logger.info("Identity successfully updated from template")
        else:
            logger.error("Failed to update identity from template")
            raise RuntimeError("Identity update failed - cannot proceed")

    await runtime._create_startup_node()


async def verify_identity_integrity(runtime: Any) -> bool:
    """Verify identity was properly established.

    In first-run mode, identity is not seeded yet (waiting for user to select template),
    so we only verify that the identity manager was created.
    """
    from ciris_engine.logic.setup.first_run import is_first_run

    if not runtime.identity_manager:
        logger.error("Identity manager not initialized")
        return False

    if is_first_run():
        logger.info("First-run mode: Identity manager created (identity will be seeded after setup)")
        return True

    result: bool = await runtime.identity_manager.verify_identity_integrity()
    return result


async def initialize_security_services(runtime: Any) -> None:
    """Initialize security-critical services first."""
    config = _ensure_config(runtime)
    await runtime.service_initializer.initialize_security_services(config, runtime.essential_config)


async def verify_security_services(runtime: Any) -> bool:
    """Verify security services are operational."""
    result: bool = await runtime.service_initializer.verify_security_services()
    return result


async def initialize_services(runtime: Any) -> None:
    """Initialize all remaining core services.

    In first-run mode, identity is not yet established (user selects template in setup wizard).
    We skip full service initialization - only the API adapter runs for the setup wizard.
    """
    from ciris_engine.logic.setup.first_run import is_first_run

    config = _ensure_config(runtime)

    if is_first_run():
        logger.info("First-run mode: Skipping core service initialization (setup wizard only)")
        return

    if not runtime.agent_identity:
        raise RuntimeError("CRITICAL: Cannot initialize services without agent identity")

    await runtime.service_initializer.initialize_all_services(
        config,
        runtime.essential_config,
        runtime.agent_identity.agent_id,
        runtime.startup_channel_id,
        runtime.modules_to_load,
    )

    if runtime.modules_to_load:
        logger.info(f"Loading {len(runtime.modules_to_load)} external modules: {runtime.modules_to_load}")
        await runtime.service_initializer.load_modules(runtime.modules_to_load)

    _set_service_runtime_references(runtime)


async def verify_core_services(runtime: Any) -> bool:
    """Verify all core services are operational.

    In first-run mode, services aren't initialized yet - just return True.
    """
    from ciris_engine.logic.setup.first_run import is_first_run

    if is_first_run():
        logger.info("First-run mode: Core services verification skipped")
        return True

    result: bool = runtime.service_initializer.verify_core_services()
    return result


async def start_adapters(runtime: Any) -> None:
    """Start all adapters."""
    await asyncio.gather(*(adapter.start() for adapter in runtime.adapters))
    logger.info(f"All {len(runtime.adapters)} adapters started")
    await runtime._migrate_adapter_configs_to_graph()


async def register_adapter_services(runtime: Any) -> None:
    """Register services provided by the loaded adapters.

    In first-run mode, skip registration since services aren't initialized.
    """
    await runtime._register_adapter_services()


async def initialize_maintenance_service(runtime: Any) -> None:
    """Initialize the maintenance service and perform startup cleanup.

    In first-run mode, services aren't initialized - skip maintenance.
    """
    from ciris_engine.logic.setup.first_run import is_first_run

    if is_first_run():
        logger.info("First-run mode: Skipping maintenance service initialization")
        return

    if not runtime.maintenance_service:
        raise RuntimeError("Maintenance service was not initialized properly")
    logger.info("Maintenance service verified available")

    await runtime._perform_startup_maintenance()


async def build_components(runtime: Any) -> None:
    """Build all processing components."""
    await runtime._build_components()


async def start_adapter_connections(runtime: Any) -> None:
    """Start adapter connections and wait for them to be ready."""
    await runtime._start_adapter_connections()


async def final_verification(runtime: Any) -> None:
    """Perform final system verification.

    In first-run mode, identity isn't established yet - skip full verification.
    """
    from ciris_engine.logic.setup.first_run import is_first_run

    if is_first_run():
        logger.info("First-run mode: Skipping final verification (waiting for setup wizard)")
        logger.info("=" * 60)
        logger.info("CIRIS Agent First-Run Mode Active")
        logger.info("Setup wizard is ready at http://127.0.0.1:8080/setup")
        logger.info("=" * 60)
        return

    if not runtime.agent_identity:
        raise RuntimeError("No agent identity established")

    logger.info("=" * 60)
    logger.info("CIRIS Agent Pre-Wakeup Verification Complete")
    logger.info(f"Identity: {runtime.agent_identity.agent_id}")
    logger.info(f"Purpose: {runtime.agent_identity.core_profile.description}")
    logger.info(f"Capabilities: {len(runtime.agent_identity.permitted_actions)} allowed")

    service_count = 0
    if runtime.service_registry:
        registry_info = runtime.service_registry.get_provider_info()
        for service_list in registry_info.get("services", {}).values():
            service_count += len(service_list)

    logger.info(f"Services: {service_count} registered")
    logger.info("=" * 60)


def _ensure_config(runtime: Any) -> EssentialConfig:
    """Ensure essential_config is available, raise if not."""
    if not runtime.essential_config:
        raise RuntimeError("Essential config not initialized")
    config: EssentialConfig = runtime.essential_config
    return config


def _set_service_runtime_references(runtime: Any) -> None:
    """Set runtime references on services that need them."""
    if runtime.audit_service:
        runtime.audit_service._runtime = runtime
        logger.debug("Set runtime reference on audit service for trace correlations")

    if runtime.visibility_service:
        runtime.visibility_service._runtime = runtime
        logger.debug("Set runtime reference on visibility service for trace retrieval")

    if runtime.runtime_control_service:
        if hasattr(runtime.runtime_control_service, "_set_runtime"):
            runtime.runtime_control_service._set_runtime(runtime)
        else:
            runtime.runtime_control_service.runtime = runtime
        logger.info("Updated runtime control service with runtime reference")

    if runtime.telemetry_service and hasattr(runtime.telemetry_service, "_set_runtime"):
        runtime.telemetry_service._set_runtime(runtime)
        logger.info("Updated telemetry service with runtime reference for aggregator")
