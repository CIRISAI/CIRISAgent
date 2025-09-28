"""
Tests for system snapshot builder - ensuring type safety and proper context extraction.

These tests align with CIRIS principles:
- Type safety (fail fast and loud on violations)
- Proper channel context extraction
- Resource monitoring integration
- Service health tracking
"""

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from ciris_engine.logic.context.system_snapshot import build_system_snapshot
from ciris_engine.schemas.adapters.tools import ToolInfo
from ciris_engine.schemas.runtime.models import Task, TaskStatus
from ciris_engine.schemas.runtime.system_context import ChannelContext, SystemSnapshot, ThoughtSummary, UserProfile
from ciris_engine.schemas.services.graph_core import GraphNode, GraphNodeAttributes, GraphScope, NodeType
from tests.fixtures.mocks import (
    MockMemoryService,
    MockResourceMonitor,
    MockRuntime,
    MockSecretsService,
    MockServiceRegistry,
    MockTelemetryService,
    create_mock_task,
    create_mock_thought,
)


@pytest.fixture
def mock_resource_monitor():
    """Create a mock resource monitor (REQUIRED for system snapshots)."""
    return MockResourceMonitor()


@pytest.fixture
def mock_time_service():
    """Create a mock time service with fixed time."""
    from datetime import datetime, timezone
    from unittest.mock import Mock

    time_service = Mock()
    # Fixed time for consistent testing
    fixed_time = datetime(2025, 9, 27, 12, 0, 0, tzinfo=timezone.utc)
    time_service.now.return_value = fixed_time
    return time_service


@pytest.fixture
def mock_memory_service():
    """Create a mock memory service."""
    return MockMemoryService()


@pytest.fixture
def sample_task():
    """Create a sample task with context."""
    # Task context field is optional, so we can pass None or omit it
    task = Task(
        task_id="task_001",
        channel_id="fallback_channel",
        description="Test task",
        status=TaskStatus.ACTIVE,
        priority=5,
        created_at=datetime.now(timezone.utc).isoformat(),
        updated_at=datetime.now(timezone.utc).isoformat(),
    )
    # Add mock context as an attribute for testing
    mock_context = MagicMock()
    system_snapshot = MagicMock()
    system_snapshot.channel_id = "test_channel_123"
    mock_context.system_snapshot = system_snapshot
    task.context = mock_context
    return task


@pytest.fixture
def sample_thought():
    """Create a sample thought."""
    thought = MagicMock()
    thought.thought_id = "thought_001"
    thought.content = "Processing test request"
    thought.status = MagicMock(value="processing")
    thought.source_task_id = "task_001"
    thought.thought_type = "NORMAL"
    thought.thought_depth = 1
    return thought


