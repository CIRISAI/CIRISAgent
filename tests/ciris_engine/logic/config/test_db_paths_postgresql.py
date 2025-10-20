"""
Tests for PostgreSQL URL modification in db_paths module.

Verifies that derivative database URLs (secrets, auth) are correctly
constructed while preserving query parameters.
"""

import pytest

from ciris_engine.logic.config.db_paths import _modify_database_name_in_url


class TestModifyDatabaseNameInURL:
    """Test the _modify_database_name_in_url helper function."""

    def test_basic_url_with_no_params(self) -> None:
        """Test modifying database name without query parameters."""
        url = "postgresql://user:pass@localhost:5432/mydb"
        result = _modify_database_name_in_url(url, "_secrets")
        assert result == "postgresql://user:pass@localhost:5432/mydb_secrets"

    def test_url_with_sslmode_require(self) -> None:
        """Test that sslmode parameter is preserved (Scout's bug case)."""
        url = "postgresql://ciris_user:password@10.2.96.6:16751/ciris_db?sslmode=require"
        result = _modify_database_name_in_url(url, "_secrets")
        assert result == "postgresql://ciris_user:password@10.2.96.6:16751/ciris_db_secrets?sslmode=require"

    def test_url_with_encoded_password(self) -> None:
        """Test that URL-encoded password is preserved."""
        url = "postgresql://ciris_user:%7D7gCg%40%7DPnH5UXp%5D%7B@10.2.96.6:16751/ciris_db?sslmode=require"
        result = _modify_database_name_in_url(url, "_secrets")
        assert result == "postgresql://ciris_user:%7D7gCg%40%7DPnH5UXp%5D%7B@10.2.96.6:16751/ciris_db_secrets?sslmode=require"

    def test_url_with_multiple_params(self) -> None:
        """Test that multiple query parameters are preserved."""
        url = "postgresql://user:pass@host:5432/db?sslmode=require&connect_timeout=10"
        result = _modify_database_name_in_url(url, "_auth")
        assert result == "postgresql://user:pass@host:5432/db_auth?sslmode=require&connect_timeout=10"

    def test_url_with_auth_suffix(self) -> None:
        """Test adding _auth suffix for audit database."""
        url = "postgresql://user:pass@localhost:5432/ciris_test_db"
        result = _modify_database_name_in_url(url, "_auth")
        assert result == "postgresql://user:pass@localhost:5432/ciris_test_db_auth"

    def test_postgres_scheme_variant(self) -> None:
        """Test that 'postgres://' scheme works (in addition to 'postgresql://')."""
        url = "postgres://user:pass@localhost:5432/db?sslmode=prefer"
        result = _modify_database_name_in_url(url, "_secrets")
        assert result == "postgres://user:pass@localhost:5432/db_secrets?sslmode=prefer"

    def test_no_password_in_url(self) -> None:
        """Test URL without password."""
        url = "postgresql://user@localhost:5432/db?sslmode=disable"
        result = _modify_database_name_in_url(url, "_secrets")
        assert result == "postgresql://user@localhost:5432/db_secrets?sslmode=disable"

    def test_preserves_all_url_components(self) -> None:
        """Test that all URL components are preserved correctly."""
        # Complex URL with all components
        url = "postgresql://user:pass@host.example.com:5432/mydb?sslmode=verify-full&application_name=ciris"
        result = _modify_database_name_in_url(url, "_secrets")

        # Verify all components
        assert "postgresql://" in result
        assert "user:pass@" in result
        assert "host.example.com:5432" in result
        assert "/mydb_secrets?" in result
        assert "sslmode=verify-full" in result
        assert "application_name=ciris" in result


class TestGetSecretsDBFullPathPostgreSQL:
    """Test get_secrets_db_full_path with PostgreSQL URLs."""

    def test_returns_modified_url_for_postgresql(self) -> None:
        """Test that PostgreSQL URL is modified with _secrets suffix."""
        from ciris_engine.logic.config.db_paths import get_secrets_db_full_path
        from ciris_engine.schemas.config.essential import DatabaseConfig, EssentialConfig

        config = EssentialConfig(
            database=DatabaseConfig(
                database_url="postgresql://user:pass@localhost:5432/ciris_db?sslmode=require"
            )
        )

        result = get_secrets_db_full_path(config)
        assert result == "postgresql://user:pass@localhost:5432/ciris_db_secrets?sslmode=require"


class TestGetAuditDBFullPathPostgreSQL:
    """Test get_audit_db_full_path with PostgreSQL URLs."""

    def test_returns_modified_url_for_postgresql(self) -> None:
        """Test that PostgreSQL URL is modified with _auth suffix."""
        from ciris_engine.logic.config.db_paths import get_audit_db_full_path
        from ciris_engine.schemas.config.essential import DatabaseConfig, EssentialConfig

        config = EssentialConfig(
            database=DatabaseConfig(
                database_url="postgresql://user:pass@localhost:5432/ciris_db?sslmode=require"
            )
        )

        result = get_audit_db_full_path(config)
        assert result == "postgresql://user:pass@localhost:5432/ciris_db_auth?sslmode=require"
