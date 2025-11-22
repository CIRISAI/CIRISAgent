"""Tests for first-run detection and setup wizard."""

import base64
from pathlib import Path
from unittest.mock import Mock, patch

import pytest


class TestFirstRunDetection:
    """Tests for first-run detection logic."""

    def test_is_first_run_no_config(self, tmp_path, monkeypatch):
        """Test first run detected when no .env exists."""
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.delenv("CIRIS_CONFIGURED", raising=False)
        empty_dir = tmp_path / "empty_dir"
        empty_dir.mkdir()
        monkeypatch.chdir(empty_dir)

        from ciris_engine.logic.setup.first_run import is_first_run

        assert is_first_run() is True

    def test_is_first_run_with_env_var(self, monkeypatch):
        """Test not first run when CIRIS_CONFIGURED env var set."""
        monkeypatch.setenv("CIRIS_CONFIGURED", "true")

        from ciris_engine.logic.setup.first_run import is_first_run

        assert is_first_run() is False

    def test_is_first_run_with_cwd_env(self, tmp_path, monkeypatch):
        """Test not first run when .env exists in current directory (development mode)."""
        # Create .git directory to simulate development mode
        git_dir = tmp_path / ".git"
        git_dir.mkdir()

        env_file = tmp_path / ".env"
        env_file.write_text("CIRIS_CONFIGURED=true")
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("CIRIS_CONFIGURED", raising=False)

        from ciris_engine.logic.setup.first_run import is_first_run

        assert is_first_run() is False

    def test_is_first_run_with_user_env(self, tmp_path, monkeypatch):
        """Test not first run when .env exists in ~/.ciris/."""
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.delenv("CIRIS_CONFIGURED", raising=False)
        ciris_dir = tmp_path / ".ciris"
        ciris_dir.mkdir()
        env_file = ciris_dir / ".env"
        env_file.write_text("CIRIS_CONFIGURED=true")

        # Change to different directory
        work_dir = tmp_path / "work"
        work_dir.mkdir()
        monkeypatch.chdir(work_dir)

        from ciris_engine.logic.setup.first_run import is_first_run

        assert is_first_run() is False


class TestMacOSPythonDetection:
    """Tests for macOS Python installation validation."""

    def test_check_macos_python_non_macos(self, monkeypatch):
        """Test check passes on non-macOS systems."""
        with patch("platform.system", return_value="Linux"):
            from ciris_engine.logic.setup.first_run import check_macos_python

            is_valid, message = check_macos_python()
            assert is_valid is True
            assert message == ""

    def test_check_macos_python_homebrew(self, monkeypatch):
        """Test check passes with Homebrew Python on macOS."""
        with patch("platform.system", return_value="Darwin"):
            with patch("subprocess.run") as mock_run:
                # which python3 returns Homebrew path
                mock_run.return_value = Mock(returncode=0, stdout="/opt/homebrew/bin/python3\n")

                from ciris_engine.logic.setup.first_run import check_macos_python

                is_valid, message = check_macos_python()
                assert is_valid is True
                assert message == ""

    def test_check_macos_python_stub_no_xcode(self, monkeypatch):
        """Test check fails with system stub and no Xcode CLT."""
        with patch("platform.system", return_value="Darwin"):
            with patch("subprocess.run") as mock_run:

                def run_side_effect(*args, **kwargs):
                    cmd = args[0]
                    if cmd[0] == "which":
                        return Mock(returncode=0, stdout="/usr/bin/python3\n")
                    elif cmd[0] == "xcode-select":
                        return Mock(returncode=2)  # Not installed
                    return Mock(returncode=0, stdout="3.12\n")

                mock_run.side_effect = run_side_effect

                from ciris_engine.logic.setup.first_run import check_macos_python

                is_valid, message = check_macos_python()
                assert is_valid is False
                assert "Xcode Command Line Tools" in message
                assert "xcode-select --install" in message

    def test_check_macos_python_stub_with_xcode(self, monkeypatch):
        """Test check passes with system stub but Xcode CLT installed."""
        with patch("platform.system", return_value="Darwin"):
            with patch("subprocess.run") as mock_run:

                def run_side_effect(*args, **kwargs):
                    cmd = args[0]
                    if cmd[0] == "which":
                        return Mock(returncode=0, stdout="/usr/bin/python3\n")
                    elif cmd[0] == "xcode-select":
                        return Mock(returncode=0)  # Installed
                    elif "version_info" in str(cmd):
                        return Mock(returncode=0, stdout="3.12\n")
                    return Mock(returncode=0)

                mock_run.side_effect = run_side_effect

                from ciris_engine.logic.setup.first_run import check_macos_python

                is_valid, message = check_macos_python()
                assert is_valid is True
                assert message == ""

    def test_check_macos_python_old_version(self, monkeypatch):
        """Test check fails with Python < 3.10."""
        with patch("platform.system", return_value="Darwin"):
            with patch("subprocess.run") as mock_run:

                def run_side_effect(*args, **kwargs):
                    cmd = args[0]
                    if cmd[0] == "which":
                        return Mock(returncode=0, stdout="/opt/homebrew/bin/python3\n")
                    elif "version_info" in str(cmd):
                        return Mock(returncode=0, stdout="3.9\n")
                    return Mock(returncode=0)

                mock_run.side_effect = run_side_effect

                from ciris_engine.logic.setup.first_run import check_macos_python

                is_valid, message = check_macos_python()
                assert is_valid is False
                assert "Python 3.9 detected" in message
                assert "3.10+" in message


