"""
Tool schemas for adapter-provided tools.

Tools are provided by adapters (Discord, API, CLI) not by the runtime.
This is the single source of truth for all tool-related schemas.
"""

from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from ciris_engine.schemas.platform import PlatformRequirement
from ciris_engine.schemas.types import JSONDict


class ToolExecutionStatus(str, Enum):
    """Status of tool execution."""

    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"
    NOT_FOUND = "not_found"
    UNAUTHORIZED = "unauthorized"


class ToolParameterSchema(BaseModel):
    """Schema definition for tool parameters."""

    type: str = Field(..., description="JSON Schema type")
    properties: JSONDict = Field(..., description="Parameter properties")
    required: List[str] = Field(default_factory=list, description="Required parameters")

    model_config = ConfigDict(extra="forbid", defer_build=True)


# ============================================================================
# Tool Requirements Schemas
# ============================================================================


class BinaryRequirement(BaseModel):
    """A required CLI binary or executable."""

    name: str = Field(..., description="Binary name (e.g., 'ffmpeg', 'git')")
    min_version: Optional[str] = Field(None, description="Minimum version (semver)")
    verify_command: Optional[str] = Field(None, description="Command to verify installation (e.g., 'ffmpeg -version')")

    model_config = ConfigDict(extra="forbid", defer_build=True)


class EnvVarRequirement(BaseModel):
    """A required environment variable."""

    name: str = Field(..., description="Environment variable name")
    description: Optional[str] = Field(None, description="What this variable is for")
    secret: bool = Field(False, description="Whether this is a secret (affects display)")

    model_config = ConfigDict(extra="forbid", defer_build=True)


class ConfigRequirement(BaseModel):
    """A required CIRIS configuration key."""

    key: str = Field(..., description="Config key path (e.g., 'adapters.home_assistant.token')")
    description: Optional[str] = Field(None, description="What this config is for")

    model_config = ConfigDict(extra="forbid", defer_build=True)


class ToolRequirements(BaseModel):
    """Runtime requirements for a tool to function."""

    binaries: List[BinaryRequirement] = Field(
        default_factory=list, description="Required CLI binaries (all must be present)"
    )
    any_binaries: List[BinaryRequirement] = Field(
        default_factory=list, description="Alternative binaries (at least one required)"
    )
    env_vars: List[EnvVarRequirement] = Field(default_factory=list, description="Required environment variables")
    config_keys: List[ConfigRequirement] = Field(default_factory=list, description="Required CIRIS config keys")
    platforms: List[str] = Field(
        default_factory=list, description="Supported platforms (darwin, linux, win32). Empty = all"
    )

    model_config = ConfigDict(extra="forbid", defer_build=True)


# ============================================================================
# Installation Schemas
# ============================================================================


class InstallStep(BaseModel):
    """A single installation step for a tool dependency."""

    id: str = Field(..., description="Unique step identifier")
    kind: str = Field(..., description="Install method: brew, apt, pip, npm, manual, winget, choco")
    label: str = Field(..., description="Human-readable step description")
    formula: Optional[str] = Field(None, description="Package name for brew")
    package: Optional[str] = Field(None, description="Package name for apt/pip/npm")
    command: Optional[str] = Field(None, description="Command for manual installation")
    url: Optional[str] = Field(None, description="URL for manual download/documentation")
    target_dir: Optional[str] = Field(None, description="Extraction target directory for 'download' kind")
    strip_components: Optional[int] = Field(
        None, description="Leading path components to strip when extracting a 'download' archive (tar-style)"
    )
    provides_binaries: List[str] = Field(default_factory=list, description="Binary names this step provides")
    verify_command: Optional[str] = Field(None, description="Command to verify success")
    platforms: List[str] = Field(default_factory=list, description="Platforms this step applies to. Empty = all")

    model_config = ConfigDict(extra="forbid", defer_build=True)


# ============================================================================
# Documentation Schemas
# ============================================================================


class UsageExample(BaseModel):
    """A code example showing how to use a tool."""

    title: str = Field(..., description="Example title")
    description: Optional[str] = Field(None, description="What this example demonstrates")
    code: str = Field(..., description="The example code/parameters")
    language: str = Field("json", description="Code language for syntax highlighting")

    model_config = ConfigDict(extra="forbid", defer_build=True)


class ToolGotcha(BaseModel):
    """A common pitfall or gotcha when using a tool."""

    title: str = Field(..., description="Short gotcha title")
    description: str = Field(..., description="Detailed explanation of the pitfall")
    severity: str = Field("warning", description="Severity: info, warning, error")

    model_config = ConfigDict(extra="forbid", defer_build=True)