class TestBuildSystemSnapshot:
    """Test build_system_snapshot function."""

    @pytest.mark.asyncio
    async def test_build_minimal_snapshot(self, mock_resource_monitor, mock_time_service):
        """Test building snapshot with minimal required inputs."""
        snapshot = await build_system_snapshot(
            task=None, thought=None, resource_monitor=mock_resource_monitor, time_service=mock_time_service
        )

        assert isinstance(snapshot, SystemSnapshot)
        # Resource monitor data should be captured
        assert snapshot.resource_alerts == []  # No critical alerts

    @pytest.mark.asyncio
    async def test_build_with_task_and_thought(
        self, sample_task, sample_thought, mock_resource_monitor, mock_time_service
    ):
        """Test building snapshot with task and thought."""
        # Ensure the sample_task doesn't have channel_context that would cause validation error
        if hasattr(sample_task.context, "system_snapshot") and hasattr(
            sample_task.context.system_snapshot, "channel_context"
        ):
            # Remove channel_context to avoid validation error (MagicMock not accepted by Pydantic)
            delattr(sample_task.context.system_snapshot, "channel_context")

        snapshot = await build_system_snapshot(
            task=sample_task,
            thought=sample_thought,
            resource_monitor=mock_resource_monitor,
            time_service=mock_time_service,
        )

        assert isinstance(snapshot, SystemSnapshot)

        # Check thought summary
        assert snapshot.current_thought_summary is not None
        assert snapshot.current_thought_summary.thought_id == "thought_001"
        assert snapshot.current_thought_summary.status == "processing"

        # Check channel extraction from task context
        assert snapshot.channel_id == "test_channel_123"

    @pytest.mark.asyncio
    async def test_channel_id_extraction_priority(self, mock_resource_monitor, mock_time_service):
        """Test channel_id extraction follows correct priority."""
        # Create task without context first (context field is optional)
        task = Task(
            task_id="task_002",
            channel_id="task_channel",  # Lowest priority
            description="Test",
            status=TaskStatus.PENDING,
            created_at=datetime.now(timezone.utc).isoformat(),
            updated_at=datetime.now(timezone.utc).isoformat(),
        )

        # Add mock context as an attribute with system_snapshot having channel_id
        context = MagicMock()
        system_snapshot = MagicMock()
        system_snapshot.channel_id = "snapshot_channel"  # This becomes the priority
        # Ensure channel_context attribute doesn't exist to avoid validation issues
        system_snapshot.channel_context = None
        context.system_snapshot = system_snapshot
        task.context = context

        snapshot = await build_system_snapshot(
            task=task, thought=None, resource_monitor=mock_resource_monitor, time_service=mock_time_service
        )

        # Should use system_snapshot.channel_id
        assert snapshot.channel_id == "snapshot_channel"

    @pytest.mark.asyncio
    async def test_critical_resource_alerts(self, mock_resource_monitor, mock_time_service):
        """Test critical resource alerts are properly captured."""
        # Set critical resource state
        mock_resource_monitor.snapshot.healthy = False
        mock_resource_monitor.snapshot.critical = ["Memory usage at 95%", "Disk space critically low"]

        snapshot = await build_system_snapshot(
            task=None, thought=None, resource_monitor=mock_resource_monitor, time_service=mock_time_service
        )

        # Should have critical alerts
        assert len(snapshot.resource_alerts) >= 2
        assert any("CRITICAL" in alert for alert in snapshot.resource_alerts)
        assert any("REJECT OR DEFER" in alert for alert in snapshot.resource_alerts)

    @pytest.mark.asyncio
    async def test_memory_service_integration(self, mock_resource_monitor, mock_time_service, mock_memory_service):
        """Test memory service queries for identity and channel context."""
        # Setup mock identity node
        identity_node = GraphNode(
            id="agent/identity",
            type=NodeType.AGENT,
            scope=GraphScope.IDENTITY,
            attributes={
                "agent_id": "test_agent",
                "description": "Test AI Assistant",
                "role_description": "Testing assistant",
                "trust_level": 0.8,
                "permitted_actions": ["speak", "observe"],
                "restricted_capabilities": ["tool"],
            },
        )

        # Setup memory service responses
        async def mock_recall(query):
            if query.node_id == "agent/identity":
                return [identity_node]
            return []

        mock_memory_service.recall = AsyncMock(side_effect=mock_recall)

        snapshot = await build_system_snapshot(
            task=None,
            thought=None,
            resource_monitor=mock_resource_monitor,
            memory_service=mock_memory_service,
            time_service=mock_time_service,
        )

        # Check identity was retrieved
        assert snapshot.agent_identity["agent_id"] == "test_agent"
        assert snapshot.agent_identity["trust_level"] == 0.8
        assert snapshot.identity_purpose == "Testing assistant"
        assert "speak" in snapshot.identity_capabilities
        assert "tool" in snapshot.identity_restrictions

    @pytest.mark.asyncio
    async def test_secrets_service_integration(self, mock_resource_monitor, mock_time_service):
        """Test secrets service integration."""
        mock_secrets = AsyncMock()

        with patch(
            "ciris_engine.logic.context.system_snapshot._get_secrets_data", new_callable=AsyncMock
        ) as mock_build:
            mock_build.return_value = {
                "detected_secrets": ["API_KEY_*", "TOKEN_*"],
                "total_secrets_stored": 5,
                "secrets_filter_version": 2,
            }

            snapshot = await build_system_snapshot(
                task=None,
                thought=None,
                resource_monitor=mock_resource_monitor,
                secrets_service=mock_secrets,
                time_service=mock_time_service,
            )

            # Check secrets snapshot was integrated
            assert len(snapshot.detected_secrets) == 2
            assert snapshot.total_secrets_stored == 5
            assert snapshot.secrets_filter_version == 2

    @pytest.mark.asyncio
    async def test_service_health_tracking(self, mock_resource_monitor, mock_time_service):
        """Test service health and circuit breaker tracking."""
        mock_registry = MagicMock()

        # Mock registry provider info
        mock_registry.get_provider_info.return_value = {
            "handlers": {"speak": {"communication": [MagicMock()]}, "memory": {"memory": [MagicMock()]}}
        }

        # Setup service health checks
        for handler_info in mock_registry.get_provider_info()["handlers"].values():
            for services in handler_info.values():
                for service in services:
                    # get_health_status should return an object with is_healthy attribute
                    health_status = MagicMock()
                    health_status.is_healthy = True
                    service.get_health_status = AsyncMock(return_value=health_status)
                    service.get_circuit_breaker_status = MagicMock(return_value="CLOSED")

        snapshot = await build_system_snapshot(
            task=None,
            thought=None,
            resource_monitor=mock_resource_monitor,
            service_registry=mock_registry,
            time_service=mock_time_service,
        )

        # Check service health was captured
        assert "speak.communication" in snapshot.service_health
        assert snapshot.service_health["speak.communication"] is True
        assert "speak.communication" in snapshot.circuit_breaker_status
        assert snapshot.circuit_breaker_status["speak.communication"] == "CLOSED"

    @pytest.mark.asyncio
    async def test_telemetry_summary_integration(self, mock_resource_monitor, mock_time_service):
        """Test telemetry service integration."""
        mock_telemetry = MockTelemetryService()

        snapshot = await build_system_snapshot(
            task=None,
            thought=None,
            resource_monitor=mock_resource_monitor,
            telemetry_service=mock_telemetry,
            time_service=mock_time_service,
        )

        # Check telemetry was integrated
        assert snapshot.telemetry_summary is not None
        assert snapshot.telemetry_summary.messages_processed_24h == 100
        assert snapshot.telemetry_summary.errors_24h == 2
        assert snapshot.telemetry_summary.cost_last_hour_cents == 15.0

    @pytest.mark.asyncio
    async def test_thought_without_id_gets_default(self, mock_resource_monitor, mock_time_service):
        """Test that thought without ID gets 'unknown' default."""
        thought = MagicMock()
        thought.thought_id = None  # Missing ID
        thought.content = "Test content"
        thought.status = "processing"
        thought.source_task_id = None  # Optional field
        thought.thought_type = None  # Optional field
        thought.thought_depth = None  # Optional field
        thought.context = None  # No context to avoid channel extraction issues

        snapshot = await build_system_snapshot(
            task=None, thought=thought, resource_monitor=mock_resource_monitor, time_service=mock_time_service
        )

        # Should have thought summary with default ID
        assert snapshot.current_thought_summary is not None
        assert snapshot.current_thought_summary.thought_id == "unknown"
        assert snapshot.current_thought_summary.content == "Test content"


