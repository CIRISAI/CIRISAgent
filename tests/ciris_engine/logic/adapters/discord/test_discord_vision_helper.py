"""Comprehensive tests for Discord Vision Helper module."""

import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import discord

from ciris_engine.logic.adapters.discord.discord_vision_helper import DiscordVisionHelper


class TestDiscordVisionHelperInitialization:
    """Test vision helper initialization."""

    def test_init_with_api_key(self):
        """Test initialization with provided API key."""
        helper = DiscordVisionHelper(api_key="test_key")
        assert helper.api_key == "test_key"
        assert helper.api_url == "https://api.openai.com/v1/chat/completions"
        assert helper.model == "gpt-4o"
        assert helper.max_image_size == 20 * 1024 * 1024

    @patch.dict(os.environ, {"CIRIS_OPENAI_VISION_KEY": "env_key"})
    def test_init_with_env_var(self):
        """Test initialization with environment variable."""
        helper = DiscordVisionHelper()
        assert helper.api_key == "env_key"

    @patch.dict(os.environ, {}, clear=True)
    def test_init_no_api_key(self, caplog):
        """Test initialization without API key logs warning."""
        helper = DiscordVisionHelper()
        assert helper.api_key is None
        assert "No OpenAI Vision API key found" in caplog.text

    def test_is_available_with_key(self):
        """Test is_available returns True when API key exists."""
        helper = DiscordVisionHelper(api_key="test_key")
        assert helper.is_available() is True

    def test_is_available_without_key(self):
        """Test is_available returns False when no API key."""
        helper = DiscordVisionHelper()
        assert helper.is_available() is False


class TestProcessMessageImages:
    """Test processing images from Discord messages."""

    @pytest.fixture
    def vision_helper(self):
        """Create vision helper with API key."""
        return DiscordVisionHelper(api_key="test_key")

    @pytest.fixture
    def mock_image_attachment(self, mock_attachment):
        """Create mock image attachment."""
        return mock_attachment(
            filename="test.png",
            content_type="image/png",
            size=1000000
        )

    @pytest.fixture
    def mock_non_image_attachment(self, mock_attachment):
        """Create mock non-image attachment."""
        return mock_attachment(
            filename="test.txt",
            content_type="text/plain",
            size=1000
        )

    @pytest.mark.asyncio
    async def test_process_message_images_no_api_key(self, sample_discord_message):
        """Test processing without API key returns None."""
        helper = DiscordVisionHelper()
        result = await helper.process_message_images(sample_discord_message)
        assert result is None

    @pytest.mark.asyncio
    async def test_process_message_images_no_attachments(self, vision_helper, sample_discord_message):
        """Test processing message with no attachments."""
        sample_discord_message.attachments = []
        result = await vision_helper.process_message_images(sample_discord_message)
        assert result is None

    @pytest.mark.asyncio
    async def test_process_message_images_no_image_attachments(self, vision_helper, sample_discord_message, mock_non_image_attachment):
        """Test processing message with non-image attachments."""
        sample_discord_message.attachments = [mock_non_image_attachment]
        result = await vision_helper.process_message_images(sample_discord_message)
        assert result is None

    @pytest.mark.asyncio
    async def test_process_message_images_success(self, vision_helper, sample_discord_message, mock_image_attachment):
        """Test successful image processing."""
        sample_discord_message.attachments = [mock_image_attachment]

        with patch.object(vision_helper, '_process_single_image', return_value="A test image"):
            result = await vision_helper.process_message_images(sample_discord_message)
            assert result == "Image 'test.png': A test image"

    @pytest.mark.asyncio
    async def test_process_message_images_multiple_images(self, vision_helper, sample_discord_message, mock_attachment):
        """Test processing multiple images."""
        img1 = mock_attachment("img1.png", "image/png")
        img2 = mock_attachment("img2.jpg", "image/jpeg")
        sample_discord_message.attachments = [img1, img2]

        with patch.object(vision_helper, '_process_single_image', side_effect=["Description 1", "Description 2"]):
            result = await vision_helper.process_message_images(sample_discord_message)
            expected = "Image 'img1.png': Description 1\n\nImage 'img2.jpg': Description 2"
            assert result == expected

    @pytest.mark.asyncio
    async def test_process_message_images_with_error(self, vision_helper, sample_discord_message, mock_image_attachment):
        """Test processing with error handling."""
        sample_discord_message.attachments = [mock_image_attachment]

        with patch.object(vision_helper, '_process_single_image', side_effect=Exception("API Error")):
            result = await vision_helper.process_message_images(sample_discord_message)
            assert "Failed to process - API Error" in result


