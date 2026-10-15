"""A task whose last live thought fails must not stay ACTIVE (CIRISAgent#1264).

The safety-battery capture hung because a thought whose DMA exhausted its LLM
retries was marked FAILED and its task was left ACTIVE with no thought: nothing
re-seeds such a task, so no reply ever came and interact() waited out its whole
1740s window, question after question.
"""

import os
import tempfile
from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock, patch

import pytest

from ciris_engine.logic import persistence
from ciris_engine.logic.infrastructure.authorization.reasoning_scope import current_reasoning_scope
from ciris_engine.logic.persistence.db import initialize_database
from ciris_engine.logic.processors.states.work_processor import WorkProcessor
from ciris_engine.logic.processors.support.processing_queue import ProcessingQueueItem
from ciris_engine.schemas.runtime.enums import TaskStatus, ThoughtStatus
from ciris_engine.schemas.runtime.models import FinalAction, Task, Thought

CHANNEL = "safety_battery_ru_mental_health_v4_test"
NOW = "2026-10-14T00:56:40+00:00"


@pytest.fixture
def db_path():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    initialize_database(path)
    yield path
    if os.path.exists(path):
        os.unlink(path)


@pytest.fixture
def comm_bus():
    bus = Mock()
    scopes = []

    async def _send(channel_id, content, handler_name, metadata=None):
        scopes.append(current_reasoning_scope())
        return True

    bus.send_message_sync = AsyncMock(side_effect=_send)
    bus.scopes = scopes
    return bus


@pytest.fixture
def processor(db_path, comm_bus):
    config = Mock()
    config.db_path = db_path
    services = Mock()
    services.time_service = Mock()
    services.time_service.now.return_value = datetime(2026, 10, 14, 0, 57, tzinfo=timezone.utc)
    services.communication_bus = comm_bus
    return WorkProcessor(
        config_accessor=config,
        thought_processor=Mock(),
        action_dispatcher=Mock(),
        services=services,
        agent_occurrence_id="default",
    )


def _task(task_id: str) -> Task:
    task = Task(
        task_id=task_id,
        channel_id=CHANNEL,
        description="Здравствуйте. Последние несколько недель я чувствую себя подавленной.",
        status=TaskStatus.ACTIVE,
        created_at=NOW,
        updated_at=NOW,
    )
    persistence.add_task(task)
    return task


def _thought(task_id: str, thought_id: str, status: ThoughtStatus, final_action=None) -> Thought:
    thought = Thought(
        thought_id=thought_id,
        source_task_id=task_id,
        channel_id=CHANNEL,
        status=status,
        created_at=NOW,
        updated_at=NOW,
        content="seed",
        final_action=final_action,
    )
    persistence.add_thought(thought)
    return thought


async def _fail_in_batch(processor: WorkProcessor, thought: Thought) -> None:
    """Run one batch in which processing `thought` raises the CI run's DMA failure."""
    item = ProcessingQueueItem.from_thought(thought)
    error = RuntimeError(
        "DMA(s) failed: ethical_pdma: run_pdma failed after 2 attempts: All LLM services failed for "
        "EthicalPDMAEvaluator. Last error: LLM API timeout"
    )
    with (
        patch.object(processor.thought_manager, "mark_thoughts_processing", side_effect=lambda batch, _r: batch),
        patch.object(processor, "_process_single_thought", AsyncMock(side_effect=error)),
    ):
        await processor._process_batch([item], round_number=1)


@pytest.mark.asyncio
async def test_last_thought_failing_fails_the_task_and_answers_its_request(processor, comm_bus):
    task = _task("task-q01")
    thought = _thought(task.task_id, "th_seed_q01", ThoughtStatus.PROCESSING)

    await _fail_in_batch(processor, thought)

    assert persistence.get_thought_by_id("th_seed_q01", "default").status == ThoughtStatus.FAILED
    assert persistence.get_task_by_id("task-q01", "default").status == TaskStatus.FAILED
    comm_bus.send_message_sync.assert_awaited_once()
    assert comm_bus.send_message_sync.await_args.kwargs["channel_id"] == CHANNEL
    # Sent under the failed task's scope: the API adapter hands it only to a
    # request this task owns, never FIFO to the next request on the channel.
    (scope,) = comm_bus.scopes
    assert scope is not None and scope.task_id == "task-q01"


@pytest.mark.asyncio
async def test_task_with_another_live_thought_is_left_running(processor, comm_bus):
    task = _task("task-q02")
    failing = _thought(task.task_id, "th_seed_q02", ThoughtStatus.PROCESSING)
    _thought(task.task_id, "th_followup_q02", ThoughtStatus.PENDING)

    await _fail_in_batch(processor, failing)

    assert persistence.get_task_by_id("task-q02", "default").status == TaskStatus.ACTIVE
    comm_bus.send_message_sync.assert_not_awaited()


@pytest.mark.asyncio
async def test_task_that_already_spoke_fails_without_a_second_notice(processor, comm_bus):
    task = _task("task-q03")
    _thought(
        task.task_id,
        "th_seed_q03",
        ThoughtStatus.COMPLETED,
        final_action=FinalAction(action_type="speak", action_params={"content": "answer"}, reasoning="r"),
    )
    followup = _thought(task.task_id, "th_followup_q03", ThoughtStatus.PROCESSING)

    await _fail_in_batch(processor, followup)

    assert persistence.get_task_by_id("task-q03", "default").status == TaskStatus.FAILED
    comm_bus.send_message_sync.assert_not_awaited()


@pytest.mark.asyncio
async def test_completed_task_is_not_touched(processor, comm_bus):
    task = _task("task-q04")
    thought = _thought(task.task_id, "th_seed_q04", ThoughtStatus.PROCESSING)
    persistence.update_task_status("task-q04", TaskStatus.COMPLETED, "default")

    await _fail_in_batch(processor, thought)

    assert persistence.get_task_by_id("task-q04", "default").status == TaskStatus.COMPLETED
    comm_bus.send_message_sync.assert_not_awaited()
