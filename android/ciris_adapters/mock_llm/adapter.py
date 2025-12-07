"""
Mock LLM Adapter for CIRIS.

Provides the BaseAdapterProtocol-compliant wrapper around MockLLMService
so it can be loaded dynamically via RuntimeAdapterManager.load_adapter().
"""

import asyncio
import logging
from typing import Any, List, Optional

from ciris_engine.logic.adapters.base import Service
from ciris_engine.logic.registries.base import Priority
from ciris_engine.schemas.adapters import AdapterServiceRegistration
from ciris_engine.schemas.runtime.adapter_management import AdapterConfig, RuntimeAdapterStatus
from ciris_engine.schemas.runtime.enums import ServiceType

from .service import MockLLMService

logger = logging.getLogger(__name__)


class MockLLMAdapter(Service):
    """
    Mock LLM adapter platform for CIRIS.

    Wraps MockLLMService to provide the BaseAdapterProtocol interface
    required for dynamic adapter loading via RuntimeAdapterManager.

    This is a testing/development adapter that simulates LLM responses
    without requiring external API calls.
    """

    def __init__(self, runtime: Any, context: Optional[Any] = None, **kwargs: Any) -> None:
        """Initialize Mock LLM adapter."""
        super().__init__(config=kwargs.get("adapter_config"))
        self.runtime = runtime
        self.context = context

        # Create the underlying mock LLM service
        # It reads config from environment variables set by MockLLMConfigurableAdapter.apply_config()
        self.llm_service = MockLLMService()

        # Track adapter state
        self._running = False
        self._lifecycle_task: Optional[asyncio.Task[None]] = None

        logger.info("Mock LLM adapter initialized")

    def get_services_to_register(self) -> List[AdapterServiceRegistration]:
        """Get services provided by this adapter."""
        registrations = []

        # Register the Mock LLM service as an LLM service with its capabilities
        registrations.append(
            AdapterServiceRegistration(
                service_type=ServiceType.LLM,
                provider=self.llm_service,
                priority=Priority.CRITICAL,
                capabilities=[
                    "call_llm_structured",
                    "provider:mock",
                ],
            )
        )

        return registrations

    async def start(self) -> None:
        """Start the Mock LLM adapter."""
        logger.info("Starting Mock LLM adapter")
        await self.llm_service.start()
        self._running = True
        logger.info("Mock LLM adapter started")

    async def stop(self) -> None:
        """Stop the Mock LLM adapter."""
        logger.info("Stopping Mock LLM adapter")
        self._running = False

        if self._lifecycle_task and not self._lifecycle_task.done():
            self._lifecycle_task.cancel()
            try:
                await self._lifecycle_task
            except asyncio.CancelledError:
                pass

        # Stop the LLM service
        await self.llm_service.stop()

        logger.info("Mock LLM adapter stopped")

    async def run_lifecycle(self, agent_task: Any) -> None:
        """Run the adapter lifecycle.

        For Mock LLM, we just wait for the agent task to complete
        since the mock service doesn't need continuous polling.
        """
        logger.info("Mock LLM adapter lifecycle started")
        try:
            # Wait for the agent task to signal shutdown
            await agent_task
        except asyncio.CancelledError:
            logger.info("Mock LLM adapter lifecycle cancelled")
        finally:
            await self.stop()

    def get_config(self) -> AdapterConfig:
        """Get adapter configuration."""
        return AdapterConfig(
            adapter_type="mock_llm",
            enabled=self._running,
            settings={
                "model": "mock-model",
                "provider": "mock",
            },
        )

    def get_status(self) -> RuntimeAdapterStatus:
        """Get adapter status."""
        return RuntimeAdapterStatus(
            adapter_id="mock_llm",
            adapter_type="mock_llm",
            is_running=self._running,
            loaded_at=None,
            error=None,
        )


# Export as Adapter for load_adapter() compatibility
Adapter = MockLLMAdapter
