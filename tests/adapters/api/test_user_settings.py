"""Tests for user settings API endpoints (GET/PUT /users/me/settings).

Tests cover:
- GET /users/me/settings - Retrieve user's personal settings
- PUT /users/me/settings - Update user's personal settings
- Memory service integration
- Protected attribute bypass for user-owned settings
"""

from datetime import datetime, timezone

import pytest
from unittest.mock import AsyncMock, Mock

from ciris_engine.logic.adapters.api.routes.users import (
    UpdateUserSettingsRequest,
    UserSettingsResponse,
    get_my_settings,
    update_my_settings,
)
from ciris_engine.schemas.api.auth import AuthContext, UserRole, Permission
from ciris_engine.schemas.services.graph_core import GraphNode, GraphScope, NodeType


@pytest.fixture
def mock_auth_context():
    """Create mock AuthContext for testing."""
    auth = Mock(spec=AuthContext)
    auth.user_id = "test-user-123"
    auth.role = UserRole.OBSERVER
    auth.permissions = {Permission.VIEW_MESSAGES}
    auth.api_key_id = "test-key-123"
    auth.authenticated_at = datetime(2025, 9, 8, 12, 0, 0, tzinfo=timezone.utc)
    auth.has_permission = Mock(return_value=False)
    return auth


@pytest.fixture
def mock_memory_service():
    """Create mock memory service for testing."""
    service = AsyncMock()
    return service


@pytest.fixture
def mock_request_with_memory(mock_memory_service):
    """Create mock request with memory service in app state."""
    request = Mock()
    request.app = Mock()
    request.app.state = Mock()
    request.app.state.memory_service = mock_memory_service
    return request


@pytest.fixture
def sample_user_node():
    """Create sample user node with settings."""
    return GraphNode(
        id="user/test-user-123",
        type=NodeType.USER,
        scope=GraphScope.LOCAL,
        attributes={
            "username": "testuser",
            "user_preferred_name": "Test User",
            "location": "San Francisco",
            "interaction_preferences": "Be concise and technical",
            "marketing_opt_in": True,
            "marketing_opt_in_source": "oauth_login",
            "first_seen": "2025-01-01T00:00:00Z",
        },
    )


# =============================================================================
# GET /users/me/settings TESTS
# =============================================================================


@pytest.mark.asyncio
async def test_get_my_settings_existing_user(
    mock_request_with_memory,
    mock_auth_context,
    mock_memory_service,
    sample_user_node,
):
    """Test retrieving settings for existing user with all settings populated."""
    # Setup: memory service returns user node with settings
    mock_memory_service.recall.return_value = [sample_user_node]

    # Execute
    result = await get_my_settings(
        request=mock_request_with_memory,
        auth=mock_auth_context,
    )

    # Verify
    assert isinstance(result, UserSettingsResponse)
    assert result.user_preferred_name == "Test User"
    assert result.location == "San Francisco"
    assert result.interaction_preferences == "Be concise and technical"
    assert result.marketing_opt_in is True
    assert result.marketing_opt_in_source == "oauth_login"

    # Verify memory service was called correctly
    mock_memory_service.recall.assert_called_once()
    query = mock_memory_service.recall.call_args[0][0]
    assert query.node_id == f"user/{mock_auth_context.user_id}"
    assert query.scope == GraphScope.LOCAL
    assert query.type == NodeType.USER


@pytest.mark.asyncio
async def test_get_my_settings_new_user(
    mock_request_with_memory,
    mock_auth_context,
    mock_memory_service,
):
    """Test retrieving settings for new user with no node yet."""
    # Setup: memory service returns empty list (no user node exists)
    mock_memory_service.recall.return_value = []

    # Execute
    result = await get_my_settings(
        request=mock_request_with_memory,
        auth=mock_auth_context,
    )

    # Verify: should return defaults
    assert isinstance(result, UserSettingsResponse)
    assert result.user_preferred_name is None
    assert result.location is None
    assert result.interaction_preferences is None
    assert result.marketing_opt_in is False
    assert result.marketing_opt_in_source is None


@pytest.mark.asyncio
async def test_get_my_settings_partial_settings(
    mock_request_with_memory,
    mock_auth_context,
    mock_memory_service,
):
    """Test retrieving settings when only some settings are populated."""
    # Setup: user node with only some settings
    partial_node = GraphNode(
        id="user/test-user-123",
        type=NodeType.USER,
        scope=GraphScope.LOCAL,
        attributes={
            "username": "testuser",
            "location": "London",
            # No user_preferred_name, interaction_preferences, or marketing settings
        },
    )
    mock_memory_service.recall.return_value = [partial_node]

    # Execute
    result = await get_my_settings(
        request=mock_request_with_memory,
        auth=mock_auth_context,
    )

    # Verify: populated fields returned, others None/False
    assert result.location == "London"
    assert result.user_preferred_name is None
    assert result.interaction_preferences is None
    assert result.marketing_opt_in is False
    assert result.marketing_opt_in_source is None


