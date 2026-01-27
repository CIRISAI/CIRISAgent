"""Multi-path adapter discovery service.

Extends the base AdapterLoader to scan multiple directories:
1. ciris_adapters/         - Built-in adapters
2. ~/.ciris/adapters/      - User-installed adapters
3. .ciris/adapters/        - Workspace-local adapters
4. CIRIS_EXTRA_ADAPTERS    - Additional paths from env var

Filters discovered adapters by tool eligibility.
"""

import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Type

from ciris_engine.logic.runtime.adapter_loader import AdapterLoader
from ciris_engine.protocols.infrastructure.base import ServiceProtocol
from ciris_engine.schemas.adapters.tools import ToolInfo
from ciris_engine.schemas.runtime.manifest import ServiceDeclaration, ServiceManifest

from .eligibility_checker import EligibilityResult, ToolEligibilityChecker

logger = logging.getLogger(__name__)


class AdapterDiscoveryService:
    """Auto-discovers adapters from multiple paths with eligibility filtering.

    Discovery paths (in priority order):
    1. ciris_adapters/         - Built-in adapters
    2. ~/.ciris/adapters/      - User-installed adapters
    3. .ciris/adapters/        - Workspace-local adapters
    4. CIRIS_EXTRA_ADAPTERS    - Colon-separated additional paths
    """

    # Standard discovery paths
    DISCOVERY_PATHS = [
        Path("ciris_adapters"),  # Built-in
        Path.home() / ".ciris" / "adapters",  # User
        Path(".ciris") / "adapters",  # Workspace
    ]

    def __init__(
        self,
        eligibility_checker: Optional[ToolEligibilityChecker] = None,
        extra_paths: Optional[List[Path]] = None,
    ):
        """Initialize the discovery service.

        Args:
            eligibility_checker: Checker for tool eligibility. If None, no filtering.
            extra_paths: Additional paths to scan beyond the standard ones.
        """
        self.checker = eligibility_checker or ToolEligibilityChecker()
        self.extra_paths = extra_paths or []

        # Parse CIRIS_EXTRA_ADAPTERS env var
        extra_from_env = os.environ.get("CIRIS_EXTRA_ADAPTERS", "")
        if extra_from_env:
            for path_str in extra_from_env.split(":"):
                path_str = path_str.strip()
                if path_str:
                    self.extra_paths.append(Path(path_str))

        # Create loaders for each path and track manifest->loader mapping
        self._loaders: List[AdapterLoader] = []
        self._manifest_loaders: Dict[str, AdapterLoader] = {}  # manifest_name -> loader
        for path in self._get_all_paths():
            if path.exists() and path.is_dir():
                self._loaders.append(AdapterLoader(services_dir=path))
                logger.info(f"AdapterDiscoveryService: scanning {path}")
            else:
                logger.debug(f"AdapterDiscoveryService: skipping non-existent {path}")

    def _get_all_paths(self) -> List[Path]:
        """Get all discovery paths in priority order."""
        return self.DISCOVERY_PATHS + self.extra_paths

    def discover_adapters(self) -> List[ServiceManifest]:
        """Discover all adapter manifests from all discovery paths.

        Returns:
            List of discovered ServiceManifest objects
        """
        all_manifests: List[ServiceManifest] = []
        seen_names: set[str] = set()

        for loader in self._loaders:
            manifests = loader.discover_services()
            for manifest in manifests:
                # Skip duplicates (first occurrence wins)
                if manifest.module.name in seen_names:
                    logger.debug(f"Skipping duplicate adapter: {manifest.module.name} from {loader.services_dir}")
                    continue

                seen_names.add(manifest.module.name)
                all_manifests.append(manifest)
                # Track which loader handles this manifest
                self._manifest_loaders[manifest.module.name] = loader

        logger.info(f"AdapterDiscoveryService: discovered {len(all_manifests)} adapters")
        return all_manifests

    def load_service_class(self, manifest: ServiceManifest, class_path: str) -> Optional[Type[ServiceProtocol]]:
        """Load a service class from a discovered manifest.

        Args:
            manifest: The service manifest (must have been discovered first)
            class_path: Class path within the manifest

        Returns:
            The service class or None if not found
        """
        loader = self._manifest_loaders.get(manifest.module.name)
        if not loader:
            # Manifest wasn't discovered by us, try to find a loader for it
            logger.warning(
                f"Manifest '{manifest.module.name}' not in discovery cache, " "attempting to find appropriate loader"
            )
            # Try each loader to find one that can load this manifest
            for candidate_loader in self._loaders:
                try:
                    cls = candidate_loader.load_service_class(manifest, class_path)
                    if cls:
                        self._manifest_loaders[manifest.module.name] = candidate_loader
                        return cls
                except Exception:
                    continue
            return None

        return loader.load_service_class(manifest, class_path)

    def get_eligible_adapters(self, disabled_adapters: Optional[List[str]] = None) -> List[ServiceManifest]:
        """Get adapters whose tools all pass eligibility checks.

        An adapter is eligible if ALL of its tools are eligible.
        This ensures the adapter can function fully.

        Args:
            disabled_adapters: List of adapter names to exclude

        Returns:
            List of eligible ServiceManifest objects
        """
        disabled = set(disabled_adapters or [])
        eligible: List[ServiceManifest] = []

        for manifest in self.discover_adapters():
            if manifest.module.name in disabled:
                logger.info(f"Adapter '{manifest.module.name}' disabled by config")
                continue
            eligible.append(manifest)
            logger.debug(f"Adapter '{manifest.module.name}' eligible")

        return eligible

    async def load_eligible_adapters(
        self,
        disabled_adapters: Optional[List[str]] = None,
        service_dependencies: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, ServiceProtocol]:
        """Load adapters whose tool requirements are satisfied.

        Discovers adapters, instantiates services, checks eligibility via
        get_all_tool_info(), and returns only those that pass.

        Args:
            disabled_adapters: Adapter names to exclude from loading
            service_dependencies: Dict of kwargs to pass when instantiating
                services (bus_manager, memory_service, etc.)

        Returns:
            Dict of adapter_name -> service_instance for eligible adapters
        """
        disabled = set(disabled_adapters or [])
        deps = service_dependencies or {}
        eligible_services: Dict[str, ServiceProtocol] = {}

        for manifest in self.discover_adapters():
            adapter_name = manifest.module.name

            # Skip disabled adapters
            if adapter_name in disabled:
                logger.info(f"[AUTO-LOAD] Skipping disabled adapter: {adapter_name}")
                continue

            # Try to load and check eligibility for each service in manifest
            for service_def in manifest.services:
                try:
                    service = await self._instantiate_and_check(manifest, service_def, deps)
                    if service:
                        eligible_services[adapter_name] = service
                        logger.info(f"[AUTO-LOAD] Eligible adapter: {adapter_name}")
                    else:
                        logger.info(f"[AUTO-LOAD] Adapter '{adapter_name}' not eligible")
                except Exception as e:
                    logger.debug(f"[AUTO-LOAD] Failed to check adapter '{adapter_name}': {e}")

        logger.info(f"[AUTO-LOAD] Loaded {len(eligible_services)} eligible adapters")
        return eligible_services

    async def _instantiate_and_check(
        self,
        manifest: ServiceManifest,
        service_def: ServiceDeclaration,
        deps: Dict[str, Any],
    ) -> Optional[ServiceProtocol]:
        """Instantiate a service and check tool eligibility.

        Returns:
            Service instance if eligible, None otherwise
        """
        # Load service class
        service_class = self.load_service_class(manifest, service_def.class_path)
        if not service_class:
            return None

        # Try instantiation with dependencies, fall back to no-args
        service: Optional[ServiceProtocol] = None
        try:
            service = service_class(**deps)  # type: ignore[call-arg]
        except TypeError:
            try:
                service = service_class()  # type: ignore[call-arg]
            except Exception as e:
                logger.debug(f"Cannot instantiate {manifest.module.name}: {e}")
                return None

        if not service:
            return None

        # Check if service has get_all_tool_info (tool service)
        if not hasattr(service, "get_all_tool_info"):
            # Not a tool service, check if it has requirements another way
            # For now, assume non-tool services are eligible
            logger.debug(f"Adapter '{manifest.module.name}' has no get_all_tool_info, assuming eligible")
            return service

        # Get tool info and check eligibility
        try:
            tools = await service.get_all_tool_info()  # type: ignore[union-attr]
            if not tools:
                # No tools = eligible (service provides other capabilities)
                return service

            # Check eligibility of all tools
            all_eligible = True
            for tool in tools:
                result = self.checker.check_eligibility(tool)
                if not result.eligible:
                    logger.info(f"[AUTO-LOAD] Tool '{tool.name}' not eligible: {result.reason}")
                    all_eligible = False
                    break

            if all_eligible:
                return service
            return None

        except Exception as e:
            logger.debug(f"Error checking eligibility for {manifest.module.name}: {e}")
            return None

    def check_tool_eligibility(self, tool_info: ToolInfo) -> EligibilityResult:
        """Check if a single tool is eligible.

        Args:
            tool_info: Tool to check

        Returns:
            EligibilityResult with details
        """
        return self.checker.check_eligibility(tool_info)

    def filter_eligible_tools(self, tools: List[ToolInfo]) -> List[ToolInfo]:
        """Filter tools to only those that are eligible.

        Args:
            tools: List of tool infos

        Returns:
            List of eligible tools
        """
        return self.checker.filter_eligible_tools(tools)
