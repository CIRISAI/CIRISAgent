"""
Consent Protocol Schemas - FAIL FAST, FAIL LOUD, NO FAKE DATA.

These schemas define how CIRIS handles user data based on consent.
Default: TEMPORARY (14-day auto-forget)
"""

from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field

# Common field descriptions
REQUEST_ID_DESC = "Unique request identifier"
USER_ID_DESC = "User identifier"
CURRENT_STREAM_DESC = "Current consent stream"


class ConsentStream(str, Enum):
    """
    How we handle user data based on consent.

    TEMPORARY: Default - we forget in 14 days
    PARTNERED: Explicit consent for mutual growth
    ANONYMOUS: Statistics only, no identity
    """

    TEMPORARY = "temporary"  # 14-day auto-forget (default)
    PARTNERED = "partnered"  # Mutual growth agreement
    ANONYMOUS = "anonymous"  # Stats only, no identity


class ConsentCategory(str, Enum):
    """What types of learning the user has consented to."""

    INTERACTION = "interaction"  # Learn from our conversations
    PREFERENCE = "preference"  # Learn preferences and patterns
    IMPROVEMENT = "improvement"  # Use for self-improvement
    RESEARCH = "research"  # Use for research purposes
    SHARING = "sharing"  # Share learnings with others


class ConsentStatus(BaseModel):
    """User's consent configuration - NO DEFAULTS, FAIL FAST."""

    user_id: str = Field(..., description=USER_ID_DESC)
    stream: ConsentStream = Field(..., description=CURRENT_STREAM_DESC)
    categories: List[ConsentCategory] = Field(..., description="What they consented to")
    granted_at: datetime = Field(..., description="When consent was granted")
    expires_at: Optional[datetime] = Field(None, description="When TEMPORARY expires")
    last_modified: datetime = Field(..., description="Last modification time")
    impact_score: float = Field(0.0, ge=0.0, description="Contribution to collective learning")
    attribution_count: int = Field(0, ge=0, description="Number of patterns attributed")

    model_config = ConfigDict(use_enum_values=True)


class ConsentRequest(BaseModel):
    """Request to grant or modify consent - EXPLICIT, NO ASSUMPTIONS."""

    user_id: str = Field(..., description="User requesting consent change")
    stream: ConsentStream = Field(..., description="Requested stream")
    categories: List[ConsentCategory] = Field(..., description="Categories to consent to")
    reason: Optional[str] = Field(None, description="User's reason for change")


class ConsentAuditEntry(BaseModel):
    """Audit trail for consent changes - IMMUTABLE RECORD."""

    entry_id: str = Field(..., description="Unique audit entry ID")
    user_id: str = Field(..., description="User whose consent changed")
    timestamp: datetime = Field(..., description="When change occurred")
    previous_stream: ConsentStream = Field(..., description="Stream before change")
    new_stream: ConsentStream = Field(..., description="Stream after change")
    previous_categories: List[ConsentCategory] = Field(..., description="Categories before")
    new_categories: List[ConsentCategory] = Field(..., description="Categories after")
    initiated_by: str = Field(..., description="Who initiated change (user/system/dsar)")
    reason: Optional[str] = Field(None, description="Reason for change")


class ConsentDecayStatus(BaseModel):
    """Track decay protocol progress - NO FAKE DELETION."""

    user_id: str = Field(..., description="User being forgotten")
    decay_started: datetime = Field(..., description="When decay began")
    identity_severed: bool = Field(..., description="Identity disconnected from patterns")
    patterns_anonymized: bool = Field(..., description="Patterns converted to anonymous")
    decay_complete_at: datetime = Field(..., description="When decay will complete (90 days)")
    safety_patterns_retained: int = Field(0, ge=0, description="Patterns kept for safety")


class ConsentImpactReport(BaseModel):
    """
    Show users their contribution - REAL DATA ONLY.

    User-facing name: Commons Credits Report

    Commons Credits track non-monetary contributions that strengthen the community:
    - Sharing knowledge (patterns_contributed)
    - Supporting others (users_helped)
    - Maintaining infrastructure (interactions)

    Not currency. Not scorekeeping. Recognition for contributions traditional systems ignore.
    """

    user_id: str = Field(..., description="User requesting report")
    total_interactions: int = Field(..., ge=0, description="Total interactions")
    patterns_contributed: int = Field(..., ge=0, description="Patterns learned")
    users_helped: int = Field(..., ge=0, description="Others benefited")
    categories_active: List[ConsentCategory] = Field(..., description="Active categories")
    impact_score: float = Field(..., ge=0.0, description="Overall impact")
    example_contributions: List[str] = Field(..., description="Example learnings (anonymized)")


