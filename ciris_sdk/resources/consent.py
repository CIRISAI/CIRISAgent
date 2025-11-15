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

        result = await self._transport.request("POST", "/v1/consent/manage", json=payload.model_dump(exclude_none=True))

        if isinstance(result, dict) and "data" in result:
            return ConsentResponse(**result["data"])
        assert isinstance(result, dict), "Expected dict response from transport"
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

        result = await self._transport.request("POST", "/v1/consent/manage", json=payload.model_dump(exclude_none=True))

        if isinstance(result, dict) and "data" in result:
            return ConsentResponse(**result["data"])
        assert isinstance(result, dict), "Expected dict response from transport"
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
        assert isinstance(result, dict), "Expected dict response from transport"
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

    # ========== NEW CONSENT API METHODS (Consensual Evolution Protocol v0.2) ==========

    async def get_status(self) -> Dict[str, Any]:
        """
        Get current consent status for authenticated user.

        Returns:
            Dictionary with consent status including has_consent, stream, granted_at, expires_at

        Example:
            status = await client.consent.get_status()
            if status["has_consent"]:
                print(f"Stream: {status['stream']}")
        """
        result = await self._transport.request("GET", "/v1/consent/status")
        assert isinstance(result, dict), "Expected dict response from transport"
        return result

    async def query_consents(
        self,
        status: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Query consent records with optional filters.

        Args:
            status: Filter by status (ACTIVE, REVOKED, EXPIRED)
            user_id: Filter by user ID (admin only)

        Returns:
            Dictionary with consents list and total count

        Example:
            result = await client.consent.query_consents()
            print(f"Found {result['total']} consents")
        """
        params = {}
        if status:
            params["status"] = status
        if user_id:
            params["user_id"] = user_id

        result = await self._transport.request("GET", "/v1/consent/query", params=params)
        assert isinstance(result, dict), "Expected dict response from transport"
        return result

    async def grant_consent(
        self,
        stream: str,
        categories: Optional[List[str]] = None,
        reason: Optional[str] = None,
    ) -> Any:
        """
        Grant or update consent with specified stream and categories.

        Streams:
        - temporary: 14-day auto-forget (default)
        - partnered: Explicit consent for mutual growth (requires approval)
        - anonymous: Statistics only, no identity

        Args:
            stream: Consent stream (temporary, partnered, anonymous)
            categories: List of consent categories (required for partnered)
            reason: Reason for granting consent

        Returns:
            ConsentStatus-like object with stream, categories, etc.

        Example:
            result = await client.consent.grant_consent(
                stream="temporary",
                categories=["interaction"],
                reason="Testing consent"
            )
        """
        payload = {
            "user_id": "placeholder",  # Will be overridden by auth context on server
            "stream": stream,
            "categories": categories or [],
            "reason": reason,
        }

        result = await self._transport.request("POST", "/v1/consent/grant", json=payload)

        # Convert dict to object-like for easier access
        if isinstance(result, dict):

            class ConsentResult:
                def __init__(self, data: Dict[str, Any]):
                    for key, value in data.items():
                        setattr(self, key, value)

            return ConsentResult(result)

        return result

    async def revoke_consent(self, reason: Optional[str] = None) -> Dict[str, Any]:
        """
        Revoke consent and start decay protocol.

        - Immediate identity severance
        - 90-day pattern decay
        - Safety patterns may be retained (anonymized)

        Args:
            reason: Optional reason for revoking consent

        Returns:
            ConsentDecayStatus object

        Example:
            result = await client.consent.revoke_consent(reason="User requested deletion")
        """
        params = {}
        if reason:
            params["reason"] = reason

        result = await self._transport.request("POST", "/v1/consent/revoke", params=params)
        assert isinstance(result, dict), "Expected dict response from transport"
        return result

    async def get_impact_report(self) -> Dict[str, Any]:
        """
        Get Commons Credits report showing contribution to collective learning.

        Commons Credits track non-monetary contributions that strengthen the community:
        - Sharing knowledge (patterns_contributed)
        - Supporting others (users_helped)
        - Maintaining infrastructure (total_interactions)
        - Overall impact score
        - Example contributions (anonymized)

        Not currency. Not scorekeeping. Recognition for contributions traditional systems ignore.

        Returns:
            ConsentImpactReport object (Commons Credits Report)

        Example:
            report = await client.consent.get_impact_report()
            print(f"Commons Credits - Impact score: {report['impact_score']}")
            print(f"You've helped {report['users_helped']} people")
        """
        result = await self._transport.request("GET", "/v1/consent/impact")
        assert isinstance(result, dict), "Expected dict response from transport"
        return result

    async def get_audit_trail(self, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Get consent change history - IMMUTABLE AUDIT TRAIL.

        Args:
            limit: Maximum number of audit entries to return

        Returns:
            List of ConsentAuditEntry objects

        Example:
            audit = await client.consent.get_audit_trail(limit=50)
            for entry in audit:
                print(f"{entry['timestamp']}: {entry['action']}")
        """
        params = {"limit": limit}
        result = await self._transport.request("GET", "/v1/consent/audit", params=params)
        assert isinstance(result, list), "Expected list response from transport"
        return result

    async def get_streams(self) -> Dict[str, Any]:
        """
        Get available consent streams and their descriptions.

        Returns:
            Dictionary with streams and default stream

        Example:
            streams = await client.consent.get_streams()
            print(f"Available streams: {list(streams['streams'].keys())}")
        """
        result = await self._transport.request("GET", "/v1/consent/streams")
        assert isinstance(result, dict), "Expected dict response from transport"
        return result

    async def get_categories(self) -> Dict[str, Any]:
        """
        Get available consent categories for PARTNERED stream.

        Returns:
            Dictionary with categories

        Example:
            categories = await client.consent.get_categories()
            print(f"Available categories: {list(categories['categories'].keys())}")
        """
        result = await self._transport.request("GET", "/v1/consent/categories")
        assert isinstance(result, dict), "Expected dict response from transport"
        return result

    async def get_partnership_status(self) -> Dict[str, Any]:
        """
        Check status of pending partnership request.

        Returns current status and any pending partnership request outcome.

        Returns:
            Dictionary with current_stream, partnership_status, and message

        Example:
            status = await client.consent.get_partnership_status()
            print(f"Partnership status: {status['partnership_status']}")
        """
        result = await self._transport.request("GET", "/v1/consent/partnership/status")
        assert isinstance(result, dict), "Expected dict response from transport"
        return result

    async def cleanup_expired(self) -> Dict[str, Any]:
        """
        Clean up expired TEMPORARY consents (admin only).

        HARD DELETE after 14 days - NO GRACE PERIOD.

        Returns:
            Dictionary with cleaned count and message

        Example:
            result = await client.consent.cleanup_expired()
            print(f"Cleaned {result['cleaned']} expired consents")
        """
        result = await self._transport.request("POST", "/v1/consent/cleanup")
        assert isinstance(result, dict), "Expected dict response from transport"
        return result

    # ========== DSAR AUTOMATION METHODS ==========

    async def initiate_dsar(self, request_type: str = "full") -> Dict[str, Any]:
        """
        Initiate automated DSAR (Data Subject Access Request).

        Generates comprehensive data export including:
        - Consent history and current status
        - Interaction summaries
        - Preferences and settings
        - Impact metrics and contributions
        - Partnership and decay status

        Args:
            request_type: Type of DSAR request (full, consent_only, interactions_only)

        Returns:
            Dictionary with request_id, status, and export_data

        Example:
            result = await client.consent.initiate_dsar(request_type="full")
            print(f"DSAR request ID: {result['request_id']}")
        """
        payload = {"request_type": request_type}
        result = await self._transport.request("POST", "/v1/consent/dsar/initiate", json=payload)
        assert isinstance(result, dict), "Expected dict response from transport"
        return result

    async def get_dsar_status(self, request_id: str) -> Dict[str, Any]:
        """
        Get status of pending DSAR request.

        Args:
            request_id: ID of the DSAR request to check

        Returns:
            Dictionary with request status and completion details

        Example:
            status = await client.consent.get_dsar_status(request_id="dsar_123")
            if status["status"] == "completed":
                print(f"Export ready: {status['export_url']}")
        """
        result = await self._transport.request("GET", f"/v1/consent/dsar/status/{request_id}")
        assert isinstance(result, dict), "Expected dict response from transport"
        return result

    # ========== PARTNERSHIP MANAGEMENT METHODS ==========

    async def get_partnership_options(self) -> Dict[str, Any]:
        """
        Get available partnership categories and requirements.

        Returns information about what partnership entails:
        - Required consent categories
        - Approval process description
        - Benefits and responsibilities
        - Example use cases

        Returns:
            Dictionary with partnership options and requirements

        Example:
            options = await client.consent.get_partnership_options()
            print(f"Required categories: {options['required_categories']}")
        """
        result = await self._transport.request("GET", "/v1/partnership/options")
        assert isinstance(result, dict), "Expected dict response from transport"
        return result

    async def accept_partnership(self, task_id: str, reason: Optional[str] = None) -> Dict[str, Any]:
        """
        Accept a pending partnership request (agent-side).

        This method is used by the agent to approve a user's partnership request.
        The partnership request is tracked as a task in the task system.

        Args:
            task_id: ID of the partnership approval task
            reason: Optional reason for accepting the partnership

        Returns:
            Dictionary with acceptance confirmation and updated consent status

        Example:
            result = await client.consent.accept_partnership(
                task_id="task_123",
                reason="User demonstrated commitment to mutual growth"
            )
            print(f"Partnership approved: {result['user_id']}")
        """
        payload = {"task_id": task_id, "decision": "accept", "reason": reason}
        result = await self._transport.request("POST", "/v1/partnership/decide", json=payload)
        assert isinstance(result, dict), "Expected dict response from transport"
        return result

    async def reject_partnership(self, task_id: str, reason: str) -> Dict[str, Any]:
        """
        Reject a pending partnership request (agent-side).

        This method is used by the agent to decline a user's partnership request.
        A reason must be provided to help the user understand the decision.

        Args:
            task_id: ID of the partnership approval task
            reason: Reason for rejecting the partnership (required)

        Returns:
            Dictionary with rejection confirmation and message to user

        Example:
            result = await client.consent.reject_partnership(
                task_id="task_123",
                reason="More interaction history needed before partnership"
            )
            print(f"Partnership rejected: {result['message']}")
        """
        payload = {"task_id": task_id, "decision": "reject", "reason": reason}
        result = await self._transport.request("POST", "/v1/partnership/decide", json=payload)
        assert isinstance(result, dict), "Expected dict response from transport"
        return result

    async def defer_partnership(self, task_id: str, reason: str) -> Dict[str, Any]:
        """
        Defer a pending partnership request for more information (agent-side).

        This method is used by the agent to request more context before deciding.
        The partnership request remains pending, allowing for further interaction.

        Args:
            task_id: ID of the partnership approval task
            reason: What additional information is needed (required)

        Returns:
            Dictionary with deferral confirmation and next steps

        Example:
            result = await client.consent.defer_partnership(
                task_id="task_123",
                reason="Would like to understand your goals for the partnership better"
            )
            print(f"Partnership deferred: {result['message']}")
        """
        payload = {"task_id": task_id, "decision": "defer", "reason": reason}
        result = await self._transport.request("POST", "/v1/partnership/decide", json=payload)
        assert isinstance(result, dict), "Expected dict response from transport"
        return result