class TestUserProfileEnrichment:
    """Test user profile enrichment from memory graph (lines 496-686)."""

    @pytest.mark.asyncio
    async def test_enrich_user_profiles_from_thought_content(self, mock_resource_monitor, mock_time_service):
        """Test extracting and enriching user profiles from thought content."""
        mock_memory = AsyncMock()

        # Mock thought with user mentions
        mock_thought = MagicMock()
        mock_thought.thought_id = "thought_001"
        mock_thought.content = "User <@123456> said hello, and ID: 789012 responded"
        mock_thought.status = "processing"
        mock_thought.source_task_id = None  # Optional field
        mock_thought.thought_type = None  # Optional field
        mock_thought.thought_depth = None  # Optional field
        mock_thought.context = MagicMock()
        mock_thought.context.user_id = "555555"
        # Ensure no channel extraction issues
        mock_thought.context.system_snapshot = None

        # Mock user node responses
        async def mock_recall(query):
            if "user/123456" in query.node_id:
                return [
                    GraphNode(
                        id="user/123456",
                        type=NodeType.USER,
                        scope=GraphScope.LOCAL,
                        attributes={
                            "user_id": "123456",
                            "username": "TestUser",
                            "trust_level": 0.8,
                            "is_wa": False,
                            "permissions": ["read", "write"],
                        },
                    )
                ]
            elif "user/789012" in query.node_id:
                return [
                    GraphNode(
                        id="user/789012",
                        type=NodeType.USER,
                        scope=GraphScope.LOCAL,
                        attributes={
                            "user_id": "789012",
                            "display_name": "AdminUser",
                            "trust_level": 0.95,
                            "is_wa": True,
                        },
                    )
                ]
            elif "user/555555" in query.node_id:
                return [
                    GraphNode(
                        id="user/555555",
                        type=NodeType.USER,
                        scope=GraphScope.LOCAL,
                        attributes={"user_id": "555555", "username": "ContextUser", "communication_style": "casual"},
                    )
                ]
            return []

        mock_memory.recall = AsyncMock(side_effect=mock_recall)

        # Mock get_edges_for_node
        with patch("ciris_engine.logic.persistence.models.graph.get_edges_for_node") as mock_edges:
            mock_edges.return_value = []

            snapshot = await build_system_snapshot(
                task=None,
                thought=mock_thought,
                resource_monitor=mock_resource_monitor,
                memory_service=mock_memory,
                time_service=mock_time_service,
            )

        # Should have enriched 3 user profiles
        assert len(snapshot.user_profiles) == 3

        # Find each user and verify enrichment
        user_123456 = next((p for p in snapshot.user_profiles if p.user_id == "123456"), None)
        assert user_123456 is not None
        assert user_123456.display_name == "TestUser"
        assert user_123456.trust_level == 0.8
        assert user_123456.is_wa is False
        assert "read" in user_123456.permissions

        user_789012 = next((p for p in snapshot.user_profiles if p.user_id == "789012"), None)
        assert user_789012 is not None
        assert user_789012.display_name == "AdminUser"
        assert user_789012.is_wa is True

        user_555555 = next((p for p in snapshot.user_profiles if p.user_id == "555555"), None)
        assert user_555555 is not None
        assert user_555555.display_name == "ContextUser"

    @pytest.mark.asyncio
    async def test_user_profile_with_cross_channel_messages(self, mock_resource_monitor, mock_time_service):
        """Test enriching user profiles with messages from other channels."""
        mock_memory = AsyncMock()

        mock_thought = MagicMock()
        mock_thought.thought_id = "thought_002"
        mock_thought.content = "User ID: 999888 needs help"
        mock_thought.status = "processing"
        mock_thought.source_task_id = None  # Optional field
        mock_thought.thought_type = None  # Optional field
        mock_thought.thought_depth = None  # Optional field
        mock_thought.context = None  # No context to avoid MagicMock user_id extraction

        # Mock task with channel context - set user_id to None to avoid extraction
        mock_task = MagicMock()
        mock_task.context = MagicMock()
        mock_task.context.user_id = None  # Explicitly set to None
        mock_task.context.system_snapshot = MagicMock()
        mock_task.context.system_snapshot.channel_id = "current_channel"
        mock_task.context.system_snapshot.channel_context = None  # Avoid MagicMock validation issues

        # Mock user node
        mock_memory.recall = AsyncMock(
            return_value=[
                GraphNode(
                    id="user/999888",
                    type=NodeType.USER,
                    scope=GraphScope.LOCAL,
                    attributes={"user_id": "999888", "username": "CrossChannelUser"},
                )
            ]
        )

        # Mock database connection for cross-channel messages
        with patch("ciris_engine.logic.persistence.get_db_connection") as mock_db_conn:
            mock_conn = MagicMock()
            mock_cursor = MagicMock()

            # Mock fetchall to return messages from other channels
            mock_cursor.fetchall.return_value = [
                {
                    "tags": json.dumps({"user_id": "999888", "channel_id": "other_channel"}),
                    "request_data": json.dumps({"content": "Hello from other channel"}),
                    "created_at": datetime.now(timezone.utc),
                }
            ]

            mock_conn.cursor.return_value = mock_cursor
            mock_conn.__enter__ = MagicMock(return_value=mock_conn)
            mock_conn.__exit__ = MagicMock(return_value=None)
            mock_db_conn.return_value = mock_conn

            with patch("ciris_engine.logic.persistence.models.graph.get_edges_for_node") as mock_edges:
                mock_edges.return_value = []

                snapshot = await build_system_snapshot(
                    task=mock_task,
                    thought=mock_thought,
                    resource_monitor=mock_resource_monitor,
                    memory_service=mock_memory,
                    time_service=mock_time_service,
                )

        # Verify user profile was enriched with cross-channel messages
        assert len(snapshot.user_profiles) == 1
        user_profile = snapshot.user_profiles[0]
        assert "other_channel" in user_profile.notes
        assert "Hello from other channel" in user_profile.notes


