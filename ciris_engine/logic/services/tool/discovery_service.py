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
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Type

from ciris_engine.logic.runtime.adapter_loader import AdapterLoader
from ciris_engine.schemas.adapters.discovery import AdapterAvailabilityStatus, AdapterDiscoveryReport
from ciris_engine.schemas.adapters.tools import InstallStep, ToolInfo
from ciris_engine.schemas.runtime.manifest import ServiceDeclaration, ServiceManifest

from .eligibility_checker import EligibilityResult, ToolEligibilityChecker

logger = logging.getLogger(__name__)


@dataclass
class IneligibleAdapterInfo:
    """Information about an adapter that was discovered but is not eligible."""

    name: str
    manifest: ServiceManifest
    eligibility: EligibilityResult
    tools: List[ToolInfo] = field(default_factory=list)
    source_path: Optional[str] = None


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

    def load_service_class(self, manifest: ServiceManifest, class_path: str) -> Optional[Type[Any]]:
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
    ) -> Dict[str, Any]:
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
        eligible, _ = await self.load_adapters_with_status(disabled_adapters, service_dependencies)
        return eligible

    async def load_adapters_with_status(
        self,
        disabled_adapters: Optional[List[str]] = None,
        service_dependencies: Optional[Dict[str, Any]] = None,
    ) -> Tuple[Dict[str, Any], List[IneligibleAdapterInfo]]:
        """Load adapters and return both eligible services and ineligible info.

        Args:
            disabled_adapters: Adapter names to exclude from loading
            service_dependencies: Dependencies to pass to service constructors

        Returns:
            Tuple of (eligible_services dict, list of IneligibleAdapterInfo)
        """
        disabled = set(disabled_adapters or [])
        deps = service_dependencies or {}
        eligible_services: Dict[str, Any] = {}
        ineligible_adapters: List[IneligibleAdapterInfo] = []

        for manifest in self.discover_adapters():
            adapter_name = manifest.module.name

            # Skip disabled adapters
            if adapter_name in disabled:
                logger.info(f"[AUTO-LOAD] Skipping disabled adapter: {adapter_name}")
                continue

            # Try to load and check eligibility for each service in manifest
            for service_def in manifest.services:
                try:
                    service, ineligible_info = await self._instantiate_and_check_with_info(manifest, service_def, deps)
                    if service:
                        eligible_services[adapter_name] = service
                        logger.info(f"[AUTO-LOAD] Eligible adapter: {adapter_name}")
                    elif ineligible_info:
                        ineligible_adapters.append(ineligible_info)
                        logger.info(
                            f"[AUTO-LOAD] Adapter '{adapter_name}' not eligible: {ineligible_info.eligibility.reason}"
                        )
                except Exception as e:
                    logger.debug(f"[AUTO-LOAD] Failed to check adapter '{adapter_name}': {e}")

        logger.info(
            f"[AUTO-LOAD] Loaded {len(eligible_services)} eligible, {len(ineligible_adapters)} ineligible adapters"
        )
        return eligible_services, ineligible_adapters

    async def _instantiate_and_check(
        self,
        manifest: ServiceManifest,
        service_def: ServiceDeclaration,
        deps: Dict[str, Any],
    ) -> Optional[Any]:
        """Instantiate a service and check tool eligibility.

        Returns:
            Service instance if eligible, None otherwise
        """
        service, _ = await self._instantiate_and_check_with_info(manifest, service_def, deps)
        return service

    async def _instantiate_and_check_with_info(
        self,
        manifest: ServiceManifest,
        service_def: ServiceDeclaration,
        deps: Dict[str, Any],
    ) -> Tuple[Optional[Any], Optional[IneligibleAdapterInfo]]:
        """Instantiate a service and check tool eligibility, returning ineligible info.

        Returns:
            Tuple of (service_instance or None, IneligibleAdapterInfo or None)
        """
        adapter_name = manifest.module.name
        loader = self._manifest_loaders.get(adapter_name)
        source_path = str(loader.services_dir) if loader else None

        service = self._try_instantiate_service(manifest, service_def, deps, adapter_name)
        if not service:
            return None, None

        # Check if service has get_all_tool_info (tool service)
        if not hasattr(service, "get_all_tool_info"):
            logger.debug(f"Adapter '{adapter_name}' has no get_all_tool_info, assuming eligible")
            return service, None

        # Get tool info and check eligibility
        try:
            tools = await service.get_all_tool_info()
            if not tools:
                return service, None

            combined_result = self._check_tools_eligibility(tools)
            if combined_result.eligible:
                return service, None

            ineligible_info = IneligibleAdapterInfo(
                name=adapter_name,
                manifest=manifest,
                eligibility=combined_result,
                tools=tools,
                source_path=source_path,
            )
            return None, ineligible_info

        except Exception as e:
            logger.debug(f"Error checking eligibility for {adapter_name}: {e}")
            return None, None

    def _try_instantiate_service(
        self,
        manifest: ServiceManifest,
        service_def: ServiceDeclaration,
        deps: Dict[str, Any],
        adapter_name: str,
    ) -> Optional[Any]:
        """Try to instantiate a service with deps, falling back to no-args."""
        service_class = self.load_service_class(manifest, service_def.class_path)
        if not service_class:
            return None

        try:
            return service_class(**deps)
        except TypeError:
            try:
                return service_class()
            except Exception as e:
                logger.debug(f"Cannot instantiate {adapter_name}: {e}")
                return None

    def _check_tools_eligibility(self, tools: List[ToolInfo]) -> EligibilityResult:
        """Check eligibility of all tools and return combined result."""
        combined = EligibilityResult(eligible=True)
        install_hints: List[InstallStep] = []

        for tool in tools:
            result = self.checker.check_eligibility(tool)
            if result.eligible:
                continue

            combined.eligible = False
            combined.missing_binaries.extend(result.missing_binaries)
            combined.missing_env_vars.extend(result.missing_env_vars)
            combined.missing_config.extend(result.missing_config)
            if result.platform_mismatch:
                combined.platform_mismatch = True
            install_hints.extend(result.install_hints)

        if not combined.eligible:
            combined.reason = self._build_eligibility_reason(combined)
            combined.install_hints = install_hints

        return combined

    def _build_eligibility_reason(self, result: EligibilityResult) -> str:
        """Build a human-readable reason string from eligibility result."""
        reasons = []
        if result.missing_binaries:
            reasons.append(f"missing binaries: {', '.join(set(result.missing_binaries))}")
        if result.missing_env_vars:
            reasons.append(f"missing env vars: {', '.join(set(result.missing_env_vars))}")
        if result.missing_config:
            reasons.append(f"missing config: {', '.join(set(result.missing_config))}")
        if result.platform_mismatch:
            reasons.append("platform not supported")
        return "; ".join(reasons) if reasons else "unknown"

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

    async def get_discovery_report(
        self,
        disabled_adapters: Optional[List[str]] = None,
        service_dependencies: Optional[Dict[str, Any]] = None,
    ) -> AdapterDiscoveryReport:
        """Get a full report of all discovered adapters with eligibility status.

        This is the main method for the GET /adapters/available endpoint.

        Args:
            disabled_adapters: Adapter names to exclude
            service_dependencies: Dependencies for service instantiation

        Returns:
            AdapterDiscoveryReport with eligible and ineligible adapters
        """
        eligible_services, ineligible_list = await self.load_adapters_with_status(
            disabled_adapters, service_dependencies
        )

        eligible_statuses: List[AdapterAvailabilityStatus] = []
        ineligible_statuses: List[AdapterAvailabilityStatus] = []

        # Build eligible adapter statuses
        for adapter_name, service in eligible_services.items():
            tools: List[ToolInfo] = []
            if hasattr(service, "get_all_tool_info"):
                try:
                    tools = await service.get_all_tool_info()
                except Exception:
                    pass

            # Get source path from loader
            loader = self._manifest_loaders.get(adapter_name)
            source_path = str(loader.services_dir) if loader else None
            is_builtin = source_path and "ciris_adapters" in source_path

            eligible_statuses.append(
                AdapterAvailabilityStatus(
                    name=adapter_name,
                    eligible=True,
                    tools=tools,
                    source_path=source_path,
                    is_builtin=is_builtin,
                )
            )

        # Build ineligible adapter statuses
        for info in ineligible_list:
            is_builtin = info.source_path and "ciris_adapters" in info.source_path if info.source_path else False
            has_hints = len(info.eligibility.install_hints) > 0

            ineligible_statuses.append(
                AdapterAvailabilityStatus(
                    name=info.name,
                    eligible=False,
                    eligibility_reason=info.eligibility.reason,
                    missing_binaries=list(set(info.eligibility.missing_binaries)),
                    missing_env_vars=list(set(info.eligibility.missing_env_vars)),
                    missing_config=list(set(info.eligibility.missing_config)),
                    platform_supported=not info.eligibility.platform_mismatch,
                    can_install=has_hints,
                    install_hints=info.eligibility.install_hints,
                    tools=info.tools,
                    source_path=info.source_path,
                    is_builtin=is_builtin,
                )
            )

        total = len(eligible_statuses) + len(ineligible_statuses)
        installable = sum(1 for s in ineligible_statuses if s.can_install)

        return AdapterDiscoveryReport(
            eligible=eligible_statuses,
            ineligible=ineligible_statuses,
            total_discovered=total,
            total_eligible=len(eligible_statuses),
            total_installable=installable,
        )

    async def get_adapter_eligibility(
        self,
        adapter_name: str,
        service_dependencies: Optional[Dict[str, Any]] = None,
    ) -> Optional[AdapterAvailabilityStatus]:
        """Get eligibility status for a specific adapter.

        Args:
            adapter_name: Name of the adapter to check
            service_dependencies: Dependencies for service instantiation

        Returns:
            AdapterAvailabilityStatus or None if adapter not found
        """
        deps = service_dependencies or {}
        manifest = self._find_manifest_by_name(adapter_name)
        if not manifest:
            return None

        source_path, is_builtin = self._get_adapter_source_info(adapter_name)

        for service_def in manifest.services:
            service, ineligible_info = await self._instantiate_and_check_with_info(manifest, service_def, deps)

            if service:
                return await self._build_eligible_status(adapter_name, service, source_path, is_builtin)

            if ineligible_info:
                return self._build_ineligible_status(adapter_name, ineligible_info, source_path, is_builtin)

        return None

    def _find_manifest_by_name(self, adapter_name: str) -> Optional[ServiceManifest]:
        """Find a manifest by adapter name."""
        for manifest in self.discover_adapters():
            if manifest.module.name == adapter_name:
                return manifest
        return None

    def _get_adapter_source_info(self, adapter_name: str) -> Tuple[Optional[str], bool]:
        """Get source path and builtin flag for an adapter."""
        loader = self._manifest_loaders.get(adapter_name)
        source_path = str(loader.services_dir) if loader else None
        is_builtin = bool(source_path and "ciris_adapters" in source_path)
        return source_path, is_builtin

    async def _build_eligible_status(
        self, adapter_name: str, service: Any, source_path: Optional[str], is_builtin: bool
    ) -> AdapterAvailabilityStatus:
        """Build AdapterAvailabilityStatus for an eligible adapter."""
        tools = await self._get_service_tools(service)
        return AdapterAvailabilityStatus(
            name=adapter_name,
            eligible=True,
            tools=tools,
            source_path=source_path,
            is_builtin=is_builtin,
        )

    def _build_ineligible_status(
        self, adapter_name: str, info: IneligibleAdapterInfo, source_path: Optional[str], is_builtin: bool
    ) -> AdapterAvailabilityStatus:
        """Build AdapterAvailabilityStatus for an ineligible adapter."""
        has_hints = len(info.eligibility.install_hints) > 0
        return AdapterAvailabilityStatus(
            name=adapter_name,
            eligible=False,
            eligibility_reason=info.eligibility.reason,
            missing_binaries=list(set(info.eligibility.missing_binaries)),
            missing_env_vars=list(set(info.eligibility.missing_env_vars)),
            missing_config=list(set(info.eligibility.missing_config)),
            platform_supported=not info.eligibility.platform_mismatch,
            can_install=has_hints,
            install_hints=info.eligibility.install_hints,
            tools=info.tools,
            source_path=source_path,
            is_builtin=is_builtin,
        )

    async def _get_service_tools(self, service: Any) -> List[ToolInfo]:
        """Get tools from a service if available."""
        if not hasattr(service, "get_all_tool_info"):
            return []
        try:
            return await service.get_all_tool_info()
        except Exception:
            return []
