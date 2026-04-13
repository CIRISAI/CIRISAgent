"""Setup completion endpoint and helpers for CIRIS.

This module provides the /complete endpoint and all helper functions
for saving configuration and creating users during setup.
"""

import asyncio
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Request, status

from ciris_engine.logic.config.db_paths import get_audit_db_full_path
from ciris_engine.logic.setup.wizard import create_env_file
from ciris_engine.schemas.api.responses import SuccessResponse

from .._common import RESPONSES_400_403_500
from .dependencies import SetupOnlyDep
from .helpers import _log_oauth_linking_skip, _validate_setup_passwords
from .llm_validation import _get_provider_base_url
from .models import SetupCompleteRequest

logger = logging.getLogger(__name__)

router = APIRouter()

# Module-level set to hold references to background tasks, preventing garbage collection
_background_tasks: set[asyncio.Task[None]] = set()


# =============================================================================
# SETUP USER HELPER FUNCTIONS
# =============================================================================


async def _link_oauth_identity_to_wa(auth_service: Any, setup: SetupCompleteRequest, wa_cert: Any) -> Any:
    """Link OAuth identity to WA, handling existing links gracefully.

    Returns the WA cert to use (may be updated if existing link found).
    """
    from ciris_engine.schemas.services.authority_core import WARole

    logger.debug("CIRIS_SETUP_DEBUG *** ENTERING OAuth linking block ***")
    logger.debug(  # NOSONAR - provider:external_id is not a secret, it's a provider-assigned ID
        f"CIRIS_SETUP_DEBUG Linking OAuth identity: {setup.oauth_provider}:{setup.oauth_external_id} to WA {wa_cert.wa_id}"
    )

    try:
        # First check if OAuth identity is already linked to another WA
        existing_wa = await auth_service.get_wa_by_oauth(setup.oauth_provider, setup.oauth_external_id)
        if existing_wa and existing_wa.wa_id != wa_cert.wa_id:
            logger.info(f"CIRIS_SETUP_DEBUG OAuth identity already linked to WA {existing_wa.wa_id}")
            logger.info(
                "CIRIS_SETUP_DEBUG During first-run setup, we'll update the existing WA to be ROOT instead of creating new"
            )
            # Update the existing WA to have ROOT role and update its name
            await auth_service.update_wa(
                wa_id=existing_wa.wa_id,
                name=setup.admin_username,
                role=WARole.ROOT,
            )
            logger.info(f"CIRIS_SETUP_DEBUG ✅ Updated existing WA {existing_wa.wa_id} to ROOT role")
            return existing_wa

        # No existing link or same WA - safe to link
        await auth_service.link_oauth_identity(
            wa_id=wa_cert.wa_id,
            provider=setup.oauth_provider,
            external_id=setup.oauth_external_id,
            account_name=setup.admin_username,
            metadata={"email": setup.oauth_email} if setup.oauth_email else None,
            primary=True,
        )
        logger.debug(  # NOSONAR - provider:external_id is not a secret
            f"CIRIS_SETUP_DEBUG ✅ SUCCESS: Linked OAuth {setup.oauth_provider}:{setup.oauth_external_id} to WA {wa_cert.wa_id}"
        )
    except Exception as e:
        logger.error(f"CIRIS_SETUP_DEBUG ❌ FAILED to link OAuth identity: {e}", exc_info=True)
        # Don't fail setup if OAuth linking fails - user can still use password

    return wa_cert


async def _update_system_admin_password(auth_service: Any, setup: SetupCompleteRequest, exclude_wa_id: str) -> None:
    """Update the default admin password if specified."""
    if not setup.system_admin_password:
        return

    logger.info("Updating default admin password...")
    all_was = await auth_service.list_was(active_only=True)
    admin_wa = next((wa for wa in all_was if wa.name == "admin" and wa.wa_id != exclude_wa_id), None)

    if admin_wa:
        admin_password_hash = auth_service.hash_password(setup.system_admin_password)
        await auth_service.update_wa(wa_id=admin_wa.wa_id, password_hash=admin_password_hash)
        logger.info("✅ Updated admin password")
    else:
        logger.warning("⚠️  Default admin WA not found")


