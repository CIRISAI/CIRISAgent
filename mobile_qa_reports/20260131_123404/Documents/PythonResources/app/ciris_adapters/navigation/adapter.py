"""
Navigation Adapter for CIRIS.

Provides the BaseAdapterProtocol-compliant wrapper around NavigationToolService
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

from .service import NavigationToolService

logger = logging.getLogger(__name__)


class NavigationAdapter(Service):
    """
    Navigation adapter platform for CIRIS.

    Wraps NavigationToolService to provide the BaseAdapterProtocol interface
    required for dynamic adapter loading via RuntimeAdapterManager.
    """

    def __init__(self, runtime: Any, context: Optional[Any] = None, **kwargs: Any) -> None:
        """Initialize Navigation adapter."""
        super().__init__(config=kwargs.get("adapter_config"))
        self.runtime = runtime
        self.context = context

        # Create the underlying navigation tool service
        # It reads config from environment variables set by NavigationConfigurableAdapter.apply_config()
        self.navigation_service = NavigationToolService()

        # Track adapter state
        self._running = False
        self._lifecycle_task: Optional[asyncio.Task[None]] = None

        logger.info("Navigation adapter initialized")

    def get_services_to_register(self) -> List[AdapterServiceRegistration]:
        """Get services provided by this adapter."""
        registrations = []

        # Register the navigation service as a tool service with its capabilities
        registrations.append(
            AdapterServiceRegistration(
                service_type=ServiceType.TOOL,
                provider=self.navigation_service,
                priority=Priority.NORMAL,
                capabilities=[
                    "navigation:geocode",
                    "navigation:reverse_geocode",
                    "navigation:route",
                    "domain:navigation",
                ],
            )
        )

        return registrations

    async def start(self) -> None:
        """Start the Navigation adapter."""
        logger.info("Starting Navigation adapter")
        await self.navigation_service.start()
        self._running = True
        logger.info("Navigation adapter started")

    async def stop(self) -> None:
        """Stop the Navigation adapter."""
        logger.info("Stopping Navigation adapter")
        self._running = False

        if self._lifecycle_task and not self._lifecycle_task.done():
            self._lifecycle_task.cancel()
            try:
                await self._lifecycle_task
            except asyncio.CancelledError:
                pass

        await self.navigation_service.stop()
        logger.info("Navigation adapter stopped")

    async def run_lifecycle(self, agent_task: Any) -> None:
        """Run the adapter lifecycle.

        For Navigation, we just wait for the agent task to complete
        since the service is stateless and on-demand.
        """
        logger.info("Navigation adapter lifecycle started")
        try:
            # Wait for the agent task to signal shutdown
            await agent_task
        except asyncio.CancelledError:
            logger.info("Navigation adapter lifecycle cancelled")
        finally:
            await self.stop()

    def get_config(self) -> AdapterConfig:
        """Get adapter configuration."""
        return AdapterConfig(
            adapter_type="navigation",
            enabled=self._running,
            settings={
                "user_agent": self.navigation_service.user_agent,
                "base_url": self.navigation_service.base_url,
                "routing_url": self.navigation_service.routing_url,
            },
        )

    def get_status(self) -> RuntimeAdapterStatus:
        """Get adapter status."""
        return RuntimeAdapterStatus(
            adapter_id="navigation",
            adapter_type="navigation",
            is_running=self._running,
            loaded_at=None,
            error=None,
        )


# Export as Adapter for load_adapter() compatibility
Adapter = NavigationAdapter
