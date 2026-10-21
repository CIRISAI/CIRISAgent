"""One slow provider episode must not drain the queue.

The 2026-10-15 battery run against DeepInfra Qwen3.6 (16-68s per call, 45s
HTTP timeout) went like this: one slow thought had three parallel DMA
timeouts plus a PDMA retry, which counted as four breaker failures. The next
slow thought tripped the breaker at five. With a single provider, the bus then
skipped it for 60s, so every queued thought failed in about 0.1s with
"Last error: None" and no request was sent.

These tests pin the fixes:

* concurrent failures of one provider are one breaker failure;
* with no alternative provider, an open breaker is waited out within the
  caller's deadline instead of failing instantly;
* when the deadline cannot cover the wait, the error is categorized
  (CIRCUIT_OPEN) and carries the provider's real last error;
* multi-provider failover is unchanged;
* the wording is honest about the breaker and about attempts.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, List, Optional, Tuple, Type

import pytest
from pydantic import BaseModel

from ciris_engine.logic.buses.llm_bus import DistributionStrategy, LLMBus
from ciris_engine.logic.config.llm_budget import llm_call_deadline
from ciris_engine.logic.conscience.transport import (
    categorize_conscience_error,
    is_transient_transport_failure,
    is_transport_failure,
)
from ciris_engine.logic.registries.base import Priority, ServiceRegistry
from ciris_engine.logic.registries.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitState,
    ProviderCircuitOpenError,
)
from ciris_engine.schemas.runtime.enums import ServiceType
from ciris_engine.schemas.runtime.resources import ResourceUsage


class Answer(BaseModel):
    message: str


class _Clock:
    def timestamp(self) -> float:
        return time.time()

    def now(self) -> Any:
        from datetime import datetime, timezone

        return datetime.now(timezone.utc)


class SlowEpisodeProvider:
    """A single hosted provider with its own breaker, like OpenAICompatibleClient.

    While `slow` is set every call takes a moment and then times out, the way
    the HTTP client reports a 45s timeout; afterwards it answers.
    """

    def __init__(self, name: str, recovery_timeout: float = 60.0, latency_s: float = 0.05) -> None:
        self.service_name = name
        self.slow = True
        self.calls = 0
        self.latency_s = latency_s
        self.circuit_breaker = CircuitBreaker(
            "llm_service",
            CircuitBreakerConfig(
                failure_threshold=5,
                recovery_timeout=recovery_timeout,
                success_threshold=2,
                failure_coalesce_window_s=1.0,
            ),
        )

    async def call_llm_structured(
        self,
        messages: List[dict],
        response_model: Type[BaseModel],
        max_tokens: int = 1024,
        temperature: float = 0.0,
        **_: Any,
    ) -> Tuple[BaseModel, ResourceUsage]:
        self.circuit_breaker.check_and_raise()
        self.calls += 1
        await asyncio.sleep(self.latency_s)
        if self.slow:
            self.circuit_breaker.record_failure()
            raise TimeoutError("LLM API timeout")
        self.circuit_breaker.record_success()
        return Answer(message=f"from {self.service_name}"), ResourceUsage(tokens_used=10, model_used="m")

    def get_capabilities(self) -> Any:
        class Caps:
            supports_operation_list = ["call_llm_structured"]

        return Caps()


def _bus(registry: ServiceRegistry, **cb: Any) -> LLMBus:
    return LLMBus(
        service_registry=registry,
        time_service=_Clock(),  # type: ignore[arg-type]
        distribution_strategy=DistributionStrategy.ROUND_ROBIN,
        circuit_breaker_config=cb or None,
    )


def _register(registry: ServiceRegistry, provider: Any, priority: Priority = Priority.NORMAL) -> None:
    registry.register_service(
        service_type=ServiceType.LLM,
        provider=provider,
        priority=priority,
        capabilities=["call_llm_structured"],
        metadata={"provider": "test"},
    )


async def _call(bus: LLMBus, handler: str = "EthicalPDMAEvaluator") -> Tuple[BaseModel, ResourceUsage]:
    return await bus.call_llm_structured(
        messages=[{"role": "user", "content": "q"}], response_model=Answer, handler_name=handler
    )


async def _slow_thought(bus: LLMBus) -> None:
    """Three parallel DMAs time out together, then PDMA retries once."""
    outcomes = await asyncio.gather(
        _call(bus, "EthicalPDMAEvaluator"),
        _call(bus, "CSDMAEvaluator"),
        _call(bus, "BaseDSDMA"),
        return_exceptions=True,
    )
    assert all(isinstance(o, RuntimeError) for o in outcomes), outcomes
    with pytest.raises(RuntimeError, match="LLM API timeout"):
        await _call(bus, "EthicalPDMAEvaluator")


class TestOneSlowEpisodeDoesNotDrainTheQueue:
    @pytest.mark.asyncio
    async def test_three_concurrent_timeouts_are_one_breaker_failure(self) -> None:
        registry = ServiceRegistry()
        provider = SlowEpisodeProvider("deepinfra_primary")
        _register(registry, provider)
        bus = _bus(registry)

        await asyncio.gather(*[_call(bus) for _ in range(3)], return_exceptions=True)

        assert bus.circuit_breakers["deepinfra_primary"].failure_count == 1
        assert provider.circuit_breaker.failure_count == 1

    @pytest.mark.asyncio
    async def test_next_thought_succeeds_once_the_provider_answers(self) -> None:
        """The drained-queue regression, at the production breaker defaults (5 failures / 60s).

        Before: 3 concurrent + 1 retry = 4 failures per slow thought, so the
        second slow thought opened both breakers and every later thought
        failed without sending a request for 60s. After: 2 per slow thought.
        """
        registry = ServiceRegistry()
        provider = SlowEpisodeProvider("deepinfra_primary")
        _register(registry, provider)
        bus = _bus(registry)

        await _slow_thought(bus)
        await _slow_thought(bus)
        assert bus.circuit_breakers["deepinfra_primary"].state == CircuitState.CLOSED
        assert provider.circuit_breaker.state == CircuitState.CLOSED

        provider.slow = False
        calls_before = provider.calls
        results = await asyncio.gather(*[_call(bus) for _ in range(3)])
        assert [r[0].message for r in results] == ["from deepinfra_primary"] * 3
        assert provider.calls == calls_before + 3  # requests were actually sent

    @pytest.mark.asyncio
    async def test_sequential_failures_still_count_separately(self) -> None:
        """Coalescing is for concurrent calls only: a real outage still opens the breaker."""
        registry = ServiceRegistry()
        provider = SlowEpisodeProvider("deepinfra_primary", latency_s=0.0)
        _register(registry, provider)
        bus = _bus(registry)

        for _ in range(5):
            with pytest.raises(RuntimeError):
                await _call(bus)
        assert bus.circuit_breakers["deepinfra_primary"].state == CircuitState.OPEN


class TestOpenBreakerWithNoAlternative:
    async def _open(self, bus: LLMBus) -> None:
        for _ in range(5):
            with pytest.raises(RuntimeError):
                await _call(bus)

    @pytest.mark.asyncio
    async def test_deadline_too_short_gives_the_categorized_error_with_the_real_last_error(self) -> None:
        registry = ServiceRegistry()
        provider = SlowEpisodeProvider("deepinfra_primary", latency_s=0.0)
        _register(registry, provider)
        bus = _bus(registry)
        await self._open(bus)

        sent = provider.calls
        started = time.monotonic()
        with llm_call_deadline(20.0):  # cannot cover a ~60s recovery
            with pytest.raises(ProviderCircuitOpenError) as ei:
                await _call(bus)
        assert time.monotonic() - started < 1.0  # no wait it could not afford
        assert provider.calls == sent  # and no request

        msg = str(ei.value)
        assert msg.startswith(
            "circuit breaker open for deepinfra_primary (5 failures, last: LLM API timeout, retry in "
        )
        assert "None" not in msg
        assert isinstance(ei.value.last_error, TimeoutError)

        # Categorizers: not a fresh timeout (no DMA/facility retry), but the
        # check did not run (conscience transport -> fail-closed, check_ran=False).
        assert categorize_conscience_error(ei.value) == "CIRCUIT_OPEN"
        assert not is_transient_transport_failure(ei.value)
        assert is_transport_failure(ei.value)
        # Still a RuntimeError, so every existing `except RuntimeError` keeps catching it.
        assert isinstance(ei.value, RuntimeError)

    @pytest.mark.asyncio
    async def test_no_deadline_fails_fast_with_the_same_error(self) -> None:
        registry = ServiceRegistry()
        provider = SlowEpisodeProvider("deepinfra_primary", latency_s=0.0)
        _register(registry, provider)
        bus = _bus(registry)
        await self._open(bus)

        with pytest.raises(ProviderCircuitOpenError, match="last: LLM API timeout"):
            await _call(bus)

    @pytest.mark.asyncio
    async def test_deadline_that_covers_recovery_waits_for_the_probe(self) -> None:
        registry = ServiceRegistry()
        provider = SlowEpisodeProvider("deepinfra_primary", recovery_timeout=0.3, latency_s=0.0)
        _register(registry, provider)
        bus = _bus(registry, failure_threshold=5, recovery_timeout=0.3)
        await self._open(bus)
        assert bus.circuit_breakers["deepinfra_primary"].state == CircuitState.OPEN

        provider.slow = False
        started = time.monotonic()
        with llm_call_deadline(30.0):
            result, _ = await _call(bus)
        assert result.message == "from deepinfra_primary"
        assert time.monotonic() - started >= 0.2  # it waited for the half-open probe


class TestMultiProviderFailoverUnchanged:
    @pytest.mark.asyncio
    async def test_open_primary_fails_over_to_secondary_without_waiting(self) -> None:
        registry = ServiceRegistry()
        primary = SlowEpisodeProvider("primary", latency_s=0.0)
        secondary = SlowEpisodeProvider("secondary", latency_s=0.0)
        secondary.slow = False
        _register(registry, primary, Priority.HIGH)
        _register(registry, secondary, Priority.NORMAL)
        bus = _bus(registry)
        bus._check_circuit_breaker("primary")
        bus.circuit_breakers["primary"].force_open(reason="test")

        started = time.monotonic()
        with llm_call_deadline(120.0):
            result, _ = await _call(bus)
        assert result.message == "from secondary"
        assert time.monotonic() - started < 1.0
        assert primary.calls == 0


class TestWording:
    @pytest.mark.asyncio
    async def test_bus_logs_attempts_not_retries(self, caplog: pytest.LogCaptureFixture) -> None:
        registry = ServiceRegistry()
        _register(registry, SlowEpisodeProvider("deepinfra_primary", latency_s=0.0))
        bus = _bus(registry)
        with caplog.at_level(logging.WARNING, logger="ciris_engine.logic.buses.llm_bus"):
            with pytest.raises(RuntimeError):
                await _call(bus)
        text = caplog.text
        assert "Exhausted 1 attempt(s) on deepinfra_primary" in text
        assert "failed after 1 attempt(s)" in text
        assert "1 retries" not in text

    def test_timeout_error_does_not_claim_the_breaker_activated(self) -> None:
        from unittest.mock import MagicMock

        from ciris_engine.logic.services.runtime.llm_service.service import (
            LLMErrorContext,
            _handle_instructor_retry_exception,
        )

        ctx = LLMErrorContext(
            model="m", provider="p", response_model="R", circuit_breaker_state="closed", consecutive_failures=0
        )
        with pytest.raises(TimeoutError) as ei:
            _handle_instructor_retry_exception(Exception("Request timed out."), ctx, MagicMock())
        assert str(ei.value) == "LLM API timeout"
        assert "circuit breaker" not in str(ei.value).lower()
