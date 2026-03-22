"""Shared adapter discovery and filtering logic.

This module provides unified adapter discovery used by:
- First-run setup wizard (setup/helpers.py)
- Add adapters card (system/adapters.py)

All adapter filtering logic should be centralized here to ensure consistency.
"""

import json
import logging
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ciris_engine.schemas.runtime.adapter_management import ModuleConfigParameter, ModuleTypeInfo

logger = logging.getLogger(__name__)

# Entry point group for adapter discovery
ADAPTER_ENTRY_POINT_GROUP = "ciris.adapters"
MANIFEST_FILENAME = "manifest.json"

# Common communication capabilities for adapters
CAP_COMM_SEND_MESSAGE = "communication:send_message"
CAP_COMM_FETCH_MESSAGES = "communication:fetch_messages"
COMM_CAPABILITIES = [CAP_COMM_SEND_MESSAGE, CAP_COMM_FETCH_MESSAGES]


# ============================================================================
# Platform Requirements
# ============================================================================


def check_platform_requirements_satisfied(platform_requirements: List[str]) -> bool:
    """Check if current platform satisfies the given requirements."""
    if not platform_requirements:
        return True

    from ciris_engine.logic.utils.platform_detection import detect_platform_capabilities
    from ciris_engine.schemas.platform import PlatformRequirement

    try:
        caps = detect_platform_capabilities()
        req_enums = []
        for req_str in platform_requirements:
            try:
                req_enums.append(PlatformRequirement(req_str))
            except ValueError:
                pass  # Unknown requirement, skip
        return caps.satisfies(req_enums)
    except Exception:
        return False


def check_external_dependencies(manifest_data: Dict[str, Any]) -> Tuple[List[str], List[str], bool]:
    """Check if external CLI dependencies are available.

    Args:
        manifest_data: The adapter manifest

    Returns:
        Tuple of (all_dependencies, missing_dependencies, all_available)
    """
    external_deps: List[str] = []
    missing_deps: List[str] = []

    # Check external_dependencies field in manifest
    deps = manifest_data.get("external_dependencies", [])
    if isinstance(deps, list):
        external_deps.extend(deps)

    # Check for requires:binaries capability (indicates CLI tool needed)
    capabilities = manifest_data.get("capabilities", [])
    if "requires:binaries" in capabilities:
        module_info = manifest_data.get("module", {})
        module_name = module_info.get("name", "")
        if module_name and module_name not in external_deps:
            external_deps.append(module_name)

    # Check each dependency
    for dep in external_deps:
        if not shutil.which(dep):
            missing_deps.append(dep)

    all_available = len(missing_deps) == 0
    return external_deps, missing_deps, all_available


# ============================================================================
# Manifest Filtering
# ============================================================================


def should_filter_adapter(
    manifest_data: Dict[str, Any],
    filter_by_platform: bool = True,
    skip_adapters: Optional[set[str]] = None,
) -> bool:
    """Check if an adapter should be filtered from listings.

    Args:
        manifest_data: Raw manifest data dict
        filter_by_platform: Whether to filter by platform requirements
        skip_adapters: Set of adapter IDs to explicitly skip

    Returns:
        True if adapter should be filtered out, False if it should be included
    """
    module_info = manifest_data.get("module", {})
    metadata = manifest_data.get("metadata", {})
    services = manifest_data.get("services", [])
    module_name = module_info.get("name", "")

    # Skip explicitly excluded adapters
    if skip_adapters and module_name in skip_adapters:
        logger.debug(f"[ADAPTER_DISCOVERY] Filtering {module_name}: explicitly skipped")
        return True

    # Filter mock adapters
    if module_info.get("MOCK", False) or module_info.get("is_mock", False):
        logger.debug(f"[ADAPTER_DISCOVERY] Filtering {module_name}: mock adapter")
        return True

    # Filter reference/QA adapters
    if module_info.get("reference", False) or module_info.get("for_qa", False):
        logger.debug(f"[ADAPTER_DISCOVERY] Filtering {module_name}: reference/QA adapter")
        return True

    # Filter library modules
    if isinstance(metadata, dict) and metadata.get("type") == "library":
        logger.debug(f"[ADAPTER_DISCOVERY] Filtering {module_name}: library module")
        return True

    # Filter modules with no services (utility/common modules)
    if not services:
        logger.debug(f"[ADAPTER_DISCOVERY] Filtering {module_name}: no services")
        return True

    # Filter common modules by name pattern
    if module_name.endswith("_common") or module_name.endswith("common") or "_common_" in module_name:
        logger.debug(f"[ADAPTER_DISCOVERY] Filtering {module_name}: common module")
        return True

    # Filter internal-only adapters (e.g., ciris_verify which auto-loads)
    if module_info.get("internal_only", False):
        logger.debug(f"[ADAPTER_DISCOVERY] Filtering {module_name}: internal_only")
        return True

    # Filter adapters that don't meet platform requirements
    if filter_by_platform:
        platform_requirements = manifest_data.get("platform_requirements", [])
        if not check_platform_requirements_satisfied(platform_requirements):
            logger.debug(f"[ADAPTER_DISCOVERY] Filtering {module_name}: platform requirements not met")
            return True

    return False


