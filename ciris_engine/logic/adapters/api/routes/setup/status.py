"""Setup status endpoint for CIRIS.

This module provides the /status endpoint to check setup status.
"""

from typing import Optional

from fastapi import APIRouter, Response

from ciris_engine.logic.setup.first_run import get_default_config_path, is_first_run
from ciris_engine.schemas.api.responses import SuccessResponse

from .models import SetupStatusResponse

router = APIRouter()

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
async def get_setup_status(response: Response) -> SuccessResponse[SetupStatusResponse]:
    """Check setup status.

    Returns information about whether setup is required.
    This endpoint is always accessible without authentication.

    When running with ingress auth (e.g., HA Supervisor), the user creation
    step should be skipped since authentication is handled externally.

    Includes Cache-Control header to reduce excessive client polling.
    """
    first_run = is_first_run()
    config_path = get_default_config_path()
    config_exists = config_path.exists()

    # Check if ingress auth is available
    skip_user_step, auth_provider = _get_ingress_auth_info()

    status = SetupStatusResponse(
        is_first_run=first_run,
        config_exists=config_exists,
        config_path=str(config_path) if config_exists else None,
        setup_required=first_run,
        skip_user_step=skip_user_step,
        auth_provider=auth_provider,
    )

    # Add cache header to reduce polling frequency
    response.headers["Cache-Control"] = f"private, max-age={STATUS_CACHE_SECONDS}"

    return SuccessResponse(data=status)
