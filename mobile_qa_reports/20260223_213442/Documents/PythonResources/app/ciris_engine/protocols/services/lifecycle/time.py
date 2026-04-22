"""Time Service Protocol."""

from abc import abstractmethod
from datetime import datetime
from typing import Protocol

from ...runtime.base import ServiceProtocol


class TimeServiceProtocol(ServiceProtocol, Protocol):
    """Protocol for time service - provides consistent time operations."""

    @abstractmethod
    def now(self) -> datetime:
        """Get current time in UTC with timezone info."""
        ...

    @abstractmethod
    def now_iso(self) -> str:
        """Get current time as ISO string."""
        ...

    @abstractmethod
    def timestamp(self) -> float:
        """Get current Unix timestamp."""
        ...

    @abstractmethod
    def get_uptime(self) -> float:
        """Get service uptime in seconds."""
        ...
