"""Unit tests for skill_import.py path resolution security.

Tests the _resolve_to_allowed_path function to ensure:
1. Relative paths resolve against cwd, not home
2. Path containment uses proper path checking, not string prefix
3. Path traversal is blocked
4. Sensitive paths are blocked
"""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from ciris_engine.logic.adapters.api.routes.system.skill_import import (
    _check_path_traversal,
    _check_sensitive_paths,
    _path_matches_base_prefix,
    _resolve_to_allowed_path,
    _validate_local_path,
    _validate_path_string,
)


class TestPathMatchesBasePrefix:
    """Tests for _path_matches_base_prefix helper function."""

    def test_matches_exact_base_path(self) -> None:
        """Should match when path equals base exactly."""
        matches, relative = _path_matches_base_prefix(["home", "user"], ["/", "home", "user"])
        assert matches is True
        assert relative == []

    def test_matches_path_under_base(self) -> None:
        """Should match when path is under base and return relative components."""
        matches, relative = _path_matches_base_prefix(["home", "user", "projects", "skill"], ["/", "home", "user"])
        assert matches is True
        assert relative == ["projects", "skill"]

    def test_no_match_when_path_shorter_than_base(self) -> None:
        """Should not match when path has fewer components than base."""
        matches, relative = _path_matches_base_prefix(["home"], ["/", "home", "user"])
        assert matches is False
        assert relative == []

    def test_no_match_when_components_differ(self) -> None:
        """Should not match when path components don't match base."""
        matches, relative = _path_matches_base_prefix(["home", "other_user", "projects"], ["/", "home", "user"])
        assert matches is False
        assert relative == []

    def test_no_match_with_similar_prefix(self) -> None:
        """Should not match /tmp2 against /tmp base."""
        matches, relative = _path_matches_base_prefix(["tmp2", "foo"], ["/", "tmp"])
        assert matches is False
        assert relative == []

    def test_handles_non_root_base_parts(self) -> None:
        """Should handle base paths that don't start with /."""
        matches, relative = _path_matches_base_prefix(["projects", "skill"], ["projects"])
        assert matches is True
        assert relative == ["skill"]


class TestValidatePathString:
    """Tests for _validate_path_string."""

    def test_empty_path_rejected(self) -> None:
        with pytest.raises(ValueError, match="non-empty string"):
            _validate_path_string("")

    def test_null_byte_rejected(self) -> None:
        with pytest.raises(ValueError, match="null bytes"):
            _validate_path_string("/tmp/test\x00file")

    def test_long_path_rejected(self) -> None:
        with pytest.raises(ValueError, match="maximum length"):
            _validate_path_string("a" * 5000)

    def test_valid_path_accepted(self) -> None:
        # Should not raise
        _validate_path_string("/tmp/valid/path")
        _validate_path_string("relative/path")
        _validate_path_string("~/home/path")


class TestCheckPathTraversal:
    """Tests for _check_path_traversal."""

    def test_double_dot_rejected(self) -> None:
        with pytest.raises(ValueError, match="Path traversal"):
            _check_path_traversal("/tmp/../etc/passwd")

    def test_triple_dot_rejected(self) -> None:
        with pytest.raises(ValueError, match="Path traversal"):
            _check_path_traversal("/tmp/.../etc")

    def test_normal_path_accepted(self) -> None:
        # Should not raise
        _check_path_traversal("/tmp/normal/path")
        _check_path_traversal("relative/path/here")


class TestCheckSensitivePaths:
    """Tests for _check_sensitive_paths."""

    def test_ssh_blocked(self) -> None:
        with pytest.raises(ValueError, match=".ssh"):
            _check_sensitive_paths("/home/user/.ssh/id_rsa")

    def test_gnupg_blocked(self) -> None:
        with pytest.raises(ValueError, match=".gnupg"):
            _check_sensitive_paths("/home/user/.gnupg/private-keys")

    def test_aws_blocked(self) -> None:
        # Note: "credentials" is also in _SENSITIVE_PATTERNS, so it may match first
        with pytest.raises(ValueError, match="(credentials|.aws)"):
            _check_sensitive_paths("/home/user/.aws/credentials")

    def test_normal_path_accepted(self) -> None:
        # Should not raise
        _check_sensitive_paths("/tmp/skills/my_skill")
        _check_sensitive_paths("~/projects/skill")


