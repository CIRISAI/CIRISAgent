"""Tests for CIRISVerify license disclosure integration in system context."""

from unittest.mock import AsyncMock, Mock

import pytest

from ciris_engine.logic.context.batch_context import BatchContextData
from ciris_engine.logic.formatters.system_snapshot import format_system_snapshot
from ciris_engine.schemas.runtime.system_context import SystemSnapshot


class TestSystemSnapshotDisclosure:
    """Tests for license disclosure fields in SystemSnapshot."""

    def test_system_snapshot_accepts_disclosure_text(self):
        """Test that SystemSnapshot can be created with disclosure text."""
        snapshot = SystemSnapshot(license_disclosure_text="Test disclosure message")
        assert snapshot.license_disclosure_text == "Test disclosure message"

    def test_system_snapshot_accepts_disclosure_severity(self):
        """Test that SystemSnapshot can be created with disclosure severity."""
        snapshot = SystemSnapshot(license_disclosure_text="Test disclosure", license_disclosure_severity="WARNING")
        assert snapshot.license_disclosure_severity == "WARNING"

    def test_system_snapshot_disclosure_fields_default_to_none(self):
        """Test that disclosure fields default to None."""
        snapshot = SystemSnapshot()
        assert snapshot.license_disclosure_text is None
        assert snapshot.license_disclosure_severity is None

    def test_system_snapshot_with_all_disclosure_fields(self):
        """Test SystemSnapshot with all disclosure-related fields."""
        snapshot = SystemSnapshot(
            license_disclosure_text="Community mode - limited features", license_disclosure_severity="INFO"
        )
        assert snapshot.license_disclosure_text == "Community mode - limited features"
        assert snapshot.license_disclosure_severity == "INFO"


class TestBatchContextDataDisclosure:
    """Tests for license disclosure fields in BatchContextData."""

    def test_batch_context_data_has_disclosure_fields(self):
        """Test that BatchContextData has disclosure fields."""
        batch_data = BatchContextData()
        assert hasattr(batch_data, "license_disclosure_text")
        assert hasattr(batch_data, "license_disclosure_severity")

    def test_batch_context_data_disclosure_defaults_to_none(self):
        """Test that disclosure fields default to None in BatchContextData."""
        batch_data = BatchContextData()
        assert batch_data.license_disclosure_text is None
        assert batch_data.license_disclosure_severity is None

    def test_batch_context_data_disclosure_can_be_set(self):
        """Test that disclosure fields can be set in BatchContextData."""
        batch_data = BatchContextData()
        batch_data.license_disclosure_text = "Test disclosure"
        batch_data.license_disclosure_severity = "CRITICAL"
        assert batch_data.license_disclosure_text == "Test disclosure"
        assert batch_data.license_disclosure_severity == "CRITICAL"


class TestFormatSystemSnapshotDisclosure:
    """Tests for disclosure formatting in format_system_snapshot."""

    def test_format_with_info_disclosure(self):
        """Test formatting with INFO severity disclosure."""
        snapshot = SystemSnapshot(
            license_disclosure_text="Running in licensed mode.", license_disclosure_severity="INFO"
        )
        formatted = format_system_snapshot(snapshot)
        assert "📋 LICENSE DISCLOSURE" in formatted
        assert "Running in licensed mode." in formatted

    def test_format_with_warning_disclosure(self):
        """Test formatting with WARNING severity disclosure."""
        snapshot = SystemSnapshot(
            license_disclosure_text="Community mode - limited features.", license_disclosure_severity="WARNING"
        )
        formatted = format_system_snapshot(snapshot)
        assert "⚠️ LICENSE DISCLOSURE ⚠️" in formatted
        assert "Community mode - limited features." in formatted

    def test_format_with_critical_disclosure(self):
        """Test formatting with CRITICAL severity disclosure."""
        snapshot = SystemSnapshot(
            license_disclosure_text="License verification failed!", license_disclosure_severity="CRITICAL"
        )
        formatted = format_system_snapshot(snapshot)
        assert "🚨🚨🚨 CRITICAL LICENSE DISCLOSURE 🚨🚨🚨" in formatted
        assert "License verification failed!" in formatted

    def test_format_with_lowercase_severity(self):
        """Test formatting handles lowercase severity from ciris_verify."""
        snapshot = SystemSnapshot(
            license_disclosure_text="Test disclosure", license_disclosure_severity="warning"  # lowercase
        )
        formatted = format_system_snapshot(snapshot)
        assert "⚠️ LICENSE DISCLOSURE ⚠️" in formatted

    def test_format_without_disclosure(self):
        """Test formatting without disclosure (no disclosure header)."""
        snapshot = SystemSnapshot()
        formatted = format_system_snapshot(snapshot)
        assert "LICENSE DISCLOSURE" not in formatted

    def test_format_with_none_disclosure_text(self):
        """Test formatting with None disclosure text (no disclosure header)."""
        snapshot = SystemSnapshot(license_disclosure_text=None, license_disclosure_severity="WARNING")
        formatted = format_system_snapshot(snapshot)
        assert "LICENSE DISCLOSURE" not in formatted

    def test_format_with_empty_disclosure_text(self):
        """Test formatting with empty disclosure text (no disclosure header)."""
        snapshot = SystemSnapshot(license_disclosure_text="", license_disclosure_severity="WARNING")
        formatted = format_system_snapshot(snapshot)
        assert "LICENSE DISCLOSURE" not in formatted

    def test_disclosure_appears_at_top(self):
        """Test that disclosure appears at the top of formatted output."""
        snapshot = SystemSnapshot(
            license_disclosure_text="Important notice",
            license_disclosure_severity="WARNING",
            current_time_utc="2025-01-01T00:00:00Z",
        )
        formatted = format_system_snapshot(snapshot)
        lines = formatted.split("\n")

        # Find the indices of disclosure and time
        disclosure_idx = None
        time_idx = None
        for i, line in enumerate(lines):
            if "LICENSE DISCLOSURE" in line:
                disclosure_idx = i
            if "Time of System Snapshot" in line:
                time_idx = i

        # Disclosure should appear before time
        assert disclosure_idx is not None
        assert time_idx is not None
        assert disclosure_idx < time_idx

    def test_format_with_unknown_severity_defaults_to_info(self):
        """Test that unknown severity defaults to INFO formatting."""
        snapshot = SystemSnapshot(license_disclosure_text="Test disclosure", license_disclosure_severity="UNKNOWN")
        formatted = format_system_snapshot(snapshot)
        assert "📋 LICENSE DISCLOSURE" in formatted
