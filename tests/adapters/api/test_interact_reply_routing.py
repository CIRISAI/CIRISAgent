"""A SPEAK is delivered to the interact() request its own task owns — never
to whichever request happens to be next on the channel.

The bug: `_handle_api_interaction_response` matched SPEAKs to waiting requests
FIFO per channel. interact() removes a timed-out message_id from the queue,
so when that task SPEAKs late it popped the NEXT request's message_id, and the
user's next question was answered with the previous question's reply.

The fix routes by task: the adapter records message_id -> task_id when the
observer returns, and the SPEAK carries its task through the reasoning scope
the ActionDispatcher sets around the handler (SPEAK reaches `send_message`
inline via `send_message_sync`).
"""

import asyncio
from types import SimpleNamespace
from typing import Dict, List

import pytest
from httpx import ASGITransport, AsyncClient

from ciris_engine.logic.adapters.api.api_communication import APICommunicationService
from ciris_engine.logic.adapters.api.dependencies.auth import require_observer
from ciris_engine.logic.adapters.api.routes import agent as agent_routes
from ciris_engine.logic.infrastructure.authorization.reasoning_scope import reasoning_scope
from ciris_engine.schemas.runtime.messages import IncomingMessage

# Reuse the route-test app and auth fixtures rather than rebuilding them.
from tests.adapters.api.test_agent_routes import app, auth_context_admin  # noqa: F401


class _Channels:
    """app.state as the adapter shapes it, plus a comm service bound to it."""

    def __init__(self) -> None:
        self.state = SimpleNamespace(message_channel_map={}, message_task_map={})
        self.request = SimpleNamespace(app=SimpleNamespace(state=self.state))
        self.comm = APICommunicationService()
        self.comm._app_state = self.state

    def submit(self, channel_id: str, message_id: str, task_id: str) -> asyncio.Event:
        """What interact() + the adapter's message handler do for one request."""
        event = asyncio.Event()
        agent_routes._response_events[message_id] = event
        self.state.message_channel_map.setdefault(channel_id, []).append(message_id)
        self.state.message_task_map[message_id] = task_id
        return event

    def time_out(self, message_id: str) -> None:
        """What interact() does when its deadline passes."""
        agent_routes._cleanup_interaction_tracking(message_id, self.request)  # type: ignore[arg-type]

    async def speak(self, channel_id: str, task_id: str, content: str) -> None:
        with reasoning_scope(task_id=task_id, thought_id=f"th_{task_id}", phase="action_dispatch"):
            await self.comm._handle_api_interaction_response(channel_id, content)


@pytest.fixture
def channels():
    ch = _Channels()
    yield ch
    for store in (agent_routes._response_events, agent_routes._message_responses, agent_routes._message_task_ids):
        for key in [k for k in store if k.startswith("m")]:
            store.pop(key, None)


@pytest.mark.asyncio
class TestReplyRouting:
    async def test_late_reply_is_not_delivered_to_the_next_request(self, channels):
        channels.submit("api_u", "m1", "task-1")
        channels.time_out("m1")
        e2 = channels.submit("api_u", "m2", "task-2")

        await channels.speak("api_u", "task-1", "answer to question ONE")

        assert not e2.is_set(), "a timed-out task's late SPEAK answered the next request"
        assert "m2" not in agent_routes._message_responses
        assert channels.state.message_channel_map["api_u"] == ["m2"], "the next request must still be waiting"

        await channels.speak("api_u", "task-2", "answer to question TWO")
        assert e2.is_set()
        assert agent_routes._message_responses["m2"] == "answer to question TWO"
        assert agent_routes._message_task_ids["m2"] == "task-2"

    async def test_normal_request_reply_unchanged(self, channels):
        e1 = channels.submit("api_u", "m1", "task-1")
        await channels.speak("api_u", "task-1", "hello")
        assert e1.is_set()
        assert agent_routes._message_responses["m1"] == "hello"
        assert channels.state.message_channel_map["api_u"] == []
        assert "m1" not in channels.state.message_task_map

    async def test_task_append_one_task_owns_several_requests(self, channels):
        # With task-append, m2 was folded into task-1 (the active task on the
        # channel); task-1's SPEAKs answer its own requests oldest first.
        e1 = channels.submit("api_u", "m1", "task-1")
        e2 = channels.submit("api_u", "m2", "task-1")
        await channels.speak("api_u", "task-1", "first")
        assert e1.is_set() and not e2.is_set()
        await channels.speak("api_u", "task-1", "second")
        assert e2.is_set()
        assert agent_routes._message_responses["m2"] == "second"

    async def test_task_append_after_timeout_goes_to_the_same_tasks_live_request(self, channels):
        channels.submit("api_u", "m1", "task-1")
        channels.time_out("m1")
        e2 = channels.submit("api_u", "m2", "task-1")  # appended to the still-running task
        await channels.speak("api_u", "task-1", "reply covering both")
        assert e2.is_set()

    async def test_reply_skips_other_tasks_queued_ahead(self, channels):
        e1 = channels.submit("api_u", "m1", "task-1")
        e2 = channels.submit("api_u", "m2", "task-2")
        await channels.speak("api_u", "task-2", "two finished first")
        assert e2.is_set() and not e1.is_set()
        assert channels.state.message_channel_map["api_u"] == ["m1"]

    async def test_channels_are_independent(self, channels):
        ea = channels.submit("api_a", "m1", "task-a")
        eb = channels.submit("api_b", "m2", "task-b")
        await channels.speak("api_b", "task-b", "for b")
        assert eb.is_set() and not ea.is_set()
        # task-a speaking on channel b (no request of its own there) reaches nobody.
        channels.submit("api_b", "m3", "task-b2")
        await channels.speak("api_b", "task-a", "stray")
        assert "m3" not in agent_routes._message_responses
        await channels.speak("api_a", "task-a", "for a")
        assert ea.is_set()
        assert agent_routes._message_responses["m1"] == "for a"

    async def test_speak_outside_reasoning_scope_falls_back_to_fifo(self, channels):
        e1 = channels.submit("api_u", "m1", "task-1")
        channels.submit("api_u", "m2", "task-2")
        await channels.comm._handle_api_interaction_response("api_u", "unscoped")
        assert e1.is_set()
        assert agent_routes._message_task_ids["m1"] == "task-1"


