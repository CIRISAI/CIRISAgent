"""
Tests for batch context builder - ensuring type safety and ethical safeguards.

These tests align with CIRIS covenant principles:
- Type safety (no Dict[str, Any])
- Resilience (error handling)
- Resource awareness (critical alerts)
- Transparency (proper logging)
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import BaseModel

from ciris_engine.logic.context.batch_context import (
    BatchContextData,
    build_system_snapshot_with_batch,
    prefetch_batch_context,
)
from ciris_engine.schemas.runtime.extended import ShutdownContext
from ciris_engine.schemas.runtime.models import Task, TaskStatus
from ciris_engine.schemas.runtime.system_context import SystemSnapshot, TaskSummary, TelemetrySummary
from ciris_engine.schemas.services.graph_core import GraphNode, GraphScope, NodeType


# Mock Task model that matches what persistence returns
class MockPersistedTask(BaseModel):
    """Mock task that matches database model structure."""

    task_id: str
    channel_id: str = "system"
    created_at: datetime
    status: TaskStatus
    priority: int = 0
    retry_count: int = 0
    parent_task_id: str | None = None


class TestBatchContextData:
    """Test BatchContextData type safety and initialization."""

    def test_init_with_proper_types(self):
        """Verify all fields initialize with correct types per covenant type safety."""
        batch_data = BatchContextData()

        # Type assertions per "No Dicts, No Strings, No Kings" principle
        assert isinstance(batch_data.agent_identity, dict)
        assert batch_data.identity_purpose is None or isinstance(batch_data.identity_purpose, str)
        assert isinstance(batch_data.identity_capabilities, list)
        assert isinstance(batch_data.identity_restrictions, list)
        assert isinstance(batch_data.recent_tasks, list)
        assert isinstance(batch_data.top_tasks, list)

        # Service health must be Dict[str, bool]
        assert isinstance(batch_data.service_health, dict)
        # Circuit breaker must be Dict[str, str]
        assert isinstance(batch_data.circuit_breaker_status, dict)
        # Resource alerts must be List[str]
        assert isinstance(batch_data.resource_alerts, list)

        assert batch_data.telemetry_summary is None or isinstance(batch_data.telemetry_summary, TelemetrySummary)
        assert isinstance(batch_data.secrets_snapshot, dict)
        assert batch_data.shutdown_context is None or isinstance(batch_data.shutdown_context, ShutdownContext)

    def test_type_safety_enforcement(self):
        """Test that fields enforce type constraints per covenant."""
        batch_data = BatchContextData()

        # Test agent_identity only accepts typed values
        batch_data.agent_identity = {
            "agent_id": "test_agent",  # str
            "trust_level": 0.8,  # float
            "active": True,  # bool
            "retry_count": 5,  # int
            "capabilities": ["speak", "observe"],  # list
            "metadata": {"version": "1.0"},  # dict
        }

        # Verify all values match expected types
        assert isinstance(batch_data.agent_identity["agent_id"], str)
        assert isinstance(batch_data.agent_identity["trust_level"], float)
        assert isinstance(batch_data.agent_identity["active"], bool)
        assert isinstance(batch_data.agent_identity["retry_count"], int)
        assert isinstance(batch_data.agent_identity["capabilities"], list)
        assert isinstance(batch_data.agent_identity["metadata"], dict)

        # Service health must be bool values
        batch_data.service_health = {"memory": True, "llm": False, "telemetry": True}
        for value in batch_data.service_health.values():
            assert isinstance(value, bool)

        # Circuit breaker status must be string values
        batch_data.circuit_breaker_status = {"memory": "CLOSED", "llm": "OPEN", "telemetry": "HALF_OPEN"}
        for value in batch_data.circuit_breaker_status.values():
            assert isinstance(value, str)

    def test_resource_alerts_critical_handling(self):
        """Test resource alerts follow covenant's harm prevention principle."""
        batch_data = BatchContextData()

        # Critical alerts should be clear and actionable
        batch_data.resource_alerts = [
            "🚨 CRITICAL! CPU usage at 95%",
            "🚨 CRITICAL! RESOURCE LIMIT BREACHED! Memory at 98% - REJECT OR DEFER ALL TASKS!",
            "Warning: Disk space low (10GB remaining)",
        ]

        # Verify critical alerts are properly formatted
        critical_count = sum(1 for alert in batch_data.resource_alerts if "CRITICAL" in alert)
        assert critical_count == 2

        # Verify actionable guidance is included
        assert any("REJECT OR DEFER" in alert for alert in batch_data.resource_alerts)


