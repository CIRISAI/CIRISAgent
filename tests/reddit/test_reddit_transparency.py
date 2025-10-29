"""Tests for Reddit transparency disclosure (Community Guidelines requirement)."""

from unittest.mock import AsyncMock, Mock

import pytest

from ciris_modular_services.reddit.schemas import RedditDisclosureRequest
from ciris_modular_services.reddit.service import RedditToolService


class TestTransparencyCompliance:
    """Test Reddit community guidelines transparency compliance."""

    @pytest.mark.asyncio
    async def test_disclosure_request_schema(self):
        """Test RedditDisclosureRequest schema validation."""
        # Valid request with default message
        request = RedditDisclosureRequest(channel_reference="reddit:r/test:post/abc123")
        assert request.channel_reference == "reddit:r/test:post/abc123"
        assert request.custom_message is None

        # Valid request with custom message
        request_custom = RedditDisclosureRequest(
            channel_reference="reddit:r/test:post/abc123", custom_message="Custom AI disclosure"
        )
        assert request_custom.custom_message == "Custom AI disclosure"

    @pytest.mark.asyncio
    async def test_disclose_identity_default_message(
        self, reddit_credentials, mock_reddit_api_client, mock_time_service
    ):
        """Test reddit_disclose_identity with default message."""
        service = RedditToolService(reddit_credentials, time_service=mock_time_service)
        service._client = mock_reddit_api_client

        # Execute disclosure
        parameters = {"channel_reference": "reddit:r/test:post/test123"}
        result = await service._tool_disclose_identity(parameters, correlation_id="test_correlation")

        # Verify success
        assert result.success is True
        assert result.data is not None

        # Verify comment was posted
        mock_reddit_api_client.submit_comment.assert_called_once()

        # Verify comment contains disclosure elements
        call_args = mock_reddit_api_client.submit_comment.call_args
        comment_text = call_args[0][0].text

        # Check for AI identification
        assert "CIRIS" in comment_text
        assert "AI" in comment_text or "assistant" in comment_text

        # Check for disclosure footer
        assert "ciris.ai" in comment_text
        assert "Report issues" in comment_text or "report" in comment_text.lower()

    @pytest.mark.asyncio
    async def test_disclose_identity_custom_message(
        self, reddit_credentials, mock_reddit_api_client, mock_time_service
    ):
        """Test reddit_disclose_identity with custom message."""
        service = RedditToolService(reddit_credentials, time_service=mock_time_service)
        service._client = mock_reddit_api_client

        custom_msg = "This is a custom disclosure message explaining AI presence."

        # Execute disclosure with custom message
        parameters = {"channel_reference": "reddit:r/test:post/test123", "custom_message": custom_msg}
        result = await service._tool_disclose_identity(parameters, correlation_id="test_correlation")

        # Verify success
        assert result.success is True

        # Verify custom message is included
        call_args = mock_reddit_api_client.submit_comment.call_args
        comment_text = call_args[0][0].text
        assert custom_msg in comment_text

        # Verify footer is still appended
        assert "ciris.ai" in comment_text

    @pytest.mark.asyncio
    async def test_disclosure_footer_format(self, reddit_credentials, mock_reddit_api_client, mock_time_service):
        """Test that disclosure footer has correct format."""
        service = RedditToolService(reddit_credentials, time_service=mock_time_service)
        service._client = mock_reddit_api_client

        # Execute disclosure
        parameters = {"channel_reference": "reddit:r/test:post/test123"}
        result = await service._tool_disclose_identity(parameters, correlation_id="test_correlation")

        # Get posted comment
        call_args = mock_reddit_api_client.submit_comment.call_args
        comment_text = call_args[0][0].text

        # Verify footer format
        assert "---" in comment_text  # Markdown divider
        assert "*I am CIRIS" in comment_text  # Italic text with clear identification
        assert "[Learn more]" in comment_text  # Markdown link
        assert "[Report issues]" in comment_text  # Markdown link

    @pytest.mark.asyncio
    async def test_disclosure_requires_submission_id(
        self, reddit_credentials, mock_reddit_api_client, mock_time_service
    ):
        """Test that disclosure requires submission ID in channel reference."""
        service = RedditToolService(reddit_credentials, time_service=mock_time_service)
        service._client = mock_reddit_api_client

        # Try disclosure on subreddit (no submission ID)
        parameters = {"channel_reference": "reddit:r/test"}
        result = await service._tool_disclose_identity(parameters, correlation_id="test_correlation")

        # Verify failure
        assert result.success is False
        assert "submission" in result.error.lower() or "requires" in result.error.lower()

    @pytest.mark.asyncio
    async def test_disclosure_comment_parent_is_submission(
        self, reddit_credentials, mock_reddit_api_client, mock_time_service
    ):
        """Test that disclosure comment targets the submission."""
        service = RedditToolService(reddit_credentials, time_service=mock_time_service)
        service._client = mock_reddit_api_client

        # Execute disclosure
        parameters = {"channel_reference": "reddit:r/test:post/test123"}
        result = await service._tool_disclose_identity(parameters, correlation_id="test_correlation")

        # Verify parent is the submission
        call_args = mock_reddit_api_client.submit_comment.call_args
        comment_request = call_args[0][0]
        assert comment_request.parent_fullname == "t3_test123"

    @pytest.mark.asyncio
    async def test_disclosure_not_locked(self, reddit_credentials, mock_reddit_api_client, mock_time_service):
        """Test that disclosure doesn't lock the thread."""
        service = RedditToolService(reddit_credentials, time_service=mock_time_service)
        service._client = mock_reddit_api_client

        # Execute disclosure
        parameters = {"channel_reference": "reddit:r/test:post/test123"}
        result = await service._tool_disclose_identity(parameters, correlation_id="test_correlation")

        # Verify thread is not locked
        call_args = mock_reddit_api_client.submit_comment.call_args
        comment_request = call_args[0][0]
        assert comment_request.lock_thread is False

    @pytest.mark.asyncio
    async def test_disclosure_api_failure(self, reddit_credentials, mock_reddit_api_client, mock_time_service):
        """Test disclosure when Reddit API fails."""
        service = RedditToolService(reddit_credentials, time_service=mock_time_service)
        service._client = mock_reddit_api_client

        # Mock API failure
        mock_reddit_api_client.submit_comment.side_effect = RuntimeError("Reddit API Error")

        # Execute disclosure
        parameters = {"channel_reference": "reddit:r/test:post/test123"}
        result = await service._tool_disclose_identity(parameters, correlation_id="test_correlation")

        # Verify failure
        assert result.success is False
        assert "Reddit API Error" in result.error

    @pytest.mark.asyncio
    async def test_disclosure_validation_error(self, reddit_credentials, mock_time_service):
        """Test disclosure with invalid parameters."""
        service = RedditToolService(reddit_credentials, time_service=mock_time_service)

        # Missing required field
        parameters = {}
        result = await service._tool_disclose_identity(parameters, correlation_id="test_correlation")

        # Verify validation error
        assert result.success is False
        assert "channel_reference" in result.error.lower() or "required" in result.error.lower()

    @pytest.mark.asyncio
    async def test_disclosure_invalid_channel_reference(
        self, reddit_credentials, mock_reddit_api_client, mock_time_service
    ):
        """Test disclosure with invalid channel reference format."""
        service = RedditToolService(reddit_credentials, time_service=mock_time_service)
        service._client = mock_reddit_api_client

        # Invalid channel reference
        parameters = {"channel_reference": "invalid_format"}
        result = await service._tool_disclose_identity(parameters, correlation_id="test_correlation")

        # Verify failure
        assert result.success is False

    @pytest.mark.asyncio
    async def test_disclosure_human_oversight_mentioned(
        self, reddit_credentials, mock_reddit_api_client, mock_time_service
    ):
        """Test that disclosure mentions human oversight."""
        service = RedditToolService(reddit_credentials, time_service=mock_time_service)
        service._client = mock_reddit_api_client

        # Execute disclosure
        parameters = {"channel_reference": "reddit:r/test:post/test123"}
        result = await service._tool_disclose_identity(parameters, correlation_id="test_correlation")

        # Get posted comment
        call_args = mock_reddit_api_client.submit_comment.call_args
        comment_text = call_args[0][0].text

        # Verify human oversight is mentioned
        assert (
            "human" in comment_text.lower()
            and ("moderator" in comment_text.lower() or "review" in comment_text.lower())
        ) or "mod team" in comment_text.lower()

    @pytest.mark.asyncio
    async def test_disclosure_contact_information(self, reddit_credentials, mock_reddit_api_client, mock_time_service):
        """Test that disclosure includes contact information."""
        service = RedditToolService(reddit_credentials, time_service=mock_time_service)
        service._client = mock_reddit_api_client

        # Execute disclosure
        parameters = {"channel_reference": "reddit:r/test:post/test123"}
        result = await service._tool_disclose_identity(parameters, correlation_id="test_correlation")

        # Get posted comment
        call_args = mock_reddit_api_client.submit_comment.call_args
        comment_text = call_args[0][0].text

        # Verify contact information present
        assert "ciris.ai" in comment_text  # Website
        assert "report" in comment_text.lower() or "contact" in comment_text.lower()  # How to reach out
