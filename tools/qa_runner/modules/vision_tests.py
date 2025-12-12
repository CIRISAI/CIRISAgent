"""
Vision/Multimodal QA tests.

Tests the native multimodal vision pipeline:
- API vision helper image processing
- Image attachment to IncomingMessage
- Image propagation through task/thought pipeline
- Mock LLM multimodal message detection
"""

import base64
import logging
import traceback
from typing import Any, Dict, List, Optional

import httpx
from rich.console import Console

logger = logging.getLogger(__name__)


class VisionTests:
    """Test native multimodal vision functionality."""

    def __init__(self, client: Any, console: Console):
        """Initialize vision tests.

        Args:
            client: CIRIS SDK client (authenticated)
            console: Rich console for output
        """
        self.client = client
        self.console = console
        self.results: List[Dict[str, Any]] = []

        # Extract base URL and token from client for direct HTTP calls
        # CIRISClient stores base_url directly and in _transport
        self.base_url = getattr(client, "base_url", "http://localhost:8080")
        if hasattr(client, "_transport") and hasattr(client._transport, "base_url"):
            self.base_url = client._transport.base_url

        # Extract token (api_key) from client
        # CIRISClient stores api_key on _transport
        self.token = getattr(client, "api_key", None)
        if hasattr(client, "_transport") and hasattr(client._transport, "api_key"):
            self.token = client._transport.api_key

        # Create a simple test image (1x1 red pixel PNG)
        # This is a valid minimal PNG file
        self.test_image_base64 = (
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8DwHwAFBQIA" "X8jx0gAAAABJRU5ErkJggg=="
        )

    async def run(self) -> List[Dict[str, Any]]:
        """Run all vision tests."""
        self.console.print("\n[cyan]🖼️ Testing Native Vision/Multimodal Support[/cyan]")

        tests = [
            ("API Vision Helper - Base64", self.test_api_vision_base64),
            ("API Vision Helper - Data URL", self.test_api_vision_data_url),
            ("API Vision Helper - URL", self.test_api_vision_url),
            ("Interact with Image", self.test_interact_with_image),
            ("Interact with Multiple Images", self.test_interact_multiple_images),
            ("Image Content Schema", self.test_image_content_schema),
            ("Multimodal Message Building", self.test_multimodal_message_building),
        ]

        for name, test_func in tests:
            try:
                await test_func()
                self.results.append({"test": name, "status": "✅ PASS", "error": None})
                self.console.print(f"  ✅ {name}")
            except Exception as e:
                self.results.append({"test": name, "status": "❌ FAIL", "error": str(e)})
                self.console.print(f"  ❌ {name}: {str(e)[:100]}")
                if self.console.is_terminal:
                    self.console.print(f"     [dim]{traceback.format_exc()}[/dim]")

        self._print_summary()
        return self.results

    async def test_api_vision_base64(self) -> None:
        """Test API vision helper base64 processing."""
        from ciris_engine.logic.adapters.api.api_vision import APIVisionHelper

        helper = APIVisionHelper()
        image_content = helper.base64_to_image_content(
            self.test_image_base64,
            "image/png",
            "test.png",
        )

        assert image_content is not None, "Failed to create ImageContent from base64"
        assert image_content.source_type == "base64", "Wrong source type"
        assert image_content.media_type == "image/png", "Wrong media type"
        assert image_content.filename == "test.png", "Wrong filename"
        assert image_content.size_bytes > 0, "Size should be positive"

    async def test_api_vision_data_url(self) -> None:
        """Test API vision helper data URL processing."""
        from ciris_engine.logic.adapters.api.api_vision import APIVisionHelper

        helper = APIVisionHelper()
        data_url = f"data:image/png;base64,{self.test_image_base64}"
        image_content = helper.base64_to_image_content(data_url)

        assert image_content is not None, "Failed to create ImageContent from data URL"
        assert image_content.source_type == "base64", "Wrong source type"
        assert image_content.media_type == "image/png", "Wrong media type (should extract from data URL)"

    async def test_api_vision_url(self) -> None:
        """Test API vision helper URL processing."""
        from ciris_engine.logic.adapters.api.api_vision import APIVisionHelper

        helper = APIVisionHelper()
        url = "https://example.com/image.jpg"
        image_content = helper.url_to_image_content_sync(url, "image/jpeg", "remote.jpg")

        assert image_content is not None, "Failed to create ImageContent from URL"
        assert image_content.source_type == "url", "Wrong source type"
        assert image_content.data == url, "URL not preserved"
        assert image_content.media_type == "image/jpeg", "Wrong media type"

    async def test_interact_with_image(self) -> None:
        """Test sending a message with an image through the API."""
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{self.base_url}/v1/agent/interact",
                headers={"Authorization": f"Bearer {self.token}"},
                json={
                    "message": "What do you see in this image?",
                    "images": [
                        {
                            "data": self.test_image_base64,
                            "media_type": "image/png",
                            "filename": "test_image.png",
                        }
                    ],
                },
            )

            assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
            data = response.json()

            # Verify response structure
            assert "data" in data, "Missing 'data' in response"
            assert "response" in data["data"], "Missing 'response' in data"
            assert "message_id" in data["data"], "Missing 'message_id' in data"

            # The mock LLM should have processed this - check we got a response
            assert len(data["data"]["response"]) > 0, "Empty response"
            logger.info(f"Vision interact response: {data['data']['response'][:200]}...")

            # CRITICAL: Verify that images reached the mock LLM
            # The mock LLM includes [MULTIMODAL_DETECTED:N] in its response when images are detected
            response_text = data["data"]["response"]
            assert "[MULTIMODAL_DETECTED:1]" in response_text, (
                f"Mock LLM did not detect multimodal content! Images did not reach the LLM pipeline. "
                f"Response: {response_text[:300]}"
            )

    async def test_interact_multiple_images(self) -> None:
        """Test sending multiple images in a single message."""
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{self.base_url}/v1/agent/interact",
                headers={"Authorization": f"Bearer {self.token}"},
                json={
                    "message": "Compare these two images",
                    "images": [
                        {
                            "data": self.test_image_base64,
                            "media_type": "image/png",
                            "filename": "image1.png",
                        },
                        {
                            "data": self.test_image_base64,
                            "media_type": "image/png",
                            "filename": "image2.png",
                        },
                    ],
                },
            )

            assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
            data = response.json()
            assert "data" in data, "Missing 'data' in response"
            assert "response" in data["data"], "Missing 'response' in data"

            # CRITICAL: Verify that both images reached the mock LLM
            # The mock LLM includes [MULTIMODAL_DETECTED:N] in its response when images are detected
            response_text = data["data"]["response"]
            logger.info(f"Multi-image response: {response_text[:200]}...")
            assert "[MULTIMODAL_DETECTED:2]" in response_text, (
                f"Mock LLM did not detect both images! Expected 2 images in multimodal detection. "
                f"Response: {response_text[:300]}"
            )

    async def test_image_content_schema(self) -> None:
        """Test ImageContent schema functionality."""
        from ciris_engine.schemas.runtime.models import ImageContent

        # Test base64 source
        img = ImageContent(
            source_type="base64",
            data=self.test_image_base64,
            media_type="image/png",
            filename="test.png",
            size_bytes=100,
        )

        # Test to_data_url conversion
        data_url = img.to_data_url()
        assert data_url.startswith("data:image/png;base64,"), "Wrong data URL format"
        assert self.test_image_base64 in data_url, "Base64 data not in URL"

        # Test URL source
        img_url = ImageContent(
            source_type="url",
            data="https://example.com/image.jpg",
            media_type="image/jpeg",
        )
        assert img_url.to_data_url() == "https://example.com/image.jpg", "URL should return as-is"

    async def test_multimodal_message_building(self) -> None:
        """Test DMA multimodal message building."""
        from ciris_engine.logic.dma.base_dma import BaseDMA
        from ciris_engine.schemas.runtime.models import ImageContent

        # Create test image
        img = ImageContent(
            source_type="base64",
            data=self.test_image_base64,
            media_type="image/png",
            filename="test.png",
            size_bytes=100,
        )

        # Test with images (should return list of content blocks)
        content = BaseDMA.build_multimodal_content("Describe this", [img])
        assert isinstance(content, list), "Multimodal content should be a list"
        assert len(content) == 2, "Should have text and image blocks"
        assert content[0].type == "text", "First block should be text"
        assert content[1].type == "image_url", "Second block should be image_url"

        # Test without images (should return string)
        text_content = BaseDMA.build_multimodal_content("Just text", [])
        assert isinstance(text_content, str), "Text-only content should be string"
        assert text_content == "Just text", "Text content mismatch"

    def _print_summary(self) -> None:
        """Print test summary."""
        passed = sum(1 for r in self.results if "PASS" in r["status"])
        total = len(self.results)

        self.console.print(f"\n[bold]Vision Tests: {passed}/{total} passed[/bold]")

        if passed < total:
            self.console.print("[yellow]Failed tests:[/yellow]")
            for r in self.results:
                if "FAIL" in r["status"]:
                    self.console.print(f"  - {r['test']}: {r['error']}")
