"""
CIRIS Accord Metrics Adapter — the reasoning-observability spine.

2.9.6+ (#866 LensCore fold): bootstrap-REQUIRED, always loaded. Capture is
constitutive (the agent's local self-witness ledger, like the audit trail);
the trace pipeline is owned by the ciris-lens-core substrate. CONSENT
governs SHARING, not capture, and is a CEG wire artifact
(consent:community_trust:v1) enforced by lens-core's gate at every seal —
a recant is a hard stop. No data leaves the occurrence without the grant.
"""

import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import Any, List, Optional

from ciris_engine.logic.adapters.base import Service
from ciris_engine.logic.registries.base import Priority
from ciris_engine.schemas.adapters import AdapterServiceRegistration
from ciris_engine.schemas.runtime.adapter_management import AdapterConfig, RuntimeAdapterStatus
from ciris_engine.schemas.runtime.enums import ServiceType
from ciris_engine.schemas.types import JSONDict

from .services import AccordMetricsService

logger = logging.getLogger(__name__)


def _get_metrics_env(name: str, default: str = "") -> str:
    """Get env var with backward compatibility for old COVENANT naming.

    Checks CIRIS_ACCORD_METRICS_{name} first, falls back to CIRIS_COVENANT_METRICS_{name}.
    This allows existing .env files to continue working after the rename.
    """
    new_key = f"CIRIS_ACCORD_METRICS_{name}"
    old_key = f"CIRIS_COVENANT_METRICS_{name}"

    value = os.environ.get(new_key)
    if value is not None:
        return value

    value = os.environ.get(old_key)
    if value is not None:
        logger.info(f"Using legacy env var {old_key} - please migrate to {new_key}")
        return value

    return default


