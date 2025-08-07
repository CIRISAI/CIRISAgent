"""
Agent configuration schemas.

Minimal schemas for agent identity and templates.
"""

from typing import Dict, List, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator


class StewardshipCalculation(BaseModel):
    """Schema for the Stewardship Tier calculation details."""

    creator_influence_score: int = Field(..., description="Creator-Influence Score (CIS)")
    risk_magnitude: int = Field(..., description="Risk Magnitude (RM)")
    formula: str = Field(..., description="Formula used for calculation")
    result: int = Field(..., description="Calculated Stewardship Tier (ST)")


class CreatorLedgerEntry(BaseModel):
    """Schema for the Creator Ledger entry."""

    creator_id: str = Field(..., description="Identifier for the creator or creating team")
    creation_timestamp: str = Field(..., description="ISO 8601 timestamp of the creation entry")
    covenant_version: str = Field(..., description="Version of the Covenant applied")
    book_vi_compliance_check: str = Field(..., description="Status of the Book VI compliance check")
    stewardship_tier_calculation: StewardshipCalculation = Field(..., description="Details of the ST calculation")
    public_key_fingerprint: str = Field(..., description="Fingerprint of the public key used for signing")
    signature: str = Field(..., description="Cryptographic signature of the ledger entry's content")


class CreatorIntentStatement(BaseModel):
    """Schema for the Creator Intent Statement (CIS)."""

    purpose_and_functionalities: List[str] = Field(..., description="The intended purpose and functionalities")
    limitations_and_design_choices: List[str] = Field(..., description="Known limitations and key design choices")
    anticipated_benefits: List[str] = Field(..., description="Anticipated benefits of the creation")
    anticipated_risks: List[str] = Field(..., description="Anticipated risks associated with the creation")


class Stewardship(BaseModel):
    """Schema for Book VI Stewardship information."""

    stewardship_tier: int = Field(..., description="Calculated Stewardship Tier (ST) for the agent")
    creator_intent_statement: CreatorIntentStatement = Field(..., description="The Creator Intent Statement (CIS)")
    creator_ledger_entry: CreatorLedgerEntry = Field(..., description="The entry for the Creator Ledger")


class AgentTemplate(BaseModel):
    """Agent profile template for identity configuration."""

    name: str = Field(..., description="Agent name/identifier")
    description: str = Field(..., description="Agent description")
    role_description: str = Field(..., description="Agent's role")

    # Permissions
    permitted_actions: List[str] = Field(default_factory=list, description="List of permitted handler actions")

    # DMA overrides
    dsdma_kwargs: Optional["DSDMAConfiguration"] = Field(None, description="Domain-specific DMA configuration")
    csdma_overrides: Optional["CSDMAOverrides"] = Field(None, description="Common sense DMA prompt overrides")
    action_selection_pdma_overrides: Optional["ActionSelectionOverrides"] = Field(
        None, description="Action selection prompt overrides"
    )

    # Adapter configs
    discord_config: Optional["DiscordAdapterOverrides"] = Field(
        None, description="Discord adapter configuration overrides"
    )
    api_config: Optional["APIAdapterOverrides"] = Field(None, description="API adapter configuration overrides")
    cli_config: Optional["CLIAdapterOverrides"] = Field(None, description="CLI adapter configuration overrides")

    # Book VI Compliance
    stewardship: Optional["Stewardship"] = Field(None, description="Book VI Stewardship information")

    model_config = ConfigDict(extra="allow")  # Allow additional fields for extensibility

    @field_validator("stewardship", mode="before")
    @classmethod
    def convert_stewardship(cls, v):
        """Convert dict to Stewardship if needed."""
        if v is None:
            return None
        if isinstance(v, dict):
            return Stewardship(**v)
        return v

    @field_validator("dsdma_kwargs", mode="before")
    @classmethod
    def convert_dsdma_kwargs(cls, v):
        """Convert dict to DSDMAConfiguration if needed."""
        if v is None:
            return None
        if isinstance(v, dict):
            return DSDMAConfiguration(**v)
        return v

    @field_validator("csdma_overrides", mode="before")
    @classmethod
    def convert_csdma_overrides(cls, v):
        """Convert dict to CSDMAOverrides if needed."""
        if v is None:
            return None
        if isinstance(v, dict):
            return CSDMAOverrides(**v)
        return v

    @field_validator("action_selection_pdma_overrides", mode="before")
    @classmethod
    def convert_action_selection_overrides(cls, v):
        """Convert dict to ActionSelectionOverrides if needed."""
        if v is None:
            return None
        if isinstance(v, dict):
            return ActionSelectionOverrides(**v)
        return v

    @field_validator("discord_config", mode="before")
    @classmethod
    def convert_discord_config(cls, v):
        """Convert dict to DiscordAdapterOverrides if needed."""
        if v is None:
            return None
        if isinstance(v, dict):
            return DiscordAdapterOverrides(**v)
        return v

    @field_validator("api_config", mode="before")
    @classmethod
    def convert_api_config(cls, v):
        """Convert dict to APIAdapterOverrides if needed."""
        if v is None:
            return None
        if isinstance(v, dict):
            return APIAdapterOverrides(**v)
        return v

    @field_validator("cli_config", mode="before")
    @classmethod
    def convert_cli_config(cls, v):
        """Convert dict to CLIAdapterOverrides if needed."""
        if v is None:
            return None
        if isinstance(v, dict):
            return CLIAdapterOverrides(**v)
        return v


