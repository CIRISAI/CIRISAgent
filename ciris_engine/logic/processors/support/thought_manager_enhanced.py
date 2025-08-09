"""
Enhanced thought manager that generates proper observation thoughts.
This shows how we could modify generate_seed_thought to use correlations.
"""

import uuid
from typing import Any, Optional

from ciris_engine.schemas.runtime.enums import ThoughtStatus, ThoughtType
from ciris_engine.schemas.runtime.models import Task, Thought


def generate_seed_thought_enhanced(self: Any, task: Task, round_number: int = 0) -> Optional[Thought]:
    """Generate a seed thought for a task - with proper observation handling."""
    now_iso = self.time_service.now().isoformat()

    # ... existing context conversion code ...

    # Determine thought type and content based on task
    thought_type = ThoughtType.STANDARD
    thought_content = f"Initial seed thought for task: {task.description}"

    # Check if this is an observation task
    if "Respond to message from" in task.description:
        # Extract info from task description
        # Format: "Respond to message from @{author} (ID: {id}) in #{channel}: '{content}'"
        import re

        # Use more specific patterns to prevent catastrophic backtracking
        # Limit field lengths and use negated character classes instead of lazy quantifiers
        match = re.match(
            r"Respond to message from @([^()]{1,100}) \(ID: ([^()]{1,50})\) in #([^:]{1,100}): '(.{0,1000})'$",
            task.description,
        )

        if match:
            # This is a properly formatted observation task
            thought_type = ThoughtType.OBSERVATION
            author_name = match.group(1)
            author_id = match.group(2)
            channel_name = match.group(3)  # This is the channel name from description
            message_content = match.group(4)

            # Get conversation history from correlations using the task's channel_id
            from ciris_engine.logic.persistence import get_correlations_by_channel

            correlations = get_correlations_by_channel(
                channel_id=task.channel_id,  # Use task's channel_id, not the extracted channel name
                limit=10,  # Last 10 messages
            )

            # Build conversation history
            history_lines = []
            for i, corr in enumerate(correlations, 1):
                if corr.action_type == "speak" and corr.request_data:
                    # Agent message
                    content = corr.request_data.parameters.get("content", "")
                    history_lines.append(f"{i}. @CIRIS (ID: ciris): {content}")

                elif corr.action_type == "observe" and corr.request_data:
                    # User message
                    params = corr.request_data.parameters
                    author = params.get("author_name", "User")
                    author_id = params.get("author_id", "unknown")
                    content = params.get("content", "")
                    history_lines.append(f"{i}. @{author} (ID: {author_id}): {content}")

            # Build the thought content in the format you suggested
            adapter_type = task.channel_id.split("_")[0] if "_" in task.channel_id else "unknown"

            thought_content = f"""You observed user @{author_name} (ID: {author_id}) in Channel {task.channel_id} on Adapter {adapter_type} say: "{message_content}"

Evaluate if or how you should respond based on your role.

=== CONVERSATION HISTORY (Last {len(history_lines)} messages) ===
{chr(10).join(history_lines)}

=== CURRENT MESSAGE ===
@{author_name} (ID: {author_id}): {message_content}

AGAIN you observed user @{author_name} say "{message_content}", so the task is to evaluate if you should respond based on your identity and ethics."""

    # Use task's channel_id or default
    task_channel_id = task.channel_id if hasattr(task, "channel_id") else "unknown"

    # Create a basic thought context (would need proper context conversion in real implementation)
    thought_context = None  # This would need to be built from task context

    thought = Thought(
        thought_id=f"th_seed_{task.task_id}_{str(uuid.uuid4())[:4]}",
        source_task_id=task.task_id,
        channel_id=task_channel_id,
        thought_type=thought_type,
        status=ThoughtStatus.PENDING,
        created_at=now_iso,
        updated_at=now_iso,
        round_number=round_number,
        content=thought_content,
        context=thought_context,
        thought_depth=0,
    )

    # ... rest of the method ...

    return thought
