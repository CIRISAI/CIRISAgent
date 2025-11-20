"""Unit tests for CIRIS path resolution utility."""

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from ciris_engine.logic.utils.path_resolution import (
    find_template_file,
    get_ciris_home,
    get_config_dir,
    get_data_dir,
    get_logs_dir,
    get_package_root,
    get_template_directory,
    is_development_mode,
)


class TestIsDevelopmentMode:
    """Test development mode detection."""

    def test_detects_git_repo(self, tmp_path, monkeypatch):
        """Test detection when .git directory exists."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".git").mkdir()
        assert is_development_mode() is True

    def test_not_git_repo(self, tmp_path, monkeypatch):
        """Test detection when no .git directory."""
        monkeypatch.chdir(tmp_path)
        assert is_development_mode() is False


class TestGetCirisHome:
    """Test CIRIS home directory resolution."""

    def test_development_mode_uses_cwd(self, tmp_path, monkeypatch):
        """Development mode should use current directory."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".git").mkdir()
        assert get_ciris_home() == tmp_path

    def test_respects_ciris_home_env(self, tmp_path, monkeypatch):
        """Should use CIRIS_HOME environment variable if set."""
        custom_home = tmp_path / "custom_ciris"
        custom_home.mkdir()
        monkeypatch.setenv("CIRIS_HOME", str(custom_home))
        # Ensure not in git repo
        monkeypatch.chdir(tmp_path)
        assert get_ciris_home() == custom_home

    def test_default_user_home(self, tmp_path, monkeypatch):
        """Should default to ~/ciris/ in installed mode."""
        monkeypatch.chdir(tmp_path)
        # No .git, no CIRIS_HOME
        monkeypatch.delenv("CIRIS_HOME", raising=False)
        expected = Path.home() / "ciris"
        assert get_ciris_home() == expected

    def test_expands_tilde_in_env(self, tmp_path, monkeypatch):
        """Should expand ~ in CIRIS_HOME environment variable."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("CIRIS_HOME", "~/my_ciris")
        result = get_ciris_home()
        assert "~" not in str(result)
        assert result == Path.home() / "my_ciris"


class TestDirectoryHelpers:
    """Test directory helper functions."""

    def test_get_data_dir(self, tmp_path, monkeypatch):
        """get_data_dir should return CIRIS_HOME/data/."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".git").mkdir()
        assert get_data_dir() == tmp_path / "data"

    def test_get_logs_dir(self, tmp_path, monkeypatch):
        """get_logs_dir should return CIRIS_HOME/logs/."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".git").mkdir()
        assert get_logs_dir() == tmp_path / "logs"

    def test_get_config_dir(self, tmp_path, monkeypatch):
        """get_config_dir should return CIRIS_HOME/config/."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".git").mkdir()
        assert get_config_dir() == tmp_path / "config"


class TestGetPackageRoot:
    """Test package root detection."""

    def test_returns_ciris_engine_path(self):
        """Should return path to ciris_engine package."""
        result = get_package_root()
        assert result.name == "ciris_engine"
        assert result.is_dir()
        assert (result / "__init__.py").exists()


