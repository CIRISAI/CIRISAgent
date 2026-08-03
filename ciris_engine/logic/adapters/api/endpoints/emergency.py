"""
Emergency API endpoints.

Provides WA-authorized emergency control endpoints including kill switch.
"""

import logging
from typing import Annotated, Any, Dict

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


# Type alias for runtime service dependency (S8410 compliance)
RuntimeServiceDep = Annotated[RuntimeControlServiceProtocol, Depends(get_runtime_service)]


@router.post(
    "/shutdown",
    responses={
        403: {"description": "Command verification failed"},
        500: {"description": "Emergency shutdown failed"},
    },
)
async def emergency_shutdown(
    command: WASignedCommand,
    runtime_service: RuntimeServiceDep,
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

    except HTTPException:
        # Re-raise HTTP exceptions as-is (don't convert to 500)
        raise
    except Exception as e:
        logger.error(f"Emergency shutdown failed: {e}")
        raise HTTPException(status_code=500, detail=f"Emergency shutdown failed: {str(e)}")


@router.get("/kill-switch/status")
async def get_kill_switch_status(
    runtime_service: RuntimeServiceDep,
) -> JSONDict:
    """
    Get current kill switch configuration status.

    Returns:
        Current kill switch configuration (without sensitive keys)
    """
    # #998 — report the REAL authority source, not a hardcoded default.
    #
    # This used to read `enabled` off a KillSwitchConfig constructed with
    # `enabled=True` in the service's __init__ and never updated, alongside a
    # `root_wa_count` taken from a list nothing populated. So it answered
    # "enabled: true, root_wa_count: 0" while every signed shutdown command was
    # being rejected. A status surface that cannot report its own failure is
    # worse than no status surface.
    #
    # Authorities now come from the accord verifier — the same trust root the
    # stego kill switch verifies against.
    from ciris_engine.logic.accord.verifier import AccordVerifier

    verifier = AccordVerifier()
    authorities = verifier.list_authorities()

    status: JSONDict = {
        # Enabled means AUTHORITIES ARE LOADED, not "a flag was set to True".
        "enabled": bool(authorities),
        "root_wa_count": len(authorities),
        "authorities": [a["wa_id"] for a in authorities],
        "trust_root": "accord-verifier",
        "signature_scheme": "ed25519",
        # LEGACY marker on the wire, not only in the source. TODO(#998):
        # trust-root-backed PQC STEGO once designed and shipped.
        "legacy": True,
        # Redundant by design: the substrate carries its own kill switch that
        # halts the node itself. Stopping the agent and stopping the node are
        # independent paths; either alone suffices.
        "redundant_substrate_killswitch": True,
    }

    if hasattr(runtime_service, "_kill_switch_config"):
        config = runtime_service._kill_switch_config
        status.update(
            {
                "trust_tree_depth": config.trust_tree_depth,
                "allow_relay": config.allow_relay,
                "max_shutdown_time_ms": config.max_shutdown_time_ms,
                "command_expiry_seconds": config.command_expiry_seconds,
            }
        )

    return status
