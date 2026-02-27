"""
Setup wizard endpoints for CIRIS first-run and reconfiguration.

Provides GUI-based setup wizard accessible at /v1/setup/*.
Replaces the CLI wizard for pip-installed CIRIS agents.
"""

import asyncio
import json
import logging
import os
import secrets
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from ciris_engine.config.model_capabilities import get_model_capabilities
from ciris_engine.logic.config.db_paths import get_audit_db_full_path
from ciris_engine.logic.setup.first_run import get_default_config_path, is_first_run
from ciris_engine.logic.setup.wizard import create_env_file
from ciris_engine.schemas.api.responses import SuccessResponse

from ._common import (
    RESPONSES_400_403_500,
    RESPONSES_401_500,
    RESPONSES_403,
    RESPONSES_404_500,
    RESPONSES_500,
    AuthAdminDep,
)

# Import device auth from the new device_auth.py module
from .setup.device_auth import (
    _activate_key_inline,
    _clear_device_auth_session,
    _get_device_auth_session_path,
    _load_device_auth_session,
    _save_device_auth_session,
    _submit_attestation_inline,
)

# Import helpers from the new helpers.py module
from .setup.helpers import (
    _create_adapter_from_manifest,
    _get_agent_templates,
    _get_available_adapters,
    _is_setup_allowed_without_auth,
    _log_oauth_linking_skip,
    _should_skip_manifest,
    _validate_setup_passwords,
)

# Import LLM validation from the new llm_validation.py module
from .setup.llm_validation import (
    _annotate_models_with_capabilities,
    _build_fallback_response,
    _classify_llm_connection_error,
    _detect_ollama,
    _fetch_live_models,
    _get_llm_providers,
    _get_provider_base_url,
    _get_static_fallback_models,
    _list_models_for_provider,
    _sort_models,
    _validate_api_key_for_provider,
    _validate_llm_connection,
)

# Import device auth models from models.py
# Import models from the new models.py module
from .setup.models import (
    AdapterConfig,
    AgentTemplate,
    AppAttestVerifyRequest,
    ChangePasswordRequest,
    ConnectNodeRequest,
    ConnectNodeResponse,
    ConnectNodeStatusResponse,
    CreateUserRequest,
    DownloadPackageRequest,
    DownloadPackageResponse,
    ListModelsResponse,
    LiveModelInfo,
    LLMProvider,
    LLMValidationRequest,
    LLMValidationResponse,
    PlayIntegrityVerifyRequest,
    SetupCompleteRequest,
    SetupConfigResponse,
    SetupStatusResponse,
    VerifyStatusResponse,
)

router = APIRouter(prefix="/setup", tags=["setup"])

# Include attestation router (endpoints moved to setup/attestation.py)
from .setup import attestation

router.include_router(attestation.router, tags=["attestation"])


# ============================================================================
# Setup-Only Route Protection
# ============================================================================


def require_setup_mode() -> None:
    """Dependency that ensures setup routes are only accessible during first-run setup.

    After setup is complete, these routes return 403 Forbidden.
    Use /v1/auth/attestation for cached attestation after setup.

    Raises:
        HTTPException: 403 if setup is already complete
    """
    if not is_first_run():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Setup routes are only available during first-run setup. "
            "Use /v1/auth/attestation for attestation status after setup.",
        )


# Type alias for the dependency
SetupOnlyDep = Depends(require_setup_mode)
logger = logging.getLogger(__name__)

# Module-level CIRISVerify singleton so App Attest endpoints and verify-status
# share the same FFI handle. The device attestation cache lives in the handle,
# so all calls must go through the same instance.
_shared_verifier: Any = None
_shared_verifier_lock: Any = None
_rust_log_cb: Any = None  # Prevent GC of ctypes callback

# Circuit breaker for Play Integrity FFI - prevents repeated crashes
# If the FFI crashes (SIGSEGV), this flag prevents further calls
_play_integrity_ffi_disabled: bool = False
_play_integrity_ffi_error: Optional[str] = None


def _get_shared_verifier() -> Any:
    """Get the global CIRISVerify singleton instance.

    Uses the global singleton from verifier_singleton module to ensure
    only ONE CIRISVerify instance exists across the entire application.
    """
    try:
        from ciris_engine.logic.services.infrastructure.authentication.verifier_singleton import get_verifier

        return get_verifier()
    except ImportError:
        logger.debug("[setup] CIRISVerify not available (import failed)")
        return None
    except Exception as e:
        logger.warning(f"[setup] Failed to get CIRISVerify singleton: {e}")
        return None


