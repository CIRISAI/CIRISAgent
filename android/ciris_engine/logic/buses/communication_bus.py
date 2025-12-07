"""
Communication message bus - handles all communication service operations
"""

import logging
import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from ciris_engine.schemas.types import JSONDict

if TYPE_CHECKING:
    from ciris_engine.logic.registries.base import ServiceRegistry

from ciris_engine.logic.registries.base import Priority
from ciris_engine.protocols.services import CommunicationService
from ciris_engine.protocols.services.lifecycle.time import TimeServiceProtocol
from ciris_engine.schemas.infrastructure.base import BusMetrics
from ciris_engine.schemas.runtime.enums import ServiceType
from ciris_engine.schemas.runtime.messages import FetchedMessage

from .base_bus import BaseBus, BusMessage

logger = logging.getLogger(__name__)

# Channel prefix constants for adapter routing
REDDIT_CHANNEL_PREFIX = "reddit:"


@dataclass
class SendMessageRequest(BusMessage):
    """Request to send a message"""

    channel_id: str
    content: str


@dataclass
class FetchMessagesRequest(BusMessage):
    """Request to fetch messages"""

    channel_id: str
    limit: int = 100


class CommunicationBus(BaseBus[CommunicationService]):
    """
    Message bus for all communication operations.

    Handles:
    - send_message
    - fetch_messages
    """

    def __init__(
        self,
        service_registry: "ServiceRegistry",
        time_service: TimeServiceProtocol,
        telemetry_service: Optional[Any] = None,
    ):
        super().__init__(service_type=ServiceType.COMMUNICATION, service_registry=service_registry)
        self._time_service = time_service
        self._start_time = time_service.now() if time_service else None

        # Metrics tracking
        self._messages_sent = 0
        self._messages_received = 0
        self._broadcasts = 0
        self._errors = 0

    async def get_default_channel(self) -> Optional[str]:
        """Get home channel from highest priority communication adapter.

        This is used when no channel_id is specified, such as during wakeup.

        Returns:
            Home channel ID or None if no adapter has a home channel
        """
        # Get all communication services sorted by priority
        all_services = self.service_registry.get_services_by_type(ServiceType.COMMUNICATION)
        logger.debug(f"get_default_channel: Found {len(all_services)} COMMUNICATION services in registry")

        # Get provider metadata for priority sorting
        providers_with_priority = []
        for service in all_services:
            # Find the provider info for this service
            provider_info = self.service_registry.get_provider_info(service_type=ServiceType.COMMUNICATION.value)
            if "services" in provider_info and ServiceType.COMMUNICATION.value in provider_info["services"]:
                for provider in provider_info["services"][ServiceType.COMMUNICATION.value]:
                    # Match by class name since we can't directly compare instances
                    if provider["name"].startswith(service.__class__.__name__):
                        priority_value = Priority[provider["priority"]].value
                        providers_with_priority.append((priority_value, service))
                        break

        # Sort by priority (lower value = higher priority)
        providers_with_priority.sort(key=lambda x: x[0])

        # Try each adapter in priority order
        logger.debug(f"Checking {len(providers_with_priority)} providers for home channel")
        for _, service in providers_with_priority:
            logger.debug(f"Checking provider: {service.__class__.__name__}")
            if hasattr(service, "get_home_channel_id"):
                logger.debug(f"Provider {service.__class__.__name__} has get_home_channel_id method")
                home_channel = service.get_home_channel_id()
                logger.debug(f"Provider {service.__class__.__name__} returned home_channel: {home_channel}")
                if home_channel:
                    logger.debug(f"Found home channel '{home_channel}' from {service.__class__.__name__}")
                    return home_channel  # type: ignore[no-any-return]
            else:
                logger.debug(f"Provider {service.__class__.__name__} does not have get_home_channel_id method")

        logger.warning("No communication adapter has a home channel configured")
        return None

    async def send_message(
        self, channel_id: Optional[str], content: str, handler_name: str, metadata: Optional[JSONDict] = None
    ) -> bool:
        """
        Send a message to a channel.

        This is async and returns immediately after queuing.
        """
        message = SendMessageRequest(
            id=str(uuid.uuid4()),
            handler_name=handler_name,
            timestamp=self._time_service.now(),
            metadata=metadata or {},
            channel_id=channel_id or "",  # Provide empty string if None
            content=content,
        )

        success = await self._enqueue(message)
        if success:
            logger.debug(f"Queued send_message for channel {channel_id}")
            self._messages_sent += 1
        return success

    async def send_message_sync(
        self, channel_id: Optional[str], content: str, handler_name: str, metadata: Optional[JSONDict] = None
    ) -> bool:
        """
        Send a message synchronously (wait for completion).

        This bypasses the queue for immediate operations.
        Routes based on channel_id prefix for cross-adapter communication.
        If channel_id is None, uses the highest priority adapter's home channel.
        """
        service = None
        resolved_channel_id = channel_id

        # If no channel_id provided or empty string, find highest priority adapter's home channel
        if not channel_id or channel_id == "":
            resolved_channel_id = await self.get_default_channel()
            if not resolved_channel_id:
                logger.error("No channel_id provided and no adapter with home channel available")
                return False
            logger.debug(f"Using default channel from highest priority adapter: {resolved_channel_id}")

        # Get all available communication services for routing
        all_services = self.service_registry.get_services_by_type(ServiceType.COMMUNICATION)

        if all_services and resolved_channel_id:
            # Route based on channel prefix
            if resolved_channel_id.startswith("discord_"):
                # Handles both discord_channelid and discord_guildid_channelid formats
                for svc in all_services:
                    if "Discord" in type(svc).__name__:
                        service = svc
                        logger.debug(f"Sync routing to Discord adapter for channel {resolved_channel_id}")
                        break
            elif resolved_channel_id.startswith("api_") or resolved_channel_id.startswith("ws:"):
                for svc in all_services:
                    if "API" in type(svc).__name__:
                        service = svc
                        logger.debug(f"Sync routing to API adapter for channel {resolved_channel_id}")
                        break
            elif resolved_channel_id.startswith("cli_"):
                for svc in all_services:
                    if "CLI" in type(svc).__name__:
                        service = svc
                        logger.debug(f"Sync routing to CLI adapter for channel {resolved_channel_id}")
                        break
            elif resolved_channel_id.startswith(REDDIT_CHANNEL_PREFIX):
                for svc in all_services:
                    if "Reddit" in type(svc).__name__:
                        service = svc
                        logger.debug(f"Sync routing to Reddit adapter for channel {resolved_channel_id}")
                        break

        # Fallback to original logic
        if not service:
            service = await self.get_service(handler_name=handler_name, required_capabilities=["send_message"])

        if not service:
            logger.error(f"No communication service available for channel {resolved_channel_id}")
            return False

        try:
            result = await service.send_message(resolved_channel_id or "", content)  # Ensure non-None
            if result:
                self._messages_sent += 1
            return bool(result)
        except Exception as e:
            logger.error(f"Failed to send message: {e}", exc_info=True)
            return False

    def _convert_to_fetched_message(self, msg: Any) -> Optional[FetchedMessage]:
        """Convert a message object to FetchedMessage format."""
        # Handle already-converted FetchedMessage objects
        if isinstance(msg, FetchedMessage):
            return msg

        # Handle dict objects
        if isinstance(msg, dict):
            return FetchedMessage(**msg)

        # Try to convert other message types to dict first
        try:
            msg_dict = msg.model_dump() if hasattr(msg, "model_dump") else dict(msg)
            return FetchedMessage(**msg_dict)
        except Exception as e:
            logger.warning(f"Skipping message of type {type(msg)}: {e}")
            return None

    async def fetch_messages(self, channel_id: str, limit: int, handler_name: str) -> List[FetchedMessage]:
        """
        Fetch messages from a channel.

        This is always synchronous as we need the result.
        """
        service = None
        all_services = self.service_registry.get_services_by_type(ServiceType.COMMUNICATION)

        if channel_id.startswith(REDDIT_CHANNEL_PREFIX):
            for svc in all_services:
                if "Reddit" in type(svc).__name__:
                    service = svc
                    logger.debug(f"Routing fetch to Reddit adapter for channel {channel_id}")
                    break

        if not service:
            service = await self.get_service(handler_name=handler_name, required_capabilities=["fetch_messages"])

        if not service:
            logger.error(f"No communication service available for {handler_name}")
            return []

        try:
            messages = await service.fetch_messages(channel_id, limit=limit)
            if not messages:
                return []

            # Convert messages to FetchedMessage objects using helper method
            fetched_messages = [
                converted for msg in messages if (converted := self._convert_to_fetched_message(msg)) is not None
            ]

            # Track messages received
            self._messages_received += len(fetched_messages)
            return fetched_messages
        except Exception as e:
            logger.error(f"Failed to fetch messages: {e}", exc_info=True)
            return []

    async def _process_message(self, message: BusMessage) -> None:
        """Process a communication message"""
        if isinstance(message, SendMessageRequest):
            await self._process_send_message(message)
        elif isinstance(message, FetchMessagesRequest):
            # Fetch is always sync, shouldn't be in queue
            logger.warning("FetchMessagesRequest in queue - this shouldn't happen")
        else:
            logger.error(f"Unknown message type: {type(message)}")

    async def _process_send_message(self, request: SendMessageRequest) -> None:
        """Process a send message request with channel-aware routing"""

        # First, try to find the right service based on channel_id prefix
        service = None
        channel_id: Optional[str] = request.channel_id
        resolved_channel_id: Optional[str] = channel_id

        # If no channel_id provided or empty string, find highest priority adapter's home channel
        if not channel_id or channel_id == "":
            resolved_channel_id = await self.get_default_channel()
            if not resolved_channel_id:
                raise RuntimeError("No channel_id provided and no adapter with home channel available")
            logger.debug(f"Using default channel from highest priority adapter: {resolved_channel_id}")

        # Get all available communication services
        all_services = self.service_registry.get_services_by_type(ServiceType.COMMUNICATION)

        if all_services and resolved_channel_id:
            # Route based on channel prefix
            if resolved_channel_id.startswith("discord_"):
                # Handles both discord_channelid and discord_guildid_channelid formats
                # Find Discord communication service
                for svc in all_services:
                    if "Discord" in type(svc).__name__:
                        service = svc
                        logger.debug(f"Routing to Discord adapter for channel {resolved_channel_id}")
                        break
            elif resolved_channel_id.startswith("api_") or resolved_channel_id.startswith("ws:"):
                # Find API communication service
                for svc in all_services:
                    if "API" in type(svc).__name__:
                        service = svc
                        logger.debug(f"Routing to API adapter for channel {resolved_channel_id}")
                        break
            elif resolved_channel_id.startswith("cli_"):
                # Find CLI communication service
                for svc in all_services:
                    if "CLI" in type(svc).__name__:
                        service = svc
                        logger.debug(f"Routing to CLI adapter for channel {resolved_channel_id}")
                        break
            elif resolved_channel_id.startswith(REDDIT_CHANNEL_PREFIX):
                for svc in all_services:
                    if "Reddit" in type(svc).__name__:
                        service = svc
                        logger.debug(f"Routing to Reddit adapter for channel {resolved_channel_id}")
                        break

        # Fallback to original logic if no specific routing found
        if not service:
            service = await self.get_service(handler_name=request.handler_name, required_capabilities=["send_message"])

        if not service:
            raise RuntimeError(f"No communication service available for channel {resolved_channel_id}")

        # Send the message (ensure non-None channel_id)
        success = await service.send_message(resolved_channel_id or "", request.content)

        if success:
            logger.debug(f"Successfully sent message to {resolved_channel_id} " f"via {type(service).__name__}")
            # Count broadcasts (messages sent to multiple recipients or channel-wide)
            if not resolved_channel_id or resolved_channel_id.startswith(("discord_", "api_", "cli_")):
                self._broadcasts += 1
        else:
            logger.warning(f"Failed to send message to {resolved_channel_id} " f"via {type(service).__name__}")

    def _collect_metrics(self) -> Dict[str, float]:
        """Collect base metrics for the communication bus."""
        uptime_seconds = 0.0
        if hasattr(self, "_time_service") and self._time_service:
            # Calculate uptime if we have a start time
            if hasattr(self, "_start_time") and self._start_time:
                uptime_seconds = (self._time_service.now() - self._start_time).total_seconds()

        return {
            "communication_messages_sent": float(self._messages_sent),
            "communication_messages_received": float(self._messages_received),
            "communication_broadcasts": float(self._broadcasts),
            "communication_errors": float(self._errors),
            "communication_uptime_seconds": uptime_seconds,
        }

    def get_metrics(self) -> BusMetrics:
        """Get all communication bus metrics as typed BusMetrics schema."""
        # Get active connections count from service registry
        active_connections = len(self.service_registry.get_services_by_type(ServiceType.COMMUNICATION))

        # Calculate uptime
        uptime_seconds = 0.0
        if hasattr(self, "_time_service") and self._time_service:
            if hasattr(self, "_start_time") and self._start_time:
                uptime_seconds = (self._time_service.now() - self._start_time).total_seconds()

        # Map to BusMetrics schema - put communication-specific metrics in additional_metrics
        return BusMetrics(
            messages_sent=self._messages_sent,
            messages_received=self._messages_received,
            messages_dropped=0,  # Not tracked yet
            average_latency_ms=0.0,  # Not tracked yet
            active_subscriptions=active_connections,
            queue_depth=self.get_queue_size(),
            errors_last_hour=self._errors,  # Total errors (not windowed yet)
            busiest_service=None,  # Could track which adapter gets most traffic
            additional_metrics={
                "communication_messages_sent": self._messages_sent,
                "communication_messages_received": self._messages_received,
                "communication_broadcasts": self._broadcasts,
                "communication_errors": self._errors,
                "communication_uptime_seconds": uptime_seconds,
            },
        )
