"""
Coverage-focused tests for Discord observer helper functions.

Targets helper functions extracted from high-complexity methods:
- _fetch_referenced_message
- _build_reply_context
- _build_message_processing_order
- _process_message_attachments
- _process_image_attachments
- _process_document_attachments
"""

import pytest
from unittest.mock import AsyncMock, Mock, patch
import discord

from ciris_engine.logic.adapters.discord.discord_observer import DiscordObserver


class TestDiscordObserverHelperCoverage:
    """Coverage-focused tests for Discord observer helper functions."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_filter_service = Mock()
        self.mock_communication_service = Mock()
        self.mock_document_parser = Mock()
        self.mock_document_parser.is_available.return_value = True
        self.mock_document_parser._is_document_attachment.return_value = True

        self.observer = DiscordObserver(
            filter_service=self.mock_filter_service,
            communication_service=self.mock_communication_service
        )
        self.observer._document_parser = self.mock_document_parser

    @pytest.mark.asyncio
    async def test_fetch_referenced_message_no_reference(self):
        """Test _fetch_referenced_message when message has no reference."""
        mock_message = Mock()
        mock_message.reference = None

        result = await self.observer._fetch_referenced_message(mock_message)

        assert result is None

    @pytest.mark.asyncio
    async def test_fetch_referenced_message_no_reference_attr(self):
        """Test _fetch_referenced_message when message has no reference attribute."""
        mock_message = Mock(spec=[])  # No reference attribute

        result = await self.observer._fetch_referenced_message(mock_message)

        assert result is None

    @pytest.mark.asyncio
    async def test_fetch_referenced_message_resolved_available(self):
        """Test _fetch_referenced_message when resolved message is available."""
        mock_resolved_message = Mock()
        mock_reference = Mock()
        mock_reference.resolved = mock_resolved_message

        mock_message = Mock()
        mock_message.reference = mock_reference

        result = await self.observer._fetch_referenced_message(mock_message)

        assert result == mock_resolved_message

    @pytest.mark.asyncio
    async def test_fetch_referenced_message_fetch_manually(self):
        """Test _fetch_referenced_message when need to fetch manually."""
        mock_channel = Mock()
        mock_fetched_message = Mock()
        mock_channel.fetch_message = AsyncMock(return_value=mock_fetched_message)

        mock_reference = Mock()
        mock_reference.resolved = None
        mock_reference.message_id = 123456789

        mock_message = Mock()
        mock_message.reference = mock_reference
        mock_message.channel = mock_channel

        result = await self.observer._fetch_referenced_message(mock_message)

        assert result == mock_fetched_message
        mock_channel.fetch_message.assert_called_once_with(123456789)

    @pytest.mark.asyncio
    async def test_fetch_referenced_message_fetch_exception(self):
        """Test _fetch_referenced_message when fetch raises exception."""
        mock_channel = Mock()
        mock_channel.fetch_message = AsyncMock(side_effect=Exception("Fetch failed"))

        mock_reference = Mock()
        mock_reference.resolved = None
        mock_reference.message_id = 123456789

        mock_message = Mock()
        mock_message.reference = mock_reference
        mock_message.channel = mock_channel

        result = await self.observer._fetch_referenced_message(mock_message)

        assert result is None

    def test_build_reply_context_success(self):
        """Test _build_reply_context with valid referenced message."""
        mock_author = Mock()
        mock_author.display_name = "TestUser"

        mock_referenced_message = Mock()
        mock_referenced_message.content = "This is the original message"
        mock_referenced_message.author = mock_author

        result = self.observer._build_reply_context(mock_referenced_message)

        assert result == "@TestUser: This is the original message"

    def test_build_reply_context_no_message(self):
        """Test _build_reply_context with None message."""
        result = self.observer._build_reply_context(None)

        assert result is None

    def test_build_reply_context_no_content(self):
        """Test _build_reply_context with message that has no content."""
        mock_referenced_message = Mock()
        mock_referenced_message.content = None

        result = self.observer._build_reply_context(mock_referenced_message)

        assert result is None

    def test_build_reply_context_empty_content(self):
        """Test _build_reply_context with message that has empty content."""
        mock_referenced_message = Mock()
        mock_referenced_message.content = ""

        result = self.observer._build_reply_context(mock_referenced_message)

        assert result is None

    def test_build_reply_context_fallback_author_name(self):
        """Test _build_reply_context with author that has no display_name."""
        mock_author = Mock(spec=[])  # No display_name attribute

        mock_referenced_message = Mock()
        mock_referenced_message.content = "Test message"
        mock_referenced_message.author = mock_author

        result = self.observer._build_reply_context(mock_referenced_message)

        assert result == "@Unknown: Test message"

    def test_build_message_processing_order_both_messages(self):
        """Test _build_message_processing_order with both messages."""
        mock_raw_message = Mock()
        mock_referenced_message = Mock()

        result = self.observer._build_message_processing_order(mock_raw_message, mock_referenced_message)

        assert len(result) == 2
        assert result[0] == ("reply", mock_raw_message)
        assert result[1] == ("original", mock_referenced_message)

    def test_build_message_processing_order_only_raw_message(self):
        """Test _build_message_processing_order with only raw message."""
        mock_raw_message = Mock()

        result = self.observer._build_message_processing_order(mock_raw_message, None)

        assert len(result) == 1
        assert result[0] == ("reply", mock_raw_message)

    def test_build_message_processing_order_only_referenced_message(self):
        """Test _build_message_processing_order with only referenced message."""
        mock_referenced_message = Mock()

        result = self.observer._build_message_processing_order(None, mock_referenced_message)

        assert len(result) == 1
        assert result[0] == ("original", mock_referenced_message)

    def test_build_message_processing_order_no_messages(self):
        """Test _build_message_processing_order with no messages."""
        result = self.observer._build_message_processing_order(None, None)

        assert len(result) == 0

    def test_process_message_attachments_complete_flow(self):
        """Test _process_message_attachments with complete message flow."""
        # Mock image attachment
        mock_image_attachment = Mock()
        mock_image_attachment.content_type = "image/png"

        # Mock document attachment
        mock_doc_attachment = Mock()

        # Mock message with attachments
        mock_message = Mock()
        mock_message.attachments = [mock_image_attachment, mock_doc_attachment]
        mock_message.embeds = [Mock(), Mock()]  # 2 embeds

        messages_to_process = [("reply", mock_message)]
        result = {
            "images": [],
            "documents": [],
            "embeds": [],
            "reply_context": None
        }

        # Mock helper methods - make sure only the doc attachment is treated as document
        def mock_is_image(attachment):
            return attachment == mock_image_attachment

        def mock_is_document(attachment):
            return attachment == mock_doc_attachment

        self.observer._is_image_attachment = mock_is_image
        self.observer._document_parser._is_document_attachment = mock_is_document

        self.observer._process_message_attachments(messages_to_process, result)

        # Should have processed images, documents, and embeds
        assert len(result["images"]) == 1
        assert len(result["documents"]) == 1  # Only the non-image attachment
        assert len(result["embeds"]) == 2

    def test_process_message_attachments_skip_none_message(self):
        """Test _process_message_attachments skips None messages."""
        messages_to_process = [("reply", None), ("original", None)]
        result = {
            "images": [],
            "documents": [],
            "embeds": [],
            "reply_context": None
        }

        self.observer._process_message_attachments(messages_to_process, result)

        # Should remain empty
        assert len(result["images"]) == 0
        assert len(result["documents"]) == 0
        assert len(result["embeds"]) == 0

    def test_process_message_attachments_embeds_only_from_reply(self):
        """Test _process_message_attachments only processes embeds from reply."""
        mock_reply_message = Mock()
        mock_reply_message.attachments = []
        mock_reply_message.embeds = [Mock()]

        mock_original_message = Mock()
        mock_original_message.attachments = []
        mock_original_message.embeds = [Mock(), Mock()]  # Should be ignored

        messages_to_process = [
            ("reply", mock_reply_message),
            ("original", mock_original_message)
        ]
        result = {
            "images": [],
            "documents": [],
            "embeds": [],
            "reply_context": None
        }

        self.observer._process_message_attachments(messages_to_process, result)

        # Should only have embeds from reply message
        assert len(result["embeds"]) == 1

    def test_process_image_attachments_success(self):
        """Test _process_image_attachments adds images up to limit."""
        mock_attachment1 = Mock()
        mock_attachment2 = Mock()

        mock_message = Mock()
        mock_message.attachments = [mock_attachment1, mock_attachment2]

        images_list = []
        self.observer._is_image_attachment = Mock(return_value=True)

        result = self.observer._process_image_attachments(mock_message, images_list, 0)

        assert result == 1  # Only 1 image added due to limit
        assert len(images_list) == 1
        assert images_list[0] == mock_attachment1

    def test_process_image_attachments_at_limit(self):
        """Test _process_image_attachments when already at limit."""
        mock_message = Mock()
        mock_message.attachments = [Mock()]

        images_list = []

        result = self.observer._process_image_attachments(mock_message, images_list, 1)

        assert result == 0  # No images added
        assert len(images_list) == 0

    def test_process_image_attachments_no_attachments(self):
        """Test _process_image_attachments when message has no attachments."""
        mock_message = Mock()
        mock_message.attachments = []

        images_list = []

        result = self.observer._process_image_attachments(mock_message, images_list, 0)

        assert result == 0
        assert len(images_list) == 0

    def test_process_image_attachments_no_attachments_attr(self):
        """Test _process_image_attachments when message has no attachments attribute."""
        mock_message = Mock(spec=[])  # No attachments attribute

        images_list = []

        result = self.observer._process_image_attachments(mock_message, images_list, 0)

        assert result == 0
        assert len(images_list) == 0

    def test_process_image_attachments_not_images(self):
        """Test _process_image_attachments when attachments are not images."""
        mock_attachment = Mock()

        mock_message = Mock()
        mock_message.attachments = [mock_attachment]

        images_list = []
        self.observer._is_image_attachment = Mock(return_value=False)

        result = self.observer._process_image_attachments(mock_message, images_list, 0)

        assert result == 0
        assert len(images_list) == 0

    def test_process_document_attachments_success(self):
        """Test _process_document_attachments adds documents up to limit."""
        mock_attachment1 = Mock()
        mock_attachment2 = Mock()
        mock_attachment3 = Mock()
        mock_attachment4 = Mock()

        mock_message = Mock()
        mock_message.attachments = [mock_attachment1, mock_attachment2, mock_attachment3, mock_attachment4]

        documents_list = []

        result = self.observer._process_document_attachments(mock_message, documents_list, 0)

        assert result == 3  # Only 3 documents added due to limit
        assert len(documents_list) == 3

    def test_process_document_attachments_at_limit(self):
        """Test _process_document_attachments when already at limit."""
        mock_message = Mock()
        mock_message.attachments = [Mock()]

        documents_list = []

        result = self.observer._process_document_attachments(mock_message, documents_list, 3)

        assert result == 0  # No documents added
        assert len(documents_list) == 0

    def test_process_document_attachments_parser_not_available(self):
        """Test _process_document_attachments when document parser not available."""
        self.mock_document_parser.is_available.return_value = False

        mock_message = Mock()
        mock_message.attachments = [Mock()]

        documents_list = []

        result = self.observer._process_document_attachments(mock_message, documents_list, 0)

        assert result == 0
        assert len(documents_list) == 0

    def test_process_document_attachments_not_documents(self):
        """Test _process_document_attachments when attachments are not documents."""
        self.mock_document_parser._is_document_attachment.return_value = False

        mock_attachment = Mock()
        mock_message = Mock()
        mock_message.attachments = [mock_attachment]

        documents_list = []

        result = self.observer._process_document_attachments(mock_message, documents_list, 0)

        assert result == 0
        assert len(documents_list) == 0

    def test_process_document_attachments_no_attachments(self):
        """Test _process_document_attachments when message has no attachments."""
        mock_message = Mock()
        mock_message.attachments = []

        documents_list = []

        result = self.observer._process_document_attachments(mock_message, documents_list, 0)

        assert result == 0
        assert len(documents_list) == 0


class TestDiscordObserverHelperIntegration:
    """Integration tests for Discord observer helper functions."""

    def setup_method(self):
        """Set up test fixtures."""
        self.observer = DiscordObserver(
            filter_service=Mock(),
            communication_service=Mock()
        )
        self.observer._document_parser = Mock()
        self.observer._document_parser.is_available.return_value = True
        self.observer._document_parser._is_document_attachment.return_value = True

    @pytest.mark.asyncio
    async def test_collect_message_attachments_with_reply_integration(self):
        """Test the refactored _collect_message_attachments_with_reply method."""
        # Mock image attachment
        mock_image = Mock()
        mock_image.content_type = "image/png"

        # Mock document attachment
        mock_doc = Mock()

        # Mock reply message with attachments
        mock_reply_message = Mock()
        mock_reply_message.attachments = [mock_image, mock_doc]
        mock_reply_message.embeds = [Mock()]

        # Mock referenced message
        mock_author = Mock()
        mock_author.display_name = "OriginalUser"
        mock_referenced_message = Mock()
        mock_referenced_message.content = "Original message text"
        mock_referenced_message.author = mock_author
        mock_referenced_message.attachments = []

        # Mock reference
        mock_reference = Mock()
        mock_reference.resolved = mock_referenced_message
        mock_reply_message.reference = mock_reference

        # Mock helper methods - make sure only the doc attachment is treated as document
        def mock_is_image(attachment):
            return attachment == mock_image

        def mock_is_document(attachment):
            return attachment == mock_doc

        self.observer._is_image_attachment = mock_is_image
        self.observer._document_parser._is_document_attachment = mock_is_document

        result = await self.observer._collect_message_attachments_with_reply(mock_reply_message)

        # Verify complete result structure
        assert "images" in result
        assert "documents" in result
        assert "embeds" in result
        assert "reply_context" in result

        # Verify reply context was built
        assert result["reply_context"] == "@OriginalUser: Original message text"

        # Verify attachments were processed
        assert len(result["images"]) == 1
        assert len(result["documents"]) == 1  # Only the non-image attachment
        assert len(result["embeds"]) == 1

    def test_helper_function_error_handling(self):
        """Test helper functions handle edge cases gracefully."""
        # Test with various edge cases
        assert self.observer._build_reply_context(None) is None

        order = self.observer._build_message_processing_order(None, None)
        assert len(order) == 0

        # Test attachment processing with empty lists
        result = {"images": [], "documents": [], "embeds": []}
        self.observer._process_message_attachments([], result)
        assert all(len(lst) == 0 for lst in result.values() if isinstance(lst, list))