"""Audit Service Protocol."""

from typing import Protocol, List, Optional
from abc import abstractmethod
from datetime import datetime

from ...runtime.base import GraphServiceProtocol
from ciris_engine.schemas.services.nodes import AuditEntry
from ciris_engine.schemas.services.graph.audit import AuditQuery, VerificationReport
from ciris_engine.schemas.runtime.enums import HandlerActionType

class AuditServiceProtocol(GraphServiceProtocol, Protocol):
    """Protocol for audit service."""
    
    @abstractmethod
    async def log_action(
        self,
        action: HandlerActionType,
        actor_id: str,
        thought_id: Optional[str] = None,
        task_id: Optional[str] = None,
        context: Optional[dict] = None,
        metadata: Optional[dict] = None
    ) -> None:
        """Log an action to the audit trail."""
        ...
    
    @abstractmethod
    async def log_event(self, event_type: str, event_data: dict, **kwargs: object) -> None:
        """Log a general audit event."""
        ...
    
    @abstractmethod
    async def log_conscience_event(
        self,
        thought_id: str,
        decision: str,
        reasoning: str,
        confidence: float,
        metadata: Optional[dict] = None
    ) -> None:
        """Log a conscience decision event."""
        ...
    
    @abstractmethod
    async def get_audit_trail(
        self,
        entity_id: Optional[str] = None,
        hours: int = 24,
        action_types: Optional[List[str]] = None
    ) -> List[AuditEntry]:
        """Get audit trail for an entity."""
        ...
    
    @abstractmethod
    async def query_audit_trail(
        self,
        query: AuditQuery
    ) -> List[AuditEntry]:
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
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        format: str = 'jsonl'
    ) -> str:
        """Export audit data."""
        ...
    
    @abstractmethod
    async def query_events(
        self,
        event_type: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 100
    ) -> List[dict]:
        """Query audit events."""
        ...
    
    @abstractmethod
    async def get_event_by_id(self, event_id: str) -> Optional[dict]:
        """Get specific audit event."""
        ...
    
    @abstractmethod
    def set_service_registry(self, registry: object) -> None:
        """Set the service registry."""
        ...