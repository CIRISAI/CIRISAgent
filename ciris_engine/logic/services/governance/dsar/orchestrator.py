"""Multi-source DSAR orchestration service.

Coordinates DSAR requests across CIRIS + external data sources (SQL, REST, HL7).

Architecture:
- Fast path: DSARAutomationService (CIRIS only, ~500ms)
- Slow path: DSAROrchestrator (multi-source, ~3-10s)

For CIRIS-only DSAR, use DSARAutomationService in consent/.
For multi-source DSAR, use this orchestrator.
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from ciris_engine.logic.buses.memory_bus import MemoryBus
from ciris_engine.logic.buses.tool_bus import ToolBus
from ciris_engine.logic.services.governance.consent.dsar_automation import DSARAutomationService
from ciris_engine.protocols.services.lifecycle.time import TimeServiceProtocol
from ciris_engine.schemas.consent.core import DSARExportFormat

from .schemas import (
    DataSourceDeletion,
    DataSourceExport,
    MultiSourceDSARAccessPackage,
    MultiSourceDSARCorrectionResult,
    MultiSourceDSARDeletionResult,
    MultiSourceDSARExportPackage,
)

logger = logging.getLogger(__name__)


class DSAROrchestrator:
    """Orchestrates DSAR across CIRIS + external data sources.

    Coordinates multi-source data subject access requests using:
    - DSARAutomationService for CIRIS internal data
    - ToolBus for discovering SQL/REST/HL7 connectors
    - Identity resolution for mapping users across systems
    """

    def __init__(
        self,
        time_service: TimeServiceProtocol,
        dsar_automation: DSARAutomationService,
        tool_bus: ToolBus,
        memory_bus: MemoryBus,
    ):
        """Initialize DSAR orchestrator.

        Args:
            time_service: Time service for consistent timestamps
            dsar_automation: CIRIS-only DSAR automation service
            tool_bus: Tool bus for discovering external connectors
            memory_bus: Memory bus for identity resolution
        """
        self._time_service = time_service
        self._dsar_automation = dsar_automation
        self._tool_bus = tool_bus
        self._memory_bus = memory_bus

        # Metrics
        self._multi_source_requests = 0
        self._total_sources_queried = 0
        self._total_processing_time = 0.0

    def _now(self) -> datetime:
        """Get current time from time service."""
        return self._time_service.now()

    async def handle_access_request_multi_source(
        self, user_identifier: str, request_id: Optional[str] = None
    ) -> MultiSourceDSARAccessPackage:
        """Handle GDPR Article 15 access request across all data sources.

        Coordinates access request across:
        1. CIRIS internal data (via DSARAutomationService)
        2. SQL databases (via ToolBus)
        3. REST APIs (via ToolBus)
        4. HL7 systems (via ToolBus - future)

        Args:
            user_identifier: User identifier (email, user_id, etc.)
            request_id: Optional request ID for tracking

        Returns:
            Aggregated access package from all sources

        TODO Implementation Steps:
        1. Start timer for performance tracking
        2. Resolve user identity across all systems
           - Use identity_resolution.resolve_user_identity()
           - Get all identifiers (email, discord_id, reddit_username, etc.)
        3. Get CIRIS internal data (fast path)
           - Call dsar_automation.handle_access_request()
        4. Query all SQL connectors
           - Use tool_bus.get_tools_by_capability("tool:sql:export_user")
           - For each SQL tool, call with appropriate identifier
           - Handle errors gracefully (log, continue)
        5. Query all REST connectors
           - Use tool_bus.get_tools_by_capability("tool:rest:export_user")
           - Similar pattern to SQL
        6. Query all HL7 connectors (future)
           - Use tool_bus.get_tools_by_capability("tool:hl7:export_patient")
        7. Aggregate all results into MultiSourceDSARAccessPackage
        8. Calculate total records and processing time
        9. Log metrics and return
        """
        # TODO: Implement multi-source access request coordination
        raise NotImplementedError("Multi-source DSAR access request coordination not yet implemented")

    async def handle_export_request_multi_source(
        self,
        user_identifier: str,
        export_format: DSARExportFormat,
        request_id: Optional[str] = None,
    ) -> MultiSourceDSARExportPackage:
        """Handle GDPR Article 20 export request across all data sources.

        Generates downloadable export aggregating data from all sources.

        Args:
            user_identifier: User identifier
            export_format: Desired format (JSON, CSV, SQLite)
            request_id: Optional request ID for tracking

        Returns:
            Aggregated export package from all sources

        TODO Implementation Steps:
        1. Start timer
        2. Resolve user identity
        3. Get CIRIS export
           - Call dsar_automation.handle_export_request()
        4. Get external exports
           - Query SQL connectors: tool:sql:export_user
           - Query REST connectors: tool:rest:export_user
        5. Aggregate exports
           - Merge data structures
           - Calculate total size
           - Generate combined checksum
        6. Return MultiSourceDSARExportPackage
        """
        # TODO: Implement multi-source export request coordination
        raise NotImplementedError("Multi-source DSAR export request coordination not yet implemented")

    async def handle_deletion_request_multi_source(
        self, user_identifier: str, request_id: Optional[str] = None
    ) -> MultiSourceDSARDeletionResult:
        """Handle GDPR Article 17 deletion request across all data sources.

        Coordinates deletion across:
        1. CIRIS internal data (90-day decay protocol)
        2. SQL databases (immediate deletion with verification)
        3. REST APIs (API-based deletion)
        4. HL7 systems (medical data deletion - future)

        Args:
            user_identifier: User identifier
            request_id: Optional request ID for tracking

        Returns:
            Aggregated deletion result from all sources

        TODO Implementation Steps:
        1. Start timer
        2. Resolve user identity
        3. Initiate CIRIS deletion
           - Call consent_service.revoke_consent()
           - Triggers 90-day decay protocol
        4. Delete from SQL connectors
           - Use tool:sql:delete_user
           - Wait for completion
           - Verify deletion: tool:sql:verify_deletion
        5. Delete from REST connectors
           - Use tool:rest:delete_user
           - Handle async deletion (may return job ID)
        6. Delete from HL7 systems (future)
           - Use tool:hl7:delete_patient
        7. Track deletion status across all sources
        8. Return MultiSourceDSARDeletionResult
        """
        # TODO: Implement multi-source deletion request coordination
        raise NotImplementedError("Multi-source DSAR deletion request coordination not yet implemented")

    async def handle_correction_request_multi_source(
        self, user_identifier: str, corrections: Dict[str, Any], request_id: Optional[str] = None
    ) -> MultiSourceDSARCorrectionResult:
        """Handle GDPR Article 16 correction request across all data sources.

        Applies corrections to user data in all connected systems.

        Args:
            user_identifier: User identifier
            corrections: Dict of field → new_value corrections
            request_id: Optional request ID for tracking

        Returns:
            Aggregated correction result from all sources

        TODO Implementation Steps:
        1. Start timer
        2. Resolve user identity
        3. Apply CIRIS corrections
           - Call dsar_automation.handle_correction_request()
        4. Apply corrections to SQL sources
           - Use tool:sql:query with UPDATE statements
           - Track which corrections applied/rejected
        5. Apply corrections to REST sources
           - Use tool:rest:update_user or tool:rest:patch
        6. Aggregate results
        7. Return MultiSourceDSARCorrectionResult
        """
        # TODO: Implement multi-source correction request coordination
        raise NotImplementedError("Multi-source DSAR correction request coordination not yet implemented")

    async def get_deletion_status_multi_source(
        self, user_identifier: str, request_id: str
    ) -> MultiSourceDSARDeletionResult:
        """Get deletion status across all sources.

        Checks deletion progress for:
        - CIRIS (90-day decay progress)
        - SQL databases (immediate, verification status)
        - REST APIs (job status)
        - HL7 systems (future)

        Args:
            user_identifier: User identifier
            request_id: Original deletion request ID

        Returns:
            Current deletion status across all sources

        TODO Implementation Steps:
        1. Resolve user identity
        2. Get CIRIS deletion status
           - Call dsar_automation.get_deletion_status()
        3. Check SQL deletion verification
           - Use tool:sql:verify_deletion
        4. Check REST deletion status
           - Use tool:rest:get_deletion_status (if available)
        5. Aggregate status
        6. Return MultiSourceDSARDeletionResult
        """
        # TODO: Implement multi-source deletion status checking
        raise NotImplementedError("Multi-source DSAR deletion status checking not yet implemented")

    async def _discover_sql_connectors(self) -> List[str]:
        """Discover all registered SQL connectors via ToolBus.

        Returns:
            List of SQL connector IDs

        TODO Implementation:
        # Get SQL data sources using metadata
        sql_services = self._tool_bus.get_tools_by_metadata({
            "data_source": True,
            "data_source_type": "sql"
        })

        # Extract connector IDs
        connector_ids = [
            service.get_service_metadata()["connector_id"]
            for service in sql_services
        ]

        return connector_ids
        """
        # TODO: Implement SQL connector discovery
        raise NotImplementedError("SQL connector discovery not yet implemented")

    async def _discover_rest_connectors(self) -> List[str]:
        """Discover all registered REST connectors via ToolBus.

        Returns:
            List of REST connector IDs

        TODO:
        - Query tool_bus for tools with capability "tool:rest"
        - Extract unique connector IDs
        - Return list
        """
        # TODO: Implement REST connector discovery
        raise NotImplementedError("REST connector discovery not yet implemented")

    async def _discover_hl7_connectors(self) -> List[str]:
        """Discover all registered HL7 connectors via ToolBus.

        Returns:
            List of HL7 connector IDs

        TODO:
        - Query tool_bus for tools with capability "tool:hl7"
        - Extract unique connector IDs
        - Return list
        """
        # TODO: Implement HL7 connector discovery
        raise NotImplementedError("HL7 connector discovery not yet implemented")

    async def _export_from_sql(self, connector_id: str, user_identifier: str) -> DataSourceExport:
        """Export user data from SQL connector.

        Args:
            connector_id: SQL connector ID
            user_identifier: User identifier

        Returns:
            Data source export result

        TODO:
        - Call tool: {connector_id}_export_user
        - Parse result
        - Build DataSourceExport
        - Handle errors
        """
        # TODO: Implement SQL data export
        raise NotImplementedError("SQL data export not yet implemented")

    async def _delete_from_sql(
        self, connector_id: str, user_identifier: str, verify: bool = True
    ) -> DataSourceDeletion:
        """Delete user data from SQL connector.

        Args:
            connector_id: SQL connector ID
            user_identifier: User identifier
            verify: Whether to verify deletion

        Returns:
            Data source deletion result

        TODO:
        - Call tool: {connector_id}_delete_user
        - If verify=True, call {connector_id}_verify_deletion
        - Build DataSourceDeletion
        - Handle errors
        """
        # TODO: Implement SQL data deletion
        raise NotImplementedError("SQL data deletion not yet implemented")

    async def _verify_deletion_sql(self, connector_id: str, user_identifier: str) -> bool:
        """Verify user data deletion from SQL connector.

        Args:
            connector_id: SQL connector ID
            user_identifier: User identifier

        Returns:
            True if zero data confirmed, False otherwise

        TODO:
        - Call tool: {connector_id}_verify_deletion
        - Check result.zero_data_confirmed
        - Return boolean
        """
        # TODO: Implement SQL deletion verification
        raise NotImplementedError("SQL deletion verification not yet implemented")

    def get_metrics(self) -> Dict[str, Any]:
        """Get orchestrator metrics.

        Returns:
            Dict with metrics:
            - multi_source_requests: Total multi-source requests
            - total_sources_queried: Total sources queried
            - avg_processing_time: Average processing time
        """
        avg_time = self._total_processing_time / self._multi_source_requests if self._multi_source_requests > 0 else 0.0

        return {
            "multi_source_requests": self._multi_source_requests,
            "total_sources_queried": self._total_sources_queried,
            "avg_processing_time_seconds": avg_time,
        }
