"""
Centralized channel resolution logic.

This module provides a single, authoritative implementation of channel ID
resolution to prevent duplication and divergence between different parts
of the codebase.
"""

import logging
from typing import Any, Optional, Tuple

from ciris_engine.logic.config.env_utils import get_env_var
from ciris_engine.logic.services.memory_service import LocalGraphMemoryService
from ciris_engine.schemas.runtime.models import Task
from ciris_engine.schemas.runtime.system_context import ChannelContext

from .system_snapshot_helpers import _resolve_channel_context

logger = logging.getLogger(__name__)


def _try_task_channel_id(task: Optional[Task]) -> Optional[str]:
    """Try to get channel_id directly from task."""
    if task and hasattr(task, "channel_id") and task.channel_id:
        return str(task.channel_id)
    return None


def _try_app_config_home_channel(app_config: Optional[Any]) -> Optional[str]:
    """Try to get channel_id from app_config home_channel."""
    if app_config and hasattr(app_config, "home_channel"):
        home_channel = getattr(app_config, "home_channel", None)
        if home_channel:
            return str(home_channel)
    return None


def _try_mode_specific_config(app_config: Optional[Any]) -> Optional[str]:
    """Try mode-specific config attributes (discord_channel_id, cli_channel_id, api_channel_id)."""
    if not app_config:
        return None

    config_attrs = ["discord_channel_id", "cli_channel_id", "api_channel_id"]
    for attr in config_attrs:
        if hasattr(app_config, attr):
            config_channel_id = getattr(app_config, attr, None)
            if config_channel_id:
                logger.debug(f"Resolved channel_id '{config_channel_id}' from app_config.{attr}")
                return str(config_channel_id)
    return None


def _try_mode_based_fallback(app_config: Optional[Any]) -> Optional[str]:
    """Try mode-based fallbacks (CLI, API, DISCORD_DEFAULT)."""
    if not app_config:
        return None

    mode = getattr(app_config, "agent_mode", "")
    mode_lower = mode.lower() if mode else ""

    if mode_lower == "cli":
        logger.debug("Using CLI mode fallback channel_id")
        return "CLI"
    elif mode_lower == "api":
        logger.debug("Using API mode fallback channel_id")
        return "API"
    elif mode == "discord":
        logger.debug("Using Discord mode fallback channel_id")
        return "DISCORD_DEFAULT"

    return None


async def resolve_channel_id_and_context(
    task: Optional[Task],
    thought: Any,
    memory_service: Optional[LocalGraphMemoryService],
    app_config: Optional[Any] = None,
) -> Tuple[Optional[str], Optional[ChannelContext]]:
    """
    Resolve channel ID and context using a standardized resolution cascade.

    Resolution order:
    1. Task/thought context (from memory)
    2. Task direct channel_id field
    3. App config (home_channel, mode-specific channels)
    4. Environment variable (DISCORD_CHANNEL_ID)
    5. Mode-based fallbacks (CLI, API, DISCORD_DEFAULT)
    6. Emergency fallback ("UNKNOWN")

    Args:
        task: Optional task containing channel context
        thought: Thought object that may have channel context
        memory_service: Memory service for graph lookups
        app_config: Application configuration for fallback lookups

    Returns:
        Tuple of (channel_id, channel_context) where either may be None
    """
    # 1. Try memory-based resolution (most reliable)
    channel_id, channel_context = await _resolve_channel_context(task, thought, memory_service)
    if channel_id:
        logger.debug(f"Resolved channel_id '{channel_id}' from memory")
        return channel_id, channel_context

    # 2. Try task's direct channel_id field
    channel_id = _try_task_channel_id(task)
    if channel_id:
        logger.debug(f"Resolved channel_id '{channel_id}' from task.channel_id")
        return channel_id, None

    # 3. Try app config home channel
    channel_id = _try_app_config_home_channel(app_config)
    if channel_id:
        logger.debug(f"Resolved channel_id '{channel_id}' from app_config.home_channel")
        return channel_id, None

    # 4. Try environment variable
    channel_id = get_env_var("DISCORD_CHANNEL_ID")
    if channel_id:
        logger.debug(f"Resolved channel_id '{channel_id}' from DISCORD_CHANNEL_ID env var")
        return channel_id, None

    # 5. Try mode-specific config attributes
    channel_id = _try_mode_specific_config(app_config)
    if channel_id:
        return channel_id, None

    # 6. Mode-based fallbacks
    channel_id = _try_mode_based_fallback(app_config)
    if channel_id:
        return channel_id, None

    # 7. Emergency fallback
    logger.warning("CRITICAL: Channel ID could not be resolved from any source")
    return "UNKNOWN", None
