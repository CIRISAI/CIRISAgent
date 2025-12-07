"""
Core protocol schemas.

Type-safe schemas for core service operations.
"""

from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class LLMUsageStatistics(BaseModel):
    """Token usage statistics for LLM service."""

    total_calls: int = Field(0, description="Total number of calls made")
    failed_calls: int = Field(0, description="Number of failed calls")
    success_rate: float = Field(1.0, ge=0.0, le=1.0, description="Success rate (0-1)")

    model_config = ConfigDict(extra="forbid")


class LLMStatus(BaseModel):
    """Status information from LLM service."""

    available: bool = Field(..., description="Whether service is available")
    model: str = Field(..., description="Current model name")
    usage: LLMUsageStatistics = Field(default_factory=LLMUsageStatistics, description="Token usage statistics")
    rate_limit_remaining: Optional[int] = Field(None, description="Remaining API calls")
    response_time_avg: Optional[float] = Field(None, description="Average response time")

    model_config = ConfigDict(extra="forbid")


class NetworkQueryRequest(BaseModel):
    """Request for network query."""

    query_type: str = Field(..., description="Type of query (e.g., 'peer_discovery')")
    parameters: Dict[str, str] = Field(default_factory=dict, description="Query parameters")
    timeout: Optional[float] = Field(30.0, description="Query timeout")

    model_config = ConfigDict(extra="forbid")


class MetricDataPoint(BaseModel):
    """A single metric data point."""

    metric_name: str = Field(..., description="Name of the metric")
    value: float = Field(..., description="Metric value")
    timestamp: datetime = Field(..., description="When metric was recorded")
    tags: Dict[str, str] = Field(default_factory=dict, description="Metric tags")
    service_name: Optional[str] = Field(None, description="Service that recorded metric")

    model_config = ConfigDict(extra="forbid")


class ResourceLimits(BaseModel):
    """Resource limits and quotas."""

    max_memory_mb: Optional[int] = Field(None, description="Maximum memory in MB")
    max_cpu_percent: Optional[float] = Field(None, description="Maximum CPU percentage")
    max_disk_gb: Optional[float] = Field(None, description="Maximum disk usage in GB")
    max_api_calls_per_minute: Optional[int] = Field(None, description="API rate limit")
    max_concurrent_operations: Optional[int] = Field(None, description="Max concurrent ops")

    model_config = ConfigDict(extra="forbid")


class SecretInfo(BaseModel):
    """Information about a stored secret."""

    uuid: str = Field(..., description="Secret UUID")
    description: str = Field(..., description="Secret description")
    secret_type: str = Field(..., description="Type of secret")
    sensitivity: str = Field(..., description="Sensitivity level")
    created_at: datetime = Field(..., description="When secret was stored")
    last_accessed: Optional[datetime] = Field(None, description="Last access time")
    access_count: int = Field(0, description="Number of times accessed")
    decrypted_value: Optional[str] = Field(None, description="Decrypted value if requested")

    model_config = ConfigDict(extra="forbid")


class SecretsServiceStats(BaseModel):
    """Statistics from secrets service."""

    secrets_stored: int = Field(..., description="Total secrets in storage")
    filter_active: bool = Field(..., description="Whether filter is active")
    patterns_enabled: List[str] = Field(..., description="Enabled detection patterns")
    recent_detections: int = Field(0, description="Detections in last hour")
    storage_size_bytes: Optional[int] = Field(None, description="Storage size used")

    model_config = ConfigDict(extra="forbid")


__all__ = ["LLMStatus", "NetworkQueryRequest", "MetricDataPoint", "ResourceLimits", "SecretInfo", "SecretsServiceStats"]