async def _check_existing_oauth_wa(auth_service: Any, setup: SetupCompleteRequest) -> tuple[Optional[Any], bool]:
    """Check if OAuth user already exists and update to ROOT if found.

    Returns:
        Tuple of (wa_cert, was_found) where wa_cert is the WA certificate and
        was_found indicates if an existing WA was found and updated.
    """
    from ciris_engine.schemas.services.authority_core import WARole

    if not (setup.oauth_provider and setup.oauth_external_id):
        return None, False

    logger.debug(  # NOSONAR - provider:external_id is not a secret
        f"CIRIS_USER_CREATE: Checking for existing OAuth user: {setup.oauth_provider}:{setup.oauth_external_id}"
    )
    existing_wa = await auth_service.get_wa_by_oauth(setup.oauth_provider, setup.oauth_external_id)

    if not existing_wa:
        logger.info("CIRIS_USER_CREATE: No existing WA found for OAuth user - will create new")
        return None, False

    logger.info(f"CIRIS_USER_CREATE: ✓ Found existing WA for OAuth user: {existing_wa.wa_id}")
    logger.info(f"CIRIS_USER_CREATE:   Current role: {existing_wa.role}")
    logger.info(f"CIRIS_USER_CREATE:   Current name: {existing_wa.name}")

    # Update existing WA to ROOT role instead of creating new one
    logger.info(
        f"CIRIS_USER_CREATE: Updating existing WA {existing_wa.wa_id} to ROOT role (keeping name: {existing_wa.name})"
    )
    await auth_service.update_wa(wa_id=existing_wa.wa_id, role=WARole.ROOT)
    logger.info(f"CIRIS_USER_CREATE: ✅ Updated existing OAuth WA to ROOT: {existing_wa.wa_id}")

    return existing_wa, True


async def _create_new_wa(auth_service: Any, setup: SetupCompleteRequest) -> Any:
    """Create a new WA certificate for the setup user.

    Returns:
        WA certificate for the newly created user
    """
    from ciris_engine.schemas.services.authority_core import WARole

    logger.info(f"CIRIS_USER_CREATE: Creating NEW user: {setup.admin_username} with role: {WARole.ROOT}")

    # Use OAuth email if available, otherwise generate local email
    user_email = setup.oauth_email or f"{setup.admin_username}@local"
    masked_email = (user_email[:3] + "***@" + user_email.split("@")[-1]) if "@" in user_email else user_email
    logger.debug(f"CIRIS_USER_CREATE: User email: {masked_email}")  # NOSONAR - email masked

    # List existing WAs before creation for debugging
    existing_was = await auth_service.list_was(active_only=False)
    logger.info(f"CIRIS_USER_CREATE: Existing WAs before creation: {len(existing_was)}")
    for wa in existing_was:
        logger.info(f"CIRIS_USER_CREATE:   - {wa.wa_id}: name={wa.name}, role={wa.role}")

    # Create WA certificate
    wa_cert = await auth_service.create_wa(
        name=setup.admin_username,
        email=user_email,
        scopes=["read:any", "write:any"],  # ROOT gets full scopes
        role=WARole.ROOT,
    )
    logger.info(f"CIRIS_USER_CREATE: ✅ Created NEW WA: {wa_cert.wa_id}")

    return wa_cert


async def _set_password_for_wa(auth_service: Any, setup: SetupCompleteRequest, wa_cert: Any) -> None:
    """Set password hash for non-OAuth users."""
    is_oauth_setup = bool(setup.oauth_provider and setup.oauth_external_id)

    if is_oauth_setup:
        logger.info(f"CIRIS_USER_CREATE: Skipping password hash for OAuth user: {wa_cert.wa_id}")
        return

    # Hash password and update WA (admin_password is guaranteed set by validation above)
    assert setup.admin_password is not None, "admin_password should be set by validation"
    password_hash = auth_service.hash_password(setup.admin_password)
    await auth_service.update_wa(wa_id=wa_cert.wa_id, password_hash=password_hash)
    logger.info(f"CIRIS_USER_CREATE: Password hash set for WA: {wa_cert.wa_id}")


async def _ensure_system_wa(auth_service: Any) -> None:
    """Ensure system WA exists for signing system tasks."""
    system_wa_id = await auth_service.ensure_system_wa_exists()
    if system_wa_id:
        logger.info(f"✅ System WA ready: {system_wa_id}")
    else:
        logger.warning("⚠️ Could not create system WA - deferral handling may not work")