def _fetch_manifest_files_from_registry(version: str) -> Optional[set[str]]:
    """Fetch manifest file list from registry.

    Args:
        version: Agent version (e.g., "2.0.0")

    Returns:
        Set of file paths from manifest, or None if fetch failed
    """
    import json
    import ssl
    import urllib.request

    try:
        url = f"https://api.registry.ciris-services-1.ai/v1/builds/{version}"
        logger.info(f"[verify-status] Fetching manifest from registry for version {version}")
        # On iOS, Python's default SSL context can't find CA certificates.
        # Use certifi bundle if available, else fall back to unverified context
        # (manifest is public, integrity is verified by hash comparison not TLS)
        ssl_ctx = None
        try:
            import certifi

            ssl_ctx = ssl.create_default_context(cafile=certifi.where())
        except ImportError:
            ssl_ctx = ssl.create_default_context()
            ssl_ctx.check_hostname = False
            ssl_ctx.verify_mode = ssl.CERT_NONE
        with urllib.request.urlopen(url, timeout=5, context=ssl_ctx) as response:
            data = json.loads(response.read().decode())
            manifest_json = data.get("file_manifest_json", {})
            if isinstance(manifest_json, dict):
                files = manifest_json.get("files", {})
                logger.info(f"[verify-status] Registry manifest has {len(files)} files")
                return set(files.keys())
    except Exception as e:
        logger.warning(f"[verify-status] Failed to fetch manifest from registry: {e}")
    return None


def _find_unexpected_python_files(agent_root: str, manifest_files: set[str]) -> tuple[List[str], List[str]]:
    """Find Python files that exist on disk but aren't in the manifest.

    Args:
        agent_root: Root directory of the agent
        manifest_files: Set of relative file paths from manifest

    Returns:
        Tuple of (unexpected files, expected_excluded files) - both max 10 items
        expected_excluded are known files like ciris_verify/ wrapper that aren't in manifest
    """
    unexpected: list[str] = []
    expected_excluded: list[str] = []
    # Files to completely ignore (not count at all)
    ignore_patterns = {".env", "__pycache__", ".pyc", "test_", "_test.py", "conftest.py", "logs/", ".db"}
    # Files that are expected to be missing from manifest (report but don't fail)
    # ciris_verify/: Python bindings wrapper, not in server manifest
    # ciris_ios/: iOS platform-specific files, not in server manifest
    # ciris_android/: Android platform-specific files, not in server manifest
    expected_missing_patterns = {"ciris_verify/", "ciris_ios/", "ciris_android/"}

    try:
        import os

        for root, dirs, files in os.walk(agent_root):
            # Skip __pycache__ and hidden directories
            dirs[:] = [d for d in dirs if d != "__pycache__" and not d.startswith(".") and d != "logs"]

            for f in files:
                if not f.endswith(".py"):
                    continue

                # Get relative path
                full_path = os.path.join(root, f)
                rel_path = os.path.relpath(full_path, agent_root)

                # Skip completely ignored files
                if any(p in rel_path for p in ignore_patterns):
                    continue

                # Check if in manifest
                if rel_path not in manifest_files:
                    # Check if it's an expected exclusion
                    if any(p in rel_path for p in expected_missing_patterns):
                        if len(expected_excluded) < 10:
                            expected_excluded.append(rel_path)
                    else:
                        unexpected.append(rel_path)
                        if len(unexpected) >= 10:
                            return unexpected, expected_excluded
    except Exception as e:
        logger.warning(f"Error scanning for unexpected files: {e}")

    return unexpected, expected_excluded


def _find_missing_manifest_files(agent_root: str, manifest_files: set[str], max_files: int = 50) -> List[str]:
    """Find files that are in the manifest but not on disk.

    Args:
        agent_root: Root directory of the agent
        manifest_files: Set of relative file paths from manifest
        max_files: Maximum number of files to return

    Returns:
        List of missing file paths (max max_files items)
    """
    missing = []
    try:
        for rel_path in manifest_files:
            full_path = os.path.join(agent_root, rel_path)
            if not os.path.exists(full_path):
                missing.append(rel_path)
                if len(missing) >= max_files:
                    break
    except Exception as e:
        logger.warning(f"Error checking for missing files: {e}")
    return missing


# Device auth session helpers are imported from setup/device_auth.py
# Models are imported from setup/models.py

# ============================================================================
# Helper Functions
# ============================================================================
# NOTE: Most helper functions have been extracted to dedicated modules:
# - _is_setup_allowed_without_auth -> helpers.py
# - LLM validation functions -> llm_validation.py
# - Device auth session functions -> device_auth.py
# - Attestation helpers -> device_auth.py


