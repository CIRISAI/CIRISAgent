"""One LLM call must be counted once in the telemetry token aggregates.

Drives a single call through the real LLMBus -> real LLM service -> real
GraphTelemetryService path, then aggregates with the same reader that feeds
``TelemetrySummary.tokens_last_hour`` / ``tokens_24h``
(``collect_metric_aggregates`` over ``METRIC_TYPES``).

Before the fix, every call was summed from several series that describe the
same tokens:

- ``llm.tokens.total``  (LLMBus, every provider)
- ``llm.tokens.input`` + ``llm.tokens.output``  (LLMBus; together == total)
- ``llm_tokens_used``  (OpenAICompatibleClient only, legacy alias)

That gave 3x on the real-provider path and 2x on the mock LLM path.
"""

import os
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional
from unittest.mock import MagicMock, patch

import pytest
from pydantic import BaseModel

from ciris_engine.logic.buses.llm_bus import DistributionStrategy, LLMBus
from ciris_engine.logic.registries.base import Priority, ServiceRegistry
from ciris_engine.logic.services.graph.telemetry_service import GraphTelemetryService
from ciris_engine.logic.services.graph.telemetry_service.helpers import METRIC_TYPES, collect_metric_aggregates
from ciris_engine.logic.services.runtime.llm_service import OpenAICompatibleClient, OpenAIConfig
from ciris_engine.schemas.runtime.enums import ServiceType
from ciris_engine.schemas.runtime.memory import TimeSeriesDataPoint
from ciris_engine.schemas.runtime.resources import ResourceUsage
from ciris_engine.schemas.services.llm import LLMMessage
from ciris_engine.schemas.services.operations import MemoryOpResult, MemoryOpStatus


class _Answer(BaseModel):
    message: str


class _Clock:
    """Real wall-clock time service (the bus needs timestamp(), telemetry needs now())."""

    def now(self) -> datetime:
        return datetime.now(timezone.utc)

    def timestamp(self) -> float:
        return self.now().timestamp()


class _InMemoryMetricBus:
    """Memory bus double: stores every metric the telemetry service writes and
    serves them back through recall_timeseries, like the graph does."""

    def __init__(self) -> None:
        self.points: List[TimeSeriesDataPoint] = []

    async def memorize_metric(
        self, metric_name: str, value: float, tags: Optional[Dict[str, str]] = None, **_: object
    ) -> MemoryOpResult[None]:
        self.points.append(
            TimeSeriesDataPoint(
                timestamp=datetime.now(timezone.utc),
                metric_name=metric_name,
                value=float(value),
                correlation_type="METRIC_DATAPOINT",
                tags={k: str(v) for k, v in (tags or {}).items()},
            )
        )
        return MemoryOpResult[None](status=MemoryOpStatus.OK)

    async def recall_timeseries(self, **_: object) -> List[TimeSeriesDataPoint]:
        return list(self.points)


def _telemetry() -> tuple[GraphTelemetryService, _InMemoryMetricBus]:
    bus = _InMemoryMetricBus()
    return GraphTelemetryService(memory_bus=bus, time_service=_Clock()), bus  # type: ignore[arg-type]


def _llm_bus(registry: ServiceRegistry, telemetry: GraphTelemetryService) -> LLMBus:
    return LLMBus(
        service_registry=registry,
        time_service=_Clock(),  # type: ignore[arg-type]
        telemetry_service=telemetry,  # type: ignore[arg-type]
        distribution_strategy=DistributionStrategy.ROUND_ROBIN,
    )


async def _aggregated_tokens(telemetry: GraphTelemetryService) -> tuple[int, int]:
    now = datetime.now(timezone.utc)
    agg = await collect_metric_aggregates(
        telemetry, METRIC_TYPES, now - timedelta(hours=24), now - timedelta(hours=1), now + timedelta(seconds=5)
    )
    return agg.tokens_24h, agg.tokens_1h


@pytest.mark.asyncio
async def test_one_real_provider_call_is_counted_once() -> None:
    """OpenAICompatibleClient path: writes llm_tokens_used AND the bus writes
    llm.tokens.total/input/output. Aggregate must equal the call's tokens_used."""
    telemetry, metric_bus = _telemetry()

    config = OpenAIConfig(api_key="test-key-12345", model_name="gpt-4o-mini", instructor_mode="JSON")
    with patch.dict(os.environ, {"MOCK_LLM": ""}, clear=False), patch("sys.argv", []):
        with patch("ciris_engine.logic.services.runtime.llm_service.service.AsyncOpenAI"):
            with patch("ciris_engine.logic.services.runtime.llm_service.service.instructor"):
                service = OpenAICompatibleClient(config=config, time_service=_Clock(), telemetry_service=telemetry)  # type: ignore[arg-type]

    completion = MagicMock(spec=["usage"])
    completion.usage = MagicMock(prompt_tokens=100, completion_tokens=50)

    async def create_with_completion(*_: object, **__: object) -> tuple[_Answer, MagicMock]:
        return _Answer(message="hi"), completion

    service.instruct_client = MagicMock()
    service.instruct_client.chat.completions.create_with_completion.side_effect = create_with_completion

    registry = ServiceRegistry()
    registry.register_service(
        service_type=ServiceType.LLM,
        provider=service,
        priority=Priority.NORMAL,
        capabilities=["call_llm_structured"],
    )
    llm_bus = _llm_bus(registry, telemetry)

    _, usage = await llm_bus.call_llm_structured(
        messages=[LLMMessage(role="user", content="hello")],
        response_model=_Answer,
        handler_name="test_handler",
    )
    assert isinstance(usage, ResourceUsage)
    assert usage.tokens_used == 150

    # Precondition: every duplicate series really was written for this call,
    # so the assertion below is not vacuous.
    written = {p.metric_name for p in metric_bus.points}
    assert {"llm.tokens.total", "llm.tokens.input", "llm.tokens.output", "llm_tokens_used"} <= written

    tokens_24h, tokens_1h = await _aggregated_tokens(telemetry)
    assert tokens_24h == usage.tokens_used, f"one call counted {tokens_24h / usage.tokens_used:g}x"
    assert tokens_1h == usage.tokens_used


@pytest.mark.asyncio
async def test_one_mock_llm_call_is_counted_once() -> None:
    """Mock LLM path: only the bus writes (total + input + output)."""
    from ciris_adapters.mock_llm.service import MockLLMService

    telemetry, metric_bus = _telemetry()
    service = MockLLMService()
    await service.start()
    try:
        registry = ServiceRegistry()
        registry.register_service(
            service_type=ServiceType.LLM,
            provider=service,
            priority=Priority.NORMAL,
            capabilities=["call_llm_structured"],
        )
        llm_bus = _llm_bus(registry, telemetry)

        _, usage = await llm_bus.call_llm_structured(
            messages=[LLMMessage(role="user", content="hello there agent")],
            response_model=_Answer,
            handler_name="test_handler",
        )
    finally:
        await service.stop()

    written = {p.metric_name for p in metric_bus.points}
    assert {"llm.tokens.total", "llm.tokens.input", "llm.tokens.output"} <= written
    assert usage.tokens_used > 0

    tokens_24h, tokens_1h = await _aggregated_tokens(telemetry)
    assert tokens_24h == usage.tokens_used, f"one call counted {tokens_24h / usage.tokens_used:g}x"
    assert tokens_1h == usage.tokens_used
