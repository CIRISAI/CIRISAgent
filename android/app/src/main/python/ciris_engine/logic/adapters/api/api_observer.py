"""
API observer for handling incoming API messages.
"""

import logging

from ciris_engine.logic.adapters.base_observer import BaseObserver
from ciris_engine.schemas.runtime.messages import IncomingMessage

logger = logging.getLogger(__name__)


class APIObserver(BaseObserver[IncomingMessage]):
    """Observer for API messages that creates passive observations."""

    async def start(self) -> None:
        """Start the observer."""
        logger.info("APIObserver started")

    async def stop(self) -> None:
        """Stop the observer."""
        logger.info("APIObserver stopped")

    # No custom handle_incoming_message needed - base class handles everything