# =============================================================================
# SETUP USER HELPER FUNCTIONS (extracted for cognitive complexity reduction)
# =============================================================================


async def _link_oauth_identity_to_wa(auth_service: Any, setup: "SetupCompleteRequest", wa_cert: Any) -> Any:
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


# _log_oauth_linking_skip moved to helpers.py


async def _update_system_admin_password(auth_service: Any, setup: "SetupCompleteRequest", exclude_wa_id: str) -> None:
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


async def _check_existing_oauth_wa(auth_service: Any, setup: "SetupCompleteRequest") -> tuple[Optional[Any], bool]:
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


async def _create_new_wa(auth_service: Any, setup: "SetupCompleteRequest") -> Any:
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


async def _set_password_for_wa(auth_service: Any, setup: "SetupCompleteRequest", wa_cert: Any) -> None:
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


def _save_pending_users(setup: SetupCompleteRequest, config_dir: Path) -> None:
    """Save pending user creation info for initialization service.

    Args:
        setup: Setup configuration with user info
        config_dir: Directory where .env file is saved
    """
    pending_users_file = config_dir / ".ciris_pending_users.json"

    # Prepare user creation data
    users_data = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "new_user": {
            "username": setup.admin_username,
            "password": setup.admin_password,  # Will be hashed by auth service
            "role": "ADMIN",  # New user gets admin role
        },
    }

    # Add system admin password update if provided
    if setup.system_admin_password:
        users_data["system_admin"] = {
            "username": "admin",  # Default system admin username
            "password": setup.system_admin_password,  # Will be hashed by auth service
        }

    # Save to JSON file
    with open(pending_users_file, "w") as f:
        json.dump(users_data, f, indent=2)


# _validate_setup_passwords moved to helpers.py


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
            from datetime import datetime, timezone

            consent_timestamp = datetime.now(timezone.utc).isoformat()
            f.write("\n# Accord Metrics Consent (auto-set when adapter enabled)\n")
            f.write("CIRIS_ACCORD_METRICS_CONSENT=true\n")
            f.write(f"CIRIS_ACCORD_METRICS_CONSENT_TIMESTAMP={consent_timestamp}\n")
            logger.info(f"[SETUP] Accord metrics consent enabled: {consent_timestamp}")

        # Adapter-specific environment variables
        if setup.adapter_config:
            f.write("\n# Adapter-Specific Configuration\n")
            for key, value in setup.adapter_config.items():
                f.write(f"{key}={value}\n")

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

    # Node flow / signing key fields
    logger.info(f"CIRIS_SETUP_DEBUG Node flow fields:")
    logger.info(f"CIRIS_SETUP_DEBUG   node_url = {repr(setup.node_url)}")
    logger.info(f"CIRIS_SETUP_DEBUG   signing_key_id = {repr(setup.signing_key_id)}")
    logger.info(f"CIRIS_SETUP_DEBUG   signing_key_provisioned = {setup.signing_key_provisioned}")
    logger.info(f"CIRIS_SETUP_DEBUG   provisioned_signing_key_b64 set = {bool(setup.provisioned_signing_key_b64)}")

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

    # Store task to prevent garbage collection and log task creation
    resume_task = asyncio.create_task(_resume_runtime())
    logger.info(f"Scheduled background resume task: {resume_task.get_name()}")


# ============================================================================
# Endpoints
# ============================================================================


@router.get("/status")
async def get_setup_status() -> SuccessResponse[SetupStatusResponse]:
    """Check setup status.

    Returns information about whether setup is required.
    This endpoint is always accessible without authentication.
    """
    first_run = is_first_run()
    config_path = get_default_config_path()
    config_exists = config_path.exists()

    status = SetupStatusResponse(
        is_first_run=first_run,
        config_exists=config_exists,
        config_path=str(config_path) if config_exists else None,
        setup_required=first_run,
    )

    return SuccessResponse(data=status)


# ============================================================================
# Attestation Endpoints (REMOVED - now in setup/attestation.py)
# All /attestation-status, /app-attest/*, /play-integrity/*, /verify-status
# endpoints are now served by attestation.router included above.
# ============================================================================


@router.get("/providers", dependencies=[SetupOnlyDep])
async def list_providers() -> SuccessResponse[List[LLMProvider]]:
    """List available LLM providers.

    Returns configuration templates for supported LLM providers.
    This endpoint is always accessible without authentication.
    """
    providers = _get_llm_providers()
    return SuccessResponse(data=providers)


