"""Wise Authority Service Protocol.

Handles authorization, deferrals, and decision guidance.
Authorization = "What can you do?"
"""

from abc import abstractmethod
from typing import List, Optional, Protocol

from ciris_engine.schemas.services.authority.wise_authority import PendingDeferral
from ciris_engine.schemas.services.authority_core import (
    DeferralApprovalContext,
    DeferralRequest,
    DeferralResponse,
    GuidanceRequest,
    GuidanceResponse,
    WAPermission,
)
from ciris_engine.schemas.services.context import GuidanceContext

from ...runtime.base import ServiceProtocol


class WiseAuthorityServiceProtocol(ServiceProtocol, Protocol):
    """Protocol for wise authority service - authorization and guidance."""

    @abstractmethod
    async def check_authorization(self, wa_id: str, action: str, resource: Optional[str] = None) -> bool:
        """Check if a WA is authorized for an action on a resource."""
        ...

    @abstractmethod
    async def request_approval(self, action: str, context: DeferralApprovalContext) -> bool:
        """Request approval for an action - may defer to human."""
        ...

    @abstractmethod
    async def get_guidance(self, request: GuidanceRequest) -> GuidanceResponse:
        """Get guidance for a situation."""
        ...

    @abstractmethod
    async def send_deferral(self, deferral: DeferralRequest) -> str:
        """Send a decision deferral to human WAs."""
        ...

    @abstractmethod
    async def get_pending_deferrals(self, wa_id: Optional[str] = None) -> List[PendingDeferral]:
        """Get pending deferrals (optionally filtered by WA)."""
        ...

    @abstractmethod
    async def resolve_deferral(self, deferral_id: str, response: DeferralResponse) -> bool:
        """Resolve a deferred decision."""
        ...

    @abstractmethod
    async def grant_permission(self, wa_id: str, permission: str, resource: Optional[str] = None) -> bool:
        """Grant a permission to a WA."""
        ...

    @abstractmethod
    async def revoke_permission(self, wa_id: str, permission: str, resource: Optional[str] = None) -> bool:
        """Revoke a permission from a WA."""
        ...

    @abstractmethod
    async def list_permissions(self, wa_id: str) -> List[WAPermission]:
        """List all permissions for a WA."""
        ...

    @abstractmethod
    async def fetch_guidance(self, context: GuidanceContext) -> Optional[str]:
        """Fetch guidance from WAs (WiseBus-compatible method)."""
        ...
