"""
Resume from first-run helpers for CIRISRuntime.

Contains helper functions for resuming initialization after the setup wizard completes.
These functions are used by resume_from_first_run() to complete the initialization
that was paused during first-run mode.
"""

import logging
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from ciris_engine.schemas.config.essential import EssentialConfig

logger = logging.getLogger(__name__)


def reload_environment_for_resume(
    runtime: Any, log_step: Callable[[int, int, str], None], total_steps: int
) -> "EssentialConfig":
    """Reload environment and config during resume from first-run."""
    from dotenv import load_dotenv

    from ciris_engine.logic.setup.first_run import get_default_config_path

    config_path = get_default_config_path()
    log_step(2, total_steps, f"Config path: {config_path}, exists: {config_path.exists()}")
    if config_path.exists():
        load_dotenv(config_path, override=True)
        log_step(2, total_steps, f"Reloaded environment from {config_path}")
    else:
        log_step(2, total_steps, f"Config path does not exist: {config_path}")

    config = _ensure_config(runtime)
    config.load_env_vars()
    log_step(3, total_steps, f"Config reloaded - default_template: {config.default_template}")
    return config


async def initialize_identity_for_resume(
    runtime: Any, config: "EssentialConfig", log_step: Callable[[int, int, str], None], total_steps: int
) -> None:
    """Initialize identity with user-selected template during resume."""
    from ciris_engine.logic.runtime.identity_manager import IdentityManager

    log_step(
        4,
        total_steps,
        f"Initializing identity... identity_manager={runtime.identity_manager is not None}, "
        f"time_service={runtime.time_service is not None}",
    )
    if runtime.identity_manager and runtime.time_service:
        runtime.identity_manager = IdentityManager(config, runtime.time_service)
        runtime.agent_identity = await runtime.identity_manager.initialize_identity()
        await runtime._create_startup_node()
        log_step(
            4,
            total_steps,
            f"Agent identity initialized: {runtime.agent_identity.agent_id if runtime.agent_identity else 'None'}",
        )
    else:
        log_step(4, total_steps, "Skipped identity init - missing identity_manager or time_service")


async def migrate_cognitive_behaviors_for_resume(
    runtime: Any, log_step: Callable[[int, int, str], None], total_steps: int
) -> None:
    """Migrate cognitive state behaviors from template during resume."""
    from ciris_engine.logic.runtime.config_migration import migrate_cognitive_state_behaviors_to_graph

    log_step(5, total_steps, "Migrating cognitive state behaviors from template...")
    if runtime.identity_manager and runtime.identity_manager.agent_template:
        template_name = getattr(runtime.identity_manager.agent_template, "name", "UNKNOWN")
        cognitive_behaviors = getattr(runtime.identity_manager.agent_template, "cognitive_state_behaviors", None)
        if cognitive_behaviors:
            log_step(
                5,
                total_steps,
                f"Template '{template_name}' has cognitive_state_behaviors: "
                f"wakeup.enabled={cognitive_behaviors.wakeup.enabled}",
            )
        else:
            log_step(5, total_steps, f"Template '{template_name}' has no cognitive_state_behaviors (will use defaults)")
        await migrate_cognitive_state_behaviors_to_graph(runtime, force_from_template=True)
        log_step(5, total_steps, "Cognitive state behaviors migrated from template")
    else:
        log_step(5, total_steps, "No template available - using default cognitive behaviors")
        await migrate_cognitive_state_behaviors_to_graph(runtime, force_from_template=False)


def set_service_runtime_references(runtime: Any) -> None:
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


async def initialize_core_services_for_resume(
    runtime: Any, config: "EssentialConfig", log_step: Callable[[int, int, str], None], total_steps: int
) -> None:
    """Initialize core services during resume."""
    log_step(
        6,
        total_steps,
        f"Initializing core services... service_initializer={runtime.service_initializer is not None}, "
        f"agent_identity={runtime.agent_identity is not None}",
    )
    if not (runtime.service_initializer and runtime.agent_identity):
        log_step(6, total_steps, "Skipped core services - missing service_initializer or agent_identity")
        return

    await runtime.service_initializer.initialize_all_services(
        config,
        runtime.essential_config,
        runtime.agent_identity.agent_id,
        runtime.startup_channel_id,
        runtime.modules_to_load,
    )
    log_step(6, total_steps, "Core services initialized")

    set_service_runtime_references(runtime)

    if runtime.modules_to_load:
        log_step(6, total_steps, f"Loading {len(runtime.modules_to_load)} external modules: {runtime.modules_to_load}")
        await runtime.service_initializer.load_modules(runtime.modules_to_load)


