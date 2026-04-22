"""
Reddit Adapter for CIRIS.

Provides the BaseAdapterProtocol-compliant wrapper around RedditToolService
and RedditCommunicationService for dynamic adapter loading via RuntimeAdapterManager.
"""

import asyncio
import logging
from typing import Any, List, Optional

from ciris_engine.logic.adapters.base import Service
from ciris_engine.logic.registries.base import Priority
from ciris_engine.schemas.adapters import AdapterServiceRegistration
from ciris_engine.schemas.runtime.adapter_management import AdapterConfig, RuntimeAdapterStatus
from ciris_engine.schemas.runtime.enums import ServiceType

from .schemas import RedditCredentials
from .service import RedditCommunicationService, RedditToolService

logger = logging.getLogger(__name__)


class RedditAdapter(Service):
    """
    Reddit adapter platform for CIRIS.

    Wraps RedditToolService and RedditCommunicationService to provide the
    BaseAdapterProtocol interface required for dynamic adapter loading via
    RuntimeAdapterManager.
    """

    def __init__(self, runtime: Any, context: Optional[Any] = None, **kwargs: Any) -> None:
        """Initialize Reddit adapter."""
        super().__init__(config=kwargs.get("adapter_config"))
        self.runtime = runtime
        self.context = context

        # Load credentials from environment
        # RedditConfigurableAdapter.apply_config() sets these environment variables
        credentials = RedditCredentials.from_env()
        if not credentials or not credentials.is_complete():
            raise RuntimeError("Reddit credentials are not configured. Run configuration wizard first.")

        # Extract runtime dependencies if available
        time_service = getattr(runtime, "time_service", None) if runtime else None
        bus_manager = getattr(runtime, "bus_manager", None) if runtime else None
        memory_service = getattr(runtime, "memory_service", None) if runtime else None
        agent_id = getattr(runtime, "agent_id", None) if runtime else None
        filter_service = getattr(runtime, "filter_service", None) if runtime else None
        secrets_service = getattr(runtime, "secrets_service", None) if runtime else None
        agent_occurrence_id = getattr(runtime, "agent_occurrence_id", "default") if runtime else "default"

        # Create underlying Reddit services
        self.tool_service = RedditToolService(
            credentials=credentials,
            time_service=time_service,
        )

        self.communication_service = RedditCommunicationService(
            credentials=credentials,
            time_service=time_service,
            bus_manager=bus_manager,
            memory_service=memory_service,
            agent_id=agent_id,
            filter_service=filter_service,
            secrets_service=secrets_service,
            agent_occurrence_id=agent_occurrence_id,
        )

        # Track adapter state
        self._running = False
        self._lifecycle_task: Optional[asyncio.Task[None]] = None

        logger.info(f"Reddit adapter initialized for u/{credentials.username}")

    def get_services_to_register(self) -> List[AdapterServiceRegistration]:
        """Get services provided by this adapter."""
        registrations = []

        # Register tool service
        registrations.append(
            AdapterServiceRegistration(
                service_type=ServiceType.TOOL,
                provider=self.tool_service,
                priority=Priority.NORMAL,
                capabilities=[
                    "tool:reddit",
                    "tool:reddit:get_user_context",
                    "tool:reddit:submit_post",
                    "tool:reddit:submit_comment",
                    "tool:reddit:remove_content",
                    "tool:reddit:get_submission",
                    "tool:reddit:observe",
                    "tool:reddit:delete_content",
                    "tool:reddit:disclose_identity",
                    "provider:reddit",
                ],
            )
        )

        # Register communication service
        registrations.append(
            AdapterServiceRegistration(
                service_type=ServiceType.COMMUNICATION,
                provider=self.communication_service,
                priority=Priority.LOW,
                capabilities=[
                    "communication:send_message",
                    "communication:fetch_messages",
                    "provider:reddit",
                ],
            )
        )

        return registrations

    async def start(self) -> None:
        """Start the Reddit adapter."""
        logger.info("Starting Reddit adapter")
        await self.tool_service.start()
        await self.communication_service.start()
        self._running = True
        logger.info("Reddit adapter started")

    async def stop(self) -> None:
        """Stop the Reddit adapter."""
        logger.info("Stopping Reddit adapter")
        self._running = False

        if self._lifecycle_task and not self._lifecycle_task.done():
            self._lifecycle_task.cancel()
            try:
                await self._lifecycle_task
            except asyncio.CancelledError:
                pass

        # Stop both services
        if hasattr(self.tool_service, "stop"):
            await self.tool_service.stop()
        if hasattr(self.communication_service, "stop"):
            await self.communication_service.stop()

        logger.info("Reddit adapter stopped")

    async def run_lifecycle(self, agent_task: Any) -> None:
        """Run the adapter lifecycle.

        For Reddit, we just wait for the agent task to complete since Reddit
        integration is event-driven via the RedditObserver and doesn't need
        continuous polling.
        """
        logger.info("Reddit adapter lifecycle started")
        try:
            # Wait for the agent task to signal shutdown
            await agent_task
        except asyncio.CancelledError:
            logger.info("Reddit adapter lifecycle cancelled")
        finally:
            await self.stop()

    def get_config(self) -> AdapterConfig:
        """Get adapter configuration."""
        # Get credentials for display (sanitized)
        creds = self.tool_service._credentials if hasattr(self.tool_service, "_credentials") else None

        return AdapterConfig(
            adapter_type="reddit",
            enabled=self._running,
            settings={
                "username": creds.username if creds else None,
                "subreddit": creds.subreddit if creds else None,
                "has_credentials": bool(creds and creds.is_complete()),
            },
        )

    def get_status(self) -> RuntimeAdapterStatus:
        """Get adapter status."""
        return RuntimeAdapterStatus(
            adapter_id="reddit",
            adapter_type="reddit",
            is_running=self._running,
            loaded_at=None,
            error=None,
        )


# Export as Adapter for load_adapter() compatibility
Adapter = RedditAdapter
