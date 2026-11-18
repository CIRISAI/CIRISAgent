"""The LLM bus waits out OpenRouter's in-flight budget, and only that (CIRISAgent#1366 item 20).

* an in-flight-budget refusal is retried after max(Retry-After, jittered
  backoff), within the caller's deadline, without failing the breaker;
* the first refusal PAUSES the provider: calls queued behind it do not reach
  the provider until the pause has passed, so a thought's parallel calls do not
  all retry on the same beat;
* every other spending-limit refusal (request too large, empty balance, key
  limit) is surfaced on its first occurrence, unretried.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, List, Optional, Tuple, Type

import httpx
import openai
import pytest
from pydantic import BaseModel

from ciris_engine.logic.buses import llm_bus as bus_module
from ciris_engine.logic.buses.llm_bus import DistributionStrategy, LLMBus
from ciris_engine.logic.config.llm_budget import llm_call_deadline
from ciris_engine.logic.registries.base import Priority, ServiceRegistry
from ciris_engine.logic.registries.circuit_breaker import CircuitState
from ciris_engine.logic.services.runtime.llm_service import provider_limits
from ciris_engine.logic.services.runtime.llm_service.provider_limits import ProviderLimitError, provider_limit_fault
from ciris_engine.schemas.runtime.enums import ServiceType
from ciris_engine.schemas.runtime.resources import ResourceUsage

IN_FLIGHT = {"reason": "in_flight_budget_exhausted", "limit_source": "openrouter_in_flight_budget"}
WEIGHT = {"reason": "weight_exceeds_budget", "limit_source": "openrouter_credits"}
CREDITS = {"limit_source": "openrouter_credits"}
KEY_LIMIT = {"limit_source": "openrouter_key_limit"}


class Answer(BaseModel):
    message: str


class _Clock:
    def timestamp(self) -> float:
        return time.time()

    def now(self) -> Any:
        from datetime import datetime, timezone

        return datetime.now(timezone.utc)


def _refusal(metadata: dict, status: int = 402, retry_after: Optional[str] = None) -> ProviderLimitError:
    """Exactly what OpenAICompatibleClient raises for a limit refusal."""
    req = httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions")
    inner = {"code": status, "message": "refused", "metadata": metadata}
    headers = {"Retry-After": retry_after} if retry_after else {}
    api_error = openai.APIStatusError(
        "refused", response=httpx.Response(status, request=req, headers=headers, json={"error": inner}), body=inner
    )
    fault = provider_limit_fault(api_error)
    assert fault is not None
    try:
        raise ProviderLimitError(fault) from api_error
    except ProviderLimitError as e:
        return e


class RefusingProvider:
    """Refuses the first `refusals` calls with `error`, then answers. Records call start times."""

    def __init__(self, error_factory: Any, refusals: int = 1, latency_s: float = 0.0) -> None:
        self.service_name = "openrouter"
        self.error_factory = error_factory
        self.refusals = refusals
        self.latency_s = latency_s
        self.starts: List[float] = []
        self.refused_at: List[float] = []

    async def call_llm_structured(
        self, messages: List[dict], response_model: Type[BaseModel], max_tokens: int = 1024, **_: Any
    ) -> Tuple[BaseModel, ResourceUsage]:
        self.starts.append(time.monotonic())
        if self.refusals > 0:
            self.refusals -= 1
            self.refused_at.append(time.monotonic())
            raise self.error_factory()
        await asyncio.sleep(self.latency_s)
        return Answer(message="ok"), ResourceUsage(tokens_used=1, model_used="m")

    def get_capabilities(self) -> Any:
        class Caps:
            supports_operation_list = ["call_llm_structured"]

        return Caps()


def _bus_with(provider: Any) -> LLMBus:
    registry = ServiceRegistry()
    registry.register_service(
        service_type=ServiceType.LLM,
        provider=provider,
        priority=Priority.NORMAL,
        capabilities=["call_llm_structured"],
        metadata={"provider": "test"},
    )
    return LLMBus(
        service_registry=registry,
        time_service=_Clock(),  # type: ignore[arg-type]
        distribution_strategy=DistributionStrategy.ROUND_ROBIN,
    )


async def _call(bus: LLMBus, handler: str = "EthicalPDMAEvaluator") -> Tuple[BaseModel, ResourceUsage]:
    return await bus.call_llm_structured(
        messages=[{"role": "user", "content": "q"}], response_model=Answer, handler_name=handler
    )


@pytest.fixture
def fast_backoff(monkeypatch):
    """Sub-second waits so the tests run in real time."""
    monkeypatch.setattr(provider_limits, "IN_FLIGHT_BACKOFF_BASE_S", 0.05)
    monkeypatch.setattr(provider_limits, "IN_FLIGHT_MIN_WAIT_S", 0.05)
    monkeypatch.setattr(bus_module, "IN_FLIGHT_RELEASE_SPREAD_S", 0.05)


class TestInFlightBudgetIsWaitedOut:
    @pytest.mark.asyncio
    async def test_retry_after_is_honoured_then_the_call_succeeds(self, fast_backoff):
        provider = RefusingProvider(lambda: _refusal(IN_FLIGHT, retry_after="0.4"))
        bus = _bus_with(provider)
        result, _ = await _call(bus)
        assert result.message == "ok"
        assert len(provider.starts) == 2
        assert provider.starts[1] - provider.refused_at[0] >= 0.4, "the retry must wait at least Retry-After"

    @pytest.mark.asyncio
    async def test_without_retry_after_it_backs_off_and_retries(self, fast_backoff):
        provider = RefusingProvider(lambda: _refusal(IN_FLIGHT), refusals=3)
        bus = _bus_with(provider)
        result, _ = await _call(bus)
        assert result.message == "ok"
        assert len(provider.starts) == 4

    @pytest.mark.asyncio
    async def test_never_a_breaker_failure(self, fast_backoff, monkeypatch):
        monkeypatch.setattr(provider_limits, "IN_FLIGHT_TOTAL_WAIT_S", 0.3)
        monkeypatch.setattr(bus_module, "IN_FLIGHT_TOTAL_WAIT_S", 0.3)
        provider = RefusingProvider(lambda: _refusal(IN_FLIGHT, retry_after="0.2"), refusals=10_000)
        bus = _bus_with(provider)
        for _ in range(6):  # more than the breaker's threshold of 5
            with pytest.raises(RuntimeError, match="in-flight spending budget"):
                await _call(bus)
        breaker = bus.circuit_breakers.get("openrouter")
        assert breaker is None or breaker.state == CircuitState.CLOSED
        assert bus.service_metrics["openrouter"].failed_requests == 0

    @pytest.mark.asyncio
    async def test_a_wait_the_deadline_cannot_afford_is_not_taken(self, fast_backoff):
        # Retry-After 5s, but the stage has 11s left and needs 10s for a useful attempt.
        provider = RefusingProvider(lambda: _refusal(IN_FLIGHT, retry_after="5"))
        bus = _bus_with(provider)
        started = time.monotonic()
        with llm_call_deadline(11.0):
            with pytest.raises(RuntimeError, match="in-flight spending budget"):
                await _call(bus)
        assert len(provider.starts) == 1
        assert time.monotonic() - started < 2.0


class TestThePauseSpacesConcurrentCalls:
    @pytest.mark.asyncio
    async def test_calls_queued_behind_a_refusal_wait_for_the_pause(self, fast_backoff, monkeypatch):
        # One in-flight slot, so the other calls queue at the gate the way a
        # thought's parallel DMAs queue behind a saturated provider.
        monkeypatch.setenv("CIRIS_LLM_MAX_CONCURRENT", "1")
        pause_s = 0.5
        provider = RefusingProvider(lambda: _refusal(IN_FLIGHT, retry_after=str(pause_s)), latency_s=0.02)
        bus = _bus_with(provider)

        results = await asyncio.gather(*(_call(bus, f"h{i}") for i in range(6)))
        assert all(r[0].message == "ok" for r in results)

        refused = provider.refused_at[0]
        after_refusal = [t for t in provider.starts if t > refused]
        assert len(after_refusal) == 6  # the 5 queued calls + the retry
        early = [t - refused for t in after_refusal if t - refused < pause_s]
        assert not early, f"calls reached the provider during the pause: {early}"


class TestOtherLimitsAreSurfacedUnretried:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "metadata,status,expected",
        [
            (WEIGHT, 402, "too large for the in-flight budget"),
            (CREDITS, 402, "credits cannot cover"),
            (KEY_LIMIT, 402, "key limit"),
            (KEY_LIMIT, 403, "key limit"),
        ],
    )
    async def test_sent_once_and_surfaced(self, fast_backoff, metadata, status, expected):
        provider = RefusingProvider(lambda: _refusal(metadata, status=status, retry_after="0.1"), refusals=10)
        bus = _bus_with(provider)
        with pytest.raises(RuntimeError, match=expected):
            await _call(bus)
        assert len(provider.starts) == 1
        assert bus._provider_paused_until == {}, "only the in-flight budget pauses the provider"