def _create_founding_partnership(wa_id: str, oauth_user_id: Optional[str] = None) -> None:
    """Create a default PARTNERED consent record for the setup user.

    The user who completes the setup wizard has explicitly consented by
    provisioning the agent.  The agent's consent is expressed through its
    template configuration — Ally's foundational identity is partnership
    ("Your growth supports mine").  This is configured consistency, not
    bypassed safeguards (see COGNITIVE_STATE_BEHAVIORS FSD).

    Creates a GraphNode with type=CONSENT using the consent/{user_id}
    pattern that matches the ConsentService lookups.

    IMPORTANT: For OAuth users, we must use the OAuth external ID (e.g.,
    "google:102773749033681671083") as the consent node ID, because that's
    what the consent service looks up when the user authenticates.

    Args:
        wa_id: The WA certificate ID (e.g., "wa-2026-04-01-337AE1")
        oauth_user_id: The OAuth external ID if available (e.g., "google:12345")
                       This takes precedence over wa_id for consent node ID.
    """
    from ciris_engine.logic.persistence import add_graph_node
    from ciris_engine.logic.services.lifecycle.time.service import TimeService
    from ciris_engine.schemas.consent.core import ConsentCategory, ConsentStatus, ConsentStream
    from ciris_engine.schemas.services.graph_core import GraphNode, GraphScope, NodeType

    now = datetime.now(timezone.utc)

    # Use OAuth user ID if available, otherwise fall back to WA ID
    # This is critical: ConsentService looks up consent by the user_id from auth,
    # which for OAuth users is the OAuth external ID (e.g., "google:12345")
    consent_user_id = oauth_user_id if oauth_user_id else wa_id

    partnered_status = ConsentStatus(
        user_id=consent_user_id,
        stream=ConsentStream.PARTNERED,
        categories=[
            ConsentCategory.INTERACTION,
            ConsentCategory.PREFERENCE,
            ConsentCategory.IMPROVEMENT,
        ],
        granted_at=now,
        expires_at=None,  # PARTNERED doesn't expire
        last_modified=now,
        impact_score=0.0,
        attribution_count=0,
    )

    # ConsentService stores nodes as consent/{user_id}
    # For OAuth users, user_id is the OAuth external ID (e.g., "google:12345")
    # For password users, user_id is the WA ID (e.g., "wa-2026-04-01-337AE1")
    node_id = f"consent/{consent_user_id}"

    node = GraphNode(
        id=node_id,
        type=NodeType.CONSENT,
        scope=GraphScope.LOCAL,
        attributes={
            "user_id": f"user/{consent_user_id}",
            "stream": (
                partnered_status.stream.value if hasattr(partnered_status.stream, "value") else partnered_status.stream
            ),
            "categories": [c.value if hasattr(c, "value") else c for c in partnered_status.categories],
            "granted_at": partnered_status.granted_at.isoformat(),
            "expires_at": None,
            "last_modified": partnered_status.last_modified.isoformat(),
            "impact_score": partnered_status.impact_score,
            "attribution_count": partnered_status.attribution_count,
            "partnership_approved": True,
            "approval_task_id": None,  # No task — founding partnership via setup wizard
            "founding_partnership": True,  # Distinguishes from bilateral consent flow
            "linked_wa_id": wa_id,  # WA certificate that owns this consent
        },
        updated_by="setup_wizard",
        updated_at=now,
    )

    time_service = TimeService()
    add_graph_node(node, time_service, None)
    print(f"[SETUP_COMPLETE] ✅ Founding partnership created: {node_id} (PARTNERED)")
    logger.info(f"✅ Founding partnership created for setup user: {node_id}")


def _store_user_preferences(user_id: str, setup: SetupCompleteRequest) -> None:
    """Store language and location preferences from setup wizard into graph memory.

    These preferences are stored as a graph node so the agent can access them
    during conversation to match the user's language and provide location-aware responses.
    """
    from ciris_engine.logic.persistence import add_graph_node
    from ciris_engine.logic.services.lifecycle.time.service import TimeService
    from ciris_engine.schemas.services.graph_core import GraphNode, GraphScope, NodeType

    attributes: dict[str, Any] = {}

    if setup.preferred_language:
        attributes["preferred_language"] = setup.preferred_language
    if setup.location_country:
        attributes["location_country"] = setup.location_country
    if setup.location_region:
        attributes["location_region"] = setup.location_region
    if setup.location_city:
        attributes["location_city"] = setup.location_city
    # Store coordinates if provided (ISO 6709 decimal degrees)
    if setup.location_latitude is not None:
        attributes["location_latitude"] = setup.location_latitude
    if setup.location_longitude is not None:
        attributes["location_longitude"] = setup.location_longitude
    if setup.timezone:
        attributes["timezone"] = setup.timezone
    # Store location sharing consent as a boolean
    attributes["share_location_in_traces"] = setup.share_location_in_traces

    if not attributes or (
        len(attributes) == 1 and "share_location_in_traces" in attributes and not setup.share_location_in_traces
    ):
        return

    # Build location string at user-chosen granularity
    location_parts = []
    if setup.location_city:
        location_parts.append(setup.location_city)
    if setup.location_region:
        location_parts.append(setup.location_region)
    if setup.location_country:
        location_parts.append(setup.location_country)
    if location_parts:
        attributes["location"] = ", ".join(location_parts)

    now = datetime.now(timezone.utc)
    node = GraphNode(
        id=f"preferences/{user_id}",
        type=NodeType.CONCEPT,
        scope=GraphScope.LOCAL,
        attributes=attributes,
        updated_by="setup_wizard",
        updated_at=now,
    )

    time_service = TimeService()
    add_graph_node(node, time_service, None)
    lang = attributes.get("preferred_language", "not set")
    loc = attributes.get("location", "not set")
    share_loc = attributes.get("share_location_in_traces", False)
    logger.info(f"Stored user preferences for {user_id}: lang={lang}, location={loc}, share_location={share_loc}")


