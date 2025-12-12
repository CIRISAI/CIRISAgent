"""
Sample Adapter for CIRIS.

Provides the BaseAdapterProtocol-compliant wrapper around sample services
so it can be loaded dynamically via RuntimeAdapterManager.load_adapter().

This serves as a complete template for creating new adapters.
"""

import asyncio
import logging
from typing import Any, List, Optional

from ciris_engine.logic.adapters.base import Service
from ciris_engine.logic.registries.base import Priority
from ciris_engine.schemas.adapters import AdapterServiceRegistration
from ciris_engine.schemas.runtime.adapter_management import AdapterConfig, RuntimeAdapterStatus
from ciris_engine.schemas.runtime.enums import ServiceType

from .services import SampleCommunicationService, SampleToolService, SampleWisdomService

logger = logging.getLogger(__name__)


class SampleAdapter(Service):
    """
    Sample adapter platform for CIRIS.

    This adapter demonstrates:
    - BaseAdapterProtocol compliance for dynamic loading
    - Registration of multiple service types (TOOL, COMMUNICATION, WISE_AUTHORITY)
    - Proper lifecycle management (start, stop, run_lifecycle)
    - Service registration with capabilities

    Use this as a template when building new adapters.
    """

    def __init__(self, runtime: Any, context: Optional[Any] = None, **kwargs: Any) -> None:
        """Initialize Sample adapter.

        Args:
            runtime: CIRIS runtime instance
            context: Optional runtime context
            **kwargs: Additional configuration (may include adapter_config)
        """
        super().__init__(config=kwargs.get("adapter_config"))
        self.runtime = runtime
        self.context = context

        # Extract config from kwargs
        adapter_config = kwargs.get("adapter_config", {})

        # Create the underlying services
        # In production adapters, read config from environment variables
        # set by ConfigurableAdapter.apply_config()
        self.tool_service = SampleToolService(config=adapter_config)
        self.communication_service = SampleCommunicationService(config=adapter_config)
        self.wisdom_service = SampleWisdomService(config=adapter_config)

        # Track adapter state
        self._running = False
        self._lifecycle_task: Optional[asyncio.Task[None]] = None

        logger.info("Sample adapter initialized")

    def get_services_to_register(self) -> List[AdapterServiceRegistration]:
        """Get services provided by this adapter.

        Returns:
            List of service registrations with type, provider, priority, and capabilities
        """
        registrations = []

        # Register TOOL service
        registrations.append(
            AdapterServiceRegistration(
                service_type=ServiceType.TOOL,
                provider=self.tool_service,
                priority=Priority.NORMAL,
                capabilities=[
                    "tool:sample",
                    "tool:sample:echo",
                    "tool:sample:status",
                    "tool:sample:config",
                ],
            )
        )

        # Register COMMUNICATION service
        registrations.append(
            AdapterServiceRegistration(
                service_type=ServiceType.COMMUNICATION,
                provider=self.communication_service,
                priority=Priority.LOW,  # Lower priority than production adapters
                capabilities=[
                    "communication:send_message",
                    "communication:fetch_messages",
                    "provider:sample",
                ],
            )
        )

        # Register WISE_AUTHORITY service
        registrations.append(
            AdapterServiceRegistration(
                service_type=ServiceType.WISE_AUTHORITY,
                provider=self.wisdom_service,
                priority=Priority.NORMAL,
                capabilities=[
                    "get_guidance",
                    "fetch_guidance",
                    "domain:sample",
                ],
            )
        )

        return registrations

    async def start(self) -> None:
        """Start the Sample adapter.

        Calls start() on all underlying services.
        """
        logger.info("Starting Sample adapter")

        # Start all services
        await self.tool_service.start()
        await self.communication_service.start()
        await self.wisdom_service.start()

        self._running = True
        logger.info("Sample adapter started")

    async def stop(self) -> None:
        """Stop the Sample adapter.

        Calls stop() on all underlying services and cancels lifecycle task.
        """
        logger.info("Stopping Sample adapter")
        self._running = False

        # Cancel lifecycle task if running
        if self._lifecycle_task and not self._lifecycle_task.done():
            self._lifecycle_task.cancel()
            try:
                await self._lifecycle_task
            except asyncio.CancelledError:
                pass

        # Stop all services
        await self.tool_service.stop()
        await self.communication_service.stop()
        await self.wisdom_service.stop()

        logger.info("Sample adapter stopped")

    async def run_lifecycle(self, agent_task: Any) -> None:
        """Run the adapter lifecycle.

        For the sample adapter, we just wait for the agent task to complete
        since it's primarily for testing and doesn't need continuous polling.

        Args:
            agent_task: The main agent task (signals shutdown when complete)
        """
        logger.info("Sample adapter lifecycle started")
        try:
            # Wait for the agent task to signal shutdown
            await agent_task
        except asyncio.CancelledError:
            logger.info("Sample adapter lifecycle cancelled")
        finally:
            await self.stop()

    def get_config(self) -> AdapterConfig:
        """Get adapter configuration.

        Returns:
            Current adapter configuration
        """
        return AdapterConfig(
            adapter_type="sample_adapter",
            enabled=self._running,
            settings={
                "tool_calls": getattr(self.tool_service, "_call_count", 0),
                "messages_sent": len(getattr(self.communication_service, "_sent_messages", [])),
                "guidance_requests": getattr(self.wisdom_service, "_guidance_count", 0),
            },
        )

    def get_status(self) -> RuntimeAdapterStatus:
        """Get adapter status.

        Returns:
            Current adapter runtime status
        """
        return RuntimeAdapterStatus(
            adapter_id="sample_adapter",
            adapter_type="sample_adapter",
            is_running=self._running,
            loaded_at=None,  # Would track actual load time in production
            error=None,
        )


# Export as Adapter for load_adapter() compatibility
# This is the critical line that allows RuntimeAdapterManager to find the adapter
Adapter = SampleAdapter