class TestResolveToAllowedPath:
    """Tests for _resolve_to_allowed_path - the main security function."""

    def test_tilde_path_resolves_to_home(self) -> None:
        """Paths starting with ~ should resolve under home directory."""
        result = _resolve_to_allowed_path("~/test/path")
        assert result == (Path.home() / "test" / "path").resolve()

    def test_relative_path_resolves_to_cwd(self) -> None:
        """Relative paths should resolve against cwd, NOT home.

        This is the regression test for the bug where relative paths
        were being resolved against the first base in the loop (home).
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a test directory structure
            test_dir = Path(tmpdir) / "skills" / "my_skill"
            test_dir.mkdir(parents=True)

            # Change to the temp directory
            old_cwd = os.getcwd()
            try:
                os.chdir(tmpdir)

                # "skills/my_skill" should resolve to {cwd}/skills/my_skill
                # NOT ~/skills/my_skill
                result = _resolve_to_allowed_path("skills/my_skill")

                # The result should be within the temp directory (cwd), not home
                assert str(result).startswith(
                    tmpdir
                ), f"Relative path resolved to {result}, expected to be under {tmpdir}"
                assert result == test_dir.resolve()
            finally:
                os.chdir(old_cwd)

    def test_absolute_path_prefix_attack_blocked(self) -> None:
        """Paths like /tmp2/foo should NOT match /tmp base.

        This is the regression test for the string-prefix matching bug
        where /tmp2/foo would match /tmp and get rewritten to /tmp/2/foo.
        """
        # /tmp2 is NOT under /tmp, so this should fail
        with pytest.raises(ValueError, match="outside allowed directories"):
            _resolve_to_allowed_path("/tmp2/foo/bar")

    def test_absolute_path_within_tmp_allowed(self) -> None:
        """Legitimate paths within /tmp should work."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # tmpdir is within /tmp (or system temp dir)
            test_file = Path(tmpdir) / "test_skill"
            test_file.mkdir(parents=True, exist_ok=True)

            result = _resolve_to_allowed_path(str(test_file))
            assert result == test_file.resolve()

    def test_absolute_path_within_home_allowed(self) -> None:
        """Legitimate paths within home directory should work."""
        home = Path.home()
        # Test with a hypothetical path under home
        test_path = str(home / "ciris" / "adapters" / "test_skill")

        # This should work as long as home is accessible
        # We can't create the actual directory, so we just verify no exception
        # is raised for a path that would be under home
        result = _resolve_to_allowed_path(test_path)
        assert str(result).startswith(str(home))

    def test_path_outside_all_bases_rejected(self) -> None:
        """Paths outside home, cwd, and tmp should be rejected."""
        with pytest.raises(ValueError, match="outside allowed directories"):
            _resolve_to_allowed_path("/etc/passwd")

        with pytest.raises(ValueError, match="outside allowed directories"):
            _resolve_to_allowed_path("/var/log/syslog")

    def test_symlink_escape_blocked(self) -> None:
        """Symlinks that escape allowed base should be blocked."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a symlink pointing outside the allowed base
            symlink_path = Path(tmpdir) / "escape_link"
            try:
                symlink_path.symlink_to("/etc")
            except OSError:
                pytest.skip("Cannot create symlinks on this system")

            # Trying to access through the symlink should fail
            with pytest.raises(ValueError, match="outside allowed directories"):
                _resolve_to_allowed_path(f"{symlink_path}/passwd")


class TestValidateLocalPath:
    """Integration tests for _validate_local_path (the main entry point)."""

    def test_path_traversal_blocked(self) -> None:
        """Path traversal attempts should be blocked."""
        with pytest.raises(ValueError):
            _validate_local_path("../../../etc/passwd")

    def test_sensitive_path_blocked(self) -> None:
        """Access to sensitive directories should be blocked."""
        with pytest.raises(ValueError, match=".ssh"):
            _validate_local_path("~/.ssh/id_rsa")

    def test_valid_tmp_path(self) -> None:
        """Valid paths in /tmp should work."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "skill.md"
            test_file.touch()

            result = _validate_local_path(str(test_file))
            assert result == test_file.resolve()

    def test_valid_relative_path_in_cwd(self) -> None:
        """Valid relative paths should resolve against cwd."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_dir = Path(tmpdir) / "skills"
            test_dir.mkdir()

            old_cwd = os.getcwd()
            try:
                os.chdir(tmpdir)
                result = _validate_local_path("skills")
                assert result == test_dir.resolve()
            finally:
                os.chdir(old_cwd)


class TestPathContainmentVsStringPrefix:
    """Specific tests for path containment vs string prefix issues."""

    def test_similar_path_names_not_confused(self) -> None:
        """Paths with similar prefixes should not be confused.

        /tmp2/foo should NOT be treated as under /tmp
        /home/user2 should NOT be treated as under /home/user
        """
        # These should all fail because they're outside allowed bases
        invalid_paths = [
            "/tmp2/foo",
            "/tmp_backup/data",
            "/temporary/stuff",  # Doesn't start with /tmp
        ]

        for path in invalid_paths:
            with pytest.raises(ValueError, match="outside allowed directories"):
                _resolve_to_allowed_path(path)

    def test_path_with_base_as_substring_rejected(self) -> None:
        """Ensure /tmpXXX doesn't match /tmp base."""
        with pytest.raises(ValueError, match="outside allowed directories"):
            _resolve_to_allowed_path("/tmpfoo/bar")

    def test_trailing_slash_handling(self) -> None:
        """Paths with trailing slashes should work correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_dir = Path(tmpdir) / "skill_dir"
            test_dir.mkdir()

            # Both with and without trailing slash should work
            result1 = _resolve_to_allowed_path(str(test_dir))
            result2 = _resolve_to_allowed_path(str(test_dir) + "/")

            assert result1 == result2 == test_dir.resolve()
