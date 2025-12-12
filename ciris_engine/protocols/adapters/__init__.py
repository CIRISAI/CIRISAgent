"""
Adapter protocols for the CIRIS platform.

This package contains protocol definitions for different types of adapters:
- base: Platform-specific adapter protocols (API, CLI, Discord, etc.)
- message: Message protocol for cross-adapter communication
- configurable: Protocol for interactive adapter configuration
"""

from ciris_engine.protocols.adapters.base import (
    APIAdapterProtocol,
    CLIAdapterProtocol,
    DiscordAdapterProtocol,
    MatrixAdapterProtocol,
    SlackAdapterProtocol,
    WebSocketAdapterProtocol,
)
from ciris_engine.protocols.adapters.configurable import ConfigurableAdapterProtocol
from ciris_engine.protocols.adapters.message import Message, MessageDict, MessageProtocol

__all__ = [
    # Base adapter protocols
    "APIAdapterProtocol",
    "CLIAdapterProtocol",
    "DiscordAdapterProtocol",
    "MatrixAdapterProtocol",
    "SlackAdapterProtocol",
    "WebSocketAdapterProtocol",
    # Configurable adapter protocol
    "ConfigurableAdapterProtocol",
    # Message protocols
    "Message",
    "MessageDict",
    "MessageProtocol",
]
