"""
Unit tests for database dialect adapter.

Tests the lightweight SQL translation layer that enables CIRIS to work
with both SQLite and PostgreSQL backends.
"""

import pytest

from ciris_engine.logic.persistence.db.dialect import (
    Dialect,
    DialectAdapter,
    get_adapter,
    init_dialect,
    parse_postgres_url,
)


class TestDialectAdapter:
    """Test DialectAdapter SQL translation functionality."""

    def test_sqlite_initialization_with_path(self):
        """Test SQLite dialect initialization with simple path."""
        adapter = DialectAdapter("data/test.db")
        assert adapter.dialect == Dialect.SQLITE
        assert adapter.db_path == "data/test.db"
        assert adapter.is_sqlite()
        assert not adapter.is_postgresql()

    def test_sqlite_initialization_with_url(self):
        """Test SQLite dialect initialization with URL."""
        adapter = DialectAdapter("sqlite://data/test.db")
        assert adapter.dialect == Dialect.SQLITE
        assert adapter.is_sqlite()

    def test_postgresql_initialization(self):
        """Test PostgreSQL dialect initialization."""
        adapter = DialectAdapter("postgresql://user:pass@localhost:5432/dbname")
        assert adapter.dialect == Dialect.POSTGRESQL
        assert adapter.db_url == "postgresql://user:pass@localhost:5432/dbname"
        assert adapter.is_postgresql()
        assert not adapter.is_sqlite()

    def test_postgres_short_scheme(self):
        """Test PostgreSQL with 'postgres' scheme (no 'ql')."""
        adapter = DialectAdapter("postgres://user:pass@localhost/db")
        assert adapter.dialect == Dialect.POSTGRESQL

    def test_default_to_sqlite(self):
        """Test that unknown schemes default to SQLite."""
        adapter = DialectAdapter("unknown://path")
        assert adapter.dialect == Dialect.SQLITE

    def test_sqlite_placeholder(self):
        """Test SQLite uses ? placeholder."""
        adapter = DialectAdapter("data/test.db")
        assert adapter.placeholder() == "?"

    def test_postgresql_placeholder(self):
        """Test PostgreSQL uses %s placeholder."""
        adapter = DialectAdapter("postgresql://localhost/db")
        assert adapter.placeholder() == "%s"

    def test_sqlite_upsert(self):
        """Test SQLite INSERT OR REPLACE generation."""
        adapter = DialectAdapter("data/test.db")
        sql = adapter.upsert(table="test_table", columns=["id", "name", "value"], conflict_columns=["id"])

        assert "INSERT OR REPLACE INTO test_table" in sql
        assert "(id, name, value)" in sql
        assert "VALUES (?, ?, ?)" in sql
        assert "ON CONFLICT" not in sql  # SQLite doesn't use this

    def test_postgresql_upsert(self):
        """Test PostgreSQL INSERT ... ON CONFLICT generation."""
        adapter = DialectAdapter("postgresql://localhost/db")
        sql = adapter.upsert(table="test_table", columns=["id", "name", "value"], conflict_columns=["id"])

        assert "INSERT INTO test_table" in sql
        assert "(id, name, value)" in sql
        assert "VALUES (%s, %s, %s)" in sql
        assert "ON CONFLICT (id)" in sql
        assert "DO UPDATE SET" in sql
        assert "name = EXCLUDED.name" in sql
        assert "value = EXCLUDED.value" in sql

    def test_postgresql_upsert_custom_update_columns(self):
        """Test PostgreSQL upsert with custom update columns."""
        adapter = DialectAdapter("postgresql://localhost/db")
        sql = adapter.upsert(
            table="test_table",
            columns=["id", "name", "value", "created_at"],
            conflict_columns=["id"],
            update_columns=["name", "value"],  # Don't update created_at
        )

        assert "name = EXCLUDED.name" in sql
        assert "value = EXCLUDED.value" in sql
        assert "created_at = EXCLUDED.created_at" not in sql

    def test_sqlite_json_extract_simple(self):
        """Test SQLite json_extract for simple path."""
        adapter = DialectAdapter("data/test.db")
        result = adapter.json_extract("data", "$.field")

        assert result == "json_extract(data, '$.field')"

    def test_sqlite_json_extract_nested(self):
        """Test SQLite json_extract for nested path."""
        adapter = DialectAdapter("data/test.db")
        result = adapter.json_extract("data", "$.parent.child")

        assert result == "json_extract(data, '$.parent.child')"

    def test_postgresql_json_extract_simple(self):
        """Test PostgreSQL JSONB operator for simple path."""
        adapter = DialectAdapter("postgresql://localhost/db")
        result = adapter.json_extract("data", "$.field")

        assert result == "data->>'field'"

    def test_postgresql_json_extract_nested(self):
        """Test PostgreSQL JSONB operator for nested path."""
        adapter = DialectAdapter("postgresql://localhost/db")
        result = adapter.json_extract("data", "$.parent.child")

        # Should use -> for intermediate, ->> for final
        assert result == "data->'parent'->>'child'"

    def test_postgresql_json_extract_empty_path(self):
        """Test PostgreSQL JSON extract with empty path."""
        adapter = DialectAdapter("postgresql://localhost/db")
        result = adapter.json_extract("data", "$")

        assert result == "data"

    def test_postgresql_json_extract_leading_dots(self):
        """Test PostgreSQL JSON extract handles various formats."""
        adapter = DialectAdapter("postgresql://localhost/db")
        result = adapter.json_extract("data", "$.field")

        assert "->>'field'" in result

    def test_sqlite_pragma_passthrough(self):
        """Test SQLite PRAGMA statements pass through."""
        adapter = DialectAdapter("data/test.db")
        result = adapter.pragma("PRAGMA foreign_keys = ON;")

        assert result == "PRAGMA foreign_keys = ON;"

    def test_postgresql_pragma_ignored(self):
        """Test PostgreSQL ignores PRAGMA statements."""
        adapter = DialectAdapter("postgresql://localhost/db")
        result = adapter.pragma("PRAGMA foreign_keys = ON;")

        assert result is None

    def test_sqlite_multiple_conflict_columns(self):
        """Test SQLite upsert with composite key."""
        adapter = DialectAdapter("data/test.db")
        sql = adapter.upsert(
            table="test_table",
            columns=["id1", "id2", "value"],
            conflict_columns=["id1", "id2"],
        )

        # SQLite doesn't explicitly list conflict columns
        assert "INSERT OR REPLACE INTO test_table" in sql

    def test_postgresql_multiple_conflict_columns(self):
        """Test PostgreSQL upsert with composite key."""
        adapter = DialectAdapter("postgresql://localhost/db")
        sql = adapter.upsert(
            table="test_table",
            columns=["id1", "id2", "value"],
            conflict_columns=["id1", "id2"],
        )

        assert "ON CONFLICT (id1, id2)" in sql
        assert "DO UPDATE SET value = EXCLUDED.value" in sql


