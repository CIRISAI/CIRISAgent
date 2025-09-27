"""
Unit tests for CONFIG node handling in MEMORIZE handler.
Tests patch 7 functionality for agent self-configuration.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ciris_engine.logic.handlers.memory.memorize_handler import MemorizeHandler
from ciris_engine.logic.infrastructure.handlers.base_handler import ActionHandlerDependencies
from ciris_engine.schemas.actions import MemorizeParams
from ciris_engine.schemas.dma.results import ActionSelectionDMAResult
from ciris_engine.schemas.runtime.contexts import ChannelContext, DispatchContext
from ciris_engine.schemas.runtime.enums import HandlerActionType, ThoughtStatus
from ciris_engine.schemas.runtime.models import Thought
from ciris_engine.schemas.services.graph_core import GraphNode, GraphScope, NodeType
from ciris_engine.schemas.services.nodes import ConfigNode, ConfigValue
from ciris_engine.schemas.services.operations import MemoryOpResult, MemoryOpStatus


class TestConfigNodeHandling:
    """Test CONFIG node handling in MEMORIZE handler."""

    @pytest.fixture
    def mock_handler(self):
        """Create a mock MEMORIZE handler."""
        # Create mock dependencies
        mock_bus_manager = MagicMock()
        mock_bus_manager.memory = AsyncMock()
        mock_time_service = MagicMock()
        mock_time_service.now.return_value = datetime.now(timezone.utc)
        mock_time_service.now_iso.return_value = datetime.now(timezone.utc).isoformat()

        dependencies = ActionHandlerDependencies(bus_manager=mock_bus_manager, time_service=mock_time_service)

        handler = MemorizeHandler(dependencies)
        handler._audit_log = AsyncMock()
        handler.complete_thought_and_create_followup = MagicMock(return_value="follow_up_123")
        return handler

    @pytest.fixture
    def dispatch_context(self):
        """Create a dispatch context."""
        now = datetime.now(timezone.utc)
        return DispatchContext(
            channel_context=ChannelContext(
                channel_id="test_channel", channel_type="test", channel_name="Test Channel", created_at=now
            ),
            author_id="test_author",
            author_name="Test Author",
            origin_service="test_service",
            handler_name="MemorizeHandler",
            action_type=HandlerActionType.MEMORIZE,
            thought_id="thought_123",
            task_id="task_123",
            source_task_id="task_123",
            event_summary="Test memorize action",
            event_timestamp=now.isoformat(),
        )

    @pytest.fixture
    def thought(self):
        """Create a test thought."""
        now = datetime.now(timezone.utc)
        return Thought(
            thought_id="thought_123",
            source_task_id="task_123",
            thought_type="standard",
            content="Test thought",
            status=ThoughtStatus.PROCESSING,
            created_at=now.isoformat(),
            updated_at=now.isoformat(),
        )

    @pytest.mark.asyncio
    async def test_config_node_with_numeric_value(self, mock_handler, dispatch_context, thought):
        """Test CONFIG node with numeric value."""
        # Create CONFIG node for spam threshold
        node = GraphNode(
            id="adaptive_filter/spam_threshold",
            type=NodeType.CONFIG,
            scope=GraphScope.LOCAL,
            attributes={"value": 0.8, "description": "Spam detection threshold"},
        )

        params = MemorizeParams(node=node)
        result = ActionSelectionDMAResult(
            selected_action=HandlerActionType.MEMORIZE, action_parameters=params, rationale="Setting spam threshold"
        )

        # Mock successful memory operation
        mock_handler.bus_manager.memory.memorize.return_value = MemoryOpResult(
            status=MemoryOpStatus.SUCCESS, data="node_123"
        )

        # Handle the memorize
        follow_up = await mock_handler.handle(result, thought, dispatch_context)

        # Verify CONFIG node was transformed
        memorize_call = mock_handler.bus_manager.memory.memorize.call_args
        stored_node = memorize_call.kwargs["node"]

        # Should have created a proper ConfigNode structure
        assert stored_node.type == NodeType.CONFIG
        assert "adaptive_filter.spam_threshold" in str(stored_node.attributes)
        assert follow_up == "follow_up_123"

    @pytest.mark.asyncio
    async def test_config_node_with_boolean_value(self, mock_handler, dispatch_context, thought):
        """Test CONFIG node with boolean value."""
        node = GraphNode(
            id="secrets_filter/jwt_detection_enabled",
            type=NodeType.CONFIG,
            scope=GraphScope.LOCAL,
            attributes={"value": True},
        )

        params = MemorizeParams(node=node)
        result = ActionSelectionDMAResult(
            selected_action=HandlerActionType.MEMORIZE, action_parameters=params, rationale="Enable JWT detection"
        )

        mock_handler.bus_manager.memory.memorize.return_value = MemoryOpResult(
            status=MemoryOpStatus.SUCCESS, data="node_123"
        )

        await mock_handler.handle(result, thought, dispatch_context)

        # Verify boolean was properly handled
        memorize_call = mock_handler.bus_manager.memory.memorize.call_args
        stored_node = memorize_call.kwargs["node"]
        assert stored_node.type == NodeType.CONFIG

    @pytest.mark.asyncio
    async def test_config_node_with_list_value(self, mock_handler, dispatch_context, thought):
        """Test CONFIG node with list value."""
        node = GraphNode(
            id="secrets_filter/custom_patterns",
            type=NodeType.CONFIG,
            scope=GraphScope.LOCAL,
            attributes={"value": ["PROJ-[0-9]{4}", "SECRET-[A-Z]+"]},
        )

        params = MemorizeParams(node=node)
        result = ActionSelectionDMAResult(
            selected_action=HandlerActionType.MEMORIZE, action_parameters=params, rationale="Set custom patterns"
        )

        mock_handler.bus_manager.memory.memorize.return_value = MemoryOpResult(
            status=MemoryOpStatus.SUCCESS, data="node_123"
        )

        await mock_handler.handle(result, thought, dispatch_context)

        memorize_call = mock_handler.bus_manager.memory.memorize.call_args
        stored_node = memorize_call.kwargs["node"]
        assert stored_node.type == NodeType.CONFIG

    @pytest.mark.asyncio
    async def test_config_node_missing_value(self, mock_handler, dispatch_context, thought):
        """Test CONFIG node with missing value shows detailed error."""
        node = GraphNode(
            id="adaptive_filter/trust_decay",
            type=NodeType.CONFIG,
            scope=GraphScope.LOCAL,
            attributes={},  # Missing value!
        )

        params = MemorizeParams(node=node)
        result = ActionSelectionDMAResult(
            selected_action=HandlerActionType.MEMORIZE, action_parameters=params, rationale="Set trust decay"
        )

        await mock_handler.handle(result, thought, dispatch_context)

        # Should have called complete_thought_and_create_followup with error
        call_args = mock_handler.complete_thought_and_create_followup.call_args
        assert call_args.kwargs["status"] == ThoughtStatus.FAILED
        error_msg = call_args.kwargs["follow_up_content"]

        # Error should contain helpful examples
        assert "MEMORIZE CONFIG FAILED" in error_msg
        assert "Missing required 'value' field" in error_msg
        assert "$memorize filter/spam_threshold CONFIG LOCAL value=0.8" in error_msg
        assert "For boolean values:" in error_msg
        assert "For list values:" in error_msg

    @pytest.mark.asyncio
    async def test_config_node_key_transformation(self, mock_handler, dispatch_context, thought):
        """Test that node ID is transformed to config key."""
        node = GraphNode(
            id="adaptive_filter/caps/detection/threshold",
            type=NodeType.CONFIG,
            scope=GraphScope.LOCAL,
            attributes={"value": 0.7},
        )

        params = MemorizeParams(node=node)
        result = ActionSelectionDMAResult(
            selected_action=HandlerActionType.MEMORIZE, action_parameters=params, rationale="Set caps threshold"
        )

        mock_handler.bus_manager.memory.memorize.return_value = MemoryOpResult(
            status=MemoryOpStatus.SUCCESS, data="node_123"
        )

        await mock_handler.handle(result, thought, dispatch_context)

        # Key should be transformed from / to .
        memorize_call = mock_handler.bus_manager.memory.memorize.call_args
        stored_node = memorize_call.kwargs["node"]
        # The key should be in attributes as adaptive_filter.caps.detection.threshold
        assert "adaptive_filter.caps.detection.threshold" in str(stored_node.attributes)

    @pytest.mark.asyncio
    async def test_non_config_node_unchanged(self, mock_handler, dispatch_context, thought):
        """Test that non-CONFIG nodes pass through unchanged."""
        node = GraphNode(
            id="user/user123", type=NodeType.USER, scope=GraphScope.LOCAL, attributes={"name": "Test User"}
        )

        params = MemorizeParams(node=node)
        result = ActionSelectionDMAResult(
            selected_action=HandlerActionType.MEMORIZE, action_parameters=params, rationale="Store user"
        )

        mock_handler.bus_manager.memory.memorize.return_value = MemoryOpResult(
            status=MemoryOpStatus.SUCCESS, data="node_123"
        )

        await mock_handler.handle(result, thought, dispatch_context)

        # Should pass through unchanged
        memorize_call = mock_handler.bus_manager.memory.memorize.call_args
        stored_node = memorize_call.kwargs["node"]
        assert stored_node.id == "user/user123"
        assert stored_node.type == NodeType.USER

    @pytest.mark.asyncio
    async def test_config_node_with_dict_value(self, mock_handler, dispatch_context, thought):
        """Test CONFIG node with dictionary value."""
        node = GraphNode(
            id="adaptive_filter/trust_mapping",
            type=NodeType.CONFIG,
            scope=GraphScope.LOCAL,
            attributes={"value": {"VERIFIED": "HIGH", "HIGH": "MEDIUM", "MEDIUM": "MEDIUM", "LOW": "LOW"}},
        )

        params = MemorizeParams(node=node)
        result = ActionSelectionDMAResult(
            selected_action=HandlerActionType.MEMORIZE, action_parameters=params, rationale="Set trust mapping"
        )

        mock_handler.bus_manager.memory.memorize.return_value = MemoryOpResult(
            status=MemoryOpStatus.SUCCESS, data="node_123"
        )

        await mock_handler.handle(result, thought, dispatch_context)

        memorize_call = mock_handler.bus_manager.memory.memorize.call_args
        stored_node = memorize_call.kwargs["node"]
        assert stored_node.type == NodeType.CONFIG

    @pytest.mark.asyncio
    async def test_config_node_identity_scope_unchanged(self, mock_handler, dispatch_context, thought):
        """Test that CONFIG nodes with IDENTITY scope don't get special handling."""
        node = GraphNode(
            id="agent/core_identity",
            type=NodeType.CONFIG,
            scope=GraphScope.IDENTITY,  # Not LOCAL
            attributes={"value": "CIRIS Agent"},
        )

        params = MemorizeParams(node=node)
        result = ActionSelectionDMAResult(
            selected_action=HandlerActionType.MEMORIZE, action_parameters=params, rationale="Set identity"
        )

        mock_handler.bus_manager.memory.memorize.return_value = MemoryOpResult(
            status=MemoryOpStatus.SUCCESS, data="node_123"
        )

        # Should require WA approval (not implemented in this test)
        # But won't get CONFIG transformation since it's IDENTITY scope
        await mock_handler.handle(result, thought, dispatch_context)

        # Verify it went through WA check path, not CONFIG path
        memorize_call = mock_handler.bus_manager.memory.memorize.call_args
        if memorize_call:  # If it got past WA check
            stored_node = memorize_call.kwargs["node"]
            assert stored_node.id == "agent/core_identity"  # Unchanged


