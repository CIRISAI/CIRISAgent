"""
Service manifest schemas for typed module loading.

Provides typed schemas in service loading and module manifests.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Union

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


class ServiceManifest(BaseModel):
    """Complete service module manifest."""

    module: ModuleInfo = Field(..., description="Module information")
    services: List[ServiceDeclaration] = Field(default_factory=list, description="Services provided")
    capabilities: List[str] = Field(default_factory=list, description="Global capabilities list")
    dependencies: Optional[LegacyDependencies] = Field(None, description="Legacy dependencies format")
    configuration: Optional[Dict[str, ConfigurationParameter]] = Field(None, description="Configuration parameters")
    exports: Optional[Dict[str, Union[str, List[str]]]] = Field(None, description="Exported components (string or list)")
    metadata: Optional[JSONDict] = Field(None, description="Additional metadata")
    requirements: List[str] = Field(default_factory=list, description="Python package requirements")
    prohibited_sensors: Optional[List[str]] = Field(None, description="Prohibited sensor types for sensor modules")

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
