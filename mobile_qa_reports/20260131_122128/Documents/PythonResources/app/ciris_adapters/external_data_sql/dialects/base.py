"""Base SQL dialect interface."""

from abc import ABC, abstractmethod
from typing import List

from ..schemas import PrivacyColumnMapping


class BaseSQLDialect(ABC):
    """Base class for SQL dialect-specific operations."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Dialect name."""
        ...

    @property
    @abstractmethod
    def supports_md5(self) -> bool:
        """Whether dialect supports MD5 function."""
        ...

    @property
    @abstractmethod
    def supports_sha256(self) -> bool:
        """Whether dialect supports SHA256 function."""
        ...

    @abstractmethod
    def build_count_query(self, table_name: str, identifier_col: str) -> str:
        """Build a COUNT query for finding user data.

        Args:
            table_name: Table to query
            identifier_col: Column to match on

        Returns:
            SQL query string with :user_id parameter
        """
        ...

    @abstractmethod
    def build_select_query(self, table_name: str, identifier_col: str) -> str:
        """Build a SELECT query for exporting user data.

        Args:
            table_name: Table to query
            identifier_col: Column to match on

        Returns:
            SQL query string with :user_id parameter
        """
        ...

    @abstractmethod
    def build_delete_query(self, table_name: str, identifier_col: str) -> str:
        """Build a DELETE query for removing user data.

        Args:
            table_name: Table to delete from
            identifier_col: Column to match on

        Returns:
            SQL query string with :user_id parameter
        """
        ...

    @abstractmethod
    def build_anonymization_clause(self, column_mapping: PrivacyColumnMapping, user_identifier: str) -> str:
        """Build anonymization clause for UPDATE statement.

        Args:
            column_mapping: Column with anonymization strategy
            user_identifier: User identifier for deterministic pseudonyms

        Returns:
            SQL fragment like "column_name = 'ANONYMIZED'" or "column_name = md5(column_name)"
        """
        ...

    @abstractmethod
    def build_substring_function(self, column_name: str, start: int, length: int) -> str:
        """Build substring function (dialect-specific).

        Args:
            column_name: Column to substring
            start: Start position (1-indexed)
            length: Length of substring

        Returns:
            SQL fragment like "SUBSTR(col, 1, 3)" or "SUBSTRING(col, 1, 3)"
        """
        ...

    def build_update_query(
        self,
        table_name: str,
        identifier_col: str,
        column_mappings: List[PrivacyColumnMapping],
        user_identifier: str,
    ) -> str:
        """Build UPDATE query for anonymization.

        Args:
            table_name: Table to update
            identifier_col: Column to match on
            column_mappings: Columns to anonymize
            user_identifier: User identifier

        Returns:
            Complete UPDATE SQL statement
        """
        updates = []
        for col_mapping in column_mappings:
            if col_mapping.anonymization_strategy == "delete":
                continue  # Skip deletion columns in anonymization
            clause = self.build_anonymization_clause(col_mapping, user_identifier)
            updates.append(clause)

        if not updates:
            return ""

        update_clause = ", ".join(updates)
        return f"UPDATE {table_name} SET {update_clause} WHERE {identifier_col} = :user_id"

    def get_database_size_query(self) -> str:
        """Get database size query (dialect-specific, may not be supported).

        Returns:
            SQL query to get database size in MB, or empty string if not supported
        """
        return ""  # Default: not supported
