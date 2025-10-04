"""
Identity schemas for agent self-model.

Provides type-safe structures for agent identity and capabilities.
"""

from datetime import datetime, timezone
from typing import Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from ciris_engine.schemas.types import ConfigValue


class CoreProfile(BaseModel):
    """Core identity profile for the agent."""

    description: str = Field(..., description="Agent's self-description")
    role_description: str = Field(..., description="Agent's role and purpose")

    # Knowledge and expertise
    domain_specific_knowledge: Dict[str, str] = Field(default_factory=dict, description="Domain expertise mappings")
    areas_of_expertise: List[str] = Field(default_factory=list, description="Areas where agent has expertise")

    # Behavioral customization
    dsdma_prompt_template: Optional[str] = Field(None, description="Custom DSDMA prompt template")
    csdma_overrides: Dict[str, str] = Field(default_factory=dict, description="Common sense overrides")
    action_selection_pdma_overrides: Dict[str, str] = Field(
        default_factory=dict, description="Action selection overrides"
    )

    # Memory and state
    last_shutdown_memory: Optional[str] = Field(None, description="Memory from last shutdown")
    startup_instructions: Optional[str] = Field(None, description="Instructions for startup")

    model_config = ConfigDict(extra="forbid")


class IdentityMetadata(BaseModel):
    """Metadata about identity creation and modification."""

    created_at: datetime = Field(..., description="When identity was created")
    last_modified: datetime = Field(..., description="Last modification time")
    modification_count: int = Field(0, description="Number of modifications")

    # Provenance
    creator_agent_id: str = Field(..., description="Agent that created this identity")
    lineage_trace: List[str] = Field(default_factory=list, description="Identity evolution lineage")

    # Approval and authorization
    approval_required: bool = Field(True, description="Whether changes need approval")
    approved_by: Optional[str] = Field(None, description="WA who approved")
    approval_timestamp: Optional[datetime] = Field(None, description="When approved")

    # Version control
    version: str = Field("1.0.0", description="Identity version")
    previous_versions: List[str] = Field(default_factory=list, description="Previous version hashes")

    model_config = ConfigDict(extra="forbid")


class CapabilityDefinition(BaseModel):
    """Definition of an agent capability."""

    capability_name: str = Field(..., description="Name of capability")
    description: str = Field(..., description="What this capability enables")
    required_permissions: List[str] = Field(default_factory=list, description="Permissions needed")

    # Constraints
    usage_limits: Optional[Dict[str, int]] = Field(None, description="Usage limits per time period")
    restricted_contexts: List[str] = Field(default_factory=list, description="Contexts where restricted")

    # Dependencies
    depends_on: List[str] = Field(default_factory=list, description="Other required capabilities")
    conflicts_with: List[str] = Field(default_factory=list, description="Conflicting capabilities")

    model_config = ConfigDict(extra="forbid")


class AgentIdentityRoot(BaseModel):
    """Root identity structure for an agent."""

    agent_id: str = Field(..., description="Unique agent identifier")
    identity_hash: str = Field(..., description="Hash of identity for integrity")

    # Core identity
    core_profile: CoreProfile = Field(..., description="Core identity profile")
    identity_metadata: IdentityMetadata = Field(..., description="Identity metadata")

    # Capabilities and permissions
    permitted_actions: List[str] = Field(default_factory=list, description="Actions this agent can perform")
    restricted_capabilities: List[str] = Field(default_factory=list, description="Explicitly restricted capabilities")
    capability_definitions: Dict[str, CapabilityDefinition] = Field(
        default_factory=dict, description="Detailed capability definitions"
    )

    # Trust and authorization
    trust_level: float = Field(0.5, ge=0.0, le=1.0, description="Agent trust level")
    authorization_scope: str = Field("standard", description="Authorization scope: limited, standard, elevated, full")

    # Relationships
    parent_agent_id: Optional[str] = Field(None, description="Parent agent if spawned")
    child_agent_ids: List[str] = Field(default_factory=list, description="Child agents spawned")

    model_config = ConfigDict(extra="forbid")


class IdentityUpdate(BaseModel):
    """Update to agent identity."""

    update_type: str = Field(..., description="Type: profile, capabilities, trust, metadata")
    field_path: str = Field(..., description="Dot-notation path to field")
    new_value: ConfigValue = Field(..., description="New value for field")

    # Authorization
    requested_by: str = Field(..., description="Who requested update")
    reason: str = Field(..., description="Reason for update")

    # Validation
    requires_approval: bool = Field(True, description="Whether needs WA approval")
    approval_status: Optional[str] = Field(None, description="Approval status")
    approved_by: Optional[str] = Field(None, description="WA who approved")

    # Audit
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    correlation_id: str = Field(..., description="For tracing")

    model_config = ConfigDict(extra="forbid")


class IdentityValidation(BaseModel):
    """Result of identity validation."""

    is_valid: bool = Field(..., description="Whether identity is valid")
    validation_errors: List[str] = Field(default_factory=list, description="Validation errors found")

    # Integrity checks
    hash_valid: bool = Field(..., description="Whether hash matches")
    signature_valid: Optional[bool] = Field(None, description="If signed, whether valid")

    # Consistency checks
    capabilities_consistent: bool = Field(..., description="Capabilities are consistent")
    permissions_valid: bool = Field(..., description="Permissions are valid")
    metadata_complete: bool = Field(..., description="Metadata is complete")

    # Recommendations
    recommendations: List[str] = Field(default_factory=list, description="Recommendations for fixes")

    model_config = ConfigDict(extra="forbid")


# IdentitySnapshot moved to schemas/services/nodes.py as TypedGraphNode

__all__ = [
    "CoreProfile",
    "IdentityMetadata",
    "CapabilityDefinition",
    "AgentIdentityRoot",
    "IdentityUpdate",
    "IdentityValidation",
]
