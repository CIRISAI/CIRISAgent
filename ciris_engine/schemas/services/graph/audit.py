"""
Graph audit service schemas.

Provides typed schemas in audit service operations.
"""

from datetime import datetime
from typing import Dict, List, Optional, Union

from pydantic import BaseModel, ConfigDict, Field


class AuditEventData(BaseModel):
    """Data for an audit event."""

    entity_id: str = Field("system", description="Entity involved in event")
    actor: str = Field("system", description="Actor performing the event")
    outcome: str = Field("success", description="Event outcome")
    severity: str = Field("info", description="Event severity level")

    # Core event data
    action: Optional[str] = Field(None, description="Action performed")
    resource: Optional[str] = Field(None, description="Resource affected")
    reason: Optional[str] = Field(None, description="Reason for action")

    # Additional context
    metadata: Dict[str, Union[str, int, float, bool]] = Field(
        default_factory=dict, description="Additional event metadata"
    )

    model_config = ConfigDict(extra="allow")  # Allow additional fields for flexibility


class VerificationReport(BaseModel):
    """Audit integrity verification report."""

    verified: bool = Field(..., description="Whether integrity check passed")
    total_entries: int = Field(..., description="Total audit entries checked")
    valid_entries: int = Field(..., description="Entries with valid signatures")
    invalid_entries: int = Field(..., description="Entries with invalid signatures")
    missing_entries: int = Field(0, description="Entries missing from chain")

    # Chain integrity
    chain_intact: bool = Field(..., description="Whether hash chain is intact")
    last_valid_entry: Optional[str] = Field(None, description="Last valid entry ID")
    first_invalid_entry: Optional[str] = Field(None, description="First invalid entry ID")

    # Timing
    verification_started: datetime = Field(..., description="Verification start time")
    verification_completed: datetime = Field(..., description="Verification end time")
    duration_ms: float = Field(..., description="Verification duration in milliseconds")

    # Errors
    errors: List[str] = Field(default_factory=list, description="Errors encountered")
    warnings: List[str] = Field(default_factory=list, description="Warnings encountered")


class AuditQueryResult(BaseModel):
    """Result of an audit query."""

    query_type: str = Field(..., description="Type of query performed")
    total_results: int = Field(..., description="Total matching entries")
    returned_results: int = Field(..., description="Number of results returned")

    # Results
    entries: List[Dict[str, Union[str, int, float, bool, datetime]]] = Field(
        default_factory=list, description="Audit entries matching query"
    )

    # Query metadata
    filters_applied: Dict[str, str] = Field(default_factory=dict, description="Filters used")
    sort_order: Optional[str] = Field(None, description="Sort order applied")
    offset: int = Field(0, description="Results offset")
    limit: Optional[int] = Field(None, description="Results limit")


class AuditQuery(BaseModel):
    """Query parameters for audit searches."""

    # Time range
    start_time: Optional[datetime] = Field(None, description="Start of time range")
    end_time: Optional[datetime] = Field(None, description="End of time range")

    # Filters
    event_type: Optional[str] = Field(None, description="Filter by event type")
    actor: Optional[str] = Field(None, description="Filter by actor")
    entity_id: Optional[str] = Field(None, description="Filter by entity")
    outcome: Optional[str] = Field(None, description="Filter by outcome")
    severity: Optional[str] = Field(None, description="Filter by severity")

    # Search
    search_text: Optional[str] = Field(None, description="Text search in details")

    # Results
    order_by: str = Field("timestamp", description="Field to order by")
    order_desc: bool = Field(True, description="Order descending")
    limit: Optional[int] = Field(100, description="Maximum results")
    offset: int = Field(0, description="Results offset")
