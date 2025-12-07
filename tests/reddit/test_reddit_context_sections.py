"""Tests for Reddit observer custom context sections.

Ensures thread context and recent posts are properly added to observations.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock, patch

import pytest

from ciris_adapters.reddit.observer import RedditObserver
from ciris_adapters.reddit.schemas import RedditCommentSummary, RedditCredentials, RedditMessage, RedditTimelineEntry


@pytest.fixture
def mock_credentials():
    """Create mock Reddit credentials."""
    return RedditCredentials(
        client_id="test_client",
        client_secret="test_secret",
        username="test_bot",
        password="test_password",
        user_agent="test_agent",
        subreddit="test",
    )


@pytest.fixture
def reddit_observer(mock_credentials):
    """Create RedditObserver with mocked dependencies."""
    observer = RedditObserver(
        credentials=mock_credentials,
        subreddit="test",
        bus_manager=Mock(),
        memory_service=Mock(),
        agent_id="test_agent",
        filter_service=Mock(),
        secrets_service=Mock(),
        time_service=Mock(),
    )
    return observer


@pytest.fixture
def sample_reddit_message():
    """Create a sample RedditMessage for testing."""
    return RedditMessage(
        message_id="comment_123",
        author_id="test_user",
        author_name="TestUser",
        content="Test comment content",
        channel_id="reddit_test_post_456_comment_123",
        channel_reference="reddit_test_post_456_comment_123",
        permalink="https://reddit.com/r/test/comments/post_456/title/comment_123",
        subreddit="test",
        submission_id="post_456",
        comment_id="comment_123",
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


class TestAddCustomContextSections:
    """Tests for _add_custom_context_sections method."""

    @pytest.mark.asyncio
    async def test_adds_thread_and_subreddit_context(self, reddit_observer, sample_reddit_message):
        """Should add both thread context and recent posts when available."""
        task_lines = []

        # Mock API client methods
        reddit_observer._api_client.fetch_submission_comments = AsyncMock(
            return_value=[
                RedditCommentSummary(
                    comment_id="other_comment_1",
                    fullname="t1_other_comment_1",
                    submission_id="post_456",
                    body="First other comment",
                    author="OtherUser1",
                    subreddit="test",
                    permalink="https://reddit.com/r/test/comments/post_456/title/other_comment_1",
                    created_at=datetime.now(timezone.utc),
                    score=5,
                    channel_reference="reddit_test_post_456_other_comment_1",
                )
            ]
        )

        reddit_observer._api_client.fetch_subreddit_new = AsyncMock(
            return_value=[
                RedditTimelineEntry(
                    item_id="recent_post_1",
                    fullname="t3_recent_post_1",
                    subreddit="test",
                    score=10,
                    entry_type="submission",
                    title="Recent Post Title",
                    body="Recent post body",
                    author="RecentAuthor",
                    created_at=datetime.now(timezone.utc),
                    channel_reference="reddit_test_recent_post_1",
                    permalink="https://reddit.com/r/test/comments/recent_post_1",
                )
            ]
        )

        await reddit_observer._add_custom_context_sections(task_lines, sample_reddit_message, [])

        # Verify thread context was added
        assert any("THREAD CONTEXT" in line for line in task_lines)
        assert any("@OtherUser1" in line for line in task_lines)
        assert any("First other comment" in line for line in task_lines)

        # Verify recent posts were added
        assert any("RECENT POSTS IN r/test" in line for line in task_lines)
        assert any("Recent Post Title" in line for line in task_lines)

    @pytest.mark.asyncio
    async def test_handles_no_submission_id(self, reddit_observer):
        """Should skip thread context when message has no submission_id."""
        task_lines = []
        msg = RedditMessage(
            message_id="msg_123",
            author_id="test_user",
            author_name="TestUser",
            content="Test content",
            channel_id="reddit_test",
            subreddit="test",
            submission_id=None,  # No submission ID
        )

        reddit_observer._api_client.fetch_subreddit_new = AsyncMock(return_value=[])

        await reddit_observer._add_custom_context_sections(task_lines, msg, [])

        # Should not have thread context
        assert not any("THREAD CONTEXT" in line for line in task_lines)

    @pytest.mark.asyncio
    async def test_handles_api_errors_gracefully(self, reddit_observer, sample_reddit_message):
        """Should not raise exceptions when API calls fail (silent failure in helper methods)."""
        task_lines = []

        # Mock API failures
        reddit_observer._api_client.fetch_submission_comments = AsyncMock(side_effect=Exception("API Error"))
        reddit_observer._api_client.fetch_subreddit_new = AsyncMock(side_effect=Exception("API Error"))

        # Should not raise exception
        await reddit_observer._add_custom_context_sections(task_lines, sample_reddit_message, [])

        # The helper methods fail silently (logged but not added to context)
        # This is expected behavior - we don't want to pollute context with errors
        assert isinstance(task_lines, list)  # Just verify it completes without exception


class TestAddThreadContext:
    """Tests for _add_thread_context method."""

    @pytest.mark.asyncio
    async def test_fetches_and_formats_comments(self, reddit_observer):
        """Should fetch comments and format them properly."""
        task_lines = []

        comments = [
            RedditCommentSummary(
                comment_id="comment_1",
                fullname="t1_comment_1",
                submission_id="post_123",
                body="This is a test comment with some content",
                author="User1",
                subreddit="test",
                permalink="https://reddit.com/r/test/comments/post_123/title/comment_1",
                created_at=datetime.now(timezone.utc),
                score=10,
                channel_reference="reddit_test_post_123_comment_1",
            ),
            RedditCommentSummary(
                comment_id="comment_2",
                fullname="t1_comment_2",
                submission_id="post_123",
                body="Another comment here",
                author="User2",
                subreddit="test",
                permalink="https://reddit.com/r/test/comments/post_123/title/comment_2",
                created_at=datetime.now(timezone.utc),
                score=5,
                channel_reference="reddit_test_post_123_comment_2",
            ),
        ]

        reddit_observer._api_client.fetch_submission_comments = AsyncMock(return_value=comments)

        await reddit_observer._add_thread_context(task_lines, "post_123", None)

        # Verify header (with newline prefix)
        assert any("THREAD CONTEXT" in line for line in task_lines)

        # Verify both comments are present
        assert any("@User1 (10 pts):" in line and "test comment" in line for line in task_lines)
        assert any("@User2 (5 pts):" in line and "Another comment" in line for line in task_lines)

        # Verify footer
        assert "=== END THREAD CONTEXT ===" in task_lines

    @pytest.mark.asyncio
    async def test_skips_current_comment(self, reddit_observer):
        """Should exclude the current comment from thread context."""
        task_lines = []

        comments = [
            RedditCommentSummary(
                comment_id="current_comment",
                fullname="t1_current_comment",
                submission_id="post_123",
                body="This is the current comment",
                author="CurrentUser",
                subreddit="test",
                permalink="https://reddit.com/r/test/comments/post_123/title/current_comment",
                created_at=datetime.now(timezone.utc),
                score=10,
                channel_reference="reddit_test_post_123_current_comment",
            ),
            RedditCommentSummary(
                comment_id="other_comment",
                fullname="t1_other_comment",
                submission_id="post_123",
                body="This is another comment",
                author="OtherUser",
                subreddit="test",
                permalink="https://reddit.com/r/test/comments/post_123/title/other_comment",
                created_at=datetime.now(timezone.utc),
                score=5,
                channel_reference="reddit_test_post_123_other_comment",
            ),
        ]

        reddit_observer._api_client.fetch_submission_comments = AsyncMock(return_value=comments)

        await reddit_observer._add_thread_context(task_lines, "post_123", "current_comment")

        # Current comment should not appear
        assert not any("CurrentUser" in line for line in task_lines)

        # Other comment should appear
        assert any("OtherUser" in line for line in task_lines)

    @pytest.mark.asyncio
    async def test_truncates_long_comments(self, reddit_observer):
        """Should truncate comments longer than 150 characters."""
        task_lines = []

        long_body = "A" * 200  # 200 character comment
        comments = [
            RedditCommentSummary(
                comment_id="long_comment",
                fullname="t1_long_comment",
                submission_id="post_123",
                body=long_body,
                author="LongUser",
                subreddit="test",
                permalink="https://reddit.com/r/test/comments/post_123/title/long_comment",
                created_at=datetime.now(timezone.utc),
                score=10,
                channel_reference="reddit_test_post_123_long_comment",
            ),
        ]

        reddit_observer._api_client.fetch_submission_comments = AsyncMock(return_value=comments)

        await reddit_observer._add_thread_context(task_lines, "post_123", None)

        # Find the comment line
        comment_lines = [line for line in task_lines if "@LongUser" in line]
        assert len(comment_lines) == 1

        # Should end with "..."
        assert comment_lines[0].endswith("...")
        # Should not contain full 200 characters
        assert len(comment_lines[0]) < len(long_body)

    @pytest.mark.asyncio
    async def test_limits_to_five_comments(self, reddit_observer):
        """Should limit thread context to 5 comments."""
        task_lines = []

        # Create 10 comments
        comments = [
            RedditCommentSummary(
                comment_id=f"comment_{i}",
                fullname=f"t1_comment_{i}",
                submission_id="post_123",
                body=f"Comment {i}",
                author=f"User{i}",
                subreddit="test",
                permalink=f"https://reddit.com/r/test/comments/post_123/title/comment_{i}",
                created_at=datetime.now(timezone.utc),
                score=i,
                channel_reference=f"reddit_test_post_123_comment_{i}",
            )
            for i in range(10)
        ]

        reddit_observer._api_client.fetch_submission_comments = AsyncMock(return_value=comments)

        await reddit_observer._add_thread_context(task_lines, "post_123", None)

        # Count comment lines (exclude header/footer)
        comment_lines = [line for line in task_lines if "@User" in line]
        assert len(comment_lines) == 5

    @pytest.mark.asyncio
    async def test_handles_no_comments(self, reddit_observer):
        """Should handle case with no comments gracefully."""
        task_lines = []

        reddit_observer._api_client.fetch_submission_comments = AsyncMock(return_value=[])

        await reddit_observer._add_thread_context(task_lines, "post_123", None)

        # With no comments, no lines should be added (function returns early)
        assert len(task_lines) == 0

    @pytest.mark.asyncio
    async def test_handles_fetch_error_silently(self, reddit_observer):
        """Should not raise exception when fetch fails."""
        task_lines = []

        reddit_observer._api_client.fetch_submission_comments = AsyncMock(side_effect=Exception("Network error"))

        # Should not raise
        await reddit_observer._add_thread_context(task_lines, "post_123", None)

        # Should not add any lines on error (silent failure)
        assert len(task_lines) == 0


class TestAddRecentPostsContext:
    """Tests for _add_recent_posts_context method."""

    @pytest.mark.asyncio
    async def test_fetches_and_formats_posts(self, reddit_observer):
        """Should fetch recent posts and format them properly."""
        task_lines = []

        posts = [
            RedditTimelineEntry(
                item_id="post_1",
                fullname="t3_post_1",
                subreddit="test",
                score=10,
                entry_type="submission",
                title="First Post Title",
                body="Post body",
                author="Author1",
                created_at=datetime(2023, 10, 15, tzinfo=timezone.utc),
                channel_reference="reddit_test_post_1",
                permalink="https://reddit.com/r/test/comments/post_1",
            ),
            RedditTimelineEntry(
                item_id="post_2",
                fullname="t3_post_2",
                subreddit="test",
                score=5,
                entry_type="submission",
                title="Second Post Title",
                body="Post body",
                author="Author2",
                created_at=datetime(2023, 10, 14, tzinfo=timezone.utc),
                channel_reference="reddit_test_post_2",
                permalink="https://reddit.com/r/test/comments/post_2",
            ),
        ]

        reddit_observer._api_client.fetch_subreddit_new = AsyncMock(return_value=posts)

        await reddit_observer._add_recent_posts_context(task_lines, "test")

        # Verify header (with newline prefix)
        assert any("RECENT POSTS IN r/test" in line for line in task_lines)

        # Verify posts are formatted with title, author, and date
        assert any("First Post Title" in line and "@Author1" in line and "2023-10-15" in line for line in task_lines)
        assert any("Second Post Title" in line and "@Author2" in line and "2023-10-14" in line for line in task_lines)

        # Verify footer
        assert "=== END RECENT POSTS IN r/test ===" in task_lines

    @pytest.mark.asyncio
    async def test_truncates_long_titles(self, reddit_observer):
        """Should truncate post titles longer than 100 characters."""
        task_lines = []

        long_title = "A" * 150  # 150 character title
        posts = [
            RedditTimelineEntry(
                item_id="post_1",
                fullname="t3_post_1",
                subreddit="test",
                score=10,
                entry_type="submission",
                title=long_title,
                body="Post body",
                author="Author1",
                created_at=datetime.now(timezone.utc),
                channel_reference="reddit_test_post_1",
                permalink="https://reddit.com/r/test/comments/post_1",
            ),
        ]

        reddit_observer._api_client.fetch_subreddit_new = AsyncMock(return_value=posts)

        await reddit_observer._add_recent_posts_context(task_lines, "test")

        # Find the post line
        post_lines = [line for line in task_lines if "•" in line]
        assert len(post_lines) == 1

        # Should end with "..."
        assert "..." in post_lines[0]

    @pytest.mark.asyncio
    async def test_limits_to_three_posts(self, reddit_observer):
        """Should limit recent posts to 3."""
        task_lines = []

        # Create 10 posts
        posts = [
            RedditTimelineEntry(
                item_id=f"post_{i}",
                fullname=f"t3_post_{i}",
                subreddit="test",
                score=i,
                entry_type="submission",
                title=f"Post {i}",
                body="Post body",
                author=f"Author{i}",
                created_at=datetime.now(timezone.utc),
                channel_reference=f"reddit_test_post_{i}",
                permalink=f"https://reddit.com/r/test/comments/post_{i}",
            )
            for i in range(10)
        ]

        reddit_observer._api_client.fetch_subreddit_new = AsyncMock(return_value=posts)

        await reddit_observer._add_recent_posts_context(task_lines, "test")

        # Count post lines (exclude header/footer, look for bullet points)
        post_lines = [line for line in task_lines if line.startswith("•")]
        assert len(post_lines) == 3

    @pytest.mark.asyncio
    async def test_handles_no_posts(self, reddit_observer):
        """Should handle case with no recent posts gracefully."""
        task_lines = []

        reddit_observer._api_client.fetch_subreddit_new = AsyncMock(return_value=[])

        await reddit_observer._add_recent_posts_context(task_lines, "test")

        # Should not add anything if no posts
        assert len(task_lines) == 0

    @pytest.mark.asyncio
    async def test_handles_none_title(self, reddit_observer):
        """Should handle posts with None title."""
        task_lines = []

        posts = [
            RedditTimelineEntry(
                item_id="post_1",
                fullname="t3_post_1",
                subreddit="test",
                score=10,
                entry_type="submission",
                title=None,  # No title
                body="Post body",
                author="Author1",
                created_at=datetime.now(timezone.utc),
                channel_reference="reddit_test_post_1",
                permalink="https://reddit.com/r/test/comments/post_1",
            ),
        ]

        reddit_observer._api_client.fetch_subreddit_new = AsyncMock(return_value=posts)

        await reddit_observer._add_recent_posts_context(task_lines, "test")

        # Should have "(no title)" placeholder
        assert any("(no title)" in line for line in task_lines)

    @pytest.mark.asyncio
    async def test_handles_fetch_error_silently(self, reddit_observer):
        """Should not raise exception when fetch fails."""
        task_lines = []

        reddit_observer._api_client.fetch_subreddit_new = AsyncMock(side_effect=Exception("Network error"))

        # Should not raise
        await reddit_observer._add_recent_posts_context(task_lines, "test")

        # Should not add any lines on error (silent failure)
        assert len(task_lines) == 0