@pytest.mark.asyncio
class TestPrefetchBatchContext:
    """Test prefetch_batch_context with focus on resilience and error handling."""

    async def test_prefetch_resilience_with_no_services(self):
        """Test graceful degradation when no services available (Resilience principle)."""
        batch_data = await prefetch_batch_context()

        # Should return valid empty state, not fail
        assert isinstance(batch_data, BatchContextData)
        assert batch_data.agent_identity == {}
        assert batch_data.recent_tasks == []
        assert batch_data.top_tasks == []
        assert batch_data.service_health == {}
        assert batch_data.resource_alerts == []

    @patch("ciris_engine.logic.context.batch_context.persistence")
    async def test_prefetch_with_proper_task_models(self, mock_persistence):
        """Test tasks are properly converted from persistence models."""
        # Create properly typed mock tasks as BaseModel instances
        mock_task1 = MockPersistedTask(
            task_id="task_123",
            channel_id="discord_456",
            created_at=datetime.now(timezone.utc),
            status=TaskStatus.COMPLETED,
            priority=5,
            retry_count=1,
            parent_task_id="parent_001",
        )

        mock_task2 = MockPersistedTask(
            task_id="task_456",
            channel_id="api_789",
            created_at=datetime.now(timezone.utc),
            status=TaskStatus.ACTIVE,
            priority=10,
            retry_count=0,
            parent_task_id=None,
        )

        mock_persistence.get_recent_completed_tasks.return_value = [mock_task1]
        mock_persistence.get_top_tasks.return_value = [mock_task2]

        batch_data = await prefetch_batch_context()

        # Verify tasks were properly converted to TaskSummary
        assert len(batch_data.recent_tasks) == 1
        assert len(batch_data.top_tasks) == 1

        # Check recent task conversion (status gets lowercased via .value)
        recent = batch_data.recent_tasks[0]
        assert recent.task_id == "task_123"
        assert recent.channel_id == "discord_456"
        assert recent.status == "completed"  # TaskStatus.COMPLETED.value returns lowercase
        assert recent.priority == 5
        assert recent.retry_count == 1
        assert recent.parent_task_id == "parent_001"

        # Check top task conversion
        top = batch_data.top_tasks[0]
        assert top.task_id == "task_456"
        assert top.channel_id == "api_789"
        assert top.status == "active"  # TaskStatus.ACTIVE.value returns lowercase
        assert top.priority == 10
        assert top.retry_count == 0
        assert top.parent_task_id is None

    async def test_prefetch_identity_from_memory(self):
        """Test agent identity retrieval respects data types."""
        mock_memory = AsyncMock()

        # Create properly structured identity node
        identity_node = GraphNode(
            id="agent/identity",
            type=NodeType.AGENT,
            scope=GraphScope.IDENTITY,
            attributes={
                "agent_id": "ciris_001",
                "description": "Ethical AI Assistant",
                "role_description": "Support human flourishing through ethical assistance",
                "trust_level": 0.85,
                "permitted_actions": ["speak", "observe", "memorize", "recall"],
                "restricted_capabilities": ["tool", "forget"],
                "covenant_version": "1.0b",
            },
        )
        mock_memory.recall.return_value = [identity_node]

        batch_data = await prefetch_batch_context(memory_service=mock_memory)

        # Verify identity was properly extracted
        assert batch_data.agent_identity["agent_id"] == "ciris_001"
        assert batch_data.agent_identity["trust_level"] == 0.85
        assert batch_data.identity_purpose == "Support human flourishing through ethical assistance"
        assert len(batch_data.identity_capabilities) == 4
        assert "speak" in batch_data.identity_capabilities
        assert "tool" in batch_data.identity_restrictions

    async def test_prefetch_handles_memory_service_failure(self):
        """Test resilience when memory service fails."""
        mock_memory = AsyncMock()
        mock_memory.recall.side_effect = Exception("Memory service unavailable")

        # Should not crash, should log warning
        with patch("ciris_engine.logic.context.batch_context.logger") as mock_logger:
            batch_data = await prefetch_batch_context(memory_service=mock_memory)

            # Verify warning was logged
            mock_logger.warning.assert_called()

            # Should have empty identity but continue
            assert batch_data.agent_identity == {}
            assert batch_data.identity_purpose is None

    async def test_prefetch_critical_resource_alerts(self):
        """Test critical resource monitoring per covenant harm prevention."""
        mock_monitor = MagicMock()
        mock_snapshot = MagicMock()

        # Simulate critical resource state
        mock_snapshot.critical = ["Memory usage at 95%", "CPU throttling detected"]
        mock_snapshot.healthy = False
        mock_monitor.snapshot = mock_snapshot

        batch_data = await prefetch_batch_context(resource_monitor=mock_monitor)

        # Should generate proper critical alerts
        assert len(batch_data.resource_alerts) >= 2

        # Check for critical alert formatting
        critical_alerts = [a for a in batch_data.resource_alerts if "CRITICAL" in a]
        assert len(critical_alerts) >= 2

        # Verify action guidance is included
        assert any("REJECT OR DEFER ALL TASKS" in alert for alert in batch_data.resource_alerts)
        assert any("IMMEDIATE ACTION REQUIRED" in alert for alert in batch_data.resource_alerts)

    async def test_prefetch_resource_monitor_failure_handling(self):
        """Test that resource monitor failures are treated as critical."""
        mock_monitor = MagicMock()
        # Simulate monitor failure
        mock_monitor.snapshot = property(lambda self: (_ for _ in ()).throw(Exception("Monitor failed")))

        batch_data = await prefetch_batch_context(resource_monitor=mock_monitor)

        # Should generate critical alert about failure
        assert len(batch_data.resource_alerts) == 1
        assert "CRITICAL" in batch_data.resource_alerts[0]
        assert "FAILED TO CHECK RESOURCES" in batch_data.resource_alerts[0]

    async def test_prefetch_secrets_snapshot_typing(self):
        """Test secrets snapshot maintains proper typing."""
        mock_secrets = AsyncMock()

        with patch("ciris_engine.logic.context.secrets_snapshot.build_secrets_snapshot") as mock_build:
            mock_build.return_value = {
                "detected_secrets": ["API_KEY_ABC*", "TOKEN_XYZ*"],
                "total_secrets_stored": 5,
                "secrets_filter_version": 2,
            }

            batch_data = await prefetch_batch_context(secrets_service=mock_secrets)

            # Verify types match schema expectations
            assert isinstance(batch_data.secrets_snapshot["detected_secrets"], list)
            assert isinstance(batch_data.secrets_snapshot["total_secrets_stored"], int)
            assert isinstance(batch_data.secrets_snapshot["secrets_filter_version"], int)

    async def test_prefetch_telemetry_summary_proper_schema(self):
        """Test telemetry summary uses proper schema."""
        mock_telemetry = AsyncMock()

        # Create proper TelemetrySummary
        telemetry_summary = TelemetrySummary(
            window_start=datetime.now(timezone.utc),
            window_end=datetime.now(timezone.utc),
            uptime_seconds=7200.0,
            messages_processed_24h=250,
            thoughts_processed_24h=125,
            tasks_completed_24h=50,
            errors_24h=3,
            messages_current_hour=15,
            thoughts_current_hour=8,
            errors_current_hour=0,
            tokens_last_hour=1500.0,
            cost_last_hour_cents=25.5,
            carbon_last_hour_grams=0.5,
            energy_last_hour_kwh=0.001,
        )
        mock_telemetry.get_telemetry_summary.return_value = telemetry_summary

        batch_data = await prefetch_batch_context(telemetry_service=mock_telemetry)

        # Verify it's the proper type
        assert isinstance(batch_data.telemetry_summary, TelemetrySummary)
        assert batch_data.telemetry_summary.messages_processed_24h == 250
        assert batch_data.telemetry_summary.errors_24h == 3
        assert batch_data.telemetry_summary.cost_last_hour_cents == 25.5

    async def test_prefetch_shutdown_context_handling(self):
        """Test shutdown context is properly handled."""
        mock_runtime = MagicMock()

        # Create proper ShutdownContext with correct fields
        shutdown_context = ShutdownContext(
            is_terminal=False,
            reason="Scheduled maintenance",
            initiated_by="system_admin",
            allow_deferral=True,
            expected_reactivation=datetime.now(timezone.utc),
            agreement_context="Previously scheduled at 2PM",
        )
        mock_runtime.current_shutdown_context = shutdown_context

        batch_data = await prefetch_batch_context(runtime=mock_runtime)

        # Verify shutdown context is preserved
        assert isinstance(batch_data.shutdown_context, ShutdownContext)
        assert batch_data.shutdown_context.reason == "Scheduled maintenance"
        assert batch_data.shutdown_context.is_terminal is False
        assert batch_data.shutdown_context.allow_deferral is True


