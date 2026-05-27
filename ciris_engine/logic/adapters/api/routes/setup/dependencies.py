"""Shared dependencies for CIRIS setup routes.

This module contains FastAPI dependencies used across setup endpoints.
"""

import logging
from typing import Any, Optional

from fastapi import Depends, HTTPException, Request, status

from ciris_engine.logic.setup.first_run import get_default_config_path, is_first_run

logger = logging.getLogger(__name__)


async def has_system_admin_user(request: Request) -> Optional[bool]:
    """Return True if at least one SYSTEM_ADMIN user exists, False if not,
    None if we can't tell (auth service unavailable yet).

    The None case is important: returning False would force the bugged-
    install self-heal forever during early boot before auth is wired.
    None means "skip the check, fall back to is_first_run alone".

    APIAuthService loads users lazily (`_users_loaded` starts False; calls
    to `list_users`/OAuth login trigger `_ensure_users_loaded()`). Setup
    status is polled BEFORE any login, so the in-memory cache can be empty
    even on a healthy install with admins persisted to the DB. We must
    trigger the lazy load here — otherwise a healthy install reads as
    "no admin" and gets bounced into the setup wizard.

    #794 context: setup_required was derived solely from is_first_run
    (which reads `.env` for CIRIS_CONFIGURED=true). On the bugged Samsung
    install a previously-aborted setup left .env claiming configured but
    no SYSTEM_ADMIN user existed. Result: server reported "setup done",
    OAuth sign-in 403'd with `auth_personal_install_observer_blocked`
    on every attempt, and the client had no recovery path.
    """
    try:
        auth_service: Any = getattr(request.app.state, "auth_service", None)
        if auth_service is None:
            return None
        from ciris_engine.schemas.runtime.api import APIRole

        # Force lazy load. Idempotent — `_ensure_users_loaded` short-circuits
        # on the `_users_loaded` flag, so polling this endpoint after the
        # first load is a no-op cache check (no DB hit).
        ensure_loaded = getattr(auth_service, "_ensure_users_loaded", None)
        if ensure_loaded is not None:
            await ensure_loaded()
        else:
            # Unknown auth service shape — can't safely assert admin absence.
            return None

        users = getattr(auth_service, "_users", None)
        if users is None:
            return None
        # Dedupe by wa_id — _users aliases the same user under multiple
        # keys (wa_id, oauth primary key, oauth link key). Without
        # dedupe a single legitimate SYSTEM_ADMIN can read as several.
        seen: set[str] = set()
        for user in users.values():
            wa_id = getattr(user, "wa_id", None)
            if not wa_id or wa_id in seen:
                continue
            seen.add(wa_id)
            if getattr(user, "api_role", None) == APIRole.SYSTEM_ADMIN:
                return True
        return False
    except Exception as e:  # pragma: no cover — defensive
        logger.debug("[SETUP] SYSTEM_ADMIN probe failed: %s", e)
        return None


async def is_setup_required(request: Request) -> bool:
    """Single source of truth for "should this device run the setup wizard?"

    Used by BOTH /setup/status (to tell the client to navigate to the
    wizard) and require_setup_mode (to gate the wizard endpoints
    themselves). If these two answers disagree, the client navigates
    to a wizard that 403s every endpoint and the user is stuck.

    True when:
      1. is_first_run() — no .env or CIRIS_CONFIGURED != true; the obvious
         setup-needed case.
      2. config_exists AND no SYSTEM_ADMIN user — the #794 bugged-install
         state where .env says we're done but the founding admin was lost
         (incomplete prior setup, DB migration that dropped the user, etc.).

    Returns False on the ambiguous "can't tell" case (auth service not
    wired yet) so we never gate setup-mode endpoints on a probe that
    couldn't run. The status endpoint applies the same conservative bias.
    """
    if is_first_run():
        return True

    # Beyond first-run: the only other path to setup-required is the
    # bugged-install self-heal (config_exists + no admin). If either
    # half of that conjunction can't be confirmed, defer to is_first_run.
    config_path = get_default_config_path()
    if not config_path.exists():
        return False

    has_admin = await has_system_admin_user(request)
    return has_admin is False


async def require_setup_mode(request: Request) -> None:
    """Dependency that ensures setup routes are only accessible during
    setup — either first-run OR the #794 bugged-install recovery flow.

    Pre-#794 (2.9.2 and earlier) this was gated on is_first_run() alone,
    which meant the bugged-install state had nowhere to go: setup-status
    correctly reported `setup_required=True` (after the #794 server fix)
    but the wizard endpoints it directed the client to all 403'd because
    .env still said `CIRIS_CONFIGURED=true`. The client landed on Setup
    and immediately bounced back with no progress.

    Now: open the same self-heal door at the gate as at the signpost.

    Raises:
        HTTPException: 403 if setup is not required (healthy post-setup
                       install, no recovery needed).
    """
    if not await is_setup_required(request):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Setup routes are only available during first-run setup "
            "or bugged-install recovery. "
            "Use /v1/auth/attestation for attestation status after setup.",
        )


# Type alias for the dependency
SetupOnlyDep = Depends(require_setup_mode)
