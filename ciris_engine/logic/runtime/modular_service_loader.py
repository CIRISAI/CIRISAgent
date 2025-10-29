"""
Dynamic loader for modular services.

Discovers and loads services from the ciris_modular_services directory.
"""

import importlib
import importlib.util
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, cast

from ciris_engine.protocols.services import ServiceProtocol
from ciris_engine.schemas.runtime.enums import ServiceType
from ciris_engine.schemas.runtime.manifest import ModuleLoadResult, ServiceManifest, ServiceMetadata, ServicePriority

logger = logging.getLogger(__name__)


class ModularServiceLoader:
    """Loads modular services from external packages."""

    def __init__(self, services_dir: Path | None = None) -> None:
        self.services_dir = services_dir or Path("ciris_modular_services")
        self.loaded_services: Dict[str, ServiceMetadata] = {}

    def discover_services(self) -> List[ServiceManifest]:
        """Discover all modular services with valid manifests."""
        services: List[ServiceManifest] = []

        if not self.services_dir.exists():
            logger.info(f"Modular services directory not found: {self.services_dir}")
            return services

        for service_dir in self.services_dir.iterdir():
            if not service_dir.is_dir() or service_dir.name.startswith("_"):
                continue

            manifest_path = service_dir / "manifest.json"
            if manifest_path.exists():
                try:
                    with open(manifest_path) as f:
                        manifest_data = json.load(f)

                    # Parse into typed manifest
                    manifest = ServiceManifest.model_validate(manifest_data)
                    # Store path separately for loading
                    setattr(manifest, "_path", service_dir)
                    services.append(manifest)
                    logger.info(f"Discovered modular service: {manifest.module.name}")
                except Exception as e:
                    logger.error(f"Failed to load manifest from {service_dir}: {e}")

        return services

    def validate_manifest(self, manifest: ServiceManifest) -> bool:
        """Validate a service manifest has required fields."""
        # Use the manifest's built-in validation
        errors = manifest.validate_manifest()
        if errors:
            for error in errors:
                logger.error(f"Manifest validation error: {error}")
            return False
        return True

    def check_dependencies(self, manifest: ServiceManifest) -> bool:
        """Check if service dependencies are available."""
        # Check legacy dependencies format if present
        if not manifest.dependencies:
            return True

        # Check protocol dependencies
        for protocol in manifest.dependencies.protocols:
            try:
                parts = protocol.split(".")
                module = importlib.import_module(".".join(parts[:-1]))
                if not hasattr(module, parts[-1]):
                    logger.error(f"Protocol not found: {protocol}")
                    return False
            except ImportError as e:
                logger.error(f"Failed to import protocol {protocol}: {e}")
                return False

        # Check schema dependencies
        for schema in manifest.dependencies.schemas:
            try:
                importlib.import_module(schema)
            except ImportError as e:
                logger.error(f"Failed to import schema {schema}: {e}")
                return False

        return True

    def load_service_class(self, manifest: ServiceManifest, class_path: str) -> Optional[type[ServiceProtocol]]:
        """Load a specific service class by class path from a manifest.

        Args:
            manifest: The service manifest
            class_path: Specific class path to load (e.g., "reddit.service.RedditCommunicationService")

        Returns:
            The loaded service class or None if loading fails
        """
        if not self.validate_manifest(manifest):
            return None

        if not self.check_dependencies(manifest):
            logger.error(f"Dependencies not satisfied for {manifest.module.name}")
            return None

        # Add service directory to Python path temporarily
        import sys

        sys.path.insert(0, str(self.services_dir))

        try:
            parts = class_path.split(".")
            module_path = ".".join(parts[:-1])
            class_name = parts[-1]

            # Import module
            module = importlib.import_module(module_path)
            service_class = getattr(module, class_name)

            logger.info(f"Successfully loaded service class: {class_name} from {manifest.module.name}")
            return cast(type[ServiceProtocol], service_class)

        except Exception as e:
            logger.error(f"Failed to load service class {class_path} from {manifest.module.name}: {e}")
            return None
        finally:
            # Remove from path
            sys.path.pop(0)

    def load_service(self, manifest: ServiceManifest) -> Optional[type[ServiceProtocol]]:
        """Dynamically load a service class from manifest (loads first service in manifest)."""
        if not self.validate_manifest(manifest):
            return None

        if not self.check_dependencies(manifest):
            logger.error(f"Dependencies not satisfied for {manifest.module.name}")
            return None

        _service_path = getattr(manifest, "_path", None)
        if not _service_path:
            logger.error("Manifest missing path information")
            return None
        service_name = manifest.module.name

        # Get class path from manifest
        if manifest.services:
            service_class_path = manifest.services[0].class_path
        elif manifest.exports and "service_class" in manifest.exports:
            # Legacy format support
            export_value = manifest.exports["service_class"]
            service_class_path = export_value if isinstance(export_value, str) else export_value[0]
        else:
            logger.error("No service class path found in manifest")
            return None

        # Use the new load_service_class method
        service_class = self.load_service_class(manifest, service_class_path)
        if not service_class:
            return None

        # Create service metadata
        parts = service_class_path.split(".")
        class_name = parts[-1]
        service_meta = ServiceMetadata(
            service_type=manifest.services[0].type if manifest.services else ServiceType.LLM,
            module_name=service_name,
            class_name=class_name,
            version=manifest.module.version,
            is_mock=manifest.module.is_mock,
            capabilities=manifest.capabilities or [],
            priority=manifest.services[0].priority if manifest.services else ServicePriority.NORMAL,
            health_status="loaded",
        )
        self.loaded_services[service_name] = service_meta
        logger.info(f"Successfully loaded modular service: {service_name}")

        return service_class

    def get_service_metadata(self, service_name: str) -> Optional[ServiceMetadata]:
        """Get metadata for a loaded service."""
        return self.loaded_services.get(service_name)

    async def initialize_modular_services(self, service_registry: Any, config: Any) -> ModuleLoadResult:
        """Initialize all discovered modular services."""
        result = ModuleLoadResult(module_name="modular_services", success=True)

        # Discover services
        discovered = self.discover_services()

        for manifest in discovered:
            # Skip if production mode and service is test-only
            if not getattr(config, "mock_llm", False) and manifest.module.is_mock:
                msg = f"Skipping mock service in production: {manifest.module.name}"
                logger.info(msg)
                result.warnings.append(msg)
                continue

            # Load service class
            service_class = self.load_service(manifest)
            if not service_class:
                continue

            try:
                # Initialize service
                service_config = {}
                if manifest.configuration:
                    # Extract default values from configuration
                    for key, param in manifest.configuration.items():
                        service_config[key] = param.default

                service_instance = service_class(**service_config)
                await service_instance.start()

                # Register with service registry
                for service_decl in manifest.services:
                    service_registry.register_global(
                        service_type=service_decl.type,
                        provider=service_instance,
                        priority=ServicePriority[service_decl.priority.value],
                        capabilities=service_decl.capabilities or manifest.capabilities or [],
                        metadata=self.loaded_services[manifest.module.name].model_dump(),
                    )

                # Update result
                service_meta = self.loaded_services[manifest.module.name]
                service_meta.health_status = "started"
                result.services_loaded.append(service_meta)
                logger.info(f"Initialized modular service: {manifest.module.name}")

            except Exception as e:
                error_msg = f"Failed to initialize {manifest.module.name}: {e}"
                logger.error(error_msg)
                result.errors.append(error_msg)
                result.success = False

        return result
