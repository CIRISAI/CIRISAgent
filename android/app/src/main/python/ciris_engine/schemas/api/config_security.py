"""
Configuration security and filtering for CIRIS API v2.0.

Automatically detects and filters sensitive configuration values
based on user role to prevent information leakage.
"""

import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field, field_serializer

from ciris_engine.schemas.types import ConfigDict, ConfigValue

from .auth import UserRole


class ConfigSecurity:
    """Configuration security and filtering rules."""

    # Patterns for sensitive keys (case-insensitive)
    SENSITIVE_PATTERNS = [
        re.compile(r".*_(key|secret|token|password|auth|credential)$", re.IGNORECASE),
        re.compile(r"^(api|oauth|jwt|encryption|private)_.*", re.IGNORECASE),
        re.compile(r".*(credential|certificate|private|password).*", re.IGNORECASE),
        re.compile(r"^(aws|azure|gcp|github|gitlab)_.*", re.IGNORECASE),
    ]

    # Exact sensitive keys
    SENSITIVE_KEYS = {
        # Authentication & Security
        "wa_root_key",
        "wa_authority_keys",
        "admin_users",
        "api_keys",
        "oauth_client_secret",
        "oauth_client_id",
        "jwt_secret",
        "encryption_key",
        "signing_key",
        # Database & Infrastructure
        "database_url",
        "redis_url",
        "mongodb_uri",
        "elasticsearch_url",
        # External Services
        "openai_api_key",
        "anthropic_api_key",
        "huggingface_token",
        "discord_bot_token",
        "slack_bot_token",
        "telegram_bot_token",
        # Cloud Providers
        "aws_access_key_id",
        "aws_secret_access_key",
        "azure_client_secret",
        "gcp_service_account",
        # Other Sensitive
        "smtp_password",
        "webhook_secret",
        "payment_api_key",
    }

    @classmethod
    def is_sensitive(cls, key: str) -> bool:
        """
        Check if a configuration key is sensitive.

        Args:
            key: Configuration key to check

        Returns:
            True if key contains sensitive data
        """
        # Check exact matches first (faster)
        if key in cls.SENSITIVE_KEYS:
            return True

        # Check patterns
        for pattern in cls.SENSITIVE_PATTERNS:
            if pattern.match(key):
                return True

        return False

    @classmethod
    def filter_value(cls, key: str, value: Any, role: UserRole) -> Any:
        """
        Filter a single configuration value based on role.

        Args:
            key: Configuration key
            value: Configuration value
            role: User's role

        Returns:
            Filtered value (may be "[REDACTED]")
        """
        if not cls.is_sensitive(key):
            return value

        # SYSTEM_ADMIN sees everything
        if role == UserRole.SYSTEM_ADMIN:
            return value

        # Special cases for certain roles
        if role == UserRole.ADMIN and key == "admin_users":
            return value  # Admins can see admin list

        if role == UserRole.AUTHORITY and key == "wa_authority_keys":
            return value  # Authorities can see authority keys

        # Everyone else gets redacted
        return "[REDACTED]"

    @classmethod
    def filter_config(cls, config: ConfigDict, role: UserRole) -> ConfigDict:
        """
        Filter entire configuration dictionary based on role.

        Args:
            config: Configuration dictionary
            role: User's role

        Returns:
            Filtered configuration
        """
        if role == UserRole.SYSTEM_ADMIN:
            return config  # SYSTEM_ADMIN sees everything

        filtered = {}
        for key, value in config.items():
            filtered[key] = cls.filter_value(key, value, role)

        return filtered

    @classmethod
    def get_visible_keys(cls, all_keys: List[str], role: UserRole) -> Dict[str, bool]:
        """
        Get visibility status for a list of keys.

        Args:
            all_keys: List of configuration keys
            role: User's role

        Returns:
            Dict mapping key -> is_visible
        """
        visibility = {}

        for key in all_keys:
            if not cls.is_sensitive(key):
                visibility[key] = True
            elif role == UserRole.SYSTEM_ADMIN:
                visibility[key] = True
            elif role == UserRole.ADMIN and key == "admin_users":
                visibility[key] = True
            elif role == UserRole.AUTHORITY and key == "wa_authority_keys":
                visibility[key] = True
            else:
                visibility[key] = False

        return visibility


class ConfigValueResponse(BaseModel):
    """Response for a single configuration value."""

    key: str = Field(..., description="Configuration key")
    value: ConfigValue = Field(..., description="Configuration value (may be redacted)")
    is_sensitive: bool = Field(..., description="Whether this is a sensitive key")
    is_redacted: bool = Field(..., description="Whether value was redacted")
    last_updated: Optional[datetime] = Field(None, description="When value was last updated")
    updated_by: Optional[str] = Field(None, description="Who last updated this value")

    @field_serializer("last_updated")
    def serialize_last_updated(self, last_updated: Optional[datetime], _info: Any) -> Optional[str]:
        return last_updated.isoformat() if last_updated else None


class ConfigListResponse(BaseModel):
    """Response for configuration list."""

    configs: ConfigDict = Field(..., description="Configuration values")
    metadata: Dict[str, Union[str, int, float, bool]] = Field(..., description="Response metadata")


def filter_config_for_role(config: ConfigDict, role: UserRole) -> ConfigDict:
    """
    Filter configuration values based on user role.

    Args:
        config: Configuration dictionary
        role: User's role

    Returns:
        Filtered configuration with sensitive values redacted
    """
    return ConfigSecurity.filter_config(config, role)


class ConfigUpdateRequest(BaseModel):
    """Request to update configuration value."""

    value: ConfigValue = Field(..., description="New configuration value")
    comment: Optional[str] = Field(None, description="Optional comment about change")


class ConfigUpdateResponse(BaseModel):
    """Response after configuration update."""

    success: bool = Field(..., description="Whether update succeeded")
    key: str = Field(..., description="Configuration key")
    message: str = Field(..., description="Status message")
    requires_restart: bool = Field(False, description="Whether change requires restart")


class ConfigHistoryEntry(BaseModel):
    """Configuration change history entry."""

    key: str = Field(..., description="Configuration key")
    old_value: ConfigValue = Field(..., description="Previous value (may be redacted)")
    new_value: ConfigValue = Field(..., description="New value (may be redacted)")
    changed_at: datetime = Field(..., description="When change occurred")
    changed_by: str = Field(..., description="Who made the change")
    comment: Optional[str] = Field(None, description="Change comment")


class ConfigValidationRequest(BaseModel):
    """Request to validate configuration changes."""

    changes: ConfigDict = Field(..., description="Proposed changes")


class ConfigValidationResponse(BaseModel):
    """Response from configuration validation."""

    valid: bool = Field(..., description="Whether all changes are valid")
    errors: Dict[str, str] = Field(default_factory=dict, description="Validation errors by key")
    warnings: Dict[str, str] = Field(default_factory=dict, description="Validation warnings by key")
    requires_restart: List[str] = Field(default_factory=list, description="Keys that require restart")
