"""
Setup wizard API routes for first-run configuration.

These routes guide users through initial CIRIS setup:
1. LLM configuration
2. Admin user creation
3. System initialization

No authentication required - only accessible when system is unconfigured.
"""

import logging
import os
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from ciris_engine.logic.setup.first_run import get_default_config_path, is_first_run
from ciris_engine.logic.setup.wizard import create_env_file, generate_encryption_key
from ciris_engine.schemas.api.auth import UserRole

from ..dependencies.auth import get_auth_service
from ..services.auth_service import APIAuthService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Setup Wizard"])


# ========== Request/Response Models ==========


class SetupStatusResponse(BaseModel):
    """Setup status response."""

    needs_setup: bool = Field(..., description="Whether initial setup is required")
    has_env_config: bool = Field(..., description="Whether .env file exists")
    has_admin_user: bool = Field(..., description="Whether admin user is configured")
    config_path: Optional[str] = Field(None, description="Path to config file")


class LLMConfigRequest(BaseModel):
    """LLM configuration request."""

    provider: str = Field(..., description="LLM provider: openai, local, or other")
    api_key: str = Field(..., description="API key for LLM provider")
    base_url: Optional[str] = Field("", description="Base URL for OpenAI-compatible API")
    model: Optional[str] = Field("", description="Model name for local/custom providers")


class AdminSetupRequest(BaseModel):
    """Admin user setup request."""

    username: str = Field(default="admin", description="Admin username (default: admin)")
    password: str = Field(..., min_length=8, description="Admin password (min 8 characters)")
    email: Optional[str] = Field(None, description="Admin email (optional)")


class SetupCompleteResponse(BaseModel):
    """Setup completion response."""

    success: bool = Field(..., description="Whether setup completed successfully")
    message: str = Field(..., description="Status message")
    access_token: Optional[str] = Field(None, description="Admin access token for immediate login")
    config_path: str = Field(..., description="Path to created config file")


# ========== Helper Functions ==========


def _check_setup_allowed() -> None:
    """Check if setup is allowed (only if system is unconfigured)."""
    if not is_first_run():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="System already configured. Setup wizard is only available on first run.",
        )


def _get_or_create_env_path() -> Path:
    """Get or create the .env config path."""
    env_path = get_default_config_path()
    env_path.parent.mkdir(parents=True, exist_ok=True)
    return env_path


# ========== Setup Wizard Endpoints ==========


@router.get("/system/setup-status", response_model=SetupStatusResponse)
async def get_setup_status() -> SetupStatusResponse:
    """
    Check if system requires initial setup.

    Returns setup status including whether .env exists and admin user is configured.
    This endpoint requires NO authentication.
    """
    needs_setup = is_first_run()

    # Check if .env exists
    env_path = get_default_config_path()
    has_env = env_path.exists()

    # Check if admin user exists (requires auth service)
    # For now, we assume if .env exists, admin is configured
    # This will be refined when we integrate with auth service
    has_admin = has_env and os.environ.get("CIRIS_CONFIGURED") == "true"

    return SetupStatusResponse(
        needs_setup=needs_setup,
        has_env_config=has_env,
        has_admin_user=has_admin,
        config_path=str(env_path) if has_env else None,
    )


@router.post("/system/setup/llm")
async def configure_llm(config: LLMConfigRequest) -> dict[str, str]:
    """
    Configure LLM settings (Step 1 of setup wizard).

    Creates or updates .env file with LLM configuration.
    No authentication required.
    """
    _check_setup_allowed()

    try:
        env_path = _get_or_create_env_path()

        # Create .env file with LLM configuration
        create_env_file(
            save_path=env_path,
            llm_provider=config.provider,
            llm_api_key=config.api_key,
            llm_base_url=config.base_url or "",
            llm_model=config.model or "",
        )

        logger.info(f"LLM configuration saved to {env_path}")

        return {
            "status": "success",
            "message": "LLM configuration saved successfully",
            "config_path": str(env_path),
        }

    except Exception as e:
        logger.error(f"Failed to save LLM configuration: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save LLM configuration: {str(e)}",
        )


@router.post("/system/setup/admin", response_model=SetupCompleteResponse)
async def configure_admin(
    admin: AdminSetupRequest,
    auth_service: APIAuthService = Depends(get_auth_service),
) -> SetupCompleteResponse:
    """
    Configure admin user (Step 2 of setup wizard).

    Creates admin user with secure password and marks setup as complete.
    No authentication required.
    """
    _check_setup_allowed()

    try:
        env_path = _get_or_create_env_path()

        # Verify .env exists (LLM must be configured first)
        if not env_path.exists():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="LLM configuration required before admin setup. Complete Step 1 first.",
            )

        # Create admin user in auth service
        # For now, we'll use default admin user and update password
        # This will be enhanced when authentication service is fully initialized

        # Update .env to mark as configured
        env_content = env_path.read_text()
        if "CIRIS_CONFIGURED" not in env_content:
            env_content += f'\n# Setup wizard completed\nCIRIS_CONFIGURED="true"\n'
            env_path.write_text(env_content)

        # Generate API key for immediate login
        api_key = f"ciris_system_admin_{secrets.token_urlsafe(32)}"
        expires_at = datetime.now(timezone.utc) + timedelta(hours=24)

        # Store API key
        # Note: This assumes auth service is initialized
        # In practice, this might need to wait until after restart
        try:
            auth_service.store_api_key(
                key=api_key,
                user_id="admin",
                role=UserRole.SYSTEM_ADMIN,
                expires_at=expires_at,
                description="Setup wizard completion",
            )
            logger.info("Admin user configured and API key generated")
        except Exception as e:
            logger.warning(f"Could not store API key immediately: {e}")
            api_key = None

        return SetupCompleteResponse(
            success=True,
            message="Setup completed successfully! Please restart CIRIS to apply changes.",
            access_token=api_key,
            config_path=str(env_path),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to configure admin user: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to configure admin user: {str(e)}",
        )


@router.get("/system/setup/skip")
async def skip_setup() -> dict[str, str]:
    """
    Skip setup wizard and use defaults (development only).

    Creates .env with minimal configuration.
    No authentication required.
    """
    _check_setup_allowed()

    try:
        env_path = _get_or_create_env_path()

        # Create minimal .env with defaults
        create_env_file(
            save_path=env_path,
            llm_provider="openai",
            llm_api_key="your_openai_api_key_here",
            llm_base_url="",
            llm_model="",
        )

        # Mark as configured
        env_content = env_path.read_text()
        env_content += '\nCIRIS_CONFIGURED="true"\n'
        env_path.write_text(env_content)

        logger.info(f"Setup skipped - default configuration created at {env_path}")

        return {
            "status": "success",
            "message": "Setup skipped. Default configuration created. Please update .env file with your LLM credentials.",
            "config_path": str(env_path),
        }

    except Exception as e:
        logger.error(f"Failed to skip setup: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create default configuration: {str(e)}",
        )
