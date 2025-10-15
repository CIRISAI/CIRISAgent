import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ciris_engine.logic import persistence
from ciris_engine.logic.services.lifecycle.time import TimeService
from ciris_engine.protocols.services import WiseAuthorityService
from ciris_engine.schemas.runtime.enums import ServiceType
from ciris_engine.schemas.services.authority_core import DeferralRequest
from ciris_engine.schemas.services.context import GuidanceContext
from ciris_engine.schemas.services.core import ServiceCapabilities, ServiceStatus
from ciris_engine.schemas.telemetry.core import ServiceCorrelation, ServiceCorrelationStatus
from ciris_engine.schemas.types import JSONDict

logger = logging.getLogger(__name__)


class CLIWiseAuthorityService(WiseAuthorityService):
    """CLI-based WA service that prompts user for guidance"""

    def __init__(self, time_service: Optional[TimeService] = None) -> None:
        super().__init__()
        self.time_service = time_service or TimeService()
        self.deferral_log: List[JSONDict] = []

    async def start(self) -> None:
        """Start the CLI wise authority service."""
        # Don't call super() on abstract method
        pass

    async def stop(self) -> None:
        """Stop the CLI wise authority service."""
        # Don't call super() on abstract method
        pass

    async def fetch_guidance(self, context: GuidanceContext) -> Optional[str]:
        """Prompt user for guidance on deferred decision"""
        print("\n[WA GUIDANCE REQUEST]")
        print(f"Question: {context.question}")
        print(f"Task ID: {context.task_id}")
        if context.ethical_considerations:
            print(f"Ethical considerations: {', '.join(context.ethical_considerations)}")
        print("Please provide guidance (or 'skip' to defer):")
        try:
            guidance = await asyncio.to_thread(input, ">>> ")
            if guidance.lower() == "skip":
                return None
            return guidance
        except Exception as e:
            logger.error(f"Failed to get CLI guidance: {e}")
            return None

    async def send_deferral(self, deferral: DeferralRequest) -> str:
        """Log deferral to CLI output with rich context"""
        from typing import cast

        deferral_id = str(uuid.uuid4())
        deferral_entry: JSONDict = {
            "deferral_id": deferral_id,
            "thought_id": deferral.thought_id,
            "task_id": deferral.task_id,
            "reason": deferral.reason,
            "defer_until": deferral.defer_until.isoformat() if deferral.defer_until else None,
            "timestamp": self.time_service.now().timestamp(),
            "context": deferral.context,
        }

        self.deferral_log.append(deferral_entry)

        # Enhanced CLI deferral output
        print(f"\n{'='*60}")
        print("[CIRIS DEFERRAL REPORT]")
        print(f"Deferral ID: {deferral_id}")
        print(f"Thought ID: {deferral.thought_id}")
        print(f"Task ID: {deferral.task_id}")
        print(f"Reason: {deferral.reason}")
        print(f"Timestamp: {self.time_service.now().isoformat()}Z")

        if deferral.defer_until:
            print(f"Defer until: {deferral.defer_until.isoformat()}")

        if deferral.context:
            if "task_description" in deferral.context:
                print(f"Task: {deferral.context['task_description']}")
            if "attempted_action" in deferral.context:
                print(f"Attempted Action: {deferral.context['attempted_action']}")
            if "max_rounds_reached" in deferral.context and deferral.context["max_rounds_reached"] == "True":
                print("Note: Maximum processing rounds reached")

        print(f"{'='*60}")

        now = datetime.now(timezone.utc)
        corr = ServiceCorrelation(
            correlation_id=deferral_id,
            service_type="cli",
            handler_name="CLIWiseAuthorityService",
            action_type="send_deferral",
            created_at=now,
            updated_at=now,
            timestamp=now,
            status=ServiceCorrelationStatus.COMPLETED,
        )
        persistence.add_correlation(corr)
        return deferral_id

    async def is_healthy(self) -> bool:
        """Check if the service is healthy."""
        return True

    def get_service_type(self) -> ServiceType:
        """Get the type of this service."""
        return ServiceType.ADAPTER

    def get_capabilities(self) -> ServiceCapabilities:
        """Get service capabilities."""
        return ServiceCapabilities(
            service_name="CLIWiseAuthorityService",
            actions=["fetch_guidance", "defer_decision"],
            version="1.0.0",
            dependencies=[],
            resource_limits={},
        )

    def get_status(self) -> ServiceStatus:
        """Get current service status."""
        return ServiceStatus(
            service_name="CLIWiseAuthorityService",
            service_type="adapter",
            is_healthy=True,
            uptime_seconds=0.0,
            metrics={"deferrals_logged": len(self.deferral_log)},
        )
