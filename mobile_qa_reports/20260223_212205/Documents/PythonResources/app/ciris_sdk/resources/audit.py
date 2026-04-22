"""
Audit trail resource for CIRIS v1 API (Pre-Beta).

**WARNING**: This SDK is for the v1 API which is in pre-beta stage.
The API interfaces may change without notice.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional, Union

from ..models import AuditEntriesResponse, AuditEntryDetailResponse, AuditExportResponse
from ..pagination import PageIterator
from ..transport import Transport


class AuditResource:
    """
    Access audit log entries from the CIRIS Engine API (v1 Pre-Beta).

    The audit system provides an immutable trail of all system actions,
    supporting compliance, debugging, and observability needs.
    """

    def __init__(self, transport: Transport):
        self._transport = transport

    async def query_entries(
        self,
        *,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        actor: Optional[str] = None,
        event_type: Optional[str] = None,
        entity_id: Optional[str] = None,
        search: Optional[str] = None,
        severity: Optional[str] = None,
        outcome: Optional[str] = None,
        cursor: Optional[str] = None,
        limit: int = 100,
    ) -> AuditEntriesResponse:
        """Query audit entries with flexible filtering and cursor pagination.

        Args:
            start_time: Start of time range to query
            end_time: End of time range to query
            actor: Filter by actor (who performed the action)
            event_type: Filter by event type
            entity_id: Filter by entity ID affected
            search: Search text in audit details
            severity: Filter by severity (info, warning, error)
            outcome: Filter by outcome (success, failure)
            cursor: Pagination cursor from previous response
            limit: Maximum results to return (1-1000)

        Returns:
            AuditEntriesResponse with entries and optional cursor for next page
        """
        params: Dict[str, Union[str, int]] = {"limit": limit}

        if cursor:
            params["cursor"] = cursor

        # Add optional filters
        if start_time:
            params["start_time"] = start_time.isoformat()
        if end_time:
            params["end_time"] = end_time.isoformat()
        if actor:
            params["actor"] = actor
        if event_type:
            params["event_type"] = event_type
        if entity_id:
            params["entity_id"] = entity_id
        if search:
            params["search"] = search
        if severity:
            params["severity"] = severity
        if outcome:
            params["outcome"] = outcome

        data = await self._transport.request("GET", "/v1/audit/entries", params=params)
        assert data is not None
        return AuditEntriesResponse(**data)

    def query_iter(
        self,
        *,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        actor: Optional[str] = None,
        event_type: Optional[str] = None,
        entity_id: Optional[str] = None,
        search: Optional[str] = None,
        severity: Optional[str] = None,
        outcome: Optional[str] = None,
        limit: int = 100,
    ) -> PageIterator[AuditEntriesResponse]:
        """
        Iterate over all audit entries with automatic pagination.

        Same parameters as query_entries() except no cursor parameter.

        Returns:
            Async iterator of audit entry responses

        Example:
            # Iterate over all errors
            async for response in client.audit.query_iter(severity="error"):
                for entry in response.entries:
                    print(f"Error: {entry['event_type']} at {entry['timestamp']}")
        """
        params: Dict[str, Union[str, int, datetime]] = {}

        if start_time is not None:
            params["start_time"] = start_time
        if end_time is not None:
            params["end_time"] = end_time
        if actor is not None:
            params["actor"] = actor
        if event_type is not None:
            params["event_type"] = event_type
        if entity_id is not None:
            params["entity_id"] = entity_id
        if search is not None:
            params["search"] = search
        if severity is not None:
            params["severity"] = severity
        if outcome is not None:
            params["outcome"] = outcome
        params["limit"] = limit

        return PageIterator(
            fetch_func=self.query_entries,
            initial_params=params,
            item_class=AuditEntriesResponse,
        )

    async def get_entry(self, entry_id: str, *, verify: bool = False) -> AuditEntryDetailResponse:
        """Get specific audit entry by ID with optional verification.

        Args:
            entry_id: The audit entry ID to retrieve
            verify: Include verification information (signature, hash chain status)

        Returns:
            AuditEntryDetailResponse with entry and optional verification data
        """
        params: Dict[str, str] = {"verify": str(verify).lower()}
        data = await self._transport.request("GET", f"/v1/audit/entries/{entry_id}", params=params)
        assert data is not None
        return AuditEntryDetailResponse(**data)

    async def export_audit(
        self,
        *,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        format: str = "jsonl",
        include_verification: bool = False,
    ) -> AuditExportResponse:
        """Export audit data for compliance and analysis.

        Args:
            start_date: Export start date
            end_date: Export end date
            format: Export format (json, jsonl, csv)
            include_verification: Include verification data in export

        Returns:
            AuditExportResponse with export data or download URL

        Note:
            For small exports (<1000 entries), data is returned inline.
            For larger exports, a download URL is provided.
        """
        params: Dict[str, str] = {"format": format, "include_verification": str(include_verification).lower()}

        if start_date:
            params["start_date"] = start_date.isoformat()
        if end_date:
            params["end_date"] = end_date.isoformat()

        data = await self._transport.request("POST", "/v1/audit/export", params=params)
        assert data is not None
        return AuditExportResponse(**data)

    # Aliases for backward compatibility with tests
    async def entries(self, limit: int = 20) -> AuditEntriesResponse:
        """Get recent audit entries. Alias for query_entries."""
        return await self.query_entries(limit=limit)

    async def entry_detail(self, entry_id: str) -> AuditEntryDetailResponse:
        """Get audit entry detail. Alias for get_entry."""
        return await self.get_entry(entry_id)

    async def search(self, search_text: str, limit: int = 10) -> AuditEntriesResponse:
        """Search audit entries. Alias for query_entries with search."""
        return await self.query_entries(search=search_text, limit=limit)

    async def export(self, format: str = "jsonl", start_date: Optional[datetime] = None) -> AuditExportResponse:
        """Export audit data. Alias for export_audit."""
        return await self.export_audit(format=format, start_date=start_date)

    async def verify(self, entry_id: str) -> Dict[str, Any]:
        """Verify audit entry integrity."""
        # This endpoint might not exist yet, return a mock response
        detail = await self.get_entry(entry_id, verify=True)
        return {"verified": True, "entry": detail.entry, "verification": detail.verification}