class TestInteractiveDetection:
    """Tests for interactive environment detection."""

    def test_is_interactive_with_tty(self, monkeypatch):
        """Test interactive detection when TTY available."""
        # Clear all non-interactive indicators
        monkeypatch.delenv("CI", raising=False)
        monkeypatch.delenv("CONTINUOUS_INTEGRATION", raising=False)
        monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
        monkeypatch.delenv("GITLAB_CI", raising=False)
        monkeypatch.delenv("CIRCLECI", raising=False)
        monkeypatch.delenv("DOCKER", raising=False)
        monkeypatch.delenv("INVOCATION_ID", raising=False)

        # Mock sys.stdin.isatty() and sys.stdout.isatty() to return True
        with patch("sys.stdin.isatty", return_value=True):
            with patch("sys.stdout.isatty", return_value=True):
                with patch("os.path.exists", return_value=False):  # No /.dockerenv
                    from ciris_engine.logic.setup.first_run import is_interactive_environment

                    assert is_interactive_environment() is True

    def test_is_not_interactive_ci_environment(self, monkeypatch):
        """Test non-interactive detection in CI environment."""
        monkeypatch.setenv("CI", "true")

        from ciris_engine.logic.setup.first_run import is_interactive_environment

        assert is_interactive_environment() is False

    def test_is_not_interactive_docker(self, monkeypatch):
        """Test non-interactive detection in Docker."""
        monkeypatch.delenv("CI", raising=False)
        monkeypatch.setenv("DOCKER", "true")

        from ciris_engine.logic.setup.first_run import is_interactive_environment

        assert is_interactive_environment() is False

    def test_is_not_interactive_dockerenv_file(self, monkeypatch):
        """Test non-interactive detection via /.dockerenv file."""
        monkeypatch.delenv("CI", raising=False)
        monkeypatch.delenv("DOCKER", raising=False)

        with patch("os.path.exists") as mock_exists:
            # Return True only for /.dockerenv
            mock_exists.side_effect = lambda path: path == "/.dockerenv"

            from ciris_engine.logic.setup.first_run import is_interactive_environment

            assert is_interactive_environment() is False

    def test_is_not_interactive_systemd(self, monkeypatch):
        """Test non-interactive detection in systemd service."""
        monkeypatch.delenv("CI", raising=False)
        monkeypatch.delenv("DOCKER", raising=False)
        monkeypatch.setenv("INVOCATION_ID", "abc123")

        from ciris_engine.logic.setup.first_run import is_interactive_environment

        assert is_interactive_environment() is False

    def test_is_not_interactive_no_tty(self, monkeypatch):
        """Test non-interactive detection when no TTY."""
        monkeypatch.delenv("CI", raising=False)
        monkeypatch.delenv("DOCKER", raising=False)
        monkeypatch.delenv("INVOCATION_ID", raising=False)

        with patch("sys.stdin.isatty", return_value=False):
            with patch("sys.stdout.isatty", return_value=True):
                with patch("os.path.exists", return_value=False):
                    from ciris_engine.logic.setup.first_run import is_interactive_environment

                    assert is_interactive_environment() is False


