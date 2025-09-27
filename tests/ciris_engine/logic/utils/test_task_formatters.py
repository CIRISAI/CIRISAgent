import pytest

from ciris_engine.logic.utils.task_formatters import format_task_context


@pytest.fixture
def current_task_data():
    return {
        "description": "Analyze the system's performance.",
        "task_id": "task-123",
        "status": "In Progress",
        "priority": "High",
    }


@pytest.fixture
def recent_actions_data():
    return [
        {"description": "Ran diagnostics", "outcome": "Success", "updated_at": "2025-09-07T18:00:00Z"},
        {"description": "Checked logs", "outcome": "Found errors", "updated_at": "2025-09-07T18:05:00Z"},
    ]


@pytest.fixture
def completed_tasks_data():
    return [{"description": "Rebooted the server", "outcome": "Completed", "updated_at": "2025-09-07T17:55:00Z"}]


class TestFormatTaskContext:
    def test_full_context_format(self, current_task_data, recent_actions_data, completed_tasks_data):
        output = format_task_context(current_task_data, recent_actions_data, completed_tasks_data)

        assert "=== Current Task ===" in output
        assert "Analyze the system's performance." in output
        assert "Task ID: task-123" in output

        assert "=== Recent Actions ===" in output
        assert "1. Ran diagnostics | Outcome: Success" in output
        assert "2. Checked logs | Outcome: Found errors" in output

        assert "=== Last Completed Task ===" in output
        assert "Rebooted the server | Outcome: Completed" in output

    def test_minimal_context(self, current_task_data):
        output = format_task_context(current_task_data, [])
        assert "=== Current Task ===" in output
        assert "=== Recent Actions ===" not in output
        assert "=== Last Completed Task ===" not in output

    def test_handles_missing_keys_gracefully(self):
        task = {"description": "A task with no other info"}
        output = format_task_context(task, [])
        assert "Status: N/A" in output
        assert "Priority: N/A" in output

    def test_max_actions_limit(self, current_task_data, recent_actions_data):
        actions = recent_actions_data * 4  # 8 actions
        output = format_task_context(current_task_data, actions, max_actions=3)

        assert "1. Ran diagnostics" in output
        assert "2. Checked logs" in output
        assert "3. Ran diagnostics" in output
        assert "4. Checked logs" not in output

    def test_raises_type_error_for_invalid_task(self):
        with pytest.raises(TypeError, match="current_task must be a dict"):
            format_task_context("not a dict", [])

    def test_handles_empty_completed_tasks(self, current_task_data, recent_actions_data):
        output = format_task_context(current_task_data, recent_actions_data, completed_tasks=[])
        assert "=== Last Completed Task ===" not in output

    def test_handles_invalid_item_in_completed_tasks(self, current_task_data):
        # The function should not crash and just skip the section
        output = format_task_context(current_task_data, [], completed_tasks=["not_a_dict"])
        assert "=== Last Completed Task ===" not in output
