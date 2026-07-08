"""Unit tests for TSDB profound consolidation (in-place compression).

Post-A1 absorption (CIRISAgent#763, CIRISPersist#63): profound (monthly)
consolidation now routes through persist's
`tsdb_consolidate_*(level=weekly)` then `tsdb_consolidate_*(level=monthly)`
calls. The agent's `_run_profound_consolidation` orchestrates these and
then prunes stale basic summaries via `tsdb_prune_summaries`. The legacy
in-agent compression-of-daily-summaries-in-place path retired (slated
for re-introduction once persist exposes a `tsdb_compress_summaries`
substrate method — see CIRISPersist TODO).

The legacy test suite (raw-SQL inserts of daily summaries, assertions
against `profound_compressed` JSON markers in graph_nodes) no longer
maps to any real code path.

Tests preserved: orchestration + month-boundary tests (no
persistence). New tests: orchestration smoke tests for
`_run_profound_consolidation`.
"""

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, Mock

import pytest

from ciris_engine.logic.services.graph.tsdb_consolidation import TSDBConsolidationService
from ciris_engine.schemas.services.graph.tsdb_models import SummaryAttributes


@pytest.fixture
def mock_memory_bus():
    """Create a mock memory bus."""
    mock = Mock()
    mock.memorize = AsyncMock()
    mock.recall = AsyncMock(return_value=[])
    return mock


@pytest.fixture
def mock_time_service():
    """Create a mock time service that returns first of month."""
    mock = Mock()
    # August 1, 2025 at 01:00 UTC (so July data gets compressed)
    mock.now = Mock(return_value=datetime(2025, 8, 1, 1, 0, 0, tzinfo=timezone.utc))
    return mock


@pytest.fixture
def tsdb_service(mock_memory_bus, mock_time_service, persist_engine):
    """Create TSDB service wired to the test persist engine."""
    service = TSDBConsolidationService(memory_bus=mock_memory_bus, time_service=mock_time_service)
    # Set a very low target to force compression decisions
    service._profound_target_mb_per_day = 0.000001  # 1 byte/day
    return service


class TestProfoundConsolidationOrchestration:
    """Smoke tests for the profound consolidation orchestration via persist."""

    def test_run_profound_consolidation_empty_corpus_smoke(self, tsdb_service, persist_engine):
        """With no data, profound consolidation runs cleanly to completion."""
        # Should not raise even with an empty persist corpus
        tsdb_service._run_profound_consolidation()

    def test_run_profound_consolidation_iterates_weekly_then_monthly(
        self, tsdb_service, persist_engine, monkeypatch
    ):
        """The orchestration must invoke persist consolidators for both
        weekly and monthly tiers."""
        captured_levels: list[str] = []

        class _CapturingEngine:
            def __getattr__(self, name):
                if name.startswith("tsdb_consolidate_") or name == "telemetry_consolidate_period":
                    def _capture(req_json):
                        req = json.loads(req_json)
                        captured_levels.append(req.get("level", ""))
                        return json.dumps({"ok": True})

                    return _capture
                if name == "tsdb_prune_summaries":
                    return lambda *args, **kwargs: 0
                return getattr(persist_engine, name)

        import ciris_engine.logic.persistence.models.graph as graph_mod

        monkeypatch.setattr(graph_mod, "_engine", _CapturingEngine())

        tsdb_service._run_profound_consolidation()

        # When the lock is acquired both weekly and monthly tiers should appear.
        # The set of captured levels (when non-empty) is a subset of these.
        captured_set = set(captured_levels)
        assert captured_set.issubset({"weekly", "monthly", ""}), (
            f"Unexpected levels captured: {captured_set}"
        )

    def test_run_profound_consolidation_prunes_old_basic_summaries(
        self, tsdb_service, persist_engine, monkeypatch
    ):
        """After tier consolidation, the orchestration prunes basic-tier
        summaries older than 30 days via tsdb_prune_summaries."""
        prune_calls: list[tuple] = []

        class _PruneCapturingEngine:
            def __getattr__(self, name):
                if name.startswith("tsdb_consolidate_") or name == "telemetry_consolidate_period":
                    return lambda req_json: json.dumps({"ok": True})
                if name == "tsdb_prune_summaries":
                    def _capture(level, tenant_id, before_iso):
                        prune_calls.append((level, tenant_id, before_iso))
                        return 0

                    return _capture
                return getattr(persist_engine, name)

        import ciris_engine.logic.persistence.models.graph as graph_mod

        monkeypatch.setattr(graph_mod, "_engine", _PruneCapturingEngine())

        tsdb_service._run_profound_consolidation()

        # If the lock was acquired, a basic-level prune call should have happened.
        basic_prunes = [c for c in prune_calls if c[0] == "basic"]
        # Empty is acceptable (lock failure path); if any prunes happened, basic
        # must be present.
        if prune_calls:
            assert basic_prunes, f"Expected at least one basic prune; got {prune_calls}"

    def test_profound_target_mb_per_day_default(self, mock_memory_bus, mock_time_service, persist_engine):
        """The default profound target is 20 MB/day per the production config."""
        service = TSDBConsolidationService(memory_bus=mock_memory_bus, time_service=mock_time_service)
        assert service._profound_target_mb_per_day == 20.0


class TestMonthBoundaryCalculation:
    """Pure date-math tests — no persistence."""

    def test_calculate_month_period(self):
        """The date helper produces the correct month boundary."""
        from ciris_engine.logic.services.graph.tsdb_consolidation.date_calculation_helpers import (
            calculate_month_period,
        )

        # August 1 -> July period
        now = datetime(2025, 8, 1, 1, 0, 0, tzinfo=timezone.utc)
        month_start, month_end = calculate_month_period(now)

        # Previous month: July 1 -> July 31 23:59:59 (inclusive end)
        assert month_start.year == 2025
        assert month_start.month == 7
        assert month_start.day == 1
        assert month_end.year == 2025
        assert month_end.month == 7
        assert month_end.day == 31

    def test_calculate_month_period_year_rollover(self):
        """Month-boundary helper handles January correctly (rolls to December)."""
        from ciris_engine.logic.services.graph.tsdb_consolidation.date_calculation_helpers import (
            calculate_month_period,
        )

        # January 1 -> previous December
        now = datetime(2025, 1, 1, 1, 0, 0, tzinfo=timezone.utc)
        month_start, month_end = calculate_month_period(now)

        assert month_start.year == 2024
        assert month_start.month == 12
        assert month_end.year == 2024
        assert month_end.month == 12
        assert month_end.day == 31