async def initialize_llm_for_resume(runtime: Any, log_step: Callable[[int, int, str], None], total_steps: int) -> None:
    """Initialize LLM service during resume."""
    log_step(
        10, total_steps, f"Initializing LLM service... service_initializer={runtime.service_initializer is not None}"
    )
    if runtime.service_initializer:
        config = _ensure_config(runtime)
        await runtime.service_initializer._initialize_llm_services(config, runtime.modules_to_load)
        log_step(10, total_steps, "LLM service initialized")
    else:
        log_step(10, total_steps, "Skipped LLM init - no service_initializer")


def reinject_adapters_for_resume(runtime: Any, log_step: Callable[[int, int, str], None], total_steps: int) -> None:
    """Re-inject services into running adapters during resume."""
    log_step(11, total_steps, f"Re-injecting services into {len(runtime.adapters)} adapters...")
    for adapter in runtime.adapters:
        if hasattr(adapter, "reinject_services"):
            adapter.reinject_services()
            log_step(11, total_steps, f"Re-injected services into {adapter.__class__.__name__}")


async def auto_enable_android_adapters_for_resume(runtime: Any) -> None:
    """Auto-enable Android-specific adapters after resume.

    Calls _auto_enable_android_adapters on any adapters that have it,
    which enables ciris_hosted_tools (web_search) when:
    - Running on Android with Google auth
    - The adapter is not already loaded
    """
    for adapter in runtime.adapters:
        if hasattr(adapter, "_auto_enable_android_adapters"):
            try:
                await adapter._auto_enable_android_adapters()
                logger.info(f"[RESUME] Called _auto_enable_android_adapters on {adapter.__class__.__name__}")
            except Exception as e:
                logger.warning(f"[RESUME] Failed to auto-enable Android adapters on {adapter.__class__.__name__}: {e}")


async def auto_enable_environment_adapters_for_resume(runtime: Any) -> None:
    """Auto-enable adapters based on detected runtime environment.

    This is the centralized entry point for environment-based adapter enabling.
    Currently supports:

    1. Home Assistant Addon Mode (SUPERVISOR_TOKEN present):
       - Auto-enables home_assistant adapter with supervisor authentication
       - No OAuth required, uses HA's automatic token injection

    2. Android Platform (CIRIS_ANDROID + Google Auth):
       - Delegated to auto_enable_android_adapters_for_resume()

    Called during runtime resume after core services are initialized.
    """
    import os

    # Check for HA addon mode (SUPERVISOR_TOKEN present)
    if os.getenv("SUPERVISOR_TOKEN"):
        await _auto_enable_ha_addon_adapter(runtime)

    # Android-specific adapters (delegated to existing logic)
    await auto_enable_android_adapters_for_resume(runtime)


