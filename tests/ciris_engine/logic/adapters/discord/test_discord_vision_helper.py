"""Tests for Discord Vision Helper - Native Multimodal Support."""

from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest

from ciris_engine.logic.adapters.discord.discord_vision_helper import DiscordVisionHelper
from ciris_engine.schemas.runtime.models import ImageContent


class TestDiscordVisionHelperInitialization:
    """Test vision helper initialization."""

    def test_init_default(self):
        """Test initialization with default settings."""
        helper = DiscordVisionHelper()
        assert helper.max_image_size == 20 * 1024 * 1024

    def test_init_custom_max_size(self):
        """Test initialization with custom max image size."""
        helper = DiscordVisionHelper(max_image_size=10 * 1024 * 1024)
        assert helper.max_image_size == 10 * 1024 * 1024

    def test_is_available_always_true(self):
        """Test is_available returns True (native vision is always available)."""
        helper = DiscordVisionHelper()
        assert helper.is_available() is True


class TestAttachmentsToImageContent:
    """Test converting Discord attachments to ImageContent."""

    @pytest.fixture
    def vision_helper(self):
        """Create vision helper."""
        return DiscordVisionHelper()

    @pytest.fixture
    def mock_image_attachment(self):
        """Create mock image attachment."""
        attachment = MagicMock(spec=discord.Attachment)
        attachment.filename = "test.png"
        attachment.content_type = "image/png"
        attachment.size = 1000000  # 1MB
        attachment.url = "https://cdn.discord.com/test.png"
        attachment.read = AsyncMock(return_value=b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
        return attachment

    @pytest.fixture
    def mock_large_attachment(self):
        """Create mock oversized attachment."""
        attachment = MagicMock(spec=discord.Attachment)
        attachment.filename = "large.png"
        attachment.content_type = "image/png"
        attachment.size = 25 * 1024 * 1024  # 25MB - too large
        attachment.url = "https://cdn.discord.com/large.png"
        return attachment

    @pytest.fixture
    def mock_non_image_attachment(self):
        """Create mock non-image attachment."""
        attachment = MagicMock(spec=discord.Attachment)
        attachment.filename = "test.txt"
        attachment.content_type = "text/plain"
        attachment.size = 1000
        attachment.url = "https://cdn.discord.com/test.txt"
        return attachment

    @pytest.mark.asyncio
    async def test_empty_attachments(self, vision_helper):
        """Test with empty attachments list returns empty list."""
        result = await vision_helper.attachments_to_image_content([])
        assert result == []

    @pytest.mark.asyncio
    async def test_skip_non_image_attachments(self, vision_helper, mock_non_image_attachment):
        """Test non-image attachments are skipped."""
        result = await vision_helper.attachments_to_image_content([mock_non_image_attachment])
        assert result == []

    @pytest.mark.asyncio
    async def test_skip_oversized_attachments(self, vision_helper, mock_large_attachment):
        """Test oversized attachments are skipped."""
        result = await vision_helper.attachments_to_image_content([mock_large_attachment])
        assert result == []

    @pytest.mark.asyncio
    async def test_process_valid_image(self, vision_helper, mock_image_attachment):
        """Test processing valid image attachment."""
        # Mock the base class method to avoid HTTP calls
        import base64

        mock_image = ImageContent(
            source_type="base64",
            data=base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100).decode(),
            media_type="image/png",
            filename="test.png",
        )

        with patch.object(vision_helper, "attachment_to_image_content", new=AsyncMock(return_value=mock_image)):
            result = await vision_helper.attachments_to_image_content([mock_image_attachment])
            assert len(result) == 1
            assert isinstance(result[0], ImageContent)
            assert result[0].media_type == "image/png"
            assert result[0].filename == "test.png"

    @pytest.mark.asyncio
    async def test_process_multiple_images(self, vision_helper, mock_image_attachment):
        """Test processing multiple image attachments."""
        import base64

        # Create a second mock attachment
        attachment2 = MagicMock(spec=discord.Attachment)
        attachment2.filename = "test2.jpg"
        attachment2.content_type = "image/jpeg"
        attachment2.size = 500000
        attachment2.url = "https://cdn.discord.com/test2.jpg"

        mock_image1 = ImageContent(
            source_type="base64", data=base64.b64encode(b"png").decode(), media_type="image/png", filename="test.png"
        )
        mock_image2 = ImageContent(
            source_type="base64", data=base64.b64encode(b"jpg").decode(), media_type="image/jpeg", filename="test2.jpg"
        )

        with patch.object(
            vision_helper, "attachment_to_image_content", new=AsyncMock(side_effect=[mock_image1, mock_image2])
        ):
            result = await vision_helper.attachments_to_image_content([mock_image_attachment, attachment2])
            assert len(result) == 2

    @pytest.mark.asyncio
    async def test_mixed_attachments(self, vision_helper, mock_image_attachment, mock_non_image_attachment):
        """Test mixed image and non-image attachments."""
        import base64

        mock_image = ImageContent(
            source_type="base64", data=base64.b64encode(b"png").decode(), media_type="image/png", filename="test.png"
        )

        # Return image for first attachment, None for non-image
        with patch.object(vision_helper, "attachment_to_image_content", new=AsyncMock(side_effect=[mock_image, None])):
            result = await vision_helper.attachments_to_image_content(
                [mock_image_attachment, mock_non_image_attachment]
            )
            assert len(result) == 1  # Only the image


class TestProcessEmbeds:
    """Test processing Discord embeds for images."""

    @pytest.fixture
    def vision_helper(self):
        """Create vision helper."""
        return DiscordVisionHelper()

    @pytest.mark.asyncio
    async def test_empty_embeds(self, vision_helper):
        """Test with empty embeds list returns empty list."""
        result = await vision_helper.process_embeds([])
        assert result == []

    @pytest.mark.asyncio
    async def test_embed_with_image(self, vision_helper):
        """Test embed with image URL."""
        import base64

        embed = MagicMock(spec=discord.Embed)
        embed.image = MagicMock()
        embed.image.url = "https://example.com/image.png"
        embed.thumbnail = None

        mock_image = ImageContent(
            source_type="base64", data=base64.b64encode(b"png").decode(), media_type="image/png", filename="image.png"
        )

        with patch.object(vision_helper, "url_to_image_content", new=AsyncMock(return_value=mock_image)):
            result = await vision_helper.process_embeds([embed])
            assert len(result) == 1


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_max_image_size_validation(self):
        """Test various max_image_size values."""
        # Small size
        helper = DiscordVisionHelper(max_image_size=1024)
        assert helper.max_image_size == 1024

        # Large size
        helper = DiscordVisionHelper(max_image_size=100 * 1024 * 1024)
        assert helper.max_image_size == 100 * 1024 * 1024

    @pytest.mark.asyncio
    async def test_attachment_read_failure(self):
        """Test handling of attachment read failure."""
        helper = DiscordVisionHelper()

        attachment = MagicMock(spec=discord.Attachment)
        attachment.filename = "test.png"
        attachment.content_type = "image/png"
        attachment.size = 1000
        attachment.url = "https://cdn.discord.com/test.png"
        attachment.read = AsyncMock(side_effect=Exception("Read failed"))

        result = await helper.attachments_to_image_content([attachment])
        assert result == []
