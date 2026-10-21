"""Utilities for assembling canonical prompt blocks."""

from typing import Any, List, Optional

from ._localized import label_localizer


def format_parent_task_chain(parent_tasks: List[dict[str, Any]], language: Optional[str] = None) -> str:
    """Formats the parent task chain, root first, for the prompt."""
    localizer = label_localizer(language)
    header = localizer("prompts.formatters.parent_task_chain", "Parent Task Chain")
    if not parent_tasks:
        return f"=== {header} ===\nNone"
    lines = [f"=== {header} ==="]
    for i, pt in enumerate(parent_tasks):
        if i == 0:
            prefix = localizer("prompts.formatters.root_task", "Root Task")
        elif i == len(parent_tasks) - 1:
            prefix = localizer("prompts.formatters.direct_parent", "Direct Parent")
        else:
            prefix = f"Parent {i}"
        desc = pt.get("description", "")
        tid = pt.get("task_id", "N/A")
        lines.append(f"{prefix}: {desc} (Task ID: {tid})")
    return "\n".join(lines)


def format_thoughts_chain(thoughts: List[dict[str, Any]], language: Optional[str] = None) -> str:
    """Formats all thoughts under consideration, active thought last."""
    localizer = label_localizer(language)
    header = localizer("prompts.formatters.thoughts_under_consideration", "Thoughts Under Consideration")
    if not thoughts:
        return f"=== {header} ===\nNone"
    lines = [f"=== {header} ==="]
    active_label = localizer("prompts.formatters.active_thought", "Active Thought")
    for i, thought in enumerate(thoughts):
        is_active = i == len(thoughts) - 1
        label = active_label if is_active else f"Thought {i+1}"
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


def append_round1_accord_blocks(messages: List[Any], *, language: str, accord_mode: str) -> None:
    """Append the round-1 parallel-DMA system blocks, in canonical order:
    ACCORD -> per-language guidance -> prohibition context (#910).

    Shared by PDMA/CSDMA/DSDMA (the round-1 DMAs) — NOT ASPDMA/recursive, which
    carry accord + language guidance but deliberately omit the prohibition block
    so a named trajectory flows forward via the existing output path rather than
    being restated at every step. Mutates ``messages`` in place, appending only
    non-empty blocks (skip empty system messages over the wire).
    """
    # Lazy imports keep the low-level formatters module free of util-layer cycles.
    from ciris_engine.logic.utils.constants import get_accord_text
    from ciris_engine.logic.utils.localization import get_language_guidance, get_prohibition_guidance

    for content in (get_accord_text(accord_mode), get_language_guidance(language), get_prohibition_guidance(language)):
        if content:
            messages.append({"role": "system", "content": content})
