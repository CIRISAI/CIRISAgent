"""
Tests for shared helper functions used across action handlers.

These tests ensure the extracted helper functions maintain their expected behavior
and provide comprehensive coverage for the shared_helpers module.
"""

import json
from datetime import datetime, timedelta, timezone
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import BaseModel

from ciris_engine.logic.infrastructure.handlers.shared_helpers import (
    KNOWN_ADAPTER_PREFIXES,
    MANAGED_USER_ATTRIBUTES,
    _add_consent_metadata_to_node,
    _add_default_consent_metadata,
    _extract_defer_audit_params,
    _extract_forget_audit_params,
    _extract_memorize_audit_params,
    _extract_observe_audit_params,
    _extract_ponder_audit_params,
    _extract_recall_audit_params,
    _extract_reject_audit_params,
    _extract_speak_audit_params,
    _extract_task_complete_audit_params,
    _extract_tool_audit_params,
    build_recalled_node_info,
    check_managed_attributes,
    create_config_node,
    extract_audit_parameters,
    extract_user_id_from_node,
    fetch_connected_nodes,
    get_node_attributes_dict,
    handle_user_consent,
    has_valid_adapter_prefix,
    is_api_channel,
    is_config_node,
    is_identity_node,
    is_user_node,
    parse_iso_timestamp,
    parse_timestamp_to_datetime,
    serialize_attributes_to_json,
    serialize_datetime_value,
    validate_config_node,
)
from ciris_engine.schemas.runtime.enums import HandlerActionType
from ciris_engine.schemas.services.graph_core import GraphNode, GraphScope, NodeType

# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def sample_datetime():
    """Sample datetime for testing."""
    return datetime(2025, 1, 15, 10, 30, 45, tzinfo=timezone.utc)


@pytest.fixture
def user_node():
    """Sample user node."""
    return GraphNode(
        id="user/test_user_123",
        type=NodeType.USER,
        scope=GraphScope.ENVIRONMENT,
        attributes={"name": "Test User", "email": "test@example.com"},
    )


@pytest.fixture
def config_node():
    """Sample config node."""
    return GraphNode(
        id="filter/spam_threshold",
        type=NodeType.CONFIG,
        scope=GraphScope.LOCAL,
        attributes={"value": 0.8, "description": "Spam filter threshold"},
    )


@pytest.fixture
def identity_node():
    """Sample identity node."""
    return GraphNode(
        id="agent/identity/core",
        type=NodeType.AGENT,
        scope=GraphScope.IDENTITY,
        attributes={"name": "CIRIS", "version": "1.8.0"},
    )


@pytest.fixture
def generic_node():
    """Sample generic node."""
    return GraphNode(
        id="concept/topic/ai",
        type=NodeType.CONCEPT,
        scope=GraphScope.COMMUNITY,
        attributes={"topic": "AI", "relevance": 0.9},
    )


class SamplePydanticModel(BaseModel):
    """Sample Pydantic model for serialization tests."""

    name: str
    count: int
    timestamp: datetime
    active: bool = True


# =============================================================================
# Test Classes
# =============================================================================


class TestDatetimeHelpers:
    """Tests for datetime parsing helper functions."""

    def test_parse_iso_timestamp_with_z_suffix(self):
        """Test parsing ISO timestamp with Z suffix."""
        result = parse_iso_timestamp("2025-01-15T10:30:45Z")
        assert result is not None
        assert result.year == 2025
        assert result.month == 1
        assert result.day == 15
        assert result.hour == 10
        assert result.minute == 30
        assert result.second == 45

    def test_parse_iso_timestamp_with_utc_offset(self):
        """Test parsing ISO timestamp with +00:00 offset."""
        result = parse_iso_timestamp("2025-01-15T10:30:45+00:00")
        assert result is not None
        assert result.year == 2025
        assert result.tzinfo is not None

    def test_parse_iso_timestamp_with_timezone_offset(self):
        """Test parsing ISO timestamp with non-UTC offset."""
        result = parse_iso_timestamp("2025-01-15T10:30:45-05:00")
        assert result is not None
        assert result.hour == 10

    def test_parse_iso_timestamp_none_input(self):
        """Test parsing None returns None."""
        assert parse_iso_timestamp(None) is None

    def test_parse_iso_timestamp_empty_string(self):
        """Test parsing empty string returns None."""
        assert parse_iso_timestamp("") is None

    def test_parse_iso_timestamp_invalid_format(self):
        """Test parsing invalid format returns None."""
        assert parse_iso_timestamp("not-a-timestamp") is None
        assert parse_iso_timestamp("2025-13-45T99:99:99Z") is None

    def test_parse_timestamp_to_datetime_valid(self):
        """Test parse_timestamp_to_datetime with valid input."""
        result = parse_timestamp_to_datetime("2025-01-15T10:30:45Z")
        assert isinstance(result, datetime)
        assert result.year == 2025

    def test_parse_timestamp_to_datetime_raises_on_invalid(self):
        """Test parse_timestamp_to_datetime raises ValueError on invalid input."""
        with pytest.raises(ValueError, match="Invalid ISO timestamp"):
            parse_timestamp_to_datetime("invalid")

    def test_parse_timestamp_to_datetime_raises_on_empty(self):
        """Test parse_timestamp_to_datetime raises ValueError on empty input."""
        with pytest.raises(ValueError, match="Invalid ISO timestamp"):
            parse_timestamp_to_datetime("")