@router.get("/templates", dependencies=[SetupOnlyDep])
async def list_templates() -> SuccessResponse[List[AgentTemplate]]:
    """List available agent templates.

    Returns pre-configured agent identity templates.
    This endpoint is always accessible without authentication.
    """
    templates = _get_agent_templates()
    return SuccessResponse(data=templates)


@router.get("/adapters", dependencies=[SetupOnlyDep])
async def list_adapters() -> SuccessResponse[List[AdapterConfig]]:
    """List available adapters with platform requirements.

    Returns ALL adapters with their requirements metadata.
    KMP clients filter locally based on platform capabilities (iOS, Android, desktop).
    This endpoint is always accessible without authentication.
    """
    adapters = _get_available_adapters()
    return SuccessResponse(data=adapters)


@router.get(
    "/adapters/available",
    responses={500: {"description": "Adapter discovery failed"}},
)
async def list_available_adapters_for_setup() -> SuccessResponse[Dict[str, Any]]:
    """List discovered adapters with eligibility status (no auth required for setup).

    Returns both eligible (ready to use) and ineligible (missing requirements)
    adapters, including installation hints for ineligible adapters.
    This endpoint is accessible without authentication during first-run setup.
    """
    from ciris_engine.logic.services.tool.discovery_service import AdapterDiscoveryService

    try:
        discovery = AdapterDiscoveryService()
        report = await discovery.get_discovery_report()
        return SuccessResponse(data=report.model_dump())
    except Exception as e:
        logger.error(f"Error getting adapter availability for setup: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/models", responses=RESPONSES_500, dependencies=[SetupOnlyDep])
async def get_model_capabilities_endpoint() -> SuccessResponse[Dict[str, Any]]:
    """Get CIRIS-compatible LLM model capabilities.

    Returns the on-device model capabilities database for BYOK model selection.
    Used by the wizard's Advanced settings to show compatible models per provider.
    This endpoint is always accessible without authentication.

    Returns model info including:
    - CIRIS compatibility requirements (128K+ context, tool use, vision)
    - Per-provider model listings with capability flags
    - Tiers (default, fast, fallback, premium)
    - Recommendations and rejection reasons
    """
    from ciris_engine.config import get_model_capabilities

    try:
        config = get_model_capabilities()

        # Convert to dict for JSON response
        return SuccessResponse(
            data={
                "version": config.version,
                "last_updated": config.last_updated.isoformat(),
                "ciris_requirements": config.ciris_requirements.model_dump(),
                "providers": {
                    provider_id: {
                        "display_name": provider.display_name,
                        "api_base": provider.api_base,
                        "models": {model_id: model.model_dump() for model_id, model in provider.models.items()},
                    }
                    for provider_id, provider in config.providers.items()
                },
                "tiers": {tier_id: tier.model_dump() for tier_id, tier in config.tiers.items()},
                "rejected_models": {model_id: model.model_dump() for model_id, model in config.rejected_models.items()},
            }
        )
    except Exception as e:
        logger.error(f"Failed to load model capabilities: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to load model capabilities: {str(e)}",
        )


