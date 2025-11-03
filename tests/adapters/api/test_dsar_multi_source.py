"""Comprehensive tests for multi-source DSAR API endpoints."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import status
from fastapi.testclient import TestClient

from ciris_engine.logic.adapters.api.app import create_app
from ciris_engine.logic.services.governance.dsar.schemas import (
    MultiSourceDSARAccessPackage,
    MultiSourceDSARCorrectionResult,
    MultiSourceDSARDeletionResult,
    MultiSourceDSARExportPackage,
)
from ciris_engine.schemas.consent.core import (
    ConsentCategory,
    ConsentImpactReport,
    ConsentStatus,
    ConsentStream,
    DSARAccessPackage,
    DSARDeletionStatus,
    DSARExportFormat,
    DSARExportPackage,
)


@pytest.fixture
def mock_orchestrator():
    """Create mock DSAROrchestrator."""
    orchestrator = AsyncMock()

    # Mock access request
    orchestrator.handle_access_request_multi_source.return_value = MultiSourceDSARAccessPackage(
        request_id="REQ-TEST-001",
        user_identifier="test@example.com",
        ciris_data=DSARAccessPackage(
            user_id="test@example.com",
            request_id="REQ-TEST-001",
            generated_at=datetime.now(timezone.utc),
            consent_status=ConsentStatus(
                user_id="test@example.com",
                stream=ConsentStream.TEMPORARY,
                categories=[ConsentCategory.INTERACTION],
                granted_at=datetime.now(timezone.utc),
                last_modified=datetime.now(timezone.utc),
            ),
            consent_history=[],
            interaction_summary={},
            contribution_metrics=ConsentImpactReport(
                user_id="test@example.com",
                total_interactions=10,
                patterns_contributed=2,
                users_helped=5,
                categories_active=[ConsentCategory.INTERACTION],
                impact_score=0.5,
                example_contributions=["Example pattern 1"],
            ),
            data_categories=[],
            retention_periods={},
            processing_purposes=[],
        ),
        external_sources=[],
        total_sources=1,
        total_records=5,
        generated_at=datetime.now(timezone.utc).isoformat(),
        processing_time_seconds=1.5,
    )

    # Mock export request
    orchestrator.handle_export_request_multi_source.return_value = MultiSourceDSARExportPackage(
        request_id="REQ-TEST-002",
        user_identifier="test@example.com",
        ciris_export=DSARExportPackage(
            user_id="test@example.com",
            request_id="REQ-TEST-002",
            export_format=DSARExportFormat.JSON,
            generated_at=datetime.now(timezone.utc).isoformat(),
            file_path=None,
            file_size_bytes=1024,
            record_counts={},
            checksum="abc123",
            includes_readme=True,
        ),
        external_exports=[],
        total_sources=1,
        total_records=10,
        total_size_bytes=1024,
        export_format="json",
        generated_at=datetime.now(timezone.utc).isoformat(),
        processing_time_seconds=2.0,
    )

    # Mock deletion request
    orchestrator.handle_deletion_request_multi_source.return_value = MultiSourceDSARDeletionResult(
        request_id="REQ-TEST-003",
        user_identifier="test@example.com",
        ciris_deletion=DSARDeletionStatus(
            ticket_id="MDSAR-TEST-003",
            user_id="test@example.com",
            decay_started=datetime.now(timezone.utc),
            current_phase="identity_severed",
            completion_percentage=10.0,
            estimated_completion=datetime.now(timezone.utc),
            milestones_completed=["identity_severed"],
            next_milestone="patterns_anonymizing",
            safety_patterns_retained=0,
        ),
        external_deletions=[],
        total_sources=1,
        sources_completed=1,
        sources_failed=0,
        total_records_deleted=15,
        all_verified=True,
        initiated_at=datetime.now(timezone.utc).isoformat(),
        processing_time_seconds=3.0,
    )

    # Mock correction request
    orchestrator.handle_correction_request_multi_source.return_value = MultiSourceDSARCorrectionResult(
        request_id="REQ-TEST-004",
        user_identifier="test@example.com",
        corrections_by_source={"ciris": {"email": "newemail@example.com"}},
        total_sources=1,
        total_corrections_applied=1,
        total_corrections_rejected=0,
        generated_at=datetime.now(timezone.utc).isoformat(),
        processing_time_seconds=1.0,
    )

    return orchestrator


@pytest.fixture
def client_with_auth(test_db, mock_orchestrator):
    """Create test client with mocked orchestrator."""
    app = create_app()

    # Mock authentication
    from ciris_engine.logic.adapters.api.services.auth_service import APIAuthService, User

    auth_service = APIAuthService()
    user = User(
        wa_id="test_admin",
        name="Test Admin",
        auth_type="password",
        api_role="ADMIN",
        created_at=datetime.now(timezone.utc),
        is_active=True,
    )
    auth_service._users[user.wa_id] = user
    app.state.auth_service = auth_service

    # Mock services needed for orchestrator
    with patch(
        "ciris_engine.logic.adapters.api.routes.dsar_multi_source._initialize_orchestrator"
    ) as mock_init:
        mock_init.return_value = mock_orchestrator
        client = TestClient(app)
        client.mock_orchestrator = mock_orchestrator
        yield client


class TestMultiSourceDSARSubmit:
    """Test multi-source DSAR submission endpoint."""

    def test_submit_access_request(self, client_with_auth):
        """Test submitting multi-source access request."""
        request_data = {
            "request_type": "access",
            "email": "user@example.com",
            "user_identifier": "user@example.com",
        }

        # Login first
        login_response = client_with_auth.post(
            "/v1/auth/login", json={"username": "admin", "password": "ciris_admin_password"}
        )
        token = login_response.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        response = client_with_auth.post("/v1/dsar/multi-source/", json=request_data, headers=headers)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["success"] is True
        assert data["data"]["ticket_id"].startswith("MDSAR-")
        assert data["data"]["status"] == "completed"
        assert data["data"]["total_sources"] == 1

    def test_submit_export_request(self, client_with_auth):
        """Test submitting multi-source export request."""
        request_data = {
            "request_type": "export",
            "email": "user@example.com",
            "user_identifier": "user@example.com",
            "export_format": "json",
        }

        login_response = client_with_auth.post(
            "/v1/auth/login", json={"username": "admin", "password": "ciris_admin_password"}
        )
        token = login_response.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        response = client_with_auth.post("/v1/dsar/multi-source/", json=request_data, headers=headers)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["success"] is True
        assert "data_package" in data["data"]

    def test_submit_deletion_request(self, client_with_auth):
        """Test submitting multi-source deletion request."""
        request_data = {
            "request_type": "delete",
            "email": "user@example.com",
            "user_identifier": "user@example.com",
        }

        login_response = client_with_auth.post(
            "/v1/auth/login", json={"username": "admin", "password": "ciris_admin_password"}
        )
        token = login_response.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        response = client_with_auth.post("/v1/dsar/multi-source/", json=request_data, headers=headers)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["success"] is True
        assert data["metadata"]["multi_source"] is True

    def test_submit_correction_request(self, client_with_auth):
        """Test submitting multi-source correction request."""
        request_data = {
            "request_type": "correct",
            "email": "user@example.com",
            "user_identifier": "user@example.com",
            "corrections": {"email": "newemail@example.com"},
        }

        login_response = client_with_auth.post(
            "/v1/auth/login", json={"username": "admin", "password": "ciris_admin_password"}
        )
        token = login_response.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        response = client_with_auth.post("/v1/dsar/multi-source/", json=request_data, headers=headers)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["success"] is True

    def test_submit_correction_without_corrections_field_fails(self, client_with_auth):
        """Test that correction request requires corrections field."""
        request_data = {
            "request_type": "correct",
            "email": "user@example.com",
            "user_identifier": "user@example.com",
            # Missing corrections field
        }

        login_response = client_with_auth.post(
            "/v1/auth/login", json={"username": "admin", "password": "ciris_admin_password"}
        )
        token = login_response.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        response = client_with_auth.post("/v1/dsar/multi-source/", json=request_data, headers=headers)

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_submit_requires_authentication(self, client_with_auth):
        """Test that submission requires authentication."""
        request_data = {
            "request_type": "access",
            "email": "user@example.com",
            "user_identifier": "user@example.com",
        }

        response = client_with_auth.post("/v1/dsar/multi-source/", json=request_data)

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_submit_invalid_request_type_fails(self, client_with_auth):
        """Test that invalid request type is rejected."""
        request_data = {
            "request_type": "invalid_type",
            "email": "user@example.com",
            "user_identifier": "user@example.com",
        }

        login_response = client_with_auth.post(
            "/v1/auth/login", json={"username": "admin", "password": "ciris_admin_password"}
        )
        token = login_response.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        response = client_with_auth.post("/v1/dsar/multi-source/", json=request_data, headers=headers)

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


class TestMultiSourceDSARStatus:
    """Test multi-source DSAR status endpoint."""

    def test_get_status_returns_details(self, client_with_auth):
        """Test getting status of multi-source DSAR."""
        # First submit a request
        request_data = {
            "request_type": "access",
            "email": "user@example.com",
            "user_identifier": "user@example.com",
        }

        login_response = client_with_auth.post(
            "/v1/auth/login", json={"username": "admin", "password": "ciris_admin_password"}
        )
        token = login_response.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        submit_response = client_with_auth.post("/v1/dsar/multi-source/", json=request_data, headers=headers)
        ticket_id = submit_response.json()["data"]["ticket_id"]

        # Get status
        status_response = client_with_auth.get(f"/v1/dsar/multi-source/{ticket_id}", headers=headers)

        assert status_response.status_code == status.HTTP_200_OK
        data = status_response.json()
        assert data["success"] is True
        assert data["data"]["ticket_id"] == ticket_id

    def test_get_status_nonexistent_ticket_fails(self, client_with_auth):
        """Test getting status of non-existent ticket."""
        login_response = client_with_auth.post(
            "/v1/auth/login", json={"username": "admin", "password": "ciris_admin_password"}
        )
        token = login_response.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        response = client_with_auth.get("/v1/dsar/multi-source/NONEXISTENT", headers=headers)

        assert response.status_code == status.HTTP_404_NOT_FOUND


class TestMultiSourceDSARPartialResults:
    """Test multi-source DSAR partial results endpoint."""

    def test_get_partial_results(self, client_with_auth):
        """Test getting partial results."""
        # Submit request first
        request_data = {
            "request_type": "access",
            "email": "user@example.com",
            "user_identifier": "user@example.com",
        }

        login_response = client_with_auth.post(
            "/v1/auth/login", json={"username": "admin", "password": "ciris_admin_password"}
        )
        token = login_response.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        submit_response = client_with_auth.post("/v1/dsar/multi-source/", json=request_data, headers=headers)
        ticket_id = submit_response.json()["data"]["ticket_id"]

        # Get partial results
        partial_response = client_with_auth.get(f"/v1/dsar/multi-source/{ticket_id}/partial", headers=headers)

        assert partial_response.status_code == status.HTTP_200_OK
        data = partial_response.json()
        assert data["success"] is True
        assert "partial_data" in data["data"]


class TestMultiSourceDSARCancellation:
    """Test multi-source DSAR cancellation endpoint."""

    def test_cancel_request(self, client_with_auth):
        """Test cancelling multi-source DSAR request."""
        # Submit request first
        request_data = {
            "request_type": "access",
            "email": "user@example.com",
            "user_identifier": "user@example.com",
        }

        login_response = client_with_auth.post(
            "/v1/auth/login", json={"username": "admin", "password": "ciris_admin_password"}
        )
        token = login_response.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        submit_response = client_with_auth.post("/v1/dsar/multi-source/", json=request_data, headers=headers)
        ticket_id = submit_response.json()["data"]["ticket_id"]

        # Try to cancel (will fail because already completed)
        cancel_response = client_with_auth.delete(f"/v1/dsar/multi-source/{ticket_id}", headers=headers)

        assert cancel_response.status_code == status.HTTP_200_OK
        data = cancel_response.json()
        # Should indicate cannot cancel completed request
        assert data["data"]["cancelled"] is False

    def test_cancel_nonexistent_request_fails(self, client_with_auth):
        """Test cancelling non-existent request."""
        login_response = client_with_auth.post(
            "/v1/auth/login", json={"username": "admin", "password": "ciris_admin_password"}
        )
        token = login_response.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        response = client_with_auth.delete("/v1/dsar/multi-source/NONEXISTENT", headers=headers)

        assert response.status_code == status.HTTP_404_NOT_FOUND


class TestMultiSourceDSARIntegration:
    """Integration tests for multi-source DSAR flow."""

    def test_complete_access_flow(self, client_with_auth):
        """Test complete access request flow."""
        login_response = client_with_auth.post(
            "/v1/auth/login", json={"username": "admin", "password": "ciris_admin_password"}
        )
        token = login_response.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # 1. Submit access request
        request_data = {
            "request_type": "access",
            "email": "integration@example.com",
            "user_identifier": "integration@example.com",
        }
        submit_response = client_with_auth.post("/v1/dsar/multi-source/", json=request_data, headers=headers)
        assert submit_response.status_code == status.HTTP_200_OK
        ticket_id = submit_response.json()["data"]["ticket_id"]

        # 2. Check status
        status_response = client_with_auth.get(f"/v1/dsar/multi-source/{ticket_id}", headers=headers)
        assert status_response.status_code == status.HTTP_200_OK

        # 3. Get partial results
        partial_response = client_with_auth.get(
            f"/v1/dsar/multi-source/{ticket_id}/partial", headers=headers
        )
        assert partial_response.status_code == status.HTTP_200_OK

    def test_orchestrator_called_with_correct_parameters(self, client_with_auth):
        """Test that orchestrator is called with correct parameters."""
        login_response = client_with_auth.post(
            "/v1/auth/login", json={"username": "admin", "password": "ciris_admin_password"}
        )
        token = login_response.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        request_data = {
            "request_type": "access",
            "email": "test@example.com",
            "user_identifier": "test@example.com",
        }

        client_with_auth.post("/v1/dsar/multi-source/", json=request_data, headers=headers)

        # Verify orchestrator was called
        orchestrator = client_with_auth.mock_orchestrator
        orchestrator.handle_access_request_multi_source.assert_called_once()
        call_kwargs = orchestrator.handle_access_request_multi_source.call_args.kwargs
        assert call_kwargs["user_identifier"] == "test@example.com"
