"""
Schemas for WA CLI wizard operations.

These replace all Dict[str, Any] usage in logic/infrastructure/sub_services/wa_cli_wizard.py.
"""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from ciris_engine.schemas.types import JSONDict


class WizardResult(BaseModel):
    """Result from a wizard operation."""

    status: str = Field(..., description="Status: success, error, observer, imported")
    error: Optional[str] = Field(None, description="Error message if failed")
    wa_id: Optional[str] = Field(None, description="WA ID if applicable")
    key_file: Optional[str] = Field(None, description="Key file path if created")
    join_code: Optional[str] = Field(None, description="Join code if generated")
    expires_at: Optional[str] = Field(None, description="Expiration time for join code")
    additional_info: JSONDict = Field(default_factory=dict, description="Additional result information")


class RootCreationResult(WizardResult):
    """Result from creating a new root WA."""

    shamir_shares: Optional[List[str]] = Field(None, description="Shamir share codes if generated")
    certificate_path: Optional[str] = Field(None, description="Path to certificate file")


class JoinRequestResult(WizardResult):
    """Result from generating a join request."""

    request_id: str = Field(..., description="Unique request ID")
    requested_role: str = Field(..., description="Role being requested")
    requester_name: str = Field(..., description="Name of requester")


class OAuthConfigResult(WizardResult):
    """Result from OAuth configuration."""

    provider: str = Field(..., description="OAuth provider name")
    redirect_uri: Optional[str] = Field(None, description="OAuth redirect URI")
    scopes: List[str] = Field(default_factory=list, description="OAuth scopes configured")


class OnboardingChoice(BaseModel):
    """User's choice during onboarding."""

    option: int = Field(..., description="Selected option number")
    description: str = Field(..., description="Description of the choice")
    requires_action: bool = Field(True, description="Whether action is required")
