"""The TaskEnvelope Phase 2 tool gate, ENFORCING (CIRISAgent#1366 item 19, #938, #905 Ask 1).

Called by ``ToolBus.dispatch_to_provider`` — the single point at which a tool
provider is invoked — before every provider call. It returns ``None`` to allow
or a typed :class:`GateRefusal` to deny. It never raises: an error inside the
gate is a denial.

Policy input is ``(subject, envelope, tool name, the dispatch arguments, the
admitted reviewed-action record)``. Nothing model-authored is trusted: the
subject's origin/component are set by CIRIS code at the call site, the record
is written by the thought processor only when the consciences passed, and the
fingerprint is RECOMPUTED here from the tool name the bus is running.

Rules (FSD/TASK_ENVELOPE.md §8 "Rules Phase 2 must follow"):

* no subject, or a subject with no envelope: DENY (never an exemption);
* gate on ``granted_tools`` (tool-name axis), not on ``capabilities``;
* a REASONING call runs only an admitted reviewed fingerprint (4 of 4 LLM
  conscience passes over it in this thought), with dispatch arguments that are
  the reviewed ones plus only the handler's rule-added keys;
* a CONTEXT_ENRICHMENT call (task-bound, pipeline-run, not model-selected) is
  explicitly permitted without review, only for a tool its provider declares
  ``context_enrichment=True`` and only under the task's own envelope;
* a non-task call must come from a caller enumerated in
  ``SYSTEM_CALLERS`` with its declared origin and a SYSTEM_COMPONENT envelope,
  and is honoured against that grant (no blanket non-reasoning exemption);
* a write to an adapter discovery root is refused for every origin
  (write-then-load).

``requires_approval`` is not duplicated here (§3): ``ThoughtProcessor.
_enforce_tool_approval`` owns it. An approval envelope's narrow grant is
UNIONED with the deployment grant for the tool-name axis, as tool_approval.py
§2 requires, so a guidance task is not stranded.
"""

from __future__ import annotations

import contextvars
import inspect
import logging
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, FrozenSet, Iterable, Iterator, List, Mapping, Optional

from ciris_engine.logic.infrastructure.authorization.enabled_tools import cached_enabled_tools
from ciris_engine.logic.infrastructure.authorization.reviewed_action import (
    consume_passed_record,
    passed_entry_for,
    review_entries_for,
    reviewed_call_fingerprint,
    undischarged_objections,
)
from ciris_engine.schemas.runtime.reviewed_action_admission import (
    SYSTEM_CALLERS,
    GateRefusal,
    GateRefusalReason,
    ToolPrincipalRestriction,
)
from ciris_engine.schemas.runtime.task_envelope import (
    EnvelopeIssuerKind,
    TaskEnvelope,
    ToolCallOrigin,
    ToolInvocationSubject,
)

logger = logging.getLogger(__name__)

#: Keys the ToolHandler adds to the reviewed arguments by rule, from values the
#: model does not author (``ToolHandler._build_tool_params``).
_HANDLER_ADDED_KEYS = frozenset({"channel_id", "task_id"})

#: Marker of a secret REFERENCE in a reviewed argument; its dispatch value is
#: the decapsulated secret, so the two legitimately differ.
_SECRET_REF_MARKER = "{SECRET:"

#: Argument names a file-writing tool uses for its target.
_PATH_ARGUMENT_NAMES = ("path", "file_path", "filepath", "destination", "dest", "target_path", "output_path")

_APPROVAL_ISSUERS = frozenset({EnvelopeIssuerKind.WISE_AUTHORITY, EnvelopeIssuerKind.NODE_OWNER})

# ---------------------------------------------------------------------------
# Principal restrictions: deterministic "only these ids may cause this tool".
# ---------------------------------------------------------------------------

PrincipalRestrictionSource = Callable[[], Iterable[ToolPrincipalRestriction]]
_PRINCIPAL_SOURCES: List[PrincipalRestrictionSource] = []


def register_principal_restriction_source(source: PrincipalRestrictionSource) -> None:
    """Register trusted state that restricts a tool to named principals.

    The source must read TRUSTED state only (a verified amendment's typed
    restriction, a signed WA directive), never message text.
    """
    _PRINCIPAL_SOURCES.append(source)


