"""Tests for user_utils.py - user nickname extraction utility."""

from unittest.mock import AsyncMock, Mock, patch

import pytest

from ciris_engine.logic.utils.user_utils import extract_user_nick


class TestExtractUserNick:
    """Test extract_user_nick function."""

    @pytest.mark.asyncio
    async def test_extract_from_discord_message_display_name(self):
        """Test extracting nickname from Discord message with display_name."""
        # Create mock Discord message
        message = Mock()
        message.author = Mock(display_name="CoolUser123", name="actual_username")

        result = await extract_user_nick(message=message)

        assert result == "CoolUser123"

    @pytest.mark.asyncio
    async def test_extract_from_discord_message_fallback_to_name(self):
        """Test extracting nickname from Discord message falling back to name."""
        # Create mock Discord message without display_name
        message = Mock()
        author = Mock()
        author.display_name = None
        author.name = "actual_username"
        message.author = author

        result = await extract_user_nick(message=message)

        assert result == "actual_username"

    @pytest.mark.asyncio
    async def test_extract_from_discord_message_empty_display_name(self):
        """Test extracting nickname when display_name is empty string."""
        # Create mock Discord message with empty display_name
        message = Mock()
        author = Mock()
        author.display_name = ""
        author.name = "actual_username"
        message.author = author

        result = await extract_user_nick(message=message)

        assert result == "actual_username"

    @pytest.mark.asyncio
    async def test_extract_from_discord_message_no_author(self):
        """Test extracting nickname from Discord message without author."""
        # Create mock Discord message without author
        message = Mock(spec=[])  # No author attribute

        result = await extract_user_nick(message=message)

        assert result is None

    @pytest.mark.asyncio
    async def test_extract_from_params_with_nick(self):
        """Test extracting nickname from params object with nick in value dict."""
        # Create mock params object
        params = Mock()
        params.value = {"nick": "ParamsUser", "user_id": "user_789"}

        result = await extract_user_nick(params=params)

        assert result == "ParamsUser"

    @pytest.mark.asyncio
    async def test_extract_from_params_with_user_id_fallback(self):
        """Test extracting nickname from params falling back to user_id."""
        # Create mock params object without nick
        params = Mock()
        params.value = {"user_id": "user_789"}

        result = await extract_user_nick(params=params)

        assert result == "user_789"

    @pytest.mark.asyncio
    async def test_extract_from_params_value_not_dict(self):
        """Test extracting nickname from params when value is not a dict."""
        # Create mock params object with non-dict value
        params = Mock()
        params.value = "not a dict"

        result = await extract_user_nick(params=params)

        assert result is None

    @pytest.mark.asyncio
    async def test_extract_from_dispatch_context_author_name(self):
        """Test extracting nickname from dispatch context with author_name."""
        dispatch_context = {"author_name": "ContextUser", "user_id": "user_456"}

        result = await extract_user_nick(dispatch_context=dispatch_context)

        assert result == "ContextUser"

    @pytest.mark.asyncio
    async def test_extract_from_dispatch_context_user_id_fallback(self):
        """Test extracting nickname from dispatch context falling back to user_id."""
        dispatch_context = {"user_id": "user_456"}

        result = await extract_user_nick(dispatch_context=dispatch_context)

        assert result == "user_456"

    @pytest.mark.asyncio
    async def test_extract_from_dispatch_context_empty(self):
        """Test extracting nickname from empty dispatch context."""
        dispatch_context = {}

        result = await extract_user_nick(dispatch_context=dispatch_context)

        assert result is None

    @pytest.mark.asyncio
    async def test_extract_from_thought_id_with_dict_context(self):
        """Test extracting nickname from thought_id with dict-like task context."""
        # Mock thought and task
        mock_thought = Mock()
        mock_thought.source_task_id = "task_123"

        mock_task = Mock()
        mock_task.context = {"author_name": "TaskUser", "user_id": "user_999"}

        with patch("ciris_engine.logic.utils.user_utils.persistence") as mock_persistence:
            mock_persistence.async_get_thought_by_id = AsyncMock(return_value=mock_thought)
            mock_persistence.get_task_by_id = Mock(return_value=mock_task)

            result = await extract_user_nick(thought_id="thought_456")

            assert result == "TaskUser"
            mock_persistence.async_get_thought_by_id.assert_called_once_with("thought_456")
            mock_persistence.get_task_by_id.assert_called_once_with("task_123")

    @pytest.mark.asyncio
    async def test_extract_from_thought_id_with_object_context(self):
        """Test extracting nickname from thought_id with object-like task context."""
        # Mock thought and task with object context
        mock_thought = Mock()
        mock_thought.source_task_id = "task_123"

        # Create a mock object without 'get' method to force attribute access
        mock_context = Mock(spec=["author_name", "user_id"])
        mock_context.author_name = "ObjectUser"
        mock_context.user_id = "user_888"

        mock_task = Mock()
        mock_task.context = mock_context

        with patch("ciris_engine.logic.utils.user_utils.persistence") as mock_persistence:
            mock_persistence.async_get_thought_by_id = AsyncMock(return_value=mock_thought)
            mock_persistence.get_task_by_id = Mock(return_value=mock_task)

            result = await extract_user_nick(thought_id="thought_789")

            assert result == "ObjectUser"

    @pytest.mark.asyncio
    async def test_extract_from_thought_id_fallback_to_user_id(self):
        """Test extracting nickname from thought_id falling back to user_id."""
        # Mock thought and task without author_name
        mock_thought = Mock()
        mock_thought.source_task_id = "task_123"

        mock_task = Mock()
        mock_task.context = {"user_id": "user_999"}

        with patch("ciris_engine.logic.utils.user_utils.persistence") as mock_persistence:
            mock_persistence.async_get_thought_by_id = AsyncMock(return_value=mock_thought)
            mock_persistence.get_task_by_id = Mock(return_value=mock_task)

            result = await extract_user_nick(thought_id="thought_456")

            assert result == "user_999"

    @pytest.mark.asyncio
    async def test_extract_from_thought_id_no_source_task(self):
        """Test extracting nickname from thought without source_task_id."""
        # Mock thought without source_task_id
        mock_thought = Mock()
        mock_thought.source_task_id = None

        with patch("ciris_engine.logic.utils.user_utils.persistence") as mock_persistence:
            mock_persistence.async_get_thought_by_id = AsyncMock(return_value=mock_thought)

            result = await extract_user_nick(thought_id="thought_456")

            assert result is None
            mock_persistence.get_task_by_id.assert_not_called()

    @pytest.mark.asyncio
    async def test_extract_from_thought_id_thought_not_found(self):
        """Test extracting nickname when thought is not found."""
        with patch("ciris_engine.logic.utils.user_utils.persistence") as mock_persistence:
            mock_persistence.async_get_thought_by_id = AsyncMock(return_value=None)

            result = await extract_user_nick(thought_id="nonexistent_thought")

            assert result is None
            mock_persistence.get_task_by_id.assert_not_called()

    @pytest.mark.asyncio
    async def test_extract_from_thought_id_task_not_found(self):
        """Test extracting nickname when parent task is not found."""
        # Mock thought but task doesn't exist
        mock_thought = Mock()
        mock_thought.source_task_id = "task_123"

        with patch("ciris_engine.logic.utils.user_utils.persistence") as mock_persistence:
            mock_persistence.async_get_thought_by_id = AsyncMock(return_value=mock_thought)
            mock_persistence.get_task_by_id = Mock(return_value=None)

            result = await extract_user_nick(thought_id="thought_456")

            assert result is None

    @pytest.mark.asyncio
    async def test_extract_from_thought_id_task_no_context(self):
        """Test extracting nickname when parent task has no context."""
        # Mock thought and task without context
        mock_thought = Mock()
        mock_thought.source_task_id = "task_123"

        mock_task = Mock()
        mock_task.context = None

        with patch("ciris_engine.logic.utils.user_utils.persistence") as mock_persistence:
            mock_persistence.async_get_thought_by_id = AsyncMock(return_value=mock_thought)
            mock_persistence.get_task_by_id = Mock(return_value=mock_task)

            result = await extract_user_nick(thought_id="thought_456")

            assert result is None

    @pytest.mark.asyncio
    async def test_extract_from_thought_id_persistence_error(self):
        """Test extracting nickname when persistence raises exception."""
        with patch("ciris_engine.logic.utils.user_utils.persistence") as mock_persistence:
            mock_persistence.async_get_thought_by_id = AsyncMock(side_effect=Exception("DB error"))

            # Should not raise, should return None
            result = await extract_user_nick(thought_id="thought_456")

            assert result is None

    @pytest.mark.asyncio
    async def test_priority_order_message_over_params(self):
        """Test that Discord message takes priority over params."""
        # Create both message and params
        message = Mock()
        message.author = Mock(display_name="MessageUser", name="msg_user")

        params = Mock()
        params.value = {"nick": "ParamsUser"}

        result = await extract_user_nick(message=message, params=params)

        # Should use message, not params
        assert result == "MessageUser"

    @pytest.mark.asyncio
    async def test_priority_order_params_over_dispatch_context(self):
        """Test that params takes priority over dispatch_context."""
        # Create both params and dispatch_context
        params = Mock()
        params.value = {"nick": "ParamsUser"}

        dispatch_context = {"author_name": "ContextUser"}

        result = await extract_user_nick(params=params, dispatch_context=dispatch_context)

        # Should use params, not dispatch_context
        assert result == "ParamsUser"

    @pytest.mark.asyncio
    async def test_priority_order_dispatch_context_over_thought_id(self):
        """Test that dispatch_context takes priority over thought_id."""
        dispatch_context = {"author_name": "ContextUser"}

        # Mock persistence for thought_id
        mock_thought = Mock()
        mock_thought.source_task_id = "task_123"
        mock_task = Mock()
        mock_task.context = {"author_name": "TaskUser"}

        with patch("ciris_engine.logic.utils.user_utils.persistence") as mock_persistence:
            mock_persistence.async_get_thought_by_id = AsyncMock(return_value=mock_thought)
            mock_persistence.get_task_by_id = Mock(return_value=mock_task)

            result = await extract_user_nick(dispatch_context=dispatch_context, thought_id="thought_456")

            # Should use dispatch_context, not thought_id
            assert result == "ContextUser"
            # Persistence should not be called
            mock_persistence.async_get_thought_by_id.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_sources_returns_none(self):
        """Test that no sources returns None."""
        result = await extract_user_nick()

        assert result is None

    @pytest.mark.asyncio
    async def test_all_sources_empty_returns_none(self):
        """Test that all empty sources returns None."""
        # Create all sources but with no useful data
        message = Mock(spec=[])  # No author
        params = Mock()
        params.value = "not a dict"
        dispatch_context = {}

        with patch("ciris_engine.logic.utils.user_utils.persistence") as mock_persistence:
            mock_persistence.async_get_thought_by_id = AsyncMock(return_value=None)

            result = await extract_user_nick(
                message=message, params=params, dispatch_context=dispatch_context, thought_id="thought_456"
            )

            assert result is None
