"""
CodingAgent Adapter for CIRIS.

Converted from Clawdbot skill: coding-agent
Run Codex CLI, Claude Code, OpenCode, or Pi Coding Agent via background process for programmatic control.
"""

import asyncio
import logging
from typing import Any, List, Optional

from ciris_engine.logic.adapters.base import Service
from ciris_engine.logic.registries.base import Priority
from ciris_engine.schemas.adapters import AdapterServiceRegistration
from ciris_engine.schemas.runtime.adapter_management import AdapterConfig, RuntimeAdapterStatus
from ciris_engine.schemas.runtime.enums import ServiceType

from .service import CodingAgentToolService

logger = logging.getLogger(__name__)


class CodingAgentAdapter(Service):
    """
    CodingAgent adapter for CIRIS.

    Provides tool guidance for: Run Codex CLI, Claude Code, OpenCode, or Pi Coding Agent via background process for programmatic control.

    Original Clawdbot skill: coding-agent
    """

    def __init__(self, runtime: Any, context: Optional[Any] = None, **kwargs: Any) -> None:
        """Initialize CodingAgent adapter."""
        super().__init__(config=kwargs.get("adapter_config"))
        self.runtime = runtime
        self.context = context

        adapter_config = kwargs.get("adapter_config", {})
        self.tool_service = CodingAgentToolService(config=adapter_config)

        self._running = False
        self._lifecycle_task: Optional[asyncio.Task[None]] = None

        logger.info("CodingAgent adapter initialized")

    def get_services_to_register(self) -> List[AdapterServiceRegistration]:
        """Get services provided by this adapter."""
        return [
            AdapterServiceRegistration(
                service_type=ServiceType.TOOL,
                provider=self.tool_service,
                priority=Priority.NORMAL,
                capabilities=[
                    "tool:coding_agent",
                    "domain:coding_agent",
                ],
            )
        ]

    async def start(self) -> None:
        """Start the adapter."""
        logger.info("Starting CodingAgent adapter")
        await self.tool_service.start()
        self._running = True
        logger.info("CodingAgent adapter started")

    async def stop(self) -> None:
        """Stop the adapter."""
        logger.info("Stopping CodingAgent adapter")
        self._running = False

        if self._lifecycle_task and not self._lifecycle_task.done():
            self._lifecycle_task.cancel()
            try:
                await self._lifecycle_task
            except asyncio.CancelledError:
                pass

        await self.tool_service.stop()
        logger.info("CodingAgent adapter stopped")

    async def run_lifecycle(self, agent_task: Any) -> None:
        """Run the adapter lifecycle."""
        logger.info("CodingAgent adapter lifecycle started")
        try:
            await agent_task
        except asyncio.CancelledError:
            logger.info("CodingAgent adapter lifecycle cancelled")
        finally:
            await self.stop()

    def get_config(self) -> AdapterConfig:
        """Get adapter configuration."""
        return AdapterConfig(
            adapter_type="clawdbot_coding_agent",
            enabled=self._running,
            settings={},
        )

    def get_status(self) -> RuntimeAdapterStatus:
        """Get adapter status."""
        return RuntimeAdapterStatus(
            adapter_id="clawdbot_coding_agent",
            adapter_type="clawdbot_coding_agent",
            is_running=self._running,
            loaded_at=None,
            error=None,
        )


# Export as Adapter for load_adapter() compatibility
Adapter = CodingAgentAdapter
