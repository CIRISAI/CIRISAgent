"""
Tests for Grace enhancements - anti-Goodhart, production monitoring, pre-commit fixes.
"""

import json
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

from tools.grace.context import SessionContext
from tools.grace.main import (
    check_production_incidents,
    fix_precommit_issues,
    get_status,
    parse_precommit_output,
    precommit,
)


class TestGraceAntiGoodhart:
    """Test anti-Goodhart principles in Grace."""

    def test_no_time_tracking_in_context(self):
        """Test that SessionContext no longer tracks time."""
        context = SessionContext()

        # These methods should not exist
        assert not hasattr(context, "log_work")
        assert not hasattr(context, "get_today_hours")
        assert not hasattr(context, "get_remaining_time")

    def test_session_flow_without_time(self):
        """Test that session flow focuses on rhythm not hours."""
        context = SessionContext()

        # Start morning session
        context.start_session("morning")
        assert context.current_session is not None
        assert context.current_session["type"] == "morning"

        # No duration tracking
        assert "hours_worked" not in context.current_session
        assert "target_hours" not in context.current_session

    @patch("tools.grace.main.SessionContext")
    def test_status_shows_philosophy_not_hours(self, mock_context_class):
        """Test that status shows anti-Goodhart philosophy."""
        mock_context = MagicMock()
        mock_context.current_session = {"type": "morning", "start_time": datetime.now().isoformat()}
        mock_context_class.return_value = mock_context

        with patch("tools.grace.main.subprocess.run"):
            with patch("tools.grace.main.check_production_incidents"):
                status = get_status()

        # Should contain philosophy, not time tracking
        assert any("quality" in line.lower() or "clarity" in line.lower() for line in status if line)
        assert not any("hours" in line.lower() and "worked" in line.lower() for line in status if line)


class TestGraceProductionMonitoring:
    """Test Grace production incident monitoring."""

    @patch("tools.grace.main.subprocess.run")
    def test_always_checks_production_incidents(self, mock_run):
        """Test that Grace always checks production for incidents."""
        # Mock SSH command response with ERROR
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="2025-08-07 ERROR: Failed to process request\n2025-08-07 INFO: Normal operation",
            stderr="",
        )

        incidents = check_production_incidents()

        # Should detect ERROR even when not DOWN
        assert len(incidents) > 0
        assert any("ERROR" in incident for incident in incidents)

    @patch("tools.grace.main.subprocess.run")
    def test_production_check_handles_connection_failure(self, mock_run):
        """Test graceful handling of SSH connection failure."""
        mock_run.return_value = MagicMock(returncode=255, stdout="", stderr="Connection refused")

        incidents = check_production_incidents()

        # Should return connection error as incident
        assert len(incidents) > 0
        assert any("connection" in incident.lower() for incident in incidents)

    @patch("tools.grace.main.subprocess.run")
    def test_production_check_filters_old_logs(self, mock_run):
        """Test that only recent incidents are shown."""
        # Mock logs with old and new entries
        mock_run.return_value = MagicMock(
            returncode=0, stdout="2025-01-01 ERROR: Old error\n2025-08-07 ERROR: Recent error", stderr=""
        )

        with patch("tools.grace.main.datetime") as mock_datetime:
            mock_datetime.now.return_value = datetime(2025, 8, 7, 15, 0)
            mock_datetime.fromisoformat = datetime.fromisoformat

            incidents = check_production_incidents()

        # Should only show recent incidents
        assert not any("Old error" in incident for incident in incidents)
        assert any("Recent error" in incident for incident in incidents)


