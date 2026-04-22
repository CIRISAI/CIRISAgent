"""
Error message emitter for system/error messages to UI/UX.

This module provides a centralized way to emit error messages that can be
displayed in the UI. Messages are sent through the communication service
and appear in the /v1/agent/history endpoint.
"""

import asyncio
import logging
from typing import Awaitable, Callable, Optional

logger = logging.getLogger(__name__)

# Global callback for emitting error messages
# Set by the runtime/adapter during initialization
_error_callback: Optional[Callable[[str, str, str], Awaitable[None]]] = None

# Rate limiting to avoid flooding
_last_emit_times: dict[str, float] = {}
_MIN_EMIT_INTERVAL = 5.0  # Minimum seconds between same-category messages


def set_error_callback(callback: Callable[[str, str, str], Awaitable[None]]) -> None:
    """
    Set the global error callback.

    Args:
        callback: Async function(channel_id, content, message_type) -> None
    """
    global _error_callback
    _error_callback = callback
    logger.info("Error emitter callback registered")


def clear_error_callback() -> None:
    """Clear the error callback (for testing/cleanup)."""
    global _error_callback
    _error_callback = None


async def emit_error(
    content: str,
    channel_id: str = "system",
    category: str = "general",
    message_type: str = "error",
) -> bool:
    """
    Emit an error message to the UI.

    Args:
        content: Error message content (kept concise, <200 chars recommended)
        channel_id: Target channel (defaults to "system")
        category: Category for rate limiting (e.g., "rate_limit", "dma_failure")
        message_type: "error" or "system"

    Returns:
        True if message was emitted, False if rate-limited or no callback
    """
    global _error_callback, _last_emit_times

    if not _error_callback:
        logger.debug(f"Error emitter not configured, skipping: {content[:100]}")
        return False

    # Rate limiting by category
    import time

    now = time.time()
    last_time = _last_emit_times.get(category, 0)
    if now - last_time < _MIN_EMIT_INTERVAL:
        logger.debug(f"Rate limiting error emission for category '{category}'")
        return False

    _last_emit_times[category] = now

    try:
        await _error_callback(channel_id, content, message_type)
        logger.debug(f"Emitted {message_type} message to {channel_id}: {content[:50]}...")
        return True
    except Exception as e:
        logger.warning(f"Failed to emit error message: {e}")
        return False


async def emit_rate_limit_error(
    provider: str,
    wait_time: float,
    channel_id: str = "system",
) -> bool:
    """Emit a rate limit error message."""
    content = f"Rate limited by {provider}. Retrying in {wait_time:.1f}s..."
    return await emit_error(
        content=content,
        channel_id=channel_id,
        category="rate_limit",
        message_type="error",
    )


async def emit_llm_failure(
    error_summary: str,
    retry_count: int,
    max_retries: int,
    channel_id: str = "system",
) -> bool:
    """Emit an LLM failure error message."""
    content = f"LLM error ({retry_count}/{max_retries}): {error_summary[:100]}"
    return await emit_error(
        content=content,
        channel_id=channel_id,
        category="llm_failure",
        message_type="error",
    )


async def emit_circuit_breaker_open(
    service_name: str,
    channel_id: str = "system",
) -> bool:
    """Emit a circuit breaker open error message."""
    content = f"LLM service '{service_name}' temporarily unavailable. Will retry shortly."
    return await emit_error(
        content=content,
        channel_id=channel_id,
        category="circuit_breaker",
        message_type="error",
    )


async def emit_dma_failure(
    dma_name: str,
    error_summary: str,
    channel_id: str = "system",
) -> bool:
    """Emit a DMA failure error message."""
    content = f"Processing error in {dma_name}: {error_summary[:80]}"
    return await emit_error(
        content=content,
        channel_id=channel_id,
        category=f"dma_{dma_name}",
        message_type="error",
    )
