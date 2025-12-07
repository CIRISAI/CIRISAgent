"""Database Maintenance Service Protocol.

Handles periodic database cleanup and archival operations.
"""

from abc import abstractmethod
from typing import Optional, Protocol

from ...runtime.base import ServiceProtocol
from ..lifecycle.time import TimeServiceProtocol


class DatabaseMaintenanceServiceProtocol(ServiceProtocol, Protocol):
    """Protocol for database maintenance service."""

    @abstractmethod
    async def perform_startup_cleanup(self, time_service: Optional[TimeServiceProtocol] = None) -> None:
        """
        Performs database cleanup at startup:
        1. Removes orphaned active tasks and thoughts.
        2. Archives tasks and thoughts older than the configured threshold.
        3. Cleans up thoughts with invalid context.
        Logs actions taken.
        """
        ...
