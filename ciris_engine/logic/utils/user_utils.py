from typing import Optional

from ciris_engine.logic import persistence
from ciris_engine.schemas.types import JSONDict


async def extract_user_nick(
    *,
    message: Optional[object] = None,
    params: Optional[object] = None,
    dispatch_context: Optional[JSONDict] = None,
    thought_id: Optional[str] = None,
) -> Optional[str]:
    """Attempt to determine a user nickname from various sources.

    Args:
        message: Optional Discord message object with author information
        params: Optional params object with user data
        dispatch_context: Optional dispatch context with author/user information
        thought_id: Optional thought ID to lookup parent task context

    Returns:
        User nickname if found, None otherwise
    """
    # 1. Directly from a Discord message object
    if message is not None:
        author = getattr(message, "author", None)
        if author is not None:
            nick = getattr(author, "display_name", None)
            if nick:
                return str(nick)
            name = getattr(author, "name", None)
            if name:
                return str(name)

    # 2. From MemorizeParams or similar params object
    if params is not None:
        value = getattr(params, "value", None)
        if isinstance(value, dict):
            nick = value.get("nick") or value.get("user_id")
            if nick:
                return str(nick)

    # 3. From dispatch context
    if dispatch_context:
        nick = dispatch_context.get("author_name") or dispatch_context.get("user_id")
        if nick:
            return str(nick)

    # 4. Fallback to parent task via thought_id
    if thought_id:
        try:
            current_thought = await persistence.async_get_thought_by_id(thought_id)
            if current_thought and current_thought.source_task_id:
                parent_task = persistence.get_task_by_id(current_thought.source_task_id)
                if parent_task and parent_task.context:
                    # Check if context has get method (dict-like) or use getattr for objects
                    if hasattr(parent_task.context, "get"):
                        nick = parent_task.context.get("author_name") or parent_task.context.get("user_id")
                    else:
                        nick = getattr(parent_task.context, "author_name", None) or getattr(
                            parent_task.context, "user_id", None
                        )
                    if nick:
                        return str(nick)
        except Exception:
            # Ignore lookup errors silently
            pass

    return None
