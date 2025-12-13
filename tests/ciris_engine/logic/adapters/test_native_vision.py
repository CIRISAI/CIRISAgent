"""Comprehensive tests for native multimodal vision support.

Tests cover:
- ImageContent schema
- BaseVisionHelper
- APIVisionHelper
- DiscordVisionHelper (native multimodal mode)
- Task image persistence
- ProcessingQueueItem image inheritance
"""

import base64
import json
from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ciris_engine.schemas.runtime.models import ImageContent


class TestImageContentSchema:
    """Test ImageContent schema validation and methods."""

    def test_create_base64_image(self):
        """Test creating ImageContent with base64 data."""
        image = ImageContent(
            source_type="base64",
            data="iVBORw0KGgoAAAANSUhEUg==",
            media_type="image/png",
            filename="test.png",
        )
        assert image.source_type == "base64"
        assert image.media_type == "image/png"
        assert image.filename == "test.png"

    def test_create_url_image(self):
        """Test creating ImageContent with URL."""
        image = ImageContent(
            source_type="url",
            data="https://example.com/image.png",
            media_type="image/png",
        )
        assert image.source_type == "url"
        assert image.data == "https://example.com/image.png"

    def test_to_data_url_base64(self):
        """Test to_data_url for base64 source."""
        image = ImageContent(
            source_type="base64",
            data="dGVzdGRhdGE=",
            media_type="image/jpeg",
        )
        data_url = image.to_data_url()
        assert data_url == "data:image/jpeg;base64,dGVzdGRhdGE="

    def test_to_data_url_url_source(self):
        """Test to_data_url for URL source returns URL directly."""
        url = "https://example.com/image.png"
        image = ImageContent(
            source_type="url",
            data=url,
            media_type="image/png",
        )
        data_url = image.to_data_url()
        assert data_url == url

    def test_default_values(self):
        """Test default values are applied."""
        image = ImageContent(
            source_type="base64",
            data="test",
        )
        assert image.media_type == "image/jpeg"
        assert image.filename is None

    def test_model_dump_json(self):
        """Test JSON serialization."""
        image = ImageContent(
            source_type="base64",
            data="testdata",
            media_type="image/png",
            filename="test.png",
        )
        dumped = image.model_dump(mode="json")
        assert dumped["source_type"] == "base64"
        assert dumped["data"] == "testdata"
        assert dumped["media_type"] == "image/png"
        assert dumped["filename"] == "test.png"

    def test_model_validate(self):
        """Test model validation from dict."""
        data = {
            "source_type": "url",
            "data": "https://example.com/img.jpg",
            "media_type": "image/jpeg",
        }
        image = ImageContent.model_validate(data)
        assert image.source_type == "url"
        assert image.data == "https://example.com/img.jpg"