class TestFindTemplateFile:
    """Test template file search functionality."""

    def test_finds_in_development_mode(self, tmp_path, monkeypatch):
        """Should find template in CWD/ciris_templates/ in dev mode."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".git").mkdir()
        templates_dir = tmp_path / "ciris_templates"
        templates_dir.mkdir()
        template_file = templates_dir / "test.yaml"
        template_file.write_text("name: test")

        result = find_template_file("test")
        assert result == template_file

    def test_finds_with_yaml_extension(self, tmp_path, monkeypatch):
        """Should find template whether .yaml extension is provided or not."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".git").mkdir()
        templates_dir = tmp_path / "ciris_templates"
        templates_dir.mkdir()
        template_file = templates_dir / "test.yaml"
        template_file.write_text("name: test")

        # Both should work
        assert find_template_file("test") == template_file
        assert find_template_file("test.yaml") == template_file

    def test_finds_in_user_home(self, tmp_path, monkeypatch):
        """Should find template in ~/ciris/ciris_templates/."""
        monkeypatch.chdir(tmp_path)
        # Not in dev mode
        user_ciris = Path.home() / "ciris"
        templates_dir = user_ciris / "ciris_templates"
        templates_dir.mkdir(parents=True, exist_ok=True)
        template_file = templates_dir / "user_template.yaml"
        template_file.write_text("name: user")

        try:
            result = find_template_file("user_template")
            assert result == template_file
        finally:
            # Cleanup
            template_file.unlink(missing_ok=True)

    def test_finds_in_package(self):
        """Should find bundled templates in package."""
        # This tests against the actual installed/development package
        result = find_template_file("default")
        assert result is not None
        assert result.name == "default.yaml"
        assert result.exists()

    def test_returns_none_if_not_found(self, tmp_path, monkeypatch):
        """Should return None if template not found anywhere."""
        monkeypatch.chdir(tmp_path)
        result = find_template_file("nonexistent_template_xyz")
        assert result is None

    def test_search_order_priority(self, tmp_path, monkeypatch):
        """Development mode CWD should take priority over other locations."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".git").mkdir()

        # Create template in CWD (highest priority)
        cwd_templates = tmp_path / "ciris_templates"
        cwd_templates.mkdir()
        cwd_template = cwd_templates / "priority_test.yaml"
        cwd_template.write_text("source: cwd")

        # Create template in user home (lower priority)
        user_ciris = Path.home() / "ciris" / "ciris_templates"
        user_ciris.mkdir(parents=True, exist_ok=True)
        user_template = user_ciris / "priority_test.yaml"
        user_template.write_text("source: user")

        try:
            result = find_template_file("priority_test")
            # Should find CWD version (dev mode priority)
            assert result == cwd_template
            assert result.read_text() == "source: cwd"
        finally:
            user_template.unlink(missing_ok=True)

    def test_ciris_home_overrides_user_home(self, tmp_path, monkeypatch):
        """CIRIS_HOME should override ~/ciris/ location."""
        monkeypatch.chdir(tmp_path)
        # Not in dev mode
        custom_home = tmp_path / "custom"
        custom_home.mkdir()
        monkeypatch.setenv("CIRIS_HOME", str(custom_home))

        # Create template in CIRIS_HOME location
        ciris_home_templates = custom_home / "ciris_templates"
        ciris_home_templates.mkdir()
        ciris_home_template = ciris_home_templates / "custom_test.yaml"
        ciris_home_template.write_text("source: ciris_home")

        # Create template in user home (should not be found)
        user_templates = Path.home() / "ciris" / "ciris_templates"
        user_templates.mkdir(parents=True, exist_ok=True)
        user_template = user_templates / "custom_test.yaml"
        user_template.write_text("source: user")

        try:
            result = find_template_file("custom_test")
            # Should find CIRIS_HOME version
            assert result == ciris_home_template
            assert result.read_text() == "source: ciris_home"
        finally:
            user_template.unlink(missing_ok=True)


class TestGetTemplateDirectory:
    """Test template directory resolution."""

    def test_returns_cwd_in_dev_mode(self, tmp_path, monkeypatch):
        """Should return CWD/ciris_templates/ in development mode."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".git").mkdir()
        templates_dir = tmp_path / "ciris_templates"
        templates_dir.mkdir()

        result = get_template_directory()
        assert result == templates_dir

    def test_returns_ciris_home_when_set(self, tmp_path, monkeypatch):
        """Should return CIRIS_HOME/ciris_templates/ when CIRIS_HOME is set."""
        monkeypatch.chdir(tmp_path)
        custom_home = tmp_path / "custom_ciris"
        templates_dir = custom_home / "ciris_templates"
        templates_dir.mkdir(parents=True)
        monkeypatch.setenv("CIRIS_HOME", str(custom_home))

        result = get_template_directory()
        assert result == templates_dir

    def test_returns_package_root_as_fallback(self, tmp_path, monkeypatch):
        """Should return package templates as final fallback."""
        monkeypatch.chdir(tmp_path)
        # Not in dev mode, no CIRIS_HOME
        monkeypatch.delenv("CIRIS_HOME", raising=False)

        result = get_template_directory()
        # Should be either user home templates (if exists) or package location
        user_templates = Path.home() / "ciris" / "ciris_templates"
        package_templates = get_package_root() / "ciris_templates"
        assert result in (user_templates, package_templates)


class TestIntegration:
    """Integration tests for path resolution."""

    def test_paths_consistent_in_dev_mode(self, tmp_path, monkeypatch):
        """All paths should be consistent in development mode."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".git").mkdir()

        home = get_ciris_home()
        assert home == tmp_path
        assert get_data_dir() == tmp_path / "data"
        assert get_logs_dir() == tmp_path / "logs"
        assert get_config_dir() == tmp_path / "config"

    def test_paths_consistent_in_installed_mode(self, tmp_path, monkeypatch):
        """All paths should be consistent in installed mode."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("CIRIS_HOME", raising=False)

        expected_home = Path.home() / "ciris"
        assert get_ciris_home() == expected_home
        assert get_data_dir() == expected_home / "data"
        assert get_logs_dir() == expected_home / "logs"
        assert get_config_dir() == expected_home / "config"

    def test_ciris_home_env_affects_all_paths(self, tmp_path, monkeypatch):
        """Setting CIRIS_HOME should affect all derived paths."""
        monkeypatch.chdir(tmp_path)
        custom_home = tmp_path / "my_ciris_installation"
        custom_home.mkdir()
        monkeypatch.setenv("CIRIS_HOME", str(custom_home))

        assert get_ciris_home() == custom_home
        assert get_data_dir() == custom_home / "data"
        assert get_logs_dir() == custom_home / "logs"
        assert get_config_dir() == custom_home / "config"