async def _log_wa_list(auth_service: Any, phase: str) -> None:
    """Log list of WAs for debugging purposes."""
    was = await auth_service.list_was(active_only=False)
    logger.info(f"CIRIS_USER_CREATE: WAs {phase}: {len(was)}")
    for wa in was:
        logger.info(f"CIRIS_USER_CREATE:   - {wa.wa_id}: name={wa.name}, role={wa.role}")


async def _create_setup_users(setup: SetupCompleteRequest, auth_db_path: str) -> None:
    """Create users immediately during setup completion.

    This is called during setup completion to create users without waiting for restart.
    Creates users directly in the database using authentication store functions.

    IMPORTANT: For OAuth users, we check if they already exist and update to ROOT instead
    of creating a duplicate WA. This prevents multiple ROOT users from being created.

    Args:
        setup: Setup configuration with user details
        auth_db_path: Path to the audit database (from running application)
    """
    from ciris_engine.logic.services.infrastructure.authentication.service import AuthenticationService
    from ciris_engine.logic.services.lifecycle.time.service import TimeService

    logger.info("=" * 70)
    logger.info("CIRIS_USER_CREATE: _create_setup_users() called")
    logger.info("=" * 70)
    logger.info(f"CIRIS_USER_CREATE: auth_db_path = {auth_db_path}")
    logger.info(f"CIRIS_USER_CREATE: admin_username = {setup.admin_username}")
    logger.info(f"CIRIS_USER_CREATE: oauth_provider = {repr(setup.oauth_provider)}")
    logger.info(f"CIRIS_USER_CREATE: oauth_external_id = {repr(setup.oauth_external_id)}")
    logger.info(f"CIRIS_USER_CREATE: oauth_email = {repr(setup.oauth_email)}")

    # Create temporary authentication service for user creation
    time_service = TimeService()
    await time_service.start()

    auth_service = AuthenticationService(
        db_path=auth_db_path, time_service=time_service, key_dir=None  # Use default ~/.ciris/
    )
    await auth_service.start()

    try:
        # Check if OAuth user already exists and update to ROOT if found
        wa_cert, _ = await _check_existing_oauth_wa(auth_service, setup)

        # Create new WA if we didn't find an existing OAuth user
        if wa_cert is None:
            wa_cert = await _create_new_wa(auth_service, setup)

        # Set password for non-OAuth users
        await _set_password_for_wa(auth_service, setup, wa_cert)

        # Log WAs after creation for debugging
        await _log_wa_list(auth_service, "after setup")

        # Create founding partnership for setup user — the user consented by
        # completing setup, the agent's consent is configured in its template
        # For OAuth users, use the OAuth external ID as the consent node ID
        # (this is what ConsentService looks up when the user authenticates)
        oauth_user_id = None
        if setup.oauth_provider and setup.oauth_external_id:
            oauth_user_id = f"{setup.oauth_provider}:{setup.oauth_external_id}"
        _create_founding_partnership(wa_cert.wa_id, oauth_user_id)

        # Store user preferences keyed by wa_id for consistency
        _store_user_preferences(wa_cert.wa_id, setup)

        # Ensure system WA exists
        await _ensure_system_wa(auth_service)

        # CIRIS_SETUP_DEBUG: Log OAuth linking decision
        logger.debug("CIRIS_SETUP_DEBUG _create_setup_users() OAuth linking check:")
        logger.debug(f"CIRIS_SETUP_DEBUG   setup.oauth_provider = {repr(setup.oauth_provider)}")
        logger.debug(f"CIRIS_SETUP_DEBUG   setup.oauth_external_id = {repr(setup.oauth_external_id)}")
        logger.debug(f"CIRIS_SETUP_DEBUG   bool(setup.oauth_provider) = {bool(setup.oauth_provider)}")
        logger.debug(f"CIRIS_SETUP_DEBUG   bool(setup.oauth_external_id) = {bool(setup.oauth_external_id)}")
        oauth_link_condition = bool(setup.oauth_provider) and bool(setup.oauth_external_id)
        logger.debug(f"CIRIS_SETUP_DEBUG   Condition (provider AND external_id) = {oauth_link_condition}")

        # Link OAuth identity if provided - THIS IS CRITICAL for OAuth login to work
        if setup.oauth_provider and setup.oauth_external_id:
            wa_cert = await _link_oauth_identity_to_wa(auth_service, setup, wa_cert)
        else:
            _log_oauth_linking_skip(setup)

        # Update default admin password if specified
        assert wa_cert is not None, "wa_cert should be set by create_wa or existing WA lookup"
        await _update_system_admin_password(auth_service, setup, wa_cert.wa_id)

    finally:
        await auth_service.stop()
        await time_service.stop()


