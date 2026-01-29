"""Tests for the pip detection fix in ToolInstaller."""

import subprocess
import sys
from unittest.mock import MagicMock, patch

import pytest

from ciris_engine.logic.services.tool.installer import ToolInstaller


class TestPipDetection:
    """Tests for pip detection logic."""

    def test_has_package_manager_pip_binary_exists(self):
        """Test that pip is detected if the binary exists (standard case)."""
        installer = ToolInstaller()

        # Mock shutil.which to return a path
        with patch("shutil.which", return_value="/usr/bin/pip"):
            assert installer._has_package_manager("pip") is True

    def test_has_package_manager_pip_module_exists(self):
        """Test that pip is detected if the binary is missing but module exists."""
        installer = ToolInstaller()

        # Mock shutil.which to return None (binary missing)
        # Mock subprocess.run to succeed (module present)
        with patch("shutil.which", return_value=None), \
             patch("subprocess.run") as mock_run:

            mock_run.return_value.returncode = 0

            assert installer._has_package_manager("pip") is True

            # Verify subprocess was called correctly
            mock_run.assert_called_once()
            args = mock_run.call_args[0][0]
            assert args == [sys.executable, "-m", "pip", "--version"]

    def test_has_package_manager_pip_missing_completely(self):
        """Test that pip is NOT detected if both binary and module are missing."""
        installer = ToolInstaller()

        # Mock shutil.which to return None
        # Mock subprocess.run to raise CalledProcessError (module missing/failing)
        with patch("shutil.which", return_value=None), \
             patch("subprocess.run", side_effect=subprocess.CalledProcessError(1, ["cmd"])):

            assert installer._has_package_manager("pip") is False

    def test_has_package_manager_other_tools_unchanged(self):
        """Test that other tools still use shutil.which."""
        installer = ToolInstaller()

        # Test brew (should rely on shutil.which)
        with patch("shutil.which", return_value="/usr/bin/brew") as mock_which, \
             patch("subprocess.run") as mock_run:

            assert installer._has_package_manager("brew") is True
            mock_which.assert_called_with("brew")
            mock_run.assert_not_called()
