"""
Minimal protocol for messages across different adapters.
"""

from typing import Optional, Protocol, Union, runtime_checkable


@runtime_checkable
class MessageProtocol(Protocol):
    """
    Minimal protocol that all adapter messages must satisfy.

    Based on actual usage in AdaptiveFilterService.
    """

    @property
    def content(self) -> Optional[str]:
        """The text content of the message"""
        ...

    @property
    def user_id(self) -> Optional[str]:
        """ID of the user who sent the message"""
        ...

    @property
    def author_id(self) -> Optional[str]:
        """Alternative field for user ID (Discord uses this)"""
        ...

    @property
    def channel_id(self) -> Optional[str]:
        """ID of the channel where message was sent"""
        ...

    @property
    def message_id(self) -> Optional[str]:
        """Unique ID of the message"""
        ...

    @property
    def id(self) -> Optional[str]:
        """Alternative field for message ID"""
        ...

    @property
    def is_dm(self) -> Optional[bool]:
        """Whether this is a direct message"""
        ...


class MessageDict(dict):
    """
    Simple dict wrapper that implements MessageProtocol.

    This allows plain dicts to be used as messages while
    still providing type safety.
    """

    @property
    def content(self) -> Optional[str]:
        return self.get("content")

    @property
    def user_id(self) -> Optional[str]:
        return self.get("user_id")

    @property
    def author_id(self) -> Optional[str]:
        return self.get("author_id")

    @property
    def channel_id(self) -> Optional[str]:
        return self.get("channel_id")

    @property
    def message_id(self) -> Optional[str]:
        return self.get("message_id")

    @property
    def id(self) -> Optional[str]:
        return self.get("id")

    @property
    def is_dm(self) -> Optional[bool]:
        return self.get("is_dm")


# Type alias for messages
Message = Union[MessageProtocol, dict]
