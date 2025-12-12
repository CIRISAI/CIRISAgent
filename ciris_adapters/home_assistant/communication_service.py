"""
Home Assistant Communication Service.

Provides COMMUNICATION capabilities for Home Assistant:
- Receiving events as incoming messages (motion, person detected, doorbell, etc.)
- Sending messages via TTS or HA conversation integration
- Bidirectional event-driven communication channel

This implements the CommunicationService protocol for proper integration
with the CIRIS message bus.
"""

import asyncio
import logging
import uuid
from collections import deque
from datetime import datetime, timezone
from typing import Any, Deque, Dict, List, Optional

from ciris_engine.schemas.runtime.messages import IncomingMessage
from ciris_engine.schemas.services.core import ServiceCapabilities

from .schemas import DetectionEvent, EventType, HAEventType
from .service import HAIntegrationService

logger = logging.getLogger(__name__)


class HACommunicationService:
    """
    Communication service for Home Assistant.

    Converts HA events into IncomingMessages that the agent can process
    and respond to, enabling event-driven smart home interactions.

    Channels:
    - ha_events: General HA events (state changes, automations fired)
    - ha_camera_{name}: Per-camera event channels
    - ha_doorbell: Doorbell events
    - ha_voice: Voice assistant integration (if configured)
    """

    def __init__(self, ha_service: HAIntegrationService) -> None:
        """Initialize with underlying HA integration service."""
        self.ha_service = ha_service
        self._started = False

        # Message queues per channel
        self._message_queues: Dict[str, Deque[IncomingMessage]] = {}
        self._event_callbacks: List[Any] = []

        # Detection event to message conversion
        self._detection_subscriptions: Dict[str, bool] = {}

        # WebSocket connection for real-time HA events (if available)
        self._ws_task: Optional[asyncio.Task[None]] = None

        logger.info("HACommunicationService initialized")

    def get_capabilities(self) -> ServiceCapabilities:
        """Return communication capabilities."""
        return ServiceCapabilities(
            service_name="ha_communication",
            actions=[
                "send_message",
                "fetch_messages",
                "subscribe_events",
                "get_channels",
            ],
            version="1.0.0",
            dependencies=[],
            metadata={
                "capabilities": [
                    "send_message",
                    "fetch_messages",
                    "provider:home_assistant",
                    "channel:ha_events",
                    "channel:ha_camera",
                    "modality:event:motion",
                    "modality:event:person",
                ]
            },
        )

    async def start(self) -> None:
        """Start the communication service."""
        self._started = True

        # Initialize default channels
        self._message_queues["ha_events"] = deque(maxlen=100)

        # Create camera channels
        cameras = await self.ha_service.get_available_cameras()
        for camera in cameras:
            channel = f"ha_camera_{camera}"
            self._message_queues[channel] = deque(maxlen=50)
            logger.info(f"Created camera channel: {channel}")

        # Start event detection for configured cameras
        for camera in cameras:
            await self._start_camera_event_stream(camera)

        logger.info(f"HACommunicationService started with {len(self._message_queues)} channels")

    async def stop(self) -> None:
        """Stop the communication service."""
        self._started = False

        # Stop camera event detection
        cameras = await self.ha_service.get_available_cameras()
        for camera in cameras:
            await self.ha_service.stop_event_detection(camera)

        # Cancel WebSocket task if running
        if self._ws_task and not self._ws_task.done():
            self._ws_task.cancel()
            try:
                await self._ws_task
            except asyncio.CancelledError:
                pass

        logger.info("HACommunicationService stopped")

    async def get_channels(self) -> List[str]:
        """Get list of available communication channels."""
        return list(self._message_queues.keys())

    async def send_message(
        self,
        channel_id: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        Send a message via Home Assistant.

        For HA, 'sending' typically means:
        - TTS announcement on media players
        - Notification to mobile devices
        - Response to HA conversation integration

        Args:
            channel_id: Target channel (ha_tts, ha_notify, ha_conversation)
            content: Message content
            metadata: Additional data (target device, etc.)

        Returns:
            True if message was sent successfully
        """
        metadata = metadata or {}

        try:
            if channel_id.startswith("ha_tts"):
                # TTS announcement
                entity_id = metadata.get("media_player", "media_player.living_room")
                return await self._send_tts(content, entity_id)

            elif channel_id.startswith("ha_notify"):
                # Mobile notification
                from .schemas import HANotification

                notification = HANotification(
                    title=metadata.get("title", "CIRIS"),
                    message=content,
                    target=metadata.get("target"),
                )
                return await self.ha_service.send_notification(notification)

            elif channel_id == "ha_conversation":
                # HA conversation integration response
                # This would integrate with HA's conversation API
                logger.info(f"Conversation response: {content}")
                return True

            else:
                logger.warning(f"Unknown send channel: {channel_id}")
                return False

        except Exception as e:
            logger.error(f"Error sending message to {channel_id}: {e}")
            return False

    async def _send_tts(self, message: str, media_player: str) -> bool:
        """Send TTS message to a media player."""
        if not self.ha_service.ha_token:
            return False

        try:
            import aiohttp

            payload = {
                "entity_id": media_player,
                "message": message,
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.ha_service.ha_url}/api/services/tts/speak",
                    headers=self.ha_service._get_headers(),
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as response:
                    return response.status == 200
        except Exception as e:
            logger.error(f"TTS error: {e}")
            return False

    async def fetch_messages(
        self,
        channel_id: Optional[str] = None,
        limit: int = 10,
    ) -> List[IncomingMessage]:
        """
        Fetch pending messages from Home Assistant event channels.

        Args:
            channel_id: Specific channel to fetch from (None = all channels)
            limit: Maximum messages to return

        Returns:
            List of IncomingMessage objects representing HA events
        """
        messages: List[IncomingMessage] = []

        if channel_id:
            # Fetch from specific channel
            queue = self._message_queues.get(channel_id)
            if queue:
                while queue and len(messages) < limit:
                    messages.append(queue.popleft())
        else:
            # Fetch from all channels
            for ch_id, queue in self._message_queues.items():
                while queue and len(messages) < limit:
                    messages.append(queue.popleft())

        return messages

    async def _start_camera_event_stream(self, camera_name: str) -> None:
        """Start event detection for a camera and convert events to messages."""
        # Register callback for detection events
        self._detection_subscriptions[camera_name] = True

        # Hook into the HA service's detection loop
        # Override the event handler to convert to messages
        original_send_event = self.ha_service._send_ha_event

        async def event_to_message(event: DetectionEvent) -> bool:
            """Convert detection event to IncomingMessage."""
            # Still send to HA
            await original_send_event(event)

            # Also create an IncomingMessage for the agent
            channel = f"ha_camera_{event.camera_name}"
            if channel not in self._message_queues:
                self._message_queues[channel] = deque(maxlen=50)

            message = self._detection_event_to_message(event)
            self._message_queues[channel].append(message)

            logger.info(f"Camera event converted to message: {event.event_type} on {event.camera_name}")
            return True

        # Replace the event handler
        self.ha_service._send_ha_event = event_to_message  # type: ignore

        # Start detection if not already running
        if camera_name not in self.ha_service._detection_tasks:
            await self.ha_service.start_event_detection(camera_name)

    def _detection_event_to_message(self, event: DetectionEvent) -> IncomingMessage:
        """Convert a DetectionEvent to an IncomingMessage."""
        # Map event type to human-readable description
        event_descriptions = {
            EventType.PERSON: "Person detected",
            EventType.VEHICLE: "Vehicle detected",
            EventType.ANIMAL: "Animal detected",
            EventType.PACKAGE: "Package detected",
            EventType.MOTION: "Motion detected",
            EventType.ACTIVITY: "Activity detected",
        }

        description = event_descriptions.get(event.event_type, "Event detected")
        content = f"{description} on {event.camera_name}"
        if event.description:
            content = f"{content}: {event.description}"

        return IncomingMessage(
            message_id=str(uuid.uuid4()),
            channel_id=f"ha_camera_{event.camera_name}",
            author_id="home_assistant",
            author_name="Home Assistant",
            content=content,
            timestamp=event.timestamp,
            metadata={
                "event_type": event.event_type.value if hasattr(event.event_type, "value") else str(event.event_type),
                "ha_event_type": (
                    event.ha_event_type.value if hasattr(event.ha_event_type, "value") else str(event.ha_event_type)
                ),
                "camera_name": event.camera_name,
                "confidence": event.confidence,
                "zones": event.zones,
                "source": "home_assistant_camera",
            },
        )

    async def subscribe_to_ha_events(self, event_types: Optional[List[str]] = None) -> bool:
        """
        Subscribe to Home Assistant state change events via WebSocket.

        This enables real-time event streaming from HA.
        """
        # TODO: Implement WebSocket connection to HA for real-time events
        # ws://ha_url/api/websocket
        # This would enable:
        # - State change events
        # - Automation triggered events
        # - Script execution events
        # - Service call events
        logger.info("HA event subscription: WebSocket integration pending")
        return True

    def create_ha_state_change_message(
        self,
        entity_id: str,
        old_state: str,
        new_state: str,
        friendly_name: str,
    ) -> IncomingMessage:
        """Create an IncomingMessage from an HA state change event."""
        content = f"{friendly_name} changed from {old_state} to {new_state}"

        return IncomingMessage(
            message_id=str(uuid.uuid4()),
            channel_id="ha_events",
            author_id="home_assistant",
            author_name="Home Assistant",
            content=content,
            timestamp=datetime.now(timezone.utc),
            metadata={
                "event_type": "state_changed",
                "entity_id": entity_id,
                "old_state": old_state,
                "new_state": new_state,
                "source": "home_assistant_state",
            },
        )