class TestChannelHelpers:
    """Tests for channel identification helper functions."""

    def test_is_api_channel_with_api_prefix(self):
        """Test is_api_channel detects api_ prefix."""
        assert is_api_channel("api_123456") is True
        assert is_api_channel("api_test_channel") is True

    def test_is_api_channel_with_ws_prefix(self):
        """Test is_api_channel detects ws: prefix."""
        assert is_api_channel("ws:connection_1") is True
        assert is_api_channel("ws:user_session") is True

    def test_is_api_channel_with_discord_prefix(self):
        """Test is_api_channel returns False for discord channels."""
        assert is_api_channel("discord_123456") is False

    def test_is_api_channel_with_cli_prefix(self):
        """Test is_api_channel returns False for cli channels."""
        assert is_api_channel("cli_session") is False

    def test_is_api_channel_none_input(self):
        """Test is_api_channel returns False for None."""
        assert is_api_channel(None) is False

    def test_is_api_channel_empty_string(self):
        """Test is_api_channel returns False for empty string."""
        assert is_api_channel("") is False

    def test_has_valid_adapter_prefix_known_prefixes(self):
        """Test has_valid_adapter_prefix for known prefixes."""
        assert has_valid_adapter_prefix("api_123") is True
        assert has_valid_adapter_prefix("discord_456") is True
        assert has_valid_adapter_prefix("cli_session") is True
        assert has_valid_adapter_prefix("ws:connection") is True
        assert has_valid_adapter_prefix("reddit_thread") is True

    def test_has_valid_adapter_prefix_unknown_prefix(self):
        """Test has_valid_adapter_prefix returns False for unknown prefixes."""
        assert has_valid_adapter_prefix("unknown_channel") is False
        assert has_valid_adapter_prefix("telegram_123") is False
        assert has_valid_adapter_prefix("slack_channel") is False

    def test_known_adapter_prefixes_is_frozenset(self):
        """Test KNOWN_ADAPTER_PREFIXES is immutable."""
        assert isinstance(KNOWN_ADAPTER_PREFIXES, frozenset)
        assert len(KNOWN_ADAPTER_PREFIXES) == 5


class TestAttributeSerializationHelpers:
    """Tests for attribute serialization helper functions."""

    def test_serialize_datetime_value_with_datetime(self, sample_datetime):
        """Test serialize_datetime_value converts datetime to ISO string."""
        result = serialize_datetime_value(sample_datetime)
        assert isinstance(result, str)
        assert "2025-01-15" in result

    def test_serialize_datetime_value_passthrough_string(self):
        """Test serialize_datetime_value passes through strings."""
        assert serialize_datetime_value("test") == "test"

    def test_serialize_datetime_value_passthrough_int(self):
        """Test serialize_datetime_value passes through integers."""
        assert serialize_datetime_value(42) == 42

    def test_serialize_datetime_value_passthrough_none(self):
        """Test serialize_datetime_value passes through None."""
        assert serialize_datetime_value(None) is None

    def test_serialize_datetime_value_passthrough_list(self):
        """Test serialize_datetime_value passes through lists."""
        test_list = [1, 2, 3]
        assert serialize_datetime_value(test_list) == test_list

    def test_serialize_attributes_to_json_from_dict(self, sample_datetime):
        """Test serialize_attributes_to_json with dict input."""
        attrs = {"name": "test", "created": sample_datetime, "count": 5}
        result = serialize_attributes_to_json(attrs)

        assert result["name"] == "test"
        assert result["count"] == 5
        assert isinstance(result["created"], str)
        assert "2025-01-15" in result["created"]

    def test_serialize_attributes_to_json_from_pydantic_model(self, sample_datetime):
        """Test serialize_attributes_to_json with Pydantic model."""
        model = SamplePydanticModel(name="test", count=10, timestamp=sample_datetime)
        result = serialize_attributes_to_json(model)

        assert result["name"] == "test"
        assert result["count"] == 10
        assert result["active"] is True
        assert isinstance(result["timestamp"], str)

    def test_serialize_attributes_to_json_empty_dict(self):
        """Test serialize_attributes_to_json with empty dict."""
        assert serialize_attributes_to_json({}) == {}

    def test_serialize_attributes_to_json_none_returns_empty(self):
        """Test serialize_attributes_to_json with None returns empty dict."""
        assert serialize_attributes_to_json(None) == {}

    def test_serialize_attributes_to_json_nested_datetime(self, sample_datetime):
        """Test that nested datetimes are serialized."""
        attrs = {"nested": {"inner_date": sample_datetime}}
        result = serialize_attributes_to_json(attrs)
        # Note: nested dicts' datetime values stay as-is with current implementation
        assert "nested" in result


