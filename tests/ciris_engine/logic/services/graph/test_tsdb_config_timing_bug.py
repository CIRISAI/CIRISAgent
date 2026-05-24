"""Test to reproduce TSDBConsolidationService config timing bug.

This test reproduces the issue where TSDBConsolidationService tries to access
the database before the config service is available during initialization.

Post-A1 absorption (CIRISAgent#763, CIRISPersist#63): db_path is mostly
cosmetic now — persist owns the connection. The service can construct and
start regardless of config-service availability as long as the persist
engine is wired.
"""

import asyncio
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import pytest

from ciris_engine.logic.services.graph.tsdb_consolidation import TSDBConsolidationService
from ciris_engine.schemas.config.essential import DatabaseConfig, EssentialConfig


class TestTSDBConfigTimingBug:
    """Test to reproduce and verify fix for TSDB config timing bug."""

    @pytest.fixture
    def temp_db_path(self):
        """Create a temporary database file."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        yield db_path
        Path(db_path).unlink(missing_ok=True)

    @pytest.fixture
    def essential_config(self, temp_db_path):
        """Create an essential config with test database path."""
        config = EssentialConfig()
        config.database = DatabaseConfig(
            main_db=Path(temp_db_path),
            secrets_db=Path(temp_db_path.replace(".db", "_secrets.db")),
            audit_db=Path(temp_db_path.replace(".db", "_audit.db")),
        )
        return config

    @pytest.fixture
    def mock_memory_bus(self):
        """Create a mock memory bus."""
        mock = Mock()
        mock.memorize = AsyncMock(return_value=Mock(status="ok"))
        mock.recall = AsyncMock(return_value=[])
        mock.search = AsyncMock(return_value=[])
        return mock

    @pytest.fixture
    def mock_time_service(self):
        """Create a mock time service."""
        mock = Mock()
        mock.now = Mock(return_value=datetime.now(timezone.utc))
        return mock

    def test_bug_reproduction_without_fix(self, mock_memory_bus, mock_time_service, temp_db_path, persist_engine):
        """Verify the fix: Service works correctly with db_path and doesn't need ServiceRegistry.

        Post-persist: db_path is cosmetic; persist owns the connection.
        QueryManager exposes the path via `_db_path`; EdgeManager via `db_path`.
        """
        with patch("ciris_engine.logic.registries.base.get_global_registry") as mock_registry:
            mock_registry.return_value.get_services_by_type.return_value = []

            service = TSDBConsolidationService(
                memory_bus=mock_memory_bus,
                time_service=mock_time_service,
                db_path=temp_db_path,
            )

            # Verify db_path plumbed through (signature compat)
            assert service.db_path == temp_db_path
            assert service._query_manager._db_path == temp_db_path
            # EdgeManager uses `db_path` (public), not `_db_path`
            assert service._edge_manager.db_path == temp_db_path

            # Start service - works without config service because persist engine is wired
            asyncio.run(service.start())
            assert service._running is True

            asyncio.run(service.stop())

    def test_config_service_not_available_error(self, mock_memory_bus, mock_time_service, persist_engine):
        """Test that the service works correctly even without config when db_path is provided."""
        with patch("ciris_engine.logic.registries.base.get_global_registry") as mock_registry:
            mock_registry.return_value.get_services_by_type.return_value = []

            with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
                test_db_path = f.name

            try:
                service = TSDBConsolidationService(
                    memory_bus=mock_memory_bus,
                    time_service=mock_time_service,
                    db_path=test_db_path,
                )

                # Start service - this should work now
                asyncio.run(service.start())
                assert service._running is True

                asyncio.run(service.stop())
            finally:
                Path(test_db_path).unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_proper_initialization_sequence(
        self, mock_memory_bus, mock_time_service, temp_db_path, essential_config, persist_engine
    ):
        """Test the proper initialization sequence with persist wired.

        Post-persist: the bug was about db_path not being plumbed to QueryManager.
        With the persist substrate owning the connection, the smoke test is:
        1. construct with db_path
        2. start successfully
        3. stop cleanly
        """
        service = TSDBConsolidationService(
            memory_bus=mock_memory_bus,
            time_service=mock_time_service,
            db_path=temp_db_path,
        )

        await service.start()
        assert service._running is True

        await service.stop()

    def test_fix_verification_querymanager_gets_dbpath(self, mock_memory_bus, mock_time_service, temp_db_path):
        """Verify the fix: QueryManager should receive db_path from TSDBConsolidationService.

        Persist owns the connection now, but db_path is still plumbed to QueryManager
        for signature compatibility.
        """
        service = TSDBConsolidationService(
            memory_bus=mock_memory_bus, time_service=mock_time_service, db_path=temp_db_path
        )

        assert hasattr(
            service._query_manager, "_db_path"
        ), "QueryManager should store the db_path passed from TSDBConsolidationService"
        assert (
            service._query_manager._db_path == temp_db_path
        ), "QueryManager should have the same db_path as TSDBConsolidationService"
