"""
TSDB Consolidation Service - Main service class.

This service runs every 6 hours to consolidate telemetry and memory data
into permanent summary records with proper edge connections.
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Union
from uuid import uuid4

if TYPE_CHECKING:
    from ciris_engine.logic.registries.base import ServiceRegistry

from ciris_engine.constants import UTC_TIMEZONE_SUFFIX
from ciris_engine.logic.buses.memory_bus import MemoryBus
from ciris_engine.logic.services.base_graph_service import BaseGraphService
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
from ciris_engine.schemas.services.graph.query_results import TSDBNodeQueryResult
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


class TSDBConsolidationService(BaseGraphService):
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
        self._extensive_task: Optional[asyncio.Task[None]] = None
        self._profound_task: Optional[asyncio.Task[None]] = None
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

    def _set_service_registry(self, registry: "ServiceRegistry") -> None:
        """Set the service registry for accessing services."""
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

        # Consolidate any missed windows before starting the regular loop
        await self._consolidate_missed_windows()

        # Start all consolidation loops
        self._consolidation_task = asyncio.create_task(self._consolidation_loop())
        self._extensive_task = asyncio.create_task(self._extensive_consolidation_loop())
        self._profound_task = asyncio.create_task(self._profound_consolidation_loop())
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

        # Cancel all tasks
        tasks_to_cancel = [self._consolidation_task, self._extensive_task, self._profound_task]

        for task in tasks_to_cancel:
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass  # NOSONAR - Expected when stopping the service in stop()

        await super().stop()
        logger.info("TSDBConsolidationService stopped")

    async def _consolidation_loop(self) -> None:
        """Main consolidation loop that runs every 6 hours."""
        while self._running:
            try:
                # Calculate next run time
                next_run = self._period_manager.get_next_period_start(self._now())
                wait_seconds = (next_run - self._now()).total_seconds()

                if wait_seconds > 0:
                    logger.info(f"Next consolidation at {next_run} ({wait_seconds:.0f}s)")
                    await asyncio.sleep(wait_seconds)

                if self._running:
                    await self._run_consolidation()

            except asyncio.CancelledError:
                logger.debug("Consolidation loop cancelled")
                raise  # Re-raise to properly exit the task
            except Exception as e:
                logger.error(f"Consolidation loop error: {e}", exc_info=True)
                await asyncio.sleep(300)  # 5 minutes

    async def _extensive_consolidation_loop(self) -> None:
        """Extensive consolidation loop that runs weekly on Mondays."""
        # Wait one hour before starting extensive consolidation
        await asyncio.sleep(3600)

        while self._running:
            try:
                # Calculate next Monday at 00:00 UTC
                next_run = self._get_next_weekly_monday()
                wait_seconds = (next_run - self._now()).total_seconds()

                if wait_seconds > 0:
                    logger.info(
                        f"Next extensive consolidation on Monday {next_run.date()} at 00:00 UTC ({wait_seconds:.0f}s)"
                    )
                    await asyncio.sleep(wait_seconds)

                if self._running:
                    await self._run_extensive_consolidation()

                    # CRITICAL: After running, we must ensure we wait until the NEXT Monday
                    # Otherwise we'll run again immediately if we're still in the same time window
                    next_run = self._get_next_weekly_monday()
                    # Force calculation to be at least 1 day in the future
                    min_next_run = self._now() + timedelta(days=1)
                    if next_run <= min_next_run:
                        # If next Monday is too close, add a week
                        next_run = next_run + timedelta(days=7)

                    wait_seconds = (next_run - self._now()).total_seconds()
                    if wait_seconds > 0:
                        logger.info(
                            f"Extensive consolidation complete. Next run on Monday {next_run.date()} at 00:00 UTC ({wait_seconds:.0f}s)"
                        )
                        await asyncio.sleep(wait_seconds)

            except asyncio.CancelledError:
                logger.debug("Extensive consolidation loop cancelled")
                raise
            except Exception as e:
                logger.error(f"Extensive consolidation error: {e}", exc_info=True)
                await asyncio.sleep(3600)  # 1 hour

    async def _profound_consolidation_loop(self) -> None:
        """Profound consolidation loop that runs monthly on the 1st."""
        # Wait two hours before starting profound consolidation
        await asyncio.sleep(7200)

        while self._running:
            try:
                # Calculate next 1st of month at 00:00 UTC
                next_run = self._get_next_month_start()
                wait_seconds = (next_run - self._now()).total_seconds()

                if wait_seconds > 0:
                    logger.info(
                        f"Next profound consolidation on {next_run.strftime('%Y-%m-01')} at 00:00 UTC ({wait_seconds:.0f}s)"
                    )
                    await asyncio.sleep(wait_seconds)

                if self._running:
                    self._run_profound_consolidation()

                    # CRITICAL: After running, we must ensure we wait until the NEXT month
                    # Otherwise we'll run again immediately if we're still in the same time window
                    next_run = self._get_next_month_start()
                    # Force calculation to be at least 1 day in the future
                    min_next_run = self._now() + timedelta(days=1)
                    if next_run <= min_next_run:
                        # If next month start is too close, add a month
                        # Move to next month
                        if next_run.month == 12:
                            next_run = next_run.replace(year=next_run.year + 1, month=1)
                        else:
                            next_run = next_run.replace(month=next_run.month + 1)

                    wait_seconds = (next_run - self._now()).total_seconds()
                    if wait_seconds > 0:
                        logger.info(
                            f"Profound consolidation complete. Next run on {next_run.strftime('%Y-%m-01')} at 00:00 UTC ({wait_seconds:.0f}s)"
                        )
                        await asyncio.sleep(wait_seconds)

            except asyncio.CancelledError:
                logger.debug("Profound consolidation loop cancelled")
                raise
            except Exception as e:
                logger.error(f"Profound consolidation error: {e}", exc_info=True)
                await asyncio.sleep(3600)  # 1 hour

    async def _run_consolidation(self) -> None:
        """Run a single consolidation cycle."""
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

            # Get oldest unconsolidated data
            oldest_data = self._find_oldest_unconsolidated_period()
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

                # Check if already consolidated
                if not self._query_manager.check_period_consolidated(current_start):
                    period_start_time = self._now()
                    logger.info(f"Consolidating period: {current_start.isoformat()} to {current_end.isoformat()}")

                    # Count records in this period before consolidation
                    period_records = len(self._query_manager.query_all_nodes_in_period(current_start, current_end))
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

                current_start = current_end

            if periods_consolidated > 0:
                logger.info(f"Consolidation complete: {periods_consolidated} periods processed")
                logger.info(f"  - Total records processed: {total_records_processed}")
                logger.info(f"  - Total summaries created: {total_summaries_created}")
                if total_records_processed > 0:
                    compression_ratio = total_records_processed / max(total_summaries_created, 1)
                    logger.info(f"  - Compression ratio: {compression_ratio:.1f}:1")

            # Cleanup old data
            cleanup_start = self._now()
            logger.info("Starting cleanup of old consolidated data...")
            # Count nodes before cleanup (logged later)
            len(self._query_manager.query_all_nodes_in_period(now - timedelta(days=30), now))

            nodes_deleted = self._cleanup_old_data()
            cleanup_stats["nodes_deleted"] = nodes_deleted

            # Cleanup orphaned edges
            edges_deleted = self._edge_manager.cleanup_orphaned_edges()
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
                    logger.info(f"Consolidating missed period: {period_start} to {period_end}")

                    summaries = await self._consolidate_period(period_start, period_end)
                    if summaries:
                        logger.info(f"Created {len(summaries)} summaries for missed period {period_start}")
                        periods_consolidated += 1
                    else:
                        logger.debug(f"No data found for period {period_start}")
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
                self._last_consolidation = now
            else:
                logger.info("No missed periods needed consolidation")

        except Exception as e:
            logger.error(f"Failed to consolidate missed windows: {e}", exc_info=True)

    async def _consolidate_period(self, period_start: datetime, period_end: datetime) -> List[GraphNode]:
        """
        Consolidate all data for a specific period.

        This is the main consolidation logic that:
        1. Queries all nodes and correlations
        2. Creates summary nodes
        3. Creates proper edges

        Args:
            period_start: Start of period
            period_end: End of period

        Returns:
            List of created summary nodes
        """
        period_label = self._period_manager.get_period_label(period_start)
        summaries_created: List[GraphNode] = []

        # 1. Query ALL data for the period
        logger.info(f"Querying all data for period {period_label}")

        # Get all graph nodes in the period
        nodes_by_type = self._query_manager.query_all_nodes_in_period(period_start, period_end)

        # Get all correlations in the period
        correlations = self._query_manager.query_service_correlations(period_start, period_end)

        # Get tasks completed in the period
        tasks = self._query_manager.query_tasks_in_period(period_start, period_end)

        # 1.5. Handle consent expiry - anonymize expired TEMPORARY nodes
        await self._handle_consent_expiry(nodes_by_type, period_end)

        # 2. Create summaries

        # Store converted correlation objects for reuse in edge creation
        converted_correlations: Dict[str, List[Union[MetricCorrelationData, ServiceInteractionData, TraceSpanData]]] = (
            {}
        )
        converted_tasks: List[TaskCorrelationData] = []  # Store converted tasks separately

        # Metrics summary (TSDB data + correlations)
        tsdb_nodes = nodes_by_type.get(
            "tsdb_data", TSDBNodeQueryResult(nodes=[], period_start=period_start, period_end=period_end)
        ).nodes
        metric_correlations = correlations.metric_correlations

        converted_correlations["metric_datapoint"] = list(metric_correlations)

        if tsdb_nodes or metric_correlations:
            metric_summary = await self._metrics_consolidator.consolidate(
                period_start, period_end, period_label, tsdb_nodes, metric_correlations
            )
            if metric_summary:
                summaries_created.append(metric_summary)

        # Task summary (tasks are already TaskCorrelationData objects)
        if tasks:
            # Store converted tasks for edge creation
            converted_tasks = tasks

            task_summary = await self._task_consolidator.consolidate(period_start, period_end, period_label, tasks)
            if task_summary:
                summaries_created.append(task_summary)

        # Memory consolidator doesn't create a summary, it only creates edges
        # We'll call it later in _create_all_edges

        # Conversation summary
        service_interactions = correlations.service_interactions
        if service_interactions:
            converted_correlations["service_interaction"] = list(service_interactions)

            if service_interactions:
                conversation_summary = await self._conversation_consolidator.consolidate(
                    period_start, period_end, period_label, service_interactions
                )
                if conversation_summary:
                    summaries_created.append(conversation_summary)

                    # Get participant data and create user edges
                    participant_data = self._conversation_consolidator.get_participant_data(service_interactions)
                    if participant_data:
                        user_edges = self._edge_manager.create_user_participation_edges(
                            conversation_summary, participant_data, period_label
                        )
                        logger.info(f"Created {user_edges} user participation edges")

        # Trace summary
        trace_spans = correlations.trace_spans
        if trace_spans:
            converted_correlations["trace_span"] = list(trace_spans)

            trace_summary = await self._trace_consolidator.consolidate(
                period_start, period_end, period_label, trace_spans
            )
            if trace_summary:
                summaries_created.append(trace_summary)

        # Audit summary
        audit_nodes = nodes_by_type.get(
            "audit_entry", TSDBNodeQueryResult(nodes=[], period_start=period_start, period_end=period_end)
        ).nodes
        if audit_nodes:
            audit_summary = await self._audit_consolidator.consolidate(
                period_start, period_end, period_label, audit_nodes
            )
            if audit_summary:
                summaries_created.append(audit_summary)

        # 3. Create edges
        if summaries_created:
            await self._create_all_edges(
                summaries_created,
                nodes_by_type,
                converted_correlations,  # Use converted correlations instead of raw
                converted_tasks,  # Use converted tasks instead of raw
                period_start,
                period_label,
            )

        return summaries_created

    def _get_consolidator_edges_for_summary(
        self,
        summary: GraphNode,
        nodes_by_type: Dict[str, TSDBNodeQueryResult],
        correlations: Dict[str, List[Union[MetricCorrelationData, ServiceInteractionData, TraceSpanData]]],
        tasks: List[TaskCorrelationData],
        period_start: datetime,
    ) -> List[Any]:
        """
        Get edges from the appropriate consolidator based on summary type.

        Args:
            summary: Summary node
            nodes_by_type: All nodes in the period by type
            correlations: All correlations in the period by type
            tasks: All tasks in the period
            period_start: Start of the period

        Returns:
            List of edges from the consolidator
        """
        if summary.type == NodeType.TSDB_SUMMARY:
            tsdb_nodes = nodes_by_type.get(
                "tsdb_data", TSDBNodeQueryResult(nodes=[], period_start=period_start, period_end=period_start)
            ).nodes
            metric_correlations_raw = correlations.get("metric_datapoint", [])
            metric_correlations = [c for c in metric_correlations_raw if isinstance(c, MetricCorrelationData)]
            return self._metrics_consolidator.get_edges(summary, tsdb_nodes, metric_correlations)

        elif summary.type == NodeType.CONVERSATION_SUMMARY:
            service_interactions_raw = correlations.get("service_interaction", [])
            service_interactions = [c for c in service_interactions_raw if isinstance(c, ServiceInteractionData)]
            return self._conversation_consolidator.get_edges(summary, service_interactions)

        elif summary.type == NodeType.TRACE_SUMMARY:
            trace_spans_raw = correlations.get("trace_span", [])
            trace_spans = [c for c in trace_spans_raw if isinstance(c, TraceSpanData)]
            return self._trace_consolidator.get_edges(summary, trace_spans)

        elif summary.type == NodeType.AUDIT_SUMMARY:
            audit_nodes = nodes_by_type.get(
                "audit_entry", TSDBNodeQueryResult(nodes=[], period_start=period_start, period_end=period_start)
            ).nodes
            return self._audit_consolidator.get_edges(summary, audit_nodes)

        elif summary.type == NodeType.TASK_SUMMARY:
            return self._task_consolidator.get_edges(summary, tasks)

        return []

    async def _create_daily_summary_edges(
        self,
        summaries: List[GraphNode],
        day: datetime,
    ) -> None:
        """
        Create edges between daily summaries for the same day.

        This method creates:
        1. Cross-type edges (e.g., TSDB->Audit, Task->Trace) within the same day
        2. Temporal edges to previous day's summaries

        Args:
            summaries: List of daily summary nodes
            day: The date for these summaries
        """
        if not summaries:
            return

        # Create cross-summary edges for same day
        if len(summaries) > 1:
            edges_created = self._edge_manager.create_cross_summary_edges(summaries, day)
            logger.info(f"Created {edges_created} same-day edges for {day.date()}")

        # Create temporal edges to previous day for each summary
        for summary in summaries:
            # Extract summary type from ID (e.g., "tsdb_summary_daily_20250715" -> "tsdb_summary")
            parts = summary.id.split("_")
            if len(parts) >= 3 and parts[2] == "daily":
                summary_type = f"{parts[0]}_{parts[1]}"
                # Previous day
                previous_day = day - timedelta(days=1)
                previous_id = f"{summary_type}_daily_{previous_day.strftime('%Y%m%d')}"

                # Create temporal edges
                created = self._edge_manager.create_temporal_edges(summary, previous_id)
                if created:
                    logger.debug(f"Created {created} temporal edges from {summary.id} to {previous_id}")

    async def _create_all_edges(
        self,
        summaries: List[GraphNode],
        nodes_by_type: Dict[str, TSDBNodeQueryResult],
        correlations: Dict[str, List[Union[MetricCorrelationData, ServiceInteractionData, TraceSpanData]]],
        tasks: List[TaskCorrelationData],  # Now contains typed task objects
        period_start: datetime,
        period_label: str,
    ) -> None:
        """
        Create all necessary edges for the summaries.

        This includes:
        1. Type-specific edges (e.g., TSDB->metrics, conversation->users)
        2. Summary->ALL nodes edges (SUMMARIZES relationship)
        3. Temporal edges to previous period
        4. Cross-summary edges within same period

        Args:
            summaries: List of summary nodes created
            nodes_by_type: All nodes in the period by type
            correlations: All correlations in the period by type
            tasks: All tasks in the period
            period_start: Start of the period
            period_label: Human-readable period label
        """
        all_edges = []

        # Collect edges from each consolidator based on summary type
        for summary in summaries:
            edges = self._get_consolidator_edges_for_summary(summary, nodes_by_type, correlations, tasks, period_start)
            all_edges.extend(edges)

        # Get memory edges (links from summaries to memory nodes)
        # Convert TSDBNodeQueryResult back to dict format for memory consolidator
        nodes_by_type_dict = {node_type: result.nodes for node_type, result in nodes_by_type.items()}
        memory_edges = self._memory_consolidator.consolidate(
            period_start, period_start + self._consolidation_interval, period_label, nodes_by_type_dict, summaries
        )
        all_edges.extend(memory_edges)

        # Create all edges in batch
        if all_edges:
            edges_created = self._edge_manager.create_edges(all_edges)
            logger.info(f"Created {edges_created} edges for period {period_label}")

        # CRITICAL: Create edges from summaries to ALL nodes in the period
        # This ensures every node gets at least one edge after consolidation
        all_nodes_in_period = []
        logger.debug(f"Collecting nodes for SUMMARIZES edges. nodes_by_type keys: {list(nodes_by_type.keys())}")

        for node_type, result in nodes_by_type.items():
            # Skip TSDB_DATA nodes as they're temporary and will be cleaned up
            if node_type != "tsdb_data":
                node_count = len(result.nodes) if hasattr(result, "nodes") else 0
                logger.debug(f"  {node_type}: {node_count} nodes")
                if hasattr(result, "nodes"):
                    all_nodes_in_period.extend(result.nodes)
                else:
                    logger.warning(f"  {node_type} result has no 'nodes' attribute: {type(result)}")

        logger.info(f"Total nodes collected for SUMMARIZES edges: {len(all_nodes_in_period)}")

        if all_nodes_in_period:
            # Create a primary summary (TSDB or first available) to link all nodes
            primary_summary = next(
                (s for s in summaries if s.type == NodeType.TSDB_SUMMARY), summaries[0] if summaries else None
            )

            if primary_summary:
                logger.info(f"Creating edges from {primary_summary.id} to {len(all_nodes_in_period)} nodes in period")
                edges_created = self._edge_manager.create_summary_to_nodes_edges(
                    primary_summary, all_nodes_in_period, "SUMMARIZES", f"Node active during {period_label}"
                )
                logger.info(f"Created {edges_created} SUMMARIZES edges for period {period_label}")

        # Create cross-summary edges (same period relationships)
        if len(summaries) > 1:
            cross_edges = self._edge_manager.create_cross_summary_edges(summaries, period_start)
            logger.info(f"Created {cross_edges} cross-summary edges for period {period_label}")

        # Create temporal edges to previous period summaries
        for summary in summaries:
            # Extract summary type from ID
            summary_type = summary.id.split("_")[0] + "_" + summary.id.split("_")[1]
            previous_period = period_start - self._consolidation_interval
            previous_id = self._edge_manager.get_previous_summary_id(
                summary_type, previous_period.strftime("%Y%m%d_%H")
            )

            if previous_id:
                created = self._edge_manager.create_temporal_edges(summary, previous_id)
                if created:
                    logger.debug(f"Created {created} temporal edges for {summary.id}")

        # Also check if there's a next period already consolidated and link to it
        edges_to_next = self._edge_manager.update_next_period_edges(period_start, summaries)
        if edges_to_next > 0:
            logger.info(f"Created {edges_to_next} edges to next period summaries")

    def _find_oldest_unconsolidated_period(self) -> Optional[datetime]:
        """Find the oldest data that needs consolidation."""
        try:
            from ciris_engine.logic.persistence.db.core import get_db_connection

            with get_db_connection(db_path=self.db_path) as conn:
                cursor = conn.cursor()

                # Check for oldest TSDB data
                cursor.execute(
                    """
                    SELECT MIN(created_at) as oldest
                    FROM graph_nodes
                    WHERE node_type = 'tsdb_data'
                """
                )
                row = cursor.fetchone()

                if row and row["oldest"]:
                    return datetime.fromisoformat(row["oldest"].replace("Z", UTC_TIMEZONE_SUFFIX))

                # Check for oldest correlation
                cursor.execute(
                    """
                    SELECT MIN(timestamp) as oldest
                    FROM service_correlations
                """
                )
                row = cursor.fetchone()

                if row and row["oldest"]:
                    return datetime.fromisoformat(row["oldest"].replace("Z", UTC_TIMEZONE_SUFFIX))

        except Exception as e:
            logger.error(f"Failed to find oldest data: {e}")

        return None

    def _cleanup_old_data(self) -> int:
        """
        Clean up old consolidated data that has been successfully summarized.

        IMPORTANT: This method NEVER touches the audit_log table.
        Audit entries are preserved forever for absolute reputability.
        Only graph node representations are cleaned up.
        """
        try:
            import sqlite3

            from ciris_engine.logic.config import get_sqlite_db_full_path
            from ciris_engine.logic.services.graph.tsdb_consolidation.cleanup_helpers import (
                cleanup_audit_summary,
                cleanup_trace_summary,
                cleanup_tsdb_summary,
            )
            from ciris_engine.logic.services.graph.tsdb_consolidation.date_calculation_helpers import (
                get_retention_cutoff_date,
            )
            from ciris_engine.logic.services.graph.tsdb_consolidation.db_query_helpers import (
                query_expired_summaries,
            )

            logger.info("Starting cleanup of consolidated graph data (audit_log untouched)")

            # Connect to database
            db_path = self.db_path or get_sqlite_db_full_path()
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()

            # Find all summaries older than retention period
            retention_cutoff = get_retention_cutoff_date(self._now(), int(self._raw_retention.total_seconds() / 3600))
            summaries = query_expired_summaries(cursor, retention_cutoff)

            total_deleted = 0

            # Process each expired summary
            for node_id, node_type, attrs_json in summaries:
                deleted = 0

                if node_type == "tsdb_summary":
                    deleted = cleanup_tsdb_summary(cursor, node_id, attrs_json)
                elif node_type == "audit_summary":
                    deleted = cleanup_audit_summary(cursor, node_id, attrs_json)
                elif node_type == "trace_summary":
                    deleted = cleanup_trace_summary(cursor, node_id, attrs_json)

                total_deleted += deleted

            # Commit changes
            if total_deleted > 0:
                conn.commit()
                logger.info(f"Cleanup complete: deleted {total_deleted} total records")
            else:
                logger.info("No data to cleanup")

            conn.close()
            return total_deleted

        except Exception as e:
            logger.error(f"Error during cleanup: {e}", exc_info=True)
            return 0

    async def is_healthy(self) -> bool:
        """Check if the service is healthy."""
        return (
            self._running
            and self._memory_bus is not None
            and (self._consolidation_task is None or not self._consolidation_task.done())
            and (self._extensive_task is None or not self._extensive_task.done())
            and (self._profound_task is None or not self._profound_task.done())
        )

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
                "basic_task_running": (
                    1.0 if (self._consolidation_task and not self._consolidation_task.done()) else 0.0
                ),
                "extensive_task_running": 1.0 if (self._extensive_task and not self._extensive_task.done()) else 0.0,
                "profound_task_running": 1.0 if (self._profound_task and not self._profound_task.done()) else 0.0,
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
        """Check if a period has already been consolidated."""
        try:
            # Query for existing TSDB summary for this exact period
            # Use direct DB query since MemoryQuery doesn't support field conditions
            from ciris_engine.logic.persistence.db.core import get_db_connection

            conn = get_db_connection(db_path=self.db_path)
            cursor = conn.cursor()

            # Query for TSDB summaries with matching period
            cursor.execute(
                """
                SELECT COUNT(*) FROM graph_nodes
                WHERE node_type = ?
                AND json_extract(attributes_json, '$.period_start') = ?
                AND json_extract(attributes_json, '$.period_end') = ?
            """,
                (NodeType.TSDB_SUMMARY.value, period_start.isoformat(), period_end.isoformat()),
            )

            result = cursor.fetchone()
            count = int(result[0]) if result else 0
            conn.close()

            return count > 0
        except Exception as e:
            logger.error(f"Error checking if period consolidated: {e}")
            return False

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

            # Check if SUMMARIZES edges already exist
            from ciris_engine.logic.persistence.db.core import get_db_connection

            with get_db_connection(db_path=self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT COUNT(*) as count
                    FROM graph_edges
                    WHERE source_node_id = ?
                      AND relationship = 'SUMMARIZES'
                """,
                    (summary_id,),
                )

                edge_count = cursor.fetchone()["count"]

                if edge_count > 0:
                    logger.debug(f"Period {period_label} already has {edge_count} SUMMARIZES edges")
                    return

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
        """Get the summary for a specific period."""
        try:
            # Use direct DB query since MemoryQuery doesn't support field conditions
            from ciris_engine.logic.persistence.db.core import get_db_connection

            conn = get_db_connection(db_path=self.db_path)
            cursor = conn.cursor()

            # Query for TSDB summaries with matching period
            cursor.execute(
                """
                SELECT attributes_json FROM graph_nodes
                WHERE node_type = ?
                AND json_extract(attributes_json, '$.period_start') = ?
                AND json_extract(attributes_json, '$.period_end') = ?
                LIMIT 1
            """,
                (NodeType.TSDB_SUMMARY.value, period_start.isoformat(), period_end.isoformat()),
            )

            row = cursor.fetchone()
            conn.close()

            if row:
                # Parse the node data
                import json

                node_data = json.loads(row[0])
                attrs = node_data.get("attributes", {})
                # Return the summary data as a typed schema
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
            return None
        except Exception as e:
            logger.error(f"Error getting summary for period: {e}")
            return None

    def get_service_type(self) -> ServiceType:
        """Get the service type."""
        return ServiceType.TELEMETRY

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
            # Check if node has consent_stream and expires_at
            if hasattr(node, "consent_stream") and hasattr(node, "expires_at"):
                # Check if TEMPORARY and expired
                if node.consent_stream == ConsentStream.TEMPORARY and node.expires_at:
                    if period_end > node.expires_at:
                        # Node has expired - anonymize it
                        old_id = node.id

                        # Generate anonymized ID based on hash of original ID
                        import hashlib

                        id_hash = hashlib.sha256(old_id.encode()).hexdigest()[:8]

                        # Rename based on stream type
                        if node.consent_stream == ConsentStream.TEMPORARY:
                            new_id = f"temporary_user_{id_hash}"
                        else:
                            new_id = f"anonymous_user_{id_hash}"

                        logger.info(f"Anonymizing expired node: {old_id} -> {new_id}")

                        # Update the node ID
                        node.id = new_id

                        # Clear any PII from attributes if present
                        if hasattr(node, "attributes") and isinstance(node.attributes, dict):
                            # Remove PII fields
                            pii_fields = ["email", "name", "phone", "address", "ip_address"]
                            for field in pii_fields:
                                if field in node.attributes:
                                    del node.attributes[field]

                            # Add anonymization metadata
                            node.attributes["anonymized_at"] = period_end.isoformat()
                            node.attributes["original_stream"] = node.consent_stream

                        # Update in memory bus if available
                        if self._memory_bus:
                            try:
                                # Update the node in the graph using memorize
                                status = await self._memory_bus.memorize(node, handler_name="tsdb_consolidation")
                                if status.status == MemoryOpStatus.SUCCESS:
                                    logger.info(f"Successfully anonymized node {old_id}")
                                else:
                                    logger.warning(f"Failed to update anonymized node: {status.reason}")
                            except Exception as e:
                                logger.error(f"Error updating anonymized node: {e}")

    def _get_actions(self) -> List[str]:
        """Get list of actions this service can handle."""
        # Graph services typically don't handle actions through buses
        return []

    async def _run_extensive_consolidation(self) -> None:
        """
        Run extensive consolidation - consolidates basic summaries from the past week.
        This reduces data volume by creating daily summaries (4 basic summaries → 1 daily summary).
        Creates 7 daily summaries for each node type.
        """
        from ciris_engine.logic.persistence.db.core import get_db_connection
        from ciris_engine.logic.services.graph.tsdb_consolidation.aggregation_helpers import (
            aggregate_action_counts,
            aggregate_metric_stats,
            aggregate_resource_usage,
            group_summaries_by_day,
            parse_summary_attributes,
        )
        from ciris_engine.logic.services.graph.tsdb_consolidation.date_calculation_helpers import (
            calculate_week_period,
        )
        from ciris_engine.logic.services.graph.tsdb_consolidation.extensive_helpers import (
            check_daily_summary_exists,
            create_daily_summary_attributes,
            create_daily_summary_node,
            maintain_temporal_chain_to_daily,
            query_basic_summaries_in_period,
        )
        from ciris_engine.schemas.services.operations import MemoryOpStatus

        consolidation_start = self._now()
        total_basic_summaries = 0
        daily_summaries_created = 0

        try:
            logger.info("=" * 60)
            logger.info("Starting extensive (weekly) consolidation")
            logger.info(f"Started at: {consolidation_start.isoformat()}")

            now = self._now()

            # Calculate the previous week period using helper
            period_start, period_end = calculate_week_period(now)

            week_start = period_start.date()
            week_end = period_end.date()

            logger.info(f"Consolidating week: {week_start} to {week_end}")
            logger.info(f"Period: {period_start.isoformat()} to {period_end.isoformat()}")

            # Process summaries
            with get_db_connection(db_path=self.db_path) as conn:
                cursor = conn.cursor()

                # Get all summary types to consolidate
                summary_types = [
                    "tsdb_summary",
                    "audit_summary",
                    "trace_summary",
                    "conversation_summary",
                    "task_summary",
                ]

                for summary_type in summary_types:
                    # Query basic summaries using helper
                    summaries = query_basic_summaries_in_period(cursor, summary_type, period_start, period_end)

                    if not summaries:
                        logger.info(f"No {summary_type} summaries found for consolidation")
                        continue

                    logger.info(f"Found {len(summaries)} {summary_type} summaries to consolidate")
                    total_basic_summaries += len(summaries)

                    # Group summaries by day using helper
                    summaries_by_day = group_summaries_by_day(summaries)

                    # Create daily summary for each day
                    for day, day_summaries in summaries_by_day.items():
                        if len(day_summaries) == 0:
                            continue

                        # Convert date to datetime for helpers
                        day_datetime = datetime.combine(day, datetime.min.time(), tzinfo=timezone.utc)

                        # Generate daily node ID
                        daily_node_id = f"{summary_type}_daily_{day.strftime('%Y%m%d')}"

                        # Check if already exists using helper
                        if check_daily_summary_exists(cursor, daily_node_id):
                            logger.debug(f"Daily summary {daily_node_id} already exists, skipping")
                            continue

                        # Parse summary attributes using helper
                        summary_attrs_list = parse_summary_attributes(day_summaries)

                        # Aggregate metrics, resources, and actions using helpers
                        daily_metrics = aggregate_metric_stats(summary_attrs_list)
                        daily_resources = aggregate_resource_usage(summary_attrs_list)
                        daily_action_counts = aggregate_action_counts(summary_attrs_list)

                        # Create daily summary attributes using helper
                        daily_attrs = create_daily_summary_attributes(
                            summary_type,
                            day_datetime,
                            day_summaries,
                            daily_metrics,
                            daily_resources,
                            daily_action_counts,
                        )

                        # Create daily summary node using helper
                        daily_summary = create_daily_summary_node(summary_type, day_datetime, daily_attrs, now)

                        # Store in memory
                        if self._memory_bus:
                            result = await self._memory_bus.memorize(daily_summary, handler_name="tsdb_consolidation")
                            if result.status == MemoryOpStatus.OK:
                                daily_summaries_created += 1
                                logger.info(
                                    f"Created daily summary {daily_node_id} from {len(day_summaries)} basic summaries"
                                )

                # Final summary
                total_duration = (self._now() - consolidation_start).total_seconds()
                logger.info(f"Extensive consolidation complete in {total_duration:.2f}s:")
                logger.info(f"  - Basic summaries processed: {total_basic_summaries}")
                logger.info(f"  - Daily summaries created: {daily_summaries_created}")
                if total_basic_summaries > 0:
                    compression_ratio = total_basic_summaries / max(daily_summaries_created, 1)
                    logger.info(f"  - Compression ratio: {compression_ratio:.1f}:1")
                logger.info("=" * 60)

                # Maintain temporal chain using helper
                if daily_summaries_created > 0:
                    edges_created = maintain_temporal_chain_to_daily(cursor, period_start)
                    if edges_created > 0:
                        logger.info(f"Created {edges_created} temporal chain edges")

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
        """
        Run profound consolidation - compresses existing daily summaries in-place.
        Target: Configurable MB per day of data retention.

        This process compresses daily summaries to meet storage targets without
        creating new nodes. Future versions will handle multimedia compression.
        """
        from ciris_engine.logic.persistence.db.core import get_db_connection
        from ciris_engine.logic.services.graph.tsdb_consolidation.date_calculation_helpers import (
            calculate_month_period,
        )
        from ciris_engine.logic.services.graph.tsdb_consolidation.profound_helpers import (
            calculate_storage_metrics,
            cleanup_old_basic_summaries,
            compress_and_update_summaries,
            query_extensive_summaries_in_month,
        )

        from .compressor import SummaryCompressor

        consolidation_start = self._now()
        total_daily_summaries = 0
        summaries_compressed = 0
        storage_before_mb = 0.0
        storage_after_mb = 0.0

        try:
            logger.info("=" * 60)
            logger.info("Starting profound (monthly) consolidation")
            logger.info(f"Started at: {consolidation_start.isoformat()}")

            now = self._now()

            # Calculate the previous month period using helper
            month_start, month_end = calculate_month_period(now)

            # Initialize compressor
            compressor = SummaryCompressor(self._profound_target_mb_per_day)

            # Query and process summaries
            with get_db_connection(db_path=self.db_path) as conn:
                cursor = conn.cursor()

                # Query all extensive summaries from the month using helper
                summaries = query_extensive_summaries_in_month(cursor, month_start, month_end)
                total_daily_summaries = len(summaries)

                if len(summaries) < 7:  # Less than a week's worth
                    logger.info(
                        f"Not enough daily summaries for profound consolidation (found {len(summaries)}, need at least 7)"
                    )
                    return

                logger.info(f"Found {total_daily_summaries} daily summaries to compress")

                # Calculate current storage using helper
                days_in_period = (month_end - month_start).days + 1
                current_daily_mb, summary_attrs_list = calculate_storage_metrics(
                    cursor, month_start, month_end, compressor
                )
                storage_before_mb = float(current_daily_mb * days_in_period)
                logger.info(f"Current storage: {current_daily_mb:.2f}MB/day ({storage_before_mb:.2f}MB total)")
                logger.info(f"Target: {self._profound_target_mb_per_day}MB/day")

                # Check if compression is needed
                if not compressor.needs_compression(summary_attrs_list, days_in_period):
                    logger.info("Daily summaries already meet storage target, skipping compression")
                    return

                # Compress summaries using helper
                compressed_count, total_reduction = compress_and_update_summaries(cursor, summaries, compressor, now)
                summaries_compressed = compressed_count

                conn.commit()

                # Calculate new storage using helper
                new_daily_mb, _ = calculate_storage_metrics(cursor, month_start, month_end, compressor)
                storage_after_mb = new_daily_mb * days_in_period
                avg_reduction = total_reduction / compressed_count if compressed_count > 0 else 0

                # Final summary
                total_duration = (self._now() - consolidation_start).total_seconds()
                logger.info(f"Profound consolidation complete in {total_duration:.2f}s:")
                logger.info(f"  - Daily summaries processed: {total_daily_summaries}")
                logger.info(f"  - Summaries compressed: {summaries_compressed}")
                logger.info(f"  - Average compression: {avg_reduction:.1%}")
                logger.info(
                    f"  - Storage before: {storage_before_mb:.2f}MB ({storage_before_mb/days_in_period:.2f}MB/day)"
                )
                logger.info(f"  - Storage after: {storage_after_mb:.2f}MB ({new_daily_mb:.2f}MB/day)")
                if storage_before_mb > 0:
                    logger.info(
                        f"  - Total reduction: {((storage_before_mb - storage_after_mb) / storage_before_mb * 100):.1f}%"
                    )

                # Clean up old basic summaries using helper
                cleanup_cutoff = now - timedelta(days=30)
                deleted = cleanup_old_basic_summaries(cursor, cleanup_cutoff)

                if deleted > 0:
                    logger.info(f"Cleaned up {deleted} old basic summaries")
                    conn.commit()

            self._last_profound_consolidation = now

        except Exception as e:
            logger.error(f"Profound consolidation failed: {e}", exc_info=True)
