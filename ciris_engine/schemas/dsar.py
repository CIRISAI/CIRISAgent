"""Unified Pydantic schemas for DSAR (Data Subject Access Request) operations.

All schemas follow the zero-untyped-data principle and include mandatory 
signature fields for cryptographic audit trails (Ed25519).
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from ciris_engine.schemas.consent.core import DSARAccessPackage, DSARDeletionStatus, DSARExportPackage
from ciris_engine.schemas.identity import UserIdentityNode

# Constants for common field descriptions
_DESC_SIGNATURE = "Ed25519 signature for cryptographic verification"
_DESC_USER_IDENTIFIER = "User identifier (email, user_id, etc.)"
_DESC_PROCESSING_TIME = "Total processing time in seconds"


class DataSourceExport(BaseModel):
    """Export from a single data source (internal or external)."""

    source_id: str = Field(..., description="Unique identifier for the data source")
    source_type: str = Field(..., description="Type of source (sql, rest, hl7, internal)")
    source_name: str = Field(default="", description="Human-readable name of the source")
    tables_or_endpoints: List[str] = Field(
        default_factory=list,
        description="List of tables or endpoints queried",
    )
    total_records: int = Field(default=0, description="Number of records found and exported")
    data: Dict[str, Any] = Field(default_factory=dict, description="The actual exported data")
    checksum: Optional[str] = Field(default=None, description="SHA256 checksum of the exported data")
    export_timestamp: str = Field(..., description="ISO 8601 timestamp of the export")
    signature: str = Field(..., description=_DESC_SIGNATURE)
    errors: List[str] = Field(default_factory=list, description="List of errors encountered during export")


class DataSourceDeletion(BaseModel):
    """Result of a deletion operation on a single data source."""

    source_id: str = Field(..., description="Unique identifier for the data source")
    source_type: str = Field(..., description="Type of source")
    success: bool = Field(..., description="Whether the deletion was successful")
    tables_affected: List[str] = Field(default_factory=list, description="Tables where data was removed")
    total_records_deleted: int = Field(default=0, description="Number of records deleted")
    verification_passed: bool = Field(default=False, description="Result of post-deletion verification")
    deletion_timestamp: str = Field(..., description="ISO 8601 timestamp of the deletion")
    signature: str = Field(..., description=_DESC_SIGNATURE)
    errors: List[str] = Field(default_factory=list, description="List of errors encountered")


class MultiSourceDSARAccessPackage(BaseModel):
    """Aggregated DSAR access package from multiple sources."""

    request_id: str = Field(..., description="Unique DSAR request identifier")
    user_identifier: str = Field(..., description=_DESC_USER_IDENTIFIER)
    ciris_data: DSARAccessPackage = Field(..., description="Internal CIRIS data package")
    external_sources: List[DataSourceExport] = Field(
        default_factory=list, description="Data from external sources"
    )
    identity_node: Optional[UserIdentityNode] = Field(
        default=None, description="Resolved identity graph node"
    )
    total_sources: int = Field(default=0, description="Count of sources queried")
    total_records: int = Field(default=0, description="Total records across all sources")
    generated_at: str = Field(..., description="ISO 8601 generation timestamp")
    processing_time_seconds: float = Field(default=0.0, description=_DESC_PROCESSING_TIME)
    signature: str = Field(..., description=_DESC_SIGNATURE)


class MultiSourceDSARExportPackage(BaseModel):
    """Aggregated DSAR export package from multiple sources."""

    request_id: str = Field(..., description="Unique DSAR export identifier")
    user_identifier: str = Field(..., description=_DESC_USER_IDENTIFIER)
    ciris_export: DSARExportPackage = Field(..., description="Internal CIRIS export package")
    external_exports: List[DataSourceExport] = Field(
        default_factory=list, description="Exports from external sources"
    )
    identity_node: Optional[UserIdentityNode] = Field(default=None)
    total_sources: int = Field(default=0)
    total_records: int = Field(default=0)
    total_size_bytes: int = Field(default=0)
    export_format: str = Field(default="json")
    generated_at: str = Field(..., description="ISO 8601 generation timestamp")
    processing_time_seconds: float = Field(default=0.0)
    signature: str = Field(..., description=_DESC_SIGNATURE)


class MultiSourceDSARDeletionResult(BaseModel):
    """Aggregated DSAR deletion results from multiple sources."""

    request_id: str = Field(..., description="Unique DSAR deletion identifier")
    user_identifier: str = Field(..., description=_DESC_USER_IDENTIFIER)
    ciris_deletion: DSARDeletionStatus = Field(..., description="CIRIS-specific deletion status")
    external_deletions: List[DataSourceDeletion] = Field(default_factory=list)
    identity_node: Optional[UserIdentityNode] = Field(default=None)
    total_sources: int = Field(default=0)
    sources_completed: int = Field(default=0)
    sources_failed: int = Field(default=0)
    total_records_deleted: int = Field(default=0)
    all_verified: bool = Field(default=False)
    initiated_at: str = Field(..., description="ISO 8601 initiation timestamp")
    completed_at: Optional[str] = Field(default=None)
    processing_time_seconds: float = Field(default=0.0)
    signature: str = Field(..., description=_DESC_SIGNATURE)
