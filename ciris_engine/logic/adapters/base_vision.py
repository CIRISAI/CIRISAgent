"""
Base Vision Helper for multimodal image processing.

Provides a common base class for all adapters to handle image processing,
supporting both legacy text-description mode and native multimodal mode.
"""

import base64
import logging
from abc import ABC, abstractmethod
from typing import Any, List, Optional, Protocol, runtime_checkable

import aiohttp

from ciris_engine.schemas.runtime.models import ImageContent
from ciris_engine.schemas.services.llm import (
    ContentBlock,
    ImageContentBlock,
    ImageURLDetail,
    LLMMessage,
    TextContentBlock,
)
from ciris_engine.schemas.types import JSONDict

logger = logging.getLogger(__name__)


# Maximum image size (20MB default)
DEFAULT_MAX_IMAGE_SIZE = 20 * 1024 * 1024

# Default media type for images
DEFAULT_IMAGE_MEDIA_TYPE = "image/jpeg"


@runtime_checkable
class ImageAttachment(Protocol):
    """Protocol for image attachments from various sources."""

    @property
    def url(self) -> str:
        """URL to download the image."""
        ...

    @property
    def content_type(self) -> Optional[str]:
        """MIME type of the image."""
        ...

    @property
    def filename(self) -> str:
        """Filename of the attachment."""
        ...

    @property
    def size(self) -> int:
        """Size in bytes."""
        ...


