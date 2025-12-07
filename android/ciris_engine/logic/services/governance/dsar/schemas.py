"""Schemas for multi-source DSAR orchestration."""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from ciris_engine.schemas.consent.core import DSARAccessPackage, DSARDeletionStatus, DSARExportPackage
from ciris_engine.schemas.identity import UserIdentityNode

# Field description constants to avoid duplication
_DESC_USER_IDENTIFIER = "User identifier used for request"
_DESC_IDENTITY_NODE = "Resolved user identity across systems"
_DESC_PROCESSING_TIME = "Total processing time"


class DataSourceExport(BaseModel):
    """Export from a single external data source."""

    source_id: str = Field(..., description="Unique connector identifier")
    source_type: str = Field(..., description="Type of data source (sql, rest, hl7, etc.)")
    source_name: str = Field(default="", description="Human-readable source name")
    tables_or_endpoints: List[str] = Field(
        default_factory=list,
        description="Tables queried (SQL) or endpoints called (REST)",
    )
    total_records: int = Field(default=0, description="Total records exported")
    data: Dict[str, Any] = Field(default_factory=dict, description="Exported data structure")
    checksum: Optional[str] = Field(default=None, description="SHA256 checksum of export")
    export_timestamp: str = Field(..., description="When export was generated")
    errors: List[str] = Field(default_factory=list, description="Any errors encountered")


class MultiSourceDSARAccessPackage(BaseModel):
    """DSAR access package aggregated from multiple sources."""

    request_id: str = Field(..., description="DSAR request identifier")
    user_identifier: str = Field(..., description=_DESC_USER_IDENTIFIER)

    # CIRIS internal data (fast path)
    ciris_data: DSARAccessPackage = Field(..., description="Data from CIRIS internal systems")

    # External data sources
    external_sources: List[DataSourceExport] = Field(default_factory=list, description="Data from external sources")

    # Identity resolution
    identity_node: Optional[UserIdentityNode] = Field(default=None, description=_DESC_IDENTITY_NODE)

    # Metadata
    total_sources: int = Field(default=0, description="Total number of sources queried")
    total_records: int = Field(default=0, description="Total records across all sources")
    generated_at: str = Field(..., description="When package was generated")
    processing_time_seconds: float = Field(default=0.0, description=_DESC_PROCESSING_TIME)


class MultiSourceDSARExportPackage(BaseModel):
    """DSAR export package aggregated from multiple sources."""

    request_id: str = Field(..., description="DSAR export request identifier")
    user_identifier: str = Field(..., description=_DESC_USER_IDENTIFIER)

    # CIRIS internal export
    ciris_export: DSARExportPackage = Field(..., description="Export from CIRIS internal systems")

    # External exports
    external_exports: List[DataSourceExport] = Field(default_factory=list, description="Exports from external sources")

    # Identity resolution
    identity_node: Optional[UserIdentityNode] = Field(default=None, description=_DESC_IDENTITY_NODE)

    # Aggregated metadata
    total_sources: int = Field(default=0, description="Total number of sources exported")
    total_records: int = Field(default=0, description="Total records across all sources")
    total_size_bytes: int = Field(default=0, description="Total size of all exports")
    export_format: str = Field(default="json", description="Export format")
    generated_at: str = Field(..., description="When package was generated")
    processing_time_seconds: float = Field(default=0.0, description=_DESC_PROCESSING_TIME)


class DataSourceDeletion(BaseModel):
    """Deletion result from a single data source."""

    source_id: str = Field(..., description="Unique connector identifier")
    source_type: str = Field(..., description="Type of data source")
    source_name: str = Field(default="", description="Human-readable source name")
    success: bool = Field(..., description="Whether deletion succeeded")
    tables_affected: List[str] = Field(default_factory=list, description="Tables where data was deleted")
    total_records_deleted: int = Field(default=0, description="Total records deleted")
    verification_passed: bool = Field(default=False, description="Whether post-deletion verification passed")
    errors: List[str] = Field(default_factory=list, description="Any errors encountered")
    deletion_timestamp: str = Field(..., description="When deletion occurred")


class MultiSourceDSARDeletionResult(BaseModel):
    """DSAR deletion result aggregated from multiple sources."""

    request_id: str = Field(..., description="DSAR deletion request identifier")
    user_identifier: str = Field(..., description=_DESC_USER_IDENTIFIER)

    # CIRIS internal deletion
    ciris_deletion: DSARDeletionStatus = Field(..., description="Deletion status from CIRIS (90-day decay)")

    # External deletions
    external_deletions: List[DataSourceDeletion] = Field(
        default_factory=list, description="Deletion results from external sources"
    )

    # Identity resolution
    identity_node: Optional[UserIdentityNode] = Field(default=None, description=_DESC_IDENTITY_NODE)

    # Aggregated status
    total_sources: int = Field(default=0, description="Total number of sources processed")
    sources_completed: int = Field(default=0, description="Number of sources with completed deletion")
    sources_failed: int = Field(default=0, description="Number of sources with failed deletion")
    total_records_deleted: int = Field(default=0, description="Total records deleted across all sources")
    all_verified: bool = Field(default=False, description="Whether all deletions were verified")
    initiated_at: str = Field(..., description="When deletion was initiated")
    completed_at: Optional[str] = Field(default=None, description="When all deletions completed (if completed)")
    processing_time_seconds: float = Field(default=0.0, description=_DESC_PROCESSING_TIME)


class MultiSourceDSARCorrectionResult(BaseModel):
    """DSAR correction result aggregated from multiple sources."""

    request_id: str = Field(..., description="DSAR correction request identifier")
    user_identifier: str = Field(..., description=_DESC_USER_IDENTIFIER)

    # Corrections by source
    corrections_by_source: Dict[str, Dict[str, Any]] = Field(
        default_factory=dict,
        description="Corrections applied per source {source_id: {field: new_value}}",
    )

    # Identity resolution
    identity_node: Optional[UserIdentityNode] = Field(default=None, description=_DESC_IDENTITY_NODE)

    # Aggregated status
    total_sources: int = Field(default=0, description="Total number of sources processed")
    total_corrections_applied: int = Field(default=0, description="Total corrections applied")
    total_corrections_rejected: int = Field(default=0, description="Total corrections rejected")
    generated_at: str = Field(..., description="When correction was completed")
    processing_time_seconds: float = Field(default=0.0, description=_DESC_PROCESSING_TIME)
