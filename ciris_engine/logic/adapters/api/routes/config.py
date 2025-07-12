"""
Config service endpoints for CIRIS API v1.

Simplified configuration management with role-based filtering.
"""
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone
from fastapi import APIRouter, Request, HTTPException, Depends, Path
from pydantic import BaseModel, Field, field_serializer

from ciris_engine.schemas.api.responses import SuccessResponse
from ciris_engine.schemas.api.config_security import ConfigSecurity
from ciris_engine.schemas.api.auth import UserRole
from ..dependencies.auth import require_observer, require_admin, AuthContext, get_auth_context

router = APIRouter(prefix="/config", tags=["config"])

# Request/Response schemas

class ConfigItemResponse(BaseModel):
    """Configuration item in API response."""
    key: str = Field(..., description="Configuration key")
    value: Any = Field(..., description="Configuration value (may be redacted)")
    updated_at: datetime = Field(..., description="Last update time")
    updated_by: str = Field(..., description="Who updated this config")
    is_sensitive: bool = Field(False, description="Whether value contains sensitive data")

    @field_serializer('updated_at')
    def serialize_updated_at(self, updated_at: datetime, _info) -> Optional[str]:
        return updated_at.isoformat() if updated_at else None

class ConfigListResponse(BaseModel):
    """List of configuration values."""
    configs: List[ConfigItemResponse] = Field(..., description="Configuration entries")
    total: int = Field(..., description="Total count")

class ConfigUpdate(BaseModel):
    """Configuration update request."""
    value: Any = Field(..., description="New configuration value")
    reason: Optional[str] = Field(None, description="Reason for change")

# Endpoints

@router.get("", response_model=SuccessResponse[ConfigListResponse])
async def list_configs(
    request: Request,
    prefix: Optional[str] = None,
    auth: AuthContext = Depends(require_observer)
) -> SuccessResponse[ConfigListResponse]:
    """
    List all configurations.

    Get all configuration values, with sensitive values filtered based on role.
    """
    config_service = getattr(request.app.state, 'config_service', None)
    if not config_service:
        raise HTTPException(status_code=503, detail="Config service not available")

    try:
        # Get all configs
        all_configs = {}
        if hasattr(config_service, 'list_configs'):
            all_configs = await config_service.list_configs(prefix=prefix)

        # Filter based on prefix if provided
        if prefix:
            all_configs = {k: v for k, v in all_configs.items() if k.startswith(prefix)}

        # Convert to list format with role filtering
        config_list = []
        for key, value in all_configs.items():
            # Apply role-based filtering
            is_sensitive = ConfigSecurity.is_sensitive(key)
            filtered_value = ConfigSecurity.filter_value(key, value, auth.role)

            config_list.append(ConfigItemResponse(
                key=key,
                value=filtered_value,
                updated_at=datetime.now(timezone.utc),  # Would get from graph
                updated_by="system",  # Would get from graph
                is_sensitive=is_sensitive
            ))

        result = ConfigListResponse(
            configs=config_list,
            total=len(config_list)
        )

        return SuccessResponse(data=result)

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{key:path}", response_model=SuccessResponse[ConfigItemResponse])
async def get_config(
    request: Request,
    key: str = Path(..., description="Configuration key"),
    auth: AuthContext = Depends(require_observer)
) -> SuccessResponse[ConfigItemResponse]:
    """
    Get specific config.

    Get a specific configuration value.
    """
    config_service = getattr(request.app.state, 'config_service', None)
    if not config_service:
        raise HTTPException(status_code=503, detail="Config service not available")

    try:
        # Get config node
        config_node = await config_service.get_config(key)

        if config_node is None:
            raise HTTPException(status_code=404, detail=f"Configuration key '{key}' not found")

        # Extract the actual value from the ConfigNode
        actual_value = config_node.value

        # Apply role-based filtering
        is_sensitive = ConfigSecurity.is_sensitive(key)
        filtered_value = ConfigSecurity.filter_value(key, actual_value, auth.role)

        config = ConfigItemResponse(
            key=key,
            value=filtered_value,
            updated_at=config_node.updated_at,
            updated_by=config_node.updated_by,
            is_sensitive=is_sensitive
        )

        return SuccessResponse(data=config)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/{key:path}", response_model=SuccessResponse[ConfigItemResponse])
async def update_config(
    request: Request,
    body: ConfigUpdate,
    key: str = Path(..., description="Configuration key"),
    auth: AuthContext = Depends(get_auth_context)
) -> SuccessResponse[ConfigItemResponse]:
    """
    Update config.

    Update a configuration value. Requires ADMIN role, or SYSTEM_ADMIN for sensitive configs.
    """
    config_service = getattr(request.app.state, 'config_service', None)
    if not config_service:
        raise HTTPException(status_code=503, detail="Config service not available")

    # Check permissions
    is_sensitive = ConfigSecurity.is_sensitive(key)
    if is_sensitive and auth.role != UserRole.SYSTEM_ADMIN:
        raise HTTPException(
            status_code=403,
            detail=f"Cannot modify sensitive config '{key}' without SYSTEM_ADMIN role"
        )
    elif not is_sensitive and auth.role.level < UserRole.ADMIN.level:
        raise HTTPException(
            status_code=403,
            detail="Insufficient permissions. Requires ADMIN role or higher."
        )

    try:
        # Validate the configuration value
        _errors = []
        _warnings = []

        # Check for system configs
        if key.startswith("system.") and auth.role != UserRole.SYSTEM_ADMIN:
            raise HTTPException(
                status_code=403,
                detail=f"Cannot modify system config '{key}' without SYSTEM_ADMIN role"
            )

        # Update config
        await config_service.set_config(
            key=key,
            value=body.value,
            updated_by=auth.user_id
        )

        # Return updated config (show actual value since user has permission to update)
        config = ConfigItemResponse(
            key=key,
            value=body.value,
            updated_at=datetime.now(timezone.utc),
            updated_by=auth.user_id,
            is_sensitive=is_sensitive
        )

        return SuccessResponse(data=config)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/{key:path}", response_model=SuccessResponse[Dict[str, str]])
async def delete_config(
    request: Request,
    key: str = Path(..., description="Configuration key"),
    auth: AuthContext = Depends(require_admin)
) -> SuccessResponse[Dict[str, str]]:
    """
    Delete config.

    Remove a configuration value. Requires ADMIN role.
    """
    config_service = getattr(request.app.state, 'config_service', None)
    if not config_service:
        raise HTTPException(status_code=503, detail="Config service not available")

    try:
        # Check if it's a sensitive key
        if ConfigSecurity.is_sensitive(key) and auth.role != UserRole.SYSTEM_ADMIN:
            raise HTTPException(
                status_code=403,
                detail=f"Cannot delete sensitive config '{key}' without SYSTEM_ADMIN role"
            )

        # Delete config
        if hasattr(config_service, 'delete_config'):
            await config_service.delete_config(key)
        else:
            # Set to None as deletion
            await config_service.set_config(key, None, updated_by=auth.user_id)

        return SuccessResponse(data={"status": "deleted", "key": key})

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
