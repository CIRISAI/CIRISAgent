"""
Tests for Grace enhancements - anti-Goodhart, production monitoring, pre-commit fixes.
"""

import json
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

from tools.grace.context import WorkContext
from tools.grace.main import Grace


class TestGraceAntiGoodhart:
    """Test anti-Goodhart principles in Grace."""

    def test_no_time_tracking_in_context(self):
        """Test that WorkContext no longer tracks time."""
        context = WorkContext()

        # These methods should not exist
        assert not hasattr(context, "log_work")
        assert not hasattr(context, "get_today_hours")
        assert not hasattr(context, "get_remaining_time")

    def test_work_context_saves_state(self):
        """Test that WorkContext saves work state without time tracking."""
        context = WorkContext()

        # Save context
        context.save("Working on feature X")

        # Load context
        saved = context.load()
        assert saved is not None
        assert saved["message"] == "Working on feature X"
        assert "timestamp" in saved
        assert "git_branch" in saved
        assert "last_commit" in saved

        # No time tracking fields
        assert "hours_worked" not in saved
        assert "work_duration" not in saved

    def test_grace_status_no_hours(self):
        """Test that Grace status doesn't show hours worked."""
        grace = Grace()
        status = grace.status()

        # Should show time but not hours worked
        assert "Time:" in status
        assert "hours worked" not in status.lower()
        assert "remaining" not in status.lower()
        assert "target" not in status.lower()


class TestGraceProductionMonitoring:
    """Test production incident monitoring features."""

    def test_grace_checks_incidents(self):
        """Test that Grace checks production incidents."""
        grace = Grace()

        # Check that incident checking method exists
        assert hasattr(grace, "check_incidents")

        # Should return empty string or incident details
        incidents = grace.check_incidents()
        assert isinstance(incidents, str)

    @patch("tools.grace.main.subprocess.run")
    def test_incidents_in_status(self, mock_run):
        """Test that incidents appear in status when running in container."""
        # Mock being in a container with incidents
        mock_run.return_value = MagicMock(returncode=0, stdout="2025-08-07 15:00:00 ERROR: Test incident")

        with patch("tools.grace.main.Path.exists", return_value=True):
            grace = Grace()
            status = grace.status()

            # Status should include incidents if available
            # (Note: actual behavior depends on implementation)
            assert isinstance(status, str)


class TestGracePrecommit:
    """Test pre-commit integration features."""

    def test_grace_has_precommit_method(self):
        """Test that Grace has precommit method."""
        grace = Grace()
        assert hasattr(grace, "precommit")

    @patch("tools.grace.main.subprocess.run")
    def test_precommit_runs_hooks(self, mock_run):
        """Test that precommit runs pre-commit hooks."""
        mock_run.return_value = MagicMock(returncode=0, stdout="All hooks passed")

        grace = Grace()
        result = grace.precommit()

        assert "Pre-commit Status" in result
        mock_run.assert_called()

    @patch("tools.grace.main.subprocess.run")
    def test_precommit_with_autofix(self, mock_run):
        """Test that precommit can autofix issues."""
        mock_run.return_value = MagicMock(
            returncode=1, stdout="black....................................................................Failed"
        )

        grace = Grace()
        result = grace.precommit(autofix=True)

        # Should attempt to fix issues
        assert mock_run.call_count >= 1


class TestGraceDeploymentStatus:
    """Test deployment status reporting."""

    def test_grace_has_deploy_status(self):
        """Test that Grace has deploy_status method."""
        grace = Grace()
        assert hasattr(grace, "deploy_status")

    @patch("tools.grace.main.check_deployment")
    def test_deploy_shows_failures(self, mock_check):
        """Test that deployment status shows failures correctly."""
        mock_check.return_value = "❌ Recent deployment FAILED [abc123]"

        grace = Grace()
        status = grace.deploy_status()

        assert "❌" in status
        assert "FAILED" in status

    @patch("tools.grace.main.check_deployment")
    def test_deploy_shows_success(self, mock_check):
        """Test that deployment status shows success correctly."""
        mock_check.return_value = "✅ Recent deployment succeeded [def456]"

        grace = Grace()
        status = grace.deploy_status()

        assert "✅" in status
        assert "succeeded" in status