@router.get("/models/{provider_id}", responses=RESPONSES_404_500, dependencies=[SetupOnlyDep])
async def get_provider_models(provider_id: str) -> SuccessResponse[Dict[str, Any]]:
    """Get CIRIS-compatible models for a specific provider.

    Returns models for the given provider with compatibility information.
    Used by the wizard to populate model dropdown after provider selection.
    """
    from ciris_engine.config import get_model_capabilities

    try:
        config = get_model_capabilities()

        if provider_id not in config.providers:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Provider '{provider_id}' not found")

        provider = config.providers[provider_id]
        compatible_models = []
        incompatible_models = []

        for model_id, model in provider.models.items():
            model_data = {
                "id": model_id,
                **model.model_dump(),
            }
            if model.ciris_compatible:
                compatible_models.append(model_data)
            else:
                incompatible_models.append(model_data)

        # Sort: recommended first, then by display name
        compatible_models.sort(key=lambda m: (not m.get("ciris_recommended", False), m["display_name"]))

        return SuccessResponse(
            data={
                "provider_id": provider_id,
                "display_name": provider.display_name,
                "api_base": provider.api_base,
                "compatible_models": compatible_models,
                "incompatible_models": incompatible_models,
                "ciris_requirements": config.ciris_requirements.model_dump(),
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get provider models: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get provider models: {str(e)}",
        )


@router.post("/validate-llm", dependencies=[SetupOnlyDep])
async def validate_llm(config: LLMValidationRequest) -> SuccessResponse[LLMValidationResponse]:
    """Validate LLM configuration.

    Tests the provided LLM configuration by attempting a connection.
    This endpoint is always accessible without authentication during first-run.
    """
    validation_result = await _validate_llm_connection(config)
    return SuccessResponse(data=validation_result)


@router.post("/list-models", dependencies=[SetupOnlyDep])
async def list_models(config: LLMValidationRequest) -> SuccessResponse[ListModelsResponse]:
    """List available models from a provider's live API.

    Queries the provider's models API using the provided credentials,
    then cross-references with the on-device MODEL_CAPABILITIES.json
    for CIRIS compatibility annotations.

    Falls back to static capabilities data if the live query fails.
    This endpoint is always accessible without authentication during first-run.
    """
    result = await _list_models_for_provider(config)
    return SuccessResponse(data=result)


# ============================================================================
# Connect to Node (Device Auth Flow)
# ============================================================================
# Models are imported from setup/models.py
# Helper functions are imported from setup/device_auth.py


@router.post("/connect-node", responses=RESPONSES_500, dependencies=[SetupOnlyDep])
async def connect_node(req: ConnectNodeRequest) -> SuccessResponse[ConnectNodeResponse]:
    """Initiate device auth via CIRISPortal.

    The user provides a Portal URL directly. This endpoint:
    1. Checks for existing non-expired device auth session (reuses if found)
    2. Normalizes the Portal URL (adds https:// if needed)
    3. Calls Portal's POST /api/device/authorize with agent info
    4. Persists the session so it survives app restarts
    5. Returns verification URL for user to open in browser

    CRITICAL: Device codes are persisted to survive app restarts. If user
    pays for a license in browser and app restarts, we must continue polling
    with the SAME device code, not request a new one.

    This endpoint is accessible without authentication during first-run.
    """
    import httpx

    portal_url = req.node_url.strip().rstrip("/")
    # Normalize URL — add https:// if no scheme provided
    if not portal_url.startswith("http://") and not portal_url.startswith("https://"):
        portal_url = f"https://{portal_url}"

    # Check for existing non-expired session — reuse it if found
    existing_session = _load_device_auth_session()
    if existing_session and existing_session.get("portal_url") == portal_url:
        logger.info("Reusing existing device auth session (device_code=%s...)", existing_session["device_code"][:16])
        remaining = int(existing_session["expires_at"] - time.time())
        return SuccessResponse(
            data=ConnectNodeResponse(
                verification_uri_complete=existing_session["verification_uri_complete"],
                device_code=existing_session["device_code"],
                user_code=existing_session.get("user_code", ""),
                portal_url=portal_url,
                expires_in=max(remaining, 0),
                interval=existing_session.get("interval", 5),
            )
        )

    device_auth_endpoint = "/api/device/authorize"

    # For first-run setup, we send empty agent_info since we're provisioning a new agent.
    # Existing agents reconnecting would include their hash and public key here.
    agent_info: Dict[str, Any] = {}

    # Call Portal's device authorize endpoint directly
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            auth_resp = await client.post(
                f"{portal_url}{device_auth_endpoint}",
                json={
                    "portal_url": portal_url,
                    "agent_info": agent_info,
                },
            )
            auth_resp.raise_for_status()
            auth_data = auth_resp.json()
    except httpx.HTTPError as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to initiate device auth with Portal at {portal_url}: {e}",
        )

    # If Portal returned a challenge_nonce, submit attestation inline
    # before returning to the client. This keeps KMP simple.
    challenge_nonce = auth_data.get("challenge_nonce")
    if challenge_nonce:
        await _submit_attestation_inline(
            challenge_nonce=challenge_nonce,
            device_code=auth_data["device_code"],
            portal_url=portal_url,
        )

    # Persist the session so it survives app restarts
    device_code = auth_data["device_code"]
    expires_in = auth_data.get("expires_in", 900)
    interval = auth_data.get("interval", 5)
    verification_uri = auth_data["verification_uri_complete"]
    user_code = auth_data.get("user_code", "")

    _save_device_auth_session(
        device_code=device_code,
        portal_url=portal_url,
        verification_uri_complete=verification_uri,
        user_code=user_code,
        expires_in=expires_in,
        interval=interval,
    )

    return SuccessResponse(
        data=ConnectNodeResponse(
            verification_uri_complete=verification_uri,
            device_code=device_code,
            user_code=user_code,
            portal_url=portal_url,
            expires_in=expires_in,
            interval=interval,
        )
    )