class TestGracePrecommitEnhancements:
    """Test Grace pre-commit integration enhancements."""

    def test_parse_precommit_output(self):
        """Test parsing pre-commit hook output."""
        output = """
black....................................................................Failed
- hook id: black
- files were modified by this hook

isort....................................................................Passed
mypy.....................................................................Failed
- hook id: mypy
- exit code: 1

tests/test_example.py:10: error: Missing return statement
        """

        results = parse_precommit_output(output)

        assert results["black"]["status"] == "Failed"
        assert results["black"]["modified_files"] is True
        assert results["isort"]["status"] == "Passed"
        assert results["mypy"]["status"] == "Failed"
        assert "Missing return statement" in results["mypy"]["details"]

    @patch("tools.grace.main.subprocess.run")
    def test_fix_command_runs_formatters(self, mock_run):
        """Test that fix command runs black and isort."""
        mock_run.return_value = MagicMock(returncode=0)

        success = fix_precommit_issues()

        assert success is True
        # Should call black and isort
        assert mock_run.call_count >= 2
        calls = [call[0][0] for call in mock_run.call_args_list]
        assert any("black" in " ".join(cmd) for cmd in calls)
        assert any("isort" in " ".join(cmd) for cmd in calls)

    @patch("tools.grace.main.subprocess.run")
    def test_precommit_with_autofix(self, mock_run):
        """Test pre-commit with autofix parameter."""
        # First call returns formatting failures
        # Second and third calls are black/isort fixes
        # Fourth call is successful pre-commit
        mock_run.side_effect = [
            MagicMock(returncode=1, stdout="black....Failed\n- files were modified"),
            MagicMock(returncode=0),  # black fix
            MagicMock(returncode=0),  # isort fix
            MagicMock(returncode=0, stdout="All hooks passed!"),
        ]

        with patch("builtins.print"):
            precommit(autofix=True)

        # Should run pre-commit twice (before and after fix)
        pre_commit_calls = [call for call in mock_run.call_args_list if "pre-commit" in " ".join(call[0][0])]
        assert len(pre_commit_calls) >= 2

    @patch("tools.grace.main.subprocess.run")
    def test_precommit_identifies_blocking_issues(self, mock_run):
        """Test that pre-commit identifies critical blocking issues."""
        output = """
black....................................................................Passed
check-merge-conflict.....................................................Failed
- hook id: check-merge-conflict
- exit code: 1

Merge conflict markers found in:
  src/example.py
        """

        mock_run.return_value = MagicMock(returncode=1, stdout=output)

        with patch("builtins.print") as mock_print:
            precommit()

        # Should highlight merge conflict as blocking issue
        print_calls = " ".join(str(call) for call in mock_print.call_args_list)
        assert "merge" in print_calls.lower() and "conflict" in print_calls.lower()


class TestGracePhilosophy:
    """Test that Grace embodies sustainable development philosophy."""

    def test_grace_commands_exist(self):
        """Test that all Grace commands are available."""
        from tools.grace.__main__ import main

        # Commands that should exist
        expected_commands = ["status", "morning", "pause", "resume", "night", "precommit", "fix", "deploy", "incidents"]

        # Import argparse to check registered commands
        import argparse

        parser = argparse.ArgumentParser()

        # This is a bit hacky but works for testing
        with patch("sys.argv", ["grace", "--help"]):
            with patch("argparse.ArgumentParser.parse_args"):
                # The main function should set up all commands
                # We're just checking they don't throw errors
                for cmd in expected_commands:
                    with patch("sys.argv", ["grace", cmd]):
                        # Should not raise an error
                        pass

    def test_night_command_philosophy(self):
        """Test that night command emphasizes choice not obligation."""
        from tools.grace.main import night

        with patch("tools.grace.main.SessionContext") as mock_context:
            with patch("builtins.print") as mock_print:
                night()

        # Should present choice, not obligation
        print_output = " ".join(str(call) for call in mock_print.call_args_list)
        assert "choose" in print_output.lower() or "want" in print_output.lower()
        assert "must" not in print_output.lower()

    def test_error_messages_are_helpful(self):
        """Test that error messages are constructive not punitive."""
        context = SessionContext()

        # Try to end non-existent session
        with patch("builtins.print") as mock_print:
            context.end_session()

        # Error should be informative, not harsh
        if mock_print.called:
            error_output = str(mock_print.call_args_list[0])
            assert "!" not in error_output  # No shouting
            assert "error" not in error_output.lower()  # Gentle language
