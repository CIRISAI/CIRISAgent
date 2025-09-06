"""
Consolidated Graph Audit Service

Combines functionality from:
- AuditService (file-based)
- SignedAuditService (cryptographic signatures)
- GraphAuditService (graph-based storage)

This service provides:
1. Graph-based storage (everything is memory)
2. Optional file export for compliance
3. Cryptographic hash chain for tamper evidence
4. Unified interface for all audit operations
"""

import asyncio
import json
import logging
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Union
from uuid import uuid4

# Optional import for psutil
try:
    import psutil

    PSUTIL_AVAILABLE = True
except ImportError:
    psutil = None  # type: ignore
    PSUTIL_AVAILABLE = False

if TYPE_CHECKING:
    from ciris_engine.logic.registries.base import ServiceRegistry

from ciris_engine.constants import UTC_TIMEZONE_SUFFIX
from ciris_engine.logic.audit.hash_chain import AuditHashChain
from ciris_engine.logic.audit.verifier import AuditVerifier
from ciris_engine.logic.buses.memory_bus import MemoryBus
from ciris_engine.logic.services.base_graph_service import BaseGraphService
from ciris_engine.protocols.services import AuditService as AuditServiceProtocol
from ciris_engine.protocols.services.lifecycle.time import TimeServiceProtocol
from ciris_engine.schemas.runtime.audit import AuditActionContext, AuditRequest
from ciris_engine.schemas.runtime.enums import HandlerActionType, ServiceType
from ciris_engine.schemas.runtime.memory import TimeSeriesDataPoint
from ciris_engine.schemas.services.graph.audit import AuditEventData, AuditQuery, VerificationReport

# TSDB functionality integrated into graph nodes
from ciris_engine.schemas.services.graph_core import GraphNode, GraphScope, NodeType
from ciris_engine.schemas.services.nodes import AuditEntry as AuditEntryNode
from ciris_engine.schemas.services.nodes import AuditEntryContext
from ciris_engine.schemas.services.operations import MemoryOpStatus, MemoryQuery

# Type alias for protocol compatibility
AuditEntry = AuditEntryNode

logger = logging.getLogger(__name__)

try:
    from ciris_engine.logic.audit.signature_manager import AuditSignatureManager
except ImportError as e:
    logger.error(f"Failed to import AuditSignatureManager: {e}")
    raise


