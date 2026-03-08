"""Tests for _sanitize_for_log helper functions across multiple route modules.

Each module has its own copy of _sanitize_for_log, so we test each to ensure coverage.
"""

import pytest


class TestMemorySanitizeForLog:
    """Tests for memory.py _sanitize_for_log."""

    def test_returns_none_placeholder(self):
        """Should return <none> for None input."""
        from ciris_engine.logic.adapters.api.routes.memory import _sanitize_for_log

        result = _sanitize_for_log(None)
        assert result == "<none>"

    def test_removes_control_characters(self):
        """Should remove control characters."""
        from ciris_engine.logic.adapters.api.routes.memory import _sanitize_for_log

        result = _sanitize_for_log("hello\nworld\r\ttab\x00\x7f")
        assert result == "helloworldtab"

    def test_truncates_long_strings(self):
        """Should truncate long strings."""
        from ciris_engine.logic.adapters.api.routes.memory import _sanitize_for_log

        result = _sanitize_for_log("a" * 100, max_length=64)
        assert len(result) == 67  # 64 + "..."
        assert result.endswith("...")

    def test_preserves_normal_strings(self):
        """Should preserve normal strings under max_length."""
        from ciris_engine.logic.adapters.api.routes.memory import _sanitize_for_log

        result = _sanitize_for_log("normal text")
        assert result == "normal text"


class TestAdaptersSanitizeForLog:
    """Tests for adapters.py _sanitize_for_log."""

    def test_returns_none_placeholder(self):
        """Should return <none> for None input."""
        from ciris_engine.logic.adapters.api.routes.system.adapters import _sanitize_for_log

        result = _sanitize_for_log(None)
        assert result == "<none>"

    def test_removes_control_characters(self):
        """Should remove control characters."""
        from ciris_engine.logic.adapters.api.routes.system.adapters import _sanitize_for_log

        result = _sanitize_for_log("hello\x00\x1f\x7f\x9fworld")
        assert result == "helloworld"

    def test_truncates_long_strings(self):
        """Should truncate long strings."""
        from ciris_engine.logic.adapters.api.routes.system.adapters import _sanitize_for_log

        result = _sanitize_for_log("b" * 100, max_length=64)
        assert len(result) == 67
        assert result.endswith("...")

    def test_preserves_normal_strings(self):
        """Should preserve normal strings."""
        from ciris_engine.logic.adapters.api.routes.system.adapters import _sanitize_for_log

        result = _sanitize_for_log("adapter name")
        assert result == "adapter name"


class TestUsersSanitizeForLog:
    """Tests for users.py _sanitize_for_log."""

    def test_returns_none_placeholder(self):
        """Should return <none> for None input."""
        from ciris_engine.logic.adapters.api.routes.users import _sanitize_for_log

        result = _sanitize_for_log(None)
        assert result == "<none>"

    def test_removes_control_characters(self):
        """Should remove control characters."""
        from ciris_engine.logic.adapters.api.routes.users import _sanitize_for_log

        result = _sanitize_for_log("user\n\rid\t\x00")
        assert result == "userid"

    def test_truncates_long_strings(self):
        """Should truncate long strings."""
        from ciris_engine.logic.adapters.api.routes.users import _sanitize_for_log

        result = _sanitize_for_log("c" * 100, max_length=64)
        assert len(result) == 67
        assert result.endswith("...")

    def test_preserves_normal_strings(self):
        """Should preserve normal strings."""
        from ciris_engine.logic.adapters.api.routes.users import _sanitize_for_log

        result = _sanitize_for_log("user@example.com")
        assert result == "user@example.com"


class TestToolsSanitizeForLog:
    """Tests for tools.py _sanitize_for_log."""

    def test_returns_none_placeholder(self):
        """Should return <none> for None input."""
        from ciris_engine.logic.adapters.api.routes.tools import _sanitize_for_log

        result = _sanitize_for_log(None)
        assert result == "<none>"

    def test_removes_control_characters(self):
        """Should remove control characters."""
        from ciris_engine.logic.adapters.api.routes.tools import _sanitize_for_log

        result = _sanitize_for_log("tool\x01\x02\x03name")
        assert result == "toolname"

    def test_truncates_long_strings(self):
        """Should truncate long strings."""
        from ciris_engine.logic.adapters.api.routes.tools import _sanitize_for_log

        result = _sanitize_for_log("d" * 100, max_length=64)
        assert len(result) == 67
        assert result.endswith("...")

    def test_preserves_normal_strings(self):
        """Should preserve normal strings."""
        from ciris_engine.logic.adapters.api.routes.tools import _sanitize_for_log

        result = _sanitize_for_log("my_tool_name")
        assert result == "my_tool_name"


class TestWASanitizeForLog:
    """Tests for wa.py sanitize_for_log (different implementation)."""

    def test_replaces_newlines_with_spaces(self):
        """Should replace newlines with spaces."""
        from ciris_engine.logic.adapters.api.routes.wa import sanitize_for_log

        result = sanitize_for_log("hello\nworld")
        assert result == "hello world"

    def test_replaces_carriage_returns_with_spaces(self):
        """Should replace carriage returns with spaces."""
        from ciris_engine.logic.adapters.api.routes.wa import sanitize_for_log

        result = sanitize_for_log("hello\rworld")
        assert result == "hello world"

    def test_replaces_tabs_with_spaces(self):
        """Should replace tabs with spaces."""
        from ciris_engine.logic.adapters.api.routes.wa import sanitize_for_log

        result = sanitize_for_log("hello\tworld")
        assert result == "hello world"

    def test_replaces_non_printable_with_spaces(self):
        """Should replace non-printable characters with spaces."""
        from ciris_engine.logic.adapters.api.routes.wa import sanitize_for_log

        result = sanitize_for_log("hello\x00world")
        assert result == "hello world"

    def test_preserves_printable_strings(self):
        """Should preserve normal printable strings."""
        from ciris_engine.logic.adapters.api.routes.wa import sanitize_for_log

        result = sanitize_for_log("deferral-123")
        assert result == "deferral-123"
