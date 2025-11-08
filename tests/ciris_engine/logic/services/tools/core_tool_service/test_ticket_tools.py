"""
Tests for Core Tool Service - Ticket Management Tools

Tests cover:
- update_ticket tool with all 8 status values
- Metadata deep merge for stages
- defer_ticket tool with automatic status='deferred'
- Tool info with complete status enum
- Metrics tracking
- Error handling
"""

import os
import sqlite3
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import pytest
import pytest_asyncio

from ciris_engine.logic.persistence.models.tickets import create_ticket
from ciris_engine.logic.secrets.service import SecretsService
from ciris_engine.logic.services.tools.core_tool_service.service import CoreToolService
from ciris_engine.schemas.adapters.tools import ToolExecutionStatus


class TestCoreToolServiceTicketTools:
    """Test ticket management tools in Core Tool Service."""

    @pytest.fixture
    def temp_db_path(self):
        """Create temporary database with migrations applied."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        # Apply migrations
        test_file = Path(__file__).resolve()
        project_root = test_file.parent.parent.parent.parent.parent.parent.parent
        migrations_dir = project_root / "ciris_engine" / "logic" / "persistence" / "migrations" / "sqlite"

        conn = sqlite3.connect(db_path)
        for i in range(1, 10):
            migration_files = list(migrations_dir.glob(f"{i:03d}_*.sql"))
            if migration_files:
                with open(migration_files[0], "r") as f:
                    sql = f.read()
                    # Workaround for pre-existing view bug in migration 001
                    if i == 1:
                        sql = sql.replace("t.task_id as associated_task_id", "t.thought_id as associated_thought_id")
                    conn.executescript(sql)

        conn.commit()
        conn.close()

        yield db_path

        if os.path.exists(db_path):
            os.unlink(db_path)

    @pytest.fixture
    def mock_secrets_service(self):
        """Create a mock secrets service."""
        mock = Mock(spec=SecretsService)
        mock.retrieve_secret = AsyncMock()
        return mock

    @pytest.fixture
    def mock_time_service(self):
        """Create a mock time service."""
        mock = Mock()
        mock.now.return_value = datetime(2025, 11, 7, 12, 0, 0, tzinfo=timezone.utc)
        return mock

    @pytest_asyncio.fixture
    async def tool_service(self, mock_secrets_service, mock_time_service, temp_db_path):
        """Create Core Tool Service instance."""
        service = CoreToolService(
            secrets_service=mock_secrets_service, time_service=mock_time_service, db_path=temp_db_path
        )
        await service.start()
        return service

    @pytest.fixture
    def test_ticket_id(self, temp_db_path):
        """Create a test ticket."""
        ticket_id = "TEST-TOOL-001"
        create_ticket(
            ticket_id=ticket_id,
            sop="DSAR_ACCESS",
            ticket_type="dsar",
            status="in_progress",
            email="tooltest@example.com",
            submitted_at=datetime.now(timezone.utc).isoformat(),
            metadata={"stages": {"identity_resolution": {"status": "completed", "result": "user@example.com"}}},
            db_path=temp_db_path,
        )
        return ticket_id

    @pytest.mark.asyncio
    async def test_update_ticket_status_only(self, tool_service, test_ticket_id):
        """TC-CT001: Verify status can be updated via tool."""
        result = await tool_service.execute_tool("update_ticket", {"ticket_id": test_ticket_id, "status": "blocked"})

        assert result.success is True
        assert result.status == ToolExecutionStatus.COMPLETED
        assert result.data["updates"]["status"] == "blocked"
        assert tool_service._tickets_updated == 1

    @pytest.mark.asyncio
    async def test_update_ticket_all_8_statuses(self, tool_service, test_ticket_id):
        """TC-CT002: Verify all 8 status values accepted."""
        all_statuses = ["pending", "assigned", "in_progress", "blocked", "deferred", "completed", "cancelled", "failed"]

        for status in all_statuses:
            result = await tool_service.execute_tool("update_ticket", {"ticket_id": test_ticket_id, "status": status})

            assert result.success is True, f"Status {status} should be accepted"
            assert result.data["updates"]["status"] == status

    @pytest.mark.asyncio
    async def test_update_ticket_metadata_deep_merge(self, tool_service, test_ticket_id):
        """TC-CT003: Verify stages metadata deep merges correctly."""
        # Update with new stage data
        result = await tool_service.execute_tool(
            "update_ticket",
            {
                "ticket_id": test_ticket_id,
                "metadata": {
                    "stages": {"data_collection": {"status": "completed", "result": {"records": 42}}},
                    "current_stage": "data_packaging",
                },
            },
        )

        assert result.success is True

        # Verify deep merge
        from ciris_engine.logic.persistence.models.tickets import get_ticket

        ticket = get_ticket(test_ticket_id, db_path=tool_service.db_path)
        metadata = ticket["metadata"]

        # Original stage preserved
        assert "identity_resolution" in metadata["stages"]
        assert metadata["stages"]["identity_resolution"]["status"] == "completed"
        assert metadata["stages"]["identity_resolution"]["result"] == "user@example.com"

        # New stage added
        assert "data_collection" in metadata["stages"]
        assert metadata["stages"]["data_collection"]["status"] == "completed"

        # Top-level metadata added
        assert metadata["current_stage"] == "data_packaging"

    @pytest.mark.asyncio
    async def test_update_ticket_shallow_metadata_merge(self, tool_service, test_ticket_id):
        """TC-CT004: Verify non-stages metadata does shallow merge."""
        # Update with non-stages metadata
        result = await tool_service.execute_tool(
            "update_ticket", {"ticket_id": test_ticket_id, "metadata": {"foo": "updated", "new_field": "new_value"}}
        )

        assert result.success is True

        from ciris_engine.logic.persistence.models.tickets import get_ticket

        ticket = get_ticket(test_ticket_id, db_path=tool_service.db_path)
        metadata = ticket["metadata"]

        # Stages preserved from original
        assert "stages" in metadata
        assert "identity_resolution" in metadata["stages"]

        # New fields added
        assert metadata["foo"] == "updated"
        assert metadata["new_field"] == "new_value"

    @pytest.mark.asyncio
    async def test_update_ticket_combined_updates(self, tool_service, test_ticket_id):
        """TC-CT005: Verify combined updates work."""
        result = await tool_service.execute_tool(
            "update_ticket",
            {
                "ticket_id": test_ticket_id,
                "status": "blocked",
                "metadata": {"reason": "Awaiting legal"},
                "notes": "Legal review required",
            },
        )

        assert result.success is True
        assert result.data["updates"]["status"] == "blocked"
        assert result.data["updates"]["notes"] == "Legal review required"
        assert result.data["updates"]["metadata"] == {"reason": "Awaiting legal"}

    @pytest.mark.asyncio
    async def test_update_ticket_nonexistent(self, tool_service):
        """TC-CT006: Verify error handling for missing ticket."""
        result = await tool_service.execute_tool("update_ticket", {"ticket_id": "NONEXISTENT", "status": "completed"})

        assert result.success is False
        assert "not found" in result.error.lower()

    @pytest.mark.asyncio
    async def test_defer_ticket_sets_status_deferred(self, tool_service, test_ticket_id):
        """TC-CT007: Verify defer_ticket automatically sets status='deferred'."""
        result = await tool_service.execute_tool(
            "defer_ticket", {"ticket_id": test_ticket_id, "defer_hours": 24, "reason": "Awaiting external data"}
        )

        assert result.success is True
        assert result.data["status_updated"] == "deferred"
        assert "deferred_until" in result.data

        # Verify status in database
        from ciris_engine.logic.persistence.models.tickets import get_ticket

        ticket = get_ticket(test_ticket_id, db_path=tool_service.db_path)
        assert ticket["status"] == "deferred"

    @pytest.mark.asyncio
    async def test_defer_ticket_await_human(self, tool_service, test_ticket_id):
        """TC-CT008: Verify defer with await_human flag."""
        result = await tool_service.execute_tool(
            "defer_ticket", {"ticket_id": test_ticket_id, "await_human": True, "reason": "Legal review needed"}
        )

        assert result.success is True
        assert result.data["deferral_type"] == "awaiting_human"
        assert result.data["status_updated"] == "deferred"

        # Verify metadata
        from ciris_engine.logic.persistence.models.tickets import get_ticket

        ticket = get_ticket(test_ticket_id, db_path=tool_service.db_path)
        assert ticket["status"] == "deferred"
        assert ticket["metadata"]["awaiting_human_response"] is True

    @pytest.mark.asyncio
    async def test_defer_ticket_until_timestamp(self, tool_service, test_ticket_id):
        """TC-CT009: Verify defer with absolute timestamp."""
        defer_until = "2025-11-08T10:00:00Z"
        result = await tool_service.execute_tool(
            "defer_ticket", {"ticket_id": test_ticket_id, "defer_until": defer_until, "reason": "Scheduled processing"}
        )

        assert result.success is True
        assert result.data["deferral_type"] == "until_timestamp"
        assert result.data["deferred_until"] == defer_until
        assert result.data["status_updated"] == "deferred"

    @pytest.mark.asyncio
    async def test_defer_ticket_hours(self, tool_service, test_ticket_id, mock_time_service):
        """TC-CT010: Verify defer with relative hours."""
        result = await tool_service.execute_tool(
            "defer_ticket", {"ticket_id": test_ticket_id, "defer_hours": 48, "reason": "Wait period"}
        )

        assert result.success is True
        assert result.data["deferral_type"] == "relative_hours"
        assert result.data["defer_hours"] == 48

        # Verify deferred_until is approximately now + 48 hours
        expected = mock_time_service.now() + timedelta(hours=48)
        actual_str = result.data["deferred_until"]
        actual = datetime.fromisoformat(actual_str.replace("Z", "+00:00"))

        # Allow 1 second tolerance
        assert abs((actual - expected).total_seconds()) < 1

    @pytest.mark.asyncio
    async def test_defer_ticket_missing_parameters(self, tool_service, test_ticket_id):
        """TC-CT011: Verify error when no defer parameters provided."""
        result = await tool_service.execute_tool("defer_ticket", {"ticket_id": test_ticket_id, "reason": "Test"})

        assert result.success is False
        assert "must provide" in result.error.lower()

    @pytest.mark.asyncio
    async def test_get_tool_info_update_ticket(self, tool_service):
        """TC-CT012: Verify tool info includes all 8 status values."""
        tool_info = await tool_service.get_tool_info("update_ticket")

        assert tool_info is not None
        assert tool_info.name == "update_ticket"

        # Verify status enum includes all 8 values
        status_prop = tool_info.parameters.properties.get("status")
        assert status_prop is not None
        assert "enum" in status_prop

        expected_statuses = [
            "pending",
            "assigned",
            "in_progress",
            "blocked",
            "deferred",
            "completed",
            "cancelled",
            "failed",
        ]
        assert set(status_prop["enum"]) == set(expected_statuses)

    @pytest.mark.asyncio
    async def test_metrics_tickets_updated(self, tool_service, test_ticket_id):
        """TC-CT013: Verify _tickets_updated metric tracked."""
        # Execute 3 updates
        for i in range(3):
            await tool_service.execute_tool("update_ticket", {"ticket_id": test_ticket_id, "status": "in_progress"})

        metrics = await tool_service.get_metrics()
        assert metrics["tickets_updated_total"] == 3.0

    @pytest.mark.asyncio
    async def test_metrics_tickets_deferred(self, tool_service, test_ticket_id):
        """TC-CT014: Verify _tickets_deferred metric tracked."""
        # Create second ticket
        ticket_id_2 = "TEST-TOOL-002"
        create_ticket(
            ticket_id=ticket_id_2,
            sop="DSAR_ACCESS",
            ticket_type="dsar",
            status="in_progress",
            email="test2@example.com",
            submitted_at=datetime.now(timezone.utc).isoformat(),
            db_path=tool_service.db_path,
        )

        # Defer both tickets
        await tool_service.execute_tool(
            "defer_ticket", {"ticket_id": test_ticket_id, "defer_hours": 24, "reason": "Test 1"}
        )

        await tool_service.execute_tool(
            "defer_ticket", {"ticket_id": ticket_id_2, "await_human": True, "reason": "Test 2"}
        )

        metrics = await tool_service.get_metrics()
        assert metrics["tickets_deferred_total"] == 2.0


class TestCoreToolServiceGetTicket:
    """Test get_ticket tool."""

    @pytest.fixture
    def temp_db_path(self):
        """Create temporary database."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        test_file = Path(__file__).resolve()
        project_root = test_file.parent.parent.parent.parent.parent.parent.parent
        migrations_dir = project_root / "ciris_engine" / "logic" / "persistence" / "migrations" / "sqlite"

        conn = sqlite3.connect(db_path)
        for i in range(1, 10):
            migration_files = list(migrations_dir.glob(f"{i:03d}_*.sql"))
            if migration_files:
                with open(migration_files[0], "r") as f:
                    sql = f.read()
                    # Workaround for pre-existing view bug in migration 001
                    if i == 1:
                        sql = sql.replace("t.task_id as associated_task_id", "t.thought_id as associated_thought_id")
                    conn.executescript(sql)

        conn.commit()
        conn.close()

        yield db_path

        if os.path.exists(db_path):
            os.unlink(db_path)

    @pytest_asyncio.fixture
    async def tool_service(self, temp_db_path):
        """Create tool service."""
        mock_secrets = Mock(spec=SecretsService)
        mock_secrets.retrieve_secret = AsyncMock()
        mock_time = Mock()
        mock_time.now.return_value = datetime.now(timezone.utc)

        service = CoreToolService(secrets_service=mock_secrets, time_service=mock_time, db_path=temp_db_path)
        await service.start()
        return service

    @pytest.mark.asyncio
    async def test_get_ticket_success(self, tool_service):
        """Verify get_ticket retrieves ticket data."""
        # Create ticket
        ticket_id = "GET-TEST-001"
        create_ticket(
            ticket_id=ticket_id,
            sop="DSAR_ACCESS",
            ticket_type="dsar",
            status="in_progress",
            email="get@example.com",
            submitted_at=datetime.now(timezone.utc).isoformat(),
            metadata={"test": "data"},
            db_path=tool_service.db_path,
        )

        result = await tool_service.execute_tool("get_ticket", {"ticket_id": ticket_id})

        assert result.success is True
        assert result.data["ticket_id"] == ticket_id
        assert result.data["status"] == "in_progress"
        assert result.data["metadata"]["test"] == "data"
        assert tool_service._tickets_retrieved == 1
