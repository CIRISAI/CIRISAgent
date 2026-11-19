"""Typed task origin (#1366): who created a task, set by the creating code, and what the ablated judges see.

- ``TaskContext.origin`` round-trips through both task loaders (each rebuilds TaskContext from a fixed field list).
- The creation sites set it: an adapter message is USER, the shared wakeup/shutdown tasks, wakeup steps, system tasks
  and guidance tasks are ENGINE_*.
- Under a trusted rule, entropy and the optimization veto see an engine-created task's sender as the engine (id = the
  agent's id, role SYSTEM, verified by system); a guidance task's as the resolving Wise Authority when its certificate
  role was read, otherwise the engine. A user task with no verified sender stays "not verified": SYSTEM is never
  derived from a missing sender.
"""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, Mock, patch

import pytest

from ciris_engine.schemas.runtime.enums import TaskOrigin, TaskStatus
from ciris_engine.schemas.runtime.models import Task, TaskContext, WAAuthorization
from ciris_engine.schemas.services.authority_core import WARole
from tests.ciris_engine.logic.test_verified_sender_phase2_1366 import _id_scoped_identity, _judges
from tests.fixtures.persist_engine import persist_engine  # noqa: F401

_NOW = "2026-11-18T00:00:00+00:00"
_ABLATED = [j for j in _judges() if j[3]]


def _task(origin: Optional[TaskOrigin], task_id: str = "task-origin") -> Task:
    return Task(
        task_id=task_id,
        channel_id="api_ch",
        description="d",
        status=TaskStatus.ACTIVE,
        created_at=_NOW,
        updated_at=_NOW,
        context=TaskContext(channel_id="api_ch", correlation_id="c-origin", origin=origin),
    )


# ------------------------------------------------------------------------------------------------ persistence


@pytest.mark.parametrize("origin", [TaskOrigin.ENGINE_WAKEUP, TaskOrigin.ENGINE_GUIDANCE, TaskOrigin.USER])
def test_origin_round_trips_through_both_loaders(persist_engine: Any, origin: TaskOrigin) -> None:
    from ciris_engine.logic.persistence.models.tasks import (
        _persist_row_to_task,
        _task_to_persist_payload,
        add_task,
        get_task_by_id,
    )
    from ciris_engine.logic.persistence.utils import map_row_to_task

    add_task(_task(origin))
    loaded = get_task_by_id("task-origin", "default")
    assert loaded is not None and loaded.context is not None and loaded.context.origin is origin

    payload = _task_to_persist_payload(_task(origin))
    assert _persist_row_to_task(payload).context.origin is origin
    row = dict(payload, context_json=json.dumps(payload["context"]))
    assert map_row_to_task(row).context.origin is origin


def test_an_unrecorded_or_unknown_origin_loads_as_none() -> None:
    from ciris_engine.logic.persistence.models.tasks import _persist_row_to_task, _task_to_persist_payload

    payload = _task_to_persist_payload(_task(None))
    assert _persist_row_to_task(payload).context.origin is None
    payload["context"]["origin"] = "engine_something_new"
    assert _persist_row_to_task(payload).context.origin is None


# ------------------------------------------------------------------------------------------------ creation sites


def test_create_task_sets_and_keeps_the_origin() -> None:
    from ciris_engine.logic.utils.task_thought_factory import create_task

    task = create_task(
        description="d", channel_id="c", agent_occurrence_id="occ", correlation_id="x", origin=TaskOrigin.USER
    )
    assert task.context is not None and task.context.origin is TaskOrigin.USER
    # The occurrence-id correction rebuilds the context and must keep it.
    ctx = TaskContext(correlation_id="x", agent_occurrence_id="other", origin=TaskOrigin.ENGINE_DREAM)
    task = create_task(description="d", channel_id="c", agent_occurrence_id="occ", correlation_id="x", context=ctx)
    assert task.context is not None and task.context.origin is TaskOrigin.ENGINE_DREAM


