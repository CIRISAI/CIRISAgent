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