class TestAdapterIntegration:
    """Test adapter channels and tools collection with FAIL FAST behavior."""

    @pytest.mark.asyncio
    async def test_adapter_channels_collection_success(self, mock_resource_monitor, mock_time_service):
        """Test successful collection of adapter channels."""
        mock_runtime = MagicMock()
        mock_adapter_manager = MagicMock()

        # Create mock adapters with channels
        mock_discord_adapter = MagicMock()
        mock_discord_adapter.get_channel_list.return_value = [
            ChannelContext(
                channel_id="discord_123", channel_type="discord", created_at=datetime.now(timezone.utc), is_active=True
            ),
            ChannelContext(
                channel_id="discord_456", channel_type="discord", created_at=datetime.now(timezone.utc), is_active=True
            ),
        ]

        mock_api_adapter = MagicMock()
        mock_api_adapter.get_channel_list.return_value = [
            ChannelContext(
                channel_id="api_789", channel_type="api", created_at=datetime.now(timezone.utc), is_active=True
            )
        ]

        mock_adapter_manager._adapters = {"discord": mock_discord_adapter, "api": mock_api_adapter}

        mock_runtime.adapter_manager = mock_adapter_manager
        mock_runtime.current_shutdown_context = None  # Ensure no MagicMock for shutdown_context

        snapshot = await build_system_snapshot(
            task=None,
            thought=None,
            resource_monitor=mock_resource_monitor,
            runtime=mock_runtime,
            time_service=mock_time_service,
        )

        # Verify adapter channels were collected
        assert "discord" in snapshot.adapter_channels
        assert len(snapshot.adapter_channels["discord"]) == 2
        assert "api" in snapshot.adapter_channels
        assert len(snapshot.adapter_channels["api"]) == 1

    @pytest.mark.asyncio
    async def test_adapter_channels_fail_fast_on_invalid_type(self, mock_resource_monitor, mock_time_service):
        """Test FAIL FAST when adapter returns invalid channel type."""
        mock_runtime = MagicMock()
        mock_adapter_manager = MagicMock()

        # Create adapter that returns wrong type
        mock_bad_adapter = MagicMock()
        mock_bad_adapter.get_channel_list.return_value = [
            {"channel_id": "bad", "type": "wrong"}  # Not a ChannelContext!
        ]

        mock_adapter_manager._adapters = {"bad": mock_bad_adapter}
        mock_runtime.adapter_manager = mock_adapter_manager

        # Should raise TypeError - FAIL FAST AND LOUD
        with pytest.raises(TypeError) as exc_info:
            await build_system_snapshot(
                task=None, thought=None, resource_monitor=mock_resource_monitor, runtime=mock_runtime
            )

        assert "returned invalid channel list type" in str(exc_info.value)
        assert "expected ChannelContext" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_available_tools_collection_success(self, mock_resource_monitor, mock_time_service):
        """Test successful collection of available tools."""
        mock_runtime = MagicMock()
        mock_service_registry = MagicMock()

        # Create mock tool service
        mock_tool_service = MagicMock()
        mock_tool_service.adapter_id = "discord_tool"
        mock_tool_service.get_available_tools.return_value = ["speak", "observe"]

        def get_tool_info(name):
            from ciris_engine.schemas.adapters.tools import ToolParameterSchema

            if name == "speak":
                return ToolInfo(
                    name="speak",
                    description="Send a message",
                    parameters=ToolParameterSchema(type="object", properties={"message": {"type": "string"}}),
                )
            elif name == "observe":
                return ToolInfo(
                    name="observe",
                    description="Observe a message",
                    parameters=ToolParameterSchema(type="object", properties={"channel": {"type": "string"}}),
                )
            return None

        mock_tool_service.get_tool_info = get_tool_info

        mock_service_registry.get_services_by_type.return_value = [mock_tool_service]

        mock_runtime.bus_manager = MagicMock()
        mock_runtime.service_registry = mock_service_registry
        mock_runtime.current_shutdown_context = None  # Ensure no MagicMock for shutdown_context

        snapshot = await build_system_snapshot(
            task=None,
            thought=None,
            resource_monitor=mock_resource_monitor,
            runtime=mock_runtime,
            time_service=mock_time_service,
        )

        # Verify tools were collected
        assert "discord" in snapshot.available_tools
        assert len(snapshot.available_tools["discord"]) == 2
        tool_names = [t.name for t in snapshot.available_tools["discord"]]
        assert "speak" in tool_names
        assert "observe" in tool_names

    @pytest.mark.asyncio
    async def test_available_tools_fail_fast_on_invalid_type(self, mock_resource_monitor, mock_time_service):
        """Test FAIL FAST when tool service returns invalid type."""
        mock_runtime = MagicMock()
        mock_service_registry = MagicMock()

        # Create tool service that returns wrong type
        mock_bad_tool_service = MagicMock()
        mock_bad_tool_service.adapter_id = "bad_tool"
        mock_bad_tool_service.get_available_tools.return_value = ["tool1"]
        mock_bad_tool_service.get_tool_info.return_value = {"name": "tool1"}  # Not ToolInfo!

        mock_service_registry.get_services_by_type.return_value = [mock_bad_tool_service]

        mock_runtime.bus_manager = MagicMock()
        mock_runtime.service_registry = mock_service_registry
        mock_runtime.current_shutdown_context = None  # Ensure no MagicMock for shutdown_context

        # Should raise TypeError - FAIL FAST AND LOUD
        with pytest.raises(TypeError) as exc_info:
            await build_system_snapshot(
                task=None, thought=None, resource_monitor=mock_resource_monitor, runtime=mock_runtime
            )

        assert "returned invalid type" in str(exc_info.value)
        assert "expected ToolInfo" in str(exc_info.value)


