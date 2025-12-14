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
        raw_initial_ctx = initial_ctx if initial_ctx is not None else thought_instance.context
        # Accept ProcessingThoughtContext, ThoughtContext, dict, or any Pydantic model
        if hasattr(raw_initial_ctx, "model_dump") or isinstance(
            raw_initial_ctx, (dict, ProcessingThoughtContext, ThoughtContext)
        ):
            final_initial_ctx = raw_initial_ctx
        else:
            final_initial_ctx = None

        raw_content = queue_item_content if queue_item_content is not None else thought_instance.content
        if isinstance(raw_content, ThoughtContent):
            resolved_content = raw_content
        elif isinstance(raw_content, str):
            resolved_content = ThoughtContent(text=raw_content)
        else:  # isinstance(raw_content, dict)
            resolved_content = ThoughtContent(**raw_content)

        # Get images from task if not provided
        # Images are stored at the TASK level, so all thoughts for a task share the same images
        images: List[ImageContent] = []
        if task_images is not None:
            images = task_images
        else:
            # Look up the task to get its images
            try:
                from ciris_engine.logic.persistence.models.tasks import get_task_by_id

                task = get_task_by_id(thought_instance.source_task_id, thought_instance.agent_occurrence_id)
                if task and task.images:
                    images = task.images
                    if images:
                        logger.info(
                            f"[VISION] ProcessingQueueItem inheriting {len(images)} images "
                            f"from task {thought_instance.source_task_id}"
                        )
            except Exception as e:
                logger.warning(f"Failed to load task images for thought {thought_instance.thought_id}: {e}")

        return cls(
            thought_id=thought_instance.thought_id,
            source_task_id=thought_instance.source_task_id,
            thought_type=thought_instance.thought_type,
            content=resolved_content,
            agent_occurrence_id=thought_instance.agent_occurrence_id,
            thought_depth=thought_instance.thought_depth,
            raw_input_string=raw_input if raw_input is not None else str(thought_instance.content),
            initial_context=final_initial_ctx,
            ponder_notes=thought_instance.ponder_notes,
            images=images,
        )


ProcessingQueue = collections.deque[ProcessingQueueItem]
