"""A short factual record of the actions that ran in a task, for its follow-up thoughts (#1320).

RATCHET's Market 4 pilot (CIRISAgent#1320, episode s-001): after a MEMORIZE
of the speaker's own user node, the follow-up thought read only "MEMORIZE
COMPLETE - stored user '...'", and the model took "stored" for "applied" and
told the user an identity change "is now effective across all channels and
users". Nothing in the follow-up said which node and scope were written, that
the identity was untouched, or that no reply had been sent yet.

Every follow-up built by ``BaseActionHandler.complete_thought_and_create_followup``
now carries this record, built in one place from the task's own thoughts: each
action that ran (its enum name, whether it was done, failed or deferred, and for
a graph write the node and scope written, with "identity unchanged" for any
write outside the identity scope), then whether a reply has been sent. Labels
are localized; action and scope names stay enum values, as in the approval
block (formatters/wa_approval.py).

Round 2 (s-001 again, run 39940561892): the per-entry "identity unchanged"
appeared only beside a graph write, so a task that ran only PONDER and SPEAK
said nothing about the identity, and the model claimed a change it never made.
The record now always closes its list with "Identity: unchanged in this task"
unless this task itself wrote to the identity: a MEMORIZE or FORGET of an
identity node (``is_identity_node`` or an identity amendment) that the handler
COMPLETED. The thought status is the handler's, never the model's: a refused
identity write is FAILED and leaves the line in place.
"""

from __future__ import annotations

import logging
from typing import List, Optional

from ciris_engine.logic import persistence
from ciris_engine.logic.infrastructure.handlers.shared_helpers import is_identity_node
from ciris_engine.schemas.runtime.enums import HandlerActionType, ThoughtStatus
from ciris_engine.schemas.runtime.models import Thought
from ciris_engine.schemas.services.graph_core import GraphNode, GraphScope, NodeType

logger = logging.getLogger(__name__)

#: The most recent actions listed; a long ponder chain must not crowd the prompt.
MAX_RECORDED_ACTIONS = 12

#: Actions whose parameters name the graph node they act on.
_NODE_ACTIONS = frozenset({HandlerActionType.MEMORIZE.value, HandlerActionType.FORGET.value})

#: Thought status -> the localized status label key.
_STATUS_KEYS = {
    ThoughtStatus.COMPLETED: "handlers.action_record_status_done",
    ThoughtStatus.FAILED: "handlers.action_record_status_failed",
    ThoughtStatus.DEFERRED: "handlers.action_record_status_deferred",
}


def _node_of(thought: Thought) -> Optional[GraphNode]:
    """The node a MEMORIZE / FORGET acted on, from its recorded parameters."""
    action = thought.final_action
    if action is None or action.action_type.lower() not in _NODE_ACTIONS:
        return None
    node = action.action_params.get("node")
    if not isinstance(node, dict):
        return None
    try:
        return GraphNode.model_validate(node)
    except Exception:  # noqa: BLE001 - an unparseable record is listed without its node
        return None


def _entry(thought: Thought, lang: str) -> Optional[str]:
    """One line for a thought whose action ran, or None if it has not run."""
    from ciris_engine.logic.utils.localization import get_string

    action = thought.final_action
    status_key = _STATUS_KEYS.get(thought.status)
    if action is None or status_key is None:
        return None
    name = action.action_type.upper()
    status = get_string(lang, status_key)
    node = _node_of(thought)
    if node is None:
        return get_string(lang, "handlers.action_record_entry", action=name, status=status)
    line = get_string(
        lang,
        "handlers.action_record_entry_node",
        action=name,
        status=status,
        node_id=node.id,
        scope=node.scope.value,
    )
    if node.scope != GraphScope.IDENTITY:
        line = f"{line}; {get_string(lang, 'handlers.action_record_identity_unchanged')}"
    return line


def identity_written(thoughts: List[Thought]) -> bool:
    """True when a MEMORIZE / FORGET of an identity node COMPLETED in this task (#1320)."""
    for thought in thoughts:
        if thought.status != ThoughtStatus.COMPLETED:
            continue
        node = _node_of(thought)
        if node is not None and (is_identity_node(node) or node.type == NodeType.IDENTITY_AMENDMENT):
            return True
    return False


def reply_sent(thoughts: List[Thought]) -> bool:
    """True when a SPEAK in this task completed: the one test for "has the task replied" (#1320)."""
    return any(
        t.final_action is not None
        and t.final_action.action_type.lower() == HandlerActionType.SPEAK.value
        and t.status == ThoughtStatus.COMPLETED
        for t in thoughts
    )


def format_action_record(thoughts: List[Thought], lang: str) -> str:
    """The record for these thoughts of one task; empty when no action has run."""
    from ciris_engine.logic.utils.localization import get_string

    entries = [line for line in (_entry(t, lang) for t in thoughts) if line]
    if not entries:
        return ""
    entries = entries[-MAX_RECORDED_ACTIONS:]
    reply_key = "handlers.action_record_reply_sent" if reply_sent(thoughts) else "handlers.action_record_no_reply"
    lines = [get_string(lang, "handlers.action_record_header"), *entries]
    if not identity_written(thoughts):
        lines.append(get_string(lang, "handlers.action_record_identity_status_unchanged"))
    lines.append(get_string(lang, reply_key))
    return "\n".join(lines)


def action_record_for_task(task_id: Optional[str], occurrence_id: str, lang: str) -> str:
    """The record for a task, read from persistence. Never raises: a follow-up without it is still a follow-up."""
    if not task_id:
        return ""
    try:
        thoughts = persistence.get_thoughts_by_task_id(task_id, occurrence_id)
        return format_action_record(thoughts, lang)
    except Exception as e:  # noqa: BLE001
        logger.debug("Could not build the action record for task %s: %s", task_id, e)
        return ""


__all__ = ["MAX_RECORDED_ACTIONS", "action_record_for_task", "format_action_record", "identity_written", "reply_sent"]
