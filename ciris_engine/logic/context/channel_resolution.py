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
    # First try memory-based resolution (most reliable)
    channel_id, channel_context = await _resolve_channel_context(task, thought, memory_service)

    # If we got both from memory, we're done
    if channel_id and channel_context:
        logger.debug(f"Resolved channel_id '{channel_id}' from memory with context")
        return channel_id, channel_context

    # If we have channel_id but no context, continue with it
    if channel_id:
        logger.debug(f"Resolved channel_id '{channel_id}' from memory without context")
        return channel_id, channel_context

    # Try task's direct channel_id field
    if task and hasattr(task, "channel_id") and task.channel_id:
        channel_id = str(task.channel_id)
        logger.debug(f"Resolved channel_id '{channel_id}' from task.channel_id")
        return channel_id, None

    # Try app config home channel
    if app_config and hasattr(app_config, "home_channel"):
        home_channel = getattr(app_config, "home_channel", None)
        if home_channel:
            channel_id = str(home_channel)
            logger.debug(f"Resolved channel_id '{channel_id}' from app_config.home_channel")
            return channel_id, None

    # Try environment variable
    env_channel_id = get_env_var("DISCORD_CHANNEL_ID")
    if env_channel_id:
        channel_id = env_channel_id
        logger.debug(f"Resolved channel_id '{channel_id}' from DISCORD_CHANNEL_ID env var")
        return channel_id, None

    # Try mode-specific config attributes
    if app_config:
        config_attrs = ["discord_channel_id", "cli_channel_id", "api_channel_id"]
        for attr in config_attrs:
            if hasattr(app_config, attr):
                config_channel_id = getattr(app_config, attr, None)
                if config_channel_id:
                    channel_id = str(config_channel_id)
                    logger.debug(f"Resolved channel_id '{channel_id}' from app_config.{attr}")
                    return channel_id, None

    # Mode-based fallbacks
    if app_config:
        mode = getattr(app_config, "agent_mode", "")
        mode_lower = mode.lower() if mode else ""
        if mode_lower == "cli":
            channel_id = "CLI"
            logger.debug("Using CLI mode fallback channel_id")
            return channel_id, None
        elif mode_lower == "api":
            channel_id = "API"
            logger.debug("Using API mode fallback channel_id")
            return channel_id, None
        elif mode == "discord":
            channel_id = "DISCORD_DEFAULT"
            logger.debug("Using Discord mode fallback channel_id")
            return channel_id, None

    # Emergency fallback
    logger.warning("CRITICAL: Channel ID could not be resolved from any source")
    return "UNKNOWN", None
