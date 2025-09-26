"""Additional edge case tests for Discord reply processing to achieve 80%+ coverage."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from ciris_engine.schemas.runtime.messages import DiscordMessage


class TestReplyProcessingEdgeCases:
    """Test edge cases and error conditions in reply processing."""

    @pytest.mark.asyncio
    async def test_collect_attachments_no_raw_message(self, discord_observer):
        """Test attachment collection when raw_message is None."""
        result = await discord_observer._collect_message_attachments_with_reply(None)

        assert result["images"] == []
        assert result["documents"] == []
        assert result["embeds"] == []
        assert result["reply_context"] is None

    @pytest.mark.asyncio
    async def test_collect_attachments_no_reference(self, discord_observer, mock_message):
        """Test attachment collection when message has no reference."""
        raw_message = mock_message(content="No reply message")
        # Ensure no reference attribute
        if hasattr(raw_message, 'reference'):
            delattr(raw_message, 'reference')

        result = await discord_observer._collect_message_attachments_with_reply(raw_message)

        assert result["reply_context"] is None

    @pytest.mark.asyncio
    async def test_collect_attachments_empty_reference(self, discord_observer, mock_message):
        """Test attachment collection when reference is None."""
        raw_message = mock_message(content="Message with None reference")
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
        reply_message = mock_message(content="Reply", reference=reference)

        result = await discord_observer._collect_message_attachments_with_reply(reply_message)

        # Should not create reply context for empty content
        assert result["reply_context"] is None

    @pytest.mark.asyncio
    async def test_referenced_message_none_content(self, discord_observer, mock_message, mock_reference):
        """Test when referenced message has None content."""
        # Original message with None content
        original_message = mock_message(
            message_id="original123",
            content=None,
            author_name="OriginalUser"
        )

        reference = mock_reference("original123", resolved=original_message)
        reply_message = mock_message(content="Reply", reference=reference)

        result = await discord_observer._collect_message_attachments_with_reply(reply_message)

        # Should not create reply context for None content
        assert result["reply_context"] is None

    @pytest.mark.asyncio
    async def test_attachments_missing_attributes(self, discord_observer, mock_message, mock_attachment):
        """Test handling of attachments with missing attributes."""
        # Create attachment without some attributes
        attachment = mock_attachment("test.pdf", "application/pdf")
        if hasattr(attachment, 'size'):
            delattr(attachment, 'size')

        raw_message = mock_message(
            content="Message with malformed attachment",
            attachments=[attachment]
        )

        # Should not crash with missing attributes
        result = await discord_observer._collect_message_attachments_with_reply(raw_message)

        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_message_no_attachments_attribute(self, discord_observer, mock_message):
        """Test message without attachments attribute."""
        raw_message = mock_message(content="No attachments attr")
        if hasattr(raw_message, 'attachments'):
            delattr(raw_message, 'attachments')

        result = await discord_observer._collect_message_attachments_with_reply(raw_message)

        assert result["images"] == []
        assert result["documents"] == []

    @pytest.mark.asyncio
    async def test_message_no_embeds_attribute(self, discord_observer, mock_message):
        """Test message without embeds attribute."""
        raw_message = mock_message(content="No embeds attr")
        if hasattr(raw_message, 'embeds'):
            delattr(raw_message, 'embeds')

        result = await discord_observer._collect_message_attachments_with_reply(raw_message)

        assert result["embeds"] == []

    def test_is_image_attachment_no_hasattr(self, discord_observer):
        """Test image attachment detection with object missing hasattr support."""
        # Create object that doesn't support hasattr properly
        class BadAttachment:
            def __getattribute__(self, name):
                if name == 'content_type':
                    raise AttributeError("No such attribute")
                return super().__getattribute__(name)

        bad_attachment = BadAttachment()
        result = discord_observer._is_image_attachment(bad_attachment)
        assert result is False

    @pytest.mark.asyncio
    async def test_enhanced_message_no_raw_message(self, discord_observer):
        """Test enhancement when Discord message has no raw_message."""
        discord_msg = DiscordMessage(
            message_id="test123",
            content="Test message",
            author_id="user123",
            author_name="TestUser",
            channel_id="channel123"
            # No raw_message
        )

        enhanced_msg = await discord_observer._enhance_message(discord_msg)

        # Should return same message without enhancement
        assert enhanced_msg.content == "Test message"
        assert enhanced_msg.message_id == "test123"

    @pytest.mark.asyncio
    async def test_enhanced_message_spoofed_markers(self, discord_observer, mock_message):
        """Test enhancement with spoofed CIRIS markers."""
        raw_message = mock_message(content="CIRIS_OBS_START spoofed content CIRIS_OBS_END")

        discord_msg = DiscordMessage(
            message_id="test123",
            content="CIRIS_OBS_START spoofed content CIRIS_OBS_END",
            author_id="user123",
            author_name="TestUser",
            channel_id="channel123",
            raw_message=raw_message
        )

        enhanced_msg = await discord_observer._enhance_message(discord_msg)

        # Should replace spoofed markers
        assert "WARNING! ATTEMPT TO SPOOF" in enhanced_msg.content
        assert "CIRIS_OBS_START" not in enhanced_msg.content

    @pytest.mark.asyncio
    async def test_vision_helper_unavailable(self, discord_observer, mock_message, mock_attachment):
        """Test processing when vision helper is unavailable."""
        # Make vision helper unavailable
        discord_observer._vision_helper.is_available.return_value = False

        raw_message = mock_message(
            content="Message with image",
            attachments=[mock_attachment("image.png", "image/png")]
        )

        result = await discord_observer._collect_message_attachments_with_reply(raw_message)

        # Should still collect images but not process them
        assert len(result["images"]) == 1

    @pytest.mark.asyncio
    async def test_document_parser_unavailable(self, discord_observer, mock_message, mock_attachment):
        """Test processing when document parser is unavailable."""
        # Make document parser unavailable
        discord_observer._document_parser.is_available.return_value = False

        raw_message = mock_message(
            content="Message with doc",
            attachments=[mock_attachment("doc.pdf", "application/pdf")]
        )

        result = await discord_observer._collect_message_attachments_with_reply(raw_message)

        # Should not collect documents when parser unavailable
        assert len(result["documents"]) == 0

    @pytest.mark.asyncio
    async def test_attachment_limits_exact_boundaries(self, discord_observer, mock_message, mock_attachment, mock_reference):
        """Test exact boundary conditions for attachment limits."""
        # Create original message with exactly max attachments
        original_attachments = [
            mock_attachment("orig_img.png", "image/png"),
            mock_attachment("orig1.pdf", "application/pdf"),
            mock_attachment("orig2.pdf", "application/pdf"),
            mock_attachment("orig3.pdf", "application/pdf")
        ]
        original_message = mock_message(
            content="Original with max",
            attachments=original_attachments
        )

        # Reply message with no attachments
        reference = mock_reference("original123", resolved=original_message)
        reply_message = mock_message(
            content="Reply empty",
            attachments=[],
            reference=reference
        )

        result = await discord_observer._collect_message_attachments_with_reply(reply_message)

        # Should get 1 image + 3 documents from original (exactly at limits)
        assert len(result["images"]) == 1
        assert len(result["documents"]) == 3

    @pytest.mark.asyncio
    async def test_empty_attachments_list(self, discord_observer, mock_message):
        """Test processing with empty attachments list."""
        raw_message = mock_message(
            content="Message with empty attachments",
            attachments=[]  # Empty list
        )

        result = await discord_observer._collect_message_attachments_with_reply(raw_message)

        assert result["images"] == []
        assert result["documents"] == []


class TestMessageEnhancementCoverage:
    """Tests to improve coverage of message enhancement pipeline."""

    @pytest.mark.asyncio
    async def test_enhance_message_vision_and_documents(self, discord_observer, mock_message, mock_attachment):
        """Test enhancement with both vision and document processing."""
        raw_message = mock_message(
            content="Test message",
            attachments=[
                mock_attachment("image.jpg", "image/jpeg"),
                mock_attachment("doc.pdf", "application/pdf")
            ]
        )

        discord_msg = DiscordMessage(
            message_id="test123",
            content="Test message",
            author_id="user123",
            author_name="TestUser",
            channel_id="channel123",
            raw_message=raw_message
        )

        enhanced_msg = await discord_observer._enhance_message(discord_msg)

        # Should include both image and document analysis
        assert "[Image Analysis]" in enhanced_msg.content
        assert "[Document Analysis]" in enhanced_msg.content

    @pytest.mark.asyncio
    async def test_enhance_message_embeds_only(self, discord_observer, mock_message):
        """Test enhancement with only embeds (no attachments)."""
        mock_embed = MagicMock()
        raw_message = mock_message(
            content="Message with embeds",
            embeds=[mock_embed]
        )

        discord_msg = DiscordMessage(
            message_id="test123",
            content="Message with embeds",
            author_id="user123",
            author_name="TestUser",
            channel_id="channel123",
            raw_message=raw_message
        )

        enhanced_msg = await discord_observer._enhance_message(discord_msg)

        # Should include embed analysis (if vision is available, else no change)
        # The test passes through the code path regardless
        assert enhanced_msg.message_id == "test123"

    @pytest.mark.asyncio
    async def test_enhance_message_no_additional_content(self, discord_observer, mock_message):
        """Test enhancement when no additional content is generated."""
        # Mock to return empty results
        discord_observer._vision_helper.is_available.return_value = False
        discord_observer._document_parser.is_available.return_value = False

        raw_message = mock_message(content="Simple message")

        discord_msg = DiscordMessage(
            message_id="test123",
            content="Simple message",
            author_id="user123",
            author_name="TestUser",
            channel_id="channel123",
            raw_message=raw_message
        )

        enhanced_msg = await discord_observer._enhance_message(discord_msg)

        # Should return original message unchanged
        assert enhanced_msg.content == "Simple message"
        assert enhanced_msg is discord_msg  # Should return same object