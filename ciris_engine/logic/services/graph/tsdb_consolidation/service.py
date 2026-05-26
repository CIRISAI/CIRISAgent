"""
TSDB Consolidation Service - Main service class.

This service runs every 6 hours to consolidate telemetry and memory data
into permanent summary records with proper edge connections.
"""

import asyncio
import logging
import random
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple, Union
from uuid import uuid4

if TYPE_CHECKING:
    from ciris_engine.logic.registries.base import ServiceRegistry

from ciris_engine.constants import UTC_TIMEZONE_SUFFIX
from ciris_engine.logic.buses.memory_bus import MemoryBus
from ciris_engine.logic.services.base_graph_service import BaseGraphService
from ciris_engine.protocols.infrastructure.base import RegistryAwareServiceProtocol, ServiceRegistryProtocol
from ciris_engine.protocols.services.lifecycle.time import TimeServiceProtocol
from ciris_engine.schemas.consent.core import ConsentStream
from ciris_engine.schemas.runtime.enums import ServiceType
from ciris_engine.schemas.services.core import ServiceCapabilities, ServiceStatus
from ciris_engine.schemas.services.graph.consolidation import (
    MetricCorrelationData,
    ServiceInteractionData,
    TaskCorrelationData,
    TraceSpanData,
    TSDBPeriodSummary,
)
from ciris_engine.schemas.services.graph.query_results import ServiceCorrelationQueryResult, TSDBNodeQueryResult
from ciris_engine.schemas.services.graph.tsdb_models import SummaryAttributes
from ciris_engine.schemas.services.graph_core import GraphNode, NodeType
from ciris_engine.schemas.services.operations import MemoryOpStatus

from .consolidators import (
    AuditConsolidator,
    ConversationConsolidator,
    MemoryConsolidator,
    MetricsConsolidator,
    TaskConsolidator,
    TraceConsolidator,
)
from .edge_manager import EdgeManager
from .period_manager import PeriodManager
from .query_manager import QueryManager

logger = logging.getLogger(__name__)