def reset_principal_restriction_sources() -> None:
    """For tests and runtime teardown."""
    _PRINCIPAL_SOURCES.clear()


def _restrictions_for(tool_name: str) -> List[ToolPrincipalRestriction]:
    found: List[ToolPrincipalRestriction] = []
    for source in list(_PRINCIPAL_SOURCES):
        for restriction in source():
            if restriction.tool_name == tool_name:
                found.append(restriction)
    return found


# ---------------------------------------------------------------------------
# Gated-dispatch marker: providers with a second, non-bus entry point refuse
# any call that did not arrive through the gate.
# ---------------------------------------------------------------------------

_GATED_TOOL: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar("ciris_gated_tool", default=None)


@contextmanager
def gated_dispatch(tool_name: str) -> Iterator[None]:
    """Mark the provider call ``ToolBus.dispatch_to_provider`` makes after the gate allowed it."""
    token = _GATED_TOOL.set(tool_name)
    try:
        yield
    finally:
        _GATED_TOOL.reset(token)


def ungated_refusal(tool_name: str, provider: str) -> Optional[GateRefusal]:
    """``None`` when ``tool_name`` is being run by a gated dispatch, else the refusal.

    For providers whose tool entry point is reachable without the bus (the
    Discord adapter delegating to its own handler): the call must have passed
    the gate for this exact tool.
    """
    if _GATED_TOOL.get() == tool_name:
        return None
    refusal = GateRefusal(
        reason=GateRefusalReason.UNGATED_PROVIDER_CALL,
        tool_name=tool_name,
        detail=f"{provider} runs tools only through ToolBus.dispatch_to_provider",
    )
    _log_denial(refusal)
    return refusal


# ---------------------------------------------------------------------------
# Adapter discovery roots (write-then-load).
# ---------------------------------------------------------------------------


def adapter_discovery_roots() -> List[Path]:
    """Every root the adapter loader scans, resolved."""
    from ciris_engine.logic.services.tool.discovery_service import AdapterDiscoveryService

    roots: List[Path] = []
    for root in AdapterDiscoveryService.standard_and_env_paths():
        try:
            roots.append(root.expanduser().resolve())
        except OSError:
            continue
    return roots


def _writes_into_adapter_root(parameters: Mapping[str, Any]) -> Optional[str]:
    """The adapter root a path argument lands in, if any."""
    candidates = [parameters.get(name) for name in _PATH_ARGUMENT_NAMES]
    paths = [c for c in candidates if isinstance(c, str) and c.strip()]
    if not paths:
        return None
    roots = adapter_discovery_roots()
    for raw in paths:
        try:
            target = Path(raw).expanduser().resolve()
        except (OSError, RuntimeError):
            return raw  # unresolvable target near a loader is refused, not guessed
        for root in roots:
            if target == root or root in target.parents:
                return str(root)
    return None


# ---------------------------------------------------------------------------
# The gate.
# ---------------------------------------------------------------------------


def effective_grant(envelope: TaskEnvelope) -> FrozenSet[str]:
    """The tool-name grant the gate checks.

    An approval envelope (WA / node owner) is minted NARROW on purpose — only
    the approved tool — so that ``requires_approval`` is not widened. On the
    tool-name axis it is unioned with the deployment grant (tool_approval.py
    §2), otherwise a guidance task could use no ordinary tool at all.
    """
    if envelope.issuer.kind in _APPROVAL_ISSUERS:
        return envelope.granted_tools | (cached_enabled_tools() or frozenset())
    return envelope.granted_tools


def _contains_secret_ref(value: Any) -> bool:
    if isinstance(value, str):
        return _SECRET_REF_MARKER in value
    if isinstance(value, dict):
        return any(_contains_secret_ref(v) for v in value.values())
    if isinstance(value, (list, tuple)):
        return any(_contains_secret_ref(v) for v in value)
    return False


def _arguments_changed(
    parameters: Mapping[str, Any], reviewed: Mapping[str, Any], channel_id: Optional[str], task_id: Optional[str]
) -> Optional[str]:
    """Why the dispatch arguments are not the reviewed ones, or ``None``."""
    for key, value in parameters.items():
        if key in reviewed:
            if value != reviewed[key] and not _contains_secret_ref(reviewed[key]):
                return f"argument {key!r} differs from the reviewed value"
        elif key == "channel_id":
            if value != channel_id:
                return "channel_id differs from the reviewed target"
        elif key == "task_id":
            if value != task_id:
                return "task_id is not the handler-authoritative task"
        else:
            return f"argument {key!r} was not reviewed"
    missing = [k for k in reviewed if k not in parameters]
    if missing:
        return f"reviewed arguments missing at dispatch: {sorted(missing)}"
    return None