@router.get("/connect-node/status", responses=RESPONSES_500, dependencies=[SetupOnlyDep])
async def connect_node_status(device_code: str, portal_url: str) -> SuccessResponse[ConnectNodeStatusResponse]:
    """Poll device auth status.

    Called periodically by the setup wizard to check if the user has
    completed the device auth flow in the Portal browser UI.

    Args:
        device_code: Opaque device code from /connect-node
        portal_url: Portal URL to poll (from node manifest)

    Returns:
        Status: pending (keep polling), complete (key ready), or error.
    """
    import httpx

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            token_resp = await client.post(
                f"{portal_url.rstrip('/')}/api/device/token",
                json={"device_code": device_code},
            )

            # 428 = authorization_pending (RFC 8628)
            if token_resp.status_code == 428:
                return SuccessResponse(data=ConnectNodeStatusResponse(status="pending"))

            if token_resp.status_code == 403:
                # Authorization denied — clear session so user can retry
                _clear_device_auth_session()
                return SuccessResponse(data=ConnectNodeStatusResponse(status="error"))

            if token_resp.status_code != 200:
                body = (
                    token_resp.json()
                    if token_resp.headers.get("content-type", "").startswith("application/json")
                    else {}
                )
                error_desc = body.get("error_description", body.get("error", f"HTTP {token_resp.status_code}"))
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=f"Portal token endpoint error: {error_desc}",
                )

            data = token_resp.json()
    except httpx.HTTPError as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to poll Portal token endpoint: {e}",
        )

    # Success — extract provisioned data
    signing_key = data.get("signing_key", {})
    agent_record = data.get("agent_record", {})
    licensed_package = data.get("licensed_package") or {}

    # Log what Portal returned for debugging
    logger.info("[connect-node/status] Portal token response keys: %s", list(data.keys()))
    logger.info("[connect-node/status] signing_key keys: %s", list(signing_key.keys()) if signing_key else "None")
    logger.info("[connect-node/status] signing_key.key_id = %s", signing_key.get("key_id"))
    logger.info("[connect-node/status] agent_record keys: %s", list(agent_record.keys()) if agent_record else "None")

    # Extract the provisioned signing key — it will be saved during /complete setup.
    # We don't eagerly save here to avoid filesystem issues (e.g., iOS read-only bundles).
    private_key_b64 = signing_key.get("ed25519_private_key", "")

    # PHASE 2: Key Activation - import key and submit second attestation
    # This binds the agent identity to this specific key instance.
    # Key reuse across agents is FORBIDDEN.
    if private_key_b64:
        await _activate_key_inline(private_key_b64, device_code, portal_url)

    # Clear device auth session — flow completed successfully
    _clear_device_auth_session()
    logger.info("Device auth flow completed successfully")

    return SuccessResponse(
        data=ConnectNodeStatusResponse(
            status="complete",
            template=agent_record.get("identity_template"),
            adapters=agent_record.get("approved_adapters"),
            org_id=signing_key.get("org_id"),
            signing_key_b64=private_key_b64,
            key_id=signing_key.get("key_id"),
            stewardship_tier=agent_record.get("stewardship_tier"),
            package_download_url=licensed_package.get("download_url"),
            package_template_id=licensed_package.get("template_id"),
        )
    )


@router.post("/reset-device-auth", responses=RESPONSES_500, dependencies=[SetupOnlyDep])
async def reset_device_auth() -> SuccessResponse[Dict[str, Any]]:
    """Reset device auth session state.

    Called when user backs out of the node auth flow (e.g., after timeout or cancel).
    This clears any stale device auth session to allow a fresh retry.

    No authentication required since this only affects local session state.
    """
    logger.info("Resetting device auth session (user backed out of node auth flow)")
    _clear_device_auth_session()

    return SuccessResponse(
        data={
            "status": "reset",
            "message": "Device auth session cleared",
        }
    )


# ============================================================================
# CIRISVerify Attestation (inline helper for connect_node)
# - _submit_attestation_inline and _activate_key_inline are now in device_auth.py
# ============================================================================


# Attestation helpers (_submit_attestation_inline, _activate_key_inline)
# are now imported from setup/device_auth.py


# ============================================================================
# Licensed Package Download + Configure
# ============================================================================
# DownloadPackageRequest and DownloadPackageResponse models are now in setup/models.py


