"""
LLM System route schemas - Request/Response models for /system/llm/* endpoints.

These schemas expose the full LLMBus runtime capabilities:
- Bus-level status and metrics
- Per-provider status with circuit breaker state
- Distribution strategy management
- Circuit breaker management (reset, config)
"""

from datetime import datetime
from enum import Enum
from typing import Any, List, Optional

from pydantic import BaseModel, Field, field_serializer

from ciris_engine.utils.serialization import serialize_timestamp

# ============================================================================
# Enums
# ============================================================================


class DistributionStrategy(str, Enum):
    """LLMBus distribution strategy for selecting providers."""

    ROUND_ROBIN = "round_robin"
    LATENCY_BASED = "latency_based"
    RANDOM = "random"
    LEAST_LOADED = "least_loaded"


class CircuitBreakerState(str, Enum):
    """Circuit breaker state."""

    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Service disabled due to failures
    HALF_OPEN = "half_open"  # Testing recovery


class ProviderPriority(str, Enum):
    """Provider priority levels."""

    CRITICAL = "critical"  # 0 - Always try first
    HIGH = "high"  # 1 - Primary providers
    NORMAL = "normal"  # 2 - Standard providers
    LOW = "low"  # 3 - Use when others unavailable
    FALLBACK = "fallback"  # 9 - Last resort


# ============================================================================
# Circuit Breaker Schemas
# ============================================================================


class CircuitBreakerConfig(BaseModel):
    """Circuit breaker configuration (mutable at runtime)."""

    failure_threshold: int = Field(5, description="Failures before opening")
    recovery_timeout_seconds: float = Field(10.0, description="Time in OPEN before HALF_OPEN")
    success_threshold: int = Field(3, description="Successes in HALF_OPEN to close")
    timeout_duration_seconds: float = Field(30.0, description="Request timeout")


class CircuitBreakerStatus(BaseModel):
    """Full circuit breaker status for a provider."""

    state: CircuitBreakerState = Field(CircuitBreakerState.CLOSED, description="Current CB state")
    failure_count: int = Field(0, description="Current window failure count")
    success_count: int = Field(0, description="Current window success count")
    total_calls: int = Field(0, description="Lifetime call count")
    total_failures: int = Field(0, description="Lifetime failure count")
    total_successes: int = Field(0, description="Lifetime success count")
    success_rate: float = Field(1.0, description="Success rate 0.0-1.0")
    consecutive_failures: int = Field(0, description="Current consecutive failures")
    recovery_attempts: int = Field(0, description="Times entered HALF_OPEN")
    state_transitions: int = Field(0, description="Total state changes")
    time_in_open_state_seconds: float = Field(0.0, description="Cumulative time in OPEN")
    last_failure_age_seconds: Optional[float] = Field(None, description="Seconds since last failure")
    config: CircuitBreakerConfig = Field(default_factory=CircuitBreakerConfig, description="CB configuration")


# ============================================================================
# Provider Status Schemas
# ============================================================================


class ProviderMetrics(BaseModel):
    """Runtime metrics for an LLM provider."""

    total_requests: int = Field(0, description="Total requests handled")
    failed_requests: int = Field(0, description="Total failures")
    failure_rate: float = Field(0.0, description="Failure rate 0.0-1.0")
    average_latency_ms: float = Field(0.0, description="Average response latency")
    consecutive_failures: int = Field(0, description="Current consecutive failures")
    last_request_time: Optional[datetime] = Field(None, description="Last request timestamp")
    last_failure_time: Optional[datetime] = Field(None, description="Last failure timestamp")
    is_rate_limited: bool = Field(False, description="Currently in rate limit cooldown")
    rate_limit_cooldown_remaining_seconds: Optional[float] = Field(None, description="Seconds remaining in cooldown")

    @field_serializer("last_request_time", "last_failure_time")
    def serialize_times(self, dt: Optional[datetime], _info: Any) -> Optional[str]:
        return serialize_timestamp(dt, _info) if dt else None


class LLMProviderStatus(BaseModel):
    """Full status for an LLM provider including metrics and CB state."""

    name: str = Field(..., description="Provider name/identifier")
    healthy: bool = Field(..., description="Overall health status")
    enabled: bool = Field(True, description="Whether provider is enabled")
    priority: ProviderPriority = Field(ProviderPriority.NORMAL, description="Provider priority")
    metrics: ProviderMetrics = Field(default_factory=ProviderMetrics, description="Runtime metrics")
    circuit_breaker: CircuitBreakerStatus = Field(
        default_factory=CircuitBreakerStatus, description="Circuit breaker status"
    )


# ============================================================================
# Bus Status Schemas
# ============================================================================


class LLMBusStatusResponse(BaseModel):
    """Full LLMBus status including aggregate metrics."""

    distribution_strategy: DistributionStrategy = Field(..., description="Current distribution strategy")
    total_requests: int = Field(0, description="Total requests across all providers")
    failed_requests: int = Field(0, description="Total failures across all providers")
    average_latency_ms: float = Field(0.0, description="Average latency across all providers")
    error_rate: float = Field(0.0, description="Overall error rate 0.0-1.0")
    providers_total: int = Field(0, description="Total registered providers")
    providers_available: int = Field(0, description="Healthy providers (CB not OPEN)")
    providers_rate_limited: int = Field(0, description="Providers in rate limit cooldown")
    circuit_breakers_closed: int = Field(0, description="CBs in CLOSED state")
    circuit_breakers_open: int = Field(0, description="CBs in OPEN state")
    circuit_breakers_half_open: int = Field(0, description="CBs in HALF_OPEN state")
    uptime_seconds: float = Field(0.0, description="Bus uptime")
    timestamp: datetime = Field(..., description="Status timestamp")

    @field_serializer("timestamp")
    def serialize_ts(self, timestamp: datetime, _info: Any) -> Optional[str]:
        return serialize_timestamp(timestamp, _info)


