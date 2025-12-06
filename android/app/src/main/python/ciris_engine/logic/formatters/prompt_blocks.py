"""Utilities for assembling canonical prompt blocks."""

from typing import Any, List, Optional


def format_parent_task_chain(parent_tasks: List[dict[str, Any]]) -> str:
    """Formats the parent task chain, root first, for the prompt."""
    if not parent_tasks:
        return "=== Parent Task Chain ===\nNone"
    lines = ["=== Parent Task Chain ==="]
    for i, pt in enumerate(parent_tasks):
        if i == 0:
            prefix = "Root Task"
        elif i == len(parent_tasks) - 1:
            prefix = "Direct Parent"
        else:
            prefix = f"Parent {i}"
        desc = pt.get("description", "")
        tid = pt.get("task_id", "N/A")
        lines.append(f"{prefix}: {desc} (Task ID: {tid})")
    return "\n".join(lines)


def format_thoughts_chain(thoughts: List[dict[str, Any]]) -> str:
    """Formats all thoughts under consideration, active thought last."""
    if not thoughts:
        return "=== Thoughts Under Consideration ===\nNone"
    lines = ["=== Thoughts Under Consideration ==="]
    for i, thought in enumerate(thoughts):
        is_active = i == len(thoughts) - 1
        label = "Active Thought" if is_active else f"Thought {i+1}"
        content = str(thought.get("content", ""))
        lines.append(f"{label}: {content}")
    return "\n".join(lines)


def format_system_prompt_blocks(
    identity_block: str,
    task_history_block: str,
    system_snapshot_block: str,
    user_profiles_block: str,
    escalation_guidance_block: Optional[str] = None,
    system_guidance_block: Optional[str] = None,
) -> str:
    """Assemble the system prompt in canonical CIRIS order."""
    blocks = [identity_block, task_history_block]
    if system_guidance_block:
        blocks.append(system_guidance_block)
    if escalation_guidance_block:
        blocks.append(escalation_guidance_block)
    blocks.extend([system_snapshot_block, user_profiles_block])
    return "\n\n".join(filter(None, blocks)).strip()


def format_user_prompt_blocks(
    parent_tasks_block: str,
    thoughts_chain_block: str,
    schema_block: Optional[str] = None,
) -> str:
    """Assemble the user prompt in canonical CIRIS order."""
    blocks = [parent_tasks_block, thoughts_chain_block]
    if schema_block:
        blocks.append(schema_block)
    return "\n\n".join(filter(None, blocks)).strip()