# ============================================================================
# Manifest Parsing
# ============================================================================


def extract_service_types(manifest_data: Dict[str, Any]) -> List[str]:
    """Extract unique service types from manifest services list."""
    service_types = []
    for svc in manifest_data.get("services", []):
        svc_type = svc.get("type", "")
        if svc_type and svc_type not in service_types:
            service_types.append(svc_type)
    return service_types


def parse_config_parameters(manifest_data: Dict[str, Any]) -> List[ModuleConfigParameter]:
    """Parse configuration parameters from manifest."""
    config_params: List[ModuleConfigParameter] = []
    for param_name, param_data in manifest_data.get("configuration", {}).items():
        if isinstance(param_data, dict):
            config_params.append(
                ModuleConfigParameter(
                    name=param_name,
                    param_type=param_data.get("type", "string"),
                    default=param_data.get("default"),
                    description=param_data.get("description", ""),
                    env_var=param_data.get("env"),
                    required=param_data.get("required", True),
                    sensitivity=param_data.get("sensitivity"),
                )
            )
    return config_params


def parse_manifest_to_module_info(manifest_data: Dict[str, Any], module_id: str) -> ModuleTypeInfo:
    """Parse a module manifest into a ModuleTypeInfo."""
    module_info = manifest_data.get("module", {})

    # Extract service types and config params
    service_types = extract_service_types(manifest_data)
    config_params = parse_config_parameters(manifest_data)

    # Extract external dependencies (Python packages)
    deps = manifest_data.get("dependencies", {})
    external_deps = deps.get("external", {}) if isinstance(deps, dict) else {}
    external_deps = external_deps or {}

    # Extract CLI dependencies (binary tools)
    cli_deps: List[str] = []
    manifest_cli_deps = manifest_data.get("cli_dependencies", [])
    if isinstance(manifest_cli_deps, list):
        cli_deps.extend(manifest_cli_deps)

    # Only use module name as fallback when requires:binaries is present
    capabilities = manifest_data.get("capabilities", [])
    if "requires:binaries" in capabilities and not cli_deps:
        module_name = module_info.get("name", module_id)
        if module_name:
            cli_deps.append(module_name)

    # Extract metadata
    metadata = manifest_data.get("metadata", {})
    safe_domain = metadata.get("safe_domain") if isinstance(metadata, dict) else None
    prohibited = metadata.get("prohibited", []) if isinstance(metadata, dict) else []

    # Extract platform requirements
    platform_requirements = manifest_data.get("platform_requirements", [])
    platform_requirements_rationale = manifest_data.get("platform_requirements_rationale")

    # Check platform availability
    platform_available = check_platform_requirements_satisfied(platform_requirements)

    return ModuleTypeInfo(
        module_id=module_id,
        name=module_info.get("name", module_id),
        version=module_info.get("version", "1.0.0"),
        description=module_info.get("description", ""),
        author=module_info.get("author", "Unknown"),
        module_source="modular",
        service_types=service_types,
        capabilities=manifest_data.get("capabilities", []),
        configuration_schema=config_params,
        requires_external_deps=bool(external_deps),
        external_dependencies=external_deps,
        cli_dependencies=cli_deps,
        is_mock=module_info.get("MOCK", False) or module_info.get("is_mock", False),
        safe_domain=safe_domain if isinstance(safe_domain, str) else None,
        prohibited=prohibited if isinstance(prohibited, list) else [],
        metadata=metadata if isinstance(metadata, dict) else None,
        platform_requirements=platform_requirements,
        platform_requirements_rationale=platform_requirements_rationale,
        platform_available=platform_available,
        internal_only=module_info.get("internal_only", False),
    )


# ============================================================================
# Core Adapter Info (api, cli, discord)
# ============================================================================


