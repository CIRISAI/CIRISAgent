"""
Wise Authority resource for CIRIS v1 API (Pre-Beta).

**WARNING**: This SDK is for the v1 API which is in pre-beta stage.
The API interfaces may change without notice.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from ..transport import Transport


class WAStatus(BaseModel):
    """WA service status."""

    service_healthy: bool = Field(..., description="Whether service is healthy")
    active_was: int = Field(..., description="Number of active WAs")
    pending_deferrals: int = Field(..., description="Number of pending deferrals")

    model_config = ConfigDict(extra="allow")


class WAGuidance(BaseModel):
    """WA guidance response."""

    guidance: str = Field(..., description="Guidance text")
    wa_id: str = Field(..., description="WA that provided guidance")
    confidence: float = Field(..., description="Confidence score")

    model_config = ConfigDict(extra="allow")


class WiseAuthorityResource:
    """Client for interacting with Wise Authority endpoints."""

    def __init__(self, transport: Transport):
        self._transport = transport

    async def get_deferrals(
        self, status: Optional[str] = None, cursor: Optional[str] = None, limit: int = 100
    ) -> Dict[str, Any]:
        """Get list of deferrals with cursor pagination.

        Args:
            status: Filter by status (pending, resolved, expired)
            cursor: Pagination cursor from previous response
            limit: Maximum number of deferrals to return

        Returns:
            Dict containing deferrals list, cursor, and pagination info
        """
        params: Dict[str, Any] = {"limit": limit}
        if status:
            params["status"] = status
        if cursor:
            params["cursor"] = cursor

        data = await self._transport.request("GET", "/v1/wa/deferrals", params=params)
        assert data is not None
        return data

    async def resolve_deferral(
        self, deferral_id: str, resolution: str, guidance: Optional[str] = None, reasoning: Optional[str] = None
    ) -> Dict[str, Any]:
        """Resolve a deferral with integrated guidance.

        Args:
            deferral_id: The ID of the deferral to resolve
            resolution: The resolution decision (e.g., "approved", "rejected", "modified")
            guidance: Optional guidance for the agent
            reasoning: Optional explanation of the decision

        Returns:
            Dict containing the resolved deferral details
        """
        payload: Dict[str, Any] = {"resolution": resolution}
        if guidance:
            payload["guidance"] = guidance
        if reasoning:
            payload["reasoning"] = reasoning

        data = await self._transport.request("POST", f"/v1/wa/deferrals/{deferral_id}/resolve", json=payload)
        assert data is not None
        return data

    async def get_permissions(
        self, resource_type: Optional[str] = None, permission_type: Optional[str] = None, active_only: bool = True
    ) -> Dict[str, Any]:
        """Get current permissions.

        Args:
            resource_type: Filter by resource type
            permission_type: Filter by permission type
            active_only: Only return active permissions

        Returns:
            Dict containing permissions list
        """
        params: Dict[str, Any] = {"active_only": active_only}
        if resource_type:
            params["resource_type"] = resource_type
        if permission_type:
            params["permission_type"] = permission_type

        data = await self._transport.request("GET", "/v1/wa/permissions", params=params)
        assert data is not None
        return data

    # Helper methods for common operations

    async def get_pending_deferrals(self) -> List[Dict[str, Any]]:
        """Get all pending deferrals."""
        result = await self.get_deferrals(status="pending")
        deferrals: List[Dict[str, Any]] = result.get("deferrals", [])
        return deferrals

    async def approve_deferral(self, deferral_id: str, guidance: Optional[str] = None) -> Dict[str, Any]:
        """Approve a deferral with optional guidance."""
        return await self.resolve_deferral(deferral_id=deferral_id, resolution="approved", guidance=guidance)

    async def reject_deferral(self, deferral_id: str, reasoning: str) -> Dict[str, Any]:
        """Reject a deferral with reasoning."""
        return await self.resolve_deferral(deferral_id=deferral_id, resolution="rejected", reasoning=reasoning)

    async def modify_deferral(self, deferral_id: str, guidance: str, reasoning: Optional[str] = None) -> Dict[str, Any]:
        """Modify a deferral with new guidance."""
        return await self.resolve_deferral(
            deferral_id=deferral_id, resolution="modified", guidance=guidance, reasoning=reasoning
        )

    # Aliases for backward compatibility with tests
    async def status(self) -> WAStatus:
        """Get WA service status."""
        data = await self._transport.request("GET", "/v1/wa/status")
        assert data is not None
        return WAStatus(**data)

    async def guidance(self, topic: str, context: Optional[str] = None) -> WAGuidance:
        """Request guidance from WA."""
        payload: Dict[str, Any] = {"topic": topic}
        if context:
            payload["context"] = context

        data = await self._transport.request("POST", "/v1/wa/guidance", json=payload)
        assert data is not None
        return WAGuidance(**data)