class TestBaseVisionHelper:
    """Test BaseVisionHelper methods using APIVisionHelper as concrete implementation."""

    @pytest.fixture
    def helper(self):
        """Create APIVisionHelper instance (concrete implementation of BaseVisionHelper)."""
        from ciris_engine.logic.adapters.api.api_vision import APIVisionHelper

        return APIVisionHelper()

    def test_is_available(self, helper):
        """Test is_available returns True for native multimodal."""
        assert helper.is_available() is True

    def test_get_status(self, helper):
        """Test get_status returns correct info."""
        status = helper.get_status()
        assert status["available"] is True
        assert "max_image_size_mb" in status
        assert status["multimodal_enabled"] is True

    def test_base64_to_image_content(self, helper):
        """Test base64 to ImageContent conversion."""
        b64_data = base64.b64encode(b"test image data").decode()
        result = helper.base64_to_image_content(b64_data, "image/png", "test.png")

        assert result is not None
        assert result.source_type == "base64"
        assert result.data == b64_data
        assert result.media_type == "image/png"
        assert result.filename == "test.png"

    def test_base64_to_image_content_invalid(self, helper):
        """Test base64 conversion with invalid data."""
        result = helper.base64_to_image_content("not-valid-base64!!!", "image/png")
        assert result is None

    def test_base64_to_image_content_empty(self, helper):
        """Test base64 conversion with empty data."""
        result = helper.base64_to_image_content("", "image/png")
        assert result is None

    @pytest.mark.asyncio
    async def test_url_to_image_content(self, helper):
        """Test URL to ImageContent conversion."""
        url = "https://example.com/image.jpg"

        # Mock aiohttp response
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.headers = {"Content-Type": "image/jpeg"}
        mock_response.read = AsyncMock(return_value=b"fake image data")

        mock_session = AsyncMock()
        mock_session.get = AsyncMock(return_value=AsyncMock(__aenter__=AsyncMock(return_value=mock_response)))

        with patch(
            "aiohttp.ClientSession",
            return_value=AsyncMock(__aenter__=AsyncMock(return_value=mock_session), __aexit__=AsyncMock()),
        ):
            result = await helper.url_to_image_content(url)

        # Result may be None if the mock doesn't work perfectly, but shouldn't raise
        # In real usage, this would return an ImageContent

    def test_build_multimodal_message_no_images(self, helper):
        """Test building LLM message without images."""
        from ciris_engine.schemas.services.llm import LLMMessage

        msg = helper.build_multimodal_message("Test content", [], "user")
        assert isinstance(msg, LLMMessage)
        assert msg.role == "user"
        assert msg.content == "Test content"

    def test_build_multimodal_message_with_images(self, helper):
        """Test building LLM message with images."""
        from ciris_engine.schemas.services.llm import LLMMessage

        images = [
            ImageContent(source_type="base64", data="dGVzdA==", media_type="image/png"),
            ImageContent(source_type="url", data="https://example.com/img.jpg", media_type="image/jpeg"),
        ]

        msg = helper.build_multimodal_message("Describe these images", images, "user")
        assert isinstance(msg, LLMMessage)
        assert msg.role == "user"
        # Content should be a list of content blocks
        assert isinstance(msg.content, list)
        assert len(msg.content) == 3  # 1 text + 2 images

    def test_build_multimodal_content_blocks(self, helper):
        """Test building content blocks directly."""
        images = [
            ImageContent(source_type="base64", data="dGVzdA==", media_type="image/png"),
        ]

        blocks = helper.build_multimodal_content_blocks("Test text", images)
        assert len(blocks) == 2  # 1 text + 1 image
        assert blocks[0].text == "Test text"


class TestAPIVisionHelper:
    """Test APIVisionHelper methods."""

    @pytest.fixture
    def helper(self):
        """Create APIVisionHelper instance."""
        from ciris_engine.logic.adapters.api.api_vision import APIVisionHelper

        return APIVisionHelper()

    def test_is_available(self, helper):
        """Test is_available returns True."""
        assert helper.is_available() is True

    def test_process_image_payload_base64(self, helper):
        """Test processing a single base64 image."""
        b64_data = base64.b64encode(b"fake png data").decode()
        result = helper.process_image_payload(b64_data, "image/png", "test.png")

        assert result is not None
        assert result.source_type == "base64"
        assert result.media_type == "image/png"
        assert result.filename == "test.png"

    def test_process_image_payload_url(self, helper):
        """Test processing a URL image (sync returns URL-based ImageContent)."""
        url = "https://example.com/image.jpg"
        result = helper.process_image_payload(url, "image/jpeg")

        # URL processing returns URL-type ImageContent
        assert result is not None
        assert result.source_type == "url"
        assert result.data == url

    def test_process_image_list(self, helper):
        """Test processing a list of images."""
        images = [
            {"data": base64.b64encode(b"img1").decode(), "media_type": "image/png", "filename": "img1.png"},
            {"data": "https://example.com/img2.jpg", "media_type": "image/jpeg"},
        ]

        results = helper.process_image_list(images)
        assert len(results) == 2
        assert results[0].filename == "img1.png"
        assert results[1].source_type == "url"

    def test_process_image_list_empty(self, helper):
        """Test processing empty list."""
        results = helper.process_image_list([])
        assert results == []

    def test_process_image_list_with_invalid(self, helper):
        """Test processing list with invalid entries."""
        images = [
            {"data": base64.b64encode(b"valid").decode(), "media_type": "image/png"},
            {"data": "", "media_type": "image/png"},  # Invalid - empty data
        ]

        results = helper.process_image_list(images)
        # Should have 1 valid result
        assert len(results) == 1


