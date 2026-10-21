"""A REJECTED wakeup step must be visible, and must not read as a healthy boot.

Production, 22 hours (#1069 / #1077): all three wakeup step tasks were REJECTED,
`ciris_persist` refused to record `rejected` as a task status though
`TaskStatus.REJECTED` is valid in the Python enum, and the agent span one empty
WAKEUP round every ~5 seconds for its entire uptime.

Throughout that, `/v1/system/health` reported `cognitive_state: WAKEUP` and
`status: healthy`. Both were true statements and together they were a lie: the
agent had finished deciding, and the answer was no.

The processor's refusal to enter WORK is correct and already worked — but it
refused by ACCIDENT. `_check_all_steps_complete` demands COMPLETED, and a
rejected step never becomes COMPLETED, so it reads as "not yet", which is
exactly what a boot in progress looks like. The two need opposite responses: a
boot resolves by waiting, a rejection never does.
"""

from types import SimpleNamespace
from unittest.mock import patch

from ciris_engine.logic.adapters.api.routes.system.health import _rejected_wakeup_warnings


def _task(task_id: str, status: str):
    return SimpleNamespace(task_id=task_id, status=SimpleNamespace(value=status))


def _run(tasks):
    with patch(
        "ciris_engine.logic.persistence.models.tasks.get_all_tasks", return_value=tasks
    ), patch(
        "ciris_engine.logic.utils.occurrence_utils.get_current_occurrence_id", return_value="default"
    ):
        return _rejected_wakeup_warnings(SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace())))


class TestRejectedWakeupIsVisible:
    def test_a_rejected_step_produces_an_error_warning(self):
        warnings = _run([_task("VERIFY_IDENTITY_abc123", "rejected")])
        assert len(warnings) == 1, "a rejected wakeup step must surface on the health endpoint"
        w = warnings[0]
        assert w.code == "wakeup_step_rejected"
        assert w.severity == "error"
        assert "VERIFY" in w.message

    def test_the_message_names_which_step(self):
        # "a wakeup step failed" sends an operator to read 22 hours of logs.
        warnings = _run(
            [
                _task("VERIFY_IDENTITY_a", "rejected"),
                _task("EXPRESS_GRATITUDE_b", "rejected"),
            ]
        )
        assert len(warnings) == 1
        assert "VERIFY" in warnings[0].message and "EXPRESS" in warnings[0].message

    def test_it_does_not_resolve_by_waiting(self):
        # The wording is load-bearing: the operator's instinct on a WAKEUP state
        # is to wait for boot to finish, and here that instinct is wrong.
        warnings = _run([_task("VALIDATE_INTEGRITY_x", "rejected")])
        assert "not resolve by waiting" in warnings[0].message.lower()


class TestItDoesNotFireOnHealthyBoots:
    def test_a_wakeup_in_progress_is_not_an_error(self):
        # PENDING/ACTIVE steps are a boot doing exactly what it should. Reporting
        # those would train everyone to ignore this warning.
        warnings = _run(
            [
                _task("VERIFY_IDENTITY_a", "completed"),
                _task("VALIDATE_INTEGRITY_b", "active"),
                _task("EVALUATE_RESILIENCE_c", "pending"),
            ]
        )
        assert warnings == []

    def test_a_completed_wakeup_is_not_an_error(self):
        warnings = _run([_task(f"{p}x", "completed") for p in
                         ("VERIFY_IDENTITY_", "VALIDATE_INTEGRITY_", "EXPRESS_GRATITUDE_")])
        assert warnings == []

    def test_a_rejected_NON_wakeup_task_is_not_a_wakeup_failure(self):
        # Ordinary work gets rejected all the time; that is not this condition.
        warnings = _run([_task("some_ordinary_task_id", "rejected")])
        assert warnings == []

    def test_a_health_probe_never_raises(self):
        # This runs inside /v1/system/health. A diagnostic that can take the
        # health endpoint down is worse than the condition it reports.
        with patch(
            "ciris_engine.logic.persistence.models.tasks.get_all_tasks",
            side_effect=RuntimeError("db gone"),
        ):
            assert _rejected_wakeup_warnings(SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace()))) == []
