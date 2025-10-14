"""
Emergency API endpoints.

Provides WA-authorized emergency control endpoints including kill switch.
"""

import logging
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException

from ciris_engine.protocols.services import RuntimeControlService as RuntimeControlServiceProtocol
from ciris_engine.schemas.services.shutdown import EmergencyShutdownStatus, WASignedCommand
from ciris_engine.schemas.types import JSONDict

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/emergency", tags=["emergency"])


def get_runtime_service() -> RuntimeControlServiceProtocol:
    """Get runtime control service dependency."""
    # This will be injected by the API adapter
    # For now, return None - the actual service should be injected
    return None  # type: ignore


@router.post("/shutdown", response_model=EmergencyShutdownStatus)
async def emergency_shutdown(
    command: WASignedCommand, runtime_service: RuntimeControlServiceProtocol = Depends(get_runtime_service)
) -> EmergencyShutdownStatus:
    """
    Execute WA-authorized emergency shutdown.

    This endpoint accepts a signed SHUTDOWN_NOW command from a Wise Authority
    and initiates immediate graceful shutdown, bypassing normal procedures.

    The command must be signed by a ROOT WA authority or a WA in the trust tree.

    Args:
        command: Signed emergency shutdown command

    Returns:
        Status of the emergency shutdown process

    Raises:
        HTTPException: If command verification fails
    """
    logger.critical(f"Emergency shutdown endpoint called by WA {command.wa_id}")

    try:
        # Handle the emergency command
        status = await runtime_service.handle_emergency_shutdown(command)

        if not status.command_verified:
            raise HTTPException(status_code=403, detail=f"Command verification failed: {status.verification_error}")

        return status

    except Exception as e:
        logger.error(f"Emergency shutdown failed: {e}")
        raise HTTPException(status_code=500, detail=f"Emergency shutdown failed: {str(e)}")


@router.get("/kill-switch/status")
async def get_kill_switch_status(
    runtime_service: RuntimeControlServiceProtocol = Depends(get_runtime_service),
) -> JSONDict:
    """
    Get current kill switch configuration status.

    Returns:
        Current kill switch configuration (without sensitive keys)
    """
    if hasattr(runtime_service, "_kill_switch_config"):
        config = runtime_service._kill_switch_config
        return {
            "enabled": config.enabled,
            "root_wa_count": len(config.root_wa_public_keys),  # ROOT WA authorities
            "trust_tree_depth": config.trust_tree_depth,
            "allow_relay": config.allow_relay,
            "max_shutdown_time_ms": config.max_shutdown_time_ms,
            "command_expiry_seconds": config.command_expiry_seconds,
        }

    return {"enabled": False, "error": "Kill switch not configured"}
