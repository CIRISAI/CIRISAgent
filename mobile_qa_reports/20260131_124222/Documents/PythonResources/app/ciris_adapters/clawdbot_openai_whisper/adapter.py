"""
OpenaiWhisper Adapter for CIRIS.

Converted from Clawdbot skill: openai-whisper
Local speech-to-text with the Whisper CLI (no API key).
"""

import asyncio
import logging
from typing import Any, List, Optional

from ciris_engine.logic.adapters.base import Service
from ciris_engine.logic.registries.base import Priority
from ciris_engine.schemas.adapters import AdapterServiceRegistration
from ciris_engine.schemas.runtime.adapter_management import AdapterConfig, RuntimeAdapterStatus
from ciris_engine.schemas.runtime.enums import ServiceType

from .service import OpenaiWhisperToolService

logger = logging.getLogger(__name__)


class OpenaiWhisperAdapter(Service):
    """
    OpenaiWhisper adapter for CIRIS.

    Provides tool guidance for: Local speech-to-text with the Whisper CLI (no API key).

    Original Clawdbot skill: openai-whisper
    """

    def __init__(self, runtime: Any, context: Optional[Any] = None, **kwargs: Any) -> None:
        """Initialize OpenaiWhisper adapter."""
        super().__init__(config=kwargs.get("adapter_config"))
        self.runtime = runtime
        self.context = context

        adapter_config = kwargs.get("adapter_config", {})
        self.tool_service = OpenaiWhisperToolService(config=adapter_config)

        self._running = False
        self._lifecycle_task: Optional[asyncio.Task[None]] = None

        logger.info("OpenaiWhisper adapter initialized")

    def get_services_to_register(self) -> List[AdapterServiceRegistration]:
        """Get services provided by this adapter."""
        return [
            AdapterServiceRegistration(
                service_type=ServiceType.TOOL,
                provider=self.tool_service,
                priority=Priority.NORMAL,
                capabilities=[
                    "tool:openai_whisper",
                    "domain:openai_whisper",
                ],
            )
        ]

    async def start(self) -> None:
        """Start the adapter."""
        logger.info("Starting OpenaiWhisper adapter")
        await self.tool_service.start()
        self._running = True
        logger.info("OpenaiWhisper adapter started")

    async def stop(self) -> None:
        """Stop the adapter."""
        logger.info("Stopping OpenaiWhisper adapter")
        self._running = False

        if self._lifecycle_task and not self._lifecycle_task.done():
            self._lifecycle_task.cancel()
            try:
                await self._lifecycle_task
            except asyncio.CancelledError:
                pass

        await self.tool_service.stop()
        logger.info("OpenaiWhisper adapter stopped")

    async def run_lifecycle(self, agent_task: Any) -> None:
        """Run the adapter lifecycle."""
        logger.info("OpenaiWhisper adapter lifecycle started")
        try:
            await agent_task
        except asyncio.CancelledError:
            logger.info("OpenaiWhisper adapter lifecycle cancelled")
        finally:
            await self.stop()

    def get_config(self) -> AdapterConfig:
        """Get adapter configuration."""
        return AdapterConfig(
            adapter_type="clawdbot_openai_whisper",
            enabled=self._running,
            settings={},
        )

    def get_status(self) -> RuntimeAdapterStatus:
        """Get adapter status."""
        return RuntimeAdapterStatus(
            adapter_id="clawdbot_openai_whisper",
            adapter_type="clawdbot_openai_whisper",
            is_running=self._running,
            loaded_at=None,
            error=None,
        )


# Export as Adapter for load_adapter() compatibility
Adapter = OpenaiWhisperAdapter