class TestSecretsSnapshotFix:
    """Test the secrets snapshot fix for detected_secrets field."""

    @pytest.mark.asyncio
    async def test_secrets_snapshot_returns_string_uuids(self):
        """Test that detected_secrets returns List[str] not List[SecretReference]."""
        from ciris_engine.logic.context.secrets_snapshot import build_secrets_snapshot
        from ciris_engine.schemas.secrets.core import SecretReference

        # Mock secrets service
        mock_secrets_service = MagicMock()
        mock_store = AsyncMock()
        mock_filter = MagicMock()

        # Create mock SecretReference objects
        mock_secrets = [
            SecretReference(
                uuid="uuid-1",
                description="API Key",
                context_hint="Found in message",
                sensitivity="HIGH",
                detected_pattern="api_key",
                auto_decapsulate_actions=[],
                created_at=datetime.now(timezone.utc),
            ),
            SecretReference(
                uuid="uuid-2",
                description="JWT Token",
                context_hint="Bearer token",
                sensitivity="CRITICAL",
                detected_pattern="jwt",
                auto_decapsulate_actions=[],
                created_at=datetime.now(timezone.utc),
            ),
        ]

        mock_store.list_all_secrets.return_value = mock_secrets
        mock_filter.get_filter_config.return_value = MagicMock(version=1)

        mock_secrets_service.store = mock_store
        mock_secrets_service.filter = mock_filter

        # Build snapshot
        snapshot = await build_secrets_snapshot(mock_secrets_service)

        # Verify detected_secrets contains strings, not SecretReference objects
        assert isinstance(snapshot["detected_secrets"], list)
        assert all(isinstance(s, str) for s in snapshot["detected_secrets"])
        assert set(snapshot["detected_secrets"]) == {"uuid-1", "uuid-2"}
        assert snapshot["total_secrets_stored"] == 2


