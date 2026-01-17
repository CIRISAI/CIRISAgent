"""
Configuration migration utilities for CIRISRuntime.

Handles migration of configuration from bootstrap files to the graph config service,
including adapter configs, tickets config, and cognitive state behaviors.
"""

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


def _get_adapter_id(adapter_type: str) -> str:
    """Determine adapter ID from type (handle instance-specific types like 'api:8081')."""
    if ":" in adapter_type:
        base_type, instance_id = adapter_type.split(":", 1)
        return f"{base_type}_{instance_id}"
    return f"{adapter_type}_bootstrap"


def _get_config_dict(adapter_config: Any) -> Any:
    """Extract config dict from adapter config object."""
    return adapter_config.model_dump() if hasattr(adapter_config, "model_dump") else adapter_config


async def _migrate_single_adapter_config(
    config_service: Any, adapter_type: str, adapter_config: Any
) -> None:
    """Migrate a single adapter configuration to graph."""
    adapter_id = _get_adapter_id(adapter_type)
    config_dict = _get_config_dict(adapter_config)

    # Store the full config object
    await config_service.set_config(
        key=f"adapter.{adapter_id}.config",
        value=config_dict,
        updated_by="system_bootstrap",
    )

    # Also store individual config values for easy access
    if isinstance(config_dict, dict):
        for key, value in config_dict.items():
            await config_service.set_config(
                key=f"adapter.{adapter_id}.{key}", value=value, updated_by="system_bootstrap"
            )

    logger.info(f"Migrated adapter config for {adapter_id} to graph")


async def migrate_adapter_configs_to_graph(runtime: Any) -> None:
    """Migrate adapter configurations to graph config service."""
    if not runtime.service_initializer or not runtime.service_initializer.config_service:
        logger.warning("Cannot migrate adapter configs - GraphConfigService not available")
        return

    config_service = runtime.service_initializer.config_service

    for adapter_type, adapter_config in runtime.adapter_configs.items():
        try:
            await _migrate_single_adapter_config(config_service, adapter_type, adapter_config)
        except Exception as e:
            logger.error(f"Failed to migrate adapter config for {adapter_type}: {e}")

    # Migrate tickets config from template (first-run only)
    await migrate_tickets_config_to_graph(runtime)

    # Migrate cognitive state behaviors (pre-1.7 compatibility)
    await migrate_cognitive_state_behaviors_to_graph(runtime)


async def migrate_tickets_config_to_graph(runtime: Any) -> None:
    """Migrate tickets config to graph.

    This handles two scenarios:
    1. First-run: Seeds tickets config from template to graph
    2. Pre-1.7.0 upgrade: Adds default DSAR SOPs for existing agents without tickets config

    After migration, tickets.py retrieves config from graph, not template.
    """
    if not runtime.service_initializer or not runtime.service_initializer.config_service:
        logger.warning("Cannot migrate tickets config - GraphConfigService not available")
        return

    config_service = runtime.service_initializer.config_service

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
    if runtime.identity_manager and runtime.identity_manager.agent_template:
        tickets_config = runtime.identity_manager.agent_template.tickets

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


def should_skip_cognitive_migration(force_from_template: bool) -> bool:
    """Check if cognitive migration should be skipped (first-run mode without force)."""
    from ciris_engine.logic.setup.first_run import is_first_run

    if is_first_run() and not force_from_template:
        logger.info("[COGNITIVE_MIGRATION] First-run mode: Skipping migration (will seed after setup wizard)")
        return True
    return False


async def check_existing_cognitive_config(config_service: Any) -> bool:
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


def get_cognitive_behaviors_from_template(runtime: Any) -> Optional[Any]:
    """Get cognitive behaviors from the agent template if available."""
    logger.info(f"[COGNITIVE_MIGRATION] identity_manager={runtime.identity_manager is not None}")
    if not runtime.identity_manager or not runtime.identity_manager.agent_template:
        logger.info("[COGNITIVE_MIGRATION] No template available (identity_manager or agent_template is None)")
        return None

    template = runtime.identity_manager.agent_template
    logger.info(f"[COGNITIVE_MIGRATION] Template loaded: name={getattr(template, 'name', 'UNKNOWN')}")
    cognitive_behaviors = getattr(template, "cognitive_state_behaviors", None)
    if cognitive_behaviors:
        logger.info(
            f"[COGNITIVE_MIGRATION] Template has cognitive_state_behaviors: wakeup.enabled={cognitive_behaviors.wakeup.enabled}"
        )
    else:
        logger.info("[COGNITIVE_MIGRATION] Template has NO cognitive_state_behaviors attribute")
    return cognitive_behaviors


def create_legacy_cognitive_behaviors() -> Any:
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


async def save_cognitive_behaviors_to_graph(config_service: Any, cognitive_behaviors: Any) -> None:
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


async def migrate_cognitive_state_behaviors_to_graph(runtime: Any, force_from_template: bool = False) -> None:
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
        runtime: The CIRISRuntime instance
        force_from_template: If True, always seed from template (used during resume_from_first_run
            when template is now available). This overwrites any pre-existing config.
    """
    if should_skip_cognitive_migration(force_from_template):
        return

    if not runtime.service_initializer or not runtime.service_initializer.config_service:
        logger.warning("[COGNITIVE_MIGRATION] Cannot migrate - GraphConfigService not available")
        return

    config_service = runtime.service_initializer.config_service

    logger.info("[COGNITIVE_MIGRATION] Starting cognitive state behaviors migration check...")
    logger.info(f"[COGNITIVE_MIGRATION] force_from_template={force_from_template}")

    if not force_from_template:
        if await check_existing_cognitive_config(config_service):
            return
    else:
        logger.info("[COGNITIVE_MIGRATION] Force mode: Will overwrite existing config with template values")

    # Try to get cognitive behaviors from template
    cognitive_behaviors = get_cognitive_behaviors_from_template(runtime)

    # If no template available, use Covenant-compliant defaults (all states enabled)
    # This applies to fresh installs without templates (e.g., QA testing, API-only mode)
    if not cognitive_behaviors:
        from ciris_engine.schemas.config.cognitive_state_behaviors import CognitiveStateBehaviors

        logger.info("[COGNITIVE_MIGRATION] No template - using Covenant-compliant defaults (all states enabled)")
        cognitive_behaviors = CognitiveStateBehaviors()

    try:
        await save_cognitive_behaviors_to_graph(config_service, cognitive_behaviors)
    except Exception as e:
        logger.error(f"[COGNITIVE_MIGRATION] FAILED to migrate cognitive state behaviors to graph: {e}")
