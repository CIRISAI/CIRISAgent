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

from ciris_engine.logic.config.db_paths import get_sqlite_db_full_path
from ciris_engine.logic.setup.wizard import create_env_file
from ciris_engine.logic.utils.env_file import env_line
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
            logger.info(f"CIRIS_SETUP_DEBUG [OK] Updated existing WA {existing_wa.wa_id} to ROOT role")
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
        logger.error(f"CIRIS_SETUP_DEBUG [FAIL] FAILED to link OAuth identity: {e}", exc_info=True)
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
        logger.info("[OK] Updated admin password")
    else:
        logger.warning("[WARN] Default admin WA not found")


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

    logger.info(f"CIRIS_USER_CREATE: [OK] Found existing WA for OAuth user: {existing_wa.wa_id}")
    logger.info(f"CIRIS_USER_CREATE:   Current role: {existing_wa.role}")
    logger.info(f"CIRIS_USER_CREATE:   Current name: {existing_wa.name}")

    # Update existing WA to ROOT role instead of creating new one
    logger.info(
        f"CIRIS_USER_CREATE: Updating existing WA {existing_wa.wa_id} to ROOT role (keeping name: {existing_wa.name})"
    )
    await auth_service.update_wa(wa_id=existing_wa.wa_id, role=WARole.ROOT)
    logger.info(f"CIRIS_USER_CREATE: [OK] Updated existing OAuth WA to ROOT: {existing_wa.wa_id}")

    return existing_wa, True


#: Roles a node-claimed owner can hold. Mirrors `setup/dependencies.py`, which
#: needs the same "is there already a human in charge?" answer for the wizard gate.
_OWNER_ROLES = ("root", "authority")


class _AdoptedNodeOwner:
    """The node-claimed owner, carried in the shape the setup flow expects.

    NOT a `WACertificate`, and it cannot be one: `WACertificate.wa_id` is pinned
    to `^wa-\\d{4}-\\d{2}-\\d{2}-[A-Z0-9]{6}$`, and a node-claimed owner's id is
    `wa-root-<fed-id>-<suffix>`. That regex is exactly why `_is_brain_wa_row`
    exists and why this owner is invisible to `list_was()`.

    Deliberately carries NO credential. The right to manage this node and
    responsibility for this agent come from CEG; the node has native auth and
    the server owns the password. This type exists only so the CEG artifacts the
    AGENT still owns — the founding-partnership consent node and the user's
    language/location preferences — can be keyed to the owner's id. Both take a
    plain string, so nothing here needs the brain's certificate schema.
    """

    __slots__ = ("wa_id", "name", "role")

    def __init__(self, wa_id: str, name: str, role: str) -> None:
        self.wa_id = wa_id
        self.name = name
        self.role = role