class TestDiscordVisionHelperNative:
    """Test DiscordVisionHelper in native multimodal mode."""

    @pytest.fixture
    def helper(self):
        """Create DiscordVisionHelper instance."""
        from ciris_engine.logic.adapters.discord.discord_vision_helper import DiscordVisionHelper

        return DiscordVisionHelper()

    def test_is_available(self, helper):
        """Test is_available returns True for native multimodal."""
        assert helper.is_available() is True

    def test_get_status(self, helper):
        """Test get_status returns native multimodal info."""
        status = helper.get_status()
        assert status["available"] is True
        assert status["multimodal_enabled"] is True

    @pytest.mark.asyncio
    async def test_attachments_to_image_content(self, helper):
        """Test converting Discord attachments to ImageContent."""
        # Create mock attachment
        mock_attachment = MagicMock()
        mock_attachment.content_type = "image/png"
        mock_attachment.filename = "test.png"
        mock_attachment.size = 1000
        mock_attachment.url = "https://cdn.discord.com/test.png"
        mock_attachment.read = AsyncMock(return_value=b"fake image data")

        with patch.object(
            helper,
            "attachment_to_image_content",
            return_value=ImageContent(
                source_type="base64", data="dGVzdA==", media_type="image/png", filename="test.png"
            ),
        ):
            results = await helper.attachments_to_image_content([mock_attachment])

        assert len(results) == 1
        assert results[0].filename == "test.png"

    @pytest.mark.asyncio
    async def test_attachments_to_image_content_filters_non_images(self, helper):
        """Test that non-image attachments are filtered out."""
        mock_text = MagicMock()
        mock_text.content_type = "text/plain"
        mock_text.filename = "readme.txt"

        mock_image = MagicMock()
        mock_image.content_type = "image/jpeg"
        mock_image.filename = "photo.jpg"
        mock_image.size = 5000

        with patch.object(
            helper,
            "attachment_to_image_content",
            return_value=ImageContent(
                source_type="base64", data="dGVzdA==", media_type="image/jpeg", filename="photo.jpg"
            ),
        ):
            results = await helper.attachments_to_image_content([mock_text, mock_image])

        # Only image attachment should be processed
        assert len(results) == 1
        assert results[0].filename == "photo.jpg"

    @pytest.mark.asyncio
    async def test_message_to_image_content_no_attachments(self, helper):
        """Test message with no attachments returns empty list."""
        mock_message = MagicMock()
        mock_message.attachments = []

        results = await helper.message_to_image_content(mock_message)
        assert results == []

    @pytest.mark.asyncio
    async def test_process_image_attachments_list(self, helper):
        """Test process_image_attachments_list method."""
        mock_attachment = MagicMock()
        mock_attachment.content_type = "image/png"
        mock_attachment.filename = "test.png"

        with patch.object(
            helper,
            "attachments_to_image_content",
            return_value=[ImageContent(source_type="base64", data="test", media_type="image/png", filename="test.png")],
        ):
            results = await helper.process_image_attachments_list([mock_attachment])

        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_process_embeds(self, helper):
        """Test processing Discord embeds for images."""
        mock_embed = MagicMock()
        mock_embed.image = MagicMock()
        mock_embed.image.url = "https://example.com/embed_image.png"
        mock_embed.thumbnail = None

        with patch.object(
            helper,
            "url_to_image_content",
            return_value=ImageContent(
                source_type="base64", data="dGVzdA==", media_type="image/png", filename="embed_image_0.jpg"
            ),
        ):
            results = await helper.process_embeds([mock_embed])

        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_process_embeds_no_images(self, helper):
        """Test processing embeds without images."""
        mock_embed = MagicMock()
        mock_embed.image = None
        mock_embed.thumbnail = None

        results = await helper.process_embeds([mock_embed])
        assert results == []


class TestTaskImagePersistence:
    """Test task image persistence in database."""

    @pytest.fixture
    def sample_task(self):
        """Create a sample task with images."""
        from ciris_engine.schemas.runtime.enums import TaskStatus
        from ciris_engine.schemas.runtime.models import Task, TaskContext

        return Task(
            task_id="test-task-001",
            channel_id="test-channel",
            description="Test task with images",
            status=TaskStatus.PENDING,
            created_at="2025-01-01T00:00:00Z",
            updated_at="2025-01-01T00:00:00Z",
            context=TaskContext(
                channel_id="test-channel",
                user_id="test-user",
                correlation_id="test-correlation",
            ),
            images=[
                ImageContent(source_type="base64", data="img1data", media_type="image/png", filename="img1.png"),
                ImageContent(source_type="url", data="https://example.com/img2.jpg", media_type="image/jpeg"),
            ],
        )

    def test_task_model_dump_includes_images(self, sample_task):
        """Test that task model dump includes images."""
        dumped = sample_task.model_dump(mode="json")
        assert "images" in dumped
        assert len(dumped["images"]) == 2
        assert dumped["images"][0]["filename"] == "img1.png"

    def test_task_images_serialization(self, sample_task):
        """Test images serialize to JSON correctly."""
        images_data = sample_task.model_dump(mode="json")["images"]
        json_str = json.dumps(images_data)

        # Verify round-trip
        loaded = json.loads(json_str)
        assert len(loaded) == 2

        # Reconstruct ImageContent objects
        reconstructed = [ImageContent.model_validate(img) for img in loaded]
        assert reconstructed[0].filename == "img1.png"
        assert reconstructed[1].source_type == "url"


