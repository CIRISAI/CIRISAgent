"""Tests for Reddit schemas."""

from datetime import datetime, timezone

import pytest

from ciris_modular_services.reddit.schemas import (
    RedditChannelReference,
    RedditChannelType,
    RedditCredentials,
    RedditDeleteContentRequest,
    RedditDeletionResult,
    RedditDeletionStatus,
    RedditDisclosureRequest,
)


class TestRedditSchemas:
    """Test Reddit Pydantic schemas."""

    def test_reddit_credentials_from_dict(self):
        """Test RedditCredentials creation from dict."""
        creds = RedditCredentials(
            client_id="test_id",
            client_secret="test_secret",
            username="test_user",
            password="test_pass",
            user_agent="test_agent",
            subreddit="test_sub",
        )
        assert creds.client_id == "test_id"
        assert creds.subreddit == "test_sub"

    def test_reddit_channel_reference_parse_subreddit(self):
        """Test parsing subreddit channel reference."""
        ref = RedditChannelReference.parse("reddit:r/test")
        assert ref.target == RedditChannelType.SUBREDDIT
        assert ref.subreddit == "test"

    def test_reddit_channel_reference_parse_submission(self):
        """Test parsing submission channel reference."""
        ref = RedditChannelReference.parse("reddit:r/test:post/abc123")
        assert ref.target == RedditChannelType.SUBMISSION
        assert ref.subreddit == "test"
        assert ref.submission_id == "abc123"

    def test_reddit_channel_reference_parse_comment(self):
        """Test parsing comment channel reference."""
        ref = RedditChannelReference.parse("reddit:r/test:post/abc123:comment/xyz789")
        assert ref.target == RedditChannelType.COMMENT
        assert ref.subreddit == "test"
        assert ref.submission_id == "abc123"
        assert ref.comment_id == "xyz789"

    def test_reddit_delete_content_request_defaults(self):
        """Test RedditDeleteContentRequest default values."""
        req = RedditDeleteContentRequest(thing_fullname="t3_test")
        assert req.thing_fullname == "t3_test"
        assert req.purge_cache is True  # Default should be True for ToS compliance

    def test_reddit_deletion_status_is_complete(self):
        """Test RedditDeletionStatus.is_complete property."""
        now = datetime.now(timezone.utc)

        # Incomplete - missing cache purge
        incomplete = RedditDeletionStatus(
            content_id="test",
            initiated_at=now,
            deletion_confirmed=True,
            cache_purged=False,
            audit_trail_updated=True,
        )
        assert incomplete.is_complete is False

        # Complete - all phases done
        complete = RedditDeletionStatus(
            content_id="test",
            initiated_at=now,
            completed_at=now,
            deletion_confirmed=True,
            cache_purged=True,
            audit_trail_updated=True,
        )
        assert complete.is_complete is True

    def test_reddit_disclosure_request_required_fields(self):
        """Test RedditDisclosureRequest required fields."""
        req = RedditDisclosureRequest(channel_reference="reddit:r/test:post/abc")
        assert req.channel_reference == "reddit:r/test:post/abc"
        assert req.custom_message is None

    def test_reddit_disclosure_request_with_custom_message(self):
        """Test RedditDisclosureRequest with custom message."""
        req = RedditDisclosureRequest(channel_reference="reddit:r/test:post/abc", custom_message="Custom disclosure")
        assert req.custom_message == "Custom disclosure"
