"""
Secrets service schemas.

Provides typed schemas in secrets service operations.
"""

from datetime import datetime, timezone
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class SecretContext(BaseModel):
    """Context for secret operations."""

    operation: str = Field(..., description="Operation being performed")
    channel_id: Optional[str] = Field(None, description="Channel context")
    user_id: Optional[str] = Field(None, description="User context")
    request_id: Optional[str] = Field(None, description="Request ID for tracking")
    metadata: Dict[str, str] = Field(default_factory=dict, description="Additional metadata")


class ConfigUpdate(BaseModel):
    """Configuration update for secrets filters."""

    action: str = Field(..., description="Update action: add, remove, update")
    filter_type: str = Field(..., description="Type of filter")
    filter_name: Optional[str] = Field(None, description="Name of filter")
    patterns: Optional[List[str]] = Field(None, description="Patterns to add/update")
    enabled: Optional[bool] = Field(None, description="Enable/disable filter")
    metadata: Dict[str, str] = Field(default_factory=dict, description="Additional settings")


class SecretAccessLog(BaseModel):
    """Log entry for secret access."""

    secret_id: str = Field(..., description="Secret UUID")
    operation: str = Field(..., description="Operation performed")
    requester_id: str = Field(..., description="Who requested access")
    granted: bool = Field(..., description="Whether access was granted")
    reason: Optional[str] = Field(None, description="Reason for grant/denial")
    context: SecretContext = Field(..., description="Access context")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Access time")


class SecretFilterStatus(BaseModel):
    """Status of a secret filter."""

    filter_name: str = Field(..., description="Filter name")
    filter_type: str = Field(..., description="Filter type")
    enabled: bool = Field(..., description="Whether filter is active")
    pattern_count: int = Field(..., description="Number of patterns")
    last_match: Optional[datetime] = Field(None, description="Last match time")
    match_count: int = Field(0, description="Total matches")
    metadata: Dict[str, str] = Field(default_factory=dict, description="Filter metadata")


class SecretsServiceStats(BaseModel):
    """Statistics for the secrets service."""

    total_secrets: int = Field(0, description="Total secrets stored")
    active_filters: int = Field(0, description="Number of active filters")
    filter_matches_today: int = Field(0, description="Filter matches today")
    last_filter_update: Optional[datetime] = Field(None, description="Last filter update time")
    encryption_enabled: bool = Field(True, description="Whether encryption is enabled")
