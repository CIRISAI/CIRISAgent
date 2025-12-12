"""
Module loader with MOCK safety checks.

Ensures MOCK modules disable corresponding real services and emit warnings.
"""

import importlib
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from ciris_engine.schemas.runtime.enums import ServiceType
from ciris_engine.schemas.runtime.manifest import ModuleLoadResult, ServiceManifest, ServiceMetadata

logger = logging.getLogger(__name__)


class ModuleLoader:
    """Loads modules with MOCK safety enforcement."""

    def __init__(self, modules_dir: Optional[Path] = None) -> None:
        self.modules_dir = modules_dir or Path("ciris_adapters")
        self.loaded_modules: Dict[str, ServiceManifest] = {}
        self.mock_modules: Set[str] = set()
        self.disabled_service_types: Set[ServiceType] = set()

    def load_module(self, module_name: str, disable_core: bool = False) -> bool:
        """Load a module by name with safety checks."""
        module_path = self.modules_dir / module_name
        manifest_path = module_path / "manifest.json"

        if not manifest_path.exists():
            logger.error(f"Module {module_name} not found at {module_path}")
            return False

        try:
            with open(manifest_path) as f:
                manifest_data = json.load(f)

            # Parse into typed manifest
            manifest = ServiceManifest.model_validate(manifest_data)

            # Validate manifest consistency
            errors = manifest.validate_manifest()
            if errors:
                logger.error(f"Manifest validation errors for {module_name}: {errors}")
                return False

            if manifest.module.is_mock:
                self._handle_mock_module(module_name, manifest, disable_core)
            else:
                self._handle_real_module(module_name, manifest)

            self.loaded_modules[module_name] = manifest
            return True

        except Exception as e:
            logger.error(f"Failed to load module {module_name}: {e}")
            return False

    def _handle_mock_module(self, module_name: str, manifest: ServiceManifest, disable_core: bool) -> None:
        """Handle loading of MOCK modules with safety warnings."""
        self.mock_modules.add(module_name)

        # Emit LOUD warnings
        logger.warning("=" * 80)
        logger.warning("🚨 MOCK MODULE DETECTED 🚨")
        logger.warning(f"Loading MOCK module: {module_name}")
        logger.warning("THIS IS FOR TESTING ONLY - NOT FOR PRODUCTION")
        logger.warning("=" * 80)

        # Determine which service types this mock provides
        for service in manifest.services:
            self.disabled_service_types.add(service.type)

            if disable_core:
                logger.warning(f"⚠️  DISABLING all non-mock {service.type.value} services")
                logger.warning(f"⚠️  ONLY {module_name} will provide {service.type.value} services")

        # Log to audit trail
        logger.critical(
            f"MOCK_MODULE_LOADED: {module_name} - Production services disabled for types: {[st.value for st in self.disabled_service_types]}"
        )

    def _handle_real_module(self, module_name: str, manifest: ServiceManifest) -> None:
        """Handle loading of real modules."""
        # Check if any mock modules are loaded that would conflict
        for service in manifest.services:
            if service.type in self.disabled_service_types:
                logger.error(
                    f"❌ CANNOT load real module {module_name}: MOCK module already loaded for {service.type.value}"
                )
                raise RuntimeError(
                    f"MOCK safety violation: Cannot load real {service.type.value} service when mock is active"
                )

        logger.info(f"Loading module: {module_name}")

    def is_service_type_mocked(self, service_type: ServiceType) -> bool:
        """Check if a service type has been mocked."""
        return service_type in self.disabled_service_types

    def get_mock_warnings(self) -> List[str]:
        """Get all mock warnings for display."""
        if not self.mock_modules:
            return []

        warnings = [
            "🚨 MOCK MODULES ACTIVE 🚨",
            f"Mock modules loaded: {', '.join(self.mock_modules)}",
            f"Disabled service types: {', '.join(st.value for st in self.disabled_service_types)}",
            "DO NOT USE IN PRODUCTION",
        ]
        return warnings

    async def initialize_module_services(self, module_name: str, service_registry: Any) -> ModuleLoadResult:
        """Initialize services from a loaded module."""
        result = ModuleLoadResult(module_name=module_name, success=False)

        if module_name not in self.loaded_modules:
            error_msg = f"Module {module_name} not loaded"
            logger.error(error_msg)
            result.errors.append(error_msg)
            return result

        manifest = self.loaded_modules[module_name]
        initialized_services: List[ServiceMetadata] = []

        # Add module directory to path
        import sys

        _module_path = self.modules_dir / module_name
        sys.path.insert(0, str(self.modules_dir))

        try:
            for service_decl in manifest.services:
                # Skip if this service type is mocked and this isn't the mock
                if not manifest.module.is_mock and self.is_service_type_mocked(service_decl.type):
                    warning = f"Skipping {service_decl.class_path}: {service_decl.type.value} is mocked"
                    logger.warning(warning)
                    result.warnings.append(warning)
                    continue

                # Load service class
                parts = service_decl.class_path.split(".")
                module = importlib.import_module(".".join(parts[:-1]))
                service_class = getattr(module, parts[-1])

                # Initialize service
                service = service_class()
                await service.start()

                # Create typed metadata
                service_metadata = ServiceMetadata(
                    service_type=service_decl.type,
                    module_name=module_name,
                    class_name=service_class.__name__,
                    version=manifest.module.version,
                    is_mock=manifest.module.is_mock,
                    capabilities=service_decl.capabilities,
                    priority=service_decl.priority,
                    health_status="started",
                )

                # Register with loud warnings if mock
                registry_metadata = service_metadata.model_dump()
                if manifest.module.is_mock:
                    registry_metadata["warning"] = "MOCK SERVICE - NOT FOR PRODUCTION"

                from ciris_engine.logic.registries.base import Priority

                priority = Priority[service_decl.priority.value]

                service_registry.register_service(
                    service_type=service_decl.type,
                    provider=service,
                    priority=priority,
                    capabilities=service_decl.capabilities,
                    metadata=registry_metadata,
                )

                initialized_services.append(service_metadata)

                if manifest.module.is_mock:
                    logger.warning(f"⚠️  MOCK service registered: {service_class.__name__}")
                    result.warnings.append(f"MOCK service registered: {service_class.__name__}")
                    # Log SERVICE X/22 for mock LLM services (replaces real LLM service #14)
                    if service_decl.type == ServiceType.LLM:
                        msg = "[SERVICE 14/22] MockLLMService STARTED"
                        logger.warning(msg)
                        print(msg)  # Also print to console for Android logcat
                else:
                    logger.info(f"Service registered: {service_class.__name__}")

            result.success = True
            result.services_loaded = initialized_services

        except Exception as e:
            error_msg = f"Failed to initialize services from {module_name}: {str(e)}"
            logger.error(error_msg)
            result.errors.append(error_msg)

        finally:
            sys.path.pop(0)

        return result
