"""
Unit tests for ProcessingQueueItem and related processing queue functionality.

Tests coverage for the complex from_thought method which handles:
- Context type detection (ProcessingThoughtContext, ThoughtContext, dict)
- Content type resolution (ThoughtContent, str, dict)
- Image lookup from tasks
- All edge cases and error paths
"""

import uuid
from datetime import datetime, timezone
from typing import Optional
from unittest.mock import MagicMock, Mock, patch

import pytest

from ciris_engine.logic.processors.support.processing_queue import ProcessingQueueItem, ThoughtContent
from ciris_engine.schemas.runtime.enums import ThoughtStatus, ThoughtType
from ciris_engine.schemas.runtime.models import ImageContent, Thought, ThoughtContext

# Patch location for get_task_by_id - it's imported inside the from_thought method
TASK_LOOKUP_PATCH = "ciris_engine.logic.persistence.models.tasks.get_task_by_id"


class TestThoughtContent:
    """Tests for ThoughtContent model."""

    def test_thought_content_basic(self):
        """Test creating basic thought content."""
        content = ThoughtContent(text="Hello world")
        assert content.text == "Hello world"
        assert content.metadata == {}

    def test_thought_content_with_metadata(self):
        """Test thought content with metadata."""
        content = ThoughtContent(text="Test content", metadata={"key": "value", "count": 42})
        assert content.text == "Test content"
        assert content.metadata["key"] == "value"
        assert content.metadata["count"] == 42

    def test_thought_content_empty_text(self):
        """Test thought content with empty text."""
        content = ThoughtContent(text="")
        assert content.text == ""


class TestProcessingQueueItemBasic:
    """Tests for basic ProcessingQueueItem functionality."""

    def test_create_queue_item_minimal(self):
        """Test creating queue item with minimal fields."""
        content = ThoughtContent(text="Test content")
        item = ProcessingQueueItem(
            thought_id="thought_123",
            source_task_id="task_456",
            thought_type=ThoughtType.STANDARD,
            content=content,
        )

        assert item.thought_id == "thought_123"
        assert item.source_task_id == "task_456"
        assert item.thought_type == ThoughtType.STANDARD
        assert item.content_text == "Test content"
        assert item.agent_occurrence_id == "default"
        assert item.images == []

    def test_create_queue_item_full(self):
        """Test creating queue item with all fields."""
        content = ThoughtContent(text="Full content", metadata={"key": "value"})
        context = ThoughtContext(
            task_id="task_123",
            channel_id="channel_456",
            round_number=2,
            depth=1,
            correlation_id="corr_789",
            agent_occurrence_id="occ_001",
        )
        image = ImageContent(
            source_type="base64",
            data="base64data",
            media_type="image/jpeg",
            filename="test.jpg",
            size_bytes=1024,
        )

        item = ProcessingQueueItem(
            thought_id="thought_123",
            source_task_id="task_456",
            thought_type=ThoughtType.GUIDANCE,
            content=content,
            agent_occurrence_id="occ_001",
            raw_input_string="Original input",
            initial_context=context,
            ponder_notes=["Note 1", "Note 2"],
            conscience_feedback={"approved": True},
            images=[image],
        )

        assert item.thought_type == ThoughtType.GUIDANCE
        assert item.agent_occurrence_id == "occ_001"
        assert item.raw_input_string == "Original input"
        assert item.initial_context == context
        assert item.ponder_notes == ["Note 1", "Note 2"]
        assert item.conscience_feedback == {"approved": True}
        assert len(item.images) == 1
        assert item.images[0].filename == "test.jpg"

    def test_content_text_property(self):
        """Test content_text property returns text from content."""
        content = ThoughtContent(text="Property test")
        item = ProcessingQueueItem(
            thought_id="t1",
            source_task_id="task1",
            thought_type=ThoughtType.STANDARD,
            content=content,
        )
        assert item.content_text == "Property test"


