"""Per-round cost must not grow with accumulated rows (load-spike RCA, memory benchmark).

The py-spy profile of the 1000-message burst showed every default-executor
thread inside `recall_timeseries` -> `_query_tsdb_nodes`, paging up to 1000
tsdb_data graph nodes per call, with the event loop decoding the rows. Two
per-thought callers drove it: the ACTION_COMPLETE resource lookup (six
recalls per thought) and the telemetry summary (one recall per metric type,
recomputed by every thought of a batch when the cache expired). The DMA prompt
templates were re-parsed by the pure-Python YAML loader on every DMA call.
Each test below fails against the old code path (see the negative checks).
"""

import asyncio
import threading
from datetime import datetime, timedelta, timezone
from typing import Any, List
from unittest.mock import MagicMock

import pytest

from ciris_engine.logic.buses.thought_resource_ledger import ThoughtResourceLedger, empty_resource_summary
from ciris_engine.logic.services.graph.telemetry_service import GraphTelemetryService
from ciris_engine.logic.utils.round_timing import RoundPhase, RoundPhaseTimer, format_phase_totals
from ciris_engine.schemas.runtime.memory import TimeSeriesDataPoint
from ciris_engine.schemas.runtime.resources import ResourceUsage


class _Clock:
    def now(self) -> datetime:
        return datetime.now(timezone.utc)

    def timestamp(self) -> float:
        return self.now().timestamp()


# --------------------------------------------------------------------------- #
# Per-thought resource totals: a dict lookup, not six graph scans
# --------------------------------------------------------------------------- #


def _usage(tokens: int, model: str = "m") -> ResourceUsage:
    return ResourceUsage(
        tokens_used=tokens,
        tokens_input=tokens - 1,
        tokens_output=1,
        cost_cents=0.5,
        carbon_grams=0.1,
        energy_kwh=0.000002,
        model_used=model,
    )


def test_ledger_totals_per_thought():
    ledger = ThoughtResourceLedger()
    ledger.record("th-1", _usage(10, "a"), "base-1")
    ledger.record("th-1", _usage(20, "b"), None)
    ledger.record("th-2", _usage(5), None)
    s = ledger.summary("th-1")
    assert s["tokens_total"] == 30 and s["tokens_input"] == 28 and s["tokens_output"] == 2
    assert s["llm_calls"] == 2
    assert s["cost_cents"] == pytest.approx(1.0)
    assert s["energy_mwh"] == pytest.approx(4.0)
    assert s["models_used"] == ["a", "b"] and s["api_bases_used"] == ["base-1", "default"]
    assert ledger.summary("unknown") == empty_resource_summary()


def test_ledger_is_bounded():
    ledger = ThoughtResourceLedger(max_thoughts=3)
    for i in range(10):
        ledger.record(f"th-{i}", _usage(1), None)
    assert len(ledger) == 3
    assert ledger.summary("th-0")["llm_calls"] == 0
    assert ledger.summary("th-9")["llm_calls"] == 1


@pytest.mark.asyncio
async def test_llm_bus_records_into_the_ledger_even_without_telemetry():
    from ciris_engine.logic.buses import llm_bus as llm_bus_module
    from ciris_engine.logic.buses.llm_bus import LLMBus
    from ciris_engine.logic.registries.base import ServiceRegistry

    bus = LLMBus(service_registry=ServiceRegistry(), time_service=_Clock(), telemetry_service=None)  # type: ignore[arg-type]
    await bus._record_resource_telemetry("svc", "Handler", _usage(42), 1.0, thought_id="th-ledger", api_base="b")
    assert llm_bus_module.thought_resource_ledger.summary("th-ledger")["tokens_total"] == 42


@pytest.mark.asyncio
async def test_action_complete_reads_the_ledger_not_the_graph():
    from ciris_engine.logic.buses.thought_resource_ledger import thought_resource_ledger
    from ciris_engine.logic.processors.core import step_decorators
    from ciris_engine.schemas.services.runtime_control import StepPoint

    thought_resource_ledger.record("th-ac", _usage(7), None)
    telemetry = MagicMock()
    processor = MagicMock(telemetry_service=telemetry)
    kwargs: dict = {}
    await step_decorators._maybe_add_resource_usage(StepPoint.ACTION_COMPLETE, processor, "th-ac", None, kwargs)
    assert kwargs["_resource_usage"]["tokens_total"] == 7
    telemetry.query_metrics.assert_not_called()  # negative: the old path queried the graph six times
    assert not hasattr(step_decorators, "_query_thought_resources")