class TestChannelContextExtraction:
    """Test channel context extraction logic and edge cases."""

    @pytest.mark.asyncio
    async def test_channel_search_fallback(self, mock_resource_monitor, mock_time_service):
        """Test channel search when direct lookup fails."""
        mock_memory = AsyncMock()

        # First recall returns empty (direct lookup fails)
        # Then search is called
        mock_memory.recall = AsyncMock(return_value=[])
        mock_memory.search = AsyncMock(
            return_value=[
                GraphNode(
                    id="channel/found_channel",
                    type=NodeType.CHANNEL,
                    scope=GraphScope.LOCAL,
                    attributes={"channel_id": "found_channel", "channel_type": "discord"},
                )
            ]
        )

        mock_task = MagicMock()
        mock_task.context = MagicMock()
        mock_task.context.system_snapshot = MagicMock()
        mock_task.context.system_snapshot.channel_id = "found_channel"
        mock_task.context.system_snapshot.channel_context = None  # Avoid MagicMock validation issues

        snapshot = await build_system_snapshot(
            task=mock_task,
            thought=None,
            resource_monitor=mock_resource_monitor,
            memory_service=mock_memory,
            time_service=mock_time_service,
        )

        # Verify search was called as fallback
        mock_memory.search.assert_called_once()
        assert snapshot.channel_id == "found_channel"

    @pytest.mark.asyncio
    async def test_channel_extraction_from_dict_context(self, mock_resource_monitor, mock_time_service):
        """Test channel extraction when context is a dict."""
        mock_task = MagicMock()
        mock_task.context = {"channel_id": "dict_channel"}

        snapshot = await build_system_snapshot(
            task=mock_task, thought=None, resource_monitor=mock_resource_monitor, time_service=mock_time_service
        )

        assert snapshot.channel_id == "dict_channel"

    @pytest.mark.asyncio
    async def test_channel_extraction_handles_exception(self, mock_resource_monitor, mock_time_service):
        """Test channel extraction handles exceptions gracefully."""
        mock_task = MagicMock()

        # Create a context that will raise an exception
        class BadContext:
            @property
            def system_snapshot(self):
                raise RuntimeError("Context access failed")

        mock_task.context = BadContext()

        # Should handle exception and continue
        snapshot = await build_system_snapshot(
            task=mock_task, thought=None, resource_monitor=mock_resource_monitor, time_service=mock_time_service
        )

        assert snapshot.channel_id is None