@pytest.mark.parametrize(
    "task_type, origin", [("wakeup", TaskOrigin.ENGINE_WAKEUP), ("shutdown", TaskOrigin.ENGINE_SHUTDOWN)]
)
def test_shared_tasks_carry_the_engine_origin(task_type: str, origin: TaskOrigin) -> None:
    from ciris_engine.logic.persistence.models import tasks

    with patch(
        "ciris_engine.logic.infrastructure.authorization.envelope_issuer.issue_deployment_envelope_from_cache",
        side_effect=RuntimeError("cold cache"),
    ):
        ctx = tasks._shared_task_context("X_SHARED_1", "ch", Mock(), task_type)
    # Even with no envelope (denied by the gate), the task records who created it.
    assert ctx.origin is origin and ctx.envelope is None


def test_add_system_task_marks_an_unrecorded_origin_engine_system() -> None:
    from ciris_engine.logic.persistence.models import tasks

    task = _task(None)
    with patch.object(tasks, "add_task", return_value=task.task_id), patch(
        "ciris_engine.logic.infrastructure.authorization.envelope_issuer.issue_task_envelope_best_effort"
    ):
        asyncio.run(tasks.add_system_task(task))
    assert task.context is not None and task.context.origin is TaskOrigin.ENGINE_SYSTEM
    kept = _task(TaskOrigin.ENGINE_WAKEUP)
    with patch.object(tasks, "add_task", return_value=kept.task_id), patch(
        "ciris_engine.logic.infrastructure.authorization.envelope_issuer.issue_task_envelope_best_effort"
    ):
        asyncio.run(tasks.add_system_task(kept))
    assert kept.context is not None and kept.context.origin is TaskOrigin.ENGINE_WAKEUP


def test_the_wa_role_is_read_from_the_certificate() -> None:
    from ciris_engine.logic.services.governance.wise_authority.service import WiseAuthorityService

    service = object.__new__(WiseAuthorityService)
    service.auth_service = Mock(get_wa=AsyncMock(return_value=SimpleNamespace(role=WARole.AUTHORITY)))
    assert asyncio.run(service._wa_role("wa-1")) is WARole.AUTHORITY
    service.auth_service = Mock(get_wa=AsyncMock(return_value=None))
    assert asyncio.run(service._wa_role("wa-1")) is None
    service.auth_service = Mock(get_wa=AsyncMock(side_effect=RuntimeError("store down")))
    assert asyncio.run(service._wa_role("wa-1")) is None


# ------------------------------------------------------------------------------------------------ the ablated judges


def _judge(cls: type, result: Any, context: Any) -> Dict[str, Any]:
    from ciris_engine.logic.prompt_assembly.assembler import current_guard_mode
    from ciris_engine.schemas.context.prompt_provenance import AssemblyMode
    from tests.ciris_engine.logic.conscience.test_context_flow_1366 import _conscience, _speak

    assert current_guard_mode() == AssemblyMode.FAIL_CLOSED  # a violation would raise, not be stripped
    seen: Dict[str, Any] = {}
    with patch("ciris_engine.logic.persistence.get_thoughts_by_task_id", return_value=[]):
        asyncio.run(_conscience(cls, seen, result).check(_speak(), context))
    seen["sent"] = json.dumps([m.content for m in seen["messages"]], ensure_ascii=False)
    assert seen["manifest"].guard_violations == []
    (seen["sender"],) = [r for r in seen["manifest"].segments if r.kind.value == "sender_identity"]
    return seen


def _context(origin: Optional[TaskOrigin], grant: Optional[WAAuthorization] = None, **task_fields: Any) -> Any:
    from ciris_engine.schemas.conscience.context import ConscienceCheckContext

    thought = SimpleNamespace(thought_id="t1", source_task_id="task-origin", agent_occurrence_id="default", content="c")
    task = SimpleNamespace(description="d", context=TaskContext(correlation_id="c", origin=origin), **task_fields)
    return ConscienceCheckContext(
        thought=thought, task=task, agent_identity=_id_scoped_identity(), wa_authorization=grant
    )


