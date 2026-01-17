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


async def initialize_llm_for_resume(
    runtime: Any, log_step: Callable[[int, int, str], None], total_steps: int
) -> None:
    """Initialize LLM service during resume."""
    log_step(10, total_steps, f"Initializing LLM service... service_initializer={runtime.service_initializer is not None}")
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


def _ensure_config(runtime: Any) -> "EssentialConfig":
    """Ensure essential_config is available, raise if not."""
    if not runtime.essential_config:
        raise RuntimeError("Essential config not initialized")
    return runtime.essential_config
