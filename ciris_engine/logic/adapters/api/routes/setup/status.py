"""Setup status endpoint for CIRIS.

This module provides the /status endpoint to check setup status.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Request, Response

from ciris_engine.logic.setup.first_run import get_default_config_path, is_first_run
from ciris_engine.schemas.api.responses import SuccessResponse

from .dependencies import is_setup_required
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


@router.get("/status")
async def get_setup_status(request: Request, response: Response) -> SuccessResponse[SetupStatusResponse]:
    """Check setup status.

    Returns information about whether setup is required.
    This endpoint is always accessible without authentication.

    When running with ingress auth (e.g., HA Supervisor), the user creation
    step should be skipped since authentication is handled externally.

    Includes Cache-Control header to reduce excessive client polling.

    Setup-required resolution lives in `is_setup_required()` so the gate
    on the wizard endpoints (require_setup_mode) and the signpost from
    this status response stay in lock-step. If they disagree, the client
    navigates to a wizard that 403s every endpoint and the user is stuck —
    the original #794 failure mode in a different shape.
    """
    first_run = is_first_run()
    config_path = get_default_config_path()
    config_exists = config_path.exists()

    setup_required = await is_setup_required(request)
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
