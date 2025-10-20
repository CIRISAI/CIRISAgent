"""Unit tests for migration_runner helper functions."""

from unittest.mock import MagicMock

import pytest

from ciris_engine.logic.persistence.db.migration_runner import _filter_comment_only_statements, _is_all_comments


class TestIsAllComments:
    """Tests for _is_all_comments()."""

    def test_all_comments(self):
        """Test statement with only comments."""
        stmt = "-- This is a comment\n-- Another comment"
        assert _is_all_comments(stmt) is True

    def test_has_sql(self):
        """Test statement with SQL and comments."""
        stmt = "-- Comment\nCREATE TABLE test;"
        assert _is_all_comments(stmt) is False

    def test_only_sql(self):
        """Test statement with only SQL."""
        stmt = "CREATE TABLE test;"
        assert _is_all_comments(stmt) is False

    def test_empty_lines_and_comments(self):
        """Test statement with empty lines and comments."""
        stmt = "\n-- Comment\n\n-- Another comment\n"
        assert _is_all_comments(stmt) is True

    def test_inline_comment_after_sql(self):
        """Test SQL with inline comment."""
        stmt = "CREATE TABLE test; -- comment"
        assert _is_all_comments(stmt) is False


class TestFilterCommentOnlyStatements:
    """Tests for _filter_comment_only_statements()."""

    def test_filter_mixed_statements(self):
        """Test filtering mix of SQL and comment-only statements."""
        statements = [
            "CREATE TABLE test;",
            "-- Just a comment",
            "INSERT INTO test VALUES (1);",
            "-- Another comment\n-- And another",
            "SELECT * FROM test;",
        ]
        result = _filter_comment_only_statements(statements)
        assert len(result) == 3
        assert result[0] == "CREATE TABLE test;"
        assert result[1] == "INSERT INTO test VALUES (1);"
        assert result[2] == "SELECT * FROM test;"

    def test_filter_all_sql(self):
        """Test filtering when all statements are SQL."""
        statements = [
            "CREATE TABLE test;",
            "INSERT INTO test VALUES (1);",
        ]
        result = _filter_comment_only_statements(statements)
        assert len(result) == 2

    def test_filter_all_comments(self):
        """Test filtering when all statements are comments."""
        statements = [
            "-- Comment 1",
            "-- Comment 2",
        ]
        result = _filter_comment_only_statements(statements)
        assert len(result) == 0

    def test_filter_empty_statements(self):
        """Test filtering empty statements."""
        statements = ["", "CREATE TABLE test;", ""]
        result = _filter_comment_only_statements(statements)
        assert len(result) == 1
        assert result[0] == "CREATE TABLE test;"