@router.post("/download-package", responses=RESPONSES_500, dependencies=[SetupOnlyDep])
async def download_package(req: DownloadPackageRequest) -> SuccessResponse[DownloadPackageResponse]:
    """Download and install a licensed module package from Portal.

    1. Downloads the zip from the Portal package endpoint
    2. Verifies checksum from response headers
    3. Unzips to the agent's licensed_modules/ directory
    4. Returns paths for template, modules, and config

    This endpoint is accessible without authentication during first-run.
    """
    import asyncio
    import hashlib
    import shutil
    import tempfile
    import zipfile
    from urllib.parse import urlparse

    import httpx

    # Determine install directory
    data_dir = Path(os.environ.get("CIRIS_DATA_DIR", "."))
    licensed_modules_dir = data_dir / "licensed_modules"

    # Validate URL is from trusted Portal domains and paths only (security: prevent SSRF)
    ALLOWED_PORTAL_HOSTS = {
        "portal.ciris.ai",
        "portal.ciris-services-1.ai",
        "portal.ciris-services-2.ai",
        "localhost",
        "127.0.0.1",
    }
    ALLOWED_PATH_PREFIXES = ("/api/", "/v1/")  # Only allow API endpoints
    parsed_url = urlparse(req.package_download_url)
    if parsed_url.hostname not in ALLOWED_PORTAL_HOSTS:
        return SuccessResponse(
            data=DownloadPackageResponse(
                status="error",
                error=f"Invalid package URL: host '{parsed_url.hostname}' not in allowed Portal domains",
            )
        )
    if not any(parsed_url.path.startswith(prefix) for prefix in ALLOWED_PATH_PREFIXES):
        return SuccessResponse(
            data=DownloadPackageResponse(
                status="error",
                error="Invalid package URL: path must start with /api/ or /v1/",
            )
        )

    try:
        # Download the zip from Portal
        async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
            headers: Dict[str, str] = {}
            if req.portal_session_cookie:
                headers["Cookie"] = req.portal_session_cookie

            dl_resp = await client.get(req.package_download_url, headers=headers)
            dl_resp.raise_for_status()

        # Get checksum from response header
        expected_checksum = dl_resp.headers.get("x-package-checksum", "")
        package_id = dl_resp.headers.get("x-package-id", "unknown")
        package_version = dl_resp.headers.get("x-package-version", "0.0.0")

        # Verify checksum
        actual_checksum = hashlib.sha256(dl_resp.content).hexdigest()
        if expected_checksum and actual_checksum != expected_checksum:
            return SuccessResponse(
                data=DownloadPackageResponse(
                    status="error",
                    error=f"Checksum mismatch: expected {expected_checksum}, got {actual_checksum}",
                )
            )

        # Save zip to temp file (run sync I/O in thread to avoid blocking event loop)
        def _write_temp_file(content: bytes) -> str:
            with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
                tmp.write(content)
                return tmp.name

        tmp_path = await asyncio.to_thread(_write_temp_file, dl_resp.content)

        # Create install directory
        install_dir = licensed_modules_dir / package_id
        if install_dir.exists():
            # Remove old version
            shutil.rmtree(install_dir)
        install_dir.mkdir(parents=True, exist_ok=True)

        # Unzip
        with zipfile.ZipFile(tmp_path, "r") as zf:
            zf.extractall(install_dir)

        # Cleanup temp file
        os.unlink(tmp_path)

        logger.info(f"[Package Download] Installed {package_id} v{package_version} to {install_dir}")

        # Find key paths within the extracted package
        template_file = None
        modules_path = None
        config_path = None

        templates_dir = install_dir / "templates"
        if templates_dir.exists():
            yamls = list(templates_dir.glob("*.yaml"))
            if yamls:
                template_file = str(yamls[0])

        mods_dir = install_dir / "modules"
        if mods_dir.exists():
            modules_path = str(mods_dir)

        cfg_dir = install_dir / "config"
        if cfg_dir.exists():
            config_path = str(cfg_dir)

        return SuccessResponse(
            data=DownloadPackageResponse(
                status="success",
                package_path=str(install_dir),
                template_file=template_file,
                modules_path=modules_path,
                config_path=config_path,
                checksum=actual_checksum,
            )
        )

    except httpx.HTTPError as e:
        logger.error(f"[Package Download] HTTP error: {e}")
        return SuccessResponse(
            data=DownloadPackageResponse(
                status="error",
                error=f"Failed to download package: {e}",
            )
        )
    except zipfile.BadZipFile:
        logger.error("[Package Download] Invalid zip file received")
        return SuccessResponse(
            data=DownloadPackageResponse(
                status="error",
                error="Downloaded file is not a valid zip archive",
            )
        )
    except Exception as e:
        logger.error(f"[Package Download] Unexpected error: {e}")
        return SuccessResponse(
            data=DownloadPackageResponse(
                status="error",
                error=f"Package installation failed: {e}",
            )
        )


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

        # If a Registry-provisioned signing key was provided (Connect to Node flow),
        # save it now so the agent uses the Registry-issued key instead of self-generating.
        if setup.signing_key_provisioned and setup.provisioned_signing_key_b64:
            from ciris_engine.logic.audit.signing_protocol import UnifiedSigningKey

            provisioned_key = UnifiedSigningKey()
            provisioned_key.load_provisioned_key(setup.provisioned_signing_key_b64)
            provisioned_key_id = provisioned_key.key_id
            logger.info(f"[Setup Complete] Saved Registry-provisioned signing key (key_id={provisioned_key_id})")

            # Audit the key provisioning event - critical for Level 5 attestation
            audit_service = getattr(request.app.state, "audit_service", None)
            if audit_service:
                import asyncio

                from ciris_engine.schemas.services.graph.audit import AuditEventData

                audit_event = AuditEventData(
                    event_type="signing_key_provisioned",
                    details={
                        "key_id": provisioned_key_id,
                        "signing_key_id": setup.signing_key_id,
                        "source": "portal_registry",
                        "node_url": setup.node_url,
                    },
                    severity="info",
                    source="setup_complete",
                )
                asyncio.create_task(audit_service.log_event("signing_key_provisioned", audit_event))
                logger.info(f"[Setup Complete] Audit entry created for key provisioning")

            # Clear the key from the request to avoid logging it
            setup.provisioned_signing_key_b64 = None

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
        await _create_setup_users(setup, auth_db_path)

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


