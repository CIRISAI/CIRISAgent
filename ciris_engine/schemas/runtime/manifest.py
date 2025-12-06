"""
Service manifest schemas for typed module loading.

Provides typed schemas in service loading and module manifests.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field

from ciris_engine.schemas.runtime.enums import ServiceType
from ciris_engine.schemas.types import JSONDict


class ServicePriority(str, Enum):
    """Service priority levels for registration."""

    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    NORMAL = "NORMAL"
    LOW = "LOW"


class ServiceCapabilityDeclaration(BaseModel):
    """Declaration of a service capability."""

    name: str = Field(..., description="Capability name (e.g., 'call_llm_structured')")
    description: str = Field(..., description="Human-readable description of the capability")
    version: str = Field(default="1.0.0", description="Capability version")
    parameters: Optional[Dict[str, str]] = Field(None, description="Parameter descriptions")

    model_config = ConfigDict(extra="forbid")


class ServiceDependency(BaseModel):
    """Declaration of a service dependency."""

    service_type: ServiceType = Field(..., description="Type of service required")
    required: bool = Field(True, description="Whether this dependency is required")
    minimum_version: Optional[str] = Field(None, description="Minimum service version required")
    capabilities_required: List[str] = Field(default_factory=list, description="Required capabilities")

    model_config = ConfigDict(extra="forbid")


class ServiceDeclaration(BaseModel):
    """Declaration of a service in a manifest."""

    type: ServiceType = Field(..., description="Service type this implements")
    class_path: str = Field(..., description="Full class path (e.g., 'mock_llm.service.MockLLMService')", alias="class")
    priority: ServicePriority = Field(ServicePriority.NORMAL, description="Service priority level")
    capabilities: List[str] = Field(default_factory=list, description="List of capability names")

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class ModuleInfo(BaseModel):
    """Module-level information."""

    name: str = Field(..., description="Module name")
    version: str = Field(..., description="Module version")
    description: str = Field(..., description="Module description")
    author: str = Field(..., description="Module author")
    is_mock: bool = Field(False, description="Whether this is a MOCK module", alias="MOCK")
    license: Optional[str] = Field(None, description="Module license")
    homepage: Optional[str] = Field(None, description="Module homepage URL")
    safe_domain: Optional[bool] = Field(None, description="Whether module operates in safe domains")

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class LegacyDependencies(BaseModel):
    """Legacy dependency format for backward compatibility."""

    protocols: List[str] = Field(default_factory=list, description="Required protocols")
    schemas: List[str] = Field(default_factory=list, description="Required schemas")
    external: Optional[Dict[str, str]] = Field(None, description="External package dependencies")

    model_config = ConfigDict(extra="forbid")


class ConfigurationParameter(BaseModel):
    """Configuration parameter definition."""

    type: str = Field(..., description="Parameter type (integer, float, string, boolean)")
    default: Optional[Union[int, float, str, bool]] = Field(None, description="Default value (optional)")
    description: str = Field(..., description="Parameter description")
    env: Optional[str] = Field(None, description="Environment variable name")
    sensitivity: Optional[str] = Field(None, description="Sensitivity level (e.g., 'HIGH' for secrets)")
    required: bool = Field(True, description="Whether this parameter is required")

    model_config = ConfigDict(extra="forbid")


class DiscoveredInstance(BaseModel):
    """A discovered service instance (e.g., Home Assistant)."""

    name: str = Field(..., description="Instance name")
    host: str = Field(..., description="Host address")
    port: int = Field(..., description="Port number")
    addresses: List[str] = Field(default_factory=list, description="List of IP addresses")
    base_url: Optional[str] = Field(None, description="Base URL for API access")
    version: Optional[str] = Field(None, description="Service version")
    location_name: Optional[str] = Field(None, description="Location name if available")
    uuid: Optional[str] = Field(None, description="Unique identifier")
    requires_api_password: bool = Field(False, description="Whether API password is required")

    model_config = ConfigDict(extra="forbid")


class SelectionOption(BaseModel):
    """An option for user selection."""

    id: str = Field(..., description="Option ID")
    name: str = Field(..., description="Option name")
    description: Optional[str] = Field(None, description="Option description")
    metadata: Optional[Dict[str, str]] = Field(None, description="String metadata only")

    model_config = ConfigDict(extra="forbid")


class OAuthConfig(BaseModel):
    """OAuth configuration for a module."""

    provider_name: str = Field(..., description="Provider name registered via /v1/auth/oauth/providers")
    authorization_path: str = Field(..., description="Authorization endpoint path (e.g., '/auth/authorize')")
    token_path: str = Field(..., description="Token endpoint path (e.g., '/auth/token')")
    client_id_source: Literal["static", "indieauth"] = Field(..., description="How to obtain client ID")
    scopes: List[str] = Field(default_factory=list, description="OAuth scopes to request")
    pkce_required: bool = Field(True, description="Whether PKCE is required")

    model_config = ConfigDict(extra="forbid")


class ConfigurationStep(BaseModel):
    """A step in the configuration workflow."""

    step_id: str = Field(..., description="Unique step identifier")
    step_type: Literal["discovery", "oauth", "select", "confirm"] = Field(..., description="Type of configuration step")
    title: str = Field(..., description="Step title for UI")
    description: str = Field(..., description="Step description for UI")
    discovery_method: Optional[str] = Field(None, description="Discovery method name (for discovery steps)")
    oauth_config: Optional[OAuthConfig] = Field(None, description="OAuth configuration (for oauth steps)")
    depends_on: List[str] = Field(default_factory=list, description="Step IDs this depends on")

    model_config = ConfigDict(extra="forbid")


class InteractiveConfiguration(BaseModel):
    """Interactive configuration definition."""

    required: bool = Field(False, description="Whether configuration is required for module to function")
    workflow_type: Literal["wizard", "discovery_then_config"] = Field(..., description="Type of configuration workflow")
    steps: List[ConfigurationStep] = Field(..., description="Configuration steps in order")
    completion_method: str = Field(..., description="Method name to call on completion")

    model_config = ConfigDict(extra="forbid")


class ServiceManifest(BaseModel):
    """Complete service module manifest."""

    module: ModuleInfo = Field(..., description="Module information")
    services: List[ServiceDeclaration] = Field(default_factory=list, description="Services provided")
    capabilities: List[str] = Field(default_factory=list, description="Global capabilities list")
    dependencies: Optional[LegacyDependencies] = Field(None, description="Legacy dependencies format")
    configuration: Optional[Dict[str, ConfigurationParameter]] = Field(None, description="Configuration parameters")
    exports: Optional[Dict[str, Union[str, List[str]]]] = Field(
        None, description="Exported components (string or list)"
    )
    metadata: Optional[JSONDict] = Field(None, description="Additional metadata")
    requirements: List[str] = Field(default_factory=list, description="Python package requirements")
    prohibited_sensors: Optional[List[str]] = Field(None, description="Prohibited sensor types for sensor modules")
    interactive_config: Optional[InteractiveConfiguration] = Field(
        None, description="Interactive configuration workflow definition"
    )

    model_config = ConfigDict(extra="forbid")

    def validate_manifest(self) -> List[str]:
        """Validate manifest consistency.

        Returns:
            List of validation errors (empty if valid)
        """
        errors = []

        # Global capabilities are just a list in the current format
        # Service capabilities can reference these or define their own

        # Check for MOCK module warnings
        if self.module.is_mock:
            for service in self.services:
                if service.priority == ServicePriority.CRITICAL:
                    # MOCK modules often use CRITICAL priority to override real services
                    # This is actually allowed but worth noting
                    pass

        # Validate service types
        for service in self.services:
            try:
                # Ensure service type is valid
                _ = service.type
            except Exception as e:
                errors.append(f"Invalid service type in {service.class_path}: {e}")

        return errors


class ServiceMetadata(BaseModel):
    """Runtime metadata about a loaded service."""

    service_type: ServiceType = Field(..., description="Type of this service")
    module_name: str = Field(..., description="Module this service came from")
    class_name: str = Field(..., description="Service class name")
    version: str = Field(..., description="Service version")
    is_mock: bool = Field(False, description="Whether this is a MOCK service")
    loaded_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    capabilities: List[str] = Field(default_factory=list, description="Active capabilities")
    priority: ServicePriority = Field(ServicePriority.NORMAL, description="Service priority")
    health_status: str = Field("unknown", description="Current health status")

    model_config = ConfigDict(extra="forbid")


class ModuleLoadResult(BaseModel):
    """Result of loading a module."""

    module_name: str = Field(..., description="Module that was loaded")
    success: bool = Field(..., description="Whether load succeeded")
    services_loaded: List[ServiceMetadata] = Field(default_factory=list, description="Services that were loaded")
    errors: List[str] = Field(default_factory=list, description="Any errors encountered")
    warnings: List[str] = Field(default_factory=list, description="Any warnings generated")

    model_config = ConfigDict(extra="forbid")


class ServiceRegistration(BaseModel):
    """Registration information for a service in the registry."""

    service_type: ServiceType = Field(..., description="Type of service")
    provider_id: str = Field(..., description="Unique ID of the provider instance")
    priority: ServicePriority = Field(..., description="Registration priority")
    capabilities: List[str] = Field(default_factory=list, description="Service capabilities")
    metadata: ServiceMetadata = Field(..., description="Service metadata")
    registered_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    model_config = ConfigDict(extra="forbid")
