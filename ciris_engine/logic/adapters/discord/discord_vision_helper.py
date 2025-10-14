"""Discord Vision Helper for processing images with GPT-4 Vision."""

import base64
import logging
import os
from typing import Any, Dict, List, Optional
from ciris_engine.schemas.types import JSONDict

import aiohttp
import discord

logger = logging.getLogger(__name__)


class DiscordVisionHelper:
    """Helper class for processing Discord images with GPT-4 Vision."""

    def __init__(self, api_key: Optional[str] = None):
        """Initialize the vision helper.

        Args:
            api_key: OpenAI API key for Vision. If not provided, uses CIRIS_OPENAI_VISION_KEY env var.
        """
        self.api_key = api_key or os.environ.get("CIRIS_OPENAI_VISION_KEY")
        if not self.api_key:
            logger.warning("No OpenAI Vision API key found. Image processing will be disabled.")

        self.api_url = "https://api.openai.com/v1/chat/completions"
        self.model = "gpt-4o"  # Updated to current vision-capable model
        self.max_image_size = 20 * 1024 * 1024  # 20MB limit

    async def process_message_images(self, message: discord.Message) -> Optional[str]:
        """Process all images in a Discord message and return descriptions.

        Args:
            message: Discord message containing attachments

        Returns:
            Combined description of all images, or None if no images
        """
        if not self.api_key:
            return None

        if not message.attachments:
            return None

        # Filter for image attachments
        image_attachments = [
            att for att in message.attachments if att.content_type and att.content_type.startswith("image/")
        ]

        if not image_attachments:
            return None

        descriptions = []

        for attachment in image_attachments:
            try:
                description = await self._process_single_image(attachment)
                if description:
                    descriptions.append(f"Image '{attachment.filename}': {description}")
            except Exception as e:
                logger.error(f"Failed to process image {attachment.filename}: {e}")
                descriptions.append(f"Image '{attachment.filename}': [Failed to process - {str(e)}]")

        if descriptions:
            return "\n\n".join(descriptions)

        return None

    async def process_image_attachments_list(self, attachments: List[discord.Attachment]) -> Optional[str]:
        """Process a list of Discord image attachments.

        Args:
            attachments: List of Discord attachment objects (already filtered for images)

        Returns:
            Combined description of all images, or None if no images processed
        """
        if not self.api_key or not attachments:
            return None

        descriptions = []

        for attachment in attachments:
            try:
                description = await self._process_single_image(attachment)
                if description:
                    descriptions.append(f"Image '{attachment.filename}': {description}")
            except Exception as e:
                logger.error(f"Failed to process image {attachment.filename}: {e}")
                descriptions.append(f"Image '{attachment.filename}': [Failed to process - {str(e)}]")

        if descriptions:
            return "\n\n".join(descriptions)

        return None

    async def _process_single_image(self, attachment: discord.Attachment) -> Optional[str]:
        """Process a single Discord image attachment.

        Args:
            attachment: Discord attachment object

        Returns:
            Description of the image or None if failed
        """
        # Check file size
        if attachment.size > self.max_image_size:
            return f"Image too large ({attachment.size / 1024 / 1024:.1f}MB, max {self.max_image_size / 1024 / 1024}MB)"

        try:
            # Download the image
            async with aiohttp.ClientSession() as session:
                async with session.get(attachment.url) as response:
                    if response.status != 200:
                        return f"Failed to download image (HTTP {response.status})"

                    image_data = await response.read()
                    base64_image = base64.b64encode(image_data).decode("utf-8")

            # Prepare the API request
            headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}

            payload = {
                "model": self.model,
                "messages": [
                    {
                        "role": "system",
                        "content": "You are a helpful assistant that describes images clearly and concisely. Focus on the main subjects, actions, text, and any notable details.",
                    },
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": "Please describe this image in detail. If there is any text in the image, transcribe it exactly.",
                            },
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:{attachment.content_type};base64,{base64_image}"},
                            },
                        ],
                    },
                ],
                "max_tokens": 500,
            }

            # Call GPT-4 Vision API
            async with aiohttp.ClientSession() as session:
                async with session.post(self.api_url, headers=headers, json=payload) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        logger.error(f"OpenAI API error: {response.status} - {error_text}")
                        return f"API error: {response.status}"

                    result = await response.json()

                    if "choices" in result and result["choices"]:
                        content: str = result["choices"][0]["message"]["content"]
                        return content
                    else:
                        return "No description generated"

        except Exception as e:
            logger.exception(f"Error processing image with GPT-4 Vision: {e}")
            return f"Error: {str(e)}"

    async def process_embeds(self, embeds: List[discord.Embed]) -> Optional[str]:
        """Process images from Discord embeds.

        Args:
            embeds: List of Discord embeds

        Returns:
            Combined description of embed images, or None
        """
        if not self.api_key or not embeds:
            return None

        descriptions = []

        for embed in embeds:
            # Check for image in embed
            if embed.image and embed.image.url:
                description = await self._process_image_url(embed.image.url, "Embed image")
                if description:
                    descriptions.append(description)

            # Check for thumbnail
            if embed.thumbnail and embed.thumbnail.url:
                description = await self._process_image_url(embed.thumbnail.url, "Embed thumbnail")
                if description:
                    descriptions.append(description)

        if descriptions:
            return "\n\n".join(descriptions)

        return None

    async def _process_image_url(self, url: str, image_type: str = "Image") -> Optional[str]:
        """Process an image from a URL.

        Args:
            url: Image URL
            image_type: Type of image for description prefix

        Returns:
            Description with prefix, or None
        """
        try:
            # Create a mock attachment-like object
            class MockAttachment:
                def __init__(self, url: str, content_type: str = "image/png") -> None:
                    self.url = url
                    self.content_type = content_type
                    self.filename = url.split("/")[-1] or "image"
                    self.size = 0  # Unknown size for URL images

            mock = MockAttachment(url)
            description = await self._process_single_image(mock)  # type: ignore[arg-type]

            if description:
                return f"{image_type}: {description}"

        except Exception as e:
            logger.error(f"Failed to process image URL {url}: {e}")

        return None

    def is_available(self) -> bool:
        """Check if vision processing is available.

        Returns:
            True if API key is configured
        """
        return bool(self.api_key)

    def get_status(self) -> JSONDict:
        """Get current status of vision helper.

        Returns:
            Status dictionary
        """
        return {
            "available": self.is_available(),
            "model": self.model,
            "max_image_size_mb": self.max_image_size / 1024 / 1024,
            "api_key_configured": bool(self.api_key),
        }
