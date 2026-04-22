"""
Ticket configuration schemas for agent templates.

Tickets are CIRIS's mechanism for tracking multi-stage workflows with SOP (Standard Operating Procedure) enforcement.
DSAR tickets are always present (GDPR compliance), agents can add custom ticket types via templates.
"""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class TicketStageConfig(BaseModel):
    """Configuration for a single stage in a ticket workflow."""

    name: str = Field(..., description="Stage name (e.g., 'identity_resolution', 'data_export')")
    tools: List[str] = Field(default_factory=list, description="List of tool names required for this stage")
    optional: bool = Field(
        default=False,
        description="Whether this stage is optional (failure won't block ticket completion)",
    )
    parallel: bool = Field(
        default=False,
        description="Whether tools in this stage can be executed in parallel",
    )
    description: Optional[str] = Field(
        None,
        description="Human-readable description of what this stage does",
    )


class TicketSOPConfig(BaseModel):
    """Configuration for a Standard Operating Procedure (SOP)."""

    sop: str = Field(..., description="SOP identifier (e.g., 'DSAR_ACCESS', 'APPOINTMENT_SCHEDULE')")
    ticket_type: str = Field(..., description="Ticket type category (e.g., 'dsar', 'appointment', 'incident')")
    required_fields: List[str] = Field(
        default_factory=list,
        description="List of required metadata fields for ticket creation",
    )
    deadline_days: Optional[int] = Field(
        None,
        description="Number of days until deadline (e.g., 30 for GDPR compliance)",
    )
    priority_default: int = Field(
        default=5,
        ge=1,
        le=10,
        description="Default priority level (1=lowest, 10=urgent)",
    )
    stages: List[TicketStageConfig] = Field(
        default_factory=list,
        description="Ordered list of stages in the ticket workflow",
    )
    description: Optional[str] = Field(
        None,
        description="Human-readable description of what this SOP does",
    )


class TicketsConfig(BaseModel):
    """Ticket system configuration for an agent."""

    enabled: bool = Field(
        default=True,
        description="Whether ticket system is enabled for this agent (DSAR always present)",
    )
    sops: List[TicketSOPConfig] = Field(
        default_factory=list,
        description="List of supported Standard Operating Procedures",
    )

    def get_sop(self, sop_name: str) -> Optional[TicketSOPConfig]:
        """Get SOP configuration by name."""
        for sop in self.sops:
            if sop.sop == sop_name:
                return sop
        return None

    def is_sop_supported(self, sop_name: str) -> bool:
        """Check if an SOP is supported."""
        return any(sop.sop == sop_name for sop in self.sops)

    def list_sops(self) -> List[str]:
        """List all supported SOP names."""
        return [sop.sop for sop in self.sops]
