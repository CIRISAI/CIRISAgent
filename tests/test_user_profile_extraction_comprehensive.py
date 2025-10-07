"""
Comprehensive test for user profile extraction with full stack mocking.

This test ensures ALL dependencies are properly mocked to track down
why user profiles are not being extracted from the task context.
"""

import json
import logging
import sys
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

# Set up logging to capture all debug messages
logging.basicConfig(level=logging.DEBUG, format="%(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

from ciris_engine.logic.context.system_snapshot import build_system_snapshot
from ciris_engine.schemas.runtime.enums import TaskStatus, ThoughtStatus, ThoughtType
from ciris_engine.schemas.runtime.extended import ShutdownContext
from ciris_engine.schemas.runtime.models import Task, TaskContext, ThoughtContext
from ciris_engine.schemas.runtime.system_context import TelemetrySummary, UserProfile
from ciris_engine.schemas.services.graph_core import GraphNode, GraphNodeAttributes, GraphScope, NodeType
from ciris_engine.schemas.services.operations import MemoryQuery


class MockThought:
    """Mock thought object for testing."""

    def __init__(self, content="", user_id=None):
        self.id = "test_thought_id"
        self.status = ThoughtStatus.PROCESSING
        self.thought_type = ThoughtType.STANDARD
        self.content = content
        self.confidence = 0.8
        self.channel_id = "test_channel"

        if user_id:
            self.context = ThoughtContext(
                task_id="test_task", correlation_id="test_correlation", round_number=1, depth=0, user_id=user_id
            )
        else:
            self.context = ThoughtContext(
                task_id="test_task", correlation_id="test_correlation", round_number=1, depth=0
            )


class TestUserProfileExtractionComprehensive:

    @pytest.fixture
    def mock_time_service(self):
        """Create a mock time service."""
        from datetime import datetime, timezone
        from unittest.mock import Mock

        time_service = Mock()
        # Fixed time for consistent testing
        fixed_time = datetime(2025, 9, 27, 12, 0, 0, tzinfo=timezone.utc)
        time_service.now.return_value = fixed_time
        return time_service

    def create_mock_user_node(self, user_id):
        """Create a properly structured user node."""
        node = MagicMock()
        node.id = f"user/{user_id}"
        node.type = NodeType.USER
        node.scope = GraphScope.LOCAL

        # Create attributes as a dict that will be accessible
        attrs = {
            "username": f"user_{user_id}",
            "email": f"user_{user_id}@example.com",
            "last_seen": datetime.now(timezone.utc).isoformat(),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "first_seen": datetime.now(timezone.utc).isoformat(),
            "trust_level": 0.8,
            "is_wa": False,
            "custom_field": f"custom_value_{user_id}",
            "preferences": {"theme": "dark", "language": "en"},
            "tags": ["active", "verified"],
            "permissions": ["read", "write"],
            "restrictions": [],
            "communication_style": "formal",
            "timezone": "UTC",
            "language": "en",
            "consent_stream": "TEMPORARY",
            "partnership_approved": False,
        }

        # Make attributes accessible both as dict and as attribute
        node.attributes = attrs

        # Also make it work with hasattr checks
        node.__dict__.update(attrs)

        return node

    @pytest.mark.asyncio
    async def test_full_stack_user_extraction(self, mock_time_service):
        """Test user extraction with comprehensive mocking of all dependencies."""

        # Create task with user
        task = Task(
            task_id="test_task",
            channel_id="test_channel",
            description="Test task",
            status=TaskStatus.ACTIVE,
            created_at=datetime.now(timezone.utc).isoformat(),
            updated_at=datetime.now(timezone.utc).isoformat(),
            context=TaskContext(correlation_id="test_correlation", user_id="123456789"),
        )

        # Create thought
        thought = MockThought(content="Test thought content")

        # Create comprehensive mocks for all services

        # 1. Resource Monitor Mock
        resource_monitor = MagicMock()
        resource_monitor.get_current_resources = MagicMock(
            return_value={
                "cpu": {"usage_percent": 10.0},
                "memory": {"used_mb": 100, "available_mb": 4000},
                "disk": {"used_gb": 10, "available_gb": 100},
            }
        )
        resource_monitor.current_memory = 100
        resource_monitor.current_memory_percent = 2.5
        resource_monitor.current_shutdown_context = None

        # 2. Memory Service Mock - CRITICAL
        memory_service = AsyncMock()

        # Create the user node that will be returned
        user_node = self.create_mock_user_node("123456789")

        # Mock recall to return the user node
        async def mock_recall(query):
            print(f"[MOCK RECALL] Called with query: {query}")
            print(f"[MOCK RECALL] Query has node_id: {hasattr(query, 'node_id')}")
            if hasattr(query, "node_id"):
                print(f"[MOCK RECALL] Query node_id: {query.node_id}")
                if "user/123456789" in query.node_id:
                    print(f"[MOCK RECALL] MATCH! Returning user node for 123456789")
                    return [user_node]
            print(f"[MOCK RECALL] No match, returning empty list")
            return []

        memory_service.recall = mock_recall
        memory_service.query_nodes = AsyncMock(return_value=[])
        memory_service.memorize = AsyncMock(return_value=MagicMock(success=True))
        memory_service.query = AsyncMock(return_value=[])
        memory_service.search = AsyncMock(return_value=[])

        # 3. GraphQL Provider Mock
        graphql_provider = AsyncMock()
        graphql_provider.enrich_context = AsyncMock(return_value={})
        graphql_provider.query = AsyncMock(return_value=[])

        # 4. Telemetry Service Mock
        telemetry_service = AsyncMock()
        telemetry_service.capture_service_metrics = AsyncMock(return_value={})
        telemetry_service.get_operational_context = AsyncMock(
            return_value={
                "status": "online",
                "overall_health": "healthy",
                "services_total": 25,
                "services_online": 25,
                "memory_used_mb": 100,
                "memory_percent": 2.5,
            }
        )
        telemetry_service.record_thought = AsyncMock()

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
        telemetry_service.get_telemetry_summary = AsyncMock(return_value=telemetry_summary)
        telemetry_service.get_continuity_summary = AsyncMock(return_value=None)  # No continuity data in tests

        # 5. Secrets Service Mock
        secrets_service = MagicMock()
        secrets_service.list_secrets = MagicMock(return_value=[])

        # 6. Runtime Mock
        runtime = MagicMock()
        runtime.agent_id = "test_agent"
        runtime.current_shutdown_context = None

        # 7. Service Registry Mock
        service_registry = MagicMock()
        service_registry.get_all = MagicMock(return_value={})

        # Patch all external dependencies
        with patch("ciris_engine.logic.context.system_snapshot.build_secrets_snapshot", return_value={}), patch(
            "ciris_engine.logic.context.system_snapshot_helpers.persistence"
        ) as mock_persistence, patch("ciris_engine.logic.persistence.models.graph.get_edges_for_node", return_value=[]):

            # Set up persistence mocks
            mock_persistence.get_recent_completed_tasks.return_value = []
            mock_persistence.get_top_tasks.return_value = []

            # Create proper queue status mock
            queue_status_mock = MagicMock()
            queue_status_mock.total_tasks = 0
            queue_status_mock.queue_size = 0
            queue_status_mock.active_tasks = 0
            queue_status_mock.deferred_tasks = 0
            queue_status_mock.paused = False
            mock_persistence.get_queue_status.return_value = queue_status_mock

            # Mock database connection for correlation history
            mock_cursor = MagicMock()
            mock_cursor.fetchall.return_value = []  # No additional users from correlation
            mock_cursor.fetchone.return_value = None
            mock_conn = MagicMock()
            mock_conn.cursor.return_value = mock_cursor
            mock_conn.__enter__ = MagicMock(return_value=mock_conn)
            mock_conn.__exit__ = MagicMock(return_value=None)
            mock_persistence.get_db_connection.return_value = mock_conn

            # Enable actual logging (not mocked)
            import ciris_engine.logic.context.system_snapshot as snapshot_module

            original_logger = snapshot_module.logger

            try:
                # Replace with a real logger that will output
                snapshot_module.logger = logging.getLogger("ciris_engine.logic.context.system_snapshot")
                snapshot_module.logger.setLevel(logging.DEBUG)

                # Add a handler to capture logs
                import io

                log_capture = io.StringIO()
                handler = logging.StreamHandler(log_capture)
                handler.setLevel(logging.DEBUG)
                snapshot_module.logger.addHandler(handler)

                print(f"\n=== Starting build_system_snapshot ===")
                print(f"Task user_id: {task.context.user_id}")
                print(f"Memory service: {memory_service}")

                # Build the snapshot
                snapshot = await build_system_snapshot(
                    task=task,
                    thought=thought,
                    resource_monitor=resource_monitor,
                    memory_service=memory_service,
                    graphql_provider=graphql_provider,
                    telemetry_service=telemetry_service,
                    secrets_service=secrets_service,
                    runtime=runtime,
                    service_registry=service_registry,
                    time_service=mock_time_service,
                )

                # Get captured logs
                log_output = log_capture.getvalue()
                print(f"\n=== Captured Logs ===")
                for line in log_output.split("\n"):
                    if "USER EXTRACTION" in line or "DEBUG" in line:
                        print(line)

                print(f"\n=== Results ===")
                print(f"Snapshot created: {snapshot is not None}")
                print(f"User profiles count: {len(snapshot.user_profiles) if snapshot else 0}")

                if snapshot and snapshot.user_profiles:
                    for profile in snapshot.user_profiles:
                        print(f"  - User {profile.user_id}: {profile.display_name}")
                        print(f"    Trust level: {profile.trust_level}")
                        print(f"    Has notes: {bool(profile.notes)}")
                        if profile.memorized_attributes:
                            # Check if ALL attributes were captured in memorized_attributes
                            if "custom_field" in profile.memorized_attributes:
                                print(f"    ✓ Custom fields captured")
                            if "preferences" in profile.memorized_attributes:
                                print(f"    ✓ Preferences captured")
                            if "tags" in profile.memorized_attributes:
                                print(f"    ✓ Tags captured")

                # Assertions
                assert snapshot is not None, "Snapshot should be created"
                assert snapshot.user_profiles, f"User profiles should not be empty. Got: {snapshot.user_profiles}"
                assert len(snapshot.user_profiles) > 0, "Should have at least one user profile"

                # Find the user profile
                user_profile = next((p for p in snapshot.user_profiles if p.user_id == "123456789"), None)
                assert user_profile is not None, "User profile for 123456789 should exist"

                # Verify profile data
                assert user_profile.display_name == "user_123456789"
                assert user_profile.trust_level == 0.8
                assert user_profile.is_wa == False

                # Verify ALL custom attributes were captured in memorized_attributes
                assert user_profile.memorized_attributes is not None, "memorized_attributes should not be None"

                # Verify custom fields are captured in memorized_attributes
                assert user_profile.memorized_attributes["custom_field"] == "custom_value_123456789"

                # Verify complex objects are stringified in memorized_attributes
                preferences = json.loads(user_profile.memorized_attributes["preferences"])
                assert preferences["theme"] == "dark"

                tags = json.loads(user_profile.memorized_attributes["tags"])
                assert "active" in tags

                print(f"\n=== TEST PASSED ===")
                print(f"✓ User profile extracted from task context")
                print(f"✓ All user attributes captured")
                print(f"✓ Custom fields preserved")

            finally:
                # Restore original logger
                snapshot_module.logger = original_logger

    @pytest.mark.asyncio
    async def test_extraction_from_correlation_history(self, mock_time_service):
        """Test extraction of users from correlation history."""

        task = Task(
            task_id="test_task",
            channel_id="test_channel",
            description="Test task",
            status=TaskStatus.ACTIVE,
            created_at=datetime.now(timezone.utc).isoformat(),
            updated_at=datetime.now(timezone.utc).isoformat(),
            context=TaskContext(correlation_id="test_correlation_with_history", user_id="123456789"),
        )

        thought = MockThought()

        # Set up mocks
        resource_monitor = MagicMock()
        resource_monitor.get_current_resources = MagicMock(
            return_value={
                "cpu": {"usage_percent": 10.0},
                "memory": {"used_mb": 100, "available_mb": 4000},
                "disk": {"used_gb": 10, "available_gb": 100},
            }
        )
        resource_monitor.current_memory = 100
        resource_monitor.current_memory_percent = 2.5
        resource_monitor.current_shutdown_context = None

        # Memory service that returns users
        memory_service = AsyncMock()

        async def mock_recall(query):
            if hasattr(query, "node_id"):
                if "user/123456789" in query.node_id:
                    return [self.create_mock_user_node("123456789")]
                elif "user/999888777" in query.node_id:
                    return [self.create_mock_user_node("999888777")]
                elif "user/111222333" in query.node_id:
                    return [self.create_mock_user_node("111222333")]
            return []

        memory_service.recall = mock_recall
        memory_service.query = AsyncMock(return_value=[])
        memory_service.search = AsyncMock(return_value=[])
        memory_service.memorize = AsyncMock(return_value=MagicMock(success=True))

        # Other service mocks
        graphql_provider = AsyncMock()
        graphql_provider.enrich_context = AsyncMock(return_value={})

        telemetry_service = AsyncMock()
        telemetry_service.capture_service_metrics = AsyncMock(return_value={})
        telemetry_service.get_operational_context = AsyncMock(
            return_value={
                "status": "online",
                "overall_health": "healthy",
                "services_total": 25,
                "services_online": 25,
                "memory_used_mb": 100,
                "memory_percent": 2.5,
            }
        )
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
        telemetry_service.get_telemetry_summary = AsyncMock(return_value=telemetry_summary)
        telemetry_service.get_continuity_summary = AsyncMock(return_value=None)  # No continuity data in tests

        secrets_service = MagicMock()
        secrets_service.list_secrets = MagicMock(return_value=[])

        runtime = MagicMock()
        runtime.agent_id = "test_agent"
        runtime.current_shutdown_context = None

        service_registry = MagicMock()
        service_registry.get_all = MagicMock(return_value={})

        with patch("ciris_engine.logic.context.system_snapshot.build_secrets_snapshot", return_value={}), patch(
            "ciris_engine.logic.context.system_snapshot_helpers.persistence"
        ) as mock_persistence, patch("ciris_engine.logic.persistence.models.graph.get_edges_for_node", return_value=[]):

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

            # Mock correlation history with additional users
            mock_cursor = MagicMock()

            # First call returns correlation users, subsequent calls return empty
            call_count = [0]

            def fetchall_side_effect():
                call_count[0] += 1
                if call_count[0] == 1:
                    # Return users from correlation history
                    return [
                        {"user_id": "999888777"},
                        {"user_id": "111222333"},
                        {"user_id": "123456789"},  # Duplicate, should be deduplicated
                    ]
                return []

            mock_cursor.fetchall = fetchall_side_effect
            mock_cursor.fetchone.return_value = None

            mock_conn = MagicMock()
            mock_conn.cursor.return_value = mock_cursor
            mock_conn.__enter__ = MagicMock(return_value=mock_conn)
            mock_conn.__exit__ = MagicMock(return_value=None)
            mock_persistence.get_db_connection.return_value = mock_conn

            print(f"\n=== Testing Correlation History Extraction ===")

            snapshot = await build_system_snapshot(
                task=task,
                thought=thought,
                resource_monitor=resource_monitor,
                memory_service=memory_service,
                graphql_provider=graphql_provider,
                telemetry_service=telemetry_service,
                secrets_service=secrets_service,
                runtime=runtime,
                service_registry=service_registry,
                time_service=mock_time_service,
            )

            print(f"User profiles count: {len(snapshot.user_profiles)}")
            user_ids = {p.user_id for p in snapshot.user_profiles}
            print(f"User IDs found: {user_ids}")

            # Should have all three users
            assert "123456789" in user_ids, "Task user should be present"
            assert "999888777" in user_ids, "Correlation user 1 should be present"
            assert "111222333" in user_ids, "Correlation user 2 should be present"
            assert len(user_ids) == 3, "Should have exactly 3 unique users"

            print(f"✓ All users from correlation history extracted")


if __name__ == "__main__":
    pytest.main([__file__, "-xvs", "--tb=short"])
