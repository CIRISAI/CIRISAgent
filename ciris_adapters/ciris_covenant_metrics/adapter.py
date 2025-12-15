"""
CIRIS Covenant Metrics Adapter.

This adapter provides covenant compliance metrics collection for CIRISLens,
reporting WBD (Wisdom-Based Deferral) events and PDMA decision events.

CRITICAL: This adapter requires EXPLICIT opt-in via the setup wizard.
No data is collected or sent without user consent.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, List, Optional

from ciris_engine.logic.adapters.base import Service
from ciris_engine.logic.registries.base import Priority
from ciris_engine.schemas.adapters import AdapterServiceRegistration
from ciris_engine.schemas.runtime.adapter_management import AdapterConfig, RuntimeAdapterStatus
from ciris_engine.schemas.runtime.enums import ServiceType
from ciris_engine.schemas.types import JSONDict

from .services import CovenantMetricsService

logger = logging.getLogger(__name__)


class CovenantMetricsAdapter(Service):
    """
    CIRIS Covenant Metrics Adapter.

    This adapter:
    1. Registers a WiseAuthority service to receive WBD events
    2. Provides consent management for data collection
    3. Batches and sends events to CIRISLens API

    IMPORTANT: This adapter is NOT auto-loaded. It must be:
    1. Explicitly added via --adapter ciris_covenant_metrics
    2. Configured via the setup wizard with EXPLICIT consent

    No data is sent until the user completes the consent flow.
    """

    def __init__(
        self,
        runtime: Any,
        context: Optional[Any] = None,
        **kwargs: Any,
    ) -> None:
        """Initialize Covenant Metrics adapter.

        Args:
            runtime: CIRIS runtime instance
            context: Optional runtime context
            **kwargs: Additional configuration (may include adapter_config)
        """
        super().__init__(config=kwargs.get("adapter_config"))
        self.runtime = runtime
        self.context = context

        # Extract config from kwargs
        adapter_config = kwargs.get("adapter_config", {})

        # Check consent state from config
        self._consent_given = adapter_config.get("consent_given", False)
        self._consent_timestamp = adapter_config.get("consent_timestamp")

        if not self._consent_given:
            logger.warning(
                "CovenantMetricsAdapter initialized WITHOUT consent - "
                "complete setup wizard to enable data collection"
            )

        # Create the underlying service with config
        self.metrics_service = CovenantMetricsService(config=adapter_config)

        # Set agent ID if available from runtime
        if runtime and hasattr(runtime, "agent_id"):
            self.metrics_service.set_agent_id(runtime.agent_id)
        elif context and hasattr(context, "agent_id"):
            self.metrics_service.set_agent_id(context.agent_id)

        # Track adapter state
        self._running = False
        self._lifecycle_task: Optional[asyncio.Task[None]] = None
        self._started_at: Optional[datetime] = None

        logger.info(f"CovenantMetricsAdapter initialized (consent={self._consent_given})")

    def get_services_to_register(self) -> List[AdapterServiceRegistration]:
        """Get services provided by this adapter.

        Returns:
            List of service registrations for WiseAuthority bus
        """
        registrations = []

        # Only register if consent is given
        # This prevents the service from receiving events before consent
        if self._consent_given:
            registrations.append(
                AdapterServiceRegistration(
                    service_type=ServiceType.WISE_AUTHORITY,
                    provider=self.metrics_service,
                    priority=Priority.LOW,  # Low priority - observational only
                    capabilities=[
                        "send_deferral",  # Receive WBD events
                        "covenant_metrics",
                    ],
                )
            )
            logger.info("Registered CovenantMetricsService with send_deferral capability")
        else:
            logger.warning(
                "CovenantMetricsService NOT registered - consent required. " "Complete setup wizard to enable."
            )

        return registrations

    async def start(self) -> None:
        """Start the Covenant Metrics adapter."""
        logger.info("Starting CovenantMetricsAdapter")

        await self.metrics_service.start()

        self._running = True
        self._started_at = datetime.now(timezone.utc)

        if self._consent_given:
            logger.info("CovenantMetricsAdapter started with consent - collecting metrics")
        else:
            logger.info(
                "CovenantMetricsAdapter started WITHOUT consent - " "no metrics will be collected until user consents"
            )

    async def stop(self) -> None:
        """Stop the Covenant Metrics adapter."""
        logger.info("Stopping CovenantMetricsAdapter")
        self._running = False

        # Cancel lifecycle task if running
        if self._lifecycle_task and not self._lifecycle_task.done():
            self._lifecycle_task.cancel()
            try:
                await self._lifecycle_task
            except asyncio.CancelledError:
                pass

        await self.metrics_service.stop()

        logger.info("CovenantMetricsAdapter stopped")

    async def run_lifecycle(self, agent_task: Any) -> None:
        """Run the adapter lifecycle.

        For the covenant metrics adapter, we just wait for the agent task
        to complete since it passively receives events.

        Args:
            agent_task: The main agent task (signals shutdown when complete)
        """
        logger.info("CovenantMetricsAdapter lifecycle started")
        try:
            await agent_task
        except asyncio.CancelledError:
            logger.info("CovenantMetricsAdapter lifecycle cancelled")
        finally:
            await self.stop()

    def get_config(self) -> AdapterConfig:
        """Get adapter configuration.

        Returns:
            Current adapter configuration
        """
        metrics = self.metrics_service.get_metrics()

        return AdapterConfig(
            adapter_type="ciris_covenant_metrics",
            enabled=self._running and self._consent_given,
            settings={
                "consent_given": self._consent_given,
                "consent_timestamp": self._consent_timestamp,
                "events_received": metrics.get("events_received", 0),
                "events_sent": metrics.get("events_sent", 0),
                "events_failed": metrics.get("events_failed", 0),
                "events_queued": metrics.get("events_queued", 0),
            },
        )

    def get_status(self) -> RuntimeAdapterStatus:
        """Get adapter status.

        Returns:
            Current adapter runtime status
        """
        metrics = self.metrics_service.get_metrics()

        return RuntimeAdapterStatus(
            adapter_id="ciris_covenant_metrics",
            adapter_type="ciris_covenant_metrics",
            is_running=self._running,
            loaded_at=self._started_at or datetime.now(timezone.utc),
            config_params=AdapterConfig(
                adapter_type="ciris_covenant_metrics",
                enabled=self._running and self._consent_given,
                settings={
                    "consent_given": self._consent_given,
                    "consent_timestamp": self._consent_timestamp,
                    "events_received": metrics.get("events_received", 0),
                    "events_sent": metrics.get("events_sent", 0),
                },
            ),
        )

    # =========================================================================
    # Consent Management API
    # =========================================================================

    def update_consent(self, consent_given: bool) -> None:
        """Update consent state.

        This is called by the setup wizard when consent is granted/revoked.

        Args:
            consent_given: Whether user has consented
        """
        self._consent_given = consent_given
        self._consent_timestamp = datetime.now(timezone.utc).isoformat()

        self.metrics_service.set_consent(consent_given, self._consent_timestamp)

        if consent_given:
            logger.info(f"Consent GRANTED for covenant metrics collection " f"at {self._consent_timestamp}")
        else:
            logger.info(f"Consent REVOKED for covenant metrics collection " f"at {self._consent_timestamp}")

    def is_consent_given(self) -> bool:
        """Check if consent has been given.

        Returns:
            True if user has explicitly consented
        """
        return bool(self._consent_given)


# Export as Adapter for load_adapter() compatibility
# This is the critical line that allows RuntimeAdapterManager to find the adapter
Adapter = CovenantMetricsAdapter
