"""Unit tests for TSDB consolidation cleanup logic.

Post-A1 absorption (CIRISAgent#763, CIRISPersist#63): cleanup now routes
through persist's `tsdb_prune_summaries(level, tenant_id, before)` for
each summary node_type. The legacy "delete raw data if summary exists"
semantics retired — persist owns the storage lifecycle, and the agent
just calls prune per level.

The legacy raw-SQL tests in this module (TestRawDataCleanup,
TestAuditNodeCleanup, TestCorrelationCleanup, TestForeignKeyConstraintHandling)
exercised the pre-2.9.0 cursor-cascade-by-hand path that no longer exists.
They've been removed; remaining edge-case tests verify the new persist
prune wrapper handles empty/within-retention/missing-engine cases.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, Mock

import pytest

from ciris_engine.logic.services.graph.tsdb_consolidation import TSDBConsolidationService
from ciris_engine.schemas.services.operations import MemoryOpResult, MemoryOpStatus


@pytest.fixture
def mock_memory_bus():
    """Create a mock memory bus."""
    mock = Mock()
    mock.memorize = AsyncMock(return_value=MemoryOpResult(status=MemoryOpStatus.OK))
    mock.recall = AsyncMock(return_value=[])
    return mock


@pytest.fixture
def mock_time_service():
    """Create a mock time service."""
    mock = Mock()
    # Set to a time where we have old data to clean up
    mock.now = Mock(return_value=datetime(2025, 7, 15, 12, 0, 0, tzinfo=timezone.utc))
    return mock


@pytest.fixture
def tsdb_service(mock_memory_bus, mock_time_service):
    """Create TSDB service for testing."""
    return TSDBConsolidationService(
        memory_bus=mock_memory_bus,
        time_service=mock_time_service,
        consolidation_interval_hours=6,
        raw_retention_hours=24,
    )


class TestPrunePathSmoke:
    """Smoke tests for the persist-backed prune path."""

    def test_cleanup_with_no_engine_returns_zero(self, tsdb_service, monkeypatch):
        """When the persist engine isn't wired, cleanup returns 0 gracefully."""
        # Force get_persist_engine to return None
        import ciris_engine.logic.persistence.models.graph as graph_mod

        monkeypatch.setattr(graph_mod, "_engine", None)

        deleted = tsdb_service._cleanup_old_data()
        assert deleted == 0

    def test_cleanup_with_empty_persist_returns_zero(self, tsdb_service, persist_engine):
        """With a wired but empty persist engine, cleanup returns 0."""
        deleted = tsdb_service._cleanup_old_data()
        # No summary nodes exist, so prune returns 0 per level
        assert deleted == 0

    def test_cleanup_handles_persist_errors_gracefully(self, tsdb_service, persist_engine, monkeypatch):
        """A failing prune call should not propagate; cleanup returns 0."""
        # ciris_persist.Engine methods are read-only Rust attrs; wrap the
        # whole engine with a stub that raises on tsdb_prune_summaries.
        class _RaisingEngine:
            def __getattr__(self, name):
                if name == "tsdb_prune_summaries":
                    def _raise(*args, **kwargs):
                        raise RuntimeError("simulated persist failure")

                    return _raise
                return getattr(persist_engine, name)

        import ciris_engine.logic.persistence.models.graph as graph_mod

        monkeypatch.setattr(graph_mod, "_engine", _RaisingEngine())

        deleted = tsdb_service._cleanup_old_data()
        assert deleted == 0


class TestCleanupRetentionWindow:
    """Verify cleanup honors the retention window argument shape."""

    def test_cleanup_uses_configured_retention_hours(
        self, mock_memory_bus, mock_time_service, persist_engine, monkeypatch
    ):
        """Cleanup should compute a cutoff based on raw_retention_hours and pass
        an RFC-3339 'before' to persist's prune."""
        captured_cutoffs: list[str] = []

        def fake_prune(level, tenant_id, before_iso):
            captured_cutoffs.append(before_iso)
            return 0

        # ciris_persist.Engine attrs are read-only; wrap with capture stub.
        class _CapturingEngine:
            def __getattr__(self, name):
                if name == "tsdb_prune_summaries":
                    return fake_prune
                return getattr(persist_engine, name)

        import ciris_engine.logic.persistence.models.graph as graph_mod

        monkeypatch.setattr(graph_mod, "_engine", _CapturingEngine())

        # 24h retention => cutoff = now - 24h
        service = TSDBConsolidationService(
            memory_bus=mock_memory_bus,
            time_service=mock_time_service,
            consolidation_interval_hours=6,
            raw_retention_hours=24,
        )
        service._cleanup_old_data()

        # 'basic', 'daily', 'weekly' — three calls expected
        assert len(captured_cutoffs) >= 3

        # Each cutoff must be a tz-aware RFC-3339 string
        for cutoff in captured_cutoffs:
            assert cutoff.endswith("Z") or "+" in cutoff
            parsed = datetime.fromisoformat(cutoff.replace("Z", "+00:00"))
            now = mock_time_service.now()
            delta = now - parsed
            # Retention is 24h; allow generous slack for date math.
            assert delta >= timedelta(hours=23)
