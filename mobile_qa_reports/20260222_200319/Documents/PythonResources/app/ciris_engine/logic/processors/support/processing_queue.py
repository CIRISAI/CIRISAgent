import collections
import logging
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field

from ciris_engine.schemas.runtime.enums import ThoughtType
from ciris_engine.schemas.runtime.models import ImageContent, Thought, ThoughtContext

# Import both types of ThoughtContext
from ciris_engine.schemas.runtime.processing_context import ProcessingThoughtContext
from ciris_engine.schemas.types import JSONDict

logger = logging.getLogger(__name__)


class ThoughtContent(BaseModel):
    """Typed content for a thought."""

    text: str
    metadata: JSONDict = Field(default_factory=dict)


class ProcessingQueueItem(BaseModel):
    """
    Represents an item loaded into an in-memory processing queue (e.g., collections.deque).
    This is a lightweight representation derived from a Thought, optimized for queue processing.
    """

    thought_id: str
    source_task_id: str
    thought_type: ThoughtType  # Corresponds to Thought.thought_type
    content: ThoughtContent
    agent_occurrence_id: str = Field(
        default="default", description="Agent occurrence ID that owns this thought (multi-occurrence support)"
    )
    thought_depth: int = Field(
        ..., ge=0, le=7, description="Current thought depth in the processing chain (REQUIRED, never defaults)"
    )
    raw_input_string: Optional[str] = Field(
        default=None, description="The original input string that generated this thought, if applicable."
    )
    initial_context: Optional[Union[JSONDict, ProcessingThoughtContext, ThoughtContext]] = Field(
        default=None, description="Initial context when the thought was first received/generated for processing."
    )
    ponder_notes: Optional[List[str]] = Field(
        default=None, description="Key questions from a previous Ponder action if this item is being re-queued."
    )
    conscience_feedback: Optional[Any] = Field(
        default=None, description="conscience evaluation feedback if applicable."
    )
    images: List[ImageContent] = Field(
        default_factory=list, description="Images attached to this thought for multimodal processing"
    )

    @property
    def content_text(self) -> str:
        """Return a best-effort text representation of the content."""
        return self.content.text

    @staticmethod
    def _resolve_initial_context(
        initial_ctx: Optional[JSONDict], thought_context: Any
    ) -> Optional[Union[JSONDict, ProcessingThoughtContext, ThoughtContext]]:
        """Resolve the initial context from provided context or thought context."""
        raw_ctx = initial_ctx if initial_ctx is not None else thought_context
        if hasattr(raw_ctx, "model_dump") or isinstance(raw_ctx, (dict, ProcessingThoughtContext, ThoughtContext)):
            return raw_ctx
        return None

    @staticmethod
    def _resolve_content(
        queue_item_content: Optional[Union[ThoughtContent, str, JSONDict]], thought_content: Any
    ) -> ThoughtContent:
        """Resolve content to ThoughtContent from various input types."""
        raw_content = queue_item_content if queue_item_content is not None else thought_content
        if isinstance(raw_content, ThoughtContent):
            return raw_content
        if isinstance(raw_content, str):
            return ThoughtContent(text=raw_content)
        return ThoughtContent(**raw_content)

    @staticmethod
    def _load_task_images(
        task_images: Optional[List[ImageContent]], source_task_id: str, agent_occurrence_id: str, thought_id: str
    ) -> List[ImageContent]:
        """Load images from task if not explicitly provided."""
        if task_images is not None:
            return task_images
        try:
            from ciris_engine.logic.persistence.models.tasks import get_task_by_id

            task = get_task_by_id(source_task_id, agent_occurrence_id)
            if task and task.images:
                logger.info(
                    f"[VISION] ProcessingQueueItem inheriting {len(task.images)} images from task {source_task_id}"
                )
                return task.images
        except Exception as e:
            logger.warning(f"Failed to load task images for thought {thought_id}: {e}")
        return []

    @classmethod
    def from_thought(
        cls,
        thought_instance: Thought,
        raw_input: Optional[str] = None,
        initial_ctx: Optional[JSONDict] = None,
        queue_item_content: Optional[Union[ThoughtContent, str, JSONDict]] = None,
        task_images: Optional[List[ImageContent]] = None,
    ) -> "ProcessingQueueItem":
        """
        Creates a ProcessingQueueItem from a Thought instance.

        Args:
            thought_instance: The thought to create a queue item from
            raw_input: Optional raw input string
            initial_ctx: Optional initial context
            queue_item_content: Optional content override
            task_images: Optional list of images from the source task. If not provided,
                        the method will attempt to look up the task and get its images.
        """
        return cls(
            thought_id=thought_instance.thought_id,
            source_task_id=thought_instance.source_task_id,
            thought_type=thought_instance.thought_type,
            content=cls._resolve_content(queue_item_content, thought_instance.content),
            agent_occurrence_id=thought_instance.agent_occurrence_id,
            thought_depth=thought_instance.thought_depth,
            raw_input_string=raw_input if raw_input is not None else str(thought_instance.content),
            initial_context=cls._resolve_initial_context(initial_ctx, thought_instance.context),
            ponder_notes=thought_instance.ponder_notes,
            images=cls._load_task_images(
                task_images,
                thought_instance.source_task_id,
                thought_instance.agent_occurrence_id,
                thought_instance.thought_id,
            ),
        )


ProcessingQueue = collections.deque[ProcessingQueueItem]
