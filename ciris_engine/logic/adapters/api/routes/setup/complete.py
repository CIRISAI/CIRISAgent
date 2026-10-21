"""Setup completion endpoint and helpers for CIRIS.

This module provides the /complete endpoint and all helper functions
for saving configuration during setup. Users are the node's: setup reads the
node-claimed owner and keys the agent's consent and preferences to it.
"""

import asyncio
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, status

from ciris_engine.logic.config.db_paths import get_sqlite_db_full_path
from ciris_engine.logic.setup.wizard import create_env_file
from ciris_engine.logic.utils.env_file import env_line
from ciris_engine.logic.utils.node_ownership import claim_pin_file, node_owned
from ciris_engine.schemas.api.responses import SuccessResponse
from ciris_engine.schemas.runtime.node_ownership import CLAIM_ROUTE, NODE_UNCLAIMED_ERROR, UPGRADE_CLAIM_ROUTES

from .._common import RESPONSES_400_403_500
from .dependencies import SetupOnlyDep
from .helpers import _validate_system_admin_password
from .llm_validation import _get_provider_base_url
from .models import SetupCompleteRequest

logger = logging.getLogger(__name__)


class _NodeUnclaimedRefusal(Exception):
    """Setup completion on a node with no owner: refused with 409, never minted."""


router = APIRouter()

# Module-level set to hold references to background tasks, preventing garbage collection
_background_tasks: set[asyncio.Task[None]] = set()


# =============================================================================
# SETUP USER HELPER FUNCTIONS
# =============================================================================


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
        logger.info("[OK] Updated admin password")
    else:
        logger.warning("[WARN] Default admin WA not found")


#: Roles a node-claimed owner can hold. Mirrors `setup/dependencies.py`, which
#: needs the same "is there already a human in charge?" answer for the wizard gate.
_OWNER_ROLES = ("root", "authority")


class _NodeOwner:
    """The node-claimed owner: the ONE user setup completes for.

    NOT a `WACertificate`, and it cannot be one: `WACertificate.wa_id` is pinned
    to `^wa-\\d{4}-\\d{2}-\\d{2}-[A-Z0-9]{6}$`, and a node-claimed owner's id is
    `wa-root-<...>`. That regex is exactly why `_is_brain_wa_row` exists and why
    this owner is invisible to `list_was()`.

    Deliberately carries NO credential. The node owns auth and user creation
    (CIRISServer#9), ROOT bootstrap (#19) and the upgrade claim (#37); every
    login it accepts resolves to this `wa_id`, which is therefore the
    `AuthContext.user_id` every brain route sees. This type exists only so the
    artifacts the AGENT still owns, the founding-partnership consent node and
    the user's language/location preferences, are keyed to that same id.
    """

    __slots__ = ("wa_id", "name", "role")

    def __init__(self, wa_id: str, name: str, role: str) -> None:
        self.wa_id = wa_id
        self.name = name
        self.role = role


def _node_owner_rows() -> list[_NodeOwner]:
    """Every active node-claimed owner row (ROOT or AUTHORITY, not a brain cert).

    A failed read yields what it read, never an invented owner: the caller
    refuses setup when it cannot name one, so a read error fails closed.
    """
    from ciris_engine.logic.persistence.stores.authentication_store import _is_brain_wa_row, _list_active_by_role

    owners: list[_NodeOwner] = []
    for role in _OWNER_ROLES:
        try:
            rows = _list_active_by_role(role)
        except Exception as exc:  # noqa: BLE001
            logger.warning("CIRIS_USER_CREATE: could not enumerate %s rows (%s)", role, type(exc).__name__)
            continue
        for row in rows or []:
            if _is_brain_wa_row(row) or not row.get("wa_id"):
                continue
            owners.append(
                _NodeOwner(
                    wa_id=str(row.get("wa_id")),
                    name=str(row.get("name") or ""),
                    role=str(row.get("role") or role),
                )
            )
    return owners


