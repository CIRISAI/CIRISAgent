"""Tests for ciris_engine.cli entry point wrapper."""

import builtins
import sys
from pathlib import Path
from unittest.mock import Mock, patch

import pytest


class TestCLIEntryPoint:
    """Tests for the ciris-agent CLI command entry point."""

    def test_main_function_exists(self):
        """Verify main() function exists and is callable."""
        from ciris_engine import cli

        assert hasattr(cli, "main")
        assert callable(cli.main)

    def test_main_delegates_to_main_module(self, monkeypatch):
        """Test that cli.main() calls main.main()."""
        # Mock the main module import
        mock_main_module = Mock()
        mock_main_module.main = Mock()

        # Mock sys.path manipulation (we don't care about the actual path changes in this test)
        original_path = sys.path.copy()

        with patch.dict("sys.modules", {"main": mock_main_module}):
            from ciris_engine import cli

            cli.main()

            # Verify main.main() was called
            mock_main_module.main.assert_called_once()

        # Restore original sys.path
        sys.path = original_path

    def test_sys_path_manipulation(self, monkeypatch, tmp_path):
        """Test that parent directory added to sys.path."""
        # Create a mock file structure
        ciris_engine_dir = tmp_path / "ciris_engine"
        ciris_engine_dir.mkdir()
        cli_file = ciris_engine_dir / "cli.py"

        # Mock __file__ to point to our temp location
        mock_file_path = str(cli_file)

        # Mock the main module to prevent actual execution
        mock_main_module = Mock()

        original_path_len = len(sys.path)

        with patch.dict("sys.modules", {"main": mock_main_module}):
            with patch("ciris_engine.cli.Path") as mock_path_class:
                # Mock Path(__file__).parent.parent to return tmp_path
                mock_path_instance = Mock()
                mock_path_instance.parent.parent = tmp_path
                mock_path_class.return_value = mock_path_instance

                from ciris_engine import cli

                cli.main()

                # Verify parent directory was added to sys.path
                assert str(tmp_path) in sys.path or any(str(tmp_path) in p for p in sys.path)

    def test_sys_path_not_duplicated(self, monkeypatch):
        """Test parent dir not added if already in sys.path."""
        # Create a mock parent directory
        parent_dir = "/mock/parent/dir"

        # Pre-populate sys.path with the parent directory
        original_sys_path = sys.path.copy()
        sys.path.insert(0, parent_dir)

        mock_main_module = Mock()

        try:
            with patch.dict("sys.modules", {"main": mock_main_module}):
                with patch("ciris_engine.cli.Path") as mock_path_class:
                    mock_path_instance = Mock()
                    mock_path_instance.parent.parent = Path(parent_dir)
                    mock_path_class.return_value = mock_path_instance

                    from ciris_engine import cli

                    # Count occurrences before
                    count_before = sys.path.count(parent_dir)

                    cli.main()

                    # Count should be the same (no duplicate insertion)
                    count_after = sys.path.count(parent_dir)
                    assert count_after == count_before

        finally:
            # Restore original sys.path
            sys.path = original_sys_path

    def test_import_error_handling(self, monkeypatch, capsys):
        """Test graceful handling of main module import failure."""
        # Ensure main is not in sys.modules
        if "main" in sys.modules:
            original_main = sys.modules["main"]
            del sys.modules["main"]
        else:
            original_main = None

        try:
            # Store the original __import__ to avoid recursion
            original_import = builtins.__import__

            # Mock the import to raise ImportError
            def mock_import(name, *args, **kwargs):
                if name == "main":
                    raise ImportError("Mock import failure")
                return original_import(name, *args, **kwargs)

            with patch("builtins.__import__", side_effect=mock_import):
                from ciris_engine import cli

                with pytest.raises(SystemExit) as exc_info:
                    cli.main()

                # Verify exit code is 1
                assert exc_info.value.code == 1

                # Verify error message in stderr
                captured = capsys.readouterr()
                assert "ERROR: Failed to import main module" in captured.err

        finally:
            # Restore original main module if it existed
            if original_main is not None:
                sys.modules["main"] = original_main

    def test_import_error_message_content(self, monkeypatch, capsys):
        """Test error message provides helpful context."""
        if "main" in sys.modules:
            original_main = sys.modules["main"]
            del sys.modules["main"]
        else:
            original_main = None

        try:
            original_import = builtins.__import__

            def mock_import(name, *args, **kwargs):
                if name == "main":
                    raise ImportError("Mock failure for testing")
                return original_import(name, *args, **kwargs)

            with patch("builtins.__import__", side_effect=mock_import):
                from ciris_engine import cli

                with pytest.raises(SystemExit):
                    cli.main()

                captured = capsys.readouterr()
                # Verify helpful error messages
                assert "ERROR: Failed to import main module" in captured.err
                assert "This should not happen in a properly installed package" in captured.err

        finally:
            if original_main is not None:
                sys.modules["main"] = original_main

    def test_cli_preserves_click_functionality(self, monkeypatch):
        """Test that CLI wrapper preserves all Click options."""
        # This is an integration-style test
        mock_main_module = Mock()
        mock_main_func = Mock()
        mock_main_module.main = mock_main_func

        with patch.dict("sys.modules", {"main": mock_main_module}):
            from ciris_engine import cli

            # Call the wrapper
            cli.main()

            # Verify the main.main() function was called
            # (actual Click argument passing is tested in main.py tests)
            mock_main_func.assert_called_once()
