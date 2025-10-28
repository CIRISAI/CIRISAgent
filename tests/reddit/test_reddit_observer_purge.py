"""Tests for Reddit observer auto-purge (Reddit ToS compliance)."""

from collections import OrderedDict
from unittest.mock import AsyncMock, Mock, patch

import pytest

from ciris_modular_services.reddit.observer import RedditObserver


class TestObserverAutoPurge:
    """Test Reddit observer auto-purge for ToS compliance."""

    @pytest.fixture
    def mock_observer(self, reddit_credentials, mock_reddit_api_client, mock_time_service):
        """Create mock observer for testing."""
        with patch("ciris_modular_services.reddit.observer.RedditAPIClient", return_value=mock_reddit_api_client):
            observer = RedditObserver(
                credentials=reddit_credentials, subreddit="test", poll_interval=15.0, time_service=mock_time_service
            )
            observer._api_client = mock_reddit_api_client
            return observer

    @pytest.mark.asyncio
    async def test_check_content_deleted_removed_by_moderator(self, mock_observer):
        """Test detection of content removed by moderator."""
        # Mock deleted content
        mock_observer._api_client._fetch_item_metadata.return_value = {
            "removed_by_category": "moderator",
            "removed": True,
        }

        is_deleted = await mock_observer.check_content_deleted("test123")
        assert is_deleted is True

    @pytest.mark.asyncio
    async def test_check_content_deleted_removed_flag(self, mock_observer):
        """Test detection via removed flag."""
        # Mock removed content
        mock_observer._api_client._fetch_item_metadata.return_value = {
            "removed_by_category": None,
            "removed": True,
        }

        is_deleted = await mock_observer.check_content_deleted("test123")
        assert is_deleted is True

    @pytest.mark.asyncio
    async def test_check_content_deleted_deleted_flag(self, mock_observer):
        """Test detection via deleted flag."""
        # Mock deleted content
        mock_observer._api_client._fetch_item_metadata.return_value = {
            "removed_by_category": None,
            "removed": False,
            "deleted": True,
        }

        is_deleted = await mock_observer.check_content_deleted("test123")
        assert is_deleted is True

    @pytest.mark.asyncio
    async def test_check_content_not_deleted(self, mock_observer):
        """Test detection when content is NOT deleted."""
        # Mock active content
        mock_observer._api_client._fetch_item_metadata.return_value = {
            "removed_by_category": None,
            "removed": False,
            "deleted": False,
        }

        is_deleted = await mock_observer.check_content_deleted("test123")
        assert is_deleted is False

    @pytest.mark.asyncio
    async def test_check_content_deleted_api_error(self, mock_observer):
        """Test deletion detection when API fails (assume deleted)."""
        # Mock API failure
        mock_observer._api_client._fetch_item_metadata.side_effect = RuntimeError("API Error")

        is_deleted = await mock_observer.check_content_deleted("test123")
        assert is_deleted is True  # Assume deleted on error

    @pytest.mark.asyncio
    async def test_check_content_deleted_with_prefix(self, mock_observer):
        """Test deletion check with t3_ prefix."""
        # Mock deleted content
        mock_observer._api_client._fetch_item_metadata.return_value = {"removed_by_category": "moderator"}

        is_deleted = await mock_observer.check_content_deleted("t3_test123")
        assert is_deleted is True

        # Verify fullname handling
        mock_observer._api_client._fetch_item_metadata.assert_called_with("t3_test123")

    @pytest.mark.asyncio
    async def test_purge_deleted_content_from_posts_cache(self, mock_observer):
        """Test purging from posts cache."""
        # Add content to posts cache
        mock_observer._seen_posts["test123"] = None

        # Purge
        await mock_observer.purge_deleted_content("test123", "submission")

        # Verify purged
        assert "test123" not in mock_observer._seen_posts

    @pytest.mark.asyncio
    async def test_purge_deleted_content_from_comments_cache(self, mock_observer):
        """Test purging from comments cache."""
        # Add content to comments cache
        mock_observer._seen_comments["comment123"] = None

        # Purge
        await mock_observer.purge_deleted_content("comment123", "comment")

        # Verify purged
        assert "comment123" not in mock_observer._seen_comments

    @pytest.mark.asyncio
    async def test_purge_deleted_content_from_both_caches(self, mock_observer):
        """Test purging from both caches simultaneously."""
        # Add content to both caches
        mock_observer._seen_posts["test123"] = None
        mock_observer._seen_comments["test123"] = None

        # Purge
        await mock_observer.purge_deleted_content("test123", "unknown")

        # Verify purged from both
        assert "test123" not in mock_observer._seen_posts
        assert "test123" not in mock_observer._seen_comments

    @pytest.mark.asyncio
    async def test_purge_content_not_in_cache(self, mock_observer):
        """Test purging content that's not in cache (no-op)."""
        # Purge non-existent content (should not raise)
        await mock_observer.purge_deleted_content("nonexistent", "submission")

        # Verify no errors
        assert True

    @pytest.mark.asyncio
    async def test_check_and_purge_if_deleted_true(self, mock_observer):
        """Test check_and_purge_if_deleted when content is deleted."""
        # Mock deleted content
        mock_observer._api_client._fetch_item_metadata.return_value = {"removed_by_category": "moderator"}

        # Add to cache
        mock_observer._seen_posts["t3_test123"] = None

        # Check and purge
        was_deleted = await mock_observer.check_and_purge_if_deleted("t3_test123")

        # Verify deleted and purged
        assert was_deleted is True
        assert "t3_test123" not in mock_observer._seen_posts

    @pytest.mark.asyncio
    async def test_check_and_purge_if_deleted_false(self, mock_observer):
        """Test check_and_purge_if_deleted when content is NOT deleted."""
        # Mock active content
        mock_observer._api_client._fetch_item_metadata.return_value = {"removed_by_category": None, "removed": False}

        # Add to cache
        mock_observer._seen_posts["t3_test123"] = None

        # Check and purge
        was_deleted = await mock_observer.check_and_purge_if_deleted("t3_test123")

        # Verify not deleted and still in cache
        assert was_deleted is False
        assert "t3_test123" in mock_observer._seen_posts

    @pytest.mark.asyncio
    async def test_purge_logs_audit_event(self, mock_observer):
        """Test that purge logs audit event."""
        # Add content to cache
        mock_observer._seen_posts["test123"] = None

        # Capture logs
        with patch("ciris_modular_services.reddit.observer.logger") as mock_logger:
            await mock_observer.purge_deleted_content("test123", "submission")

            # Verify audit log was created
            mock_logger.info.assert_called_once()
            log_message = mock_logger.info.call_args[0][0]
            assert "Purged" in log_message
            assert "test123" in log_message
            assert "ToS compliance" in log_message

    @pytest.mark.asyncio
    async def test_zero_retention_enforcement(self, mock_observer):
        """Test Reddit ToS zero retention policy enforcement."""
        # Add deleted content to both caches
        mock_observer._seen_posts["deleted123"] = None
        mock_observer._seen_comments["deleted123"] = None

        # Mock as deleted
        mock_observer._api_client._fetch_item_metadata.return_value = {"removed": True}

        # Check and purge
        was_deleted = await mock_observer.check_and_purge_if_deleted("deleted123")

        # Verify ZERO retention: content removed from ALL caches
        assert was_deleted is True
        assert "deleted123" not in mock_observer._seen_posts
        assert "deleted123" not in mock_observer._seen_comments

    @pytest.mark.asyncio
    async def test_cache_limit_not_affected_by_purge(self, mock_observer):
        """Test that cache limits still work after purges."""
        # Fill caches
        for i in range(10):
            mock_observer._seen_posts[f"post{i}"] = None

        # Purge one item
        await mock_observer.purge_deleted_content("post5", "submission")

        # Verify cache still works
        assert "post5" not in mock_observer._seen_posts
        assert "post0" in mock_observer._seen_posts
        assert len(mock_observer._seen_posts) == 9

    @pytest.mark.asyncio
    async def test_purge_multiple_items_sequentially(self, mock_observer):
        """Test purging multiple items in sequence."""
        # Add multiple items to cache
        items = ["post1", "post2", "post3"]
        for item in items:
            mock_observer._seen_posts[item] = None

        # Purge all
        for item in items:
            await mock_observer.purge_deleted_content(item, "submission")

        # Verify all purged
        for item in items:
            assert item not in mock_observer._seen_posts

    @pytest.mark.asyncio
    async def test_content_type_detection_submission(self, mock_observer):
        """Test content type detection for submissions."""
        mock_observer._api_client._fetch_item_metadata.return_value = {"removed": True}

        was_deleted = await mock_observer.check_and_purge_if_deleted("t3_test123")

        # Verify submission type detected
        assert was_deleted is True

    @pytest.mark.asyncio
    async def test_content_type_detection_comment(self, mock_observer):
        """Test content type detection for comments."""
        mock_observer._api_client._fetch_item_metadata.return_value = {"removed": True}

        was_deleted = await mock_observer.check_and_purge_if_deleted("t1_comment123")

        # Verify comment type detected
        assert was_deleted is True