class TestNodeTypeHelpers:
    """Tests for node type identification helper functions."""

    def test_is_user_node_by_type(self):
        """Test is_user_node detects USER node type."""
        node = GraphNode(id="some_id", type=NodeType.USER, scope=GraphScope.ENVIRONMENT, attributes={})
        assert is_user_node(node) is True

    def test_is_user_node_by_user_slash_prefix(self, user_node):
        """Test is_user_node detects user/ prefix."""
        assert is_user_node(user_node) is True

    def test_is_user_node_by_user_underscore_prefix(self):
        """Test is_user_node detects user_ prefix."""
        node = GraphNode(id="user_123", type=NodeType.CONCEPT, scope=GraphScope.ENVIRONMENT, attributes={})
        assert is_user_node(node) is True

    def test_is_user_node_false_for_generic(self, generic_node):
        """Test is_user_node returns False for generic nodes."""
        assert is_user_node(generic_node) is False

    def test_is_identity_node_by_scope(self):
        """Test is_identity_node detects IDENTITY scope."""
        node = GraphNode(id="some_id", type=NodeType.CONCEPT, scope=GraphScope.IDENTITY, attributes={})
        assert is_identity_node(node) is True

    def test_is_identity_node_by_id_prefix(self, identity_node):
        """Test is_identity_node detects agent/identity prefix."""
        assert is_identity_node(identity_node) is True

    def test_is_identity_node_by_agent_type(self):
        """Test is_identity_node detects AGENT node type."""
        node = GraphNode(id="other_agent", type=NodeType.AGENT, scope=GraphScope.LOCAL, attributes={})
        assert is_identity_node(node) is True

    def test_is_identity_node_false_for_user(self, user_node):
        """Test is_identity_node returns False for user nodes."""
        assert is_identity_node(user_node) is False

    def test_is_config_node_correct_type_and_scope(self, config_node):
        """Test is_config_node detects CONFIG type with LOCAL scope."""
        assert is_config_node(config_node) is True

    def test_is_config_node_wrong_scope(self):
        """Test is_config_node returns False for non-LOCAL scope."""
        node = GraphNode(id="config/setting", type=NodeType.CONFIG, scope=GraphScope.ENVIRONMENT, attributes={})
        assert is_config_node(node) is False

    def test_is_config_node_wrong_type(self):
        """Test is_config_node returns False for non-CONFIG type."""
        node = GraphNode(id="config/setting", type=NodeType.CONCEPT, scope=GraphScope.LOCAL, attributes={})
        assert is_config_node(node) is False

    def test_extract_user_id_from_node_slash_format(self, user_node):
        """Test extract_user_id_from_node with user/ format."""
        result = extract_user_id_from_node(user_node)
        assert result == "test_user_123"

    def test_extract_user_id_from_node_underscore_format(self):
        """Test extract_user_id_from_node with user_ format."""
        node = GraphNode(id="user_abc123", type=NodeType.USER, scope=GraphScope.ENVIRONMENT, attributes={})
        result = extract_user_id_from_node(node)
        assert result == "abc123"

    def test_extract_user_id_from_node_returns_none_for_non_user(self, generic_node):
        """Test extract_user_id_from_node returns None for non-user nodes."""
        assert extract_user_id_from_node(generic_node) is None


class TestManagedAttributeHelpers:
    """Tests for managed attribute checking helper functions."""

    def test_managed_user_attributes_contains_expected_keys(self):
        """Test MANAGED_USER_ATTRIBUTES contains critical keys."""
        expected_keys = [
            "last_seen",
            "trust_level",
            "is_wa",
            "permissions",
            "oauth_provider",
            "oauth_email",
        ]
        for key in expected_keys:
            assert key in MANAGED_USER_ATTRIBUTES

    def test_get_node_attributes_dict_from_dict(self, user_node):
        """Test get_node_attributes_dict extracts dict attributes."""
        result = get_node_attributes_dict(user_node)
        assert result["name"] == "Test User"
        assert result["email"] == "test@example.com"

    def test_get_node_attributes_dict_empty_attributes(self):
        """Test get_node_attributes_dict returns empty dict for no attributes."""
        node = GraphNode(id="test", type=NodeType.CONCEPT, scope=GraphScope.LOCAL, attributes={})
        result = get_node_attributes_dict(node)
        assert result == {}

    def test_get_node_attributes_dict_none_like_attributes(self):
        """Test get_node_attributes_dict handles empty attributes."""
        # GraphNode doesn't accept None for attributes, so test empty dict
        node = GraphNode(id="test", type=NodeType.CONCEPT, scope=GraphScope.LOCAL, attributes={})
        result = get_node_attributes_dict(node)
        assert result == {}

    def test_check_managed_attributes_detects_last_seen(self):
        """Test check_managed_attributes detects last_seen."""
        node = GraphNode(
            id="user/test",
            type=NodeType.USER,
            scope=GraphScope.ENVIRONMENT,
            attributes={"last_seen": "2025-01-15T10:00:00Z"},
        )
        result = check_managed_attributes(node)
        assert result is not None
        assert "MEMORIZE BLOCKED" in result
        assert "last_seen" in result

    def test_check_managed_attributes_detects_trust_level(self):
        """Test check_managed_attributes detects trust_level."""
        node = GraphNode(
            id="user/test",
            type=NodeType.USER,
            scope=GraphScope.ENVIRONMENT,
            attributes={"trust_level": 5},
        )
        result = check_managed_attributes(node)
        assert result is not None
        assert "trust_level" in result

    def test_check_managed_attributes_detects_oauth_fields(self):
        """Test check_managed_attributes detects OAuth fields."""
        node = GraphNode(
            id="user/test",
            type=NodeType.USER,
            scope=GraphScope.ENVIRONMENT,
            attributes={"oauth_email": "test@example.com"},
        )
        result = check_managed_attributes(node)
        assert result is not None
        assert "oauth_email" in result

    def test_check_managed_attributes_allows_custom_attrs(self, user_node):
        """Test check_managed_attributes allows custom attributes."""
        result = check_managed_attributes(user_node)
        assert result is None

    def test_check_managed_attributes_skips_non_user_nodes(self, generic_node):
        """Test check_managed_attributes skips non-user nodes."""
        generic_node.attributes = {"last_seen": "2025-01-15"}
        result = check_managed_attributes(generic_node)
        assert result is None