class GraphAuditService(BaseGraphService, AuditServiceProtocol):
    """
    Consolidated audit service that stores all audit entries in the graph.

    Features:
    - Primary storage in graph (everything is memory)
    - Optional file export for compliance
    - Cryptographic hash chain for integrity
    - Digital signatures for non-repudiation
    - Unified interface for all audit operations
    """

    def __init__(
        self,
        memory_bus: Optional[MemoryBus] = None,
        time_service: Optional[TimeServiceProtocol] = None,
        # File export options
        export_path: Optional[str] = None,
        export_format: str = "jsonl",  # jsonl, csv, or sqlite
        # Hash chain options
        enable_hash_chain: bool = True,
        db_path: str = "ciris_audit.db",
        key_path: str = "audit_keys",
        # Retention options
        retention_days: int = 90,
        cache_size: int = 1000,
    ) -> None:
        """
        Initialize the consolidated audit service.

        Args:
            memory_bus: Bus for graph storage operations
            time_service: Time service for consistent timestamps
            export_path: Optional path for file exports
            export_format: Format for exports (jsonl, csv, sqlite)
            enable_hash_chain: Whether to maintain cryptographic hash chain
            db_path: Path for hash chain database
            key_path: Directory for signing keys
            retention_days: How long to retain audit data
            cache_size: Size of in-memory cache
        """
        if not time_service:
            raise RuntimeError("CRITICAL: TimeService is required for GraphAuditService")

        # Initialize BaseGraphService with version 2.0.0
        super().__init__(memory_bus=memory_bus, time_service=time_service, version="2.0.0")

        self._service_registry: Optional["ServiceRegistry"] = None

        # Export configuration
        self.export_path = Path(export_path) if export_path else None
        self.export_format = export_format

        # Hash chain configuration
        self.enable_hash_chain = enable_hash_chain
        self.db_path = Path(db_path)
        self.key_path = Path(key_path)

        # Retention configuration
        self.retention_days = retention_days

        # Cache for recent entries
        self._recent_entries: List[AuditRequest] = []
        self._max_cached_entries = cache_size

        # Hash chain components
        self.hash_chain: Optional[AuditHashChain] = None
        self.signature_manager: Optional[AuditSignatureManager] = None
        self.verifier: Optional[AuditVerifier] = None
        self._db_connection: Optional[sqlite3.Connection] = None

        # Export buffer
        self._export_buffer: List[AuditRequest] = []
        self._export_task: Optional[asyncio.Task] = None

        # Memory tracking
        self._process = psutil.Process() if PSUTIL_AVAILABLE else None

        # Track uptime
        self._start_time: Optional[datetime] = None

        # Lock for hash chain operations
        self._hash_chain_lock = asyncio.Lock()

    def _set_service_registry(self, registry: object) -> None:
        """Set the service registry for accessing memory bus."""
        from ciris_engine.logic.registries.base import ServiceRegistry

        if isinstance(registry, ServiceRegistry):
            self._service_registry = registry
        if not self._memory_bus and self._service_registry:
            try:
                from ciris_engine.logic.buses import MemoryBus

                # ServiceRegistry is already imported above from base module
                if self._time_service:
                    self._memory_bus = MemoryBus(self._service_registry, self._time_service)
            except Exception as e:
                logger.error(f"Failed to initialize memory bus: {e}")

    async def start(self) -> None:
        """Start the audit service."""
        # Don't call super() as BaseService has async start
        self._started = True

        logger.info("Starting consolidated GraphAuditService")

        # Set start time
        if self._time_service:
            self._start_time = self._time_service.now()
        else:
            self._start_time = datetime.now()

        # Initialize hash chain if enabled
        if self.enable_hash_chain:
            await self._initialize_hash_chain()

        # Create export directory if needed
        if self.export_path:
            self.export_path.parent.mkdir(parents=True, exist_ok=True)

        # Start export task if configured
        if self.export_path:
            self._export_task = asyncio.create_task(self._export_worker())

        logger.info("GraphAuditService started - all audit data flows through graph")

    async def stop(self) -> None:
        """Stop the audit service."""
        # Flush export buffer
        if self._export_buffer:
            await self._flush_exports()

        # Cancel export task
        if self._export_task:
            self._export_task.cancel()
            try:
                await self._export_task
            except asyncio.CancelledError:
                pass  # NOSONAR - Expected when stopping the service in stop()

        # Log final shutdown event BEFORE closing database
        from ciris_engine.schemas.services.graph.audit import AuditEventData

        shutdown_event = AuditEventData(
            entity_id="audit_service",
            actor="system",
            outcome="success",
            severity="info",
            action="shutdown",
            resource="audit_service",
            reason="service_shutdown",
            metadata={"cached_entries": len(self._recent_entries), "pending_exports": len(self._export_buffer)},
        )
        try:
            await self.log_event("audit_service_shutdown", shutdown_event.model_dump())
        except Exception as e:
            logger.warning(f"Failed to log shutdown event: {e}")

        # Close database connection AFTER logging
        if self._db_connection:
            self._db_connection.close()

        logger.info("GraphAuditService stopped")

        # Don't call super() as BaseService has async stop
        self._started = False

    async def log_action(
        self, action_type: HandlerActionType, context: AuditActionContext, outcome: Optional[str] = None
    ) -> None:
        """Log an action by storing it in the graph."""
        try:
            # Create audit entry
            entry = AuditRequest(
                entry_id=str(uuid4()),
                timestamp=self._time_service.now() if self._time_service else datetime.now(),
                entity_id=context.thought_id,
                event_type=action_type.value,
                actor=context.handler_name or "system",
                details={
                    "action_type": action_type.value,
                    "thought_id": context.thought_id,
                    "task_id": context.task_id,
                    "handler_name": context.handler_name,
                    "metadata": str(getattr(context, "metadata", {})),
                },
                outcome=outcome,
            )

            # Store in graph
            await self._store_entry_in_graph(entry, action_type)

            # Add to hash chain if enabled
            if self.enable_hash_chain:
                await self._add_to_hash_chain(entry)

            # Cache for quick access
            self._cache_entry(entry)

            # Queue for export if configured
            if self.export_path:
                self._export_buffer.append(entry)

        except Exception as e:
            logger.error(f"Failed to log action {action_type}: {e}")

    async def log_event(
        self, event_type: str, event_data: Union[Dict[Any, Any], AuditEventData], **kwargs: object
    ) -> None:
        """Log a general event.

        Args:
            event_type: Type of event being logged
            event_data: Event data as AuditEventData object or dict with matching fields
        """
        # Convert dict to AuditEventData if needed
        if isinstance(event_data, dict):
            # Extract required fields with defaults
            audit_data = AuditEventData(
                entity_id=str(event_data.get("thought_id", event_data.get("entity_id", "unknown"))),
                actor=str(event_data.get("handler_name", event_data.get("actor", "system"))),
                outcome=event_data.get("outcome", "success"),
                severity=event_data.get("severity", "info"),
                action=event_data.get("action", event_type),
                resource=event_data.get("resource", event_type),
                reason=event_data.get("reason", "event_logged"),
                metadata=event_data.get("metadata", {}) if "metadata" in event_data else {},
            )
        elif isinstance(event_data, AuditEventData):
            # Already an AuditEventData object
            audit_data = event_data
        else:
            # Fallback for unexpected types
            audit_data = AuditEventData(  # type: ignore[unreachable]
                entity_id="unknown",
                actor="system",
                outcome="success",
                severity="info",
                action=event_type,
                resource=event_type,
                reason="event_logged",
                metadata={},
            )
        try:
            # Create audit entry with string-only details
            details_dict = {}
            for key, value in audit_data.model_dump().items():
                if value is not None:
                    details_dict[key] = str(value) if not isinstance(value, str) else value

            entry = AuditRequest(
                entry_id=str(uuid4()),
                timestamp=self._time_service.now() if self._time_service else datetime.now(),
                entity_id=audit_data.entity_id,
                event_type=event_type,
                actor=audit_data.actor,
                details=details_dict,
                outcome=audit_data.outcome,
            )

            # Create graph node
            node = AuditEntryNode(
                id=f"audit_{entry.entry_id}",
                action=event_type,
                actor=entry.actor,
                timestamp=entry.timestamp,
                context=AuditEntryContext(
                    service_name=self.__class__.__name__,
                    correlation_id=entry.entry_id,
                    additional_data={
                        "event_type": event_type,
                        "severity": audit_data.severity,
                        "outcome": entry.outcome or "logged",
                    },
                ),
                signature=None,  # Will be set by hash chain if enabled
                hash_chain=None,  # Will be set by hash chain if enabled
                scope=GraphScope.LOCAL,
                attributes={},
            )

            # Store in graph
            if self._memory_bus:
                await self._memory_bus.memorize(
                    node=node.to_graph_node(),
                    handler_name="audit_service",
                    metadata={"audit_entry": entry.model_dump(), "event": True, "immutable": True},
                )

            # Add to hash chain if enabled
            logger.debug(f"enable_hash_chain={self.enable_hash_chain}")
            if self.enable_hash_chain:
                logger.debug("Adding entry to hash chain")
                await self._add_to_hash_chain(entry)
            else:
                logger.debug("Hash chain disabled, not writing to audit_log table")

            # Cache and export
            self._cache_entry(entry)
            if self.export_path:
                logger.debug(f"Adding to export buffer, path={self.export_path}")
                self._export_buffer.append(entry)
            else:
                logger.debug("No export path configured")

            # Create trace correlation for this event
            from ciris_engine.schemas.runtime.enums import HandlerActionType

            action_type = HandlerActionType.OBSERVE  # Default for general audit events
            await self._create_trace_correlation(entry, action_type)

        except Exception as e:
            logger.error(f"Failed to log event {event_type}: {e}")

    async def log_conscience_event(
        self, thought_id: str, decision: str, reasoning: str, metadata: Optional[dict] = None
    ) -> None:
        """Log conscience check events."""
        # Create proper AuditEventData object
        from ciris_engine.schemas.services.graph.audit import AuditEventData

        event_data = AuditEventData(
            entity_id=thought_id,
            actor="conscience_system",
            outcome="allowed" if decision == "ALLOW" else "denied",
            severity="high" if decision != "ALLOW" else "info",
            action="conscience_check",
            resource="conscience",
            reason=reasoning,
            metadata=metadata or {},
        )

        await self.log_event("conscience_check", event_data.model_dump())

    async def get_audit_trail(
        self, entity_id: Optional[str] = None, hours: int = 24, action_types: Optional[List[str]] = None
    ) -> List[AuditEntry]:
        """Get audit trail for an entity."""
        # Check cache first if entity_id provided
        cached = []
        if entity_id:
            cached = [e for e in self._recent_entries if e.entity_id == entity_id]
        else:
            cached = list(self._recent_entries)

        # Query from graph
        if not self._memory_bus:
            logger.error("Memory bus not available for audit queries")
            # Convert cached AuditRequest to AuditEntry
            return [self._audit_request_to_entry(e) for e in cached]

        try:
            # Query timeseries data
            timeseries_data = await self._memory_bus.recall_timeseries(
                scope="local", hours=hours, correlation_types=["AUDIT_EVENT"], handler_name="audit_service"
            )

            # Convert to AuditEntry objects and filter
            results = self._convert_timeseries_to_entries(timeseries_data, entity_id)

            # Combine with cache and deduplicate
            # Convert AuditRequest to AuditEntry if needed
            all_entries: Dict[str, AuditEntry] = {}
            for req in cached:
                if hasattr(req, "entry_id"):
                    entry = self._audit_request_to_entry(req)
                    all_entries[entry.id] = entry
            for result_entry in results:
                if hasattr(result_entry, "id"):
                    all_entries[result_entry.id] = result_entry
                elif hasattr(result_entry, "entry_id"):
                    # This shouldn't happen but handle it anyway
                    entry = self._audit_request_to_entry(result_entry)  # type: ignore
                    all_entries[entry.id] = entry

            # Sort and limit
            sorted_entries = sorted(all_entries.values(), key=lambda x: x.timestamp, reverse=True)

            # Apply action_types filter if provided
            if action_types:
                sorted_entries = [e for e in sorted_entries if hasattr(e, "action") and e.action in action_types]

            return sorted_entries

        except Exception as e:
            logger.error(f"Failed to get audit trail: {e}")
            # Convert cached AuditRequest to AuditEntry
            return [self._audit_request_to_entry(e) for e in cached]

    async def query_audit_trail(self, query: AuditQuery) -> List[AuditEntry]:
        """Query audit trail with advanced filters - implements AuditServiceProtocol."""
        if not self._memory_bus:
            return []

        # Query audit_entry nodes directly from graph memory
        from ciris_engine.schemas.services.graph_core import NodeType

        # Search for all audit entries using query string format
        # The search method looks for "type:" in the query string, not in filters
        search_query = f"type:{NodeType.AUDIT_ENTRY.value} scope:{GraphScope.LOCAL.value}"

        # Search for all audit entries
        nodes = await self._memory_bus.search(search_query, filters=None, handler_name="audit_service")

        # Convert GraphNode to AuditEntry
        audit_entries = []
        for node in nodes:
            # Extract audit data from node attributes
            if isinstance(node.attributes, dict):
                attrs = node.attributes
            elif hasattr(node.attributes, "model_dump"):
                attrs = node.attributes.model_dump()
            else:
                continue

            # Parse timestamp if it's a string
            timestamp = attrs.get("timestamp", self._time_service.now() if self._time_service else datetime.now())
            if isinstance(timestamp, str):
                try:
                    timestamp = datetime.fromisoformat(timestamp.replace("Z", UTC_TIMEZONE_SUFFIX))
                except (ValueError, TypeError):
                    timestamp = self._time_service.now() if self._time_service else datetime.now()

            # Extract context data - handle both dict and nested structures
            context_data = attrs.get("context", {})
            if isinstance(context_data, dict):
                # Extract service_name from nested structure or top level
                service_name = context_data.get("service_name", attrs.get("service_name", ""))
                correlation_id = context_data.get("correlation_id", attrs.get("correlation_id", ""))

                # Get additional_data and flatten it to primitives only
                additional_data = context_data.get("additional_data", {})
                if isinstance(additional_data, dict):
                    # Filter out non-primitive values
                    flat_data: Dict[str, Union[str, int, float, bool]] = {}
                    for k, v in additional_data.items():
                        if isinstance(v, (str, int, float, bool)):
                            flat_data[k] = v
                        elif v is None:
                            # Skip None values
                            continue
                        else:
                            # Convert complex types to string
                            flat_data[k] = str(v)
                    additional_data = flat_data
            else:
                service_name = attrs.get("service_name", "")
                correlation_id = attrs.get("correlation_id", "")
                additional_data = {}

            # Create AuditEntryNode from graph data
            entry = AuditEntryNode(
                id=node.id,
                action=attrs.get("action", ""),
                actor=attrs.get("actor", ""),
                timestamp=timestamp,
                context=AuditEntryContext(
                    service_name=service_name, correlation_id=correlation_id, additional_data=additional_data
                ),
                signature=attrs.get("signature"),
                hash_chain=attrs.get("hash_chain"),
                scope=node.scope,
                attributes={},
            )

            # Apply filters from query
            if query.start_time and entry.timestamp < query.start_time:
                continue
            if query.end_time and entry.timestamp > query.end_time:
                continue
            if query.actor and entry.actor != query.actor:
                continue
            if query.event_type and entry.action != query.event_type:
                continue
            if query.entity_id and entry.context.correlation_id != query.entity_id:
                continue
            if query.search_text:
                # Simple text search in action and actor
                search_lower = query.search_text.lower()
                if search_lower not in entry.action.lower() and search_lower not in entry.actor.lower():
                    continue

            audit_entries.append(entry)

        # Sort and paginate
        audit_entries.sort(key=lambda e: e.timestamp, reverse=query.order_desc)

        # Apply offset and limit
        start = query.offset
        end = query.offset + query.limit if query.limit else None

        return audit_entries[start:end]

    async def verify_audit_integrity(self) -> VerificationReport:
        """Verify the integrity of the audit trail."""
        start_time = self._time_service.now() if self._time_service else datetime.now()

        if not self.enable_hash_chain or not self.verifier:
            return VerificationReport(
                verified=False,
                total_entries=0,
                valid_entries=0,
                invalid_entries=0,
                chain_intact=False,
                verification_started=start_time,
                verification_completed=self._time_service.now() if self._time_service else datetime.now(),
                duration_ms=0,
                errors=["Hash chain not enabled"],
            )

        try:
            result = await asyncio.to_thread(self.verifier.verify_complete_chain)
            end_time = self._time_service.now() if self._time_service else datetime.now()

            # Extract all errors
            all_errors = []
            all_errors.extend(result.hash_chain_errors or [])
            all_errors.extend(result.signature_errors or [])
            if result.error:
                all_errors.append(result.error)

            return VerificationReport(
                verified=result.valid,
                total_entries=result.entries_verified,
                valid_entries=result.entries_verified if result.valid else 0,
                invalid_entries=0 if result.valid else result.entries_verified,
                chain_intact=result.hash_chain_valid,
                last_valid_entry=None,  # Not provided by CompleteVerificationResult
                first_invalid_entry=None,  # Not provided by CompleteVerificationResult
                verification_started=start_time,
                verification_completed=end_time,
                duration_ms=(end_time - start_time).total_seconds() * 1000,
                errors=all_errors,
                warnings=[],  # No warnings in CompleteVerificationResult
            )
        except Exception as e:
            logger.error(f"Audit verification failed: {e}")
            end_time = self._time_service.now() if self._time_service else datetime.now()
            return VerificationReport(
                verified=False,
                total_entries=0,
                valid_entries=0,
                invalid_entries=0,
                chain_intact=False,
                verification_started=start_time,
                verification_completed=end_time,
                duration_ms=(end_time - start_time).total_seconds() * 1000,
                errors=[str(e)],
            )

    async def get_verification_report(self) -> VerificationReport:
        """Generate a comprehensive audit verification report."""
        start_time = self._time_service.now() if self._time_service else datetime.now()

        if not self.enable_hash_chain or not self.verifier:
            return VerificationReport(
                verified=False,
                total_entries=0,
                valid_entries=0,
                invalid_entries=0,
                chain_intact=False,
                verification_started=start_time,
                verification_completed=self._time_service.now() if self._time_service else datetime.now(),
                duration_ms=0,
                errors=["Hash chain not enabled"],
            )

        try:
            # Delegate to verify_audit_integrity which already returns VerificationReport
            return await self.verify_audit_integrity()
        except Exception as e:
            logger.error(f"Failed to generate verification report: {e}")
            end_time = self._time_service.now() if self._time_service else datetime.now()
            return VerificationReport(
                verified=False,
                total_entries=0,
                valid_entries=0,
                invalid_entries=0,
                chain_intact=False,
                verification_started=start_time,
                verification_completed=end_time,
                duration_ms=(end_time - start_time).total_seconds() * 1000,
                errors=[str(e)],
            )

    async def export_audit_data(
        self, start_time: Optional[datetime] = None, end_time: Optional[datetime] = None, format: Optional[str] = None
    ) -> str:
        """Export audit data to file."""
        format = format or self.export_format

        # Query data
        from ciris_engine.schemas.services.graph.audit import AuditQuery

        query = AuditQuery(start_time=start_time, end_time=end_time, limit=10000)  # Higher limit for exports
        entries = await self.query_audit_trail(query)

        # Generate filename
        timestamp = (self._time_service.now() if self._time_service else datetime.now()).strftime("%Y%m%d_%H%M%S")
        if not self.export_path:
            raise ValueError("Export path not configured")
        filename = self.export_path.parent / f"audit_export_{timestamp}.{format}"

        # Convert AuditEntry to AuditRequest for export methods
        audit_requests = []
        for entry in entries:
            audit_requests.append(
                AuditRequest(
                    entry_id=entry.id,
                    timestamp=entry.timestamp,
                    entity_id=entry.context.correlation_id or entry.actor,
                    event_type=entry.action,
                    actor=entry.actor,
                    details={
                        "service": entry.context.service_name or "",
                        "method": entry.context.method_name or "",
                        "user_id": entry.context.user_id or "",
                        **(
                            {k: str(v) for k, v in entry.context.additional_data.items()}
                            if entry.context.additional_data
                            else {}
                        ),
                    },
                    outcome=None,  # AuditEntry doesn't have outcome field
                )
            )

        # Export based on format
        if format == "jsonl":
            await self._export_jsonl(audit_requests, filename)
        elif format == "csv":
            await self._export_csv(audit_requests, filename)
        elif format == "sqlite":
            await self._export_sqlite(audit_requests, filename)
        else:
            raise ValueError(f"Unsupported export format: {format}")

        return str(filename)

    # ========== GraphServiceProtocol Implementation ==========

    def get_node_type(self) -> str:
        """Get the type of nodes this service manages."""
        return "AUDIT"

    # ========== ServiceProtocol Implementation ==========

    def _collect_custom_metrics(self) -> Dict[str, float]:
        """Collect audit-specific metrics."""
        metrics = super()._collect_custom_metrics()

        # Calculate cache size
        cache_size_mb = 0.0
        try:
            cache_size = sys.getsizeof(self._recent_entries) + sys.getsizeof(self._export_buffer)
            cache_size_mb = cache_size / 1024 / 1024
        except Exception:
            pass

        # Add audit-specific metrics
        metrics.update(
            {
                "cached_entries": float(len(self._recent_entries)),
                "pending_exports": float(len(self._export_buffer)),
                "hash_chain_enabled": float(self.enable_hash_chain),
                "cache_size_mb": cache_size_mb,
            }
        )

        return metrics

    async def get_metrics(self) -> Dict[str, float]:
        """
        Get all audit service metrics including base, custom, and v1.4.3 specific.
        """
        # Get all base + custom metrics
        metrics = self._collect_metrics()
        # Count total events from cache and estimate from graph
        total_events = len(self._recent_entries)

        # Count events by severity from cached entries
        severity_counts = {"info": 0, "low": 0, "medium": 0, "high": 0, "critical": 0}
        compliance_checks = 0

        # Analyze cached entries for severity and compliance
        for entry in self._recent_entries:
            # Extract severity from details or determine from event type
            details = entry.details or {}
            severity = details.get("severity", "info")

            # Count by severity
            if severity in severity_counts:
                severity_counts[severity] += 1
            else:
                severity_counts["info"] += 1

            # Count compliance-related events
            event_type = entry.event_type.lower()
            if any(keyword in event_type for keyword in ["compliance", "audit", "verify", "check", "integrity"]):
                compliance_checks += 1

        # Calculate uptime
        uptime_seconds = 0.0
        if self._start_time:
            current_time = self._time_service.now() if self._time_service else datetime.now()
            uptime_seconds = (current_time - self._start_time).total_seconds()

        # Return exact metrics from v1.4.3 set
        # Add v1.4.3 specific metrics
        metrics.update(
            {
                "audit_events_total": float(total_events),
                "audit_events_by_severity": float(sum(severity_counts.values())),  # Flattened count
                "audit_compliance_checks": float(compliance_checks),
                "audit_uptime_seconds": uptime_seconds,
            }
        )

        return metrics

    # ========== Private Helper Methods ==========

    async def _store_entry_in_graph(self, entry: AuditRequest, action_type: HandlerActionType) -> None:
        """Store an audit entry in the graph and create a trace correlation."""
        if not self._memory_bus:
            logger.error("Memory bus not available for audit storage")
            return

        # Create specialized audit node
        node = AuditEntryNode(
            id=f"audit_{action_type.value}_{entry.entry_id}",
            action=action_type.value,
            actor=entry.actor,
            timestamp=entry.timestamp,
            context=AuditEntryContext(
                service_name=entry.details.get("handler_name", ""),
                correlation_id=entry.entry_id,
                additional_data={
                    "thought_id": entry.details.get("thought_id", ""),
                    "task_id": entry.details.get("task_id", ""),
                    "outcome": entry.outcome or "success",
                    "severity": self._get_severity(action_type),
                },
            ),
            scope=GraphScope.LOCAL,
            attributes={"action_type": action_type.value, "event_id": entry.entry_id},
        )

        # Store via memory bus
        result = await self._memory_bus.memorize(
            node=node.to_graph_node(),
            handler_name="audit_service",
            metadata={"audit_entry": entry.model_dump(), "immutable": True},
        )

        if result.status != MemoryOpStatus.OK:
            logger.error(f"Failed to store audit entry in graph: {result}")

        # Create a ServiceCorrelation for trace tracking
        await self._create_trace_correlation(entry, action_type)

    async def _create_trace_correlation(self, entry: AuditRequest, action_type: HandlerActionType) -> None:
        """Create a ServiceCorrelation for trace tracking."""
        logger.info(f"Creating trace correlation for audit event {entry.entry_id}")
        try:
            from ciris_engine.schemas.telemetry.core import (
                CorrelationType,
                ServiceCorrelation,
                ServiceCorrelationStatus,
                ServiceRequestData,
                ServiceResponseData,
                TraceContext,
            )

            # Get telemetry service from runtime
            telemetry_service = None
            if hasattr(self, "_runtime") and self._runtime:
                telemetry_service = getattr(self._runtime, "telemetry_service", None)

            if not telemetry_service:
                # Try to get from service registry
                from ciris_engine.logic.registries.service_registry import ServiceRegistry

                registry = ServiceRegistry()
                from ciris_engine.schemas.runtime.enums import ServiceType

                telemetry_service = registry.get_service(ServiceType.TELEMETRY)

            if not telemetry_service:
                logger.debug("Telemetry service not available for trace correlation")
                return

            # Create correlation
            correlation = ServiceCorrelation(
                correlation_id=entry.entry_id,
                correlation_type=CorrelationType.AUDIT_EVENT,
                service_type="audit",
                handler_name=entry.actor,
                action_type=action_type.value,
                request_data=ServiceRequestData(
                    service_type="audit",
                    method_name="log_event",
                    thought_id=entry.details.get("thought_id"),
                    task_id=entry.details.get("task_id"),
                    parameters={
                        "action": action_type.value,
                        "entity_id": entry.entity_id,
                    },
                    request_timestamp=entry.timestamp,
                ),
                response_data=ServiceResponseData(
                    success=True if entry.outcome == "success" else False,
                    execution_time_ms=0,  # We don't track this for audit events
                    response_timestamp=entry.timestamp,  # Use same timestamp for audit events
                ),
                status=ServiceCorrelationStatus.COMPLETED,
                created_at=entry.timestamp,
                updated_at=entry.timestamp,
                timestamp=entry.timestamp,
                trace_context=TraceContext(
                    trace_id=f"trace_{entry.entry_id}",
                    span_id=entry.entry_id,
                    parent_span_id=entry.details.get("thought_id"),
                    span_name=f"audit.{action_type.value}",
                ),
                tags={
                    "action": action_type.value,
                    "actor": entry.actor,
                    "severity": self._get_severity(action_type),
                },
            )

            # Store correlation in telemetry service
            if hasattr(telemetry_service, "_store_correlation"):
                await telemetry_service._store_correlation(correlation)
                logger.info(f"Successfully stored trace correlation for audit event {entry.entry_id}")
            else:
                logger.warning(f"Telemetry service does not have _store_correlation method")

        except Exception as e:
            logger.error(f"Failed to create trace correlation: {e}", exc_info=True)
            # Don't fail the audit operation if trace creation fails

    async def _initialize_hash_chain(self) -> None:
        """Initialize hash chain components."""
        try:
            # Ensure directories exist
            self.key_path.mkdir(parents=True, exist_ok=True)

            # Initialize database
            await self._init_database()

            # Initialize components
            self.hash_chain = AuditHashChain(str(self.db_path))
            logger.debug(
                f"Initializing AuditSignatureManager with key_path={self.key_path}, db_path={self.db_path}, time_service={self._time_service}"
            )

            # Ensure time_service is not None
            if not self._time_service:
                raise RuntimeError("TimeService is None - cannot initialize AuditSignatureManager")

            # Check actual types
            logger.debug(
                f"Types: key_path={type(self.key_path)}, db_path={type(self.db_path)}, time_service={type(self._time_service)}"
            )

            self.signature_manager = AuditSignatureManager(str(self.key_path), str(self.db_path), self._time_service)
            self.verifier = AuditVerifier(str(self.db_path), str(self.key_path), self._time_service)

            # Initialize in thread
            await asyncio.to_thread(self._init_components_sync)

            logger.info("Hash chain audit system initialized")

        except Exception as e:
            logger.error(f"Failed to initialize hash chain: {e}", exc_info=True)
            self.enable_hash_chain = False

    def _init_components_sync(self) -> None:
        """Synchronous initialization of audit components."""
        if not self.hash_chain or not self.signature_manager or not self.verifier:
            raise RuntimeError("Hash chain components not initialized")

        self.hash_chain.initialize()
        self.signature_manager.initialize()
        self.verifier.initialize()

        if not self.signature_manager.test_signing():
            raise RuntimeError("Signing test failed")

    async def _init_database(self) -> None:
        """Initialize the audit database."""

        def _create_tables() -> None:
            conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
            cursor = conn.cursor()

            # Audit log table
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS audit_log (
                    entry_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id TEXT NOT NULL UNIQUE,
                    event_timestamp TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    originator_id TEXT NOT NULL,
                    target_id TEXT,
                    event_summary TEXT,
                    event_payload TEXT,
                    sequence_number INTEGER NOT NULL,
                    previous_hash TEXT NOT NULL,
                    entry_hash TEXT NOT NULL,
                    signature TEXT NOT NULL,
                    signing_key_id TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(sequence_number)
                )
            """
            )

            # Signing keys table
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS audit_signing_keys (
                    key_id TEXT PRIMARY KEY,
                    public_key TEXT NOT NULL,
                    algorithm TEXT NOT NULL DEFAULT 'rsa-pss',
                    key_size INTEGER NOT NULL DEFAULT 2048,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    revoked_at TEXT
                )
            """
            )

            # Indexes
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_audit_log_event_timestamp
                ON audit_log(event_timestamp)
            """
            )

            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_audit_log_event_type
                ON audit_log(event_type)
            """
            )

            conn.commit()
            conn.close()

        await asyncio.to_thread(_create_tables)
        self._db_connection = sqlite3.connect(str(self.db_path), check_same_thread=False)

    async def _add_to_hash_chain(self, entry: AuditRequest) -> None:
        """Add an entry to the hash chain."""
        if not self.enable_hash_chain:
            return

        async with self._hash_chain_lock:

            def _write_to_chain() -> None:
                entry_dict = {
                    "event_id": entry.entry_id,
                    "event_timestamp": entry.timestamp.isoformat(),
                    "event_type": entry.event_type,
                    "originator_id": entry.entity_id,
                    "event_payload": json.dumps(entry.details),
                }

                if not self.hash_chain or not self.signature_manager:
                    raise RuntimeError("Hash chain not available")

                prepared = self.hash_chain.prepare_entry(entry_dict)
                signature = self.signature_manager.sign_entry(prepared["entry_hash"])

                if not self._db_connection:
                    raise RuntimeError("Database connection not available")

                cursor = self._db_connection.cursor()
                cursor.execute(
                    """
                    INSERT INTO audit_log
                    (event_id, event_timestamp, event_type, originator_id,
                     event_summary, event_payload, sequence_number, previous_hash,
                     entry_hash, signature, signing_key_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                    (
                        entry.entry_id,
                        entry.timestamp.isoformat(),
                        entry.event_type,
                        entry.entity_id,
                        f"{entry.event_type} by {entry.actor}",
                        json.dumps(entry.details),
                        prepared["sequence_number"],
                        prepared["previous_hash"],
                        prepared["entry_hash"],
                        signature,
                        self.signature_manager.key_id or "unknown",
                    ),
                )

                self._db_connection.commit()

            try:
                logger.debug(f"About to write to hash chain for entry {entry.entry_id}")
                await asyncio.to_thread(_write_to_chain)
                logger.debug(f"Successfully wrote to hash chain for entry {entry.entry_id}")
            except Exception as e:
                logger.error(f"Failed to add to hash chain: {e}", exc_info=True)

    def _cache_entry(self, entry: AuditRequest) -> None:
        """Add entry to cache."""
        self._recent_entries.append(entry)
        if len(self._recent_entries) > self._max_cached_entries:
            self._recent_entries = self._recent_entries[-self._max_cached_entries :]

    async def _export_worker(self) -> None:
        """Background task to export audit data."""
        while True:
            try:
                await asyncio.sleep(60)  # Export every minute
                if self._export_buffer:
                    await self._flush_exports()
            except asyncio.CancelledError:
                logger.debug("Export worker cancelled")
                raise  # Re-raise to properly exit the task
            except Exception as e:
                logger.error(f"Export worker error: {e}")

    async def _flush_exports(self) -> None:
        """Flush export buffer to file."""
        if not self._export_buffer or not self.export_path:
            return

        try:
            if self.export_format == "jsonl":
                await self._export_jsonl(self._export_buffer, self.export_path)
            elif self.export_format == "csv":
                await self._export_csv(self._export_buffer, self.export_path)
            elif self.export_format == "sqlite":
                await self._export_sqlite(self._export_buffer, self.export_path)

            self._export_buffer.clear()
        except Exception as e:
            logger.error(f"Failed to flush exports: {e}")

    async def _export_jsonl(self, entries: List[AuditRequest], path: Path) -> None:
        """Export entries to JSONL format."""

        def _write_jsonl() -> None:
            with open(path, "a") as f:
                for entry in entries:
                    f.write(json.dumps(entry.model_dump(), default=str) + "\n")

        await asyncio.to_thread(_write_jsonl)

    async def _export_csv(self, entries: List[AuditRequest], path: Path) -> None:
        """Export entries to CSV format."""
        import csv

        def _write_csv() -> None:
            file_exists = path.exists()
            with open(path, "a", newline="") as f:
                writer = csv.writer(f)

                # Write header if new file
                if not file_exists:
                    writer.writerow(["entry_id", "timestamp", "entity_id", "event_type", "actor", "outcome", "details"])

                # Write entries
                for entry in entries:
                    writer.writerow(
                        [
                            entry.entry_id,
                            entry.timestamp.isoformat(),
                            entry.entity_id,
                            entry.event_type,
                            entry.actor,
                            entry.outcome,
                            json.dumps(entry.details),
                        ]
                    )

        await asyncio.to_thread(_write_csv)

    async def _export_sqlite(self, entries: List[AuditRequest], path: Path) -> None:
        """Export entries to SQLite format."""

        def _write_sqlite() -> None:
            conn = sqlite3.connect(str(path), check_same_thread=False)
            cursor = conn.cursor()

            # Create table if needed
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS audit_export (
                    entry_id TEXT PRIMARY KEY,
                    timestamp TEXT NOT NULL,
                    entity_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    outcome TEXT,
                    details TEXT
                )
            """
            )

            # Insert entries
            for entry in entries:
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO audit_export
                    (entry_id, timestamp, entity_id, event_type, actor, outcome, details)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                    (
                        entry.entry_id,
                        entry.timestamp.isoformat(),
                        entry.entity_id,
                        entry.event_type,
                        entry.actor,
                        entry.outcome,
                        json.dumps(entry.details),
                    ),
                )

            conn.commit()
            conn.close()

        await asyncio.to_thread(_write_sqlite)

    def _get_severity(self, action: HandlerActionType) -> str:
        """Determine severity level for an action."""
        if action in [HandlerActionType.DEFER, HandlerActionType.REJECT, HandlerActionType.FORGET]:
            return "high"
        elif action in [HandlerActionType.TOOL, HandlerActionType.MEMORIZE, HandlerActionType.TASK_COMPLETE]:
            return "medium"
        else:
            return "low"

    def _calculate_hours(self, start_time: Optional[datetime], end_time: Optional[datetime]) -> int:
        """Calculate hours for time range."""
        if start_time and end_time:
            return int((end_time - start_time).total_seconds() / 3600)
        elif start_time:
            return int(
                ((self._time_service.now() if self._time_service else datetime.now()) - start_time).total_seconds()
                / 3600
            )
        else:
            return 24 * 30  # Default 30 days

    def _matches_filters(
        self,
        data: GraphNode,
        start_time: Optional[datetime],
        end_time: Optional[datetime],
        action_types: Optional[List[str]],
        thought_id: Optional[str],
        task_id: Optional[str],
    ) -> bool:
        """Check if data matches query filters."""
        # Time filters
        timestamp = data.attributes.created_at if hasattr(data.attributes, "created_at") else data.updated_at
        if timestamp:
            if start_time and timestamp < start_time:
                return False
            if end_time and timestamp > end_time:
                return False

        # Action type filter
        tags = data.attributes.tags if hasattr(data.attributes, "tags") else []
        _tag_dict = dict.fromkeys(tags, True)  # Convert list to dict for lookup

        # Check attributes dict as well
        attrs = data.attributes.model_dump() if hasattr(data.attributes, "model_dump") else {}

        if action_types and attrs.get("action_type") not in action_types:
            return False

        # Entity filters
        if thought_id and attrs.get("thought_id") != thought_id:
            return False
        if task_id and attrs.get("task_id") != task_id:
            return False

        return True

    def _tsdb_to_audit_entry(self, data: GraphNode) -> Optional[AuditRequest]:
        """Convert TSDB node to AuditEntry."""
        # Check if this is an AuditEntryNode by looking for the marker
        attrs = data.attributes if isinstance(data.attributes, dict) else {}

        # If it's an AuditEntryNode stored with to_graph_node(), convert back
        if attrs.get("node_class") == "AuditEntry":
            try:
                audit_node = AuditEntryNode.from_graph_node(data)
                # Convert from AuditEntryNode to runtime AuditRequest
                return AuditRequest(
                    entry_id=audit_node.id.replace("audit_", ""),
                    timestamp=audit_node.timestamp,
                    entity_id=audit_node.context.correlation_id or "",
                    event_type=audit_node.action,
                    actor=audit_node.actor,
                    details={
                        "action_type": audit_node.action,
                        "thought_id": (
                            audit_node.context.additional_data.get("thought_id", "")
                            if audit_node.context.additional_data
                            else ""
                        ),
                        "task_id": (
                            audit_node.context.additional_data.get("task_id", "")
                            if audit_node.context.additional_data
                            else ""
                        ),
                        "handler_name": audit_node.context.service_name or "",
                        "context": audit_node.context.model_dump(),
                    },
                    outcome=(
                        audit_node.context.additional_data.get("outcome")
                        if audit_node.context.additional_data
                        else None
                    ),
                )
            except Exception as e:
                logger.warning(f"Failed to convert AuditEntryNode: {e}, falling back to manual parsing")

        # Fallback: manual parsing for backwards compatibility
        # Extract attributes
        attrs = data.attributes.model_dump() if hasattr(data.attributes, "model_dump") else {}
        _tags = data.attributes.tags if hasattr(data.attributes, "tags") else []

        # Look for action_type in attributes
        action_type = attrs.get("action_type")
        if not action_type and "action_type" in attrs:
            action_type = attrs["action_type"]

        if not action_type:
            return None

        # Get timestamp
        timestamp = data.attributes.created_at if hasattr(data.attributes, "created_at") else data.updated_at
        if not timestamp:
            timestamp = self._time_service.now() if self._time_service else datetime.now()

        return AuditRequest(
            entry_id=attrs.get("event_id", str(uuid4())),
            timestamp=timestamp,
            entity_id=attrs.get("thought_id", "") or attrs.get("task_id", ""),
            event_type=action_type,
            actor=attrs.get("actor", attrs.get("handler_name", "system")),
            details={
                "action_type": action_type,
                "thought_id": attrs.get("thought_id", ""),
                "task_id": attrs.get("task_id", ""),
                "handler_name": attrs.get("handler_name", ""),
                "attributes": attrs,
            },
            outcome=attrs.get("outcome"),
        )

    def _convert_timeseries_to_entries(
        self, timeseries_data: List[TimeSeriesDataPoint], entity_id: Optional[str] = None
    ) -> List[AuditEntry]:
        """Convert timeseries data to audit entries."""
        results: List[AuditEntry] = []

        for data in timeseries_data:
            # Filter by entity if specified
            if entity_id:
                tags = data.tags or {}
                if entity_id not in [tags.get("thought_id"), tags.get("task_id")]:
                    continue

            # Convert TimeSeriesDataPoint to GraphNode for compatibility
            # TimeSeriesDataPoint doesn't directly map to audit entries, skip
            # This method seems to be looking for audit entries stored as timeseries
            # but TimeSeriesDataPoint is for metrics, not audit entries
            continue

        return results

    async def query_events(
        self,
        event_type: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 100,
    ) -> List[dict]:
        """Query audit events."""
        # Call query_audit_trail directly with parameters
        from ciris_engine.schemas.services.graph.audit import AuditQuery

        query = AuditQuery(
            start_time=start_time, end_time=end_time, action_types=[event_type] if event_type else None, limit=limit
        )
        entries = await self.query_audit_trail(query)

        # Convert to dict format expected by protocol
        result = []
        for entry in entries:
            # AuditEntry format (query_audit_trail returns List[AuditEntry])
            result.append(
                {
                    "event_id": entry.id,
                    "event_type": entry.action,
                    "timestamp": entry.timestamp.isoformat() if entry.timestamp else None,
                    "user_id": entry.actor,  # Using actor as user_id
                    "data": {"context": entry.context.model_dump()},
                    "metadata": {"signature": entry.signature} if entry.signature else {},
                }
            )
        return result

    async def get_event_by_id(self, event_id: str) -> Optional[dict]:
        """Get specific audit event by ID."""
        # Query for the specific event

        query = MemoryQuery(
            node_id=event_id, scope=GraphScope.LOCAL, type=NodeType.AUDIT_ENTRY, include_edges=False, depth=1
        )

        if self._memory_bus:
            nodes = await self._memory_bus.recall(query)
            if nodes and len(nodes) > 0:
                # Convert node to AuditEntry using proper conversion
                entry = self._tsdb_to_audit_entry(nodes[0])
                if entry:
                    return {
                        "event_id": entry.entry_id,
                        "event_type": entry.event_type,
                        "timestamp": entry.timestamp.isoformat() if entry.timestamp else None,
                        "user_id": entry.actor,
                        "data": entry.details,
                        "metadata": {"outcome": entry.outcome} if entry.outcome else {},
                    }

        # Also check recent cache
        for entry in self._recent_entries:
            if entry.entry_id == event_id:
                return {
                    "event_id": entry.entry_id,
                    "event_type": entry.event_type,
                    "timestamp": entry.timestamp.isoformat() if entry.timestamp else None,
                    "user_id": entry.actor,
                    "data": entry.details,
                    "metadata": {"outcome": entry.outcome} if entry.outcome else {},
                }

        return None

    def _audit_request_to_entry(self, req: AuditRequest) -> AuditEntry:
        """Convert AuditRequest to AuditEntry."""
        return AuditEntryNode(
            id=f"audit_{req.entry_id}",
            action=req.event_type,
            actor=req.actor,
            timestamp=req.timestamp,
            context=AuditEntryContext(
                service_name=req.details.get("handler_name", ""),
                correlation_id=req.entity_id,
                additional_data={k: str(v) for k, v in req.details.items()},
            ),
            signature=None,
            hash_chain=None,
            scope=GraphScope.LOCAL,
            attributes={},
        )

    # Required methods for BaseGraphService

    def get_service_type(self) -> ServiceType:
        """Get the service type."""
        return ServiceType.AUDIT

    def _get_actions(self) -> List[str]:
        """Get the list of actions this service supports."""
        return [
            "log_action",
            "log_event",
            "log_request",
            "get_audit_trail",
            "query_audit_trail",
            "query_by_actor",
            "query_by_time_range",
            "export_audit_log",
            "verify_integrity",
            "verify_signatures",
            "get_complete_verification_report",
            "query_events",
            "get_event_by_id",
            "verify_audit_integrity",
        ]

    def _check_dependencies(self) -> bool:
        """Check if all dependencies are satisfied."""
        # Check parent dependencies (memory bus)
        if not super()._check_dependencies():
            return False

        # No need to check hash_chain here - it's initialized during start()
        # The hash_chain is an internal component, not an external dependency

        return True
