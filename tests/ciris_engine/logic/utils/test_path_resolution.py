"""Unit tests for CIRIS path resolution utility."""

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from ciris_engine.logic.utils.path_resolution import (
    _sanitize_env_value,
    _validate_env_var_name,
    find_template_file,
    get_ciris_home,
    get_config_dir,
    get_data_dir,
    get_logs_dir,
    get_package_root,
    get_template_directory,
    is_development_mode,
    sync_env_var,
    validate_path_safety,
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


class TestValidatePathSafety:
    """Test path safety validation."""

    def test_accepts_valid_paths(self, tmp_path):
        """Should accept normal paths in non-system directories."""
        valid_path = tmp_path / "ciris" / "data"
        result = validate_path_safety(valid_path, "test")
        assert result == valid_path.resolve()

    def test_accepts_home_directory_paths(self):
        """Should accept paths under home directory."""
        home_path = Path.home() / "ciris" / "config"
        result = validate_path_safety(home_path, "test")
        assert result == home_path.resolve()

    def test_rejects_etc_paths(self):
        """Should reject paths in /etc."""
        with pytest.raises(ValueError, match="forbidden system directory"):
            validate_path_safety(Path("/etc/ciris/config"), "test")

    def test_rejects_bin_paths(self):
        """Should reject paths in /bin."""
        with pytest.raises(ValueError, match="forbidden system directory"):
            validate_path_safety(Path("/bin/ciris"), "test")

    def test_rejects_usr_bin_paths(self):
        """Should reject paths in /usr/bin."""
        with pytest.raises(ValueError, match="forbidden system directory"):
            validate_path_safety(Path("/usr/bin/evil"), "test")

    def test_rejects_root_paths(self):
        """Should reject paths in /root."""
        with pytest.raises(ValueError, match="forbidden system directory"):
            validate_path_safety(Path("/root/.ciris"), "test")

    def test_null_bytes_rejected_by_system(self):
        """Null bytes are rejected at the system level (Path.resolve)."""
        # Note: Python's pathlib.Path.resolve() raises ValueError for null bytes
        # before our custom validation runs, which is the desired behavior
        # Error message varies: "embedded null byte" or "embedded null character"
        with pytest.raises(ValueError, match="embedded null"):
            validate_path_safety(Path("/tmp/safe\x00/attack"), "test")

    def test_resolves_relative_paths(self, tmp_path, monkeypatch):
        """Should resolve relative paths to absolute."""
        monkeypatch.chdir(tmp_path)
        relative_path = Path("./data")
        result = validate_path_safety(relative_path, "test")
        assert result.is_absolute()
        assert result == (tmp_path / "data").resolve()

    def test_context_appears_in_error_message(self):
        """Error messages should include context parameter."""
        with pytest.raises(ValueError, match="CIRIS_HOME"):
            validate_path_safety(Path("/etc/passwd"), "CIRIS_HOME")


class TestGetCirisHomeWithInvalidPath:
    """Test CIRIS home with invalid CIRIS_HOME env var."""

    def test_ignores_forbidden_ciris_home(self, tmp_path, monkeypatch):
        """Should ignore CIRIS_HOME pointing to forbidden directory."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("CIRIS_HOME", "/etc/ciris")
        # Should fall back to default, not use /etc/ciris
        result = get_ciris_home()
        assert "/etc" not in str(result)
        # Should fall back to ~/ciris (not in dev mode)
        assert result == Path.home() / "ciris"

    def test_null_byte_in_env_rejected_by_os(self, tmp_path, monkeypatch):
        """Null bytes in environment variables are rejected by the OS."""
        # Note: The OS rejects null bytes in environment variable values,
        # so this attack vector is already blocked at the system level
        # Error message varies: "embedded null byte" or "embedded null character"
        monkeypatch.chdir(tmp_path)
        with pytest.raises(ValueError, match="embedded null"):
            monkeypatch.setenv("CIRIS_HOME", f"{tmp_path}/safe\x00/evil")


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


class TestSanitizeEnvValue:
    """Test environment value sanitization for .env file security."""

    def test_sanitize_removes_newlines(self):
        """Newlines should be removed to prevent injection."""
        assert _sanitize_env_value("hello\nworld") == "helloworld"
        assert _sanitize_env_value("line1\nline2\nline3") == "line1line2line3"

    def test_sanitize_removes_carriage_returns(self):
        """Carriage returns should be removed."""
        assert _sanitize_env_value("hello\rworld") == "helloworld"
        assert _sanitize_env_value("line1\r\nline2") == "line1line2"

    def test_sanitize_escapes_double_quotes(self):
        """Double quotes should be escaped."""
        assert _sanitize_env_value('say "hello"') == 'say \\"hello\\"'
        assert _sanitize_env_value('"quoted"') == '\\"quoted\\"'

    def test_sanitize_handles_empty_string(self):
        """Empty string should remain empty."""
        assert _sanitize_env_value("") == ""

    def test_sanitize_preserves_safe_characters(self):
        """Safe characters should be preserved."""
        safe = "abcXYZ123-_.!@#$%^&*()+=[]{}|;:',<>/?"
        result = _sanitize_env_value(safe)
        # Only double quotes would be escaped
        assert result == safe

    def test_sanitize_injection_attempt(self):
        """Test against actual injection attempt."""
        # Attempt to inject a new variable
        malicious = 'value"\nMALICIOUS_VAR="evil'
        result = _sanitize_env_value(malicious)
        assert "\n" not in result
        assert result == 'value\\"MALICIOUS_VAR=\\"evil'


class TestValidateEnvVarName:
    """Test environment variable name validation."""

    def test_valid_simple_name(self):
        """Simple alphanumeric names should be valid."""
        assert _validate_env_var_name("MY_VAR") is True
        assert _validate_env_var_name("CIRIS_HOME") is True
        assert _validate_env_var_name("var123") is True

    def test_valid_starts_with_underscore(self):
        """Names starting with underscore should be valid."""
        assert _validate_env_var_name("_PRIVATE") is True
        assert _validate_env_var_name("__dunder__") is True

    def test_invalid_starts_with_number(self):
        """Names starting with number should be invalid."""
        assert _validate_env_var_name("123VAR") is False
        assert _validate_env_var_name("1") is False

    def test_invalid_contains_special_chars(self):
        """Names with special characters should be invalid."""
        assert _validate_env_var_name("MY-VAR") is False
        assert _validate_env_var_name("MY.VAR") is False
        assert _validate_env_var_name("MY VAR") is False
        assert _validate_env_var_name("MY=VAR") is False

    def test_invalid_empty_name(self):
        """Empty name should be invalid."""
        assert _validate_env_var_name("") is False

    def test_injection_via_var_name(self):
        """Injection attempts via var name should be rejected."""
        assert _validate_env_var_name("VAR\nEVIL=bad") is False
        assert _validate_env_var_name("VAR;echo bad") is False
        assert _validate_env_var_name("$(whoami)") is False


class TestSyncEnvVarSecurity:
    """Test sync_env_var security measures."""

    def test_rejects_invalid_var_name(self, monkeypatch):
        """Should raise ValueError for invalid var names."""
        with pytest.raises(ValueError, match="Invalid environment variable name"):
            sync_env_var("INVALID-NAME", "value", persist_to_file=False)

    def test_rejects_injection_in_var_name(self, monkeypatch):
        """Should reject injection attempts in var name."""
        with pytest.raises(ValueError):
            sync_env_var("VAR\nEVIL=x", "value", persist_to_file=False)

    def test_accepts_valid_var_name(self, monkeypatch):
        """Should accept valid var names."""
        # Just test that it doesn't raise - actual env update happens
        result = sync_env_var("VALID_VAR_123", "test_value", persist_to_file=False)
        assert result is True
        assert os.environ.get("VALID_VAR_123") == "test_value"

    def test_sanitizes_value_in_env_file(self, tmp_path, monkeypatch):
        """Values written to .env file should be sanitized."""
        # Create a mock .env file
        env_file = tmp_path / ".env"
        env_file.write_text("EXISTING=value\n")

        # Patch to use our test .env file
        monkeypatch.setattr("ciris_engine.logic.utils.path_resolution.get_env_file_path", lambda: env_file)
        # Patch allowlist check to allow tmp_path for testing
        monkeypatch.setattr("ciris_engine.logic.utils.path_resolution._is_path_in_allowed_env_dirs", lambda p: True)

        # Try to inject via value - attacker tries to close quotes, add newline, set new var
        sync_env_var("TEST_VAR", 'value"\nINJECTED=evil', persist_to_file=True)

        # Read back and verify no injection occurred
        content = env_file.read_text()
        lines = content.strip().split("\n")

        # Should only have 2 lines (original + new), not 3
        # The newline in the value should have been stripped
        assert len(lines) == 2, f"Expected 2 lines, got {len(lines)}: {lines}"

        # Verify the structure - only 2 variable assignments
        # INJECTED should be inside TEST_VAR's value, not a separate var
        assert "TEST_VAR=" in content
        assert "EXISTING=" in content

        # The key security check: INJECTED should NOT be at the start of a line
        # (which would make it its own variable)
        for line in lines:
            assert not line.startswith("INJECTED="), "Injection attack succeeded!"

        # The embedded quote should be escaped
        assert '\\"' in content
