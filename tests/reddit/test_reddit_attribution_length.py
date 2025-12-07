"""Tests for Reddit attribution length handling."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ciris_adapters.reddit.schemas import RedditCredentials, RedditSubmitCommentRequest, RedditSubmitPostRequest
from ciris_adapters.reddit.service import RedditAPIClient


@pytest.fixture
def mock_credentials():
    """Mock Reddit credentials."""
    return RedditCredentials(
        client_id="test_client_id",
        client_secret="test_client_secret",
        username="test_user",
        password="test_pass",
        subreddit="test",
        user_agent="CIRIS-Test/1.0",
    )


@pytest.fixture
def client(mock_credentials):
    """Create RedditAPIClient instance."""
    return RedditAPIClient(mock_credentials)


class TestAttributionLengthHandling:
    """Test Reddit attribution footer length handling."""

    def test_attribution_within_limit(self, client):
        """Test that short text gets attribution without truncation."""
        text = "Hello world!"
        result = client._add_ciris_attribution(text)

        assert text in result
        assert "Posted by a CIRIS agent" in result
        assert "https://ciris.ai" in result
        assert len(result) <= 10000

    def test_attribution_exactly_at_limit(self, client):
        """Test text that exactly fits with attribution."""
        # Create text that with attribution equals 10000 chars
        attribution_length = len(client._add_ciris_attribution("")) - 0  # Just attribution
        text = "A" * (10000 - attribution_length)

        result = client._add_ciris_attribution(text)

        assert len(result) == 10000
        assert "Posted by a CIRIS agent" in result
        assert not result.startswith("...")

    def test_attribution_exceeds_limit_truncates(self, client):
        """Test that text exceeding limit gets truncated."""
        # Create text that would exceed 10000 with attribution
        text = "A" * 10000  # Already at limit without attribution

        result = client._add_ciris_attribution(text)

        assert len(result) <= 10000
        assert "Posted by a CIRIS agent" in result
        assert "..." in result  # Truncation marker
        assert result.count("A") < 10000  # Original text was truncated

    def test_attribution_near_limit(self, client):
        """Test text very close to limit (within 150 chars)."""
        # Create text that's 9900 chars (within 100 of limit)
        text = "B" * 9900

        result = client._add_ciris_attribution(text)

        assert len(result) <= 10000
        assert "Posted by a CIRIS agent" in result
        # May or may not be truncated depending on attribution length
        if len(result) == 10000:
            assert "..." in result

    def test_attribution_custom_limit(self, client):
        """Test custom max_length parameter."""
        text = "C" * 500
        custom_limit = 600

        result = client._add_ciris_attribution(text, max_length=custom_limit)

        assert len(result) <= custom_limit
        assert "Posted by a CIRIS agent" in result

    def test_attribution_very_short_limit(self, client):
        """Test behavior when limit is too small for attribution."""
        text = "D" * 50
        tiny_limit = 50  # Too small for attribution

        result = client._add_ciris_attribution(text, max_length=tiny_limit)

        # Should return truncated text without attribution
        assert len(result) <= tiny_limit
        assert "Posted by a CIRIS agent" not in result

    def test_attribution_preserves_content_priority(self, client):
        """Test that original content is prioritized over attribution when truncating."""
        # Create text slightly over limit
        text = "Important content: " + "X" * 9990

        result = client._add_ciris_attribution(text)

        assert len(result) <= 10000
        assert "Important content:" in result  # Beginning preserved
        assert "Posted by a CIRIS agent" in result  # Attribution included
        assert "..." in result  # Truncation marker present

    def test_attribution_multiline_text(self, client):
        """Test attribution with multiline text."""
        text = "Line 1\nLine 2\nLine 3\n" + "Z" * 9950

        result = client._add_ciris_attribution(text)

        assert len(result) <= 10000
        assert "Posted by a CIRIS agent" in result
        assert "Line 1" in result

    @pytest.mark.asyncio
    async def test_submit_post_respects_limit(self, client, mock_credentials):
        """Test that submit_post doesn't send oversized content to Reddit."""
        # Mock token refresh to avoid authentication
        with patch.object(client, "refresh_token", new_callable=AsyncMock) as mock_refresh:
            mock_refresh.return_value = True
            client._token = MagicMock(access_token="test_token", is_expired=lambda x: False)

            await client.start()

            # Create a post with text at limit
            long_text = "Y" * 9990
            request = RedditSubmitPostRequest(title="Test", body=long_text, subreddit="test")

            with patch.object(client, "_request", new_callable=AsyncMock) as mock_request:
                mock_response = MagicMock()
                mock_response.status_code = 200
                mock_response.json.return_value = {
                    "json": {
                        "errors": [],
                        "data": {
                            "id": "test123",
                            "name": "t3_test123",
                            "url": "https://reddit.com/r/test/comments/test123",
                        },
                    }
                }
                mock_request.return_value = mock_response

                await client.submit_post(request)

                # Verify the submitted text length
                call_args = mock_request.call_args
                submitted_data = call_args.kwargs["data"]
                submitted_text = submitted_data["text"]

                assert len(submitted_text) <= 10000
                assert "Posted by a CIRIS agent" in submitted_text

            await client.stop()

    @pytest.mark.asyncio
    async def test_submit_comment_respects_limit(self, client, mock_credentials):
        """Test that submit_comment doesn't send oversized content to Reddit."""
        # Mock token refresh to avoid authentication
        with patch.object(client, "refresh_token", new_callable=AsyncMock) as mock_refresh:
            mock_refresh.return_value = True
            client._token = MagicMock(access_token="test_token", is_expired=lambda x: False)

            await client.start()

            # Create a comment with text at limit
            long_text = "W" * 9990
            request = RedditSubmitCommentRequest(parent_fullname="t3_abc123", text=long_text)

            with patch.object(client, "_request", new_callable=AsyncMock) as mock_request:
                mock_response = MagicMock()
                mock_response.status_code = 200
                mock_response.json.return_value = {
                    "json": {
                        "errors": [],
                        "data": {
                            "things": [
                                {
                                    "data": {
                                        "id": "comment123",
                                        "name": "t1_comment123",
                                        "body": long_text[:100],
                                        "link_id": "t3_abc123",
                                        "subreddit": "test",
                                        "author": "test_user",
                                        "created_utc": "1234567890",
                                        "score": "1",
                                        "permalink": "/r/test/comments/abc123/_/comment123",
                                    }
                                }
                            ],
                        },
                    }
                }
                mock_request.return_value = mock_response

                await client.submit_comment(request)

                # Verify the submitted text length
                call_args = mock_request.call_args
                submitted_data = call_args.kwargs["data"]
                submitted_text = submitted_data["text"]

                assert len(submitted_text) <= 10000
                assert "Posted by a CIRIS agent" in submitted_text

            await client.stop()

    def test_attribution_exact_boundary_cases(self, client):
        """Test exact boundary cases for truncation logic."""
        attribution = client._add_ciris_attribution("")
        attribution_len = len(attribution)

        # Case 1: Text that exactly fits
        exact_fit_text = "F" * (10000 - attribution_len)
        result = client._add_ciris_attribution(exact_fit_text)
        assert len(result) == 10000
        assert "..." not in result

        # Case 2: Text that's 1 char over
        one_over_text = "G" * (10000 - attribution_len + 1)
        result = client._add_ciris_attribution(one_over_text)
        assert len(result) <= 10000
        assert "..." in result

        # Case 3: Text that's 100 chars over
        hundred_over_text = "H" * (10000 - attribution_len + 100)
        result = client._add_ciris_attribution(hundred_over_text)
        assert len(result) <= 10000
        assert "..." in result