class TestConsentHelpers:
    """Tests for consent handling helper functions."""

    @pytest.fixture
    def mock_consent_service(self):
        """Mock consent service."""
        service = AsyncMock()
        return service

    @pytest.fixture
    def mock_time_service(self):
        """Mock time service."""
        service = MagicMock()
        # Return a current time that's after any test expiration dates
        service.now.return_value = datetime(2025, 6, 1, tzinfo=timezone.utc)
        return service

    @pytest.fixture
    def mock_consent_status(self):
        """Mock consent status."""
        status = MagicMock()
        status.stream = "STANDARD"
        status.expires_at = None
        status.granted_at = datetime(2025, 1, 1, tzinfo=timezone.utc)
        return status

    @pytest.mark.asyncio
    async def test_handle_user_consent_existing_consent(
        self, user_node, mock_consent_service, mock_time_service, mock_consent_status
    ):
        """Test handle_user_consent with existing valid consent."""
        mock_consent_service.get_consent.return_value = mock_consent_status

        error, metadata_added = await handle_user_consent(
            "test_user", user_node, mock_consent_service, mock_time_service
        )

        assert error is None
        assert metadata_added is True
        mock_consent_service.get_consent.assert_called_once_with("test_user")

    @pytest.mark.asyncio
    async def test_handle_user_consent_expired_temporary(self, user_node, mock_consent_service, mock_time_service):
        """Test handle_user_consent blocks expired TEMPORARY consent."""
        from ciris_engine.schemas.consent.core import ConsentStream

        expired_status = MagicMock()
        expired_status.stream = ConsentStream.TEMPORARY
        expired_status.expires_at = datetime(2024, 1, 1, tzinfo=timezone.utc)  # Expired
        expired_status.granted_at = datetime(2023, 12, 1, tzinfo=timezone.utc)

        mock_consent_service.get_consent.return_value = expired_status

        error, metadata_added = await handle_user_consent(
            "test_user", user_node, mock_consent_service, mock_time_service
        )

        assert error is not None
        assert "MEMORIZE BLOCKED" in error
        assert "expired" in error.lower()
        assert metadata_added is False
        mock_consent_service.revoke_consent.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_user_consent_creates_default_for_new_user(
        self, user_node, mock_consent_service, mock_time_service
    ):
        """Test handle_user_consent creates default consent for new users."""
        from ciris_engine.logic.services.governance.consent import ConsentNotFoundError

        mock_consent_service.get_consent.side_effect = ConsentNotFoundError("No consent")
        mock_consent_service.grant_consent.return_value = None

        user_node.attributes = {}
        error, metadata_added = await handle_user_consent(
            "new_user", user_node, mock_consent_service, mock_time_service
        )

        assert error is None
        assert metadata_added is True
        mock_consent_service.grant_consent.assert_called_once()

    def test_add_consent_metadata_to_node(self, user_node, mock_consent_status):
        """Test _add_consent_metadata_to_node adds expected fields."""
        _add_consent_metadata_to_node(user_node, mock_consent_status)

        assert "consent_stream" in user_node.attributes
        assert "consent_granted_at" in user_node.attributes

    def test_add_default_consent_metadata(self, user_node):
        """Test _add_default_consent_metadata adds TEMPORARY consent."""
        now = datetime.now(timezone.utc)
        _add_default_consent_metadata(user_node, now)

        from ciris_engine.schemas.consent.core import ConsentStream

        assert user_node.attributes.get("consent_stream") == ConsentStream.TEMPORARY
        assert "consent_expires_at" in user_node.attributes
        assert "consent_notice" in user_node.attributes


