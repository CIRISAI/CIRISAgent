"""
Adapter management endpoints.

Provides functionality for listing, loading, unloading, and managing adapters.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from pydantic import ValidationError

from ciris_engine.schemas.api.responses import SuccessResponse
from ciris_engine.schemas.runtime.adapter_management import (
    AdapterConfig,
    AdapterListResponse,
    AdapterMetrics,
    AdapterOperationResult,
    ModuleConfigParameter,
    ModuleTypeInfo,
    ModuleTypesResponse,
)
from ciris_engine.schemas.runtime.adapter_management import RuntimeAdapterStatus as AdapterStatusSchema
from ciris_engine.schemas.services.core.runtime import AdapterInfo, AdapterStatus

from ...constants import ERROR_RUNTIME_CONTROL_SERVICE_NOT_AVAILABLE
from ...dependencies.auth import AuthContext, require_admin, require_observer
from .helpers import get_adapter_config_service
from .schemas import (
    AdapterActionRequest,
    ConfigStepInfo,
    ConfigurableAdapterInfo,
    ConfigurableAdaptersResponse,
    PersistedConfigsResponse,
    RemovePersistedResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter()

# Capability constants
CAP_COMM_SEND_MESSAGE = "communication:send_message"
CAP_COMM_FETCH_MESSAGES = "communication:fetch_messages"
MANIFEST_FILENAME = "manifest.json"
ERROR_ADAPTER_CONFIG_SERVICE_NOT_AVAILABLE = "Adapter configuration service not available"

# Common communication capabilities for adapters
COMM_CAPABILITIES = [CAP_COMM_SEND_MESSAGE, CAP_COMM_FETCH_MESSAGES]

# Entry point group for adapter discovery
ADAPTER_ENTRY_POINT_GROUP = "ciris.adapters"


# ============================================================================
# Module Types Discovery Helpers
# ============================================================================


def _get_core_adapter_info(adapter_type: str) -> ModuleTypeInfo:
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


def _check_platform_requirements_satisfied(platform_requirements: List[str]) -> bool:
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


def _should_filter_adapter(manifest_data: Dict[str, Any], filter_by_platform: bool = True) -> bool:
    """Check if an adapter should be filtered from public listings."""
    module_info = manifest_data.get("module", {})
    metadata = manifest_data.get("metadata", {})
    services = manifest_data.get("services", [])

    # Filter mock adapters
    if module_info.get("MOCK", False):
        return True

    # Filter library modules
    if isinstance(metadata, dict) and metadata.get("type") == "library":
        return True

    # Filter modules with no services (utility/common modules)
    if not services:
        return True

    # Filter common modules by name pattern
    module_name = module_info.get("name", "")
    if module_name.endswith("_common") or module_name.endswith("common"):
        return True

    # Filter adapters that don't meet platform requirements
    if filter_by_platform:
        platform_requirements = manifest_data.get("platform_requirements", [])
        if not _check_platform_requirements_satisfied(platform_requirements):
            return True

    return False


def _extract_service_types(manifest_data: Dict[str, Any]) -> List[str]:
    """Extract unique service types from manifest services list."""
    service_types = []
    for svc in manifest_data.get("services", []):
        svc_type = svc.get("type", "")
        if svc_type and svc_type not in service_types:
            service_types.append(svc_type)
    return service_types


def _parse_config_parameters(manifest_data: Dict[str, Any]) -> List[ModuleConfigParameter]:
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


def _parse_manifest_to_module_info(manifest_data: Dict[str, Any], module_id: str) -> ModuleTypeInfo:
    """Parse a module manifest into a ModuleTypeInfo."""
    module_info = manifest_data.get("module", {})

    # Extract service types and config params using helpers
    service_types = _extract_service_types(manifest_data)
    config_params = _parse_config_parameters(manifest_data)

    # Extract external dependencies
    deps = manifest_data.get("dependencies", {})
    external_deps = deps.get("external", {}) if isinstance(deps, dict) else {}
    external_deps = external_deps or {}

    # Extract metadata
    metadata = manifest_data.get("metadata", {})
    safe_domain = metadata.get("safe_domain") if isinstance(metadata, dict) else None
    prohibited = metadata.get("prohibited", []) if isinstance(metadata, dict) else []

    # Extract platform requirements
    platform_requirements = manifest_data.get("platform_requirements", [])
    platform_requirements_rationale = manifest_data.get("platform_requirements_rationale")

    # Check platform availability using shared helper
    platform_available = _check_platform_requirements_satisfied(platform_requirements)

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
        is_mock=module_info.get("MOCK", False) or module_info.get("is_mock", False),
        safe_domain=safe_domain if isinstance(safe_domain, str) else None,
        prohibited=prohibited if isinstance(prohibited, list) else [],
        metadata=metadata if isinstance(metadata, dict) else None,
        platform_requirements=platform_requirements,
        platform_requirements_rationale=platform_requirements_rationale,
        platform_available=platform_available,
    )


async def _read_manifest_async(manifest_path: Path) -> Optional[Dict[str, Any]]:
    """Read and parse a manifest file asynchronously."""
    import aiofiles

    try:
        async with aiofiles.open(manifest_path, mode="r") as f:
            content = await f.read()
        result: Dict[str, Any] = json.loads(content)
        return result
    except Exception:
        return None


def _try_load_service_manifest(service_name: str, apply_filter: bool = True) -> Optional[ModuleTypeInfo]:
    """Try to load a modular service manifest by name."""
    import importlib

    try:
        submodule = importlib.import_module(f"ciris_adapters.{service_name}")
        if not hasattr(submodule, "__path__"):
            return None
        manifest_file = Path(submodule.__path__[0]) / MANIFEST_FILENAME
        if not manifest_file.exists():
            return None
        with open(manifest_file) as f:
            manifest_data = json.load(f)

        # Filter out mock/common/library modules from public listings
        if apply_filter and _should_filter_adapter(manifest_data):
            logger.debug("Filtering adapter %s from listings (mock/common/library)", service_name)
            return None

        return _parse_manifest_to_module_info(manifest_data, service_name)
    except Exception as e:
        logger.debug("Service %s not available: %s", service_name, e)
        return None


async def _discover_services_from_directory(services_base: Path) -> List[ModuleTypeInfo]:
    """Discover modular services by iterating the services directory."""
    adapters: List[ModuleTypeInfo] = []

    for item in services_base.iterdir():
        if not item.is_dir() or item.name.startswith("_"):
            continue

        # Try importlib-based loading first (Android compatibility)
        module_info = _try_load_service_manifest(item.name)
        if module_info:
            adapters.append(module_info)
            logger.debug("Discovered modular service: %s", item.name)
            continue

        # Fallback to direct file access
        manifest_path = item / MANIFEST_FILENAME
        manifest_data = await _read_manifest_async(manifest_path)
        if manifest_data:
            # Apply filter for direct file access path
            if _should_filter_adapter(manifest_data):
                logger.debug("Filtering adapter %s from listings (mock/common/library)", item.name)
                continue

            module_info = _parse_manifest_to_module_info(manifest_data, item.name)
            adapters.append(module_info)
            logger.debug("Discovered modular service (direct): %s", item.name)

    return adapters


async def _discover_services_via_entry_points() -> List[ModuleTypeInfo]:
    """Discover modular services via importlib.metadata entry points."""
    from importlib.metadata import entry_points
    from typing import Iterable

    adapters: List[ModuleTypeInfo] = []

    try:
        # Get entry points - API varies by Python version
        eps = entry_points()

        # Try the modern API first (Python 3.10+)
        adapter_eps: Iterable[Any]
        if hasattr(eps, "select"):
            # Python 3.10+ with SelectableGroups
            adapter_eps = eps.select(group=ADAPTER_ENTRY_POINT_GROUP)
        elif isinstance(eps, dict):
            # Python 3.9 style dict-like access
            adapter_eps = eps.get(ADAPTER_ENTRY_POINT_GROUP, [])
        else:
            # Fallback - try to iterate or access as needed
            adapter_eps = getattr(eps, ADAPTER_ENTRY_POINT_GROUP, [])

        for ep in adapter_eps:
            module_info = _try_load_service_manifest(ep.name)
            if module_info:
                adapters.append(module_info)
                logger.debug("Discovered adapter via entry point: %s", ep.name)

    except Exception as e:
        logger.warning("Entry point discovery failed: %s", e)

    return adapters


async def _discover_adapters() -> List[ModuleTypeInfo]:
    """Discover all available modular services."""
    try:
        import ciris_adapters

        if not hasattr(ciris_adapters, "__path__"):
            return await _discover_services_via_entry_points()

        services_base = Path(ciris_adapters.__path__[0])
        logger.debug("Modular services base path: %s", services_base)

        try:
            return await _discover_services_from_directory(services_base)
        except OSError as e:
            logger.debug("iterdir failed (%s), falling back to entry points", e)
            return await _discover_services_via_entry_points()

    except ImportError as e:
        logger.debug("ciris_adapters not available: %s", e)
        return await _discover_services_via_entry_points()


# ============================================================================
# Endpoints
# ============================================================================


@router.get("/adapters", response_model=SuccessResponse[AdapterListResponse])
async def list_adapters(
    request: Request, auth: AuthContext = Depends(require_observer)
) -> SuccessResponse[AdapterListResponse]:
    """
    List all loaded adapters.

    Returns information about all currently loaded adapter instances
    including their type, status, and basic metrics.
    """
    runtime_control = getattr(request.app.state, "main_runtime_control_service", None)
    if not runtime_control:
        raise HTTPException(status_code=503, detail=ERROR_RUNTIME_CONTROL_SERVICE_NOT_AVAILABLE)

    try:
        # Get adapter list from runtime control service
        adapters = await runtime_control.list_adapters()
        seen_adapter_ids = {a.adapter_id for a in adapters}

        # Also include auto-loaded adapters from ServiceRegistry
        service_registry = getattr(request.app.state, "service_registry", None)
        if service_registry:
            from ciris_engine.schemas.runtime.enums import ServiceType

            for service_type in [ServiceType.TOOL, ServiceType.WISE_AUTHORITY]:
                try:
                    providers = service_registry.get_providers_by_type(service_type)
                    for provider_info in providers:
                        metadata = provider_info.get("metadata", {})
                        if metadata.get("auto_loaded"):
                            adapter_name = metadata.get("adapter", "unknown")
                            adapter_id = f"{adapter_name}_auto"
                            if adapter_id not in seen_adapter_ids:
                                seen_adapter_ids.add(adapter_id)
                                adapters.append(
                                    AdapterInfo(
                                        adapter_id=adapter_id,
                                        adapter_type=adapter_name.upper(),
                                        status=AdapterStatus.RUNNING,
                                        started_at=datetime.now(timezone.utc),
                                        config_params=AdapterConfig(
                                            adapter_type=adapter_name, enabled=True, settings={}
                                        ),
                                        services_registered=[service_type.value],
                                        messages_processed=0,
                                        error_count=0,
                                        last_error=None,
                                        tools=[],
                                    )
                                )
                except Exception as e:
                    logger.debug(f"Error getting {service_type} providers: {e}")

        # Convert to response format
        adapter_statuses = []
        for adapter in adapters:
            # Convert AdapterInfo to AdapterStatusSchema
            is_running = adapter.status == AdapterStatus.RUNNING or str(adapter.status).lower() == "running"

            # Use actual config from adapter if available
            config = adapter.config_params or AdapterConfig(
                adapter_type=adapter.adapter_type, enabled=is_running, settings={}
            )

            metrics = None
            if adapter.messages_processed > 0 or adapter.error_count > 0:
                metrics = AdapterMetrics(
                    messages_processed=adapter.messages_processed,
                    errors_count=adapter.error_count,
                    uptime_seconds=(
                        (datetime.now(timezone.utc) - adapter.started_at).total_seconds() if adapter.started_at else 0
                    ),
                    last_error=adapter.last_error,
                    last_error_time=None,
                )

            adapter_statuses.append(
                AdapterStatusSchema(
                    adapter_id=adapter.adapter_id,
                    adapter_type=adapter.adapter_type,
                    is_running=is_running,
                    loaded_at=adapter.started_at or datetime.now(timezone.utc),
                    services_registered=adapter.services_registered,
                    config_params=config,
                    metrics=metrics,
                    last_activity=None,
                    tools=adapter.tools,
                )
            )

        running_count = sum(1 for a in adapter_statuses if a.is_running)

        response = AdapterListResponse(
            adapters=adapter_statuses, total_count=len(adapter_statuses), running_count=running_count
        )

        return SuccessResponse(data=response)

    except ValidationError as e:
        logger.error(f"Validation error listing adapters: {e}")
        logger.error(f"Validation errors detail: {e.errors()}")
        return SuccessResponse(data=AdapterListResponse(adapters=[], total_count=0, running_count=0))
    except Exception as e:
        logger.error(f"Error listing adapters: {e}")
        logger.error(f"Error type: {type(e).__name__}")
        import traceback

        logger.error(f"Traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/adapters/types", response_model=SuccessResponse[ModuleTypesResponse])
async def list_module_types(
    request: Request, auth: AuthContext = Depends(require_observer)
) -> SuccessResponse[ModuleTypesResponse]:
    """
    List all available module/adapter types.

    Returns both core adapters (api, cli, discord) and modular services
    (mcp_client, mcp_server, reddit, etc.) with their typed configuration schemas.
    """
    try:
        # Get core adapters
        core_adapter_types = ["api", "cli", "discord"]
        core_modules = [_get_core_adapter_info(t) for t in core_adapter_types]

        # Discover modular services
        adapters = await _discover_adapters()

        response = ModuleTypesResponse(
            core_modules=core_modules,
            adapters=adapters,
            total_core=len(core_modules),
            total_adapters=len(adapters),
        )

        return SuccessResponse(data=response)

    except Exception as e:
        logger.error("Error listing module types: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


# NOTE: Static routes must come BEFORE the parametrized route /adapters/{adapter_id}


@router.get(
    "/adapters/persisted",
    response_model=SuccessResponse[PersistedConfigsResponse],
)
async def list_persisted_configurations(
    request: Request,
    auth: AuthContext = Depends(require_admin),
) -> SuccessResponse[PersistedConfigsResponse]:
    """
    List all persisted adapter configurations.

    Returns configurations that are set to load on startup.

    Requires ADMIN role.
    """
    try:
        adapter_config_service = getattr(request.app.state, "adapter_configuration_service", None)
        config_service = getattr(request.app.state, "config_service", None)

        if not adapter_config_service:
            raise HTTPException(status_code=503, detail=ERROR_ADAPTER_CONFIG_SERVICE_NOT_AVAILABLE)

        persisted_configs: Dict[str, Dict[str, Any]] = {}
        if config_service:
            persisted_configs = await adapter_config_service.load_persisted_configs(config_service)

        response = PersistedConfigsResponse(
            persisted_configs=persisted_configs,
            count=len(persisted_configs),
        )
        return SuccessResponse(data=response)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing persisted configurations: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete(
    "/adapters/{adapter_type}/persisted",
    response_model=SuccessResponse[RemovePersistedResponse],
)
async def remove_persisted_configuration(
    adapter_type: str,
    request: Request,
    auth: AuthContext = Depends(require_admin),
) -> SuccessResponse[RemovePersistedResponse]:
    """
    Remove a persisted adapter configuration.

    This prevents the adapter from being automatically loaded on startup.

    Requires ADMIN role.
    """
    try:
        adapter_config_service = getattr(request.app.state, "adapter_configuration_service", None)
        config_service = getattr(request.app.state, "config_service", None)

        if not adapter_config_service:
            raise HTTPException(status_code=503, detail=ERROR_ADAPTER_CONFIG_SERVICE_NOT_AVAILABLE)

        if not config_service:
            raise HTTPException(status_code=503, detail="Config service not available")

        success = await adapter_config_service.remove_persisted_config(
            adapter_type=adapter_type,
            config_service=config_service,
        )

        if success:
            message = f"Removed persisted configuration for {adapter_type}"
        else:
            message = f"No persisted configuration found for {adapter_type}"

        response = RemovePersistedResponse(
            success=success,
            adapter_type=adapter_type,
            message=message,
        )
        return SuccessResponse(data=response)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error removing persisted configuration: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/adapters/available", response_model=SuccessResponse[Dict[str, Any]])
async def list_available_adapters(
    request: Request, auth: AuthContext = Depends(require_observer)
) -> SuccessResponse[Dict[str, Any]]:
    """
    List all discovered adapters with eligibility status.

    Returns both eligible (ready to use) and ineligible (missing requirements)
    adapters, including installation hints for ineligible adapters.
    """
    from ciris_engine.logic.services.tool.discovery_service import AdapterDiscoveryService

    try:
        discovery = AdapterDiscoveryService()
        report = await discovery.get_discovery_report()

        return SuccessResponse(data=report.model_dump())

    except Exception as e:
        logger.error(f"Error getting adapter availability: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/adapters/{adapter_name}/install", response_model=SuccessResponse[Dict[str, Any]])
async def install_adapter_dependencies(
    adapter_name: str,
    request: Request,
    body: Dict[str, Any] = Body(default={}),
    auth: AuthContext = Depends(require_admin),
) -> SuccessResponse[Dict[str, Any]]:
    """
    Install missing dependencies for an adapter.

    Attempts to install missing binaries or packages using the adapter's
    install hints (brew, apt, pip, npm, etc.).

    Requires ADMIN role.
    """
    from ciris_engine.logic.services.tool.discovery_service import AdapterDiscoveryService
    from ciris_engine.logic.services.tool.installer import ToolInstaller
    from ciris_engine.schemas.adapters.discovery import InstallResponse

    try:
        dry_run = body.get("dry_run", False)
        install_step_id = body.get("install_step_id")

        discovery = AdapterDiscoveryService()
        status = await discovery.get_adapter_eligibility(adapter_name)

        if not status:
            raise HTTPException(status_code=404, detail=f"Adapter '{adapter_name}' not found")

        if status.eligible:
            return SuccessResponse(
                data=InstallResponse(
                    success=True,
                    message=f"Adapter '{adapter_name}' is already eligible",
                    now_eligible=True,
                    eligibility=status,
                ).model_dump()
            )

        if not status.can_install or not status.install_hints:
            return SuccessResponse(
                data=InstallResponse(
                    success=False,
                    message=f"No installation hints available for '{adapter_name}'",
                    now_eligible=False,
                    eligibility=status,
                ).model_dump()
            )

        # Find specific step if requested, otherwise use all hints
        hints = status.install_hints
        if install_step_id:
            hints = [h for h in hints if h.id == install_step_id]
            if not hints:
                return SuccessResponse(
                    data=InstallResponse(
                        success=False,
                        message=f"Install step '{install_step_id}' not found",
                        now_eligible=False,
                    ).model_dump()
                )

        # Run installation
        installer = ToolInstaller(dry_run=dry_run)
        install_result = await installer.install_first_applicable(hints)

        # Recheck eligibility after installation
        new_status = await discovery.get_adapter_eligibility(adapter_name)

        return SuccessResponse(
            data=InstallResponse(
                success=install_result.success,
                message=install_result.message,
                installed_binaries=install_result.binaries_installed or [],
                now_eligible=new_status.eligible if new_status else False,
                eligibility=new_status,
            ).model_dump()
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error installing adapter dependencies: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/adapters/{adapter_name}/check-eligibility", response_model=SuccessResponse[Dict[str, Any]])
async def recheck_adapter_eligibility(
    adapter_name: str,
    request: Request,
    auth: AuthContext = Depends(require_observer),
) -> SuccessResponse[Dict[str, Any]]:
    """
    Recheck eligibility for an adapter.

    Useful after manual installation of dependencies to see if the
    adapter is now eligible.
    """
    from ciris_engine.logic.services.tool.discovery_service import AdapterDiscoveryService
    from ciris_engine.schemas.adapters.discovery import RecheckEligibilityResponse

    try:
        discovery = AdapterDiscoveryService()
        status = await discovery.get_adapter_eligibility(adapter_name)

        if not status:
            raise HTTPException(status_code=404, detail=f"Adapter '{adapter_name}' not found")

        return SuccessResponse(
            data=RecheckEligibilityResponse(
                name=adapter_name,
                eligible=status.eligible,
                eligibility_reason=status.eligibility_reason,
                missing_binaries=status.missing_binaries,
                missing_env_vars=status.missing_env_vars,
                missing_config=status.missing_config,
                can_install=status.can_install,
            ).model_dump()
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error checking adapter eligibility: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/adapters/configurable", response_model=SuccessResponse[ConfigurableAdaptersResponse])
async def list_configurable_adapters(
    request: Request, auth: AuthContext = Depends(require_admin)
) -> SuccessResponse[ConfigurableAdaptersResponse]:
    """
    List adapters that support interactive configuration.

    Returns information about all adapters that have defined interactive
    configuration workflows, including their workflow types and step counts.

    Requires ADMIN role.
    """
    try:
        config_service = get_adapter_config_service(request)
        adapter_types = config_service.get_configurable_adapters()

        # Build detailed info for each adapter
        adapters = []
        for adapter_type in adapter_types:
            manifest = config_service._adapter_manifests.get(adapter_type)
            if not manifest:
                continue

            # Check if any step is OAuth
            requires_oauth = any(step.step_type == "oauth" for step in manifest.steps)

            adapters.append(
                ConfigurableAdapterInfo(
                    adapter_type=adapter_type,
                    name=adapter_type.replace("_", " ").title(),
                    description=f"Interactive configuration for {adapter_type}",
                    workflow_type=manifest.workflow_type,
                    step_count=len(manifest.steps),
                    requires_oauth=requires_oauth,
                    steps=[
                        ConfigStepInfo(
                            step_id=step.step_id,
                            step_type=step.step_type,
                            title=step.title,
                            description=step.description,
                            optional=getattr(step, "optional", False),
                        )
                        for step in manifest.steps
                    ],
                )
            )

        response = ConfigurableAdaptersResponse(adapters=adapters, total_count=len(adapters))
        return SuccessResponse(data=response)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing configurable adapters: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/adapters/{adapter_id}", response_model=SuccessResponse[AdapterStatusSchema])
async def get_adapter_status(
    adapter_id: str, request: Request, auth: AuthContext = Depends(require_observer)
) -> SuccessResponse[AdapterStatusSchema]:
    """
    Get detailed status of a specific adapter.

    Returns comprehensive information about an adapter instance
    including configuration, metrics, and service registrations.
    """
    runtime_control = getattr(request.app.state, "main_runtime_control_service", None)
    if not runtime_control:
        raise HTTPException(status_code=503, detail=ERROR_RUNTIME_CONTROL_SERVICE_NOT_AVAILABLE)

    try:
        # Get adapter info from runtime control service
        adapter_info = await runtime_control.get_adapter_info(adapter_id)

        if not adapter_info:
            raise HTTPException(status_code=404, detail=f"Adapter '{adapter_id}' not found")

        # Debug logging
        logger.info(f"Adapter info type: {type(adapter_info)}, value: {adapter_info}")

        # Convert to response format
        metrics_dict = None
        if adapter_info.messages_processed > 0 or adapter_info.error_count > 0:
            metrics = AdapterMetrics(
                messages_processed=adapter_info.messages_processed,
                errors_count=adapter_info.error_count,
                uptime_seconds=(
                    (datetime.now(timezone.utc) - adapter_info.started_at).total_seconds()
                    if adapter_info.started_at
                    else 0
                ),
                last_error=adapter_info.last_error,
                last_error_time=None,
            )
            metrics_dict = metrics.__dict__

        # Use actual config from adapter if available, otherwise create minimal default
        config_params = adapter_info.config_params or AdapterConfig(
            adapter_type=adapter_info.adapter_type, enabled=True, settings={}
        )

        status = AdapterStatusSchema(
            adapter_id=adapter_info.adapter_id,
            adapter_type=adapter_info.adapter_type,
            is_running=adapter_info.status == AdapterStatus.RUNNING,
            loaded_at=adapter_info.started_at,
            services_registered=adapter_info.services_registered,
            config_params=config_params,
            metrics=metrics_dict,
            last_activity=None,
            tools=adapter_info.tools,
        )

        return SuccessResponse(data=status)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting adapter status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/adapters/{adapter_type}", response_model=SuccessResponse[AdapterOperationResult])
async def load_adapter(
    adapter_type: str,
    body: AdapterActionRequest,
    request: Request,
    adapter_id: Optional[str] = None,
    auth: AuthContext = Depends(require_admin),
) -> SuccessResponse[AdapterOperationResult]:
    """
    Load a new adapter instance.

    Dynamically loads and starts a new adapter of the specified type.
    Requires ADMIN role.

    Adapter types: cli, api, discord, mcp, mcp_server
    """
    runtime_control = getattr(request.app.state, "main_runtime_control_service", None)
    if not runtime_control:
        raise HTTPException(status_code=503, detail=ERROR_RUNTIME_CONTROL_SERVICE_NOT_AVAILABLE)

    try:
        # Generate adapter ID if not provided
        import uuid

        if not adapter_id:
            adapter_id = f"{adapter_type}_{uuid.uuid4().hex[:8]}"

        logger.info(f"[LOAD_ADAPTER] Loading adapter: type={adapter_type}, id={adapter_id}, persist={body.persist}")

        # Merge persist flag into config for RuntimeAdapterManager
        config = body.config or {}
        if isinstance(config, dict):
            config["persist"] = body.persist

        logger.debug(f"[LOAD_ADAPTER] Config: {config}")

        result = await runtime_control.load_adapter(adapter_type=adapter_type, adapter_id=adapter_id, config=config)

        logger.info(
            f"[LOAD_ADAPTER] Result: success={result.success}, adapter_id={result.adapter_id}, error={result.error}"
        )

        # Convert response
        response = AdapterOperationResult(
            success=result.success,
            adapter_id=result.adapter_id,
            adapter_type=adapter_type,
            message=result.error if not result.success else f"Adapter {result.adapter_id} loaded successfully",
            error=result.error,
            details={"timestamp": result.timestamp.isoformat()},
        )

        return SuccessResponse(data=response)

    except Exception as e:
        logger.error(f"[LOAD_ADAPTER] Error loading adapter type={adapter_type}, id={adapter_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/adapters/{adapter_id}", response_model=SuccessResponse[AdapterOperationResult])
async def unload_adapter(
    adapter_id: str, request: Request, auth: AuthContext = Depends(require_admin)
) -> SuccessResponse[AdapterOperationResult]:
    """
    Unload an adapter instance.

    Stops and removes an adapter from the runtime.
    Will fail if it's the last communication-capable adapter.
    Requires ADMIN role.
    """
    runtime_control = getattr(request.app.state, "main_runtime_control_service", None)
    if not runtime_control:
        raise HTTPException(status_code=503, detail=ERROR_RUNTIME_CONTROL_SERVICE_NOT_AVAILABLE)

    try:
        # Unload adapter through runtime control service
        result = await runtime_control.unload_adapter(
            adapter_id=adapter_id, force=False  # Never force, respect safety checks
        )

        # Log failures explicitly
        if not result.success:
            logger.error(f"Adapter unload failed: {result.error}")

        # Convert response
        response = AdapterOperationResult(
            success=result.success,
            adapter_id=result.adapter_id,
            adapter_type=result.adapter_type,
            message=result.error if not result.success else f"Adapter {result.adapter_id} unloaded successfully",
            error=result.error,
            details={"timestamp": result.timestamp.isoformat()},
        )

        return SuccessResponse(data=response)

    except Exception as e:
        logger.error(f"Error unloading adapter: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/adapters/{adapter_id}/reload", response_model=SuccessResponse[AdapterOperationResult])
async def reload_adapter(
    adapter_id: str, body: AdapterActionRequest, request: Request, auth: AuthContext = Depends(require_admin)
) -> SuccessResponse[AdapterOperationResult]:
    """
    Reload an adapter with new configuration.

    Stops the adapter and restarts it with new configuration.
    Useful for applying configuration changes without full restart.
    Requires ADMIN role.
    """
    runtime_control = getattr(request.app.state, "main_runtime_control_service", None)
    if not runtime_control:
        raise HTTPException(status_code=503, detail=ERROR_RUNTIME_CONTROL_SERVICE_NOT_AVAILABLE)

    try:
        # Get current adapter info to preserve type
        adapter_info = await runtime_control.get_adapter_info(adapter_id)
        if not adapter_info:
            raise HTTPException(status_code=404, detail=f"Adapter '{adapter_id}' not found")

        # First unload the adapter
        unload_result = await runtime_control.unload_adapter(adapter_id, force=False)
        if not unload_result.success:
            raise HTTPException(status_code=400, detail=f"Failed to unload adapter: {unload_result.error}")

        # Then reload with new config
        # Merge persist flag into config for RuntimeAdapterManager
        config = body.config or {}
        if isinstance(config, dict):
            config["persist"] = body.persist

        load_result = await runtime_control.load_adapter(
            adapter_type=adapter_info.adapter_type,
            adapter_id=adapter_id,
            config=config,
        )

        # Convert response
        response = AdapterOperationResult(
            success=load_result.success,
            adapter_id=load_result.adapter_id,
            adapter_type=adapter_info.adapter_type,
            message=(
                f"Adapter {adapter_id} reloaded successfully"
                if load_result.success
                else f"Reload failed: {load_result.error}"
            ),
            error=load_result.error,
            details={"timestamp": load_result.timestamp.isoformat()},
        )

        return SuccessResponse(data=response)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error reloading adapter: {e}")
        raise HTTPException(status_code=500, detail=str(e))