@pytest.mark.asyncio
async def test_interact_end_to_end_late_reply_stays_out_of_the_next_response(app, auth_context_admin, monkeypatch):
    """Through the real route: interact #1 times out (outcome=timeout, task
    named), its task SPEAKs while interact #2 waits, and #2 still returns its
    own task's reply."""
    app.state.message_channel_map = {}
    app.state.message_task_map = {}
    comm = APICommunicationService()
    comm._app_state = app.state
    task_for: Dict[str, str] = {"question one": "task-1", "question two": "task-2"}
    seen: List[str] = []

    async def on_message(msg: IncomingMessage) -> None:
        app.state.message_channel_map.setdefault(msg.channel_id, []).append(msg.message_id)
        app.state.message_task_map[msg.message_id] = task_for[msg.content]
        seen.append(msg.channel_id)

    app.state.on_message = on_message
    app.dependency_overrides[require_observer] = lambda: auth_context_admin

    async def speak(task_id: str, content: str) -> None:
        with reasoning_scope(task_id=task_id, thought_id=f"th_{task_id}", phase="action_dispatch"):
            await comm._handle_api_interaction_response(seen[0], content)

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            monkeypatch.setenv("CIRIS_API_INTERACTION_TIMEOUT", "0.2")
            first = (await client.post("/agent/interact", json={"message": "question one"})).json()["data"]
            assert first["outcome"] == "timeout"
            assert first["task_id"] == "task-1"

            monkeypatch.setenv("CIRIS_API_INTERACTION_TIMEOUT", "5")
            second_call = asyncio.create_task(client.post("/agent/interact", json={"message": "question two"}))
            for _ in range(200):
                if len(seen) == 2:
                    break
                await asyncio.sleep(0.01)
            await speak("task-1", "ANSWER ONE (late)")
            await asyncio.sleep(0.05)
            assert not second_call.done(), "the late reply completed the next request"
            await speak("task-2", "ANSWER TWO")
            second = (await second_call).json()["data"]
    finally:
        app.dependency_overrides.clear()

    assert second["outcome"] == "complete"
    assert second["task_id"] == "task-2"
    assert second["response"].startswith("ANSWER TWO")
    assert "ANSWER ONE" not in second["response"]


@pytest.mark.asyncio
async def test_send_message_routes_by_the_dispatch_scope(channels, monkeypatch):
    """The public entry point the CommunicationBus calls: `send_message`
    inside the dispatcher's reasoning scope routes by that scope's task."""
    monkeypatch.setattr(channels.comm, "_create_speak_correlation", lambda channel_id, content: None)
    channels.submit("api_u", "m1", "task-1")
    channels.time_out("m1")
    e2 = channels.submit("api_u", "m2", "task-2")
    with reasoning_scope(task_id="task-1", thought_id="th_1", phase="action_dispatch"):
        assert await channels.comm.send_message("api_u", "late") is True
    assert not e2.is_set()
    with reasoning_scope(task_id="task-2", thought_id="th_2", phase="action_dispatch"):
        await channels.comm.send_message("api_u", "mine")
    assert agent_routes._message_responses["m2"] == "mine"


@pytest.mark.asyncio
async def test_adapter_handler_records_which_task_owns_each_message():
    """The adapter writes message_id -> task_id from the observer's result,
    including the task-append case where the message joins an existing task."""
    from unittest.mock import AsyncMock

    from ciris_engine.logic.adapters.api.adapter import ApiPlatform
    from ciris_engine.schemas.runtime.messages import MessageHandlingResult, MessageHandlingStatus

    state = SimpleNamespace(message_channel_map={}, message_task_map={})
    observer = SimpleNamespace(
        handle_incoming_message=AsyncMock(
            side_effect=[
                MessageHandlingResult(
                    status=MessageHandlingStatus.TASK_CREATED, task_id="task-1", message_id="m1", channel_id="api_u"
                ),
                MessageHandlingResult(
                    status=MessageHandlingStatus.UPDATED_EXISTING_TASK,
                    task_id="task-1",
                    message_id="m2",
                    channel_id="api_u",
                    existing_task_updated=True,
                ),
            ]
        )
    )
    fake_adapter = SimpleNamespace(
        app=SimpleNamespace(state=state), message_observer=observer, _create_message_correlation=AsyncMock()
    )
    handler = ApiPlatform._create_message_handler(fake_adapter)  # type: ignore[arg-type]
    for mid in ("m1", "m2"):
        await handler(
            IncomingMessage(message_id=mid, author_id="u", author_name="U", content="hi", channel_id="api_u")
        )
    assert state.message_channel_map["api_u"] == ["m1", "m2"]
    assert state.message_task_map == {"m1": "task-1", "m2": "task-1"}
