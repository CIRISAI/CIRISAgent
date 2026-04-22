"""Protocol definitions for the Reddit adapter service."""

from __future__ import annotations

from typing import Protocol

from ciris_engine.protocols.services import CommunicationService, ToolService

from .schemas import RedditCredentials


class RedditOAuthProtocol(Protocol):
    """Common contract for services that manage Reddit OAuth credentials."""

    async def update_credentials(self, credentials: RedditCredentials) -> None:
        """Update the credentials used for Reddit OAuth."""

    async def refresh_token(self, force: bool = False) -> bool:
        """Ensure an access token is available, optionally forcing a refresh."""


class RedditToolProtocol(RedditOAuthProtocol, ToolService, Protocol):
    """Tool service protocol for Reddit operations."""


class RedditCommunicationProtocol(RedditOAuthProtocol, CommunicationService, Protocol):
    """Communication service protocol for Reddit messaging."""


__all__ = [
    "RedditOAuthProtocol",
    "RedditToolProtocol",
    "RedditCommunicationProtocol",
]
