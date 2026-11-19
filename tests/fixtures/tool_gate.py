"""Build the ToolInvocationSubject a production ToolHandler dispatch carries.

The Phase 2 tool gate (``dispatch_gate``, CIRISAgent#1366 item 19) denies any
``ToolBus`` call without a subject. In production the ToolHandler attaches one:
a task-bound REASONING subject under the task's envelope, naming the reviewed
call the thought processor admitted after all four LLM consciences passed.

Tests that exercise bus routing or provider behaviour (not the gate itself)
use :func:`admitted_tool_subject` to make the same call production makes,
instead of an identity-less one the gate correctly refuses. The gate's own
rules are pinned in ``tests/ciris_engine/logic/infrastructure/authorization``.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from ciris_engine.logic.infrastructure.authorization.reviewed_action import (
    admit_reviewed_action,
    make_review_entry,
    reviewed_call_fingerprint,
)
from ciris_engine.schemas.api.auth import UserRole
from ciris_engine.schemas.runtime.reviewed_action_admission import (
    REQUIRED_REVIEW_CONSCIENCES,
    ReviewedCall,
    ReviewOutcome,
    ReviewRecord,
)
from ciris_engine.schemas.runtime.task_envelope import (
    ALL_TOOL_CAPABILITIES,
    DeploymentScope,
    EnvelopeIssuer,
    EnvelopeIssuerKind,
    EnvironmentTier,
    RequesterAuthorization,
    TaskEnvelope,
    ToolInvocationSubject,
)

TEST_TASK_ID = "task-tool-gate-fixture"
TEST_THOUGHT_ID = "thought-tool-gate-fixture"


def admitted_tool_subject(
    tool_name: str,
    arguments: Dict[str, Any],
    *,
    channel_id: Optional[str] = None,
    task_id: str = TEST_TASK_ID,
    thought_id: str = TEST_THOUGHT_ID,
) -> ToolInvocationSubject:
    """Admit one passed review of ``tool_name(arguments)`` and return its subject.

    Single-use, as in production: one admitted review authorizes one dispatch
    of exactly these arguments.
    """
    fingerprint = reviewed_call_fingerprint(tool_name, arguments, channel_id)
    admitted = admit_reviewed_action(
        make_review_entry(
            ReviewRecord(
                fingerprint=fingerprint,
                thought=thought_id,
                outcome=ReviewOutcome.PASSED,
                faculties=tuple(sorted(REQUIRED_REVIEW_CONSCIENCES)),
            ),
            task_id=task_id,
            derived_from=("request:sha256:00",),
        )
    )
    assert admitted is not None, "the fixture review record was not admitted"
    envelope = TaskEnvelope(
        envelope_id=f"env-{task_id}",
        task_id=task_id,
        issued_at="2026-11-18T00:00:00Z",
        issuer=EnvelopeIssuer(kind=EnvelopeIssuerKind.DEPLOYMENT_RESOLVED),
        deployment=DeploymentScope(environment_tier=EnvironmentTier.QA, agent_id="ally", template="ally"),
        requester=RequesterAuthorization(user_id="user-1", role=UserRole.OBSERVER),
        granted_tools=frozenset({tool_name}),
        capabilities=ALL_TOOL_CAPABILITIES,
    )
    return ToolInvocationSubject.for_task(
        task_id=task_id,
        thought_id=thought_id,
        handler_name="ToolHandler",
        envelope=envelope,
        reviewed_call=ReviewedCall(
            fingerprint=fingerprint, tool_name=tool_name, arguments=arguments, channel_id=channel_id
        ),
    )


__all__ = ["TEST_TASK_ID", "TEST_THOUGHT_ID", "admitted_tool_subject"]