@router.get("/config", responses=RESPONSES_401_500)
async def get_current_config(request: Request) -> SuccessResponse[SetupConfigResponse]:
    """Get current configuration.

    Returns current setup configuration for editing.
    Requires authentication if setup is already completed.
    """
    # If not first-run, require authentication
    if not _is_setup_allowed_without_auth():
        # Manually get auth context from request
        try:
            from ..dependencies.auth import get_auth_context, get_auth_service

            # Extract authorization header and auth service manually since we're not using Depends()
            authorization = request.headers.get("Authorization")
            auth_service = get_auth_service(request)
            auth = await get_auth_context(request, authorization, auth_service)
            if auth is None:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
        except HTTPException:
            raise
        except Exception as e:
            logger.warning(f"Authentication failed for /setup/config: {e}")
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")

    # Get template from CLI flag (via runtime config) or environment variable
    # CLI --template flag takes precedence on first-run before .env exists
    template_id = os.getenv("CIRIS_TEMPLATE")
    if not template_id:
        runtime = getattr(request.app.state, "runtime", None)
        if runtime and hasattr(runtime, "essential_config") and runtime.essential_config:
            template_id = getattr(runtime.essential_config, "default_template", None)
    if not template_id:
        template_id = "default"

    # Read current config from environment
    config = SetupConfigResponse(
        llm_provider="openai" if os.getenv("OPENAI_API_BASE") is None else "other",
        llm_base_url=os.getenv("OPENAI_API_BASE"),
        llm_model=os.getenv("OPENAI_MODEL"),
        llm_api_key_set=bool(os.getenv("OPENAI_API_KEY")),
        backup_llm_base_url=os.getenv("CIRIS_OPENAI_API_BASE_2"),
        backup_llm_model=os.getenv("CIRIS_OPENAI_MODEL_NAME_2"),
        backup_llm_api_key_set=bool(os.getenv("CIRIS_OPENAI_API_KEY_2")),
        template_id=template_id,
        enabled_adapters=os.getenv("CIRIS_ADAPTER", "api").split(","),
        agent_port=int(os.getenv("CIRIS_API_PORT", "8080")),
    )

    return SuccessResponse(data=config)


@router.put(
    "/config",
    responses={**RESPONSES_403, **RESPONSES_500},
)
async def update_config(
    setup: SetupCompleteRequest,
    auth: AuthAdminDep,
) -> SuccessResponse[Dict[str, str]]:
    """Update configuration.

    Updates setup configuration after initial setup.
    Requires admin authentication (enforced by AuthAdminDep).
    """
    # Note: Admin role check is performed by AuthAdminDep dependency
    _ = auth  # Used for auth enforcement

    try:
        # Save updated configuration (path determined internally)
        config_path = _save_setup_config(setup)

        return SuccessResponse(
            data={
                "status": "updated",
                "message": "Configuration updated successfully",
                "config_path": str(config_path),
                "next_steps": "Restart the agent to apply changes",
            }
        )

    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
