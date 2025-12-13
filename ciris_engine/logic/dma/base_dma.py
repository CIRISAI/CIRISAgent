from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, Generic, List, Optional, Tuple, TypeVar, Union

import yaml
from pydantic import BaseModel

from ciris_engine.logic.registries.base import ServiceRegistry
from ciris_engine.protocols.services import LLMService
from ciris_engine.schemas.dma.prompts import PromptCollection
from ciris_engine.schemas.runtime.enums import ServiceType
from ciris_engine.schemas.runtime.models import ImageContent, Task
from ciris_engine.schemas.services.llm import (
    ContentBlock,
    ImageContentBlock,
    ImageURLDetail,
    TextContentBlock,
)
from ciris_engine.schemas.types import JSONDict

if TYPE_CHECKING:
    from ciris_engine.protocols.faculties import EpistemicFaculty

logger = logging.getLogger(__name__)

InputT = TypeVar("InputT")
DMAResultT = TypeVar("DMAResultT", bound=BaseModel)


class BaseDMA(ABC, Generic[InputT, DMAResultT]):
    """Concrete base class for Decision Making Algorithms.

    This class provides the implementation of the BaseDMAInterface
    with backward compatibility for existing DMAs.
    """

    def __init__(
        self,
        service_registry: ServiceRegistry,
        model_name: Optional[str] = None,
        max_retries: int = 3,
        prompt_overrides: Optional[Union[Dict[str, str], PromptCollection]] = None,
        faculties: Optional[Dict[str, "EpistemicFaculty"]] = None,
        sink: Optional[Any] = None,
        **kwargs: Any,
    ) -> None:
        self.service_registry = service_registry
        self.model_name = model_name
        self.max_retries = max_retries
        self.faculties = faculties or {}
        self.sink = sink

        self.kwargs = kwargs

        self.prompts: Union[Dict[str, str], PromptCollection] = {}
        self._load_prompts(prompt_overrides)

    def _load_prompts(self, overrides: Optional[Union[Dict[str, str], PromptCollection]] = None) -> None:
        """Load prompts from YAML file or use defaults.

        First checks for PROMPT_FILE class attribute, then falls back to
        prompts/<class_name>.yml file in the same directory as the DMA.
        Finally falls back to DEFAULT_PROMPT or DEFAULT_PROMPT_TEMPLATE if defined.
        """
        prompt_file = None
        if hasattr(self.__class__, "PROMPT_FILE"):
            prompt_file = getattr(self.__class__, "PROMPT_FILE")
        else:
            dma_file = Path(self.__class__.__module__.replace(".", "/"))
            prompt_file = dma_file.parent / "prompts" / f"{self.__class__.__name__.lower()}.yml"

        if prompt_file and Path(prompt_file).exists():
            try:
                # If overrides is already a PromptCollection, use it directly
                if isinstance(overrides, PromptCollection):
                    self.prompts = overrides
                    return

                with open(prompt_file, "r") as f:
                    file_prompts = yaml.safe_load(f) or {}

                # Support both dict and PromptCollection
                if isinstance(overrides, dict):
                    self.prompts = {**file_prompts, **overrides}
                else:
                    self.prompts = file_prompts
                return
            except Exception as e:
                import logging

                logger = logging.getLogger(__name__)
                logger.warning(f"Failed to load prompts from {prompt_file}: {e}")

        # Handle overrides as PromptCollection
        if isinstance(overrides, PromptCollection):
            self.prompts = overrides
            return

        defaults = {}
        if hasattr(self, "DEFAULT_PROMPT"):
            defaults = getattr(self, "DEFAULT_PROMPT")
        elif hasattr(self, "DEFAULT_PROMPT_TEMPLATE"):
            defaults = getattr(self, "DEFAULT_PROMPT_TEMPLATE")

        if isinstance(overrides, dict):
            self.prompts = {**defaults, **overrides}
        else:
            self.prompts = defaults

    async def get_llm_service(self) -> Optional[LLMService]:
        """Return the LLM service for this DMA from the service registry."""
        service = await self.service_registry.get_service(
            handler=self.__class__.__name__,
            service_type=ServiceType.LLM,
        )
        return service

    async def call_llm_structured(
        self,
        messages: List[JSONDict],
        response_model: type,
        max_tokens: int = 1024,
        temperature: float = 0.0,
        thought_id: Optional[str] = None,
        task_id: Optional[str] = None,
    ) -> Tuple[Any, ...]:
        """Call LLM via sink for centralized failover, round-robin, and circuit breaker protection.

        Args:
            messages: List of message dictionaries
            response_model: Pydantic model for response
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature
            thought_id: Optional thought_id for resource tracking
            task_id: Optional task_id for ciris.ai billing (all calls with same task_id share 1 credit)

        Returns:
            Tuple[BaseModel, ResourceUsage]
        """
        if not self.sink:
            # Critical system failure - DMAs cannot function without the multi-service sink
            import logging

            logger = logging.getLogger(__name__)
            logger.critical(
                f"FATAL: No multi-service sink available for {self.__class__.__name__}. System cannot continue."
            )
            raise RuntimeError(
                f"FATAL: No multi-service sink available for {self.__class__.__name__}. DMAs require the sink for all LLM calls. System must shutdown."
            )

        # Use LLM bus for centralized failover, round-robin, and circuit breaker protection
        result = await self.sink.llm.call_llm_structured(
            messages=messages,
            response_model=response_model,
            handler_name=self.__class__.__name__,
            max_tokens=max_tokens,
            temperature=temperature,
            thought_id=thought_id,
            task_id=task_id,
        )

        # The sink returns Optional[tuple] which we need to ensure is a valid tuple
        if result is None:
            raise RuntimeError(f"Multi-service sink returned None for structured LLM call in {self.__class__.__name__}")

        # Ensure result is a tuple (it should be from the type annotation)
        if not isinstance(result, tuple):
            raise RuntimeError(f"Multi-service sink returned non-tuple: {type(result)}")

        return result

    async def apply_faculties(self, content: str, context: Optional[JSONDict] = None) -> Dict[str, BaseModel]:
        """Apply available epistemic faculties to content.

        Args:
            content: The content to analyze
            context: Optional context for analysis (FacultyContext or dict to convert)

        Returns:
            Dictionary mapping faculty name to evaluation result
        """
        from ciris_engine.schemas.dma.faculty import FacultyContext

        # Use Dict[str, BaseModel] to match return type
        results: Dict[str, BaseModel] = {}

        if not self.faculties:
            return results

        # Convert dict to FacultyContext if needed
        faculty_context: Optional[FacultyContext] = None
        if context is not None:
            if isinstance(context, dict):
                faculty_context = FacultyContext(**context)
            else:
                faculty_context = context

        for name, faculty in self.faculties.items():
            try:
                result = await faculty.analyze(content, faculty_context)
                results[name] = result
            except Exception as e:
                # Log error but don't fail the entire evaluation
                import logging

                logger = logging.getLogger(__name__)
                logger.warning(f"Faculty {name} failed to evaluate: {e}")
                continue

        return results

    def get_algorithm_type(self) -> str:
        """Get the type of decision making algorithm."""
        # Return class name by default
        return self.__class__.__name__

    async def fetch_original_task(self, source_task_id: str, agent_occurrence_id: str = "default") -> Optional[Task]:
        """Fetch the original task from persistence.

        Args:
            source_task_id: The task ID to fetch
            agent_occurrence_id: The occurrence ID for the task

        Returns:
            Task object if found, None otherwise
        """
        try:
            from ciris_engine.logic import persistence

            task = persistence.get_task_by_id(source_task_id, agent_occurrence_id)
            if task:
                logger.debug(f"[DMA] Fetched original task: {source_task_id}")
            else:
                logger.warning(f"[DMA] Task {source_task_id} not found in persistence")
            return task
        except Exception as e:
            logger.error(f"[DMA] Failed to fetch task {source_task_id}: {e}")
            return None

    def format_task_context(self, task: Optional[Task], thought_depth: int = 0) -> str:
        """Format task context for inclusion in DMA prompts.

        Args:
            task: The original Task object (or None if not found)
            thought_depth: Current thought depth (0=initial, >0=follow-up)

        Returns:
            Formatted string with task context for the prompt
        """
        if not task:
            return "(Original task not available)"

        parts = []
        parts.append(f'Task: "{task.description}"')
        parts.append(f"Task ID: {task.task_id}")

        if hasattr(task, "status") and task.status:
            parts.append(f"Status: {task.status}")

        # Include parent task context if available (for subtasks)
        if task.context and task.context.parent_task_id:
            parts.append(f"Parent Task ID: {task.context.parent_task_id}")

        # Add follow-through guidance for non-initial thoughts
        if thought_depth > 0:
            parts.append("")
            parts.append(
                "⚠️ FOLLOW-THROUGH REQUIRED: This is thought depth {depth}. "
                "Previous actions have been taken. Evaluate whether the current "
                "thought properly continues toward completing the original task.".format(depth=thought_depth)
            )

        return "\n".join(parts)

    @staticmethod
    def build_multimodal_content(
        text: str,
        images: List[ImageContent],
    ) -> Union[str, List[Dict[str, Any]]]:
        """
        Build content for an LLM message, supporting both text-only and multimodal.

        If no images are provided, returns the text string directly.
        If images are provided, returns a list of serialized content block dicts.

        Args:
            text: Text content of the message
            images: List of ImageContent objects (can be empty)

        Returns:
            Either a string (text-only) or List[Dict] (multimodal content blocks)
        """
        if not images:
            return text

        # Build content blocks for multimodal message and serialize to dicts
        # This ensures JSON serialization works when sent to LLM APIs
        content: List[Dict[str, Any]] = [TextContentBlock(text=text).model_dump()]

        for img in images:
            image_block = ImageContentBlock(image_url=ImageURLDetail(url=img.to_data_url()))
            content.append(image_block.model_dump())

        return content

    def build_user_message(
        self,
        text: str,
        images: Optional[List[ImageContent]] = None,
    ) -> JSONDict:
        """
        Build a user message dict for LLM calls, with optional multimodal support.

        Args:
            text: Text content of the message
            images: Optional list of ImageContent objects

        Returns:
            Message dict with role and content (text or multimodal)
        """
        content = self.build_multimodal_content(text, images or [])
        return {"role": "user", "content": content}

    @abstractmethod
    async def evaluate(self, *args: Any, **kwargs: Any) -> BaseModel:
        """Execute DMA evaluation and return a pydantic model.

        Note: This maintains the old signature for backward compatibility.
        New DMAs should use the typed interface methods.
        """
        raise NotImplementedError
