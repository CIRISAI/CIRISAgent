"""
Schemas for runtime adapter management.

These replace all Dict[str, Any] usage in adapter_manager.py.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field

# Constants for field descriptions to avoid duplication
ADAPTER_ID_DESC = "Adapter ID"
ADAPTER_TYPE_DESC = "Adapter type"
IS_RUNNING_DESC = "Whether adapter is running"


class AdapterConfig(BaseModel):
    """Configuration for an adapter."""

    adapter_type: str = Field(..., description="Type of adapter (cli, api, discord, etc.)")
    enabled: bool = Field(True, description="Whether adapter is enabled")
    settings: Dict[str, Optional[Union[str, int, float, bool, List[str]]]] = Field(
        default_factory=dict, description="Adapter-specific settings"
    )


class AdapterLoadRequest(BaseModel):
    """Request to load an adapter."""

    adapter_type: str = Field(..., description="Type of adapter to load")
    adapter_id: str = Field(..., description="Unique ID for the adapter instance")
    config: Optional[AdapterConfig] = Field(None, description="Configuration parameters")
    auto_start: bool = Field(True, description="Whether to auto-start the adapter")


class AdapterOperationResult(BaseModel):
    """Result of an adapter operation."""

    success: bool = Field(..., description="Whether operation succeeded")
    adapter_id: str = Field(..., description=ADAPTER_ID_DESC)
    adapter_type: Optional[str] = Field(None, description=ADAPTER_TYPE_DESC)
    message: Optional[str] = Field(None, description="Operation message")
    error: Optional[str] = Field(None, description="Error message if failed")
    details: Optional[Dict[str, Union[str, int, float, bool]]] = Field(None, description="Additional details")


class AdapterMetrics(BaseModel):
    """Metrics for an adapter."""

    messages_processed: int = Field(0, description="Total messages processed")
    errors_count: int = Field(0, description="Total errors")
    uptime_seconds: float = Field(0.0, description="Adapter uptime in seconds")
    last_error: Optional[str] = Field(None, description="Last error message")
    last_error_time: Optional[datetime] = Field(None, description="Last error timestamp")


class AdapterStatus(BaseModel):
    """Status of a single adapter."""

    adapter_id: str = Field(..., description="Unique " + ADAPTER_ID_DESC)
    adapter_type: str = Field(..., description="Type of adapter")
    is_running: bool = Field(..., description=IS_RUNNING_DESC)
    loaded_at: datetime = Field(..., description="When adapter was loaded")
    services_registered: List[str] = Field(default_factory=list, description="Services registered by adapter")
    config_params: AdapterConfig = Field(..., description="Adapter configuration")
    metrics: Optional[AdapterMetrics] = Field(None, description="Adapter metrics")
    last_activity: Optional[datetime] = Field(None, description="Last activity timestamp")
    tools: Optional[List[str]] = Field(None, description="Tool names provided by adapter")


class AdapterListResponse(BaseModel):
    """Response containing list of adapters."""

    adapters: List[AdapterStatus] = Field(..., description="List of adapter statuses")
    total_count: int = Field(..., description="Total number of adapters")
    running_count: int = Field(..., description="Number of running adapters")


class ServiceRegistrationInfo(BaseModel):
    """Information about a service registration."""

    service_type: str = Field(..., description="Type of service")
    provider_name: str = Field(..., description="Provider name")
    priority: str = Field(..., description="Registration priority")
    capabilities: List[str] = Field(..., description="Service capabilities")


class AdapterInfo(BaseModel):
    """Detailed information about an adapter."""

    adapter_id: str = Field(..., description=ADAPTER_ID_DESC)
    adapter_type: str = Field(..., description=ADAPTER_TYPE_DESC)
    config: AdapterConfig = Field(..., description="Adapter configuration")
    load_time: str = Field(..., description="ISO timestamp when loaded")
    is_running: bool = Field(..., description=IS_RUNNING_DESC)


class CommunicationAdapterInfo(BaseModel):
    """Information about a communication adapter."""

    adapter_id: str = Field(..., description=ADAPTER_ID_DESC)
    adapter_type: str = Field(..., description=ADAPTER_TYPE_DESC)
    is_running: bool = Field(..., description=IS_RUNNING_DESC)


class CommunicationAdapterStatus(BaseModel):
    """Status of all communication adapters."""

    total_communication_adapters: int = Field(..., description="Total count")
    running_communication_adapters: int = Field(..., description="Running count")
    communication_adapters: List[CommunicationAdapterInfo] = Field(..., description="List of adapters")
    safe_to_unload: bool = Field(..., description="Whether safe to unload")
    warning_message: Optional[str] = Field(None, description="Warning message")
