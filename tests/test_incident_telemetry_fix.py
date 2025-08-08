"""
Test to verify the incident telemetry fix.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ciris_engine.logic.services.graph.incident_service import IncidentManagementService
from ciris_engine.schemas.services.graph.incident import IncidentNode, IncidentSeverity, IncidentStatus


@pytest.mark.asyncio
async def test_get_incident_count():
    """Test that get_incident_count method works correctly."""
    # Create mock services
    memory_bus = AsyncMock()
    time_service = MagicMock()
    time_service.now.return_value = datetime.now(timezone.utc)

    # Create service
    service = IncidentManagementService(memory_bus=memory_bus, time_service=time_service)

    # Mock _get_recent_incidents to return some test incidents
    test_incidents = [
        IncidentNode(
            id=f"incident_{i}",
            type="AUDIT_ENTRY",
            scope="LOCAL",
            attributes={},
            incident_type="ERROR",
            severity=IncidentSeverity.MEDIUM,
            status=IncidentStatus.OPEN,
            description=f"Test incident {i}",
            component="test_component",
            impact="Low",
            detection_time=datetime.now(timezone.utc) - timedelta(minutes=30),
            updated_by="test",
            updated_at=datetime.now(timezone.utc),
        )
        for i in range(5)
    ]

    with patch.object(service, "_get_recent_incidents", return_value=test_incidents):
        # Test getting incident count
        count = await service.get_incident_count(hours=1)

        # Verify
        assert count == 5, f"Expected 5 incidents, got {count}"

        # Verify the method was called with correct cutoff time
        service._get_recent_incidents.assert_called_once()
        call_args = service._get_recent_incidents.call_args[0]
        cutoff_time = call_args[0]

        # Check that cutoff time is approximately 1 hour ago
        expected_cutoff = time_service.now.return_value - timedelta(hours=1)
        time_diff = abs((cutoff_time - expected_cutoff).total_seconds())
        assert time_diff < 1, f"Cutoff time not correct, diff: {time_diff} seconds"


@pytest.mark.asyncio
async def test_get_incident_count_with_error():
    """Test that get_incident_count handles errors gracefully."""
    # Create mock services
    memory_bus = AsyncMock()
    time_service = MagicMock()
    time_service.now.return_value = datetime.now(timezone.utc)

    # Create service
    service = IncidentManagementService(memory_bus=memory_bus, time_service=time_service)

    # Mock _get_recent_incidents to raise an error
    with patch.object(service, "_get_recent_incidents", side_effect=Exception("Database error")):
        # Test getting incident count
        count = await service.get_incident_count(hours=1)

        # Should return 0 on error
        assert count == 0, f"Expected 0 on error, got {count}"


@pytest.mark.asyncio
async def test_incident_service_has_get_incident_count():
    """Test that the incident service has the get_incident_count method."""
    # Create mock services
    memory_bus = AsyncMock()
    time_service = MagicMock()
    time_service.now.return_value = datetime.now(timezone.utc)

    # Create service
    service = IncidentManagementService(memory_bus=memory_bus, time_service=time_service)

    # Check the method exists
    assert hasattr(service, "get_incident_count"), "IncidentManagementService should have get_incident_count method"
    assert callable(getattr(service, "get_incident_count")), "get_incident_count should be callable"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