class BaseVisionHelper(ABC):
    """
    Base class for vision helpers across all adapters.

    Provides common functionality for:
    - Converting attachments to ImageContent objects
    - Building multimodal LLM messages
    - Image size validation
    - Base64 encoding

    Subclasses can override methods for adapter-specific behavior.
    """

    def __init__(self, max_image_size: int = DEFAULT_MAX_IMAGE_SIZE) -> None:
        """
        Initialize the base vision helper.

        Args:
            max_image_size: Maximum allowed image size in bytes
        """
        self.max_image_size = max_image_size

    async def attachment_to_image_content(self, attachment: ImageAttachment) -> Optional[ImageContent]:
        """
        Convert an attachment to an ImageContent object.

        Downloads the image and encodes it as base64.

        Args:
            attachment: An object implementing the ImageAttachment protocol

        Returns:
            ImageContent object or None if conversion failed
        """
        # Validate size
        if attachment.size > self.max_image_size:
            logger.warning(
                f"Image {attachment.filename} too large: {attachment.size} bytes (max {self.max_image_size} bytes)"
            )
            return None

        # Validate content type
        content_type = attachment.content_type or DEFAULT_IMAGE_MEDIA_TYPE
        if not content_type.startswith("image/"):
            logger.warning(f"Attachment {attachment.filename} is not an image: {content_type}")
            return None

        try:
            # Download the image
            async with aiohttp.ClientSession() as session:
                async with session.get(attachment.url) as response:
                    if response.status != 200:
                        logger.error(f"Failed to download image {attachment.filename}: HTTP {response.status}")
                        return None

                    image_data = await response.read()
                    base64_data = base64.b64encode(image_data).decode("utf-8")

            return ImageContent(
                source_type="base64",
                data=base64_data,
                media_type=content_type,
                filename=attachment.filename,
                size_bytes=len(image_data),
            )

        except Exception as e:
            logger.exception(f"Error converting attachment {attachment.filename}: {e}")
            return None

    async def url_to_image_content(
        self,
        url: str,
        media_type: str = DEFAULT_IMAGE_MEDIA_TYPE,
        filename: Optional[str] = None,
    ) -> Optional[ImageContent]:
        """
        Convert a URL to an ImageContent object.

        Downloads the image and encodes it as base64.

        Args:
            url: URL of the image
            media_type: MIME type of the image
            filename: Optional filename

        Returns:
            ImageContent object or None if conversion failed
        """
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    if response.status != 200:
                        logger.error(f"Failed to download image from {url}: HTTP {response.status}")
                        return None

                    image_data = await response.read()

                    # Check size after download
                    if len(image_data) > self.max_image_size:
                        logger.warning(
                            f"Image from {url} too large: {len(image_data)} bytes (max {self.max_image_size} bytes)"
                        )
                        return None

                    base64_data = base64.b64encode(image_data).decode("utf-8")

            return ImageContent(
                source_type="base64",
                data=base64_data,
                media_type=media_type,
                filename=filename or url.split("/")[-1] or "image",
                size_bytes=len(image_data),
            )

        except Exception as e:
            logger.exception(f"Error downloading image from {url}: {e}")
            return None

    def bytes_to_image_content(
        self,
        data: bytes,
        media_type: str = DEFAULT_IMAGE_MEDIA_TYPE,
        filename: Optional[str] = None,
    ) -> Optional[ImageContent]:
        """
        Convert raw bytes to an ImageContent object.

        Args:
            data: Raw image bytes
            media_type: MIME type of the image
            filename: Optional filename

        Returns:
            ImageContent object or None if conversion failed
        """
        if len(data) > self.max_image_size:
            logger.warning(f"Image data too large: {len(data)} bytes (max {self.max_image_size} bytes)")
            return None

        try:
            base64_data = base64.b64encode(data).decode("utf-8")
            return ImageContent(
                source_type="base64",
                data=base64_data,
                media_type=media_type,
                filename=filename or "image",
                size_bytes=len(data),
            )
        except Exception as e:
            logger.exception(f"Error encoding image bytes: {e}")
            return None

    @staticmethod
    def build_multimodal_message(
        text: str,
        images: List[ImageContent],
        role: str = "user",
    ) -> LLMMessage:
        """
        Build a multimodal LLM message from text and images.

        Args:
            text: Text content of the message
            images: List of ImageContent objects
            role: Message role (user, system, assistant)

        Returns:
            LLMMessage with multimodal content if images present, text-only otherwise
        """
        if not images:
            return LLMMessage(role=role, content=text)

        # Build content blocks
        content: List[ContentBlock] = [TextContentBlock(text=text)]

        for img in images:
            image_block = ImageContentBlock(image_url=ImageURLDetail(url=img.to_data_url()))
            content.append(image_block)

        return LLMMessage(role=role, content=content)

    @staticmethod
    def build_multimodal_content_blocks(
        text: str,
        images: List[ImageContent],
    ) -> List[ContentBlock]:
        """
        Build content blocks for multimodal messages.

        Useful when you need the raw content blocks without wrapping in LLMMessage.

        Args:
            text: Text content
            images: List of ImageContent objects

        Returns:
            List of content blocks
        """
        content: List[ContentBlock] = [TextContentBlock(text=text)]

        for img in images:
            image_block = ImageContentBlock(image_url=ImageURLDetail(url=img.to_data_url()))
            content.append(image_block)

        return content

    def get_status(self) -> JSONDict:
        """
        Get current status of the vision helper.

        Returns:
            Status dictionary
        """
        return {
            "max_image_size_mb": self.max_image_size / 1024 / 1024,
            "multimodal_enabled": True,
        }

    @abstractmethod
    def is_available(self) -> bool:
        """
        Check if vision processing is available.

        Returns:
            True if vision processing can be performed
        """
        ...


class SimpleVisionHelper(BaseVisionHelper):
    """
    Simple vision helper implementation.

    Always available, used for adapters that just need basic
    image-to-ImageContent conversion without external API calls.
    """

    def is_available(self) -> bool:
        """Always available for basic image handling."""
        return True


# Singleton instance for simple cases
_simple_vision_helper: Optional[SimpleVisionHelper] = None


def get_simple_vision_helper() -> SimpleVisionHelper:
    """Get or create the simple vision helper singleton."""
    global _simple_vision_helper
    if _simple_vision_helper is None:
        _simple_vision_helper = SimpleVisionHelper()
    return _simple_vision_helper