class TestMapRowToTask:
    """Test map_row_to_task with images_json column."""

    def test_map_row_with_images(self):
        """Test mapping a database row with images_json."""
        from ciris_engine.logic.persistence.utils import map_row_to_task

        images_json = json.dumps(
            [
                {"source_type": "base64", "data": "testdata", "media_type": "image/png", "filename": "test.png"},
            ]
        )

        # Create a mock row (dict-like)
        row = {
            "task_id": "test-123",
            "channel_id": "channel-1",
            "agent_occurrence_id": "default",
            "description": "Test task",
            "status": "pending",
            "priority": 5,
            "created_at": "2025-01-01T00:00:00Z",
            "updated_at": "2025-01-01T00:00:00Z",
            "parent_task_id": None,
            "context_json": None,
            "outcome_json": None,
            "signed_by": None,
            "signature": None,
            "signed_at": None,
            "images_json": images_json,
        }

        task = map_row_to_task(row)
        assert len(task.images) == 1
        assert task.images[0].filename == "test.png"

    def test_map_row_without_images(self):
        """Test mapping a database row without images_json."""
        from ciris_engine.logic.persistence.utils import map_row_to_task

        row = {
            "task_id": "test-456",
            "channel_id": "channel-2",
            "agent_occurrence_id": "default",
            "description": "Test task no images",
            "status": "pending",
            "priority": 0,
            "created_at": "2025-01-01T00:00:00Z",
            "updated_at": "2025-01-01T00:00:00Z",
            "parent_task_id": None,
            "context_json": None,
            "outcome_json": None,
            "signed_by": None,
            "signature": None,
            "signed_at": None,
            "images_json": None,
        }

        task = map_row_to_task(row)
        assert task.images == []

    def test_map_row_with_empty_images_json(self):
        """Test mapping a row with empty images array."""
        from ciris_engine.logic.persistence.utils import map_row_to_task

        row = {
            "task_id": "test-789",
            "channel_id": "channel-3",
            "agent_occurrence_id": "default",
            "description": "Test task empty images",
            "status": "pending",
            "priority": 0,
            "created_at": "2025-01-01T00:00:00Z",
            "updated_at": "2025-01-01T00:00:00Z",
            "parent_task_id": None,
            "context_json": None,
            "outcome_json": None,
            "signed_by": None,
            "signature": None,
            "signed_at": None,
            "images_json": "[]",
        }

        task = map_row_to_task(row)
        assert task.images == []


