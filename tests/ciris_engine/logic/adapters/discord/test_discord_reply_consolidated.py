"""Consolidated tests for Discord reply processing with attachment inheritance and edge cases.

This file merges test_discord_reply_processing.py and test_discord_reply_edge_cases.py
for better test efficiency while maintaining comprehensive coverage.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from ciris_engine.schemas.runtime.messages import DiscordMessage


class TestReplyDetectionAndProcessing:
    """Test reply detection, context extraction, and basic processing."""

    @pytest.mark.asyncio
    async def test_non_reply_message_processing(self, discord_observer, mock_attachment_collection):
        """Test processing of a regular (non-reply) message."""
        from tests.ciris_engine.logic.adapters.discord.conftest import MockDiscordMessage

        # Create a regular message with attachments using enhanced fixtures
        raw_message = MockDiscordMessage(
            content="Regular message",
            attachments=[
                mock_attachment_collection["image_png"],
                mock_attachment_collection["document_pdf"]
            ]
        )

        result = await discord_observer._collect_message_attachments_with_reply(raw_message)

        assert result["reply_context"] is None
        assert len(result["images"]) == 1
        assert len(result["documents"]) == 1
        assert result["images"][0].filename == "image.png"
        assert result["documents"][0].filename == "doc.pdf"

    @pytest.mark.asyncio
    async def test_reply_message_with_resolved_reference(self, discord_observer, sample_reply_chain):
        """Test reply message with resolved reference using enhanced fixtures."""
        reply_message = sample_reply_chain["reply1"]

        result = await discord_observer._collect_message_attachments_with_reply(reply_message)

        assert result["reply_context"] is not None
        assert "Original message content" in result["reply_context"]
        assert "OriginalUser" in result["reply_context"]

    @pytest.mark.asyncio
    async def test_reply_message_with_unresolved_reference(self, discord_observer, mock_message, mock_reference):
        """Test reply message where reference needs to be fetched."""
        # Create reply with unresolved reference
        reference = mock_reference("original123", resolved=None)
        reply_message = mock_message(
            content="Reply content",
            reference=reference
        )

        # Mock the fetch behavior
        original_message = mock_message(
            message_id="original123",
            content="Fetched original content",
            author_name="FetchedUser"
        )
        reply_message.reference.resolved = MagicMock()
        reply_message.reference.resolved.fetch = AsyncMock(return_value=original_message)

        result = await discord_observer._collect_message_attachments_with_reply(reply_message)

        # Should attempt to fetch the original message
        assert result["reply_context"] is not None

    @pytest.mark.asyncio
    async def test_reply_message_fetch_failure(self, discord_observer, mock_message, mock_reference):
        """Test graceful handling when fetching referenced message fails."""
        # Mock channel to raise exception when fetching
        mock_channel = MagicMock()
        mock_channel.fetch_message = AsyncMock(side_effect=Exception("Fetch failed"))

        reference = mock_reference("original123", resolved=None)
        reply_message = mock_message(content="Reply content", reference=reference)
        reply_message.channel = mock_channel

        result = await discord_observer._collect_message_attachments_with_reply(reply_message)

        # Should handle gracefully
        assert result["reply_context"] is None


class TestAttachmentPriorityAndLimits:
    """Test attachment priority rules and limits."""

    @pytest.mark.asyncio
    async def test_reply_wins_single_image_limit(self, discord_observer, mock_attachment_collection):
        """Test 'Reply wins' rule - reply image takes precedence over original."""
        from tests.ciris_engine.logic.adapters.discord.conftest import MockDiscordMessage, MockDiscordReference

        # Original message with image
        original = MockDiscordMessage(
            message_id="original123",
            content="Original with image",
            attachments=[mock_attachment_collection["image_png"]]
        )

        # Reply message with different image
        reference = MockDiscordReference("original123", resolved=original)
        reply = MockDiscordMessage(
            content="Reply with image",
            reference=reference,
            attachments=[mock_attachment_collection["image_jpg"]]
        )

        result = await discord_observer._collect_message_attachments_with_reply(reply)

        # Should only have reply image (reply wins)
        assert len(result["images"]) == 1
        assert result["images"][0].filename == "photo.jpg"  # From reply, not original

    @pytest.mark.asyncio
    async def test_original_image_when_reply_has_none(self, discord_observer, mock_attachment_collection):
        """Test original image is used when reply has no images."""
        from tests.ciris_engine.logic.adapters.discord.conftest import MockDiscordMessage, MockDiscordReference

        # Original message with image
        original = MockDiscordMessage(
            attachments=[mock_attachment_collection["image_png"]]
        )

        # Reply message with no images
        reference = MockDiscordReference("original123", resolved=original)
        reply = MockDiscordMessage(content="Reply without image", reference=reference)

        result = await discord_observer._collect_message_attachments_with_reply(reply)

        # Should have original image
        assert len(result["images"]) == 1
        assert result["images"][0].filename == "image.png"

    @pytest.mark.asyncio
    async def test_document_limit_three_total(self, discord_observer, mock_attachment_collection):
        """Test maximum of 3 documents total across reply and original."""
        from tests.ciris_engine.logic.adapters.discord.conftest import MockDiscordMessage, MockDiscordReference

        # Original message with 2 documents
        original = MockDiscordMessage(
            attachments=[
                mock_attachment_collection["document_pdf"],
                mock_attachment_collection["document_docx"]
            ]
        )

        # Reply message with 2 more documents
        reference = MockDiscordReference("original123", resolved=original)
        reply = MockDiscordMessage(
            reference=reference,
            attachments=[
                mock_attachment_collection["document_pdf"],  # Different instance
                mock_attachment_collection["document_docx"]  # Different instance
            ]
        )

        result = await discord_observer._collect_message_attachments_with_reply(reply)

        # Should be limited to 3 total documents (reply takes priority)
        assert len(result["documents"]) == 3


class TestEdgeCasesAndErrorHandling:
    """Test edge cases and error conditions."""

    @pytest.mark.asyncio
    async def test_collect_attachments_no_raw_message(self, discord_observer):
        """Test attachment collection when raw_message is None."""
        result = await discord_observer._collect_message_attachments_with_reply(None)

        assert result["images"] == []
        assert result["documents"] == []
        assert result["embeds"] == []
        assert result["reply_context"] is None

    @pytest.mark.asyncio
    async def test_collect_attachments_no_reference(self, discord_observer):
        """Test attachment collection when message has no reference."""
        from tests.ciris_engine.logic.adapters.discord.conftest import MockDiscordMessage

        raw_message = MockDiscordMessage(content="No reply message")
        # Ensure no reference attribute
        if hasattr(raw_message, 'reference'):
            delattr(raw_message, 'reference')

        result = await discord_observer._collect_message_attachments_with_reply(raw_message)

        assert result["reply_context"] is None

    @pytest.mark.asyncio
    async def test_collect_attachments_empty_reference(self, discord_observer):
        """Test attachment collection when reference is None."""
        from tests.ciris_engine.logic.adapters.discord.conftest import MockDiscordMessage

        raw_message = MockDiscordMessage(content="Message with None reference")
        raw_message.reference = None

        result = await discord_observer._collect_message_attachments_with_reply(raw_message)

        assert result["reply_context"] is None

    @pytest.mark.asyncio
    async def test_referenced_message_no_content(self, discord_observer, mock_message, mock_reference):
        """Test when referenced message has no content."""
        # Original message with empty content
        original_message = mock_message(
            message_id="original123",
            content="",  # Empty content
            author_name="OriginalUser"
        )

        reference = mock_reference("original123", resolved=original_message)
        reply_message = mock_message(content="Reply content", reference=reference)

        result = await discord_observer._collect_message_attachments_with_reply(reply_message)

        # Should not create reply context for empty content (per implementation logic)
        assert result["reply_context"] is None

    @pytest.mark.asyncio
    async def test_attachments_missing_attributes(self, discord_observer):
        """Test handling of malformed attachments."""
        from tests.ciris_engine.logic.adapters.discord.conftest import MockDiscordMessage

        # Create attachment missing required attributes
        malformed_attachment = MagicMock()
        malformed_attachment.filename = "test.png"
        # Missing content_type attribute

        raw_message = MockDiscordMessage(
            content="Message with malformed attachment",
            attachments=[malformed_attachment]
        )

        # Should not crash
        result = await discord_observer._collect_message_attachments_with_reply(raw_message)

        # Malformed attachments should be filtered out
        assert result["images"] == []

    @pytest.mark.asyncio
    async def test_vision_helper_unavailable(self, discord_observer, mock_attachment_collection):
        """Test behavior when vision helper is unavailable."""
        from ciris_engine.schemas.runtime.messages import DiscordMessage

        # Disable vision helper
        discord_observer._vision_helper.is_available.return_value = False

        discord_msg = DiscordMessage(
            message_id="msg123",
            content="Message with image",
            author_name="TestUser",
            author_id="user123",
            channel_id="channel123",
            raw_message=MagicMock()
        )

        enhanced_message = await discord_observer._enhance_message(discord_msg)

        # Should handle gracefully without vision processing
        assert enhanced_message is not None

    @pytest.mark.asyncio
    async def test_document_parser_unavailable(self, discord_observer, mock_attachment_collection):
        """Test behavior when document parser is unavailable."""
        from ciris_engine.schemas.runtime.messages import DiscordMessage

        # Disable document parser
        discord_observer._document_parser.is_available.return_value = False

        discord_msg = DiscordMessage(
            message_id="msg123",
            content="Message with document",
            author_name="TestUser",
            author_id="user123",
            channel_id="channel123",
            raw_message=MagicMock()
        )

        enhanced_message = await discord_observer._enhance_message(discord_msg)

        # Should handle gracefully without document processing
        assert enhanced_message is not None


class TestImageAttachmentDetection:
    """Test image attachment detection logic."""

    @pytest.mark.asyncio
    async def test_is_image_attachment_valid_types(self, discord_observer, mock_attachment_collection):
        """Test image detection for valid image types."""
        # Test various valid image types
        valid_images = [
            mock_attachment_collection["image_png"],
            mock_attachment_collection["image_jpg"]
        ]

        for attachment in valid_images:
            is_image = discord_observer._is_image_attachment(attachment)
            assert is_image, f"Should detect {attachment.content_type} as image"

    @pytest.mark.asyncio
    async def test_is_image_attachment_invalid_types(self, discord_observer, mock_attachment_collection):
        """Test image detection for non-image types."""
        # Test non-image types
        non_images = [
            mock_attachment_collection["document_pdf"],
            mock_attachment_collection["other_txt"]
        ]

        for attachment in non_images:
            is_image = discord_observer._is_image_attachment(attachment)
            assert not is_image, f"Should not detect {attachment.content_type} as image"

    @pytest.mark.asyncio
    async def test_is_image_attachment_missing_content_type(self, discord_observer):
        """Test image detection with missing content_type."""
        attachment = MagicMock()
        attachment.filename = "test.png"
        # Missing content_type

        is_image = discord_observer._is_image_attachment(attachment)
        assert not is_image


class TestMessageEnhancement:
    """Test comprehensive message enhancement with attachments."""

    @pytest.mark.asyncio
    async def test_enhanced_message_with_reply_context(self, discord_observer, sample_reply_chain):
        """Test message enhancement includes reply context."""
        from ciris_engine.schemas.runtime.messages import DiscordMessage
        from unittest.mock import patch

        reply = sample_reply_chain["reply1"]

        discord_msg = DiscordMessage(
            message_id="reply123",
            content="Reply message",
            author_name="ReplyUser",
            author_id="user123",
            channel_id="channel123",
            raw_message=reply
        )

        # Mock the collection method to return reply context
        with patch.object(
            discord_observer,
            '_collect_message_attachments_with_reply',
            return_value={
                "images": [],
                "documents": [],
                "embeds": [],
                "reply_context": "@OriginalUser: Original message content"
            }
        ):
            enhanced = await discord_observer._enhance_message(discord_msg)

        # Should include reply context
        assert "[Reply Context]" in enhanced.content
        assert "@OriginalUser: Original message content" in enhanced.content

    @pytest.mark.asyncio
    async def test_enhanced_message_with_attachments_and_reply(self, discord_observer, mock_attachment_collection):
        """Test message enhancement with both attachments and reply context."""
        from ciris_engine.schemas.runtime.messages import DiscordMessage
        from unittest.mock import patch

        discord_msg = DiscordMessage(
            message_id="reply123",
            content="Reply message",
            author_name="ReplyUser",
            author_id="user123",
            channel_id="channel123",
            raw_message=MagicMock()
        )

        # Mock the collection method to return both attachments and reply context
        with patch.object(
            discord_observer,
            '_collect_message_attachments_with_reply',
            return_value={
                "images": [mock_attachment_collection["image_png"]],
                "documents": [mock_attachment_collection["document_pdf"]],
                "embeds": [],
                "reply_context": "@OriginalUser: Original message"
            }
        ):
            enhanced = await discord_observer._enhance_message(discord_msg)

        # Should include both image analysis and reply context
        assert "[Image Analysis]" in enhanced.content or "[Vision Analysis]" in enhanced.content
        assert "[Reply Context]" in enhanced.content

    @pytest.mark.asyncio
    async def test_enhanced_message_processing_error(self, discord_observer, sample_reply_chain):
        """Test graceful error handling during message enhancement."""
        from ciris_engine.schemas.runtime.messages import DiscordMessage
        from unittest.mock import patch

        reply = sample_reply_chain["reply1"]

        discord_msg = DiscordMessage(
            message_id="reply123",
            content="Reply message",
            author_name="ReplyUser",
            author_id="user123",
            channel_id="channel123",
            raw_message=reply
        )

        # Mock to raise exception
        with patch.object(
            discord_observer,
            '_collect_message_attachments_with_reply',
            side_effect=Exception("Processing failed")
        ):
            enhanced = await discord_observer._enhance_message(discord_msg)

        # Should include error message
        assert "[Attachment Processing Error: Processing failed]" in enhanced.content


class TestAttachmentLimitsAndBoundaries:
    """Test attachment limit enforcement and boundary conditions."""

    @pytest.mark.asyncio
    async def test_attachment_limits_exact_boundaries(self, discord_observer, mock_attachment_collection):
        """Test exact boundary conditions for attachment limits."""
        from tests.ciris_engine.logic.adapters.discord.conftest import MockDiscordMessage

        # Test with exactly 1 image and 3 documents (at limits)
        raw_message = MockDiscordMessage(
            content="Message at limits",
            attachments=[
                mock_attachment_collection["image_png"],  # 1 image (limit)
                mock_attachment_collection["document_pdf"],  # 3 documents
                mock_attachment_collection["document_docx"],
                mock_attachment_collection["document_pdf"]  # Different instance
            ]
        )

        result = await discord_observer._collect_message_attachments_with_reply(raw_message)

        assert len(result["images"]) == 1
        assert len(result["documents"]) == 3

    @pytest.mark.asyncio
    async def test_empty_attachments_list(self, discord_observer):
        """Test handling of empty attachments list."""
        from tests.ciris_engine.logic.adapters.discord.conftest import MockDiscordMessage

        raw_message = MockDiscordMessage(
            content="Message with no attachments",
            attachments=[]
        )

        result = await discord_observer._collect_message_attachments_with_reply(raw_message)

        assert result["images"] == []
        assert result["documents"] == []
        assert result["embeds"] == []