# DSAR Automation Schemas


class DSARAccessPackage(BaseModel):
    """Package of user data for DSAR access requests - REAL DATA ONLY."""

    user_id: str = Field(..., description="User requesting access")
    request_id: str = Field(..., description=REQUEST_ID_DESC)
    generated_at: datetime = Field(..., description="When package was generated")
    consent_status: ConsentStatus = Field(..., description="Current consent configuration")
    consent_history: List[ConsentAuditEntry] = Field(..., description="Complete consent audit trail")
    interaction_summary: dict[str, object] = Field(..., description="Interaction statistics by channel")
    contribution_metrics: ConsentImpactReport = Field(..., description="User's contribution impact")
    data_categories: List[str] = Field(..., description="Categories of data collected")
    retention_periods: dict[str, str] = Field(..., description="How long each data type is retained")
    processing_purposes: List[str] = Field(..., description="Why data is being processed")


class DSARExportFormat(str, Enum):
    """Export format for DSAR data portability."""

    JSON = "json"  # Machine-readable JSON
    CSV = "csv"  # Spreadsheet-compatible
    SQLITE = "sqlite"  # Database export


class DSARExportPackage(BaseModel):
    """Package for DSAR data portability export."""

    user_id: str = Field(..., description="User requesting export")
    request_id: str = Field(..., description=REQUEST_ID_DESC)
    export_format: DSARExportFormat = Field(..., description="Format of exported data")
    generated_at: datetime = Field(..., description="When export was generated")
    file_path: Optional[str] = Field(None, description="Path to export file (if file-based)")
    file_size_bytes: int = Field(..., ge=0, description="Size of export in bytes")
    record_counts: dict[str, int] = Field(..., description="Number of records by type")
    checksum: str = Field(..., description="SHA256 checksum for integrity verification")
    includes_readme: bool = Field(True, description="Whether README file is included")


class DSARCorrectionRequest(BaseModel):
    """Request to correct user data under GDPR Article 16."""

    user_id: str = Field(..., description="User requesting correction")
    field_name: str = Field(..., description="Field to correct (e.g., 'email', 'preferences.language')")
    current_value: Optional[str] = Field(None, description="Current (incorrect) value")
    new_value: str = Field(..., description="Corrected value")
    reason: str = Field(..., description="Reason for correction")


class DSARCorrectionResult(BaseModel):
    """Result of DSAR correction request."""

    user_id: str = Field(..., description="User whose data was corrected")
    request_id: str = Field(..., description=REQUEST_ID_DESC)
    corrections_applied: List[dict[str, object]] = Field(..., description="Successfully applied corrections")
    corrections_rejected: List[dict[str, object]] = Field(..., description="Rejected corrections with reasons")
    affected_systems: List[str] = Field(..., description="Systems notified of corrections")
    audit_entry_id: str = Field(..., description="Audit trail entry ID")
    completed_at: datetime = Field(..., description="When corrections were completed")


class DSARDeletionStatus(BaseModel):
    """Track DSAR deletion request progress (linked to decay protocol)."""

    ticket_id: str = Field(..., description="DSAR ticket ID")
    user_id: str = Field(..., description="User being deleted")
    decay_started: datetime = Field(..., description="When deletion began")
    current_phase: str = Field(
        ..., description="Current decay phase (identity_severed, patterns_anonymizing, complete)"
    )
    completion_percentage: float = Field(..., ge=0.0, le=100.0, description="Progress toward completion")
    estimated_completion: datetime = Field(..., description="Estimated completion date (90 days from start)")
    milestones_completed: List[str] = Field(..., description="Completed decay milestones")
    next_milestone: Optional[str] = Field(None, description="Next milestone to complete")
    safety_patterns_retained: int = Field(0, ge=0, description="Anonymized safety patterns retained")


# Partnership Management Schemas