class TestConfigPaths:
    """Tests for config path detection."""

    def test_get_config_paths_priority(self, tmp_path, monkeypatch):
        """Test config paths returned in correct priority order (development mode)."""
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.chdir(tmp_path)

        # Create .git directory to simulate development mode
        git_dir = tmp_path / ".git"
        git_dir.mkdir()

        from ciris_engine.logic.setup.first_run import get_config_paths

        paths = get_config_paths()

        # Should be: cwd/.env, ~/ciris/.env, possibly /etc/ciris/.env
        assert paths[0].name == ".env"
        assert paths[0] == tmp_path / ".env"  # Current directory

        assert paths[1].parts[-2:] == ("ciris", ".env")

    def test_get_config_paths_installed_mode(self, tmp_path, monkeypatch):
        """Test config paths in installed mode (no git repo)."""
        monkeypatch.setenv("HOME", str(tmp_path))
        work_dir = tmp_path / "work"
        work_dir.mkdir()
        monkeypatch.chdir(work_dir)

        from ciris_engine.logic.setup.first_run import get_config_paths

        paths = get_config_paths()

        # Should NOT include current directory - only user and system paths
        assert all(p != work_dir / ".env" for p in paths)
        assert paths[0].parts[-2:] == ("ciris", ".env")

    def test_get_default_config_path_git_repo(self, tmp_path, monkeypatch):
        """Test default path is cwd/.env in git repo."""
        monkeypatch.chdir(tmp_path)
        git_dir = tmp_path / ".git"
        git_dir.mkdir()

        from ciris_engine.logic.setup.first_run import get_default_config_path

        path = get_default_config_path()
        assert path == tmp_path / ".env"

    def test_get_default_config_path_user_install(self, tmp_path, monkeypatch):
        """Test default path is ~/ciris/.env for user install."""
        monkeypatch.setenv("HOME", str(tmp_path))
        work_dir = tmp_path / "some" / "other" / "dir"
        work_dir.mkdir(parents=True)
        monkeypatch.chdir(work_dir)

        from ciris_engine.logic.setup.first_run import get_default_config_path

        path = get_default_config_path()
        assert path == tmp_path / "ciris" / ".env"


