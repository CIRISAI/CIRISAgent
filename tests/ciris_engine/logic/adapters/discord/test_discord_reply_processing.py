"""Tests for Discord reply processing with attachment inheritance and priority rules."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from ciris_engine.schemas.runtime.messages import DiscordMessage


class TestReplyDetection:
    """Test reply detection and context extraction."""

    @pytest.mark.asyncio
    async def test_non_reply_message_processing(self, discord_observer, mock_message, mock_attachment):
        """Test processing of a regular (non-reply) message."""
        # Create a regular message with attachments
        raw_message = mock_message(
            content="Regular message",
            attachments=[
                mock_attachment("image.png", "image/png"),
                mock_attachment("doc.pdf", "application/pdf")
            ]
        )

        result = await discord_observer._collect_message_attachments_with_reply(raw_message)

        assert result["reply_context"] is None
        assert len(result["images"]) == 1
        assert len(result["documents"]) == 1
        assert result["images"][0].filename == "image.png"
        assert result["documents"][0].filename == "doc.pdf"

    @pytest.mark.asyncio
    async def test_reply_message_with_resolved_reference(self, discord_observer, mock_message, mock_reference):
        """Test reply message with resolved reference."""
        # Create referenced (original) message
        original_message = mock_message(
            message_id="original123",
            content="Original message content",
            author_name="OriginalUser"
        )

        # Create reply message with reference
        reference = mock_reference("original123", resolved=original_message)
        reply_message = mock_message(
            content="Reply content",
            author_name="ReplyUser",
            reference=reference
        )

        result = await discord_observer._collect_message_attachments_with_reply(reply_message)

        assert result["reply_context"] == "@OriginalUser: Original message content"

    @pytest.mark.asyncio
    async def test_reply_message_with_unresolved_reference(self, discord_observer, mock_message, mock_reference):
        """Test reply message with unresolved reference that needs fetching."""
        # Create referenced (original) message
        original_message = mock_message(
            message_id="original123",
            content="Fetched original content",
            author_name="OriginalUser"
        )

        # Mock channel to return the original message when fetched
        mock_channel = MagicMock()
        mock_channel.fetch_message = AsyncMock(return_value=original_message)

        # Create reply message with unresolved reference
        reference = mock_reference("original123", resolved=None)
        reply_message = mock_message(
            content="Reply content",
            reference=reference,
            channel=mock_channel
        )

        result = await discord_observer._collect_message_attachments_with_reply(reply_message)

        assert result["reply_context"] == "@OriginalUser: Fetched original content"
        mock_channel.fetch_message.assert_called_once_with("original123")

    @pytest.mark.asyncio
    async def test_reply_message_fetch_failure(self, discord_observer, mock_message, mock_reference):
        """Test reply message when fetching referenced message fails."""
        # Mock channel to raise exception when fetching
        mock_channel = MagicMock()
        mock_channel.fetch_message = AsyncMock(side_effect=Exception("Fetch failed"))

        # Create reply message with unresolved reference
        reference = mock_reference("original123", resolved=None)
        reply_message = mock_message(
            content="Reply content",
            reference=reference,
            channel=mock_channel
        )

        result = await discord_observer._collect_message_attachments_with_reply(reply_message)

        assert result["reply_context"] is None  # Should be None when fetch fails


class TestAttachmentPriorityRules:
    """Test attachment priority rules between reply and original message."""

    @pytest.mark.asyncio
    async def test_reply_wins_single_image_limit(self, discord_observer, mock_message, mock_attachment, mock_reference):
        """Test that reply message wins when both have images (1 image max)."""
        # Original message with image
        original_message = mock_message(
            content="Original with image",
            attachments=[mock_attachment("original.jpg", "image/jpeg")]
        )

        # Reply message with image (should win)
        reference = mock_reference("original123", resolved=original_message)
        reply_message = mock_message(
            content="Reply with image",
            attachments=[mock_attachment("reply.png", "image/png")],
            reference=reference
        )

        result = await discord_observer._collect_message_attachments_with_reply(reply_message)

        # Reply image should be chosen
        assert len(result["images"]) == 1
        assert result["images"][0].filename == "reply.png"

    @pytest.mark.asyncio
    async def test_original_image_when_reply_has_none(self, discord_observer, mock_message, mock_attachment, mock_reference):
        """Test that original message image is used when reply has no image."""
        # Original message with image
        original_message = mock_message(
            content="Original with image",
            attachments=[mock_attachment("original.jpg", "image/jpeg")]
        )

        # Reply message with no images
        reference = mock_reference("original123", resolved=original_message)
        reply_message = mock_message(
            content="Reply with no image",
            attachments=[mock_attachment("doc.pdf", "application/pdf")],
            reference=reference
        )

        result = await discord_observer._collect_message_attachments_with_reply(reply_message)

        # Original image should be chosen since reply has none
        assert len(result["images"]) == 1
        assert result["images"][0].filename == "original.jpg"

    @pytest.mark.asyncio
    async def test_document_limit_three_total(self, discord_observer, mock_message, mock_attachment, mock_reference):
        """Test 3 document limit across both messages with reply priority."""
        # Original message with 2 documents
        original_message = mock_message(
            content="Original with docs",
            attachments=[
                mock_attachment("original1.pdf", "application/pdf"),
                mock_attachment("original2.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
            ]
        )

        # Reply message with 2 documents (should get priority)
        reference = mock_reference("original123", resolved=original_message)
        reply_message = mock_message(
            content="Reply with docs",
            attachments=[
                mock_attachment("reply1.pdf", "application/pdf"),
                mock_attachment("reply2.pdf", "application/pdf")
            ],
            reference=reference
        )

        result = await discord_observer._collect_message_attachments_with_reply(reply_message)

        # Should have 3 documents total: 2 from reply (priority) + 1 from original
        assert len(result["documents"]) == 3
        filenames = [doc.filename for doc in result["documents"]]
        assert "reply1.pdf" in filenames
        assert "reply2.pdf" in filenames
        assert "original1.pdf" in filenames  # First original doc fits in limit
        assert "original2.docx" not in filenames  # Second original doc exceeds limit

    @pytest.mark.asyncio
    async def test_reply_with_max_attachments_blocks_original(self, discord_observer, mock_message, mock_attachment, mock_reference):
        """Test that when reply has max attachments, original gets only text."""
        # Original message with image and documents
        original_message = mock_message(
            content="Original content",
            attachments=[
                mock_attachment("original.jpg", "image/jpeg"),
                mock_attachment("original.pdf", "application/pdf")
            ]
        )

        # Reply message with 1 image and 3 documents (max limits)
        reference = mock_reference("original123", resolved=original_message)
        reply_message = mock_message(
            content="Reply content",
            attachments=[
                mock_attachment("reply.png", "image/png"),
                mock_attachment("reply1.pdf", "application/pdf"),
                mock_attachment("reply2.pdf", "application/pdf"),
                mock_attachment("reply3.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
            ],
            reference=reference
        )

        result = await discord_observer._collect_message_attachments_with_reply(reply_message)

        # Only reply attachments should be included due to limits
        assert len(result["images"]) == 1
        assert len(result["documents"]) == 3
        assert result["images"][0].filename == "reply.png"

        # Original message content should still be included as context
        assert result["reply_context"] == "@TestUser: Original content"


class TestImageAttachmentDetection:
    """Test image attachment detection logic."""

    def test_is_image_attachment_valid_types(self, discord_observer, mock_attachment):
        """Test detection of valid image types."""
        valid_image_types = [
            "image/png", "image/jpeg", "image/jpg", "image/gif",
            "image/webp", "image/svg+xml", "image/bmp"
        ]

        for content_type in valid_image_types:
            attachment = mock_attachment("test.jpg", content_type)
            assert discord_observer._is_image_attachment(attachment) is True

    def test_is_image_attachment_invalid_types(self, discord_observer, mock_attachment):
        """Test rejection of non-image types."""
        invalid_types = [
            "application/pdf", "text/plain", "video/mp4",
            "audio/mp3", "application/json", None
        ]

        for content_type in invalid_types:
            attachment = mock_attachment("test.file", content_type)
            assert discord_observer._is_image_attachment(attachment) is False

    def test_is_image_attachment_missing_content_type(self, discord_observer):
        """Test attachment without content_type attribute."""
        attachment = MagicMock()
        attachment.filename = "test.jpg"
        # No content_type attribute
        delattr(attachment, 'content_type') if hasattr(attachment, 'content_type') else None

        assert discord_observer._is_image_attachment(attachment) is False


class TestFullMessageEnhancement:
    """Test the full message enhancement pipeline with replies."""

    @pytest.mark.asyncio
    async def test_enhanced_message_with_reply_context(self, discord_observer, mock_message, mock_reference):
        """Test full message enhancement including reply context."""
        # Original message
        original_message = mock_message(
            content="Original message",
            author_name="OriginalUser"
        )

        # Reply message
        reference = mock_reference("original123", resolved=original_message)
        raw_message = mock_message(
            content="Reply message",
            reference=reference
        )

        # Create Discord message
        discord_msg = DiscordMessage(
            message_id="reply123",
            content="Reply message",
            author_id="user123",
            author_name="ReplyUser",
            channel_id="channel123",
            raw_message=raw_message
        )

        # Mock the attachment collection to return reply context
        with patch.object(
            discord_observer,
            '_collect_message_attachments_with_reply',
            return_value={
                "images": [],
                "documents": [],
                "embeds": [],
                "reply_context": "@OriginalUser: Original message"
            }
        ):
            enhanced_msg = await discord_observer._enhance_message(discord_msg)

        # Should include reply context
        assert "[Reply Context]" in enhanced_msg.content
        assert "@OriginalUser: Original message" in enhanced_msg.content

    @pytest.mark.asyncio
    async def test_enhanced_message_with_attachments_and_reply(self, discord_observer, mock_message, mock_attachment, mock_reference):
        """Test full enhancement with both attachments and reply context."""
        # Original message
        original_message = mock_message(
            content="Original with context",
            author_name="OriginalUser"
        )

        # Reply message with attachments
        reference = mock_reference("original123", resolved=original_message)
        raw_message = mock_message(
            content="Reply with attachments",
            attachments=[mock_attachment("image.png", "image/png")],
            reference=reference
        )

        # Create Discord message
        discord_msg = DiscordMessage(
            message_id="reply123",
            content="Reply with attachments",
            author_id="user123",
            author_name="ReplyUser",
            channel_id="channel123",
            raw_message=raw_message
        )

        enhanced_msg = await discord_observer._enhance_message(discord_msg)

        # Should include both image analysis and reply context
        assert "[Image Analysis]" in enhanced_msg.content
        assert "[Reply Context]" in enhanced_msg.content
        assert "@OriginalUser: Original with context" in enhanced_msg.content

    @pytest.mark.asyncio
    async def test_enhanced_message_processing_error(self, discord_observer, mock_message):
        """Test error handling in message enhancement."""
        # Mock the attachment collection to raise an error
        raw_message = mock_message(content="Test message")

        discord_msg = DiscordMessage(
            message_id="test123",
            content="Test message",
            author_id="user123",
            author_name="TestUser",
            channel_id="channel123",
            raw_message=raw_message
        )

        with patch.object(
            discord_observer,
            '_collect_message_attachments_with_reply',
            side_effect=Exception("Processing failed")
        ):
            enhanced_msg = await discord_observer._enhance_message(discord_msg)

        # Should include error message
        assert "[Attachment Processing Error: Processing failed]" in enhanced_msg.content