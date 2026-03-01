"""Tests for ciris_engine.cli entry point wrapper."""

import sys
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

import pytest


class TestCLIEntryPoint:
    """Tests for the ciris-agent CLI command entry point."""

    def test_main_function_exists(self):
        """Verify main() function exists and is callable."""
        from ciris_engine import cli

        assert hasattr(cli, "main")
        assert callable(cli.main)

    def test_server_mode_with_adapter_flag(self, monkeypatch):
        """Test that --adapter flag triggers server mode."""
        monkeypatch.setattr(sys, "argv", ["ciris-agent", "--adapter", "api"])

        with patch("ciris_engine.cli._run_server_mode") as mock_server:
            with patch("ciris_engine.cli._run_desktop_mode") as mock_desktop:
                from ciris_engine import cli

                cli.main()

                mock_server.assert_called_once()
                mock_desktop.assert_not_called()

    def test_server_mode_with_server_flag(self, monkeypatch):
        """Test that --server flag triggers server mode."""
        monkeypatch.setattr(sys, "argv", ["ciris-agent", "--server"])

        with patch("ciris_engine.cli._run_server_mode") as mock_server:
            with patch("ciris_engine.cli._run_desktop_mode") as mock_desktop:
                from ciris_engine import cli

                cli.main()

                mock_server.assert_called_once()
                mock_desktop.assert_not_called()

    def test_desktop_mode_by_default(self, monkeypatch):
        """Test that desktop mode is used by default (no flags)."""
        monkeypatch.setattr(sys, "argv", ["ciris-agent"])

        with patch("ciris_engine.cli._run_server_mode") as mock_server:
            with patch("ciris_engine.cli._run_desktop_mode") as mock_desktop:
                from ciris_engine import cli

                cli.main()

                mock_desktop.assert_called_once()
                mock_server.assert_not_called()

    def test_help_triggers_server_mode(self, monkeypatch):
        """Test that --help triggers server mode (to show Click help)."""
        monkeypatch.setattr(sys, "argv", ["ciris-agent", "--help"])

        with patch("ciris_engine.cli._run_server_mode") as mock_server:
            with patch("ciris_engine.cli._run_desktop_mode") as mock_desktop:
                from ciris_engine import cli

                cli.main()

                mock_server.assert_called_once()
                mock_desktop.assert_not_called()

    def test_run_server_mode_imports_main(self, monkeypatch):
        """Test that _run_server_mode() imports and calls main.main()."""
        mock_main_module = Mock()
        mock_main_module.main = Mock()

        with patch.dict("sys.modules", {"main": mock_main_module}):
            from ciris_engine import cli

            cli._run_server_mode()

            mock_main_module.main.assert_called_once()

    def test_run_server_mode_handles_import_error(self, monkeypatch, capsys):
        """Test _run_server_mode() handles ImportError gracefully."""
        # Remove main from sys.modules if present
        if "main" in sys.modules:
            del sys.modules["main"]

        # Mock import to fail
        original_import = __builtins__.__import__ if hasattr(__builtins__, '__import__') else __import__

        def mock_import(name, *args, **kwargs):
            if name == "main":
                raise ImportError("Mock import failure")
            return original_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=mock_import):
            from ciris_engine import cli

            with pytest.raises(SystemExit) as exc_info:
                cli._run_server_mode()

            assert exc_info.value.code == 1

            captured = capsys.readouterr()
            assert "ERROR: Failed to import main module" in captured.err

    def test_server_entry_point_exists(self):
        """Verify server() entry point exists for ciris-server command."""
        from ciris_engine import cli

        assert hasattr(cli, "server")
        assert callable(cli.server)

    def test_desktop_entry_point_exists(self):
        """Verify desktop() entry point exists for ciris-desktop command."""
        from ciris_engine import cli

        assert hasattr(cli, "desktop")
        assert callable(cli.desktop)

    def test_sys_path_manipulation_in_server_mode(self, monkeypatch):
        """Test that parent directory is added to sys.path in server mode."""
        mock_main_module = Mock()

        original_path = sys.path.copy()

        with patch.dict("sys.modules", {"main": mock_main_module}):
            from ciris_engine import cli

            # Get the expected parent directory
            parent_dir = str(Path(cli.__file__).parent.parent)

            cli._run_server_mode()

            # Verify parent directory was added to sys.path
            assert parent_dir in sys.path

        # Restore original sys.path
        sys.path = original_path
