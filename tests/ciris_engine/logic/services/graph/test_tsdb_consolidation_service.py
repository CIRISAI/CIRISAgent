"""Unit tests for TSDB Consolidation Service.

Post-A1 absorption (CIRISAgent#763, CIRISPersist#63): the consolidation
service routes through persist substrate methods (`tsdb_consolidate_*`,
`tsdb_prune_summaries`, `lock_try_acquire`). The legacy
`_consolidate_period` orchestration method, `_cleanup_old_nodes`, and the
inline raw-SQL consolidators retired.

Tests for the removed `_consolidate_period` / `_cleanup_old_nodes` direct
flow have been removed. Remaining tests cover:
- start/stop lifecycle
- `_calculate_next_run_time` scheduling math
- TSDBSummary <-> GraphNode round-trip
- `get_capabilities` / `get_status` / `get_node_type`
- `_consolidate_missed_windows` lock acquisition behavior
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

    async def recall_timeseries_side_effect(*args, **kwargs):
        return []

    mock.recall_timeseries = AsyncMock(side_effect=recall_timeseries_side_effect)
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
async def test_tsdb_service_auto_consolidation(tsdb_service, mock_memory_bus, mock_time_service):
    """Test automatic consolidation scheduling."""
    current_time = datetime(2024, 12, 22, 14, 30, 0, tzinfo=timezone.utc)
    mock_time_service.now.return_value = current_time

    # Calculate next run time
    next_run = tsdb_service._calculate_next_run_time()

    # Should be at 18:00 (next 6-hour boundary)
    assert next_run.hour == 18
    assert next_run.minute == 0
    assert next_run.second == 0
    assert next_run.day == 22

    # Test midnight rollover
    current_time = datetime(2024, 12, 22, 23, 30, 0, tzinfo=timezone.utc)
    mock_time_service.now.return_value = current_time

    next_run = tsdb_service._calculate_next_run_time()

    assert next_run.hour == 0
    assert next_run.minute == 0
    assert next_run.second == 0
    assert next_run.day == 23


def test_tsdb_service_capabilities(tsdb_service):
    """Test TSDBConsolidationService.get_capabilities() returns correct info."""
    caps = tsdb_service.get_capabilities()

    assert isinstance(caps, ServiceCapabilities)
    assert caps.service_name == "TSDBConsolidationService"
    assert "consolidate_tsdb_nodes" in caps.actions
    assert "create_6hour_summaries" in caps.actions
    assert "consolidate_all_data" in caps.actions
    assert "create_proper_edges" in caps.actions
    assert "track_memory_events" in caps.actions
    assert "summarize_tasks" in caps.actions
    assert caps.version == "2.0.0"


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


@pytest.mark.asyncio
async def test_consolidate_missed_windows_acquires_locks(tsdb_service, mock_memory_bus):
    """Test that _consolidate_missed_windows acquires locks before consolidating each period."""
    oldest_time = datetime.now(timezone.utc) - timedelta(hours=48)
    with patch.object(tsdb_service, "_find_oldest_unconsolidated_period", return_value=oldest_time):
        with patch.object(tsdb_service._query_manager, "check_period_consolidated", return_value=False):
            with patch.object(
                tsdb_service._query_manager, "_try_acquire_lock", return_value=True
            ) as mock_acquire:
                with patch.object(
                    tsdb_service, "_consolidate_period", new_callable=AsyncMock
                ) as mock_consolidate:
                    tsdb_service._consolidation_enabled = True

                    await tsdb_service._consolidate_missed_windows()

                    # Verify locks were acquired for each missed period
                    assert mock_acquire.call_count > 0

                    # Verify each lock acquisition used correct key format
                    for call in mock_acquire.call_args_list:
                        lock_key = call[0][0]
                        assert lock_key.startswith("missed:")
                        assert lock_key.endswith("Z") or lock_key.endswith("+00:00")

                    # Verify consolidation happened after acquiring locks
                    assert mock_consolidate.call_count == mock_acquire.call_count


@pytest.mark.asyncio
async def test_consolidate_missed_windows_skips_locked_periods(tsdb_service):
    """Test that _consolidate_missed_windows skips periods when lock is held by another occurrence."""
    oldest_time = datetime.now(timezone.utc) - timedelta(hours=48)
    with patch.object(tsdb_service, "_find_oldest_unconsolidated_period", return_value=oldest_time):
        with patch.object(tsdb_service._query_manager, "check_period_consolidated", return_value=False):
            with patch.object(
                tsdb_service._query_manager, "_try_acquire_lock", return_value=False
            ) as mock_acquire:
                with patch.object(
                    tsdb_service, "_consolidate_period", new_callable=AsyncMock
                ) as mock_consolidate:
                    tsdb_service._consolidation_enabled = True

                    await tsdb_service._consolidate_missed_windows()

                    # Verify lock acquisition was attempted
                    assert mock_acquire.call_count > 0
                    # Verify consolidation was SKIPPED
                    assert mock_consolidate.call_count == 0


@pytest.mark.asyncio
async def test_consolidate_missed_windows_partial_lock_acquisition(tsdb_service):
    """Test missed window consolidation with mixed lock acquisition results."""
    lock_results = [True, False, True, False]
    lock_call_count = 0

    def mock_acquire_lock(*args, **kwargs):
        nonlocal lock_call_count
        if lock_call_count < len(lock_results):
            result = lock_results[lock_call_count]
            lock_call_count += 1
            return result
        return False

    oldest_time = datetime.now(timezone.utc) - timedelta(hours=48)
    with patch.object(tsdb_service, "_find_oldest_unconsolidated_period", return_value=oldest_time):
        with patch.object(tsdb_service._query_manager, "check_period_consolidated", return_value=False):
            with patch.object(
                tsdb_service._query_manager, "_try_acquire_lock", side_effect=mock_acquire_lock
            ):
                with patch.object(
                    tsdb_service, "_consolidate_period", new_callable=AsyncMock
                ) as mock_consolidate:
                    tsdb_service._consolidation_enabled = True

                    await tsdb_service._consolidate_missed_windows()

                    expected_consolidations = sum(1 for result in lock_results if result)
                    assert mock_consolidate.call_count == expected_consolidations


@pytest.mark.asyncio
async def test_consolidate_missed_windows_respects_already_consolidated(tsdb_service):
    """Test that already-consolidated periods are skipped without lock acquisition."""
    with patch.object(tsdb_service._query_manager, "check_period_consolidated", return_value=True):
        with patch.object(tsdb_service._query_manager, "_try_acquire_lock") as mock_acquire:
            with patch.object(
                tsdb_service, "_consolidate_period", new_callable=AsyncMock
            ) as mock_consolidate:
                tsdb_service._consolidation_enabled = True

                await tsdb_service._consolidate_missed_windows()

                assert mock_acquire.call_count == 0
                assert mock_consolidate.call_count == 0


@pytest.mark.asyncio
async def test_consolidate_missed_windows_lock_key_format(tsdb_service):
    """Test that lock keys follow correct format for missed window consolidation."""
    captured_lock_keys = []

    def capture_lock_key(lock_key, *args, **kwargs):
        captured_lock_keys.append(lock_key)
        return True

    oldest_time = datetime.now(timezone.utc) - timedelta(hours=48)
    with patch.object(tsdb_service, "_find_oldest_unconsolidated_period", return_value=oldest_time):
        with patch.object(tsdb_service._query_manager, "check_period_consolidated", return_value=False):
            with patch.object(
                tsdb_service._query_manager, "_try_acquire_lock", side_effect=capture_lock_key
            ):
                with patch.object(tsdb_service, "_consolidate_period", new_callable=AsyncMock):
                    tsdb_service._consolidation_enabled = True

                    await tsdb_service._consolidate_missed_windows()

                    for lock_key in captured_lock_keys:
                        assert lock_key.startswith("missed:")
                        timestamp_str = lock_key.split(":", 1)[1]
                        assert "T" in timestamp_str
                        assert timestamp_str.endswith("Z") or timestamp_str.endswith("+00:00")
                        if timestamp_str.endswith("Z"):
                            datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
                        else:
                            datetime.fromisoformat(timestamp_str)