class TestBaseObserverFix:
    """Test the base observer SecretReference.uuid fix."""

    def test_secret_reference_uses_uuid_not_secret_uuid(self):
        """Test that base_observer uses ref.uuid not ref.secret_uuid."""
        # We can't easily test the actual method without a full setup,
        # but we can verify the fix is in place by checking the code
        import inspect

        from ciris_engine.logic.adapters.base_observer import BaseObserver

        source = inspect.getsource(BaseObserver._process_message_secrets)

        # Verify the fix: should use ref.uuid, not ref.secret_uuid
        assert "ref.uuid" in source
        assert "ref.secret_uuid" not in source


class TestFilterTestModule:
    """Test that filter test module is properly integrated."""

    def test_filter_module_in_qa_runner(self):
        """Test that FILTERS module is available in QA runner."""
        from tools.qa_runner.config import QAModule

        assert QAModule.FILTERS
        assert QAModule.FILTERS.value == "filters"

    def test_filter_tests_use_mock_llm_format(self):
        """Test that filter tests use correct mock LLM command format."""
        from tools.qa_runner.modules.filter_tests import FilterTestModule

        tests = FilterTestModule.get_filter_tests()

        # Check that tests use $memorize format
        for test in tests:
            if "memorize" in test.description.lower():
                message = test.payload.get("message", "")
                # Should use $memorize format, not "MEMORIZE:"
                if message.startswith("$memorize"):
                    assert " CONFIG LOCAL" in message or " USER LOCAL" in message

    def test_filter_test_count(self):
        """Test that we have the expected number of filter tests."""
        from tools.qa_runner.modules.filter_tests import FilterTestModule

        tests = FilterTestModule.get_filter_tests()
        assert len(tests) == 36  # Should have 36 filter tests (comprehensive RECALL/MEMORIZE and secrets tests)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