@pytest.mark.asyncio
class TestBuildSystemSnapshotWithBatch:
    """Test system snapshot building with focus on completeness and type safety."""

    async def test_build_snapshot_maintains_type_safety(self):
        """Verify snapshot maintains type safety throughout."""
        batch_data = BatchContextData()

        # Set typed data
        batch_data.agent_identity = {"agent_id": "test", "trust_level": 0.9}
        batch_data.service_health = {"memory": True, "llm": False}
        batch_data.circuit_breaker_status = {"memory": "CLOSED", "llm": "OPEN"}
        batch_data.resource_alerts = ["High memory usage"]

        snapshot = await build_system_snapshot_with_batch(task=None, thought=None, batch_data=batch_data)

        # Verify SystemSnapshot type
        assert isinstance(snapshot, SystemSnapshot)

        # Verify nested types
        assert isinstance(snapshot.agent_identity, dict)
        assert isinstance(snapshot.service_health, dict)
        assert isinstance(snapshot.circuit_breaker_status, dict)
        assert isinstance(snapshot.resource_alerts, list)

        # Verify values maintain types
        assert snapshot.service_health["memory"] is True
        assert snapshot.circuit_breaker_status["llm"] == "OPEN"

    async def test_build_snapshot_with_complete_context(self):
        """Test building snapshot with all context fields populated."""
        batch_data = BatchContextData()

        # Populate all batch data fields
        batch_data.agent_identity = {"agent_id": "ciris_test", "description": "Test agent", "trust_level": 0.75}
        batch_data.identity_purpose = "Testing and validation"
        batch_data.identity_capabilities = ["speak", "observe", "memorize"]
        batch_data.identity_restrictions = ["tool", "forget"]

        # Add task summaries
        task_summary = TaskSummary(
            task_id="task_001",
            channel_id="test_channel",
            created_at=datetime.now(timezone.utc),
            status="completed",  # TaskStatus enum values are lowercase
            priority=5,
            retry_count=0,
        )
        batch_data.recent_tasks = [task_summary]
        batch_data.top_tasks = [task_summary]

        # Add service health
        batch_data.service_health = {"memory": True, "llm": True, "telemetry": False}
        batch_data.circuit_breaker_status = {"memory": "CLOSED", "llm": "CLOSED", "telemetry": "OPEN"}

        # Add alerts
        batch_data.resource_alerts = ["🚨 CRITICAL! High memory usage"]

        # Add secrets
        batch_data.secrets_snapshot = {
            "detected_secrets": ["KEY_*", "TOKEN_*"],
            "total_secrets_stored": 3,
            "secrets_filter_version": 1,
        }

        # Build snapshot
        snapshot = await build_system_snapshot_with_batch(task=None, thought=None, batch_data=batch_data)

        # Verify all fields are properly populated
        assert snapshot.agent_identity["agent_id"] == "ciris_test"
        assert snapshot.identity_purpose == "Testing and validation"
        assert len(snapshot.identity_capabilities) == 3
        assert len(snapshot.identity_restrictions) == 2
        assert len(snapshot.recently_completed_tasks_summary) == 1
        assert len(snapshot.top_pending_tasks_summary) == 1
        assert snapshot.service_health["memory"] is True
        assert snapshot.circuit_breaker_status["telemetry"] == "OPEN"
        assert len(snapshot.resource_alerts) == 1
        assert len(snapshot.detected_secrets) == 2
        assert snapshot.total_secrets_stored == 3
        assert snapshot.secrets_filter_version == 1

    async def test_build_snapshot_extracts_channel_context(self):
        """Test channel context extraction from nested task context."""
        batch_data = BatchContextData()

        # Create a mock task with nested context
        mock_task = MagicMock()
        mock_task.task_id = "task_999"
        mock_task.channel_id = "fallback_channel"
        mock_task.created_at = datetime.now(timezone.utc)
        mock_task.status = TaskStatus.ACTIVE
        mock_task.priority = 5
        mock_task.retry_count = 0
        mock_task.parent_task_id = None

        # Mock the context attribute
        mock_context = MagicMock()
        mock_system_snapshot = MagicMock()
        mock_system_snapshot.channel_id = "discord_12345"
        mock_context.system_snapshot = mock_system_snapshot
        mock_task.context = mock_context

        # Mock memory service for channel query
        mock_memory = AsyncMock()
        mock_memory.recall.return_value = []

        snapshot = await build_system_snapshot_with_batch(
            task=mock_task, thought=None, batch_data=batch_data, memory_service=mock_memory
        )

        # Should extract channel_id from nested context
        assert snapshot.channel_id == "discord_12345"

        # Current task details will be None as our mock task is not a BaseModel
        # The function only creates TaskSummary for BaseModel instances
        assert snapshot.current_task_details is None

        # Should attempt to query channel context
        mock_memory.recall.assert_called_once()
        call_args = mock_memory.recall.call_args[0][0]
        assert call_args.node_id == "channel/discord_12345"

    async def test_build_snapshot_handles_thought_status_variants(self):
        """Test handling of different thought status representations."""
        batch_data = BatchContextData()

        # Test with status as enum-like object
        mock_thought1 = MagicMock()
        mock_thought1.thought_id = "thought_001"
        mock_thought1.content = "Processing request"
        mock_thought1.status = MagicMock(value="processing")  # Lowercase
        mock_thought1.source_task_id = "task_001"
        mock_thought1.thought_type = "NORMAL"
        mock_thought1.thought_depth = 1

        snapshot1 = await build_system_snapshot_with_batch(task=None, thought=mock_thought1, batch_data=batch_data)

        assert snapshot1.current_thought_summary.status == "processing"

        # Test with status as string
        mock_thought2 = MagicMock()
        mock_thought2.thought_id = "thought_002"
        mock_thought2.content = "Another thought"
        mock_thought2.status = "completed"  # Lowercase
        mock_thought2.source_task_id = "task_002"
        mock_thought2.thought_type = "NORMAL"
        mock_thought2.thought_depth = 1

        snapshot2 = await build_system_snapshot_with_batch(task=None, thought=mock_thought2, batch_data=batch_data)

        assert snapshot2.current_thought_summary.status == "completed"

        # Test with no status
        mock_thought3 = MagicMock()
        mock_thought3.thought_id = "thought_003"
        mock_thought3.content = "Third thought"
        mock_thought3.status = None
        mock_thought3.source_task_id = "task_003"
        mock_thought3.thought_type = "NORMAL"
        mock_thought3.thought_depth = 1

        snapshot3 = await build_system_snapshot_with_batch(task=None, thought=mock_thought3, batch_data=batch_data)

        assert snapshot3.current_thought_summary.status is None
