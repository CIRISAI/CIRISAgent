"""Multi-source DSAR orchestration service.

Coordinates DSAR requests across CIRIS + external data sources (SQL, REST, HL7).

Architecture:
- Fast path: DSARAutomationService (CIRIS only, ~500ms)
- Slow path: DSAROrchestrator (multi-source, ~3-10s)

For CIRIS-only DSAR, use DSARAutomationService in consent/.
For multi-source DSAR, use this orchestrator.
"""

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, cast

from fastapi import HTTPException, status

from ciris_engine.logic.buses.memory_bus import MemoryBus
from ciris_engine.logic.buses.tool_bus import ToolBus
from ciris_engine.logic.services.governance.consent import ConsentService
from ciris_engine.logic.services.governance.consent.dsar_automation import DSARAutomationService
from ciris_engine.protocols.services.graph.memory import MemoryServiceProtocol
from ciris_engine.protocols.services.lifecycle.time import TimeServiceProtocol
from ciris_engine.schemas.consent.core import (
    ConsentCategory,
    ConsentImpactReport,
    ConsentStatus,
    ConsentStream,
    DSARExportFormat,
)

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
    - ConsentService for initiating decay protocol
    - ToolBus for discovering SQL/REST/HL7 connectors
    - Identity resolution for mapping users across systems
    """

    def __init__(
        self,
        time_service: TimeServiceProtocol,
        dsar_automation: DSARAutomationService,
        consent_service: ConsentService,
        tool_bus: ToolBus,
        memory_bus: MemoryBus,
    ):
        """Initialize DSAR orchestrator.

        Args:
            time_service: Time service for consistent timestamps
            dsar_automation: CIRIS-only DSAR automation service
            consent_service: Consent service for revoking consent and initiating decay
            tool_bus: Tool bus for discovering external connectors
            memory_bus: Memory bus for identity resolution
        """
        self._time_service = time_service
        self._dsar_automation = dsar_automation
        self._consent_service = consent_service
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

        Implementation:
        - Resolves user identity across systems
        - Gets CIRIS internal data (fast path)
        - Queries all SQL/REST connectors via ToolBus
        - Aggregates results with performance tracking
        """
        import hashlib
        import time

        from ciris_engine.logic.utils.identity_resolution import resolve_user_identity

        # Start timer
        start_time = time.time()

        # Generate request ID if not provided
        if not request_id:
            request_id = f"DSAR-ACCESS-{self._now().strftime('%Y%m%d-%H%M%S')}"

        logger.info(f"Starting multi-source access request {request_id} for {user_identifier}")

        # Step 1: Resolve user identity across all systems
        identity_node = await resolve_user_identity(user_identifier, cast(MemoryServiceProtocol, self._memory_bus))

        # Step 2: Get CIRIS internal data (fast path)
        try:
            ciris_data = await self._dsar_automation.handle_access_request(user_identifier)
        except Exception as e:
            logger.exception(f"Failed to get CIRIS data for {user_identifier}: {e}")
            # Create empty package as fallback
            from ciris_engine.schemas.consent.core import ConsentAuditEntry, DSARAccessPackage

            ciris_data = DSARAccessPackage(
                user_id=user_identifier,
                request_id=request_id,
                generated_at=self._now(),
                consent_status=ConsentStatus(
                    user_id=user_identifier,
                    stream=ConsentStream.TEMPORARY,
                    categories=[],
                    granted_at=self._now(),
                    last_modified=self._now(),
                ),
                consent_history=[],
                interaction_summary={},
                contribution_metrics=ConsentImpactReport(
                    user_id=user_identifier,
                    total_interactions=0,
                    patterns_contributed=0,
                    users_helped=0,
                    categories_active=[],
                    impact_score=0.0,
                    example_contributions=[],
                ),
                data_categories=[],
                retention_periods={},
                processing_purposes=[],
            )

        # Step 3: Discover and query SQL connectors
        external_sources: List[DataSourceExport] = []
        sql_connectors = await self._discover_sql_connectors()

        for connector_id in sql_connectors:
            try:
                export = await self._export_from_sql(connector_id, user_identifier)
                external_sources.append(export)
            except Exception as e:
                logger.error(f"Failed to export from SQL connector {connector_id}: {e}")
                # Add error entry
                external_sources.append(
                    DataSourceExport(
                        source_id=connector_id,
                        source_type="sql",
                        source_name=connector_id,
                        export_timestamp=self._now().isoformat(),
                        errors=[str(e)],
                    )
                )

        # Step 4: Discover and query REST connectors (future)
        # TODO Phase 2: Implement REST connector discovery and export
        # Implementation:
        # 1. Call _discover_rest_connectors() to find REST API connectors
        # 2. For each connector, call _export_from_rest(connector_id, user_identifier)
        # 3. Aggregate REST exports into external_sources list
        # 4. Handle errors gracefully (similar to SQL connector pattern above)

        # Step 5: Calculate totals
        total_records = sum(src.total_records for src in external_sources)
        processing_time = time.time() - start_time

        # Step 6: Update metrics
        self._multi_source_requests += 1
        self._total_sources_queried += 1 + len(external_sources)  # CIRIS + external
        self._total_processing_time += processing_time

        # Step 7: Build aggregated package
        package = MultiSourceDSARAccessPackage(
            request_id=request_id,
            user_identifier=user_identifier,
            ciris_data=ciris_data,
            external_sources=external_sources,
            identity_node=identity_node,
            total_sources=1 + len(external_sources),
            total_records=total_records,
            generated_at=self._now().isoformat(),
            processing_time_seconds=processing_time,
        )

        logger.info(
            f"Completed multi-source access request {request_id}: "
            f"{package.total_sources} sources, {total_records} records, {processing_time:.2f}s"
        )

        return package

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

        Implementation:
        - Resolves user identity
        - Gets CIRIS export in specified format
        - Queries all SQL connectors for exports
        - Aggregates data and calculates total size/checksum
        """
        import hashlib
        import json
        import time

        from ciris_engine.logic.utils.identity_resolution import resolve_user_identity

        # Start timer
        start_time = time.time()

        # Generate request ID if not provided
        if not request_id:
            request_id = f"DSAR-EXPORT-{self._now().strftime('%Y%m%d-%H%M%S')}"

        logger.info(
            f"Starting multi-source export request {request_id} for {user_identifier} (format: {export_format})"
        )

        # Step 1: Resolve user identity
        identity_node = await resolve_user_identity(user_identifier, cast(MemoryServiceProtocol, self._memory_bus))

        # Step 2: Get CIRIS export
        try:
            ciris_export = await self._dsar_automation.handle_export_request(user_identifier, export_format)
        except Exception as e:
            logger.exception(f"Failed to get CIRIS export for {user_identifier}: {e}")
            # Create empty export as fallback
            from ciris_engine.schemas.consent.core import DSARExportPackage

            ciris_export = DSARExportPackage(
                user_id=user_identifier,
                request_id=request_id,
                export_format=export_format,
                generated_at=self._now(),
                file_path=None,
                file_size_bytes=0,
                record_counts={},
                checksum="",
                includes_readme=True,
            )

        # Step 3: Discover and export from SQL connectors
        external_exports: List[DataSourceExport] = []
        sql_connectors = await self._discover_sql_connectors()

        for connector_id in sql_connectors:
            try:
                export = await self._export_from_sql(connector_id, user_identifier)
                external_exports.append(export)
            except Exception as e:
                logger.error(f"Failed to export from SQL connector {connector_id}: {e}")
                external_exports.append(
                    DataSourceExport(
                        source_id=connector_id,
                        source_type="sql",
                        source_name=connector_id,
                        export_timestamp=self._now().isoformat(),
                        errors=[str(e)],
                    )
                )

        # Step 4: Calculate total size
        total_size_bytes = ciris_export.file_size_bytes + sum(
            len(json.dumps(src.data).encode("utf-8")) for src in external_exports
        )
        total_records = sum(src.total_records for src in external_exports)

        # Step 5: Calculate processing time
        processing_time = time.time() - start_time

        # Step 6: Update metrics
        self._multi_source_requests += 1
        self._total_sources_queried += 1 + len(external_exports)
        self._total_processing_time += processing_time

        # Step 7: Build export package
        package = MultiSourceDSARExportPackage(
            request_id=request_id,
            user_identifier=user_identifier,
            ciris_export=ciris_export,
            external_exports=external_exports,
            identity_node=identity_node,
            total_sources=1 + len(external_exports),
            total_records=total_records,
            total_size_bytes=total_size_bytes,
            export_format=export_format.value if hasattr(export_format, "value") else str(export_format),
            generated_at=self._now().isoformat(),
            processing_time_seconds=processing_time,
        )

        logger.info(
            f"Completed multi-source export {request_id}: "
            f"{package.total_sources} sources, {total_size_bytes} bytes, {processing_time:.2f}s"
        )

        return package

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

        Implementation:
        - Resolves user identity
        - Initiates 90-day decay in CIRIS (via ConsentService - future)
        - Deletes from all SQL connectors with verification
        - Tracks success/failure across all sources

        Note: CIRIS internal deletion requires ConsentService.revoke_consent()
        which isn't available in DSAROrchestrator constructor. This should be
        added when orchestrator is integrated into the service layer.
        """
        import time

        from ciris_engine.logic.utils.identity_resolution import resolve_user_identity

        # Start timer
        start_time = time.time()

        # Generate request ID if not provided
        if not request_id:
            request_id = f"DSAR-DELETE-{self._now().strftime('%Y%m%d-%H%M%S')}"

        logger.info(f"Starting multi-source deletion request {request_id} for {user_identifier}")

        # Step 1: Resolve user identity
        identity_node = await resolve_user_identity(user_identifier, cast(MemoryServiceProtocol, self._memory_bus))

        # Step 2: Initiate CIRIS deletion (90-day decay protocol)
        try:
            # Revoke consent to initiate decay protocol
            await self._consent_service.revoke_consent(
                user_id=user_identifier,
                reason=f"GDPR Article 17 - Multi-source deletion request {request_id}",
            )
            logger.info(f"Initiated consent revocation and decay protocol for {user_identifier}")

            # Get actual deletion status from DSAR automation
            ciris_deletion = await self._dsar_automation.get_deletion_status(user_identifier, request_id)

            # If no status found yet, create initial status
            if ciris_deletion is None:
                from ciris_engine.schemas.consent.core import DSARDeletionStatus

                ciris_deletion = DSARDeletionStatus(
                    ticket_id=request_id,
                    user_id=user_identifier,
                    decay_started=self._now(),
                    current_phase="identity_severed",  # First phase of decay
                    completion_percentage=0.0,
                    estimated_completion=self._now() + timedelta(days=90),
                    milestones_completed=[],
                    next_milestone="interaction_history_purged",
                    safety_patterns_retained=0,
                )
        except Exception as e:
            logger.exception(f"Failed to initiate consent revocation for {user_identifier}: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to initiate CIRIS deletion: {str(e)}",
            ) from e

        # Step 3: Delete from SQL connectors with verification
        external_deletions: List[DataSourceDeletion] = []
        sql_connectors = await self._discover_sql_connectors()

        for connector_id in sql_connectors:
            try:
                deletion = await self._delete_from_sql(connector_id, user_identifier, verify=True)
                external_deletions.append(deletion)
            except Exception as e:
                logger.error(f"Failed to delete from SQL connector {connector_id}: {e}")
                external_deletions.append(
                    DataSourceDeletion(
                        source_id=connector_id,
                        source_type="sql",
                        source_name=connector_id,
                        success=False,
                        deletion_timestamp=self._now().isoformat(),
                        errors=[str(e)],
                    )
                )

        # Step 4: Calculate aggregated status
        sources_completed = sum(1 for d in external_deletions if d.success and d.verification_passed)
        sources_failed = sum(1 for d in external_deletions if not d.success)
        total_records_deleted = sum(d.total_records_deleted for d in external_deletions)
        all_verified = all(d.verification_passed for d in external_deletions if d.success)

        # Step 5: Calculate processing time
        processing_time = time.time() - start_time

        # Step 6: Update metrics
        self._multi_source_requests += 1
        self._total_sources_queried += 1 + len(external_deletions)
        self._total_processing_time += processing_time

        # Step 7: Build deletion result
        result = MultiSourceDSARDeletionResult(
            request_id=request_id,
            user_identifier=user_identifier,
            ciris_deletion=ciris_deletion,
            external_deletions=external_deletions,
            identity_node=identity_node,
            total_sources=1 + len(external_deletions),
            sources_completed=sources_completed,
            sources_failed=sources_failed,
            total_records_deleted=total_records_deleted,
            all_verified=all_verified,
            initiated_at=self._now().isoformat(),
            completed_at=self._now().isoformat() if sources_failed == 0 else None,
            processing_time_seconds=processing_time,
        )

        logger.info(
            f"Completed multi-source deletion {request_id}: "
            f"{sources_completed}/{result.total_sources} completed, "
            f"{total_records_deleted} records deleted, {processing_time:.2f}s"
        )

        return result

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

        Implementation:
        - Resolves user identity
        - Applies corrections to CIRIS data
        - Applies corrections to all SQL sources
        - Tracks applied/rejected corrections per source
        """
        import time

        from ciris_engine.logic.utils.identity_resolution import resolve_user_identity

        # Start timer
        start_time = time.time()

        # Generate request ID if not provided
        if not request_id:
            request_id = f"DSAR-CORRECT-{self._now().strftime('%Y%m%d-%H%M%S')}"

        logger.info(f"Starting multi-source correction request {request_id} for {user_identifier}")

        # Step 1: Resolve user identity
        identity_node = await resolve_user_identity(user_identifier, cast(MemoryServiceProtocol, self._memory_bus))

        # Step 2: Apply CIRIS corrections
        corrections_by_source: Dict[str, Dict[str, Any]] = {}
        total_corrections_applied = 0
        total_corrections_rejected = 0

        try:
            # Apply corrections to CIRIS via DSARAutomationService
            from ciris_engine.schemas.consent.core import DSARCorrectionRequest

            # Build correction requests for each field
            for field_name, new_value in corrections.items():
                correction_req = DSARCorrectionRequest(
                    user_id=user_identifier,
                    field_name=field_name,
                    current_value=None,  # Could query current value first
                    new_value=str(new_value),
                    reason="Multi-source DSAR correction request",
                )
                ciris_result = await self._dsar_automation.handle_correction_request(correction_req, request_id)

            # Track CIRIS corrections
            corrections_by_source["ciris"] = corrections
            total_corrections_applied += len(corrections)
            logger.info(f"Applied {len(corrections)} corrections to CIRIS for {user_identifier}")
        except Exception as e:
            logger.exception(f"Failed to apply CIRIS corrections for {user_identifier}: {e}")
            corrections_by_source["ciris"] = {}
            total_corrections_rejected += len(corrections)

        # Step 3: Apply corrections to SQL sources
        # Note: This requires UPDATE statement support via SQL connectors
        # For now, we'll log that SQL corrections are not yet implemented
        sql_connectors = await self._discover_sql_connectors()
        for connector_id in sql_connectors:
            try:
                # TODO Phase 2: Implement SQL UPDATE via tool_bus
                # Implementation:
                # 1. Create sql_update_user tool that accepts corrections dict
                # 2. Call await tool_bus.execute_tool("sql_update_user", {
                #        "connector_id": connector_id,
                #        "user_identifier": user_identifier,
                #        "corrections": corrections
                #    })
                # 3. Parse result to determine which corrections were applied/rejected
                # 4. Update corrections_by_source and counters accordingly
                # For now, mark as rejected
                corrections_by_source[connector_id] = {}
                total_corrections_rejected += len(corrections)
                logger.warning(f"SQL corrections not yet implemented for {connector_id}")
            except Exception as e:
                logger.error(f"Failed to apply corrections to SQL connector {connector_id}: {e}")
                corrections_by_source[connector_id] = {}
                total_corrections_rejected += len(corrections)

        # Step 4: Calculate processing time
        processing_time = time.time() - start_time

        # Step 5: Update metrics
        self._multi_source_requests += 1
        self._total_sources_queried += 1 + len(sql_connectors)
        self._total_processing_time += processing_time

        # Step 6: Build correction result
        result = MultiSourceDSARCorrectionResult(
            request_id=request_id,
            user_identifier=user_identifier,
            corrections_by_source=corrections_by_source,
            identity_node=identity_node,
            total_sources=1 + len(sql_connectors),
            total_corrections_applied=total_corrections_applied,
            total_corrections_rejected=total_corrections_rejected,
            generated_at=self._now().isoformat(),
            processing_time_seconds=processing_time,
        )

        logger.info(
            f"Completed multi-source correction {request_id}: "
            f"{total_corrections_applied} applied, {total_corrections_rejected} rejected, {processing_time:.2f}s"
        )

        return result

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
        """
        import time

        from ciris_engine.logic.utils.identity_resolution import resolve_user_identity

        # Start timer
        start_time = time.time()

        logger.info(f"Checking multi-source deletion status for {request_id} - {user_identifier}")

        # Step 1: Resolve user identity
        identity_node = await resolve_user_identity(user_identifier, cast(MemoryServiceProtocol, self._memory_bus))

        # Step 2: Get CIRIS deletion status
        try:
            ciris_deletion = await self._dsar_automation.get_deletion_status(user_identifier, request_id)
        except Exception as e:
            logger.exception(f"Failed to get CIRIS deletion status for {user_identifier}: {e}")
            ciris_deletion = None

        # Create fallback if no status found
        if ciris_deletion is None:
            from ciris_engine.schemas.consent.core import DSARDeletionStatus

            ciris_deletion = DSARDeletionStatus(
                ticket_id=request_id,
                user_id=user_identifier,
                decay_started=self._now(),
                current_phase="unknown",
                completion_percentage=0.0,
                estimated_completion=self._now() + timedelta(days=90),
                milestones_completed=[],
                next_milestone="unknown",
                safety_patterns_retained=0,
            )

        # Step 3: Check SQL deletion verification for all connectors
        external_deletions: List[DataSourceDeletion] = []
        sql_connectors = await self._discover_sql_connectors()

        for connector_id in sql_connectors:
            try:
                # Verify deletion for this connector
                verification_passed = await self._verify_deletion_sql(connector_id, user_identifier)

                # Create deletion status entry
                external_deletions.append(
                    DataSourceDeletion(
                        source_id=connector_id,
                        source_type="sql",
                        source_name=connector_id,
                        success=verification_passed,  # If verification passed, deletion was successful
                        total_records_deleted=0,  # Unknown - already deleted
                        verification_passed=verification_passed,
                        deletion_timestamp=self._now().isoformat(),
                        errors=[] if verification_passed else ["Deletion verification failed - data still present"],
                    )
                )
            except Exception as e:
                logger.error(f"Failed to verify deletion from SQL connector {connector_id}: {e}")
                external_deletions.append(
                    DataSourceDeletion(
                        source_id=connector_id,
                        source_type="sql",
                        source_name=connector_id,
                        success=False,
                        verification_passed=False,
                        deletion_timestamp=self._now().isoformat(),
                        errors=[str(e)],
                    )
                )

        # Step 4: Calculate aggregated status
        sources_completed = sum(1 for d in external_deletions if d.success and d.verification_passed)
        sources_failed = sum(1 for d in external_deletions if not d.success)
        total_records_deleted = sum(d.total_records_deleted for d in external_deletions)
        all_verified = all(d.verification_passed for d in external_deletions if d.success)

        # Step 5: Calculate processing time
        processing_time = time.time() - start_time

        # Step 6: Build deletion result
        result = MultiSourceDSARDeletionResult(
            request_id=request_id,
            user_identifier=user_identifier,
            ciris_deletion=ciris_deletion,
            external_deletions=external_deletions,
            identity_node=identity_node,
            total_sources=1 + len(external_deletions),
            sources_completed=sources_completed,
            sources_failed=sources_failed,
            total_records_deleted=total_records_deleted,
            all_verified=all_verified,
            initiated_at=(
                ciris_deletion.decay_started.isoformat() if ciris_deletion.decay_started else self._now().isoformat()
            ),
            completed_at=(
                self._now().isoformat()
                if sources_failed == 0 and ciris_deletion.completion_percentage >= 100.0
                else None
            ),
            processing_time_seconds=processing_time,
        )

        logger.info(
            f"Deletion status check complete for {request_id}: "
            f"{sources_completed}/{result.total_sources} verified, "
            f"CIRIS at {ciris_deletion.completion_percentage:.1f}%"
        )

        return result

    async def _discover_sql_connectors(self) -> List[str]:
        """Discover all registered SQL connectors via ToolBus.

        Returns:
            List of SQL connector IDs
        """
        try:
            # Get SQL data sources using metadata
            sql_services = self._tool_bus.get_tools_by_metadata({"data_source": True, "data_source_type": "sql"})

            # Extract connector IDs from metadata
            connector_ids = []
            for service in sql_services:
                try:
                    metadata = service.get_service_metadata()
                    connector_id = metadata.get("connector_id") or metadata.get("service_name")
                    if connector_id:
                        connector_ids.append(connector_id)
                except Exception as e:
                    logger.warning(f"Failed to get metadata from SQL service: {e}")
                    continue

            logger.info(f"Discovered {len(connector_ids)} SQL connectors: {connector_ids}")
            return connector_ids

        except Exception as e:
            logger.error(f"Failed to discover SQL connectors: {e}")
            return []

    async def _discover_rest_connectors(self) -> List[str]:
        """Discover all registered REST connectors via ToolBus.

        Returns:
            List of REST connector IDs

        TODO Phase 2: Implement REST connector discovery
        Implementation:
        1. Query tool_bus for tools with metadata:
           - data_source=True, data_source_type="rest"
        2. Extract connector_id from each service's metadata
        3. Return list of connector IDs
        4. Similar pattern to _discover_sql_connectors()
        """
        # TODO: Implement REST connector discovery
        raise NotImplementedError("REST connector discovery not yet implemented")

    async def _discover_hl7_connectors(self) -> List[str]:
        """Discover all registered HL7 connectors via ToolBus.

        Returns:
            List of HL7 connector IDs

        TODO Phase 2+: Implement HL7 connector discovery
        Implementation:
        1. Query tool_bus for tools with metadata:
           - data_source=True, data_source_type="hl7"
        2. Extract connector_id from each service's metadata
        3. Return list of connector IDs
        4. Similar pattern to _discover_sql_connectors()

        Note: HL7 is a future feature and lower priority than REST
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
        """
        import hashlib
        import json

        try:
            # Call SQL export tool via ToolBus
            # SQL tools are registered with fixed names (sql_export_user, not connector_id prefix)
            tool_name = "sql_export_user"
            exec_result = await self._tool_bus.execute_tool(
                tool_name=tool_name,
                parameters={
                    "connector_id": connector_id,
                    "user_identifier": user_identifier,
                    "identifier_type": "email",  # Default to email for DSAR requests
                },
                handler_name="default",
            )

            # Parse export result from ToolExecutionResult
            if exec_result.data and isinstance(exec_result.data, dict):
                data = exec_result.data.get("data", {})
                tables = exec_result.data.get("tables_scanned", [])
                total_records = exec_result.data.get("total_records", 0)
            else:
                # Fallback: treat result as data
                data = {"export": str(exec_result.data) if exec_result.data else ""}
                tables = []
                total_records = 0

            # Calculate checksum
            data_json = json.dumps(data, sort_keys=True)
            checksum = hashlib.sha256(data_json.encode("utf-8")).hexdigest()

            return DataSourceExport(
                source_id=connector_id,
                source_type="sql",
                source_name=connector_id,
                tables_or_endpoints=tables,
                total_records=total_records,
                data=data,
                checksum=checksum,
                export_timestamp=self._now().isoformat(),
                errors=[],
            )

        except Exception as e:
            logger.exception(f"Failed to export from SQL connector {connector_id}: {e}")
            return DataSourceExport(
                source_id=connector_id,
                source_type="sql",
                source_name=connector_id,
                export_timestamp=self._now().isoformat(),
                errors=[str(e)],
            )

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
        """
        try:
            # Call SQL delete tool via ToolBus
            # SQL tools are registered with fixed names (sql_delete_user, not connector_id prefix)
            tool_name = "sql_delete_user"
            exec_result = await self._tool_bus.execute_tool(
                tool_name=tool_name,
                parameters={
                    "connector_id": connector_id,
                    "user_identifier": user_identifier,
                    "identifier_type": "email",  # Default to email for DSAR requests
                    "verify": verify,
                },
                handler_name="default",
            )

            # Parse deletion result from ToolExecutionResult
            if exec_result.data and isinstance(exec_result.data, dict):
                success = exec_result.data.get("success", False)
                tables_affected = exec_result.data.get("tables_affected", [])
                total_records_deleted = exec_result.data.get("total_records_deleted", 0)
            else:
                # Fallback: assume success if no error
                success = exec_result.success
                tables_affected = []
                total_records_deleted = 0

            # Verify deletion if requested
            verification_passed = False
            if verify and success:
                verification_passed = await self._verify_deletion_sql(connector_id, user_identifier)

            return DataSourceDeletion(
                source_id=connector_id,
                source_type="sql",
                source_name=connector_id,
                success=success,
                tables_affected=tables_affected,
                total_records_deleted=total_records_deleted,
                verification_passed=verification_passed,
                deletion_timestamp=self._now().isoformat(),
                errors=[],
            )

        except Exception as e:
            logger.exception(f"Failed to delete from SQL connector {connector_id}: {e}")
            return DataSourceDeletion(
                source_id=connector_id,
                source_type="sql",
                source_name=connector_id,
                success=False,
                deletion_timestamp=self._now().isoformat(),
                errors=[str(e)],
            )

    async def _verify_deletion_sql(self, connector_id: str, user_identifier: str) -> bool:
        """Verify user data deletion from SQL connector.

        Args:
            connector_id: SQL connector ID
            user_identifier: User identifier

        Returns:
            True if zero data confirmed, False otherwise
        """
        try:
            # Call SQL verify_deletion tool via ToolBus
            # SQL tools are registered with fixed names (sql_verify_deletion, not connector_id prefix)
            tool_name = "sql_verify_deletion"
            exec_result = await self._tool_bus.execute_tool(
                tool_name=tool_name,
                parameters={
                    "connector_id": connector_id,
                    "user_identifier": user_identifier,
                    "identifier_type": "email",  # Default to email for DSAR requests
                },
                handler_name="default",
            )

            # Parse verification result from ToolExecutionResult
            if exec_result.data and isinstance(exec_result.data, dict):
                zero_data_confirmed = bool(exec_result.data.get("zero_data_confirmed", False))
                return zero_data_confirmed
            elif isinstance(exec_result.data, bool):
                return exec_result.data
            else:
                # Fallback: assume not verified if unexpected result
                logger.warning(f"Unexpected verification result from {connector_id}: {exec_result.data}")
                return False

        except Exception as e:
            logger.exception(f"Failed to verify deletion from SQL connector {connector_id}: {e}")
            return False

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