def _resolve_node_owner(setup: SetupCompleteRequest) -> Optional[_NodeOwner]:
    """THE ONE USER SOURCE: the owner the node already holds for this setup.

    The wizard claims the node (claim-remote, or upgrade-owner) BEFORE it posts
    /v1/setup/complete, so the user exists by the time this runs, and the node
    made it. The agent mints nothing. It used to: a brain ROOT cert, OAuth
    linking, a password hash, then a provisional-cert retirement and a
    single-holder repair to undo the duplicates its own minting created. All of
    that is the node's (CIRISServer#9/#19/#37) and is gone.

    Which owner row, in order of precision:
      1. OAuth: the cert the substrate bound this provider identity to at claim.
      2. The owner row answering to the setup username.
      3. The node's single owner row, when there is exactly one.
    None when the node holds no owner this setup can name; the caller refuses
    with 409 node_unclaimed and writes nothing.
    """
    from ciris_engine.logic.persistence.stores import authentication_store

    owners = _node_owner_rows()

    if setup.oauth_provider and setup.oauth_external_id:
        try:
            holder = authentication_store.fabric_oauth_holder_id(
                str(setup.oauth_provider), str(setup.oauth_external_id)
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("CIRIS_USER_CREATE: could not read the provider identity's holder (%s)", type(exc).__name__)
            holder = None
        if holder:
            for owner in owners:
                if owner.wa_id == holder:
                    return owner
            return _NodeOwner(wa_id=holder, name=setup.admin_username, role="root")

    wanted = (setup.admin_username or "").strip().casefold()
    if wanted:
        for owner in owners:
            if owner.name.strip().casefold() == wanted:
                return owner

    if len(owners) == 1:
        return owners[0]
    return None


async def _ensure_system_wa(auth_service: Any) -> None:
    """Ensure system WA exists for signing system tasks."""
    system_wa_id = await auth_service.ensure_system_wa_exists()
    if system_wa_id:
        logger.info(f"[OK] System WA ready: {system_wa_id}")
    else:
        logger.warning("[WARN] Could not create system WA - deferral handling may not work")


def _create_founding_partnership(wa_id: str, ingress_user_id: Optional[str] = None) -> None:
    """Create a default PARTNERED consent record for the setup user.

    The user who completes the setup wizard has explicitly consented by
    provisioning the agent.  The agent's consent is expressed through its
    template configuration — Ally's foundational identity is partnership
    ("Your growth supports mine").  This is configured consistency, not
    bypassed safeguards (see COGNITIVE_STATE_BEHAVIORS FSD).

    Creates a GraphNode with type=CONSENT using the consent/{user_id}
    pattern that matches the ConsentService lookups.

    THE KEY IS THE ID THE USER AUTHENTICATES AS. ConsentService looks consent
    up by `AuthContext.user_id`. Every node login (password, Google, Apple, the
    OAuth callback, the device grant) resolves to the owner's `wa_id`
    (`ciris_server.resolve_bearer`), so the node owner's consent lives at
    `consent/{wa_id}`. Keying OAuth owners by `provider:subject` instead was
    correct only while the brain issued its own OAuth tokens; once auth folded
    into the node (2.9.14) the owner's first interact missed this record and got
    the TEMPORARY default.

    The one exception is ingress auth (HA Supervisor and similar), whose
    `AuthContext.user_id` is still `provider:external_id`.

    Args:
        wa_id: The owner's WA id (e.g. "wa-root-..." for a node-claimed owner)
        ingress_user_id: Ingress setup only: the ingress identity
                         ("provider:external_id") that ingress auth resolves to.
    """
    from ciris_engine.logic.persistence import add_graph_node
    from ciris_engine.logic.services.lifecycle.time.service import TimeService
    from ciris_engine.schemas.consent.core import ConsentCategory, ConsentStatus, ConsentStream
    from ciris_engine.schemas.services.graph_core import GraphNode, GraphScope, NodeType

    now = datetime.now(timezone.utc)

    consent_user_id = ingress_user_id if ingress_user_id else wa_id

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

    # ConsentService stores nodes as consent/{user_id}, user_id = AuthContext.user_id
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
    add_graph_node(node, time_service)
    # FALSE POSITIVE (py/clear-text-logging-sensitive-data). `node_id` is a graph
    # node key -- `consent/{user_id}` -- where user_id is the owner's WA id (or,
    # for ingress setup, the ingress id). Identifiers that appear throughout the
    # audit trail by design; not a credential.
    # CodeQL flags it because the value derives from the setup request, which
    # ALSO carries a password field it never reaches.
    #
    # Newly reported only because the emoji sweep rewrote these two lines
    # (checkmark -> [OK]) for the Windows cp1252 fix, so pre-existing logging
    # counts as "changed by this PR".
    # codeql[py/clear-text-logging-sensitive-data]
    print(f"[SETUP_COMPLETE] [OK] Founding partnership created: {node_id} (PARTNERED)")
    # codeql[py/clear-text-logging-sensitive-data]
    logger.info(f"[OK] Founding partnership created for setup user: {node_id}")


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
    add_graph_node(node, time_service)
    # SAME RULE AS THE OAUTH LINES ABOVE: nothing derived from `setup` reaches the
    # logger. `attributes` is built from the setup request, which carries
    # system_admin_password, so language/location/user_id are all tainted — and a
    # user's LOCATION is genuinely worth not writing to a log file regardless of
    # what CodeQL thinks of it. Which preferences exist is the diagnostic; their
    # values are the user's business.
    stored = sorted(k for k in ("preferred_language", "location", "share_location_in_traces") if k in attributes)
    logger.info("Stored user preferences for the setup user: %d key(s) %s", len(stored), stored)


async def _create_setup_users(
    setup: SetupCompleteRequest,
    main_db_path: str,
    ingress_user_id: Optional[str] = None,
    ingress_user_name: Optional[str] = None,
    ingress_user_email: Optional[str] = None,
) -> None:
    """Attach the agent's per-user artifacts to the node-claimed owner.

    The node creates the user (CIRISServer#9 auth, #19 ROOT bootstrap, #37
    upgrade-owner) when the wizard claims it, before this runs. Setup mints no
    user: it resolves that owner (`_resolve_node_owner`), refuses with 409
    node_unclaimed when there is none, and writes the founding partnership and
    preferences under the owner's wa_id.

    When skip_user_creation=True (external auth like HA ingress, CIRISMedical enterprise),
    we skip regular user creation but AUTO-MINT a WA and create founding partnership
    for the ingress user who completed setup.

    Args:
        setup: Setup configuration with user details
        main_db_path: Path to the main agent database (from running application)
        ingress_user_id: User ID of ingress auth user completing setup (e.g., "home_assistant:abc123")
        ingress_user_name: Display name of the ingress user (for WA creation)
        ingress_user_email: Email of the ingress user (for WA creation)
    """
    from ciris_engine.logic.services.infrastructure.authentication.service import AuthenticationService
    from ciris_engine.logic.services.lifecycle.time.service import TimeService
    from ciris_engine.schemas.services.authority_core import WARole

    logger.info("=" * 70)
    logger.info("CIRIS_USER_CREATE: _create_setup_users() called")
    logger.info("=" * 70)
    from ciris_engine.logic.persistence.db.core import _redact_dsn

    logger.info(f"CIRIS_USER_CREATE: main_db_path = {_redact_dsn(str(main_db_path))}")
    logger.info(f"CIRIS_USER_CREATE: skip_user_creation = {setup.skip_user_creation}")
    # SECURITY: Log provider only, not full external_id (could be PII)
    ingress_provider = ingress_user_id.split(":")[0] if ingress_user_id and ":" in ingress_user_id else None
    logger.info(f"CIRIS_USER_CREATE: ingress_provider = {ingress_provider}, has_user_id = {bool(ingress_user_id)}")
    logger.info(f"CIRIS_USER_CREATE: ingress_user_name = {ingress_user_name}")

    # IMPORTANT: If we have an ingress user completing setup, they ARE the admin
    # Don't create a separate "ha_admin" user - use the ingress identity directly
    # This prevents identity fragmentation (two separate users for same person)
    use_ingress_user = ingress_user_id is not None

    # Skip regular user creation when:
    # 1. External auth is handling authentication (skip_user_creation=True)
    # 2. We have an ingress user completing setup (use their identity)
    # In both cases, AUTO-MINT a WA for the ingress user with ROOT authority
    if setup.skip_user_creation or use_ingress_user:
        reason = (
            "skip_user_creation=True" if setup.skip_user_creation else f"ingress user detected ({ingress_provider})"
        )
        logger.info(f"CIRIS_USER_CREATE: Skipping regular user creation ({reason}) - auto-minting WA for ingress user")
        # Still need to ensure system WA exists for agent operations
        time_service = TimeService()
        await time_service.start()
        auth_service = AuthenticationService(db_path=main_db_path, time_service=time_service, key_dir=None)
        await auth_service.start()
        try:
            await _ensure_system_wa(auth_service)
            logger.info("CIRIS_USER_CREATE: System WA ensured for agent operations")

            # AUTO-MINT: Create WA with ROOT role for ingress user who completed setup
            if ingress_user_id:
                # SECURITY: Log provider only, not full external_id
                logger.info(f"CIRIS_USER_CREATE: Auto-minting ROOT WA for ingress provider: {ingress_provider}")

                # Use provided name/email or derive from ingress_user_id
                wa_name = ingress_user_name or ingress_user_id.split(":")[-1]  # e.g., "home_assistant:admin" -> "admin"
                wa_email = ingress_user_email or f"{wa_name}@ingress.local"

                # Create WA with ROOT role - they completed setup, they're the authority
                wa_cert = await auth_service.create_wa(
                    name=wa_name,
                    email=wa_email,
                    scopes=["read:any", "write:any"],  # ROOT gets full scopes
                    role=WARole.ROOT,
                )
                logger.info(f"CIRIS_USER_CREATE: [OK] Auto-minted WA: {wa_cert.wa_id} (name={wa_name}, role=ROOT)")

                # Link ingress identity to WA so lookups by provider:external_id work
                # ingress_user_id format: "provider:external_id" (e.g., "home_assistant:abc123")
                if ":" in ingress_user_id:
                    provider, external_id = ingress_user_id.split(":", 1)
                    try:
                        await auth_service.link_oauth_identity(
                            wa_id=wa_cert.wa_id,
                            provider=provider,
                            external_id=external_id,
                            account_name=wa_name,
                            metadata={"ingress_setup": "true"},
                            primary=True,
                        )
                        logger.info(
                            f"CIRIS_USER_CREATE: ✅ Linked ingress identity ({ingress_provider}) to WA {wa_cert.wa_id}"
                        )
                    except Exception as link_err:
                        # Non-fatal - log but continue (founding partnership is more important)
                        logger.warning(f"CIRIS_USER_CREATE: [WARN] Failed to link ingress identity: {link_err}")

                # Create founding partnership for the ingress user
                logger.info(
                    f"CIRIS_USER_CREATE: Creating founding partnership for ingress provider: {ingress_provider}"
                )
                _create_founding_partnership(wa_cert.wa_id, ingress_user_id)
                logger.info(
                    f"CIRIS_USER_CREATE: ✅ Founding partnership created for ingress provider: {ingress_provider}"
                )

                # Store preferences if provided
                _store_user_preferences(wa_cert.wa_id, setup)
            else:
                logger.info("CIRIS_USER_CREATE: No ingress user ID provided, skipping WA mint and partnership")
        finally:
            await auth_service.stop()
            await time_service.stop()
        return

    # THE NODE-CLAIMED OWNER IS THE USER. The node created it at claim time; the
    # agent reads it and keys its own artifacts to it. Resolved before anything
    # is written, so a node with no owner this setup can name writes nothing.
    owner = _resolve_node_owner(setup)
    if owner is None:
        raise _NodeUnclaimedRefusal(
            "The node holds no owner for this setup user. The node creates the user when it is "
            f"claimed ({CLAIM_ROUTE}, or {' then '.join(UPGRADE_CLAIM_ROUTES)} on an upgraded node); "
            "the agent mints none."
        )
    logger.info("CIRIS_USER_CREATE: setup completes for the node-claimed owner; the agent mints no user")

    time_service = TimeService()
    await time_service.start()

    auth_service = AuthenticationService(db_path=main_db_path, time_service=time_service, key_dir=None)
    await auth_service.start()

    try:
        # Founding partnership: the user consented by completing setup, the
        # agent's consent is configured in its template. Keyed to the owner's
        # wa_id, the id every node login resolves to (AuthContext.user_id).
        _create_founding_partnership(owner.wa_id)
        _store_user_preferences(owner.wa_id, setup)
        await _ensure_system_wa(auth_service)
        await _update_system_admin_password(auth_service, setup, owner.wa_id)
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
    f.write(env_line("CIRIS_OPENAI_API_KEY_2", setup.backup_llm_api_key))
    if setup.backup_llm_base_url:
        f.write(env_line("CIRIS_OPENAI_API_BASE_2", setup.backup_llm_base_url))
    if setup.backup_llm_model:
        f.write(env_line("CIRIS_OPENAI_MODEL_NAME_2", setup.backup_llm_model))


def _write_node_connection_config(f: Any, setup: SetupCompleteRequest) -> None:
    """Write CIRISNode connection configuration if provided."""
    if not setup.node_url:
        return
    _write_section_header(f, "CIRISNode Connection (provisioned via device auth)")
    f.write(env_line("CIRISNODE_BASE_URL", setup.node_url))
    if setup.identity_template:
        f.write(env_line("CIRIS_IDENTITY_TEMPLATE", setup.identity_template))
    if setup.stewardship_tier is not None:
        f.write(f"CIRIS_STEWARDSHIP_TIER={setup.stewardship_tier}\n")
    if setup.approved_adapters:
        f.write(env_line("CIRIS_APPROVED_ADAPTERS", ",".join(setup.approved_adapters)))
    if setup.org_id:
        f.write(env_line("CIRIS_ORG_ID", setup.org_id))
    # Portal-issued key ID (private key is stored in hardware keystore, NOT here)
    if setup.signing_key_id:
        f.write(env_line("CIRIS_SIGNING_KEY_ID", setup.signing_key_id))


def _write_licensed_package_config(f: Any, setup: SetupCompleteRequest) -> None:
    """Write licensed module package configuration if provided."""
    if not setup.licensed_package_path:
        return
    _write_section_header(f, "Licensed Module Package")
    f.write(env_line("CIRIS_LICENSED_PACKAGE_PATH", setup.licensed_package_path))
    if setup.licensed_modules_path:
        f.write(env_line("CIRIS_MODULE_PATH", setup.licensed_modules_path))


def _write_verify_config(f: Any, setup: SetupCompleteRequest) -> None:
    """Write CIRISVerify configuration if provided."""
    if not setup.verify_binary_path:
        return
    _write_section_header(f, "CIRISVerify")
    f.write(env_line("CIRIS_VERIFY_BINARY_PATH", setup.verify_binary_path))
    require_hw = "true" if setup.verify_require_hardware else "false"
    f.write(f"CIRIS_VERIFY_REQUIRE_HARDWARE={require_hw}\n")


def _emit_accord_metrics_consent(setup: SetupCompleteRequest) -> None:
    """Accord-traces opt-in at setup → the CEG consent wire artifact.

    2.9.6 (#866 LensCore fold): the adapter is bootstrap-required, so the
    setup checkbox no longer controls loading and no longer writes
    CIRIS_ACCORD_METRICS_CONSENT* env vars (those survive only as a
    QA-runner override). Opt-in IS the CEG promotion event: a
    `consent:community_trust:v1` grant attestation written to the local
    persist tier, which lens-core's consent gate resolves (newest-wins)
    at every trace seal. Revocation later writes withdraws/recants via
    the my-data routes — the same dimension, the same gate.

    Best-effort: a failed emit must never break setup completion — the
    user can re-grant from Data & Privacy settings (the accord-settings
    PUT emits the identical artifact).

    Goes through the one trace-sharing handle so the wizard grants the
    SHIP gate too. Granting capture alone was the silent failure: traces
    sealed, the node reported healthy, and nothing ever left it because
    no ``consent:replication`` grant named the canonical.

    ``require_opt_in=False``: the checkbox IS the owner's act (this only
    runs when the user selected it), and the env var it normally lands in
    has not been written yet at this point in completion.

    ``analyze`` is the wizard's own toggle, not a constant. The substrate
    marks the be-scored dimension ``required: false`` with named costs;
    hardcoding it True granted a dimension the owner was never asked about.
    """
    if "ciris_accord_metrics" not in setup.enabled_adapters:
        return
    try:
        from ciris_engine.logic.services.governance.consent.trace_sharing import grant_trace_sharing
        from ciris_engine.schemas.consent.trace_sharing import TraceConsentSource

        result = grant_trace_sharing(
            TraceConsentSource.SETUP_WIZARD,
            require_opt_in=False,
            analyze=setup.trace_analyze,
        )
        if result.complete:
            logger.info(
                f"[SETUP] Accord-traces consent granted: capture={result.capture_grant_id} "
                f"ship={result.peers_authored}"
            )
        else:
            # Not necessarily wrong: pre-root there is no canonical peer to name
            # yet, and the delivery probe retries the ship grant after the claim.
            logger.warning(
                f"[SETUP] Accord-traces opt-in INCOMPLETE: capture="
                f"{result.capture_grant_id or 'MISSING'} ship={result.peers_authored or 'MISSING'} "
                f"errors={result.errors} — the delivery probe retries the ship grant once a "
                f"canonical peer roots; user can also re-grant from Data & Privacy settings"
            )
    except Exception as e:
        logger.warning(f"[SETUP] Accord-traces CEG grant emit failed (non-fatal): {e}")


#: Providers that run without an API key — on-device inference and local
#: inference servers. Mirrors the wizard's own keyless whitelist
#: (``SetupState.canProceedFromCurrentStep``); a provider outside this set with
#: an empty key is not a configuration, it is an unfinished one.
KEYLESS_LLM_PROVIDERS = frozenset({"local", "localai", "local_inference", "mobile_local"})


def _has_usable_llm_provider(setup: SetupCompleteRequest) -> bool:
    """Will this configuration produce a working LLM?

    Not a style check — a false answer here is the difference between an agent
    that degrades and one that refuses to boot. ``llm_service`` is optional only
    on the first run; on the NEXT boot ``is_first_run()`` is False, so
    ``verify_core_services`` promotes it to critical and initialization ABORTS.
    The untouched wizard default (``provider="OpenAI"``, ``key=""``) lands
    exactly there.
    """
    if setup.run_without_ai:
        return False
    provider = (setup.llm_provider or "").strip().lower()
    if not provider or provider == "none":
        return False
    if provider in KEYLESS_LLM_PROVIDERS:
        return True
    return bool((setup.llm_api_key or "").strip())


def _write_llm_availability_config(f: Any, setup: SetupCompleteRequest) -> None:
    """Write ``CIRIS_SERVICES_DISABLED=true`` when no usable provider was chosen.

    This is the existing, shipped mechanism — the same state
    ``POST /v1/system/llm/ciris-services/disable`` produces — and it is what
    keeps ``llm_service`` optional at boot. It is written for the explicit
    "run without AI" choice AND for any path that ends without a usable
    provider, because those two are the same runtime state and only one of
    them used to be handled.
    """
    if _has_usable_llm_provider(setup):
        return
    _write_section_header(f, "AI disabled (no usable LLM provider configured)")
    f.write("CIRIS_SERVICES_DISABLED=true\n")
    if setup.run_without_ai:
        logger.info("[SETUP] Owner chose to run without AI — CIRIS_SERVICES_DISABLED=true")
        _write_run_without_ai(f)
    else:
        logger.warning(
            "[SETUP] No usable LLM provider (provider=%r, key_set=%s) — writing "
            "CIRIS_SERVICES_DISABLED=true so the next boot degrades instead of aborting",
            setup.llm_provider,
            bool((setup.llm_api_key or "").strip()),
        )


def _retract_run_without_ai(config_path: Optional[Path]) -> None:
    """Undo ``_write_run_without_ai`` after a post-save failure.

    The flag is written by ``_save_and_reload_config`` BEFORE the fallible half
    of setup (audit bootstrap, persist engine, admin users, auth reload). If any
    of those raise, the client gets an error -- but a flag left in the file means
    the NEXT launch bypasses the setup runtime and boots the standalone node,
    with no admin account and no wizard to retry. Same shape as the signing-key
    rollback above it: remove the file so the next start is a clean first run,
    and clear the process copy so this process's own exit path
    (``main.py`` -> ``node_only_config``) does not act on it either.
    """
    from ciris_engine.node_only import ENV_FLAG, ENV_KEY_ID

    for key in (ENV_FLAG, ENV_KEY_ID):
        os.environ.pop(key, None)
    if config_path is None:
        return
    try:
        config_path.unlink(missing_ok=True)
        logger.warning(
            "[RUN-WITHOUT-AI] setup failed after %s was written -- removed it so the next start is a clean "
            "first run, not a node-only boot with no admin account",
            config_path,
        )
    except OSError as exc:
        logger.error("[RUN-WITHOUT-AI] could not remove %s after a failed setup: %s", config_path, exc)


def _write_run_without_ai(f: Any) -> None:
    """Record the explicit choice so every later boot is ciris-server and the client (CIRISAgent#1149).

    ``CIRIS_SERVICES_DISABLED`` only keeps llm_service optional inside the
    brain; this flag means there is no brain at all. The node's keystore alias
    is written beside it so the node-only boot serves the SAME identity the
    wizard just claimed -- the wheel's own desktop default (``ciris-client``)
    would mint a second one.
    """
    from ciris_engine.node_only import ENV_FLAG, ENV_KEY_ID

    f.write(f"{ENV_FLAG}=true\n")
    key_id: Optional[str] = None
    try:
        from ciris_engine.logic.runtime.node_fold import _resolve_key_id

        key_id = _resolve_key_id()
    except Exception as exc:  # noqa: BLE001 -- the flag must still be written
        logger.warning("[SETUP] could not resolve the node key alias for node-only boots: %s", exc)
    if key_id:
        f.write(f"{ENV_KEY_ID}={key_id}\n")
    logger.info(
        "[RUN-WITHOUT-AI] recorded in the home's .env: %s=true %s=%s -- from now on every boot is ciris-server "
        "and the client (no brain); the read API will be on :%d. Set %s=false in the environment to run the brain once.",
        ENV_FLAG,
        ENV_KEY_ID,
        key_id or "<unresolved: the node will use the wheel's default label>",
        4243,
        ENV_FLAG,
    )
    if not key_id:
        logger.error(
            "[RUN-WITHOUT-AI] the node key alias could not be resolved at setup-complete; node-only boots will "
            "NOT serve the identity this wizard claimed until %s is set in .env",
            ENV_KEY_ID,
        )


def _write_mobile_local_llm_config(f: Any, setup: SetupCompleteRequest) -> None:
    """Write Mobile Local LLM adapter configuration if enabled."""
    if "mobile_local_llm" not in setup.enabled_adapters and setup.llm_provider != "mobile_local":
        return
    f.write("\n# Mobile Local LLM (On-Device Inference)\n")
    f.write("CIRIS_MOBILE_LOCAL_LLM_ENABLED=true\n")
    if setup.llm_model:
        f.write(env_line("CIRIS_MOBILE_LOCAL_LLM_MODEL", setup.llm_model))
    logger.info("[SETUP] Mobile Local LLM adapter enabled for on-device inference")


def _write_adapter_specific_config(f: Any, setup: SetupCompleteRequest) -> None:
    """Write adapter-specific environment variables."""
    if not setup.adapter_config:
        return
    f.write("\n# Adapter-Specific Configuration\n")
    ha_env_mapping = {
        "access_token": "HOME_ASSISTANT_TOKEN",
        "refresh_token": "HOME_ASSISTANT_REFRESH_TOKEN",
        "base_url": "HOME_ASSISTANT_URL",
        "client_id": "HOME_ASSISTANT_CLIENT_ID",
    }
    for key, value in setup.adapter_config.items():
        env_var_name = ha_env_mapping.get(key, key)
        f.write(f"{env_var_name}={value}\n")


def _write_location_config(f: Any, setup: SetupCompleteRequest) -> None:
    """Write location settings for weather/navigation adapters."""
    if setup.location_city:
        f.write(env_line("CIRIS_USER_CITY", setup.location_city))
    if setup.location_region:
        f.write(env_line("CIRIS_USER_REGION", setup.location_region))
    if setup.location_country:
        f.write(env_line("CIRIS_USER_COUNTRY", setup.location_country))
        location_parts = [setup.location_city, setup.location_region, setup.location_country]
        location_display = ", ".join(p for p in location_parts if p)
        f.write(env_line("CIRIS_USER_LOCATION", location_display))
    if setup.location_latitude is not None:
        f.write(env_line("CIRIS_USER_LATITUDE", setup.location_latitude))
    if setup.location_longitude is not None:
        f.write(env_line("CIRIS_USER_LONGITUDE", setup.location_longitude))
    if setup.timezone:
        f.write(env_line("CIRIS_USER_TIMEZONE", setup.timezone))


def _write_location_sharing_consent(f: Any, setup: SetupCompleteRequest) -> None:
    """Write location sharing consent for telemetry."""
    if not setup.share_location_in_traces:
        return
    consent_timestamp = datetime.now(timezone.utc).isoformat()
    f.write("\n# Location Data Sharing Consent\n")
    f.write("CIRIS_SHARE_LOCATION_IN_TRACES=true\n")
    f.write(f"CIRIS_LOCATION_CONSENT_TIMESTAMP={consent_timestamp}\n")
    logger.info(f"[SETUP] Location sharing consent enabled: {consent_timestamp}")


def _save_setup_config(setup: SetupCompleteRequest) -> Path:
    """Save setup configuration to .env file.

    Args:
        setup: Setup configuration

    Returns:
        Path where config was saved
    """
    llm_base_url = _get_provider_base_url(setup.llm_provider or "", setup.llm_base_url) or ""

    # For local providers, use "local" as placeholder API key if none provided
    # mobile_local provider doesn't need an API key - it runs on-device
    llm_api_key = setup.llm_api_key or ""
    if not llm_api_key and setup.llm_provider in ("local", "local_inference", "mobile_local"):
        llm_api_key = "local"

    config_path = create_env_file(
        llm_provider=setup.llm_provider or "",
        llm_api_key=llm_api_key,
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

        # Write adapter-specific configs using helper functions
        _emit_accord_metrics_consent(setup)
        _write_llm_availability_config(f, setup)
        _write_mobile_local_llm_config(f, setup)
        _write_adapter_specific_config(f, setup)

        # User preferences (language & location)
        f.write("\n# User Preferences (from setup wizard PREFERENCES step)\n")
        preferred_lang = setup.preferred_language or "en"
        f.write(env_line("CIRIS_PREFERRED_LANGUAGE", preferred_lang))
        _write_location_config(f, setup)
        _write_location_sharing_consent(f, setup)

        # Write optional configuration sections
        _write_backup_llm_config(f, setup)
        _write_node_connection_config(f, setup)
        _write_licensed_package_config(f, setup)
        _write_verify_config(f, setup)

    return config_path


def _log_setup_debug_info(setup: SetupCompleteRequest) -> None:
    """Log which kind of setup this is. Never the provider subject or email (PII)."""
    logger.info("CIRIS_SETUP_DEBUG " + "=" * 60)
    logger.info("CIRIS_SETUP_DEBUG complete_setup() endpoint called")
    logger.info("CIRIS_SETUP_DEBUG " + "=" * 60)

    logger.info(f"CIRIS_SETUP_DEBUG   oauth setup = {bool(setup.oauth_provider)}")

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


async def _node_only_restart(runtime: Any) -> None:
    """After a run-without-AI setup, become the node -- here, not via the runtime's shutdown.

    Registered with ``BackgroundTasks``, so Starlette runs it AFTER the
    setup-complete response has been sent. That ordering is the contract the
    client asked for (CIRISAgent#1149/#1151): the 200 always arrives first, and
    a dropped connection on ``/v1/setup/complete`` stays a real failure.

    WHY THIS DOES THE WORK ITSELF. The first version asked the runtime to shut
    down and let ``main.py``'s exit path exec into the node. That is correct
    only while the runtime is RUNNING, and the moment this feature fires is
    exactly the moment it is not: during first-run the runtime is parked waiting
    for the wizard, nothing awaits its shutdown event, and an end-to-end run
    showed ``RUNTIME SHUTDOWN REQUESTED`` logged and then :8080 still serving
    nine minutes later. So the hand-off happens here, and ``main.py``'s exit
    path stays as the second door for a setup re-run against a live runtime.

    :8080 is told to stop accepting BEFORE the exec, so a client that has not
    yet re-pointed gets connection-refused -- positive evidence -- rather than a
    socket that accepts and never answers. Its task is deliberately not awaited:
    this coroutine is itself one of that server's in-flight requests.
    """
    from ciris_engine import node_only

    cfg = node_only.node_only_config()
    if cfg is None:
        logger.error(
            "[RUN-WITHOUT-AI] the flag was just written but does not read back from the home's .env; "
            "staying on the agent runtime rather than handing off blind"
        )
        return

    for adapter in getattr(runtime, "adapters", None) or []:
        server = getattr(adapter, "_server", None)
        if server is not None:
            server.should_exit = True
            logger.info(
                "[RUN-WITHOUT-AI] asked %s to stop accepting on :8080; a client that has not moved yet "
                "will get connection-refused rather than a hang",
                type(adapter).__name__,
            )

    # Let the response finish leaving the transport before the process image is
    # replaced. The bytes are already written; this is the drain, not a guess at
    # how long the client needs.
    await asyncio.sleep(0.25)

    logger.info(
        "[RUN-WITHOUT-AI] setup complete; replacing this process (pid=%d) with the ciris-server node. "
        ":8080 goes away and the client moves to :4243",
        os.getpid(),
    )
    if not node_only.exec_into_node(cfg):
        from ciris_engine.logic.utils.platform_detection import is_desktop

        if not is_desktop():
            # Not a failure: an embedded runtime has no process to become and must
            # not end the host's (CIRISClient#43). The flag is recorded, :8080 has
            # stopped, and the node starts on the runtime's next boot. Do NOT ask
            # the parked runtime to shut down here -- while parked it ignores the
            # request (CIRISAgent#1152), and a log line claiming a shutdown that
            # never happens is the exact vacuous shape this feature has already
            # produced once.
            logger.info(
                "[RUN-WITHOUT-AI] embedded runtime: hand-off deferred to the runtime's next boot; "
                "the flag is recorded and :8080 has stopped. In-session hand-off here is gated on #1152."
            )
            return
        logger.error(
            "[RUN-WITHOUT-AI] exec into the node FAILED; the agent runtime is left without its API server. "
            "Asking it to shut down so the next boot starts the node from the recorded flag."
        )
        runtime.request_shutdown("Run without AI: exec into the ciris-server node failed")


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
    has_resume = hasattr(runtime, "resume_from_first_run")
    logger.info(
        "[Setup] Scheduling runtime resume: runtime_type=%s has_resume_from_first_run=%s "
        "resume_started_at=%.3f agent_processor_present=%s",
        type(runtime).__name__,
        has_resume,
        runtime._resume_started_at,
        bool(getattr(runtime, "agent_processor", None)),
    )

    async def _resume_runtime() -> None:
        await asyncio.sleep(0.5)  # Brief delay to ensure response is sent
        try:
            logger.info("[Setup] Background resume task starting")
            await runtime.resume_from_first_run()
            logger.info(
                "Successfully resumed from first-run mode - agent processor running=%s",
                bool(getattr(runtime, "agent_processor", None)),
            )
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


async def _try_get_ingress_user(request: Request) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """Try to get ingress user info from the request without requiring auth.

    This is used during setup completion to detect if an ingress auth provider
    is handling the request, so we can auto-mint a WA for them.

    Returns:
        Tuple of (user_id, display_name, email) or (None, None, None) if no ingress auth
    """
    import os

    from ...dependencies.auth import _ingress_auth_providers

    # First check registered providers
    for registered in _ingress_auth_providers:
        provider = registered.provider
        try:
            if provider.can_handle_request(request):
                ingress_user = await provider.authenticate_request(request)
                if ingress_user:
                    user_id = f"{ingress_user.provider}:{ingress_user.external_id}"
                    display_name = ingress_user.display_name or ingress_user.username
                    email = ingress_user.email
                    logger.info(f"[SETUP] Detected ingress user: {user_id} ({display_name})")
                    return user_id, display_name, email
        except Exception as e:
            logger.debug(f"[SETUP] Ingress provider {provider.provider_name} check failed: {e}")
            continue

    # FALLBACK: Check for HA ingress headers directly if in supervisor mode
    # This handles first-run setup where HA adapter isn't loaded yet
    # SECURITY: Only trust headers from the HA Supervisor IP (172.30.32.2)
    if os.getenv("SUPERVISOR_TOKEN"):
        ha_user_id = request.headers.get("X-Remote-User-Id")
        if ha_user_id:
            # Verify request comes from trusted HA Supervisor IP
            client_ip = request.client.host if request.client else None
            trusted_ips = {"172.30.32.2", "127.0.0.1", "::1"}  # Supervisor + localhost for dev

            if client_ip not in trusted_ips:
                # SECURITY: Don't reveal trusted IP list in logs
                logger.warning(f"[SETUP] Rejecting HA ingress headers from untrusted source")
                return None, None, None

            display_name = request.headers.get("X-Remote-User-Display-Name") or request.headers.get(
                "X-Remote-User-Name"
            )
            # HA doesn't provide email in ingress headers
            logger.info(f"[SETUP] Detected HA ingress user (direct): home_assistant:{ha_user_id} ({display_name})")
            return f"home_assistant:{ha_user_id}", display_name, None

    return None, None, None


@router.post("/complete", responses=RESPONSES_400_403_500, dependencies=[SetupOnlyDep])
async def complete_setup(
    setup: SetupCompleteRequest, request: Request, background_tasks: BackgroundTasks
) -> SuccessResponse[Dict[str, str]]:
    """Complete initial setup.

    Saves configuration and creates initial admin user.
    Only accessible during first-run (SetupOnlyDep enforces this).
    After setup, authentication is required for reconfiguration.

    For ingress auth scenarios (HA Supervisor, CIRISMedical), the user completing
    setup gets an auto-minted WA with ROOT role and a founding partnership.
    """
    _log_setup_debug_info(setup)

    # Try to detect ingress user completing setup (for auto-mint)
    ingress_user_id, ingress_user_name, ingress_user_email = await _try_get_ingress_user(request)
    if ingress_user_id:
        # SECURITY: Log provider only, not full external_id
        _ingress_provider = ingress_user_id.split(":")[0] if ":" in ingress_user_id else "unknown"
        logger.info(f"[SETUP] Ingress user detected ({_ingress_provider}) - will auto-mint WA")

    # The owner's credential is the node's (password, OAuth, or none at all for
    # add-device); only the local admin replacement is checked here.
    _validate_system_admin_password(setup)

    config_path: Optional[Path] = None
    try:
        # Save configuration and reload environment variables
        config_path = _save_and_reload_config(setup)

        # SELF-CUSTODY KEY (FSD-002 / 2.9.7 second-signer removal): the
        # agent's signing identity is the persist Engine's local Ed25519
        # signer — bootstrapped from a local seed at engine construction and
        # federation-registered. A CIRIS agent without a working signing key
        # cannot audit, cannot attest, and cannot operate under the CIRIS
        # trust model, so an unwired/unsignable engine here is terminal.
        try:
            from ciris_engine.logic.persistence.models.graph import get_persist_engine

            engine = get_persist_engine()
            if engine is None:
                # First-run mobile boot order: the wizard completes BEFORE the
                # runtime wires the persist engine (desktop wires it at server
                # boot, which is why this only bites on-device). The engine is
                # the signing identity now, so wire it here — same default DSN
                # the post-setup restart uses; initialize_database is idempotent.
                # MUST run off the event loop: Engine() spins a tokio runtime
                # and block_on's — on the asyncio thread that deadlocks
                # ("Cannot start a runtime from within a runtime").
                import asyncio

                from ciris_engine.logic.persistence import initialize_database

                await asyncio.get_event_loop().run_in_executor(None, initialize_database)
                engine = get_persist_engine()
            if engine is None:
                raise RuntimeError("persist engine not wired — no signing identity available")
            signing_key_id = str(engine.local_derived_key_id())
            logger.info(f"[Setup Complete] Using self-custody signing key (key_id={signing_key_id})")
        except Exception as signing_err:
            # Roll back the partial setup so the next start is a clean
            # first-run rather than a zombie "setup done but no admin" state.
            try:
                config_path.unlink(missing_ok=True)
            except OSError as unlink_err:
                logger.warning(
                    "[Setup Complete] Could not roll back %s after signing failure: %s",
                    config_path,
                    unlink_err,
                )
            # The detail message carries the underlying exception so the
            # client's "Technical details:" line shows the real cause instead
            # of an opaque code. User-facing copy lives in the localized
            # Kotlin/Swift strings.
            msg = (
                f"Signing capability unavailable on this device "
                f"({type(signing_err).__name__}: {signing_err}). "
                "The agent cannot sign audit entries without the persist "
                "engine's local signing identity. Setup has been rolled back; "
                "the agent will now shut down."
            )
            logger.critical("[Setup Complete] %s", msg)
            # Ask the runtime to shut down once this response has been sent.
            runtime = getattr(request.app.state, "runtime", None)
            if runtime is not None:
                try:
                    runtime.request_shutdown(
                        "Signing capability unavailable: engine signing identity initialization failed"
                    )
                except Exception as shutdown_err:
                    logger.error(
                        "[Setup Complete] request_shutdown raised while reporting signing failure: %s",
                        shutdown_err,
                    )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={
                    "code": "CIRIS_VERIFY_SIGNING_UNAVAILABLE",
                    "message": msg,
                },
            )

        # EVERY NODE IS ALWAYS CLAIMED. Setup mints a ROOT WA, and a node that
        # sees a ROOT mints no claim PIN, so completing on an unowned node would
        # suppress the deployer's PIN. Read here, once the engine is wired.
        ownership = await node_owned(fresh=True)
        if ownership.unclaimed:
            raise _NodeUnclaimedRefusal(ownership.unclaimed_message())

        # Audit the key initialization - ensures audit_log table exists.
        # Attestation verifies audit_log exists, so we must have at least one
        # entry before attestation runs post-setup.
        audit_service = getattr(request.app.state, "audit_service", None)
        if audit_service:
            from ciris_engine.schemas.services.graph.audit import AuditEventData

            audit_event = AuditEventData(
                event_type="signing_key_initialized",
                details={
                    "key_id": signing_key_id,
                    "source": "self_custody",  # Agent controls its own key
                    "algorithm": "ed25519",
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

        # 2.9.0: WA certs live in the one process-wide persist engine on the
        # main DB. The auth service attaches to that engine — handing it any
        # other path trips EngineConfigMismatch.
        main_db_path = get_sqlite_db_full_path(runtime.essential_config)
        logger.info(f"Using runtime main database: {main_db_path}")

        # Create users immediately (don't wait for restart)
        # For ingress auth, pass the detected user info for auto-mint
        print(f"[SETUP_COMPLETE] Calling _create_setup_users(username={setup.admin_username})")
        print(f"[SETUP_COMPLETE] Ingress provider: {_ingress_provider if ingress_user_id else 'none'}")
        try:
            await _create_setup_users(
                setup,
                main_db_path,
                ingress_user_id=ingress_user_id,
                ingress_user_name=ingress_user_name,
                ingress_user_email=ingress_user_email,
            )
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
            logger.info("[OK] User cache reloaded - new users now visible to authentication")

        # Build next steps message
        next_steps = "Configuration completed. The agent is now starting. You can log in immediately."
        if setup.system_admin_password:
            next_steps += " Both user passwords have been configured."

        # Resume initialization from first-run mode to start agent processor
        logger.info("Setup complete - resuming initialization to start agent processor")
        if setup.run_without_ai:
            # No runtime to resume: the wizard is done and the owner chose a node
            # with no AI. Handed to FastAPI as a BACKGROUND TASK, which Starlette
            # runs only after this response has been sent -- so the client always
            # receives its 200 before :8080 goes away, and never has to treat a
            # dropped connection as success (CIRISAgent#1149, the client's
            # handover question). main.py's exit path then replaces the process
            # with the ciris-server node.
            background_tasks.add_task(_node_only_restart, runtime)
        else:
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

    except _NodeUnclaimedRefusal as refusal:
        # Roll back like the signing failure above, so the next attempt is
        # still a first run: the deployer claims the node, then completes.
        logger.warning(f"Setup completion refused: {refusal}")
        if config_path is not None:
            try:
                config_path.unlink(missing_ok=True)
            except OSError as unlink_err:
                logger.warning(f"[Setup Complete] Could not roll back {config_path}: {unlink_err}")
        if setup.run_without_ai:
            _retract_run_without_ai(config_path)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": NODE_UNCLAIMED_ERROR,
                "message": f"{NODE_UNCLAIMED_ERROR}: claim the node first. {refusal}",
                "claim_pin_file": claim_pin_file(),
                "claim_route": CLAIM_ROUTE,
                "upgrade_claim_routes": list(UPGRADE_CLAIM_ROUTES),
            },
        )
    except Exception as e:
        logger.error(f"Setup completion failed: {e}", exc_info=True)
        if setup.run_without_ai:
            _retract_run_without_ai(config_path)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
