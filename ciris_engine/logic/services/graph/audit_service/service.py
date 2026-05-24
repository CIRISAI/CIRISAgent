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
import base64
import hashlib
import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Union
from uuid import uuid4

from ciris_engine.logic.utils.jsondict_helpers import get_int, get_str
from ciris_engine.schemas.types import JSONDict

# Optional import for psutil
try:
    import psutil

    PSUTIL_AVAILABLE = True
except ImportError:
    psutil = None  # type: ignore[assignment,unused-ignore]
    PSUTIL_AVAILABLE = False

if TYPE_CHECKING:
    from ciris_engine.logic.registries.base import ServiceRegistry
    from ciris_engine.schemas.audit.core import EventPayload, AuditLogEntry

from ciris_engine.constants import UTC_TIMEZONE_SUFFIX
from ciris_engine.logic.audit.persist_signing import (
    get_signer_material as _audit_signer_material,
    resolve_tenant_id as _audit_tenant_id,
    sign_with_verifier as _audit_sign,
)
from ciris_engine.logic.audit.verifier import AuditVerifier
from ciris_engine.logic.buses.memory_bus import MemoryBus
from ciris_engine.logic.services.base_graph_service import BaseGraphService
from ciris_engine.protocols.infrastructure.base import RegistryAwareServiceProtocol, ServiceRegistryProtocol
from ciris_engine.protocols.services import AuditService as AuditServiceProtocol
from ciris_engine.protocols.services.lifecycle.time import TimeServiceProtocol
from ciris_engine.schemas.audit.hash_chain import AuditEntryResult
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


def _resolve_action_type(event_type: str) -> str:
    """Map an AuditRequest.event_type onto a valid AuditEventType value.

    Persist's audit_log enforces a CHECK constraint (migrations V018/V020)
    locking action_type to the 21 AuditEventType values; the SQLite arm has
    no such CHECK. log_action passes a bare HandlerActionType value
    ('speak'); log_event passes an arbitrary event name ('agent_configured').
    Neither is directly a valid AuditEventType, so normalize both. The
    precise event name is always preserved in the persist payload's
    event_type field.
    """
    from ciris_engine.schemas.audit.core import AuditEventType

    try:
        return AuditEventType(event_type).value
    except ValueError:
        pass
    try:
        return AuditEventType(f"handler_action_{event_type}").value
    except ValueError:
        pass
    return AuditEventType.SYSTEM_EVENT.value


# CIRISVerify briefly blocks signing-key access while a tree attestation runs
# (typically at startup). It surfaces a retryable AttestationInProgressError;
# the signal itself suggests retrying after ~500ms. The agent_configured
# audit event fires during startup, sometimes BEFORE CIRISVerify finishes
# attestation; under the postgres backend's per-op latency on a shared CI
# runner that initial window can stretch past ten retries × 500ms = 5s.
# Budget bumped to 30 × 500ms = 15s, which comfortably covers observed
# attestation completion on the dual-backend matrix.
_AUDIT_SIGN_MAX_RETRIES = 30
_AUDIT_SIGN_RETRY_DELAY_S = 0.5


def _attestation_in_progress_error() -> Optional[type]:
    """Return CIRISVerify's AttestationInProgressError type, if available.

    ciris_verify is an optional adapter, so the type is resolved
    dynamically — mirrors logic/audit/signing_protocol.py.
    """
    try:
        import ciris_adapters.ciris_verify as ciris_verify

        err = getattr(ciris_verify, "AttestationInProgressError", None)
        return err if isinstance(err, type) else None
    except ImportError:
        return None


