"""
Initialization step handlers for CIRISRuntime.

Contains the individual initialization step implementations that are registered
with the InitializationService for phased startup.
"""

import asyncio
import logging
import os
from typing import TYPE_CHECKING, Any, Dict, Optional, Set

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
        name="Load Saved Adapters",
        handler=lambda: load_saved_adapters_from_graph(runtime),
        critical=False,  # Non-critical - system can run without saved adapters
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
    template_name = getattr(runtime, "_template_name", None) or getattr(config, "default_template", "default")
    logger.info(f"[IDENTITY_UPDATE] Checking flag: _identity_update={identity_update}, template_name={template_name}")
    if identity_update:
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


def _extract_config_value(config_node: Any) -> Any:
    """Extract the actual value from a ConfigNode.

    ConfigNode.value is a ConfigValue wrapper with a .value property.
    This helper safely extracts the underlying value.
    """
    if config_node is None:
        return None

    # If it's already a primitive type, return as-is
    if isinstance(config_node, (str, int, float, bool, list, dict)):
        return config_node

    # ConfigNode has .value which is ConfigValue, which has .value property
    if hasattr(config_node, "value"):
        config_value = config_node.value
        # ConfigValue has a .value property that returns the actual value
        if hasattr(config_value, "value"):
            return config_value.value
        # Or it might be the value directly
        return config_value

    return config_node


def _get_runtime_service(runtime: Any, service_name: str) -> Any:
    """Get a service from runtime's service_initializer."""
    if not hasattr(runtime, "service_initializer") or not runtime.service_initializer:
        return None
    return getattr(runtime.service_initializer, service_name, None)


def _extract_adapter_ids_from_configs(all_configs: Dict[str, Any]) -> Set[str]:
    """Extract unique adapter IDs from config keys."""
    adapter_ids: Set[str] = set()
    for key in all_configs.keys():
        parts = key.split(".")
        if len(parts) >= 2 and parts[0] == "adapter":
            adapter_ids.add(parts[1])
    return adapter_ids


def _get_bootstrap_adapter_ids(runtime: Any) -> Set[str]:
    """Get adapter IDs already loaded from bootstrap."""
    bootstrap_ids: Set[str] = set()
    for adapter in runtime.adapters:
        adapter_id = getattr(adapter, "adapter_id", None)
        if adapter_id:
            bootstrap_ids.add(adapter_id)
    return bootstrap_ids


def _build_adapter_config_from_data(adapter_type: str, adapter_config_data: Any) -> Optional[Any]:
    """Build AdapterConfig from saved config data."""
    if not adapter_config_data:
        return None

    from ciris_engine.schemas.runtime.adapter_management import AdapterConfig

    if isinstance(adapter_config_data, AdapterConfig):
        return adapter_config_data

    if isinstance(adapter_config_data, dict):
        return AdapterConfig(
            adapter_type=adapter_type,
            enabled=adapter_config_data.get("enabled", True),
            settings=adapter_config_data.get("settings", {}),
            adapter_config=adapter_config_data.get("adapter_config"),
        )

    return None


async def _load_single_saved_adapter(
    adapter_id: str,
    config_service: Any,
    adapter_manager: Any,
    bootstrap_ids: Set[str],
    current_occurrence_id: str,
) -> bool:
    """Load a single saved adapter from graph config. Returns True if loaded.

    In multi-occurrence deployments, only loads adapters that were saved by this occurrence
    or adapters without an occurrence_id (legacy/shared adapters).
    """
    # Skip if already loaded
    if adapter_id in bootstrap_ids:
        logger.debug(f"Adapter {adapter_id} already loaded from bootstrap, skipping")
        return False

    if adapter_id in adapter_manager.loaded_adapters:
        logger.debug(f"Adapter {adapter_id} already in adapter_manager, skipping")
        return False

    # Get adapter type, config, and occurrence_id
    adapter_type_node = await config_service.get_config(f"adapter.{adapter_id}.type")
    adapter_config_node = await config_service.get_config(f"adapter.{adapter_id}.config")
    occurrence_id_node = await config_service.get_config(f"adapter.{adapter_id}.occurrence_id")

    adapter_type = _extract_config_value(adapter_type_node)
    adapter_config_data = _extract_config_value(adapter_config_node)
    saved_occurrence_id = _extract_config_value(occurrence_id_node)

    # Check occurrence_id - only load if matches current occurrence
    # Adapters WITHOUT occurrence_id are legacy adapters - load them on any occurrence
    # (they will be stamped with current occurrence_id when next saved)
    if saved_occurrence_id is not None and saved_occurrence_id != current_occurrence_id:
        logger.debug(
            f"Adapter {adapter_id} belongs to occurrence {saved_occurrence_id}, "
            f"current is {current_occurrence_id}, skipping"
        )
        return False

    if not adapter_type or not isinstance(adapter_type, str):
        logger.warning(f"No valid adapter type found for saved adapter {adapter_id}, skipping")
        return False

    adapter_config = _build_adapter_config_from_data(adapter_type, adapter_config_data)
    logger.info(
        f"Loading saved adapter: {adapter_id} (type: {adapter_type}, occurrence: {saved_occurrence_id or 'legacy'})"
    )

    result = await adapter_manager.load_adapter(
        adapter_type=adapter_type,
        adapter_id=adapter_id,
        config_params=adapter_config,
    )

    if result.success:
        logger.info(f"Successfully loaded saved adapter: {adapter_id}")
        return True

    logger.warning(f"Failed to load saved adapter {adapter_id}: {result.message}")
    return False


async def load_saved_adapters_from_graph(runtime: Any) -> None:
    """Load adapters that were saved to the graph config service.

    This restores dynamically loaded adapters (added via API) after restart.
    Skipped in first-run mode since config service isn't available.

    In multi-occurrence deployments, only loads adapters saved by this occurrence.
    """
    from ciris_engine.logic.setup.first_run import is_first_run
    from ciris_engine.logic.utils.occurrence_utils import get_current_occurrence_id

    if is_first_run():
        logger.info("First-run mode: Skipping saved adapter loading")
        return

    config_service = _get_runtime_service(runtime, "config_service")
    if not config_service:
        logger.debug("Config service not available - skipping saved adapter loading")
        return

    # Get adapter_manager from runtime_control_service (not directly from service_initializer)
    runtime_control_service = _get_runtime_service(runtime, "runtime_control_service")
    if not runtime_control_service:
        logger.debug("Runtime control service not available - skipping saved adapter loading")
        return

    adapter_manager = getattr(runtime_control_service, "adapter_manager", None)
    if not adapter_manager:
        logger.debug("Adapter manager not available on runtime_control_service - skipping saved adapter loading")
        return

    try:
        # Get current occurrence ID for filtering
        current_occurrence_id = get_current_occurrence_id()

        all_configs = await config_service.list_configs(prefix="adapter.")
        adapter_ids = _extract_adapter_ids_from_configs(all_configs)
        logger.info(f"Found {len(adapter_ids)} saved adapter configs in graph (occurrence={current_occurrence_id})")

        bootstrap_ids = _get_bootstrap_adapter_ids(runtime)
        loaded_count = 0

        for adapter_id in adapter_ids:
            loaded = await _load_single_saved_adapter(
                adapter_id, config_service, adapter_manager, bootstrap_ids, current_occurrence_id
            )
            if loaded:
                loaded_count += 1

        if loaded_count > 0:
            logger.info(f"Loaded {loaded_count} saved adapters from graph for occurrence {current_occurrence_id}")

    except Exception as e:
        logger.error(f"Error loading saved adapters from graph: {e}", exc_info=True)


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
