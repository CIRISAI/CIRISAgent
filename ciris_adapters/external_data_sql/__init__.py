"""External Data SQL Module - SQL database connector for DSAR automation."""

from .protocol import SQLDataSourceProtocol
from .schemas import (
    DataLocation,
    PrivacyColumnMapping,
    PrivacySchemaConfig,
    PrivacyTableMapping,
    SQLAnonymizationResult,
    SQLConnectorConfig,
    SQLDeletionResult,
    SQLDialect,
    SQLExportResult,
    SQLQueryResult,
    SQLStatsResult,
    SQLVerificationResult,
)
from .service import SQLToolService

__all__ = [
    "SQLDataSourceProtocol",
    "SQLToolService",
    "SQLConnectorConfig",
    "PrivacySchemaConfig",
    "PrivacyTableMapping",
    "PrivacyColumnMapping",
    "SQLDialect",
    "DataLocation",
    "SQLQueryResult",
    "SQLExportResult",
    "SQLDeletionResult",
    "SQLAnonymizationResult",
    "SQLVerificationResult",
    "SQLStatsResult",
]
