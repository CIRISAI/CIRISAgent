import pytest
from unittest.mock import AsyncMock, MagicMock
from ciris_adapters.reddit.observer import RedditObserver
from ciris_adapters.reddit.schemas import RedditCredentials

@pytest.mark.asyncio
async def test_purge_deleted_content_logs_audit_event():
    """Test that purging content logs an audit event."""

    # Mock credentials
    creds = MagicMock(spec=RedditCredentials)
    creds.subreddit = "test_subreddit"
    creds.username = "test_user"
    creds.password = "test_pass"
    creds.client_id = "test_id"
    creds.client_secret = "test_secret"
    creds.user_agent = "test_agent"

    # Mock audit service
    audit_service = AsyncMock()

    # Initialize observer with mock audit service
    # This is expected to raise TypeError before the fix is implemented
    try:
        observer = RedditObserver(
            credentials=creds,
            audit_service=audit_service
        )
    except TypeError:
        pytest.fail("RedditObserver does not accept audit_service argument yet")

    # Simulate content in cache
    observer._seen_posts["post123"] = None

    # Call purge
    await observer.purge_deleted_content("post123", "submission")

    # Verify audit log
    assert audit_service.log_event.called

    # Verify call arguments
    args, _ = audit_service.log_event.call_args
    event = args[0]
    assert event["event"] == "reddit_content_purged"
    assert event["content_id"] == "post123"
    assert event["content_type"] == "submission"
    assert event["purged_from_posts"] is True