def _node_owner_named(username: str) -> Optional[_AdoptedNodeOwner]:
    """The node-claimed owner answering to `username`, if one already exists.

    WHY THIS EXISTS. Setup performs the node self-claim FIRST — the saga logs
    it as `E5 claim_accepted role=SYSTEM_ADMIN waId=wa-root-…` — and only then
    runs `completeSetup`. By that point the owner the user asked for already
    exists. But the duplicate check in `_create_new_wa` goes through
    `list_was()`, which ends in `if _is_brain_wa_row(row)` (#922) and therefore
    CANNOT see `wa-root-*`. The brain concludes nobody exists and mints a second
    ROOT certificate under the same name.

    Nothing is corrupt afterwards and nothing raises. The agent reports
    `status=healthy state=work init=True` — and every login attempt gets 409
    from the node:

        2 active certificates answer to the name "qaadmin"
        (wa-2026-08-16-143618, wa-root-qa-node-…) — refusing to choose
        between them.

    That refusal is correct: picking one would silently authenticate the user as
    whichever row the node happened to order first, and only one of them carries
    the password. So the fix belongs here, at the site that creates the
    ambiguity, not at the node that reports it.

    HOW IT GOT HERE (2a26daba0, 2026-07-15, shipped since v2.9.10). The
    claim-then-complete REORDER made the node write its owner row before
    `/v1/setup/complete` read it. `_row_to_wa` then raised on that row and
    `completeSetup` 500'd — loud, and it blocked setup, so nobody ended up with
    a broken install. That commit fixed the crash by filtering `wa-root-*` out
    of the brain's WA world, explicitly to restore "the brain's WA world to
    exactly its pre-node-claim state".

    That is the flaw. Pre-node-claim state means the brain still believes no
    owner exists, so it goes on to mint one. The 500 became a silent duplicate:
    setup now COMPLETES, the agent comes up healthy, and login is impossible
    forever. Seven releases carried it because nothing errors and no unit test
    looks across both identity kinds — keeping them apart is the filter's job.

    This is the fourth call site blinded by that filter, after the setup-wizard
    lockout and the missing founding partnership (both fixed in 2.9.16 the same
    way, by consulting `_list_active_by_role` alongside `list_was()`).
    """
    try:
        from ciris_engine.logic.persistence.stores.authentication_store import (
            _is_brain_wa_row,
            _list_active_by_role,
        )
    except Exception:  # pragma: no cover - store unavailable in some test rigs
        return None

    wanted = (username or "").strip().casefold()
    if not wanted:
        return None

    for role in _OWNER_ROLES:
        try:
            rows = _list_active_by_role(role)
        except Exception as exc:  # noqa: BLE001
            # A failed probe is NOT evidence of absence. Minting on a read error
            # is what creates the lockout, so treat it as "unknown" and let the
            # caller fall through to its normal path rather than asserting the
            # owner is missing.
            logger.warning("CIRIS_USER_CREATE: could not enumerate %s rows (%s)", role, type(exc).__name__)
            continue
        for row in rows or []:
            if _is_brain_wa_row(row):
                continue  # a brain cert is visible to list_was(); not our concern
            if str(row.get("name") or "").strip().casefold() != wanted:
                continue
            return _AdoptedNodeOwner(
                wa_id=str(row.get("wa_id")),
                name=str(row.get("name")),
                role=str(row.get("role") or role),
            )
    return None


async def _create_new_wa(auth_service: Any, setup: SetupCompleteRequest) -> Any:
    """Create a new WA certificate for the setup user, or adopt the node's owner.

    Returns:
        WA certificate for the newly created user, or the already-existing
        node-claimed owner of the same name (see `_node_owner_named`).
    """
    from ciris_engine.schemas.services.authority_core import WARole

    # Ask the substrate before minting. `list_was()` below cannot answer this.
    adopted = _node_owner_named(setup.admin_username)
    if adopted is not None:
        logger.info(
            "CIRIS_USER_CREATE: node-claimed owner %s already answers to this "
            "username — adopting it instead of minting a second ROOT cert "
            "(a same-named rival makes every login 409 at the node)",
            adopted.wa_id,
        )
        return adopted

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
    logger.info(f"CIRIS_USER_CREATE: [OK] Created NEW WA: {wa_cert.wa_id}")

    return wa_cert


async def _set_password_for_wa(auth_service: Any, setup: SetupCompleteRequest, wa_cert: Any) -> None:
    """Set password hash for non-OAuth users the BRAIN owns.

    Never for a node-claimed owner. The node has native auth and the server owns
    the credential — it was already set there, and `E6 owner_login ok` fires in
    the setup saga BEFORE `/v1/setup/complete` runs, which is the proof: the node
    had authenticated that owner before the brain did anything. Writing a second
    password here would make the agent an authority on a credential it does not
    own, and leave two places to rotate it.
    """
    if isinstance(wa_cert, _AdoptedNodeOwner):
        logger.info(
            "CIRIS_USER_CREATE: skipping password for node-claimed owner %s — "
            "the node owns auth for this identity",
            wa_cert.wa_id,
        )
        return

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
        logger.info(f"[OK] System WA ready: {system_wa_id}")
    else:
        logger.warning("[WARN] Could not create system WA - deferral handling may not work")


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
    add_graph_node(node, time_service)
    # FALSE POSITIVE (py/clear-text-logging-sensitive-data). `node_id` is a graph
    # node key -- `consent/{user_id}` -- where user_id is an OAuth external id
    # ("google:12345") or a WA id ("wa-2026-04-01-337AE1"). Both are identifiers
    # that appear throughout the audit trail by design; neither is a credential.
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


