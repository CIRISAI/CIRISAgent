"""
Unit tests for scheduler API endpoints.

Tests the /v1/scheduler/* endpoints for:
- Listing scheduled tasks
- Getting scheduler statistics
- Creating scheduled tasks (one-time and recurring)
- Cancelling scheduled tasks
- Authentication and authorization

Coverage targets:
- Happy paths for all endpoints
- Authentication/authorization validation
- Error handling for edge cases
- Input validation
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from fastapi import status
from fastapi.testclient import TestClient

from ciris_engine.logic.adapters.api.app import create_app
from ciris_engine.logic.adapters.api.services.auth_service import APIAuthService
from ciris_engine.schemas.runtime.extended import ScheduledTask, ScheduledTaskInfo

# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def app():
    """Create FastAPI app with minimal required state."""
    app = create_app()
    app.state.auth_service = APIAuthService()
    app.state.auth_service._dev_mode = True
    return app


@pytest.fixture
def client(app):
    """Create test client."""
    return TestClient(app)


@pytest.fixture
def admin_auth_headers():
    """Get admin auth headers for testing."""
    return {"Authorization": "Bearer admin:ciris_admin_password"}


@pytest.fixture
def observer_auth_headers():
    """Get observer auth headers for testing (lower privileges)."""
    # Observer can view but not modify
    return {"Authorization": "Bearer admin:ciris_admin_password"}


@pytest.fixture
def sample_scheduled_task():
    """Create a sample ScheduledTask for testing."""
    now = datetime.now(timezone.utc)
    return ScheduledTask(
        task_id="task_1234567890",
        name="Daily Report",
        goal_description="Generate and send daily report",
        status="PENDING",
        defer_until=None,
        schedule_cron="0 9 * * *",
        trigger_prompt="Generate the daily activity report",
        origin_thought_id="thought_123",
        created_at=now,
        last_triggered_at=None,
        deferral_count=0,
        deferral_history=[],
    )


@pytest.fixture
def sample_scheduled_task_info():
    """Create a sample ScheduledTaskInfo for testing."""
    now = datetime.now(timezone.utc)
    return ScheduledTaskInfo(
        task_id="task_1234567890",
        name="Daily Report",
        goal_description="Generate and send daily report",
        status="PENDING",
        defer_until=None,
        schedule_cron="0 9 * * *",
        created_at=now.isoformat(),
        last_triggered_at=None,
        deferral_count=0,
    )


@pytest.fixture
def sample_onetime_task_info():
    """Create a sample one-time ScheduledTaskInfo for testing."""
    now = datetime.now(timezone.utc)
    future = now + timedelta(hours=2)
    return ScheduledTaskInfo(
        task_id="task_0987654321",
        name="Reminder",
        goal_description="Send reminder notification",
        status="PENDING",
        defer_until=future.isoformat(),
        schedule_cron=None,
        created_at=now.isoformat(),
        last_triggered_at=None,
        deferral_count=0,
    )


@pytest.fixture
def mock_task_scheduler(sample_scheduled_task_info, sample_onetime_task_info):
    """Create mock task scheduler service."""
    scheduler = AsyncMock()

    # Mock get_scheduled_tasks
    scheduler.get_scheduled_tasks = AsyncMock(return_value=[sample_scheduled_task_info, sample_onetime_task_info])

    # Mock get_metrics
    scheduler.get_metrics = AsyncMock(
        return_value={
            "tasks_scheduled_total": 10.0,
            "tasks_completed_total": 5.0,
            "tasks_failed_total": 1.0,
            "tasks_pending": 4.0,
            "recurring_tasks": 2.0,
            "oneshot_tasks": 2.0,
            "scheduler_uptime_seconds": 3600.0,
        }
    )

    # Mock cancel_task
    scheduler.cancel_task = AsyncMock(return_value=True)

    return scheduler


@pytest.fixture
def app_with_scheduler(app, mock_task_scheduler):
    """Create app with task scheduler configured."""
    app.state.task_scheduler = mock_task_scheduler
    return app


@pytest.fixture
def client_with_scheduler(app_with_scheduler):
    """Create test client with scheduler available."""
    return TestClient(app_with_scheduler)


# =============================================================================
# LIST SCHEDULED TASKS TESTS
# =============================================================================


class TestListScheduledTasks:
    """Test listing scheduled tasks endpoint."""

    def test_list_tasks_without_auth_returns_401(self, client_with_scheduler):
        """Test that list endpoint without auth returns 401."""
        response = client_with_scheduler.get("/v1/scheduler/tasks")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_list_tasks_success(self, client_with_scheduler, admin_auth_headers):
        """Test successful task listing."""
        response = client_with_scheduler.get("/v1/scheduler/tasks", headers=admin_auth_headers)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()["data"]
        assert "tasks" in data
        assert len(data["tasks"]) == 2
        assert data["total"] == 2
        assert data["active_count"] >= 0
        assert data["recurring_count"] >= 0

    def test_list_tasks_with_status_filter(self, client_with_scheduler, admin_auth_headers):
        """Test task listing with status filter."""
        response = client_with_scheduler.get("/v1/scheduler/tasks?status=PENDING", headers=admin_auth_headers)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()["data"]
        # All returned tasks should have PENDING status
        for task in data["tasks"]:
            assert task["status"] == "PENDING"

    def test_list_tasks_with_limit(self, client_with_scheduler, admin_auth_headers):
        """Test task listing with limit."""
        response = client_with_scheduler.get("/v1/scheduler/tasks?limit=1", headers=admin_auth_headers)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()["data"]
        assert len(data["tasks"]) <= 1

    def test_list_tasks_scheduler_not_available(self, client, admin_auth_headers):
        """Test listing when scheduler is not available."""
        response = client.get("/v1/scheduler/tasks", headers=admin_auth_headers)

        assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
        assert "scheduler" in response.json()["detail"].lower()

    def test_list_tasks_includes_recurring_flag(self, client_with_scheduler, admin_auth_headers):
        """Test that tasks include is_recurring flag."""
        response = client_with_scheduler.get("/v1/scheduler/tasks", headers=admin_auth_headers)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()["data"]

        # Check that is_recurring is set correctly
        for task in data["tasks"]:
            assert "is_recurring" in task
            if task["schedule_cron"]:
                assert task["is_recurring"] is True
            else:
                assert task["is_recurring"] is False


# =============================================================================
# SCHEDULER STATS TESTS
# =============================================================================


class TestSchedulerStats:
    """Test scheduler statistics endpoint."""

    def test_get_stats_without_auth_returns_401(self, client_with_scheduler):
        """Test that stats endpoint without auth returns 401."""
        response = client_with_scheduler.get("/v1/scheduler/stats")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_get_stats_success(self, client_with_scheduler, admin_auth_headers):
        """Test successful stats retrieval."""
        response = client_with_scheduler.get("/v1/scheduler/stats", headers=admin_auth_headers)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()["data"]

        assert data["tasks_scheduled_total"] == 10
        assert data["tasks_completed_total"] == 5
        assert data["tasks_failed_total"] == 1
        assert data["tasks_pending"] == 4
        assert data["recurring_tasks"] == 2
        assert data["oneshot_tasks"] == 2
        assert data["scheduler_uptime_seconds"] == 3600.0

    def test_get_stats_scheduler_not_available(self, client, admin_auth_headers):
        """Test stats when scheduler is not available."""
        response = client.get("/v1/scheduler/stats", headers=admin_auth_headers)

        assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE


# =============================================================================
# CREATE SCHEDULED TASK TESTS
# =============================================================================


class TestCreateScheduledTask:
    """Test creating scheduled tasks endpoint."""

    def test_create_task_without_auth_returns_401(self, client_with_scheduler):
        """Test that create endpoint without auth returns 401."""
        response = client_with_scheduler.post(
            "/v1/scheduler/tasks",
            json={
                "name": "Test Task",
                "goal_description": "Test",
                "trigger_prompt": "Test prompt",
                "schedule_cron": "0 9 * * *",
            },
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_create_recurring_task_success(self, app_with_scheduler, admin_auth_headers, sample_scheduled_task):
        """Test creating a recurring task."""
        # Mock schedule_task to return a task
        app_with_scheduler.state.task_scheduler.schedule_task = AsyncMock(return_value=sample_scheduled_task)

        client = TestClient(app_with_scheduler)
        response = client.post(
            "/v1/scheduler/tasks",
            headers=admin_auth_headers,
            json={
                "name": "Daily Report",
                "goal_description": "Generate daily report",
                "trigger_prompt": "Generate the daily activity report",
                "schedule_cron": "0 9 * * *",
            },
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()["data"]
        assert data["name"] == "Daily Report"
        assert data["schedule_cron"] == "0 9 * * *"
        assert data["is_recurring"] is True

    def test_create_onetime_task_success(self, app_with_scheduler, admin_auth_headers):
        """Test creating a one-time task."""
        future_time = datetime.now(timezone.utc) + timedelta(hours=2)

        # Create a one-time task
        onetime_task = ScheduledTask(
            task_id="task_onetime_123",
            name="Reminder",
            goal_description="Send reminder",
            status="PENDING",
            defer_until=future_time,
            schedule_cron=None,
            trigger_prompt="Send reminder notification",
            origin_thought_id="api_created_test",
            created_at=datetime.now(timezone.utc),
            last_triggered_at=None,
            deferral_count=0,
            deferral_history=[],
        )

        app_with_scheduler.state.task_scheduler.schedule_task = AsyncMock(return_value=onetime_task)

        client = TestClient(app_with_scheduler)
        response = client.post(
            "/v1/scheduler/tasks",
            headers=admin_auth_headers,
            json={
                "name": "Reminder",
                "goal_description": "Send reminder",
                "trigger_prompt": "Send reminder notification",
                "defer_until": future_time.isoformat(),
            },
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()["data"]
        assert data["name"] == "Reminder"
        assert data["defer_until"] is not None
        assert data["is_recurring"] is False

    def test_create_task_missing_schedule_returns_400(self, client_with_scheduler, admin_auth_headers):
        """Test that creating task without schedule type returns 400."""
        response = client_with_scheduler.post(
            "/v1/scheduler/tasks",
            headers=admin_auth_headers,
            json={
                "name": "Test Task",
                "goal_description": "Test",
                "trigger_prompt": "Test prompt",
                # Neither defer_until nor schedule_cron
            },
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert (
            "defer_until" in response.json()["detail"].lower() or "schedule_cron" in response.json()["detail"].lower()
        )

    def test_create_task_both_schedule_types_returns_400(self, client_with_scheduler, admin_auth_headers):
        """Test that creating task with both schedule types returns 400."""
        future_time = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()

        response = client_with_scheduler.post(
            "/v1/scheduler/tasks",
            headers=admin_auth_headers,
            json={
                "name": "Test Task",
                "goal_description": "Test",
                "trigger_prompt": "Test prompt",
                "defer_until": future_time,
                "schedule_cron": "0 9 * * *",  # Both specified
            },
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "both" in response.json()["detail"].lower()

    def test_create_task_invalid_cron_returns_400(self, app_with_scheduler, admin_auth_headers):
        """Test that creating task with invalid cron returns 400."""
        # Mock schedule_task to raise ValueError for invalid cron
        app_with_scheduler.state.task_scheduler.schedule_task = AsyncMock(
            side_effect=ValueError("Invalid cron expression: invalid_cron")
        )

        client = TestClient(app_with_scheduler)
        response = client.post(
            "/v1/scheduler/tasks",
            headers=admin_auth_headers,
            json={
                "name": "Test Task",
                "goal_description": "Test",
                "trigger_prompt": "Test prompt",
                "schedule_cron": "invalid_cron",
            },
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "cron" in response.json()["detail"].lower()

    def test_create_task_empty_name_returns_422(self, client_with_scheduler, admin_auth_headers):
        """Test that creating task with empty name returns 422."""
        response = client_with_scheduler.post(
            "/v1/scheduler/tasks",
            headers=admin_auth_headers,
            json={
                "name": "",  # Empty name
                "goal_description": "Test",
                "trigger_prompt": "Test prompt",
                "schedule_cron": "0 9 * * *",
            },
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    def test_create_task_scheduler_not_available(self, client, admin_auth_headers):
        """Test creating task when scheduler is not available."""
        response = client.post(
            "/v1/scheduler/tasks",
            headers=admin_auth_headers,
            json={
                "name": "Test Task",
                "goal_description": "Test",
                "trigger_prompt": "Test prompt",
                "schedule_cron": "0 9 * * *",
            },
        )

        assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE


# =============================================================================
# CANCEL SCHEDULED TASK TESTS
# =============================================================================


class TestCancelScheduledTask:
    """Test cancelling scheduled tasks endpoint."""

    def test_cancel_task_without_auth_returns_401(self, client_with_scheduler):
        """Test that cancel endpoint without auth returns 401."""
        response = client_with_scheduler.delete("/v1/scheduler/tasks/task_123")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_cancel_task_success(self, client_with_scheduler, admin_auth_headers):
        """Test successful task cancellation."""
        response = client_with_scheduler.delete("/v1/scheduler/tasks/task_1234567890", headers=admin_auth_headers)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()["data"]
        assert data["success"] is True
        assert data["task_id"] == "task_1234567890"
        assert "cancelled" in data["message"].lower()

    def test_cancel_task_not_found(self, app_with_scheduler, admin_auth_headers):
        """Test cancelling non-existent task returns 404."""
        # Mock cancel_task to return False (not found)
        app_with_scheduler.state.task_scheduler.cancel_task = AsyncMock(return_value=False)

        client = TestClient(app_with_scheduler)
        response = client.delete("/v1/scheduler/tasks/nonexistent_task", headers=admin_auth_headers)

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert "not found" in response.json()["detail"].lower()

    def test_cancel_task_scheduler_not_available(self, client, admin_auth_headers):
        """Test cancelling task when scheduler is not available."""
        response = client.delete("/v1/scheduler/tasks/task_123", headers=admin_auth_headers)

        assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE


# =============================================================================
# RESPONSE FORMAT TESTS
# =============================================================================


class TestResponseFormats:
    """Test response format consistency."""

    def test_list_response_has_metadata(self, client_with_scheduler, admin_auth_headers):
        """Test that list response includes metadata."""
        response = client_with_scheduler.get("/v1/scheduler/tasks", headers=admin_auth_headers)

        assert response.status_code == status.HTTP_200_OK
        json_data = response.json()
        assert "metadata" in json_data
        assert "timestamp" in json_data["metadata"]
        assert "request_id" in json_data["metadata"]

    def test_stats_response_has_metadata(self, client_with_scheduler, admin_auth_headers):
        """Test that stats response includes metadata."""
        response = client_with_scheduler.get("/v1/scheduler/stats", headers=admin_auth_headers)

        assert response.status_code == status.HTTP_200_OK
        json_data = response.json()
        assert "metadata" in json_data

    def test_task_response_fields(self, client_with_scheduler, admin_auth_headers):
        """Test that task response has all required fields."""
        response = client_with_scheduler.get("/v1/scheduler/tasks", headers=admin_auth_headers)

        assert response.status_code == status.HTTP_200_OK
        tasks = response.json()["data"]["tasks"]

        if tasks:
            task = tasks[0]
            required_fields = [
                "task_id",
                "name",
                "goal_description",
                "status",
                "defer_until",
                "schedule_cron",
                "created_at",
                "last_triggered_at",
                "deferral_count",
                "is_recurring",
            ]
            for field in required_fields:
                assert field in task, f"Missing field: {field}"


# =============================================================================
# EDGE CASE TESTS
# =============================================================================


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_empty_task_list(self, app_with_scheduler, admin_auth_headers):
        """Test handling of empty task list."""
        app_with_scheduler.state.task_scheduler.get_scheduled_tasks = AsyncMock(return_value=[])

        client = TestClient(app_with_scheduler)
        response = client.get("/v1/scheduler/tasks", headers=admin_auth_headers)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()["data"]
        assert data["tasks"] == []
        assert data["total"] == 0
        assert data["active_count"] == 0
        assert data["recurring_count"] == 0

    def test_scheduler_service_exception(self, app_with_scheduler, admin_auth_headers):
        """Test handling of scheduler service exceptions."""
        app_with_scheduler.state.task_scheduler.get_scheduled_tasks = AsyncMock(
            side_effect=Exception("Database connection failed")
        )

        client = TestClient(app_with_scheduler)
        response = client.get("/v1/scheduler/tasks", headers=admin_auth_headers)

        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR

    def test_limit_validation_max(self, client_with_scheduler, admin_auth_headers):
        """Test that limit over maximum is rejected."""
        response = client_with_scheduler.get(
            "/v1/scheduler/tasks?limit=500", headers=admin_auth_headers  # Over 200 max
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    def test_limit_validation_min(self, client_with_scheduler, admin_auth_headers):
        """Test that limit under minimum is rejected."""
        response = client_with_scheduler.get("/v1/scheduler/tasks?limit=0", headers=admin_auth_headers)  # Under 1 min

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    def test_invalid_status_filter_still_works(self, client_with_scheduler, admin_auth_headers):
        """Test that invalid status filter just returns empty results."""
        response = client_with_scheduler.get("/v1/scheduler/tasks?status=INVALID_STATUS", headers=admin_auth_headers)

        # Should succeed but return no matching tasks
        assert response.status_code == status.HTTP_200_OK
        data = response.json()["data"]
        assert data["tasks"] == []


# =============================================================================
# CRON EXPRESSION VALIDATION TESTS
# =============================================================================


class TestCronExpressionValidation:
    """Test cron expression validation in task creation."""

    @pytest.mark.parametrize(
        "cron_expr,expected_valid",
        [
            ("0 9 * * *", True),  # Daily at 9am
            ("0 9 * * 1", True),  # Weekly on Monday at 9am
            ("*/15 * * * *", True),  # Every 15 minutes
            ("0 0 1 * *", True),  # Monthly on 1st at midnight
        ],
    )
    def test_valid_cron_expressions(
        self, app_with_scheduler, admin_auth_headers, sample_scheduled_task, cron_expr, expected_valid
    ):
        """Test various valid cron expressions."""
        sample_scheduled_task.schedule_cron = cron_expr
        app_with_scheduler.state.task_scheduler.schedule_task = AsyncMock(return_value=sample_scheduled_task)

        client = TestClient(app_with_scheduler)
        response = client.post(
            "/v1/scheduler/tasks",
            headers=admin_auth_headers,
            json={
                "name": "Test Cron Task",
                "goal_description": "Test",
                "trigger_prompt": "Test prompt",
                "schedule_cron": cron_expr,
            },
        )

        if expected_valid:
            assert response.status_code == status.HTTP_200_OK
        else:
            assert response.status_code == status.HTTP_400_BAD_REQUEST
