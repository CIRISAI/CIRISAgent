"""
Prompt-related schemas for DMA system.

Provides typed schemas with properly typed structures for prompt management.
"""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from ciris_engine.schemas.types import JSONDict


class PromptTemplate(BaseModel):
    """A single prompt template with metadata."""

    name: str = Field(..., description="Template name/identifier")
    content: str = Field(..., description="Template content with {variable} placeholders")
    description: Optional[str] = Field(None, description="What this template is for")

    # Template metadata
    version: str = Field("1.0", description="Template version")
    category: str = Field("general", description="Template category")
    requires_covenant: bool = Field(False, description="Whether COVENANT_TEXT should be prepended")

    # Variable requirements
    required_variables: List[str] = Field(default_factory=list, description="Required template variables")
    optional_variables: List[str] = Field(default_factory=list, description="Optional template variables")

    # Usage hints
    usage_context: Optional[str] = Field(None, description="When to use this template")
    example_output: Optional[str] = Field(None, description="Example of filled template")

    model_config = ConfigDict(extra="forbid")


class PromptCollection(BaseModel):
    """Collection of prompt templates for a DMA component."""

    # Metadata
    component_name: str = Field(..., description="Name of the DMA component")
    description: str = Field(..., description="Description of this prompt collection")
    version: str = Field("1.0", description="Collection version")

    # Core prompt sections
    system_header: Optional[str] = Field(None, description="System message header")
    system_guidance_header: Optional[str] = Field(None, description="System guidance header")

    # Domain-specific prompts
    domain_principles: Optional[str] = Field(None, description="Domain principles template")
    evaluation_steps: Optional[str] = Field(None, description="Evaluation steps template")
    evaluation_criteria: Optional[str] = Field(None, description="Evaluation criteria template")

    # Response formatting
    response_format: Optional[str] = Field(None, description="Response format guidance")
    response_guidance: Optional[str] = Field(None, description="Response guidance template")
    decision_format: Optional[str] = Field(None, description="Decision format template")

    # Action-specific prompts
    action_parameter_schemas: Optional[str] = Field(None, description="Action parameter schemas")

    # Guidance prompts
    csdma_ambiguity_guidance: Optional[str] = Field(None, description="CSDMA ambiguity guidance")
    action_params_speak_csdma_guidance: Optional[str] = Field(None, description="SPEAK action guidance")
    action_params_ponder_guidance: Optional[str] = Field(None, description="PONDER action guidance")
    action_params_observe_guidance: Optional[str] = Field(None, description="OBSERVE action guidance")
    rationale_csdma_guidance: Optional[str] = Field(None, description="Rationale guidance")

    # Special case prompts
    final_ponder_advisory: Optional[str] = Field(None, description="Final ponder advisory template")
    closing_reminder: Optional[str] = Field(None, description="Closing reminder text")

    # Context integration
    context_integration: Optional[str] = Field(None, description="Context integration template")

    # Agent-specific variations (e.g., "ciris_mode_<prompt_key>")
    agent_variations: Dict[str, str] = Field(default_factory=dict, description="Agent-specific prompt variations")

    # Additional custom prompts
    custom_prompts: Dict[str, str] = Field(default_factory=dict, description="Additional custom prompts")

    # Metadata flags
    uses_covenant_header: bool = Field(False, description="Whether to use COVENANT_TEXT")
    supports_agent_modes: bool = Field(True, description="Whether agent-specific prompts are supported")

    def get_prompt(self, key: str, agent_name: Optional[str] = None) -> Optional[str]:
        """Get a prompt by key, with agent-specific fallback."""
        # Try agent-specific first
        if agent_name and self.supports_agent_modes:
            agent_key = f"{agent_name.lower()}_mode_{key}"
            if agent_key in self.agent_variations:
                return self.agent_variations[agent_key]

        # Try direct attribute
        if hasattr(self, key):
            return getattr(self, key)  # type: ignore[no-any-return]  # Dynamic attribute lookup

        # Try custom prompts
        if key in self.custom_prompts:
            return self.custom_prompts[key]

        return None

    def to_dict(self) -> JSONDict:
        """Convert to JSON-serializable dictionary for backward compatibility.

        Returns a flattened dictionary containing all prompt strings,
        agent variations, and custom prompts.
        """
        result: JSONDict = {}

        # Add all non-None string fields
        for field_name in self.model_fields:
            value = getattr(self, field_name)
            if isinstance(value, str) and value is not None:
                result[field_name] = value

        # Add agent variations
        result.update(self.agent_variations)

        # Add custom prompts
        result.update(self.custom_prompts)

        return result

    model_config = ConfigDict(extra="forbid")


class PromptVariable(BaseModel):
    """Definition of a template variable."""

    name: str = Field(..., description="Variable name (without braces)")
    description: str = Field(..., description="What this variable represents")
    type: str = Field("str", description="Variable type: str, int, float, bool, list, dict")
    required: bool = Field(True, description="Whether this variable is required")
    default: Optional[Any] = Field(None, description="Default value if not provided")
    example: Optional[Any] = Field(None, description="Example value")

    # Validation rules
    min_length: Optional[int] = Field(None, description="Minimum length for strings")
    max_length: Optional[int] = Field(None, description="Maximum length for strings")
    allowed_values: Optional[List[Any]] = Field(None, description="Allowed values (enum)")
    pattern: Optional[str] = Field(None, description="Regex pattern for validation")

    model_config = ConfigDict(extra="forbid")


class PromptMetadata(BaseModel):
    """Metadata about a prompt file or collection."""

    file_path: str = Field(..., description="Path to the prompt file")
    format: str = Field("yaml", description="File format: yaml, json, txt")

    # Versioning
    version: str = Field(..., description="Prompt version")
    last_modified: str = Field(..., description="ISO timestamp of last modification")
    author: Optional[str] = Field(None, description="Author of the prompts")

    # Content summary
    description: str = Field(..., description="What these prompts are for")
    component: str = Field(..., description="Which DMA component uses these")
    prompt_count: int = Field(0, description="Number of prompts in file")

    # Dependencies
    requires: List[str] = Field(default_factory=list, description="Required prompt files")
    imports: List[str] = Field(default_factory=list, description="Imported prompt collections")

    # Usage stats
    usage_count: int = Field(0, description="How many times loaded")
    last_used: Optional[str] = Field(None, description="ISO timestamp of last use")

    model_config = ConfigDict(extra="forbid")
