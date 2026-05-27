"""Setup status endpoint for CIRIS.

This module provides the /status endpoint to check setup status.
"""

import logging
from typing import Any, Optional

from fastapi import APIRouter, Request, Response

from ciris_engine.logic.setup.first_run import get_default_config_path, is_first_run
from ciris_engine.schemas.api.responses import SuccessResponse

from .models import SetupStatusResponse

router = APIRouter()

logger = logging.getLogger(__name__)

# Cache duration for status endpoint (reduces polling frequency)
STATUS_CACHE_SECONDS = 5


def _get_ingress_auth_info() -> tuple[bool, Optional[str]]:
    """Check if ingress auth is available and should skip user step.

    Returns:
        Tuple of (skip_user_step, auth_provider_name)
    """
    try:
        from ciris_engine.logic.adapters.api.dependencies.auth import (
            get_active_ingress_provider_names,
            should_skip_setup_wizard_user_step,
        )

        skip = should_skip_setup_wizard_user_step()
        providers = get_active_ingress_provider_names()
        provider_name = providers[0] if providers else None
        return (skip, provider_name)
    except ImportError:
        return (False, None)


def _has_system_admin_user(request: Request) -> Optional[bool]:
    """Return True if at least one SYSTEM_ADMIN user exists, False if not,
    None if we can't tell (auth service unavailable yet).

    The None case is important: returning False would force setup_required
    forever during early boot before auth is wired. None means "skip the
    check, fall back to is_first_run behavior".

    #794 root cause: setup_required was derived solely from is_first_run
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
        logger.debug("[SETUP_STATUS] SYSTEM_ADMIN probe failed: %s", e)
        return None


@router.get("/status")
async def get_setup_status(request: Request, response: Response) -> SuccessResponse[SetupStatusResponse]:
    """Check setup status.

    Returns information about whether setup is required.
    This endpoint is always accessible without authentication.

    When running with ingress auth (e.g., HA Supervisor), the user creation
    step should be skipped since authentication is handled externally.

    Includes Cache-Control header to reduce excessive client polling.

    Setup-required resolution:
      1. If `is_first_run()` (no .env or CIRIS_CONFIGURED != true) → required.
      2. ELSE if auth_service is wired AND no SYSTEM_ADMIN user exists →
         required. This catches the "bugged install" state where a
         previously-aborted setup left config present but no admin
         (#794). Without this check the client lands in an
         unrecoverable observer-block loop on OAuth sign-in.
      3. ELSE → not required (healthy post-setup install).
    """
    first_run = is_first_run()
    config_path = get_default_config_path()
    config_exists = config_path.exists()

    # Bugged-install self-heal: even when .env says we're configured,
    # if no SYSTEM_ADMIN exists the device cannot accept logins. Route
    # the user back through the setup wizard so they can re-establish
    # ownership.
    has_admin = _has_system_admin_user(request)
    setup_required = first_run or (has_admin is False and config_exists)
    if setup_required and not first_run:
        logger.warning(
            "[SETUP_STATUS] config_exists=True but no SYSTEM_ADMIN user "
            "present — flagging setup_required=True to recover bugged "
            "install (see CIRISAgent#794)"
        )

    # Check if ingress auth is available
    skip_user_step, auth_provider = _get_ingress_auth_info()

    status = SetupStatusResponse(
        is_first_run=first_run,
        config_exists=config_exists,
        config_path=str(config_path) if config_exists else None,
        setup_required=setup_required,
        skip_user_step=skip_user_step,
        auth_provider=auth_provider,
    )

    # Add cache header to reduce polling frequency
    response.headers["Cache-Control"] = f"private, max-age={STATUS_CACHE_SECONDS}"

    return SuccessResponse(data=status)
