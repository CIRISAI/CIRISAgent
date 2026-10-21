"""Channel history: the bus must be found, and the window is asymmetric.

TWO THINGS, ONE FILE, because the second is unmeasurable without the first.

1. THE BUS WAS NEVER FOUND (silent single-turn conversations)

   Adapters built their observer inside `start()` with
   `bus_manager=getattr(self.runtime, "bus_manager", None)`. That reads a LIVE
   property — CIRISRuntime.bus_manager delegates to
   `service_initializer.bus_manager` — but reads it ONCE and stores the result.
   At observer-construction time the ServiceInitializer has not built the
   BusManager yet (service_initializer.py:750), so the observer captured None
   and kept it forever, while the same property began returning a live
   BusManager moments later.

   `_get_channel_history` therefore returned [] on EVERY call: every
   conversation was single-turn, the agent never saw what came before, and the
   only symptom was a warning nobody read. Nothing else broke, because SPEAK
   reaches the bus by a different route — which is what made it invisible. On a
   real Android run the observer reported the bus absent at 19:06:31 while the
   SPEAK handler sent through it at 19:06:51, in the same process.

2. THE WINDOW IS ASYMMETRIC (RATCHET#20)

   A flat "last 20" spends about half the window on the agent's own output, so
   most of what it reads before answering is text it wrote itself. Keep the last
   10 non-agent messages and only the last 3 agent messages.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, List, Optional

import pytest

from ciris_engine.logic.adapters.base_observer import (
    HISTORY_AGENT_MESSAGE_LIMIT,
    HISTORY_USER_MESSAGE_LIMIT,
    BaseObserver,
)


class _Observer(BaseObserver[Any]):
    """Minimal concrete observer — BaseObserver is ABC."""

    async def start(self) -> None:  # pragma: no cover - not exercised
        pass

    async def stop(self) -> None:  # pragma: no cover - not exercised
        pass

    async def handle_incoming_message(self, msg: Any) -> None:  # pragma: no cover
        pass


def _msg(content: str, is_bot: bool) -> SimpleNamespace:
    return SimpleNamespace(
        content=content,
        is_bot=is_bot,
        author_id="ciris" if is_bot else "user-1",
        author_name="CIRIS" if is_bot else "User",
        message_id=content,
    )


def _make(bus: Optional[Any] = None, provider: Any = None) -> _Observer:
    return _Observer(
        on_observe=lambda _: None,  # type: ignore[arg-type,return-value]
        bus_manager=bus,
        bus_manager_provider=provider,
    )


# ---------------------------------------------------------------- late binding


def test_bus_manager_is_resolved_after_construction_not_at_it() -> None:
    """The exact defect: absent when the observer is built, present later."""
    runtime = SimpleNamespace(bus_manager=None)  # ServiceInitializer hasn't run
    obs = _make(provider=lambda: runtime.bus_manager)

    assert obs.bus_manager is None, "precondition: nothing to find yet"

    runtime.bus_manager = SimpleNamespace(communication=object())  # boot completes

    assert obs.bus_manager is runtime.bus_manager, (
        "the observer captured None at construction and never looked again — this is "
        "what made every conversation single-turn while SPEAK kept working"
    )


def test_snapshot_style_construction_still_supported() -> None:
    """Passing a live bus directly (tests, embedders) must keep working."""
    bus = SimpleNamespace(communication=object())
    assert _make(bus=bus).bus_manager is bus


def test_provider_is_not_consulted_once_resolved() -> None:
    """Steady state is one attribute read, not a call per access."""
    bus = SimpleNamespace(communication=object())
    calls = {"n": 0}

    def provider() -> Any:
        calls["n"] += 1
        return bus

    obs = _make(provider=provider)
    for _ in range(5):
        assert obs.bus_manager is bus
    assert calls["n"] == 1


def test_bus_manager_remains_assignable() -> None:
    """Existing code and tests assign this attribute directly."""
    obs = _make()
    bus = SimpleNamespace(communication=object())
    obs.bus_manager = bus
    assert obs.bus_manager is bus


# ------------------------------------------------------------ asymmetric window


def _kinds(selected: List[Any]) -> tuple[int, int]:
    agents = sum(1 for m in selected if m.is_bot)
    return len(selected) - agents, agents


def test_keeps_ten_user_and_three_agent_messages() -> None:
    convo: List[Any] = []
    for i in range(20):
        convo.append(_msg(f"u{i}", is_bot=False))
        convo.append(_msg(f"a{i}", is_bot=True))

    selected = BaseObserver._select_history_window(convo)
    users, agents = _kinds(selected)
    assert users == HISTORY_USER_MESSAGE_LIMIT == 10
    assert agents == HISTORY_AGENT_MESSAGE_LIMIT == 3


def test_keeps_the_MOST_RECENT_of_each_kind() -> None:
    convo = [_msg(f"u{i}", False) for i in range(20)] + [_msg(f"a{i}", True) for i in range(20)]
    selected = BaseObserver._select_history_window(convo)
    contents = [m.content for m in selected]

    assert "u19" in contents and "u10" in contents, "newest user messages must survive"
    assert "u9" not in contents, "older user messages must be dropped"
    assert contents[-3:] == ["a17", "a18", "a19"], f"newest agent messages only: {contents[-3:]}"


def test_chronological_order_is_preserved() -> None:
    """The agent must read a conversation, not two concatenated blocks."""
    convo: List[Any] = []
    for i in range(6):
        convo.append(_msg(f"u{i}", is_bot=False))
        convo.append(_msg(f"a{i}", is_bot=True))

    selected = BaseObserver._select_history_window(convo)
    order = [convo.index(m) for m in selected]
    assert order == sorted(order), f"interleaving lost: {[m.content for m in selected]}"


def test_agent_heavy_channel_still_yields_ten_user_messages() -> None:
    """Why the scan window is wider than the slice.

    With five agent messages per user turn, the 10th-most-recent user message is
    ~60 messages back; a flat 20-message window would surface two of them.
    """
    convo: List[Any] = []
    for i in range(12):
        convo.append(_msg(f"u{i}", is_bot=False))
        convo.extend(_msg(f"a{i}-{j}", is_bot=True) for j in range(5))

    users, agents = _kinds(BaseObserver._select_history_window(convo))
    assert users == 10
    assert agents == 3


def test_short_conversations_are_returned_whole() -> None:
    convo = [_msg("u0", False), _msg("a0", True), _msg("u1", False)]
    selected = BaseObserver._select_history_window(convo)
    assert [m.content for m in selected] == ["u0", "a0", "u1"]


def test_empty_history_is_empty() -> None:
    assert BaseObserver._select_history_window([]) == []


def test_all_agent_channel_keeps_only_three() -> None:
    convo = [_msg(f"a{i}", True) for i in range(10)]
    selected = BaseObserver._select_history_window(convo)
    assert [m.content for m in selected] == ["a7", "a8", "a9"]


@pytest.mark.asyncio
async def test_numbering_matches_the_returned_window_not_the_scan() -> None:
    """MESSAGE_n_OF_total is anti-spoofing: gaps read as tampering.

    Numbering the scan window and then dropping messages would emit e.g.
    "MESSAGE_37_OF_60" inside a 13-message history — indistinguishable from
    content an attacker removed.
    """
    convo: List[Any] = []
    for i in range(20):
        convo.append(_msg(f"u{i}", is_bot=False))
        convo.append(_msg(f"a{i}", is_bot=True))

    class _Bus:
        def __init__(self) -> None:
            self.communication = self

        async def fetch_messages(self, channel_id: str, limit: int, _who: str) -> List[Any]:
            return list(reversed(convo))[:limit]  # bus returns newest-first

    obs = _make(bus=_Bus())
    history = await obs._get_channel_history("chan")

    total = len(history)
    assert total == HISTORY_USER_MESSAGE_LIMIT + HISTORY_AGENT_MESSAGE_LIMIT
    for i, entry in enumerate(history):
        assert f"MESSAGE_{i + 1}_OF_{total}_START" in str(entry["content"])


@pytest.mark.asyncio
async def test_history_is_empty_without_a_bus_and_does_not_raise() -> None:
    """Degrade quietly, as before — but now it should not be the normal case."""
    assert await _make()._get_channel_history("chan") == []


@pytest.mark.asyncio
async def test_prior_turn_content_reaches_the_task_description() -> None:
    """End-to-end for the data half: what was said earlier must be READABLE.

    Retrieval returning rows is not the same as the agent being able to read
    them. This asserts the actual text of a previous turn survives into the
    description the seed thought carries — the string the DMAs are prompted
    with — because that is the thing the user experiences as "it remembered".
    """
    convo = [
        _msg("Remember this: my favorite color is chartreuse.", is_bot=False),
        _msg("Noted: your favorite color is chartreuse.", is_bot=True),
    ]

    class _Bus:
        def __init__(self) -> None:
            self.communication = self

        async def fetch_messages(self, channel_id: str, limit: int, _who: str) -> List[Any]:
            return list(reversed(convo))[:limit]

    obs = _make(bus=_Bus())
    history = await obs._get_channel_history("chan")

    joined = " ".join(str(h["content"]) for h in history)
    assert "chartreuse" in joined, (
        "the fact from a previous turn did not survive into the history the agent "
        "reads; retrieval counts were non-zero but the content was not there"
    )
    # And both sides of the exchange are present, not just the user's half.
    assert sum(1 for h in history if h["is_agent"]) == 1
    assert sum(1 for h in history if not h["is_agent"]) == 1