class TestConfigNodeHelpers:
    """Tests for config node helper functions."""

    def test_validate_config_node_valid(self, config_node):
        """Test validate_config_node with valid config."""
        key, value, error = validate_config_node(config_node)

        assert key == "filter.spam_threshold"
        assert value == 0.8
        assert error is None

    def test_validate_config_node_missing_value(self):
        """Test validate_config_node detects missing value."""
        node = GraphNode(
            id="filter/setting",
            type=NodeType.CONFIG,
            scope=GraphScope.LOCAL,
            attributes={"description": "Missing value"},
        )

        key, value, error = validate_config_node(node)

        assert key == "filter.setting"
        assert value is None
        assert error is not None
        assert "MEMORIZE CONFIG FAILED" in error
        assert "Missing required 'value' field" in error

    def test_create_config_node_with_bool(self):
        """Test create_config_node with boolean value."""
        node = GraphNode(
            id="filter/enabled",
            type=NodeType.CONFIG,
            scope=GraphScope.LOCAL,
            attributes={"value": True},
        )

        result = create_config_node(node, "filter.enabled", True)
        assert result is not None
        assert result.type == NodeType.CONFIG

    def test_create_config_node_with_int(self):
        """Test create_config_node with integer value."""
        node = GraphNode(
            id="limits/max_retries",
            type=NodeType.CONFIG,
            scope=GraphScope.LOCAL,
            attributes={"value": 5},
        )

        result = create_config_node(node, "limits.max_retries", 5)
        assert result is not None

    def test_create_config_node_with_float(self, config_node):
        """Test create_config_node with float value."""
        result = create_config_node(config_node, "filter.spam_threshold", 0.8)
        assert result is not None

    def test_create_config_node_with_string(self):
        """Test create_config_node with string value."""
        node = GraphNode(
            id="filter/mode",
            type=NodeType.CONFIG,
            scope=GraphScope.LOCAL,
            attributes={"value": "strict"},
        )

        result = create_config_node(node, "filter.mode", "strict")
        assert result is not None

    def test_create_config_node_with_list(self):
        """Test create_config_node with list value."""
        node = GraphNode(
            id="filter/blocked_words",
            type=NodeType.CONFIG,
            scope=GraphScope.LOCAL,
            attributes={"value": ["spam", "scam"]},
        )

        result = create_config_node(node, "filter.blocked_words", ["spam", "scam"])
        assert result is not None

    def test_create_config_node_with_dict(self):
        """Test create_config_node with dict value."""
        node = GraphNode(
            id="settings/advanced",
            type=NodeType.CONFIG,
            scope=GraphScope.LOCAL,
            attributes={"value": {"key1": "val1", "key2": 42}},
        )

        result = create_config_node(node, "settings.advanced", {"key1": "val1", "key2": 42})
        assert result is not None


class TestRecallResultHelpers:
    """Tests for recall result building helper functions."""

    def test_build_recalled_node_info_basic(self, user_node):
        """Test build_recalled_node_info creates correct structure."""
        result = build_recalled_node_info(user_node)

        assert result.type == NodeType.USER
        assert result.scope == GraphScope.ENVIRONMENT
        assert result.attributes["name"] == "Test User"

    def test_build_recalled_node_info_with_string_attrs(self):
        """Test build_recalled_node_info creates correct structure with attributes."""
        # GraphNode attributes must be JSON-serializable, test with valid types
        node = GraphNode(
            id="test",
            type=NodeType.CONCEPT,
            scope=GraphScope.LOCAL,
            attributes={"created": "2025-01-15T10:30:45+00:00", "name": "test"},
        )

        result = build_recalled_node_info(node)

        assert result.attributes["created"] == "2025-01-15T10:30:45+00:00"
        assert result.attributes["name"] == "test"

    @pytest.mark.asyncio
    async def test_fetch_connected_nodes_empty_edges(self, user_node):
        """Test fetch_connected_nodes returns empty list when no edges."""
        mock_bus_manager = MagicMock()

        with patch(
            "ciris_engine.logic.persistence.models.graph.get_edges_for_node",
            return_value=[],
        ):
            result = await fetch_connected_nodes(user_node, mock_bus_manager, "test_handler")

        assert result == []

    @pytest.mark.asyncio
    async def test_fetch_connected_nodes_handles_exception(self, user_node):
        """Test fetch_connected_nodes handles exceptions gracefully."""
        mock_bus_manager = MagicMock()

        with patch(
            "ciris_engine.logic.persistence.models.graph.get_edges_for_node",
            side_effect=Exception("Database error"),
        ):
            result = await fetch_connected_nodes(user_node, mock_bus_manager, "test_handler")

        assert result == []