class TSDBConsolidationService(BaseGraphService, RegistryAwareServiceProtocol):
    """
    Refactored TSDB Consolidation Service.

    Key improvements:
    1. Consolidates BOTH graph nodes AND service correlations
    2. Creates proper edges in graph_edges table
    3. Links summaries to ALL nodes in the period
    4. Includes task summaries with outcomes
    """

    def __init__(
        self,
        memory_bus: Optional[MemoryBus] = None,
        time_service: Optional[TimeServiceProtocol] = None,
        consolidation_interval_hours: int = 6,
        raw_retention_hours: int = 24,
        db_path: Optional[str] = None,
    ) -> None:
        """
        Initialize the consolidation service.

        Args:
            memory_bus: Bus for memory operations
            time_service: Time service for consistent timestamps
            consolidation_interval_hours: How often to run (default: 6)
            raw_retention_hours: How long to keep raw data (default: 24)
            db_path: Database path to use (if not provided, uses default)
        """
        super().__init__(memory_bus=memory_bus, time_service=time_service)
        self.service_name = "TSDBConsolidationService"
        self.db_path = db_path

        # Initialize components
        self._period_manager = PeriodManager(consolidation_interval_hours)
        self._query_manager = QueryManager(memory_bus, db_path=db_path)
        self._edge_manager = EdgeManager(db_path=db_path)

        # Initialize all consolidators
        self._metrics_consolidator = MetricsConsolidator(memory_bus)
        self._memory_consolidator = MemoryConsolidator(memory_bus)
        self._task_consolidator = TaskConsolidator(memory_bus)
        self._conversation_consolidator = ConversationConsolidator(memory_bus, time_service)
        self._trace_consolidator = TraceConsolidator(memory_bus)
        self._audit_consolidator = AuditConsolidator(memory_bus, time_service)

        self._consolidation_interval = timedelta(hours=consolidation_interval_hours)
        self._raw_retention = timedelta(hours=raw_retention_hours)

        # Load consolidation intervals from config
        self._load_consolidation_config()

        # Retention periods for different levels
        self._basic_retention = timedelta(days=7)  # Keep basic summaries for 7 days
        self._extensive_retention = timedelta(days=30)  # Keep daily summaries for 30 days

        # Task management
        self._consolidation_task: Optional[asyncio.Task[None]] = None
        self._running = False

        # Track last successful consolidation
        self._last_consolidation: Optional[datetime] = None
        self._last_extensive_consolidation: Optional[datetime] = None
        self._last_profound_consolidation: Optional[datetime] = None
        self._start_time: Optional[datetime] = None

        # Telemetry tracking variables
        self._basic_consolidations = 0
        self._extensive_consolidations = 0
        self._profound_consolidations = 0
        self._records_consolidated = 0
        self._records_deleted = 0
        self._compression_ratio = 1.0
        self._last_consolidation_duration = 0.0
        self._consolidation_errors = 0
        self._start_time = None  # Will be set when service starts

    def _load_consolidation_config(self) -> None:
        """Load consolidation configuration from essential config."""
        # Fixed intervals for calendar alignment
        self._basic_interval = timedelta(hours=6)  # 00:00, 06:00, 12:00, 18:00 UTC
        self._extensive_interval = timedelta(days=7)  # Weekly on Mondays
        self._profound_interval = timedelta(days=30)  # Monthly on 1st

        # Load configurable values
        # Set default configurable values
        self._profound_target_mb_per_day = 20.0  # Default 20MB/day
        logger.info(f"TSDB profound consolidation target: {self._profound_target_mb_per_day} MB/day")

    async def attach_registry(self, registry: "ServiceRegistryProtocol") -> None:
        """
        Attach service registry for service discovery.

        Implements RegistryAwareServiceProtocol to enable proper initialization
        of time service dependency.

        Args:
            registry: Service registry providing access to services
        """
        self._service_registry = registry

        # Only get time service from registry if not provided
        if not self._time_service and registry:
            from ciris_engine.schemas.runtime.enums import ServiceType

            time_services = registry.get_services_by_type(ServiceType.TIME)
            if time_services:
                self._time_service = time_services[0]

    def _now(self) -> datetime:
        """Get current time from time service."""
        return self._time_service.now() if self._time_service else datetime.now(timezone.utc)

    async def start(self) -> None:
        """Start the consolidation service."""
        if self._running:
            logger.warning("TSDBConsolidationService already running")
            return

        await super().start()
        self._running = True
        self._start_time = self._now()

        # Start single consolidation loop that handles basic → extensive → profound sequentially
        # The loop will consolidate missed windows first before entering the regular schedule
        self._consolidation_task = asyncio.create_task(self._consolidation_loop())
        logger.info(
            f"TSDBConsolidationService started - Basic: {self._basic_interval}, Extensive: {self._extensive_interval}, Profound: {self._profound_interval}"
        )

    async def stop(self) -> None:
        """Stop the consolidation service gracefully."""
        self._running = False

        # Cancel any ongoing consolidation task
        if self._consolidation_task and not self._consolidation_task.done():
            logger.info("Cancelling ongoing consolidation task...")
            self._consolidation_task.cancel()
            try:
                await self._consolidation_task
            except asyncio.CancelledError:
                logger.debug("Consolidation task cancelled successfully")
                # Only re-raise if we're being cancelled ourselves
                current = asyncio.current_task()
                if current and current.cancelled():
                    raise
                # Otherwise, this is a normal stop - don't propagate the cancellation
            except Exception as e:
                logger.error(f"Error cancelling consolidation task: {e}")

        # Note: Final consolidation should be run explicitly by runtime BEFORE
        # stopping services, not during stop() to avoid dependency issues

        await super().stop()
        logger.info("TSDBConsolidationService stopped")

    async def _consolidation_loop(self) -> None:
        """
        Main consolidation loop that runs every 6 hours.

        The occurrence that wins the lock becomes "the consolidator" and runs:
        1. Basic consolidation (always)
        2. Extensive consolidation (if it's Monday)
        3. Profound consolidation (if it's the 1st of the month)

        This ensures only ONE occurrence handles all consolidation types sequentially,
        preventing race conditions between consolidation levels.
        """
        # First, consolidate any missed windows in the background
        # This runs asynchronously and doesn't block the main init sequence
        try:
            await self._consolidate_missed_windows()
        except Exception as e:
            logger.error(f"Error consolidating missed windows: {e}", exc_info=True)
            # Continue anyway - don't let missed window errors block regular operation

        while self._running:
            try:
                # Calculate next run time
                next_run = self._period_manager.get_next_period_start(self._now())
                wait_seconds = (next_run - self._now()).total_seconds()

                if wait_seconds > 0:
                    logger.info(f"Next consolidation at {next_run} ({wait_seconds:.0f}s)")
                    await asyncio.sleep(wait_seconds)

                if self._running:
                    # Add random delay (30-600s) to prevent thundering herd
                    # when multiple instances start simultaneously
                    jitter_seconds = random.randint(30, 600)
                    logger.info(f"Adding random jitter delay of {jitter_seconds}s to prevent race conditions")
                    await asyncio.sleep(jitter_seconds)

                    if self._running:
                        # Run basic consolidation
                        # The occurrence that wins the lock becomes "the consolidator" for this run
                        await self._run_consolidation()

                        # If we're the consolidator, check if we should run extensive/profound
                        now = self._now()

                        # Check if it's Monday (0 = Monday) for extensive consolidation
                        if now.weekday() == 0:
                            logger.info("It's Monday - running extensive consolidation")
                            await self._run_extensive_consolidation()

                        # Check if it's the 1st of the month for profound consolidation
                        if now.day == 1:
                            logger.info("It's the 1st of the month - running profound consolidation")
                            await asyncio.to_thread(self._run_profound_consolidation)

            except asyncio.CancelledError:
                logger.debug("Consolidation loop cancelled")
                raise  # Re-raise to properly exit the task
            except Exception as e:
                logger.error(f"Consolidation loop error: {e}", exc_info=True)
                await asyncio.sleep(300)  # 5 minutes

    async def _run_consolidation(self) -> None:
        """Run a single consolidation cycle.

        Note: Uses asyncio.to_thread() for blocking DB operations to prevent
        blocking the event loop (which can cause Discord heartbeat failures).
        """
        consolidation_start = self._now()
        total_records_processed = 0
        total_summaries_created = 0
        cleanup_stats = {"nodes_deleted": 0, "edges_deleted": 0}

        try:
            logger.info("=" * 60)
            logger.info("Starting TSDB consolidation cycle")
            logger.info(f"Started at: {consolidation_start.isoformat()}")

            # Find periods that need consolidation
            now = self._now()
            cutoff_time = now - timedelta(hours=24)

            # Get oldest unconsolidated data (run in thread to avoid blocking)
            oldest_data = await asyncio.to_thread(self._find_oldest_unconsolidated_period)
            if not oldest_data:
                logger.info("No unconsolidated data found - nothing to consolidate")
                return

            logger.info(f"Oldest unconsolidated data from: {oldest_data.isoformat()}")
            logger.info(f"Will consolidate up to: {cutoff_time.isoformat()}")

            # Process periods
            current_start, _ = self._period_manager.get_period_boundaries(oldest_data)
            periods_consolidated = 0
            max_periods = 30  # Limit per run

            while current_start < cutoff_time and periods_consolidated < max_periods:
                current_end = current_start + self._consolidation_interval

                # Try to acquire lock for this period to prevent duplicate consolidation
                # Run in thread to avoid blocking event loop
                lock_acquired = await asyncio.to_thread(self._query_manager.acquire_period_lock, current_start)

                if not lock_acquired:
                    logger.info(f"Period {current_start.isoformat()} is locked by another instance, skipping")
                    current_start = current_end
                    continue

                try:
                    # Check if already consolidated (double-check after acquiring lock)
                    is_consolidated = await asyncio.to_thread(
                        self._query_manager.check_period_consolidated, current_start
                    )
                    if not is_consolidated:
                        period_start_time = self._now()
                        logger.info(f"Consolidating period: {current_start.isoformat()} to {current_end.isoformat()}")

                        # Count records in this period before consolidation (run in thread)
                        nodes_in_period = await asyncio.to_thread(
                            self._query_manager.query_all_nodes_in_period, current_start, current_end
                        )
                        period_records = len(nodes_in_period)
                        total_records_processed += period_records

                        summaries = await self._consolidate_period(current_start, current_end)
                        if summaries:
                            total_summaries_created += len(summaries)
                            period_duration = (self._now() - period_start_time).total_seconds()
                            logger.info(
                                f"  ✓ Created {len(summaries)} summaries from {period_records} records in {period_duration:.2f}s"
                            )
                            periods_consolidated += 1
                        else:
                            logger.info("  - No summaries created for period (no data)")
                    else:
                        logger.info(f"Period {current_start.isoformat()} already consolidated by another instance")

                finally:
                    # Always release the lock (run in thread)
                    await asyncio.to_thread(self._query_manager.release_period_lock, current_start)

                current_start = current_end

            if periods_consolidated > 0:
                logger.info(f"Consolidation complete: {periods_consolidated} periods processed")
                logger.info(f"  - Total records processed: {total_records_processed}")
                logger.info(f"  - Total summaries created: {total_summaries_created}")
                if total_records_processed > 0:
                    compression_ratio = total_records_processed / max(total_summaries_created, 1)
                    logger.info(f"  - Compression ratio: {compression_ratio:.1f}:1")

            # Cleanup old data (run in thread to avoid blocking event loop)
            cleanup_start = self._now()
            logger.info("Starting cleanup of old consolidated data...")

            # Run cleanup in thread to prevent Discord heartbeat blocking
            nodes_deleted = await asyncio.to_thread(self._cleanup_old_data)
            cleanup_stats["nodes_deleted"] = nodes_deleted

            # Cleanup orphaned edges (run in thread)
            edges_deleted = await asyncio.to_thread(self._edge_manager.cleanup_orphaned_edges)
            cleanup_stats["edges_deleted"] = edges_deleted

            cleanup_duration = (self._now() - cleanup_start).total_seconds()
            if nodes_deleted > 0 or edges_deleted > 0:
                logger.info(f"Cleanup complete in {cleanup_duration:.2f}s:")
                logger.info(f"  - Nodes deleted: {nodes_deleted}")
                logger.info(f"  - Edges deleted: {edges_deleted}")

            self._last_consolidation = now

            # Final summary
            total_duration = (self._now() - consolidation_start).total_seconds()
            logger.info(f"TSDB consolidation cycle completed in {total_duration:.2f}s")
            logger.info("=" * 60)

        except Exception as e:
            duration = (self._now() - consolidation_start).total_seconds()
            logger.error(f"Consolidation failed after {duration:.2f}s: {e}", exc_info=True)
            logger.error(f"Partial progress - Records: {total_records_processed}, Summaries: {total_summaries_created}")

    async def _consolidate_missed_windows(self) -> None:
        """
        Consolidate any missed windows since the last consolidation.
        Called at startup to catch up on any periods missed while shutdown.
        """
        try:
            logger.info("Checking for missed consolidation windows...")
            # Console output for mobile app startup indicator
            print("[CONSOLIDATOR] Checking for missed windows...", flush=True)

            # Find the last consolidated period
            last_consolidated = await self._query_manager.get_last_consolidated_period()

            now = self._now()
            cutoff_time = now - timedelta(hours=24)  # Don't go back more than 24 hours

            if last_consolidated:
                # Start from the period after the last consolidated one
                start_from = last_consolidated + self._consolidation_interval
                logger.info(f"Last consolidated period: {last_consolidated}, starting from: {start_from}")
            else:
                # No previous consolidation found, check for oldest data
                oldest_data = self._find_oldest_unconsolidated_period()
                if not oldest_data:
                    logger.info("No unconsolidated data found")
                    return

                # Start from the period containing the oldest data
                start_from, _ = self._period_manager.get_period_boundaries(oldest_data)
                logger.info(f"No previous consolidation found, starting from oldest data: {start_from}")

            # Don't go back too far
            if start_from < cutoff_time:
                start_from = self._period_manager.get_period_start(cutoff_time)
                logger.info(f"Limiting lookback to 24 hours, adjusted start: {start_from}")

            # Process all missed periods up to the most recent completed period
            current_period_start = self._period_manager.get_period_start(now)
            periods_consolidated = 0

            period_start = start_from
            while period_start < current_period_start:
                period_end = period_start + self._consolidation_interval

                # Check if this period needs consolidation
                if not self._query_manager.check_period_consolidated(period_start):
                    # Try to acquire lock for this period - only one occurrence should consolidate
                    lock_key = f"missed:{period_start.isoformat()}"
                    if self._query_manager._try_acquire_lock(lock_key):
                        logger.info(f"Acquired lock, consolidating missed period: {period_start} to {period_end}")
                        # Console output for mobile app
                        print(f"[CONSOLIDATOR] Processing period {periods_consolidated + 1}...", flush=True)

                        summaries = await self._consolidate_period(period_start, period_end)
                        if summaries:
                            logger.info(f"Created {len(summaries)} summaries for missed period {period_start}")
                            periods_consolidated += 1
                        else:
                            logger.debug(f"No data found for period {period_start}")
                    else:
                        logger.info(f"Another occurrence is consolidating period {period_start}, skipping")
                else:
                    logger.debug(f"Period {period_start} already consolidated, checking edges...")
                    # Ensure edges exist for this already-consolidated period
                    await self._ensure_summary_edges(period_start, period_end)

                # Move to next period
                period_start = period_end

                # Safety limit to prevent excessive processing
                if periods_consolidated >= 10:
                    logger.warning("Reached limit of 10 periods in missed window consolidation")
                    break

            if periods_consolidated > 0:
                logger.info(f"Successfully consolidated {periods_consolidated} missed periods")
                # Console output for mobile app
                print(f"[CONSOLIDATOR] Complete - {periods_consolidated} periods processed", flush=True)
                self._last_consolidation = now
            else:
                logger.info("No missed periods needed consolidation")
                # Console output for mobile app
                print("[CONSOLIDATOR] Complete - no missed periods", flush=True)

        except Exception as e:
            logger.error(f"Failed to consolidate missed windows: {e}", exc_info=True)


    def _find_oldest_unconsolidated_period(self) -> Optional[datetime]:
        """Find the oldest tsdb_data graph node or correlation needing consolidation.

        Post-A1 absorption: uses persist's cirisgraph_query_nodes (ASC by
        created_at, limit 1) for the node side and correlation_query (ASC by
        timestamp via empty filter, limit 1) for the correlation side.
        Returns the older of the two.
        """
        import json as _json

        from ciris_engine.logic.persistence.models.graph import get_persist_engine
        from ciris_engine.logic.services.graph.tsdb_consolidation.sql_builders import parse_datetime_field

        engine = get_persist_engine()
        if engine is None:
            return None

        candidates: List[datetime] = []

        # Oldest tsdb_data node: persist returns DESC by default; use the
        # `order` filter knob if available, otherwise paginate to the tail.
        try:
            filter_json = _json.dumps({
                "scope": "ENVIRONMENT",  # TSDB nodes live in ENVIRONMENT scope
                "node_type": "tsdb_data",
                "order": "asc",
            })
            cursor = _json.dumps({"version": "v1", "last_ts": "9999-12-31T23:59:59Z", "last_id": ""})
            raw = engine.cirisgraph_query_nodes(filter_json, cursor, 1)
            parsed = _json.loads(raw) if isinstance(raw, (bytes, str)) else raw
            items = parsed.get("items", []) if isinstance(parsed, dict) else []
            if items:
                created_at_raw = items[0].get("created_at")
                parsed_dt = parse_datetime_field(created_at_raw) if created_at_raw else None
                if parsed_dt:
                    candidates.append(parsed_dt)
        except Exception as e:
            logger.warning(f"Failed to find oldest tsdb_data via persist: {e}")

        # Oldest correlation
        try:
            cursor = _json.dumps({"version": "v1", "last_ts": "9999-12-31T23:59:59Z", "last_id": ""})
            raw = engine.correlation_query(_json.dumps({"order": "asc"}), cursor, 1)
            parsed = _json.loads(raw) if isinstance(raw, (bytes, str)) else raw
            items = parsed.get("items", []) if isinstance(parsed, dict) else []
            if items:
                ts_raw = items[0].get("timestamp") or items[0].get("created_at")
                parsed_dt = parse_datetime_field(ts_raw) if ts_raw else None
                if parsed_dt:
                    candidates.append(parsed_dt)
        except Exception as e:
            logger.warning(f"Failed to find oldest correlation via persist: {e}")

        return min(candidates) if candidates else None

    def _cleanup_old_data(self) -> int:
        """Prune consolidated summary nodes older than the retention window.

        Post-A1 absorption (CIRISAgent#763, CIRISPersist#63): routes through
        persist's `tsdb_prune_summaries(level, tenant_id, before)` for each
        summary node_type. Persist cascades TEMPORAL_NEXT edges internally.
        The audit chain in `cirislens_audit_log` is preserved — persist's
        prune call only touches summary nodes.
        """
        try:
            import os

            from ciris_engine.logic.persistence.models.graph import get_persist_engine
            from ciris_engine.logic.services.graph.tsdb_consolidation.date_calculation_helpers import (
                get_retention_cutoff_date,
            )

            engine = get_persist_engine()
            if engine is None:
                return 0

            tenant_id = os.environ.get("CIRIS_AGENT_TENANT", "agent-default")
            retention_cutoff = get_retention_cutoff_date(
                self._now(), int(self._raw_retention.total_seconds() / 3600)
            )
            cutoff_iso = retention_cutoff.isoformat().replace("+00:00", "Z")

            total_deleted = 0
            for level in ("basic", "daily", "weekly"):  # 'monthly' retained for long-term archival
                try:
                    deleted = int(engine.tsdb_prune_summaries(level, tenant_id, cutoff_iso))
                except Exception as e:
                    logger.warning(f"tsdb_prune_summaries({level}) failed: {e}")
                    continue
                total_deleted += deleted

            if total_deleted > 0:
                logger.info(f"Cleanup complete: pruned {total_deleted} summary nodes")
            else:
                logger.info("No expired summary nodes to prune")
            return total_deleted

        except Exception as e:
            logger.error(f"Error during cleanup: {e}", exc_info=True)
            return 0

    async def is_healthy(self) -> bool:
        """Check if the service is healthy.

        The service is healthy if:
        - It's running
        - Memory bus is available

        Note: We don't check consolidation_task state because the task may
        complete between consolidation windows and that's normal behavior.
        """
        return self._running and self._memory_bus is not None

    def get_capabilities(self) -> ServiceCapabilities:
        """Get service capabilities."""
        return ServiceCapabilities(
            service_name="TSDBConsolidationService",
            actions=[
                "consolidate_tsdb_nodes",
                "consolidate_all_data",
                "create_proper_edges",
                "track_memory_events",
                "summarize_tasks",
                "create_6hour_summaries",
            ],
            version="2.0.0",
            dependencies=["MemoryService", "TimeService"],
            metadata=None,
        )

    def get_status(self) -> ServiceStatus:
        """Get service status."""
        current_time = self._now()
        uptime_seconds = 0.0
        if self._start_time:
            uptime_seconds = (current_time - self._start_time).total_seconds()

        return ServiceStatus(
            service_name="TSDBConsolidationService",
            service_type="graph_service",
            is_healthy=self._running and self._memory_bus is not None,
            uptime_seconds=uptime_seconds,
            metrics={
                "last_consolidation_timestamp": (
                    self._last_consolidation.timestamp() if self._last_consolidation else 0.0
                ),
                "task_running": 1.0 if (self._consolidation_task and not self._consolidation_task.done()) else 0.0,
                "last_basic_consolidation": self._last_consolidation.timestamp() if self._last_consolidation else 0.0,
                "last_extensive_consolidation": (
                    self._last_extensive_consolidation.timestamp() if self._last_extensive_consolidation else 0.0
                ),
                "last_profound_consolidation": (
                    self._last_profound_consolidation.timestamp() if self._last_profound_consolidation else 0.0
                ),
                "consolidation_task_running": (
                    1.0 if (self._consolidation_task and not self._consolidation_task.done()) else 0.0
                ),
            },
            last_error=None,
            last_health_check=current_time,
            custom_metrics={
                "basic_interval_hours": self._basic_interval.total_seconds() / 3600,
                "extensive_interval_days": self._extensive_interval.total_seconds() / 86400,
                "profound_interval_days": self._profound_interval.total_seconds() / 86400,
                "profound_target_mb_per_day": self._profound_target_mb_per_day,
            },
        )

    def get_node_type(self) -> NodeType:
        """Get the node type this service manages."""
        return NodeType.TSDB_SUMMARY

    def _is_period_consolidated(self, period_start: datetime, period_end: datetime) -> bool:
        """Check if a period has been consolidated via persist's substrate.

        Persist exposes `tsdb_query_summary_nodes` per typed sub-table
        (`task_summary` / `conversation_summary` / `trace_summary` /
        `audit_summary`); the cirisgraph-namespace string
        "tsdb_summary" is NOT a valid `node_type` argument and would
        silently return zero rows (root cause of #788's
        "never-advances" behaviour). Use the shared
        `query_typed_summaries` helper which unions across all 4 typed
        tables.
        """
        try:
            import os

            from ciris_engine.logic.persistence.models.graph import get_persist_engine
            from ciris_engine.logic.services.graph.tsdb_consolidation.query_manager import (
                query_typed_summaries,
            )

            engine = get_persist_engine()
            if engine is None:
                return False

            tenant_id = os.environ.get("CIRIS_AGENT_TENANT", "agent-default")
            from_iso = period_start.isoformat().replace("+00:00", "Z")
            to_iso = (period_end + timedelta(milliseconds=1)).isoformat().replace("+00:00", "Z")

            rows = query_typed_summaries(engine, "basic", tenant_id, from_iso, to_iso)
            return bool(rows)
        except Exception as e:
            logger.error(f"Error checking if period consolidated: {e}")
            return False

    async def _consolidate_period(
        self, period_start: datetime, period_end: datetime
    ) -> List[Dict[str, Any]]:
        """Basic (6-hour) consolidation: run persist's 5 consolidators for
        this period at `level=basic`, then read back the summary rows
        they produced via `tsdb_query_summary_nodes`.

        Mirrors the pattern in `_run_extensive_consolidation` (`level=daily`)
        and `_run_profound_consolidation` (`level=weekly`/`monthly`), but
        scoped to the single period. Returns the list of summary node
        dicts the caller uses to count and report.
        """
        import json as _json
        import os

        from ciris_engine.logic.persistence.models.graph import get_persist_engine

        engine = get_persist_engine()
        if engine is None:
            logger.warning("persist engine not wired — basic consolidation skipped")
            return []

        tenant_id = os.environ.get("CIRIS_AGENT_TENANT", "agent-default")
        req_json = _json.dumps({
            "tenant_id": tenant_id,
            "period_start": period_start.isoformat().replace("+00:00", "Z"),
            "period_end": period_end.isoformat().replace("+00:00", "Z"),
            "locked_by": f"ciris-agent-{os.environ.get('CIRIS_AGENT_ID', 'default')}",
            "level": "basic",
        })

        for name in (
            "telemetry_consolidate_period",
            "tsdb_consolidate_tasks",
            "tsdb_consolidate_conversations",
            "tsdb_consolidate_traces",
            "tsdb_consolidate_audit",
        ):
            try:
                await asyncio.to_thread(getattr(engine, name), req_json)
            except Exception as e:
                logger.error(f"persist {name}(level=basic) failed: {e}", exc_info=True)

        # Read back any summary rows produced for this period.
        # Persist's `tsdb_query_summary_nodes` is typed (one node_type
        # per call); the previous single-arg JSON-blob shape was
        # removed in CIRISPersist v1.6.2 and any call still using it
        # raises TypeError on import (this was the root cause of #788).
        # Use the shared helper which unions across all 4 typed tables.
        from ciris_engine.logic.services.graph.tsdb_consolidation.query_manager import (
            query_typed_summaries,
        )

        from_iso = period_start.isoformat().replace("+00:00", "Z")
        to_iso = period_end.isoformat().replace("+00:00", "Z")
        try:
            summaries: List[Dict[str, Any]] = await asyncio.to_thread(
                query_typed_summaries, engine, "basic", tenant_id, from_iso, to_iso
            )
        except Exception as e:
            logger.error(f"reading summaries for period failed: {e}", exc_info=True)
            summaries = []

        if summaries:
            self._basic_consolidations += 1
            self._records_consolidated += len(summaries)
        return summaries

    async def _ensure_summary_edges(self, period_start: datetime, period_end: datetime) -> None:
        """
        Ensure edges exist for an already-consolidated period.
        This fixes the issue where summaries exist but have no SUMMARIZES edges.

        Args:
            period_start: Start of the period
            period_end: End of the period
        """
        try:
            period_label = self._period_manager.get_period_label(period_start)
            logger.info(f"Ensuring edges exist for consolidated period {period_label}")

            # Find the summary node for this period
            period_id = period_start.strftime("%Y%m%d_%H")
            summary_id = f"tsdb_summary_{period_id}"

            # Check if SUMMARIZES edges already exist via persist substrate.
            import json as _json

            from ciris_engine.logic.persistence.models.graph import get_persist_engine

            engine = get_persist_engine()
            if engine is not None:
                try:
                    raw = engine.cirisgraph_get_edges_for_node(summary_id, "LOCAL", "outbound", None)
                    edges = _json.loads(raw) if isinstance(raw, (bytes, str)) else (raw or [])
                    summarizes_count = sum(
                        1 for e in edges if isinstance(e, dict) and e.get("relationship") == "SUMMARIZES"
                    )
                    if summarizes_count > 0:
                        logger.debug(
                            f"Period {period_label} already has {summarizes_count} SUMMARIZES edges"
                        )
                        return
                except Exception as e:
                    logger.warning(f"persist edge-check failed for {summary_id}: {e}")

            # No SUMMARIZES edges exist - we need to create them
            logger.warning(f"Period {period_label} has NO SUMMARIZES edges! Creating them now...")

            # Query all nodes in the period
            nodes_by_type = self._query_manager.query_all_nodes_in_period(period_start, period_end)

            # Get the summary node
            from ciris_engine.schemas.services.graph_core import GraphNode, GraphScope, NodeType

            summary_node = GraphNode(
                id=summary_id,
                type=NodeType.TSDB_SUMMARY,
                scope=GraphScope.LOCAL,
                attributes={},
                updated_by="tsdb_consolidation",
                updated_at=period_end,
            )

            # Collect all nodes (except tsdb_data)
            all_nodes_in_period = []
            for node_type, result in nodes_by_type.items():
                if node_type != "tsdb_data" and hasattr(result, "nodes"):
                    all_nodes_in_period.extend(result.nodes)

            if all_nodes_in_period:
                logger.info(f"Creating SUMMARIZES edges from {summary_id} to {len(all_nodes_in_period)} nodes")
                edges_created = self._edge_manager.create_summary_to_nodes_edges(
                    summary_node, all_nodes_in_period, "SUMMARIZES", f"Node active during {period_label}"
                )
                logger.info(f"Created {edges_created} SUMMARIZES edges for period {period_label}")
            else:
                logger.warning(f"No nodes found in period {period_label} to create edges to")

        except Exception as e:
            logger.error(f"Error ensuring summary edges: {e}", exc_info=True)

    def _calculate_next_run_time(self) -> datetime:
        """Calculate when the next consolidation should run."""
        # Run at the start of the next 6-hour period
        current_time = self._now()
        hours_since_epoch = current_time.timestamp() / 3600
        periods_since_epoch = int(hours_since_epoch / 6)
        next_period = periods_since_epoch + 1
        next_run_timestamp = next_period * 6 * 3600
        return datetime.fromtimestamp(next_run_timestamp, tz=timezone.utc)

    def _calculate_next_period_start(self, interval: timedelta) -> datetime:
        """Calculate the next period start for a given interval."""
        current_time = self._now()
        seconds_since_epoch = current_time.timestamp()
        interval_seconds = interval.total_seconds()
        periods_since_epoch = int(seconds_since_epoch / interval_seconds)
        next_period = periods_since_epoch + 1
        next_run_timestamp = next_period * interval_seconds
        return datetime.fromtimestamp(next_run_timestamp, tz=timezone.utc)

    def _get_next_weekly_monday(self) -> datetime:
        """Get next Monday at 00:00 UTC for weekly consolidation."""
        now = self._now()
        days_until_monday = (7 - now.weekday()) % 7

        # If it's Monday but past midnight, schedule for next Monday
        if days_until_monday == 0 and now.hour > 0:
            days_until_monday = 7

        next_monday = now.date() + timedelta(days=days_until_monday)
        return datetime.combine(next_monday, datetime.min.time(), tzinfo=timezone.utc)

    def _get_next_month_start(self) -> datetime:
        """Get first day of next month at 00:00 UTC for monthly consolidation."""
        now = self._now()

        # If it's the 1st at exactly 00:00, run now
        if now.day == 1 and now.hour == 0 and now.minute == 0:
            return now.replace(second=0, microsecond=0)

        # Otherwise, calculate first day of next month
        if now.month == 12:
            next_month_date = now.replace(year=now.year + 1, month=1, day=1)
        else:
            next_month_date = now.replace(month=now.month + 1, day=1)

        return next_month_date.replace(hour=0, minute=0, second=0, microsecond=0)

    def _cleanup_old_nodes(self) -> int:
        """Legacy method name - calls _cleanup_old_data."""
        result = self._cleanup_old_data()
        return result if result is not None else 0

    def get_summary_for_period(self, period_start: datetime, period_end: datetime) -> Optional[TSDBPeriodSummary]:
        """Get the consolidated summary for a specific period via persist.

        Persist exposes one summary per typed sub-table; we union across
        all 4 (see `query_typed_summaries` docstring + #788). Returns the
        typed TSDBPeriodSummary built from the FIRST matching attributes
        dict — under normal consolidation any of the 4 sub-tables carries
        the period-level totals + metrics this caller needs.
        """
        try:
            import os

            from ciris_engine.logic.persistence.models.graph import get_persist_engine
            from ciris_engine.logic.services.graph.tsdb_consolidation.query_manager import (
                query_typed_summaries,
            )

            engine = get_persist_engine()
            if engine is None:
                return None

            tenant_id = os.environ.get("CIRIS_AGENT_TENANT", "agent-default")
            from_iso = period_start.isoformat().replace("+00:00", "Z")
            to_iso = (period_end + timedelta(milliseconds=1)).isoformat().replace("+00:00", "Z")

            rows = query_typed_summaries(engine, "basic", tenant_id, from_iso, to_iso)
            if not rows:
                return None
            attrs = rows[0] if isinstance(rows[0], dict) else {}

            return TSDBPeriodSummary(
                metrics=attrs.get("metrics", {}),
                total_tokens=attrs.get("total_tokens", 0),
                total_cost_cents=attrs.get("total_cost_cents", 0),
                total_carbon_grams=attrs.get("total_carbon_grams", 0),
                total_energy_kwh=attrs.get("total_energy_kwh", 0),
                action_counts=attrs.get("action_counts", {}),
                source_node_count=attrs.get("source_node_count", 0),
                period_start=attrs.get("period_start", period_start.isoformat()),
                period_end=attrs.get("period_end", period_end.isoformat()),
                period_label=attrs.get("period_label", ""),
                conversations=attrs.get("conversations", []),
                traces=attrs.get("traces", []),
                audits=attrs.get("audits", []),
                tasks=attrs.get("tasks", []),
                memories=attrs.get("memories", []),
            )
        except Exception as e:
            logger.error(f"Error getting summary for period: {e}")
            return None

    def get_service_type(self) -> ServiceType:
        """Get the service type."""
        return ServiceType.TELEMETRY

    def _should_anonymize_node(self, node: GraphNode, period_end: datetime) -> bool:
        """Check if a node should be anonymized due to consent expiry."""
        if not hasattr(node, "consent_stream") or not hasattr(node, "expires_at"):
            return False

        if node.consent_stream != ConsentStream.TEMPORARY or not node.expires_at:
            return False

        return period_end > node.expires_at

    def _generate_anonymized_id(self, original_id: str, consent_stream: ConsentStream) -> str:
        """Generate anonymized ID based on hash of original ID."""
        import hashlib

        id_hash = hashlib.sha256(original_id.encode()).hexdigest()[:8]

        if consent_stream == ConsentStream.TEMPORARY:
            return f"temporary_user_{id_hash}"
        else:
            return f"anonymous_user_{id_hash}"

    def _remove_pii_from_attributes(self, node: GraphNode, period_end: datetime) -> None:
        """Remove PII fields from node attributes and add anonymization metadata."""
        if not hasattr(node, "attributes") or not isinstance(node.attributes, dict):
            return

        # Remove PII fields
        pii_fields = ["email", "name", "phone", "address", "ip_address"]
        for field in pii_fields:
            if field in node.attributes:
                del node.attributes[field]

        # Add anonymization metadata
        node.attributes["anonymized_at"] = period_end.isoformat()
        node.attributes["original_stream"] = node.consent_stream

    async def _update_anonymized_node(self, node: GraphNode, old_id: str) -> None:
        """Update anonymized node in memory bus."""
        if not self._memory_bus:
            return

        try:
            status = await self._memory_bus.memorize(node, handler_name="tsdb_consolidation")
            if status.status == MemoryOpStatus.SUCCESS:
                logger.info(f"Successfully anonymized node {old_id}")
            else:
                logger.warning(f"Failed to update anonymized node: {status.reason}")
        except Exception as e:
            logger.error(f"Error updating anonymized node: {e}")

    async def _handle_consent_expiry(self, nodes_by_type: Dict[str, TSDBNodeQueryResult], period_end: datetime) -> None:
        """
        Handle consent expiry by anonymizing expired TEMPORARY nodes.

        When a TEMPORARY node expires (14 days), it gets renamed from:
        - user_<id> -> temporary_user_<hash>

        When transitioning to ANONYMOUS, it becomes:
        - user_<id> -> anonymous_user_<hash>

        Args:
            nodes_by_type: All nodes in the period by type
            period_end: End of the consolidation period
        """
        # Check user nodes for expiry
        user_nodes = nodes_by_type.get(
            "user", TSDBNodeQueryResult(nodes=[], period_start=period_end, period_end=period_end)
        ).nodes

        for node in user_nodes:
            if not self._should_anonymize_node(node, period_end):
                continue

            # Node has expired - anonymize it
            old_id = node.id
            new_id = self._generate_anonymized_id(old_id, node.consent_stream)

            logger.info(f"Anonymizing expired node: {old_id} -> {new_id}")

            # Update the node ID
            node.id = new_id

            # Clear any PII from attributes
            self._remove_pii_from_attributes(node, period_end)

            # Update in memory bus
            await self._update_anonymized_node(node, old_id)

    def _get_actions(self) -> List[str]:
        """Get list of actions this service can handle."""
        # Graph services typically don't handle actions through buses
        return []

    async def _run_extensive_consolidation(self) -> None:
        """Extensive (weekly) consolidation — daily-tier rollup via persist.

        Post-Phase 3b cutover (CIRISAgent#763, CIRISPersist#63 + #68): persist
        owns the entire daily-tier aggregation. The agent issues one
        consolidation request per (summary_type) with `level=daily` over the
        previous week; persist reads basic-level summaries from that period
        and emits a daily summary node + the TEMPORAL_NEXT chain.
        """
        import json as _json
        import os

        from ciris_engine.logic.persistence.models.graph import get_persist_engine
        from ciris_engine.logic.services.graph.tsdb_consolidation.date_calculation_helpers import (
            calculate_week_period,
        )

        consolidation_start = self._now()
        try:
            logger.info("=" * 60)
            logger.info("Starting extensive (weekly) consolidation via persist")
            now = self._now()
            period_start, period_end = calculate_week_period(now)
            week_identifier = period_start.date().isoformat()

            logger.info(
                f"Consolidating week: {period_start.isoformat()} → {period_end.isoformat()}"
            )

            # Lock: persist's lock_acquire substrate is already used by
            # query_manager.acquire_consolidation_lock — keep that here.
            lock_acquired = self._query_manager.acquire_consolidation_lock(
                "extensive", week_identifier
            )
            if not lock_acquired:
                logger.info(
                    f"Extensive consolidation for week {week_identifier} locked by another instance, skipping"
                )
                return

            try:
                engine = get_persist_engine()
                if engine is None:
                    logger.warning("persist engine not wired — extensive consolidation skipped")
                    return

                tenant_id = os.environ.get("CIRIS_AGENT_TENANT", "agent-default")
                req_json = _json.dumps({
                    "tenant_id": tenant_id,
                    "period_start": period_start.isoformat().replace("+00:00", "Z"),
                    "period_end": period_end.isoformat().replace("+00:00", "Z"),
                    "locked_by": f"ciris-agent-{os.environ.get('CIRIS_AGENT_ID', 'default')}",
                    "level": "daily",
                })

                outcomes: Dict[str, Any] = {}
                for name in (
                    "telemetry_consolidate_period",
                    "tsdb_consolidate_tasks",
                    "tsdb_consolidate_conversations",
                    "tsdb_consolidate_traces",
                    "tsdb_consolidate_audit",
                ):
                    try:
                        raw = getattr(engine, name)(req_json)
                        outcomes[name] = (
                            _json.loads(raw) if isinstance(raw, (bytes, str)) else raw
                        )
                    except Exception as e:
                        logger.error(f"persist {name}(level=daily) failed: {e}", exc_info=True)
                        outcomes[name] = {"error": str(e)}

                total_duration = (self._now() - consolidation_start).total_seconds()
                logger.info(
                    f"Extensive consolidation complete in {total_duration:.2f}s: outcomes={outcomes}"
                )
                logger.info("=" * 60)
            finally:
                self._query_manager.release_consolidation_lock("extensive", week_identifier)

        except Exception as e:
            logger.error(f"Extensive consolidation failed: {e}", exc_info=True)

    async def get_metrics(self) -> Dict[str, float]:
        """Get TSDB consolidation service metrics.

        Returns exactly the 4 metrics from v1.4.3 API specification:
        - tsdb_consolidations_total: Total consolidations performed
        - tsdb_datapoints_processed: Total data points processed
        - tsdb_storage_saved_mb: Storage saved by consolidation (MB)
        - tsdb_uptime_seconds: Service uptime in seconds
        """
        # Calculate uptime
        uptime_seconds = 0.0
        if hasattr(self, "_start_time") and self._start_time:
            uptime_seconds = (self._now() - self._start_time).total_seconds()

        # Calculate total consolidations performed
        total_consolidations = (
            self._basic_consolidations + self._extensive_consolidations + self._profound_consolidations
        )

        # Calculate storage saved (estimate based on compression ratio and records processed)
        # Each record averages ~2KB, storage saved = records_deleted * avg_size_kb / 1024
        avg_record_size_kb = 2.0
        storage_saved_mb = (self._records_deleted * avg_record_size_kb) / 1024.0

        return {
            "tsdb_consolidations_total": float(total_consolidations),
            "tsdb_datapoints_processed": float(self._records_consolidated),
            "tsdb_storage_saved_mb": storage_saved_mb,
            "tsdb_uptime_seconds": uptime_seconds,
        }

    def _run_profound_consolidation(self) -> None:
        """Profound (monthly) consolidation — weekly/monthly tier rollup via persist.

        Post-Phase 3b cutover (CIRISAgent#763): persist's consolidators with
        `level=weekly` then `level=monthly` produce the higher-tier summaries.
        Storage-compression of daily nodes is a future feature once persist
        exposes a `tsdb_compress_summaries` substrate (not in scope for 2.9.0).
        Basic-summary cleanup is delegated to `tsdb_prune_summaries`.
        """
        import json as _json
        import os

        from ciris_engine.logic.persistence.models.graph import get_persist_engine
        from ciris_engine.logic.services.graph.tsdb_consolidation.date_calculation_helpers import (
            calculate_month_period,
        )

        consolidation_start = self._now()
        try:
            logger.info("=" * 60)
            logger.info("Starting profound (monthly) consolidation via persist")
            now = self._now()
            month_start, month_end = calculate_month_period(now)
            month_identifier = month_start.strftime("%Y-%m")

            lock_acquired = self._query_manager.acquire_consolidation_lock(
                "profound", month_identifier
            )
            if not lock_acquired:
                logger.info(
                    f"Profound consolidation for month {month_identifier} locked by another instance, skipping"
                )
                return

            try:
                engine = get_persist_engine()
                if engine is None:
                    logger.warning("persist engine not wired — profound consolidation skipped")
                    return

                tenant_id = os.environ.get("CIRIS_AGENT_TENANT", "agent-default")
                base_req = {
                    "tenant_id": tenant_id,
                    "period_start": month_start.isoformat().replace("+00:00", "Z"),
                    "period_end": month_end.isoformat().replace("+00:00", "Z"),
                    "locked_by": f"ciris-agent-{os.environ.get('CIRIS_AGENT_ID', 'default')}",
                }

                outcomes: Dict[str, Any] = {}
                for level in ("weekly", "monthly"):
                    req_json = _json.dumps({**base_req, "level": level})
                    for name in (
                        "telemetry_consolidate_period",
                        "tsdb_consolidate_tasks",
                        "tsdb_consolidate_conversations",
                        "tsdb_consolidate_traces",
                        "tsdb_consolidate_audit",
                    ):
                        try:
                            raw = getattr(engine, name)(req_json)
                            outcomes[f"{level}/{name}"] = (
                                _json.loads(raw) if isinstance(raw, (bytes, str)) else raw
                            )
                        except Exception as e:
                            logger.error(
                                f"persist {name}(level={level}) failed: {e}", exc_info=True
                            )
                            outcomes[f"{level}/{name}"] = {"error": str(e)}

                # Prune basic-tier summaries older than the retention window.
                cleanup_cutoff = (now - timedelta(days=30)).isoformat().replace("+00:00", "Z")
                try:
                    deleted = int(engine.tsdb_prune_summaries("basic", tenant_id, cleanup_cutoff))
                    if deleted > 0:
                        logger.info(f"Pruned {deleted} stale basic summary nodes")
                except Exception as e:
                    logger.warning(f"tsdb_prune_summaries(basic) failed: {e}")

                total_duration = (self._now() - consolidation_start).total_seconds()
                logger.info(
                    f"Profound consolidation complete in {total_duration:.2f}s: outcomes={outcomes}"
                )
                logger.info("=" * 60)
                self._last_profound_consolidation = now

            finally:
                self._query_manager.release_consolidation_lock("profound", month_identifier)

        except Exception as e:
            logger.error(f"Profound consolidation failed: {e}", exc_info=True)