@pytest.mark.asyncio
async def test_get_my_settings_memory_service_unavailable(mock_auth_context):
    """Test GET settings when memory service is not available."""
    from fastapi import HTTPException

    # Setup: request with no memory service
    request = Mock()
    request.app = Mock()
    request.app.state = Mock()
    request.app.state.memory_service = None

    # Execute & Verify: should raise 503
    with pytest.raises(HTTPException) as exc_info:
        await get_my_settings(request=request, auth=mock_auth_context)

    assert exc_info.value.status_code == 503
    assert "Memory service not available" in str(exc_info.value.detail)


# =============================================================================
# PUT /users/me/settings TESTS
# =============================================================================


@pytest.mark.asyncio
async def test_update_my_settings_existing_user(
    mock_request_with_memory,
    mock_auth_context,
    mock_memory_service,
    sample_user_node,
):
    """Test updating settings for existing user."""
    # Setup: memory service returns existing user node
    mock_memory_service.recall.return_value = [sample_user_node]
    mock_memory_service.memorize = AsyncMock()

    # Prepare update request
    update_request = UpdateUserSettingsRequest(
        user_preferred_name="Updated Name",
        location="Tokyo",
        interaction_preferences="Be friendly and detailed",
        marketing_opt_in=False,
    )

    # Execute
    result = await update_my_settings(
        http_request=mock_request_with_memory,
        request=update_request,
        auth=mock_auth_context,
    )

    # Verify response
    assert isinstance(result, UserSettingsResponse)
    assert result.user_preferred_name == "Updated Name"
    assert result.location == "Tokyo"
    assert result.interaction_preferences == "Be friendly and detailed"
    assert result.marketing_opt_in is False
    assert result.marketing_opt_in_source == "settings_api"  # Auto-updated

    # Verify memory service was called to save
    mock_memory_service.memorize.assert_called_once()
    saved_node = mock_memory_service.memorize.call_args[0][0]
    assert saved_node.id == f"user/{mock_auth_context.user_id}"
    assert saved_node.attributes["user_preferred_name"] == "Updated Name"
    assert saved_node.attributes["location"] == "Tokyo"
    assert saved_node.attributes["interaction_preferences"] == "Be friendly and detailed"
    assert saved_node.attributes["marketing_opt_in"] is False
    assert saved_node.attributes["marketing_opt_in_source"] == "settings_api"
    # Original attributes should be preserved
    assert saved_node.attributes["username"] == "testuser"
    assert saved_node.attributes["first_seen"] == "2025-01-01T00:00:00Z"


@pytest.mark.asyncio
async def test_update_my_settings_new_user(
    mock_request_with_memory,
    mock_auth_context,
    mock_memory_service,
):
    """Test updating settings for new user (creates node)."""
    # Setup: memory service returns empty (no existing node)
    mock_memory_service.recall.return_value = []
    mock_memory_service.memorize = AsyncMock()

    # Prepare update request
    update_request = UpdateUserSettingsRequest(
        user_preferred_name="New User",
        location="Berlin",
    )

    # Execute
    result = await update_my_settings(
        http_request=mock_request_with_memory,
        request=update_request,
        auth=mock_auth_context,
    )

    # Verify response
    assert result.user_preferred_name == "New User"
    assert result.location == "Berlin"
    assert result.interaction_preferences is None
    assert result.marketing_opt_in is False

    # Verify memory service created new node
    mock_memory_service.memorize.assert_called_once()
    saved_node = mock_memory_service.memorize.call_args[0][0]
    assert saved_node.id == f"user/{mock_auth_context.user_id}"
    assert saved_node.type == NodeType.USER
    assert saved_node.scope == GraphScope.LOCAL
    assert saved_node.attributes["user_preferred_name"] == "New User"
    assert saved_node.attributes["location"] == "Berlin"


@pytest.mark.asyncio
async def test_update_my_settings_partial_update(
    mock_request_with_memory,
    mock_auth_context,
    mock_memory_service,
    sample_user_node,
):
    """Test partial update (only updating some fields)."""
    # Setup
    mock_memory_service.recall.return_value = [sample_user_node]
    mock_memory_service.memorize = AsyncMock()

    # Prepare partial update (only location)
    update_request = UpdateUserSettingsRequest(
        location="Paris",
        # Other fields are None (not being updated)
    )

    # Execute
    result = await update_my_settings(
        http_request=mock_request_with_memory,
        request=update_request,
        auth=mock_auth_context,
    )

    # Verify: only location changed, others preserved
    assert result.location == "Paris"
    assert result.user_preferred_name == "Test User"  # Preserved
    assert result.interaction_preferences == "Be concise and technical"  # Preserved
    assert result.marketing_opt_in is True  # Preserved

    # Verify saved node preserves other attributes
    saved_node = mock_memory_service.memorize.call_args[0][0]
    assert saved_node.attributes["location"] == "Paris"
    assert saved_node.attributes["user_preferred_name"] == "Test User"
    assert saved_node.attributes["username"] == "testuser"


