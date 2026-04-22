"""SQLite dialect implementation."""

import hashlib

from ..schemas import PrivacyColumnMapping
from .base import BaseSQLDialect


class SQLiteDialect(BaseSQLDialect):
    """SQLite-specific SQL dialect."""

    @property
    def name(self) -> str:
        return "sqlite"

    @property
    def supports_md5(self) -> bool:
        return False  # SQLite doesn't have built-in MD5

    @property
    def supports_sha256(self) -> bool:
        return False  # SQLite doesn't have built-in SHA256

    def build_count_query(self, table_name: str, identifier_col: str) -> str:
        return f"SELECT COUNT(*) as cnt FROM {table_name} WHERE {identifier_col} = :user_id"

    def build_select_query(self, table_name: str, identifier_col: str) -> str:
        return f"SELECT * FROM {table_name} WHERE {identifier_col} = :user_id"

    def build_delete_query(self, table_name: str, identifier_col: str) -> str:
        return f"DELETE FROM {table_name} WHERE {identifier_col} = :user_id"

    def build_anonymization_clause(self, column_mapping: PrivacyColumnMapping, user_identifier: str) -> str:
        """Build anonymization clause for SQLite (no built-in hash functions)."""
        col_name = column_mapping.column_name
        strategy = column_mapping.anonymization_strategy

        if strategy == "null":
            return f"{col_name} = NULL"
        elif strategy == "hash":
            # SQLite doesn't have MD5, use placeholder
            return f"{col_name} = 'HASH_REDACTED'"
        elif strategy == "pseudonymize":
            # Generate deterministic pseudonym (done at Python level)
            pseudonym = hashlib.sha256(f"{user_identifier}_{col_name}".encode()).hexdigest()[:16]
            return f"{col_name} = '{pseudonym}'"
        elif strategy == "truncate":
            # SQLite uses SUBSTR
            return f"{col_name} = {self.build_substring_function(col_name, 1, 3)} || '***'"
        else:
            return f"{col_name} = 'ANONYMIZED'"

    def build_substring_function(self, column_name: str, start: int, length: int) -> str:
        """SQLite uses SUBSTR function."""
        return f"SUBSTR({column_name}, {start}, {length})"

    def get_database_size_query(self) -> str:
        """SQLite: Get size via page_count * page_size."""
        return """
        SELECT (page_count * page_size) / 1024.0 / 1024.0 as size_mb
        FROM pragma_page_count(), pragma_page_size()
        """