class GraphAuditService(BaseGraphService, AuditServiceProtocol, RegistryAwareServiceProtocol):
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
            retention_days: How long to retain audit data
            cache_size: Size of in-memory cache
        """
        if not time_service:
            raise RuntimeError("CRITICAL: TimeService is required for GraphAuditService")

        # Initialize BaseGraphService with version 2.0.0
        super().__init__(memory_bus=memory_bus, time_service=time_service, version="2.0.0")

        self._service_registry: Optional[ServiceRegistryProtocol] = None

        # Export configuration
        self.export_path = Path(export_path) if export_path else None
        self.export_format = export_format

        # Hash chain configuration
        self.enable_hash_chain = enable_hash_chain
        # For PostgreSQL, keep connection string as-is; for SQLite, ensure Path object
        self.db_path: str | Path
        if db_path.startswith(("postgresql://", "postgres://")):
            self.db_path = db_path
        else:
            self.db_path = Path(db_path)

        # Retention configuration (cleanup implemented in cleanup_old_entries)
        self.retention_days = retention_days

        # Cache for recent entries
        self._recent_entries: List[AuditRequest] = []
        self._max_cached_entries = cache_size

        # Hash chain components — A3 cutover: writes go through persist's
        # cirislens_audit_log substrate (`_write_to_persist_chain`); reads
        # go through `verifier` which delegates to persist's
        # `audit_verify_chain`. The legacy AuditHashChain /
        # AuditSignatureManager / raw sqlite3 connection are gone.
        self.verifier: Optional[AuditVerifier] = None

        # Export buffer
        self._export_buffer: List[AuditRequest] = []
        self._export_task: Optional[asyncio.Task[None]] = None

        # Memory tracking
        self._process = psutil.Process() if PSUTIL_AVAILABLE else None

        # Track uptime
        self._start_time: Optional[datetime] = None

        # Lock for hash chain operations
        self._hash_chain_lock = asyncio.Lock()

        # A3 cutover: persist-routed chain state. Lazy-loaded on first
        # write via _refresh_persist_chain_state. _next_seq=None signals
        # "not yet primed from persist"; sequence_number values written
        # are always >= 1 (1 == fresh genesis, 2+ == post-A0b-bridge).
        self._next_seq: Optional[int] = None
        self._last_entry_hash_b64: Optional[str] = None

    async def attach_registry(self, registry: "ServiceRegistryProtocol") -> None:
        """
        Attach service registry for bus and service discovery.

        Implements RegistryAwareServiceProtocol to enable proper initialization
        of memory bus dependency.

        Args:
            registry: Service registry providing access to buses and services
        """
        self._service_registry = registry

        if not self._memory_bus and self._service_registry and self._time_service:
            try:
                from ciris_engine.logic.buses import MemoryBus

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
                # Re-raise after cleanup as per asyncio best practices
                raise

        # Log final shutdown event BEFORE closing database
        from ciris_engine.schemas.audit.core import EventPayload

        shutdown_event = EventPayload(
            action="shutdown",
            service_name="audit_service",
            user_id="system",
            result="success",
        )
        try:
            await self.log_event("audit_service_shutdown", shutdown_event)
        except Exception as e:
            logger.warning(f"Failed to log shutdown event: {e}")

        # Persist owns the connection pool — nothing to close here.

        logger.info("GraphAuditService stopped")

        # Don't call super() as BaseService has async stop
        self._started = False

    async def log_action(
        self, action_type: HandlerActionType, context: AuditActionContext, outcome: Optional[str] = None
    ) -> AuditEntryResult:
        """Log an action and return audit entry with hash chain data (REQUIRED)."""
        # Create audit entry
        import json

        from ciris_engine.schemas.audit.hash_chain import AuditEntryResult

        logger.info(
            f"DEBUG: log_action called with action_type={action_type.value}, context.parameters={context.parameters}"
        )

        # Serialize parameters dict to JSON string for AuditRequest (Dict[str, str] requirement)
        parameters_json = json.dumps(context.parameters) if context.parameters else "{}"

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
                "parameters": parameters_json,  # JSON-serialized parameters (e.g., {"tool_name": "reddit_submit_post"})
            },
            outcome=outcome,
        )

        logger.debug(f"Created AuditRequest with details.parameters={entry.details.get('parameters')}")

        # Add to hash chain FIRST (REQUIRED in production)
        hash_chain_data = await self._add_to_hash_chain(entry)

        if not hash_chain_data:
            raise RuntimeError(
                f"Hash chain data not generated for action {action_type.value}. "
                f"enable_hash_chain={self.enable_hash_chain}. "
                f"This is a critical audit trail failure."
            )

        # Store in graph WITH hash chain data (signature + entry_hash)
        await self._store_entry_in_graph(entry, action_type, hash_chain_data)

        # Cache for quick access
        self._cache_entry(entry)

        # Queue for export if configured
        if self.export_path:
            self._export_buffer.append(entry)

        # Return audit entry result with REQUIRED fields
        return AuditEntryResult(
            entry_id=entry.entry_id,
            sequence_number=hash_chain_data["sequence_number"],
            entry_hash=hash_chain_data["entry_hash"],
            previous_hash=hash_chain_data.get("previous_hash"),
            signature=hash_chain_data["signature"],
            signing_key_id=hash_chain_data.get("signing_key_id"),
        )

    async def log_event(self, event_type: str, event_data: "EventPayload", **kwargs: object) -> AuditEntryResult:
        """Log a general event.

        Args:
            event_type: Type of event being logged
            event_data: Event data as EventPayload object

        Returns:
            AuditEntryResult with entry_id and hash chain data (if enabled)
        """

        # Convert EventPayload to AuditEventData
        audit_data = AuditEventData(
            entity_id=str(getattr(event_data, "user_id", "unknown")),
            actor=str(getattr(event_data, "service_name", "system")),
            outcome=str(getattr(event_data, "result", "success")),
            severity="info",
            action=str(getattr(event_data, "action", event_type)),
            resource=str(getattr(event_data, "service_name", event_type)),
            reason=str(getattr(event_data, "error", "event_logged") or "event_logged"),
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

            # Add to hash chain FIRST to get signature before storing in graph
            logger.debug(f"enable_hash_chain={self.enable_hash_chain}")
            hash_chain_data = None
            if self.enable_hash_chain:
                logger.debug("Adding entry to hash chain")
                hash_chain_data = await self._add_to_hash_chain(entry)
            else:
                logger.debug("Hash chain disabled, not writing to audit_log table")

            # Create graph node WITH signature from hash chain
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
                signature=hash_chain_data.get("signature") if hash_chain_data else None,
                hash_chain=hash_chain_data.get("entry_hash") if hash_chain_data else None,
                scope=GraphScope.LOCAL,
                attributes={},
            )

            # Store in graph with signature already set
            if self._memory_bus:
                await self._memory_bus.memorize(
                    node=node.to_graph_node(),
                    handler_name="audit_service",
                    metadata={"audit_entry": entry.model_dump(), "event": True, "immutable": True},
                )

            # Cache and export
            self._cache_entry(entry)
            if self.export_path:
                logger.debug(f"Adding to export buffer, path={self.export_path}")
                self._export_buffer.append(entry)
            else:
                logger.debug("No export path configured")

            # Create trace correlation for this event
            from ciris_engine.schemas.runtime.enums import HandlerActionType

            # Extract action type from event data - try to map to HandlerActionType
            # For non-handler events like WA operations, system events, etc., default to OBSERVE
            action_name = event_data.action if hasattr(event_data, "action") else event_type
            try:
                action_type = HandlerActionType(action_name)
            except ValueError:
                # Not a handler action - use OBSERVE as default for system/auth events
                action_type = HandlerActionType.OBSERVE

            await self._create_trace_correlation(entry, action_type)

            # Return full audit entry result with hash chain data
            return AuditEntryResult(
                entry_id=entry.entry_id,
                sequence_number=hash_chain_data.get("sequence_number") if hash_chain_data else None,
                entry_hash=hash_chain_data.get("entry_hash") if hash_chain_data else None,
                previous_hash=hash_chain_data.get("previous_hash") if hash_chain_data else None,
                signature=hash_chain_data.get("signature") if hash_chain_data else None,
                signing_key_id=hash_chain_data.get("signing_key_id") if hash_chain_data else None,
            )

        except Exception as e:
            logger.error(f"Failed to log event {event_type}: {e}")
            # Fail fast - audit failures are critical
            raise RuntimeError(f"Failed to create audit entry for event {event_type}: {e}") from e

    async def log_conscience_event(
        self, thought_id: str, decision: str, reasoning: str, metadata: Optional["EventPayload"] = None
    ) -> None:
        """Log conscience check events."""
        # Create EventPayload for log_event
        from ciris_engine.schemas.audit.core import EventPayload

        # Use metadata if provided, otherwise create basic payload
        if metadata:
            event_payload = metadata
        else:
            event_payload = EventPayload(
                action="conscience_check",
                service_name="conscience_system",
                user_id=thought_id,
                result="allowed" if decision == "ALLOW" else "denied",
                error=reasoning if decision != "ALLOW" else None,
            )

        await self.log_event("conscience_check", event_payload)

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
            # 2.9.0: the SQLite-format export was removed from the core
            # audit service because it required `import sqlite3` outside
            # `ciris_adapters/`. Re-add via a dedicated archive adapter if
            # the use case returns. Users who want SQLite-format export
            # can pipe the JSONL output through a one-liner converter.
            raise ValueError(
                "SQLite-format export was removed in 2.9.0. "
                "Use format='jsonl' or 'csv' instead."
            )
        else:
            raise ValueError(f"Unsupported export format: {format}")

        return str(filename)

    async def cleanup_old_entries(self, retention_days: Optional[int] = None) -> int:
        """
        Clean up audit entries older than retention threshold.

        This method deletes audit entries older than the specified retention period
        while preserving hash chain integrity by re-anchoring the chain at the oldest
        remaining entry.

        Args:
            retention_days: Days to retain (defaults to self.retention_days, typically 90)

        Returns:
            Number of entries deleted

        Note:
            After truncation, the oldest remaining entry's previous_hash is updated to
            "REANCHOR_{timestamp}" to mark it as the new chain anchor. This maintains
            audit integrity while allowing old data to be purged.
        """
        days = retention_days or self.retention_days
        if days <= 0:
            logger.warning("Invalid retention_days, skipping cleanup")
            return 0

        cutoff_time = (self._time_service.now() if self._time_service else datetime.now()) - __import__(
            "datetime"
        ).timedelta(days=days)
        cutoff_iso = cutoff_time.isoformat()

        deleted_count = 0

        # Step 1: Prune the persist-owned audit chain via maintenance_prune_audit_chain.
        if self.enable_hash_chain:
            try:
                deleted_count = await self._prune_persist_audit_chain(cutoff_iso)
            except Exception as e:
                logger.error(f"Failed to prune persist audit chain: {e}", exc_info=True)

        # Step 2: Delete old audit graph nodes via memory bus
        if self._memory_bus:
            try:
                graph_deleted = await self._cleanup_audit_graph_nodes(cutoff_time)
                logger.info(f"Audit cleanup: deleted {graph_deleted} graph nodes older than {days} days")
            except Exception as e:
                logger.error(f"Failed to cleanup audit graph nodes: {e}", exc_info=True)

        # Step 3: Clear expired entries from cache
        self._recent_entries = [e for e in self._recent_entries if e.timestamp >= cutoff_time]

        if deleted_count > 0:
            logger.info(f"Audit retention cleanup complete: deleted {deleted_count} entries older than {days} days")

        return deleted_count

    async def _prune_persist_audit_chain(self, cutoff_iso: str) -> int:
        """Prune persist's cirislens_audit_log via maintenance substrate.

        Persist's `maintenance_prune_audit_chain(tenant_id, cutoff_iso)`
        handles re-anchoring + deletion atomically. Returns the count of
        deleted entries.
        """

        def _do_prune() -> int:
            from ciris_engine.logic.persistence.models.graph import get_persist_engine

            engine = get_persist_engine()
            if engine is None:
                return 0
            tenant_id = _audit_tenant_id()
            try:
                raw = engine.maintenance_prune_audit_chain(tenant_id, cutoff_iso)
            except Exception as e:
                logger.warning(f"persist maintenance_prune_audit_chain failed: {e}")
                return 0
            # Persist returns either an int or a small JSON envelope; tolerate both.
            if isinstance(raw, int):
                return raw
            if isinstance(raw, (bytes, str)):
                try:
                    parsed = json.loads(raw)
                    if isinstance(parsed, int):
                        return parsed
                    if isinstance(parsed, dict):
                        for key in ("deleted", "removed", "pruned"):
                            v = parsed.get(key)
                            if isinstance(v, int):
                                return v
                except Exception:
                    return 0
            return 0

        return await asyncio.to_thread(_do_prune)

    async def _cleanup_audit_graph_nodes(self, cutoff_time: datetime) -> int:
        """Delete audit nodes older than cutoff from graph storage."""
        if not self._memory_bus:
            return 0

        deleted = 0

        # Query for old audit nodes
        from ciris_engine.schemas.services.graph_core import NodeType

        search_query = f"type:{NodeType.AUDIT_ENTRY.value} scope:{GraphScope.LOCAL.value}"
        try:
            nodes = await self._memory_bus.search(search_query, filters=None, handler_name="audit_service")

            for node in nodes:
                # Extract timestamp from node (updated_at at node level, or created_at in attributes)
                node_timestamp = node.updated_at
                if node_timestamp is None and hasattr(node.attributes, "created_at"):
                    node_timestamp = node.attributes.created_at
                if node_timestamp and node_timestamp < cutoff_time:
                    # Delete via forget - pass the full node
                    result = await self._memory_bus.forget(
                        node=node,
                        handler_name="audit_service",
                        metadata={"reason": f"retention_cleanup_{self.retention_days}d"},
                    )
                    if result.status == MemoryOpStatus.OK:
                        deleted += 1

        except Exception as e:
            logger.error(f"Error querying/deleting audit graph nodes: {e}")

        return deleted

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

    async def _store_entry_in_graph(
        self, entry: AuditRequest, action_type: HandlerActionType, hash_chain_data: Optional[JSONDict] = None
    ) -> None:
        """Store an audit entry in the graph and create a trace correlation.

        Args:
            entry: The audit request to store
            action_type: The handler action type
            hash_chain_data: Optional hash chain data with signature/entry_hash to include in node
        """
        if not self._memory_bus:
            logger.error("Memory bus not available for audit storage")
            return

        # Create specialized audit node WITH signature from hash chain
        # Build additional_data with core fields plus any extra parameters from context
        import json

        additional_data = {
            "thought_id": entry.details.get("thought_id", ""),
            "task_id": entry.details.get("task_id", ""),
            "outcome": entry.outcome or "success",
            "severity": self._get_severity(action_type),
        }

        # Include any additional parameters from the audit context (e.g., tool_name, follow_up_thought_id)
        logger.debug(f"entry.details keys: {entry.details.keys()}")
        if "parameters" in entry.details and entry.details["parameters"]:
            logger.debug(f"Found parameters in entry.details: {entry.details['parameters']}")
            try:
                # Deserialize JSON string back to dict
                params_dict = json.loads(entry.details["parameters"])
                additional_data.update(params_dict)
                logger.debug(f"Updated additional_data: {additional_data}")
            except json.JSONDecodeError as e:
                logger.warning(f"Failed to parse parameters JSON: {e}")
        else:
            logger.debug("No 'parameters' key in entry.details or empty")

        node = AuditEntryNode(
            id=f"audit_{action_type.value}_{entry.entry_id}",
            action=action_type.value,
            actor=entry.actor,
            timestamp=entry.timestamp,
            context=AuditEntryContext(
                service_name=entry.details.get("handler_name", ""),
                correlation_id=entry.entry_id,
                additional_data=additional_data,
            ),
            signature=hash_chain_data.get("signature") if hash_chain_data else None,
            hash_chain=hash_chain_data.get("entry_hash") if hash_chain_data else None,
            scope=GraphScope.LOCAL,
            attributes={"action_type": action_type.value, "event_id": entry.entry_id},
        )

        # Store via memory bus with signature already set
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
        logger.debug(f"Creating trace correlation for audit event {entry.entry_id}")
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
                if self._service_registry:
                    from ciris_engine.schemas.runtime.enums import ServiceType

                    services = self._service_registry.get_services_by_type(ServiceType.TELEMETRY)
                    telemetry_service = services[0] if services else None

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
                logger.debug(f"Successfully stored trace correlation for audit event {entry.entry_id}")
            else:
                logger.warning(f"Telemetry service does not have _store_correlation method")

        except Exception as e:
            logger.error(f"Failed to create trace correlation: {e}", exc_info=True)
            # Don't fail the audit operation if trace creation fails

    async def _initialize_hash_chain(self) -> None:
        """Wire up the persist-routed audit chain.

        A3 cutover: persist owns the cirislens_audit_log table + signing
        keys + chain state. The agent just needs a verifier handle for the
        verify_complete_chain code path. There's no Python-side table init,
        no signing-key bootstrap, no per-process SQLite connection.
        """
        if not self._time_service:
            raise RuntimeError("TimeService is None — cannot initialize audit verifier")
        self.verifier = AuditVerifier(str(self.db_path), self._time_service)
        # Verifier's initialize is a no-op now (persist owns the table) but
        # we keep the call for symmetry with the legacy lifecycle.
        await asyncio.to_thread(self.verifier.initialize)
        logger.info("Audit hash chain wired through persist substrate")

    async def _add_to_hash_chain(self, entry: AuditRequest) -> Optional[JSONDict]:
        """Add an entry to the hash chain via persist.

        A3 cutover (CIRISAgent#763 Lane A): the agent no longer writes to
        the legacy `ciris_audit.db` audit_log table. All writes route
        through persist's `cirislens_audit_log` substrate via the
        canonicalize-hash → sign → record_entry pattern that A0b
        established for the bridge entry.

        Returns:
            Dict with hash chain data (sequence_number, entry_hash,
            previous_hash, signature, signing_key_id) or None if hash
            chain is disabled.
        """
        if not self.enable_hash_chain:
            return None

        # The persist-chain write mutates no chain state (_next_seq /
        # _last_entry_hash_b64) until its final audit_record_entry, and
        # AttestationInProgressError is raised before that point — so the
        # whole write is safe to retry while CIRISVerify finishes attesting.
        attestation_in_progress = _attestation_in_progress_error()

        async with self._hash_chain_lock:
            for attempt in range(_AUDIT_SIGN_MAX_RETRIES):
                try:
                    return await asyncio.to_thread(self._write_to_persist_chain, entry)
                except Exception as e:
                    last_attempt = attempt >= _AUDIT_SIGN_MAX_RETRIES - 1
                    msg = str(e)
                    # The signing wrapper may re-raise CIRISVerify's
                    # AttestationInProgressError as a generic exception that
                    # only carries the message — match the type OR the message.
                    is_attestation = (
                        attestation_in_progress is not None
                        and isinstance(e, attestation_in_progress)
                    ) or "attestation in progress" in msg.lower()
                    # persist raises "chain integrity: sequence gap ..." when
                    # the cached _next_seq has drifted from the chain tail.
                    # Self-heal: drop the cache so the retry re-reads the head
                    # — otherwise one drift cascades into unbounded failures.
                    is_chain_desync = "chain integrity" in msg or "sequence gap" in msg

                    if last_attempt or not (is_attestation or is_chain_desync):
                        logger.exception("Failed to add to persist audit chain")
                        return None

                    if is_chain_desync:
                        logger.warning(
                            "audit chain desync (%s) — re-syncing chain state from persist and retrying",
                            msg,
                        )
                        self._next_seq = None
                        self._last_entry_hash_b64 = None
                    else:
                        logger.debug(
                            "persist audit chain write deferred (attestation in progress); "
                            "retry %d/%d in %.1fs",
                            attempt + 1,
                            _AUDIT_SIGN_MAX_RETRIES,
                            _AUDIT_SIGN_RETRY_DELAY_S,
                        )
                        await asyncio.sleep(_AUDIT_SIGN_RETRY_DELAY_S)
            return None

    def _write_to_persist_chain(self, entry: AuditRequest) -> JSONDict:
        """Synchronous persist-routed write — assemble, hash, sign, record.

        Runs in a worker thread (called via asyncio.to_thread from the
        async wrapper). Holds the chain-state cache under the service's
        async lock, so we never race on `_next_seq` / `_last_entry_hash_b64`.
        """
        from ciris_engine.logic.persistence.models.graph import get_persist_engine

        engine = get_persist_engine()
        if engine is None:
            raise RuntimeError(
                "persist engine not wired — A3 audit cutover requires the "
                "engine to be initialized by ServiceInitializer first"
            )

        # Lazy-load chain state (next sequence + last entry hash) on first call.
        if self._next_seq is None or self._last_entry_hash_b64 is None:
            self._refresh_persist_chain_state(engine)

        _pubkey_bytes, actor_id_b64, signing_key_id = _audit_signer_material()
        tenant_id = _audit_tenant_id()

        recorded_at = entry.timestamp.isoformat().replace("+00:00", "Z")
        if not recorded_at.endswith("Z"):
            recorded_at = recorded_at + "Z" if "T" in recorded_at and "+" not in recorded_at else recorded_at

        payload_obj: JSONDict = {
            "event_type": entry.event_type,
            "actor": entry.actor,
            "details": entry.details,
            "outcome": entry.outcome,
        }

        # action_type must be one of the 21 AuditEventType values — persist's
        # audit_log CHECK constraint (V018/V020) enforces this on Postgres.
        persist_entry: JSONDict = {
            "entry_id": entry.entry_id,
            "sequence_number": self._next_seq,
            "tenant_id": tenant_id,
            "actor_id": actor_id_b64,
            "action_type": _resolve_action_type(entry.event_type),
            "subject_kind": "agent_event",
            "subject_id": entry.entity_id,
            "payload": json.dumps(payload_obj, sort_keys=True, separators=(",", ":")),
            "prev_hash": self._last_entry_hash_b64,
            "recorded_at": recorded_at,
            "signing_key_id": signing_key_id,
            "entry_hash": "",
            "signature": "",
        }

        # Persist owns canonicalization for hash + signing.
        hash_canon = engine.audit_canonicalize_for_hash(json.dumps(persist_entry))
        hash_bytes = hash_canon if isinstance(hash_canon, bytes) else hash_canon.encode()
        entry_hash_b64 = base64.b64encode(hashlib.sha256(hash_bytes).digest()).decode()
        persist_entry["entry_hash"] = entry_hash_b64

        sign_canon = engine.audit_canonicalize_for_signing(json.dumps(persist_entry))
        sign_bytes = sign_canon if isinstance(sign_canon, bytes) else sign_canon.encode()
        signature_b64 = base64.b64encode(_audit_sign(sign_bytes)).decode()
        persist_entry["signature"] = signature_b64

        engine.audit_record_entry(json.dumps(persist_entry))

        result: JSONDict = {
            "sequence_number": self._next_seq,
            "entry_hash": entry_hash_b64,
            "previous_hash": self._last_entry_hash_b64,
            "signature": signature_b64,
            "signing_key_id": signing_key_id,
        }

        # Advance chain-state cache for the next write.
        self._last_entry_hash_b64 = entry_hash_b64
        self._next_seq = (self._next_seq or 0) + 1
        return result

    def _refresh_persist_chain_state(self, engine: Any) -> None:
        """Query persist for the last entry; set _next_seq and _last_entry_hash_b64.

        Called once per service lifetime on the first write. The bridge
        entry written by A0b is sequence_number=1; the first agent-emitted
        entry is therefore sequence_number=2 with prev_hash = bridge
        entry's entry_hash. On a fresh install (no bridge, no prior
        writes), start at sequence_number=1 with the all-zeros prev_hash.

        persist's `audit_list_entries` paginates with an AuditCursor
        (`version`, `last_ts`, `last_id`); setting last_ts to a far-future
        timestamp + empty last_id returns the latest entry first (DESC by
        recorded_at). Response is a JSON string `{"items": [...]}`.
        """
        filter_json = json.dumps({"tenant_id": _audit_tenant_id()})
        cursor_json = json.dumps(
            {"version": "v1", "last_ts": "9999-12-31T23:59:59Z", "last_id": ""}
        )
        # Fetch a window, not just 1: audit_list_entries paginates DESC by
        # recorded_at — NOT by sequence_number. On sub-millisecond writes
        # (equal recorded_at) or any clock skew, items[0] is NOT the true
        # chain tail, which would set _next_seq one short and every write
        # would then fail "sequence gap" forever.
        raw = engine.audit_list_entries(filter_json, cursor_json, 256)

        items: List[Any] = []
        if isinstance(raw, str):
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError:
                parsed = None
            if isinstance(parsed, dict):
                items = list(parsed.get("items") or [])

        # The chain's authoritative order is sequence_number — select the
        # max-sequence entry as the true tail regardless of recorded_at order.
        head = max(
            (it for it in items if isinstance(it, dict)),
            key=lambda it: int(it.get("sequence_number", 0)),
            default=None,
        )

        if head is None:
            self._next_seq = 1
            self._last_entry_hash_b64 = base64.b64encode(b"\x00" * 32).decode()
            logger.info("audit chain state: fresh genesis (no prior entries in persist)")
            return

        last_seq = int(head.get("sequence_number", 0))
        last_hash = str(head.get("entry_hash", ""))
        self._next_seq = last_seq + 1
        self._last_entry_hash_b64 = last_hash
        logger.info(
            "audit chain state: resumed at seq=%d after last_entry=%s...",
            self._next_seq, last_hash[:16],
        )

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
            # 2.9.0: sqlite export removed (audit service must not depend on
            # sqlite3 outside ciris_adapters/). See export_audit_data for
            # the user-facing error.

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

    def _extract_thought_id_from_audit_node(self, audit_node: AuditEntryNode) -> str:
        """Extract thought_id from audit node context."""
        if not audit_node.context.additional_data:
            return ""
        value = audit_node.context.additional_data.get("thought_id", "")
        return str(value) if value else ""

    def _extract_task_id_from_audit_node(self, audit_node: AuditEntryNode) -> str:
        """Extract task_id from audit node context."""
        if not audit_node.context.additional_data:
            return ""
        value = audit_node.context.additional_data.get("task_id", "")
        return str(value) if value else ""

    def _extract_outcome_from_audit_node(self, audit_node: AuditEntryNode) -> Optional[str]:
        """Extract outcome from audit node context."""
        if not audit_node.context.additional_data:
            return None
        value = audit_node.context.additional_data.get("outcome")
        return str(value) if value is not None else None

    def _convert_audit_entry_node(self, audit_node: AuditEntryNode) -> AuditRequest:
        """Convert AuditEntryNode to AuditRequest."""
        return AuditRequest(
            entry_id=audit_node.id.replace("audit_", ""),
            timestamp=audit_node.timestamp,
            entity_id=audit_node.context.correlation_id or "",
            event_type=audit_node.action,
            actor=audit_node.actor,
            details={
                "action_type": audit_node.action,
                "thought_id": self._extract_thought_id_from_audit_node(audit_node),
                "task_id": self._extract_task_id_from_audit_node(audit_node),
                "handler_name": audit_node.context.service_name or "",
                "context": audit_node.context.model_dump(),
            },
            outcome=self._extract_outcome_from_audit_node(audit_node),
        )

    def _get_timestamp_from_data(self, data: GraphNode) -> datetime:
        """Get timestamp from data node with fallback."""
        timestamp = data.attributes.created_at if hasattr(data.attributes, "created_at") else data.updated_at
        if not timestamp:
            timestamp = self._time_service.now() if self._time_service else datetime.now()
        return timestamp

    def _extract_action_type_from_attrs(self, attrs: JSONDict) -> Optional[str]:
        """Extract action_type from attributes with fallback."""
        action_type_val = get_str(attrs, "action_type", "")
        if action_type_val:
            return action_type_val
        return None

    def _create_audit_request_from_attrs(self, attrs: JSONDict, timestamp: datetime, action_type: str) -> AuditRequest:
        """Create AuditRequest from manual attribute parsing."""
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

    def _tsdb_to_audit_entry(self, data: GraphNode) -> Optional[AuditRequest]:
        """Convert TSDB node to AuditEntry."""
        # Check if this is an AuditEntryNode by looking for the marker
        attrs = data.attributes if isinstance(data.attributes, dict) else {}

        # If it's an AuditEntryNode stored with to_graph_node(), convert back
        if attrs.get("node_class") == "AuditEntry":
            try:
                audit_node = AuditEntryNode.from_graph_node(data)
                return self._convert_audit_entry_node(audit_node)
            except Exception as e:
                logger.warning(f"Failed to convert AuditEntryNode: {e}, falling back to manual parsing")

        # Fallback: manual parsing for backwards compatibility
        attrs = data.attributes.model_dump() if hasattr(data.attributes, "model_dump") else {}

        action_type = self._extract_action_type_from_attrs(attrs)
        if not action_type:
            return None

        timestamp = self._get_timestamp_from_data(data)
        return self._create_audit_request_from_attrs(attrs, timestamp, action_type)

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
    ) -> List["AuditLogEntry"]:
        """Query audit events."""
        # Call query_audit_trail directly with parameters
        from ciris_engine.schemas.services.graph.audit import AuditQuery

        query = AuditQuery(
            start_time=start_time, end_time=end_time, action_types=[event_type] if event_type else None, limit=limit
        )
        entries = await self.query_audit_trail(query)

        # Convert to AuditLogEntry format
        from ciris_engine.schemas.audit.core import AuditLogEntry, EventPayload

        result = []
        for entry in entries:
            # Create EventPayload from entry context
            event_payload = EventPayload(
                action=entry.action, user_id=entry.actor, service_name=getattr(entry, "resource", "audit_service")
            )

            # Create AuditLogEntry
            entity_id = entry.context.correlation_id or ""
            log_entry = AuditLogEntry(
                event_id=entry.id,
                event_timestamp=entry.timestamp,
                event_type=entry.action,
                originator_id=entry.actor,
                target_id=entity_id,
                event_summary=f"{entry.action} by {entry.actor}",
                event_payload=event_payload,
                thought_id=entity_id if entity_id.startswith("thought") else None,
                entry_hash=entry.signature,
            )
            result.append(log_entry)
        return result

    def _convert_entry_to_audit_log_dict(self, entry: AuditRequest) -> JSONDict:
        """Convert audit entry to audit log dictionary format."""
        return {
            "event_id": entry.entry_id,
            "event_type": entry.event_type,
            "timestamp": entry.timestamp.isoformat() if entry.timestamp else None,
            "user_id": entry.actor,
            "data": entry.details,
            "metadata": {"outcome": entry.outcome} if entry.outcome else {},
        }

    async def _search_event_in_memory_bus(self, event_id: str) -> Optional[JSONDict]:
        """Search for event in memory bus."""
        if not self._memory_bus:
            return None

        query = MemoryQuery(
            node_id=event_id, scope=GraphScope.LOCAL, type=NodeType.AUDIT_ENTRY, include_edges=False, depth=1
        )

        nodes = await self._memory_bus.recall(query)
        if not nodes or len(nodes) == 0:
            return None

        entry = self._tsdb_to_audit_entry(nodes[0])
        if not entry:
            return None

        return self._convert_entry_to_audit_log_dict(entry)

    def _search_event_in_recent_cache(self, event_id: str) -> Optional[JSONDict]:
        """Search for event in recent entries cache."""
        for entry in self._recent_entries:
            if entry.entry_id == event_id:
                return self._convert_entry_to_audit_log_dict(entry)
        return None

    async def get_event_by_id(self, event_id: str) -> Optional["AuditLogEntry"]:
        """Get specific audit event by ID."""
        from ciris_engine.schemas.audit.core import AuditLogEntry, EventPayload

        # Try memory bus first
        result_dict = await self._search_event_in_memory_bus(event_id)
        if not result_dict:
            # Fall back to recent cache
            result_dict = self._search_event_in_recent_cache(event_id)

        if not result_dict:
            return None

        # Convert dict to AuditLogEntry
        return AuditLogEntry(
            event_id=result_dict.get("event_id", event_id),
            event_timestamp=result_dict.get("timestamp"),
            event_type=result_dict.get("event_type", ""),
            originator_id=result_dict.get("user_id", ""),
            target_id=result_dict.get("user_id", ""),
            event_summary=f"{result_dict.get('event_type', '')} event",
            event_payload=EventPayload(
                action=result_dict.get("event_type", ""),
                service_name="audit_service",
                user_id=result_dict.get("user_id", ""),
            ),
        )

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