def _save_and_reload_config(setup: SetupCompleteRequest) -> Path:
    """Save setup configuration to .env and reload environment variables.

    Args:
        setup: Setup configuration request

    Returns:
        Path to the saved configuration file
    """
    from dotenv import load_dotenv

    from ciris_engine.logic.utils.path_resolution import get_ciris_home, is_android, is_development_mode

    logger.info("[Setup Complete] Path resolution:")
    logger.info(f"[Setup Complete]   is_android(): {is_android()}")
    logger.info(f"[Setup Complete]   is_development_mode(): {is_development_mode()}")
    logger.info(f"[Setup Complete]   get_ciris_home(): {get_ciris_home()}")

    # Save configuration (path determined internally by get_default_config_path)
    logger.info("[Setup Complete] Saving configuration...")
    config_path = _save_setup_config(setup)
    logger.info(f"[Setup Complete] Configuration saved to: {config_path}")

    # Verify the file was written
    if config_path.exists():
        file_size = config_path.stat().st_size
        logger.info(f"[Setup Complete] Verified: .env exists ({file_size} bytes)")
    else:
        logger.error(f"[Setup Complete] ERROR: .env file NOT found at {config_path} after save!")

    # Reload environment variables from the new .env file
    load_dotenv(config_path, override=True)
    logger.info(f"[Setup Complete] Reloaded environment variables from {config_path}")

    # Verify key env vars were loaded
    openai_key = os.getenv("OPENAI_API_KEY")
    openai_base = os.getenv("OPENAI_API_BASE")
    logger.info(f"[Setup Complete] After reload - OPENAI_API_KEY: {openai_key[:20] if openai_key else '(not set)'}...")
    logger.info(f"[Setup Complete] After reload - OPENAI_API_BASE: {openai_base}")

    return config_path


def _write_section_header(f: Any, title: str) -> None:
    """Write a section header with separators to the config file."""
    f.write("\n# ============================================================================\n")
    f.write(f"# {title}\n")
    f.write("# ============================================================================\n")


def _write_backup_llm_config(f: Any, setup: SetupCompleteRequest) -> None:
    """Write backup/secondary LLM configuration if provided."""
    if not setup.backup_llm_api_key:
        return
    f.write("\n# Backup/Secondary LLM Configuration\n")
    f.write(f'CIRIS_OPENAI_API_KEY_2="{setup.backup_llm_api_key}"\n')
    if setup.backup_llm_base_url:
        f.write(f'CIRIS_OPENAI_API_BASE_2="{setup.backup_llm_base_url}"\n')
    if setup.backup_llm_model:
        f.write(f'CIRIS_OPENAI_MODEL_NAME_2="{setup.backup_llm_model}"\n')


def _write_node_connection_config(f: Any, setup: SetupCompleteRequest) -> None:
    """Write CIRISNode connection configuration if provided."""
    if not setup.node_url:
        return
    _write_section_header(f, "CIRISNode Connection (provisioned via device auth)")
    f.write(f'CIRISNODE_BASE_URL="{setup.node_url}"\n')
    if setup.identity_template:
        f.write(f'CIRIS_IDENTITY_TEMPLATE="{setup.identity_template}"\n')
    if setup.stewardship_tier is not None:
        f.write(f"CIRIS_STEWARDSHIP_TIER={setup.stewardship_tier}\n")
    if setup.approved_adapters:
        f.write(f'CIRIS_APPROVED_ADAPTERS="{",".join(setup.approved_adapters)}"\n')
    if setup.org_id:
        f.write(f'CIRIS_ORG_ID="{setup.org_id}"\n')
    # Portal-issued key ID (private key is stored in hardware keystore, NOT here)
    if setup.signing_key_id:
        f.write(f'CIRIS_SIGNING_KEY_ID="{setup.signing_key_id}"\n')


def _write_licensed_package_config(f: Any, setup: SetupCompleteRequest) -> None:
    """Write licensed module package configuration if provided."""
    if not setup.licensed_package_path:
        return
    _write_section_header(f, "Licensed Module Package")
    f.write(f'CIRIS_LICENSED_PACKAGE_PATH="{setup.licensed_package_path}"\n')
    if setup.licensed_modules_path:
        f.write(f'CIRIS_MODULE_PATH="{setup.licensed_modules_path}"\n')