class TestGlobalAdapterFunctions:
    """Test global adapter initialization and retrieval."""

    def test_init_dialect_default(self):
        """Test init_dialect with default SQLite."""
        adapter = init_dialect()
        assert adapter.dialect == Dialect.SQLITE
        assert "data/ciris.db" in adapter.db_path

    def test_init_dialect_custom_path(self):
        """Test init_dialect with custom path."""
        adapter = init_dialect("custom/path.db")
        assert adapter.dialect == Dialect.SQLITE
        assert "custom/path.db" in adapter.db_path

    def test_init_dialect_postgresql(self):
        """Test init_dialect with PostgreSQL URL."""
        adapter = init_dialect("postgresql://localhost/testdb")
        assert adapter.dialect == Dialect.POSTGRESQL

    def test_get_adapter_after_init(self):
        """Test get_adapter returns initialized adapter."""
        # Initialize with specific path
        init_adapter = init_dialect("test.db")

        # Get should return same adapter
        get_adapter_result = get_adapter()

        assert get_adapter_result.dialect == init_adapter.dialect
        assert get_adapter_result.db_path == init_adapter.db_path

    def test_get_adapter_auto_initializes(self):
        """Test get_adapter auto-initializes if not set."""
        # Note: This test assumes clean state or is run first
        # In real scenarios, adapter may already be initialized
        adapter = get_adapter()
        assert adapter is not None
        assert isinstance(adapter, DialectAdapter)


