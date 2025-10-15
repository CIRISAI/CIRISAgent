"""
Base adapter class with common correlation and message handling functionality.
"""

import logging
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from ciris_engine.logic.adapters.base import Service
from ciris_engine.protocols.services.lifecycle.time import TimeServiceProtocol
from ciris_engine.schemas.runtime.system_context import ChannelContext
from ciris_engine.schemas.types import JSONDict

if TYPE_CHECKING:
    from ciris_engine.schemas.adapters.runtime_context import AdapterStartupContext

logger = logging.getLogger(__name__)


class BaseAdapter(Service):
    """
    Base adapter with common correlation functionality.

    Provides:
    - Correlation creation for speak/observe actions
    - Message history fetching from correlations
    - Common telemetry patterns
    """

    def __init__(
        self,
        adapter_type: str,
        runtime: Any,
        config: Optional[JSONDict] = None,
        context: Optional["AdapterStartupContext"] = None,
    ) -> None:
        """
        Initialize base adapter.

        Args:
            adapter_type: Type of adapter (discord, api, cli, etc)
            runtime: Runtime instance (for backward compatibility)
            config: Legacy config dict (for backward compatibility)
            context: New AdapterStartupContext with all startup information
        """
        # Initialize parent class with config (same regardless of context)
        super().__init__(config)

        self.adapter_type = adapter_type
        self.runtime = runtime
        self.context = context
        self._time_service: Optional[TimeServiceProtocol] = None

        # If context provided, extract services
        if context:
            self._time_service = getattr(context, "time_service", None)

    def _get_time_service(self) -> Optional[TimeServiceProtocol]:
        """Get time service from runtime."""
        if self._time_service is None and self.runtime:
            self._time_service = getattr(self.runtime, "time_service", None)
        return self._time_service

    def get_channel_list(self) -> List[ChannelContext]:
        """
        Get list of available channels for this adapter.

        Returns:
            List of ChannelContext objects containing channel information.

        This base implementation returns empty list.
        Subclasses should override to provide actual channels.
        """
        return []