def _write_verify_config(f: Any, setup: SetupCompleteRequest) -> None:
    """Write CIRISVerify configuration if provided."""
    if not setup.verify_binary_path:
        return
    _write_section_header(f, "CIRISVerify")
    f.write(f'CIRIS_VERIFY_BINARY_PATH="{setup.verify_binary_path}"\n')
    require_hw = "true" if setup.verify_require_hardware else "false"
    f.write(f"CIRIS_VERIFY_REQUIRE_HARDWARE={require_hw}\n")


def _save_setup_config(setup: SetupCompleteRequest) -> Path:
    """Save setup configuration to .env file.

    Args:
        setup: Setup configuration

    Returns:
        Path where config was saved
    """
    llm_base_url = _get_provider_base_url(setup.llm_provider, setup.llm_base_url) or ""
    config_path = create_env_file(
        llm_provider=setup.llm_provider,
        llm_api_key=setup.llm_api_key,
        llm_base_url=llm_base_url,
        llm_model=setup.llm_model or "",
        agent_port=setup.agent_port,
    )

    with open(config_path, "a") as f:
        # Template and adapter configuration
        f.write("\n# Agent Template\n")
        f.write(f"CIRIS_TEMPLATE={setup.template_id}\n")
        f.write("\n# Enabled Adapters\n")
        f.write(f"CIRIS_ADAPTER={','.join(setup.enabled_adapters)}\n")

        # Accord metrics consent
        if "ciris_accord_metrics" in setup.enabled_adapters:
            consent_timestamp = datetime.now(timezone.utc).isoformat()
            f.write("\n# Accord Metrics Consent (auto-set when adapter enabled)\n")
            f.write("CIRIS_ACCORD_METRICS_CONSENT=true\n")
            f.write(f"CIRIS_ACCORD_METRICS_CONSENT_TIMESTAMP={consent_timestamp}\n")
            logger.info(f"[SETUP] Accord metrics consent enabled: {consent_timestamp}")

        # Adapter-specific environment variables with proper env var naming
        if setup.adapter_config:
            f.write("\n# Adapter-Specific Configuration\n")
            # Mapping of generic config keys to adapter-specific env var names
            HA_ENV_MAPPING = {
                "access_token": "HOME_ASSISTANT_TOKEN",
                "refresh_token": "HOME_ASSISTANT_REFRESH_TOKEN",
                "base_url": "HOME_ASSISTANT_URL",
                "client_id": "HOME_ASSISTANT_CLIENT_ID",
            }
            for key, value in setup.adapter_config.items():
                # Use mapped env var name if available, otherwise use key as-is
                env_var_name = HA_ENV_MAPPING.get(key, key)
                f.write(f"{env_var_name}={value}\n")

        # User preferences (language & location)
        # Always write language preference (defaults to English if not set)
        f.write("\n# User Preferences (from setup wizard PREFERENCES step)\n")
        preferred_lang = setup.preferred_language or "en"
        f.write(f'CIRIS_PREFERRED_LANGUAGE="{preferred_lang}"\n')

        # Location settings - write individual fields for weather/navigation adapters
        if setup.location_city:
            f.write(f'CIRIS_USER_CITY="{setup.location_city}"\n')
        if setup.location_region:
            f.write(f'CIRIS_USER_REGION="{setup.location_region}"\n')
        if setup.location_country:
            f.write(f'CIRIS_USER_COUNTRY="{setup.location_country}"\n')
            # Also write combined display name for backwards compatibility
            location_parts = [setup.location_city, setup.location_region, setup.location_country]
            location_display = ", ".join(p for p in location_parts if p)
            f.write(f'CIRIS_USER_LOCATION="{location_display}"\n')
        # Store coordinates in ISO 6709 decimal degrees format
        if setup.location_latitude is not None:
            f.write(f'CIRIS_USER_LATITUDE="{setup.location_latitude}"\n')
        if setup.location_longitude is not None:
            f.write(f'CIRIS_USER_LONGITUDE="{setup.location_longitude}"\n')
        if setup.timezone:
            f.write(f'CIRIS_USER_TIMEZONE="{setup.timezone}"\n')
        # Location sharing consent for telemetry
        if setup.share_location_in_traces:
            consent_timestamp = datetime.now(timezone.utc).isoformat()
            f.write("\n# Location Data Sharing Consent\n")
            f.write("CIRIS_SHARE_LOCATION_IN_TRACES=true\n")
            f.write(f"CIRIS_LOCATION_CONSENT_TIMESTAMP={consent_timestamp}\n")
            logger.info(f"[SETUP] Location sharing consent enabled: {consent_timestamp}")

        # Write optional configuration sections
        _write_backup_llm_config(f, setup)
        _write_node_connection_config(f, setup)
        _write_licensed_package_config(f, setup)
        _write_verify_config(f, setup)

    return config_path


