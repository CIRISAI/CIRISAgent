"""Discord Vision Helper for native multimodal image processing.

Extends BaseVisionHelper to provide Discord-specific image handling.
Images are converted to ImageContent and flow through the pipeline
to the main LLM's vision capabilities.
"""

import logging
from typing import List

import discord

from ciris_engine.logic.adapters.base_vision import BaseVisionHelper
from ciris_engine.schemas.runtime.models import ImageContent
from ciris_engine.schemas.types import JSONDict

logger = logging.getLogger(__name__)


class DiscordVisionHelper(BaseVisionHelper):
    """
    Helper class for processing Discord images via native multimodal.

    Converts Discord attachments to ImageContent objects that flow through
    the pipeline to vision-capable LLMs (Llama 4, GPT-4o, Claude, etc).

    Inherits from BaseVisionHelper for common image conversion functionality.
    """

    def __init__(self, max_image_size: int = 20 * 1024 * 1024):
        """Initialize the vision helper.

        Args:
            max_image_size: Maximum allowed image size in bytes (default 20MB)
        """
        super().__init__(max_image_size=max_image_size)

    async def attachments_to_image_content(
        self, attachments: List[discord.Attachment]
    ) -> List[ImageContent]:
        """
        Convert Discord attachments to ImageContent objects for native multimodal.

        Args:
            attachments: List of Discord attachment objects

        Returns:
            List of ImageContent objects (filtered for images, within size limits)
        """
        images: List[ImageContent] = []

        # Filter for image attachments
        image_attachments = [
            att for att in attachments
            if att.content_type and att.content_type.startswith("image/")
        ]

        for attachment in image_attachments:
            try:
                # Use parent class method for conversion
                image_content = await self.attachment_to_image_content(attachment)
                if image_content:
                    images.append(image_content)
            except Exception as e:
                logger.error(f"Failed to convert attachment {attachment.filename}: {e}")

        return images

    async def message_to_image_content(
        self, message: discord.Message
    ) -> List[ImageContent]:
        """
        Extract all images from a Discord message as ImageContent objects.

        Args:
            message: Discord message

        Returns:
            List of ImageContent objects from message attachments
        """
        if not message.attachments:
            return []

        return await self.attachments_to_image_content(list(message.attachments))

    def is_available(self) -> bool:
        """Check if vision processing is available.

        Returns:
            True - native multimodal is always available
        """
        return True

    def get_status(self) -> JSONDict:
        """Get current status of vision helper.

        Returns:
            Status dictionary
        """
        return {
            "available": True,
            "max_image_size_mb": self.max_image_size / 1024 / 1024,
            "multimodal_enabled": True,
        }
