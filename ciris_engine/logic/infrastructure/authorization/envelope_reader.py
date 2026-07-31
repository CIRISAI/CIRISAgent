"""Read-only task-envelope lookup (CIRISAgent#938, Phase 1).

Split out from :mod:`.envelope_issuer` on purpose. The handler layer needs to
*read* the envelope bound to the task it is executing, so it needs an import.
If that import were of the issuer module, the import-boundary assertion in
``test_reasoning_cannot_mint.py`` ("nothing under ``logic/handlers/`` imports
the issuer") would have to be weakened to nothing.

Nothing here mints, widens or writes an envelope. ``None`` means **denial** to
Phase 2 — it never means "unconstrained".
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional

from ciris_engine.schemas.runtime.task_envelope import TaskEnvelope

if TYPE_CHECKING:
    from ciris_engine.schemas.runtime.models import Task

logger = logging.getLogger(__name__)


def resolve_task_envelope(task: Optional["Task"]) -> Optional[TaskEnvelope]:
    """The envelope bound to ``task``, or ``None``."""
    if task is None or task.context is None:
        return None
    return task.context.envelope


def resolve_envelope_for_task_id(task_id: str, agent_occurrence_id: str = "default") -> Optional[TaskEnvelope]:
    """Load the task row and return its envelope, or ``None``.

    Any failure resolves to ``None`` — the fail-closed direction.
    """
    if not task_id:
        return None
    try:
        from ciris_engine.logic.persistence import get_task_by_id

        return resolve_task_envelope(get_task_by_id(task_id, agent_occurrence_id))
    except Exception as exc:
        logger.warning("TaskEnvelope: could not resolve envelope for task %s: %s", task_id, exc)
        return None


__all__ = ["resolve_envelope_for_task_id", "resolve_task_envelope"]
