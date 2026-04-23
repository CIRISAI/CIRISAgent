"""
Tests for the LLM bus FIFO concurrency gate and centralized 502-backoff path.

Covers the scenario we hit live against qwen/qwen3.5-35b-a3b via OpenRouter:
  - N concurrent DMAs all racing a single external endpoint
  - Upstream returns intermittent 502 "Provider returned error"
  - With the gate, only max_in_flight requests hit the provider at once; the
    rest queue FIFO instead of failing fast
  - With the centralized 502 path, transient 5xx responses get polite-backoff
    (same path as 429) rather than counting against the circuit breaker
  - With dual replicas at the same priority, LEAST_LOADED routes new calls to
    the replica with semaphore headroom
"""

import asyncio
import os
import time
from typing import Any, Dict, List, Tuple, Type
from unittest.mock import Mock

import pytest
from pydantic import BaseModel

from ciris_engine.logic.buses.llm_bus import DistributionStrategy, LLMBus
from ciris_engine.logic.registries.base import ServiceRegistry
from ciris_engine.schemas.runtime.resources import ResourceUsage


class MockResponse(BaseModel):
    content: str = "ok"


class MockTimeService:
    def __init__(self) -> None:
        self._t = time.time()

    def now(self):
        from datetime import datetime, timezone

        return datetime.fromtimestamp(self._t, tz=timezone.utc)

    def timestamp(self) -> float:
        return self._t

    def advance(self, s: float) -> None:
        self._t += s


class CountingMockService:
    """Mock LLM service that tracks concurrent in-flight calls."""

    def __init__(self, name: str, delay: float = 0.05, fail_first_n: int = 0, fail_code: int = 502) -> None:
        self._name = name
        self._service_name = name
        self.delay = delay
        self.call_count = 0
        self.fail_first_n = fail_first_n
        self.fail_code = fail_code
        self.concurrent_now = 0
        self.peak_concurrent = 0
        self._lock = asyncio.Lock()

    def get_service_name(self) -> str:  # what _get_service_name looks for
        return self._service_name

    async def call_llm_structured(
        self,
        messages: List[Dict[str, Any]],
        response_model: Type[BaseModel],
        max_tokens: int = 1024,
        temperature: float = 0.0,
        **kwargs,
    ) -> Tuple[BaseModel, ResourceUsage]:
        async with self._lock:
            self.call_count += 1
            self.concurrent_now += 1
            self.peak_concurrent = max(self.peak_concurrent, self.concurrent_now)
            my_call = self.call_count
        try:
            await asyncio.sleep(self.delay)
            if my_call <= self.fail_first_n:
                # Simulate upstream-relay error shape (OpenRouter 502s come as
                # "Provider returned error" with code 502 in the message).
                raise RuntimeError(
                    f"Error code: {self.fail_code} - "
                    '{"message": "Provider returned error", "code": '
                    + str(self.fail_code)
                    + "}"
                )
            return MockResponse(), ResourceUsage(
                tokens_used=10,
                tokens_input=5,
                tokens_output=5,
                cost_cents=0.001,
                model_used="mock",
            )
        finally:
            async with self._lock:
                self.concurrent_now -= 1

    def get_capabilities(self):
        class C:
            supports_operation_list = ["call_llm_structured"]

        return C()

    async def is_healthy(self) -> bool:
        return True


@pytest.fixture
def registry():
    return Mock(spec=ServiceRegistry)


@pytest.fixture
def time_svc():
    return MockTimeService()


def _build_bus(registry, time_svc, services: List[CountingMockService], max_in_flight: int = 3) -> LLMBus:
    """Build an LLMBus with the given max-in-flight and inject services."""
    os.environ["CIRIS_LLM_MAX_CONCURRENT"] = str(max_in_flight)
    try:
        bus = LLMBus(
            service_registry=registry,
            time_service=time_svc,
            telemetry_service=None,
            distribution_strategy=DistributionStrategy.LEAST_LOADED,
            circuit_breaker_config={
                "failure_threshold": 5,
                "recovery_timeout": 60.0,
                "half_open_max_calls": 3,
                "timeout_duration": 30.0,
            },
        )
    finally:
        os.environ.pop("CIRIS_LLM_MAX_CONCURRENT", None)

    async def _get_prioritized_services(handler_name: str, domain=None):
        return list(services)

    def _group_by_priority(services_list):
        return {0: list(services_list)}

    def _get_service_name(svc):
        return svc.get_service_name()

    bus._get_prioritized_services = _get_prioritized_services  # type: ignore[assignment]
    bus._group_by_priority = _group_by_priority  # type: ignore[assignment]
    bus._get_service_name = _get_service_name  # type: ignore[assignment]
    return bus


