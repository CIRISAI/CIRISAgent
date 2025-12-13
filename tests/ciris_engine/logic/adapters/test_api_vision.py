"""Unit tests for API vision helper functionality."""

import base64
from unittest.mock import patch

import pytest

from ciris_engine.logic.adapters.api.api_vision import APIVisionHelper, get_api_vision_helper


class TestAPIVisionHelper:
    """Tests for APIVisionHelper class."""

    @pytest.fixture
    def helper(self):
        """Create helper instance."""
        return APIVisionHelper()

    def test_init_default_size(self, helper):
        """Test default max image size."""
        assert helper.max_image_size == 20 * 1024 * 1024  # 20MB

    def test_init_custom_size(self):
        """Test custom max image size."""
        helper = APIVisionHelper(max_image_size=10 * 1024 * 1024)
        assert helper.max_image_size == 10 * 1024 * 1024

    def test_is_available(self, helper):
        """Test that vision is always available."""
        assert helper.is_available() is True

    def test_get_status(self, helper):
        """Test status dictionary."""
        status = helper.get_status()
        assert status["available"] is True
        assert status["multimodal_enabled"] is True
        assert "max_image_size_mb" in status
        assert "base64" in status["supported_formats"]
        assert "url" in status["supported_formats"]


class TestBase64ToImageContent:
    """Tests for base64_to_image_content method."""

    @pytest.fixture
    def helper(self):
        """Create helper instance."""
        return APIVisionHelper()

    def test_valid_base64(self, helper):
        """Test valid base64 conversion."""
        data = base64.b64encode(b"fake image data").decode("utf-8")
        result = helper.base64_to_image_content(data, "image/jpeg", "test.jpg")

        assert result is not None
        assert result.source_type == "base64"
        assert result.media_type == "image/jpeg"
        assert result.filename == "test.jpg"
        assert result.data == data

    def test_data_url_format(self, helper):
        """Test data URL format extraction."""
        raw_data = b"image bytes"
        b64_data = base64.b64encode(raw_data).decode("utf-8")
        data_url = f"data:image/png;base64,{b64_data}"

        result = helper.base64_to_image_content(data_url, "image/jpeg")  # Will be overridden

        assert result is not None
        assert result.media_type == "image/png"  # Extracted from data URL
        assert result.data == b64_data

    def test_empty_base64(self, helper):
        """Test empty base64 data."""
        result = helper.base64_to_image_content("", "image/jpeg")
        assert result is None

    def test_invalid_base64(self, helper):
        """Test invalid base64 data."""
        result = helper.base64_to_image_content("not-valid-base64!!!", "image/jpeg")
        assert result is None

    def test_too_large(self, helper):
        """Test image too large."""
        large_data = base64.b64encode(b"x" * (helper.max_image_size + 1)).decode("utf-8")
        result = helper.base64_to_image_content(large_data, "image/jpeg")
        assert result is None

    def test_default_filename(self, helper):
        """Test default filename."""
        data = base64.b64encode(b"data").decode("utf-8")
        result = helper.base64_to_image_content(data, "image/jpeg")

        assert result is not None
        assert result.filename == "api_image"


class TestUrlToImageContentSync:
    """Tests for url_to_image_content_sync method."""

    @pytest.fixture
    def helper(self):
        """Create helper instance."""
        return APIVisionHelper()

    def test_url_storage(self, helper):
        """Test that URL is stored directly without download."""
        result = helper.url_to_image_content_sync(
            "https://example.com/image.jpg", "image/jpeg", "photo.jpg"
        )

        assert result is not None
        assert result.source_type == "url"
        assert result.data == "https://example.com/image.jpg"
        assert result.media_type == "image/jpeg"
        assert result.filename == "photo.jpg"
        assert result.size_bytes is None

    def test_url_default_filename(self, helper):
        """Test filename extraction from URL."""
        result = helper.url_to_image_content_sync("https://example.com/path/image.png", "image/png")

        assert result is not None
        assert result.filename == "image.png"

    def test_url_with_empty_path(self, helper):
        """Test URL with empty path component."""
        result = helper.url_to_image_content_sync("https://example.com/", "image/jpeg")

        assert result is not None
        assert result.filename == "url_image"  # Default when can't extract


