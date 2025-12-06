"""
Schemas for CIRIS Agent Secrets Management System.

These schemas define the data structures for secure storage, detection,
and management of sensitive information within the CIRIS pipeline.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from ciris_engine.schemas.runtime.enums import SensitivityLevel
from ciris_engine.schemas.types import JSONDict


class SecretType(str, Enum):
    """Standard secret types with default detection patterns"""

    API_KEYS = "api_keys"
    BEARER_TOKENS = "bearer_tokens"
    PASSWORDS = "passwords"
    URLS_WITH_AUTH = "urls_with_auth"
    PRIVATE_KEYS = "private_keys"
    CREDIT_CARDS = "credit_cards"
    SOCIAL_SECURITY = "social_security"
    AWS_ACCESS_KEY = "aws_access_key"
    AWS_SECRET_KEY = "aws_secret_key"
    GITHUB_TOKEN = "github_token"
    SLACK_TOKEN = "slack_token"
    DISCORD_TOKEN = "discord_token"


class SecretRecord(BaseModel):
    """Encrypted secret storage record"""

    secret_uuid: str = Field(..., description="UUID identifier for the secret")
    encrypted_value: bytes = Field(..., description="AES-256-GCM encrypted secret value")
    encryption_key_ref: str = Field(..., description="Reference to encryption key in secure store")
    salt: bytes = Field(..., description="Cryptographic salt")
    nonce: bytes = Field(..., description="AES-GCM nonce")

    description: str = Field(..., description="Human-readable description")
    sensitivity_level: SensitivityLevel = Field(..., description="Sensitivity level")
    detected_pattern: str = Field(..., description="Pattern that detected this secret")
    context_hint: str = Field(..., description="Safe context description")

    created_at: datetime = Field(..., description="Creation timestamp")
    last_accessed: Optional[datetime] = Field(None, description="Last access time")
    access_count: int = Field(0, description="Number of times accessed")
    source_message_id: Optional[str] = Field(None, description="Source message ID")

    auto_decapsulate_for_actions: List[str] = Field(default_factory=list, description="Actions that can auto-decrypt")
    manual_access_only: bool = Field(False, description="Require manual access")

    model_config = ConfigDict(extra="forbid")


class SecretReference(BaseModel):
    """Non-sensitive reference to a stored secret for SystemSnapshot"""

    uuid: str = Field(..., description="Secret UUID")
    description: str = Field(..., description="Description")
    context_hint: str = Field(..., description="Context hint")
    sensitivity: str = Field(..., description="Sensitivity level")
    detected_pattern: str = Field(..., description="Detection pattern")
    auto_decapsulate_actions: List[str] = Field(..., description="Auto-decrypt actions")
    created_at: datetime = Field(..., description="Creation time")
    last_accessed: Optional[datetime] = Field(None, description="Last access")

    model_config = ConfigDict(extra="forbid")


class SecretAccessLog(BaseModel):
    """Audit log for secret access"""

    access_id: str = Field(..., description="Unique access identifier")
    secret_uuid: str = Field(..., description="Secret that was accessed")
    access_type: Literal["VIEW", "DECRYPT", "UPDATE", "DELETE", "STORE"] = Field(..., description="Access type")
    accessor: str = Field(..., description="Who/what accessed the secret")
    purpose: str = Field(..., description="Stated purpose for access")
    timestamp: datetime = Field(..., description="Access timestamp")
    source_ip: Optional[str] = Field(None, description="Source IP")
    user_agent: Optional[str] = Field(None, description="User agent")
    action_context: Optional[str] = Field(None, description="Action context")
    success: bool = Field(True, description="Whether access succeeded")
    failure_reason: Optional[str] = Field(None, description="Failure reason if any")

    model_config = ConfigDict(extra="forbid")


class DetectedSecret(BaseModel):
    """Secret detected during filtering process"""

    original_value: str = Field(..., description="Original secret value")
    secret_uuid: str = Field(..., description="Generated UUID for this secret")
    pattern_name: str = Field(..., description="Detection pattern that found this secret")
    description: str = Field(..., description="Human-readable description")
    sensitivity: SensitivityLevel = Field(..., description="Sensitivity level")
    context_hint: str = Field(..., description="Safe context description")
    replacement_text: str = Field(..., description="Text to replace secret with in context")

    model_config = ConfigDict(extra="forbid")


class SecretsFilterResult(BaseModel):
    """Result of applying secrets filter to content"""

    filtered_content: str = Field(..., description="Content with secrets replaced by references")
    detected_secrets: List[DetectedSecret] = Field(default_factory=list, description="Detected secrets")
    secrets_found: int = Field(default=0, description="Number of secrets found")
    patterns_matched: List[str] = Field(default_factory=list, description="Patterns that matched")

    model_config = ConfigDict(extra="forbid")


class RecallSecretParams(BaseModel):
    """Parameters for RECALL_SECRET tool"""

    secret_uuid: str = Field(..., description="UUID of the secret to recall")
    purpose: str = Field(..., description="Why the secret is needed (for audit)")
    decrypt: bool = Field(default=False, description="Whether to decrypt the secret value")

    model_config = ConfigDict(extra="forbid")


class SecretPattern(BaseModel):
    """Pattern for detecting secrets"""

    name: str = Field(..., description="Pattern name")
    pattern: str = Field(..., description="Regex pattern")
    description: str = Field(..., description="What this pattern detects")
    sensitivity: SensitivityLevel = Field(..., description="Default sensitivity")
    enabled: bool = Field(True, description="Whether pattern is active")

    model_config = ConfigDict(extra="forbid")


def _default_secret_patterns() -> List[SecretPattern]:
    """Default secret detection patterns."""
    return [
        SecretPattern(
            name="api_key",
            pattern=r"(?i)(api[_\-]?key|apikey)\s*[:=]\s*['\"]?([A-Za-z0-9\-_]{20,})['\"]?",
            description="API Key",
            sensitivity=SensitivityLevel.HIGH,
            enabled=True,
        ),
        SecretPattern(
            name="bearer_token",
            pattern=r"(?i)bearer\s+([A-Za-z0-9\-_.~+/]+={0,2})",
            description="Bearer Token",
            sensitivity=SensitivityLevel.HIGH,
            enabled=True,
        ),
        SecretPattern(
            name="private_key",
            pattern=r"-----BEGIN\s+(?:RSA\s+)?PRIVATE\s+KEY-----",
            description="Private Key",
            sensitivity=SensitivityLevel.CRITICAL,
            enabled=True,
        ),
    ]


class SecretsDetectionConfig(BaseModel):
    """Configuration for secrets detection"""

    enabled: bool = Field(True, description="Whether detection is enabled")
    patterns: List[SecretPattern] = Field(default_factory=_default_secret_patterns, description="Detection patterns")

    model_config = ConfigDict(extra="forbid")


class UpdateSecretsFilterParams(BaseModel):
    """Parameters for UPDATE_SECRETS_FILTER tool"""

    operation: Literal["add_pattern", "remove_pattern", "update_pattern", "get_current"] = Field(
        ..., description="Operation to perform"
    )

    pattern: Optional[SecretPattern] = Field(None, description="Pattern for add/update operations")
    pattern_name: Optional[str] = Field(None, description="Pattern name for remove/update")
    config_updates: Optional[Dict[str, str]] = Field(None, description="Configuration updates")

    model_config = ConfigDict(extra="forbid")


class SecretStorageConfig(BaseModel):
    """Configuration for secret storage"""

    encryption_algorithm: str = Field("AES-256-GCM", description="Encryption algorithm")
    key_derivation_function: str = Field("PBKDF2", description="KDF algorithm")
    key_iterations: int = Field(100000, description="KDF iterations")
    auto_expire_days: Optional[int] = Field(None, description="Auto-expiry in days")
    require_mfa: bool = Field(False, description="Require MFA for access")

    model_config = ConfigDict(extra="forbid")


class SecretMetrics(BaseModel):
    """Metrics for secret management"""

    total_secrets: int = Field(..., description="Total stored secrets")
    secrets_by_type: Dict[str, int] = Field(..., description="Count by type")
    secrets_by_sensitivity: Dict[str, int] = Field(..., description="Count by sensitivity")
    access_count_last_day: int = Field(..., description="Accesses in last 24h")
    detection_count_last_day: int = Field(..., description="Detections in last 24h")

    model_config = ConfigDict(extra="forbid")


class PatternStats(BaseModel):
    """Statistics about active patterns."""

    total_patterns: int = Field(0, description="Total number of patterns")
    default_patterns: int = Field(0, description="Number of active default patterns")
    custom_patterns: int = Field(0, description="Number of custom patterns")
    disabled_patterns: int = Field(0, description="Number of disabled patterns")
    builtin_patterns: bool = Field(True, description="Whether builtin patterns are enabled")
    filter_version: str = Field("v1.0", description="Filter version")

    model_config = ConfigDict(extra="forbid")


class ConfigExport(BaseModel):
    """Exported configuration data."""

    filter_id: str = Field("config_based", description="Filter identifier")
    version: int = Field(1, description="Configuration version")
    builtin_patterns_enabled: bool = Field(True, description="Whether builtin patterns are enabled")
    custom_patterns: List[SecretPattern] = Field(default_factory=list, description="Custom patterns")
    disabled_patterns: List[str] = Field(default_factory=list, description="Disabled pattern names")
    sensitivity_overrides: JSONDict = Field(default_factory=dict, description="Sensitivity overrides")
    require_confirmation_for: List[str] = Field(default_factory=list, description="Actions requiring confirmation")
    auto_decrypt_for_actions: List[str] = Field(default_factory=list, description="Actions that auto-decrypt")

    model_config = ConfigDict(extra="forbid")


class FilterConfigUpdate(BaseModel):
    """Update to filter configuration."""

    updates: JSONDict = Field(..., description="Configuration updates to apply")
    update_type: str = Field("config", description="Type of update")
    validation_errors: List[str] = Field(default_factory=list, description="Validation errors if any")

    model_config = ConfigDict(extra="forbid")


__all__ = [
    "SecretType",
    "SecretRecord",
    "SecretReference",
    "SecretAccessLog",
    "DetectedSecret",
    "SecretsFilterResult",
    "RecallSecretParams",
    "SecretPattern",
    "UpdateSecretsFilterParams",
    "SecretStorageConfig",
    "SecretMetrics",
    "PatternStats",
    "ConfigExport",
    "FilterConfigUpdate",
]