def _log_setup_debug_info(setup: SetupCompleteRequest) -> bool:
    """Log comprehensive debug information for OAuth identity linking.

    Args:
        setup: Setup configuration request

    Returns:
        Whether OAuth linking will happen
    """
    logger.info("CIRIS_SETUP_DEBUG " + "=" * 60)
    logger.info("CIRIS_SETUP_DEBUG complete_setup() endpoint called")
    logger.info("CIRIS_SETUP_DEBUG " + "=" * 60)

    # Log ALL OAuth-related fields received from frontend
    logger.info("CIRIS_SETUP_DEBUG OAuth fields received from frontend:")
    logger.info(f"CIRIS_SETUP_DEBUG   oauth_provider = {repr(setup.oauth_provider)}")
    logger.info(f"CIRIS_SETUP_DEBUG   oauth_external_id = {repr(setup.oauth_external_id)}")
    logger.info(f"CIRIS_SETUP_DEBUG   oauth_email = {repr(setup.oauth_email)}")

    # Check truthiness explicitly
    logger.debug("CIRIS_SETUP_DEBUG Truthiness checks:")
    logger.debug(f"CIRIS_SETUP_DEBUG   bool(oauth_provider) = {bool(setup.oauth_provider)}")
    logger.debug(f"CIRIS_SETUP_DEBUG   bool(oauth_external_id) = {bool(setup.oauth_external_id)}")
    logger.debug(f"CIRIS_SETUP_DEBUG   oauth_external_id is None = {setup.oauth_external_id is None}")
    logger.debug(f"CIRIS_SETUP_DEBUG   oauth_external_id == '' = {setup.oauth_external_id == ''}")

    # The critical check that determines OAuth linking
    will_link_oauth = bool(setup.oauth_provider) and bool(setup.oauth_external_id)
    logger.debug(
        f"CIRIS_SETUP_DEBUG CRITICAL: Will OAuth linking happen? = {will_link_oauth}"
    )  # NOSONAR - boolean status only
    if not will_link_oauth:
        if not setup.oauth_provider:
            logger.debug("CIRIS_SETUP_DEBUG   Reason: oauth_provider is falsy")
        if not setup.oauth_external_id:
            logger.debug("CIRIS_SETUP_DEBUG   Reason: oauth_external_id is falsy")

    # Log other setup fields
    logger.debug("CIRIS_SETUP_DEBUG Other setup fields:")
    logger.debug(f"CIRIS_SETUP_DEBUG   admin_username = {setup.admin_username}")
    logger.debug(
        f"CIRIS_SETUP_DEBUG   admin_password set = {bool(setup.admin_password)}"
    )  # NOSONAR - boolean only, not password
    logger.debug(
        f"CIRIS_SETUP_DEBUG   system_admin_password set = {bool(setup.system_admin_password)}"
    )  # NOSONAR - boolean only
    logger.debug(f"CIRIS_SETUP_DEBUG   llm_provider = {setup.llm_provider}")
    logger.debug(f"CIRIS_SETUP_DEBUG   template_id = {setup.template_id}")

    # Node flow / signing key fields (self-custody - FSD-002)
    logger.info("CIRIS_SETUP_DEBUG Node flow fields:")
    logger.info(f"CIRIS_SETUP_DEBUG   node_url = {repr(setup.node_url)}")
    logger.info(f"CIRIS_SETUP_DEBUG   signing_key_id = {repr(setup.signing_key_id)}")
    # NOTE: signing_key_provisioned and provisioned_signing_key_b64 are DEPRECATED
    # Under self-custody (FSD-002), agent generates its own key - Portal never sends private keys

    return will_link_oauth


async def _schedule_runtime_resume(runtime: Any) -> None:
    """Schedule runtime resume in background after setup completion.

    Args:
        runtime: The application runtime object
    """
    # Set resume flag AND timestamp BEFORE scheduling task to prevent SmartStartup from killing us
    # This flag blocks local-shutdown requests during the resume sequence
    # The timestamp enables timeout detection for stuck resume scenarios
    runtime._resume_in_progress = True
    runtime._resume_started_at = time.time()
    logger.info(f"[Setup] Set _resume_in_progress=True, _resume_started_at={runtime._resume_started_at:.3f}")

    async def _resume_runtime() -> None:
        await asyncio.sleep(0.5)  # Brief delay to ensure response is sent
        try:
            await runtime.resume_from_first_run()
            logger.info("Successfully resumed from first-run mode - agent processor running")
        except Exception as e:
            logger.error(f"Failed to resume from first-run: {e}", exc_info=True)
            # Clear the flag and timestamp so shutdown can proceed
            runtime._resume_in_progress = False
            runtime._resume_started_at = None
            logger.info("[Setup] Cleared _resume_in_progress due to error")
            # If resume fails, fall back to restart
            runtime.request_shutdown("Resume failed - restarting to apply configuration")

    # Store task in module-level set to prevent garbage collection
    resume_task = asyncio.create_task(_resume_runtime())
    _background_tasks.add(resume_task)
    resume_task.add_done_callback(_background_tasks.discard)
    logger.info(f"Scheduled background resume task: {resume_task.get_name()}")


