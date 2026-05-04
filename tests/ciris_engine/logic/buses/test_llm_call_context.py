"""Unit tests for the parent-event ContextVar that drives LLM_CALL parent linkage.

The contract this module locks in (TRACE_WIRE_FORMAT.md §5.10, item #5 of
#712, required as of 2.7.9):

  - get_parent_event_context() returns ("UNKNOWN_PARENT", 0) when no
    set_parent_event_context block is on the call stack
  - set_parent_event_context(event_type, attempt_index) binds the value
    for the duration of the with-block and restores the prior value on
    exit (including across exceptions)
  - Negative parent_attempt_index is clamped to 0 with a logged warning
  - The ContextVar inherits across async boundaries (asyncio default
    behavior — pinned here so a future ContextVar→threadlocal regression
    fails loudly at test time)
"""

import asyncio
import logging

import pytest

from ciris_engine.logic.buses.llm_call_context import (
    UNKNOWN_PARENT_ATTEMPT_INDEX,
    UNKNOWN_PARENT_EVENT_TYPE,
    get_parent_event_context,
    set_parent_event_context,
)


class TestParentContextDefault:
    """When no streaming_step has set the context, callers see the sentinel."""

    def test_default_is_unknown_parent_sentinel(self):
        # Outside any set_parent_event_context block
        event_type, attempt_index = get_parent_event_context()
        assert event_type == UNKNOWN_PARENT_EVENT_TYPE
        assert attempt_index == UNKNOWN_PARENT_ATTEMPT_INDEX

    def test_sentinel_is_distinguishable_string(self):
        """The sentinel must NOT collide with any real ReasoningEvent
        value — lens dashboards filter on it to surface unwired call
        sites. 'UNKNOWN_PARENT' is intentionally upper-case + underscore
        to never alias DMA_RESULTS / ASPDMA_RESULT / etc."""
        from ciris_engine.schemas.services.runtime_control import ReasoningEvent

        real_values = {ev.value for ev in ReasoningEvent}
        # Real values are lower-snake (llm_call, action_result, etc.).
        # The sentinel uses uppercase to avoid any string-equality
        # collision under lens-side discriminator dispatch.
        assert UNKNOWN_PARENT_EVENT_TYPE not in real_values
        assert UNKNOWN_PARENT_EVENT_TYPE.isupper()


class TestSetParentEventContext:
    """The with-block contract for binding a parent event."""

    def test_set_binds_for_block_duration(self):
        with set_parent_event_context("DMA_RESULTS", 3):
            event_type, attempt_index = get_parent_event_context()
            assert event_type == "DMA_RESULTS"
            assert attempt_index == 3

        # Reset on exit
        event_type, attempt_index = get_parent_event_context()
        assert event_type == UNKNOWN_PARENT_EVENT_TYPE
        assert attempt_index == 0

    def test_nested_set_restores_outer_on_exit(self):
        """Nested with-blocks must restore the outer binding, not the
        sentinel — so a recursive step inside another step sees the
        recursive parent during its inner block, then the outer parent
        when the inner exits."""
        with set_parent_event_context("ASPDMA_RESULT", 0):
            assert get_parent_event_context() == ("ASPDMA_RESULT", 0)
            with set_parent_event_context("CONSCIENCE_RESULT", 1):
                assert get_parent_event_context() == ("CONSCIENCE_RESULT", 1)
            # Inner exited — outer restored
            assert get_parent_event_context() == ("ASPDMA_RESULT", 0)
        # Both exited
        assert get_parent_event_context() == (UNKNOWN_PARENT_EVENT_TYPE, 0)

    def test_exception_inside_block_still_restores_context(self):
        """If the wrapped handler raises, the ContextVar still resets —
        otherwise a failing thought would leak its parent context onto
        the next thought processed by the same task."""
        with pytest.raises(ValueError):
            with set_parent_event_context("ASPDMA_RESULT", 0):
                assert get_parent_event_context() == ("ASPDMA_RESULT", 0)
                raise ValueError("simulated handler failure")

        # Despite the exception, context reset
        assert get_parent_event_context() == (UNKNOWN_PARENT_EVENT_TYPE, 0)

    def test_negative_attempt_index_clamped_to_zero(self, caplog):
        """Defensive clamp + warn — persistence rejects negative indices
        so we never let one through to the wire."""
        with caplog.at_level(logging.WARNING, logger="ciris_engine.logic.buses.llm_call_context"):
            with set_parent_event_context("ASPDMA_RESULT", -5):
                event_type, attempt_index = get_parent_event_context()
                assert attempt_index == 0
                assert event_type == "ASPDMA_RESULT"

        # Warning surfaced for the operator
        warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert any("negative parent_attempt_index" in r.message for r in warnings)


class TestAsyncBoundaries:
    """ContextVar inherits across asyncio.create_task and await boundaries.
    The streaming_step decorator depends on this — LLM calls happen many
    awaits deep inside the handler."""

    @pytest.mark.asyncio
    async def test_context_inherits_through_await(self):
        """A coroutine awaited inside the with-block sees the same context."""
        async def inner_observer():
            return get_parent_event_context()

        with set_parent_event_context("DMA_RESULTS", 7):
            observed = await inner_observer()
            assert observed == ("DMA_RESULTS", 7)

    @pytest.mark.asyncio
    async def test_concurrent_tasks_have_isolated_contexts(self):
        """Concurrent thoughts on the same event loop must NOT see each
        other's parent context. ContextVar's per-task copy semantics
        guarantee this — pinned here so a future move to threadlocal
        breaks at test time."""
        observed_a: list = []
        observed_b: list = []

        async def task_a():
            with set_parent_event_context("ASPDMA_RESULT", 0):
                # Yield to let task_b run with its own context
                await asyncio.sleep(0.001)
                observed_a.append(get_parent_event_context())

        async def task_b():
            with set_parent_event_context("CONSCIENCE_RESULT", 2):
                await asyncio.sleep(0.001)
                observed_b.append(get_parent_event_context())

        await asyncio.gather(task_a(), task_b())

        # Each task saw ITS OWN context, not a leaked one
        assert observed_a == [("ASPDMA_RESULT", 0)]
        assert observed_b == [("CONSCIENCE_RESULT", 2)]

    @pytest.mark.asyncio
    async def test_context_set_in_outer_task_does_not_leak_to_sibling(self):
        """If task A sets the context and task B starts WITHOUT a
        set_parent_event_context, B sees the default sentinel — not A's
        binding. This is the load-bearing async isolation property."""
        observed_b: list = []

        async def sibling_task_with_no_context():
            await asyncio.sleep(0.001)
            observed_b.append(get_parent_event_context())

        async def parent_task():
            with set_parent_event_context("ASPDMA_RESULT", 0):
                # Spawn sibling — it should NOT inherit ASPDMA_RESULT,
                # because asyncio.create_task copies context AT TASK CREATION,
                # so we set the context BEFORE spawning. Wait — actually
                # asyncio.create_task DOES copy the parent's context. To
                # observe isolation we'd need to run the sibling in
                # another task that started outside the with-block. Let's
                # do that via gather of two top-level coroutines with
                # only one of them in the with-block.
                pass

        async def task_with_context():
            with set_parent_event_context("ASPDMA_RESULT", 0):
                await asyncio.sleep(0.001)

        await asyncio.gather(task_with_context(), sibling_task_with_no_context())

        # Sibling task that did NOT enter the with-block sees the sentinel
        assert observed_b == [(UNKNOWN_PARENT_EVENT_TYPE, 0)]
