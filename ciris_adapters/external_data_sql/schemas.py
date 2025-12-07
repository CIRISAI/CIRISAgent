"""Schemas for SQL external data connector."""

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class SQLDialect(str, Enum):
    """Supported SQL dialects."""

    SQLITE = "sqlite"
    MYSQL = "mysql"
    POSTGRESQL = "postgresql"


class PrivacyColumnMapping(BaseModel):
    """Privacy-sensitive column mapping."""

    column_name: str = Field(..., description="Column name in the table")
    data_type: str = Field(..., description="Data type (email, name, phone, etc.)")
    is_identifier: bool = Field(default=False, description="Whether this column is used for user identification")
    anonymization_strategy: str = Field(
        default="delete",
        description="Strategy: delete, pseudonymize, hash, truncate, null",
    )


class PrivacyTableMapping(BaseModel):
    """Privacy schema for a single table."""

    table_name: str = Field(..., description="Table name")
    columns: List[PrivacyColumnMapping] = Field(..., description="Privacy-sensitive columns")
    identifier_column: str = Field(..., description="Primary column for user identification (e.g., user_id, email)")
    cascade_deletes: List[str] = Field(
        default_factory=list,
        description="Related tables to cascade delete (e.g., user_sessions)",
    )


class PrivacySchemaConfig(BaseModel):
    """Complete privacy schema configuration for a database."""

    tables: List[PrivacyTableMapping] = Field(..., description="Table mappings")
    global_identifier_column: Optional[str] = Field(
        default=None,
        description="Global identifier column name if consistent across tables",
    )


class SQLConnectorConfig(BaseModel):
    """Configuration for SQL connector."""

    connector_id: str = Field(..., description="Unique identifier for this connector")
    connection_string: str = Field(..., description="ODBC/SQLAlchemy connection string")
    dialect: SQLDialect = Field(..., description="SQL dialect")
    privacy_schema: Optional[PrivacySchemaConfig] = Field(
        default=None, description="Privacy schema configuration (can be loaded from file)"
    )
    connection_timeout: int = Field(default=30, description="Connection timeout in seconds")
    query_timeout: int = Field(default=60, description="Query timeout in seconds")
    max_retries: int = Field(default=3, description="Maximum retry attempts")


class DataLocation(BaseModel):
    """Location of user data in database."""

    table_name: str = Field(..., description="Table name")
    column_name: str = Field(..., description="Column name")
    data_type: str = Field(..., description="Data type")
    row_count: int = Field(..., description="Number of rows found")
    sample_value: Optional[str] = Field(default=None, description="Sample value (anonymized)")


class SQLQueryResult(BaseModel):
    """Result from SQL query execution."""

    success: bool = Field(..., description="Whether query succeeded")
    row_count: int = Field(default=0, description="Number of rows returned")
    columns: List[str] = Field(default_factory=list, description="Column names")
    rows: List[Dict[str, Any]] = Field(default_factory=list, description="Result rows")
    error: Optional[str] = Field(default=None, description="Error message if failed")
    execution_time_ms: float = Field(default=0.0, description="Query execution time in milliseconds")


class SQLExportResult(BaseModel):
    """Result from user data export."""

    success: bool = Field(..., description="Whether export succeeded")
    user_identifier: str = Field(..., description="User identifier")
    tables_exported: List[str] = Field(default_factory=list, description="Tables included in export")
    total_rows: int = Field(default=0, description="Total rows exported")
    data: Dict[str, List[Dict[str, Any]]] = Field(default_factory=dict, description="Exported data by table")
    export_format: str = Field(default="json", description="Export format")
    checksum: Optional[str] = Field(default=None, description="SHA256 checksum of export")
    error: Optional[str] = Field(default=None, description="Error message if failed")


class SQLDeletionResult(BaseModel):
    """Result from user data deletion."""

    success: bool = Field(..., description="Whether deletion succeeded")
    user_identifier: str = Field(..., description="User identifier")
    tables_affected: List[str] = Field(default_factory=list, description="Tables where data was deleted")
    total_rows_deleted: int = Field(default=0, description="Total rows deleted")
    cascade_deletions: Dict[str, int] = Field(default_factory=dict, description="Cascade deletions by table")
    verification_passed: bool = Field(default=False, description="Whether post-deletion verification passed")
    error: Optional[str] = Field(default=None, description="Error message if failed")


class SQLAnonymizationResult(BaseModel):
    """Result from user data anonymization."""

    success: bool = Field(..., description="Whether anonymization succeeded")
    user_identifier: str = Field(..., description="User identifier")
    tables_affected: List[str] = Field(default_factory=list, description="Tables where data was anonymized")
    columns_anonymized: Dict[str, List[str]] = Field(default_factory=dict, description="Columns anonymized by table")
    total_rows_affected: int = Field(default=0, description="Total rows anonymized")
    anonymization_strategy: str = Field(default="pseudonymize", description="Strategy used")
    error: Optional[str] = Field(default=None, description="Error message if failed")


class SQLVerificationResult(BaseModel):
    """Result from deletion verification scan."""

    success: bool = Field(..., description="Whether verification succeeded")
    user_identifier: str = Field(..., description="User identifier")
    zero_data_confirmed: bool = Field(default=False, description="Whether zero user data was found")
    tables_scanned: List[str] = Field(default_factory=list, description="Tables scanned")
    remaining_data: Dict[str, int] = Field(
        default_factory=dict, description="Remaining data by table (should be empty)"
    )
    verification_timestamp: str = Field(..., description="Verification timestamp")
    cryptographic_proof: Optional[str] = Field(default=None, description="Ed25519 signature of verification")
    error: Optional[str] = Field(default=None, description="Error message if failed")


class SQLStatsResult(BaseModel):
    """Database statistics result."""

    success: bool = Field(..., description="Whether stats collection succeeded")
    total_tables: int = Field(default=0, description="Total tables in database")
    total_rows: int = Field(default=0, description="Total rows across all tables")
    tables: Dict[str, int] = Field(default_factory=dict, description="Row counts by table")
    database_size_mb: Optional[float] = Field(default=None, description="Database size in MB")
    error: Optional[str] = Field(default=None, description="Error message if failed")
