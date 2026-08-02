"""Reasoning-scope marker (CIRISAgent#938, Phase 1).

The non-negotiable property of the task envelope is that it is **issued from
outside the reasoning loop**. If the agent can mint or widen its own envelope,
everything built on it is theater.

This module is the runtime half of that guarantee: a :mod:`contextvars` marker
that the processor sets around thought processing and action dispatch, and that
:mod:`ciris_engine.logic.infrastructure.authorization.envelope_issuer` refuses
to mint inside.

What this proves and what it does not
------------------------------------
It proves that a mint call *made while the marker is set* raises. Because
``contextvars`` are copied into child ``asyncio`` tasks at creation, work the
reasoning loop spawns inherits the marker too.

It does **not** prove that every reasoning code path sets the marker — a future
processor that dispatches handlers without entering the scope would evade it.
That gap is covered separately, and imperfectly, by the import-boundary test in
``tests/.../test_reasoning_cannot_mint.py``, which asserts that no module under
``logic/dma/``, ``logic/conscience/`` or ``logic/handlers/`` imports the issuer
at all. Neither test is a sandbox: this is a Python process, and anything with
``import`` can reach anything. The honest claim is "an accidental mint from the
reasoning path fails loudly and a deliberate one is visible in the diff", not
"the reasoning path cannot mint".
"""

from __future__ import annotations

import contextvars
import logging
from contextlib import contextmanager
from typing import Iterator, NamedTuple, Optional

logger = logging.getLogger(__name__)


class ReasoningScope(NamedTuple):
    """Identity of the reasoning work currently in flight."""

    task_id: Optional[str]
    thought_id: Optional[str]
    phase: str


_REASONING_SCOPE: contextvars.ContextVar[Optional[ReasoningScope]] = contextvars.ContextVar(
    "ciris_reasoning_scope", default=None
)


@contextmanager
def reasoning_scope(
    *, task_id: Optional[str], thought_id: Optional[str], phase: str
) -> Iterator[ReasoningScope]:
    """Mark the enclosed block as reasoning-loop execution.

    Safe to nest — ``process_thought`` and ``ActionDispatcher.dispatch`` both
    enter it and the latter runs inside the former in most processors.
    """
    scope = ReasoningScope(task_id=task_id, thought_id=thought_id, phase=phase)
    token = _REASONING_SCOPE.set(scope)
    try:
        yield scope
    finally:
        _REASONING_SCOPE.reset(token)


def current_reasoning_scope() -> Optional[ReasoningScope]:
    """The reasoning scope in flight on this context, or ``None``."""
    return _REASONING_SCOPE.get()


def in_reasoning_scope() -> bool:
    """True when the calling code is executing inside the reasoning loop."""
    return _REASONING_SCOPE.get() is not None


__all__ = [
    "ReasoningScope",
    "current_reasoning_scope",
    "in_reasoning_scope",
    "reasoning_scope",
]
