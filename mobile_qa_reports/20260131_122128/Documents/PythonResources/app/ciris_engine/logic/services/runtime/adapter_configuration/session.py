"""
Configuration session model for adapter configuration workflows.

Tracks the state of an interactive adapter configuration session including
collected configuration data, current step, OAuth state, and session status.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional


class SessionStatus(str, Enum):
    """Status of a configuration session."""

    ACTIVE = "active"
    AWAITING_OAUTH = "awaiting_oauth"
    COMPLETED = "completed"
    FAILED = "failed"
    EXPIRED = "expired"


@dataclass
class AdapterConfigSession:
    """Tracks state of an adapter configuration workflow.

    This dataclass maintains all state for an interactive configuration session,
    including the current step, collected configuration data, and OAuth state
    when needed.

    Attributes:
        session_id: Unique identifier for this session
        adapter_type: Type of adapter being configured
        user_id: ID of user performing configuration
        current_step_index: Index of current step in workflow
        status: Current session status
        collected_config: Configuration data collected from completed steps
        step_results: Results from individual step executions
        created_at: Timestamp when session was created
        updated_at: Timestamp when session was last updated
        pkce_verifier: PKCE code verifier for OAuth flows (when applicable)

    Example:
        >>> session = AdapterConfigSession(
        ...     session_id="sess_123",
        ...     adapter_type="homeassistant",
        ...     user_id="user_456"
        ... )
        >>> session.collected_config["base_url"] = "https://homeassistant.local"
        >>> session.update()
    """

    session_id: str
    adapter_type: str
    user_id: str
    current_step_index: int = 0
    status: SessionStatus = SessionStatus.ACTIVE
    collected_config: Dict[str, Any] = field(default_factory=dict)
    step_results: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    pkce_verifier: Optional[str] = None

    def update(self) -> None:
        """Update the session's last modified timestamp."""
        self.updated_at = datetime.now(timezone.utc)
