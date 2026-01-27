"""
NanoBananaPro Adapter for CIRIS.

Converted from Clawdbot skill: nano-banana-pro
Generate or edit images via Gemini 3 Pro Image (Nano Banana Pro).
"""

import asyncio
import logging
from typing import Any, List, Optional

from ciris_engine.logic.adapters.base import Service
from ciris_engine.logic.registries.base import Priority
from ciris_engine.schemas.adapters import AdapterServiceRegistration
from ciris_engine.schemas.runtime.adapter_management import AdapterConfig, RuntimeAdapterStatus
from ciris_engine.schemas.runtime.enums import ServiceType

from .service import NanoBananaProToolService

logger = logging.getLogger(__name__)


class NanoBananaProAdapter(Service):
    """
    NanoBananaPro adapter for CIRIS.

    Provides tool guidance for: Generate or edit images via Gemini 3 Pro Image (Nano Banana Pro).

    Original Clawdbot skill: nano-banana-pro
    """

    def __init__(self, runtime: Any, context: Optional[Any] = None, **kwargs: Any) -> None:
        """Initialize NanoBananaPro adapter."""
        super().__init__(config=kwargs.get("adapter_config"))
        self.runtime = runtime
        self.context = context

        adapter_config = kwargs.get("adapter_config", {})
        self.tool_service = NanoBananaProToolService(config=adapter_config)

        self._running = False
        self._lifecycle_task: Optional[asyncio.Task[None]] = None

        logger.info("NanoBananaPro adapter initialized")

    def get_services_to_register(self) -> List[AdapterServiceRegistration]:
        """Get services provided by this adapter."""
        return [
            AdapterServiceRegistration(
                service_type=ServiceType.TOOL,
                provider=self.tool_service,
                priority=Priority.NORMAL,
                capabilities=[
                    "tool:nano_banana_pro",
                    "domain:nano_banana_pro",
                ],
            )
        ]

    async def start(self) -> None:
        """Start the adapter."""
        logger.info("Starting NanoBananaPro adapter")
        await self.tool_service.start()
        self._running = True
        logger.info("NanoBananaPro adapter started")

    async def stop(self) -> None:
        """Stop the adapter."""
        logger.info("Stopping NanoBananaPro adapter")
        self._running = False

        if self._lifecycle_task and not self._lifecycle_task.done():
            self._lifecycle_task.cancel()
            try:
                await self._lifecycle_task
            except asyncio.CancelledError:
                pass

        await self.tool_service.stop()
        logger.info("NanoBananaPro adapter stopped")

    async def run_lifecycle(self, agent_task: Any) -> None:
        """Run the adapter lifecycle."""
        logger.info("NanoBananaPro adapter lifecycle started")
        try:
            await agent_task
        except asyncio.CancelledError:
            logger.info("NanoBananaPro adapter lifecycle cancelled")
        finally:
            await self.stop()

    def get_config(self) -> AdapterConfig:
        """Get adapter configuration."""
        return AdapterConfig(
            adapter_type="clawdbot_nano_banana_pro",
            enabled=self._running,
            settings={},
        )

    def get_status(self) -> RuntimeAdapterStatus:
        """Get adapter status."""
        return RuntimeAdapterStatus(
            adapter_id="clawdbot_nano_banana_pro",
            adapter_type="clawdbot_nano_banana_pro",
            is_running=self._running,
            loaded_at=None,
            error=None,
        )


# Export as Adapter for load_adapter() compatibility
Adapter = NanoBananaProAdapter