class TestProcessingQueueItemFromThought:
    """Tests for ProcessingQueueItem.from_thought class method."""

    @pytest.fixture
    def base_thought(self):
        """Create a base thought for testing."""
        return Thought(
            thought_id="thought_123",
            source_task_id="task_456",
            agent_occurrence_id="occ_001",
            thought_type=ThoughtType.STANDARD,
            status=ThoughtStatus.PENDING,
            created_at=datetime.now(timezone.utc).isoformat(),
            updated_at=datetime.now(timezone.utc).isoformat(),
            round_number=1,
            content="Thought content",
            thought_depth=0,
        )

    def test_from_thought_basic(self, base_thought):
        """Test basic thought to queue item conversion."""
        with patch(TASK_LOOKUP_PATCH) as mock_get_task:
            mock_get_task.return_value = None

            item = ProcessingQueueItem.from_thought(base_thought)

            assert item.thought_id == "thought_123"
            assert item.source_task_id == "task_456"
            assert item.thought_type == ThoughtType.STANDARD
            assert item.agent_occurrence_id == "occ_001"
            assert item.content_text == "Thought content"

    def test_from_thought_with_thought_context(self, base_thought):
        """Test conversion with ThoughtContext."""
        context = ThoughtContext(
            task_id="task_456",
            channel_id="channel_789",
            round_number=2,
            depth=1,
            correlation_id="corr_123",
            agent_occurrence_id="occ_001",
        )
        base_thought.context = context

        with patch(TASK_LOOKUP_PATCH) as mock_get_task:
            mock_get_task.return_value = None

            item = ProcessingQueueItem.from_thought(base_thought)

            assert item.initial_context == context
            assert item.initial_context.channel_id == "channel_789"

    def test_from_thought_with_pydantic_context(self, base_thought):
        """Test conversion with a Pydantic model context that has model_dump."""
        # Create a ThoughtContext (which has model_dump method)
        context = ThoughtContext(
            task_id="task_456",
            channel_id="channel_pydantic",
            round_number=3,
            depth=2,
            correlation_id="proc_corr_123",
            agent_occurrence_id="occ_001",
        )
        base_thought.context = context

        with patch(TASK_LOOKUP_PATCH) as mock_get_task:
            mock_get_task.return_value = None

            item = ProcessingQueueItem.from_thought(base_thought)

            assert item.initial_context == context
            assert hasattr(item.initial_context, "model_dump")

    def test_from_thought_with_dict_context(self, base_thought):
        """Test conversion with dict context."""
        context_dict = {
            "task_id": "task_456",
            "channel_id": "channel_dict",
            "round_number": 4,
        }
        base_thought.context = context_dict

        with patch(TASK_LOOKUP_PATCH) as mock_get_task:
            mock_get_task.return_value = None

            item = ProcessingQueueItem.from_thought(base_thought)

            assert item.initial_context == context_dict

    def test_from_thought_with_none_context(self, base_thought):
        """Test conversion with None context."""
        base_thought.context = None

        with patch(TASK_LOOKUP_PATCH) as mock_get_task:
            mock_get_task.return_value = None

            item = ProcessingQueueItem.from_thought(base_thought)

            assert item.initial_context is None

    def test_from_thought_with_explicit_initial_context(self, base_thought):
        """Test that explicit initial_ctx parameter overrides thought context."""
        thought_context = ThoughtContext(
            task_id="task_456",
            channel_id="thought_channel",
            round_number=1,
            depth=0,
            correlation_id="thought_corr",
            agent_occurrence_id="occ_001",
        )
        base_thought.context = thought_context

        explicit_ctx = {"explicit": "context", "priority": "high"}

        with patch(TASK_LOOKUP_PATCH) as mock_get_task:
            mock_get_task.return_value = None

            item = ProcessingQueueItem.from_thought(base_thought, initial_ctx=explicit_ctx)

            assert item.initial_context == explicit_ctx
            assert item.initial_context.get("explicit") == "context"

    def test_from_thought_content_as_thought_content(self, base_thought):
        """Test content override with ThoughtContent object."""
        override_content = ThoughtContent(text="Override content", metadata={"override": True})

        with patch(TASK_LOOKUP_PATCH) as mock_get_task:
            mock_get_task.return_value = None

            item = ProcessingQueueItem.from_thought(base_thought, queue_item_content=override_content)

            assert item.content_text == "Override content"
            assert item.content.metadata["override"] is True

    def test_from_thought_content_as_string(self, base_thought):
        """Test content override with string."""
        with patch(TASK_LOOKUP_PATCH) as mock_get_task:
            mock_get_task.return_value = None

            item = ProcessingQueueItem.from_thought(base_thought, queue_item_content="String content override")

            assert item.content_text == "String content override"

    def test_from_thought_content_as_dict(self, base_thought):
        """Test content override with dict."""
        content_dict = {"text": "Dict content", "metadata": {"from": "dict"}}

        with patch(TASK_LOOKUP_PATCH) as mock_get_task:
            mock_get_task.return_value = None

            item = ProcessingQueueItem.from_thought(base_thought, queue_item_content=content_dict)

            assert item.content_text == "Dict content"
            assert item.content.metadata["from"] == "dict"

    def test_from_thought_with_raw_input(self, base_thought):
        """Test with explicit raw_input parameter."""
        with patch(TASK_LOOKUP_PATCH) as mock_get_task:
            mock_get_task.return_value = None

            item = ProcessingQueueItem.from_thought(base_thought, raw_input="Custom raw input")

            assert item.raw_input_string == "Custom raw input"

    def test_from_thought_raw_input_defaults_to_content(self, base_thought):
        """Test that raw_input defaults to thought content when not provided."""
        with patch(TASK_LOOKUP_PATCH) as mock_get_task:
            mock_get_task.return_value = None

            item = ProcessingQueueItem.from_thought(base_thought)

            assert item.raw_input_string == "Thought content"

    def test_from_thought_with_ponder_notes(self, base_thought):
        """Test conversion preserves ponder notes."""
        base_thought.ponder_notes = ["Question 1", "Question 2", "Question 3"]

        with patch(TASK_LOOKUP_PATCH) as mock_get_task:
            mock_get_task.return_value = None

            item = ProcessingQueueItem.from_thought(base_thought)

            assert item.ponder_notes == ["Question 1", "Question 2", "Question 3"]

    def test_from_thought_inherits_images_from_task(self, base_thought):
        """Test that images are inherited from task."""
        mock_task = Mock()
        mock_task.images = [
            ImageContent(
                source_type="base64",
                data="task_image_data",
                media_type="image/png",
                filename="task_image.png",
                size_bytes=2048,
            )
        ]

        with patch(TASK_LOOKUP_PATCH) as mock_get_task:
            mock_get_task.return_value = mock_task

            item = ProcessingQueueItem.from_thought(base_thought)

            assert len(item.images) == 1
            assert item.images[0].filename == "task_image.png"
            assert item.images[0].media_type == "image/png"

    def test_from_thought_with_explicit_task_images(self, base_thought):
        """Test explicit task_images parameter overrides lookup."""
        explicit_images = [
            ImageContent(
                source_type="url",
                data="https://example.com/image.jpg",
                media_type="image/jpeg",
                filename="explicit.jpg",
                size_bytes=None,
            )
        ]

        with patch(TASK_LOOKUP_PATCH) as mock_get_task:
            # This should NOT be called when task_images is provided
            mock_get_task.return_value = None

            item = ProcessingQueueItem.from_thought(base_thought, task_images=explicit_images)

            assert len(item.images) == 1
            assert item.images[0].filename == "explicit.jpg"
            assert item.images[0].source_type == "url"

    def test_from_thought_task_lookup_no_images(self, base_thought):
        """Test when task exists but has no images."""
        mock_task = Mock()
        mock_task.images = None

        with patch(TASK_LOOKUP_PATCH) as mock_get_task:
            mock_get_task.return_value = mock_task

            item = ProcessingQueueItem.from_thought(base_thought)

            assert item.images == []

    def test_from_thought_task_lookup_empty_images(self, base_thought):
        """Test when task exists with empty images list."""
        mock_task = Mock()
        mock_task.images = []

        with patch(TASK_LOOKUP_PATCH) as mock_get_task:
            mock_get_task.return_value = mock_task

            item = ProcessingQueueItem.from_thought(base_thought)

            assert item.images == []

    def test_from_thought_task_lookup_failure(self, base_thought):
        """Test handling of task lookup failure."""
        with patch(TASK_LOOKUP_PATCH) as mock_get_task:
            mock_get_task.side_effect = Exception("Database error")

            # Should not raise, just log warning and have empty images
            item = ProcessingQueueItem.from_thought(base_thought)

            assert item.images == []

    def test_from_thought_task_not_found(self, base_thought):
        """Test when task is not found."""
        with patch(TASK_LOOKUP_PATCH) as mock_get_task:
            mock_get_task.return_value = None

            item = ProcessingQueueItem.from_thought(base_thought)

            assert item.images == []

    def test_from_thought_with_multiple_images(self, base_thought):
        """Test with multiple images from task."""
        mock_task = Mock()
        mock_task.images = [
            ImageContent(
                source_type="base64",
                data="data1",
                media_type="image/jpeg",
                filename="image1.jpg",
                size_bytes=1000,
            ),
            ImageContent(
                source_type="base64",
                data="data2",
                media_type="image/png",
                filename="image2.png",
                size_bytes=2000,
            ),
            ImageContent(
                source_type="url",
                data="https://example.com/image3.gif",
                media_type="image/gif",
                filename="image3.gif",
                size_bytes=None,
            ),
        ]

        with patch(TASK_LOOKUP_PATCH) as mock_get_task:
            mock_get_task.return_value = mock_task

            item = ProcessingQueueItem.from_thought(base_thought)

            assert len(item.images) == 3
            assert item.images[0].filename == "image1.jpg"
            assert item.images[1].filename == "image2.png"
            assert item.images[2].filename == "image3.gif"

    def test_from_thought_context_with_model_dump(self, base_thought):
        """Test context with model_dump method (Pydantic models)."""
        # The code detects objects with model_dump as valid contexts
        # Use a real ThoughtContext which has model_dump
        real_context = ThoughtContext(
            task_id="task_456",
            channel_id="model_dump_channel",
            round_number=5,
            depth=3,
            correlation_id="model_dump_corr",
            agent_occurrence_id="occ_001",
        )
        base_thought.context = real_context

        with patch(TASK_LOOKUP_PATCH) as mock_get_task:
            mock_get_task.return_value = None

            item = ProcessingQueueItem.from_thought(base_thought)

            # Should accept context with model_dump
            assert item.initial_context == real_context
            assert hasattr(item.initial_context, "model_dump")

    def test_from_thought_unsupported_context_type(self, base_thought):
        """Test handling of unsupported context type."""
        # Use a type that doesn't match any expected pattern
        base_thought.context = 12345  # Integer, not a valid context

        with patch(TASK_LOOKUP_PATCH) as mock_get_task:
            mock_get_task.return_value = None

            item = ProcessingQueueItem.from_thought(base_thought)

            # Should be None for unsupported types
            assert item.initial_context is None


