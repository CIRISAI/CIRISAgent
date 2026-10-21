"""Parent-event context for LLM_CALL trace events.

Implements the parent-event linkage required by TRACE_WIRE_FORMAT.md §5.10
(item #5 of #712). Every LLM_CALL ReasoningEvent MUST carry
`parent_event_type` + `parent_attempt_index` so the persistence layer's
`trace_llm_calls` foreign key into `trace_events` resolves to a specific
parent row in the dedup tuple `(agent_id_hash, trace_id, thought_id,
parent_event_type, parent_attempt_index)`.

The pipeline events that issue LLM calls — DMA_RESULTS, IDMA_RESULT,
ASPDMA_RESULT, CONSCIENCE_RESULT — are produced by handlers wrapped in
`@streaming_step` decorators (`ciris_engine/logic/processors/core/
step_decorators.py`). When a handler enters its step, the decorator sets
this ContextVar to (parent_event_type, parent_attempt_index); LLM calls
issued from inside that handler — through `LLMBus._execute_llm_call` —
read the ContextVar at LLM_CALL broadcast time.

Why ContextVar (not threadlocal): asyncio. The agent's LLM call path is
fully async; ContextVar inherits across `asyncio.create_task` and `await`
boundaries while threadlocal does not. ContextVar's per-task isolation
also means concurrent thoughts processing in parallel each see their own
parent context.

Sentinel: when no streaming_step is on the call stack (e.g. boot-time
diagnostic LLM calls before the pipeline starts), the ContextVar default
returns ("UNKNOWN_PARENT", 0) so the wire-format contract holds even at
the cost of a sentinel value. The broadcast helper logs at WARNING when
it observes the sentinel so uncovered code paths surface during testing
rather than silently producing un-joinable LLM_CALL rows.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Iterator, Tuple

logger = logging.getLogger(__name__)

# Sentinel value used when no streaming_step has set the parent context.
# Intentionally distinguishable in lens dashboards so unwired call sites
# surface immediately rather than silently producing un-joinable rows.
UNKNOWN_PARENT_EVENT_TYPE: str = "UNKNOWN_PARENT"
UNKNOWN_PARENT_ATTEMPT_INDEX: int = 0

_DEFAULT_PARENT: Tuple[str, int] = (UNKNOWN_PARENT_EVENT_TYPE, UNKNOWN_PARENT_ATTEMPT_INDEX)

# Per-task parent context — (parent_event_type, parent_attempt_index).
# Set by streaming_step at handler entry; read by LLMBus at LLM_CALL emit.
_parent_event_context: ContextVar[Tuple[str, int]] = ContextVar(
    "_parent_event_context",
    default=_DEFAULT_PARENT,
)


def get_parent_event_context() -> Tuple[str, int]:
    """Return the current (parent_event_type, parent_attempt_index).

    Falls back to ("UNKNOWN_PARENT", 0) if no streaming_step has set the
    context for this task. Callers SHOULD treat the sentinel as a
    diagnostic signal — every LLM call ought to be inside a known
    pipeline event under normal operation.
    """
    return _parent_event_context.get()


@contextmanager
def set_parent_event_context(parent_event_type: str, parent_attempt_index: int) -> Iterator[None]:
    """Bind (parent_event_type, parent_attempt_index) for the duration of
    the wrapped block. Intended to wrap the inner handler call inside a
    `@streaming_step` decorator so all LLM calls issued during the
    handler's execution carry the right parent linkage.

    Usage:
        with set_parent_event_context("ASPDMA_RESULT", 0):
            result = await handler(...)
    """
    if parent_attempt_index < 0:
        # Defensive: persistence rejects negative indices; clamp + warn.
        logger.warning(
            "set_parent_event_context received negative parent_attempt_index=%d; clamping to 0",
            parent_attempt_index,
        )
        parent_attempt_index = 0

    token = _parent_event_context.set((parent_event_type, parent_attempt_index))
    try:
        yield
    finally:
        _parent_event_context.reset(token)
