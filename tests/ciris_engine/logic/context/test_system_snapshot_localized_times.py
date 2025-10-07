"""
Test system snapshot localized times functionality.

Tests that the system snapshot includes correctly localized times for
LONDON, CHICAGO, and TOKYO, and fails fast when time_service is missing.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock

import pytest

from ciris_engine.logic.context.system_snapshot import build_system_snapshot


class TestSystemSnapshotLocalizedTimes:
    """Test class for system snapshot localized time functionality."""

    @pytest.mark.asyncio
    async def test_localized_times_correct_calculation(self):
        """Test that localized times are correctly calculated for LONDON, CHICAGO, TOKYO."""
        # Create a fixed UTC time for testing (2025-09-27 19:30:00 UTC)
        fixed_utc_time = datetime(2025, 9, 27, 19, 30, 0, tzinfo=timezone.utc)

        # Mock time service
        time_service = Mock()
        time_service.now.return_value = fixed_utc_time

        # Mock required services
        resource_monitor = Mock()
        resource_monitor.get_resource_alerts.return_value = []

        secrets_service = Mock()
        secrets_service.get_secrets_stats = AsyncMock(
            return_value={"total_secrets_stored": 0, "secrets_filter_version": 1}
        )

        # Build snapshot
        snapshot = await build_system_snapshot(
            task=None,
            thought=None,
            resource_monitor=resource_monitor,
            time_service=time_service,
            secrets_service=secrets_service,
        )

        # Verify all localized time fields exist
        assert hasattr(snapshot, "current_time_utc")
        assert hasattr(snapshot, "current_time_london")
        assert hasattr(snapshot, "current_time_chicago")
        assert hasattr(snapshot, "current_time_tokyo")

        # Calculate expected localized times using zoneinfo (Python 3.9+ standard library)
        from zoneinfo import ZoneInfo

        london_tz = ZoneInfo("Europe/London")
        chicago_tz = ZoneInfo("America/Chicago")
        tokyo_tz = ZoneInfo("Asia/Tokyo")

        expected_utc = fixed_utc_time.isoformat()
        expected_london = fixed_utc_time.astimezone(london_tz).isoformat()
        expected_chicago = fixed_utc_time.astimezone(chicago_tz).isoformat()
        expected_tokyo = fixed_utc_time.astimezone(tokyo_tz).isoformat()

        # Verify times are correctly calculated
        assert snapshot.current_time_utc == expected_utc
        assert snapshot.current_time_london == expected_london
        assert snapshot.current_time_chicago == expected_chicago
        assert snapshot.current_time_tokyo == expected_tokyo

        # Verify time zone offsets are correct
        # London in September should be +01:00 (BST)
        assert "+01:00" in snapshot.current_time_london
        # Chicago in September should be -05:00 (CDT)
        assert "-05:00" in snapshot.current_time_chicago
        # Tokyo should be +09:00 (JST)
        assert "+09:00" in snapshot.current_time_tokyo

    @pytest.mark.asyncio
    async def test_fail_fast_when_time_service_none(self):
        """Test that system fails fast and loud when time_service is None."""
        # Mock required services
        resource_monitor = Mock()
        resource_monitor.get_resource_alerts.return_value = []

        secrets_service = Mock()
        secrets_service.get_secrets_stats = AsyncMock(
            return_value={"total_secrets_stored": 0, "secrets_filter_version": 1}
        )

        # Attempt to build snapshot without time_service
        with pytest.raises(RuntimeError) as exc_info:
            await build_system_snapshot(
                task=None,
                thought=None,
                resource_monitor=resource_monitor,
                time_service=None,  # This should cause failure
                secrets_service=secrets_service,
            )

        # Verify error message contains expected text
        error_msg = str(exc_info.value)
        assert "CRITICAL: time_service is None" in error_msg
        assert "Cannot get localized times" in error_msg
        assert "must be properly initialized" in error_msg

    @pytest.mark.asyncio
    async def test_fail_fast_when_time_service_returns_wrong_type(self):
        """Test that system fails fast when time_service.now() returns wrong type."""
        # Mock time service that returns wrong type
        time_service = Mock()
        time_service.now.return_value = "not a datetime"  # Wrong type

        # Mock required services
        resource_monitor = Mock()
        resource_monitor.get_resource_alerts.return_value = []

        secrets_service = Mock()
        secrets_service.get_secrets_stats = AsyncMock(
            return_value={"total_secrets_stored": 0, "secrets_filter_version": 1}
        )

        # Attempt to build snapshot with bad time_service
        with pytest.raises(RuntimeError) as exc_info:
            await build_system_snapshot(
                task=None,
                thought=None,
                resource_monitor=resource_monitor,
                time_service=time_service,
                secrets_service=secrets_service,
            )

        # Verify error message contains expected text
        error_msg = str(exc_info.value)
        assert "time_service.now() returned" in error_msg
        assert "expected datetime" in error_msg
        assert "not properly configured" in error_msg

    @pytest.mark.asyncio
    async def test_timezone_handling_across_dst_boundaries(self):
        """Test timezone handling works correctly across DST boundaries."""
        # Test with a winter date (no DST)
        winter_utc_time = datetime(2025, 1, 15, 12, 0, 0, tzinfo=timezone.utc)

        time_service = Mock()
        time_service.now.return_value = winter_utc_time

        # Mock required services
        resource_monitor = Mock()
        resource_monitor.get_resource_alerts.return_value = []

        secrets_service = Mock()
        secrets_service.get_secrets_stats = AsyncMock(
            return_value={"total_secrets_stored": 0, "secrets_filter_version": 1}
        )

        # Build snapshot
        snapshot = await build_system_snapshot(
            task=None,
            thought=None,
            resource_monitor=resource_monitor,
            time_service=time_service,
            secrets_service=secrets_service,
        )

        # In January (winter):
        # London should be +00:00 (GMT)
        # Chicago should be -06:00 (CST)
        # Tokyo should be +09:00 (JST - no DST)

        assert "+00:00" in snapshot.current_time_london  # GMT in winter
        assert "-06:00" in snapshot.current_time_chicago  # CST in winter
        assert "+09:00" in snapshot.current_time_tokyo  # JST (no DST)

    @pytest.mark.asyncio
    async def test_localized_times_with_batch_context(self):
        """Test that localized times work with batch context builder."""
        from ciris_engine.logic.context.batch_context import build_system_snapshot_with_batch
        from ciris_engine.schemas.runtime.system_context import TaskSummary

        # Create mock batch data
        batch_data = Mock()
        batch_data.top_tasks = []
        batch_data.recent_tasks = []
        batch_data.agent_identity = {}
        batch_data.identity_purpose = ""
        batch_data.identity_capabilities = []
        batch_data.identity_restrictions = []
        batch_data.secrets_snapshot = {"detected_secrets": [], "secrets_filter_version": 1, "total_secrets_stored": 0}
        batch_data.service_health = {}
        batch_data.circuit_breaker_status = {}
        batch_data.resource_alerts = []
        batch_data.shutdown_context = None
        batch_data.telemetry_summary = None
        batch_data.continuity_summary = None  # No continuity data in tests

        # Fixed time for testing
        fixed_utc_time = datetime(2025, 6, 15, 14, 30, 0, tzinfo=timezone.utc)
        time_service = Mock()
        time_service.now.return_value = fixed_utc_time

        # Build snapshot with batch context
        snapshot = await build_system_snapshot_with_batch(
            task=None,
            thought=None,
            batch_data=batch_data,
            time_service=time_service,
        )

        # Verify all localized time fields exist
        assert hasattr(snapshot, "current_time_utc")
        assert hasattr(snapshot, "current_time_london")
        assert hasattr(snapshot, "current_time_chicago")
        assert hasattr(snapshot, "current_time_tokyo")

        # Verify times are correctly set
        # June (summer): London +01:00 (BST), Chicago -05:00 (CDT), Tokyo +09:00 (JST)
        assert "+01:00" in snapshot.current_time_london
        assert "-05:00" in snapshot.current_time_chicago
        assert "+09:00" in snapshot.current_time_tokyo
