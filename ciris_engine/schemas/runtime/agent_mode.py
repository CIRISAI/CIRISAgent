"""
AgentMode schema for CIRIS.

Defines the global runtime mode for an agent occurrence. The mode is a
first-class config (visible to all services), NOT a service of its own.

Three modes:
- CLIENT: egress-only, minimal queue, no listener.
- PROXY (default): bidirectional, listens, forwards.
- SERVER: always-on listener, public node, requires >= 256 GiB free disk.

Reference pattern: ``agent_occurrence_id`` on
``ciris_engine/schemas/config/essential.py`` (EssentialConfig).
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class AgentMode(str, Enum):
    """Global runtime mode for an agent occurrence."""

    CLIENT = "client"
    PROXY = "proxy"
    SERVER = "server"


class AgentModeStatus(BaseModel):
    """Snapshot of the current agent mode and the disk facts that gate SERVER."""

    mode: AgentMode = Field(..., description="Current active agent mode")
    available_disk_bytes: int = Field(
        ...,
        ge=0,
        description="Free disk bytes on the data directory at the moment the snapshot was taken",
    )
    server_minimum_disk_bytes: int = Field(
        ...,
        ge=0,
        description="Minimum free disk bytes required to switch to SERVER mode",
    )
    server_eligible: bool = Field(
        ...,
        description="True when available_disk_bytes >= server_minimum_disk_bytes",
    )
    data_dir: str = Field(
        ...,
        description="Filesystem path the disk measurement was taken against",
    )

    model_config = ConfigDict(defer_build=True, extra="forbid")


class AgentModeUpdateRequest(BaseModel):
    """Request body for PUT /v1/system/agent-mode."""

    mode: AgentMode = Field(..., description="Mode to switch to")

    model_config = ConfigDict(defer_build=True, extra="forbid")


class AgentModeChangedEvent(BaseModel):
    """Event broadcast by AgentModeBroker when the mode transitions."""

    previous_mode: AgentMode = Field(..., description="Mode before the transition")
    new_mode: AgentMode = Field(..., description="Mode after the transition")
    timestamp: datetime = Field(..., description="UTC timestamp of the transition")

    model_config = ConfigDict(defer_build=True, extra="forbid")
