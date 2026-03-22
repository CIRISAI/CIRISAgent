"""Helper functions for CIRIS setup module.

This module contains shared utility functions used by setup endpoints,
including adapter discovery, template loading, and password validation.

Adapter discovery uses the shared module `_adapter_discovery.py` to ensure
consistency with the "Add Adapters" card in system/adapters.py.
"""

import asyncio
import logging
import secrets
from typing import TYPE_CHECKING, Any, List

if TYPE_CHECKING:
    from ciris_engine.schemas.runtime.adapter_management import ModuleTypeInfo

from fastapi import HTTPException, status

from ciris_engine.logic.setup.first_run import is_first_run

from .._adapter_discovery import discover_adapters, get_cli_dependency_status
from .models import AdapterConfig, AgentTemplate, SetupCompleteRequest

logger = logging.getLogger(__name__)

# Constants for adapter filtering
_SKIP_ADAPTERS = {"ciris_accord_metrics"}  # Handled by consent checkbox in setup
_CIRIS_SERVICES_ADAPTERS = {"ciris_hosted_tools"}  # Require Google sign-in


def _is_setup_allowed_without_auth() -> bool:
    """Check if setup endpoints should be accessible without authentication.

    Returns True during first-run (no config exists).
    Returns False after setup (config exists, requires auth).
    """
    return is_first_run()


def _get_agent_templates() -> List[AgentTemplate]:
    """Get list of available agent templates from ciris_templates directory.

    Returns template metadata for GUI display including:
    - 4 default DSAR SOPs for GDPR compliance
    - Book VI Stewardship information with creator signature
    """
    import yaml

    from ciris_engine.logic.utils.path_resolution import get_template_directory
    from ciris_engine.schemas.config.agent import AgentTemplate as ConfigAgentTemplate

    templates: List[AgentTemplate] = []
    template_dir = get_template_directory()

    logger.info(f"[SETUP TEMPLATES] Loading templates from: {template_dir}")
    logger.info(f"[SETUP TEMPLATES] Directory exists: {template_dir.exists()}")

    # Skip test.yaml and backup files
    skip_templates = {"test.yaml", "CIRIS_TEMPLATE_GUIDE.md"}

    yaml_files = list(template_dir.glob("*.yaml"))
    logger.info(f"[SETUP TEMPLATES] Found {len(yaml_files)} .yaml files: {[f.name for f in yaml_files]}")

    for template_file in yaml_files:
        if template_file.name in skip_templates or template_file.name.endswith(".backup"):
            logger.info(f"[SETUP TEMPLATES] Skipping: {template_file.name}")
            continue

        try:
            logger.info(f"[SETUP TEMPLATES] Loading: {template_file.name}")
            with open(template_file, "r") as f:
                template_data = yaml.safe_load(f)

            # Load and validate template
            config_template = ConfigAgentTemplate(**template_data)

            # Skip internal-only templates (same pattern as adapters)
            if config_template.internal_only:
                logger.info(f"[SETUP TEMPLATES] Skipping internal template: {template_file.name}")
                continue

            # Extract SOP names from tickets config
            supported_sops: List[str] = []
            if config_template.tickets and config_template.tickets.sops:
                supported_sops = [sop.sop for sop in config_template.tickets.sops]

            # Extract stewardship info
            stewardship_tier = 3  # Default medium risk
            creator_id = "Unknown"
            signature = "unsigned"

            if config_template.stewardship:
                stewardship_tier = config_template.stewardship.stewardship_tier
                creator_id = config_template.stewardship.creator_ledger_entry.creator_id
                signature = config_template.stewardship.creator_ledger_entry.signature

            # Create API response template
            template = AgentTemplate(
                id=template_file.stem,  # Use filename without .yaml as ID
                name=config_template.name,
                description=config_template.description,
                identity=config_template.role_description,
                example_use_cases=[],  # Can be added to template schema later
                supported_sops=supported_sops,
                stewardship_tier=stewardship_tier,
                creator_id=creator_id,
                signature=signature,
            )

            templates.append(template)
            logger.info(f"[SETUP TEMPLATES] Loaded: id={template.id}, name={template.name}")

        except Exception as e:
            logger.warning(f"[SETUP TEMPLATES] Failed to load template {template_file}: {e}")
            continue

    logger.info(f"[SETUP TEMPLATES] Total templates loaded: {len(templates)}")
    logger.info(f"[SETUP TEMPLATES] Template IDs: {[t.id for t in templates]}")
    return templates


def _module_info_to_adapter_config(module_info: "ModuleTypeInfo") -> AdapterConfig:
    """Convert ModuleTypeInfo from shared discovery to AdapterConfig for setup API.

    Args:
        module_info: ModuleTypeInfo from _adapter_discovery module

    Returns:
        AdapterConfig for setup wizard API response
    """
    from ciris_engine.schemas.runtime.adapter_management import ModuleTypeInfo

    capabilities = module_info.capabilities or []
    requires_binaries = "requires:binaries" in capabilities

    # Extract supported platforms from metadata
    supported_platforms: List[str] = []
    if module_info.metadata:
        platforms = module_info.metadata.get("supported_platforms")
        if platforms and isinstance(platforms, list):
            supported_platforms = platforms

    requires_ciris_services = module_info.module_id in _CIRIS_SERVICES_ADAPTERS

    # Get CLI dependency info
    cli_deps, missing_deps, _ = get_cli_dependency_status(module_info)

    return AdapterConfig(
        id=module_info.module_id,
        name=module_info.name.replace("_", " ").title(),
        description=module_info.description or f"{module_info.module_id} adapter",
        enabled_by_default=requires_ciris_services,
        required_env_vars=[],
        optional_env_vars=[],
        platform_requirements=module_info.platform_requirements or [],
        platform_available=module_info.platform_available,
        requires_binaries=requires_binaries,
        required_binaries=cli_deps,
        supported_platforms=supported_platforms,
        requires_ciris_services=requires_ciris_services,
    )