async def _create_setup_users(
    setup: SetupCompleteRequest,
    main_db_path: str,
    ingress_user_id: Optional[str] = None,
    ingress_user_name: Optional[str] = None,
    ingress_user_email: Optional[str] = None,
) -> None:
    """Create users immediately during setup completion.

    This is called during setup completion to create users without waiting for restart.
    Creates users directly in the database using authentication store functions.

    IMPORTANT: For OAuth users, we check if they already exist and update to ROOT instead
    of creating a duplicate WA. This prevents multiple ROOT users from being created.

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

    logger.info(f"CIRIS_USER_CREATE: admin_username = {setup.admin_username}")
    logger.info(f"CIRIS_USER_CREATE: oauth_provider = {repr(setup.oauth_provider)}")
    logger.info(f"CIRIS_USER_CREATE: oauth_external_id = {repr(setup.oauth_external_id)}")
    logger.info(f"CIRIS_USER_CREATE: oauth_email = {repr(setup.oauth_email)}")

    # Create temporary authentication service for user creation
    time_service = TimeService()
    await time_service.start()

    auth_service = AuthenticationService(
        db_path=main_db_path, time_service=time_service, key_dir=None  # Use default ~/.ciris/
    )
    await auth_service.start()

    try:
        from ciris_engine.logic.persistence.stores import authentication_store

        # WORKAROUND (#1098 — drop once ciris-server mints OAuth WA ids as proper
        # `wa-…`): the OAuth browser-handoff parks the session as a live wa_cert
        # whose id is the placeholder `oauth-<provider>-<sub>`. Capture it BEFORE
        # we mint+link (linking can repoint the primary oauth index) so we can
        # retire it afterwards and leave exactly one live cert for the identity.
        provisional_oauth_wa_id: Optional[str] = None
        if setup.oauth_provider and setup.oauth_external_id:
            provisional_oauth_wa_id = authentication_store.provisional_oauth_cert_id(
                setup.oauth_provider, setup.oauth_external_id
            )

        # Check if OAuth user already exists and update to ROOT if found
        existing_wa, _ = await _check_existing_oauth_wa(auth_service, setup)

        # DOES THE FABRIC ALREADY HOLD THIS IDENTITY?
        #
        # claim-remote (substrate) binds the provider identity to the owner it
        # mints — `wa-root-<user>` — BEFORE completeSetup runs. That cert cannot
        # be materialized as a WACertificate (its wa_id does not match our minting
        # pattern), so `existing_wa` comes back None for an identity that is very
        # much taken, and the branch below used to mint a SECOND ROOT and link the
        # same provider identity to it.
        #
        # The substrate then correctly refused every later sign-in:
        #   AMBIGUOUS provider identity — multiple live certs claim this account
        #   holders=2 wa_ids=["wa-2026-…", "wa-root-mooreericnyc-…"]
        # Google failed on the ambiguity and local failed because an OAuth user has
        # no password: a closed door on both sides, on a fresh install.
        #
        # We must not author a second claim on an identity the fabric has already
        # bound. Ownership is the fabric's to produce and ours to surface.
        fabric_holder_id: Optional[str] = None
        fabric_provider: str = ""
        fabric_provider_subject: str = ""
        if existing_wa is None and setup.oauth_provider and setup.oauth_external_id:
            fabric_provider = str(setup.oauth_provider)
            fabric_provider_subject = str(setup.oauth_external_id)
            fabric_holder_id = authentication_store.fabric_oauth_holder_id(
                fabric_provider, fabric_provider_subject
            )

        if fabric_holder_id:
            # LOG THE FACT, NOT THE SUBJECT.
            #
            # `oauth_external_id` is the provider's subject identifier — PII, and
            # the substrate redacts it to a tail (`subject=…1383`) for exactly that
            # reason. Reading attributes off `setup` also taints the statement for
            # CodeQL, because SetupCompleteRequest carries system_admin_password:
            # three HIGH "clear-text logging of sensitive information" alerts, all
            # on this one call.
            #
            # The diagnostic value here is "the identity was already bound, and to
            # whom" — the provider and a tail are enough to correlate with the
            # substrate's own line, and the holder id is not sensitive.
            # LOG ONLY THE HOLDER. Binding the provider and subject to locals did
            # NOT clear the CodeQL taint — it propagates through `str()`, so any
            # value derived from `setup` keeps carrying it. Laundering the taint
            # through more locals would only hide the finding rather than answer
            # it.
            #
            # And nothing is actually lost. The substrate already logs the pair,
            # redacted, at the moment it binds them:
            #     oauth sign-in CREATED a local identity provider=google subject=…1383
            # The fact THIS line has to carry is the one the substrate cannot know:
            # that setup declined to mint a second ROOT, and which cert it deferred
            # to. `fabric_holder_id` comes from the store, not from `setup`, and is
            # not sensitive.
            logger.info(
                "CIRIS_USER_CREATE: this provider identity is ALREADY bound by the substrate to %s "
                "(claim-remote owner-binding) — NOT minting a second ROOT. Minting here is what "
                "produced 'AMBIGUOUS provider identity / holders=2' and locked first-run OAuth users out.",
                fabric_holder_id,
            )
            # Annotated because this is now the FIRST binding in the function, so
            # an unannotated str here makes mypy reject the later `= None` on the
            # normal path.
            oauth_user_id: Optional[str] = f"{fabric_provider}:{fabric_provider_subject}"
            # The agent-tier work still applies, keyed on the FABRIC's cert.
            _create_founding_partnership(fabric_holder_id, oauth_user_id)
            _store_user_preferences(fabric_holder_id, setup)
            await _ensure_system_wa(auth_service)
            # THE ADOPTION PATH STILL OWES THE CALLER EVERYTHING ELSE IT PROMISED.
            # An earlier version of this branch returned here, which skipped
            # _update_system_admin_password() below — so a request carrying
            # system_admin_password got a response saying both credentials were
            # configured while the default admin password was silently unchanged.
            # Declining to mint a duplicate ROOT is not a licence to drop the rest
            # of the contract.
            await _update_system_admin_password(auth_service, setup, fabric_holder_id)

            # The provisional placeholder is the substrate's to retire, and it
            # already did (claim-remote logs "retired a duplicate cert"). Nothing
            # of ours to clean up.
            return

        # Create new WA if we didn't find an existing OAuth user
        if existing_wa is None:
            wa_cert = await _create_new_wa(auth_service, setup)
        else:
            wa_cert = existing_wa

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

        # Retire the substrate's provisional OAuth cert so it does not duplicate
        # the WA we just minted+linked (#1098 workaround — drop once ciris-server
        # mints OAuth WA ids correctly). Raw set_active, so the placeholder id is
        # never materialized into a WACertificate.
        if provisional_oauth_wa_id and provisional_oauth_wa_id != wa_cert.wa_id:
            authentication_store.update_wa_certificate(provisional_oauth_wa_id, {"active": False})
            logger.info(
                "CIRIS_USER_CREATE: retired provisional OAuth cert %s (kept minted %s)",
                provisional_oauth_wa_id,
                wa_cert.wa_id,
            )

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
        from ciris_engine.logic.services.governance.consent.trace_sharing import (
            grant_trace_sharing,
        )
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
    else:
        logger.warning(
            "[SETUP] No usable LLM provider (provider=%r, key_set=%s) — writing "
            "CIRIS_SERVICES_DISABLED=true so the next boot degrades instead of aborting",
            setup.llm_provider,
            bool((setup.llm_api_key or "").strip()),
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
    llm_base_url = _get_provider_base_url(setup.llm_provider, setup.llm_base_url) or ""

    # For local providers, use "local" as placeholder API key if none provided
    # mobile_local provider doesn't need an API key - it runs on-device
    llm_api_key = setup.llm_api_key
    if not llm_api_key and setup.llm_provider in ("local", "local_inference", "mobile_local"):
        llm_api_key = "local"

    config_path = create_env_file(
        llm_provider=setup.llm_provider,
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
async def complete_setup(setup: SetupCompleteRequest, request: Request) -> SuccessResponse[Dict[str, str]]:
    """Complete initial setup.

    Saves configuration and creates initial admin user.
    Only accessible during first-run (SetupOnlyDep enforces this).
    After setup, authentication is required for reconfiguration.

    For ingress auth scenarios (HA Supervisor, CIRISMedical), the user completing
    setup gets an auto-minted WA with ROOT role and a founding partnership.
    """
    # Log debug info and determine if OAuth linking will happen
    _log_setup_debug_info(setup)

    # Try to detect ingress user completing setup (for auto-mint)
    ingress_user_id, ingress_user_name, ingress_user_email = await _try_get_ingress_user(request)
    if ingress_user_id:
        # SECURITY: Log provider only, not full external_id
        _ingress_provider = ingress_user_id.split(":")[0] if ":" in ingress_user_id else "unknown"
        logger.info(f"[SETUP] Ingress user detected ({_ingress_provider}) - will auto-mint WA")

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