@pytest.mark.asyncio
async def test_update_my_settings_marketing_opt_in_source_tracking(
    mock_request_with_memory,
    mock_auth_context,
    mock_memory_service,
    sample_user_node,
):
    """Test that marketing_opt_in_source is automatically updated to 'settings_api'."""
    # Setup: existing user with oauth_login source
    assert sample_user_node.attributes["marketing_opt_in_source"] == "oauth_login"
    mock_memory_service.recall.return_value = [sample_user_node]
    mock_memory_service.memorize = AsyncMock()

    # Update marketing_opt_in
    update_request = UpdateUserSettingsRequest(
        marketing_opt_in=False,
    )

    # Execute
    result = await update_my_settings(
        http_request=mock_request_with_memory,
        request=update_request,
        auth=mock_auth_context,
    )

    # Verify: source changed to settings_api
    assert result.marketing_opt_in_source == "settings_api"

    # Verify in saved node
    saved_node = mock_memory_service.memorize.call_args[0][0]
    assert saved_node.attributes["marketing_opt_in_source"] == "settings_api"


@pytest.mark.asyncio
async def test_update_my_settings_memory_service_unavailable(mock_auth_context):
    """Test PUT settings when memory service is not available."""
    from fastapi import HTTPException

    # Setup: request with no memory service
    request = Mock()
    request.app = Mock()
    request.app.state = Mock()
    request.app.state.memory_service = None

    update_request = UpdateUserSettingsRequest(location="London")

    # Execute & Verify: should raise 503
    with pytest.raises(HTTPException) as exc_info:
        await update_my_settings(
            http_request=request,
            request=update_request,
            auth=mock_auth_context,
        )

    assert exc_info.value.status_code == 503
    assert "Memory service not available" in str(exc_info.value.detail)


@pytest.mark.asyncio
async def test_update_my_settings_bypasses_protected_attributes(
    mock_request_with_memory,
    mock_auth_context,
    mock_memory_service,
    sample_user_node,
):
    """Test that user settings API bypasses MANAGED_USER_ATTRIBUTES protection.

    This endpoint calls memory_service.memorize() directly, which should
    bypass the MANAGED_USER_ATTRIBUTES check in memorize_handler.py.
    """
    # Setup
    mock_memory_service.recall.return_value = [sample_user_node]
    mock_memory_service.memorize = AsyncMock()

    # Update user_preferred_name (which is in MANAGED_USER_ATTRIBUTES)
    update_request = UpdateUserSettingsRequest(
        user_preferred_name="Updated via API",
    )

    # Execute: should succeed without triggering protection
    result = await update_my_settings(
        http_request=mock_request_with_memory,
        request=update_request,
        auth=mock_auth_context,
    )

    # Verify: update succeeded
    assert result.user_preferred_name == "Updated via API"

    # Verify memorize was called with handler_name="UserSettingsAPI"
    mock_memory_service.memorize.assert_called_once()
    call_kwargs = mock_memory_service.memorize.call_args[1]
    assert call_kwargs["handler_name"] == "UserSettingsAPI"


# =============================================================================
# ERROR HANDLING TESTS
# =============================================================================


@pytest.mark.asyncio
async def test_get_my_settings_memory_error(
    mock_request_with_memory,
    mock_auth_context,
    mock_memory_service,
):
    """Test GET settings when memory service raises an error."""
    from fastapi import HTTPException

    # Setup: memory service raises exception
    mock_memory_service.recall.side_effect = RuntimeError("Database connection failed")

    # Execute & Verify
    with pytest.raises(HTTPException) as exc_info:
        await get_my_settings(
            request=mock_request_with_memory,
            auth=mock_auth_context,
        )

    assert exc_info.value.status_code == 500
    assert "Failed to retrieve user settings" in str(exc_info.value.detail)


@pytest.mark.asyncio
async def test_update_my_settings_memory_error(
    mock_request_with_memory,
    mock_auth_context,
    mock_memory_service,
):
    """Test PUT settings when memory service raises an error."""
    from fastapi import HTTPException

    # Setup: memory service raises exception on memorize
    mock_memory_service.recall.return_value = []
    mock_memory_service.memorize = AsyncMock(side_effect=RuntimeError("Write failed"))

    update_request = UpdateUserSettingsRequest(location="London")

    # Execute & Verify
    with pytest.raises(HTTPException) as exc_info:
        await update_my_settings(
            http_request=mock_request_with_memory,
            request=update_request,
            auth=mock_auth_context,
        )

    assert exc_info.value.status_code == 500
    assert "Failed to update user settings" in str(exc_info.value.detail)