class TestGraphQLIntegration:
    """Test GraphQL provider integration for user profiles."""

    @pytest.mark.asyncio
    async def test_graphql_user_profile_conversion(self, mock_resource_monitor, mock_time_service):
        """Test conversion of GraphQL profiles to UserProfile."""
        mock_graphql = AsyncMock()

        # Create mock enriched context
        mock_enriched = MagicMock()

        # Create mock GraphQL user profiles
        mock_graphql_profile = MagicMock()
        mock_graphql_profile.nick = "GraphQLUser"
        mock_graphql_profile.trust_score = 0.85
        mock_graphql_profile.last_seen = "2025-01-01T12:00:00"

        mock_attr1 = MagicMock()
        mock_attr1.key = "is_wa"
        mock_attr1.value = "true"

        mock_attr2 = MagicMock()
        mock_attr2.key = "permission"
        mock_attr2.value = "admin"

        mock_graphql_profile.attributes = [mock_attr1, mock_attr2]

        mock_enriched.user_profiles = [("user123", mock_graphql_profile)]
        mock_enriched.identity_context = {"source": "graphql"}
        mock_enriched.community_context = {"server": "test"}

        mock_graphql.enrich_context = AsyncMock(return_value=mock_enriched)

        snapshot = await build_system_snapshot(
            task=None,
            thought=None,
            resource_monitor=mock_resource_monitor,
            graphql_provider=mock_graphql,
            time_service=mock_time_service,
        )

        # Verify GraphQL profiles were converted
        assert len(snapshot.user_profiles) == 1
        profile = snapshot.user_profiles[0]
        assert profile.user_id == "user123"
        assert profile.display_name == "GraphQLUser"
        assert profile.trust_level == 0.85
        assert profile.is_wa is True
        assert "admin" in profile.permissions

        # Note: identity_context and community_context are not SystemSnapshot fields
        # They would need to be added to the schema if needed

    @pytest.mark.asyncio
    async def test_graphql_consent_attributes_extraction(self, mock_resource_monitor, mock_time_service):
        """Test extraction of consent attributes from GraphQL profiles."""
        mock_graphql = AsyncMock()
        mock_enriched = MagicMock()

        # Create GraphQL profile with consent attributes
        mock_profile = MagicMock()
        mock_profile.nick = "ConsentUser"
        mock_profile.trust_score = 0.7
        mock_profile.last_seen = "2025-01-20T12:00:00"

        # Consent stream attribute
        consent_attr = MagicMock()
        consent_attr.key = "consent_stream"
        consent_attr.value = "PARTNERED"

        # Consent expires at attribute
        expires_attr = MagicMock()
        expires_attr.key = "consent_expires_at"
        expires_attr.value = "2025-12-31T23:59:59"

        # Partnership requested at attribute
        partnership_attr = MagicMock()
        partnership_attr.key = "partnership_requested_at"
        partnership_attr.value = "2025-01-15T10:00:00"

        mock_profile.attributes = [consent_attr, expires_attr, partnership_attr]
        mock_enriched.user_profiles = [("consent_user", mock_profile)]

        mock_graphql.enrich_context = AsyncMock(return_value=mock_enriched)

        snapshot = await build_system_snapshot(
            task=None,
            thought=None,
            resource_monitor=mock_resource_monitor,
            graphql_provider=mock_graphql,
            time_service=mock_time_service,
        )

        # Verify consent attributes were extracted
        assert len(snapshot.user_profiles) == 1
        profile = snapshot.user_profiles[0]
        assert profile.consent_stream == "PARTNERED"
        assert profile.consent_expires_at is not None
        assert profile.partnership_requested_at is not None

    @pytest.mark.asyncio
    async def test_graphql_consent_invalid_dates(self, mock_resource_monitor, mock_time_service):
        """Test handling of invalid dates in consent attributes."""
        mock_graphql = AsyncMock()
        mock_enriched = MagicMock()

        # Create profile with invalid date values
        mock_profile = MagicMock()
        mock_profile.nick = "BadDateUser"
        mock_profile.trust_score = 0.5
        mock_profile.last_seen = None

        # Invalid expires date
        expires_attr = MagicMock()
        expires_attr.key = "consent_expires_at"
        expires_attr.value = "not-a-date"

        # Invalid partnership date
        partnership_attr = MagicMock()
        partnership_attr.key = "partnership_requested_at"
        partnership_attr.value = None  # Will cause TypeError

        mock_profile.attributes = [expires_attr, partnership_attr]
        mock_enriched.user_profiles = [("bad_date_user", mock_profile)]

        mock_graphql.enrich_context = AsyncMock(return_value=mock_enriched)

        # Should handle invalid dates gracefully
        snapshot = await build_system_snapshot(
            task=None,
            thought=None,
            resource_monitor=mock_resource_monitor,
            graphql_provider=mock_graphql,
            time_service=mock_time_service,
        )

        # Profile created but dates are None
        assert len(snapshot.user_profiles) == 1
        profile = snapshot.user_profiles[0]
        assert profile.consent_expires_at is None
        assert profile.partnership_requested_at is None