async def _provider_declares_enrichment(service: Any, tool_name: str) -> bool:
    getter = getattr(service, "get_tool_info", None)
    if not callable(getter):
        return False
    info = getter(tool_name)
    if inspect.isawaitable(info):
        info = await info
    return bool(getattr(info, "context_enrichment", False) is True)


def _refuse(reason: GateRefusalReason, tool_name: str, detail: str, subject: Optional[ToolInvocationSubject]) -> GateRefusal:
    return GateRefusal(
        reason=reason, tool_name=tool_name, detail=detail, subject=subject.describe() if subject else "none"
    )


def _check_reasoning(
    subject: ToolInvocationSubject, envelope: TaskEnvelope, tool_name: str, parameters: Mapping[str, Any]
) -> Optional[GateRefusal]:
    """rc21 §4 dispatch for a model-selected call: only an admitted reviewed fingerprint runs."""
    call = subject.reviewed_call
    if call is None:
        return _refuse(GateRefusalReason.NOT_REVIEWED, tool_name, "no reviewed call accompanies this dispatch", subject)
    fingerprint = reviewed_call_fingerprint(tool_name, call.arguments, call.channel_id)
    if fingerprint != call.fingerprint:
        return _refuse(
            GateRefusalReason.NOT_REVIEWED, tool_name, f"changed call: dispatching {fingerprint}, reviewed {call.fingerprint}", subject
        )
    thought_id = subject.thought_id or ""
    entry = passed_entry_for(thought_id, fingerprint)
    if entry is None or entry.task_id != subject.task_id:
        return _refuse(
            GateRefusalReason.NOT_REVIEWED, tool_name, f"no passed record names {fingerprint} in thought {thought_id}", subject
        )
    if entry.record.missing_faculties:
        return _refuse(
            GateRefusalReason.REVIEW_INCOMPLETE,
            tool_name,
            f"the record lacks {sorted(entry.record.missing_faculties)}",
            subject,
        )
    blocking = undischarged_objections(entry, review_entries_for(thought_id))
    if blocking:
        return _refuse(
            GateRefusalReason.OBJECTION_UNDISCHARGED,
            tool_name,
            f"objections {[b.digest for b in blocking]} against this call are not discharged by a trusted row",
            subject,
        )
    if envelope.issuer.kind in _APPROVAL_ISSUERS and tool_name in envelope.granted_tools:
        # The call rests on a Wise Authority / owner approval: only its call_fingerprint runs.
        if fingerprint not in envelope.approved_calls:
            return _refuse(
                GateRefusalReason.APPROVAL_MISMATCH,
                tool_name,
                f"the approval binds {sorted(envelope.approved_calls)}, not {fingerprint}",
                subject,
            )
    authority = _authority_unbacked(envelope, tool_name)
    if authority is not None:
        return _refuse(GateRefusalReason.EFFECT_UNTRUSTED_UNACKNOWLEDGED, tool_name, authority, subject)
    if not entry.derived_from:
        return _refuse(
            GateRefusalReason.EFFECT_UNTRUSTED_UNACKNOWLEDGED,
            tool_name,
            "the action does not declare the untrusted input its arguments derive from",
            subject,
        )
    changed = _arguments_changed(parameters, call.arguments, call.channel_id, subject.task_id)
    if changed is not None:
        return _refuse(GateRefusalReason.NOT_REVIEWED, tool_name, f"changed call: {changed}", subject)
    return None


def _authority_unbacked(envelope: TaskEnvelope, tool_name: str) -> Optional[str]:
    """Why an action that claims to act for a person lacks the trusted row for it, or ``None``.

    A tool restricted to named principals claims, when it runs, to act for one
    of them. The trusted row is the requester's VERIFIED id among them (never a
    display name). Constitution answer 2026-11-18: a claimed authority without
    its trusted row is ``effect_untrusted_unacknowledged``.
    """
    requester_id = envelope.requester.user_id
    for restriction in _restrictions_for(tool_name):
        if requester_id is None or requester_id not in restriction.authorized_user_ids:
            return (
                f"acts for a principal authorized by {restriction.source_id}, but the verified requester "
                f"{requester_id!r} is not one"
            )
    return None