class TestDialectEnum:
    """Test Dialect enum."""

    def test_dialect_values(self):
        """Test Dialect enum has expected values."""
        assert Dialect.SQLITE.value == "sqlite"
        assert Dialect.POSTGRESQL.value == "postgresql"

    def test_dialect_string_representation(self):
        """Test Dialect enum string representation."""
        assert str(Dialect.SQLITE) == "Dialect.SQLITE"
        assert str(Dialect.POSTGRESQL) == "Dialect.POSTGRESQL"


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_empty_columns_list(self):
        """Test upsert with empty columns list."""
        adapter = DialectAdapter("data/test.db")
        sql = adapter.upsert(table="test", columns=[], conflict_columns=[])

        # Should still generate valid SQL even if unusual
        assert "INSERT OR REPLACE INTO test" in sql

    def test_json_extract_special_characters(self):
        """Test JSON extract with special field names."""
        adapter = DialectAdapter("postgresql://localhost/db")
        result = adapter.json_extract("data", "$.field-name")

        # Should handle hyphens in field names
        assert "field-name" in result

    def test_multiple_nested_json_levels(self):
        """Test deeply nested JSON paths."""
        adapter = DialectAdapter("postgresql://localhost/db")
        result = adapter.json_extract("data", "$.level1.level2.level3.level4")

        # Should have multiple -> operators
        assert result.count("->") >= 3
        assert "->>" in result  # Final element extracted as text

    def test_sqlite3_scheme_variant(self):
        """Test sqlite3:// URL scheme."""
        adapter = DialectAdapter("sqlite3://path/to/db")
        assert adapter.dialect == Dialect.SQLITE