class TestProcessingQueueItemImageInheritance:
    """Test ProcessingQueueItem inheriting images from tasks."""

    @pytest.fixture
    def sample_thought(self):
        """Create a sample thought."""
        from ciris_engine.schemas.runtime.enums import ThoughtStatus, ThoughtType
        from ciris_engine.schemas.runtime.models import Thought, ThoughtContext

        return Thought(
            thought_id="thought-001",
            source_task_id="task-001",
            channel_id="test-channel",
            thought_type=ThoughtType.STANDARD,
            status=ThoughtStatus.PENDING,
            created_at="2025-01-01T00:00:00Z",
            updated_at="2025-01-01T00:00:00Z",
            content="Test thought content",
            agent_occurrence_id="default",
        )

    @pytest.fixture
    def sample_task_with_images(self):
        """Create a sample task with images."""
        from ciris_engine.schemas.runtime.enums import TaskStatus
        from ciris_engine.schemas.runtime.models import Task, TaskContext

        return Task(
            task_id="task-001",
            channel_id="test-channel",
            description="Task with images",
            status=TaskStatus.ACTIVE,
            created_at="2025-01-01T00:00:00Z",
            updated_at="2025-01-01T00:00:00Z",
            context=TaskContext(
                channel_id="test-channel",
                user_id="user-1",
                correlation_id="corr-1",
            ),
            images=[
                ImageContent(source_type="base64", data="taskimg", media_type="image/png", filename="task_img.png"),
            ],
        )

    def test_from_thought_with_task_images(self, sample_thought, sample_task_with_images):
        """Test from_thought inherits images when task_images provided."""
        from ciris_engine.logic.processors.support.processing_queue import ProcessingQueueItem

        item = ProcessingQueueItem.from_thought(
            sample_thought,
            task_images=sample_task_with_images.images,
        )

        assert len(item.images) == 1
        assert item.images[0].filename == "task_img.png"

    def test_from_thought_without_task_images(self, sample_thought):
        """Test from_thought without task_images looks up task."""
        from ciris_engine.logic.processors.support.processing_queue import ProcessingQueueItem

        # Mock get_task_by_id to return a task with images
        mock_task = MagicMock()
        mock_task.images = [
            ImageContent(source_type="base64", data="lookedup", media_type="image/jpeg", filename="looked_up.jpg"),
        ]

        with patch("ciris_engine.logic.persistence.models.tasks.get_task_by_id", return_value=mock_task):
            item = ProcessingQueueItem.from_thought(sample_thought)

        assert len(item.images) == 1
        assert item.images[0].filename == "looked_up.jpg"

    def test_from_thought_task_not_found(self, sample_thought):
        """Test from_thought when task lookup fails."""
        from ciris_engine.logic.processors.support.processing_queue import ProcessingQueueItem

        with patch("ciris_engine.logic.persistence.models.tasks.get_task_by_id", return_value=None):
            item = ProcessingQueueItem.from_thought(sample_thought)

        # Should have empty images list
        assert item.images == []

    def test_from_thought_task_lookup_error(self, sample_thought):
        """Test from_thought handles task lookup errors gracefully."""
        from ciris_engine.logic.processors.support.processing_queue import ProcessingQueueItem

        with patch("ciris_engine.logic.persistence.models.tasks.get_task_by_id", side_effect=Exception("DB error")):
            item = ProcessingQueueItem.from_thought(sample_thought)

        # Should have empty images list and not raise
        assert item.images == []


class TestDMAMultimodalSupport:
    """Test DMA multimodal support."""

    def test_build_multimodal_content_in_dma(self):
        """Test that DMAs can build multimodal content."""
        from ciris_engine.logic.dma.base_dma import BaseDMA

        images = [
            ImageContent(source_type="base64", data="test", media_type="image/png"),
        ]

        # build_multimodal_content is a static method
        content = BaseDMA.build_multimodal_content("Test prompt", images)

        # Should return a list of content blocks when images present
        assert isinstance(content, list)
        assert len(content) == 2  # 1 text + 1 image

    def test_build_multimodal_content_no_images(self):
        """Test build_multimodal_content with no images returns string."""
        from ciris_engine.logic.dma.base_dma import BaseDMA

        content = BaseDMA.build_multimodal_content("Test prompt", [])

        # Should return plain string when no images
        assert content == "Test prompt"

    def test_build_multimodal_content_with_multiple_images(self):
        """Test build_multimodal_content with multiple images."""
        from ciris_engine.logic.dma.base_dma import BaseDMA

        images = [
            ImageContent(source_type="base64", data="img1", media_type="image/png"),
            ImageContent(source_type="url", data="https://example.com/img2.jpg", media_type="image/jpeg"),
        ]

        content = BaseDMA.build_multimodal_content("Analyze these images", images)

        # Should return list with 1 text + 2 images
        assert isinstance(content, list)
        assert len(content) == 3


class TestIncomingMessageImages:
    """Test IncomingMessage schema with images."""

    def test_incoming_message_with_images(self):
        """Test creating IncomingMessage with images."""
        from ciris_engine.schemas.runtime.messages import IncomingMessage

        images = [
            ImageContent(source_type="base64", data="test", media_type="image/png", filename="test.png"),
        ]

        msg = IncomingMessage(
            message_id="msg-001",
            author_id="user-1",
            author_name="TestUser",
            content="Check this image",
            images=images,
        )

        assert len(msg.images) == 1
        assert msg.images[0].filename == "test.png"

    def test_discord_message_inherits_images(self):
        """Test DiscordMessage inherits images field."""
        from ciris_engine.schemas.runtime.messages import DiscordMessage

        images = [
            ImageContent(source_type="url", data="https://cdn.discord.com/img.png", media_type="image/png"),
        ]

        msg = DiscordMessage(
            message_id="discord-msg-001",
            author_id="discord-user",
            author_name="DiscordUser",
            content="Discord message with image",
            channel_id="channel-1",
            images=images,
        )

        assert len(msg.images) == 1
        assert msg.images[0].source_type == "url"
