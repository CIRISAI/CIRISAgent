"""Review integrity: execute only what was reviewed (CIRISAgent#1366 item 10).

FSD/PROMPT_CONTEXT_PROVENANCE.md §9 "Review integrity", and ``ReviewIntegrity``
in ``formal/h3ere_ctxflow/H3EREContextFlow.tla``: the executed action's hash
(tool, arguments, target, scope) must equal the hash of the draft the
consciences reviewed. Otherwise it is not executed; it is re-reviewed.

Two fingerprints, one canonical form:

``reviewed_action_fingerprint``
    What the consciences judged. Computed when the consciences pass
    (``ThoughtProcessor._stamp_reviewed_action``), carried on
    ``ActionSelectionDMAResult.reviewed_action_hash``, and recomputed by
    ``ToolHandler`` over what is about to run. Covers:

    - the verb (``tool``);
    - the RESOLVED tool name — aliases are resolved before the consciences see
      the draft, so they review the tool that will actually run;
    - the arguments exactly as reviewed — secret REFERENCES, never the
      decapsulated values. Decapsulation happens after the check, so a
      legitimate secret substitution can never trip it, and no secret value
      ever enters a hash that is logged or persisted;
    - the target/scope: ``channel_id`` (it also routes the call to a provider,
      ``ToolBus.execute_tool`` step 4).

    Deliberately excluded, because the handler adds them by rule AFTER the
    check, from values the model does not author:

    - the ``channel_id`` copied into the argument map: it is
      ``ToolParams.channel_id``, which is already in the hash;
    - ``task_id``: handler-authoritative (``thought.source_task_id``,
      CIRISAgent#938); a model-supplied ``task_id`` argument IS hashed (it was
      reviewed) and then overwritten.

``tool_call_fingerprint``
    What a human approved (#942): tool + arguments, no target. The approval
    screen shows the tool and the arguments; it does not show a channel, so
    binding a channel the human never saw would bind nothing they decided.

Canonical form: JSON, sorted keys, no whitespace, no ASCII escaping, NaN
refused. ``ToolParams.parameters`` is restricted to str/int/float/bool/
List[str]/Dict[str, str], so this is total over every legal argument map and
keeps ``1``, ``1.0``, ``"1"`` and ``true`` distinct.
"""

from __future__ import annotations

import hashlib
import inspect
import json
from typing import TYPE_CHECKING, Any, Mapping, Optional

if TYPE_CHECKING:
    from ciris_engine.schemas.dma.results import ActionSelectionDMAResult

FINGERPRINT_PREFIX = "sha256:"
_REVIEWED_ACTION_SCHEME = "ciris.reviewed_action.v1"
_TOOL_CALL_SCHEME = "ciris.tool_call.v1"


def _digest(payload: Mapping[str, object]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    return FINGERPRINT_PREFIX + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def tool_call_fingerprint(tool_name: str, arguments: Mapping[str, object]) -> str:
    """Fingerprint of a tool call as a human approves it: tool + arguments."""
    return _digest({"scheme": _TOOL_CALL_SCHEME, "tool": tool_name, "arguments": dict(arguments)})


def reviewed_action_fingerprint(
    action: "ActionSelectionDMAResult", resolved_tool_name: Optional[str] = None
) -> Optional[str]:
    """Fingerprint of a TOOL action as reviewed, or ``None`` if it cannot be one.

    ``resolved_tool_name`` overrides the name in the params: the dispatch side
    passes the name the bus will actually run, so an alias registered after
    review changes the fingerprint. ``None`` for anything that is not a TOOL
    with typed ``ToolParams`` — the caller treats ``None`` as "not reviewable",
    which at dispatch is a refusal.
    """
    from ciris_engine.schemas.actions.parameters import ToolParams
    from ciris_engine.schemas.runtime.enums import HandlerActionType

    if action.selected_action != HandlerActionType.TOOL:
        return None
    params = action.action_parameters
    if not isinstance(params, ToolParams):
        return None
    return _digest(
        {
            "scheme": _REVIEWED_ACTION_SCHEME,
            "verb": HandlerActionType.TOOL.value,
            "tool": resolved_tool_name if resolved_tool_name is not None else params.name,
            "arguments": dict(params.parameters),
            "channel_id": params.channel_id,
        }
    )


def resolve_tool_name_via_bus(bus_manager: Any, tool_name: str) -> str:
    """The tool ``ToolBus.execute_tool`` would run for ``tool_name`` (alias-resolved).

    The one resolver both sides of the review use: the thought processor before
    the consciences see a draft, and ``ToolHandler`` just before dispatch. A bus
    without alias support, or an answer that is not a non-empty string,
    resolves to the name itself — an unresolvable alias is then caught by the
    dispatch-side fingerprint comparison, never silently trusted.
    """
    tool_bus = getattr(bus_manager, "tool", None)
    resolver = getattr(tool_bus, "resolve_tool_name", None)
    if not callable(resolver):
        return tool_name
    resolved = resolver(tool_name)
    if inspect.iscoroutine(resolved):
        resolved.close()
        return tool_name
    if isinstance(resolved, str) and resolved:
        return resolved
    return tool_name


__all__ = [
    "FINGERPRINT_PREFIX",
    "resolve_tool_name_via_bus",
    "reviewed_action_fingerprint",
    "tool_call_fingerprint",
]