class TestServiceHealthCollection:
    """Test service health and circuit breaker status collection."""

    @pytest.mark.asyncio
    async def test_global_services_health_collection(self, mock_resource_monitor, mock_time_service):
        """Test collecting health from global services."""
        mock_registry = MagicMock()

        # Create mock global service
        mock_global_service = MagicMock()  # Use MagicMock not AsyncMock
        mock_health = MagicMock()
        mock_health.is_healthy = True
        mock_global_service.get_health_status = AsyncMock(return_value=mock_health)
        mock_global_service.get_circuit_breaker_status = MagicMock(return_value="CLOSED")

        mock_registry.get_provider_info.return_value = {
            "handlers": {},
            "global_services": {"telemetry": [mock_global_service]},
        }

        snapshot = await build_system_snapshot(
            task=None,
            thought=None,
            resource_monitor=mock_resource_monitor,
            service_registry=mock_registry,
            time_service=mock_time_service,
        )

        # Verify global service health was collected
        assert "global.telemetry" in snapshot.service_health
        assert snapshot.service_health["global.telemetry"] is True
        assert "global.telemetry" in snapshot.circuit_breaker_status
        assert snapshot.circuit_breaker_status["global.telemetry"] == "CLOSED"


class TestResourceMonitorEdgeCases:
    """Test resource monitor unavailability and exceptions."""

    @pytest.mark.asyncio
    async def test_resource_monitor_unavailable(self, mock_time_service):
        """Test when resource monitor is None."""
        # Should handle None resource monitor
        snapshot = await build_system_snapshot(
            task=None, thought=None, resource_monitor=None, time_service=mock_time_service
        )  # Unavailable

        # Should have warning in alerts
        assert len(snapshot.resource_alerts) == 0  # No alerts when monitor unavailable

    @pytest.mark.asyncio
    async def test_resource_monitor_exception(self, mock_time_service):
        """Test when resource monitor throws exception."""
        mock_monitor = MagicMock()
        # Make snapshot a property that throws exception when accessed
        mock_monitor.snapshot = property(lambda self: (_ for _ in ()).throw(RuntimeError("Monitor failed")))

        snapshot = await build_system_snapshot(
            task=None, thought=None, resource_monitor=mock_monitor, time_service=mock_time_service
        )

        # Should have critical alert about failure
        assert len(snapshot.resource_alerts) > 0
        assert any("CRITICAL! FAILED TO CHECK RESOURCES" in alert for alert in snapshot.resource_alerts)


