"""
Tests for transparency feed endpoint.
"""

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import status
from fastapi.testclient import TestClient

from ciris_engine.logic.adapters.api.app import create_app


@pytest.fixture
def client():
    """Create test client with mocked audit service."""
    app = create_app()

    # Mock the audit service to provide real-looking data
    mock_audit = AsyncMock()

    # Mock query_events to return realistic audit events
    async def mock_query_events(start_time=None, end_time=None, event_types=None):
        """Return mock audit events based on event types."""
        events = []

        if event_types and "handler_action" in event_types:
            # Return simple dict events that match what the transparency endpoint expects
            events.extend(
                [
                    type("Event", (), {"event_type": "handler_action", "data": {"action": "SPEAK", "duration_ms": 45}}),
                    type(
                        "Event",
                        (),
                        {
                            "event_type": "handler_action",
                            "data": {"action": "DEFER", "reason": "uncertainty", "duration_ms": 30},
                        },
                    ),
                    type("Event", (), {"event_type": "handler_action", "data": {"action": "SPEAK", "duration_ms": 50}}),
                    type(
                        "Event",
                        (),
                        {
                            "event_type": "handler_action",
                            "data": {"action": "REJECT", "harmful": True, "duration_ms": 20},
                        },
                    ),
                ]
            )

        if event_types and "dsar_request" in event_types:
            # Add some DSAR events
            events.extend(
                [
                    type("Event", (), {"event_type": "dsar_request", "data": {}}),
                    type("Event", (), {"event_type": "dsar_completed", "data": {}}),
                ]
            )

        return events

    mock_audit.query_events = mock_query_events
    app.state.audit_service = mock_audit

    return TestClient(app)


class TestTransparencyEndpoint:
    """Test transparency endpoint functionality."""

    def test_get_transparency_feed_no_auth(self, client):
        """Test that transparency feed requires no authentication."""
        response = client.get("/v1/transparency/feed")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        # Check required fields
        assert "period_start" in data
        assert "period_end" in data
        assert "total_interactions" in data
        assert "actions_taken" in data
        assert "deferrals_to_human" in data
        assert "harmful_requests_blocked" in data
        assert "uptime_percentage" in data

    def test_transparency_feed_time_periods(self, client):
        """Test transparency feed with different time periods."""
        # Test various valid periods
        for hours in [1, 24, 72, 168]:
            response = client.get(f"/v1/transparency/feed?hours={hours}")
            assert response.status_code == status.HTTP_200_OK

            data = response.json()
            period_start = datetime.fromisoformat(data["period_start"].replace("Z", "+00:00"))
            period_end = datetime.fromisoformat(data["period_end"].replace("Z", "+00:00"))

            # Check period is approximately correct (allow some variance)
            period_hours = (period_end - period_start).total_seconds() / 3600
            assert abs(period_hours - hours) < 1  # Within 1 hour tolerance

    def test_transparency_feed_invalid_hours(self, client):
        """Test transparency feed with invalid hour values."""
        # Too small
        response = client.get("/v1/transparency/feed?hours=0")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

        # Too large
        response = client.get("/v1/transparency/feed?hours=200")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_transparency_feed_action_breakdown(self, client):
        """Test that action breakdown is properly formatted."""
        response = client.get("/v1/transparency/feed")
        data = response.json()

        assert isinstance(data["actions_taken"], list)

        total_percentage = 0
        for action in data["actions_taken"]:
            assert "action" in action
            assert "count" in action
            assert "percentage" in action
            assert action["count"] >= 0
            assert 0 <= action["percentage"] <= 100
            total_percentage += action["percentage"]

        # Percentages should sum to approximately 100
        assert 99 <= total_percentage <= 101

    def test_transparency_feed_no_personal_data(self, client):
        """Test that transparency feed contains no personal data."""
        response = client.get("/v1/transparency/feed")
        data = response.json()

        # Convert to string and check for personal data patterns
        data_str = json.dumps(data).lower()

        # Should not contain
        assert "@" not in data_str  # No email addresses
        assert "discord" not in data_str  # No Discord IDs
        assert "user_" not in data_str  # No user IDs
        assert "channel_" not in data_str  # No channel IDs

        # Should only contain aggregated counts
        assert isinstance(data["total_interactions"], int)
        assert isinstance(data["deferrals_to_human"], int)
        assert isinstance(data["harmful_requests_blocked"], int)

    def test_transparency_policy_endpoint(self, client):
        """Test transparency policy endpoint."""
        response = client.get("/v1/transparency/policy")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        # Check required fields
        assert data["version"] == "1.0"
        assert data["retention_days"] == 14  # Pilot phase retention
        assert isinstance(data["commitments"], list)
        assert len(data["commitments"]) > 0

        # Check commitments content
        commitments_str = " ".join(data["commitments"]).lower()
        assert "not train" in commitments_str
        assert "14 days" in commitments_str
        assert "defer" in commitments_str

        # Check links
        assert "links" in data
        assert data["links"]["privacy"] == "/privacy-policy.html"
        assert data["links"]["terms"] == "/terms-of-service.html"
        assert data["links"]["when_we_pause"] == "/when-we-pause.html"
        assert data["links"]["dsar"] == "/v1/dsar"

    def test_transparency_system_status(self, client):
        """Test system status endpoint."""
        response = client.get("/v1/transparency/status")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        # Check required fields
        assert "status" in data
        assert "message" in data
        assert "pause_active" in data
        assert "updated_at" in data

        # Default should be operational
        assert data["status"] == "operational"
        assert data["pause_active"] is False

    def test_transparency_feed_safety_metrics(self, client):
        """Test that safety metrics are included."""
        response = client.get("/v1/transparency/feed")
        data = response.json()

        # Safety metrics should be present
        assert "harmful_requests_blocked" in data
        assert "rate_limit_triggers" in data
        assert "emergency_shutdowns" in data

        # All should be non-negative
        assert data["harmful_requests_blocked"] >= 0
        assert data["rate_limit_triggers"] >= 0
        assert data["emergency_shutdowns"] >= 0

    def test_transparency_feed_data_requests(self, client):
        """Test that DSAR metrics are included."""
        response = client.get("/v1/transparency/feed")
        data = response.json()

        # DSAR metrics
        assert "data_requests_received" in data
        assert "data_requests_completed" in data

        # Completed should not exceed received
        assert data["data_requests_completed"] <= data["data_requests_received"]

    @patch("ciris_engine.logic.adapters.api.routes.transparency.datetime")
    def test_transparency_feed_updates(self, mock_datetime, client):
        """Test that transparency feed updates over time."""
        # Mock current time with timezone awareness
        from datetime import timezone

        mock_now = datetime(2025, 8, 7, 15, 0, 0, tzinfo=timezone.utc)
        mock_datetime.now.return_value = mock_now
        mock_datetime.fromisoformat = datetime.fromisoformat

        response = client.get("/v1/transparency/feed?hours=1")
        data = response.json()

        period_end = datetime.fromisoformat(data["period_end"].replace("Z", "+00:00"))

        # Period end should be close to mocked time
        assert abs((period_end - mock_now).total_seconds()) < 60

    def test_transparency_feed_no_audit_service(self):
        """Test that transparency feed fails gracefully without audit service."""
        # Create app without audit service
        app = create_app()
        app.state.audit_service = None
        client = TestClient(app)

        response = client.get("/v1/transparency/feed")

        # Should return 503 Service Unavailable
        assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
        data = response.json()
        assert "audit service not available" in data["detail"].lower()
