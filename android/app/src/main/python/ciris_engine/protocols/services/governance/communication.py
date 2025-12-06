"""Communication Service Protocol.

IMPORTANT: This is NOT one of the 22 core services!

This protocol defines the interface for adapter-provided communication services.
It is used by the CommunicationBus to enable multiple communication providers:
- CLIAdapter provides CLI-based communication
- APICommunicationService provides API-based communication
- DiscordAdapter provides Discord-based communication

There is no core CommunicationService - all communication is handled by adapters
that implement this protocol and register with the CommunicationBus.

See CLAUDE.md section on "Message Bus Architecture" for more details.
"""

from abc import abstractmethod
from datetime import datetime
from typing import List, Optional, Protocol

from ciris_engine.schemas.runtime.messages import FetchedMessage

from ...runtime.base import ServiceProtocol


class CommunicationServiceProtocol(ServiceProtocol, Protocol):
    """Protocol for adapter-provided communication services.

    This protocol must be implemented by any adapter that wants to provide
    communication capabilities to the CIRIS system. Adapters register their
    implementation with the CommunicationBus at runtime.
    """

    @abstractmethod
    async def send_message(self, channel_id: str, content: str) -> bool:
        """Send a message to the specified channel."""
        ...

    @abstractmethod
    async def fetch_messages(
        self,
        channel_id: str,
        *,
        limit: int = 50,
        before: Optional[datetime] = None,
    ) -> List[FetchedMessage]:
        """Retrieve messages from a channel."""
        ...

    @abstractmethod
    def get_home_channel_id(self) -> Optional[str]:
        """Get the home channel ID for this communication adapter.

        Returns:
            The formatted channel ID (e.g., 'discord_123456', 'cli_user@host', 'api_0.0.0.0_8080')
            or None if no home channel is configured.
        """
        ...
