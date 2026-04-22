"""
Weather Adapter for CIRIS.

Provides the BaseAdapterProtocol-compliant wrapper around WeatherToolService
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

from .service import WeatherToolService

logger = logging.getLogger(__name__)


class WeatherAdapter(Service):
    """
    Weather adapter platform for CIRIS.

    Wraps WeatherToolService to provide the BaseAdapterProtocol interface
    required for dynamic adapter loading via RuntimeAdapterManager.
    """

    def __init__(self, runtime: Any, context: Optional[Any] = None, **kwargs: Any) -> None:
        """Initialize Weather adapter."""
        super().__init__(config=kwargs.get("adapter_config"))
        self.runtime = runtime
        self.context = context

        # Create the underlying weather tool service
        # It reads config from environment variables set by WeatherConfigurableAdapter.apply_config()
        self.weather_service = WeatherToolService()

        # Track adapter state
        self._running = False
        self._lifecycle_task: Optional[asyncio.Task[None]] = None

        logger.info("Weather adapter initialized")

    def get_services_to_register(self) -> List[AdapterServiceRegistration]:
        """Get services provided by this adapter."""
        registrations = []

        # Register the weather service as a tool service with its capabilities
        registrations.append(
            AdapterServiceRegistration(
                service_type=ServiceType.TOOL,
                provider=self.weather_service,
                priority=Priority.NORMAL,
                capabilities=[
                    "weather:current",
                    "weather:forecast",
                    "weather:alerts",
                    "domain:weather",
                ],
            )
        )

        return registrations

    async def start(self) -> None:
        """Start the Weather adapter."""
        logger.info("Starting Weather adapter")
        await self.weather_service.start()
        self._running = True
        logger.info("Weather adapter started")

    async def stop(self) -> None:
        """Stop the Weather adapter."""
        logger.info("Stopping Weather adapter")
        self._running = False

        if self._lifecycle_task and not self._lifecycle_task.done():
            self._lifecycle_task.cancel()
            try:
                await self._lifecycle_task
            except asyncio.CancelledError:
                pass

        # Stop the weather service
        await self.weather_service.stop()

        logger.info("Weather adapter stopped")

    async def run_lifecycle(self, agent_task: Any) -> None:
        """Run the adapter lifecycle.

        For Weather, we just wait for the agent task to complete
        since weather tools are invoked on-demand and don't need continuous polling.
        """
        logger.info("Weather adapter lifecycle started")
        try:
            # Wait for the agent task to signal shutdown
            await agent_task
        except asyncio.CancelledError:
            logger.info("Weather adapter lifecycle cancelled")
        finally:
            await self.stop()

    def get_config(self) -> AdapterConfig:
        """Get adapter configuration."""
        return AdapterConfig(
            adapter_type="weather",
            enabled=self._running,
            settings={
                "noaa_user_agent": self.weather_service.user_agent,
                "has_owm_key": bool(self.weather_service.owm_api_key),
            },
        )

    def get_status(self) -> RuntimeAdapterStatus:
        """Get adapter status."""
        return RuntimeAdapterStatus(
            adapter_id="weather",
            adapter_type="weather",
            is_running=self._running,
            loaded_at=None,
            error=None,
        )


# Export as Adapter for load_adapter() compatibility
Adapter = WeatherAdapter