class TestToolServiceValidation:
    """Test tool service validation and error handling."""

    @pytest.mark.asyncio
    async def test_tool_services_non_iterable(self, mock_resource_monitor, mock_time_service):
        """Test handling when get_services_by_type returns non-iterable."""
        mock_runtime = MagicMock()
        mock_registry = MagicMock()

        # Return non-iterable (single object instead of list)
        mock_registry.get_services_by_type.return_value = MagicMock()  # Not iterable!

        mock_runtime.service_registry = mock_registry
        mock_runtime.bus_manager = MagicMock()
        mock_runtime.current_shutdown_context = None

        # Should handle gracefully
        snapshot = await build_system_snapshot(
            task=None,
            thought=None,
            resource_monitor=mock_resource_monitor,
            runtime=mock_runtime,
            time_service=mock_time_service,
        )

        # Should have empty tools (fallback to empty list)
        assert snapshot.available_tools == {}


class TestChannelContextExtraction:
    """Test channel context extraction including system_snapshot.channel_context."""

    @pytest.mark.asyncio
    async def test_channel_context_object_extraction(self, mock_resource_monitor, mock_time_service):
        """Test extracting channel_context object from system_snapshot."""
        mock_task = MagicMock()
        mock_context = MagicMock()
        mock_system_snapshot = MagicMock()

        # Create proper ChannelContext object
        from ciris_engine.schemas.runtime.system_context import ChannelContext

        channel_ctx = ChannelContext(
            channel_id="context_channel_123",
            channel_type="discord",
            created_at=datetime.now(timezone.utc),
            is_active=True,
        )

        mock_system_snapshot.channel_context = channel_ctx
        mock_context.system_snapshot = mock_system_snapshot
        mock_task.context = mock_context

        snapshot = await build_system_snapshot(
            task=mock_task, thought=None, resource_monitor=mock_resource_monitor, time_service=mock_time_service
        )

        # Should extract channel_id from channel_context object
        assert snapshot.channel_id == "context_channel_123"
        assert snapshot.channel_context is not None
        assert snapshot.channel_context.channel_type == "discord"


class TestTypeEnforcement:
    """Test that type safety is enforced (fail fast and loud)."""

    @pytest.mark.asyncio
    async def test_snapshot_requires_resource_monitor(self):
        """Test that resource_monitor is required."""
        # Should fail without resource_monitor
        with pytest.raises(TypeError):
            await build_system_snapshot(
                task=None,
                thought=None,
                # Missing required resource_monitor
            )

    @pytest.mark.asyncio
    async def test_invalid_task_type_fails(self, mock_resource_monitor, mock_time_service):
        """Test that invalid task type is handled gracefully."""
        # Create an object that looks like a task but isn't a proper Task
        invalid_task = MagicMock()
        invalid_task.context = None  # No context to avoid AttributeError
        invalid_task.task_id = "invalid_task"
        invalid_task.channel_id = None

        # Should handle gracefully
        snapshot = await build_system_snapshot(
            task=invalid_task, thought=None, resource_monitor=mock_resource_monitor, time_service=mock_time_service
        )

        # The function handles this by checking attributes
        assert snapshot.channel_id is None  # No channel extracted from invalid object

    @pytest.mark.asyncio
    async def test_channel_context_type_preservation(self, mock_resource_monitor, mock_time_service):
        """Test that channel_id is properly extracted from task context."""
        # Create task without context in constructor (to avoid validation error)
        task = Task(
            task_id="task_typed",
            channel_id="fallback",
            description="Test",
            status=TaskStatus.ACTIVE,
            created_at=datetime.now(timezone.utc).isoformat(),
            updated_at=datetime.now(timezone.utc).isoformat(),
        )

        # Add mock context as an attribute after creation
        context = MagicMock()
        system_snapshot = MagicMock()
        system_snapshot.channel_id = "typed_channel"
        system_snapshot.channel_context = None  # Avoid MagicMock validation issues
        context.system_snapshot = system_snapshot
        task.context = context

        snapshot = await build_system_snapshot(
            task=task, thought=None, resource_monitor=mock_resource_monitor, time_service=mock_time_service
        )

        # Channel ID should be extracted from context
        assert snapshot.channel_id == "typed_channel"
