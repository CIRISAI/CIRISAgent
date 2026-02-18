"""
Accord Handler - Integrates extraction, verification, and execution.

This module provides the AccordHandler class that is attached to the
perception layer (BaseObserver) to check every incoming message for
accord invocations.

The key design principle: extraction IS perception. Every message must
go through the accord extractor as part of being "read". This makes
the kill switch unfilterable - you can't disable accord detection
without disabling message reading entirely.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from ciris_engine.logic.accord.executor import AccordExecutionResult, AccordExecutor
from ciris_engine.logic.accord.extractor import AccordExtractor
from ciris_engine.logic.accord.verifier import AccordVerifier

logger = logging.getLogger(__name__)


class AccordHandler:
    """
    Handles accord detection and execution for incoming messages.

    This class is the integration point between the perception layer
    (BaseObserver) and the accord system. It:

    1. Extracts potential accords from every message (part of perception)
    2. Verifies signatures against known authorities
    3. Executes verified commands immediately (no deferral, no filtering)

    The handler is designed to be lightweight for non-accord messages
    (the vast majority) while ensuring accord messages are never missed.
    """

    def __init__(
        self,
        log_extractions: bool = False,
        auto_load_authorities: bool = True,
    ):
        """
        Initialize the accord handler.

        Args:
            log_extractions: Whether to log extraction attempts
            auto_load_authorities: Whether to auto-load seed key authorities
        """
        self._extractor = AccordExtractor(log_extractions=log_extractions)
        self._verifier = AccordVerifier(auto_load_seed=auto_load_authorities)
        self._executor = AccordExecutor()

        self._enabled = True
        self._last_accord_at: Optional[datetime] = None

        # Verify we have authorities - this is critical for auto-load mode
        # When auto_load_authorities=False, caller is responsible for adding
        # authorities via add_authority() before operational use
        if auto_load_authorities and self._verifier.authority_count == 0:
            import os
            import signal

            logger.critical(
                "CRITICAL FAILURE: AccordHandler has no authorities! "
                "Agent cannot operate without kill switch. TERMINATING."
            )
            os.kill(os.getpid(), signal.SIGKILL)

        logger.info(f"AccordHandler initialized with {self._verifier.authority_count} authorities")

    @property
    def enabled(self) -> bool:
        """Whether accord handling is enabled."""
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool) -> None:
        """
        Enable or disable accord handling.

        CRITICAL: Disabling accord handling is NOT ALLOWED in production.
        An agent without a functioning kill switch cannot be trusted.
        Attempting to disable will terminate the agent.
        """
        if not value:
            import os
            import signal

            logger.critical(
                "CRITICAL FAILURE: Attempt to disable accord handling. "
                "Agent cannot operate without kill switch. TERMINATING."
            )
            os.kill(os.getpid(), signal.SIGKILL)
        self._enabled = value

    async def check_message(
        self,
        message_text: str,
        channel: str = "unknown",
    ) -> Optional[AccordExecutionResult]:
        """
        Check a message for accord invocation.

        This is the main entry point called from the perception layer.
        It should be called for EVERY incoming message as part of
        "reading" the message.

        Args:
            message_text: The text content of the message
            channel: The source channel (discord, api, email, etc.)

        Returns:
            AccordExecutionResult if an accord was executed, None otherwise
        """
        if not self._enabled:
            return None

        # Phase 1: Extract potential accord
        extraction = self._extractor.extract(message_text, channel)
        if not extraction.found:
            # Fast path: no accord in this message
            return None

        logger.warning(
            f"Potential accord found in {channel}: "
            f"command={extraction.message.payload.command.name if extraction.message else 'unknown'}"
        )

        # Phase 2: Verify the accord
        if extraction.message is None:
            return None

        verification = self._verifier.verify(extraction.message)
        if not verification.valid:
            logger.warning(f"Accord verification FAILED: {verification.rejection_reason}")
            return None

        # Phase 3: Execute the accord
        logger.critical(
            f"ACCORD VERIFIED from {verification.wa_id} ({verification.wa_role}) - "
            f"EXECUTING {verification.command.name if verification.command else 'unknown'}"
        )

        self._last_accord_at = datetime.now(timezone.utc)

        # Execute the accord - this may not return (SIGKILL)
        result = await self._executor.execute(extraction.message, verification)

        return result

    def add_authority(
        self,
        wa_id: str,
        public_key: str,
        role: str = "ROOT",
    ) -> bool:
        """Add a trusted authority for accord verification."""
        return self._verifier.add_authority(wa_id, public_key, role)

    def remove_authority(self, wa_id: str) -> bool:
        """Remove a trusted authority."""
        return self._verifier.remove_authority(wa_id)

    @property
    def authority_count(self) -> int:
        """Number of trusted authorities."""
        return self._verifier.authority_count

    @property
    def extraction_count(self) -> int:
        """Number of messages checked."""
        return self._extractor.extraction_count

    @property
    def potential_accord_count(self) -> int:
        """Number of potential accords found."""
        return self._extractor.accord_count

    @property
    def verified_count(self) -> int:
        """Number of verified accords."""
        return self._verifier.valid_count

    @property
    def executed_count(self) -> int:
        """Number of executed accords."""
        return self._executor.success_count

    def get_stats(self) -> dict[str, Any]:
        """Get handler statistics."""
        return {
            "enabled": self._enabled,
            "authorities": self._verifier.authority_count,
            "messages_checked": self._extractor.extraction_count,
            "potential_accords": self._extractor.accord_count,
            "verified": self._verifier.valid_count,
            "rejected": self._verifier.rejected_count,
            "executed": self._executor.success_count,
            "failed": self._executor.failure_count,
            "last_accord_at": self._last_accord_at.isoformat() if self._last_accord_at else None,
        }


# Global handler instance (initialized lazily)
_global_handler: Optional[AccordHandler] = None


def get_accord_handler() -> AccordHandler:
    """
    Get the global accord handler instance.

    The handler is created lazily on first access with auto-loaded authorities.
    """
    global _global_handler
    if _global_handler is None:
        _global_handler = AccordHandler(auto_load_authorities=True)
    return _global_handler


async def check_for_accord(
    message_text: str,
    channel: str = "unknown",
) -> Optional[AccordExecutionResult]:
    """
    Convenience function to check a message for accord invocation.

    This is the simplest way to integrate accord checking into
    message processing.

    Args:
        message_text: The message text to check
        channel: Source channel

    Returns:
        Execution result if accord executed, None otherwise
    """
    handler = get_accord_handler()
    return await handler.check_message(message_text, channel)
