"""
Tests for Partnership Management API endpoints.
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

    # Mock outcome
    mock_outcome = PartnershipOutcome(
        user_id="discord_123456",
        task_id="TASK-001",
        outcome_type=PartnershipOutcomeType.APPROVED,
        decided_by="admin",
        decided_at=now,
        reason="Manually approved by admin",
        notes="Good candidate",
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

    # Set up manager methods
    manager.list_pending_partnerships_typed.return_value = [mock_request]
    manager.get_partnership_metrics_typed.return_value = mock_metrics

    # Manual methods are async - need AsyncMock
    from unittest.mock import AsyncMock

    manager.manual_approve = AsyncMock(return_value=mock_outcome)
    manager.manual_reject = AsyncMock(return_value=mock_outcome)
    manager.manual_defer = AsyncMock(return_value=mock_outcome)

    manager.finalize_partnership_approval.return_value = None
    manager.get_partnership_history.return_value = mock_history

    return manager


class TestPartnershipEndpoints:
    """Test partnership API endpoints."""

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
        response = client_with_user_auth.get("/v1/partnership/pending", headers={"Authorization": "Bearer user_token"})

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
    def test_approve_partnership_admin(self, mock_auth, client, mock_partnership_manager):
        """Test approving a partnership as admin."""
        # Mock admin user
        mock_auth.return_value = MagicMock(user_id="admin", username="admin", role="ADMIN")

        # Mock consent service and partnership manager
        with patch.object(client.app.state, "consent_manager", create=True) as mock_consent:
            mock_consent._partnership_manager = mock_partnership_manager

            response = client.post(
                "/v1/partnership/discord_123456/approve",
                json={"notes": "Good candidate"},
                headers={"Authorization": "Bearer admin_token"},
            )

            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert data["success"] is True
            assert data["data"]["user_id"] == "discord_123456"
            assert data["data"]["outcome_type"] == "approved"
            assert data["data"]["decided_by"] == "admin"

            # Verify manager methods were called
            mock_partnership_manager.manual_approve.assert_called_once_with(
                user_id="discord_123456",
                admin_username="admin",
                notes="Good candidate",
            )
            mock_partnership_manager.finalize_partnership_approval.assert_called_once_with("discord_123456", "TASK-001")

    @patch("ciris_engine.logic.adapters.api.routes.partnership.get_current_user")
    def test_reject_partnership_admin(self, mock_auth, client, mock_partnership_manager):
        """Test rejecting a partnership as admin."""
        # Mock admin user
        mock_auth.return_value = MagicMock(user_id="admin", username="admin", role="ADMIN")

        # Update mock outcome for rejection
        from unittest.mock import AsyncMock

        mock_outcome = PartnershipOutcome(
            user_id="discord_123456",
            task_id="TASK-001",
            outcome_type=PartnershipOutcomeType.REJECTED,
            decided_by="admin",
            decided_at=datetime.now(timezone.utc),
            reason="Not suitable at this time",
            notes="Needs more interaction history",
        )
        mock_partnership_manager.manual_reject = AsyncMock(return_value=mock_outcome)

        # Mock consent service and partnership manager
        with patch.object(client.app.state, "consent_manager", create=True) as mock_consent:
            mock_consent._partnership_manager = mock_partnership_manager

            response = client.post(
                "/v1/partnership/discord_123456/reject",
                json={"notes": "Needs more interaction history"},
                headers={"Authorization": "Bearer admin_token"},
            )

            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert data["success"] is True
            assert data["data"]["outcome_type"] == "rejected"
            assert data["data"]["notes"] == "Needs more interaction history"

    @patch("ciris_engine.logic.adapters.api.routes.partnership.get_current_user")
    def test_defer_partnership_admin(self, mock_auth, client, mock_partnership_manager):
        """Test deferring a partnership as admin."""
        # Mock admin user
        mock_auth.return_value = MagicMock(user_id="admin", username="admin", role="ADMIN")

        # Update mock outcome for deferral
        from unittest.mock import AsyncMock

        mock_outcome = PartnershipOutcome(
            user_id="discord_123456",
            task_id="TASK-001",
            outcome_type=PartnershipOutcomeType.DEFERRED,
            decided_by="admin",
            decided_at=datetime.now(timezone.utc),
            reason="Need more information",
            notes="Waiting for user clarification",
        )
        mock_partnership_manager.manual_defer = AsyncMock(return_value=mock_outcome)

        # Mock consent service and partnership manager
        with patch.object(client.app.state, "consent_manager", create=True) as mock_consent:
            mock_consent._partnership_manager = mock_partnership_manager

            response = client.post(
                "/v1/partnership/discord_123456/defer",
                json={"notes": "Waiting for user clarification"},
                headers={"Authorization": "Bearer admin_token"},
            )

            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert data["success"] is True
            assert data["data"]["outcome_type"] == "deferred"
            assert data["data"]["reason"] == "Need more information"

    @patch("ciris_engine.logic.adapters.api.routes.partnership.get_current_user")
    def test_approve_nonexistent_partnership(self, mock_auth, client, mock_partnership_manager):
        """Test approving non-existent partnership returns 404."""
        # Mock admin user
        mock_auth.return_value = MagicMock(user_id="admin", username="admin", role="ADMIN")

        # Mock ValueError for non-existent partnership
        from unittest.mock import AsyncMock

        mock_partnership_manager.manual_approve = AsyncMock(side_effect=ValueError("No pending partnership request"))

        # Mock consent service and partnership manager
        with patch.object(client.app.state, "consent_manager", create=True) as mock_consent:
            mock_consent._partnership_manager = mock_partnership_manager

            response = client.post(
                "/v1/partnership/nonexistent_user/approve",
                json={},
                headers={"Authorization": "Bearer admin_token"},
            )

            assert response.status_code == status.HTTP_404_NOT_FOUND
            assert "No pending partnership request" in response.json()["detail"]

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

    def test_partnership_actions_non_admin(self, client_with_user_auth):
        """Test that non-admins cannot perform partnership actions."""
        # Try approve
        response = client_with_user_auth.post(
            "/v1/partnership/discord_123/approve",
            json={},
            headers={"Authorization": "Bearer user_token"},
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

        # Try reject
        response = client_with_user_auth.post(
            "/v1/partnership/discord_123/reject",
            json={},
            headers={"Authorization": "Bearer user_token"},
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

        # Try defer
        response = client_with_user_auth.post(
            "/v1/partnership/discord_123/defer",
            json={},
            headers={"Authorization": "Bearer user_token"},
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

        # Try history
        response = client_with_user_auth.get(
            "/v1/partnership/history/discord_123",
            headers={"Authorization": "Bearer user_token"},
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

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
