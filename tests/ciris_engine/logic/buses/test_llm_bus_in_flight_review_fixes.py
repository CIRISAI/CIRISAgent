"""RATCHET review of the in-flight budget handling (CIRISAgent#1366 item 20).

One test (or more) per finding, each written to FAIL with its fix reverted:

* F1 -- the gate re-reads the pause after every sleep: a later refusal that
  extends it holds callers already sleeping (built on the review's race.py);
* F2 -- the pause belongs to the account (base URL + key digest), so services
  with different names on the same key pause together;
* F3 -- no hedge starts while a provider is paused;
* F4 -- an in-flight retry stuck behind the concurrency queue surfaces the
  refusal within its deadline instead of running into a DMA timeout;
* F6 -- sustained pressure backs off across calls (account-level exponent);
* F7 -- a request too large for the budget is not a breaker failure;
* F11 -- in-flight retries are numbered on the LLM_CALL event.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, List, Optional, Tuple, Type

import pytest
from pydantic import BaseModel

from ciris_engine.logic.buses import llm_bus as bus_module
from ciris_engine.logic.buses.llm_bus import DistributionStrategy, LLMBus
from ciris_engine.logic.config.llm_budget import llm_call_deadline
from ciris_engine.logic.registries.base import Priority, ServiceRegistry
from ciris_engine.logic.registries.circuit_breaker import CircuitState
from ciris_engine.logic.services.runtime.llm_service import provider_limits
from ciris_engine.logic.utils import hedging
from ciris_engine.schemas.runtime.enums import ServiceType
from ciris_engine.schemas.runtime.resources import ResourceUsage

from test_llm_bus_in_flight_budget import (  # noqa: E402 - sibling test module (rootdir import mode)
    IN_FLIGHT,
    WEIGHT,
    Answer,
    RefusingProvider,
    _bus_with,
    _call,
    _Clock,
    _refusal,
)


@pytest.fixture
def fast_backoff(monkeypatch):
    monkeypatch.setattr(provider_limits, "IN_FLIGHT_BACKOFF_BASE_S", 0.05)
    monkeypatch.setattr(provider_limits, "IN_FLIGHT_MIN_WAIT_S", 0.05)
    monkeypatch.setattr(bus_module, "IN_FLIGHT_RELEASE_SPREAD_S", 0.0)
    hedging.reset()
    yield
    hedging.reset()


class _Scripted(RefusingProvider):
    """Refuses the first call of named handlers after a delay, with a given Retry-After."""

    def __init__(self, script: dict) -> None:
        super().__init__(None, 0)
        self.script = dict(script)  # content -> (delay_s, retry_after)
        self.log: List[Tuple[float, str]] = []

    async def call_llm_structured(
        self, messages: List[dict], response_model: Type[BaseModel], max_tokens: int = 1024, **_: Any
    ) -> Tuple[BaseModel, ResourceUsage]:
        who = messages[0]["content"]
        self.log.append((time.monotonic(), who))
        if who in self.script:
            delay, retry_after = self.script.pop(who)
            await asyncio.sleep(delay)
            self.refused_at.append(time.monotonic())
            raise _refusal(IN_FLIGHT, retry_after=retry_after)
        await asyncio.sleep(0.01)
        return Answer(message="ok"), ResourceUsage(tokens_used=1, model_used="m")


async def _named_call(bus: LLMBus, who: str) -> Tuple[BaseModel, ResourceUsage]:
    return await bus.call_llm_structured(
        messages=[{"role": "user", "content": who}], response_model=Answer, handler_name=who
    )


class TestF1PauseIsReReadAfterEverySleep:
    @pytest.mark.asyncio
    async def test_a_later_refusal_extends_the_pause_for_callers_already_waiting(self, fast_backoff, monkeypatch):
        # race.py: two slots. A is refused at ~0.02s (Retry-After 0.3), B at
        # ~0.10s (Retry-After 1.0). C took A's slot and was sleeping on A's
        # pause when B extended it: C must not reach the provider before B's.
        monkeypatch.setenv("CIRIS_LLM_MAX_CONCURRENT", "2")
        provider = _Scripted({"A": (0.02, "0.3"), "B": (0.10, "1.0")})
        bus = _bus_with(provider)

        await asyncio.gather(_named_call(bus, "A"), _named_call(bus, "B"), _named_call(bus, "C"))

        b_refused = provider.refused_at[1]
        c_start = next(t for t, who in provider.log if who == "C")
        assert c_start - b_refused >= 0.95, (
            f"C reached the provider {c_start - b_refused:.2f}s after B's refusal, inside B's 1.0s pause"
        )


class _Keyed(RefusingProvider):
    """A provider with its own service name and an account identity."""

    def __init__(self, name: str, shared: dict, identity: Tuple[str, str]) -> None:
        super().__init__(None, 0)
        self.service_name = name
        self.shared = shared
        self.identity = identity

    def budget_identity(self) -> Tuple[str, str]:
        return self.identity

    async def call_llm_structured(
        self, messages: List[dict], response_model: Type[BaseModel], max_tokens: int = 1024, **_: Any
    ) -> Tuple[BaseModel, ResourceUsage]:
        self.shared["starts"].append((time.monotonic(), self.service_name))
        if not self.shared["refused"]:
            self.shared["refused"].append(time.monotonic())
            raise _refusal(IN_FLIGHT, retry_after="0.5")
        await asyncio.sleep(0.01)
        return Answer(message="ok"), ResourceUsage(tokens_used=1, model_used="m")


def _bus_over(*providers: Any) -> LLMBus:
    registry = ServiceRegistry()
    for p in providers:
        registry.register_service(
            service_type=ServiceType.LLM,
            provider=p,
            priority=Priority.NORMAL,
            capabilities=["call_llm_structured"],
            metadata={"provider": "test"},
        )
    return LLMBus(
        service_registry=registry,
        time_service=_Clock(),  # type: ignore[arg-type]
        distribution_strategy=DistributionStrategy.ROUND_ROBIN,
    )


class TestF2PauseBelongsToTheAccount:
    @pytest.mark.asyncio
    async def test_replicas_on_one_key_pause_together(self, fast_backoff):
        shared: dict = {"starts": [], "refused": []}
        ident = ("https://openrouter.ai/api/v1", "0123456789abcdef")
        bus = _bus_over(_Keyed("openrouter_0", shared, ident), _Keyed("openrouter_1", shared, ident))

        first = asyncio.ensure_future(_named_call(bus, "A"))
        await asyncio.sleep(0.05)  # A has been refused and the pause published
        await asyncio.gather(first, _named_call(bus, "B"))

        refused = shared["refused"][0]
        services = {name for _, name in shared["starts"]}
        assert services == {"openrouter_0", "openrouter_1"}, "both replicas must have been called"
        early = [(round(t - refused, 3), n) for t, n in shared["starts"] if 0 < t - refused < 0.5]
        assert not early, f"a sibling replica on the same key sent during the pause: {early}"

    def test_the_key_is_never_in_the_pause_key(self):
        from ciris_engine.logic.services.runtime.llm_service.provider_limits import budget_identity

        secret = "sk-or-v1-supersecret"
        url, digest = budget_identity("https://openrouter.ai/api/v1/", secret)
        assert secret not in url + digest and len(digest) == 16
        assert budget_identity("https://openrouter.ai/api/v1", secret) == (url, digest)
        assert budget_identity("https://openrouter.ai/api/v1", secret + "x")[1] != digest

    def test_a_service_without_identity_keys_on_its_name(self):
        assert LLMBus._budget_key(object(), "svc") == ("service", "svc")


class TestF3NoHedgeWhilePaused:
    def test_a_pause_suppresses_hedging_until_it_ends(self, fast_backoff):
        bus = _bus_with(RefusingProvider(None, 0))
        assert hedging.try_hedge(), "a fresh book affords one hedge"
        hedging.reset()
        fault = _refusal(IN_FLIGHT, retry_after="0.3").fault
        assert bus._pause_for_in_flight_budget("openrouter", "h", fault, 0, time.monotonic())
        assert not hedging.try_hedge(), "no hedge while the provider is paused"
        time.sleep(0.35)
        assert hedging.try_hedge(), "hedging resumes once the pause has passed"


class _SlowAfterRefusal(RefusingProvider):
    """A: refused once (after 50 ms). B, queued behind A, then holds the only slot for 3s."""

    async def call_llm_structured(
        self, messages: List[dict], response_model: Type[BaseModel], max_tokens: int = 1024, **_: Any
    ) -> Tuple[BaseModel, ResourceUsage]:
        who = messages[0]["content"]
        self.starts.append(time.monotonic())
        if who == "A" and not self.refused_at:
            await asyncio.sleep(0.05)  # B queues for the slot meanwhile
            self.refused_at.append(time.monotonic())
            raise _refusal(IN_FLIGHT, retry_after="0.1")
        if who == "B":
            await asyncio.sleep(3.0)
        return Answer(message="ok"), ResourceUsage(tokens_used=1, model_used="m")


class TestF4QueueTimeCountsAgainstTheDeadline:
    @pytest.mark.asyncio
    async def test_a_retry_stuck_in_the_queue_surfaces_the_refusal_in_time(self, fast_backoff, monkeypatch):
        monkeypatch.setenv("CIRIS_LLM_MAX_CONCURRENT", "1")
        provider = _SlowAfterRefusal(None, 0)
        bus = _bus_with(provider)
        started = time.monotonic()
        # 10.8s left: one useful attempt (10s) + 0.8s the retry may wait.
        with llm_call_deadline(10.8):
            a = asyncio.ensure_future(_named_call(bus, "A"))
            await asyncio.sleep(0.01)  # A holds the only slot
            b = asyncio.ensure_future(_named_call(bus, "B"))
            with pytest.raises(RuntimeError, match="in-flight spending budget"):
                await a
            a_done = time.monotonic() - started
            await b
        assert a_done < 2.0, f"the retry waited {a_done:.1f}s in the queue, past its deadline"


class TestF6BackoffIsSharedAcrossCalls:
    def test_sustained_refusals_raise_the_exponent_for_a_new_call(self, monkeypatch):
        seen: List[int] = []

        def record(attempt: int, retry_after: Optional[float]) -> float:
            seen.append(attempt)
            return 0.01

        monkeypatch.setattr(bus_module, "in_flight_backoff_s", record)
        bus = _bus_with(RefusingProvider(None, 0))
        fault = _refusal(IN_FLIGHT).fault
        for _ in range(3):  # three separate calls, each refused on its first attempt
            assert bus._pause_for_in_flight_budget("openrouter", "h", fault, 0, time.monotonic())
            time.sleep(0.02)  # the pause ends; the next refusal is a new episode
        assert seen == [0, 1, 2]

    def test_refusals_inside_one_pause_are_one_episode(self, monkeypatch):
        seen: List[int] = []
        monkeypatch.setattr(bus_module, "in_flight_backoff_s", lambda a, r: seen.append(a) or 5.0)
        bus = _bus_with(RefusingProvider(None, 0))
        fault = _refusal(IN_FLIGHT).fault
        for _ in range(4):  # a thought's parallel calls refused together
            bus._pause_for_in_flight_budget("openrouter", "h", fault, 0, time.monotonic())
        assert seen == [0, 0, 0, 0]

    @pytest.mark.asyncio
    async def test_a_success_resets_the_account_streak(self, fast_backoff):
        provider = RefusingProvider(lambda: _refusal(IN_FLIGHT), refusals=1)
        bus = _bus_with(provider)
        await _call(bus)
        assert dict(bus._in_flight_streak) == {}


class TestF7TooLargeIsNotABreakerFailure:
    @pytest.mark.asyncio
    async def test_six_too_large_requests_leave_the_breaker_closed(self, fast_backoff):
        provider = RefusingProvider(lambda: _refusal(WEIGHT), refusals=10_000)
        bus = _bus_with(provider)
        for _ in range(6):  # more than the breaker's threshold of 5
            with pytest.raises(RuntimeError, match="lower max_tokens or the prompt, or add credits"):
                await _call(bus)
        assert len(provider.starts) == 6, "sent once per call, never retried"
        breaker = bus.circuit_breakers.get("openrouter")
        assert breaker is None or breaker.state == CircuitState.CLOSED
        assert bus.service_metrics["openrouter"].failed_requests == 0


class TestF11InFlightRetriesAreNumbered:
    @pytest.mark.asyncio
    async def test_the_llm_call_event_counts_the_in_flight_retry(self, fast_backoff, monkeypatch):
        counts: List[Tuple[bool, int]] = []

        async def capture(ctx: Any) -> None:
            counts.append((ctx.success, ctx.retry_count))

        monkeypatch.setattr(bus_module, "_broadcast_llm_call_event", capture)
        bus = _bus_with(RefusingProvider(lambda: _refusal(IN_FLIGHT), refusals=2))
        await _call(bus)
        assert counts == [(False, 0), (False, 1), (True, 2)]