class ToolDocumentation(BaseModel):
    """Rich documentation for a tool."""

    quick_start: Optional[str] = Field(None, description="TL;DR quick start guide")
    detailed_instructions: Optional[str] = Field(None, description="Full markdown documentation")
    examples: List[UsageExample] = Field(default_factory=list, description="Usage examples")
    gotchas: List[ToolGotcha] = Field(default_factory=list, description="Common pitfalls")
    related_tools: List[str] = Field(default_factory=list, description="Names of related tools")
    homepage: Optional[str] = Field(None, description="Tool homepage URL")
    docs_url: Optional[str] = Field(None, description="Documentation URL")

    model_config = ConfigDict(extra="forbid", defer_build=True)


# ============================================================================
# DMA Guidance Schema
# ============================================================================


class ToolDMAGuidance(BaseModel):
    """Guidance for the Decision-Making Architecture when selecting this tool."""

    when_not_to_use: Optional[str] = Field(None, description="Conditions when this tool should NOT be used")
    ethical_considerations: Optional[str] = Field(None, description="Ethical considerations for using this tool")
    prerequisite_actions: List[str] = Field(
        default_factory=list, description="Actions that should be taken before this tool"
    )
    followup_actions: List[str] = Field(
        default_factory=list, description="Actions to consider after this tool completes"
    )
    min_confidence: float = Field(0.0, ge=0.0, le=1.0, description="Minimum confidence score to use this tool")
    requires_approval: bool = Field(False, description="Whether this tool requires wise authority approval")

    model_config = ConfigDict(extra="forbid", defer_build=True)


# ============================================================================
# ToolInfo (Enhanced)
# ============================================================================


class ToolInfo(BaseModel):
    """Information about a tool provided by an adapter."""

    name: str = Field(..., description="Tool name")
    description: str = Field(..., description="What the tool does")
    parameters: ToolParameterSchema = Field(..., description="Tool parameters schema")
    category: str = Field("general", description="Tool category")
    cost: float = Field(0.0, description="Cost to execute the tool")
    when_to_use: Optional[str] = Field(None, description="Guidance on when to use the tool")

    # Context enrichment: if True, this tool is automatically run during context gathering
    # and its results are added to the system snapshot for use in action selection
    context_enrichment: bool = Field(
        False,
        description="If True, tool is automatically run during context gathering to enrich ASPDMA prompt",
    )
    # Default parameters to use when running as context enrichment tool
    context_enrichment_params: Optional[JSONDict] = Field(
        None, description="Default parameters when running as context enrichment (e.g., {'domain': 'light'})"
    )

    # Platform requirements: security/platform features required to use this tool
    # If not satisfied, the tool will not be available in the agent's tool list
    platform_requirements: List[PlatformRequirement] = Field(
        default_factory=list,
        description="Platform security requirements (e.g., ANDROID_PLAY_INTEGRITY, DPOP)",
    )
    # Human-readable explanation of why platform requirements exist
    platform_requirements_rationale: Optional[str] = Field(
        None,
        description="Why these requirements exist (shown if requirements not met)",
    )

    # === NEW FIELDS (skill-like rich documentation) ===

    # Runtime requirements (binaries, env vars, config)
    requirements: Optional[ToolRequirements] = Field(
        None, description="Runtime requirements (binaries, env vars, config keys)"
    )

    # Installation steps for dependencies
    install_steps: List[InstallStep] = Field(
        default_factory=list, description="Installation steps for tool dependencies"
    )

    # Rich documentation
    documentation: Optional[ToolDocumentation] = Field(
        None, description="Rich documentation (quick start, examples, gotchas)"
    )

    # DMA guidance for tool selection
    dma_guidance: Optional[ToolDMAGuidance] = Field(None, description="Guidance for DMA tool selection decisions")

    # Categorization tags
    tags: List[str] = Field(
        default_factory=list, description="Categorization tags for discovery (e.g., 'weather', 'api')"
    )

    # Tool version
    version: Optional[str] = Field(None, description="Tool version string")

    model_config = ConfigDict(extra="forbid", defer_build=True)


# ============================================================================
# Tool Disclosure (first-run consent surface)
# ============================================================================


class ToolCapabilityFlag(str, Enum):
    """A consequential capability a tool grants, derived from its live ToolInfo.

    These are NOT hand-assigned per tool. They are derived structurally from the
    tool's declared parameter schema (and ``dma_guidance``) by
    ``ciris_engine.logic.services.tool.tool_disclosure.derive_capability_flags``,
    so a newly-registered tool with the same parameter shape is flagged
    automatically and a disclosure list cannot silently drift from the code.
    """

    NETWORK_FETCH = "network_fetch"
    CUSTOM_HEADERS = "custom_headers"
    REQUEST_BODY = "request_body"
    SHELL_EXECUTION = "shell_execution"
    FILE_READ = "file_read"
    FILE_WRITE = "file_write"
    SECRET_PLAINTEXT = "secret_plaintext"
    AFFECTS_OTHER_PEOPLE = "affects_other_people"
    REQUIRES_APPROVAL = "requires_approval"