class TestProcessingQueueItemAllThoughtTypes:
    """Tests for all thought types."""

    @pytest.fixture
    def create_thought(self):
        """Factory to create thoughts with specific types."""

        def _create(thought_type: ThoughtType):
            return Thought(
                thought_id=f"thought_{thought_type.value}",
                source_task_id="task_123",
                agent_occurrence_id="default",
                thought_type=thought_type,
                status=ThoughtStatus.PENDING,
                created_at=datetime.now(timezone.utc).isoformat(),
                updated_at=datetime.now(timezone.utc).isoformat(),
                round_number=0,
                content=f"Content for {thought_type.value}",
                thought_depth=0,
            )

        return _create

    @pytest.mark.parametrize(
        "thought_type",
        [
            ThoughtType.STANDARD,
            ThoughtType.FOLLOW_UP,
            ThoughtType.GUIDANCE,
            ThoughtType.MEMORY,
        ],
    )
    def test_from_thought_all_types(self, create_thought, thought_type):
        """Test conversion works for all thought types."""
        thought = create_thought(thought_type)

        with patch(TASK_LOOKUP_PATCH) as mock_get_task:
            mock_get_task.return_value = None

            item = ProcessingQueueItem.from_thought(thought)

            assert item.thought_type == thought_type
            assert item.content_text == f"Content for {thought_type.value}"