class PartnershipAgingStatus(str, Enum):
    """Aging status for partnership requests."""

    NORMAL = "normal"  # <7 days
    WARNING = "warning"  # 7-14 days
    CRITICAL = "critical"  # >14 days


class PartnershipOutcomeType(str, Enum):
    """Outcome types for partnership decisions."""

    APPROVED = "approved"
    REJECTED = "rejected"
    DEFERRED = "deferred"
    EXPIRED = "expired"  # Auto-rejected due to age


class PartnershipPriority(str, Enum):
    """Priority levels for partnership requests."""

    HIGH = "high"  # Long-term users (>90 days TEMPORARY) or high impact
    NORMAL = "normal"  # Standard requests
    LOW = "low"  # New users


class PartnershipRequest(BaseModel):
    """Partnership request awaiting approval."""

    user_id: str = Field(..., description="User requesting partnership")
    task_id: str = Field(..., description="Agent approval task ID")
    categories: List[ConsentCategory] = Field(..., description="Categories requested")
    reason: Optional[str] = Field(None, description="User's reason for partnership")
    channel_id: str = Field(..., description="Channel where request originated")
    created_at: datetime = Field(..., description="When request was created")
    age_hours: float = Field(..., ge=0.0, description="Hours since request created")
    aging_status: PartnershipAgingStatus = Field(..., description="Aging classification")
    priority: PartnershipPriority = Field(PartnershipPriority.NORMAL, description="Request priority level")
    notes: Optional[str] = Field(None, description="Admin notes about request")


class PartnershipOutcome(BaseModel):
    """Outcome of partnership decision."""

    user_id: str = Field(..., description="User whose partnership was decided")
    task_id: str = Field(..., description="Task ID for this partnership")
    outcome_type: PartnershipOutcomeType = Field(..., description="Decision outcome")
    decided_by: str = Field(..., description="Who made decision (agent_id or admin username)")
    decided_at: datetime = Field(..., description="When decision was made")
    reason: Optional[str] = Field(None, description="Reason for decision")
    notes: Optional[str] = Field(None, description="Additional notes")


class PartnershipMetrics(BaseModel):
    """Partnership system metrics."""

    total_requests: int = Field(..., ge=0, description="Total requests all-time")
    total_approvals: int = Field(..., ge=0, description="Total approved")
    total_rejections: int = Field(..., ge=0, description="Total rejected")
    total_deferrals: int = Field(..., ge=0, description="Total deferred")
    pending_count: int = Field(..., ge=0, description="Currently pending")
    approval_rate_percent: float = Field(..., ge=0.0, le=100.0, description="Approval rate percentage")
    rejection_rate_percent: float = Field(..., ge=0.0, le=100.0, description="Rejection rate percentage")
    deferral_rate_percent: float = Field(..., ge=0.0, le=100.0, description="Deferral rate percentage")
    avg_pending_hours: float = Field(..., ge=0.0, description="Average hours requests are pending")
    oldest_pending_hours: float = Field(0.0, ge=0.0, description="Age of oldest pending request")
    critical_count: int = Field(0, ge=0, description="Requests in critical aging status")


class PartnershipHistory(BaseModel):
    """Historical partnership decisions for a user."""

    user_id: str = Field(..., description="User ID")
    total_requests: int = Field(..., ge=0, description="Total requests by this user")
    outcomes: List[PartnershipOutcome] = Field(..., description="All past outcomes")
    current_status: str = Field(..., description="Current partnership status (pending/approved/none)")
    last_request_at: Optional[datetime] = Field(None, description="When last request was made")
    last_decision_at: Optional[datetime] = Field(None, description="When last decision was made")


# Metrics Collection Input Schemas


class PartnershipCounters(BaseModel):
    """Partnership counters for metrics collection."""

    requests: int = Field(..., ge=0, description="Total partnership requests")
    approvals: int = Field(..., ge=0, description="Total approvals")
    rejections: int = Field(..., ge=0, description="Total rejections")
    pending_count: int = Field(..., ge=0, description="Currently pending")


class DecayCounters(BaseModel):
    """Decay protocol counters for metrics collection."""

    total_initiated: int = Field(..., ge=0, description="Total decays initiated")
    completed: int = Field(..., ge=0, description="Decays completed")
    active_count: int = Field(..., ge=0, description="Currently active decays")