# --------------------------------------------------------------------------- #
# Telemetry summary: one recall per computation, one computation per expiry
# --------------------------------------------------------------------------- #


class _CountingBus:
    def __init__(self, points: List[TimeSeriesDataPoint]) -> None:
        self.points = points
        self.recalls = 0

    async def recall_timeseries(self, **_: Any) -> List[TimeSeriesDataPoint]:
        self.recalls += 1
        await asyncio.sleep(0.01)  # a real recall yields to the loop
        return list(self.points)


def _point(name: str, value: float) -> TimeSeriesDataPoint:
    return TimeSeriesDataPoint(
        timestamp=datetime.now(timezone.utc) - timedelta(minutes=1),
        metric_name=name,
        value=value,
        correlation_type="METRIC_DATAPOINT",
        tags={},
    )


@pytest.mark.asyncio
async def test_query_metric_set_recalls_once_for_many_names():
    bus = _CountingBus([_point("a", 1), _point("b", 2), _point("a", 3), _point("c", 9)])
    telemetry = GraphTelemetryService(memory_bus=bus, time_service=_Clock())  # type: ignore[arg-type]
    now = datetime.now(timezone.utc)
    by_name = await telemetry.query_metric_set(["a", "b", "z"], start_time=now - timedelta(hours=1), end_time=now)
    assert bus.recalls == 1
    assert [r.value for r in by_name["a"]] == [1, 3]
    assert [r.value for r in by_name["b"]] == [2]
    assert by_name["z"] == []
    # query_metrics keeps its contract
    assert [r.value for r in await telemetry.query_metrics("a", start_time=now - timedelta(hours=1), end_time=now)] == [1, 3]


@pytest.mark.asyncio
async def test_metric_aggregates_cost_one_recall():
    from ciris_engine.logic.services.graph.telemetry_service.helpers import METRIC_TYPES, collect_metric_aggregates

    bus = _CountingBus([_point("llm.tokens.total", 100), _point("thought_processing_completed", 1)])
    telemetry = GraphTelemetryService(memory_bus=bus, time_service=_Clock())  # type: ignore[arg-type]
    now = datetime.now(timezone.utc)
    agg = await collect_metric_aggregates(telemetry, METRIC_TYPES, now - timedelta(hours=24), now - timedelta(hours=1), now)
    assert bus.recalls == 1  # negative: was len(METRIC_TYPES)
    assert len(METRIC_TYPES) > 1
    assert agg.tokens_24h == 100


@pytest.mark.asyncio
async def test_concurrent_summary_misses_compute_once(monkeypatch):
    from ciris_engine.logic.services.graph.telemetry_service import service as telemetry_module

    async def _depth(*_: Any) -> float:
        return 1.0

    monkeypatch.setattr(telemetry_module, "get_average_thought_depth", _depth)
    bus = _CountingBus([_point("llm.tokens.total", 5)])
    telemetry = GraphTelemetryService(memory_bus=bus, time_service=_Clock())  # type: ignore[arg-type]
    telemetry._start_time = datetime.now(timezone.utc)
    computed = 0
    real = telemetry._compute_telemetry_summary

    async def _counting(*args: Any, **kwargs: Any) -> Any:
        nonlocal computed
        computed += 1
        return await real(*args, **kwargs)

    telemetry._compute_telemetry_summary = _counting  # type: ignore[method-assign]
    results = await asyncio.gather(*(telemetry.get_telemetry_summary() for _ in range(50)), return_exceptions=True)
    assert computed == 1  # negative: 50 concurrent misses each recomputed
    assert len({id(r) for r in results}) == 1


