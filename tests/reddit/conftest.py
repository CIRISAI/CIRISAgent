"""Pytest fixtures for Reddit module tests."""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock, Mock

import pytest

from ciris_modular_services.reddit.schemas import (
    RedditChannelReference,
    RedditCommentResult,
    RedditCommentSummary,
    RedditCredentials,
    RedditPostResult,
    RedditRemovalResult,
    RedditToken,
)


@pytest.fixture
def reddit_credentials() -> RedditCredentials:
    """Create test Reddit credentials."""
    return RedditCredentials(
        client_id="test_client_id",
        client_secret="test_client_secret",
        username="test_bot",
        password="test_password",
        user_agent="CIRIS-RedditAdapter-Test/1.0",
        subreddit="test_subreddit",
    )


@pytest.fixture
def reddit_token() -> RedditToken:
    """Create test Reddit OAuth token."""
    return RedditToken(
        access_token="test_access_token_12345", expires_at=datetime.now(timezone.utc) + timedelta(hours=1)
    )


@pytest.fixture
def mock_httpx_response() -> Mock:
    """Create mock httpx response."""
    response = Mock()
    response.status_code = 200
    response.json.return_value = {"access_token": "test_token", "expires_in": 3600}
    response.text = "OK"
    return response


@pytest.fixture
def mock_reddit_api_client(reddit_credentials: RedditCredentials, reddit_token: RedditToken) -> AsyncMock:
    """Create mock Reddit API client."""
    client = AsyncMock()
    client._credentials = reddit_credentials
    client._token = reddit_token
    client._request_count = 0
    client._error_count = 0

    # Mock common methods
    client.start = AsyncMock()
    client.stop = AsyncMock()
    client.refresh_token = AsyncMock(return_value=True)
    client.delete_content = AsyncMock(return_value=True)
    client.submit_comment = AsyncMock(
        return_value=RedditCommentResult(
            comment=RedditCommentSummary(
                comment_id="abc123",
                fullname="t1_abc123",
                permalink="/r/test/comments/xyz/test/abc123",
                subreddit="test",
                author="test_bot",
                body="Test comment",
                created_at=datetime.now(timezone.utc),
                score=1,
                submission_id="xyz",
                channel_reference="reddit:r/test:post/xyz:comment/abc123",
            )
        )
    )
    client._fetch_item_metadata = AsyncMock(return_value={"removed_by_category": None, "removed": False})

    return client


@pytest.fixture
def mock_time_service() -> Mock:
    """Create mock time service."""
    service = Mock()
    service.now.return_value = datetime.now(timezone.utc)
    return service


@pytest.fixture
def sample_submission_data() -> Dict[str, Any]:
    """Sample Reddit submission data."""
    return {
        "id": "test123",
        "name": "t3_test123",
        "title": "Test Submission",
        "selftext": "Test content",
        "subreddit": "test",
        "author": "test_user",
        "score": 42,
        "num_comments": 5,
        "created_utc": datetime.now(timezone.utc).timestamp(),
        "permalink": "/r/test/comments/test123/test_submission/",
        "url": "https://reddit.com/r/test/comments/test123/test_submission/",
    }


@pytest.fixture
def sample_comment_data() -> Dict[str, Any]:
    """Sample Reddit comment data."""
    return {
        "id": "comment123",
        "name": "t1_comment123",
        "body": "Test comment body",
        "author": "test_user",
        "subreddit": "test",
        "link_id": "t3_test123",
        "score": 10,
        "created_utc": datetime.now(timezone.utc).timestamp(),
        "permalink": "/r/test/comments/test123/test_submission/comment123/",
    }


@pytest.fixture
def sample_deleted_content_data() -> Dict[str, Any]:
    """Sample deleted Reddit content data."""
    return {
        "id": "deleted123",
        "name": "t3_deleted123",
        "removed_by_category": "moderator",
        "removed": True,
        "deleted": True,
    }


@pytest.fixture
def reddit_channel_reference() -> str:
    """Sample Reddit channel reference."""
    return "reddit:r/test:post/test123"


@pytest.fixture
def reddit_comment_reference() -> str:
    """Sample Reddit comment channel reference."""
    return "reddit:r/test:post/test123:comment/comment123"
