"""
Schemas for runtime adapter management.

These replace all Dict[str, Any] usage in adapter_manager.py.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field

from ciris_engine.schemas.adapters.tools import ToolInfo

# Constants for field descriptions to avoid duplication
ADAPTER_ID_DESC = "Adapter ID"
ADAPTER_TYPE_DESC = "Adapter type"
IS_RUNNING_DESC = "Whether adapter is running"


class AdapterConfig(BaseModel):
    """Configuration for an adapter.

    This schema supports two configuration approaches:
    1. Simple adapters (CLI, API, Discord): Use `settings` dict with flat primitives
    2. Complex adapters (MCP): Use `adapter_config` dict for nested structures

    The adapter's own typed config class (e.g., MCPAdapterConfig, DiscordAdapterConfig)
    performs full validation when the adapter is loaded.
    """

    adapter_type: str = Field(..., description="Type of adapter (cli, api, discord, etc.)")
    enabled: bool = Field(True, description="Whether adapter is enabled")
    settings: Dict[str, Optional[Union[str, int, float, bool, List[str]]]] = Field(
        default_factory=dict,
        description="Simple adapter settings (flat primitives only). "
        "Use adapter_config for complex nested configurations.",
    )
    adapter_config: Optional[Dict[str, Any]] = Field(
        None,
        description="Full adapter configuration for adapters requiring nested objects "
        "(e.g., MCP servers with bus_bindings). Validated by the adapter's typed config class.",
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


class RuntimeAdapterStatus(BaseModel):
    """Status of a single adapter."""

    adapter_id: str = Field(..., description="Unique " + ADAPTER_ID_DESC)
    adapter_type: str = Field(..., description="Type of adapter")
    is_running: bool = Field(..., description=IS_RUNNING_DESC)
    loaded_at: datetime = Field(..., description="When adapter was loaded")
    services_registered: List[str] = Field(default_factory=list, description="Services registered by adapter")
    config_params: AdapterConfig = Field(..., description="Adapter configuration")
    metrics: Optional[AdapterMetrics] = Field(None, description="Adapter metrics")
    last_activity: Optional[datetime] = Field(None, description="Last activity timestamp")
    tools: Optional[List[ToolInfo]] = Field(None, description="Tools provided by adapter")


class AdapterListResponse(BaseModel):
    """Response containing list of adapters."""

    adapters: List[RuntimeAdapterStatus] = Field(..., description="List of adapter statuses")
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


class ModuleConfigParameter(BaseModel):
    """Configuration parameter definition for a module."""

    name: str = Field(..., description="Parameter name")
    param_type: str = Field(..., description="Parameter type (string, integer, float, boolean, array)")
    default: Optional[Union[str, int, float, bool, List[str]]] = Field(None, description="Default value")
    description: str = Field(..., description="Parameter description")
    env_var: Optional[str] = Field(None, description="Environment variable name")
    required: bool = Field(True, description="Whether parameter is required")
    sensitivity: Optional[str] = Field(None, description="Sensitivity level (e.g., 'HIGH' for secrets)")


class ModuleTypeInfo(BaseModel):
    """Information about an available module/adapter type."""

    module_id: str = Field(..., description="Unique module identifier (e.g., 'api', 'mcp_client')")
    name: str = Field(..., description="Human-readable module name")
    version: str = Field(..., description="Module version")
    description: str = Field(..., description="Module description")
    author: str = Field(..., description="Module author")
    module_source: str = Field(..., description="Source: 'core' for built-in or 'modular' for plugin")
    service_types: List[str] = Field(
        default_factory=list, description="Service types provided (e.g., TOOL, COMMUNICATION)"
    )
    capabilities: List[str] = Field(default_factory=list, description="Capabilities provided")
    configuration_schema: List[ModuleConfigParameter] = Field(
        default_factory=list, description="Configuration parameters and their types"
    )
    requires_external_deps: bool = Field(False, description="Whether module requires external packages")
    external_dependencies: Dict[str, str] = Field(
        default_factory=dict, description="External package dependencies with version constraints"
    )
    is_mock: bool = Field(False, description="Whether this is a mock/test module")
    safe_domain: Optional[str] = Field(None, description="Safe domain classification")
    prohibited: List[str] = Field(default_factory=list, description="Prohibited use cases")
    metadata: Optional[Dict[str, Union[str, bool, int, List[str]]]] = Field(None, description="Additional metadata")
    # Platform requirements for this adapter
    platform_requirements: List[str] = Field(
        default_factory=list, description="Platform requirements (e.g., 'android_play_integrity', 'google_native_auth')"
    )
    platform_requirements_rationale: Optional[str] = Field(
        None, description="Explanation of why platform requirements exist"
    )
    platform_available: bool = Field(True, description="Whether this adapter is available on the current platform")


class ModuleTypesResponse(BaseModel):
    """Response containing all available module types."""

    core_modules: List[ModuleTypeInfo] = Field(..., description="Built-in core adapters")
    adapters: List[ModuleTypeInfo] = Field(..., description="Dynamically loaded adapters")
    total_core: int = Field(..., description="Total number of core modules")
    total_adapters: int = Field(..., description="Total number of adapters")
