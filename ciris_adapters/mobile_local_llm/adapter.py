"""
BaseAdapterProtocol-compliant wrapper for the mobile local LLM service.

The adapter owns the lifecycle of the on-device inference server and
registers the service with the CIRIS LLM bus. Its behaviour matches the
other LLM adapters (``mock_llm``, production ``llm_service``) so it plugs
into :class:`RuntimeAdapterManager` without special cases:

* ``start()`` probes device capability, spawns the inference server if the
  device is capable, and flips the service to healthy.
* ``run_lifecycle()`` runs a background health loop so a crashed server is
  detected quickly and the LLM bus routes to the hosted fallback.
* ``stop()`` terminates the inference server gracefully.
* ``get_status()`` exposes the tier, model variant, and server PID so the
  status endpoints can show whether local inference is in use.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, List, Optional

from ciris_engine.logic.adapters.base import Service
from ciris_engine.logic.registries.base import Priority
from ciris_engine.schemas.adapters import AdapterServiceRegistration
from ciris_engine.schemas.runtime.adapter_management import AdapterConfig, RuntimeAdapterStatus
from ciris_engine.schemas.runtime.enums import ServiceType

from .capability import probe_device_capability
from .config import MobileLocalLLMConfig, DeviceTier, load_config_from_env
from .service import MobileLocalLLMService

logger = logging.getLogger(__name__)


# Health loop cadence guard. The config exposes the nominal interval, but we
# never poll faster than this floor so we do not starve the inference server
# of CPU on weaker devices.
_MIN_HEALTH_INTERVAL_SECONDS = 5.0


class MobileLocalLLMAdapter(Service):
    """Adapter that runs a local Gemma 4 inference server on capable phones."""

    def __init__(self, runtime: Any, context: Optional[Any] = None, **kwargs: Any) -> None:
        super().__init__(config=kwargs.get("adapter_config"))
        self.runtime = runtime
        self.context = context

        # Allow callers to pass a fully built config (tests) or an env override.
        provided = kwargs.get("adapter_config")
        if isinstance(provided, MobileLocalLLMConfig):
            self._config = provided
        else:
            # Start from env then layer any dict-form overrides on top.
            self._config = load_config_from_env()
            if isinstance(provided, dict):
                self._config = self._config.model_copy(update=provided)

        self._llm_service = MobileLocalLLMService(self._config)
        self._capability = None  # populated during start()
        self._running = False
        self._lifecycle_task: Optional[asyncio.Task[None]] = None
        self._health_task: Optional[asyncio.Task[None]] = None

        logger.info(
            "MobileLocalLLMAdapter initialised (enabled=%s, variant=%s)",
            self._config.enabled,
            self._config.model_variant.value,
        )

    # ------------------------------------------------------------------
    # Service registration
    # ------------------------------------------------------------------

    def get_services_to_register(self) -> List[AdapterServiceRegistration]:
        """Register the local LLM with HIGH priority.

        HIGH (not CRITICAL) sits just below the mock provider so tests still
        work, but above the NORMAL cloud providers. On capable phones the
        bus will prefer on-device inference; when the adapter reports
        unhealthy (weak device, crashed server, etc.) the bus drops to the
        cloud provider automatically.
        """
        return [
            AdapterServiceRegistration(
                service_type=ServiceType.LLM,
                provider=self._llm_service,
                priority=Priority.HIGH,
                capabilities=[
                    "call_llm_structured",
                    "provider:mobile_local",
                    f"model:{self._config.model_variant.value}",
                ],
            )
        ]

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        logger.info("Starting MobileLocalLLMAdapter")
        # Probe once at adapter level so get_status() has something to show
        # even if the service layer short-circuits due to enabled=False.
        self._capability = probe_device_capability(self._config)
        logger.info("Device capability: %s", self._capability.summary())

        await self._llm_service.start()
        self._running = True

        # Only run the health loop on devices that actually started the
        # server. Weaker devices never flip to available, so the loop would
        # be pure noise there.
        if self._llm_service.available:
            self._health_task = asyncio.create_task(
                self._health_loop(), name="mobile-local-llm-health"
            )

        logger.info(
            "MobileLocalLLMAdapter started (available=%s, tier=%s)",
            self._llm_service.available,
            self._capability.tier.value,
        )

    async def stop(self) -> None:
        logger.info("Stopping MobileLocalLLMAdapter")
        self._running = False

        if self._health_task and not self._health_task.done():
            self._health_task.cancel()
            try:
                await self._health_task
            except asyncio.CancelledError:
                pass
        self._health_task = None

        if self._lifecycle_task and not self._lifecycle_task.done():
            self._lifecycle_task.cancel()
            try:
                await self._lifecycle_task
            except asyncio.CancelledError:
                pass
        self._lifecycle_task = None

        await self._llm_service.stop()
        logger.info("MobileLocalLLMAdapter stopped")

    async def run_lifecycle(self, agent_task: Any) -> None:
        """Block until the agent task signals shutdown.

        The actual health polling runs in :meth:`_health_loop`, which was
        started from :meth:`start`. We keep ``run_lifecycle`` minimal so the
        adapter matches the pattern used by mock_llm.
        """
        logger.info("MobileLocalLLMAdapter lifecycle started")
        try:
            await agent_task
        except asyncio.CancelledError:
            logger.info("MobileLocalLLMAdapter lifecycle cancelled")
        finally:
            await self.stop()

    # ------------------------------------------------------------------
    # Health loop
    # ------------------------------------------------------------------

    async def _health_loop(self) -> None:
        """Periodically probe the local server and flip availability.

        On three consecutive failed probes we ask the service to fully stop
        so that its ``is_healthy()`` returns False. The LLM bus will then
        route all traffic to the cloud fallback until the adapter is
        restarted — we intentionally do NOT attempt automatic restarts here
        because restart policy belongs at the ``RuntimeAdapterManager``
        layer, not inside a single adapter.
        """
        interval = max(_MIN_HEALTH_INTERVAL_SECONDS, self._config.health_interval_seconds)
        consecutive_failures = 0
        while self._running:
            try:
                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                break

            if not self._running:
                break
            try:
                healthy = await self._llm_service.is_healthy()
            except Exception as exc:  # pragma: no cover - defensive
                logger.exception("MobileLocalLLM health probe raised: %s", exc)
                healthy = False

            if healthy:
                if consecutive_failures:
                    logger.info("MobileLocalLLM: server recovered after %s failures", consecutive_failures)
                consecutive_failures = 0
                continue

            consecutive_failures += 1
            logger.warning(
                "MobileLocalLLM: health probe failed (consecutive=%s)", consecutive_failures
            )
            if consecutive_failures >= 3:
                logger.error(
                    "MobileLocalLLM: marking local provider permanently unavailable after "
                    "3 failed health probes; LLM bus will use hosted fallback."
                )
                try:
                    await self._llm_service.stop()
                except Exception:  # pragma: no cover - defensive
                    logger.exception("MobileLocalLLM: error during health-triggered stop")
                break

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    def get_config(self) -> AdapterConfig:
        tier = self._capability.tier.value if self._capability else DeviceTier.INCAPABLE.value
        return AdapterConfig(
            adapter_type="mobile_local_llm",
            enabled=self._running and self._llm_service.available,
            settings={
                "enabled": self._config.enabled,
                "variant": self._config.model_variant.value,
                "host": self._config.host,
                "port": self._config.port,
                "device_tier": tier,
                "available": self._llm_service.available,
            },
        )

    def get_status(self) -> RuntimeAdapterStatus:
        error: Optional[str] = None
        if self._running and self._capability and self._capability.is_stub:
            # iOS-stub is not an error per se — it is the documented
            # "platform supported, model not shipped yet" state. The wizard
            # uses this to surface a "coming soon" option. We still report
            # it here so the runtime status is accurate.
            error = "ios_stub: " + "; ".join(self._capability.reasons)
        elif self._running and self._capability and not self._capability.capable:
            error = "device_not_capable: " + "; ".join(self._capability.reasons)
        elif self._running and not self._llm_service.available:
            error = "local_inference_unavailable"
        return RuntimeAdapterStatus(
            adapter_id="mobile_local_llm",
            adapter_type="mobile_local_llm",
            is_running=self._running,
            loaded_at=None,
            error=error,
        )

    # Useful for QA / tests
    @property
    def llm_service(self) -> MobileLocalLLMService:
        return self._llm_service

    @property
    def config(self) -> MobileLocalLLMConfig:
        return self._config


# Export as Adapter for RuntimeAdapterManager.load_adapter() compatibility.
Adapter = MobileLocalLLMAdapter

__all__ = ["Adapter", "MobileLocalLLMAdapter"]
