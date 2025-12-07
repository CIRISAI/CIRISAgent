"""
Home Assistant Adapter for CIRIS.

Provides the BaseAdapterProtocol-compliant wrapper around HAIntegrationService
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

from .service import HAIntegrationService

logger = logging.getLogger(__name__)


class HomeAssistantAdapter(Service):
    """
    Home Assistant adapter platform for CIRIS.

    Wraps HAIntegrationService to provide the BaseAdapterProtocol interface
    required for dynamic adapter loading via RuntimeAdapterManager.
    """

    def __init__(self, runtime: Any, context: Optional[Any] = None, **kwargs: Any) -> None:
        """Initialize Home Assistant adapter."""
        super().__init__(config=kwargs.get("adapter_config"))
        self.runtime = runtime
        self.context = context

        # Create the underlying HA integration service
        # It reads config from environment variables set by HAConfigurableAdapter.apply_config()
        self.ha_service = HAIntegrationService()

        # Track adapter state
        self._running = False
        self._lifecycle_task: Optional[asyncio.Task[None]] = None

        logger.info(f"Home Assistant adapter initialized for {self.ha_service.ha_url}")

    def get_services_to_register(self) -> List[AdapterServiceRegistration]:
        """Get services provided by this adapter."""
        registrations = []

        # Register the HA service as a communication service with its capabilities
        registrations.append(
            AdapterServiceRegistration(
                service_type=ServiceType.COMMUNICATION,
                provider=self.ha_service,
                priority=Priority.NORMAL,
                capabilities=[
                    "ha_chat_bridge",
                    "ha_device_control",
                    "ha_automation_trigger",
                    "ha_sensor_data",
                    "ha_event_detection",
                    "ha_camera_frames",
                    "provider:home_assistant",
                ],
            )
        )

        return registrations

    async def start(self) -> None:
        """Start the Home Assistant adapter."""
        logger.info("Starting Home Assistant adapter")
        await self.ha_service.initialize()
        self._running = True
        logger.info("Home Assistant adapter started")

    async def stop(self) -> None:
        """Stop the Home Assistant adapter."""
        logger.info("Stopping Home Assistant adapter")
        self._running = False

        if self._lifecycle_task and not self._lifecycle_task.done():
            self._lifecycle_task.cancel()
            try:
                await self._lifecycle_task
            except asyncio.CancelledError:
                pass

        # Stop the HA service if it has a stop method
        if hasattr(self.ha_service, "stop"):
            await self.ha_service.stop()
        elif hasattr(self.ha_service, "shutdown"):
            await self.ha_service.shutdown()

        logger.info("Home Assistant adapter stopped")

    async def run_lifecycle(self, agent_task: Any) -> None:
        """Run the adapter lifecycle.

        For Home Assistant, we just wait for the agent task to complete
        since HA integration is event-driven and doesn't need continuous polling.
        """
        logger.info("Home Assistant adapter lifecycle started")
        try:
            # Wait for the agent task to signal shutdown
            await agent_task
        except asyncio.CancelledError:
            logger.info("Home Assistant adapter lifecycle cancelled")
        finally:
            await self.stop()

    def get_config(self) -> AdapterConfig:
        """Get adapter configuration."""
        return AdapterConfig(
            adapter_type="home_assistant",
            enabled=self._running,
            settings={
                "ha_url": self.ha_service.ha_url,
                "has_token": bool(self.ha_service.ha_token),
            },
        )

    def get_status(self) -> RuntimeAdapterStatus:
        """Get adapter status."""
        return RuntimeAdapterStatus(
            adapter_id="home_assistant",
            adapter_type="home_assistant",
            is_running=self._running,
            loaded_at=None,
            error=None,
        )


# Export as Adapter for load_adapter() compatibility
Adapter = HomeAssistantAdapter
