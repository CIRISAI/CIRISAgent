"""
LLM service backed by a local on-device inference server.

This service implements :class:`LLMServiceProtocol` so that the CIRIS
``LLMBus`` can route structured inference calls to it just like any other
provider. It talks to an OpenAI-compatible HTTP server that the
:class:`InferenceServerManager` either spawns or attaches to. When the
device is not capable enough (per the Gemma 4 guidance) the service stays
healthy=False so the bus falls back to a hosted LLM provider.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional, Tuple, Type

from pydantic import BaseModel

from ciris_engine.logic.services.base_service import BaseService
from ciris_engine.protocols.services import LLMService as LLMServiceProtocol
from ciris_engine.protocols.services.runtime.llm import MessageDict
from ciris_engine.schemas.runtime.enums import ServiceType
from ciris_engine.schemas.runtime.resources import ResourceUsage
from ciris_engine.schemas.services.core import ServiceCapabilities, ServiceStatus

from .capability import DeviceCapabilityReport, probe_device_capability
from .config import MobileLocalLLMConfig, DeviceTier, ModelVariant
from .inference_server import InferenceServerError, InferenceServerManager

logger = logging.getLogger(__name__)


class MobileLocalLLMService(BaseService, LLMServiceProtocol):
    """Structured LLM provider backed by a local on-device server.

    Why subclass :class:`BaseService`? We get consistent metrics, health
    bookkeeping, and ``get_status()`` implementation for free, matching the
    production LLM service and the mock LLM service.
    """

    def __init__(
        self,
        config: MobileLocalLLMConfig,
        *,
        server_manager: Optional[InferenceServerManager] = None,
        capability_report: Optional[DeviceCapabilityReport] = None,
    ) -> None:
        super().__init__(service_name="MobileLocalLLMService", version="1.0.0")
        self._config = config
        self._server = server_manager or InferenceServerManager(config)
        self._capability: Optional[DeviceCapabilityReport] = capability_report
        self._available = False  # flips to True once server is up and variant is supported
        self._started_at: Optional[float] = None

        # Rollup metrics (reported via get_metrics()).
        self._total_requests = 0
        self._total_errors = 0
        self._total_input_tokens = 0
        self._total_output_tokens = 0

    # ------------------------------------------------------------------
    # BaseService wiring
    # ------------------------------------------------------------------

    def get_service_type(self) -> ServiceType:
        return ServiceType.LLM

    def _get_actions(self) -> List[str]:
        return ["call_llm_structured"]

    def _check_dependencies(self) -> bool:
        # The only hard dependency is the inference server process; everything
        # else is probed lazily during start().
        return True

    def _collect_custom_metrics(self) -> Dict[str, float]:
        return {
            "total_requests": float(self._total_requests),
            "total_errors": float(self._total_errors),
            "total_input_tokens": float(self._total_input_tokens),
            "total_output_tokens": float(self._total_output_tokens),
            "available": 1.0 if self._available else 0.0,
        }

    # ------------------------------------------------------------------
    # Capability / configuration
    # ------------------------------------------------------------------

    @property
    def capability_report(self) -> Optional[DeviceCapabilityReport]:
        return self._capability

    @property
    def config(self) -> MobileLocalLLMConfig:
        return self._config

    @property
    def available(self) -> bool:
        """True when the local server is running and handling requests."""
        return self._available

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Probe device capability, start the server, and become available.

        This never raises on capability failure — it just stays unavailable.
        That keeps the adapter safe to load on every device: weak phones
        silently fall back to the hosted LLM bus provider.
        """
        await super().start()
        self._started_at = time.time()

        if not self._config.enabled:
            logger.info("MobileLocalLLM: adapter disabled by config; staying unavailable")
            return

        if self._capability is None:
            self._capability = probe_device_capability(self._config)

        logger.info("MobileLocalLLM capability probe: %s", self._capability.summary())
        for reason in self._capability.reasons:
            logger.info("MobileLocalLLM capability reason: %s", reason)

        if not self._capability.capable:
            logger.warning(
                "MobileLocalLLM: device not capable of local Gemma 4 inference; "
                "the LLM bus will use hosted providers instead."
            )
            return

        if not self._capability.can_run(self._config.model_variant):
            logger.warning(
                "MobileLocalLLM: device tier %s cannot safely run %s; staying unavailable",
                self._capability.tier.value,
                self._config.model_variant.value,
            )
            return

        try:
            await self._server.start()
        except InferenceServerError as exc:
            logger.error("MobileLocalLLM: failed to start local inference server: %s", exc)
            self._available = False
            return
        except Exception as exc:  # pragma: no cover - defensive
            logger.exception("MobileLocalLLM: unexpected error starting server: %s", exc)
            self._available = False
            return

        self._available = True
        logger.info(
            "MobileLocalLLM ready: variant=%s tier=%s endpoint=%s",
            self._config.model_variant.value,
            self._capability.tier.value,
            self._config.base_url(),
        )

    async def stop(self) -> None:
        """Tear down the local server and mark ourselves unavailable."""
        self._available = False
        try:
            await self._server.stop()
        except Exception as exc:  # pragma: no cover - defensive
            logger.exception("MobileLocalLLM: error stopping inference server: %s", exc)
        await super().stop()

    # ------------------------------------------------------------------
    # Health / status
    # ------------------------------------------------------------------

    async def is_healthy(self) -> bool:
        """Healthy only when we are available AND the server responds."""
        if not self._available:
            return False
        try:
            ok = await self._server.health_check()
        except Exception:  # pragma: no cover - defensive
            ok = False
        if not ok:
            # Health probe failed — mark unavailable so the LLM bus routes away
            # from us until the adapter's lifecycle loop restarts the server.
            self._available = False
        return ok

    def get_capabilities(self) -> ServiceCapabilities:
        return ServiceCapabilities(
            service_name="MobileLocalLLMService",
            actions=["call_llm_structured"],
            version="1.0.0",
        )

    def get_status(self) -> ServiceStatus:
        uptime = time.time() - self._started_at if self._started_at else 0.0
        return ServiceStatus(
            service_name="MobileLocalLLMService",
            service_type="llm",
            is_healthy=self._available,
            uptime_seconds=uptime,
        )

    async def get_metrics(self) -> Dict[str, float]:
        """v1.4.3-compliant LLM metrics."""
        uptime = time.time() - self._started_at if self._started_at else 0.0
        total_tokens = self._total_input_tokens + self._total_output_tokens
        return {
            "uptime_seconds": uptime,
            "request_count": float(self._total_requests),
            "error_count": float(self._total_errors),
            "error_rate": self._total_errors / max(1, self._total_requests),
            "llm_requests_total": float(self._total_requests),
            "llm_tokens_input": float(self._total_input_tokens),
            "llm_tokens_output": float(self._total_output_tokens),
            "llm_tokens_total": float(total_tokens),
            # Local inference has no cloud cost; carbon/energy are left to
            # the on-device telemetry collector which knows the actual SoC.
            "llm_cost_cents": 0.0,
            "llm_errors_total": float(self._total_errors),
            "llm_uptime_seconds": uptime,
            "local_inference_available": 1.0 if self._available else 0.0,
        }

    # ------------------------------------------------------------------
    # LLM protocol
    # ------------------------------------------------------------------

    async def call_llm_structured(
        self,
        messages: List[MessageDict],
        response_model: Type[BaseModel],
        max_tokens: int = 1024,
        temperature: float = 0.0,
        thought_id: Optional[str] = None,
        task_id: Optional[str] = None,
    ) -> Tuple[BaseModel, ResourceUsage]:
        """Run a structured LLM call against the on-device server.

        Uses ``instructor`` + an OpenAI-compatible ``AsyncOpenAI`` client so
        that the rest of CIRIS does not have to care where the model lives.
        """
        if not self._available:
            raise RuntimeError(
                "MobileLocalLLMService is not available; LLM bus should route to the next provider"
            )

        self._total_requests += 1
        try:
            parsed = await self._dispatch_structured(
                messages=messages,
                response_model=response_model,
                max_tokens=max_tokens,
                temperature=temperature,
            )
        except Exception:
            self._total_errors += 1
            # Any inference failure means the server is suspect; drop to
            # unavailable and let the bus retry against the next provider.
            self._available = False
            raise

        # Cheap token estimate for resource accounting. Real servers return
        # usage details but we do not require them — the LLM bus only needs
        # token counts for budgeting / telemetry.
        input_tokens = _estimate_input_tokens(messages)
        output_tokens = max(1, max_tokens // 4)
        self._total_input_tokens += input_tokens
        self._total_output_tokens += output_tokens

        usage = ResourceUsage(
            tokens_used=input_tokens + output_tokens,
            tokens_input=input_tokens,
            tokens_output=output_tokens,
            cost_cents=0.0,  # local inference is free at the billing layer
            energy_kwh=_estimate_energy_kwh(input_tokens + output_tokens),
            carbon_grams=_estimate_carbon_grams(input_tokens + output_tokens),
            model_used=f"{self._config.model_variant.value} (mobile-local)",
        )
        return parsed, usage

    async def _dispatch_structured(
        self,
        *,
        messages: List[MessageDict],
        response_model: Type[BaseModel],
        max_tokens: int,
        temperature: float,
    ) -> BaseModel:
        """Actually call the on-device OpenAI-compatible server.

        We import ``openai`` and ``instructor`` lazily so that devices that
        never load this adapter do not pay the import cost.
        """
        try:
            import instructor  # type: ignore[import-not-found]
            from openai import AsyncOpenAI  # type: ignore[import-not-found]
        except ImportError as exc:  # pragma: no cover - dependency guard
            raise RuntimeError(
                "MobileLocalLLMService requires the 'openai' and 'instructor' packages"
            ) from exc

        client = AsyncOpenAI(
            base_url=self._config.base_url(),
            api_key="local",  # loopback server ignores the token
            timeout=self._config.request_timeout_seconds,
        )
        patched = instructor.patch(client)

        response = await patched.chat.completions.create(
            model=self._config.model_variant.value,
            messages=list(messages),
            response_model=response_model,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        return response


# ---------------------------------------------------------------------------
# Small helpers (kept module-level to simplify testing)
# ---------------------------------------------------------------------------


def _estimate_input_tokens(messages: List[MessageDict]) -> int:
    """Rough ~1.3 tokens / word heuristic, matching MockLLMService."""
    words = 0
    for msg in messages:
        content: Any = msg.get("content", "")
        if isinstance(content, str):
            words += len(content.split())
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    words += len(str(block.get("text", "")).split())
    return max(1, int(words * 1.3))


def _estimate_energy_kwh(total_tokens: int) -> float:
    # Mobile SoC inference is more efficient than datacenter inference per
    # token; ~0.00002 kWh/1k tokens is a reasonable Gemma-4-E2B estimate.
    return total_tokens * 0.00002 / 1000.0


def _estimate_carbon_grams(total_tokens: int) -> float:
    # Using the same on-device factor; callers can refine with the real
    # grid intensity reported by the mobile telemetry collector.
    return _estimate_energy_kwh(total_tokens) * 500.0


__all__ = ["MobileLocalLLMService"]