class TestProcessingQueueItemEdgeCases:
    """Edge case tests for ProcessingQueueItem."""

    def test_empty_content_thought(self):
        """Test thought with empty content."""
        thought = Thought(
            thought_id="empty_thought",
            source_task_id="task_123",
            agent_occurrence_id="default",
            thought_type=ThoughtType.STANDARD,
            status=ThoughtStatus.PENDING,
            created_at=datetime.now(timezone.utc).isoformat(),
            updated_at=datetime.now(timezone.utc).isoformat(),
            round_number=0,
            content="",
            thought_depth=0,
        )

        with patch(TASK_LOOKUP_PATCH) as mock_get_task:
            mock_get_task.return_value = None

            item = ProcessingQueueItem.from_thought(thought)

            assert item.content_text == ""

    def test_unicode_content_thought(self):
        """Test thought with unicode content."""
        unicode_content = "Hello 世界! 🌍 Привет мир!"
        thought = Thought(
            thought_id="unicode_thought",
            source_task_id="task_123",
            agent_occurrence_id="default",
            thought_type=ThoughtType.STANDARD,
            status=ThoughtStatus.PENDING,
            created_at=datetime.now(timezone.utc).isoformat(),
            updated_at=datetime.now(timezone.utc).isoformat(),
            round_number=0,
            content=unicode_content,
            thought_depth=0,
        )

        with patch(TASK_LOOKUP_PATCH) as mock_get_task:
            mock_get_task.return_value = None

            item = ProcessingQueueItem.from_thought(thought)

            assert item.content_text == unicode_content

    def test_very_long_content(self):
        """Test thought with very long content."""
        long_content = "A" * 100000  # 100KB of text
        thought = Thought(
            thought_id="long_thought",
            source_task_id="task_123",
            agent_occurrence_id="default",
            thought_type=ThoughtType.STANDARD,
            status=ThoughtStatus.PENDING,
            created_at=datetime.now(timezone.utc).isoformat(),
            updated_at=datetime.now(timezone.utc).isoformat(),
            round_number=0,
            content=long_content,
            thought_depth=0,
        )

        with patch(TASK_LOOKUP_PATCH) as mock_get_task:
            mock_get_task.return_value = None

            item = ProcessingQueueItem.from_thought(thought)

            assert len(item.content_text) == 100000

    def test_special_occurrence_ids(self):
        """Test with special occurrence IDs like __shared__."""
        thought = Thought(
            thought_id="shared_thought",
            source_task_id="task_123",
            agent_occurrence_id="__shared__",
            thought_type=ThoughtType.STANDARD,
            status=ThoughtStatus.PENDING,
            created_at=datetime.now(timezone.utc).isoformat(),
            updated_at=datetime.now(timezone.utc).isoformat(),
            round_number=0,
            content="Shared content",
            thought_depth=0,
        )

        with patch(TASK_LOOKUP_PATCH) as mock_get_task:
            mock_get_task.return_value = None

            item = ProcessingQueueItem.from_thought(thought)

            assert item.agent_occurrence_id == "__shared__"

    def test_high_round_thought(self):
        """Test thought with high round number value."""
        thought = Thought(
            thought_id="many_rounds_thought",
            source_task_id="task_123",
            agent_occurrence_id="default",
            thought_type=ThoughtType.FOLLOW_UP,
            status=ThoughtStatus.PENDING,
            created_at=datetime.now(timezone.utc).isoformat(),
            updated_at=datetime.now(timezone.utc).isoformat(),
            round_number=100,  # High round number is fine
            content="Many rounds content",
            thought_depth=5,  # Max depth is 7
        )

        with patch(TASK_LOOKUP_PATCH) as mock_get_task:
            mock_get_task.return_value = None

            item = ProcessingQueueItem.from_thought(thought)

            assert item.thought_id == "many_rounds_thought"

    def test_many_ponder_notes(self):
        """Test thought with many ponder notes."""
        thought = Thought(
            thought_id="pondering_thought",
            source_task_id="task_123",
            agent_occurrence_id="default",
            thought_type=ThoughtType.STANDARD,
            status=ThoughtStatus.PENDING,
            created_at=datetime.now(timezone.utc).isoformat(),
            updated_at=datetime.now(timezone.utc).isoformat(),
            round_number=0,
            content="Pondering content",
            thought_depth=0,
            ponder_notes=[f"Note {i}" for i in range(100)],
        )

        with patch(TASK_LOOKUP_PATCH) as mock_get_task:
            mock_get_task.return_value = None

            item = ProcessingQueueItem.from_thought(thought)

            assert len(item.ponder_notes) == 100
