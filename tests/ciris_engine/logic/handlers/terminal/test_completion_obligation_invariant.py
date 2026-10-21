"""A task is not complete while an obligation is outstanding (NULLWORKS RC3 / F4).

The independent RC3 retest reproduced this with COMPLETE-01: PENDING and
PROCESSING siblings blocked completion, but DEFERRED and FAILED siblings could
coexist with a COMPLETED write.

DEFERRED is the one that makes the record untrue. `defer_handler` sets it when a
decision is escalated to a Wise Authority — it means a HUMAN OWES AN ANSWER. A
task reporting COMPLETED while a person is still holding one of its questions is
making a false statement about itself, and audit, telemetry and every dashboard
downstream inherit it.

The underlying defect is the same one that made a REJECTED wakeup step read as a
healthy boot in 2.9.28: the predicate keyed on which status NAMES it happened to
list, rather than on whether an obligation was resolved. Same error, one level up.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from ciris_engine.logic.handlers.terminal.task_complete_handler import TaskCompleteHandler
from ciris_engine.schemas.runtime.enums import ThoughtStatus


def _thought(tid, status):
    return SimpleNamespace(thought_id=tid, status=status)


def _handler():
    h = TaskCompleteHandler.__new__(TaskCompleteHandler)
    h.logger = MagicMock()
    return h


def _verify(siblings, current="cur"):
    h = _handler()
    with patch(
        "ciris_engine.logic.handlers.terminal.task_complete_handler.persistence.get_thoughts_by_task_id",
        return_value=siblings + [_thought(current, ThoughtStatus.PROCESSING)],
    ):
        h._verify_no_pending_thoughts("task-1", current)
    return h


class TestOutstandingObligationsBlock:
    def test_a_deferred_sibling_blocks_completion(self):
        # The finding. A human was asked and has not answered.
        with pytest.raises(RuntimeError) as e:
            _verify([_thought("t-deferred", ThoughtStatus.DEFERRED)])
        assert "t-deferred" in str(e.value)

    def test_the_error_says_a_human_is_owed_not_that_a_handler_broke(self):
        # An operator told "a handler failed to complete processing" goes looking
        # for a bug. The truth is that a person has not replied — different fix,
        # different place to look.
        with pytest.raises(RuntimeError) as e:
            _verify([_thought("t-deferred", ThoughtStatus.DEFERRED)])
        msg = str(e.value)
        assert "DEFERRED" in msg and "Wise Authority" in msg

    @pytest.mark.parametrize("status", [ThoughtStatus.PENDING, ThoughtStatus.PROCESSING])
    def test_in_flight_siblings_still_block(self, status):
        # Pre-existing behaviour must not regress.
        with pytest.raises(RuntimeError):
            _verify([_thought("t-busy", status)])


class TestSettledSiblingsDoNotBlock:
    def test_a_completed_sibling_does_not_block(self):
        _verify([_thought("t-done", ThoughtStatus.COMPLETED)])  # no raise

    def test_a_failed_sibling_does_not_block_but_is_recorded(self):
        # Deliberate: nothing re-opens a FAILED thought, so blocking would strand
        # the task forever with no resolution path. The completion is allowed and
        # marked as qualified rather than passed off as clean.
        h = _verify([_thought("t-failed", ThoughtStatus.FAILED)])
        warned = " ".join(str(c) for c in h.logger.warning.call_args_list)
        assert "t-failed" in warned or "FAILED" in warned, (
            "a completion over a failed sibling must not be silent — that is the "
            "difference between a record that is true and one that is merely not false"
        )

    def test_a_clean_completion_warns_about_nothing(self):
        h = _verify([_thought("t-done", ThoughtStatus.COMPLETED)])
        assert not h.logger.warning.called


class TestTheCurrentThoughtIsExempt:
    def test_the_completing_thought_does_not_block_itself(self):
        # The thought issuing TASK_COMPLETE is PROCESSING by definition.
        _verify([], current="cur")  # no raise
