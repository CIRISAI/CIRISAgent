"""API Vision Helper for native multimodal image processing.

Extends BaseVisionHelper to provide API-specific image handling.
Images can be submitted as base64 data or URLs in the interact endpoint.
"""

import base64
import logging
from typing import Any, Dict, List, Optional

from ciris_engine.logic.adapters.base_vision import BaseVisionHelper
from ciris_engine.schemas.runtime.models import ImageContent
from ciris_engine.schemas.types import JSONDict

logger = logging.getLogger(__name__)

# Default media type for images
DEFAULT_IMAGE_MEDIA_TYPE = "image/jpeg"


class APIVisionHelper(BaseVisionHelper):
    """
    Helper class for processing API images via native multimodal.

    Converts API image payloads to ImageContent objects that flow through
    the pipeline to vision-capable LLMs (Llama 4, GPT-4o, Claude, etc).

    Inherits from BaseVisionHelper for common image conversion functionality.
    """

    def __init__(self, max_image_size: int = 20 * 1024 * 1024):
        """Initialize the vision helper.

        Args:
            max_image_size: Maximum allowed image size in bytes (default 20MB)
        """
        super().__init__(max_image_size=max_image_size)

    def base64_to_image_content(
        self,
        base64_data: str,
        media_type: str = DEFAULT_IMAGE_MEDIA_TYPE,
        filename: Optional[str] = None,
    ) -> Optional[ImageContent]:
        """
        Convert base64 string to ImageContent object.

        Args:
            base64_data: Base64-encoded image data (with or without data URL prefix)
            media_type: MIME type of the image
            filename: Optional filename

        Returns:
            ImageContent object or None if conversion failed
        """
        try:
            # Handle data URL format: data:image/jpeg;base64,/9j/4AAQ...
            if base64_data.startswith("data:"):
                # Extract media type and data from data URL
                header, data = base64_data.split(",", 1)
                if ";" in header:
                    media_type = header.split(":")[1].split(";")[0]
                base64_data = data

            # Validate base64 by decoding
            try:
                decoded = base64.b64decode(base64_data)
                size_bytes = len(decoded)
                if size_bytes == 0:
                    logger.warning("Empty base64 data (0 bytes)")
                    return None
            except Exception as e:
                logger.error(f"Invalid base64 data: {e}")
                return None

            # Check size
            if size_bytes > self.max_image_size:
                logger.warning(f"Image too large: {size_bytes} bytes (max {self.max_image_size} bytes)")
                return None

            return ImageContent(
                source_type="base64",
                data=base64_data,
                media_type=media_type,
                filename=filename or "api_image",
                size_bytes=size_bytes,
            )

        except Exception as e:
            logger.exception(f"Error converting base64 to ImageContent: {e}")
            return None

    def url_to_image_content_sync(
        self,
        url: str,
        media_type: str = DEFAULT_IMAGE_MEDIA_TYPE,
        filename: Optional[str] = None,
    ) -> ImageContent:
        """
        Create ImageContent from URL (stores URL directly, no download).

        For API requests, we store the URL and let the LLM fetch it directly
        since many vision APIs support URL-based image input.

        Args:
            url: URL of the image
            media_type: MIME type of the image
            filename: Optional filename

        Returns:
            ImageContent object with URL source type
        """
        return ImageContent(
            source_type="url",
            data=url,
            media_type=media_type,
            filename=filename or url.split("/")[-1] or "url_image",
            size_bytes=None,  # Unknown for URL images
        )

    def process_image_payload(
        self,
        image_data: str,
        media_type: str = DEFAULT_IMAGE_MEDIA_TYPE,
        filename: Optional[str] = None,
    ) -> Optional[ImageContent]:
        """
        Process an image payload from the API (auto-detect base64 vs URL).

        Args:
            image_data: Either base64-encoded data or a URL
            media_type: MIME type of the image
            filename: Optional filename

        Returns:
            ImageContent object or None if processing failed
        """
        # Detect URL vs base64 (checking format, not making connections)
        if image_data.startswith(("http://", "https://")):  # NOSONAR - format detection only
            return self.url_to_image_content_sync(image_data, media_type, filename)
        else:
            return self.base64_to_image_content(image_data, media_type, filename)

    def process_image_list(
        self,
        images: List[Dict[str, Any]],
    ) -> List[ImageContent]:
        """
        Process a list of image payloads from the API.

        Each image dict should have:
        - data: base64 string or URL
        - media_type: (optional) MIME type, defaults to image/jpeg
        - filename: (optional) filename

        Args:
            images: List of image dictionaries

        Returns:
            List of ImageContent objects
        """
        result: List[ImageContent] = []

        for img in images:
            if not isinstance(img, dict):
                logger.warning(f"Invalid image entry (not a dict): {type(img)}")
                continue

            data = img.get("data")
            if not data:
                logger.warning("Image entry missing 'data' field")
                continue

            media_type = img.get("media_type", DEFAULT_IMAGE_MEDIA_TYPE)
            filename = img.get("filename")

            image_content = self.process_image_payload(data, media_type, filename)
            if image_content:
                result.append(image_content)

        logger.info(f"Processed {len(result)} images from API payload")
        return result

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
            "supported_formats": ["base64", "url", "data_url"],
        }


# Singleton instance
_api_vision_helper: Optional[APIVisionHelper] = None


def get_api_vision_helper() -> APIVisionHelper:
    """Get or create the API vision helper singleton."""
    global _api_vision_helper
    if _api_vision_helper is None:
        _api_vision_helper = APIVisionHelper()
    return _api_vision_helper