def get_core_adapter_info(adapter_type: str) -> ModuleTypeInfo:
    """Generate ModuleTypeInfo for a core adapter."""
    core_adapters: Dict[str, Dict[str, Any]] = {
        "api": {
            "name": "API Adapter",
            "description": "REST API adapter providing HTTP endpoints for CIRIS interaction",
            "service_types": ["COMMUNICATION", "TOOL", "RUNTIME_CONTROL"],
            "capabilities": [*COMM_CAPABILITIES, "tool:api", "runtime_control"],
            "configuration": [
                ModuleConfigParameter(
                    name="host",
                    param_type="string",
                    default="127.0.0.1",
                    description="Host address to bind to",
                    env_var="CIRIS_API_HOST",
                    required=False,
                ),
                ModuleConfigParameter(
                    name="port",
                    param_type="integer",
                    default=8000,
                    description="Port to listen on",
                    env_var="CIRIS_API_PORT",
                    required=False,
                ),
                ModuleConfigParameter(
                    name="debug",
                    param_type="boolean",
                    default=False,
                    description="Enable debug mode",
                    env_var="CIRIS_API_DEBUG",
                    required=False,
                ),
            ],
        },
        "cli": {
            "name": "CLI Adapter",
            "description": "Command-line interface adapter for interactive terminal sessions",
            "service_types": ["COMMUNICATION"],
            "capabilities": COMM_CAPABILITIES,
            "configuration": [
                ModuleConfigParameter(
                    name="prompt",
                    param_type="string",
                    default="CIRIS> ",
                    description="CLI prompt string",
                    required=False,
                ),
            ],
        },
        "discord": {
            "name": "Discord Adapter",
            "description": "Discord bot adapter for community interaction",
            "service_types": ["COMMUNICATION", "TOOL"],
            "capabilities": [*COMM_CAPABILITIES, "tool:discord"],
            "configuration": [
                ModuleConfigParameter(
                    name="discord_token",
                    param_type="string",
                    description="Discord bot token",
                    env_var="CIRIS_DISCORD_TOKEN",
                    required=True,
                    sensitivity="HIGH",
                ),
                ModuleConfigParameter(
                    name="guild_id",
                    param_type="string",
                    description="Discord guild ID to operate in",
                    env_var="CIRIS_DISCORD_GUILD_ID",
                    required=False,
                ),
                ModuleConfigParameter(
                    name="channel_id",
                    param_type="string",
                    description="Default channel ID for messages",
                    env_var="CIRIS_DISCORD_CHANNEL_ID",
                    required=False,
                ),
            ],
        },
    }

    adapter_info = core_adapters.get(adapter_type, {})
    return ModuleTypeInfo(
        module_id=adapter_type,
        name=adapter_info.get("name", adapter_type.title()),
        version="1.0.0",
        description=adapter_info.get("description", f"Core {adapter_type} adapter"),
        author="CIRIS Team",
        module_source="core",
        service_types=adapter_info.get("service_types", []),
        capabilities=adapter_info.get("capabilities", []),
        configuration_schema=adapter_info.get("configuration", []),
        requires_external_deps=adapter_type == "discord",
        external_dependencies={"discord.py": ">=2.0.0"} if adapter_type == "discord" else {},
        is_mock=False,
        safe_domain=None,
        prohibited=[],
        metadata=None,
    )


# ============================================================================
# Adapter Discovery
# ============================================================================


def try_load_service_manifest(
    service_name: str,
    apply_filter: bool = True,
    filter_by_platform: bool = True,
    skip_adapters: Optional[set[str]] = None,
) -> Optional[ModuleTypeInfo]:
    """Try to load a modular service manifest by name.

    Args:
        service_name: Name of the service/adapter
        apply_filter: Whether to apply filtering rules
        filter_by_platform: Whether to filter by platform requirements
        skip_adapters: Set of adapter IDs to explicitly skip

    Returns:
        ModuleTypeInfo if successfully loaded, None if filtered or failed
    """
    import importlib

    try:
        submodule = importlib.import_module(f"ciris_adapters.{service_name}")
        if not hasattr(submodule, "__path__"):
            logger.debug(f"[ADAPTER_DISCOVERY] {service_name}: no __path__ attribute")
            return None

        manifest_file = Path(submodule.__path__[0]) / MANIFEST_FILENAME
        if not manifest_file.exists():
            logger.debug(f"[ADAPTER_DISCOVERY] {service_name}: no manifest.json")
            return None

        with open(manifest_file) as f:
            manifest_data = json.load(f)

        # Apply filtering
        if apply_filter and should_filter_adapter(manifest_data, filter_by_platform, skip_adapters):
            logger.debug(f"[ADAPTER_DISCOVERY] {service_name}: filtered out")
            return None

        result = parse_manifest_to_module_info(manifest_data, service_name)
        logger.debug(
            f"[ADAPTER_DISCOVERY] {service_name}: OK (services={result.service_types}, "
            f"platform_available={result.platform_available})"
        )
        return result

    except Exception as e:
        logger.debug(f"[ADAPTER_DISCOVERY] {service_name}: error: {e}")
        return None