class TestPostgreSQLURLParsing:
    """Test PostgreSQL URL parsing with special characters in passwords.

    Critical for production deployments where passwords may contain special characters
    that break standard urlparse() functionality.
    """

    def test_parse_postgres_url_simple(self):
        """Test parsing simple PostgreSQL URL."""
        url = "postgresql://user:password@localhost:5432/dbname"
        scheme, user, password, port, host, database, params = parse_postgres_url(url)

        assert scheme == "postgresql"
        assert user == "user"
        assert password == "password"
        assert host == "localhost"
        assert port == 5432
        assert database == "dbname"
        assert params == ""

    def test_parse_postgres_url_with_at_symbol(self):
        """Test parsing PostgreSQL URL with @ in password."""
        # Simulates production case with special chars including @
        url = "postgresql://testuser:p@ss@w0rd@192.168.1.100:5432/testdb"
        scheme, user, password, port, host, database, params = parse_postgres_url(url)

        assert scheme == "postgresql"
        assert user == "testuser"
        assert password == "p@ss@w0rd"
        assert host == "192.168.1.100"
        assert port == 5432
        assert database == "testdb"

    def test_parse_postgres_url_with_url_encoded_password(self):
        """Test parsing PostgreSQL URL with URL-encoded password."""
        # URL-encoded version: p@ss{w}rd[123] → p%40ss%7Bw%7Drd%5B123%5D
        url = "postgresql://user:p%40ss%7Bw%7Drd%5B123%5D@localhost:5432/db"
        scheme, user, password, port, host, database, params = parse_postgres_url(url)

        assert scheme == "postgresql"
        assert user == "user"
        # Should URL-decode the password
        assert password == "p@ss{w}rd[123]"
        assert host == "localhost"
        assert port == 5432
        assert database == "db"

    def test_parse_postgres_url_with_query_params(self):
        """Test parsing PostgreSQL URL with query parameters."""
        url = "postgresql://user:pass@localhost:5432/db?sslmode=require&connect_timeout=10"
        scheme, user, password, port, host, database, params = parse_postgres_url(url)

        assert scheme == "postgresql"
        assert database == "db"
        assert params == "?sslmode=require&connect_timeout=10"

    def test_parse_postgres_url_short_scheme(self):
        """Test parsing with 'postgres' (not 'postgresql') scheme."""
        url = "postgres://user:pass@host:5432/db"
        scheme, user, password, port, host, database, params = parse_postgres_url(url)

        assert scheme == "postgres"
        assert user == "user"
        assert host == "host"

    def test_parse_postgres_url_special_chars_in_username(self):
        """Test parsing URL with special characters in username."""
        url = "postgresql://user-name_123:password@localhost:5432/db"
        scheme, user, password, port, host, database, params = parse_postgres_url(url)

        assert user == "user-name_123"

    def test_parse_postgres_url_brackets_in_password(self):
        """Test parsing URL with brackets in password (IPv6-like chars)."""
        url = "postgresql://user:pass[word]:value@localhost:5432/db"
        scheme, user, password, port, host, database, params = parse_postgres_url(url)

        assert password == "pass[word]:value"

    def test_parse_postgres_url_curly_braces_in_password(self):
        """Test parsing URL with curly braces in password."""
        url = "postgresql://user:p{a}s{s}@localhost:5432/db"
        scheme, user, password, port, host, database, params = parse_postgres_url(url)

        assert password == "p{a}s{s}"

    def test_parse_postgres_url_percent_in_password(self):
        """Test parsing URL with percent sign in password."""
        url = "postgresql://user:pass%word@localhost:5432/db"
        scheme, user, password, port, host, database, params = parse_postgres_url(url)

        assert password == "pass%word"

    def test_parse_postgres_url_invalid_format(self):
        """Test parsing invalid PostgreSQL URL raises ValueError."""
        with pytest.raises(ValueError, match="Invalid PostgreSQL URL format"):
            parse_postgres_url("invalid://url")

    def test_parse_postgres_url_missing_port(self):
        """Test parsing URL without port raises ValueError."""
        with pytest.raises(ValueError, match="Invalid PostgreSQL URL format"):
            parse_postgres_url("postgresql://user:pass@localhost/db")

    def test_parse_postgres_url_missing_database(self):
        """Test parsing URL without database raises ValueError."""
        with pytest.raises(ValueError, match="Invalid PostgreSQL URL format"):
            parse_postgres_url("postgresql://user:pass@localhost:5432")

    def test_dialect_adapter_with_special_char_password(self):
        """Test DialectAdapter initialization with special character password."""
        # Simulates real-world case with special chars
        url = "postgresql://dbuser:p@ss{w}rd[123]@192.168.1.50:5432/myapp?sslmode=require"
        adapter = DialectAdapter(url)

        assert adapter.dialect == Dialect.POSTGRESQL
        assert adapter.is_postgresql()
        assert adapter.db_url == url
        assert adapter.db_path == ""  # PostgreSQL doesn't use file paths

    def test_dialect_adapter_with_url_encoded_password(self):
        """Test DialectAdapter with URL-encoded special characters."""
        url = "postgresql://user:p%40ss%7Bw%7Drd%5B123%5D@localhost:5432/db"
        adapter = DialectAdapter(url)

        assert adapter.dialect == Dialect.POSTGRESQL
        assert adapter.is_postgresql()

    def test_dialect_adapter_fallback_on_parse_error(self):
        """Test DialectAdapter falls back gracefully on parse errors."""
        # Create a PostgreSQL URL that our custom parser can't handle
        # but standard urlparse might (edge case)
        url = "postgresql://user@localhost:5432/db"  # No password
        adapter = DialectAdapter(url)

        # Should still detect as PostgreSQL
        assert adapter.dialect == Dialect.POSTGRESQL

    def test_multiple_at_symbols_in_password(self):
        """Test password with multiple @ symbols."""
        url = "postgresql://user:p@ss@w@rd@localhost:5432/db"
        scheme, user, password, port, host, database, params = parse_postgres_url(url)

        # Our regex captures everything between first : and last @
        assert "@" in password
        assert host == "localhost"

    def test_colon_in_password(self):
        """Test password with colon character."""
        url = "postgresql://user:pass:word:123@localhost:5432/db"
        scheme, user, password, port, host, database, params = parse_postgres_url(url)

        # Password should include colons
        assert password == "pass:word:123"

    def test_slash_in_database_name(self):
        """Test database name without slashes (valid case)."""
        url = "postgresql://user:pass@localhost:5432/my_database"
        scheme, user, password, port, host, database, params = parse_postgres_url(url)

        assert database == "my_database"

    def test_ip_address_host(self):
        """Test with IP address as host."""
        url = "postgresql://user:pass@10.20.30.40:5432/db"
        scheme, user, password, port, host, database, params = parse_postgres_url(url)

        assert host == "10.20.30.40"
        assert port == 5432

    def test_empty_password(self):
        """Test URL with empty password."""
        url = "postgresql://user:@localhost:5432/db"
        scheme, user, password, port, host, database, params = parse_postgres_url(url)

        assert user == "user"
        assert password == ""
        assert host == "localhost"

    def test_complex_production_url(self):
        """Test complex production URL with all special characters."""
        # Combines multiple edge cases: @, {, }, [, ] in password
        url = "postgresql://appuser:p@ss{w}rd[v2]@10.0.1.100:5432/appdb?sslmode=require"
        scheme, user, password, port, host, database, params = parse_postgres_url(url)

        assert scheme == "postgresql"
        assert user == "appuser"
        assert password == "p@ss{w}rd[v2]"
        assert host == "10.0.1.100"
        assert port == 5432
        assert database == "appdb"
        assert params == "?sslmode=require"

        # Verify adapter can use this URL
        adapter = DialectAdapter(url)
        assert adapter.is_postgresql()
        assert adapter.placeholder() == "%s"