async def _auto_enable_ha_addon_adapter(runtime: Any) -> None:
    """Auto-enable Home Assistant adapter when running as HA addon.

    When SUPERVISOR_TOKEN is present (injected by HA Supervisor),
    the home_assistant adapter can be auto-enabled with automatic
    authentication - no OAuth flow required.
    """
    import os

    supervisor_token = os.getenv("SUPERVISOR_TOKEN")
    if not supervisor_token:
        return

    # Check if home_assistant adapter is already loaded
    loaded_adapter_types = set()
    for adapter in runtime.adapters:
        adapter_type = getattr(adapter, "adapter_type", None)
        if adapter_type:
            loaded_adapter_types.add(str(adapter_type).lower())
        class_name = adapter.__class__.__name__.lower()
        if "homeassistant" in class_name or "home_assistant" in class_name:
            loaded_adapter_types.add("home_assistant")

    if "home_assistant" in loaded_adapter_types:
        logger.debug("[AUTO_ENABLE] home_assistant adapter already loaded, skipping")
        return

    logger.info("[AUTO_ENABLE] HA addon mode detected (SUPERVISOR_TOKEN present) - enabling home_assistant adapter")

    try:
        # Use runtime_control_service to load the adapter properly
        runtime_control = getattr(runtime, "runtime_control_service", None)
        if not runtime_control:
            logger.warning("[AUTO_ENABLE] No runtime_control_service available for adapter loading")
            return

        result = await runtime_control.load_adapter(
            adapter_type="home_assistant",
            adapter_id="home_assistant_auto",
            config={
                "supervisor_mode": True,
                "auto_enabled": True,
            },
        )

        if result.success:
            logger.info(f"[AUTO_ENABLE] Successfully auto-enabled home_assistant adapter (id: {result.adapter_id})")

            # Persist to CIRIS_ADAPTER env for next restart
            existing = os.environ.get("CIRIS_ADAPTER", "")
            if "home_assistant" not in existing:
                new_adapters = f"{existing},home_assistant" if existing else "home_assistant"
                os.environ["CIRIS_ADAPTER"] = new_adapters
                logger.info(f"[AUTO_ENABLE] Updated CIRIS_ADAPTER: {new_adapters}")

                # Try to persist to .env file
                await _persist_adapter_to_env("home_assistant")
        else:
            logger.warning(f"[AUTO_ENABLE] Failed to enable home_assistant adapter: {result.error}")
    except Exception as e:
        logger.warning(f"[AUTO_ENABLE] Error enabling home_assistant adapter: {e}")


async def _persist_adapter_to_env(adapter_type: str) -> None:
    """Persist adapter to .env file for next restart."""
    try:
        from ciris_engine.logic.utils.path_resolution import get_env_file_path

        env_path = get_env_file_path()
        if env_path and env_path.exists():
            content = env_path.read_text()
            lines = content.split("\n")
            updated = False

            for i, line in enumerate(lines):
                if line.startswith("CIRIS_ADAPTER="):
                    existing = line.split("=", 1)[1].strip().strip('"')
                    if adapter_type not in existing:
                        new_value = f"{existing},{adapter_type}" if existing else adapter_type
                        lines[i] = f'CIRIS_ADAPTER="{new_value}"'
                        updated = True
                    break

            if not updated:
                # Add new CIRIS_ADAPTER line
                lines.append(f'CIRIS_ADAPTER="{adapter_type}"')

            env_path.write_text("\n".join(lines))
            logger.info(f"[AUTO_ENABLE] Persisted {adapter_type} to .env file")
    except Exception as e:
        logger.debug(f"[AUTO_ENABLE] Could not persist {adapter_type} to .env: {e}")


# Bootstrap adapters that are always loaded at startup (before setup wizard)
BOOTSTRAP_ADAPTERS = {"api", "cli", "ciris_verify"}


async def _persist_adapter_to_graph(runtime: Any, adapter_type: str, adapter_config: Any) -> None:
    """Persist adapter config to graph so it loads on subsequent restarts.

    Uses the same key pattern as RuntimeAdapterManager: adapter.{adapter_id}.*
    """
    from ciris_engine.logic.utils.occurrence_utils import get_current_occurrence_id

    config_service = getattr(runtime, "config_service", None)
    if not config_service:
        logger.warning(f"[RESUME] No config_service - cannot persist adapter {adapter_type} to graph")
        return

    try:
        occurrence_id = get_current_occurrence_id()
        adapter_id = adapter_type  # Use adapter_type as ID for simplicity

        # Save adapter config to graph (same pattern as RuntimeAdapterManager)
        await config_service.set_config(f"adapter.{adapter_id}.type", adapter_type)
        await config_service.set_config(f"adapter.{adapter_id}.config", adapter_config.model_dump_json())
        await config_service.set_config(f"adapter.{adapter_id}.occurrence_id", occurrence_id)
        await config_service.set_config(f"adapter.{adapter_id}.persist", True)

        logger.info(f"[RESUME] Persisted adapter {adapter_type} to graph (occurrence={occurrence_id})")
    except Exception as e:
        logger.warning(f"[RESUME] Failed to persist adapter {adapter_type} to graph: {e}")


