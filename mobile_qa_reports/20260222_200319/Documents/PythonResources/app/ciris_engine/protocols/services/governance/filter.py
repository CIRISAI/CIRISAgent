"""Adaptive Filter Service Protocol."""

from abc import abstractmethod
from typing import Any, Protocol

from ciris_engine.schemas.services.filters_core import FilterHealth, FilterResult, FilterTrigger

from ...runtime.base import ServiceProtocol


class AdaptiveFilterServiceProtocol(ServiceProtocol, Protocol):
    """Protocol for adaptive filter service."""

    @abstractmethod
    async def filter_message(self, message: Any, adapter_type: str, is_llm_response: bool = False) -> FilterResult:
        """Apply filters to determine message priority and processing.

        Args:
            message: The message object to filter
            adapter_type: The adapter type (discord, cli, api)
            is_llm_response: Whether this is an LLM-generated response

        Returns:
            FilterResult with priority, triggered filters, and processing decision
        """
        ...

    @abstractmethod
    async def get_health(self) -> FilterHealth:
        """Get filter service health and statistics."""
        ...

    @abstractmethod
    async def add_filter_trigger(self, trigger: FilterTrigger, trigger_list: str = "review") -> bool:
        """Add a new filter trigger to the configuration.

        Args:
            trigger: The filter trigger to add
            trigger_list: Which list to add to ("attention", "review", or "llm")

        Returns:
            True if trigger was added successfully
        """
        ...

    @abstractmethod
    async def remove_filter_trigger(self, trigger_id: str) -> bool:
        """Remove a filter trigger from the configuration.

        Args:
            trigger_id: The ID of the trigger to remove

        Returns:
            True if trigger was removed successfully
        """
        ...
