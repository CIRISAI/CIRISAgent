"""Protocol for SQL data source connectors."""

from typing import Any, Dict, Optional, Protocol

from .schemas import (
    DataLocation,
    SQLAnonymizationResult,
    SQLDeletionResult,
    SQLExportResult,
    SQLQueryResult,
    SQLStatsResult,
    SQLVerificationResult,
)


class SQLDataSourceProtocol(Protocol):
    """Protocol for SQL-based data source connectors.

    This protocol defines the interface for interacting with SQL databases
    for DSAR automation and privacy compliance.
    """

    async def find_user_data(self, user_identifier: str, identifier_type: str = "email") -> list[DataLocation]:
        """Discover all locations where user data exists.

        Args:
            user_identifier: User identifier (email, user_id, etc.)
            identifier_type: Type of identifier (email, user_id, phone, etc.)

        Returns:
            List of data locations where user data was found
        """
        ...

    async def export_user_data(self, user_identifier: str, export_format: str = "json") -> SQLExportResult:
        """Export all user data from the database.

        Args:
            user_identifier: User identifier
            export_format: Export format (json, csv, sqlite)

        Returns:
            Export result with data and metadata
        """
        ...

    async def delete_user_data(self, user_identifier: str, verify: bool = True) -> SQLDeletionResult:
        """Delete all user data from the database.

        Args:
            user_identifier: User identifier
            verify: Whether to verify deletion after completion

        Returns:
            Deletion result with counts and verification status
        """
        ...

    async def anonymize_user_data(self, user_identifier: str, strategy: str = "pseudonymize") -> SQLAnonymizationResult:
        """Anonymize user data instead of deleting.

        Args:
            user_identifier: User identifier
            strategy: Anonymization strategy (pseudonymize, hash, null, truncate)

        Returns:
            Anonymization result with affected tables/columns
        """
        ...

    async def verify_deletion(self, user_identifier: str, sign: bool = True) -> SQLVerificationResult:
        """Verify that user data has been completely deleted.

        Args:
            user_identifier: User identifier
            sign: Whether to generate Ed25519 cryptographic proof

        Returns:
            Verification result with zero-data assertion and optional signature
        """
        ...

    async def get_stats(self) -> SQLStatsResult:
        """Get database statistics.

        Returns:
            Database statistics including table counts and sizes
        """
        ...

    async def query(self, sql: str, parameters: Optional[Dict[str, Any]] = None) -> SQLQueryResult:
        """Execute raw SQL query (with privacy constraints).

        Args:
            sql: SQL query string
            parameters: Query parameters for parameterized queries

        Returns:
            Query result with rows and metadata
        """
        ...
