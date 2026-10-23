"""A task that completes without speaking releases its interact() at once (CIRISAgent#1320, fix 5).

RATCHET's Market 4 pilot, episode s-000: the agent stored the claim and ended
with TASK_COMPLETE and no SPEAK. ``task_complete_handler`` allows that on API
channels, but ``/v1/agent/interact`` is released only by a SPEAK, so the caller
waited out the whole window and got a 420 s timeout.

Now the handler sends the localized ``agent.completed_without_reply`` notice
under the task's reasoning scope (the #1264 failure-notice pattern), the API
adapter hands it only to the request that task owns, and interact() returns it
with ``outcome: completed_without_reply``. ``response`` still carries text, so
an older client that reads only ``response`` keeps working.
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, Mock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from ciris_engine.logic.adapters.api.api_communication import APICommunicationService
from ciris_engine.logic.adapters.api.dependencies.auth import require_observer
from ciris_engine.logic.adapters.api.routes import agent as agent_routes
from ciris_engine.logic.handlers.terminal.task_complete_handler import TaskCompleteHandler
from ciris_engine.logic.infrastructure.authorization.reasoning_scope import reasoning_scope
from ciris_engine.logic.infrastructure.handlers.base_handler import ActionHandlerDependencies
from ciris_engine.logic.utils.localization import get_string
from ciris_engine.schemas.runtime.enums import TaskStatus, ThoughtStatus, ThoughtType
from ciris_engine.schemas.runtime.messages import IncomingMessage
from ciris_engine.schemas.runtime.models import FinalAction, Task, Thought

# Reuse the route-test app and auth fixtures rather than rebuilding them.
from tests.adapters.api.test_agent_routes import app, auth_context_admin  # noqa: F401

TS = "2026-10-22T00:00:00+00:00"
NOTICE = get_string("en", "agent.completed_without_reply")


def _task(task_id: str, status: TaskStatus, channel_id: str = "api_admin_user") -> Task:
    return Task(
        task_id=task_id,
        channel_id=channel_id,
        description="d",
        status=status,
        created_at=TS,
        updated_at=TS,
    )


def _thought(thought_id: str, action: str, status: ThoughtStatus = ThoughtStatus.COMPLETED) -> Thought:
    return Thought(
        thought_id=thought_id,
        source_task_id="task-1",
        content="c",
        status=status,
        thought_type=ThoughtType.STANDARD,
        created_at=TS,
        updated_at=TS,
        final_action=FinalAction(action_type=action, action_params={}, reasoning="r"),
    )


def _handler(comm: Any) -> TaskCompleteHandler:
    bus = Mock()
    bus.communication = Mock()

    async def _send(channel_id: str, content: str, handler_name: str = "") -> bool:
        return bool(await comm.send_message(channel_id, content))

    bus.communication.send_message_sync = AsyncMock(side_effect=_send)
    deps = ActionHandlerDependencies(bus_manager=bus, time_service=Mock())
    return TaskCompleteHandler(deps)


# ------------------------------------------------------------------ the handler


@pytest.mark.asyncio
async def test_a_silent_completion_sends_the_notice() -> None:
    handler = _handler(Mock(send_message=AsyncMock(return_value=True)))
    handler._send_notification = AsyncMock(return_value=True)  # type: ignore[method-assign]
    with patch(
        "ciris_engine.logic.persistence.get_thoughts_by_task_id",
        return_value=[_thought("t1", "memorize"), _thought("t2", "task_complete")],
    ):
        await handler._handle_completion_notification(_task("task-1", TaskStatus.COMPLETED), "task-1")

    handler._send_notification.assert_awaited_once_with("api_admin_user", NOTICE)


@pytest.mark.asyncio
async def test_a_task_that_replied_sends_no_notice() -> None:
    handler = _handler(Mock())
    handler._send_notification = AsyncMock(return_value=True)  # type: ignore[method-assign]
    with patch(
        "ciris_engine.logic.persistence.get_thoughts_by_task_id",
        return_value=[_thought("t1", "speak"), _thought("t2", "task_complete")],
    ):
        await handler._handle_completion_notification(_task("task-1", TaskStatus.COMPLETED), "task-1")

    handler._send_notification.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_non_api_channel_gets_no_notice() -> None:
    handler = _handler(Mock())
    handler._send_notification = AsyncMock(return_value=True)  # type: ignore[method-assign]
    with patch("ciris_engine.logic.persistence.get_thoughts_by_task_id", return_value=[]):
        await handler._handle_completion_notification(
            _task("task-1", TaskStatus.COMPLETED, channel_id="discord_123"), "task-1"
        )

    handler._send_notification.assert_not_awaited()


# ------------------------------------------------------------------- the outcome


@pytest.mark.parametrize(
    ("status", "actions", "expected"),
    [
        (TaskStatus.COMPLETED, ["memorize", "task_complete"], agent_routes.InteractOutcome.COMPLETED_WITHOUT_REPLY),
        (TaskStatus.COMPLETED, ["speak", "task_complete"], agent_routes.InteractOutcome.COMPLETE),
        (TaskStatus.ACTIVE, ["memorize"], agent_routes.InteractOutcome.COMPLETE),
        (TaskStatus.FAILED, ["memorize"], agent_routes.InteractOutcome.FAILED),
    ],
)
def test_the_outcome_names_a_completion_without_reply(
    status: TaskStatus, actions: List[str], expected: agent_routes.InteractOutcome
) -> None:
    thoughts = [_thought(f"t{i}", a) for i, a in enumerate(actions)]
    with (
        patch("ciris_engine.logic.persistence.get_task_by_id", return_value=_task("task-1", status)),
        patch("ciris_engine.logic.persistence.get_thoughts_by_task_id", return_value=thoughts),
    ):
        assert agent_routes._outcome_for_answered_task("task-1") is expected


def test_the_outcome_value_is_stable() -> None:
    """The wire value a client keys on."""
    assert agent_routes.InteractOutcome.COMPLETED_WITHOUT_REPLY.value == "completed_without_reply"


# ------------------------------------------------------------- end to end


@pytest.mark.asyncio
async def test_interact_returns_on_a_silent_task_complete(app, auth_context_admin, monkeypatch):  # noqa: F811
    """Through the real route and the real API comm service: no SPEAK, and interact still returns."""
    app.state.message_channel_map = {}
    app.state.message_task_map = {}
    comm = APICommunicationService()
    comm._app_state = app.state
    monkeypatch.setattr(comm, "_create_speak_correlation", lambda channel_id, content: None)
    seen: List[str] = []

    async def on_message(msg: IncomingMessage) -> None:
        app.state.message_channel_map.setdefault(msg.channel_id, []).append(msg.message_id)
        app.state.message_task_map[msg.message_id] = "task-1"
        seen.append(msg.channel_id)

    app.state.on_message = on_message
    app.dependency_overrides[require_observer] = lambda: auth_context_admin
    handler = _handler(comm)
    thoughts = [_thought("t1", "memorize"), _thought("t2", "task_complete")]

    try:
        with (
            patch("ciris_engine.logic.persistence.get_thoughts_by_task_id", return_value=thoughts),
            patch(
                "ciris_engine.logic.persistence.get_task_by_id", return_value=_task("task-1", TaskStatus.COMPLETED)
            ),
        ):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                monkeypatch.setenv("CIRIS_API_INTERACTION_TIMEOUT", "10")
                call = asyncio.create_task(client.post("/agent/interact", json={"message": "store this"}))
                for _ in range(200):
                    if seen:
                        break
                    await asyncio.sleep(0.01)
                task = _task("task-1", TaskStatus.COMPLETED, channel_id=seen[0])
                with reasoning_scope(task_id="task-1", thought_id="t2", phase="action_dispatch"):
                    await handler._handle_completion_notification(task, "task-1")
                data: Dict[str, Any] = (await asyncio.wait_for(call, timeout=5)).json()["data"]
    finally:
        app.dependency_overrides.clear()
        for store in (agent_routes._response_events, agent_routes._message_responses, agent_routes._message_task_ids):
            store.clear()

    assert data["outcome"] == "completed_without_reply"
    assert data["task_id"] == "task-1"
    assert data["response"].startswith(NOTICE)
    assert data["processing_time_ms"] < 5000
