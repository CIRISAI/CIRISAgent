"""
Module configuration schemas for interactive setup workflows.

Provides type-safe schemas for multi-step module configuration processes
including discovery, OAuth, selection, and confirmation steps.
"""

from datetime import datetime
from typing import List, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field

from ciris_engine.schemas.runtime.manifest import (
    ConfigurationStep,
    DiscoveredInstance,
    SelectionOption,
)


# Step Data Models (discriminated by step_type)


class DiscoveryStepData(BaseModel):
    """Data for discovery step results."""

    step_type: Literal["discovery"] = "discovery"
    discovered_items: List[DiscoveredInstance] = Field(
        default_factory=list, description="Items discovered during discovery"
    )

    model_config = ConfigDict(extra="forbid")


class OAuthStepData(BaseModel):
    """Data for OAuth step results."""

    step_type: Literal["oauth"] = "oauth"
    oauth_url: Optional[str] = Field(None, description="OAuth authorization URL")
    awaiting_callback: bool = Field(False, description="Whether waiting for OAuth callback")
    tokens_received: bool = Field(False, description="Whether tokens have been received")

    model_config = ConfigDict(extra="forbid")


class SelectionStepData(BaseModel):
    """Data for selection step results."""

    step_type: Literal["select"] = "select"
    options: List[SelectionOption] = Field(default_factory=list, description="Available selection options")

    model_config = ConfigDict(extra="forbid")


class ConfirmStepData(BaseModel):
    """Data for confirmation step."""

    step_type: Literal["confirm"] = "confirm"
    summary: dict[str, str] = Field(default_factory=dict, description="Configuration summary (string values only)")

    model_config = ConfigDict(extra="forbid")


# Discriminated union - type-safe step data
StepData = Union[DiscoveryStepData, OAuthStepData, SelectionStepData, ConfirmStepData]


# Step Input Models (discriminated by step_type)


class DiscoveryStepInput(BaseModel):
    """Input for discovery step (usually empty)."""

    step_type: Literal["discovery"] = "discovery"

    model_config = ConfigDict(extra="forbid")


class OAuthStepInput(BaseModel):
    """Input for OAuth step."""

    step_type: Literal["oauth"] = "oauth"
    code: Optional[str] = Field(None, description="OAuth authorization code (present on callback)")
    state: Optional[str] = Field(None, description="OAuth state parameter")

    model_config = ConfigDict(extra="forbid")


class SelectionStepInput(BaseModel):
    """Input for selection step."""

    step_type: Literal["select"] = "select"
    selection: Union[str, List[str]] = Field(..., description="Selected option(s) - single or multi-select")

    model_config = ConfigDict(extra="forbid")


class ConfirmStepInput(BaseModel):
    """Input for confirmation step."""

    step_type: Literal["confirm"] = "confirm"
    confirmed: bool = Field(True, description="Whether user confirmed the configuration")

    model_config = ConfigDict(extra="forbid")


# Discriminated union - type-safe step input
StepInput = Union[DiscoveryStepInput, OAuthStepInput, SelectionStepInput, ConfirmStepInput]


# Step Result Model


class StepResult(BaseModel):
    """Result of executing a configuration step."""

    step_id: str = Field(..., description="Step identifier")
    step_type: Literal["discovery", "oauth", "select", "confirm"] = Field(..., description="Step type")
    success: bool = Field(..., description="Whether step execution succeeded")
    data: StepData = Field(..., description="Type-safe step data (discriminated by step_type)")
    next_step: Optional[int] = Field(None, description="Index of next step to execute (None if workflow complete)")
    error: Optional[str] = Field(None, description="Error message if step failed")

    model_config = ConfigDict(extra="forbid")


# Configuration Session Model


class ModuleConfigSession(BaseModel):
    """Active configuration session."""

    session_id: str = Field(..., description="Unique session identifier")
    module_name: str = Field(..., description="Name of module being configured")
    user_id: str = Field(..., description="User ID performing configuration")
    steps: List[ConfigurationStep] = Field(..., description="Configuration steps")
    current_step: int = Field(..., description="Current step index (0-based)")
    collected_config: dict[str, str] = Field(
        default_factory=dict, description="Collected configuration values (string values only)"
    )
    created_at: datetime = Field(..., description="Session creation timestamp")
    expires_at: datetime = Field(..., description="Session expiration timestamp")

    model_config = ConfigDict(extra="forbid")
