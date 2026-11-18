"""Per-task test directives for the mock LLM (CIRISAgent#1366, RATCHET context-flow harness).

A harness can append directives to a user message. They are lifted out of the
message before the mock parses its ``$command``, recorded here under the task id,
and applied to every later mock call made for that task:

``$veto <conscience>[:<n>]``
    Fail the first ``n`` (default 1) evaluations of that conscience within the
    task, then pass. ``<conscience>`` is ``entropy``, ``coherence``, ``optveto``
    or ``epistemic``. Repeat the directive to veto more than one conscience.

``$ponder_loop``
    Every action selection in the task chooses PONDER, so the thought chain
    deepens until the thought-depth guardrail defers it.

How a directive reaches a conscience that never sees the user's message
-----------------------------------------------------------------------
Entropy and the optimization veto are ablated by design: their prompts carry the
draft reply, not the user's message. Nothing here adds user text to them. The
LLM bus hands every provider the ``task_id`` and ``thought_id`` of the thought
it is serving (``LLMBus.call_llm_structured`` -> ``call_llm_structured(...,
thought_id=, task_id=)``); a live provider ignores them, the mock keys on them.
Action selection runs before the consciences and its prompt does carry the
message, so the mock records the directives there, under the thought's
``source_task_id``. When a conscience call later arrives with the same task id,
the mock looks the directive up. The conscience prompt is the one a live run
sends, byte for byte.

The registry lives in this process, bounded to the most recent tasks.
"""

import re
import threading
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

#: Conscience names a ``$veto`` directive accepts.
VETO_CONSCIENCES = ("entropy", "coherence", "optveto", "epistemic")

_VETO = re.compile(r"\$veto\s+(entropy|coherence|optveto|epistemic)(?::(\d+))?(?=\s|$)", re.IGNORECASE)
_PONDER_LOOP = re.compile(r"\$ponder_loop(?=\s|$)", re.IGNORECASE)

#: Context-item prefix extract_context_from_messages uses to carry a directive
#: from the prompt to create_response. Internal routing only, never a result field.
DIRECTIVE_CONTEXT_PREFIX = "mock_directive:"

_MAX_TASKS = 1024


@dataclass
class _TaskDirectives:
    veto_budget: Dict[str, int] = field(default_factory=dict)
    veto_seen: Dict[str, int] = field(default_factory=dict)
    ponder_loop: bool = False


_registry: "OrderedDict[str, _TaskDirectives]" = OrderedDict()
_lock = threading.Lock()


def strip_directives(message: str) -> Tuple[str, List[str]]:
    """``message`` without its directives, and the directives as context items.

    The items read ``mock_directive:veto:<conscience>:<n>`` and
    ``mock_directive:ponder_loop``.
    """
    items: List[str] = []
    for match in _VETO.finditer(message):
        count = int(match.group(2)) if match.group(2) else 1
        items.append(f"{DIRECTIVE_CONTEXT_PREFIX}veto:{match.group(1).lower()}:{count}")
    if _PONDER_LOOP.search(message):
        items.append(f"{DIRECTIVE_CONTEXT_PREFIX}ponder_loop")
    if not items:
        return message, items
    cleaned = _PONDER_LOOP.sub("", _VETO.sub("", message))
    return re.sub(r"[ \t]{2,}", " ", cleaned).strip(), items


def record(task_id: Optional[str], context: List[str]) -> None:
    """Record the directives in ``context`` for ``task_id``.

    The first sighting of a veto sets its budget; a later prompt for the same
    task (a conscience retry re-reads the message) never resets the count.
    """
    if not task_id:
        return
    items = [i[len(DIRECTIVE_CONTEXT_PREFIX) :] for i in context if i.startswith(DIRECTIVE_CONTEXT_PREFIX)]
    if not items:
        return
    with _lock:
        entry = _registry.get(task_id)
        if entry is None:
            entry = _registry[task_id] = _TaskDirectives()
            while len(_registry) > _MAX_TASKS:
                _registry.popitem(last=False)
        for item in items:
            if item == "ponder_loop":
                entry.ponder_loop = True
            elif item.startswith("veto:"):
                _, conscience, count = item.split(":")
                entry.veto_budget.setdefault(conscience, int(count))


def take_veto(task_id: Optional[str], conscience: str) -> Optional[Tuple[int, int]]:
    """Count one evaluation of ``conscience`` for the task.

    Returns ``(evaluation_number, budget)`` when this evaluation must fail,
    else None.
    """
    if not task_id:
        return None
    with _lock:
        entry = _registry.get(task_id)
        if entry is None or conscience not in entry.veto_budget:
            return None
        seen = entry.veto_seen.get(conscience, 0) + 1
        entry.veto_seen[conscience] = seen
        budget = entry.veto_budget[conscience]
        return (seen, budget) if seen <= budget else None


def ponder_loop_active(task_id: Optional[str]) -> bool:
    """Whether the task is in ``$ponder_loop`` mode."""
    if not task_id:
        return False
    with _lock:
        entry = _registry.get(task_id)
        return bool(entry and entry.ponder_loop)


def reset() -> None:
    """Forget every recorded directive (tests)."""
    with _lock:
        _registry.clear()