class DSDMAConfiguration(BaseModel):
    """Configuration for Domain-Specific Decision Making Agent."""

    prompt_template: Optional[str] = Field(None, description="Custom prompt template")
    domain_specific_knowledge: Optional[Dict[str, Union[str, List[str], Dict[str, str]]]] = Field(
        None, description="Domain-specific knowledge like rules, principles, examples"
    )
    model_config = ConfigDict(extra="allow")  # Allow domain-specific fields


class CSDMAOverrides(BaseModel):
    """Common Sense DMA prompt overrides."""

    system_prompt: Optional[str] = Field(None, description="Override system prompt")
    user_prompt_template: Optional[str] = Field(None, description="Override user prompt template")
    model_config = ConfigDict(extra="forbid")  # Strict validation


class ActionSelectionOverrides(BaseModel):
    """Action selection prompt overrides."""

    system_prompt: Optional[str] = Field(None, description="Override system prompt")
    user_prompt_template: Optional[str] = Field(None, description="Override user prompt template")
    action_descriptions: Optional[Dict[str, str]] = Field(None, description="Override action descriptions")
    model_config = ConfigDict(extra="allow")  # Allow for additional, template-specific guidance


class DiscordAdapterOverrides(BaseModel):
    """Discord adapter configuration overrides."""

    # Override specific Discord settings from template
    home_channel_id: Optional[str] = Field(None, description="Override home channel")
    deferral_channel_id: Optional[str] = Field(None, description="Override deferral channel")
    monitored_channel_ids: Optional[List[str]] = Field(None, description="Override monitored channels")
    allowed_user_ids: Optional[List[str]] = Field(None, description="Override allowed users")
    allowed_role_ids: Optional[List[str]] = Field(None, description="Override allowed roles")
    model_config = ConfigDict(extra="forbid")  # Only allow known overrides


class APIAdapterOverrides(BaseModel):
    """API adapter configuration overrides."""

    # Override specific API settings from template
    rate_limit_per_minute: Optional[int] = Field(None, description="Override rate limit")
    max_request_size: Optional[int] = Field(None, description="Override max request size")
    cors_origins: Optional[List[str]] = Field(None, description="Override CORS origins")
    model_config = ConfigDict(extra="forbid")  # Only allow known overrides


class CLIAdapterOverrides(BaseModel):
    """CLI adapter configuration overrides."""

    # Override specific CLI settings from template
    prompt_prefix: Optional[str] = Field(None, description="Override prompt prefix")
    enable_colors: Optional[bool] = Field(None, description="Override color output")
    max_history_entries: Optional[int] = Field(None, description="Override history size")
    model_config = ConfigDict(extra="forbid")  # Only allow known overrides


# Update forward references
AgentTemplate.model_rebuild()
