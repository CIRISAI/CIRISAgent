"""PostgreSQL dialect implementation."""

import hashlib

from ..schemas import PrivacyColumnMapping
from .base import BaseSQLDialect


class PostgreSQLDialect(BaseSQLDialect):
    """PostgreSQL-specific SQL dialect."""

    @property
    def name(self) -> str:
        return "postgresql"

    @property
    def supports_md5(self) -> bool:
        return True  # PostgreSQL has MD5

    @property
    def supports_sha256(self) -> bool:
        return True  # PostgreSQL has SHA256 via pgcrypto

    def build_count_query(self, table_name: str, identifier_col: str) -> str:
        return f"SELECT COUNT(*) as cnt FROM {table_name} WHERE {identifier_col} = :user_id"

    def build_select_query(self, table_name: str, identifier_col: str) -> str:
        return f"SELECT * FROM {table_name} WHERE {identifier_col} = :user_id"

    def build_delete_query(self, table_name: str, identifier_col: str) -> str:
        return f"DELETE FROM {table_name} WHERE {identifier_col} = :user_id"

    def build_anonymization_clause(self, column_mapping: PrivacyColumnMapping, user_identifier: str) -> str:
        """Build anonymization clause for PostgreSQL (has MD5, SHA256)."""
        col_name = column_mapping.column_name
        strategy = column_mapping.anonymization_strategy

        if strategy == "null":
            return f"{col_name} = NULL"
        elif strategy == "hash":
            # PostgreSQL has built-in MD5
            return f"{col_name} = md5({col_name})"
        elif strategy == "pseudonymize":
            # Generate deterministic pseudonym (done at Python level for consistency)
            pseudonym = hashlib.sha256(f"{user_identifier}_{col_name}".encode()).hexdigest()[:16]
            return f"{col_name} = '{pseudonym}'"
        elif strategy == "truncate":
            # PostgreSQL uses SUBSTRING
            return f"{col_name} = {self.build_substring_function(col_name, 1, 3)} || '***'"
        else:
            return f"{col_name} = 'ANONYMIZED'"

    def build_substring_function(self, column_name: str, start: int, length: int) -> str:
        """PostgreSQL uses SUBSTRING function."""
        return f"SUBSTRING({column_name}, {start}, {length})"

    def get_database_size_query(self) -> str:
        """PostgreSQL: Get database size."""
        return "SELECT pg_database_size(current_database()) / 1024.0 / 1024.0 as size_mb"