class TestSetupWizard:
    """Tests for setup wizard functionality."""

    def test_generate_encryption_key(self):
        """Test encryption key generation."""
        from ciris_engine.logic.setup.wizard import generate_encryption_key

        key1 = generate_encryption_key()
        key2 = generate_encryption_key()

        # Keys should be unique
        assert key1 != key2

        # Keys should be base64-encoded 32-byte values
        decoded = base64.b64decode(key1)
        assert len(decoded) == 32

    def test_create_env_file_openai(self, tmp_path):
        """Test .env file creation for OpenAI provider."""
        from ciris_engine.logic.setup.wizard import create_env_file

        env_file = tmp_path / ".env"

        create_env_file(
            save_path=env_file,
            llm_provider="openai",
            llm_api_key="sk-test123",
            llm_base_url="",
            llm_model="",
        )

        assert env_file.exists()
        content = env_file.read_text()
        assert 'OPENAI_API_KEY="sk-test123"' in content
        assert "SECRETS_MASTER_KEY=" in content
        assert "TELEMETRY_ENCRYPTION_KEY=" in content
        assert 'CIRIS_CONFIGURED="true"' in content

        # Verify encryption keys are different
        lines = content.split("\n")
        secrets_key = [l for l in lines if l.startswith("SECRETS_MASTER_KEY=")][0]
        telemetry_key = [l for l in lines if l.startswith("TELEMETRY_ENCRYPTION_KEY=")][0]
        assert secrets_key != telemetry_key

    def test_create_env_file_local_llm(self, tmp_path):
        """Test .env file creation for local LLM provider."""
        from ciris_engine.logic.setup.wizard import create_env_file

        env_file = tmp_path / ".env"

        create_env_file(
            save_path=env_file,
            llm_provider="local",
            llm_api_key="local",
            llm_base_url="http://localhost:11434",
            llm_model="llama3",
        )

        content = env_file.read_text()
        assert 'OPENAI_API_BASE="http://localhost:11434"' in content
        assert 'OPENAI_MODEL="llama3"' in content
        assert 'OPENAI_API_KEY="local"' in content

    def test_create_env_file_creates_parent_dir(self, tmp_path):
        """Test .env file creation creates parent directory if needed."""
        from ciris_engine.logic.setup.wizard import create_env_file

        env_file = tmp_path / "nested" / "dir" / ".env"

        create_env_file(
            save_path=env_file,
            llm_provider="openai",
            llm_api_key="test",
            llm_base_url="",
            llm_model="",
        )

        assert env_file.exists()
        assert env_file.parent.exists()

    def test_wizard_keyboard_interrupt(self, mocker):
        """Test wizard handles Ctrl+C gracefully."""
        from ciris_engine.logic.setup.wizard import run_setup_wizard

        # Mock input to raise KeyboardInterrupt
        mocker.patch("builtins.input", side_effect=KeyboardInterrupt)

        # Should propagate KeyboardInterrupt (main.py catches it)
        with pytest.raises(KeyboardInterrupt):
            run_setup_wizard()

    def test_wizard_overwrite_prompt_decline(self, tmp_path, mocker):
        """Test wizard prompts for overwrite if .env exists and user declines."""
        env_file = tmp_path / ".env"
        env_file.write_text("EXISTING_CONFIG=true")

        # Mock input to decline overwrite
        mocker.patch("builtins.input", return_value="n")

        from ciris_engine.logic.setup.wizard import run_setup_wizard

        result = run_setup_wizard(save_path=env_file)

        # Should return existing path without modification
        assert result == env_file
        assert "EXISTING_CONFIG=true" in env_file.read_text()

    def test_wizard_overwrite_prompt_accept(self, tmp_path, mocker):
        """Test wizard overwrites when user accepts."""
        env_file = tmp_path / ".env"
        env_file.write_text("EXISTING_CONFIG=true")

        # Mock inputs: yes to overwrite, option 1 (OpenAI), skip API key
        inputs = iter(["y", "1", ""])
        mocker.patch("builtins.input", side_effect=inputs)

        from ciris_engine.logic.setup.wizard import run_setup_wizard

        result = run_setup_wizard(save_path=env_file)

        # Should overwrite with new config
        assert result == env_file
        content = env_file.read_text()
        assert "EXISTING_CONFIG=true" not in content
        assert "CIRIS_CONFIGURED=" in content

    def test_prompt_llm_configuration_openai(self, mocker):
        """Test LLM configuration prompts for OpenAI."""
        from ciris_engine.logic.setup.wizard import prompt_llm_configuration

        # Mock inputs: option 1 (OpenAI), API key
        inputs = iter(["1", "sk-test123"])
        mocker.patch("builtins.input", side_effect=inputs)

        provider, api_key, base_url, model = prompt_llm_configuration()

        assert provider == "openai"
        assert api_key == "sk-test123"
        assert base_url == ""
        assert model == ""

    def test_prompt_llm_configuration_local(self, mocker):
        """Test LLM configuration prompts for local LLM."""
        from ciris_engine.logic.setup.wizard import prompt_llm_configuration

        # Mock inputs: option 2 (local), defaults for all prompts
        inputs = iter(["2", "", "", ""])
        mocker.patch("builtins.input", side_effect=inputs)

        provider, api_key, base_url, model = prompt_llm_configuration()

        assert provider == "local"
        assert api_key == "local"
        assert base_url == "http://localhost:11434"
        assert model == "llama3"

    def test_prompt_llm_configuration_other(self, mocker):
        """Test LLM configuration prompts for other provider."""
        from ciris_engine.logic.setup.wizard import prompt_llm_configuration

        # Mock inputs: option 3 (other), custom values
        inputs = iter(["3", "https://api.groq.com/openai/v1", "llama-3.1-70b", "gsk_test123"])
        mocker.patch("builtins.input", side_effect=inputs)

        provider, api_key, base_url, model = prompt_llm_configuration()

        assert provider == "other"
        assert api_key == "gsk_test123"
        assert base_url == "https://api.groq.com/openai/v1"
        assert model == "llama-3.1-70b"