@pytest.mark.asyncio
async def test_fifo_gate_bounds_in_flight_per_service(registry, time_svc):
    """FIFO semaphore must cap concurrent in-flight calls per service name."""
    svc = CountingMockService("ciris_primary", delay=0.1)
    bus = _build_bus(registry, time_svc, [svc], max_in_flight=3)

    async def call():
        return await bus.call_llm_structured(
            messages=[{"role": "user", "content": "hi"}],
            response_model=MockResponse,
        )

    # Launch 20 concurrent callers against a 3-in-flight gate.
    results = await asyncio.gather(*[call() for _ in range(20)], return_exceptions=True)
    assert all(not isinstance(r, Exception) for r in results), results

    # All 20 completed, but the provider never saw more than 3 at once.
    assert svc.call_count == 20
    assert svc.peak_concurrent <= 3, f"gate breached: peak={svc.peak_concurrent}"


@pytest.mark.asyncio
async def test_502_routes_through_rate_limit_backoff(registry, time_svc):
    """HTTP 502 / 'Provider returned error' should NOT count against the circuit
    breaker. It takes the same polite-backoff path as 429s."""
    # First 2 attempts return 502, then success on the 3rd attempt.
    svc = CountingMockService("ciris_primary", delay=0.01, fail_first_n=2, fail_code=502)
    bus = _build_bus(registry, time_svc, [svc], max_in_flight=2)

    # Speed up the test — make rate-limit retry wait ~immediate.
    bus._extract_retry_after_time = lambda _err: 0.01  # type: ignore[assignment]

    result, _usage = await bus.call_llm_structured(
        messages=[{"role": "user", "content": "hi"}],
        response_model=MockResponse,
    )
    assert isinstance(result, MockResponse)
    # Service was called 3 times (2 fails + 1 success).
    assert svc.call_count == 3

    # 502s must NOT have tripped the circuit breaker:
    if "ciris_primary" in bus.circuit_breakers:
        assert bus.circuit_breakers["ciris_primary"].failure_count == 0


@pytest.mark.asyncio
async def test_server_error_detector_covers_all_5xx_shapes():
    """_is_server_error matches 502/503/504 and OpenRouter relay errors."""
    bus = LLMBus(
        service_registry=Mock(spec=ServiceRegistry),
        time_service=MockTimeService(),
        telemetry_service=None,
    )
    assert bus._is_server_error("", "HTTP 502 Bad Gateway")
    assert bus._is_server_error("", "Error code: 503 - service unavailable")
    assert bus._is_server_error("", "Gateway timeout (504)")
    assert bus._is_server_error("", '{"message": "Provider returned error", "code": 400}')
    # Negatives
    assert not bus._is_server_error("", "Invalid API key (401)")
    assert not bus._is_server_error("", "Invalid input (400 validation)")


