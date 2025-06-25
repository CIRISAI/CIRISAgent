"""
Adapter protocols for the CIRIS Trinity Architecture.

These protocols define contracts for platform adapters.
Adapters are the interfaces between CIRIS and external platforms.
"""
from typing import Callable, Optional
from abc import abstractmethod

from ciris_engine.protocols.runtime.base import BaseAdapterProtocol

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
    def get_openapi_spec(self) -> dict:
        """Get OpenAPI specification."""
        ...
    
    @abstractmethod
    def add_middleware(self, middleware: Callable) -> None:
        """Add middleware to the API."""
        ...
    
    @abstractmethod
    def get_route_metrics(self) -> Dict[str, Dict[str, int]]:
        """Get metrics for each route."""
        ...

class CLIAdapterProtocol(BaseAdapterProtocol):
    """Protocol for Command Line Interface adapter."""
    
    @abstractmethod
    def register_commands(self) -> None:
        """Register all CLI commands."""
        ...
    
    @abstractmethod
    async def handle_input(self, input_text: str) -> str:
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
    async def handle_reaction(self, reaction: Any, user: Any) -> None:
        """Handle reaction events."""
        ...
    
    @abstractmethod
    async def send_message(self, channel_id: str, content: str, embed: Optional[Any] = None) -> Any:
        """Send message to Discord channel."""
        ...
    
    @abstractmethod
    def get_guild_config(self, guild_id: str) -> dict:
        """Get configuration for a specific guild."""
        ...
    
    @abstractmethod
    async def handle_slash_command(self, interaction: Any) -> None:
        """Handle slash command interaction."""
        ...

# ============================================================================
# FUTURE ADAPTER PROTOCOLS
# ============================================================================

class SlackAdapterProtocol(BaseAdapterProtocol):
    """Protocol for Slack adapter (future)."""
    
    @abstractmethod
    async def handle_event(self, event: dict) -> None:
        """Handle Slack event."""
        ...
    
    @abstractmethod
    async def handle_slash_command(self, command: dict) -> dict:
        """Handle Slack slash command."""
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
    async def handle_room_message(self, room: Any, event: Any) -> None:
        """Handle Matrix room message."""
        ...
    
    @abstractmethod
    async def join_room(self, room_id: str) -> None:
        """Join a Matrix room."""
        ...