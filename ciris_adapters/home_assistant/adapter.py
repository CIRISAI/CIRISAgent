"""
Home Assistant Adapter for CIRIS.

Provides the BaseAdapterProtocol-compliant wrapper that properly separates:
- HAToolService: Device control, automation, sensor queries, notifications (TOOL)
- HACommunicationService: Event streams, TTS, bidirectional messaging (COMMUNICATION)

This is the correct pattern - tools and communication are registered separately.
"""

import asyncio
import logging
from typing import Any, List, Optional

from ciris_engine.logic.adapters.base import Service
from ciris_engine.logic.registries.base import Priority
from ciris_engine.schemas.adapters import AdapterServiceRegistration
from ciris_engine.schemas.runtime.adapter_management import AdapterConfig, RuntimeAdapterStatus
from ciris_engine.schemas.runtime.enums import ServiceType

from .communication_service import HACommunicationService
from .service import HAIntegrationService
from .tool_service import HAToolService

logger = logging.getLogger(__name__)


class HomeAssistantAdapter(Service):
    """
    Home Assistant adapter platform for CIRIS.

    Properly separates concerns:
    - HAToolService (ServiceType.TOOL): execute_tool for device control, automations, sensors
    - HACommunicationService (ServiceType.COMMUNICATION): send_message/fetch_messages for events

    This follows the same pattern as Discord adapter which separates
    DiscordAdapter (communication) from DiscordToolService (tools).
    """

    def __init__(self, runtime: Any, context: Optional[Any] = None, **kwargs: Any) -> None:
        """Initialize Home Assistant adapter."""
        super().__init__(config=kwargs.get("adapter_config"))
        self.runtime = runtime
        self.context = context

        # Create the underlying HA integration service (shared by tool and comms)
        self.ha_service = HAIntegrationService()

        # Create properly separated services
        self.tool_service = HAToolService(self.ha_service)
        self.communication_service = HACommunicationService(self.ha_service)

        # Track adapter state
        self._running = False
        self._lifecycle_task: Optional[asyncio.Task[None]] = None

        logger.info(f"Home Assistant adapter initialized for {self.ha_service.ha_url}")

    def get_services_to_register(self) -> List[AdapterServiceRegistration]:
        """Get services provided by this adapter.

        Returns SEPARATE registrations for TOOL and COMMUNICATION services.
        This is the correct pattern per CIRIS architecture.
        """
        registrations = []

        # Register TOOL service for device control, automations, sensor queries
        registrations.append(
            AdapterServiceRegistration(
                service_type=ServiceType.TOOL,
                provider=self.tool_service,
                priority=Priority.NORMAL,
                capabilities=[
                    "execute_tool",
                    "get_available_tools",
                    "ha_device_control",
                    "ha_automation_trigger",
                    "ha_sensor_query",
                    "ha_notification",
                    "ha_camera_analyze",
                    "provider:home_assistant",
                ],
            )
        )

        # Register COMMUNICATION service for event streams and messaging
        registrations.append(
            AdapterServiceRegistration(
                service_type=ServiceType.COMMUNICATION,
                provider=self.communication_service,
                priority=Priority.NORMAL,
                capabilities=[
                    "send_message",
                    "fetch_messages",
                    "ha_event_stream",
                    "ha_camera_events",
                    "ha_tts",
                    "provider:home_assistant",
                ],
            )
        )

        return registrations

    async def start(self) -> None:
        """Start the Home Assistant adapter."""
        logger.info("Starting Home Assistant adapter")

        # Initialize underlying HA service
        await self.ha_service.initialize()

        # Start tool service
        await self.tool_service.start()
        logger.info("HAToolService started")

        # Start communication service (sets up event channels)
        await self.communication_service.start()
        logger.info("HACommunicationService started")

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

        # Stop communication service
        await self.communication_service.stop()

        # Stop tool service
        await self.tool_service.stop()

        # Cleanup HA service
        if hasattr(self.ha_service, "cleanup"):
            await self.ha_service.cleanup()

        logger.info("Home Assistant adapter stopped")

    async def run_lifecycle(self, agent_task: Any) -> None:
        """Run the adapter lifecycle.

        For Home Assistant, we just wait for the agent task to complete
        since HA integration is event-driven and doesn't need continuous polling.
        """
        logger.info("Home Assistant adapter lifecycle started")
        try:
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

    async def get_active_channels(self) -> List[dict]:
        """Get active communication channels from HA communication service."""
        channels = []
        if self.communication_service and self._running:
            channel_ids = await self.communication_service.get_channels()
            for ch_id in channel_ids:
                channels.append(
                    {
                        "channel_id": ch_id,
                        "channel_type": "home_assistant",
                        "platform": "home_assistant",
                        "name": ch_id.replace("ha_", "HA ").replace("_", " ").title(),
                        "is_active": True,
                    }
                )
        return channels


# Export as Adapter for load_adapter() compatibility
Adapter = HomeAssistantAdapter