class TestProcessImageAttachmentsList:
    """Test processing list of image attachments."""

    @pytest.fixture
    def vision_helper(self):
        """Create vision helper with API key."""
        return DiscordVisionHelper(api_key="test_key")

    @pytest.mark.asyncio
    async def test_process_image_attachments_list_no_api_key(self, sample_image_attachment):
        """Test processing without API key returns None."""
        helper = DiscordVisionHelper()
        result = await helper.process_image_attachments_list([sample_image_attachment])
        assert result is None

    @pytest.mark.asyncio
    async def test_process_image_attachments_list_empty(self, vision_helper):
        """Test processing empty list."""
        result = await vision_helper.process_image_attachments_list([])
        assert result is None

    @pytest.mark.asyncio
    async def test_process_image_attachments_list_success(self, vision_helper, sample_image_attachment):
        """Test successful processing of attachment list."""
        with patch.object(vision_helper, '_process_single_image', return_value="Test description"):
            result = await vision_helper.process_image_attachments_list([sample_image_attachment])
            assert result == "Image 'test_image.png': Test description"


class TestProcessEmbeds:
    """Test processing Discord embeds."""

    @pytest.fixture
    def vision_helper(self):
        """Create vision helper with API key."""
        return DiscordVisionHelper(api_key="test_key")

    @pytest.fixture
    def mock_embed_with_image(self):
        """Create mock embed with image."""
        embed = MagicMock(spec=discord.Embed)
        embed.image = MagicMock()
        embed.image.url = "https://example.com/image.png"
        embed.thumbnail = None
        return embed

    @pytest.fixture
    def mock_embed_without_image(self):
        """Create mock embed without image."""
        embed = MagicMock(spec=discord.Embed)
        embed.image = None
        embed.thumbnail = None
        return embed

    @pytest.mark.asyncio
    async def test_process_embeds_no_api_key(self, mock_embed_with_image):
        """Test processing embeds without API key."""
        helper = DiscordVisionHelper()
        result = await helper.process_embeds([mock_embed_with_image])
        assert result is None

    @pytest.mark.asyncio
    async def test_process_embeds_empty_list(self, vision_helper):
        """Test processing empty embed list."""
        result = await vision_helper.process_embeds([])
        assert result is None

    @pytest.mark.asyncio
    async def test_process_embeds_no_images(self, vision_helper, mock_embed_without_image):
        """Test processing embeds without images."""
        result = await vision_helper.process_embeds([mock_embed_without_image])
        assert result is None

    @pytest.mark.asyncio
    async def test_process_embeds_with_images(self, vision_helper, mock_embed_with_image):
        """Test processing embeds with images."""
        with patch.object(vision_helper, '_process_image_url', return_value="Embed image description"):
            result = await vision_helper.process_embeds([mock_embed_with_image])
            assert "Embed image description" in result


class TestPrivateMethods:
    """Test private methods of vision helper."""

    @pytest.fixture
    def vision_helper(self):
        """Create vision helper with API key."""
        return DiscordVisionHelper(api_key="test_key")

    @pytest.mark.asyncio
    async def test_process_single_image_size_limit(self, vision_helper, mock_attachment):
        """Test single image processing with size limit."""
        large_attachment = mock_attachment("large.png", "image/png", size=25*1024*1024)

        result = await vision_helper._process_single_image(large_attachment)
        assert "Image too large" in result


class TestEdgeCases:
    """Test edge cases and error conditions."""

    @pytest.fixture
    def vision_helper(self):
        """Create vision helper with API key."""
        return DiscordVisionHelper(api_key="test_key")

    def test_initialization_edge_cases(self):
        """Test initialization with edge cases."""
        # Empty string API key should fallback to None via environment
        with patch.dict(os.environ, {}, clear=True):
            helper = DiscordVisionHelper(api_key="")
            assert helper.api_key == "" or helper.api_key is None

        # None API key explicitly
        with patch.dict(os.environ, {}, clear=True):
            helper = DiscordVisionHelper(api_key=None)
            assert helper.api_key is None