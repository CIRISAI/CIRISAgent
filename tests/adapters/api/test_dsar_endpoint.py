"""
Tests for Data Subject Access Request (DSAR) endpoint.
"""

import json
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
from fastapi import status
from fastapi.testclient import TestClient

from ciris_engine.logic.adapters.api.app import create_app
from ciris_engine.logic.adapters.api.routes import dsar


@pytest.fixture
def client():
    """Create test client."""
    app = create_app()
    return TestClient(app)


@pytest.fixture
def auth_headers():
    """Create auth headers for admin user."""
    return {"Authorization": "Bearer test_admin_token"}


class TestDSAREndpoint:
    """Test DSAR endpoint functionality."""

    def test_submit_dsar_request(self, client):
        """Test submitting a DSAR request."""
        request_data = {
            "request_type": "access",
            "email": "user@example.com",
            "user_identifier": "discord_123456",
            "details": "Please provide all data you have about me",
            "urgent": False,
        }

        response = client.post("/v1/dsr/", json=request_data)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["success"] is True
        assert "ticket_id" in data["data"]
        assert data["data"]["ticket_id"].startswith("DSAR-")
        assert data["data"]["status"] == "pending_review"
        assert "14 days" in data["data"]["message"]  # Pilot phase retention

    def test_submit_urgent_dsar_request(self, client):
        """Test submitting an urgent DSAR request."""
        request_data = {"request_type": "delete", "email": "urgent@example.com", "urgent": True}

        response = client.post("/v1/dsr/", json=request_data)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "3 days" in data["data"]["message"]  # Urgent timeline

    def test_dsar_request_types(self, client):
        """Test all valid DSAR request types."""
        valid_types = ["access", "delete", "export", "correct"]

        for request_type in valid_types:
            request_data = {"request_type": request_type, "email": f"{request_type}@example.com"}

            response = client.post("/v1/dsr/", json=request_data)
            assert response.status_code == status.HTTP_200_OK

    def test_invalid_dsar_request_type(self, client):
        """Test invalid DSAR request type."""
        request_data = {"request_type": "invalid_type", "email": "user@example.com"}

        response = client.post("/v1/dsr/", json=request_data)
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    def test_check_dsar_status(self, client):
        """Test checking DSAR request status."""
        # First submit a request
        request_data = {"request_type": "access", "email": "status@example.com"}

        submit_response = client.post("/v1/dsr/", json=request_data)
        ticket_id = submit_response.json()["data"]["ticket_id"]

        # Check status
        status_response = client.get(f"/v1/dsr/{ticket_id}")

        assert status_response.status_code == status.HTTP_200_OK
        data = status_response.json()
        assert data["success"] is True
        assert data["data"]["ticket_id"] == ticket_id
        assert data["data"]["status"] == "pending_review"
        assert data["data"]["request_type"] == "access"

    def test_check_nonexistent_dsar_status(self, client):
        """Test checking status of non-existent DSAR."""
        response = client.get("/v1/dsr/DSAR-NONEXISTENT")

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert "not found" in response.json()["detail"]

    @patch("ciris_engine.logic.adapters.api.routes.dsar.get_current_user")
    def test_list_dsar_requests_admin(self, mock_auth, client):
        """Test listing DSAR requests as admin."""
        # Mock admin user
        mock_auth.return_value = MagicMock(user_id="admin", username="admin", role="ADMIN")

        # Submit some requests first
        for i in range(3):
            request_data = {"request_type": "access", "email": f"user{i}@example.com"}
            client.post("/v1/dsr/", json=request_data)

        # List requests
        response = client.get("/v1/dsr/", headers={"Authorization": "Bearer admin_token"})

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["success"] is True
        assert "requests" in data["data"]
        assert data["data"]["total"] >= 3

    @patch("ciris_engine.logic.adapters.api.routes.dsar.get_current_user")
    def test_list_dsar_requests_non_admin(self, mock_auth, client):
        """Test that non-admins cannot list DSAR requests."""
        # Mock regular user
        mock_auth.return_value = MagicMock(user_id="user", username="user", role="OBSERVER")

        response = client.get("/v1/dsr/", headers={"Authorization": "Bearer user_token"})

        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert "Only administrators" in response.json()["detail"]

    @patch("ciris_engine.logic.adapters.api.routes.dsar.get_current_user")
    def test_update_dsar_status_admin(self, mock_auth, client):
        """Test updating DSAR status as admin."""
        # Mock admin user
        mock_auth.return_value = MagicMock(user_id="admin", username="admin", role="ADMIN")

        # Submit a request first
        request_data = {"request_type": "delete", "email": "update@example.com"}
        submit_response = client.post("/v1/dsr/", json=request_data)
        ticket_id = submit_response.json()["data"]["ticket_id"]

        # Update status
        update_response = client.put(
            f"/v1/dsr/{ticket_id}/status",
            params={"new_status": "in_progress", "notes": "Processing request"},
            headers={"Authorization": "Bearer admin_token"},
        )

        assert update_response.status_code == status.HTTP_200_OK
        data = update_response.json()
        assert data["success"] is True
        assert data["data"]["new_status"] == "in_progress"
        assert data["data"]["updated_by"] == "admin"

    @patch("ciris_engine.logic.adapters.api.routes.dsar.get_current_user")
    def test_update_dsar_invalid_status(self, mock_auth, client):
        """Test updating DSAR with invalid status."""
        # Mock admin user
        mock_auth.return_value = MagicMock(user_id="admin", username="admin", role="ADMIN")

        # Submit a request first
        request_data = {"request_type": "access", "email": "invalid@example.com"}
        submit_response = client.post("/v1/dsr/", json=request_data)
        ticket_id = submit_response.json()["data"]["ticket_id"]

        # Try invalid status
        update_response = client.put(
            f"/v1/dsr/{ticket_id}/status",
            params={"new_status": "invalid_status"},
            headers={"Authorization": "Bearer admin_token"},
        )

        assert update_response.status_code == status.HTTP_400_BAD_REQUEST
        assert "Invalid status" in update_response.json()["detail"]

    def test_dsar_retention_timeline(self, client):
        """Test that DSAR timeline reflects 14-day pilot retention."""
        request_data = {"request_type": "export", "email": "retention@example.com", "urgent": False}

        response = client.post("/v1/dsr/", json=request_data)
        data = response.json()

        # Check estimated completion
        estimated = datetime.strptime(data["data"]["estimated_completion"], "%Y-%m-%d")
        expected = datetime.utcnow().date() + timedelta(days=14)

        # Allow 1 day variance for timezone differences
        assert abs((estimated.date() - expected).days) <= 1

    def test_dsar_gdpr_articles_compliance(self, client):
        """Test that DSAR endpoint mentions GDPR articles."""
        # The endpoint docstring should reference GDPR articles
        import inspect

        docstring = inspect.getdoc(dsar.submit_dsar)

        assert "Article 15" in docstring  # Right of access
        assert "Article 16" in docstring  # Right to rectification
        assert "Article 17" in docstring  # Right to erasure
        assert "Article 20" in docstring  # Right to data portability