class ToolDisclosureSource(str, Enum):
    """Where a disclosed tool list was read from, so the UI can be honest about it."""

    RUNTIME = "runtime"
    """Read from a tool service that is registered and running right now."""

    PROSPECTIVE = "prospective"
    """Read from the adapter's own tool service before the adapter is loaded.

    This is the real ``get_all_tool_info()`` output, not a transcription of it,
    but the adapter has not been configured with live credentials yet.
    """

    UNAVAILABLE = "unavailable"
    """The tool list cannot be read until the adapter loads.

    Disclosed as unknown rather than omitted -- an empty list would read as
    "grants nothing", which would be false.
    """


class ToolDisclosure(BaseModel):
    """One tool, described for a human deciding whether to grant it.

    Every field is copied from the live ``ToolInfo`` or derived from it. Nothing
    here is authored per-tool by hand.
    """

    name: str = Field(..., description="Tool name, verbatim from the tool service")
    description: str = Field(..., description="Tool description, verbatim from the tool service")
    category: str = Field("general", description="Tool category, verbatim from the tool service")
    model_authored_parameters: List[str] = Field(
        default_factory=list,
        description="Parameter names the model fills in itself when it calls this tool",
    )
    capability_flags: List[ToolCapabilityFlag] = Field(
        default_factory=list, description="Consequential capabilities derived from the parameter schema"
    )

    model_config = ConfigDict(extra="forbid", defer_build=True)


class AdapterToolDisclosure(BaseModel):
    """Every tool one wizard choice grants (or that no choice controls)."""

    adapter_id: str = Field(..., description="Adapter id, matching the setup wizard's adapter list")
    adapter_name: str = Field(..., description="Human-readable display name")
    always_on: bool = Field(
        False, description="True if these tools are registered regardless of any wizard choice"
    )
    source: ToolDisclosureSource = Field(..., description="Where this tool list was read from")
    source_note: Optional[str] = Field(None, description="Plain-language caveat when the list is not complete")
    tools: List[ToolDisclosure] = Field(default_factory=list, description="Tools this choice grants")

    model_config = ConfigDict(extra="forbid", defer_build=True)


class ToolDisclosureReport(BaseModel):
    """The complete tool disclosure shown at the first-run consent point."""

    adapters: List[AdapterToolDisclosure] = Field(
        default_factory=list, description="Tool grants controlled by an adapter choice"
    )
    always_on: List[AdapterToolDisclosure] = Field(
        default_factory=list, description="Tool grants no wizard choice controls and that cannot be declined"
    )
    total_tools: int = Field(0, description="Total number of disclosed tools across every group")

    model_config = ConfigDict(extra="forbid", defer_build=True)


class ToolResult(BaseModel):
    """Result from tool execution."""

    success: bool = Field(..., description="Whether execution succeeded")
    data: Optional[JSONDict] = Field(None, description="Result data")
    error: Optional[str] = Field(None, description="Error message if failed")

    model_config = ConfigDict(extra="forbid", defer_build=True)


class ToolExecutionResult(BaseModel):
    """Complete tool execution result with metadata."""

    tool_name: str = Field(..., description="Name of executed tool")
    status: ToolExecutionStatus = Field(..., description="Execution status")
    success: bool = Field(..., description="Whether execution succeeded")
    data: Optional[JSONDict] = Field(None, description="Result data")
    error: Optional[str] = Field(None, description="Error message if failed")
    correlation_id: str = Field(..., description="Correlation ID for tracking")

    model_config = ConfigDict(extra="forbid", defer_build=True)


__all__ = [
    # Execution
    "ToolExecutionStatus",
    "ToolExecutionResult",
    "ToolResult",
    # Core
    "ToolParameterSchema",
    "ToolInfo",
    # Requirements
    "BinaryRequirement",
    "EnvVarRequirement",
    "ConfigRequirement",
    "ToolRequirements",
    # Installation
    "InstallStep",
    # Documentation
    "UsageExample",
    "ToolGotcha",
    "ToolDocumentation",
    # DMA Guidance
    "ToolDMAGuidance",
    # Disclosure (first-run consent surface)
    "ToolCapabilityFlag",
    "ToolDisclosureSource",
    "ToolDisclosure",
    "AdapterToolDisclosure",
    "ToolDisclosureReport",
]