# --------------------------------------------------------------------------- #
# Time-series rows are decoded off the event loop
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_recall_timeseries_decodes_rows_on_the_worker(monkeypatch):
    import json

    from ciris_engine.logic.persistence.models import graph as graph_model
    from ciris_engine.logic.services.graph.memory_service import LocalGraphMemoryService

    now = datetime.now(timezone.utc)
    decoded_on: List[str] = []
    real_point = TimeSeriesDataPoint

    class _Engine:
        def cirisgraph_query_nodes(self, filter_json: str, cursor_json: str, page: int) -> str:
            if json.loads(cursor_json)["last_id"]:
                return json.dumps({"items": []})
            attrs = {"metric_name": "m", "value": 1.0, "created_at": now.isoformat(), "labels": {"k": "v"}}
            row = {"node_id": "n1", "created_at": now.isoformat(), "attributes": json.dumps(attrs)}
            return json.dumps({"items": [row]})

    def _point_spy(**kwargs: Any) -> TimeSeriesDataPoint:
        decoded_on.append(threading.current_thread().name)
        return real_point(**kwargs)

    from ciris_engine.logic.services.graph import memory_service as ms_module

    monkeypatch.setattr(graph_model, "get_persist_engine", lambda: _Engine())
    monkeypatch.setattr(ms_module, "TimeSeriesDataPoint", _point_spy)
    service = LocalGraphMemoryService.__new__(LocalGraphMemoryService)
    service._time_service = _Clock()
    service._track_request = lambda: None  # type: ignore[method-assign]
    points = await service.recall_timeseries(scope="local", start_time=now - timedelta(hours=1), end_time=now + timedelta(seconds=1))
    assert [p.metric_name for p in points] == ["m"]
    assert decoded_on and threading.main_thread().name not in decoded_on


# --------------------------------------------------------------------------- #
# DMA prompt templates are parsed once per file version
# --------------------------------------------------------------------------- #


def test_prompt_template_parsed_once_and_reparsed_when_edited(tmp_path, monkeypatch):
    from ciris_engine.logic.dma import prompt_loader as pl

    monkeypatch.setattr(pl, "_TEMPLATE_DATA_CACHE", {})
    template = tmp_path / "probe.yml"
    template.write_text("system_guidance_header: |\n  first\n", encoding="utf-8")
    parses = []
    real_load = pl.yaml.load
    monkeypatch.setattr(pl.yaml, "load", lambda text, Loader: parses.append(1) or real_load(text, Loader=Loader))
    loader = pl.DMAPromptLoader(prompts_dir=str(tmp_path))

    first = loader.load_prompt_template("probe")
    second = loader.load_prompt_template("probe")
    assert len(parses) == 1  # negative: parsed on every call before
    assert first.system_guidance_header == second.system_guidance_header == "first\n"

    template.write_text("system_guidance_header: |\n  second, longer\n", encoding="utf-8")
    assert loader.load_prompt_template("probe").system_guidance_header == "second, longer\n"
    assert len(parses) == 2


def test_prompt_cache_is_bypassed_under_research_overrides(tmp_path, monkeypatch):
    from ciris_engine.logic.dma import prompt_loader as pl
    from ciris_engine.logic.utils import research_overrides

    monkeypatch.setattr(pl, "_TEMPLATE_DATA_CACHE", {})
    monkeypatch.setattr(research_overrides, "get_active_overrides", lambda: object())
    monkeypatch.setattr(pl, "_apply_research_overrides", lambda name, coll: coll)
    (tmp_path / "probe.yml").write_text("system_guidance_header: x\n", encoding="utf-8")
    loader = pl.DMAPromptLoader(prompts_dir=str(tmp_path))
    loader.load_prompt_template("probe")
    assert pl._TEMPLATE_DATA_CACHE == {}


def test_shipped_templates_parse_identically_with_the_fast_loader():
    import glob
    from pathlib import Path

    import yaml

    from ciris_engine.logic.dma import prompt_loader as pl

    files = glob.glob(str(Path(pl.__file__).parent / "prompts" / "**" / "*.yml"), recursive=True)
    assert files
    for path in files:
        text = Path(path).read_text(encoding="utf-8")
        assert yaml.load(text, Loader=pl._YAML_SAFE_LOADER) == yaml.safe_load(text), path


# --------------------------------------------------------------------------- #
# Round phase timing
# --------------------------------------------------------------------------- #


