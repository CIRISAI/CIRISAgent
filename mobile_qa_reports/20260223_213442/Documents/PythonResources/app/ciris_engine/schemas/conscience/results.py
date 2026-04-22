"""
Conscience result schemas for contract-driven architecture.

Typed results from conscience checks.
"""

from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field


class ConscienceResult(BaseModel):
    """Result from any conscience check."""

    conscience_name: str = Field(..., description="Name of the conscience")
    passed: bool = Field(..., description="Whether the conscience check passed")
    severity: Literal["info", "warning", "error", "critical"] = Field(..., description="Severity level of the result")
    message: str = Field(..., description="Result message")
    override_action: Optional[str] = Field(None, description="Action to override if failed")
    details: Optional[Dict[str, Union[str, float, bool, List[Any]]]] = Field(
        None, description="Additional details about the check"
    )

    model_config = ConfigDict(extra="forbid")
