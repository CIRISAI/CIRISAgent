"""Task-envelope issuance (CIRISAgent#938, Phase 1).

The one property this file exists to hold: **an envelope is issued from outside
the reasoning loop.** If the agent can mint or widen its own envelope,
everything built on top is theater.

Three entry points, and only three:

* :func:`issue_deployment_envelope` — the deterministic resolver. Runs at task
  creation, resolves ``(environment tier, agent role/template, enabled tools,
  requester authorization)`` and freezes the result. Refuses to run inside a
  reasoning scope.
* :func:`issue_authority_envelope` — an explicit owner/WA grant, for anything
  the deterministic resolver cannot know. Refuses to run inside a reasoning
  scope.
* :func:`attenuate_envelope` — narrowing only, and therefore *permitted*
  inside a reasoning scope: a capability that is being given away cannot be a
  privilege escalation. Widening raises
  :class:`~ciris_engine.schemas.runtime.task_envelope.EnvelopeWideningError`
  and there is no widening entry point anywhere.

Plus :func:`resolve_task_envelope`, a read-only lookup used at the bus call
site. It never mints.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, FrozenSet, Iterable, Optional, Tuple

from ciris_engine.logic.infrastructure.authorization.deployment import resolve_deployment_scope
from ciris_engine.logic.infrastructure.authorization.enabled_tools import (
    ToolNameSource,
    cached_enabled_tools,
    prime_enabled_tools,
)
from ciris_engine.logic.infrastructure.authorization.reasoning_scope import (
    current_reasoning_scope,
    in_reasoning_scope,
)
from ciris_engine.schemas.runtime.task_envelope import (
    ALL_TOOL_CAPABILITIES,
    DeploymentScope,
    EnvelopeIssuer,
    EnvelopeIssuerKind,
    IssuedCredential,
    RequesterAuthorization,
    TargetRoot,
    TaskEnvelope,
    ToolCapability,
)

if TYPE_CHECKING:
    from ciris_engine.protocols.services.lifecycle.time import TimeServiceProtocol
    from ciris_engine.schemas.runtime.models import Task

logger = logging.getLogger(__name__)


class EnvelopeIssuanceForbidden(RuntimeError):
    """Raised when envelope minting is attempted from inside the reasoning loop.

    This is the runtime expression of "the envelope is issued from outside the
    reasoning loop". See ``reasoning_scope`` for exactly what that guard proves
    and, more importantly, what it does not.
    """


def _forbid_in_reasoning_scope(operation: str) -> None:
    if in_reasoning_scope():
        scope = current_reasoning_scope()
        detail = f"task={scope.task_id} thought={scope.thought_id} phase={scope.phase}" if scope else "unknown"
        raise EnvelopeIssuanceForbidden(
            f"{operation} was called from inside the reasoning loop ({detail}). "
            "Task envelopes are issued from outside the reasoning loop by design "
            "(CIRISAgent#938); a reasoning path that needs a narrower scope must "
            "use attenuate_envelope(), which cannot widen."
        )


def _now_iso(time_service: Optional["TimeServiceProtocol"] = None) -> str:
    if time_service is not None:
        try:
            return str(time_service.now_iso())
        except Exception:  # pragma: no cover - defensive
            pass
    return datetime.now(timezone.utc).isoformat()


async def issue_deployment_envelope(
    *,
    task_id: str,
    agent_occurrence_id: str = "default",
    requester: Optional[RequesterAuthorization] = None,
    tool_source: Optional[ToolNameSource] = None,
    time_service: Optional["TimeServiceProtocol"] = None,
) -> TaskEnvelope:
    """Mint the deployment-resolved envelope for a newly created task.

    The grant is resolved, not declared: the enabled-tool set comes from the
    live registry and is written into the envelope as an explicit enumeration.
    By construction it is identical for every task in the deployment — the
    envelope is bound per task for attribution and for future narrowing, not
    because the grant differs.

    Consequential tools (kick/ban, Home Assistant, spend) are **included**.
    Their control is the conscience layer and Wisdom-Based Deferral, which
    judge the specific content; the envelope must not preempt that judgement.

    Raises:
        EnvelopeIssuanceForbidden: if called from inside the reasoning loop.
    """
    _forbid_in_reasoning_scope("issue_deployment_envelope")

    granted_tools = await prime_enabled_tools(tool_source)
    if not granted_tools:
        logger.warning(
            "TaskEnvelope: issuing envelope for task %s with an EMPTY tool grant — "
            "the tool registry has not been observed yet. Inert in Phase 1; under "
            "Phase 2 enforcement this would deny every tool call for this task.",
            task_id,
        )

    return TaskEnvelope(
        envelope_id=f"env_{uuid.uuid4().hex}",
        task_id=task_id,
        issued_at=_now_iso(time_service),
        issuer=EnvelopeIssuer(kind=EnvelopeIssuerKind.DEPLOYMENT_RESOLVED),
        deployment=resolve_deployment_scope(agent_occurrence_id),
        requester=requester or RequesterAuthorization(),
        granted_tools=granted_tools,
        # CIRISAgent declares the full effect-class set: with a near-total tool
        # grant, claiming a narrower effect summary would be false. Verticals
        # with typed tasks resolve a strict subset.
        capabilities=ALL_TOOL_CAPABILITIES,
    )


def issue_deployment_envelope_from_cache(
    *,
    task_id: str,
    agent_occurrence_id: str = "default",
    requester: Optional[RequesterAuthorization] = None,
    time_service: Optional["TimeServiceProtocol"] = None,
) -> TaskEnvelope:
    """Synchronous sibling of :func:`issue_deployment_envelope`.

    For task-creation sites that are not ``async`` (``TaskManager.create_task``
    and the system tasks it builds). Uses the cached enabled-tool set; if the
    registry has never been observed the grant is empty and a warning names the
    task.

    Raises:
        EnvelopeIssuanceForbidden: if called from inside the reasoning loop.
    """
    _forbid_in_reasoning_scope("issue_deployment_envelope_from_cache")

    granted_tools = cached_enabled_tools()
    if granted_tools is None:
        logger.warning(
            "TaskEnvelope: issuing envelope for task %s with an EMPTY tool grant — "
            "the tool registry has not been observed yet (sync issuance path). "
            "Inert in Phase 1; under Phase 2 enforcement this would deny every "
            "tool call for this task.",
            task_id,
        )
        granted_tools = frozenset()

    return TaskEnvelope(
        envelope_id=f"env_{uuid.uuid4().hex}",
        task_id=task_id,
        issued_at=_now_iso(time_service),
        issuer=EnvelopeIssuer(kind=EnvelopeIssuerKind.DEPLOYMENT_RESOLVED),
        deployment=resolve_deployment_scope(agent_occurrence_id),
        requester=requester or RequesterAuthorization(),
        granted_tools=granted_tools,
        capabilities=ALL_TOOL_CAPABILITIES,
    )


def issue_authority_envelope(
    *,
    task_id: str,
    issuer_kind: EnvelopeIssuerKind,
    issuer_id: str,
    granted_tools: Iterable[str],
    capabilities: Iterable[ToolCapability],
    deployment: Optional[DeploymentScope] = None,
    agent_occurrence_id: str = "default",
    requester: Optional[RequesterAuthorization] = None,
    target_roots: Tuple[TargetRoot, ...] = (),
    credentials: Tuple[IssuedCredential, ...] = (),
    time_service: Optional["TimeServiceProtocol"] = None,
) -> TaskEnvelope:
    """Mint an envelope from an explicit owner/WA grant.

    Everything the deterministic resolver cannot know — a declared target root,
    an issued credential, a deliberately narrowed grant — comes through here,
    and only with a named issuer.

    Raises:
        EnvelopeIssuanceForbidden: if called from inside the reasoning loop.
        ValueError: if ``issuer_kind`` is the deterministic resolver's.
    """
    _forbid_in_reasoning_scope("issue_authority_envelope")

    if issuer_kind is EnvelopeIssuerKind.DEPLOYMENT_RESOLVED:
        raise ValueError(
            "issue_authority_envelope requires a named authority "
            "(WISE_AUTHORITY or NODE_OWNER); use issue_deployment_envelope for the resolver"
        )

    return TaskEnvelope(
        envelope_id=f"env_{uuid.uuid4().hex}",
        task_id=task_id,
        issued_at=_now_iso(time_service),
        issuer=EnvelopeIssuer(kind=issuer_kind, issuer_id=issuer_id),
        deployment=deployment or resolve_deployment_scope(agent_occurrence_id),
        requester=requester or RequesterAuthorization(),
        granted_tools=frozenset(granted_tools),
        capabilities=frozenset(capabilities),
        target_roots=tuple(target_roots),
        credentials=tuple(credentials),
    )


def attenuate_envelope(
    envelope: TaskEnvelope,
    *,
    granted_tools: Optional[Iterable[str]] = None,
    capabilities: Optional[Iterable[ToolCapability]] = None,
    target_roots: Optional[Tuple[TargetRoot, ...]] = None,
    credentials: Optional[Tuple[IssuedCredential, ...]] = None,
    time_service: Optional["TimeServiceProtocol"] = None,
) -> TaskEnvelope:
    """Narrow an existing envelope. Permitted inside the reasoning loop.

    Giving capability away is not privilege escalation, so this is the one
    envelope operation the reasoning path may perform. It cannot widen:
    :meth:`TaskEnvelope.attenuate` raises ``EnvelopeWideningError`` on any
    superset argument.

    CIRISAgent ships **no narrowing policy** — nothing in the product path
    calls this. It exists for the typed-task verticals (CIRISMedical,
    CIRISFinancial) where task purpose is knowable at creation.
    """
    return envelope.attenuate(
        envelope_id=f"env_{uuid.uuid4().hex}",
        issued_at=_now_iso(time_service),
        granted_tools=granted_tools,
        capabilities=capabilities,
        target_roots=target_roots,
        credentials=credentials,
    )


def attach_envelope_to_task(task: "Task", envelope: TaskEnvelope) -> None:
    """Bind ``envelope`` to ``task``'s context before the task is persisted.

    Called by task-creation sites only, never from the reasoning loop; the
    guard lives on the issuance functions that produce the envelope in the
    first place.
    """
    from ciris_engine.schemas.runtime.models import TaskContext

    if envelope.task_id != task.task_id:
        raise ValueError(
            f"envelope {envelope.envelope_id} is bound to task {envelope.task_id}, not {task.task_id}"
        )
    if task.context is None:
        task.context = TaskContext(
            channel_id=task.channel_id,
            user_id=None,
            correlation_id=str(uuid.uuid4()),
            parent_task_id=task.parent_task_id,
            agent_occurrence_id=task.agent_occurrence_id,
            envelope=envelope,
        )
    else:
        task.context = task.context.model_copy(update={"envelope": envelope})


def issue_task_envelope_best_effort(
    task: "Task",
    *,
    requester: Optional[RequesterAuthorization] = None,
    time_service: Optional["TimeServiceProtocol"] = None,
) -> None:
    """Issue and bind an envelope for a synchronously-created task.

    Convenience wrapper for the non-async task-creation sites (system tasks,
    wakeup/dream steps). Best-effort by design: an issuance failure must not
    drop a task. A task with no envelope is a denial to a future gate, never a
    bypass.

    Raises:
        EnvelopeIssuanceForbidden: propagated, never swallowed — a mint attempt
            from inside the reasoning loop is a defect, not a transient error.
    """
    try:
        envelope = issue_deployment_envelope_from_cache(
            task_id=task.task_id,
            agent_occurrence_id=task.agent_occurrence_id,
            requester=requester
            or RequesterAuthorization(
                user_id=getattr(task.context, "user_id", None) if task.context else None,
                channel_id=task.channel_id,
                source_ref=getattr(task.context, "correlation_id", None) if task.context else None,
            ),
            time_service=time_service,
        )
        attach_envelope_to_task(task, envelope)
    except EnvelopeIssuanceForbidden:
        raise
    except Exception as exc:
        logger.warning(
            "Failed to issue task envelope for task %s: %s. Task proceeds with no envelope "
            "(a denial to any future tool gate, never a bypass).",
            task.task_id,
            exc,
        )


def deployment_capabilities() -> FrozenSet[ToolCapability]:
    """The effect classes a CIRISAgent deployment declares. Enumerated, not wildcarded."""
    return ALL_TOOL_CAPABILITIES


__all__ = [
    "EnvelopeIssuanceForbidden",
    "attach_envelope_to_task",
    "attenuate_envelope",
    "deployment_capabilities",
    "issue_authority_envelope",
    "issue_deployment_envelope",
    "issue_deployment_envelope_from_cache",
    "issue_task_envelope_best_effort",
]