class TestProcessImagePayload:
    """Tests for process_image_payload method."""

    @pytest.fixture
    def helper(self):
        """Create helper instance."""
        return APIVisionHelper()

    def test_detects_https_url(self, helper):
        """Test HTTPS URL detection."""
        result = helper.process_image_payload("https://example.com/image.jpg", "image/jpeg")

        assert result is not None
        assert result.source_type == "url"

    def test_detects_http_url(self, helper):
        """Test HTTP URL detection."""
        result = helper.process_image_payload("http://example.com/image.jpg", "image/jpeg")

        assert result is not None
        assert result.source_type == "url"

    def test_detects_base64(self, helper):
        """Test base64 detection."""
        data = base64.b64encode(b"image").decode("utf-8")
        result = helper.process_image_payload(data, "image/jpeg")

        assert result is not None
        assert result.source_type == "base64"


class TestProcessImageList:
    """Tests for process_image_list method."""

    @pytest.fixture
    def helper(self):
        """Create helper instance."""
        return APIVisionHelper()

    def test_empty_list(self, helper):
        """Test processing empty list."""
        result = helper.process_image_list([])
        assert result == []

    def test_valid_images(self, helper):
        """Test processing valid image list."""
        b64_data = base64.b64encode(b"image data").decode("utf-8")
        images = [
            {"data": b64_data, "media_type": "image/jpeg", "filename": "img1.jpg"},
            {"data": "https://example.com/img2.png", "media_type": "image/png"},
        ]

        result = helper.process_image_list(images)

        assert len(result) == 2
        assert result[0].filename == "img1.jpg"
        assert result[1].source_type == "url"

    def test_invalid_entry_not_dict(self, helper):
        """Test handling non-dict entry."""
        images = [
            "not a dict",
            {"data": "https://example.com/image.jpg", "media_type": "image/jpeg"},
        ]

        result = helper.process_image_list(images)

        assert len(result) == 1  # Only valid entry

    def test_missing_data_field(self, helper):
        """Test handling entry without data field."""
        images = [
            {"no_data_here": "value"},
            {"data": "https://example.com/image.jpg", "media_type": "image/jpeg"},
        ]

        result = helper.process_image_list(images)

        assert len(result) == 1

    def test_default_media_type(self, helper):
        """Test default media type for images."""
        b64_data = base64.b64encode(b"image").decode("utf-8")
        images = [{"data": b64_data}]  # No media_type specified

        result = helper.process_image_list(images)

        assert len(result) == 1
        assert result[0].media_type == "image/jpeg"  # Default

    def test_mixed_valid_invalid(self, helper):
        """Test list with mixed valid and invalid entries."""
        b64_data = base64.b64encode(b"image").decode("utf-8")
        images = [
            {"data": b64_data, "media_type": "image/jpeg"},
            123,  # Invalid
            {"missing_data": True},  # Invalid
            {"data": "https://example.com/img.png", "media_type": "image/png"},
            None,  # Invalid
        ]

        result = helper.process_image_list(images)

        assert len(result) == 2  # Only 2 valid entries


class TestGetAPIVisionHelper:
    """Tests for get_api_vision_helper singleton function."""

    def test_returns_singleton(self):
        """Test that function returns singleton instance."""
        import ciris_engine.logic.adapters.api.api_vision as module

        module._api_vision_helper = None

        helper1 = get_api_vision_helper()
        helper2 = get_api_vision_helper()

        assert helper1 is helper2

    def test_returns_api_vision_helper(self):
        """Test that function returns APIVisionHelper instance."""
        import ciris_engine.logic.adapters.api.api_vision as module

        module._api_vision_helper = None

        helper = get_api_vision_helper()
        assert isinstance(helper, APIVisionHelper)
