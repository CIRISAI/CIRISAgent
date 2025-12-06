"""
Runtime bootstrap configuration schema.

This replaces the raw **kwargs pattern in CIRISRuntime.__init__ with strongly-typed configuration.
Follows CIRIS philosophy: No Untyped Dicts, No Bypass Patterns, No Exceptions.
"""

from typing import Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from ciris_engine.schemas.runtime.adapter_management import AdapterConfig, AdapterLoadRequest


class RuntimeBootstrapConfig(BaseModel):
    """
    Strongly-typed bootstrap configuration for CIRIS Runtime.

    This replaces the raw **kwargs pattern with explicit, validated configuration.
    All runtime initialization parameters are declared here - no hidden parameters allowed.
    """

    adapters: List[AdapterLoadRequest] = Field(default_factory=list, description="List of adapters to load at startup")
    adapter_overrides: Dict[str, AdapterConfig] = Field(
        default_factory=dict,
        description="Adapter-specific configuration overrides keyed by adapter ID (e.g. 'discord:main', not just 'discord')",
    )
    modules: List[str] = Field(default_factory=list, description="External modules to load (e.g., 'mock_llm')")
    startup_channel_id: Optional[str] = Field(None, description="Channel ID for startup messages")
    debug: bool = Field(False, description="Enable debug mode")
    preload_tasks: List[str] = Field(default_factory=list, description="Tasks to preload after WORK state transition")

    model_config = ConfigDict(extra="forbid")  # No additional parameters allowed - all must be declared explicitly
