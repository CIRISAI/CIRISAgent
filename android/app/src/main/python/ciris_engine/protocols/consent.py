"""
Consent Protocol Interface - FAIL FAST, NO FALLBACKS.

Defines the contract for consent management.
"""

from abc import abstractmethod
from datetime import datetime
from typing import List, Optional, Protocol

from ciris_engine.schemas.consent.core import (
    ConsentAuditEntry,
    ConsentCategory,
    ConsentDecayStatus,
    ConsentImpactReport,
    ConsentRequest,
    ConsentStatus,
    ConsentStream,
)


class ConsentManagerProtocol(Protocol):
    """
    Protocol for managing user consent.
    NO FAKE DATA - if consent doesn't exist, FAIL FAST.
    """

    @abstractmethod
    async def get_consent(self, user_id: str) -> ConsentStatus:
        """
        Get user's consent status.
        MUST raise if user doesn't exist.
        NO DEFAULT FALLBACK.
        """
        ...

    @abstractmethod
    async def grant_consent(self, request: ConsentRequest) -> ConsentStatus:
        """
        Grant or update consent.
        MUST validate request.
        MUST create audit entry.
        """
        ...

    @abstractmethod
    async def revoke_consent(self, user_id: str, reason: Optional[str] = None) -> ConsentDecayStatus:
        """
        Start decay protocol for user.
        MUST initiate 90-day decay.
        MUST sever identity immediately.
        """
        ...

    @abstractmethod
    async def check_expiry(self, user_id: str) -> bool:
        """
        Check if TEMPORARY consent has expired.
        Returns True if expired and needs cleanup.
        NO GRACE PERIOD.
        """
        ...

    @abstractmethod
    async def get_impact_report(self, user_id: str) -> ConsentImpactReport:
        """
        Generate impact report for user.
        REAL DATA ONLY.
        MUST fail if user doesn't exist.
        """
        ...

    @abstractmethod
    async def get_audit_trail(self, user_id: str, limit: int = 100) -> List[ConsentAuditEntry]:
        """
        Get consent change history.
        IMMUTABLE AUDIT TRAIL.
        """
        ...

    @abstractmethod
    async def cleanup_expired(self) -> int:
        """
        Clean up all expired TEMPORARY consents.
        Returns count of cleaned records.
        HARD DELETE after 14 days.
        """
        ...
