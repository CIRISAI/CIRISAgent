"""Consent management resource for CIRIS SDK."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from ..transport import Transport


class ConsentAction(str, Enum):
    """Types of consent actions."""

    GRANT = "GRANT"
    REVOKE = "REVOKE"
    QUERY = "QUERY"


class ConsentScope(str, Enum):
    """Scopes for consent."""

    FULL = "FULL"
    LIMITED = "LIMITED"
    MINIMAL = "MINIMAL"


class ConsentStatus(str, Enum):
    """Status of consent."""

    ACTIVE = "ACTIVE"
    REVOKED = "REVOKED"
    EXPIRED = "EXPIRED"
    PENDING = "PENDING"


class ConsentRequest(BaseModel):
    """Request for consent management."""

    user_id: str = Field(..., description="User ID")
    action: ConsentAction = Field(..., description="Action to perform")
    scope: Optional[ConsentScope] = Field(None, description="Scope of consent")
    purpose: Optional[str] = Field(None, description="Purpose of consent")
    duration_hours: Optional[int] = Field(None, description="Duration in hours")
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Additional metadata")


class ConsentRecord(BaseModel):
    """A consent record."""

    id: str = Field(..., description="Consent record ID")
    user_id: str = Field(..., description="User ID")
    status: ConsentStatus = Field(..., description="Current status")
    scope: ConsentScope = Field(..., description="Scope of consent")
    purpose: Optional[str] = Field(None, description="Purpose of consent")
    granted_at: datetime = Field(..., description="When consent was granted")
    expires_at: Optional[datetime] = Field(None, description="When consent expires")
    revoked_at: Optional[datetime] = Field(None, description="When consent was revoked")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")


class ConsentResponse(BaseModel):
    """Response from consent operations."""

    success: bool = Field(..., description="Whether operation succeeded")
    consent: Optional[ConsentRecord] = Field(None, description="Consent record")
    message: Optional[str] = Field(None, description="Status message")


class ConsentQueryResponse(BaseModel):
    """Response from consent query."""

    consents: List[ConsentRecord] = Field(..., description="List of consent records")
    total: int = Field(..., description="Total number of records")


class ConsentResource:
    """
    Consent management client for v1 API.

    Manages user consent for data processing and agent actions.
    Implements GDPR-compliant consent tracking with granular scopes.
    """

    def __init__(self, transport: Transport):
        self._transport = transport

    async def grant(
        self,
        user_id: str,
        scope: ConsentScope = ConsentScope.LIMITED,
        purpose: Optional[str] = None,
        duration_hours: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ConsentResponse:
        """
        Grant consent for a user.

        Args:
            user_id: ID of the user granting consent
            scope: Scope of consent (FULL, LIMITED, MINIMAL)
            purpose: Purpose for which consent is granted
            duration_hours: How long consent is valid (None = indefinite)
            metadata: Additional metadata to store

        Returns:
            ConsentResponse with the consent record

        Example:
            # Grant limited consent for 24 hours
            result = await client.consent.grant(
                user_id="user123",
                scope=ConsentScope.LIMITED,
                purpose="conversation_analysis",
                duration_hours=24
            )
        """
        payload = ConsentRequest(
            user_id=user_id,
            action=ConsentAction.GRANT,
            scope=scope,
            purpose=purpose,
            duration_hours=duration_hours,
            metadata=metadata or {},
        )

        result = await self._transport.request("POST", "/v1/consent/manage", json=payload.dict(exclude_none=True))

        if isinstance(result, dict) and "data" in result:
            return ConsentResponse(**result["data"])
        return ConsentResponse(**result)

    async def revoke(self, user_id: str) -> ConsentResponse:
        """
        Revoke consent for a user.

        Args:
            user_id: ID of the user revoking consent

        Returns:
            ConsentResponse confirming revocation

        Example:
            result = await client.consent.revoke("user123")
            if result.success:
                print("Consent revoked successfully")
        """
        payload = ConsentRequest(user_id=user_id, action=ConsentAction.REVOKE)

        result = await self._transport.request("POST", "/v1/consent/manage", json=payload.dict(exclude_none=True))

        if isinstance(result, dict) and "data" in result:
            return ConsentResponse(**result["data"])
        return ConsentResponse(**result)

    async def query(
        self,
        user_id: Optional[str] = None,
        status: Optional[ConsentStatus] = None,
        scope: Optional[ConsentScope] = None,
    ) -> ConsentQueryResponse:
        """
        Query consent records.

        Args:
            user_id: Filter by user ID (optional)
            status: Filter by status (optional)
            scope: Filter by scope (optional)

        Returns:
            ConsentQueryResponse with matching records

        Example:
            # Get all active consents
            active = await client.consent.query(status=ConsentStatus.ACTIVE)

            # Get consent for specific user
            user_consent = await client.consent.query(user_id="user123")
        """
        params = {}
        if user_id:
            params["user_id"] = user_id
        if status:
            params["status"] = status.value
        if scope:
            params["scope"] = scope.value

        result = await self._transport.request("GET", "/v1/consent/query", params=params)

        if isinstance(result, dict) and "data" in result:
            return ConsentQueryResponse(**result["data"])
        return ConsentQueryResponse(**result)

    async def check(self, user_id: str) -> bool:
        """
        Check if a user has active consent.

        Args:
            user_id: ID of the user to check

        Returns:
            True if user has active consent, False otherwise

        Example:
            if await client.consent.check("user123"):
                # User has active consent
                await process_user_data()
        """
        result = await self.query(user_id=user_id, status=ConsentStatus.ACTIVE)
        return len(result.consents) > 0

    async def get_active(self) -> List[ConsentRecord]:
        """
        Get all active consent records.

        Returns:
            List of active ConsentRecord objects
        """
        result = await self.query(status=ConsentStatus.ACTIVE)
        return result.consents

    async def get_user_consent(self, user_id: str) -> Optional[ConsentRecord]:
        """
        Get the current consent record for a user.

        Args:
            user_id: ID of the user

        Returns:
            ConsentRecord if found, None otherwise
        """
        result = await self.query(user_id=user_id, status=ConsentStatus.ACTIVE)
        if result.consents:
            return result.consents[0]
        return None
