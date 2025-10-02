"""
Runtime configuration schemas for runtime control service.

Provides typed schemas for runtime control operations.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field

from ciris_engine.schemas.types import JSONDict


class AdapterConfig(BaseModel):
    """Configuration for adapter instances."""

    adapter_type: str = Field(..., description="Type of adapter")
    adapter_id: str = Field(..., description="Unique adapter identifier")
    enabled: bool = Field(True, description="Whether adapter is enabled")

    # Connection settings
    host: Optional[str] = Field(None, description="Host for network adapters")
    port: Optional[int] = Field(None, description="Port for network adapters")

    # Authentication
    auth_type: Optional[str] = Field(None, description="Authentication type")
    credentials: Optional[Dict[str, str]] = Field(None, description="Auth credentials")

    # Behavior settings
    max_retries: int = Field(3, description="Maximum retry attempts")
    timeout_seconds: float = Field(30.0, description="Operation timeout")

    # Custom settings
    custom_settings: JSONDict = Field(default_factory=dict, description="Adapter-specific settings")


class ProcessorConfig(BaseModel):
    """Configuration for processor instances."""

    processor_type: str = Field(..., description="Type of processor")
    enabled: bool = Field(True, description="Whether processor is enabled")

    # Performance settings
    max_concurrent_thoughts: int = Field(10, description="Max concurrent thoughts")
    thought_timeout_seconds: float = Field(300.0, description="Thought processing timeout")

    # Queue settings
    queue_size: int = Field(100, description="Maximum queue size")
    batch_size: int = Field(1, description="Batch processing size")

    # Custom settings
    custom_settings: JSONDict = Field(default_factory=dict, description="Processor-specific settings")


class RuntimeConfig(BaseModel):
    """Complete runtime configuration."""

    version: str = Field(..., description="Config version")
    environment: str = Field("production", description="Runtime environment")

    # Component configs
    adapters: List[AdapterConfig] = Field(default_factory=list, description="Adapter configurations")
    processors: List[ProcessorConfig] = Field(default_factory=list, description="Processor configurations")

    # Global settings
    global_timeout: float = Field(600.0, description="Global operation timeout")
    max_memory_mb: int = Field(4096, description="Maximum memory usage")

    # Feature flags
    features: Dict[str, bool] = Field(default_factory=dict, description="Feature toggles")

    # Metadata
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ServiceInfo(BaseModel):
    """Information about a registered service."""

    service_name: str = Field(..., description="Service name")
    service_type: str = Field(..., description="Service type")
    status: str = Field(..., description="Service status")
    healthy: bool = Field(..., description="Health status")

    # Capabilities
    actions: List[str] = Field(default_factory=list, description="Supported actions")
    handlers: List[str] = Field(default_factory=list, description="Registered handlers")

    # Performance
    requests_handled: int = Field(0, description="Total requests handled")
    average_latency_ms: float = Field(0.0, description="Average request latency")
    error_rate: float = Field(0.0, description="Error rate")

    # Resources
    memory_usage_mb: Optional[float] = Field(None, description="Memory usage")
    cpu_usage_percent: Optional[float] = Field(None, description="CPU usage")


class ServiceHealthReport(BaseModel):
    """Health report for services."""

    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    overall_health: str = Field(..., description="Overall health status")
    healthy_services: int = Field(..., description="Number of healthy services")
    unhealthy_services: int = Field(..., description="Number of unhealthy services")

    # Service details
    services: Dict[str, ServiceInfo] = Field(default_factory=dict, description="Service information")

    # System metrics
    system_load: float = Field(..., description="System load average")
    memory_percent: float = Field(..., description="Memory usage percentage")

    # Recent issues
    recent_errors: List[str] = Field(default_factory=list, description="Recent error messages")
    warnings: List[str] = Field(default_factory=list, description="Warning messages")