def _get_available_adapters() -> List[AdapterConfig]:
    """Get all adapters using shared discovery logic.

    Uses the same filtering as the "Add Adapters" card via the shared
    _adapter_discovery module. This ensures consistency between first-run
    setup and runtime adapter management.

    Returns:
        List of AdapterConfig for setup wizard display
    """
    adapters: List[AdapterConfig] = []

    # Always include API adapter first (required, cannot be disabled)
    adapters.append(
        AdapterConfig(
            id="api",
            name="Web API",
            description="RESTful API server with built-in web interface",
            enabled_by_default=True,
            required_env_vars=[],
            optional_env_vars=["CIRIS_API_PORT", "NEXT_PUBLIC_API_BASE_URL"],
            platform_available=True,
            requires_binaries=False,
            required_binaries=[],
            supported_platforms=[],
            requires_ciris_services=False,
        )
    )

    try:
        # Use shared discovery with consistent filtering
        # filter_by_platform=True applies same filtering as Add Adapter card
        # skip_adapters excludes accord_metrics (handled by consent checkbox)
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            # Already in async context - create task
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(
                    asyncio.run, discover_adapters(filter_by_platform=True, skip_adapters=_SKIP_ADAPTERS)
                )
                discovered = future.result(timeout=10)
        else:
            # Not in async context - run directly
            discovered = asyncio.run(discover_adapters(filter_by_platform=True, skip_adapters=_SKIP_ADAPTERS))

        for module_info in discovered:
            # Skip internal-only adapters (e.g., ciris_verify)
            if module_info.internal_only:
                continue

            adapter_config = _module_info_to_adapter_config(module_info)
            adapters.append(adapter_config)
            logger.debug(
                f"[SETUP ADAPTERS] Discovered adapter: {module_info.module_id} "
                f"(requires_binaries={adapter_config.requires_binaries}, "
                f"platform_available={adapter_config.platform_available})"
            )

    except Exception as e:
        logger.warning(f"[SETUP ADAPTERS] Failed to discover adapters: {e}")
        import traceback

        logger.debug(f"[SETUP ADAPTERS] Traceback: {traceback.format_exc()}")

    logger.info(f"[SETUP ADAPTERS] Total adapters available: {len(adapters)}")
    return adapters


# Legacy function for backwards compatibility - now unused
def _should_skip_manifest(*args: Any, **kwargs: Any) -> bool:
    """DEPRECATED: Use shared _adapter_discovery.should_filter_adapter instead."""
    raise NotImplementedError("Use _adapter_discovery.should_filter_adapter instead")


def _create_adapter_from_manifest(*args: Any, **kwargs: Any) -> AdapterConfig:
    """DEPRECATED: Use _module_info_to_adapter_config instead."""
    raise NotImplementedError("Use _module_info_to_adapter_config instead")


def _validate_setup_passwords(setup: SetupCompleteRequest, is_oauth_user: bool) -> str:
    """Validate and potentially generate admin password for setup.

    For OAuth users without a password, generates a secure random password.
    For non-OAuth users, validates password requirements.

    Args:
        setup: Setup configuration request
        is_oauth_user: Whether user is authenticating via OAuth

    Returns:
        Validated or generated admin password

    Raises:
        HTTPException: If password validation fails
    """
    admin_password = setup.admin_password

    if not admin_password or len(admin_password) == 0:
        if is_oauth_user:
            # Generate a secure random password for OAuth users
            # They won't use this password - they'll authenticate via OAuth
            admin_password = secrets.token_urlsafe(32)
            logger.info("[Setup Complete] Generated random password for OAuth user (password auth disabled)")
        else:
            # Non-OAuth users MUST provide a password
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="New user password must be at least 8 characters"
            )
    elif len(admin_password) < 8:
        # If a password was provided, it must meet minimum requirements
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="New user password must be at least 8 characters"
        )

    # Validate system admin password strength if provided
    if setup.system_admin_password and len(setup.system_admin_password) < 8:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="System admin password must be at least 8 characters"
        )

    return admin_password


def _log_oauth_linking_skip(setup: SetupCompleteRequest) -> None:
    """Log debug information when OAuth linking is skipped."""
    logger.info("CIRIS_SETUP_DEBUG *** SKIPPING OAuth linking block - condition not met ***")
    if not setup.oauth_provider:
        logger.info("CIRIS_SETUP_DEBUG   Reason: oauth_provider is falsy/empty")
    if not setup.oauth_external_id:
        logger.info("CIRIS_SETUP_DEBUG   Reason: oauth_external_id is falsy/empty")
