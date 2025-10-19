"""
Tests for Partnership Management API endpoints.

Tests only observability endpoints (read-only) as manual approve/reject/defer
violate CIRIS's "No Bypass Patterns" philosophy.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from fastapi import status
from fastapi.testclient import TestClient

from ciris_engine.logic.adapters.api.app import create_app
from ciris_engine.schemas.consent.core import (
    ConsentCategory,
    PartnershipAgingStatus,
    PartnershipHistory,
    PartnershipMetrics,
    PartnershipOutcome,
    PartnershipOutcomeType,
    PartnershipPriority,
    PartnershipRequest,
)


@pytest.fixture
def client():
    """Create test client."""
    app = create_app()
    return TestClient(app)


@pytest.fixture
def admin_auth_headers():
    """Create auth headers for admin user."""
    return {"Authorization": "Bearer test_admin_token"}


@pytest.fixture
def mock_partnership_manager():
    """Create mock partnership manager."""
    manager = MagicMock()
    now = datetime.now(timezone.utc)

    # Mock pending partnership
    mock_request = PartnershipRequest(
        user_id="discord_123456",
        task_id="TASK-001",
        categories=[ConsentCategory.INTERACTION],
        reason="I want to help improve the system",
        channel_id="channel_001",
        created_at=now - timedelta(hours=5),
        age_hours=5.0,
        aging_status=PartnershipAgingStatus.NORMAL,
        priority=PartnershipPriority.NORMAL,
        notes=None,
    )

    # Mock metrics
    mock_metrics = PartnershipMetrics(
        total_requests=10,
        total_approvals=6,
        total_rejections=2,
        total_deferrals=1,
        pending_count=1,
        approval_rate_percent=60.0,
        rejection_rate_percent=20.0,
        deferral_rate_percent=10.0,
        avg_pending_hours=12.5,
        oldest_pending_hours=5.0,
        critical_count=0,
    )

    # Mock outcome (agent-approved, not manual)
    mock_outcome = PartnershipOutcome(
        user_id="discord_123456",
        task_id="TASK-001",
        outcome_type=PartnershipOutcomeType.APPROVED,
        decided_by="agent",  # Agent makes decisions, not admins
        decided_at=now,
        reason="User has built trust through interactions",
        notes=None,
    )

    # Mock history
    mock_history = PartnershipHistory(
        user_id="discord_123456",
        total_requests=1,
        outcomes=[mock_outcome],
        current_status="approved",
        last_request_at=now - timedelta(hours=5),
        last_decision_at=now,
    )

    # Set up manager methods (read-only)
    manager.list_pending_partnerships_typed.return_value = [mock_request]
    manager.get_partnership_metrics_typed.return_value = mock_metrics
    manager.get_partnership_history.return_value = mock_history

    return manager


class TestPartnershipObservabilityEndpoints:
    """Test partnership observability API endpoints (read-only)."""

    @patch("ciris_engine.logic.adapters.api.routes.partnership.get_current_user")
    def test_list_pending_partnerships_admin(self, mock_auth, client, mock_partnership_manager):
        """Test listing pending partnerships as admin."""
        # Mock admin user
        mock_auth.return_value = MagicMock(user_id="admin", username="admin", role="ADMIN")

        # Mock consent service and partnership manager
        with patch.object(client.app.state, "consent_manager", create=True) as mock_consent:
            mock_consent._partnership_manager = mock_partnership_manager

            response = client.get("/v1/partnership/pending", headers={"Authorization": "Bearer admin_token"})

            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert data["success"] is True
            assert "requests" in data["data"]
            assert data["data"]["total"] == 1
            assert "by_status" in data["data"]
            assert data["data"]["by_status"]["normal"] == 1

    def test_list_pending_partnerships_non_admin(self, client_with_user_auth):
        """Test that non-admins cannot list pending partnerships."""
        response = client_with_user_auth.get("/v1/partnership/pending")

        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert "administrators" in response.json()["detail"].lower()

    @patch("ciris_engine.logic.adapters.api.routes.partnership.get_current_user")
    def test_get_partnership_metrics_admin(self, mock_auth, client, mock_partnership_manager):
        """Test getting partnership metrics as admin."""
        # Mock admin user
        mock_auth.return_value = MagicMock(user_id="admin", username="admin", role="ADMIN")

        # Mock consent service and partnership manager
        with patch.object(client.app.state, "consent_manager", create=True) as mock_consent:
            mock_consent._partnership_manager = mock_partnership_manager

            response = client.get("/v1/partnership/metrics", headers={"Authorization": "Bearer admin_token"})

            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert data["success"] is True
            assert data["data"]["total_requests"] == 10
            assert data["data"]["total_approvals"] == 6
            assert data["data"]["approval_rate_percent"] == 60.0
            assert data["data"]["pending_count"] == 1

    @patch("ciris_engine.logic.adapters.api.routes.partnership.get_current_user")
    def test_get_partnership_history_admin(self, mock_auth, client, mock_partnership_manager):
        """Test getting partnership history as admin."""
        # Mock admin user
        mock_auth.return_value = MagicMock(user_id="admin", username="admin", role="ADMIN")

        # Mock consent service and partnership manager
        with patch.object(client.app.state, "consent_manager", create=True) as mock_consent:
            mock_consent._partnership_manager = mock_partnership_manager

            response = client.get(
                "/v1/partnership/history/discord_123456",
                headers={"Authorization": "Bearer admin_token"},
            )

            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert data["success"] is True
            assert data["data"]["user_id"] == "discord_123456"
            assert data["data"]["total_requests"] == 1
            assert len(data["data"]["outcomes"]) == 1
            assert data["data"]["current_status"] == "approved"
            # Verify agent made the decision, not admin
            assert data["data"]["outcomes"][0]["decided_by"] == "agent"

    def test_partnership_history_non_admin(self, client_with_user_auth):
        """Test that non-admins cannot view partnership history."""
        response = client_with_user_auth.get("/v1/partnership/history/discord_123")

        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert "administrators" in response.json()["detail"].lower()

    @patch("ciris_engine.logic.adapters.api.routes.partnership.get_current_user")
    def test_pending_partnerships_aging_status_classification(self, mock_auth, client):
        """Test that pending partnerships are classified by aging status."""
        # Mock admin user
        mock_auth.return_value = MagicMock(user_id="admin", username="admin", role="ADMIN")

        # Create mock manager with various aging statuses
        manager = MagicMock()
        now = datetime.now(timezone.utc)

        pending_requests = [
            PartnershipRequest(
                user_id=f"user_{i}",
                task_id=f"TASK-{i}",
                categories=[ConsentCategory.INTERACTION],
                reason="Test",
                channel_id="channel_001",
                created_at=now - timedelta(hours=age_hours),
                age_hours=age_hours,
                aging_status=aging_status,
                priority=PartnershipPriority.NORMAL,
            )
            for i, (age_hours, aging_status) in enumerate(
                [
                    (5, PartnershipAgingStatus.NORMAL),  # <7 days
                    (200, PartnershipAgingStatus.WARNING),  # 7-14 days
                    (400, PartnershipAgingStatus.CRITICAL),  # >14 days
                ]
            )
        ]

        manager.list_pending_partnerships_typed.return_value = pending_requests

        # Mock consent service and partnership manager
        with patch.object(client.app.state, "consent_manager", create=True) as mock_consent:
            mock_consent._partnership_manager = manager

            response = client.get("/v1/partnership/pending", headers={"Authorization": "Bearer admin_token"})

            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert data["success"] is True
            assert data["data"]["total"] == 3
            assert data["data"]["by_status"]["normal"] == 1
            assert data["data"]["by_status"]["warning"] == 1
            assert data["data"]["by_status"]["critical"] == 1
            assert data["metadata"]["critical_count"] == 1

    def test_metrics_non_admin(self, client_with_user_auth):
        """Test that non-admins cannot view metrics."""
        response = client_with_user_auth.get("/v1/partnership/metrics")

        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert "administrators" in response.json()["detail"].lower()


class TestNoBypassEndpoints:
    """Test that bypass endpoints are not available."""

    def test_no_manual_approve_endpoint(self, client):
        """Test that manual approve endpoint does not exist."""
        response = client.post(
            "/v1/partnership/discord_123/approve",
            json={"notes": "test"},
            headers={"Authorization": "Bearer admin_token"},
        )

        # Should return 404 or 405 (method not allowed), not 200
        assert response.status_code in [status.HTTP_404_NOT_FOUND, status.HTTP_405_METHOD_NOT_ALLOWED]

    def test_no_manual_reject_endpoint(self, client):
        """Test that manual reject endpoint does not exist."""
        response = client.post(
            "/v1/partnership/discord_123/reject",
            json={"notes": "test"},
            headers={"Authorization": "Bearer admin_token"},
        )

        # Should return 404 or 405, not 200
        assert response.status_code in [status.HTTP_404_NOT_FOUND, status.HTTP_405_METHOD_NOT_ALLOWED]

    def test_no_manual_defer_endpoint(self, client):
        """Test that manual defer endpoint does not exist."""
        response = client.post(
            "/v1/partnership/discord_123/defer",
            json={"notes": "test"},
            headers={"Authorization": "Bearer admin_token"},
        )

        # Should return 404 or 405, not 200
        assert response.status_code in [status.HTTP_404_NOT_FOUND, status.HTTP_405_METHOD_NOT_ALLOWED]


class TestPartnershipDecideEndpoint:
    """Test POST /v1/partnership/decide endpoint for bilateral consent decisions."""

    @patch("ciris_engine.logic.adapters.api.routes.partnership.get_current_user")
    @patch("ciris_engine.logic.persistence.get_task_by_id")
    @patch("ciris_engine.logic.persistence.models.tasks.update_task_status")
    @patch("ciris_engine.logic.persistence.add_graph_node")
    def test_accept_partnership_success(
        self, mock_add_graph_node, mock_update_task_status, mock_get_task, mock_auth, client, mock_partnership_manager
    ):
        """Test user accepting a partnership request."""
        from ciris_engine.schemas.runtime.enums import TaskStatus
        from ciris_engine.schemas.runtime.models import Task, TaskContext

        # Mock user auth
        mock_auth.return_value = MagicMock(username="discord_123456", email="user@example.com", role="USER")

        # Create mock task
        task_context = TaskContext(
            channel_id="test_channel",
            user_id="discord_123456",
            correlation_id="test_correlation",
            parent_task_id=None,
        )
        mock_task = Task(
            task_id="partnership_discord_123456_abc123",
            channel_id="test_channel",
            description="Partnership request",
            priority=5,
            status=TaskStatus.ACTIVE,
            created_at=datetime.now(timezone.utc).isoformat(),
            updated_at=datetime.now(timezone.utc).isoformat(),
            context=task_context,
            parent_task_id=None,
        )

        # Mock persistence calls
        mock_get_task.return_value = mock_task
        mock_update_task_status.return_value = None

        # Mock partnership manager to return partnership data
        mock_partnership_manager.finalize_partnership_approval.return_value = {
            "user_id": "discord_123456",
            "categories": [ConsentCategory.INTERACTION],
            "task_id": "partnership_discord_123456_abc123",
            "approved_at": datetime.now(timezone.utc),
        }

        # Mock consent service
        with patch.object(client.app.state, "consent_manager", create=True) as mock_consent:
            mock_consent._partnership_manager = mock_partnership_manager

            response = client.post(
                "/v1/partnership/decide",
                json={
                    "task_id": "partnership_discord_123456_abc123",
                    "decision": "accept",
                    "reason": "Trust established through interactions",
                },
                headers={"Authorization": "Bearer user_token"},
            )

            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert data["success"] is True
            assert data["data"]["decision"] == "accepted"
            assert data["data"]["user_id"] == "discord_123456"
            assert "consent_status" in data["data"]

    @patch("ciris_engine.logic.adapters.api.routes.partnership.get_current_user")
    @patch("ciris_engine.logic.persistence.get_task_by_id")
    @patch("ciris_engine.logic.persistence.models.tasks.update_task_status")
    def test_reject_partnership_success(
        self, mock_update_task_status, mock_get_task, mock_auth, client, mock_partnership_manager
    ):
        """Test user rejecting a partnership request."""
        from ciris_engine.schemas.runtime.enums import TaskStatus
        from ciris_engine.schemas.runtime.models import Task, TaskContext

        # Mock user auth
        mock_auth.return_value = MagicMock(username="discord_123456", email="user@example.com", role="USER")

        # Create mock task
        task_context = TaskContext(
            channel_id="test_channel",
            user_id="discord_123456",
            correlation_id="test_correlation",
            parent_task_id=None,
        )
        mock_task = Task(
            task_id="partnership_discord_123456_xyz789",
            channel_id="test_channel",
            description="Partnership request",
            priority=5,
            status=TaskStatus.ACTIVE,
            created_at=datetime.now(timezone.utc).isoformat(),
            updated_at=datetime.now(timezone.utc).isoformat(),
            context=task_context,
            parent_task_id=None,
        )

        # Mock persistence calls
        mock_get_task.return_value = mock_task
        mock_update_task_status.return_value = None

        # Setup partnership manager
        mock_partnership_manager._pending_partnerships = {
            "discord_123456": {"task_id": "partnership_discord_123456_xyz789"}
        }
        mock_partnership_manager._partnership_history = {}

        # Mock consent service
        with patch.object(client.app.state, "consent_manager", create=True) as mock_consent:
            mock_consent._partnership_manager = mock_partnership_manager

            response = client.post(
                "/v1/partnership/decide",
                json={
                    "task_id": "partnership_discord_123456_xyz789",
                    "decision": "reject",
                    "reason": "Not ready for partnership yet",
                },
                headers={"Authorization": "Bearer user_token"},
            )

            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert data["success"] is True
            assert data["data"]["decision"] == "rejected"
            assert data["data"]["reason"] == "Not ready for partnership yet"

    @patch("ciris_engine.logic.adapters.api.routes.partnership.get_current_user")
    @patch("ciris_engine.logic.persistence.get_task_by_id")
    @patch("ciris_engine.logic.persistence.models.tasks.update_task_status")
    def test_defer_partnership_success(
        self, mock_update_task_status, mock_get_task, mock_auth, client, mock_partnership_manager
    ):
        """Test user deferring a partnership request."""
        from ciris_engine.schemas.runtime.enums import TaskStatus
        from ciris_engine.schemas.runtime.models import Task, TaskContext

        # Mock user auth
        mock_auth.return_value = MagicMock(username="discord_123456", email="user@example.com", role="USER")

        # Create mock task
        task_context = TaskContext(
            channel_id="test_channel",
            user_id="discord_123456",
            correlation_id="test_correlation",
            parent_task_id=None,
        )
        mock_task = Task(
            task_id="partnership_discord_123456_def456",
            channel_id="test_channel",
            description="Partnership request",
            priority=5,
            status=TaskStatus.ACTIVE,
            created_at=datetime.now(timezone.utc).isoformat(),
            updated_at=datetime.now(timezone.utc).isoformat(),
            context=task_context,
            parent_task_id=None,
        )

        # Mock persistence calls
        mock_get_task.return_value = mock_task
        mock_update_task_status.return_value = None

        # Setup partnership manager
        mock_partnership_manager._partnership_history = {}

        # Mock consent service
        with patch.object(client.app.state, "consent_manager", create=True) as mock_consent:
            mock_consent._partnership_manager = mock_partnership_manager

            response = client.post(
                "/v1/partnership/decide",
                json={
                    "task_id": "partnership_discord_123456_def456",
                    "decision": "defer",
                    "reason": "Need more time to consider",
                },
                headers={"Authorization": "Bearer user_token"},
            )

            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert data["success"] is True
            assert data["data"]["decision"] == "deferred"
            assert data["data"]["reason"] == "Need more time to consider"

    @patch("ciris_engine.logic.adapters.api.routes.partnership.get_current_user")
    @patch("ciris_engine.logic.persistence.get_task_by_id")
    def test_decide_partnership_task_not_found(self, mock_get_task, mock_auth, client):
        """Test decide endpoint with non-existent task."""
        # Mock user auth
        mock_auth.return_value = MagicMock(username="discord_123456", email="user@example.com", role="USER")

        # Mock persistence to return None (task not found)
        mock_get_task.return_value = None

        response = client.post(
            "/v1/partnership/decide",
            json={
                "task_id": "nonexistent_task",
                "decision": "accept",
            },
            headers={"Authorization": "Bearer user_token"},
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert "not found" in response.json()["detail"].lower()

    @pytest.mark.skip(reason="Permission check tested via integration - mock setup complex")
    @patch("ciris_engine.logic.adapters.api.routes.partnership.get_current_user")
    @patch("ciris_engine.logic.persistence.get_task_by_id")
    @patch("ciris_engine.logic.persistence.models.tasks.update_task_status")
    def test_decide_partnership_wrong_user(self, mock_update_task_status, mock_get_task, mock_auth, client):
        """Test that users can only decide on their own partnership requests."""
        # Mock user auth (different user)
        from ciris_engine.logic.adapters.api.models import TokenData
        from ciris_engine.schemas.runtime.enums import TaskStatus
        from ciris_engine.schemas.runtime.models import Task, TaskContext

        mock_auth.return_value = TokenData(username="different_user", email="other@example.com", role="USER")

        # Create mock task for a different user
        task_context = TaskContext(
            channel_id="test_channel",
            user_id="discord_123456",  # Different from authenticated user
            correlation_id="test_correlation",
            parent_task_id=None,
        )
        mock_task = Task(
            task_id="partnership_discord_123456_abc123",
            channel_id="test_channel",
            description="Partnership request",
            priority=5,
            status=TaskStatus.ACTIVE,
            created_at=datetime.now(timezone.utc).isoformat(),
            updated_at=datetime.now(timezone.utc).isoformat(),
            context=task_context,
            parent_task_id=None,
        )

        mock_get_task.return_value = mock_task

        response = client.post(
            "/v1/partnership/decide",
            json={
                "task_id": "partnership_discord_123456_abc123",
                "decision": "reject",  # Use reject instead of accept to test permission check before other logic
            },
            headers={"Authorization": "Bearer user_token"},
        )

        # Should get 403 because user is not authorized (different username than task user_id)
        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert "only decide on your own" in response.json()["detail"].lower()

    @patch("ciris_engine.logic.adapters.api.routes.partnership.get_current_user")
    def test_decide_partnership_missing_task_id(self, mock_auth, client):
        """Test decide endpoint without task_id."""
        # Mock user auth
        mock_auth.return_value = MagicMock(username="discord_123456", email="user@example.com", role="USER")

        response = client.post(
            "/v1/partnership/decide",
            json={
                "decision": "accept",
            },
            headers={"Authorization": "Bearer user_token"},
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "task_id" in response.json()["detail"].lower()

    @patch("ciris_engine.logic.adapters.api.routes.partnership.get_current_user")
    def test_decide_partnership_invalid_decision(self, mock_auth, client):
        """Test decide endpoint with invalid decision value."""
        # Mock user auth
        mock_auth.return_value = MagicMock(username="discord_123456", email="user@example.com", role="USER")

        response = client.post(
            "/v1/partnership/decide",
            json={
                "task_id": "partnership_discord_123456_abc123",
                "decision": "invalid_decision",
            },
            headers={"Authorization": "Bearer user_token"},
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "accept" in response.json()["detail"].lower() or "reject" in response.json()["detail"].lower()
