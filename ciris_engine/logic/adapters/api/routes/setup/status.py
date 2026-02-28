"""Setup status endpoint for CIRIS.

This module provides the /status endpoint to check setup status.
"""

from fastapi import APIRouter

from ciris_engine.logic.setup.first_run import get_default_config_path, is_first_run
from ciris_engine.schemas.api.responses import SuccessResponse

from .models import SetupStatusResponse

router = APIRouter()


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
