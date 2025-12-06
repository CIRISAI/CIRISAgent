"""Type stubs for discord.py library."""

from typing import Any, List, Optional

class Client:
    """Discord client stub."""

    def __init__(self, *args: Any, **kwargs: Any) -> None: ...
    async def start(self, token: str) -> None: ...
    async def close(self) -> None: ...
    @property
    def user(self) -> Optional["User"]: ...
    @property
    def guilds(self) -> List["Guild"]: ...

class User:
    """Discord user stub."""

    id: int
    name: str
    discriminator: str
    avatar: Optional[str]
    bot: bool

class Guild:
    """Discord guild/server stub."""

    id: int
    name: str
    owner_id: int
    member_count: int

class Message:
    """Discord message stub."""

    id: int
    content: str
    author: User
    channel: "Channel"
    guild: Optional[Guild]

class Channel:
    """Discord channel stub."""

    id: int
    name: str
    type: int
    async def send(self, content: Optional[str] = None, **kwargs: Any) -> Message: ...

__all__ = ["Client", "User", "Guild", "Message", "Channel"]
