"""
Specific type models to replace Dict[str, Any] usage in models.py.

These models provide type-safe alternatives for various contexts and metadata.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, field_serializer


# Node Attribute Models
class BaseAttributes(BaseModel):
    """Base attributes for graph nodes."""

    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: Optional[datetime] = Field(None, description="Last update timestamp")
    tags: List[str] = Field(default_factory=list, description="Associated tags")

    model_config = ConfigDict(extra="allow")

    @field_serializer("created_at", "updated_at")
    def serialize_datetime(self, dt: Optional[datetime], _info: Any) -> Optional[str]:
        return dt.isoformat() if dt else None


class MemoryAttributes(BaseAttributes):
    """Attributes for memory nodes."""

    content: str = Field(..., description="Memory content")
    importance: float = Field(default=0.5, ge=0.0, le=1.0, description="Importance score")
    source: Optional[str] = Field(None, description="Source of memory")
    related_to: List[str] = Field(default_factory=list, description="Related node IDs")


class ConfigAttributes(BaseAttributes):
    """Attributes for configuration nodes."""

    value: Union[str, int, float, bool, List[Any], Dict[str, Any]] = Field(..., description="Config value")
    description: Optional[str] = Field(None, description="Config description")
    sensitive: bool = Field(default=False, description="Whether value is sensitive")
    validator: Optional[str] = Field(None, description="Validation rule")


class TelemetryAttributes(BaseAttributes):
    """Attributes for telemetry nodes."""

    metric_name: str = Field(..., description="Metric name")
    value: float = Field(..., description="Metric value")
    unit: Optional[str] = Field(None, description="Unit of measurement")
    service: Optional[str] = Field(None, description="Source service")


# Result Models
class ProcessorResult(BaseModel):
    """Result from processor operations."""

    status: str = Field(..., description="Operation status: success|failure|partial")
    message: Optional[str] = Field(None, description="Result message")
    affected_items: int = Field(default=0, description="Number of items affected")
    details: Dict[str, str] = Field(default_factory=dict, description="Additional details")

    model_config = ConfigDict(extra="forbid")


# Config Models
class ConfigParam(BaseModel):
    """Individual configuration parameter."""

    name: str = Field(..., description="Parameter name")
    value: Union[str, int, float, bool, List[Any]] = Field(..., description="Parameter value")
    type: str = Field(..., description="Value type")
    required: bool = Field(default=False, description="Whether required")

    model_config = ConfigDict(extra="forbid")


class AdapterConfig(BaseModel):
    """Adapter configuration parameters."""

    adapter_type: str = Field(..., description="Type of adapter")
    connection_params: Dict[str, ConfigParam] = Field(default_factory=dict, description="Connection parameters")
    feature_flags: Dict[str, bool] = Field(default_factory=dict, description="Feature toggles")
    limits: Dict[str, int] = Field(default_factory=dict, description="Resource limits")

    model_config = ConfigDict(extra="allow")


# Lineage Models
class LineageInfo(BaseModel):
    """Agent lineage information."""

    version: str = Field(..., description="Agent version")
    commit_hash: Optional[str] = Field(None, description="Git commit hash")
    build_date: Optional[datetime] = Field(None, description="Build timestamp")
    parent_version: Optional[str] = Field(None, description="Parent version")
    environment: str = Field(default="production", description="Deployment environment")
    features: List[str] = Field(default_factory=list, description="Enabled features")

    @field_serializer("build_date")
    def serialize_datetime(self, dt: Optional[datetime], _info: Any) -> Optional[str]:
        return dt.isoformat() if dt else None


# Processor State Models
class CognitiveStateInfo(BaseModel):
    """Information about cognitive state."""

    current_state: str = Field(..., description="Current state name")
    entered_at: datetime = Field(..., description="When state was entered")
    duration_seconds: float = Field(..., description="Time in current state")
    previous_state: Optional[str] = Field(None, description="Previous state")
    transition_reason: Optional[str] = Field(None, description="Reason for transition")

    @field_serializer("entered_at")
    def serialize_datetime(self, dt: Optional[datetime], _info: Any) -> Optional[str]:
        return dt.isoformat() if dt else None


class ProcessorStateInfo(BaseModel):
    """Detailed processor state information."""

    cognitive: CognitiveStateInfo = Field(..., description="Cognitive state info")
    performance: Dict[str, float] = Field(default_factory=dict, description="Performance metrics")
    queue_sizes: Dict[str, int] = Field(default_factory=dict, description="Queue sizes by priority")
    active_handlers: List[str] = Field(default_factory=list, description="Active handler names")

    model_config = ConfigDict(extra="allow")


# Configuration Snapshot Models
class SystemConfiguration(BaseModel):
    """System configuration snapshot."""

    profile: str = Field(..., description="Active configuration profile")
    environment: str = Field(..., description="Deployment environment")
    features: Dict[str, bool] = Field(default_factory=dict, description="Feature flags")
    limits: Dict[str, Union[int, float]] = Field(default_factory=dict, description="System limits")
    integrations: List[str] = Field(default_factory=list, description="Active integrations")

    model_config = ConfigDict(extra="allow")


# Service Metadata Models
class ServiceMetadata(BaseModel):
    """Service metadata information."""

    version: Optional[str] = Field(None, description="Service version")
    uptime_seconds: float = Field(default=0.0, description="Service uptime")
    last_restart: Optional[datetime] = Field(None, description="Last restart time")
    restart_count: int = Field(default=0, description="Number of restarts")
    error_count: int = Field(default=0, description="Total errors")
    success_rate: float = Field(default=1.0, ge=0.0, le=1.0, description="Success rate")
    average_response_ms: Optional[float] = Field(None, description="Average response time")

    @field_serializer("last_restart")
    def serialize_datetime(self, dt: Optional[datetime], _info: Any) -> Optional[str]:
        return dt.isoformat() if dt else None


# Context Models
class BaseContext(BaseModel):
    """Base context for operations."""

    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Context timestamp")
    request_id: Optional[str] = Field(None, description="Request identifier")
    trace_id: Optional[str] = Field(None, description="Trace identifier")

    model_config = ConfigDict(extra="allow")

    @field_serializer("timestamp")
    def serialize_datetime(self, dt: Optional[datetime], _info: Any) -> Optional[str]:
        return dt.isoformat() if dt else None


class DeferralContext(BaseContext):
    """Context for deferral operations."""

    original_thought_id: str = Field(..., description="Original thought ID")
    authority_id: str = Field(..., description="Authority creating deferral")
    priority: str = Field(..., description="Deferral priority: high|medium|low")
    reason_code: str = Field(..., description="Standardized reason code")
    additional_info: Dict[str, str] = Field(default_factory=dict, description="Additional context")


class AuditContext(BaseContext):
    """Context for audit entries."""

    entity_id: Optional[str] = Field(None, description="Entity being audited")
    entity_type: Optional[str] = Field(None, description="Type of entity")
    operation: Optional[str] = Field(None, description="Operation performed")
    description: Optional[str] = Field(None, description="Human-readable description")
    request_id: Optional[str] = Field(None, description="Request ID")
    correlation_id: Optional[str] = Field(None, description="Correlation ID")
    user_id: Optional[str] = Field(None, description="User who triggered action")
    ip_address: Optional[str] = Field(None, description="Client IP address")
    user_agent: Optional[str] = Field(None, description="User agent string")
    result: Optional[str] = Field(None, description="Operation result")
    error: Optional[str] = Field(None, description="Error message if failed")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Additional metadata")


# Verification Models
class VerificationDetails(BaseModel):
    """Details of verification operations."""

    algorithm: str = Field(..., description="Verification algorithm used")
    signature: Optional[str] = Field(None, description="Digital signature")
    hash_value: Optional[str] = Field(None, description="Hash value")
    certificate: Optional[str] = Field(None, description="Certificate used")

    model_config = ConfigDict(extra="forbid")


class VerificationResult(BaseModel):
    """Result of verification operation."""

    signature_valid: bool = Field(..., description="Whether signature verification passed")
    hash_chain_valid: bool = Field(..., description="Whether hash chain verification passed")
    verified_at: Union[str, datetime] = Field(..., description="Verification timestamp")
    verifier: str = Field(..., description="Verifier identifier")
    algorithm: str = Field(..., description="Verification algorithm used")
    previous_hash_match: Optional[bool] = Field(None, description="Whether previous hash matches")

    # Optional fields for compatibility
    is_valid: Optional[bool] = Field(None, description="Overall verification status")
    verified_by: Optional[str] = Field(None, description="Verifier identifier (alias)")
    details: Optional[VerificationDetails] = Field(None, description="Verification details")
    errors: List[str] = Field(default_factory=list, description="Verification errors")

    model_config = ConfigDict(extra="allow")

    @field_serializer("verified_at")
    def serialize_datetime(self, dt: Union[str, datetime, None], _info: Any) -> Optional[str]:
        if isinstance(dt, datetime):
            return dt.isoformat()
        return dt


# Thought Models
class ThoughtContent(BaseModel):
    """Content of a thought for traces."""

    thought_id: str = Field(..., description="Unique thought ID")
    content: str = Field(..., description="Thought content")
    handler: str = Field(..., description="Handler type")
    created_at: datetime = Field(..., description="Creation time")
    completed_at: Optional[datetime] = Field(None, description="Completion time")
    status: str = Field(..., description="Status: PENDING|PROCESSING|COMPLETED|FAILED")
    result: Optional[str] = Field(None, description="Processing result")
    metadata: Dict[str, str] = Field(default_factory=dict, description="Additional metadata")

    @field_serializer("created_at", "completed_at")
    def serialize_datetime(self, dt: Optional[datetime], _info: Any) -> Optional[str]:
        return dt.isoformat() if dt else None
