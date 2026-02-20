"""
Vision/Multimodal QA tests.

Tests the native multimodal vision pipeline:
- API vision helper image processing
- Image attachment to IncomingMessage
- Image propagation through task/thought pipeline
- Mock LLM multimodal message detection
"""

import asyncio
import logging
import traceback
from typing import Any, Dict, List, Optional

import httpx
from rich.console import Console

from .filter_test_helper import FilterTestHelper

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

        # SSE helper for waiting on task completion
        self.sse_helper: Optional[FilterTestHelper] = None

    async def run(self) -> List[Dict[str, Any]]:
        """Run all vision tests."""
        self.console.print("\n[cyan]🖼️ Testing Native Vision/Multimodal Support[/cyan]")

        # Start SSE monitoring for interact tests
        if self.token:
            self.sse_helper = FilterTestHelper(self.base_url, self.token, verbose=False)
            try:
                self.sse_helper.start_monitoring()
            except Exception as e:
                logger.warning(f"Could not start SSE monitoring: {e}")
                self.sse_helper = None

        tests = [
            ("API Vision Helper - Base64", self.test_api_vision_base64),
            ("API Vision Helper - Data URL", self.test_api_vision_data_url),
            ("API Vision Helper - URL", self.test_api_vision_url),
            # Run multi-image test FIRST to avoid task overlap with single image test
            ("Interact with Multiple Images", self.test_interact_multiple_images),
            ("Interact with Image", self.test_interact_with_image),
            ("Image Content Schema", self.test_image_content_schema),
            ("Multimodal Message Building", self.test_multimodal_message_building),
        ]

        try:
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
        finally:
            # Stop SSE monitoring
            if self.sse_helper:
                self.sse_helper.stop_monitoring()

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
        from datetime import datetime, timezone

        # Wait for any existing tasks to complete before starting
        if self.sse_helper:
            # Give time for any previous tasks to complete
            logger.info("Waiting for any active tasks to complete before vision test...")
            self.sse_helper.wait_for_task_complete(timeout=10.0)
            # Small delay to ensure clean state
            await asyncio.sleep(1.0)
            # Reset flags for this test
            self.sse_helper.task_complete_seen = False
            self.sse_helper.completed_tasks.clear()

        # Record submission time BEFORE sending - used to filter history
        submission_time = datetime.now(timezone.utc)

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

            response_text = data["data"]["response"]

            # If we got "Still processing", wait for TASK_COMPLETE via SSE then get history
            if "Still processing" in response_text and self.sse_helper:
                logger.info("Response is 'Still processing', waiting for TASK_COMPLETE via SSE...")
                completed = self.sse_helper.wait_for_task_complete(timeout=45.0)
                if completed:
                    # Get the actual response from history - FILTER BY TIMESTAMP
                    history = await self.client.agent.get_history(limit=10)
                    for msg in history.messages:
                        # Must be agent message AFTER our submission time
                        msg_time = getattr(msg, "timestamp", None) or getattr(msg, "created_at", None)
                        if msg_time:
                            if isinstance(msg_time, str):
                                msg_time = datetime.fromisoformat(msg_time.replace("Z", "+00:00"))
                            if msg.is_agent and msg_time > submission_time and "Still processing" not in msg.content:
                                response_text = msg.content
                                logger.info(
                                    f"Found response from history after {submission_time}: {response_text[:100]}..."
                                )
                                break

            # The mock LLM should have processed this - check we got a response
            assert len(response_text) > 0, "Empty response"
            logger.info(f"Vision interact response: {response_text[:200]}...")

            # CRITICAL: Verify that images reached the mock LLM
            # The mock LLM includes [MULTIMODAL_DETECTED:N] in its response when images are detected
            assert "[MULTIMODAL_DETECTED:1]" in response_text, (
                f"Mock LLM did not detect multimodal content! Images did not reach the LLM pipeline. "
                f"Response: {response_text[:300]}"
            )

            # CRITICAL: Always wait for task completion before test ends
            # This ensures the task is marked COMPLETE in the database before the next test starts
            if self.sse_helper and not self.sse_helper.task_complete_seen:
                logger.info("Waiting for task completion before test ends...")
                self.sse_helper.wait_for_task_complete(timeout=30.0)
                # Extra delay to ensure database is updated
                await asyncio.sleep(1.0)

    async def test_interact_multiple_images(self) -> None:
        """Test sending multiple images in a single message."""
        from datetime import datetime, timezone

        # Wait for any existing tasks to complete before starting
        if self.sse_helper:
            # Give time for any previous tasks to complete (including follow-up thoughts)
            logger.info("Waiting for any active tasks to complete before multi-image vision test...")
            self.sse_helper.wait_for_task_complete(timeout=30.0)
            # Longer delay to ensure all follow-up thoughts complete
            await asyncio.sleep(3.0)
            # Reset flags for this test
            self.sse_helper.task_complete_seen = False
            self.sse_helper.completed_tasks.clear()

        # Record submission time BEFORE sending - used to filter history
        submission_time = datetime.now(timezone.utc)
        waited_for_completion = False

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

            response_text = data["data"]["response"]

            # If we got "Still processing", wait for TASK_COMPLETE via SSE then get history
            if "Still processing" in response_text and self.sse_helper:
                logger.info("Response is 'Still processing', waiting for TASK_COMPLETE via SSE...")
                completed = self.sse_helper.wait_for_task_complete(timeout=45.0)
                waited_for_completion = True
                if completed:
                    # Get the actual response from history - FILTER BY TIMESTAMP
                    history = await self.client.agent.get_history(limit=10)
                    for msg in history.messages:
                        # Must be agent message AFTER our submission time
                        msg_time = getattr(msg, "timestamp", None) or getattr(msg, "created_at", None)
                        if msg_time:
                            if isinstance(msg_time, str):
                                msg_time = datetime.fromisoformat(msg_time.replace("Z", "+00:00"))
                            if msg.is_agent and msg_time > submission_time and "Still processing" not in msg.content:
                                response_text = msg.content
                                logger.info(
                                    f"Found response from history after {submission_time}: {response_text[:100]}..."
                                )
                                break

            logger.info(f"Multi-image response: {response_text[:200]}...")

            # CRITICAL: Verify that both images reached the mock LLM
            # The mock LLM includes [MULTIMODAL_DETECTED:N] in its response when images are detected
            assert "[MULTIMODAL_DETECTED:2]" in response_text, (
                f"Mock LLM did not detect both images! Expected 2 images in multimodal detection. "
                f"Response: {response_text[:300]}"
            )

        # CRITICAL: Always wait for task completion before test ends (outside httpx context)
        # This ensures the task is marked COMPLETE in the database before the next test starts
        # Only wait if we didn't already wait in the "Still processing" branch
        if self.sse_helper and not waited_for_completion:
            logger.info("Waiting for task completion before multi-image test ends...")
            # Wait for the TASK_COMPLETE that follows SPEAK
            completed = self.sse_helper.wait_for_task_complete(timeout=45.0)
            if completed:
                logger.info("Multi-image task completed successfully")
            else:
                logger.warning("Multi-image task completion timeout - proceeding anyway")
        # Extra delay to ensure database is fully updated
        await asyncio.sleep(2.0)

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

        # Test with images (should return list of content block dicts)
        content = BaseDMA.build_multimodal_content("Describe this", [img])
        assert isinstance(content, list), "Multimodal content should be a list"
        assert len(content) == 2, "Should have text and image blocks"
        # Content blocks are serialized dicts (via model_dump), not objects
        assert content[0]["type"] == "text", "First block should be text"
        assert content[1]["type"] == "image_url", "Second block should be image_url"

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