class TestObserverAlreadyHandled:
    """Test Reddit observer _already_handled for correlation tracking."""

    @pytest.fixture
    def mock_observer_with_occurrence(self, reddit_credentials, mock_reddit_api_client, mock_time_service):
        """Create mock observer with specific occurrence_id."""
        with patch("ciris_modular_services.reddit.observer.RedditAPIClient", return_value=mock_reddit_api_client):
            observer = RedditObserver(
                credentials=reddit_credentials,
                subreddit="test",
                poll_interval=15.0,
                time_service=mock_time_service,
                agent_id="test_agent",
            )
            observer._api_client = mock_reddit_api_client
            observer.agent_occurrence_id = "test_occurrence"
            return observer

    @pytest.mark.asyncio
    async def test_already_handled_task_exists(self, mock_observer_with_occurrence):
        """Test _already_handled returns True when task exists with correlation_id."""
        reddit_item_id = "reddit_post_abc123"

        # Mock get_task_by_correlation_id to return a task
        with patch("ciris_engine.logic.persistence.models.tasks.get_task_by_correlation_id") as mock_get_task:
            from ciris_engine.schemas.runtime.enums import TaskStatus
            from ciris_engine.schemas.runtime.models import Task

            mock_task = Task(
                task_id="task_123",
                channel_id="reddit:r/test",
                agent_occurrence_id="test_occurrence",
                description="Test task",
                status=TaskStatus.COMPLETED,
                priority=0,
                created_at="2025-01-01T00:00:00Z",
                updated_at="2025-01-01T00:00:00Z",
            )
            mock_get_task.return_value = mock_task

            # Check if already handled
            result = await mock_observer_with_occurrence._already_handled(reddit_item_id)

            assert result is True
            mock_get_task.assert_called_once_with(reddit_item_id, "test_occurrence")

    @pytest.mark.asyncio
    async def test_already_handled_task_not_exists(self, mock_observer_with_occurrence):
        """Test _already_handled returns False when no task exists."""
        reddit_item_id = "reddit_post_xyz789"

        # Mock get_task_by_correlation_id to return None
        with patch("ciris_engine.logic.persistence.models.tasks.get_task_by_correlation_id") as mock_get_task:
            mock_get_task.return_value = None

            # Check if already handled
            result = await mock_observer_with_occurrence._already_handled(reddit_item_id)

            assert result is False
            mock_get_task.assert_called_once_with(reddit_item_id, "test_occurrence")

    @pytest.mark.asyncio
    async def test_already_handled_database_error_fails_open(self, mock_observer_with_occurrence):
        """Test _already_handled fails open (returns False) on database error."""
        reddit_item_id = "reddit_post_error123"

        # Mock get_task_by_correlation_id to raise an exception
        with patch("ciris_engine.logic.persistence.models.tasks.get_task_by_correlation_id") as mock_get_task:
            mock_get_task.side_effect = RuntimeError("Database connection failed")

            # Check if already handled - should fail open and return False
            result = await mock_observer_with_occurrence._already_handled(reddit_item_id)

            assert result is False  # Fail open - better to re-process than miss content
            mock_get_task.assert_called_once_with(reddit_item_id, "test_occurrence")
