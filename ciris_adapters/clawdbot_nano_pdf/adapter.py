"""
NanoPdf Adapter for CIRIS.

Converted from Clawdbot skill: nano-pdf
Edit PDFs with natural-language instructions using the nano-pdf CLI.
"""

import asyncio
import logging
from typing import Any, List, Optional

from ciris_engine.logic.adapters.base import Service
from ciris_engine.logic.registries.base import Priority
from ciris_engine.schemas.adapters import AdapterServiceRegistration
from ciris_engine.schemas.runtime.adapter_management import AdapterConfig, RuntimeAdapterStatus
from ciris_engine.schemas.runtime.enums import ServiceType

from .service import NanoPdfToolService

logger = logging.getLogger(__name__)


class NanoPdfAdapter(Service):
    """
    NanoPdf adapter for CIRIS.

    Provides tool guidance for: Edit PDFs with natural-language instructions using the nano-pdf CLI.

    Original Clawdbot skill: nano-pdf
    """

    def __init__(self, runtime: Any, context: Optional[Any] = None, **kwargs: Any) -> None:
        """Initialize NanoPdf adapter."""
        super().__init__(config=kwargs.get("adapter_config"))
        self.runtime = runtime
        self.context = context

        adapter_config = kwargs.get("adapter_config", {})
        self.tool_service = NanoPdfToolService(config=adapter_config)

        self._running = False
        self._lifecycle_task: Optional[asyncio.Task[None]] = None

        logger.info("NanoPdf adapter initialized")

    def get_services_to_register(self) -> List[AdapterServiceRegistration]:
        """Get services provided by this adapter."""
        return [
            AdapterServiceRegistration(
                service_type=ServiceType.TOOL,
                provider=self.tool_service,
                priority=Priority.NORMAL,
                capabilities=[
                    "tool:nano_pdf",
                    "domain:nano_pdf",
                ],
            )
        ]

    async def start(self) -> None:
        """Start the adapter."""
        logger.info("Starting NanoPdf adapter")
        await self.tool_service.start()
        self._running = True
        logger.info("NanoPdf adapter started")

    async def stop(self) -> None:
        """Stop the adapter."""
        logger.info("Stopping NanoPdf adapter")
        self._running = False

        if self._lifecycle_task and not self._lifecycle_task.done():
            self._lifecycle_task.cancel()
            try:
                await self._lifecycle_task
            except asyncio.CancelledError:
                pass

        await self.tool_service.stop()
        logger.info("NanoPdf adapter stopped")

    async def run_lifecycle(self, agent_task: Any) -> None:
        """Run the adapter lifecycle."""
        logger.info("NanoPdf adapter lifecycle started")
        try:
            await agent_task
        except asyncio.CancelledError:
            logger.info("NanoPdf adapter lifecycle cancelled")
        finally:
            await self.stop()

    def get_config(self) -> AdapterConfig:
        """Get adapter configuration."""
        return AdapterConfig(
            adapter_type="clawdbot_nano_pdf",
            enabled=self._running,
            settings={},
        )

    def get_status(self) -> RuntimeAdapterStatus:
        """Get adapter status."""
        return RuntimeAdapterStatus(
            adapter_id="clawdbot_nano_pdf",
            adapter_type="clawdbot_nano_pdf",
            is_running=self._running,
            loaded_at=None,
            error=None,
        )


# Export as Adapter for load_adapter() compatibility
Adapter = NanoPdfAdapter
