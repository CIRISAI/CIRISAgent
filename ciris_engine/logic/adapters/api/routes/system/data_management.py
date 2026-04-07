"""
Data management endpoints.

Provides admin-protected data management operations:
- Reset account (preserves signing key for wallet access)
- Wipe signing key (DANGER: destroys wallet access permanently)

These operations are gated behind admin authentication to prevent unauthorized
data destruction, even on local devices.
"""

import logging
import os
import shutil
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from ciris_engine.schemas.api.auth import AuthContext
from ciris_engine.schemas.api.responses import SuccessResponse
from ciris_engine.schemas.audit.core import EventPayload

from ...dependencies.auth import require_admin

logger = logging.getLogger(__name__)

# Annotated type alias for FastAPI dependency injection
AuthAdminDep = Annotated[AuthContext, Depends(require_admin)]

router = APIRouter(prefix="/data", tags=["data-management"])


# ============ Schemas ============


class ResetAccountRequest(BaseModel):
    """Request to reset account data while preserving signing key."""

    confirm: bool = Field(
        ...,
        description="Must be true to confirm the reset operation",
    )
    reason: str = Field(
        default="User requested reset",
        max_length=500,
        description="Reason for reset (for audit logging)",
    )


class ResetAccountResponse(BaseModel):
    """Response from reset account operation."""

    success: bool = Field(..., description="Whether the reset succeeded")
    message: str = Field(..., description="Human-readable status message")
    signing_key_preserved: bool = Field(
        default=True,
        description="Whether the signing key was preserved (wallet access maintained)",
    )
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="When the reset was performed",
    )


class WipeSigningKeyRequest(BaseModel):
    """Request to wipe the signing key (DANGER: destroys wallet access)."""

    confirm: bool = Field(
        ...,
        description="Must be true to confirm - THIS IS IRREVERSIBLE",
    )
    confirm_wallet_loss: bool = Field(
        ...,
        description="Must be true to confirm understanding that wallet funds will be LOST FOREVER",
    )
    reason: str = Field(
        default="User requested complete identity wipe",
        max_length=500,
        description="Reason for wipe (for audit logging)",
    )


class WipeSigningKeyResponse(BaseModel):
    """Response from wipe signing key operation."""

    success: bool = Field(..., description="Whether the wipe succeeded")
    message: str = Field(..., description="Human-readable status message")
    wallet_access_destroyed: bool = Field(
        default=True,
        description="Whether wallet access was destroyed (PERMANENT)",
    )
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="When the wipe was performed",
    )


# ============ Helper Functions ============


def _get_data_directory() -> str:
    """Get the data directory path."""
    # Check for CIRIS_DATA_DIR environment variable first
    data_dir = os.environ.get("CIRIS_DATA_DIR")
    if data_dir:
        return data_dir

    # Default to ./data relative to working directory
    return os.path.join(os.getcwd(), "data")


def _get_env_file_path() -> str:
    """Get the .env file path."""
    return os.path.join(os.getcwd(), ".env")


def _clear_data_directory(preserve_signing_key: bool = True) -> None:
    """Clear the data directory.

    Args:
        preserve_signing_key: If True, preserve signing key files
    """
    data_dir = _get_data_directory()
    if not os.path.exists(data_dir):
        logger.info(f"Data directory does not exist: {data_dir}")
        return

    # Files to preserve during soft reset (signing key files)
    preserve_patterns = {"signing_key", "agent_key", ".key"} if preserve_signing_key else set()

    for item in os.listdir(data_dir):
        item_path = os.path.join(data_dir, item)

        # Check if should preserve
        should_preserve = any(pattern in item.lower() for pattern in preserve_patterns)
        if should_preserve:
            logger.info(f"Preserving: {item}")
            continue

        try:
            if os.path.isfile(item_path):
                os.remove(item_path)
                logger.info(f"Deleted file: {item}")
            elif os.path.isdir(item_path):
                shutil.rmtree(item_path)
                logger.info(f"Deleted directory: {item}")
        except Exception as e:
            logger.error(f"Failed to delete {item}: {e}")
            raise


def _delete_env_file() -> None:
    """Delete the .env file to trigger setup wizard."""
    env_path = _get_env_file_path()
    if os.path.exists(env_path):
        os.remove(env_path)
        logger.info(f"Deleted .env file: {env_path}")
    else:
        logger.info(f".env file does not exist: {env_path}")


# ============ Endpoints ============