class LLMProvidersResponse(BaseModel):
    """List of all LLM providers with their status."""

    providers: List[LLMProviderStatus] = Field(default_factory=list, description="All providers")
    total_count: int = Field(0, description="Total provider count")


# ============================================================================
# Request/Response Schemas for Mutations
# ============================================================================


class DistributionStrategyUpdateRequest(BaseModel):
    """Request to update the distribution strategy."""

    strategy: DistributionStrategy = Field(..., description="New distribution strategy")


class DistributionStrategyUpdateResponse(BaseModel):
    """Response from updating the distribution strategy."""

    success: bool = Field(..., description="Whether update succeeded")
    previous_strategy: DistributionStrategy = Field(..., description="Previous strategy")
    new_strategy: DistributionStrategy = Field(..., description="New strategy")
    message: str = Field(..., description="Status message")


class CircuitBreakerResetRequest(BaseModel):
    """Request to reset a circuit breaker."""

    force: bool = Field(False, description="Force reset even if CB is healthy")


class CircuitBreakerResetResponse(BaseModel):
    """Response from resetting a circuit breaker."""

    success: bool = Field(..., description="Whether reset succeeded")
    provider_name: str = Field(..., description="Provider that was reset")
    previous_state: CircuitBreakerState = Field(..., description="State before reset")
    new_state: CircuitBreakerState = Field(..., description="State after reset")
    message: str = Field(..., description="Status message")


class CircuitBreakerConfigUpdateRequest(BaseModel):
    """Request to update circuit breaker configuration."""

    failure_threshold: Optional[int] = Field(None, description="Failures before opening")
    recovery_timeout_seconds: Optional[float] = Field(None, description="Time in OPEN before HALF_OPEN")
    success_threshold: Optional[int] = Field(None, description="Successes in HALF_OPEN to close")
    timeout_duration_seconds: Optional[float] = Field(None, description="Request timeout")


class CircuitBreakerConfigUpdateResponse(BaseModel):
    """Response from updating circuit breaker configuration."""

    success: bool = Field(..., description="Whether update succeeded")
    provider_name: str = Field(..., description="Provider that was updated")
    previous_config: CircuitBreakerConfig = Field(..., description="Config before update")
    new_config: CircuitBreakerConfig = Field(..., description="Config after update")
    message: str = Field(..., description="Status message")


class ProviderEnableRequest(BaseModel):
    """Request to enable/disable a provider."""

    enabled: bool = Field(..., description="Whether to enable the provider")


class ProviderEnableResponse(BaseModel):
    """Response from enabling/disabling a provider."""

    success: bool = Field(..., description="Whether operation succeeded")
    provider_name: str = Field(..., description="Provider that was modified")
    enabled: bool = Field(..., description="New enabled state")
    message: str = Field(..., description="Status message")


class ProviderPriorityUpdateRequest(BaseModel):
    """Request to update a provider's priority."""

    priority: ProviderPriority = Field(..., description="New priority level")


class ProviderPriorityUpdateResponse(BaseModel):
    """Response from updating a provider's priority."""

    success: bool = Field(..., description="Whether update succeeded")
    provider_name: str = Field(..., description="Provider that was updated")
    previous_priority: ProviderPriority = Field(..., description="Previous priority")
    new_priority: ProviderPriority = Field(..., description="New priority")
    message: str = Field(..., description="Status message")


class ProviderDeleteResponse(BaseModel):
    """Response from deleting/unregistering a provider."""

    success: bool = Field(..., description="Whether delete succeeded")
    provider_name: str = Field(..., description="Provider that was deleted")
    message: str = Field(..., description="Status message")


class AddProviderRequest(BaseModel):
    """Request to add a new provider to the LLM Bus.

    Used primarily for registering discovered local inference servers.
    """

    provider_id: str = Field(..., description="Provider type: openai, anthropic, local, etc.")
    name: Optional[str] = Field(None, description="Display name (auto-generated if not provided)")
    base_url: str = Field(..., description="Base URL for the provider API")
    model: Optional[str] = Field(None, description="Default model to use")
    api_key: Optional[str] = Field(None, description="API key (empty for local servers)")
    priority: ProviderPriority = Field(ProviderPriority.FALLBACK, description="Provider priority")
    enabled: bool = Field(True, description="Whether provider is enabled")


class AddProviderResponse(BaseModel):
    """Response from adding a new provider."""

    success: bool = Field(..., description="Whether provider was added")
    provider_name: str = Field(..., description="Name of the new provider")
    provider_id: str = Field(..., description="Provider type ID")
    base_url: str = Field(..., description="Base URL that was configured")
    priority: ProviderPriority = Field(..., description="Assigned priority")
    message: str = Field(..., description="Status message")


class CirisServicesStatusResponse(BaseModel):
    """Response for CIRIS services status."""

    disabled: bool = Field(..., description="Whether CIRIS services are disabled")
    message: str = Field(..., description="Status message")
