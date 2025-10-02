"""
Adapter protocols for the CIRIS Trinity Architecture.

These protocols define contracts for platform adapters.
Adapters are the interfaces between CIRIS and external platforms.
"""

from abc import abstractmethod
from typing import TYPE_CHECKING, Any, Callable, Dict, Optional

if TYPE_CHECKING:
    from ciris_engine.logic.adapters.discord.config import DiscordAdapterConfig
    from ciris_engine.schemas.infrastructure.base import BusMetrics

from ciris_engine.protocols.runtime.base import BaseAdapterProtocol
from ciris_engine.schemas.types import JSONDict, SerializedModel

# ============================================================================
# PLATFORM ADAPTER PROTOCOLS
# ============================================================================


class APIAdapterProtocol(BaseAdapterProtocol):
    """Protocol for REST API adapter."""

    @abstractmethod
    async def setup_routes(self) -> None:
        """Setup all API routes."""
        ...

    @abstractmethod
    async def handle_request(self, request: Any) -> Any:
        """Handle incoming API request."""
        ...

    @abstractmethod
    def get_openapi_spec(self) -> JSONDict:
        """Get OpenAPI specification."""
        ...

    @abstractmethod
    def add_middleware(self, middleware: Callable[..., Any]) -> None:
        """Add middleware to the API."""
        ...

    @abstractmethod
    def get_route_metrics(self) -> "BusMetrics":
        """Get metrics for each route."""
        ...


class CLIAdapterProtocol(BaseAdapterProtocol):
    """Protocol for Command Line Interface adapter."""

    @abstractmethod
    def register_commands(self) -> None:
        """Register all CLI commands."""
        ...

    @abstractmethod
    async def handle_input(self, _: str) -> str:
        """Handle CLI input and return response."""
        ...

    @abstractmethod
    def show_prompt(self) -> str:
        """Get the CLI prompt to display."""
        ...

    @abstractmethod
    def get_command_help(self, command: Optional[str] = None) -> str:
        """Get help text for commands."""
        ...

    @abstractmethod
    def set_output_format(self, format: str) -> None:
        """Set output format (text, json, table)."""
        ...


class DiscordAdapterProtocol(BaseAdapterProtocol):
    """Protocol for Discord bot adapter."""

    @abstractmethod
    async def setup_bot(self) -> None:
        """Setup Discord bot with commands and events."""
        ...

    @abstractmethod
    async def handle_message(self, message: Any) -> None:
        """Handle incoming Discord message."""
        ...

    @abstractmethod
    async def handle_reaction(self, _: Any, user: Any) -> None:
        """Handle reaction events."""
        ...

    @abstractmethod
    async def send_message(self, channel_id: str, content: str, embed: Optional[Any] = None) -> Any:
        """Send message to Discord channel."""
        ...

    @abstractmethod
    def get_guild_config(self, guild_id: str) -> "DiscordAdapterConfig":
        """Get configuration for a specific guild."""
        ...


# ============================================================================
# FUTURE ADAPTER PROTOCOLS
# ============================================================================


class SlackAdapterProtocol(BaseAdapterProtocol):
    """Protocol for Slack adapter (future)."""

    @abstractmethod
    async def handle_event(self, event: SerializedModel) -> None:
        """Handle Slack event."""
        ...


class WebSocketAdapterProtocol(BaseAdapterProtocol):
    """Protocol for WebSocket adapter (future)."""

    @abstractmethod
    async def handle_connection(self, websocket: Any) -> None:
        """Handle new WebSocket connection."""
        ...

    @abstractmethod
    async def broadcast_message(self, message: Any) -> None:
        """Broadcast message to all connected clients."""
        ...


class MatrixAdapterProtocol(BaseAdapterProtocol):
    """Protocol for Matrix protocol adapter (future)."""

    @abstractmethod
    async def handle_room_message(self, _: Any, event: Any) -> None:
        """Handle Matrix room message."""
        ...

    @abstractmethod
    async def join_room(self, _: str) -> None:
        """Join a Matrix room."""
        ...