class OperationalCounters(BaseModel):
    """Operational counters for metrics collection."""

    consent_checks: int = Field(..., ge=0, description="Consent status checks")
    consent_grants: int = Field(..., ge=0, description="Consent grants/updates")
    consent_revokes: int = Field(..., ge=0, description="Consent revocations")
    expired_cleanups: int = Field(..., ge=0, description="Cleanup operations")
    tool_executions: int = Field(..., ge=0, description="Tool executions")
    tool_failures: int = Field(..., ge=0, description="Tool failures")


# API Response Schemas


class ConsentStatusResponse(BaseModel):
    """Response for consent status endpoint."""

    has_consent: bool = Field(..., description="Whether consent exists")
    user_id: str = Field(..., description=USER_ID_DESC)
    stream: Optional[str] = Field(None, description=CURRENT_STREAM_DESC)
    granted_at: Optional[str] = Field(None, description="When consent was granted (ISO format)")
    expires_at: Optional[str] = Field(None, description="When consent expires (ISO format)")
    message: Optional[str] = Field(None, description="Additional message if no consent")


class ConsentRecordResponse(BaseModel):
    """Individual consent record for query responses."""

    id: str = Field(..., description="Consent record ID")
    user_id: str = Field(..., description=USER_ID_DESC)
    status: str = Field(..., description="Consent status (ACTIVE/REVOKED/etc)")
    scope: str = Field(..., description="Consent scope")
    purpose: str = Field(..., description="Purpose of consent")
    granted_at: Optional[str] = Field(None, description="When granted (ISO format)")
    expires_at: Optional[str] = Field(None, description="When expires (ISO format)")
    metadata: dict[str, object] = Field(default_factory=dict, description="Additional metadata")


class ConsentQueryResponse(BaseModel):
    """Response for consent query endpoint."""

    consents: list[ConsentRecordResponse] = Field(..., description="List of consent records")
    total: int = Field(..., ge=0, description="Total number of records")


class StreamMetadata(BaseModel):
    """Metadata for a consent stream."""

    name: str = Field(..., description="Display name")
    description: str = Field(..., description="Stream description")
    duration_days: Optional[int] = Field(None, description="Duration in days (None = indefinite)")
    auto_forget: bool = Field(default=False, description="Whether stream auto-forgets")
    learning_enabled: bool = Field(default=False, description="Whether learning is enabled")
    identity_removed: bool = Field(default=False, description="Whether identity is removed")
    requires_categories: bool = Field(default=False, description="Whether categories are required")


class ConsentStreamsResponse(BaseModel):
    """Response for consent streams endpoint."""

    streams: dict[str, StreamMetadata] = Field(..., description="Available consent streams")
    default: str = Field(..., description="Default stream value")


class CategoryMetadata(BaseModel):
    """Metadata for a consent category."""

    name: str = Field(..., description="Display name")
    description: str = Field(..., description="Category description")


class ConsentCategoriesResponse(BaseModel):
    """Response for consent categories endpoint."""

    categories: dict[str, CategoryMetadata] = Field(..., description="Available consent categories")


class PartnershipStatusResponse(BaseModel):
    """Response for partnership status check."""

    current_stream: str = Field(..., description=CURRENT_STREAM_DESC)
    partnership_status: str = Field(..., description="Partnership request status")
    message: str = Field(..., description="Status message")


class ConsentCleanupResponse(BaseModel):
    """Response for consent cleanup operation."""

    cleaned: int = Field(..., ge=0, description="Number of records cleaned")
    message: str = Field(..., description="Cleanup result message")


class DSARInitiateResponse(BaseModel):
    """Response for DSAR initiation."""

    request_id: str = Field(..., description="DSAR request identifier")
    user_id: str = Field(..., description=USER_ID_DESC)
    request_type: str = Field(..., description="Type of DSAR request")
    status: str = Field(..., description="Request status")
    export_data: dict[str, object] = Field(..., description="Exported data")


class DSARStatusResponse(BaseModel):
    """Response for DSAR status check."""

    request_id: str = Field(..., description="DSAR request identifier")
    user_id: str = Field(..., description=USER_ID_DESC)
    status: str = Field(..., description="Request status")
    message: str = Field(..., description="Status message")
