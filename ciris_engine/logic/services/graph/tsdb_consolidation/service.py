"""
TSDB Consolidation Service - Main service class.

This service runs every 6 hours to consolidate telemetry and memory data
into permanent summary records with proper edge connections.
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Dict, List, Optional, Union
from uuid import uuid4

if TYPE_CHECKING:
    from ciris_engine.logic.registries.base import ServiceRegistry

from ciris_engine.constants import UTC_TIMEZONE_SUFFIX
from ciris_engine.logic.buses.memory_bus import MemoryBus
from ciris_engine.logic.services.graph.base import BaseGraphService
from ciris_engine.protocols.services.lifecycle.time import TimeServiceProtocol
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
    ) -> None:
        """
        Initialize the consolidation service.

        Args:
            memory_bus: Bus for memory operations
            time_service: Time service for consistent timestamps
            consolidation_interval_hours: How often to run (default: 6)
            raw_retention_hours: How long to keep raw data (default: 24)
        """
        super().__init__(memory_bus=memory_bus, time_service=time_service)
        self.service_name = "TSDBConsolidationService"

        # Initialize components
        self._period_manager = PeriodManager(consolidation_interval_hours)
        self._query_manager = QueryManager(memory_bus)
        self._edge_manager = EdgeManager()

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
        self._consolidation_task: Optional[asyncio.Task] = None
        self._extensive_task: Optional[asyncio.Task] = None
        self._profound_task: Optional[asyncio.Task] = None
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

        super().start()
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
                if asyncio.current_task() and asyncio.current_task().cancelled():
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

        super().stop()
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
                    await self._run_profound_consolidation()

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

        # 2. Create summaries

        # Store converted correlation objects for reuse in edge creation
        converted_correlations: Dict[
            str, Union[List[MetricCorrelationData], List[ServiceInteractionData], List[TraceSpanData]]
        ] = {}
        converted_tasks: List[TaskCorrelationData] = []  # Store converted tasks separately

        # Metrics summary (TSDB data + correlations)
        tsdb_nodes = nodes_by_type.get(
            "tsdb_data", TSDBNodeQueryResult(nodes=[], period_start=period_start, period_end=period_end)
        ).nodes
        metric_correlations = correlations.metric_correlations

        converted_correlations["metric_datapoint"] = metric_correlations

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
            converted_correlations["service_interaction"] = service_interactions

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
            converted_correlations["trace_span"] = trace_spans

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
            if summary.type == NodeType.TSDB_SUMMARY:
                # Get edges from metrics consolidator
                tsdb_nodes = nodes_by_type.get(
                    "tsdb_data", TSDBNodeQueryResult(nodes=[], period_start=period_start, period_end=period_start)
                ).nodes
                metric_correlations = correlations.get("metric_datapoint", [])
                edges = self._metrics_consolidator.get_edges(summary, tsdb_nodes, metric_correlations)
                all_edges.extend(edges)

            elif summary.type == NodeType.CONVERSATION_SUMMARY:
                # Get edges from conversation consolidator
                service_interactions = correlations.get("service_interaction", [])
                edges = self._conversation_consolidator.get_edges(summary, service_interactions)
                all_edges.extend(edges)

            elif summary.type == NodeType.TRACE_SUMMARY:
                # Get edges from trace consolidator
                trace_spans = correlations.get("trace_span", [])
                edges = self._trace_consolidator.get_edges(summary, trace_spans)
                all_edges.extend(edges)

            elif summary.type == NodeType.AUDIT_SUMMARY:
                # Get edges from audit consolidator
                audit_nodes = nodes_by_type.get(
                    "audit_entry", TSDBNodeQueryResult(nodes=[], period_start=period_start, period_end=period_start)
                ).nodes
                edges = self._audit_consolidator.get_edges(summary, audit_nodes)
                all_edges.extend(edges)

            elif summary.type == NodeType.TASK_SUMMARY:
                # Get edges from task consolidator
                edges = self._task_consolidator.get_edges(summary, tasks)
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

            with get_db_connection() as conn:
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
            import json
            import sqlite3

            logger.info("Starting cleanup of consolidated graph data (audit_log untouched)")

            # Connect to database
            from ciris_engine.logic.config import get_sqlite_db_full_path

            db_path = get_sqlite_db_full_path()
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()

            # Find all summaries that represent periods older than the retention period
            retention_cutoff = self._now() - self._raw_retention

            cursor.execute(
                """
                SELECT node_id, node_type, attributes_json
                FROM graph_nodes
                WHERE node_type LIKE '%_summary'
                  AND json_extract(attributes_json, '$.period_end') < ?
                ORDER BY json_extract(attributes_json, '$.period_end')
            """,
                (retention_cutoff.isoformat(),),
            )

            summaries = cursor.fetchall()
            total_deleted = 0

            for node_id, node_type, attrs_json in summaries:
                attrs = json.loads(attrs_json) if attrs_json else {}
                period_start = attrs.get("period_start")
                period_end = attrs.get("period_end")

                if not period_start or not period_end:
                    continue

                # Validate and delete based on node type
                if node_type == "tsdb_summary":
                    claimed_count = attrs.get("source_node_count", 0)

                    # Count actual nodes
                    cursor.execute(
                        """
                        SELECT COUNT(*) FROM graph_nodes
                        WHERE node_type = 'tsdb_data'
                          AND datetime(created_at) >= datetime(?)
                          AND datetime(created_at) < datetime(?)
                    """,
                        (period_start, period_end),
                    )
                    actual_count = cursor.fetchone()[0]

                    if claimed_count == actual_count and actual_count > 0:
                        # Delete the nodes
                        cursor.execute(
                            """
                            DELETE FROM graph_nodes
                            WHERE node_type = 'tsdb_data'
                              AND datetime(created_at) >= datetime(?)
                              AND datetime(created_at) < datetime(?)
                        """,
                            (period_start, period_end),
                        )
                        deleted = cursor.rowcount
                        if deleted > 0:
                            logger.info(f"Deleted {deleted} tsdb_data nodes for period {node_id}")
                            total_deleted += deleted

                elif node_type == "audit_summary":
                    # Graph audit nodes can be cleaned up after consolidation
                    # The SQLite audit_log table is what's preserved forever
                    claimed_count = attrs.get("source_node_count", 0)

                    # Count actual audit_entry nodes
                    cursor.execute(
                        """
                        SELECT COUNT(*) FROM graph_nodes
                        WHERE node_type = 'audit_entry'
                          AND datetime(created_at) >= datetime(?)
                          AND datetime(created_at) < datetime(?)
                    """,
                        (period_start, period_end),
                    )
                    actual_count = cursor.fetchone()[0]

                    if claimed_count == actual_count and actual_count > 0:
                        # Delete the graph nodes (NOT the audit_log table!)
                        cursor.execute(
                            """
                            DELETE FROM graph_nodes
                            WHERE node_type = 'audit_entry'
                              AND datetime(created_at) >= datetime(?)
                              AND datetime(created_at) < datetime(?)
                        """,
                            (period_start, period_end),
                        )
                        deleted = cursor.rowcount
                        if deleted > 0:
                            logger.info(
                                f"Deleted {deleted} audit_entry graph nodes for period {node_id} (audit_log table preserved)"
                            )
                            total_deleted += deleted

                elif node_type == "trace_summary":
                    claimed_count = attrs.get("source_correlation_count", 0)

                    # Count actual correlations
                    cursor.execute(
                        """
                        SELECT COUNT(*) FROM service_correlations
                        WHERE datetime(created_at) >= datetime(?)
                          AND datetime(created_at) < datetime(?)
                    """,
                        (period_start, period_end),
                    )
                    actual_count = cursor.fetchone()[0]

                    # Only delete if counts match exactly
                    if claimed_count == actual_count and actual_count > 0:
                        cursor.execute(
                            """
                            DELETE FROM service_correlations
                            WHERE datetime(created_at) >= datetime(?)
                              AND datetime(created_at) < datetime(?)
                        """,
                            (period_start, period_end),
                        )
                        deleted = cursor.rowcount
                        if deleted > 0:
                            logger.info(f"Deleted {deleted} correlations for period {node_id}")
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

    def is_healthy(self) -> bool:
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
            metadata={
                "consolidation_interval_hours": self._consolidation_interval.total_seconds() / 3600,
                "raw_retention_hours": self._raw_retention.total_seconds() / 3600,
            },
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

            conn = get_db_connection()
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

            with get_db_connection() as conn:
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

            conn = get_db_connection()
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

    async def _run_extensive_consolidation(self) -> None:
        """
        Run extensive consolidation - consolidates basic summaries from the past week.
        This reduces data volume by creating daily summaries (4 basic summaries → 1 daily summary).
        Creates 7 daily summaries for each node type.
        """
        consolidation_start = self._now()
        total_basic_summaries = 0
        daily_summaries_created = 0

        try:
            logger.info("=" * 60)
            logger.info("Starting extensive (weekly) consolidation")
            logger.info(f"Started at: {consolidation_start.isoformat()}")

            now = self._now()
            # Calculate the previous Monday-Sunday period
            # If today is Monday, we want last Monday to yesterday (Sunday)
            days_since_monday = now.weekday()  # Monday = 0, Sunday = 6
            if days_since_monday == 0:
                # It's Monday, so we want last week
                week_start = now.date() - timedelta(days=7)
                week_end = now.date() - timedelta(days=1)
            else:
                # Any other day, find the most recent Monday
                week_start = now.date() - timedelta(days=days_since_monday)
                week_end = week_start + timedelta(days=6)

            # Convert to datetime at start/end of day
            period_start = datetime.combine(week_start, datetime.min.time(), tzinfo=timezone.utc)
            period_end = datetime.combine(week_end, datetime.max.time(), tzinfo=timezone.utc)

            logger.info(f"Consolidating week: {week_start} to {week_end}")
            logger.info(f"Period: {period_start.isoformat()} to {period_end.isoformat()}")

            # Query all basic summaries from the past week
            import json
            from collections import defaultdict

            from ciris_engine.logic.persistence.db.core import get_db_connection

            with get_db_connection() as conn:
                cursor = conn.cursor()

                # Get all summary types to consolidate
                summary_types = [
                    "tsdb_summary",
                    "audit_summary",
                    "trace_summary",
                    "conversation_summary",
                    "task_summary",
                ]

                daily_summaries_created = 0

                for summary_type in summary_types:
                    # Get all summaries of this type from the calendar week
                    cursor.execute(
                        """
                        SELECT node_id, attributes_json,
                               json_extract(attributes_json, '$.period_start') as period_start
                        FROM graph_nodes
                        WHERE node_type = ?
                          AND datetime(created_at) >= datetime(?)
                          AND datetime(created_at) <= datetime(?)
                          AND (json_extract(attributes_json, '$.consolidation_level') IS NULL
                               OR json_extract(attributes_json, '$.consolidation_level') = 'basic')
                        ORDER BY period_start
                    """,
                        (summary_type, period_start.isoformat(), period_end.isoformat()),
                    )

                    summaries = cursor.fetchall()

                    if not summaries:
                        logger.info(f"No {summary_type} summaries found for consolidation")
                        continue

                    logger.info(f"Found {len(summaries)} {summary_type} summaries to consolidate")
                    total_basic_summaries += len(summaries)

                    # Group summaries by day
                    summaries_by_day = defaultdict(list)
                    for node_id, attrs_json, period_start_str in summaries:
                        if period_start_str:
                            period_dt = datetime.fromisoformat(period_start_str.replace("Z", UTC_TIMEZONE_SUFFIX))
                            day_key = period_dt.date()
                            summaries_by_day[day_key].append((node_id, attrs_json))

                    # Create daily summary for each day
                    for day, day_summaries in summaries_by_day.items():
                        if len(day_summaries) == 0:
                            continue

                        # Aggregate metrics for this day
                        daily_metrics = {}
                        daily_tokens = 0
                        daily_cost_cents = 0
                        daily_carbon_grams = 0
                        daily_energy_kwh = 0
                        daily_action_counts = {}
                        daily_error_count = 0
                        source_summary_ids = []

                        for node_id, attrs_json in day_summaries:
                            attrs = json.loads(attrs_json) if attrs_json else {}
                            source_summary_ids.append(node_id)

                            # Aggregate based on summary type
                            if summary_type == "tsdb_summary":
                                # Aggregate metrics
                                for metric, stats in attrs.get("metrics", {}).items():
                                    if metric not in daily_metrics:
                                        daily_metrics[metric] = {
                                            "count": 0,
                                            "sum": 0,
                                            "min": float("inf"),
                                            "max": float("-inf"),
                                        }

                                    # Handle both old format (single value) and new format (stats dict)
                                    if isinstance(stats, dict):
                                        daily_metrics[metric]["count"] += stats.get("count", 1)
                                        daily_metrics[metric]["sum"] += stats.get("sum", 0)
                                        daily_metrics[metric]["min"] = min(
                                            daily_metrics[metric]["min"], stats.get("min", float("inf"))
                                        )
                                        daily_metrics[metric]["max"] = max(
                                            daily_metrics[metric]["max"], stats.get("max", float("-inf"))
                                        )
                                    else:
                                        # Old format - single value
                                        daily_metrics[metric]["count"] += 1
                                        daily_metrics[metric]["sum"] += stats
                                        daily_metrics[metric]["min"] = min(daily_metrics[metric]["min"], stats)
                                        daily_metrics[metric]["max"] = max(daily_metrics[metric]["max"], stats)

                                # Aggregate resource usage
                                daily_tokens += attrs.get("total_tokens", 0)
                                daily_cost_cents += attrs.get("total_cost_cents", 0)
                                daily_carbon_grams += attrs.get("total_carbon_grams", 0)
                                daily_energy_kwh += attrs.get("total_energy_kwh", 0)
                                daily_error_count += attrs.get("error_count", 0)

                                # Aggregate action counts
                                for action, count in attrs.get("action_counts", {}).items():
                                    if action not in daily_action_counts:
                                        daily_action_counts[action] = 0
                                    daily_action_counts[action] += count

                        # Calculate averages for metrics
                        for metric, stats in daily_metrics.items():
                            if stats["count"] > 0:
                                stats["avg"] = stats["sum"] / stats["count"]
                            else:
                                stats["avg"] = 0
                            # Clean up infinity values
                            if stats["min"] == float("inf"):
                                stats["min"] = 0
                            if stats["max"] == float("-inf"):
                                stats["max"] = 0

                        # Check if daily summary already exists
                        daily_node_id = f"{summary_type}_daily_{day.strftime('%Y%m%d')}"
                        cursor.execute(
                            """
                            SELECT node_id FROM graph_nodes
                            WHERE node_id = ?
                        """,
                            (daily_node_id,),
                        )

                        if cursor.fetchone():
                            logger.debug(f"Daily summary {daily_node_id} already exists, skipping")
                            continue

                        # Create daily summary node
                        day_start = datetime.combine(day, datetime.min.time(), tzinfo=timezone.utc)
                        day_end = datetime.combine(day, datetime.max.time(), tzinfo=timezone.utc)

                        daily_attrs = {
                            "summary_type": summary_type,
                            "consolidation_level": "extensive",
                            "period_start": day_start.isoformat(),
                            "period_end": day_end.isoformat(),
                            "period_label": day.strftime("%Y-%m-%d"),
                            "source_summary_count": len(day_summaries),
                            "source_summary_ids": source_summary_ids[:10],  # Keep first 10 for reference
                        }

                        # Add type-specific attributes
                        if summary_type == "tsdb_summary":
                            daily_attrs.update(
                                {
                                    "metrics": daily_metrics,
                                    "total_tokens": daily_tokens,
                                    "total_cost_cents": daily_cost_cents,
                                    "total_carbon_grams": daily_carbon_grams,
                                    "total_energy_kwh": daily_energy_kwh,
                                    "action_counts": daily_action_counts,
                                    "error_count": daily_error_count,
                                    "success_rate": (
                                        1.0 - (daily_error_count / sum(daily_action_counts.values()))
                                        if sum(daily_action_counts.values()) > 0
                                        else 1.0
                                    ),
                                }
                            )

                        # Create the node
                        from ciris_engine.schemas.services.graph_core import GraphNode, GraphScope, NodeType

                        node_type_map = {
                            "tsdb_summary": NodeType.TSDB_SUMMARY,
                            "audit_summary": NodeType.AUDIT_SUMMARY,
                            "trace_summary": NodeType.TRACE_SUMMARY,
                            "conversation_summary": NodeType.CONVERSATION_SUMMARY,
                            "task_summary": NodeType.TASK_SUMMARY,
                        }

                        daily_summary = GraphNode(
                            id=daily_node_id,
                            type=node_type_map[summary_type],
                            scope=GraphScope.LOCAL,
                            attributes=daily_attrs,
                            updated_at=now,
                            updated_by="tsdb_consolidation_extensive",
                        )

                        # Store in memory
                        if self._memory_bus:
                            result = await self._memory_bus.memorize(daily_summary, handler_name="tsdb_consolidation")
                            if result.status == MemoryOpStatus.OK:
                                daily_summaries_created += 1
                                logger.info(
                                    f"Created daily summary {daily_node_id} from {len(day_summaries)} basic summaries"
                                )

                                # Don't create edges to source summaries - they'll be deleted!
                                # We'll create edges after all daily summaries are created

                # Final summary
                total_duration = (self._now() - consolidation_start).total_seconds()
                logger.info(f"Extensive consolidation complete in {total_duration:.2f}s:")
                logger.info(f"  - Basic summaries processed: {total_basic_summaries}")
                logger.info(f"  - Daily summaries created: {daily_summaries_created}")
                if total_basic_summaries > 0:
                    compression_ratio = total_basic_summaries / max(daily_summaries_created, 1)
                    logger.info(f"  - Compression ratio: {compression_ratio:.1f}:1")
                logger.info("=" * 60)

                # CRITICAL: Maintain temporal chain between 6-hour and daily summaries
                # Find the last 6-hour summary before the first daily summary
                if daily_summaries_created > 0 and self._memory_bus:
                    # Get the first daily summary we created
                    first_day = period_start

                    # Find last 6-hour summary before the daily summaries start
                    last_6h_before = first_day - timedelta(hours=6)
                    last_6h_id = f"tsdb_summary_{last_6h_before.strftime('%Y%m%d_%H')}"

                    # Check if it exists
                    cursor.execute(
                        """
                        SELECT node_id FROM graph_nodes
                        WHERE node_id = ? AND node_type = 'tsdb_summary'
                        AND json_extract(attributes_json, '$.consolidation_level') = 'basic'
                    """,
                        (last_6h_id,),
                    )

                    if cursor.fetchone():
                        # Update its TEMPORAL_NEXT to point to first daily summary
                        first_daily_id = f"tsdb_summary_daily_{first_day.strftime('%Y%m%d')}"

                        # Delete self-referencing edge
                        cursor.execute(
                            """
                            DELETE FROM graph_edges
                            WHERE source_node_id = ? AND target_node_id = ?
                            AND relationship = 'TEMPORAL_NEXT'
                        """,
                            (last_6h_id, last_6h_id),
                        )

                        # Create new edge to daily summary
                        cursor.execute(
                            """
                            INSERT INTO graph_edges
                            (edge_id, source_node_id, target_node_id, scope,
                             relationship, weight, attributes_json, created_at)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                            (
                                f"edge_{uuid4().hex[:8]}",
                                last_6h_id,
                                first_daily_id,
                                "local",
                                "TEMPORAL_NEXT",
                                1.0,
                                json.dumps({"context": "6-hour to daily transition"}),
                                datetime.now(timezone.utc).isoformat(),
                            ),
                        )

                        # Also create backward edge from daily to 6-hour
                        cursor.execute(
                            """
                            INSERT INTO graph_edges
                            (edge_id, source_node_id, target_node_id, scope,
                             relationship, weight, attributes_json, created_at)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                            (
                                f"edge_{uuid4().hex[:8]}",
                                first_daily_id,
                                last_6h_id,
                                "local",
                                "TEMPORAL_PREV",
                                1.0,
                                json.dumps({"context": "Daily to 6-hour backward link"}),
                                datetime.now(timezone.utc).isoformat(),
                            ),
                        )

                        logger.info(f"Linked 6-hour summary {last_6h_id} to daily summary {first_daily_id}")

                # Now create edges between daily summaries for the whole week
                # We'll need to query all the daily summaries we just created
                if daily_summaries_created > 0:
                    cursor.execute(
                        """
                        SELECT node_id, node_type,
                               json_extract(attributes_json, '$.period_start') as period_start
                        FROM graph_nodes
                        WHERE json_extract(attributes_json, '$.consolidation_level') = 'extensive'
                          AND datetime(json_extract(attributes_json, '$.period_start')) >= datetime(?)
                          AND datetime(json_extract(attributes_json, '$.period_start')) <= datetime(?)
                        ORDER BY period_start
                    """,
                        (period_start.isoformat(), period_end.isoformat()),
                    )

                    all_daily_summaries = cursor.fetchall()

                    # Group by date and create edges
                    from collections import defaultdict

                    summaries_by_date = defaultdict(list)

                    for node_id, node_type, period_start_str in all_daily_summaries:
                        if period_start_str:
                            period_dt = datetime.fromisoformat(period_start_str.replace("Z", UTC_TIMEZONE_SUFFIX))
                            date_key = period_dt.date()

                            # Create a minimal GraphNode for edge creation
                            node = GraphNode(
                                id=node_id,
                                type=node_type_map.get(node_type, NodeType.TSDB_SUMMARY),
                                scope=GraphScope.LOCAL,
                                attributes={},
                                updated_at=datetime.now(timezone.utc),
                                updated_by="tsdb_consolidation",
                            )
                            summaries_by_date[date_key].append(node)

                    # Create edges for each day
                    for date_key, day_summaries in summaries_by_date.items():
                        if len(day_summaries) > 1:
                            await self._create_daily_summary_edges(
                                day_summaries, datetime.combine(date_key, datetime.min.time(), tzinfo=timezone.utc)
                            )

            self._last_extensive_consolidation = now

        except Exception as e:
            logger.error(f"Extensive consolidation failed: {e}", exc_info=True)

    async def _create_daily_summary_edges(self, summaries: List[GraphNode], date: datetime) -> None:
        """
        Create edges between daily summaries:
        - Previous/next day edges for temporal navigation
        - Cross-type edges for same day (e.g., tsdb_daily → audit_daily)

        Args:
            summaries: List of daily summary nodes
            date: The date these summaries represent
        """
        try:
            # Create same-day edges using EdgeManager
            edges_created = self._edge_manager.create_cross_summary_edges(summaries, date)
            logger.info(f"Created {edges_created} same-day edges for {date}")

            # Create temporal edges to previous day's summaries
            for summary in summaries:
                # Extract summary type from ID (e.g., "tsdb_summary" from "tsdb_summary_daily_20250714")
                parts = summary.id.split("_")
                if len(parts) >= 3 and parts[2] == "daily":
                    summary_type = f"{parts[0]}_{parts[1]}_daily"
                    previous_date = date - timedelta(days=1)
                    previous_id = f"{summary_type}_{previous_date.strftime('%Y%m%d')}"

                    # Check if previous day's summary exists
                    previous_exists = self._edge_manager.get_previous_summary_id(
                        summary_type, previous_date.strftime("%Y%m%d")
                    )

                    if previous_exists:
                        temporal_edges = self._edge_manager.create_temporal_edges(summary, previous_id)
                        logger.info(f"Created {temporal_edges} temporal edges for {summary.id}")

                # For the first daily summary, it should point to itself (marking as latest)
                # unless there's a 6-hour summary to link to
                first_daily_summary = summaries[0] if summaries else None
                if first_daily_summary and "daily" in first_daily_summary.id:
                    # Check if it already has a TEMPORAL_PREV edge
                    from ciris_engine.logic.persistence.db.core import get_db_connection

                    with get_db_connection() as conn:
                        cursor = conn.cursor()
                        cursor.execute(
                            """
                            SELECT COUNT(*) as count FROM graph_edges
                            WHERE source_node_id = ? AND relationship = 'TEMPORAL_PREV'
                        """,
                            (first_daily_summary.id,),
                        )

                        has_prev = cursor.fetchone()["count"] > 0

                        if not has_prev:
                            # No previous link, so mark as latest by pointing to itself
                            temporal_edges = self._edge_manager.create_temporal_edges(first_daily_summary, None)
                            logger.info(
                                f"Created self-referencing edge for first daily summary {first_daily_summary.id}"
                            )

        except Exception as e:
            logger.error(f"Failed to create daily summary edges: {e}", exc_info=True)

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
        consolidation_start = self._now()
        total_daily_summaries = 0
        summaries_compressed = 0
        storage_before_mb = 0
        storage_after_mb = 0

        try:
            logger.info("=" * 60)
            logger.info("Starting profound (monthly) consolidation")
            logger.info(f"Started at: {consolidation_start.isoformat()}")

            now = self._now()
            # Calculate the previous month period
            if now.month == 1:
                # January, so previous month is December of last year
                month_start = datetime(now.year - 1, 12, 1, tzinfo=timezone.utc)
                month_end = datetime(now.year - 1, 12, 31, 23, 59, 59, tzinfo=timezone.utc)
            else:
                # Any other month
                month_start = datetime(now.year, now.month - 1, 1, tzinfo=timezone.utc)
                # Last day of previous month
                if now.month - 1 in [1, 3, 5, 7, 8, 10, 12]:
                    last_day = 31
                elif now.month - 1 == 2:
                    # February - check for leap year
                    if now.year % 4 == 0 and (now.year % 100 != 0 or now.year % 400 == 0):
                        last_day = 29
                    else:
                        last_day = 28
                else:
                    last_day = 30
                month_end = datetime(now.year, now.month - 1, last_day, 23, 59, 59, tzinfo=timezone.utc)

            # Initialize compressor
            from .compressor import SummaryCompressor

            compressor = SummaryCompressor(self._profound_target_mb_per_day)

            # Query all extensive (daily) summaries from the past month
            import json

            from ciris_engine.logic.persistence.db.core import get_db_connection

            with get_db_connection() as conn:
                cursor = conn.cursor()

                # Get all extensive summaries from the calendar month
                cursor.execute(
                    """
                    SELECT node_id, node_type, attributes_json, version
                    FROM graph_nodes
                    WHERE json_extract(attributes_json, '$.consolidation_level') = 'extensive'
                      AND datetime(json_extract(attributes_json, '$.period_start')) >= datetime(?)
                      AND datetime(json_extract(attributes_json, '$.period_start')) <= datetime(?)
                    ORDER BY node_type, json_extract(attributes_json, '$.period_start')
                """,
                    (month_start.isoformat(), month_end.isoformat()),
                )

                summaries = cursor.fetchall()
                total_daily_summaries = len(summaries)

                if len(summaries) < 7:  # Less than a week's worth
                    logger.info(
                        f"Not enough daily summaries for profound consolidation (found {len(summaries)}, need at least 7)"
                    )
                    return

                logger.info(f"Found {total_daily_summaries} daily summaries to compress")

                # Calculate current storage usage
                days_in_period = (month_end - month_start).days + 1
                summary_attrs_list = []
                for _, _, attrs_json, _ in summaries:
                    attrs_dict = json.loads(attrs_json) if attrs_json else {}
                    # Convert dict to SummaryAttributes object
                    try:
                        attrs = SummaryAttributes(**attrs_dict)
                        summary_attrs_list.append(attrs)
                    except Exception as e:
                        logger.warning(f"Failed to convert summary attributes to SummaryAttributes model: {e}")
                        # Create minimal SummaryAttributes for compatibility
                        attrs = SummaryAttributes(
                            period_start=datetime.fromisoformat(
                                attrs_dict.get("period_start", "2025-01-01T00:00:00Z").replace("Z", "+00:00")
                            ),
                            period_end=datetime.fromisoformat(
                                attrs_dict.get("period_end", "2025-01-02T00:00:00Z").replace("Z", "+00:00")
                            ),
                            consolidation_level=attrs_dict.get("consolidation_level", "basic"),
                        )
                        summary_attrs_list.append(attrs)

                current_daily_mb = compressor.estimate_daily_size(summary_attrs_list, days_in_period)
                storage_before_mb = current_daily_mb * days_in_period
                logger.info(f"Current storage: {current_daily_mb:.2f}MB/day ({storage_before_mb:.2f}MB total)")
                logger.info(f"Target: {self._profound_target_mb_per_day}MB/day")

                # Check if compression is needed
                if not compressor.needs_compression(summary_attrs_list, days_in_period):
                    logger.info("Daily summaries already meet storage target, skipping compression")
                    return

                # Compress each summary in-place
                compressed_count = 0
                total_reduction = 0.0

                for node_id, node_type, attrs_json, version in summaries:
                    attrs_dict = json.loads(attrs_json) if attrs_json else {}

                    # Convert dict to SummaryAttributes object
                    try:
                        attrs = SummaryAttributes(**attrs_dict)
                    except Exception as e:
                        logger.warning(
                            f"Failed to convert summary attributes to SummaryAttributes model for {node_id}: {e}"
                        )
                        # Create minimal SummaryAttributes for compatibility
                        attrs = SummaryAttributes(
                            period_start=datetime.fromisoformat(
                                attrs_dict.get("period_start", "2025-01-01T00:00:00Z").replace("Z", "+00:00")
                            ),
                            period_end=datetime.fromisoformat(
                                attrs_dict.get("period_end", "2025-01-02T00:00:00Z").replace("Z", "+00:00")
                            ),
                            consolidation_level=attrs_dict.get("consolidation_level", "basic"),
                        )

                    # Compress the attributes
                    compression_result = compressor.compress_summary(attrs)
                    compressed_attrs = compression_result.compressed_attributes
                    reduction_ratio = compression_result.reduction_ratio

                    # Convert back to dict and add compression metadata
                    compressed_attrs_dict = compressed_attrs.model_dump(mode="json")
                    compressed_attrs_dict["profound_compressed"] = True
                    compressed_attrs_dict["compression_date"] = now.isoformat()
                    compressed_attrs_dict["compression_ratio"] = reduction_ratio

                    # Update the node in-place
                    cursor.execute(
                        """
                        UPDATE graph_nodes
                        SET attributes_json = ?,
                            version = ?,
                            updated_by = 'tsdb_profound_consolidation',
                            updated_at = ?
                        WHERE node_id = ?
                    """,
                        (json.dumps(compressed_attrs_dict), version + 1, now.isoformat(), node_id),
                    )

                    if cursor.rowcount > 0:
                        compressed_count += 1
                        summaries_compressed += 1
                        total_reduction += reduction_ratio
                        logger.debug(f"Compressed {node_id} by {reduction_ratio:.1%}")

                conn.commit()

                # Calculate new storage usage
                compressed_attrs_list = []
                cursor.execute(
                    """
                    SELECT attributes_json
                    FROM graph_nodes
                    WHERE json_extract(attributes_json, '$.consolidation_level') = 'extensive'
                      AND datetime(json_extract(attributes_json, '$.period_start')) >= datetime(?)
                      AND datetime(json_extract(attributes_json, '$.period_start')) <= datetime(?)
                """,
                    (month_start.isoformat(), month_end.isoformat()),
                )

                for row in cursor.fetchall():
                    attrs_dict = json.loads(row[0]) if row[0] else {}
                    # Convert dict to SummaryAttributes object
                    try:
                        attrs = SummaryAttributes(**attrs_dict)
                        compressed_attrs_list.append(attrs)
                    except Exception as e:
                        logger.warning(
                            f"Failed to convert compressed summary attributes to SummaryAttributes model: {e}"
                        )
                        # Create minimal SummaryAttributes for compatibility
                        attrs = SummaryAttributes(
                            period_start=datetime.fromisoformat(
                                attrs_dict.get("period_start", "2025-01-01T00:00:00Z").replace("Z", "+00:00")
                            ),
                            period_end=datetime.fromisoformat(
                                attrs_dict.get("period_end", "2025-01-02T00:00:00Z").replace("Z", "+00:00")
                            ),
                            consolidation_level=attrs_dict.get("consolidation_level", "basic"),
                        )
                        compressed_attrs_list.append(attrs)

                new_daily_mb = compressor.estimate_daily_size(compressed_attrs_list, days_in_period)
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
                logger.info(
                    f"  - Total reduction: {((storage_before_mb - storage_after_mb) / storage_before_mb * 100):.1f}%"
                )

                # Clean up old basic summaries (> 30 days old)
                cleanup_cutoff = now - timedelta(days=30)
                cursor.execute(
                    """
                    DELETE FROM graph_nodes
                    WHERE json_extract(attributes_json, '$.consolidation_level') = 'basic'
                      AND datetime(json_extract(attributes_json, '$.period_start')) < datetime(?)
                """,
                    (cleanup_cutoff.isoformat(),),
                )

                if cursor.rowcount > 0:
                    logger.info(f"Cleaned up {cursor.rowcount} old basic summaries")
                    conn.commit()

            self._last_profound_consolidation = now

        except Exception as e:
            logger.error(f"Profound consolidation failed: {e}", exc_info=True)