async def read_manifest_async(manifest_path: Path) -> Optional[Dict[str, Any]]:
    """Read and parse a manifest file asynchronously."""
    import aiofiles

    try:
        async with aiofiles.open(manifest_path, mode="r") as f:
            content = await f.read()
        result: Dict[str, Any] = json.loads(content)
        return result
    except Exception:
        return None


async def discover_services_from_directory(
    services_base: Path,
    filter_by_platform: bool = True,
    skip_adapters: Optional[set[str]] = None,
) -> List[ModuleTypeInfo]:
    """Discover modular services by iterating the services directory."""
    adapters: List[ModuleTypeInfo] = []

    logger.debug(f"[ADAPTER_DISCOVERY] Scanning directory: {services_base}")

    for item in services_base.iterdir():
        if not item.is_dir() or item.name.startswith("_"):
            continue

        # Try importlib-based loading first (Android compatibility)
        module_info = try_load_service_manifest(
            item.name,
            apply_filter=True,
            filter_by_platform=filter_by_platform,
            skip_adapters=skip_adapters,
        )
        if module_info:
            adapters.append(module_info)
            continue

        # Fallback to direct file access
        manifest_path = item / MANIFEST_FILENAME
        manifest_data = await read_manifest_async(manifest_path)
        if manifest_data:
            if should_filter_adapter(manifest_data, filter_by_platform, skip_adapters):
                continue
            module_info = parse_manifest_to_module_info(manifest_data, item.name)
            adapters.append(module_info)

    logger.debug(f"[ADAPTER_DISCOVERY] Total discovered: {len(adapters)} adapters")
    return adapters


async def discover_services_via_entry_points(
    filter_by_platform: bool = True,
    skip_adapters: Optional[set[str]] = None,
) -> List[ModuleTypeInfo]:
    """Discover modular services via importlib.metadata entry points."""
    from importlib.metadata import entry_points
    from typing import Iterable

    adapters: List[ModuleTypeInfo] = []

    try:
        eps = entry_points()
        adapter_eps: Iterable[Any]

        if hasattr(eps, "select"):
            adapter_eps = eps.select(group=ADAPTER_ENTRY_POINT_GROUP)
        elif isinstance(eps, dict):
            adapter_eps = eps.get(ADAPTER_ENTRY_POINT_GROUP, [])
        else:
            adapter_eps = getattr(eps, ADAPTER_ENTRY_POINT_GROUP, [])

        for ep in adapter_eps:
            module_info = try_load_service_manifest(
                ep.name,
                apply_filter=True,
                filter_by_platform=filter_by_platform,
                skip_adapters=skip_adapters,
            )
            if module_info:
                adapters.append(module_info)

    except Exception as e:
        logger.warning(f"Entry point discovery failed: {e}")

    return adapters


async def discover_adapters(
    filter_by_platform: bool = True,
    skip_adapters: Optional[set[str]] = None,
) -> List[ModuleTypeInfo]:
    """Discover all available modular adapters.

    Args:
        filter_by_platform: Whether to filter by platform requirements
        skip_adapters: Set of adapter IDs to explicitly skip

    Returns:
        List of ModuleTypeInfo for discovered adapters
    """
    try:
        import ciris_adapters

        if not hasattr(ciris_adapters, "__path__"):
            return await discover_services_via_entry_points(filter_by_platform, skip_adapters)

        services_base = Path(ciris_adapters.__path__[0])

        try:
            return await discover_services_from_directory(services_base, filter_by_platform, skip_adapters)
        except OSError as e:
            logger.debug(f"iterdir failed ({e}), falling back to entry points")
            return await discover_services_via_entry_points(filter_by_platform, skip_adapters)

    except ImportError as e:
        logger.debug(f"ciris_adapters not available: {e}")
        return await discover_services_via_entry_points(filter_by_platform, skip_adapters)


def get_cli_dependency_status(adapter: ModuleTypeInfo) -> Tuple[List[str], List[str], bool]:
    """Get CLI dependency status for an adapter.

    Returns:
        Tuple of (cli_deps, missing_deps, deps_available)
    """
    cli_deps = adapter.cli_dependencies or []
    missing_deps = [dep for dep in cli_deps if not shutil.which(dep)]
    deps_available = len(missing_deps) == 0
    return cli_deps, missing_deps, deps_available