async def load_post_setup_adapters_for_resume(
    runtime: Any, log_step: Callable[[int, int, str], None], total_steps: int
) -> None:
    """Load adapters that were enabled during setup wizard.

    This loads adapters that require setup to complete first, such as:
    - cirisnode: Requires Portal registration and signing key provisioning

    Bootstrap adapters (api, cli, ciris_verify) are already loaded and skipped.

    Args:
        runtime: The CIRISRuntime instance
        log_step: Logging callback
        total_steps: Total steps for progress logging
    """
    import os

    from ciris_engine.logic.adapters import load_adapter
    from ciris_engine.schemas.adapters.runtime_context import AdapterStartupContext
    from ciris_engine.schemas.config.essential import EssentialConfig
    from ciris_engine.schemas.runtime.adapter_management import AdapterConfig

    # Get enabled adapters from environment (set during setup as CIRIS_ADAPTER)
    enabled_adapters_str = os.environ.get("CIRIS_ADAPTER", "")
    if not enabled_adapters_str:
        log_step(12, total_steps, "No CIRIS_ADAPTER configured - skipping post-setup adapter loading")
        return

    enabled_adapters = [a.strip() for a in enabled_adapters_str.split(",") if a.strip()]
    log_step(12, total_steps, f"Enabled adapters from config: {enabled_adapters}")

    # Get currently loaded adapter types
    loaded_adapter_types = set()
    for adapter in runtime.adapters:
        adapter_type = getattr(adapter, "adapter_type", None)
        if adapter_type:
            loaded_adapter_types.add(str(adapter_type).lower())
        # Also check class name
        class_name = adapter.__class__.__name__.lower()
        if "api" in class_name:
            loaded_adapter_types.add("api")
        if "cli" in class_name:
            loaded_adapter_types.add("cli")
        if "verify" in class_name:
            loaded_adapter_types.add("ciris_verify")

    log_step(12, total_steps, f"Already loaded adapters: {loaded_adapter_types}")

    # Filter to adapters that need loading (not bootstrap, not already loaded)
    adapters_to_load = [
        a for a in enabled_adapters if a.lower() not in BOOTSTRAP_ADAPTERS and a.lower() not in loaded_adapter_types
    ]

    if not adapters_to_load:
        log_step(12, total_steps, "All enabled adapters already loaded - nothing to do")
        return

    log_step(12, total_steps, f"Loading post-setup adapters: {adapters_to_load}")

    # Create startup context for adapters
    context = AdapterStartupContext(
        essential_config=runtime.essential_config or EssentialConfig(),
        modules_to_load=runtime.modules_to_load,
        startup_channel_id=runtime.startup_channel_id or "",
        debug=runtime.debug,
        bus_manager=runtime.bus_manager,
        time_service=runtime.time_service,
        service_registry=runtime.service_registry,
    )

    for adapter_type in adapters_to_load:
        try:
            adapter_class = load_adapter(adapter_type)

            # Get adapter-specific config from environment - MUST set persist=True
            adapter_config = AdapterConfig(adapter_type=adapter_type, persist=True)

            # Create and register adapter
            adapter_instance = adapter_class(runtime, context=context, adapter_config=adapter_config.settings)  # type: ignore[call-arg]
            runtime.adapters.append(adapter_instance)

            # Register adapter services with buses
            if hasattr(adapter_instance, "get_services_to_register"):
                services_to_register = adapter_instance.get_services_to_register()
                for service_reg in services_to_register:
                    if runtime.service_registry:
                        runtime.service_registry.register_service(
                            service_reg.service_type, service_reg.provider, service_reg.priority
                        )
                        logger.info(
                            f"[RESUME] Registered {adapter_type} service: "
                            f"{service_reg.service_type} (priority={service_reg.priority})"
                        )

            # Start the adapter
            if hasattr(adapter_instance, "start"):
                await adapter_instance.start()

            # Persist to graph so it loads on subsequent restarts
            await _persist_adapter_to_graph(runtime, adapter_type, adapter_config)

            logger.info(f"[RESUME] Successfully loaded and started post-setup adapter: {adapter_type}")

        except Exception as e:
            logger.error(f"[RESUME] Failed to load post-setup adapter '{adapter_type}': {e}", exc_info=True)


def _ensure_config(runtime: Any) -> "EssentialConfig":
    """Ensure essential_config is available, raise if not."""
    if not runtime.essential_config:
        raise RuntimeError("Essential config not initialized")
    config: "EssentialConfig" = runtime.essential_config
    return config