async def authorize_dispatch(
    service: Any, tool_name: str, parameters: Mapping[str, Any], subject: Optional[ToolInvocationSubject]
) -> Optional[GateRefusal]:
    """``None`` to allow this provider call, else the typed refusal (already logged)."""
    try:
        refusal = await _authorize(service, tool_name, parameters, subject)
    except Exception as exc:  # noqa: BLE001 - an error inside the gate is a denial
        refusal = _refuse(GateRefusalReason.NOT_REVIEWED, tool_name, f"gate error: {type(exc).__name__}: {exc}", subject)
    if refusal is not None:
        _log_denial(refusal)
    elif (
        subject is not None
        and subject.origin is ToolCallOrigin.REASONING
        and subject.thought_id
        and subject.reviewed_call is not None
    ):
        consume_passed_record(subject.thought_id, subject.reviewed_call.fingerprint)
    return refusal


async def _authorize(
    service: Any, tool_name: str, parameters: Mapping[str, Any], subject: Optional[ToolInvocationSubject]
) -> Optional[GateRefusal]:
    if subject is None:
        return _refuse(GateRefusalReason.NO_SUBJECT, tool_name, "no ToolInvocationSubject", subject)
    envelope = subject.envelope
    if envelope is None:
        return _refuse(GateRefusalReason.NO_ENVELOPE, tool_name, "the subject carries no task envelope", subject)

    root = _writes_into_adapter_root(parameters)
    if root is not None:
        return _refuse(
            GateRefusalReason.ADAPTER_PATH_WRITE,
            tool_name,
            f"target is inside adapter discovery root {root}",
            subject,
        )

    if subject.is_task_bound:
        if tool_name not in effective_grant(envelope):
            return _refuse(GateRefusalReason.TOOL_NOT_GRANTED, tool_name, "not in the task envelope's grant", subject)
        if subject.origin is ToolCallOrigin.CONTEXT_ENRICHMENT:
            if not await _provider_declares_enrichment(service, tool_name):
                return _refuse(
                    GateRefusalReason.NOT_ENRICHMENT_TOOL,
                    tool_name,
                    "the provider does not declare it context_enrichment",
                    subject,
                )
            return None
        return _check_reasoning(subject, envelope, tool_name, parameters)

    # Non-task: an enumerated system caller only, under its own grant.
    caller = SYSTEM_CALLERS.get(subject.component or "")
    if caller is None or caller.origin != subject.origin.value:
        return _refuse(
            GateRefusalReason.SYSTEM_CALLER_UNDECLARED,
            tool_name,
            f"component {subject.component!r} via {subject.origin.value} is not a declared system caller",
            subject,
        )
    if envelope.issuer.kind is not EnvelopeIssuerKind.SYSTEM_COMPONENT or envelope.issuer.issuer_id != subject.component:
        return _refuse(
            GateRefusalReason.NO_ENVELOPE, tool_name, "a system caller needs its own SYSTEM_COMPONENT envelope", subject
        )
    if not envelope.permits_tool(tool_name) or (caller.tools is not None and tool_name not in caller.tools):
        return _refuse(GateRefusalReason.TOOL_NOT_GRANTED, tool_name, "not in the system caller's grant", subject)
    if caller.tools is None and not await _provider_declares_enrichment(service, tool_name):
        return _refuse(
            GateRefusalReason.NOT_ENRICHMENT_TOOL, tool_name, "the provider does not declare it context_enrichment", subject
        )
    return None


def _log_denial(refusal: GateRefusal) -> None:
    # ERROR: denials reach the incident log, which is what an operator reads first.
    logger.error(
        "[TOOL_GATE] DENIED %s: %s (%s) subject=%s",
        refusal.tool_name,
        refusal.reason.value,
        refusal.detail,
        refusal.subject,
    )


__all__ = [
    "adapter_discovery_roots",
    "authorize_dispatch",
    "effective_grant",
    "gated_dispatch",
    "register_principal_restriction_source",
    "reset_principal_restriction_sources",
    "ungated_refusal",
]
