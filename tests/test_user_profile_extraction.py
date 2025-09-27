"""
Tests for user profile extraction in system_snapshot.py.

Tests that user IDs are properly extracted from:
1. Task context
2. Thought content (Discord mentions)
3. Thought context
4. Correlation history
"""

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ciris_engine.logic.context.system_snapshot import build_system_snapshot
from ciris_engine.schemas.runtime.enums import TaskStatus, ThoughtStatus, ThoughtType
from ciris_engine.schemas.runtime.models import Task, TaskContext, ThoughtContext
from ciris_engine.schemas.services.graph_core import GraphNode, GraphScope, NodeType


class MockThought:
    """Mock thought object for testing."""

    def __init__(self, content="", user_id=None):
        self.id = "test_thought_id"
        self.status = ThoughtStatus.PROCESSING
        self.thought_type = ThoughtType.STANDARD
        self.content = content
        self.confidence = 0.8
        self.channel_id = "test_channel"

        # ThoughtContext doesn't have user_id field
        self.context = ThoughtContext(task_id="test_task", correlation_id="test_correlation", round_number=1, depth=0)
        # Store user_id separately if needed
        if user_id:
            self.context_user_id = user_id
        else:
            self.context_user_id = None


class TestUserProfileExtraction:
    """Test user profile extraction from various sources."""

    @pytest.fixture
    def mock_task_with_user(self):
        """Create a task with user in context."""
        return Task(
            task_id="test_task",
            channel_id="test_channel",
            description="Test task",
            status=TaskStatus.ACTIVE,
            created_at=datetime.now(timezone.utc).isoformat(),
            updated_at=datetime.now(timezone.utc).isoformat(),
            context=TaskContext(correlation_id="test_correlation", user_id="123456789"),  # User from task context
        )

    @pytest.fixture
    def mock_thought_with_mentions(self):
        """Create a thought with Discord mentions."""
        return MockThought(
            content="Hello <@987654321> and <@555666777>, also ID: 111222333"
            # Note: Thoughts don't have user_id field
        )

    @pytest.fixture
    def mock_resource_monitor(self):
        """Create a mock resource monitor."""
        mock = MagicMock()
        mock.get_current_resources = MagicMock(
            return_value={
                "cpu": {"usage_percent": 10.0},
                "memory": {"used_mb": 100, "available_mb": 4000},
                "disk": {"used_gb": 10, "available_gb": 100},
            }
        )
        mock.current_memory = 100
        mock.current_memory_percent = 2.5
        # Add shutdown context attributes
        mock.current_shutdown_context = MagicMock()
        mock.current_shutdown_context.active = False
        mock.current_shutdown_context.reason = None
        mock.current_shutdown_context.initiated_at = None
        mock.current_shutdown_context.deadline = None
        mock.current_shutdown_context.emergency = False
        return mock

    @pytest.fixture
    def mock_memory_service(self):
        """Create a mock memory service that returns user nodes."""
        mock = AsyncMock()

        # Create user nodes for different user IDs
        def create_user_node(user_id):
            return MagicMock(
                id=f"user/{user_id}",
                type=NodeType.USER,
                scope=GraphScope.LOCAL,
                attributes={
                    "username": f"user_{user_id}",
                    "email": f"user_{user_id}@example.com",
                    "last_seen": datetime.now(timezone.utc).isoformat(),
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "trust_level": 0.8,
                    "is_wa": False,
                    "custom_field": f"custom_value_{user_id}",
                    "preferences": {"theme": "dark", "language": "en"},
                    "tags": ["active", "verified"],
                },
            )

        # Mock recall to return user nodes based on query
        async def mock_recall(query):
            if "user/123456789" in query.node_id:
                return [create_user_node("123456789")]
            elif "user/987654321" in query.node_id:
                return [create_user_node("987654321")]
            elif "user/555666777" in query.node_id:
                return [create_user_node("555666777")]
            elif "user/111222333" in query.node_id:
                return [create_user_node("111222333")]
            elif "user/444555666" in query.node_id:
                return [create_user_node("444555666")]
            elif "user/999888777" in query.node_id:
                return [create_user_node("999888777")]
            return []

        mock.recall = mock_recall
        mock.query_nodes = AsyncMock(return_value=[])
        mock.memorize = AsyncMock(return_value=MagicMock(success=True))
        return mock

    @pytest.fixture
    def setup_mocks(self):
        """Set up all required mocks with proper data structures."""
        from datetime import timedelta

        from ciris_engine.schemas.runtime.extended import ShutdownContext
        from ciris_engine.schemas.runtime.system_context import TelemetrySummary

        mocks = {
            "graphql_provider": AsyncMock(),
            "telemetry_service": AsyncMock(),
            "secrets_service": MagicMock(),
            "runtime": MagicMock(),
            "service_registry": MagicMock(),
        }

        # Configure mocks with proper data structures
        mocks["graphql_provider"].enrich_context = AsyncMock(return_value={})
        mocks["telemetry_service"].capture_service_metrics = AsyncMock(return_value={})
        mocks["telemetry_service"].get_operational_context = AsyncMock(
            return_value={
                "status": "online",
                "overall_health": "healthy",
                "services_total": 25,
                "services_online": 25,
                "memory_used_mb": 100,
                "memory_percent": 2.5,
            }
        )

        # Create proper TelemetrySummary
        now = datetime.now(timezone.utc)
        telemetry_summary = TelemetrySummary(
            window_start=now - timedelta(hours=24),
            window_end=now,
            uptime_seconds=86400.0,
            messages_processed_24h=1000,
            thoughts_processed_24h=500,
            tasks_completed_24h=200,
            errors_24h=5,
            messages_current_hour=42,
        )
        mocks["telemetry_service"].get_telemetry_summary = AsyncMock(return_value=telemetry_summary)

        # Set up secrets service
        mocks["secrets_service"].list_secrets = MagicMock(return_value=[])

        # Set up runtime with proper shutdown context
        mocks["runtime"].agent_id = "test_agent"
        mocks["runtime"].current_shutdown_context = None  # No shutdown in progress

        # Set up service registry
        mocks["service_registry"].get_all = MagicMock(return_value={})

        return mocks

    @pytest.mark.asyncio
    async def test_extract_user_from_task_context(
        self, mock_task_with_user, mock_resource_monitor, mock_memory_service, setup_mocks
    ):
        """Test that user ID is extracted from task context."""
        with patch("ciris_engine.logic.context.system_snapshot.logger") as mock_logger, patch(
            "ciris_engine.logic.context.system_snapshot.build_secrets_snapshot", return_value={}
        ), patch("ciris_engine.logic.context.system_snapshot.persistence") as mock_persistence:

            # Set up persistence mocks
            mock_persistence.get_recent_completed_tasks.return_value = []
            mock_persistence.get_top_tasks.return_value = []
            queue_status_mock = MagicMock()
            queue_status_mock.total_tasks = 0
            queue_status_mock.queue_size = 0
            queue_status_mock.active_tasks = 0
            queue_status_mock.deferred_tasks = 0
            queue_status_mock.paused = False
            mock_persistence.get_queue_status.return_value = queue_status_mock
            mock_persistence.get_db_connection.return_value.__enter__.return_value.cursor.return_value.fetchall.return_value = (
                []
            )

            # Build snapshot with task that has user_id
            print(f"DEBUG: Task user_id = {mock_task_with_user.context.user_id}")
            print(f"DEBUG: Memory service = {mock_memory_service}")

            snapshot = await build_system_snapshot(
                task=mock_task_with_user,
                thought=MockThought(),  # No mentions in thought
                resource_monitor=mock_resource_monitor,
                memory_service=mock_memory_service,
                graphql_provider=setup_mocks["graphql_provider"],
                telemetry_service=setup_mocks["telemetry_service"],
                secrets_service=setup_mocks["secrets_service"],
                runtime=setup_mocks["runtime"],
                service_registry=setup_mocks["service_registry"],
            )

            print(f"DEBUG: Snapshot user_profiles = {snapshot.user_profiles}")

            # Check that user extraction was logged
            assert any(
                "[USER EXTRACTION] Found user 123456789 from task context" in str(call)
                for call in mock_logger.debug.call_args_list
            ), "Should log user extraction from task context"

            # Verify user profile was created
            assert snapshot.user_profiles
            assert any(p.user_id == "123456789" for p in snapshot.user_profiles)

            # Verify ALL attributes were captured in notes
            user_profile = next(p for p in snapshot.user_profiles if p.user_id == "123456789")
            assert "custom_field" in user_profile.notes
            assert "custom_value_123456789" in user_profile.notes
            assert "preferences" in user_profile.notes
            assert "tags" in user_profile.notes

    @pytest.mark.asyncio
    async def test_extract_users_from_thought_content(
        self, mock_thought_with_mentions, mock_resource_monitor, mock_memory_service, setup_mocks
    ):
        """Test that user IDs are extracted from Discord mentions and ID patterns."""
        task = Task(
            task_id="test_task",
            channel_id="test_channel",
            description="Test task",
            status=TaskStatus.ACTIVE,
            created_at=datetime.now(timezone.utc).isoformat(),
            updated_at=datetime.now(timezone.utc).isoformat(),
            context=TaskContext(correlation_id="test_correlation"),
        )

        with patch("ciris_engine.logic.context.system_snapshot.logger") as mock_logger, patch(
            "ciris_engine.logic.context.system_snapshot.build_secrets_snapshot", return_value={}
        ), patch("ciris_engine.logic.context.system_snapshot.persistence") as mock_persistence:

            # Set up persistence mocks
            mock_persistence.get_recent_completed_tasks.return_value = []
            mock_persistence.get_top_tasks.return_value = []
            queue_status_mock = MagicMock()
            queue_status_mock.total_tasks = 0
            queue_status_mock.queue_size = 0
            queue_status_mock.active_tasks = 0
            queue_status_mock.deferred_tasks = 0
            queue_status_mock.paused = False
            mock_persistence.get_queue_status.return_value = queue_status_mock
            mock_persistence.get_db_connection.return_value.__enter__.return_value.cursor.return_value.fetchall.return_value = (
                []
            )

            snapshot = await build_system_snapshot(
                task=task,
                thought=mock_thought_with_mentions,
                resource_monitor=mock_resource_monitor,
                memory_service=mock_memory_service,
                graphql_provider=setup_mocks["graphql_provider"],
                telemetry_service=setup_mocks["telemetry_service"],
                secrets_service=setup_mocks["secrets_service"],
                runtime=setup_mocks["runtime"],
                service_registry=setup_mocks["service_registry"],
            )

            # Check extraction logs
            assert any(
                "[USER EXTRACTION] Found 2 users from Discord mentions" in str(call)
                for call in mock_logger.debug.call_args_list
            ), "Should log Discord mention extraction"

            assert any(
                "[USER EXTRACTION] Found 1 users from ID patterns" in str(call)
                for call in mock_logger.debug.call_args_list
            ), "Should log ID pattern extraction"

            # Note: Thoughts don't have user_id field in their context,
            # so we don't expect extraction from thought context

            # Verify all users were extracted
            user_ids = {p.user_id for p in snapshot.user_profiles}
            assert "987654321" in user_ids  # Discord mention
            assert "555666777" in user_ids  # Discord mention
            assert "111222333" in user_ids  # ID pattern
            # Note: 444555666 was from thought context which doesn't exist

    @pytest.mark.asyncio
    async def test_extract_users_from_correlation_history(
        self, mock_resource_monitor, mock_memory_service, setup_mocks
    ):
        """Test that user IDs are extracted from correlation history."""
        task = Task(
            task_id="test_task",
            channel_id="test_channel",
            description="Test task",
            status=TaskStatus.ACTIVE,
            created_at=datetime.now(timezone.utc).isoformat(),
            updated_at=datetime.now(timezone.utc).isoformat(),
            context=TaskContext(correlation_id="test_correlation_with_history", user_id="123456789"),
        )

        with patch("ciris_engine.logic.context.system_snapshot.logger") as mock_logger, patch(
            "ciris_engine.logic.context.system_snapshot.build_secrets_snapshot", return_value={}
        ), patch("ciris_engine.logic.context.system_snapshot.persistence") as mock_persistence:

            # Mock correlation history with additional users
            mock_cursor = MagicMock()
            mock_cursor.fetchall.side_effect = [
                # For correlation history query
                [
                    {"user_id": "999888777"},  # User from correlation history
                    {"user_id": "123456789"},  # Duplicate (already from task)
                ],
                # For other queries
                [],
            ]
            mock_persistence.get_db_connection.return_value.__enter__.return_value.cursor.return_value = mock_cursor
            mock_persistence.get_recent_completed_tasks.return_value = []
            mock_persistence.get_top_tasks.return_value = []
            queue_status_mock = MagicMock()
            queue_status_mock.total_tasks = 0
            queue_status_mock.queue_size = 0
            queue_status_mock.active_tasks = 0
            queue_status_mock.deferred_tasks = 0
            queue_status_mock.paused = False
            mock_persistence.get_queue_status.return_value = queue_status_mock

            snapshot = await build_system_snapshot(
                task=task,
                thought=MockThought(),
                resource_monitor=mock_resource_monitor,
                memory_service=mock_memory_service,
                graphql_provider=setup_mocks["graphql_provider"],
                telemetry_service=setup_mocks["telemetry_service"],
                secrets_service=setup_mocks["secrets_service"],
                runtime=setup_mocks["runtime"],
                service_registry=setup_mocks["service_registry"],
            )

            # Check correlation history extraction
            assert any(
                "[USER EXTRACTION] Found user 999888777 from correlation history" in str(call)
                for call in mock_logger.debug.call_args_list
            ), "Should log correlation history extraction"

            # Verify users were extracted
            user_ids = {p.user_id for p in snapshot.user_profiles}
            assert "123456789" in user_ids  # From task context
            assert "999888777" in user_ids  # From correlation history

    @pytest.mark.asyncio
    async def test_comprehensive_context_logging(
        self, mock_task_with_user, mock_resource_monitor, mock_memory_service, setup_mocks
    ):
        """Test that context building logs comprehensive statistics."""
        with patch("ciris_engine.logic.context.system_snapshot.logger") as mock_logger, patch(
            "ciris_engine.logic.context.system_snapshot.build_secrets_snapshot", return_value={}
        ), patch("ciris_engine.logic.context.system_snapshot.persistence") as mock_persistence:

            # Set up persistence mocks
            mock_persistence.get_recent_completed_tasks.return_value = []
            mock_persistence.get_top_tasks.return_value = []
            queue_status_mock = MagicMock()
            queue_status_mock.total_tasks = 0
            queue_status_mock.queue_size = 0
            queue_status_mock.active_tasks = 0
            queue_status_mock.deferred_tasks = 0
            queue_status_mock.paused = False
            mock_persistence.get_queue_status.return_value = queue_status_mock
            mock_persistence.get_db_connection.return_value.__enter__.return_value.cursor.return_value.fetchall.return_value = (
                []
            )

            snapshot = await build_system_snapshot(
                task=mock_task_with_user,
                thought=MockThought(),
                resource_monitor=mock_resource_monitor,
                memory_service=mock_memory_service,
                graphql_provider=setup_mocks["graphql_provider"],
                telemetry_service=setup_mocks["telemetry_service"],
                secrets_service=setup_mocks["secrets_service"],
                runtime=setup_mocks["runtime"],
                service_registry=setup_mocks["service_registry"],
            )

            # Check comprehensive logging
            info_logs = [str(call) for call in mock_logger.info.call_args_list]
            warning_logs = [str(call) for call in mock_logger.warning.call_args_list]

            # Should log user profile stats
            assert any(
                "[CONTEXT BUILD]" in log and "User Profiles queried" in log and "bytes added to context" in log
                for log in info_logs
            ), "Should log user profile statistics with byte count"

            # Should log final snapshot size - could be in info or warning (warning when no channel context)
            all_logs = info_logs + warning_logs
            assert any(
                "[CONTEXT BUILD] System Snapshot built with" in log and "bytes total" in log for log in all_logs
            ), "Should log total snapshot size"

    @pytest.mark.asyncio
    async def test_all_user_attributes_captured(
        self, mock_task_with_user, mock_resource_monitor, mock_memory_service, setup_mocks
    ):
        """Test that ALL user node attributes are captured in the profile."""
        with patch("ciris_engine.logic.context.system_snapshot.build_secrets_snapshot", return_value={}), patch(
            "ciris_engine.logic.context.system_snapshot.persistence"
        ) as mock_persistence:

            # Set up persistence mocks
            mock_persistence.get_recent_completed_tasks.return_value = []
            mock_persistence.get_top_tasks.return_value = []
            queue_status_mock = MagicMock()
            queue_status_mock.total_tasks = 0
            queue_status_mock.queue_size = 0
            queue_status_mock.active_tasks = 0
            queue_status_mock.deferred_tasks = 0
            queue_status_mock.paused = False
            mock_persistence.get_queue_status.return_value = queue_status_mock
            mock_persistence.get_db_connection.return_value.__enter__.return_value.cursor.return_value.fetchall.return_value = (
                []
            )

            snapshot = await build_system_snapshot(
                task=mock_task_with_user,
                thought=MockThought(),
                resource_monitor=mock_resource_monitor,
                memory_service=mock_memory_service,
                graphql_provider=setup_mocks["graphql_provider"],
                telemetry_service=setup_mocks["telemetry_service"],
                secrets_service=setup_mocks["secrets_service"],
                runtime=setup_mocks["runtime"],
                service_registry=setup_mocks["service_registry"],
            )

            # Get the user profile
            user_profile = next(p for p in snapshot.user_profiles if p.user_id == "123456789")

            # Verify ALL attributes are in notes as JSON
            assert user_profile.notes is not None
            assert "All attributes:" in user_profile.notes

            # Parse the attributes from notes
            import json

            attrs_json = user_profile.notes.split("All attributes: ")[1].split("\n")[0]
            captured_attrs = json.loads(attrs_json)

            # Verify all custom fields are captured
            assert captured_attrs["custom_field"] == "custom_value_123456789"
            assert captured_attrs["preferences"]["theme"] == "dark"
            assert captured_attrs["preferences"]["language"] == "en"
            assert "active" in captured_attrs["tags"]
            assert "verified" in captured_attrs["tags"]
            assert captured_attrs["email"] == "user_123456789@example.com"
            assert captured_attrs["trust_level"] == 0.8


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
