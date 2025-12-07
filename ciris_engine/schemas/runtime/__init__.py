"""
Runtime schemas for CIRIS Engine.

Provides typed schemas for service manifests, module loading,
and dynamic adapter configuration.
"""

from .manifest import (
    AdapterOAuthConfig,
    ConfigurationParameter,
    ConfigurationStep,
    InteractiveConfiguration,
    LegacyDependencies,
    ModuleInfo,
    ModuleLoadResult,
    ServiceCapabilityDeclaration,
    ServiceDeclaration,
    ServiceDependency,
    ServiceManifest,
    ServiceMetadata,
    ServicePriority,
    ServiceRegistration,
)

__all__ = [
    # Service manifest core
    "ServiceManifest",
    "ModuleInfo",
    "ServiceDeclaration",
    "ServicePriority",
    "ServiceCapabilityDeclaration",
    "ServiceDependency",
    "ServiceMetadata",
    "ServiceRegistration",
    "ModuleLoadResult",
    "LegacyDependencies",
    "ConfigurationParameter",
    # Interactive adapter configuration
    "AdapterOAuthConfig",
    "ConfigurationStep",
    "InteractiveConfiguration",
]
