"""Unit tests for the TSDB Consolidation Service cadence-caller.

2.9.7 DRY purge (wave 2): the service is a thin cadence-caller over the
persist substrate. Persist's consolidators are idempotent and internally
locked, so the agent-side lock wrappers, missed-window bookkeeping, and
edge repair were deleted along with their tests.

Remaining coverage:
- start/stop lifecycle
- cadence boundary math (PeriodManager.get_next_period_start)
- `_run_consolidation` iterates every complete period in the retention window
- TSDBSummary <-> GraphNode round-trip
- `get_capabilities` / `get_status` / `get_node_type`
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, Mock, patch

import pytest

from ciris_engine.logic.services.graph.tsdb_consolidation import TSDBConsolidationService
from ciris_engine.schemas.services.core import ServiceCapabilities, ServiceStatus
from ciris_engine.schemas.services.graph_core import GraphScope, NodeType
from ciris_engine.schemas.services.nodes import TSDBSummary
from ciris_engine.schemas.services.operations import MemoryOpResult, MemoryOpStatus


@pytest.fixture
def mock_memory_bus():
    """Create a mock memory bus."""
    mock = Mock()
    mock.memorize = AsyncMock(return_value=MemoryOpResult(status=MemoryOpStatus.OK))
    mock.recall = AsyncMock(return_value=[])
    mock.search = AsyncMock(return_value=[])
    mock.forget = AsyncMock(return_value=Mock(status="ok"))
    return mock


@pytest.fixture
def mock_time_service():
    """Create a mock time service."""
    mock = Mock()
    mock.now = Mock(return_value=datetime.now(timezone.utc))
    return mock


@pytest.fixture
def tsdb_service(mock_memory_bus, mock_time_service, persist_engine):
    """Create a TSDB consolidation service wired to the test persist engine."""
    service = TSDBConsolidationService(
        memory_bus=mock_memory_bus,
        time_service=mock_time_service,
    )
    yield service


@pytest.mark.asyncio
async def test_tsdb_service_lifecycle(tsdb_service):
    """Test TSDBConsolidationService start/stop lifecycle."""
    await tsdb_service.start()
    assert tsdb_service._running is True

    await tsdb_service.stop()
    assert tsdb_service._running is False


@pytest.mark.asyncio
async def test_tsdb_service_cadence_boundaries(tsdb_service, mock_time_service):
    """The cadence loop wakes at 6-hour UTC boundaries."""
    current_time = datetime(2024, 12, 22, 14, 30, 0, tzinfo=timezone.utc)
    mock_time_service.now.return_value = current_time

    next_run = tsdb_service._period_manager.get_next_period_start(current_time)
    assert next_run == datetime(2024, 12, 22, 18, 0, 0, tzinfo=timezone.utc)

    # Midnight rollover
    current_time = datetime(2024, 12, 22, 23, 30, 0, tzinfo=timezone.utc)
    next_run = tsdb_service._period_manager.get_next_period_start(current_time)
    assert next_run == datetime(2024, 12, 23, 0, 0, 0, tzinfo=timezone.utc)


@pytest.mark.asyncio
async def test_run_consolidation_covers_retention_window(tsdb_service, mock_time_service):
    """`_run_consolidation` calls `_consolidate_period` once per complete
    6h period in the raw-retention window (substrate is idempotent)."""
    now = datetime(2024, 12, 22, 14, 30, 0, tzinfo=timezone.utc)
    mock_time_service.now.return_value = now

    with patch.object(tsdb_service, "_consolidate_period", new_callable=AsyncMock, return_value=[]) as mock_cp:
        with patch.object(tsdb_service, "_cleanup_old_data", return_value=0):
            await tsdb_service._run_consolidation()

    # Window: period containing (now - 24h) = 2024-12-21T12:00 up to the
    # period containing now (exclusive) = 2024-12-22T12:00 → 4 periods.
    assert mock_cp.call_count == 4
    starts = [call.args[0] for call in mock_cp.call_args_list]
    assert starts[0] == datetime(2024, 12, 21, 12, 0, 0, tzinfo=timezone.utc)
    assert starts[-1] == datetime(2024, 12, 22, 6, 0, 0, tzinfo=timezone.utc)
    # Each call spans exactly one interval
    for call in mock_cp.call_args_list:
        assert call.args[1] - call.args[0] == timedelta(hours=6)
    assert tsdb_service._last_consolidation == now


@pytest.mark.asyncio
async def test_consolidate_period_invokes_substrate(tsdb_service, persist_engine):
    """`_consolidate_period` drives the 5 persist consolidators and reads
    back typed summaries without raising on an empty corpus."""
    period_start = datetime(2024, 12, 22, 0, 0, 0, tzinfo=timezone.utc)
    period_end = period_start + timedelta(hours=6)

    summaries = await tsdb_service._consolidate_period(period_start, period_end)
    assert isinstance(summaries, list)


def test_tsdb_service_capabilities(tsdb_service):
    """Test TSDBConsolidationService.get_capabilities() returns correct info."""
    caps = tsdb_service.get_capabilities()

    assert isinstance(caps, ServiceCapabilities)
    assert caps.service_name == "TSDBConsolidationService"
    assert "consolidate_tsdb_nodes" in caps.actions
    assert "create_6hour_summaries" in caps.actions
    assert "consolidate_all_data" in caps.actions


def test_tsdb_service_status(tsdb_service):
    """Test TSDBConsolidationService.get_status() returns correct status."""
    status = tsdb_service.get_status()

    assert isinstance(status, ServiceStatus)
    assert status.service_name == "TSDBConsolidationService"
    assert status.service_type == "graph_service"
    assert "last_consolidation_timestamp" in status.metrics
    assert "task_running" in status.metrics
    assert isinstance(status.metrics["last_consolidation_timestamp"], float)
    assert isinstance(status.metrics["task_running"], float)


@pytest.mark.asyncio
async def test_tsdb_service_typed_node_conversion(tsdb_service):
    """Test TSDBSummary TypedGraphNode conversion."""
    summary = TSDBSummary(
        id="test_summary_20241222_00",
        scope=GraphScope.LOCAL,
        attributes={},
        period_start=datetime(2024, 12, 22, 0, 0, 0, tzinfo=timezone.utc),
        period_end=datetime(2024, 12, 22, 6, 0, 0, tzinfo=timezone.utc),
        period_label="2024-12-22-night",
        metrics={"test.metric": {"count": 10.0, "sum": 1000.0, "min": 50.0, "max": 150.0, "avg": 100.0}},
        total_tokens=5000,
        total_cost_cents=10.5,
        total_carbon_grams=15.3,
        action_counts={"SPEAK": 5, "TOOL": 3},
        error_count=1,
        success_rate=0.95,
        source_node_count=100,
    )

    # Convert to GraphNode
    graph_node = summary.to_graph_node()

    assert graph_node.id == "test_summary_20241222_00"
    assert graph_node.type == NodeType.TSDB_SUMMARY
    assert graph_node.scope == GraphScope.LOCAL
    assert isinstance(graph_node.attributes, dict)
    assert graph_node.attributes["period_label"] == "2024-12-22-night"
    assert graph_node.attributes["total_tokens"] == 5000
    assert graph_node.attributes["node_class"] == "TSDBSummary"

    # Convert back from GraphNode
    reconstructed = TSDBSummary.from_graph_node(graph_node)

    assert reconstructed.id == summary.id
    assert reconstructed.period_start == summary.period_start
    assert reconstructed.period_end == summary.period_end
    assert reconstructed.period_label == summary.period_label
    assert reconstructed.metrics == summary.metrics
    assert reconstructed.total_tokens == summary.total_tokens
    assert reconstructed.total_cost_cents == summary.total_cost_cents
    assert reconstructed.action_counts == summary.action_counts
    assert reconstructed.source_node_count == summary.source_node_count


@pytest.mark.asyncio
async def test_tsdb_service_node_type(tsdb_service):
    """Test that TSDBConsolidationService manages TSDB_SUMMARY nodes."""
    node_type = tsdb_service.get_node_type()
    assert node_type == NodeType.TSDB_SUMMARY