# =============================================================================
# ENDPOINT
# =============================================================================


@router.post("/complete", responses=RESPONSES_400_403_500, dependencies=[SetupOnlyDep])
async def complete_setup(setup: SetupCompleteRequest, request: Request) -> SuccessResponse[Dict[str, str]]:
    """Complete initial setup.

    Saves configuration and creates initial admin user.
    Only accessible during first-run (SetupOnlyDep enforces this).
    After setup, authentication is required for reconfiguration.
    """
    # Log debug info and determine if OAuth linking will happen
    _log_setup_debug_info(setup)

    # Determine if this is an OAuth user (password is optional for OAuth users)
    is_oauth_user = bool(setup.oauth_provider)
    logger.debug(
        f"CIRIS_SETUP_DEBUG is_oauth_user (for password validation) = {is_oauth_user}"
    )  # NOSONAR - boolean only

    # Validate passwords and potentially generate for OAuth users
    setup.admin_password = _validate_setup_passwords(setup, is_oauth_user)

    try:
        # Save configuration and reload environment variables
        config_path = _save_and_reload_config(setup)

        # SELF-CUSTODY KEY (FSD-002): The agent's signing key was generated by
        # CIRISVerify at startup (TPM-protected). The PUBLIC key was registered
        # with Portal via /api/device/register-key. The PRIVATE key never leaves
        # the agent. We now audit that key's initialization.
        from ciris_engine.logic.audit.signing_protocol import get_unified_signing_key

        signing_key = get_unified_signing_key()
        signing_key_id = signing_key.key_id
        logger.info(f"[Setup Complete] Using self-custody signing key (key_id={signing_key_id})")

        # Audit the key initialization - ensures audit_log table exists
        # This is critical: attestation verifies audit_log exists, so we must
        # have at least one entry before attestation runs post-setup
        audit_service = getattr(request.app.state, "audit_service", None)
        if audit_service:
            from ciris_engine.schemas.services.graph.audit import AuditEventData

            audit_event = AuditEventData(
                event_type="signing_key_initialized",
                details={
                    "key_id": signing_key_id,
                    "source": "self_custody",  # Agent controls its own key
                    "algorithm": signing_key.algorithm.value,
                    "portal_key_id": setup.signing_key_id,  # Portal's reference ID
                    "node_url": setup.node_url,
                    "note": "Self-custody key (FSD-002) - private key never leaves agent",
                },
                severity="info",
                source="setup_complete",
            )
            audit_task = asyncio.create_task(audit_service.log_event("signing_key_initialized", audit_event))
            await audit_task
            logger.info("[Setup Complete] Audit entry created for self-custody key initialization")

        # Get runtime and database path from the running application
        runtime = getattr(request.app.state, "runtime", None)
        if not runtime:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Runtime not available - cannot complete setup",
            )

        # Get audit database path using same resolution as AuthenticationService
        # This handles both SQLite and PostgreSQL (adds _auth suffix to database name)
        auth_db_path = get_audit_db_full_path(runtime.essential_config)
        logger.info(f"Using runtime audit database: {auth_db_path}")

        # Create users immediately (don't wait for restart)
        print(f"[SETUP_COMPLETE] Calling _create_setup_users(username={setup.admin_username}, db={auth_db_path})")
        try:
            await _create_setup_users(setup, auth_db_path)
            print("[SETUP_COMPLETE] _create_setup_users completed successfully")
        except Exception as user_err:
            print(f"[SETUP_COMPLETE] _create_setup_users FAILED: {user_err}")
            import traceback

            traceback.print_exc()
            raise

        # Reload user cache in APIAuthService to pick up newly created users
        auth_service = getattr(request.app.state, "auth_service", None)
        if auth_service:
            logger.info("Reloading user cache after setup user creation...")
            await auth_service.reload_users_from_db()
            logger.info("✅ User cache reloaded - new users now visible to authentication")

        # Build next steps message
        next_steps = "Configuration completed. The agent is now starting. You can log in immediately."
        if setup.system_admin_password:
            next_steps += " Both user passwords have been configured."

        # Resume initialization from first-run mode to start agent processor
        logger.info("Setup complete - resuming initialization to start agent processor")
        await _schedule_runtime_resume(runtime)

        return SuccessResponse(
            data={
                "status": "completed",
                "message": "Setup completed successfully. Starting agent processor...",
                "config_path": str(config_path),
                "username": setup.admin_username,
                "next_steps": next_steps,
            }
        )

    except Exception as e:
        logger.error(f"Setup completion failed: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