def test_round_phase_timer_accumulates_and_drains():
    timer = RoundPhaseTimer()
    timer.record(RoundPhase.DMA, 1.0)
    timer.record(RoundPhase.DMA, 3.0)
    timer.record(RoundPhase.CONTEXT, 0.5)
    timer.note_loop_lag(0.2)
    timer.note_loop_lag(1.5)
    totals, lag = timer.drain()
    assert totals[RoundPhase.DMA].seconds == 4.0 and totals[RoundPhase.DMA].count == 2
    assert totals[RoundPhase.DMA].max_seconds == 3.0
    assert lag == 1.5
    assert format_phase_totals(totals) == "context 0.5s/1 (max 0.5s), dma 4.0s/2 (max 3.0s)"
    assert timer.drain() == ({}, 0.0)


# --------------------------------------------------------------------------- #
# Persistence hot paths: count, find, or take the newest -- never materialize all
# --------------------------------------------------------------------------- #


class _PagingEngine:
    """A persist engine double serving `*_list` / `correlation_query` pages DESC by created_at."""

    def __init__(self, rows: List[dict], id_key: str) -> None:
        self.rows = sorted(rows, key=lambda r: r["created_at"], reverse=True)
        self.id_key = id_key
        self.pages_served = 0

    def _page(self, filter_json: str, cursor_json: str, page_size: int) -> str:
        import json

        flt = json.loads(filter_json)
        cursor = json.loads(cursor_json)
        rows = [r for r in self.rows if all(r.get(k) == v for k, v in flt.items() if k in ("status", "correlation_type"))]
        if cursor["last_id"]:
            idx = next(i for i, r in enumerate(rows) if r[self.id_key] == cursor["last_id"])
            rows = rows[idx + 1 :]
        self.pages_served += 1
        return json.dumps({"items": rows[:page_size]})

    task_list = thought_list = correlation_query = _page


def _task_rows(n: int, status: str = "completed") -> List[dict]:
    import json

    return [
        {
            "task_id": f"task-{i:05d}",
            "channel_id": "c",
            "description": "d",
            "status": status,
            "priority": 0,
            "created_at": f"2026-10-29T00:{i // 60:02d}:{i % 60:02d}Z",
            "updated_at": f"2026-10-29T00:{i // 60:02d}:{i % 60:02d}Z",
            "context": json.dumps({"correlation_id": f"corr-{i}"}),
        }
        for i in range(n)
    ]


def test_count_tasks_does_not_build_task_models(monkeypatch):
    from ciris_engine.logic.persistence.models import tasks as tasks_model

    engine = _PagingEngine(_task_rows(450), "task_id")
    monkeypatch.setattr(tasks_model, "_get_engine", lambda: engine)
    monkeypatch.setattr(tasks_model, "_persist_row_to_task", lambda row: pytest.fail("materialized a row to count"))
    assert tasks_model.count_tasks() == 450


def test_count_thoughts_by_status_does_not_build_thought_models(monkeypatch):
    from ciris_engine.logic.persistence.models import thoughts as thoughts_model
    from ciris_engine.schemas.runtime.enums import ThoughtStatus

    rows = [
        {"thought_id": f"th-{i}", "status": "completed" if i % 3 else "pending", "created_at": f"2026-10-29T{i:06d}"}
        for i in range(300)
    ]
    engine = _PagingEngine(rows, "thought_id")
    monkeypatch.setattr(thoughts_model, "_get_engine", lambda: engine)
    monkeypatch.setattr(thoughts_model, "_persist_row_to_thought", lambda row: pytest.fail("materialized a row"))
    assert thoughts_model.count_thoughts_by_status(ThoughtStatus.PENDING) == 100
    assert thoughts_model.count_thoughts_by_status(ThoughtStatus.COMPLETED) == 200


class _IndexedEngine(_PagingEngine):
    """Adds the point read the correlation index confirms hits with."""

    def task_get(self, task_id: str) -> Any:
        import json

        row = next((r for r in self.rows if r["task_id"] == task_id), None)
        return json.dumps(row) if row is not None else None

    def insert(self, row: dict) -> None:
        self.rows.insert(0, row)
        self.rows.sort(key=lambda r: r["created_at"], reverse=True)