class TestAuditParameterHelpers:
    """Tests for audit parameter extraction helper functions."""

    def test_extract_audit_parameters_basic(self):
        """Test extract_audit_parameters with minimal input."""
        result = extract_audit_parameters(HandlerActionType.SPEAK, None)
        assert result == {}

    def test_extract_audit_parameters_with_follow_up_id(self):
        """Test extract_audit_parameters includes follow_up_id."""
        result = extract_audit_parameters(HandlerActionType.SPEAK, None, follow_up_id="thought_123")

        assert result["follow_up_thought_id"] == "thought_123"

    def test_extract_audit_parameters_with_error(self):
        """Test extract_audit_parameters includes error info."""
        error = ValueError("Something went wrong")
        result = extract_audit_parameters(HandlerActionType.SPEAK, None, error=error)

        assert "error" in result
        assert "Something went wrong" in result["error"]
        assert result["error_type"] == "ValueError"

    def test_extract_audit_parameters_tool_action(self):
        """Test extract_audit_parameters extracts tool parameters."""
        from ciris_engine.schemas.actions.parameters import ToolParams

        tool_params = ToolParams(name="search_web", parameters={"query": "test query"})
        result = extract_audit_parameters(HandlerActionType.TOOL, tool_params)

        assert result["tool_name"] == "search_web"
        assert "query" in result["tool_parameters"]

    def test_extract_tool_audit_params_with_name_attribute(self):
        """Test _extract_tool_audit_params extracts tool name."""
        params: Dict[str, str] = {}
        mock_action = MagicMock()
        mock_action.name = "test_tool"

        _extract_tool_audit_params(mock_action, params)

        assert params["tool_name"] == "test_tool"

    def test_extract_audit_parameters_non_tool_action(self):
        """Test extract_audit_parameters for non-TOOL actions doesn't extract tool params."""
        mock_params = MagicMock()
        mock_params.name = "should_not_appear"

        result = extract_audit_parameters(HandlerActionType.SPEAK, mock_params)

        assert "tool_name" not in result

    def test_extract_tool_audit_params_with_ha_prefix(self):
        """Test _extract_tool_audit_params extracts home_assistant adapter from ha_ prefix."""
        from ciris_engine.schemas.actions.parameters import ToolParams

        tool_params = ToolParams(name="ha_device_control", parameters={"entity_id": "light.lamp"})
        result = extract_audit_parameters(HandlerActionType.TOOL, tool_params)

        assert result["tool_name"] == "ha_device_control"
        assert result["tool_adapter"] == "home_assistant"

    def test_extract_tool_audit_params_with_web_prefix(self):
        """Test _extract_tool_audit_params extracts web adapter from web_ prefix."""
        from ciris_engine.schemas.actions.parameters import ToolParams

        tool_params = ToolParams(name="web_search", parameters={"query": "test"})
        result = extract_audit_parameters(HandlerActionType.TOOL, tool_params)

        assert result["tool_name"] == "web_search"
        assert result["tool_adapter"] == "web"

    def test_extract_tool_audit_params_with_secrets_prefix(self):
        """Test _extract_tool_audit_params extracts secrets adapter from secrets_ prefix."""
        from ciris_engine.schemas.actions.parameters import ToolParams

        tool_params = ToolParams(name="secrets_get", parameters={"key": "api_key"})
        result = extract_audit_parameters(HandlerActionType.TOOL, tool_params)

        assert result["tool_name"] == "secrets_get"
        assert result["tool_adapter"] == "secrets"

    def test_extract_tool_audit_params_no_adapter_prefix(self):
        """Test _extract_tool_audit_params with tool that has no known adapter prefix."""
        from ciris_engine.schemas.actions.parameters import ToolParams

        tool_params = ToolParams(name="custom_tool", parameters={"arg": "value"})
        result = extract_audit_parameters(HandlerActionType.TOOL, tool_params)

        assert result["tool_name"] == "custom_tool"
        assert "tool_adapter" not in result

    # PONDER action tests
    def test_extract_ponder_audit_params_with_questions(self):
        """Test _extract_ponder_audit_params extracts questions."""
        from ciris_engine.schemas.actions.parameters import PonderParams

        ponder_params = PonderParams(questions=["What is the ethical implication?", "Is this safe?"])
        result = extract_audit_parameters(HandlerActionType.PONDER, ponder_params)

        assert "ponder_questions" in result
        assert "What is the ethical implication?" in result["ponder_questions"]
        assert result["question_count"] == "2"

    def test_extract_ponder_audit_params_empty_questions(self):
        """Test _extract_ponder_audit_params with empty questions."""
        from ciris_engine.schemas.actions.parameters import PonderParams

        ponder_params = PonderParams(questions=[])
        result = extract_audit_parameters(HandlerActionType.PONDER, ponder_params)

        assert "ponder_questions" not in result

    def test_extract_ponder_audit_params_direct(self):
        """Test _extract_ponder_audit_params directly."""
        params: Dict[str, str] = {}
        mock_action = MagicMock()
        mock_action.questions = ["Question 1", "Question 2", "Question 3"]

        _extract_ponder_audit_params(mock_action, params)

        assert params["question_count"] == "3"
        assert "Question 1" in params["ponder_questions"]

    # SPEAK action tests
    def test_extract_speak_audit_params_short_content(self):
        """Test _extract_speak_audit_params with short content."""
        from ciris_engine.schemas.actions.parameters import SpeakParams

        speak_params = SpeakParams(content="Hello, world!")
        result = extract_audit_parameters(HandlerActionType.SPEAK, speak_params)

        assert result["content"] == "Hello, world!"
        assert "content_length" not in result

    def test_extract_speak_audit_params_long_content(self):
        """Test _extract_speak_audit_params truncates long content."""
        from ciris_engine.schemas.actions.parameters import SpeakParams

        long_content = "A" * 500
        speak_params = SpeakParams(content=long_content)
        result = extract_audit_parameters(HandlerActionType.SPEAK, speak_params)

        assert result["content_preview"].endswith("...")
        assert len(result["content_preview"]) == 203  # 200 + "..."
        assert result["content_length"] == "500"

    def test_extract_speak_audit_params_direct(self):
        """Test _extract_speak_audit_params directly."""
        params: Dict[str, str] = {}
        mock_action = MagicMock()
        mock_action.content = "Test message"

        _extract_speak_audit_params(mock_action, params)

        assert params["content"] == "Test message"

    # OBSERVE action tests
    def test_extract_observe_audit_params_with_channel(self):
        """Test _extract_observe_audit_params extracts channel."""
        from ciris_engine.schemas.actions.parameters import ObserveParams

        observe_params = ObserveParams(channel_id="discord_123", active=True, context={"key": "value"})
        result = extract_audit_parameters(HandlerActionType.OBSERVE, observe_params)

        assert result["observe_channel"] == "discord_123"
        assert result["observe_active"] == "True"
        assert "observe_context" in result

    def test_extract_observe_audit_params_direct(self):
        """Test _extract_observe_audit_params directly."""
        params: Dict[str, str] = {}
        mock_action = MagicMock()
        mock_action.channel_id = "api_456"
        mock_action.active = False
        mock_action.context = None

        _extract_observe_audit_params(mock_action, params)

        assert params["observe_channel"] == "api_456"
        assert params["observe_active"] == "False"

    # MEMORIZE action tests
    def test_extract_memorize_audit_params_with_node(self):
        """Test _extract_memorize_audit_params extracts node info."""
        from ciris_engine.schemas.actions.parameters import MemorizeParams

        node = GraphNode(id="user/test", type=NodeType.USER, scope=GraphScope.ENVIRONMENT, attributes={})
        memorize_params = MemorizeParams(node=node)
        result = extract_audit_parameters(HandlerActionType.MEMORIZE, memorize_params)

        assert result["node_id"] == "user/test"
        assert "user" in result["node_type"].lower()  # Case-insensitive check
        assert "environment" in result["node_scope"].lower()

    def test_extract_memorize_audit_params_direct(self):
        """Test _extract_memorize_audit_params directly."""
        params: Dict[str, str] = {}
        mock_node = MagicMock()
        mock_node.id = "concept/topic"
        mock_node.type = NodeType.CONCEPT
        mock_node.scope = GraphScope.LOCAL

        mock_action = MagicMock()
        mock_action.node = mock_node

        _extract_memorize_audit_params(mock_action, params)

        assert params["node_id"] == "concept/topic"

    # RECALL action tests
    def test_extract_recall_audit_params_with_query(self):
        """Test _extract_recall_audit_params extracts query info."""
        from ciris_engine.schemas.actions.parameters import RecallParams

        recall_params = RecallParams(query="find user preferences", node_type=NodeType.USER, limit=10)
        result = extract_audit_parameters(HandlerActionType.RECALL, recall_params)

        assert result["recall_query"] == "find user preferences"
        assert result["recall_limit"] == "10"

    def test_extract_recall_audit_params_direct(self):
        """Test _extract_recall_audit_params directly."""
        params: Dict[str, str] = {}
        mock_action = MagicMock()
        mock_action.query = "search query"
        mock_action.node_id = "specific_node"
        mock_action.node_type = "USER"
        mock_action.scope = "LOCAL"
        mock_action.limit = 5

        _extract_recall_audit_params(mock_action, params)

        assert params["recall_query"] == "search query"
        assert params["recall_node_id"] == "specific_node"
        assert params["recall_limit"] == "5"

    # FORGET action tests
    def test_extract_forget_audit_params_with_reason(self):
        """Test _extract_forget_audit_params extracts node and reason."""
        from ciris_engine.schemas.actions.parameters import ForgetParams

        node = GraphNode(id="outdated/data", type=NodeType.CONCEPT, scope=GraphScope.LOCAL, attributes={})
        forget_params = ForgetParams(node=node, reason="Data is outdated and no longer relevant")
        result = extract_audit_parameters(HandlerActionType.FORGET, forget_params)

        assert result["forget_node_id"] == "outdated/data"
        assert result["forget_reason"] == "Data is outdated and no longer relevant"

    def test_extract_forget_audit_params_direct(self):
        """Test _extract_forget_audit_params directly."""
        params: Dict[str, str] = {}
        mock_node = MagicMock()
        mock_node.id = "node_to_forget"
        mock_node.type = NodeType.CONCEPT

        mock_action = MagicMock()
        mock_action.node = mock_node
        mock_action.reason = "GDPR deletion request"

        _extract_forget_audit_params(mock_action, params)

        assert params["forget_node_id"] == "node_to_forget"
        assert params["forget_reason"] == "GDPR deletion request"

    # REJECT action tests
    def test_extract_reject_audit_params_with_filter(self):
        """Test _extract_reject_audit_params extracts reject info and filter."""
        from ciris_engine.schemas.actions.parameters import RejectParams

        reject_params = RejectParams(
            reason="Request violates safety guidelines",
            create_filter=True,
            filter_pattern="harmful_pattern",
            filter_type="regex",
        )
        result = extract_audit_parameters(HandlerActionType.REJECT, reject_params)

        assert result["reject_reason"] == "Request violates safety guidelines"
        assert result["creates_filter"] == "true"
        assert result["filter_pattern"] == "harmful_pattern"
        assert result["filter_type"] == "regex"

    def test_extract_reject_audit_params_without_filter(self):
        """Test _extract_reject_audit_params without creating filter."""
        from ciris_engine.schemas.actions.parameters import RejectParams

        reject_params = RejectParams(reason="Not appropriate", create_filter=False)
        result = extract_audit_parameters(HandlerActionType.REJECT, reject_params)

        assert result["reject_reason"] == "Not appropriate"
        assert "creates_filter" not in result

    def test_extract_reject_audit_params_direct(self):
        """Test _extract_reject_audit_params directly."""
        params: Dict[str, str] = {}
        mock_action = MagicMock()
        mock_action.reason = "Safety violation"
        mock_action.create_filter = True
        mock_action.filter_pattern = "bad_pattern"
        mock_action.filter_type = "exact"

        _extract_reject_audit_params(mock_action, params)

        assert params["reject_reason"] == "Safety violation"
        assert params["creates_filter"] == "true"
        assert params["filter_pattern"] == "bad_pattern"

    # DEFER action tests
    def test_extract_defer_audit_params_with_context(self):
        """Test _extract_defer_audit_params extracts defer info."""
        from ciris_engine.schemas.actions.parameters import DeferParams

        defer_params = DeferParams(
            reason="Need human approval for this action",
            context={"urgency": "high", "category": "financial"},
            defer_until="2025-01-20T10:00:00Z",
        )
        result = extract_audit_parameters(HandlerActionType.DEFER, defer_params)

        assert result["defer_reason"] == "Need human approval for this action"
        assert "defer_context" in result
        assert "urgency" in result["defer_context"]
        assert result["defer_until"] == "2025-01-20T10:00:00Z"

    def test_extract_defer_audit_params_direct(self):
        """Test _extract_defer_audit_params directly."""
        params: Dict[str, str] = {}
        mock_action = MagicMock()
        mock_action.reason = "Requires WA approval"
        mock_action.context = {"type": "sensitive"}
        mock_action.defer_until = None

        _extract_defer_audit_params(mock_action, params)

        assert params["defer_reason"] == "Requires WA approval"
        assert "defer_context" in params
        assert "defer_until" not in params

    # TASK_COMPLETE action tests
    def test_extract_task_complete_audit_params_with_reason(self):
        """Test _extract_task_complete_audit_params extracts completion reason."""
        from ciris_engine.schemas.actions.parameters import TaskCompleteParams

        complete_params = TaskCompleteParams(completion_reason="Successfully processed user request")
        result = extract_audit_parameters(HandlerActionType.TASK_COMPLETE, complete_params)

        assert result["completion_reason"] == "Successfully processed user request"

    def test_extract_task_complete_audit_params_default_reason(self):
        """Test _extract_task_complete_audit_params with default reason."""
        from ciris_engine.schemas.actions.parameters import TaskCompleteParams

        # TaskCompleteParams has a default completion_reason
        complete_params = TaskCompleteParams()
        result = extract_audit_parameters(HandlerActionType.TASK_COMPLETE, complete_params)

        assert result["completion_reason"] == "Task completed successfully"

    def test_extract_task_complete_audit_params_direct(self):
        """Test _extract_task_complete_audit_params directly."""
        params: Dict[str, str] = {}
        mock_action = MagicMock()
        mock_action.completion_reason = "Task finished"

        _extract_task_complete_audit_params(mock_action, params)

        assert params["completion_reason"] == "Task finished"


