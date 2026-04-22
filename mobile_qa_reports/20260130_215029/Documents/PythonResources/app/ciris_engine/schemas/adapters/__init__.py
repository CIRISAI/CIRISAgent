"""
Adapter-specific schemas.

These schemas are used for adapter registration and management.
"""

from .registration import AdapterServiceRegistration
from .runtime_context import AdapterStartupContext
from .tools import (
    BinaryRequirement,
    ConfigRequirement,
    EnvVarRequirement,
    InstallStep,
    ToolDMAGuidance,
    ToolDocumentation,
    ToolExecutionResult,
    ToolExecutionStatus,
    ToolGotcha,
    ToolInfo,
    ToolParameterSchema,
    ToolRequirements,
    ToolResult,
    UsageExample,
)

__all__ = [
    # Registration
    "AdapterServiceRegistration",
    "AdapterStartupContext",
    # Tools
    "BinaryRequirement",
    "ConfigRequirement",
    "EnvVarRequirement",
    "InstallStep",
    "ToolDMAGuidance",
    "ToolDocumentation",
    "ToolExecutionResult",
    "ToolExecutionStatus",
    "ToolGotcha",
    "ToolInfo",
    "ToolParameterSchema",
    "ToolRequirements",
    "ToolResult",
    "UsageExample",
]