def test_task_by_correlation_id_reads_only_new_rows(monkeypatch):
    import json

    from ciris_engine.logic.persistence.models import tasks as tasks_model

    engine = _IndexedEngine(_task_rows(450), "task_id")
    built: List[str] = []
    real = tasks_model._persist_row_to_task
    monkeypatch.setattr(tasks_model, "_get_engine", lambda: engine)
    monkeypatch.setattr(tasks_model, "_correlation_indexes", {})
    monkeypatch.setattr(tasks_model, "_persist_row_to_task", lambda row: built.append(row["task_id"]) or real(row))

    found = tasks_model.get_task_by_correlation_id("corr-440")  # first lookup indexes the history once
    assert found is not None and found.task_id == "task-00440"
    assert built == ["task-00440"]  # only the match is materialized
    warm_pages = engine.pages_served

    # a new message: a miss, answered from the index plus the one new row
    assert tasks_model.get_task_by_correlation_id("corr-new") is None
    assert engine.pages_served - warm_pages == 1  # negative: the old scan paged all 450 rows per lookup
    new_row = dict(_task_rows(1)[0], task_id="task-new", created_at="2026-10-29T01:00:00Z",
                   context=json.dumps({"correlation_id": "corr-new"}))
    engine.insert(new_row)
    before = engine.pages_served
    found_new = tasks_model.get_task_by_correlation_id("corr-new")  # written by anyone: still found
    assert found_new is not None and found_new.task_id == "task-new"
    assert engine.pages_served - before == 1


def test_a_deleted_indexed_task_falls_back_to_the_scan(monkeypatch):
    import json

    from ciris_engine.logic.persistence.models import tasks as tasks_model

    rows = _task_rows(30)
    rows.append(dict(rows[5], task_id="task-dup-newer", created_at="2026-10-29T00:59:00Z"))  # same corr-5, newer
    engine = _IndexedEngine(rows, "task_id")
    monkeypatch.setattr(tasks_model, "_get_engine", lambda: engine)
    monkeypatch.setattr(tasks_model, "_correlation_indexes", {})
    assert tasks_model.get_task_by_correlation_id("corr-5").task_id == "task-dup-newer"  # the newest match
    engine.rows = [r for r in engine.rows if r["task_id"] != "task-dup-newer"]  # deleted
    assert tasks_model.get_task_by_correlation_id("corr-5").task_id == "task-00005"  # the older one, via the scan
    assert tasks_model.get_task_by_correlation_id("corr-5").task_id == "task-00005"  # and re-indexed
    assert tasks_model.get_task_by_correlation_id("corr-none") is None


def test_recent_completed_tasks_reads_a_bounded_window(monkeypatch):
    from ciris_engine.logic.persistence.models import tasks as tasks_model

    engine = _PagingEngine(_task_rows(2000), "task_id")
    monkeypatch.setattr(tasks_model, "_get_engine", lambda: engine)
    monkeypatch.setattr(tasks_model, "_recent_completed_cache", {})
    recent = tasks_model.get_recent_completed_tasks(limit=10)
    assert [t.task_id for t in recent] == [f"task-{i:05d}" for i in range(1999, 1989, -1)]
    assert engine.pages_served == 1  # negative: all 2000 tasks (10 pages) before
    # the rest of the round's thoughts are served the same answer
    for _ in range(48):
        assert [t.task_id for t in tasks_model.get_recent_completed_tasks(limit=10)] == [t.task_id for t in recent]
    assert engine.pages_served == 1
    monkeypatch.setattr(tasks_model.time, "monotonic", lambda: 10**9)  # TTL passed
    tasks_model.get_recent_completed_tasks(limit=10)
    assert engine.pages_served == 2