@pytest.mark.parametrize("origin", [TaskOrigin.ENGINE_WAKEUP, TaskOrigin.ENGINE_DREAM, TaskOrigin.ENGINE_SYSTEM])
@pytest.mark.parametrize("name, cls, result, ablated", _ABLATED)
def test_an_engine_task_is_sent_by_the_system(origin: TaskOrigin, name: str, cls: type, result: Any, ablated: bool) -> None:
    from ciris_engine.logic.formatters.verified_sender import conscience_sender_block

    context = _context(origin)
    seen = _judge(cls, result, context)
    assert "id: ally" in seen["sent"] and "role: SYSTEM" in seen["sent"] and "verified by: system" in seen["sent"]
    authn = seen["sender"].authn
    assert (authn.subject_id, authn.role, authn.verifier) == ("ally", "SYSTEM", "system")
    assert "role: SYSTEM" in conscience_sender_block(context, "en", ablated=True)


@pytest.mark.parametrize("origin", [TaskOrigin.USER, None])
@pytest.mark.parametrize("name, cls, result, ablated", _ABLATED)
def test_a_user_task_without_a_sender_is_not_verified(
    origin: Optional[TaskOrigin], name: str, cls: type, result: Any, ablated: bool
) -> None:
    seen = _judge(cls, result, _context(origin))
    assert "role: not verified" in seen["sent"] and "SYSTEM" not in seen["sent"]
    assert (seen["sender"].authn.role, seen["sender"].authn.verifier) == ("not verified", "unverified")


@pytest.mark.parametrize("name, cls, result, ablated", _ABLATED)
def test_a_message_coalesced_onto_an_engine_task_keeps_its_sender(name: str, cls: type, result: Any, ablated: bool) -> None:
    """An update recorded on an engine task is a person's message: never shown as SYSTEM."""
    from ciris_engine.schemas.runtime.models import VerifiedSender

    seen = _judge(cls, result, _context(TaskOrigin.ENGINE_WAKEUP, updated_info_sender=VerifiedSender()))
    assert "SYSTEM" not in seen["sent"]


def _grant(role: Optional[WARole]) -> WAAuthorization:
    return WAAuthorization(
        wa_id="wa-2026-AUTH-5562FD", deferral_id="defer_1", granted_at=_NOW, guidance="Use the portal.", wa_role=role
    )


@pytest.mark.parametrize("name, cls, result, ablated", _ABLATED)
def test_a_guidance_task_is_sent_by_the_resolving_wise_authority(name: str, cls: type, result: Any, ablated: bool) -> None:
    seen = _judge(cls, result, _context(TaskOrigin.ENGINE_GUIDANCE, _grant(WARole.AUTHORITY)))
    authn = seen["sender"].authn
    assert (authn.subject_id, authn.role, authn.verifier) == ("wa-2026-AUTH-5562FD", "AUTHORITY", "wa_signature")
    assert seen["sender"].source.value == "signed_row"
    assert "SYSTEM" not in seen["sent"]


@pytest.mark.parametrize("name, cls, result, ablated", _ABLATED)
def test_a_guidance_task_without_a_verified_wa_role_is_sent_by_the_system(
    name: str, cls: type, result: Any, ablated: bool
) -> None:
    seen = _judge(cls, result, _context(TaskOrigin.ENGINE_GUIDANCE, _grant(None)))
    assert (seen["sender"].authn.role, seen["sender"].authn.verifier) == ("SYSTEM", "system")


def test_origin_values_are_closed() -> None:
    engine: List[TaskOrigin] = [o for o in TaskOrigin if o.is_engine]
    assert all(o.value.startswith("engine_") for o in engine)
    assert not TaskOrigin.USER.is_engine and not TaskOrigin.WISE_AUTHORITY.is_engine
