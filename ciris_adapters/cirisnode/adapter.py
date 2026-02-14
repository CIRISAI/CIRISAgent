"""
CIRISNode Adapter — deferral routing and trace forwarding to CIRISNode.

Registers as WISE_AUTHORITY on the WiseBus. No tools, no consent gating
(CIRISNode is the agent's own oversight node).
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, List, Optional

from ciris_engine.logic.adapters.base import Service
from ciris_engine.logic.registries.base import Priority
from ciris_engine.schemas.adapters import AdapterServiceRegistration
from ciris_engine.schemas.runtime.enums import ServiceType

from .services import CIRISNodeService

logger = logging.getLogger(__name__)


class CIRISNodeAdapter(Service):
    """CIRISNode oversight adapter.

    Registers CIRISNodeService as WISE_AUTHORITY for:
    - Deferral routing (send_deferral -> WBD submit)
    - Trace forwarding (reasoning events -> covenant/events endpoint)
    """

    def __init__(
        self,
        runtime: Any = None,
        context: Optional[Any] = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(config=kwargs.get("adapter_config"))
        self.runtime = runtime
        self.context = context

        adapter_config = kwargs.get("adapter_config", {})

        # Create the service
        self.service = CIRISNodeService(config=adapter_config)

        # Set agent ID from runtime identity or kwargs
        agent_id = kwargs.get("agent_id")
        if runtime and hasattr(runtime, "agent_identity") and runtime.agent_identity:
            self.service.set_agent_id(runtime.agent_identity.agent_id)
        elif runtime and hasattr(runtime, "agent_id") and runtime.agent_id:
            self.service.set_agent_id(runtime.agent_id)
        elif agent_id:
            self.service.set_agent_id(agent_id)

        self._running = False
        self._started_at: Optional[datetime] = None

        logger.info("CIRISNodeAdapter initialized")

    def get_services_to_register(self) -> List[AdapterServiceRegistration]:
        """Register CIRISNodeService as WISE_AUTHORITY."""
        return [
            AdapterServiceRegistration(
                service_type=ServiceType.WISE_AUTHORITY,
                provider=self.service,
                priority=Priority.NORMAL,
                capabilities=["send_deferral", "cirisnode_traces"],
            )
        ]

    async def start(self) -> None:
        """Start the adapter and its service."""
        # Re-set agent ID now that identity should be fully initialized
        if self.runtime and hasattr(self.runtime, "agent_identity") and self.runtime.agent_identity:
            self.service.set_agent_id(self.runtime.agent_identity.agent_id)
        elif self.runtime and hasattr(self.runtime, "agent_id") and self.runtime.agent_id:
            self.service.set_agent_id(self.runtime.agent_id)

        await self.service.start()
        self._running = True
        self._started_at = datetime.now(timezone.utc)
        logger.info("CIRISNodeAdapter started")

    async def run_lifecycle(self, agent_task: Any) -> None:
        """Run the adapter lifecycle — wait for agent task to complete."""
        logger.info("CIRISNodeAdapter lifecycle started")
        try:
            await agent_task
        except asyncio.CancelledError:
            logger.info("CIRISNodeAdapter lifecycle cancelled")
        finally:
            await self.stop()

    async def stop(self) -> None:
        """Stop the adapter and its service."""
        self._running = False
        await self.service.stop()
        logger.info("CIRISNodeAdapter stopped")


# load_adapter() compatibility
Adapter = CIRISNodeAdapter