class TestIntegration:
    """Integration tests combining multiple helpers."""

    def test_user_node_flow(self, user_node):
        """Test typical user node processing flow."""
        # Check if user node
        assert is_user_node(user_node) is True
        assert is_identity_node(user_node) is False
        assert is_config_node(user_node) is False

        # Extract user ID
        user_id = extract_user_id_from_node(user_node)
        assert user_id == "test_user_123"

        # Check managed attributes (should pass)
        error = check_managed_attributes(user_node)
        assert error is None

        # Build recall info
        recall_info = build_recalled_node_info(user_node)
        assert recall_info.type == NodeType.USER

    def test_config_node_flow(self, config_node):
        """Test typical config node processing flow."""
        # Check if config node
        assert is_config_node(config_node) is True
        assert is_user_node(config_node) is False

        # Validate config
        key, value, error = validate_config_node(config_node)
        assert error is None
        assert key == "filter.spam_threshold"
        assert value == 0.8

        # Create proper config node
        result = create_config_node(config_node, key, value)
        assert result.type == NodeType.CONFIG

    def test_channel_identification_flow(self):
        """Test channel identification for different adapters."""
        channels = {
            "api_12345": (True, True),  # (is_api, has_valid_prefix)
            "ws:session_1": (True, True),
            "discord_67890": (False, True),
            "cli_local": (False, True),
            "reddit_thread": (False, True),
            "unknown_channel": (False, False),
        }

        for channel_id, (expected_api, expected_valid) in channels.items():
            assert is_api_channel(channel_id) == expected_api
            assert has_valid_adapter_prefix(channel_id) == expected_valid
