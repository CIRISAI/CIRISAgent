"""Audit Service Protocol."""

from abc import abstractmethod
from datetime import datetime
from typing import TYPE_CHECKING, List, Optional, Protocol

if TYPE_CHECKING:
    from ciris_engine.schemas.audit.core import EventPayload, AuditLogEntry
    from ciris_engine.schemas.audit.hash_chain import AuditEntryResult

from ciris_engine.schemas.runtime.audit import AuditActionContext
from ciris_engine.schemas.runtime.enums import HandlerActionType
from ciris_engine.schemas.services.graph.audit import AuditQuery, VerificationReport
from ciris_engine.schemas.services.nodes import AuditEntry

from ...runtime.base import GraphServiceProtocol


class AuditServiceProtocol(GraphServiceProtocol, Protocol):
    """Protocol for audit service."""

    @abstractmethod
    async def log_action(
        self, action_type: HandlerActionType, context: AuditActionContext, outcome: Optional[str] = None
    ) -> "AuditEntryResult":
        """Log an action to the audit trail.

        Returns:
            AuditEntryResult with entry_id and hash chain data (REQUIRED)
        """
        ...

    @abstractmethod
    async def log_event(self, event_type: str, event_data: "EventPayload", **kwargs: object) -> "AuditEntryResult":
        """Log a general audit event.

        Returns:
            AuditEntryResult with entry_id and hash chain data (if hash chain enabled)
        """
        ...

    @abstractmethod
    async def log_conscience_event(
        self, thought_id: str, decision: str, reasoning: str, metadata: Optional["EventPayload"] = None
    ) -> None:
        """Log a conscience decision event."""
        ...

    @abstractmethod
    async def get_audit_trail(
        self, entity_id: Optional[str] = None, hours: int = 24, action_types: Optional[List[str]] = None
    ) -> List[AuditEntry]:
        """Get audit trail for an entity."""
        ...

    @abstractmethod
    async def query_audit_trail(self, query: AuditQuery) -> List[AuditEntry]:
        """Query audit trail with advanced filters."""
        ...

    @abstractmethod
    async def verify_audit_integrity(self) -> VerificationReport:
        """Verify audit trail integrity."""
        ...

    @abstractmethod
    async def get_verification_report(self) -> VerificationReport:
        """Get detailed verification report."""
        ...

    @abstractmethod
    async def export_audit_data(
        self, start_time: Optional[datetime] = None, end_time: Optional[datetime] = None, format: str = "jsonl"
    ) -> str:
        """Export audit data."""
        ...

    @abstractmethod
    async def query_events(
        self,
        event_type: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 100,
    ) -> List["AuditLogEntry"]:
        """Query audit events."""
        ...

    @abstractmethod
    async def get_event_by_id(self, event_id: str) -> Optional["AuditLogEntry"]:
        """Get specific audit event."""
        ...
