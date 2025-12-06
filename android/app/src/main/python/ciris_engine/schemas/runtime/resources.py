"""
Resource tracking schemas for CIRIS Trinity Architecture.

Environmental and financial impact tracking for responsible AI.
"""

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class ResourceUsage(BaseModel):
    """Track LLM resource utilization with environmental awareness."""

    # Token usage
    tokens_used: int = Field(default=0, description="Total tokens consumed")
    tokens_input: int = Field(default=0, description="Input tokens")
    tokens_output: int = Field(default=0, description="Output tokens")

    # Financial impact
    cost_cents: float = Field(default=0.0, ge=0.0, description="Cost in cents USD")

    # Environmental impact
    carbon_grams: float = Field(default=0.0, ge=0.0, description="Carbon emissions in grams CO2")
    energy_kwh: float = Field(default=0.0, ge=0.0, description="Energy consumption in kilowatt-hours")

    # Model information
    model_used: Optional[str] = Field(default=None, description="Model that incurred these costs")

    model_config = ConfigDict(extra="forbid", protected_namespaces=())


__all__ = ["ResourceUsage"]
