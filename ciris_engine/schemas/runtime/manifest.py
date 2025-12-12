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
    reference: bool = Field(False, description="Whether this is a reference/example module")
    for_qa: bool = Field(False, description="Whether this module is for QA/testing")

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class LegacyDependencies(BaseModel):
    """Legacy dependency format for backward compatibility."""

    protocols: List[str] = Field(default_factory=list, description="Required protocols")
    schemas: List[str] = Field(default_factory=list, description="Required schemas")
    external: Optional[Dict[str, str]] = Field(None, description="External package dependencies")
    internal: Optional[List[str]] = Field(None, description="Internal module dependencies")

    model_config = ConfigDict(extra="forbid")


class ConfigurationParameter(BaseModel):
    """Configuration parameter definition."""

    type: str = Field(..., description="Parameter type (integer, float, string, boolean, array)")
    default: Optional[Union[int, float, str, bool, List[str]]] = Field(None, description="Default value (optional)")
    description: str = Field(..., description="Parameter description")
    env: Optional[str] = Field(None, description="Environment variable name")
    sensitivity: Optional[str] = Field(None, description="Sensitivity level (e.g., 'HIGH' for secrets)")
    required: bool = Field(True, description="Whether this parameter is required")
    enum: Optional[List[str]] = Field(None, description="Allowed values for string parameters")

    model_config = ConfigDict(extra="forbid")


class AdapterOAuthConfig(BaseModel):
    """OAuth configuration for adapter authentication workflows.

    This is distinct from OAuthConfig in wise_authority, which handles full
    OAuth provider configuration. This schema is for adapter configuration
    workflows that need OAuth authentication.
    """

    provider_name: str = Field(..., description="OAuth provider name")
    authorization_path: str = Field("/auth/authorize", description="OAuth authorization endpoint path")
    token_path: str = Field("/auth/token", description="OAuth token endpoint path")
    client_id_source: Literal["static", "indieauth"] = Field(
        "indieauth", description="Source of client ID (static value or IndieAuth discovery)"
    )
    scopes: List[str] = Field(default_factory=list, description="OAuth scopes to request")
    pkce_required: bool = Field(True, description="Whether PKCE is required for this OAuth flow")

    model_config = ConfigDict(extra="forbid")


class ConfigurationFieldDefinition(BaseModel):
    """Definition of a field within an input step."""

    # Field identification - supports both 'name' and 'field_id' patterns
    name: Optional[str] = Field(None, description="Field name (alternative to field_id)")
    field_id: Optional[str] = Field(None, description="Field identifier (alternative to name)")
    label: Optional[str] = Field(None, description="Human-readable label for the field")

    # Field type and input
    type: Optional[str] = Field(None, description="Field data type (string, integer, number, boolean, password)")
    input_type: Optional[str] = Field(None, description="Input control type (text, password, number, select)")

    # Field metadata
    description: Optional[str] = Field(None, description="Description of the field")
    placeholder: Optional[str] = Field(None, description="Placeholder text for input")
    default: Optional[Any] = Field(None, description="Default value")
    required: bool = Field(False, description="Whether this field is required")

    # Validation
    min: Optional[Union[int, float]] = Field(None, description="Minimum value")
    max: Optional[Union[int, float]] = Field(None, description="Maximum value")

    # Conditional display
    depends_on: Optional[Dict[str, Any]] = Field(None, description="Conditional display based on other fields")

    model_config = ConfigDict(extra="allow")  # Allow additional field-specific properties


class ConfigurationStep(BaseModel):
    """A step in an adapter configuration workflow."""

    step_id: str = Field(..., description="Unique identifier for this step")
    step_type: Literal["discovery", "oauth", "select", "input", "confirm"] = Field(
        ..., description="Type of configuration step"
    )
    title: str = Field(..., description="Human-readable step title")
    description: str = Field(..., description="Description of what this step does")

    # Discovery step fields
    discovery_method: Optional[str] = Field(
        None, description="Discovery method name (e.g., 'mdns', 'api_scan') for discovery steps"
    )

    # OAuth step fields
    oauth_config: Optional[AdapterOAuthConfig] = Field(None, description="OAuth configuration for oauth steps")

    # Select step fields
    options_method: Optional[str] = Field(
        None, description="Method name to call for retrieving options in select steps"
    )
    multiple: bool = Field(False, description="Whether multiple selections are allowed")

    # Input step fields - complex form with multiple fields
    fields: Optional[List[ConfigurationFieldDefinition]] = Field(
        None, description="List of field definitions for input steps"
    )
    dynamic_fields: bool = Field(False, description="Whether fields are dynamically generated")

    # Input step fields - simple single field (alternative to 'fields' list)
    field: Optional[str] = Field(None, description="Single field name (simple input)")
    field_name: Optional[str] = Field(None, description="Configuration field name for input/select steps")
    input_type: Optional[str] = Field(None, description="Input type (text, password, number)")
    placeholder: Optional[str] = Field(None, description="Placeholder text")

    # Step requirements and flow control
    required: bool = Field(False, description="Whether this step is required")
    optional: bool = Field(False, description="Whether this step/field is optional")
    default: Optional[Any] = Field(None, description="Default value for the field")
    validation: Optional[Dict[str, Any]] = Field(None, description="Validation rules (e.g., min, max, pattern)")

    # Dependencies - supports both list of step_ids and conditional dict
    depends_on: Optional[Union[List[str], Dict[str, Any]]] = Field(
        None, description="Step dependencies - list of step_ids or conditional dict"
    )
    condition: Optional[Dict[str, Any]] = Field(
        None, description="Condition for showing this step (e.g., {field: 'x', equals: 'y'})"
    )

    # Confirm step fields
    action: Optional[str] = Field(None, description="Action to perform on confirm (e.g., 'test_connection')")

    model_config = ConfigDict(extra="allow")  # Allow additional step-specific properties


class InteractiveConfiguration(BaseModel):
    """Interactive configuration definition for adapters.

    Enables adapters to define multi-step configuration workflows including
    discovery, OAuth authentication, and user input steps.
    """

    required: bool = Field(False, description="Whether interactive configuration is required")
    workflow_type: Literal["wizard", "discovery_then_config", "simple_config"] = Field(
        "wizard", description="Type of configuration workflow"
    )
    steps: List[ConfigurationStep] = Field(default_factory=list, description="Ordered list of configuration steps")
    completion_method: str = Field("apply_config", description="Method name to call when configuration is complete")

    model_config = ConfigDict(extra="allow")  # Allow reference/documentation fields


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
    prohibited_capabilities: Optional[List[str]] = Field(None, description="Prohibited capabilities for this module")
    interactive_config: Optional[InteractiveConfiguration] = Field(
        None, description="Interactive configuration workflow for adapters"
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
