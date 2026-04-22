import logging
from typing import TYPE_CHECKING, Any, Optional

from ciris_engine.logic.utils.jsondict_helpers import get_bool
from ciris_engine.protocols.services import TimeServiceProtocol
from ciris_engine.schemas.types import JSONDict

if TYPE_CHECKING:
    from ciris_engine.schemas.processors.core import ConscienceApplicationResult

from ciris_engine.logic.utils.channel_utils import create_channel_context
from ciris_engine.schemas.runtime.contexts import DispatchContext
from ciris_engine.schemas.runtime.enums import HandlerActionType

logger = logging.getLogger(__name__)


def build_dispatch_context(
    thought: Any,
    time_service: TimeServiceProtocol,
    task: Optional[Any] = None,
    app_config: Optional[Any] = None,
    round_number: Optional[int] = None,
    extra_context: Optional[JSONDict] = None,
    conscience_result: Optional["ConscienceApplicationResult"] = None,
    action_type: Optional[Any] = None,
) -> DispatchContext:
    """
    Build a type-safe dispatch context for thought processing.

    Args:
        thought: The thought object being processed
        time_service: Time service for timestamps
        task: Optional task associated with the thought
        app_config: Optional app configuration for determining origin service
        round_number: Optional round number for processing
        extra_context: Optional additional runtime context (wa_id, correlation_id, etc.)
        conscience_result: Optional conscience evaluation results
        action_type: Optional action type override

    Returns:
        DispatchContext object with all relevant fields populated
    """

    # Core identification
    thought_id = getattr(thought, "thought_id", None)
    source_task_id = getattr(thought, "source_task_id", None)

    # Determine origin service
    if app_config and hasattr(app_config, "agent_mode"):
        origin_service = "CLI" if app_config.agent_mode.lower() == "cli" else "discord"
    else:
        origin_service = "discord"

    # Extract task context
    channel_context = None
    author_id = None
    author_name = None
    task_id = None

    # First try to get context from thought (most specific)
    if hasattr(thought, "context"):
        if hasattr(thought.context, "initial_task_context") and thought.context.initial_task_context:
            channel_context = thought.context.initial_task_context.channel_context
            author_id = thought.context.initial_task_context.author_id
            author_name = thought.context.initial_task_context.author_name

    # If not found in thought, check task
    if channel_context is None and task:
        task_id = getattr(task, "task_id", None)
        if hasattr(task, "context"):
            # Debug logging
            import logging

            logger = logging.getLogger(__name__)
            logger.info(
                f"Processing task {task_id} context type: {type(task.context)}, attributes: {dir(task.context) if task.context else 'None'}"
            )

            # Handle TaskContext (the correct type for task.context)
            if hasattr(task.context, "channel_id"):
                # TaskContext object from models.py
                channel_id = task.context.channel_id
                if channel_id:
                    channel_context = create_channel_context(channel_id)
                    author_id = task.context.user_id
                    author_name = None  # TaskContext doesn't have author_name
            else:
                logger.error(
                    f"Task {task_id} has invalid context type: {type(task.context)}. Expected TaskContext with channel_id."
                )

    # Check extra_context for channel_id as fallback
    if channel_context is None and extra_context:
        channel_id = extra_context.get("channel_id")
        if channel_id and isinstance(channel_id, str):
            channel_context = create_channel_context(channel_id)

    # Channel context is required
    if channel_context is None:
        raise ValueError(
            f"No channel context found for thought {thought_id}. Adapters must provide channel_id in task context."
        )

    # Extract additional fields from extra_context
    wa_id = None
    wa_authorized = False
    correlation_id = None
    handler_name = None
    event_summary = None

    if extra_context:
        wa_id = extra_context.get("wa_id")
        wa_authorized = get_bool(extra_context, "wa_authorized", False)  # Type-safe bool extraction
        correlation_id = extra_context.get("correlation_id")
        handler_name = extra_context.get("handler_name")
        event_summary = extra_context.get("event_summary")

    # Create the DispatchContext object with defaults for None values
    dispatch_context = DispatchContext(
        # Core identification
        channel_context=channel_context,
        author_id=author_id or "unknown",
        author_name=author_name or "Unknown",
        # Service references
        origin_service=origin_service,
        handler_name=handler_name or "unknown_handler",
        # Action context
        action_type=action_type or HandlerActionType.SPEAK,
        thought_id=thought_id or "",
        task_id=task_id or "",
        source_task_id=source_task_id or "",
        # Event details
        event_summary=event_summary or "No summary provided",
        event_timestamp=time_service.now_iso() + "Z",
        # Additional context
        wa_id=wa_id,
        wa_authorized=wa_authorized,
        correlation_id=correlation_id or f"ctx_{time_service.timestamp()}",
        # conscience results (None for terminal actions)
        # Extract ConscienceResult from ConscienceApplicationResult if needed
        conscience_failure_context=None,
    )

    return dispatch_context
