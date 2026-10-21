"""Task-scoped authorization primitives (CIRISAgent#938, Phase 1).

Phase 1 builds the *subject* a tool gate would authorize; it does not build the
gate. Nothing in this package denies anything. See ``FSD/TASK_ENVELOPE.md``.

Import boundary: modules under ``ciris_engine/logic/dma/``,
``ciris_engine/logic/conscience/`` and ``ciris_engine/logic/handlers/`` must not
import :mod:`.envelope_issuer`. That boundary is asserted by
``tests/ciris_engine/logic/infrastructure/authorization/test_reasoning_cannot_mint.py``.
Reading an already-issued envelope is the one thing the handler layer needs,
and it lives in :mod:`.envelope_reader` — a module with no minting surface at
all — so the import-boundary assertion stays meaningful.
"""

from .deployment import (
    resolve_agent_id,
    resolve_deployment_scope,
    resolve_environment_tier,
    resolve_template,
)
from .enabled_tools import (
    ToolNameSource,
    cached_enabled_tools,
    prime_enabled_tools,
    register_tool_name_source,
    reset_enabled_tools_cache,
)
from .envelope_reader import resolve_envelope_for_task_id, resolve_task_envelope
from .reasoning_scope import (
    ReasoningScope,
    current_reasoning_scope,
    in_reasoning_scope,
    reasoning_scope,
)

__all__ = [
    "ReasoningScope",
    "ToolNameSource",
    "cached_enabled_tools",
    "current_reasoning_scope",
    "in_reasoning_scope",
    "prime_enabled_tools",
    "reasoning_scope",
    "register_tool_name_source",
    "reset_enabled_tools_cache",
    "resolve_agent_id",
    "resolve_deployment_scope",
    "resolve_envelope_for_task_id",
    "resolve_environment_tier",
    "resolve_task_envelope",
    "resolve_template",
]