@router.post(
    "/reset-account",
    responses={
        400: {"description": "Invalid request (confirmation required)"},
        500: {"description": "Reset failed"},
    },
)
async def reset_account(
    body: ResetAccountRequest,
    request: Request,
    auth: AuthAdminDep,
) -> SuccessResponse[ResetAccountResponse]:
    """
    Reset account data while PRESERVING signing key.

    This operation:
    - Deletes databases, logs, and cached data
    - Deletes .env configuration (triggers setup wizard)
    - PRESERVES the signing key (wallet access maintained)

    Requires ADMIN role.

    After this operation, the app will restart into the setup wizard,
    but the user's wallet address remains accessible.
    """
    if not body.confirm:
        raise HTTPException(
            status_code=400,
            detail="Confirmation required: set confirm=true to proceed with reset",
        )

    logger.warning(
        f"RESET ACCOUNT requested by user={auth.user_id} role={auth.role.value}: {body.reason}"
    )

    try:
        # Audit the operation
        audit_service = getattr(request.app.state, "audit_service", None)
        if audit_service:
            await audit_service.log_event(
                event_type="data_management.reset_account",
                event_data=EventPayload(
                    action="reset_account",
                    user_id=auth.user_id,
                    result=f"role={auth.role.value}, reason={body.reason}, signing_key_preserved=True",
                    service_name="data_management",
                ),
            )

        # Clear data directory (preserving signing key)
        logger.info("Clearing data directory (preserving signing key)...")
        _clear_data_directory(preserve_signing_key=True)

        # Delete .env to trigger setup wizard
        logger.info("Deleting .env file...")
        _delete_env_file()

        logger.info("Reset account completed successfully")

        return SuccessResponse(
            data=ResetAccountResponse(
                success=True,
                message="Account reset successfully. Signing key preserved for wallet access. App will restart into setup wizard.",
                signing_key_preserved=True,
            )
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to reset account: {e}")
        raise HTTPException(status_code=500, detail=f"Reset failed: {e}")


@router.post(
    "/wipe-signing-key",
    responses={
        400: {"description": "Invalid request (confirmations required)"},
        500: {"description": "Wipe failed"},
    },
)
async def wipe_signing_key(
    body: WipeSigningKeyRequest,
    request: Request,
    auth: AuthAdminDep,
) -> SuccessResponse[WipeSigningKeyResponse]:
    """
    DANGER: Wipe signing key and ALL data.

    WARNING: THIS ACTION IS IRREVERSIBLE!

    This operation:
    - DESTROYS the signing key (wallet access PERMANENTLY LOST)
    - Deletes ALL data (databases, logs, cache)
    - Deletes .env configuration

    Any funds in the wallet will be LOST FOREVER.

    Requires ADMIN role AND explicit confirmation of wallet loss.

    Only use this if:
    - User has verified wallet balance is zero
    - User wants a completely fresh agent identity
    """
    if not body.confirm:
        raise HTTPException(
            status_code=400,
            detail="Confirmation required: set confirm=true to proceed",
        )

    if not body.confirm_wallet_loss:
        raise HTTPException(
            status_code=400,
            detail="DANGER: You must set confirm_wallet_loss=true to acknowledge that ANY FUNDS IN YOUR WALLET WILL BE LOST FOREVER",
        )

    logger.warning(
        f"WIPE SIGNING KEY requested by user={auth.user_id} role={auth.role.value}: {body.reason}"
    )
    logger.warning("THIS WILL PERMANENTLY DESTROY WALLET ACCESS!")

    try:
        # Audit the operation with CRITICAL severity
        audit_service = getattr(request.app.state, "audit_service", None)
        if audit_service:
            await audit_service.log_event(
                event_type="data_management.wipe_signing_key",
                event_data=EventPayload(
                    action="wipe_signing_key",
                    user_id=auth.user_id,
                    result=f"role={auth.role.value}, reason={body.reason}, IRREVERSIBLE - wallet funds lost forever",
                    service_name="data_management",
                ),
            )

        # Clear ALL data including signing key
        logger.warning("Clearing ALL data INCLUDING signing key...")
        _clear_data_directory(preserve_signing_key=False)

        # Delete .env
        logger.info("Deleting .env file...")
        _delete_env_file()

        logger.warning("Signing key DESTROYED - wallet access permanently lost")

        return SuccessResponse(
            data=WipeSigningKeyResponse(
                success=True,
                message="Signing key and all data wiped. Wallet access PERMANENTLY DESTROYED. App will restart into setup wizard with fresh identity.",
                wallet_access_destroyed=True,
            )
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to wipe signing key: {e}")
        raise HTTPException(status_code=500, detail=f"Wipe failed: {e}")
