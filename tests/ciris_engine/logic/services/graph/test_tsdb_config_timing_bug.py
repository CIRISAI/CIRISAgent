"""Test to reproduce TSDBConsolidationService config timing bug.

This test reproduces the issue where TSDBConsolidationService tries to access
the database before the config service is available during initialization.
"""

import asyncio
import sqlite3
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
        # Cleanup
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

    def test_bug_reproduction_without_fix(self, mock_memory_bus, mock_time_service, temp_db_path):
        """Verify the fix: Service works correctly with db_path and doesn't need ServiceRegistry.

        This test verifies the fix:
        1. TSDBConsolidationService is created with a db_path
        2. Service starts successfully without any config service in registry
        3. Service uses the provided db_path, not ServiceRegistry
        """
        # Initialize the database with required tables
        import sqlite3

        conn = sqlite3.connect(temp_db_path)
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS graph_nodes (
                node_id TEXT PRIMARY KEY,
                node_type TEXT NOT NULL,
                scope TEXT NOT NULL,
                attributes_json TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                updated_by TEXT,
                version INTEGER DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS service_correlations (
                correlation_id TEXT PRIMARY KEY,
                service_type TEXT NOT NULL,
                handler_name TEXT,
                action_type TEXT,
                request_data TEXT,
                response_data TEXT,
                status TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                correlation_type TEXT,
                timestamp TEXT,
                metric_name TEXT,
                metric_value REAL,
                trace_id TEXT,
                span_id TEXT,
                parent_span_id TEXT,
                tags TEXT
            );
        """
        )
        conn.commit()
        conn.close()

        # Ensure NO config service is available in registry
        with patch("ciris_engine.logic.registries.base.get_global_registry") as mock_registry:
            mock_registry.return_value.get_services_by_type.return_value = []

            # Create service WITH db_path
            service = TSDBConsolidationService(
                memory_bus=mock_memory_bus,
                time_service=mock_time_service,
                db_path=temp_db_path,  # <-- db_path provided here
            )

            # Verify the fix: Service has db_path and uses it
            assert service.db_path == temp_db_path
            assert service._query_manager._db_path == temp_db_path
            assert service._edge_manager._db_path == temp_db_path

            # Start service - should work without config service because we have db_path
            asyncio.run(service.start())

            # Service started successfully
            assert service._running is True

            # Stop service
            asyncio.run(service.stop())

    def test_config_service_not_available_error(self, mock_memory_bus, mock_time_service):
        """Test that the service works correctly even without config when db_path is provided."""

        # Ensure ServiceRegistry returns no config service
        with patch("ciris_engine.logic.registries.base.get_global_registry") as mock_registry:
            mock_registry.return_value.get_services_by_type.return_value = []

            # Create service WITH db_path - this should work now even without config
            with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
                test_db_path = f.name

            try:
                service = TSDBConsolidationService(
                    memory_bus=mock_memory_bus,
                    time_service=mock_time_service,
                    db_path=test_db_path,  # With db_path, it doesn't need config
                )

                # Start service - this should work now
                asyncio.run(service.start())

                # Service started successfully even without config
                assert service._running is True

                # Stop service
                asyncio.run(service.stop())
            finally:
                Path(test_db_path).unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_proper_initialization_sequence(
        self, mock_memory_bus, mock_time_service, temp_db_path, essential_config
    ):
        """Test the proper initialization sequence that avoids the bug.

        The proper sequence is:
        1. Initialize infrastructure services
        2. Initialize database
        3. Initialize memory service
        4. Initialize and register config service
        5. THEN initialize TSDB service with db_path
        6. TSDB should use the provided db_path, not query ServiceRegistry
        """
        # Initialize a minimal database
        conn = sqlite3.connect(temp_db_path)
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS graph_nodes (
                node_id TEXT PRIMARY KEY,
                node_type TEXT NOT NULL,
                scope TEXT NOT NULL,
                attributes_json TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                updated_by TEXT,
                version INTEGER DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS service_correlations (
                correlation_id TEXT PRIMARY KEY,
                correlation_type TEXT,
                service_type TEXT,
                action_type TEXT,
                trace_id TEXT,
                span_id TEXT,
                parent_span_id TEXT,
                timestamp TEXT,
                request_data TEXT,
                response_data TEXT,
                tags TEXT
            );

            CREATE TABLE IF NOT EXISTS tasks (
                task_id TEXT PRIMARY KEY,
                channel_id TEXT,
                description TEXT,
                status TEXT,
                priority TEXT,
                created_at TEXT,
                updated_at TEXT,
                parent_task_id TEXT,
                context_json TEXT,
                outcome_json TEXT,
                retry_count INTEGER
            );

            CREATE TABLE IF NOT EXISTS thoughts (
                thought_id TEXT PRIMARY KEY,
                source_task_id TEXT,
                thought_type TEXT,
                status TEXT,
                created_at TEXT,
                final_action_json TEXT
            );
        """
        )
        conn.commit()
        conn.close()

        # Patch get_db_connection to use our temp database WITH the db_path parameter
        def get_test_db_connection(db_path=None, **kwargs):
            """Return connection to test database."""
            # Use the provided db_path if given, otherwise fail
            if db_path:
                conn = sqlite3.connect(db_path)
            else:
                raise RuntimeError("No db_path provided and no config available - this is the bug!")
            conn.row_factory = sqlite3.Row
            return conn

        with patch(
            "ciris_engine.logic.services.graph.tsdb_consolidation.query_manager.get_db_connection",
            side_effect=get_test_db_connection,
        ):
            # Create service WITH db_path (as done in service_initializer.py)
            service = TSDBConsolidationService(
                memory_bus=mock_memory_bus,
                time_service=mock_time_service,
                db_path=temp_db_path,  # <-- Critical: db_path is provided
            )

            # Start service - this should work if db_path is properly passed through
            await service.start()

            # Service should be running
            assert service._running is True

            # Stop service
            await service.stop()

    def test_fix_verification_querymanager_gets_dbpath(self, mock_memory_bus, mock_time_service, temp_db_path):
        """Verify the fix: QueryManager should receive db_path from TSDBConsolidationService.

        The fix should:
        1. Pass db_path to QueryManager constructor
        2. QueryManager should use this db_path when calling get_db_connection
        """
        # This test will pass when the fix is implemented
        service = TSDBConsolidationService(
            memory_bus=mock_memory_bus, time_service=mock_time_service, db_path=temp_db_path
        )

        # After fix, QueryManager should have db_path
        # Currently this will fail because QueryManager doesn't store db_path
        assert hasattr(
            service._query_manager, "_db_path"
        ), "FIX NEEDED: QueryManager should store the db_path passed from TSDBConsolidationService"
        assert (
            service._query_manager._db_path == temp_db_path
        ), "FIX NEEDED: QueryManager should have the same db_path as TSDBConsolidationService"
