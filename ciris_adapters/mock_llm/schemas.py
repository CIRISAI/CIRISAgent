"""
Schemas for MockLLM service.

Defines configuration and response structures specific to mock operations.
"""

from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class MockLLMConfig(BaseModel):
    """Configuration for MockLLM service."""

    delay_ms: int = Field(default=100, description="Simulated response delay in milliseconds")
    failure_rate: float = Field(default=0.0, ge=0.0, le=1.0, description="Probability of simulated failures (0.0-1.0)")
    deterministic: bool = Field(default=True, description="Whether responses are deterministic (for testing)")


class MockLLMStatus(BaseModel):
    """Status information for MockLLM service."""

    response_count: int = Field(..., description="Total responses generated")
    failure_count: int = Field(..., description="Total simulated failures")
    average_delay_ms: float = Field(..., description="Average response delay")
    is_healthy: bool = Field(..., description="Service health status")


class MockResponseOverride(BaseModel):
    """Override configuration for specific mock responses."""

    pattern: str = Field(..., description="Pattern to match in request")
    response: Dict[str, Any] = Field(..., description="Response to return")
    delay_ms: Optional[int] = Field(None, description="Override delay for this response")
    fail: bool = Field(default=False, description="Whether to simulate failure")
