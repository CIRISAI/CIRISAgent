"""The dream processor's two callers must not race (Staged QA all_2 on #1262).

`process()` is driven by the dream loop's own task AND by the main round
(state_processors maps DREAM to the dream processor). Unserialized, both picked
up the same seed thought and dispatched it twice; one ended the session and the
other raised "'NoneType' object has no attribute 'thoughts_processed'", which
the QA incidents gate counts as a failure.
"""

import asyncio
from datetime import datetime, timezone
from typing import Any, List
from unittest.mock import AsyncMock, Mock

import pytest

from ciris_engine.logic.processors.states import minimal_dream_processor as dream_module
from ciris_engine.logic.processors.states.minimal_dream_processor import DreamSession, MinimalDreamProcessor
from ciris_engine.schemas.runtime.enums import ThoughtStatus


def _dream(monkeypatch, thought_status: List[Any]):
    dream = MinimalDreamProcessor.__new__(MinimalDreamProcessor)
    dream.time_service = Mock(now=Mock(return_value=datetime.now(timezone.utc)))
    dream.agent_occurrence_id = "default"
    dream._process_lock = asyncio.Lock()
    dream.current_session = DreamSession(session_id="s", start_time=datetime.now(timezone.utc), task_id="task_s")
    dream._is_dream_complete = Mock(return_value=False)  # type: ignore[method-assign]
    seed = Mock(thought_id="seed", status=ThoughtStatus.PENDING)
    monkeypatch.setattr(
        dream_module.persistence,
        "get_thoughts_by_task_id",
        lambda task_id, occurrence_id: [seed] if thought_status[0] == ThoughtStatus.PENDING else [],
    )
    return dream


@pytest.mark.asyncio
async def test_concurrent_rounds_process_a_thought_once(monkeypatch):
    status = [ThoughtStatus.PENDING]
    dream = _dream(monkeypatch, status)
    dispatched: List[str] = []

    async def process_thought(thought):
        await asyncio.sleep(0.01)  # an await point, like the dispatch's latch read
        dispatched.append(thought.thought_id)
        status[0] = ThoughtStatus.COMPLETED

    dream._process_dream_thought = process_thought  # type: ignore[method-assign]
    results = await asyncio.gather(dream.process(1), dream.process(2))

    assert dispatched == ["seed"]
    assert sum(r.errors for r in results) == 0


@pytest.mark.asyncio
async def test_a_session_ended_mid_thought_is_not_an_error(monkeypatch):
    status = [ThoughtStatus.PENDING]
    dream = _dream(monkeypatch, status)

    async def process_thought(thought):
        dream.current_session = None  # stop_dreaming() ended the session meanwhile
        status[0] = ThoughtStatus.COMPLETED

    dream._process_dream_thought = process_thought  # type: ignore[method-assign]
    result = await dream.process(1)
    assert result.errors == 0 and result.thoughts_processed == 1
