"""
Resource tracking schemas for CIRIS Trinity Architecture.

Environmental and financial impact tracking for responsible AI.
"""

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class LLMCallSampling(BaseModel):
    """The sampling one provider call actually sent, and who served it.

    Built by the client path that writes the wire request, so a parameter that
    path drops (Claude over HTTPS sends no temperature or seed) is None here,
    never the value the caller asked for.
    """

    temperature: Optional[float] = Field(default=None, description="Temperature sent; None if not sent")
    seed: Optional[int] = Field(default=None, description="Seed sent; None if not sent")
    max_tokens: Optional[int] = Field(default=None, ge=0, description="Output token cap sent")
    served_by: Optional[str] = Field(
        default=None, description="Upstream provider that served the call, as the router reports it (OpenRouter)"
    )
    served_model: Optional[str] = Field(default=None, description="Model the provider says served the call")

    model_config = ConfigDict(extra="forbid", frozen=True, protected_namespaces=(), defer_build=True)


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

    # What this call sent (per-call usage only; aggregates leave it None)
    sampling: Optional[LLMCallSampling] = Field(default=None, description="Sampling sent and serving provider")

    model_config = ConfigDict(extra="forbid", protected_namespaces=(), defer_build=True)


__all__ = ["LLMCallSampling", "ResourceUsage"]