@pytest.mark.asyncio
async def test_least_loaded_picks_replica_with_semaphore_headroom(registry, time_svc):
    """With two identical replicas at the same priority, LEAST_LOADED must
    prefer whichever one has more in-flight capacity.

    Simulates the 'dual OpenRouter registration, half-concurrency each'
    deployment — when primary is saturated, the second replica takes work."""
    primary = CountingMockService("ciris_primary", delay=0.3)
    replica = CountingMockService("ciris_primary_2", delay=0.3)
    bus = _build_bus(registry, time_svc, [primary, replica], max_in_flight=3)

    async def call():
        return await bus.call_llm_structured(
            messages=[{"role": "user", "content": "hi"}],
            response_model=MockResponse,
        )

    # 12 concurrent calls, 2 replicas × 3 in-flight each = 6 immediate, 6 queued.
    results = await asyncio.gather(*[call() for _ in range(12)], return_exceptions=True)
    assert all(not isinstance(r, Exception) for r in results), results

    # Load must have distributed across BOTH replicas (not piled on one).
    assert primary.call_count > 0
    assert replica.call_count > 0
    # Reasonably balanced — neither replica should have >70% of the load.
    total = primary.call_count + replica.call_count
    assert total == 12
    assert primary.call_count / total <= 0.7
    assert replica.call_count / total <= 0.7
    # Neither replica breached its own semaphore.
    assert primary.peak_concurrent <= 3
    assert replica.peak_concurrent <= 3


@pytest.mark.asyncio
async def test_gate_logs_saturation_when_in_flight_cap_hit(registry, time_svc, caplog):
    """When the gate is saturated, a LOG entry marks callers as queued so
    operators can see that the bus is backpressuring rather than failing."""
    import logging

    svc = CountingMockService("ciris_primary", delay=0.1)
    bus = _build_bus(registry, time_svc, [svc], max_in_flight=2)
    caplog.set_level(logging.INFO, logger="ciris_engine.logic.buses.llm_bus")

    async def call():
        return await bus.call_llm_structured(
            messages=[{"role": "user", "content": "hi"}],
            response_model=MockResponse,
        )

    await asyncio.gather(*[call() for _ in range(6)])

    gate_logs = [r for r in caplog.records if "LLM-GATE" in r.getMessage()]
    # At least some of the 6 calls should have seen a saturated gate.
    assert len(gate_logs) > 0, "expected at least one LLM-GATE saturated log line"


def test_max_in_flight_env_var_invalid_falls_back_to_default(registry, time_svc):
    """Invalid CIRIS_LLM_MAX_CONCURRENT values fall back to 8, not crash."""
    os.environ["CIRIS_LLM_MAX_CONCURRENT"] = "not-a-number"
    try:
        bus = LLMBus(
            service_registry=registry,
            time_service=time_svc,
            telemetry_service=None,
        )
    finally:
        os.environ.pop("CIRIS_LLM_MAX_CONCURRENT", None)
    assert bus._max_in_flight_per_service == 8


def test_max_in_flight_env_var_respects_minimum(registry, time_svc):
    """max_in_flight is clamped to at least 1 (a value of 0 or negative would
    deadlock the bus, so we floor it)."""
    os.environ["CIRIS_LLM_MAX_CONCURRENT"] = "0"
    try:
        bus = LLMBus(
            service_registry=registry,
            time_service=time_svc,
            telemetry_service=None,
        )
    finally:
        os.environ.pop("CIRIS_LLM_MAX_CONCURRENT", None)
    assert bus._max_in_flight_per_service >= 1


@pytest.mark.asyncio
async def test_502_on_replica_a_drives_traffic_to_replica_b(registry, time_svc):
    """If replica A keeps returning 502s it enters rate-limit cooldown; LEAST_LOADED
    then routes to replica B even though A isn't 'circuit-broken' yet."""
    flaky = CountingMockService("ciris_primary", delay=0.01, fail_first_n=100, fail_code=502)
    healthy = CountingMockService("ciris_primary_2", delay=0.01)
    bus = _build_bus(registry, time_svc, [flaky, healthy], max_in_flight=2)
    bus._extract_retry_after_time = lambda _err: 0.01  # type: ignore[assignment]

    async def call():
        try:
            return await bus.call_llm_structured(
                messages=[{"role": "user", "content": "hi"}],
                response_model=MockResponse,
            )
        except Exception as e:
            return e

    results = await asyncio.gather(*[call() for _ in range(8)])

    # Every one of the 8 calls must have succeeded via the healthy replica.
    # (After flaky enters rate-limit cooldown, the bus skips it and serves
    # from healthy exclusively.)
    ok_count = sum(1 for r in results if isinstance(r, tuple))
    assert ok_count == 8, f"expected all succeed via healthy replica, got {ok_count}/8"
    assert healthy.call_count >= 8