def test_channel_history_stops_once_it_has_enough(monkeypatch):
    import json

    from ciris_engine.logic.persistence.models import correlations as corr_model

    rows = [
        {
            "correlation_id": f"corr-{i:05d}",
            "correlation_type": "service_interaction",
            "action_type": "speak",
            "service_type": "api",
            "handler_name": "h",
            "status": "completed",
            "created_at": f"2026-10-29T00:{i // 60:02d}:{i % 60:02d}Z",
            "updated_at": f"2026-10-29T00:{i // 60:02d}:{i % 60:02d}Z",
            "timestamp": f"2026-10-29T00:{i // 60:02d}:{i % 60:02d}Z",
            "request_data": json.dumps(
                {
                    "channel_id": "chan",
                    "service_type": "api",
                    "method_name": "send_message",
                    "request_timestamp": "2026-10-29T00:00:00Z",
                }
            ),
        }
        for i in range(2000)
    ]
    engine = _PagingEngine(rows, "correlation_id")
    monkeypatch.setattr(corr_model, "_get_engine", lambda: engine)
    history = corr_model.get_correlations_by_channel("chan", limit=20)
    assert len(history) == 20
    assert engine.pages_served == 1  # negative: every correlation ever recorded was paged
    assert [c.correlation_id for c in history][-1] == "corr-01999"  # oldest-first, newest last


def test_queue_status_is_reused_within_its_ttl(monkeypatch):
    from ciris_engine.logic.persistence.models import queue_status as qs

    calls: List[int] = []
    monkeypatch.setattr(qs, "_queue_status_cache", {})
    monkeypatch.setattr(qs, "count_tasks", lambda status=None: calls.append(1) or 3)
    monkeypatch.setattr(qs, "count_thoughts_by_status", lambda status: 2)
    first = qs.get_queue_status()
    second = qs.get_queue_status()
    assert first is second and len(calls) == 2  # one computation (2 task counts) for both calls
    monkeypatch.setattr(qs.time, "monotonic", lambda: 10**9)
    qs.get_queue_status()
    assert len(calls) == 4  # expired: recomputed


@pytest.mark.asyncio
async def test_graph_node_write_runs_off_the_loop(monkeypatch):
    from ciris_engine.logic.persistence.models import graph as graph_model
    from ciris_engine.logic.services.graph.memory_service import LocalGraphMemoryService
    from ciris_engine.schemas.services.graph_core import GraphNode, GraphScope, NodeType

    threads: List[str] = []
    monkeypatch.setattr(graph_model, "add_graph_node", lambda node, time_service=None: threads.append(threading.current_thread().name))
    service = LocalGraphMemoryService.__new__(LocalGraphMemoryService)
    service._time_service = _Clock()
    service._track_request = lambda: None  # type: ignore[method-assign]

    async def _same(node: Any) -> Any:
        return node

    service._process_secrets_for_memorize = _same  # type: ignore[method-assign]
    node = GraphNode(id="n1", type=NodeType.CONCEPT, scope=GraphScope.LOCAL, attributes={}, updated_by="t")
    result = await service.memorize(node)
    assert result.status.value == "ok"
    assert threads and threads[0] != threading.main_thread().name  # negative: ran on the loop


def test_aspdma_schema_is_built_only_where_used(monkeypatch):
    from ciris_engine.logic.dma.action_selection.action_instruction_generator import ActionInstructionGenerator
    from ciris_engine.schemas.runtime.enums import HandlerActionType

    gen = ActionInstructionGenerator.__new__(ActionInstructionGenerator)
    built: List[str] = []
    for action, cls in ActionInstructionGenerator.ACTION_PARAM_SCHEMAS.items():
        monkeypatch.setattr(cls, "model_json_schema", classmethod(lambda c, *a, **k: built.append(c.__name__) or {}))
    assert gen._generate_schema_for_action(HandlerActionType.SPEAK).startswith("SPEAK:")
    assert gen._generate_schema_for_action(HandlerActionType.TASK_COMPLETE).startswith("TASK_COMPLETE:")
    assert built == []  # negative: computed and discarded for every action before


@pytest.mark.asyncio
async def test_secrets_scan_runs_off_the_loop(monkeypatch):
    from ciris_engine.logic.secrets import service as secrets_module

    threads: List[str] = []

    class _Engine:
        def secrets_process_incoming_text(self, text: str, source: str, actor: str) -> str:
            threads.append(threading.current_thread().name)
            return '{"filtered_text": "x", "refs": []}'

    monkeypatch.setattr(secrets_module, "_get_engine", lambda: _Engine())
    svc = secrets_module.SecretsService.__new__(secrets_module.SecretsService)
    assert await svc.process_incoming_text("hello", "m1") == ("hello", [])
    assert threads and threads[0] != threading.main_thread().name  # negative: the scan ran on the loop
