"""Adapter discovery and availability schemas.

Provides schemas for reporting adapter availability, eligibility status,
and installation options.
"""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from ciris_engine.schemas.adapters.tools import InstallStep, ToolInfo
from ciris_engine.schemas.runtime.manifest import ServiceManifest


class AdapterAvailabilityStatus(BaseModel):
    """Full availability status for a discovered adapter.

    Used to report both eligible and ineligible adapters with details
    about what's missing and how to install dependencies.
    """

    name: str = Field(..., description="Adapter module name")
    module_type: str = Field(default="", description="Module type (skill_adapter, etc.)")
    description: str = Field(default="", description="Adapter description")

    # Eligibility status
    eligible: bool = Field(..., description="Whether the adapter is currently eligible for use")
    eligibility_reason: Optional[str] = Field(None, description="Human-readable reason if not eligible")

    # Missing dependencies (detailed breakdown)
    missing_binaries: List[str] = Field(default_factory=list, description="Required binaries not in PATH")
    missing_env_vars: List[str] = Field(default_factory=list, description="Required env vars not set")
    missing_config: List[str] = Field(default_factory=list, description="Required config keys not available")
    platform_supported: bool = Field(True, description="Whether current platform is supported")

    # Installation options
    can_install: bool = Field(False, description="True if install_hints are available for missing deps")
    install_hints: List[InstallStep] = Field(
        default_factory=list, description="Installation steps for missing dependencies"
    )

    # What this adapter provides
    tools: List[ToolInfo] = Field(default_factory=list, description="Tools this adapter would provide")

    # Source information
    source_path: Optional[str] = Field(None, description="Path where adapter was discovered")
    is_builtin: bool = Field(False, description="True if from ciris_adapters/ (built-in)")

    model_config = ConfigDict(extra="forbid")


class AdapterDiscoveryReport(BaseModel):
    """Report of all discovered adapters and their availability.

    Used as the response for GET /adapters/available endpoint.
    """

    eligible: List[AdapterAvailabilityStatus] = Field(
        default_factory=list, description="Adapters that are ready to use"
    )
    ineligible: List[AdapterAvailabilityStatus] = Field(
        default_factory=list, description="Adapters that have unmet requirements"
    )

    # Summary counts
    total_discovered: int = Field(0, description="Total adapters found across all paths")
    total_eligible: int = Field(0, description="Number of eligible adapters")
    total_installable: int = Field(0, description="Number of ineligible adapters that have install hints")

    model_config = ConfigDict(extra="forbid")


class InstallRequest(BaseModel):
    """Request to install adapter dependencies."""

    dry_run: bool = Field(False, description="If true, report what would be installed without executing")
    install_step_id: Optional[str] = Field(
        None, description="Specific install step ID to use, or None for first applicable"
    )

    model_config = ConfigDict(extra="forbid")


class InstallResponse(BaseModel):
    """Response from adapter installation attempt."""

    success: bool = Field(..., description="Whether installation succeeded")
    message: str = Field(..., description="Human-readable result message")
    installed_binaries: List[str] = Field(
        default_factory=list, description="Binaries that were installed (or would be in dry-run)"
    )
    now_eligible: bool = Field(False, description="Whether adapter is now eligible after installation")
    eligibility: Optional[AdapterAvailabilityStatus] = Field(
        None, description="Updated eligibility status after installation"
    )

    model_config = ConfigDict(extra="forbid")


class RecheckEligibilityResponse(BaseModel):
    """Response from eligibility recheck."""

    name: str = Field(..., description="Adapter name")
    eligible: bool = Field(..., description="Current eligibility status")
    eligibility_reason: Optional[str] = Field(None, description="Reason if not eligible")
    missing_binaries: List[str] = Field(default_factory=list)
    missing_env_vars: List[str] = Field(default_factory=list)
    missing_config: List[str] = Field(default_factory=list)
    can_install: bool = Field(False, description="Whether install hints are available")

    model_config = ConfigDict(extra="forbid")
