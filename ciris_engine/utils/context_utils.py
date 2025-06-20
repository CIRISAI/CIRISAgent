import logging
from typing import Any, Dict, Optional, TYPE_CHECKING
from datetime import datetime

if TYPE_CHECKING:
    from ciris_engine.schemas.processing_schemas_v1 import GuardrailResult

from ciris_engine.schemas.foundational_schemas_v1 import DispatchContext, HandlerActionType
from ciris_engine.schemas.context_schemas_v1 import ChannelContext
from ciris_engine.utils.channel_utils import create_channel_context

logger = logging.getLogger(__name__)

def build_dispatch_context(
    thought: Any, 
    task: Optional[Any] = None, 
    app_config: Optional[Any] = None, 
    round_number: Optional[int] = None, 
    extra_context: Optional[Dict[str, Any]] = None,
    guardrail_result: Optional['GuardrailResult'] = None,
    action_type: Optional[Any] = None
) -> DispatchContext:
    """
    Build a type-safe dispatch context for thought processing.
    
    Args:
        thought: The thought object being processed
        task: Optional task associated with the thought
        app_config: Optional app configuration for determining origin service
        round_number: Optional round number for processing
        extra_context: Optional additional context to merge
        guardrail_result: Optional guardrail evaluation results
    
    Returns:
        DispatchContext object with all relevant fields populated
    """
    # Start with base context data
    context_data: Dict[str, Any] = {}
    
    # Extract initial context from thought if available
    if hasattr(thought, "initial_context") and thought.initial_context:
        if isinstance(thought.initial_context, dict):
            context_data.update(thought.initial_context)
    
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
            logger.info(f"Processing task {task_id} context type: {type(task.context)}, attributes: {dir(task.context) if task.context else 'None'}")
            
            # Handle both dict and ThoughtContext objects
            if isinstance(task.context, dict):
                # Legacy dict format - create ChannelContext
                channel_id = task.context.get("channel_id")
                if channel_id:
                    channel_context = create_channel_context(channel_id)
                author_id = task.context.get("author_id")
                author_name = task.context.get("author_name")
            elif hasattr(task.context, "system_snapshot"):
                # ThoughtContext object with system_snapshot
                if task.context.system_snapshot:
                    channel_context = task.context.system_snapshot.channel_context
                    # SystemSnapshot doesn't have user_id/user_name - these come from user_profiles
                    # For wakeup tasks, we don't have a specific user
                    author_id = None
                    author_name = None
            elif hasattr(task.context, "initial_task_context"):
                # ThoughtContext object with initial_task_context (from observers)
                if task.context.initial_task_context:
                    channel_context = task.context.initial_task_context.channel_context
                    author_id = task.context.initial_task_context.author_id
                    author_name = task.context.initial_task_context.author_name
                else:
                    logger.warning(f"Task {task_id} has initial_task_context attribute but it's None/empty")
    
    # Check extra_context for channel_id as fallback
    if channel_context is None and extra_context:
        channel_id = extra_context.get("channel_id")
        if channel_id:
            channel_context = create_channel_context(channel_id)
    
    # Channel context is required
    if channel_context is None:
        raise ValueError(f"No channel context found for thought {thought_id}. Adapters must provide channel_id in task context.")
    
    # Extract additional fields from extra_context
    wa_id = None
    wa_authorized = False
    correlation_id = None
    handler_name = None
    event_summary = None
    
    if extra_context:
        wa_id = extra_context.get("wa_id")
        wa_authorized = extra_context.get("wa_authorized", False)
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
        event_timestamp=datetime.utcnow().isoformat() + "Z",
        
        # Additional context
        wa_id=wa_id,
        wa_authorized=wa_authorized,
        correlation_id=correlation_id or f"ctx_{datetime.utcnow().timestamp()}",
        round_number=round_number or 0,
        
        # Guardrail results (None for terminal actions)
        guardrail_result=guardrail_result
    )
    
    return dispatch_context