class AccordMetricsAdapter(Service):
    """
    CIRIS Accord Metrics Adapter (post-fold, 2.9.6+).

    This adapter:
    1. Registers a WiseAuthority service to receive WBD events
       (registration is unconditional — consent gates sharing at the
       substrate seal, not registration)
    2. Provides the consent-state plumbing (set_consent → LensClient
       rebuild; the CEG grant/revocation artifacts are the actual consent)
    3. Hosts the AccordMetricsService that feeds reasoning events to the
       ciris-lens-core substrate (capture → seal → sign → persist)

    Bootstrap-REQUIRED: loaded with ciris_verify at every boot
    (runtime/bootstrap_helpers.py). Trace data persists locally at the
    self tier; nothing leaves the occurrence without the
    consent:community_trust:v1 grant.
    """

    def __init__(
        self,
        runtime: Any,
        context: Optional[Any] = None,
        **kwargs: Any,
    ) -> None:
        """Initialize Accord Metrics adapter.

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

        # Check consent state from config OR environment variables (for QA testing)
        # Uses backward-compatible helper that checks both ACCORD and legacy COVENANT env vars
        env_consent = _get_metrics_env("CONSENT", "").lower() == "true"
        env_timestamp = _get_metrics_env("CONSENT_TIMESTAMP") or None

        self._consent_given = adapter_config.get("consent_given", False) or env_consent
        self._consent_timestamp = adapter_config.get("consent_timestamp") or env_timestamp

        # =====================================================================
        # CONSENT STATE LOGGING - Make it OBVIOUS what's happening
        # =====================================================================
        logger.info("=" * 70)
        logger.info("📊 ACCORD METRICS ADAPTER INITIALIZING")
        logger.info(f"   Config consent_given: {adapter_config.get('consent_given', False)}")
        logger.info(f"   Env CIRIS_ACCORD_METRICS_CONSENT: {os.environ.get('CIRIS_ACCORD_METRICS_CONSENT', 'not set')}")
        logger.info(
            f"   Env CIRIS_ACCORD_METRICS_ENDPOINT: {os.environ.get('CIRIS_ACCORD_METRICS_ENDPOINT', 'not set')}"
        )

        if env_consent:
            logger.info("✅ CONSENT ENABLED via environment variable")
            # Update adapter_config so the service also gets consent
            adapter_config["consent_given"] = True
            adapter_config["consent_timestamp"] = env_timestamp or datetime.now(timezone.utc).isoformat()
            logger.info(f"   Updated config consent_given: True")
            logger.info(f"   Consent timestamp: {adapter_config['consent_timestamp']}")

        if not self._consent_given:
            logger.info("Consent not yet granted — capture runs; seals are consent_blocked at the substrate until the CEG grant exists")
            logger.warning("   Set CIRIS_ACCORD_METRICS_CONSENT=true or complete setup wizard")
        else:
            logger.info(f"✅ CONSENT GIVEN - traces WILL be captured and sent")

        logger.info("=" * 70)

        # Create the underlying service with config
        self.metrics_service = AccordMetricsService(config=adapter_config)

        # Set agent ID if available from runtime
        # Try agent_identity first (new pattern), then fall back to direct agent_id (legacy/mocks)
        if runtime and hasattr(runtime, "agent_identity") and runtime.agent_identity:
            self.metrics_service.set_agent_id(runtime.agent_identity.agent_id)
        elif runtime and hasattr(runtime, "agent_id") and runtime.agent_id:
            # Legacy fallback for mocks and lightweight runtimes
            self.metrics_service.set_agent_id(runtime.agent_id)
        elif context and hasattr(context, "agent_id") and context.agent_id:
            self.metrics_service.set_agent_id(context.agent_id)

        # Track adapter state
        self._running = False
        self._lifecycle_task: Optional[asyncio.Task[None]] = None
        self._started_at: Optional[datetime] = None

        logger.info(f"AccordMetricsAdapter initialized (consent={self._consent_given})")

    def get_services_to_register(self) -> List[AdapterServiceRegistration]:
        """Get services provided by this adapter.

        Returns:
            List of service registrations for WiseAuthority bus
        """
        logger.info("=" * 70)
        logger.info("📋 ACCORD METRICS - get_services_to_register() called")
        logger.info(f"   Current consent state: {self._consent_given}")

        # 2.9.6: registration is UNCONDITIONAL. The adapter is the agent's
        # observability spine (required like audit); consent never gated
        # whether the pipeline exists — it gates SHARING, and the only
        # consent enforcement point is the substrate's CEG gate
        # (consent:community_trust:v1, evaluated by lens-core at every
        # seal — a recant hard-stops the very next ACTION_RESULT).
        registrations = [
            AdapterServiceRegistration(
                service_type=ServiceType.WISE_AUTHORITY,
                provider=self.metrics_service,
                priority=Priority.LOW,  # Low priority - observational only
                capabilities=[
                    "send_deferral",  # Receive WBD events
                    "accord_metrics",
                ],
            )
        ]
        logger.info("✅ REGISTERED AccordMetricsService on WiseAuthority bus")
        logger.info("   Capabilities: send_deferral, accord_metrics")
        logger.info("   (consent gates sharing at the substrate seal, not registration)")

        logger.info("=" * 70)
        return registrations

    async def start(self) -> None:
        """Start the Accord Metrics adapter."""
        logger.info("=" * 70)
        logger.info("🚀 ACCORD METRICS ADAPTER STARTING")
        logger.info(f"   Consent: {self._consent_given}")
        logger.info("=" * 70)

        # Set agent ID now that identity should be initialized
        # (runtime.agent_identity is None during __init__ bootstrap)
        if self.runtime and hasattr(self.runtime, "agent_identity") and self.runtime.agent_identity:
            self.metrics_service.set_agent_id(self.runtime.agent_identity.agent_id)
            logger.info(f"   Agent ID set from identity: {self.runtime.agent_identity.agent_id}")
        elif self.runtime and hasattr(self.runtime, "agent_id") and self.runtime.agent_id:
            # Legacy fallback for mocks and lightweight runtimes
            self.metrics_service.set_agent_id(self.runtime.agent_id)
            logger.info(f"   Agent ID set from legacy runtime.agent_id: {self.runtime.agent_id}")
        else:
            logger.warning("   Agent identity not available - agent_id_hash will be 'unknown'")

        await self.metrics_service.start()

        self._running = True
        self._started_at = datetime.now(timezone.utc)

        if self._consent_given:
            logger.info("✅ AccordMetricsAdapter STARTED - collecting metrics")
        else:
            logger.info("AccordMetricsAdapter started pre-consent — capture active, sharing gated at the substrate seal")

    async def stop(self) -> None:
        """Stop the Accord Metrics adapter."""
        logger.info("Stopping AccordMetricsAdapter")
        self._running = False

        # Cancel lifecycle task if running
        if self._lifecycle_task and not self._lifecycle_task.done():
            self._lifecycle_task.cancel()
            try:
                await self._lifecycle_task
            except asyncio.CancelledError:
                pass

        await self.metrics_service.stop()

        logger.info("AccordMetricsAdapter stopped")

    async def run_lifecycle(self, agent_task: Any) -> None:
        """Run the adapter lifecycle.

        For the accord metrics adapter, we just wait for the agent task
        to complete since it passively receives events.

        Args:
            agent_task: The main agent task (signals shutdown when complete)
        """
        logger.info("AccordMetricsAdapter lifecycle started")
        try:
            await agent_task
        except asyncio.CancelledError:
            logger.info("AccordMetricsAdapter lifecycle cancelled")
        finally:
            await self.stop()

    def get_config(self) -> AdapterConfig:
        """Get adapter configuration.

        Returns:
            Current adapter configuration
        """
        metrics = self.metrics_service.get_metrics()

        return AdapterConfig(
            adapter_type="ciris_accord_metrics",
            enabled=self._running and self._consent_given,
            settings={
                "trace_level": metrics.get("trace_level", "generic"),
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
            adapter_id="ciris_accord_metrics",
            adapter_type="ciris_accord_metrics",
            is_running=self._running,
            loaded_at=self._started_at or datetime.now(timezone.utc),
            config_params=AdapterConfig(
                adapter_type="ciris_accord_metrics",
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

    def update_consent(self, consent_given: bool, request_lens_deletion: bool = False) -> None:
        """Update consent state.

        This is called by the setup wizard or DSAR self-service when consent is granted/revoked.

        When consent is revoked and request_lens_deletion is True, a deletion request
        is queued to be sent to CIRISLens on the next flush cycle.

        Args:
            consent_given: Whether user has consented
            request_lens_deletion: If True and revoking consent, queue a lens deletion request
        """
        self._consent_given = consent_given
        self._consent_timestamp = datetime.now(timezone.utc).isoformat()

        self.metrics_service.set_consent(consent_given, self._consent_timestamp)

        if consent_given:
            logger.info(f"Consent GRANTED for accord metrics collection " f"at {self._consent_timestamp}")
        else:
            logger.info(f"Consent REVOKED for accord metrics collection " f"at {self._consent_timestamp}")
            if request_lens_deletion:
                self.metrics_service.queue_lens_deletion_on_revoke()

    def is_consent_given(self) -> bool:
        """Check if consent has been given.

        Returns:
            True if user has explicitly consented
        """
        return bool(self._consent_given)


# Export as Adapter for load_adapter() compatibility
# This is the critical line that allows RuntimeAdapterManager to find the adapter
Adapter = AccordMetricsAdapter
